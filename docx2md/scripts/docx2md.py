#!/usr/bin/env python3
"""
docx2md.py - Convert DOCX files to Markdown with image extraction.

Usage:
    python docx2md.py <input.docx> [--output-dir <dir>] [--images-dir <name>]

No external dependencies - uses only Python stdlib.
"""

import argparse
import os
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

# OOXML Namespaces
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "v": "urn:schemas-microsoft-com:vml",
}


# ---------------------------------------------------------------------------
# Relationship & numbering parsers
# ---------------------------------------------------------------------------

def parse_relationships(zf: zipfile.ZipFile) -> dict:
    """Parse word/_rels/document.xml.rels → {rId: {target, type}}."""
    rels = {}
    try:
        with zf.open("word/_rels/document.xml.rels") as f:
            root = ET.parse(f).getroot()
            for el in root:
                rid = el.get("Id", "")
                target = el.get("Target", "")
                rtype = el.get("Type", "")
                rels[rid] = {"target": target, "type": rtype}
    except KeyError:
        pass
    return rels


def parse_numbering(zf: zipfile.ZipFile) -> dict:
    """Parse word/numbering.xml → {numId: {ilvl: numFmt}}."""
    numbering: dict[str, dict[str, str]] = {}
    abstract_nums: dict[str, dict[str, str]] = {}

    try:
        with zf.open("word/numbering.xml") as f:
            root = ET.parse(f).getroot()

        w = NS["w"]

        # Abstract numbering definitions
        for abstract in root.findall(f".//{{{w}}}abstractNum"):
            aid = abstract.get(f"{{{w}}}abstractNumId", "")
            levels: dict[str, str] = {}
            for lvl in abstract.findall(f"{{{w}}}lvl"):
                ilvl = lvl.get(f"{{{w}}}ilvl", "0")
                fmt_el = lvl.find(f"{{{w}}}numFmt")
                fmt = fmt_el.get(f"{{{w}}}val", "bullet") if fmt_el is not None else "bullet"
                levels[ilvl] = fmt
            abstract_nums[aid] = levels

        # Concrete numbering instances
        for num in root.findall(f".//{{{w}}}num"):
            nid = num.get(f"{{{w}}}numId", "")
            aref = num.find(f"{{{w}}}abstractNumId")
            if aref is not None:
                aid = aref.get(f"{{{w}}}val", "")
                if aid in abstract_nums:
                    numbering[nid] = abstract_nums[aid]
    except KeyError:
        pass

    return numbering


def parse_styles(zf: zipfile.ZipFile) -> dict:
    """Parse word/styles.xml → {styleId: {name, basedOn}} for heading detection."""
    styles: dict[str, dict] = {}
    try:
        with zf.open("word/styles.xml") as f:
            root = ET.parse(f).getroot()

        w = NS["w"]
        for style in root.findall(f".//{{{w}}}style"):
            sid = style.get(f"{{{w}}}styleId", "")
            name_el = style.find(f"{{{w}}}name")
            name = name_el.get(f"{{{w}}}val", "") if name_el is not None else ""
            based_el = style.find(f"{{{w}}}basedOn")
            based = based_el.get(f"{{{w}}}val", "") if based_el is not None else ""
            styles[sid] = {"name": name, "basedOn": based}
    except KeyError:
        pass
    return styles


# ---------------------------------------------------------------------------
# Image extraction
# ---------------------------------------------------------------------------

def extract_images(zf: zipfile.ZipFile, output_dir: Path, images_dir_name: str) -> dict:
    """Extract word/media/* → output_dir/images_dir_name/. Return {media/x: relative_path}."""
    images_dir = output_dir / images_dir_name
    extracted: dict[str, str] = {}

    for name in zf.namelist():
        if name.startswith("word/media/"):
            filename = os.path.basename(name)
            if not filename:
                continue
            images_dir.mkdir(parents=True, exist_ok=True)
            target = images_dir / filename
            with zf.open(name) as src, open(target, "wb") as dst:
                dst.write(src.read())
            # key = path relative to word/ (used in rels targets)
            extracted[name.replace("word/", "", 1)] = f"{images_dir_name}/{filename}"

    return extracted


# ---------------------------------------------------------------------------
# Inline content helpers
# ---------------------------------------------------------------------------

def _image_from_blip(blip, rels, image_map, drawing_or_pict):
    """Return markdown image string from a:blip element, or ''."""
    embed = blip.get(f'{{{NS["r"]}}}embed', "")
    if not embed or embed not in rels:
        return ""
    target = rels[embed]["target"]
    if target not in image_map:
        return ""
    img_path = image_map[target]
    alt = ""
    # Try to grab alt text from ancestor drawing's docPr
    for docpr in drawing_or_pict.iter(f'{{{NS["wp"]}}}docPr'):
        alt = docpr.get("descr", "") or docpr.get("name", "")
    return f"![{alt}]({img_path})"


