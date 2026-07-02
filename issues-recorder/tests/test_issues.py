"""
Tests for issues.py's Task 8 skeleton: cross-pool `read_pool` join (bug + todo)
and D9 cross-pool ID conflict detection.
Run with: python3 -m pytest issues-recorder/tests/ -v
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import issues as issues_mod
from issues import (
    atomic_write, cross_pool_id_conflicts, read_pool, CrossPoolIDConflict,
)

SCRIPT = str(Path(__file__).parent.parent / "scripts" / "issues.py")


class TestReadPoolJoin:
    """Step 1/3：read_pool join buglist + todolist 两池，断言含两池项 + pool 标记。"""

    def test_joins_both_pools_with_pool_tag(self, tmp_path):
        _write_bug_file(tmp_path, "2026-01-01", [
            {"id": "B1", "status": "OPEN", "change": "change-a", "batch": "batch-1"},
            {"id": "B2", "status": "FIXED", "change": "change-a", "batch": ""},
        ])
        _write_todo_file(tmp_path, "2026-01", [
            {"id": "T1", "status": "OPEN", "change": "change-a", "batch": ""},
        ])

        items = read_pool(str(tmp_path))

        assert len(items) == 3
        by_id = {it["id"]: it for it in items}
        assert by_id["B1"]["pool"] == "bug"
        assert by_id["B2"]["pool"] == "bug"
        assert by_id["T1"]["pool"] == "todo"
        # 每项至少含 id/status/change/batch/pool 五个字段
        for it in items:
            for key in ("id", "status", "change", "batch", "pool"):
                assert key in it
        assert by_id["B1"]["status"] == "OPEN"
        assert by_id["B1"]["change"] == "change-a"
        assert by_id["B1"]["batch"] == "batch-1"
        assert by_id["T1"]["status"] == "OPEN"
        assert by_id["T1"]["change"] == "change-a"

    def test_empty_when_no_files_in_either_pool(self, tmp_path):
        assert read_pool(str(tmp_path)) == []

    def test_only_bug_pool_present(self, tmp_path):
        _write_bug_file(tmp_path, "2026-01-01", [
            {"id": "B1", "status": "OPEN", "change": "x", "batch": ""},
        ])
        items = read_pool(str(tmp_path))
        assert [it["id"] for it in items] == ["B1"]
        assert items[0]["pool"] == "bug"

    def test_only_todo_pool_present(self, tmp_path):
        _write_todo_file(tmp_path, "2026-01", [
            {"id": "T1", "status": "OPEN", "change": "x", "batch": ""},
        ])
        items = read_pool(str(tmp_path))
        assert [it["id"] for it in items] == ["T1"]
        assert items[0]["pool"] == "todo"


class TestCrossPoolIdConflicts:
    """人造 B/T 撞号，纯函数层面测 cross_pool_id_conflicts。"""

    def test_no_conflict_when_prefixes_normal(self):
        items = [
            {"id": "B1", "pool": "bug"},
            {"id": "B2", "pool": "bug"},
            {"id": "T1", "pool": "todo"},
        ]
        assert cross_pool_id_conflicts(items) == []

    def test_detects_single_collision_across_pools(self):
        items = [
            {"id": "X1", "pool": "bug"},
            {"id": "X1", "pool": "todo"},
            {"id": "B2", "pool": "bug"},
        ]
        assert cross_pool_id_conflicts(items) == ["X1"]

    def test_detects_multiple_collisions_sorted(self):
        items = [
            {"id": "X2", "pool": "bug"},
            {"id": "X1", "pool": "bug"},
            {"id": "X2", "pool": "todo"},
            {"id": "X1", "pool": "todo"},
        ]
        assert cross_pool_id_conflicts(items) == ["X1", "X2"]

    def test_same_id_within_one_pool_is_not_a_cross_pool_conflict(self):
        """同池内重复不属于 D9 范畴（跨池才算），本函数不该误报。"""
        items = [
            {"id": "B1", "pool": "bug"},
            {"id": "B1", "pool": "bug"},
        ]
        assert cross_pool_id_conflicts(items) == []

    def test_empty_items_returns_empty(self):
        assert cross_pool_id_conflicts([]) == []


class TestReadPoolConflictGuard:
    """Step 4：read_pool 撞到跨池 ID 冲突时报错非静默（D9 防护网接入 join）。"""

    def test_read_pool_raises_on_cross_pool_id_collision(self, tmp_path):
        # 正常 B/T 前缀不会撞号；这里用显式自定义 id 人为制造撞号场景（防护网兜底）。
        _write_bug_file(tmp_path, "2026-01-01", [
            {"id": "X1", "status": "OPEN", "change": "x", "batch": ""},
        ])
        _write_todo_file(tmp_path, "2026-01", [
            {"id": "X1", "status": "OPEN", "change": "x", "batch": ""},
        ])

        with pytest.raises(CrossPoolIDConflict) as exc_info:
            read_pool(str(tmp_path))
        assert "X1" in str(exc_info.value)

    def test_read_pool_conflict_does_not_silently_return_partial_join(self, tmp_path):
        """报错必须是真报错（异常），不能退化成打印警告后仍返回一份撞号数据。"""
        _write_bug_file(tmp_path, "2026-01-01", [
            {"id": "X1", "status": "OPEN", "change": "x", "batch": ""},
        ])
        _write_todo_file(tmp_path, "2026-01", [
            {"id": "X1", "status": "OPEN", "change": "x", "batch": ""},
        ])
        try:
            read_pool(str(tmp_path))
        except CrossPoolIDConflict:
            pass
        else:
            pytest.fail("expected CrossPoolIDConflict to be raised, join returned normally")


class TestAtomicWrite:
    """同款原子写 helper（供后续任务写 issues/INDEX.md / issues/batches.md 用）。"""

    def test_writes_content_and_creates_parent_dir(self, tmp_path):
        target = tmp_path / "sub" / "dir" / "file.md"
        atomic_write(str(target), "hello\n")
        assert target.read_text(encoding="utf-8") == "hello\n"

    def test_overwrites_existing_file(self, tmp_path):
        target = tmp_path / "file.md"
        target.write_text("old", encoding="utf-8")
        atomic_write(str(target), "new")
        assert target.read_text(encoding="utf-8") == "new"

    def test_overwrite_preserves_original_file_permissions(self, tmp_path):
        target = tmp_path / "file.md"
        target.write_text("old", encoding="utf-8")
        os.chmod(target, 0o644)
        atomic_write(str(target), "new")
        assert (os.stat(target).st_mode & 0o777) == 0o644

    def test_no_leftover_tmp_file_after_success(self, tmp_path):
        target = tmp_path / "file.md"
        atomic_write(str(target), "content")
        leftovers = [p for p in tmp_path.iterdir() if p.name != "file.md"]
        assert leftovers == []

    def test_original_file_unchanged_when_replace_fails(self, tmp_path, monkeypatch):
        target = tmp_path / "file.md"
        target.write_text("original content", encoding="utf-8")

        def boom(src, dst):
            raise OSError("simulated os.replace failure")

        monkeypatch.setattr(issues_mod.os, "replace", boom)

        with pytest.raises(OSError):
            atomic_write(str(target), "new content that must not land")

        assert target.read_text(encoding="utf-8") == "original content"
        leftovers = [p for p in tmp_path.iterdir() if p.name != "file.md"]
        assert leftovers == []


class TestArgparseSkeleton:
    """argparse 骨架含 reindex/batch 两子命令（占位，真逻辑 Task 9-11）。"""

    def test_help_lists_reindex_and_batch(self):
        proc = subprocess.run(
            [sys.executable, SCRIPT, "--help"], capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert "reindex" in proc.stdout
        assert "batch" in proc.stdout

    def test_reindex_subcommand_placeholder_errors_non_silently(self, tmp_path):
        proc = subprocess.run(
            [sys.executable, SCRIPT, "--root", str(tmp_path), "reindex"],
            capture_output=True, text=True,
        )
        assert proc.returncode != 0
        assert proc.stderr.strip() != ""

    def test_batch_subcommand_placeholder_errors_non_silently(self, tmp_path):
        proc = subprocess.run(
            [sys.executable, SCRIPT, "--root", str(tmp_path), "batch"],
            capture_output=True, text=True,
        )
        assert proc.returncode != 0
        assert proc.stderr.strip() != ""

    def test_missing_subcommand_errors(self):
        proc = subprocess.run(
            [sys.executable, SCRIPT], capture_output=True, text=True,
        )
        assert proc.returncode != 0


# ── fixtures ─────────────────────────────────────────────────────────────────

def _write_bug_file(root, date, rows):
    """写一个最小合法的 dated buglist 文件（新路径 openspec/issues/buglist/），
    格式镜像 buglist-recorder/tests/test_buglist.py 的 _write_mixed_file。"""
    dir_path = Path(root) / "openspec" / "issues" / "buglist"
    dir_path.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {date} Buglist\n\n",
        "> 来源：test\n",
        f"> 创建日期：{date}\n\n",
        "## 状态总览\n\n",
        "| ID | 模块 | 问题摘要 | 优先级 | 状态 | 时间 | 关联Change | 批次 |\n",
        "|----|------|----------|--------|------|------|------------|------|\n",
    ]
    for r in rows:
        lines.append(
            f"| {r['id']} | `foo.c:1` | fixture | P2 | {r['status']} | 10:00 | "
            f"{r.get('change') or '-'} | {r.get('batch', '')} |\n"
        )
    (dir_path / f"{date}-buglist.md").write_text("".join(lines), encoding="utf-8")


def _write_todo_file(root, month, rows):
    """写一个最小合法的月度 todolist 文件（新路径 openspec/issues/todolist/），
    格式镜像 todolist.py 的 HEADER_TMPL + 表行。"""
    dir_path = Path(root) / "openspec" / "issues" / "todolist"
    dir_path.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {month} TODO\n\n",
        "> 项目：test\n\n",
        "## 状态总览\n\n",
        "| ID | 模块 | 描述 | 类型 | 状态 | 时间 | 关联Change | 批次 |\n",
        "|----|------|------|------|------|------|------------|------|\n",
    ]
    for r in rows:
        lines.append(
            f"| {r['id']} | `foo.c:1` | fixture | 代码质量 | {r['status']} | "
            f"2026-01-01 10:00 | {r.get('change') or '-'} | {r.get('batch', '')} |\n"
        )
    (dir_path / f"{month}-todolist.md").write_text("".join(lines), encoding="utf-8")
