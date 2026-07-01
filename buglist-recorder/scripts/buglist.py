#!/usr/bin/env python3
"""buglist.py — 自动记录/回写/扫描 buglist 的确定性兜底脚本。

skill `buglist-recorder` 的执行核心。把"判断"留给模型（现象 vs 根因、定优先级、
是否值得记录），把"确定性且易错"的部分交给本脚本：
  - 全局 ID 扫描自增（跨文件不撞号）
  - 今日文件/目录定位与创建（缺则建 + 写头部）
  - 状态总览表 ↔ 详细块 的双写一致（增、改都两处同步）
  - 状态回写的门禁（FIXED 必须有根因 + 证据；WONTFIX 必须有理由）
  - 扫描列表 + 表↔块一致性自检

文件布局（约定，自包含，不依赖外部 rule）：
  <root>/openspec/buglists/YYYY-MM-DD-buglist.md
  结构 = 头部元信息 → ## 状态总览（表）→ 各 bug 的 --- 分隔详细块

用法见 `python buglist.py --help`。所有写操作都是追加式，不删历史。
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys

STATUS_CODES = ["OPEN", "VERIFIED", "PROPOSED", "IN_PROGRESS", "FIXED", "WONTFIX", "BLOCKED"]
PRIORITIES = ["P0", "P1", "P2", "P3", "P4"]
DEFAULT_PREFIX = "B"
ID_RE = re.compile(r"\b([A-Z])(\d+)\b")


# ── 路径与文件 ───────────────────────────────────────────────────────────────

def repo_root(start="."):
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start, capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except Exception:
        return os.path.abspath(start)


BRANCH_PREFIX_RE = re.compile(r"^[a-z]+/")


def detect_change(root):
    """自动探测当前所处 OpenSpec change 名，供 add 时记录来源（可被 --json 里的 change 覆盖）。
    优先级：openspec/changes/ 下唯一未归档目录 → git branch 名去前缀 → 空字符串（多 change 并行/
    无法判断时交给模型显式传 change，不瞎猜）。"""
    changes_dir = os.path.join(root, "openspec", "changes")
    dirs = []
    if os.path.isdir(changes_dir):
        dirs = sorted(
            d for d in os.listdir(changes_dir)
            if d != "archive" and os.path.isdir(os.path.join(changes_dir, d))
        )
    if len(dirs) == 1:
        return dirs[0]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=root, capture_output=True, text=True, check=True,
        )
        branch = out.stdout.strip()
    except Exception:
        branch = ""
    candidate = BRANCH_PREFIX_RE.sub("", branch) if branch else ""
    if candidate and (not dirs or candidate in dirs):
        return candidate
    return ""


def buglists_dir(root):
    return os.path.join(root, "openspec", "buglists")


def list_files(root):
    d = buglists_dir(root)
    if not os.path.isdir(d):
        return []
    return sorted(
        os.path.join(d, f) for f in os.listdir(d)
        if re.match(r"\d{4}-\d{2}-\d{2}-buglist\.md$", f)
    )


def today_str(override=None):
    if override:
        return override
    return datetime.date.today().isoformat()


def file_for_date(root, date):
    return os.path.join(buglists_dir(root), f"{date}-buglist.md")


HEADER_TMPL = """# {date} Buglist

> 来源：{source}
> 创建日期：{date}

## 状态总览

| ID | 模块 | 问题摘要 | 优先级 | 状态 | 时间 | 关联Change |
|----|------|----------|--------|------|------|------------|
"""


def ensure_file(root, date, source):
    path = file_for_date(root, date)
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(HEADER_TMPL.format(date=date, source=source or "<未注明>"))
    return path


# ── ID 扫描 ──────────────────────────────────────────────────────────────────

def all_ids(root, prefix=None):
    ids = []
    for path in list_files(root):
        with open(path, encoding="utf-8") as f:
            for line in f:
                # 只认状态总览表里的行（以 | 开头且第二列是 ID）
                m = re.match(r"\|\s*([A-Z]\d+)\s*\|", line)
                if m:
                    pid = m.group(1)
                    if prefix is None or pid.startswith(prefix):
                        ids.append(pid)
    return ids


def next_id(root, prefix=DEFAULT_PREFIX):
    nums = [int(ID_RE.match(i).group(2)) for i in all_ids(root) if ID_RE.match(i)]
    n = (max(nums) + 1) if nums else 1
    return f"{prefix}{n}"


# ── 表 / 块 解析 ─────────────────────────────────────────────────────────────

def split_sections(lines):
    """返回 (head_end_idx, table_rows_range, body_start_idx)。
    head_end = 状态总览表分隔行后的位置；表行在 [rows_start, rows_end)。"""
    table_hdr = None
    for i, ln in enumerate(lines):
        if re.match(r"\|\s*ID\s*\|", ln):
            table_hdr = i
            break
    if table_hdr is None:
        return None
    sep = table_hdr + 1  # |----|----|
    rows_start = sep + 1
    rows_end = rows_start
    while rows_end < len(lines) and lines[rows_end].lstrip().startswith("|"):
        rows_end += 1
    return {"table_hdr": table_hdr, "rows_start": rows_start, "rows_end": rows_end}


def parse_table_rows(lines, sec):
    rows = {}
    for i in range(sec["rows_start"], sec["rows_end"]):
        cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        if len(cells) >= 5:
            rows[cells[0]] = {"line": i, "cells": cells}
    return rows


def block_ranges(lines):
    """返回 {id: (start, end)}，块从 '## {id}:' 到下一个 '---'/'## ' 或 EOF。"""
    out = {}
    starts = []
    for i, ln in enumerate(lines):
        m = re.match(r"##\s+([A-Z]\d+)\s*:", ln)
        if m:
            starts.append((i, m.group(1)))
    for idx, (i, bid) in enumerate(starts):
        end = len(lines)
        for j in range(i + 1, len(lines)):
            if lines[j].strip() == "---" or re.match(r"##\s+[A-Z]\d+\s*:", lines[j]):
                end = j
                break
        out[bid] = (i, end)
    return out


# ── add ──────────────────────────────────────────────────────────────────────

BLOCK_TMPL = """
---