def _images_from_element(el, rels, image_map):
    """Yield markdown image strings found anywhere inside *el*."""
    # Drawing (modern)
    for drawing in el.iter(f'{{{NS["w"]}}}drawing'):
        for blip in drawing.iter(f'{{{NS["a"]}}}blip'):
            md = _image_from_blip(blip, rels, image_map, drawing)
            if md:
                yield md
    # VML / pict (legacy)
    for pict in el.iter(f'{{{NS["w"]}}}pict'):
        for imgdata in pict.iter(f'{{{NS["v"]}}}imagedata'):
            rid = imgdata.get(f'{{{NS["r"]}}}id', "")
            if rid and rid in rels:
                target = rels[rid]["target"]
                if target in image_map:
                    yield f"![image]({image_map[target]})"


def get_run_text(run, rels, image_map):
    """Convert a <w:r> element into a Markdown fragment."""
    parts: list[str] = []
    rpr = run.find("w:rPr", NS)

    # Formatting flags
    is_bold = rpr is not None and rpr.find("w:b", NS) is not None
    is_italic = rpr is not None and rpr.find("w:i", NS) is not None
    is_strike = rpr is not None and rpr.find("w:strike", NS) is not None
    is_code = False
    if rpr is not None:
        rfonts = rpr.find("w:rFonts", NS)
        if rfonts is not None:
            ascii_font = rfonts.get(f'{{{NS["w"]}}}ascii', "").lower()
            if any(kw in ascii_font for kw in ("mono", "courier", "consolas")):
                is_code = True

    # Text
    for t in run.findall("w:t", NS):
        parts.append(t.text or "")

    # Tab / break
    for _ in run.findall("w:tab", NS):
        parts.append("\t")
    for br in run.findall("w:br", NS):
        if br.get(f'{{{NS["w"]}}}type', "") == "page":
            parts.append("\n\n---\n\n")
        else:
            parts.append("\n")

    # Inline images
    for md_img in _images_from_element(run, rels, image_map):
        parts.append(md_img)

    text = "".join(parts)
    if not text:
        return ""

    # Apply formatting (code first to avoid nesting issues)
    if is_code:
        text = f"`{text}`"
    elif is_bold and is_italic:
        text = f"***{text}***"
    elif is_bold:
        text = f"**{text}**"
    elif is_italic:
        text = f"*{text}*"
    if is_strike:
        text = f"~~{text}~~"

    return text


# ---------------------------------------------------------------------------
# Heading detection
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"[Hh]eading\s*(\d+)")


def get_heading_level(style_val: str, styles: dict) -> int:
    """Return 1-6 for headings, 0 otherwise."""
    if not style_val:
        return 0
    # Direct match on style ID
    m = _HEADING_RE.match(style_val)
    if m:
        return min(int(m.group(1)), 6)
    low = style_val.lower()
    if low == "title":
        return 1
    if low == "subtitle":
        return 2
    # Lookup via styles.xml name
    if style_val in styles:
        name = styles[style_val].get("name", "")
        m = _HEADING_RE.match(name)
        if m:
            return min(int(m.group(1)), 6)
        if name.lower() == "title":
            return 1
        if name.lower() == "subtitle":
            return 2
    return 0


# ---------------------------------------------------------------------------
# Paragraph & table processors
# ---------------------------------------------------------------------------

def process_paragraph(para, rels, image_map, numbering, styles, list_counters):
    """Convert <w:p> → Markdown line."""
    w = NS["w"]
    ppr = para.find("w:pPr", NS)

    # Style
    style_val = ""
    if ppr is not None:
        se = ppr.find("w:pStyle", NS)
        if se is not None:
            style_val = se.get(f"{{{w}}}val", "")

    heading_level = get_heading_level(style_val, styles)

    # List detection
    is_list = False
    list_prefix = ""
    if ppr is not None:
        num_pr = ppr.find("w:numPr", NS)
        if num_pr is not None:
            ilvl_el = num_pr.find("w:ilvl", NS)
            nid_el = num_pr.find("w:numId", NS)
            ilvl = ilvl_el.get(f"{{{w}}}val", "0") if ilvl_el is not None else "0"
            nid = nid_el.get(f"{{{w}}}val", "") if nid_el is not None else ""
            if nid and nid != "0":
                is_list = True
                indent = "  " * int(ilvl)
                num_fmt = "bullet"
                if nid in numbering and ilvl in numbering[nid]:
                    num_fmt = numbering[nid][ilvl]
                if num_fmt in ("bullet", "none"):
                    list_prefix = f"{indent}- "
                else:
                    key = f"{nid}_{ilvl}"
                    list_counters[key] = list_counters.get(key, 0) + 1
                    list_prefix = f"{indent}{list_counters[key]}. "

    # Collect inline content
    parts: list[str] = []
    for child in para:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

        if tag == "r":
            parts.append(get_run_text(child, rels, image_map))

        elif tag == "hyperlink":
            rid = child.get(f'{{{NS["r"]}}}id', "")
            href = rels[rid]["target"] if rid and rid in rels else ""
            link_parts = [get_run_text(r, rels, image_map) for r in child.findall("w:r", NS)]
            link_text = "".join(link_parts)
            parts.append(f"[{link_text}]({href})" if href else link_text)

        elif tag in ("pPr", "bookmarkStart", "bookmarkEnd", "proofErr"):
            pass

        elif tag == "AlternateContent":
            for md_img in _images_from_element(child, rels, image_map):
                parts.append(md_img)

    text = "".join(parts).strip()
    if not text:
        return "", is_list

    if heading_level > 0:
        return f"{'#' * heading_level} {text}", False
    if is_list:
        return f"{list_prefix}{text}", True
    return text, False


