#!/usr/bin/env python3
"""
PDF to Markdown converter with image extraction.

Usage:
    python pdf2md.py <input.pdf> [--output <output.md>] [--image-dir <dir>]

Dependencies:
    pip install pymupdf Pillow
"""

import argparse
import hashlib
import io
import os
import re
import sys
from pathlib import Path

try:
    import pymupdf
except ImportError:
    print("ERROR: pymupdf is not installed. Run: pip install pymupdf", file=sys.stderr)
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    Image = None


def extract_images(page, image_dir: Path, page_num: int, prefix: str) -> dict:
    """Extract images from a page, save to disk, return xref->relative_path mapping."""
    mapping = {}
    image_list = page.get_images(full=True)
    for img_index, img_info in enumerate(image_list):
        xref = img_info[0]
        if xref in mapping:
            continue
        try:
            base_image = page.parent.extract_image(xref)
            if not base_image:
                continue
            img_bytes = base_image["image"]
            ext = base_image.get("ext", "png")
            if ext == "jpeg":
                ext = "jpg"

            # Use content hash for dedup
            content_hash = hashlib.md5(img_bytes).hexdigest()[:8]
            filename = f"{prefix}_p{page_num + 1}_{img_index + 1}_{content_hash}.{ext}"
            filepath = image_dir / filename

            # Skip tiny images (likely decorations/icons < 20x20)
            width = base_image.get("width", 0)
            height = base_image.get("height", 0)
            if width < 20 and height < 20:
                continue

            # Optimize large images
            if Image and ext in ("png", "jpg", "jpeg") and len(img_bytes) > 500_000:
                try:
                    img = Image.open(io.BytesIO(img_bytes))
                    max_dim = 1600
                    if img.width > max_dim or img.height > max_dim:
                        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
                    buf = io.BytesIO()
                    if ext == "png":
                        img.save(buf, format="PNG", optimize=True)
                    else:
                        img.save(buf, format="JPEG", quality=85, optimize=True)
                    img_bytes = buf.getvalue()
                except Exception:
                    pass  # Fall back to original bytes

            filepath.write_bytes(img_bytes)
            rel_path = filepath.name
            mapping[xref] = rel_path
        except Exception as e:
            print(f"  Warning: failed to extract image xref={xref}: {e}", file=sys.stderr)
    return mapping


def guess_heading_level(block_dict, page_font_stats: dict) -> int:
    """Guess heading level based on font size relative to body text."""
    if "lines" not in block_dict:
        return 0
    max_size = 0
    for line in block_dict["lines"]:
        for span in line["spans"]:
            max_size = max(max_size, span["size"])

    body_size = page_font_stats.get("body_size", 12)
    if max_size >= body_size * 1.8:
        return 1
    elif max_size >= body_size * 1.4:
        return 2
    elif max_size >= body_size * 1.15:
        return 3
    return 0


def compute_font_stats(page) -> dict:
    """Compute the most common (body) font size on a page."""
    size_counts = {}
    blocks = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)["blocks"]
    for b in blocks:
        if b["type"] != 0:
            continue
        for line in b.get("lines", []):
            for span in line["spans"]:
                s = round(span["size"], 1)
                text_len = len(span["text"].strip())
                size_counts[s] = size_counts.get(s, 0) + text_len
    if not size_counts:
        return {"body_size": 12}
    body_size = max(size_counts, key=size_counts.get)
    return {"body_size": body_size}


def is_bold(span: dict) -> bool:
    """Check if a span is bold based on font name."""
    font = span.get("font", "").lower()
    return "bold" in font or "heavy" in font or "black" in font


def block_to_markdown(block_dict, heading_level: int) -> str:
    """Convert a text block to markdown."""
    if "lines" not in block_dict:
        return ""

    lines_text = []
    for line in block_dict["lines"]:
        spans_text = []
        for span in line["spans"]:
            text = span["text"]
            if not text:
                continue
            if is_bold(span) and text.strip():
                text = f"**{text.strip()}** "
            spans_text.append(text)
        line_str = "".join(spans_text).rstrip()
        if line_str:
            lines_text.append(line_str)

    if not lines_text:
        return ""

    combined = "\n".join(lines_text)

    if heading_level > 0:
        # For headings, join lines with space (headings shouldn't be multiline)
        single_line = " ".join(lines_text)
        # Remove bold markers from headings (redundant)
        single_line = single_line.replace("**", "")
        return f"{'#' * heading_level} {single_line}"

    return combined


