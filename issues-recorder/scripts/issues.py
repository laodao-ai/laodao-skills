#!/usr/bin/env python3
"""issues.py — 共享 issues 层脚本：跨 bug+todo 两池（Task 8：read + D9 冲突检测；
Task 9：reindex → issues/INDEX.md）。

背景（design.md §五 grill-amendment B-Q2）：`buglist.py`（buglist-recorder）与
`todolist.py`（todolist-recorder）是两个独立 skill 的独立脚本，各管自己一类
（add/scan/set-status/triage）。但 `reindex`/`batch` 是**跨 bug+todo**（join 两池 +
维护 `issues/INDEX.md`/`issues/batches.md`）——这类跨类型命令归本脚本独占，不塞进
per-type 脚本。

本文件现状：
  - `read_pool(root)`（Task 8）：子进程调 buglist.py/todolist.py 的 `scan --json`，
    join 成一份跨两池的 item 列表（每项打 `pool` 标记），join 后立即用
    `cross_pool_id_conflicts` 做 D9 防护网校验。
  - `cross_pool_id_conflicts(items)`（Task 8）：纯函数，检测同一 ID 是否跨池撞号。
  - `reindex`（Task 9，本任务）：`read_pool` → `generate_index_md` 纯函数重建
    `issues/INDEX.md`（首行 GENERATED banner + open item×批次物化板 + 已闭合摘要）
    → `atomic_write` 原子落盘。**禁读旧 INDEX**（D3，全量确定性重建）、**幂等**（D7）。
    批次状态同步（tasks.md §3.2）留 Task 11；`issues/batches.md` 注册表留 Task 10——
    两者落地前 `reindex` 只做 INDEX 这一半。
  - `batch`：argparse 占位（真逻辑见 tasks.md §3.3 / Task 11），当前只报"未实现"
    并以非零退出。
  - `atomic_write`：与 buglist.py/todolist.py 同款原子写 helper，供落盘
    `issues/INDEX.md`/`issues/batches.md` 用。

**并发假设边界（D8）**：本脚本假定单机单进程串行调用，不加锁、不做文件锁/乐观锁/CAS。
umbrella 设计认定"并发/共享可变状态"属 TG-26，但 TG-26 要 Phase C 才落地；Phase B（本
脚本所在阶段）显式声明串行假设、不实现锁——真需要并发调用本脚本，留给后续 change 补锁。
调用方（skill / CI / opsx-done sweep 步）需自行保证不并发调用本脚本，也不与
buglist.py/todolist.py 的写操作并发交叉。

用法见 `python issues.py --help`。
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile


# ── 兄弟脚本定位 ─────────────────────────────────────────────────────────────
# 按本脚本自身的文件位置（不是 --root / 目标项目根）定位 buglist.py/todolist.py：
# setup.sh 把仓库里的每个顶层 skill 目录（buglist-recorder / todolist-recorder /
# issues-recorder ...）各自绝对 symlink 到 ~/.claude/skills/、~/.codex/skills/ 下，
# 三者在安装后仍是同级 sibling 目录，因此“issues-recorder/scripts 的上两级”这个
# 相对关系在源码仓库和安装后的位置都成立。--root 是完全独立的另一个概念：它是
# *目标项目*（存 openspec/issues/... 的仓库）的根，两者不可混淆、不可互相替代。
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
BUGLIST_SCRIPT = os.path.join(SKILLS_ROOT, "buglist-recorder", "scripts", "buglist.py")
TODOLIST_SCRIPT = os.path.join(SKILLS_ROOT, "todolist-recorder", "scripts", "todolist.py")


def atomic_write(path, text):
    """原子写：同目录临时文件写完整内容 → os.replace 原子换入。
    中途任何异常（含 os.replace 本身失败）都不会截断/损坏原文件——旧内容原样保留，
    临时文件在 finally 里清理，不留残留 .tmp。

    tempfile.mkstemp 固定以 0600 创建临时文件；os.replace 是纯 rename，目标会
    继承临时文件的权限。覆写已存在文件前必须把临时文件权限对齐回原文件的权限，
    否则已存在文件的权限会被静默从（例如）0644 收紧到 0600（对 group/other 变
    不可读）。原文件不存在（首次创建）时用 0o644 兜底。

    与 buglist.py / todolist.py 的同名函数逐字同款（Phase B 3 个脚本各自独立、
    不互相 import，故各自内联一份，见模块 docstring "子进程解耦"）。"""
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        try:
            mode = os.stat(path).st_mode & 0o777
        except FileNotFoundError:
            mode = 0o644
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


class CrossPoolIDConflict(RuntimeError):
    """D9 防护网触发：同一 ID 同时出现在 bug 池与 todo 池。"""


# ── 跨池 read ────────────────────────────────────────────────────────────────

def _scan_pool(script, root, pool):
    """子进程调 `{script} --root {root} scan --json`，给每项打 `pool` 标记后返回列表。

    推荐子进程而非 import（brief 明确要求）：buglist.py / todolist.py 是两个独立 skill
    各自的执行核心，子进程调用只依赖它们的 CLI 契约（`scan --json` 的输出结构），不依赖
    其内部函数签名——两边各自演进互不牵连，也不会把共享层的 issues.py 变成两个 per-type
    脚本的隐式反向依赖源。
    """
    proc = subprocess.run(
        [sys.executable, script, "--root", str(root), "scan", "--json"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"{os.path.basename(script)} scan --json 失败（exit={proc.returncode}）：{proc.stderr}"
        )
    data = json.loads(proc.stdout)
    # buglist.py 输出键是 "bugs"，todolist.py 输出键是 "items"（两脚本各自的命名，
    # 不统一——brief 明确提醒过这个坑，这里按 pool 分别取对应键）。
    raw_items = data.get("bugs" if pool == "bug" else "items") or []
    out = []
    for item in raw_items:
        merged = dict(item)
        merged["pool"] = pool
        out.append(merged)
    return out


def cross_pool_id_conflicts(items):
    """检测 `items`（含 `id`/`pool` 字段的 dict 列表）里同一 ID 是否跨池撞号
    （即同时出现在 pool == 'bug' 和 pool == 'todo' 的项里）。

    正常情况下 B(bug)/T(todo) 前缀互斥、不会天然撞号——D9 已把这条前缀互斥升为显式规范
    条款（recorder 约定段）。本函数是那条规范的**防护网**：万一有人为/历史数据用了非标准
    前缀（例如显式传自定义 `id` 绕开默认前缀），撞号也不能被静默 join 掉。

    纯函数、只读，不修改入参；返回按字典序排序的冲突 ID 列表，无冲突返回 `[]`。
    """
    bug_ids = {it["id"] for it in items if it.get("pool") == "bug"}
    todo_ids = {it["id"] for it in items if it.get("pool") == "todo"}
    return sorted(bug_ids & todo_ids)


def read_pool(root):
    """读跨两池（bug + todo）的 item 列表，join 结果里每项都带 `pool`（'bug' | 'todo'）
    标记，且至少含 `id`/`status`/`change`/`batch`/`pool` 五个字段（bug 池额外带
    priority/module/... 等 buglist 专属字段，todo 池额外带 type/module/... 等 todolist
    专属字段——字段是两边的并集，不做裁剪）。

    子进程调用 `buglist.py scan --json` + `todolist.py scan --json`（见 `_scan_pool`），
    两个结果 join 后立即跑 `cross_pool_id_conflicts` 做 D9 防护网校验：一旦检测到同一 ID
    跨池撞号，直接抛 `CrossPoolIDConflict`、**不静默 join**——调用方（reindex/batch，
    Task 9-11）不应该在数据已经撞号的情况下继续往下算 INDEX/batches。

    **并发假设边界（D8）**：本函数只读、不加锁。dated 文件本身靠 buglist.py/todolist.py
    的 atomic_write 保证不会读到半截内容，但两次 `scan --json` 子进程调用之间没有任何
    快照隔离——如果调用期间另一进程正并发 add/set-status，两池读到的"时刻"不保证一致。
    Phase B 显式假定单机单进程串行调用，不处理这类竞态（同模块 docstring D8）。
    """
    items = _scan_pool(BUGLIST_SCRIPT, root, "bug") + _scan_pool(TODOLIST_SCRIPT, root, "todo")
    conflicts = cross_pool_id_conflicts(items)
    if conflicts:
        raise CrossPoolIDConflict(
            "跨池 ID 冲突（D9 防护网触发，同一 ID 同时出现在 bug 池与 todo 池）："
            + ", ".join(conflicts)
        )
    return items


# ── reindex → issues/INDEX.md（Task 9） ─────────────────────────────────────
# 批次状态同步（tasks.md §3.2）留 Task 11；`issues/batches.md` 注册表留 Task 10。
# 本节只做「从 dated 文件重建 INDEX.md」这一半。

INDEX_BANNER = "<!-- GENERATED by issues.py reindex — DO NOT EDIT -->"

# 各 recorder 的终态集（design.md §4.1 B-Q1）：进入即"这条债不再挂着"。
# per-recorder 判定，不写死字面 "DONE"（对 bug 池不成立）——两池状态词表不同。
TERMINAL_STATUSES = {
    "bug": {"FIXED", "WONTFIX"},
    "todo": {"DONE", "WONTDO"},
}


def _is_terminal(item):
    """item 是否已进入其所属 pool 的终态集（FIXED/WONTFIX 之于 bug，DONE/WONTDO 之于 todo）。"""
    return item.get("status") in TERMINAL_STATUSES.get(item.get("pool"), set())


def _render_item_table(items):
    """把一组 item 渲染成 markdown 表（ID | Pool | Status | 关联Change），按 id 升序。
    纯函数、确定性排序——供 generate_index_md 幂等（D7）用。"""
    lines = [
        "| ID | Pool | Status | 关联Change |",
        "|----|------|--------|------------|",
    ]
    for it in sorted(items, key=lambda x: x["id"]):
        change = it.get("change") or "-"
        lines.append(f"| {it['id']} | {it['pool']} | {it['status']} | {change} |")
    return "\n".join(lines)


def generate_index_md(items):
    """从 `read_pool` 返回的跨池 item 列表纯函数式生成 `issues/INDEX.md` 全文（含首行
    banner）。**禁读旧 INDEX**（D3）——只以 `items` 为唯一输入源，不看磁盘上已有内容。

    正文 = open item（非终态）× 批次的物化板：
      - 有批次的 open 项按批次分组（批次名升序），组内按 id 升序；
      - 批次为空的 open 项单列一组「未分组」，排在所有具名批次之后；
      - 已闭合（终态）项不逐条列出，只计数摘要（含 pool 拆分）。

    **幂等（D7）**：不写入时间戳/随机序等致每次不同的内容；分组键、组内排序全部确定性
    （批次名字典序、item id 字典序），故相同 `items` 两次调用逐字节输出相同。
    """
    open_items = [it for it in items if not _is_terminal(it)]
    closed_items = [it for it in items if _is_terminal(it)]

    groups = {}
    unbatched = []
    for it in open_items:
        batch = it.get("batch") or ""
        if batch:
            groups.setdefault(batch, []).append(it)
        else:
            unbatched.append(it)

    lines = [
        INDEX_BANNER,
        "",
        "# Issues Index",
        "",
        "> 本文件由 `issues.py reindex` 从 dated 文件"
        "（`issues/buglist/` + `issues/todolist/`）重建，请勿手改——"
        "手改内容会在下次 reindex 时被无条件覆盖。",
        "",
        "## Open 项（按批次）",
        "",
    ]

    if not groups and not unbatched:
        lines.append("（无 open 项）")
    else:
        for batch in sorted(groups):
            lines.append(f"### 批次：{batch}")
            lines.append("")
            lines.append(_render_item_table(groups[batch]))
            lines.append("")
        if unbatched:
            lines.append("### 未分组（批次为空）")
            lines.append("")
            lines.append(_render_item_table(unbatched))
            lines.append("")

    bug_closed = sum(1 for it in closed_items if it.get("pool") == "bug")
    todo_closed = sum(1 for it in closed_items if it.get("pool") == "todo")
    lines.append("## 已闭合（终态）摘要")
    lines.append("")
    lines.append(
        f"- 共 {len(closed_items)} 项已闭合（bug: {bug_closed}，todo: {todo_closed}）"
    )
    lines.append("")

    return "\n".join(lines)


def _die(msg):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(1)


def cmd_reindex(args):
    """重建 `issues/INDEX.md`（Task 9：只做 INDEX 部分；批次状态同步见 Task 11，
    `issues/batches.md` 见 Task 10）。

    流程：`read_pool`（内含 D9 跨池 ID 冲突检测，冲突即抛 `CrossPoolIDConflict` 中止，
    不生成半截 INDEX）→ `generate_index_md` 纯函数重建全文 → `atomic_write` 原子落盘。
    **禁读旧 INDEX.md**（D3）：全量确定性重建，不与磁盘上旧内容比较/合并。
    """
    try:
        items = read_pool(args.root)
    except RuntimeError as e:
        _die(str(e))
        return  # pragma: no cover（_die 已 sys.exit(1)，此行只安抚静态分析）

    content = generate_index_md(items)
    index_path = os.path.join(args.root, "openspec", "issues", "INDEX.md")
    atomic_write(index_path, content)

    open_n = sum(1 for it in items if not _is_terminal(it))
    closed_n = len(items) - open_n
    print(f"reindex：已重建 {index_path}（open {open_n} 项，已闭合 {closed_n} 项）")


def cmd_batch(args):
    """占位：真逻辑（`issues/batches.md` 注册表 + add/set-status）见 tasks.md §3.3。"""
    print(
        "batch：Task 8 只搭骨架，尚未实现——真逻辑见 tasks.md §3.3（Task 11）",
        file=sys.stderr,
    )
    sys.exit(1)


def main():
    p = argparse.ArgumentParser(
        description="共享 issues 层：跨 bug+todo 的 reindex / batch（骨架，Task 8）"
    )
    p.add_argument("--root", default=".", help="目标项目根（存 openspec/issues/... 的仓库）")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("reindex", help="重建 issues/INDEX.md（open×批次板；批次状态同步/batches.md 见 Task 10-11）")
    s.set_defaults(func=cmd_reindex)

    s = sub.add_parser("batch", help="issues/batches.md 注册表操作（占位，真逻辑见 Task 11）")
    s.add_argument("action", nargs="?", choices=["add", "set-status"], help="子操作（占位）")
    s.set_defaults(func=cmd_batch)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
