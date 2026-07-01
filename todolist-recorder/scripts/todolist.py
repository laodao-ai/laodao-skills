#!/usr/bin/env python3
"""todolist.py — 自动记录/回写/扫描 todolist 的确定性兜底脚本。

skill `todolist-recorder` 的执行核心。收集优化想法/技术债/改进等**非缺陷**项，
作为后续排期的收集池。与 buglist 的差异：每月一文件、T 前缀、按类型而非优先级、
详细块可选（轻量优先）、无根因/修复方案、状态码 OPEN/PROPOSED/DONE/WONTDO。

把"判断"留给模型（值不值得记、归哪类、要不要写动机/思路），把"确定性且易错"的部分
交给本脚本：全局 T-ID 自增、当月文件定位/创建、总览表 ↔ 详细块一致、DONE 门禁
（必带 change/commit 证据）、WONTDO 门禁（必带理由）、扫描 + 一致性自检。

文件布局（约定，自包含，不依赖外部 rule）：
  <root>/openspec/todolists/YYYY-MM-todolist.md
  结构 = 头部 → ## 状态总览（表）→ 各项的 --- 分隔详细块（可选）

用法见 `python todolist.py --help`。写操作追加式，不删历史。
"""

import argparse
import datetime
import glob
import json
import os
import re
import subprocess
import sys

STATUS_CODES = ["OPEN", "PROPOSED", "DONE", "WONTDO"]
TYPE_TAGS = ["性能优化", "可观测性", "代码质量", "功能增强", "基础设施"]
DEFAULT_PREFIX = "T"
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


# ── 关联文档 doc ─────────────────────────────────────────────────────────────

def normalize_doc_paths(doc):
    """把 add 时传入的 doc 字段（str / list[str] / 空）归一化为 list[str]，
    每项保证以 'openspec/' 开头（缺前缀则补）。不强制要求 .md 结尾——
    非 .md 路径仍会被记录，只是不会被 review 工具的 linkify 正则识别为可点击链接
    （该正则只认 `openspec/...同.md` 结尾的反引号内联代码）。"""
    if not doc:
        return []
    items = [doc] if isinstance(doc, str) else list(doc)
    out = []
    for item in items:
        item = (item or "").strip()
        if not item:
            continue
        if not item.startswith("openspec/"):
            item = "openspec/" + item.lstrip("/")
        out.append(item)
    return out


def validate_doc_paths(root, docs):
    """软校验：文档路径（相对 root）不存在只打 stderr 警告，不阻断记录——
    这个功能的目的是鼓励关联文档，不是做门禁。"""
    for d in docs:
        if not os.path.isfile(os.path.join(root, d)):
            print(f"WARNING: 关联文档路径不存在：{d}", file=sys.stderr)


def auto_default_doc(root, change):
    """change 已知但显式 doc 为空时，尽力探测关联文档，按优先级：
    1) openspec/changes/{change}/design.md
    2) openspec/changes/{change}/proposal.md
    3) openspec/changes/archive/*-{change}/design.md（glob，归档目录名前缀是不可预测的日期）
    4) 同上但 proposal.md
    每一步只在“唯一匹配”时采用；glob 命中多个时不猜，直接跳过该步。
    全部落空则返回 []（best-effort，不是必须项）。仅在调用方没有显式传 doc 时才应调用本函数，
    不覆盖显式值。"""
    if not change:
        return []
    for name in ("design.md", "proposal.md"):
        candidate = os.path.join("openspec", "changes", change, name)
        if os.path.isfile(os.path.join(root, candidate)):
            return [candidate.replace(os.sep, "/")]
    for name in ("design.md", "proposal.md"):
        pattern = os.path.join(root, "openspec", "changes", "archive", f"*-{change}", name)
        matches = glob.glob(pattern)
        if len(matches) == 1:
            rel = os.path.relpath(matches[0], root)
            return [rel.replace(os.sep, "/")]
    return []


def todolists_dir(root):
    return os.path.join(root, "openspec", "todolists")


def list_files(root):
    d = todolists_dir(root)
    if not os.path.isdir(d):
        return []
    return sorted(
        os.path.join(d, f) for f in os.listdir(d)
        if re.match(r"\d{4}-\d{2}-todolist\.md$", f)
    )


def this_month(override=None):
    if override:
        return override
    return datetime.date.today().strftime("%Y-%m")


def file_for_month(root, month):
    return os.path.join(todolists_dir(root), f"{month}-todolist.md")


HEADER_TMPL = """# {month} TODO

> 项目：{project}

## 状态总览

| ID | 模块 | 描述 | 类型 | 状态 | 时间 | 关联Change |
|----|------|------|------|------|------|------------|
"""