def extract_tables(page) -> list:
    """Try to find and extract tables from a page using pymupdf's table finder."""
    try:
        tables = page.find_tables()
        if not tables or len(tables.tables) == 0:
            return []
        result = []
        for table in tables:
            extracted = table.extract()
            if extracted and len(extracted) > 0:
                result.append({"bbox": table.bbox, "data": extracted})
        return result
    except Exception:
        return []


def table_to_markdown(table_data: list) -> str:
    """Convert extracted table data to markdown table."""
    if not table_data or len(table_data) == 0:
        return ""

    # Clean cells
    cleaned = []
    for row in table_data:
        cleaned_row = []
        for cell in row:
            if cell is None:
                cleaned_row.append("")
            else:
                cleaned_row.append(str(cell).replace("\n", " ").strip())
        cleaned_row.append("")
        cleaned.append(cleaned_row)

    if not cleaned:
        return ""

    # Calculate column widths
    num_cols = max(len(row) for row in cleaned)
    col_widths = [3] * num_cols
    for row in cleaned:
        for i, cell in enumerate(row):
            if i < num_cols:
                col_widths[i] = max(col_widths[i], len(cell))

    lines = []
    # Header
    header = cleaned[0] if cleaned else [""] * num_cols
    while len(header) < num_cols:
        header.append("")
    header_line = "| " + " | ".join(
        cell.ljust(col_widths[i]) for i, cell in enumerate(header[:num_cols])
    ) + " |"
    lines.append(header_line)

    # Separator
    sep_line = "| " + " | ".join("-" * col_widths[i] for i in range(num_cols)) + " |"
    lines.append(sep_line)

    # Data rows
    for row in cleaned[1:]:
        while len(row) < num_cols:
            row.append("")
        data_line = "| " + " | ".join(
            cell.ljust(col_widths[i]) for i, cell in enumerate(row[:num_cols])
        ) + " |"
        lines.append(data_line)

    return "\n".join(lines)


def bbox_overlap(bbox1, bbox2, threshold=0.5) -> bool:
    """Check if bbox1 significantly overlaps with bbox2."""
    x0 = max(bbox1[0], bbox2[0])
    y0 = max(bbox1[1], bbox2[1])
    x1 = min(bbox1[2], bbox2[2])
    y1 = min(bbox1[3], bbox2[3])

    if x0 >= x1 or y0 >= y1:
        return False

    overlap_area = (x1 - x0) * (y1 - y0)
    bbox1_area = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
    if bbox1_area == 0:
        return False

    return (overlap_area / bbox1_area) >= threshold


def convert_page(page, page_num: int, image_dir: Path, prefix: str) -> str:
    """Convert a single page to markdown."""
    font_stats = compute_font_stats(page)
    image_map = extract_images(page, image_dir, page_num, prefix)

    # Get tables
    tables = extract_tables(page)
    table_bboxes = [t["bbox"] for t in tables]

    # Get all blocks (text + image references)
    blocks = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)["blocks"]

    # Sort blocks by vertical position
    blocks.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))

    md_parts = []
    used_tables = set()

    for block in blocks:
        block_bbox = block["bbox"]

        # Check if this block overlaps with a table
        in_table = False
        for ti, tbbox in enumerate(table_bboxes):
            if bbox_overlap(block_bbox, tbbox):
                if ti not in used_tables:
                    used_tables.add(ti)
                    table_md = table_to_markdown(tables[ti]["data"])
                    if table_md:
                        md_parts.append(table_md)
                in_table = True
                break

        if in_table:
            continue

        if block["type"] == 0:  # Text block
            heading = guess_heading_level(block, font_stats)
            text = block_to_markdown(block, heading)
            if text.strip():
                md_parts.append(text)
        elif block["type"] == 1:  # Image block
            xref = block.get("xref", None)
            # Try to find matching extracted image
            if xref and xref in image_map:
                rel_path = image_map[xref]
                md_parts.append(f"![image]({rel_path})")
            else:
                # Image might have been extracted via get_images
                # Check all images on this page
                for xr, rel_path in image_map.items():
                    md_parts.append(f"![image]({rel_path})")
                    image_map.clear()
                    break

    # If there are remaining images not placed in text flow, append at end
    remaining = [p for xr, p in image_map.items()]
    for rel_path in remaining:
        if not any(rel_path in part for part in md_parts):
            md_parts.append(f"![image]({rel_path})")

    return "\n\n".join(md_parts)


