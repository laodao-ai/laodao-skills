#!/usr/bin/env python3
"""
xlsx2csv.py - Convert XLSX files to CSV with image extraction.

Usage:
    python xlsx2csv.py <input.xlsx> [--output-dir <dir>] [--images-dir <name>]
                                    [--sheet <name_or_index>] [--encoding <enc>]

No external dependencies - uses only Python stdlib.
"""

import argparse
import csv
import os
import re
import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

# OOXML Namespaces
NS = {
    "ss": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}

# Excel epoch: 1899-12-30 (because of the 1900 leap year bug)
_EXCEL_EPOCH = datetime(1899, 12, 30)

# Number format IDs that indicate date/time values
_DATE_FMT_IDS = {
    14, 15, 16, 17, 18, 19, 20, 21, 22,  # built-in date formats
    27, 28, 29, 30, 31, 32, 33, 34, 35, 36,  # CJK date formats
    45, 46, 47,  # time formats
    50, 51, 52, 53, 54, 55, 56, 57, 58,  # more CJK dates
}

# Patterns in custom format strings that suggest date/time
_DATE_FMT_PATTERN = re.compile(r"[ymdhs]", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    """Parse xl/sharedStrings.xml → list of strings."""
    strings: list[str] = []
    try:
        with zf.open("xl/sharedStrings.xml") as f:
            root = ET.parse(f).getroot()
        ss = NS["ss"]
        for si in root.findall(f"{{{ss}}}si"):
            # Simple string: <si><t>text</t></si>
            t = si.find(f"{{{ss}}}t")
            if t is not None and t.text is not None:
                strings.append(t.text)
                continue
            # Rich text: <si><r><t>part1</t></r><r><t>part2</t></r></si>
            parts: list[str] = []
            for r in si.findall(f"{{{ss}}}r"):
                t = r.find(f"{{{ss}}}t")
                if t is not None and t.text is not None:
                    parts.append(t.text)
            strings.append("".join(parts))
    except KeyError:
        pass
    return strings


def parse_workbook(zf: zipfile.ZipFile) -> list[dict]:
    """Parse xl/workbook.xml → [{name, sheetId, rId}]."""
    sheets: list[dict] = []
    try:
        with zf.open("xl/workbook.xml") as f:
            root = ET.parse(f).getroot()
        ss = NS["ss"]
        r = NS["r"]
        for s in root.findall(f".//{{{ss}}}sheet"):
            sheets.append({
                "name": s.get("name", ""),
                "sheetId": s.get("sheetId", ""),
                "rId": s.get(f"{{{r}}}id", ""),
            })
    except KeyError:
        pass
    return sheets


def parse_workbook_rels(zf: zipfile.ZipFile) -> dict:
    """Parse xl/_rels/workbook.xml.rels → {rId: target}."""
    rels: dict[str, str] = {}
    try:
        with zf.open("xl/_rels/workbook.xml.rels") as f:
            root = ET.parse(f).getroot()
        for el in root:
            rid = el.get("Id", "")
            target = el.get("Target", "")
            rels[rid] = target
    except KeyError:
        pass
    return rels


def parse_styles(zf: zipfile.ZipFile) -> dict:
    """Parse xl/styles.xml → {xfIndex: is_date}."""
    date_xfs: dict[int, bool] = {}
    custom_fmts: dict[str, str] = {}  # numFmtId -> formatCode

    try:
        with zf.open("xl/styles.xml") as f:
            root = ET.parse(f).getroot()
        ss = NS["ss"]

        # Custom number formats
        for fmt in root.findall(f".//{{{ss}}}numFmt"):
            fid = fmt.get("numFmtId", "")
            code = fmt.get("formatCode", "")
            custom_fmts[fid] = code

        # Cell xfs (the style index applied to cells)
        cell_xfs = root.find(f"{{{ss}}}cellXfs")
        if cell_xfs is not None:
            for i, xf in enumerate(cell_xfs.findall(f"{{{ss}}}xf")):
                fmt_id_str = xf.get("numFmtId", "0")
                fmt_id = int(fmt_id_str)

                is_date = False
                if fmt_id in _DATE_FMT_IDS:
                    is_date = True
                elif fmt_id_str in custom_fmts:
                    code = custom_fmts[fmt_id_str]
                    # Check if format string contains date/time patterns
                    # but not if it's purely a number format
                    cleaned = re.sub(r'"[^"]*"', "", code)  # remove quoted strings
                    cleaned = re.sub(r"\[[^\]]*\]", "", cleaned)  # remove conditions
                    if _DATE_FMT_PATTERN.search(cleaned):
                        is_date = True

                date_xfs[i] = is_date
    except KeyError:
        pass

    return date_xfs


def excel_date_to_str(value: float) -> str:
    """Convert Excel serial date number to string."""
    try:
        val = float(value)
    except (ValueError, TypeError):
        return str(value)

    if val < 0:
        return str(value)

    # Excel 1900 leap year bug: day 60 = 1900-02-29 (doesn't exist)
    if val >= 61:
        val -= 1  # adjust for the bug

    days = int(val)
    frac = val - days

    dt = _EXCEL_EPOCH + timedelta(days=days)

    if frac > 0.0001:  # has time component
        total_seconds = round(frac * 86400)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{dt.strftime('%Y-%m-%d')} {hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return dt.strftime("%Y-%m-%d")


def col_letter_to_index(col: str) -> int:
    """Convert column letter (A, B, ..., Z, AA, ...) to 0-based index."""
    result = 0
    for c in col.upper():
        result = result * 26 + (ord(c) - ord("A") + 1)
    return result - 1


_CELL_REF_RE = re.compile(r"^([A-Z]+)(\d+)$")


def parse_cell_ref(ref: str) -> tuple[int, int]:
    """Parse cell reference like 'B3' → (row=2, col=1) (0-based)."""
    m = _CELL_REF_RE.match(ref)
    if not m:
        return 0, 0
    col = col_letter_to_index(m.group(1))
    row = int(m.group(2)) - 1
    return row, col


def parse_sheet(zf: zipfile.ZipFile, sheet_path: str, shared_strings: list[str],
                date_xfs: dict) -> list[list[str]]:
    """Parse a sheet XML → 2D list of string values."""
    ss = NS["ss"]

    try:
        with zf.open(sheet_path) as f:
            root = ET.parse(f).getroot()
    except KeyError:
        return []

    rows_data: dict[int, dict[int, str]] = {}
    max_row = 0
    max_col = 0

    for row_el in root.findall(f".//{{{ss}}}row"):
        for cell in row_el.findall(f"{{{ss}}}c"):
            ref = cell.get("r", "")
            if not ref:
                continue

            row_idx, col_idx = parse_cell_ref(ref)
            max_row = max(max_row, row_idx)
            max_col = max(max_col, col_idx)

            cell_type = cell.get("t", "")
            style_idx = int(cell.get("s", "0"))
            v_el = cell.find(f"{{{ss}}}v")
            value = ""

            if cell_type == "s":
                # Shared string
                if v_el is not None and v_el.text is not None:
                    idx = int(v_el.text)
                    if 0 <= idx < len(shared_strings):
                        value = shared_strings[idx]
            elif cell_type == "inlineStr":
                # Inline string
                is_el = cell.find(f"{{{ss}}}is")
                if is_el is not None:
                    t = is_el.find(f"{{{ss}}}t")
                    if t is not None and t.text is not None:
                        value = t.text
            elif cell_type == "b":
                # Boolean
                if v_el is not None and v_el.text is not None:
                    value = "TRUE" if v_el.text == "1" else "FALSE"
            elif cell_type == "e":
                # Error
                if v_el is not None and v_el.text is not None:
                    value = v_el.text
            else:
                # Number or formula result
                if v_el is not None and v_el.text is not None:
                    raw = v_el.text
                    # Check if this is a date format
                    if date_xfs.get(style_idx, False):
                        value = excel_date_to_str(raw)
                    else:
                        value = raw

            if row_idx not in rows_data:
                rows_data[row_idx] = {}
            rows_data[row_idx][col_idx] = value

    # Build 2D array
    if not rows_data:
        return []

    result: list[list[str]] = []
    for r in range(max_row + 1):
        row: list[str] = []
        for c in range(max_col + 1):
            row.append(rows_data.get(r, {}).get(c, ""))
        result.append(row)

    # Trim trailing empty rows
    while result and all(cell == "" for cell in result[-1]):
        result.pop()

    # Trim trailing empty columns
    if result:
        while max_col >= 0 and all(row[max_col] == "" for row in result if max_col < len(row)):
            max_col -= 1
            for row in result:
                if len(row) > max_col + 1:
                    row.pop()

    return result


# ---------------------------------------------------------------------------
# Image extraction
# ---------------------------------------------------------------------------

def extract_images(zf: zipfile.ZipFile, output_dir: Path, images_dir_name: str) -> int:
    """Extract xl/media/* → output_dir/images_dir_name/. Return count."""
    images_dir = output_dir / images_dir_name
    count = 0

    for name in zf.namelist():
        if name.startswith("xl/media/"):
            filename = os.path.basename(name)
            if not filename:
                continue
            images_dir.mkdir(parents=True, exist_ok=True)
            target = images_dir / filename
            with zf.open(name) as src, open(target, "wb") as dst:
                dst.write(src.read())
            count += 1

    return count


# ---------------------------------------------------------------------------
# Main converter
# ---------------------------------------------------------------------------

def convert(xlsx_path: str, output_dir: str | None = None,
            images_dir_name: str = "images", sheet_filter: str | None = None,
            encoding: str = "utf-8-sig") -> str | None:
    xlsx = Path(xlsx_path)
    out = Path(output_dir) if output_dir else xlsx.parent / xlsx.stem
    out.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(xlsx, "r") as zf:
        shared_strings = parse_shared_strings(zf)
        sheets = parse_workbook(zf)
        rels = parse_workbook_rels(zf)
        date_xfs = parse_styles(zf)
        img_count = extract_images(zf, out, images_dir_name)

        # Determine which sheets to export
        target_sheets: list[dict] = []
        if sheet_filter is not None:
            # Try as index first
            try:
                idx = int(sheet_filter)
                if 0 <= idx < len(sheets):
                    target_sheets = [sheets[idx]]
            except ValueError:
                pass
            # Try as name
            if not target_sheets:
                for s in sheets:
                    if s["name"] == sheet_filter:
                        target_sheets = [s]
                        break
            if not target_sheets:
                print(f"Error: Sheet '{sheet_filter}' not found. Available: {[s['name'] for s in sheets]}",
                      file=sys.stderr)
                return None
        else:
            target_sheets = sheets

        multi_sheet = len(target_sheets) > 1
        csv_files: list[str] = []

        for sheet_info in target_sheets:
            rid = sheet_info["rId"]
            target = rels.get(rid, "")
            if not target:
                continue

            # Build full path in zip
            sheet_path = f"xl/{target}" if not target.startswith("xl/") else target
            # Normalize path (handle ../worksheets/sheet1.xml etc.)
            sheet_path = sheet_path.replace("\\", "/")
            if "/../" in sheet_path or target.startswith("/"):
                # Relative path resolution
                parts = sheet_path.split("/")
                resolved: list[str] = []
                for p in parts:
                    if p == "..":
                        if resolved:
                            resolved.pop()
                    elif p and p != ".":
                        resolved.append(p)
                sheet_path = "/".join(resolved)

            data = parse_sheet(zf, sheet_path, shared_strings, date_xfs)

            # Determine CSV filename
            if multi_sheet:
                safe_name = re.sub(r'[\\/:*?"<>|]', "_", sheet_info["name"])
                csv_name = f"{xlsx.stem}__{safe_name}.csv"
            else:
                csv_name = f"{xlsx.stem}.csv"

            csv_path = out / csv_name
            with open(csv_path, "w", newline="", encoding=encoding) as f:
                writer = csv.writer(f)
                for row in data:
                    writer.writerow(row)

            csv_files.append(str(csv_path))
            print(f"  Sheet '{sheet_info['name']}' -> {csv_path}")

    print(f"\nConverted: {xlsx.name} -> {out}/")
    print(f"  {len(csv_files)} CSV file(s) generated")
    if img_count > 0:
        print(f"  {img_count} image(s) extracted to {out / images_dir_name}/")

    return str(out)


def main():
    ap = argparse.ArgumentParser(description="Convert XLSX to CSV with image extraction")
    ap.add_argument("input", help="Path to the XLSX file")
    ap.add_argument("--output-dir", "-o", help="Output directory (default: subdirectory named after input)")
    ap.add_argument("--images-dir", "-i", default="images", help="Images subdirectory name (default: images)")
    ap.add_argument("--sheet", "-s", default=None, help="Export specific sheet (name or 0-based index)")
    ap.add_argument("--encoding", "-e", default="utf-8-sig",
                    help="CSV encoding (default: utf-8-sig, Excel-friendly UTF-8 with BOM)")
    args = ap.parse_args()

    if not os.path.isfile(args.input):
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    result = convert(args.input, args.output_dir, args.images_dir, args.sheet, args.encoding)
    if result is None:
        sys.exit(1)


if __name__ == "__main__":
    main()