## {id}: {title}

| 属性 | 值 |
|------|------|
| 模块 | `{module}` |
| 优先级 | {priority} |
| 状态 | {status} |

**现象**：{phenomenon}

**根因**：{rootcause}

**修复方案**：
{fix}

**影响范围**：{impact}
"""


def cmd_add(args):
    root = repo_root(args.root)
    data = _load_json(args.json)
    for req in ("module", "summary", "priority", "phenomenon"):
        if not data.get(req):
            _die(f"缺少必填字段：{req}")
    if data["priority"] not in PRIORITIES:
        _die(f"优先级非法：{data['priority']}（应为 {'/'.join(PRIORITIES)}）")
    status = data.get("status", "OPEN")
    if status not in STATUS_CODES:
        _die(f"状态码非法：{status}")

    date = today_str(args.date)
    path = ensure_file(root, date, data.get("source"))
    bid = data.get("id") or next_id(root, args.prefix)
    time_str = args.time or datetime.datetime.now().strftime("%H:%M")
    change = data.get("change") or detect_change(root)

    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    sec = split_sections(lines)
    if sec is None:
        _die("文件结构异常：找不到状态总览表")

    row = (f"| {bid} | `{data['module']}` | {data['summary']} | {data['priority']} | "
           f"{status} | {time_str} | {change or '-'} |\n")
    lines.insert(sec["rows_end"], row)

    block = BLOCK_TMPL.format(
        id=bid, title=data.get("title") or data["summary"],
        module=data["module"], priority=data["priority"], status=status,
        phenomenon=data["phenomenon"],
        rootcause=data.get("rootcause", "").strip() or "<待分析>",
        fix=_as_list(data.get("fix")), impact=data.get("impact", "<待评估>"),
    )
    extra = data.get("optional") or {}
    for k, v in extra.items():
        block += f"\n**{k}**：{v}\n"
    if not block.endswith("\n"):
        block += "\n"
    lines.append(block)

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(json.dumps({"id": bid, "file": os.path.relpath(path, root), "status": status,
                      "time": time_str, "change": change or None}, ensure_ascii=False))


# ── set-status ───────────────────────────────────────────────────────────────

def cmd_set_status(args):
    root = repo_root(args.root)
    new = args.to
    if new not in STATUS_CODES:
        _die(f"状态码非法：{new}")

    target = None
    for path in list_files(root):
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        sec = split_sections(lines)
        rows = parse_table_rows(lines, sec) if sec else {}
        if args.id in rows:
            target = (path, lines, sec, rows)
            break
    if not target:
        _die(f"未找到 ID：{args.id}")
    path, lines, sec, rows = target

    old = rows[args.id]["cells"][4]
    blocks = block_ranges(lines)
    if args.id not in blocks:
        _die(f"找到表行但缺详细块：{args.id}（表↔块不一致，请先修）")
    b_start, b_end = blocks[args.id]

    # 门禁
    if new == "FIXED":
        if not args.evidence:
            _die("置为 FIXED 必须提供 --evidence（commit hash 或 change 名）")
        if not _has_rootcause(lines, b_start, b_end):
            _die("置为 FIXED 前必须先补全『根因』（当前为空/占位符）")
    if new == "WONTFIX" and not args.reason:
        _die("置为 WONTFIX 必须提供 --reason（不修的理由）")

    # 1) 更新状态总览表的状态列
    cells = rows[args.id]["cells"]
    cells[4] = new
    lines[rows[args.id]["line"]] = "| " + " | ".join(cells) + " |\n"

    # 2) 更新详细块属性表的『状态』行
    for i in range(b_start, b_end):
        if re.match(r"\|\s*状态\s*\|", lines[i]):
            lines[i] = f"| 状态 | {new} |\n"
            break

    # 3) 追加状态变更历史（append-only，不删旧）
    note = args.evidence or args.reason or ""
    hist = f"> {today_str(args.date)} 状态：{old} → {new}" + (f"（{note}）" if note else "") + "\n"
    insert_at = b_end
    while insert_at > b_start and lines[insert_at - 1].strip() == "":
        insert_at -= 1
    lines.insert(insert_at, hist)

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(json.dumps({"id": args.id, "old": old, "new": new,
                      "file": os.path.relpath(path, root)}, ensure_ascii=False))


def _has_rootcause(lines, start, end):
    for i in range(start, end):
        m = re.match(r"\*\*根因\*\*：(.*)", lines[i].strip())
        if m:
            val = m.group(1).strip()
            return bool(val) and not re.fullmatch(r"<.*>", val)
    return False


# ── scan ─────────────────────────────────────────────────────────────────────

def cmd_scan(args):
    root = repo_root(args.root)
    bugs = []
    problems = []
    for path in list_files(root):
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        sec = split_sections(lines)
        rows = parse_table_rows(lines, sec) if sec else {}
        blocks = block_ranges(lines)
        rel = os.path.relpath(path, root)
        # 一致性：表↔块
        for bid in rows:
            if bid not in blocks:
                problems.append(f"{rel}: 表有 {bid} 但缺详细块")
        for bid in blocks:
            if bid not in rows:
                problems.append(f"{rel}: 块有 {bid} 但缺总览表行")
        # 状态一致性
        for bid, info in rows.items():
            if bid in blocks:
                bs, be = blocks[bid]
                block_status = None
                for i in range(bs, be):
                    m = re.match(r"\|\s*状态\s*\|\s*(\w+)", lines[i])
                    if m:
                        block_status = m.group(1)
                        break
                if block_status and block_status != info["cells"][4]:
                    problems.append(
                        f"{rel}: {bid} 状态不一致（表={info['cells'][4]} 块={block_status}）")
        for bid, info in rows.items():
            c = info["cells"]
            bugs.append({"id": bid, "module": c[1], "summary": c[2],
                         "priority": c[3], "status": c[4],
                         "time": c[5] if len(c) > 5 else None,
                         "change": c[6] if len(c) > 6 and c[6] != "-" else None,
                         "file": rel})

    if args.status:
        bugs = [b for b in bugs if b["status"] == args.status]
    if args.json:
        print(json.dumps({"bugs": bugs, "problems": problems}, ensure_ascii=False, indent=2))
        return
    if not bugs:
        print("（无匹配 bug）")
    for b in sorted(bugs, key=lambda x: (x["priority"], x["id"])):
        print(f"{b['id']:<5} {b['priority']} {b['status']:<12} {b['module']:<24} {b['summary']}")
    if problems:
        print("\n⚠️ 一致性问题：")
        for p in problems:
            print("  - " + p)
    else:
        print("\n✓ 表↔块一致")


# ── 工具 ─────────────────────────────────────────────────────────────────────

def _load_json(src):
    if src in (None, "-"):
        return json.load(sys.stdin)
    with open(src, encoding="utf-8") as f:
        return json.load(f)


def _as_list(fix):
    if fix is None:
        return "- <待补充>"
    if isinstance(fix, list):
        return "\n".join(f"- {x}" for x in fix)
    return str(fix)


def _die(msg):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(1)


def main():
    p = argparse.ArgumentParser(description="自动记录/回写/扫描 buglist")
    p.add_argument("--root", default=".", help="仓库根（默认自动探测 git 根）")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("next-id", help="打印下一个全局 ID")
    s.add_argument("--prefix", default=DEFAULT_PREFIX)
    s.set_defaults(func=lambda a: print(next_id(repo_root(a.root), a.prefix)))

    s = sub.add_parser("add", help="新增 bug（JSON 输入，stdin 或 --json 文件）")
    s.add_argument("--json", help="JSON 文件路径；缺省读 stdin")
    s.add_argument("--prefix", default=DEFAULT_PREFIX)
    s.add_argument("--date", help="覆盖日期 YYYY-MM-DD（默认今天）")
    s.add_argument("--time", help="覆盖记录时间 HH:MM（默认当前时刻）")
    s.set_defaults(func=cmd_add)

    s = sub.add_parser("set-status", help="回写状态（双写 + 门禁 + 追加历史）")
    s.add_argument("--id", required=True)
    s.add_argument("--to", required=True, help="目标状态码")
    s.add_argument("--evidence", help="commit hash / change 名（FIXED 必填）")
    s.add_argument("--reason", help="WONTFIX 理由（WONTFIX 必填）")
    s.add_argument("--date", help="覆盖日期")
    s.set_defaults(func=cmd_set_status)

    s = sub.add_parser("scan", help="列出 bug + 表↔块一致性自检")
    s.add_argument("--status", help="按状态码过滤")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_scan)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