def postprocess_markdown(md: str) -> str:
    """Fix common formatting issues in the converted markdown."""

    # 1. Remove zero-width spaces (U+200B) and other invisible chars
    md = md.replace('\u200b', '')
    md = md.replace('\u200c', '')
    md = md.replace('\u200d', '')
    md = md.replace('\ufeff', '')

    # 2. Remove "代码块" / "代码块​" labels (artifact from PDF code block rendering)
    md = re.sub(r'^代码块\s*$', '', md, flags=re.MULTILINE)

    # 3. Wrap ASCII art (box-drawing characters) in code blocks and strip line numbers.
    #    Detect consecutive lines containing box-drawing chars: ┌┐└┘├┤┬┴┼─│═║
    box_chars = r'[┌┐└┘├┤┬┴┼─│═║╔╗╚╝╠╣╦╩╬]'

    def wrap_ascii_art(md_text: str) -> str:
        lines = md_text.split('\n')
        result = []
        art_block = []
        in_art = False

        for line in lines:
            stripped = line.strip()
            is_art_line = bool(re.search(box_chars, stripped))
            # Line numbers between art lines: a line that is just a number (1-999)
            is_line_number = bool(re.match(r'^\d{1,3}$', stripped))

            if is_art_line:
                if not in_art:
                    in_art = True
                    art_block = []
                    # Remove trailing standalone line numbers and blanks before the art block
                    changed = True
                    while changed:
                        changed = False
                        if result and re.match(r'^\d{1,3}$', result[-1].strip()):
                            result.pop()
                            changed = True
                        elif result and result[-1].strip() == '':
                            result.pop()
                            changed = True
                    result.append('')
                art_block.append(stripped)
            elif in_art and (is_line_number or stripped == ''):
                # Skip line numbers and blank lines within art blocks
                continue
            else:
                if in_art:
                    # End of art block — flush it
                    result.append('```')
                    result.extend(art_block)
                    result.append('```')
                    result.append('')
                    in_art = False
                    art_block = []
                result.append(line)

        # Flush remaining art block
        if in_art and art_block:
            result.append('```')
            result.extend(art_block)
            result.append('```')

        return '\n'.join(result)

    md = wrap_ascii_art(md)

    # 4. Wrap JSON blocks in ```json code fences and strip line numbers.
    #    Detect blocks starting with { and ending with }
    def wrap_json_blocks(md_text: str) -> str:
        lines = md_text.split('\n')
        result = []
        json_block = []
        in_json = False
        brace_depth = 0

        i = 0
        while i < len(lines):
            stripped = lines[i].strip()

            if not in_json:
                # Detect JSON start: a line that is just "{"
                if stripped == '{':
                    in_json = True
                    json_block = [stripped]
                    brace_depth = 1
                    # Remove trailing standalone line numbers and blanks before JSON block
                    changed = True
                    while changed:
                        changed = False
                        if result and re.match(r'^\d{1,3}$', result[-1].strip()):
                            result.pop()
                            changed = True
                        elif result and result[-1].strip() == '':
                            result.pop()
                            changed = True
                    result.append('')
                    i += 1
                    continue
                else:
                    result.append(lines[i])
            else:
                # Skip line numbers (standalone digits)
                if re.match(r'^\d{1,3}$', stripped):
                    i += 1
                    continue
                if stripped == '':
                    i += 1
                    continue

                json_block.append(stripped)
                brace_depth += stripped.count('{') - stripped.count('}')

                if brace_depth <= 0:
                    # End of JSON block
                    result.append('```json')
                    result.extend(json_block)
                    result.append('```')
                    result.append('')
                    json_block = []
                    in_json = False

            i += 1

        # Flush unclosed JSON (shouldn't happen, but be safe)
        if in_json and json_block:
            result.append('```json')
            result.extend(json_block)
            result.append('```')

        return '\n'.join(result)

    md = wrap_json_blocks(md)

    # 5. Fix bullet points misidentified as headings: "### • xxx" -> "- xxx"
    md = re.sub(r'^#{1,6}\s*[•·]\s*', '- ', md, flags=re.MULTILINE)

    # 6. Fix sub-items misidentified as headings: "## ◦ xxx" -> "  - xxx"
    md = re.sub(r'^#{1,6}\s*◦\s*', '   - ', md, flags=re.MULTILINE)

    # 7. Remove stray page-break horizontal rules (--- between numbered list items)
    #    Pattern: numbered item, then ---, then next numbered item
    md = re.sub(r'(\n\d+\.\s+.+)\n\n---\n\n(\d+\.\s+)', r'\1\n\2', md)

    # 8. Remove duplicate page-break --- that appear before/after table headers or section breaks
    #    (consecutive --- with only whitespace between)
    md = re.sub(r'(\n---\n)\s*\n---\n', r'\1', md)

    # 9. Remove page-separator --- between pages (the converter inserts these)
    #    Keep only --- that appear to be intentional (after headings or in specific contexts)
    # Actually, remove all standalone --- lines that are just page separators
    # A page separator is a --- line preceded and followed by blank lines
    # We keep --- only if it appears inside content (like in a table separator)

    # 10. Clean up excessive blank lines
    md = re.sub(r'\n{4,}', '\n\n\n', md)

    # 11. Avoid nested code fences (``` inside ```)
    # If we accidentally wrapped already-fenced content, fix it
    md = re.sub(r'```\s*\n```(json)?\n', '```\\1\n', md)
    md = re.sub(r'\n```\s*\n```\s*\n', '\n```\n', md)

    return md