def ensure_file(root, month, project):
    path = file_for_month(root, month)
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(HEADER_TMPL.format(month=month, project=project or "<未注明>"))
    return path


# ── ID 扫描 ──────────────────────────────────────────────────────────────────

def all_ids(root):
    ids = []
    for path in list_files(root):
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"\|\s*([A-Z]\d+)\s*\|", line)
                if m:
                    ids.append(m.group(1))
    return ids


def next_id(root, prefix=DEFAULT_PREFIX):
    nums = [int(ID_RE.match(i).group(2)) for i in all_ids(root) if ID_RE.match(i)]
    n = (max(nums) + 1) if nums else 1
    return f"{prefix}{n}"


# ── 表 / 块 解析 ─────────────────────────────────────────────────────────────

def split_sections(lines):
    table_hdr = None
    for i, ln in enumerate(lines):
        if re.match(r"\|\s*ID\s*\|", ln):
            table_hdr = i
            break
    if table_hdr is None:
        return None
    rows_start = table_hdr + 2  # 跳过表头 + 分隔行
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
    out = {}
    starts = [(i, m.group(1)) for i, ln in enumerate(lines)
              if (m := re.match(r"##\s+([A-Z]\d+)\s*:", ln))]
    for i, bid in starts:
        end = len(lines)
        for j in range(i + 1, len(lines)):
            if lines[j].strip() == "---" or re.match(r"##\s+[A-Z]\d+\s*:", lines[j]):
                end = j
                break
        out[bid] = (i, end)
    return out


# ── add ──────────────────────────────────────────────────────────────────────

def cmd_add(args):
    root = repo_root(args.root)
    data = _load_json(args.json)
    for req in ("module", "summary", "type"):
        if not data.get(req):
            _die(f"缺少必填字段：{req}")
    if data["type"] not in TYPE_TAGS:
        _die(f"类型非法：{data['type']}（应为 {'/'.join(TYPE_TAGS)}）")
    status = data.get("status", "OPEN")
    if status not in STATUS_CODES:
        _die(f"状态码非法：{status}")

    month = this_month(args.month)
    path = ensure_file(root, month, data.get("project"))
    tid = data.get("id") or next_id(root, args.prefix)
    time_str = args.time or datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    change = data.get("change") or detect_change(root)

    docs = normalize_doc_paths(data.get("doc"))
    if not docs:
        docs = auto_default_doc(root, change)  # 显式 doc 优先；仅在为空时才尝试自动关联
    validate_doc_paths(root, docs)

    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    sec = split_sections(lines)
    if sec is None:
        _die("文件结构异常：找不到状态总览表")

    row = (f"| {tid} | `{data['module']}` | {data['summary']} | {data['type']} | "
           f"{status} | {time_str} | {change or '-'} |\n")
    lines.insert(sec["rows_end"], row)

    # 详细块可选：给了 动机/思路/备注，或有关联文档，才写（轻量优先）
    block = _build_block(tid, data, status, docs)
    if block:
        lines.append(block)

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(json.dumps({"id": tid, "file": os.path.relpath(path, root), "status": status,
                      "block": bool(block), "time": time_str, "change": change or None},
                     ensure_ascii=False))


def _build_block(tid, data, status, docs=None):
    docs = docs or []
    parts = {k: data.get(k, "").strip() for k in ("motivation", "approach", "note")}
    if not any(parts.values()) and not docs:
        return ""  # 简单项：不建块
    title = data.get("title") or data["summary"]
    b = f"\n---\n\n## {tid}: {title}\n\n"
    b += "| 属性 | 值 |\n|------|------|\n"
    b += f"| 模块 | `{data['module']}` |\n| 类型 | {data['type']} |\n| 状态 | {status} |\n"
    if docs:
        b += "\n**关联文档**：" + "、".join(f"`{d}`" for d in docs) + "\n"
    if parts["motivation"]:
        b += f"\n**动机**：{parts['motivation']}\n"
    if parts["approach"]:
        b += f"\n**思路**：{parts['approach']}\n"
    if parts["note"]:
        b += f"\n**备注**：{parts['note']}\n"
    return b


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

    # 门禁
    if new == "DONE" and not args.evidence:
        _die("置为 DONE 必须提供 --evidence（关联的 change 名或 commit hash）")
    if new == "WONTDO" and not args.reason:
        _die("置为 WONTDO 必须提供 --reason（放弃的理由）")

    old = rows[args.id]["cells"][4]
    cells = rows[args.id]["cells"]
    cells[4] = new
    lines[rows[args.id]["line"]] = "| " + " | ".join(cells) + " |\n"

    note = args.evidence or args.reason or ""
    hist = f"> {this_month(args.month)} 状态：{old} → {new}" + (f"（{note}）" if note else "") + "\n"

    blocks = block_ranges(lines)
    if args.id in blocks:
        # 有块：更新块状态 + 追加历史
        b_start, b_end = blocks[args.id]
        for i in range(b_start, b_end):
            if re.match(r"\|\s*状态\s*\|", lines[i]):
                lines[i] = f"| 状态 | {new} |\n"
                break
        insert_at = b_end
        while insert_at > b_start and lines[insert_at - 1].strip() == "":
            insert_at -= 1
        lines.insert(insert_at, hist)
    elif note:
        # 无块但有证据/理由：补一个最小块留痕（DONE/WONTDO 走这条）
        lines.append(_minimal_block(args.id, cells, new, hist))

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(json.dumps({"id": args.id, "old": old, "new": new,
                      "file": os.path.relpath(path, root)}, ensure_ascii=False))