def process_table(table, rels, image_map, numbering, styles, list_counters):
    """Convert <w:tbl> → Markdown table."""
    rows: list[list[str]] = []
    for tr in table.findall("w:tr", NS):
        cells: list[str] = []
        for tc in tr.findall("w:tc", NS):
            cell_parts: list[str] = []
            for p in tc.findall("w:p", NS):
                t, _ = process_paragraph(p, rels, image_map, numbering, styles, list_counters)
                if t:
                    cell_parts.append(t)
            cells.append(" ".join(cell_parts).replace("|", "\\|"))
        rows.append(cells)

    if not rows:
        return ""

    max_cols = max(len(r) for r in rows)
    for row in rows:
        while len(row) < max_cols:
            row.append("")

    lines = [
        "| " + " | ".join(rows[0]) + " |",
        "| " + " | ".join(["---"] * max_cols) + " |",
    ]
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main converter
# ---------------------------------------------------------------------------

def convert(docx_path: str, output_dir: str | None = None, images_dir_name: str = "images") -> str | None:
    docx = Path(docx_path)
    # 默认输出到以文件名命名的子目录，避免与其它文件混淆
    out = Path(output_dir) if output_dir else docx.parent / docx.stem
    out.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(docx, "r") as zf:
        rels = parse_relationships(zf)
        numbering = parse_numbering(zf)
        styles = parse_styles(zf)
        image_map = extract_images(zf, out, images_dir_name)

        with zf.open("word/document.xml") as f:
            root = ET.parse(f).getroot()

    body = root.find("w:body", NS)
    if body is None:
        print("Error: <w:body> not found in document.xml", file=sys.stderr)
        return None

    md_parts: list[str] = []
    list_counters: dict[str, int] = {}
    prev_was_list = False

    for el in body:
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag

        if tag == "p":
            text, is_list = process_paragraph(el, rels, image_map, numbering, styles, list_counters)
            if not is_list and prev_was_list:
                list_counters.clear()
            prev_was_list = is_list
            md_parts.append(text if text else "")

        elif tag == "tbl":
            text = process_table(el, rels, image_map, numbering, styles, list_counters)
            if text:
                md_parts.append(text)
            prev_was_list = False

        elif tag == "sdt":
            content = el.find("w:sdtContent", NS)
            if content is not None:
                for child in content:
                    ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if ctag == "p":
                        text, _ = process_paragraph(child, rels, image_map, numbering, styles, list_counters)
                        if text:
                            md_parts.append(text)
                    elif ctag == "tbl":
                        text = process_table(child, rels, image_map, numbering, styles, list_counters)
                        if text:
                            md_parts.append(text)
            prev_was_list = False

    # Collapse multiple blank lines
    markdown = "\n\n".join(md_parts)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    markdown = markdown.strip() + "\n"

    md_path = out / (docx.stem + ".md")
    md_path.write_text(markdown, encoding="utf-8")

    img_count = len(image_map)
    print(f"Converted: {docx.name} -> {md_path}")
    if img_count > 0:
        print(f"Extracted {img_count} image(s) to {out / images_dir_name}/")

    return str(md_path)


def main():
    ap = argparse.ArgumentParser(description="Convert DOCX to Markdown with image extraction")
    ap.add_argument("input", help="Path to the DOCX file")
    ap.add_argument("--output-dir", "-o", help="Output directory (default: same as input)")
    ap.add_argument("--images-dir", "-i", default="images", help="Images subdirectory name (default: images)")
    args = ap.parse_args()

    if not os.path.isfile(args.input):
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    result = convert(args.input, args.output_dir, args.images_dir)
    if result is None:
        sys.exit(1)


if __name__ == "__main__":
    main()