def convert_pdf(pdf_path: str, output_path: str = None, image_dir: str = None) -> str:
    """Convert a PDF file to Markdown."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        print(f"ERROR: File not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    # Determine output directory and paths
    # Default: create a subdirectory named after the PDF stem, put md + images inside
    if output_path:
        out_path = Path(output_path)
        out_dir = out_path.parent
    else:
        out_dir = pdf_path.parent / pdf_path.stem
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / (pdf_path.stem + ".md")

    # Determine image directory
    if image_dir:
        img_dir = Path(image_dir)
    else:
        img_dir = out_dir / "images"

    img_dir.mkdir(parents=True, exist_ok=True)

    prefix = pdf_path.stem
    # Sanitize prefix for filenames
    prefix = re.sub(r'[^\w\-]', '_', prefix)[:30]

    doc = pymupdf.open(str(pdf_path))
    total_pages = len(doc)
    print(f"Converting: {pdf_path.name} ({total_pages} pages)", file=sys.stderr)

    all_pages_md = []
    for i, page in enumerate(doc):
        print(f"  Page {i + 1}/{total_pages}...", file=sys.stderr)
        page_md = convert_page(page, i, img_dir, prefix)
        if page_md.strip():
            all_pages_md.append(page_md)

    doc.close()

    # Combine pages (use blank lines instead of --- to avoid stray separators)
    full_md = "\n\n".join(all_pages_md)

    # Post-processing: fix common formatting issues
    print("  Post-processing...", file=sys.stderr)
    full_md = postprocess_markdown(full_md)

    # Write output
    out_path.write_text(full_md, encoding="utf-8")

    # Check if image dir is empty (no images extracted)
    if not any(img_dir.iterdir()):
        img_dir.rmdir()
        print(f"Done: {out_path} (no images)", file=sys.stderr)
    else:
        img_count = len(list(img_dir.iterdir()))
        print(f"Done: {out_path} ({img_count} images in {img_dir})", file=sys.stderr)

    return str(out_path)


def main():
    parser = argparse.ArgumentParser(description="Convert PDF to Markdown with images")
    parser.add_argument("input", help="Input PDF file path")
    parser.add_argument("--output", "-o", help="Output markdown file path (default: same name .md)")
    parser.add_argument("--image-dir", "-i", help="Directory to save images (default: <name>_images/)")
    args = parser.parse_args()

    convert_pdf(args.input, args.output, args.image_dir)


if __name__ == "__main__":
    main()