def _minimal_block(tid, cells, status, hist):
    title = cells[2]
    return (f"\n---\n\n## {tid}: {title}\n\n"
            f"| 属性 | 值 |\n|------|------|\n"
            f"| 模块 | {cells[1]} |\n| 类型 | {cells[3]} |\n| 状态 | {status} |\n\n{hist}")


# ── scan ─────────────────────────────────────────────────────────────────────

def cmd_scan(args):
    root = repo_root(args.root)
    items, problems = [], []
    for path in list_files(root):
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        sec = split_sections(lines)
        rows = parse_table_rows(lines, sec) if sec else {}
        blocks = block_ranges(lines)
        rel = os.path.relpath(path, root)
        # 块若存在必须有对应表行（块可选，故只单向查）
        for bid in blocks:
            if bid not in rows:
                problems.append(f"{rel}: 块有 {bid} 但缺总览表行")
        # 状态一致性（仅对有块的项）
        for bid, info in rows.items():
            if bid in blocks:
                bs, be = blocks[bid]
                bstatus = next((m.group(1) for i in range(bs, be)
                                if (m := re.match(r"\|\s*状态\s*\|\s*(\w+)", lines[i]))), None)
                if bstatus and bstatus != info["cells"][4]:
                    problems.append(f"{rel}: {bid} 状态不一致（表={info['cells'][4]} 块={bstatus}）")
            c = info["cells"]
            items.append({"id": bid, "module": c[1], "summary": c[2],
                          "type": c[3], "status": c[4],
                          "time": c[5] if len(c) > 5 else None,
                          "change": c[6] if len(c) > 6 and c[6] != "-" else None,
                          "file": rel})

    if args.status:
        items = [b for b in items if b["status"] == args.status]
    if args.type:
        items = [b for b in items if b["type"] == args.type]
    if args.json:
        print(json.dumps({"items": items, "problems": problems}, ensure_ascii=False, indent=2))
        return
    if not items:
        print("（无匹配 TODO）")
    for b in sorted(items, key=lambda x: (x["status"], x["id"])):
        print(f"{b['id']:<5} {b['status']:<10} {b['type']:<8} {b['module']:<24} {b['summary']}")
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


def _die(msg):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(1)


def main():
    p = argparse.ArgumentParser(description="自动记录/回写/扫描 todolist")
    p.add_argument("--root", default=".", help="仓库根（默认自动探测 git 根）")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("next-id", help="打印下一个全局 ID")
    s.add_argument("--prefix", default=DEFAULT_PREFIX)
    s.set_defaults(func=lambda a: print(next_id(repo_root(a.root), a.prefix)))

    s = sub.add_parser("add", help="新增 TODO（JSON 输入，stdin 或 --json 文件）")
    s.add_argument("--json", help="JSON 文件路径；缺省读 stdin")
    s.add_argument("--prefix", default=DEFAULT_PREFIX)
    s.add_argument("--month", help="覆盖月份 YYYY-MM（默认本月）")
    s.add_argument("--time", help="覆盖记录时间 YYYY-MM-DD HH:MM（默认当前时刻）")
    s.set_defaults(func=cmd_add)

    s = sub.add_parser("set-status", help="回写状态（表写 + 门禁 + 有证据则补块留痕）")
    s.add_argument("--id", required=True)
    s.add_argument("--to", required=True, help="目标状态码")
    s.add_argument("--evidence", help="change 名 / commit hash（DONE 必填）")
    s.add_argument("--reason", help="WONTDO 理由（WONTDO 必填）")
    s.add_argument("--month", help="覆盖月份")
    s.set_defaults(func=cmd_set_status)

    s = sub.add_parser("scan", help="列出 TODO + 表↔块一致性自检")
    s.add_argument("--status", help="按状态码过滤")
    s.add_argument("--type", help="按类型过滤")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_scan)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
