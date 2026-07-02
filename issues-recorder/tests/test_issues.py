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


class TestReadPoolSubprocessFailure:
    """carry-over（Task 8 遗留）：某子进程（buglist.py/todolist.py）scan --json 返回
    非零退出码时，read_pool 必须抛 RuntimeError（不静默吞掉、不返回半截 join 结果）。"""

    def test_read_pool_raises_runtime_error_when_subprocess_exits_nonzero(
        self, tmp_path, monkeypatch
    ):
        class _FakeProc:
            returncode = 1
            stdout = ""
            stderr = "simulated subprocess failure"

        def fake_run(cmd, capture_output=True, text=True):
            return _FakeProc()

        monkeypatch.setattr(issues_mod.subprocess, "run", fake_run)

        with pytest.raises(RuntimeError) as exc_info:
            read_pool(str(tmp_path))
        assert "simulated subprocess failure" in str(exc_info.value)


class TestReindexGeneratesIndexMd:
    """Task 9：reindex 生成 issues/INDEX.md（banner + 原子写 + open×批次 board + 幂等）。"""

    def test_index_first_line_is_generated_banner(self, tmp_path):
        _write_bug_file(tmp_path, "2026-01-01", [
            {"id": "B1", "status": "OPEN", "change": "change-a", "batch": "batch-1"},
        ])
        _run_reindex(tmp_path)
        content = _read_index(tmp_path)
        assert content.splitlines()[0] == (
            "<!-- GENERATED by issues.py reindex — DO NOT EDIT -->"
        )

    def test_open_items_grouped_by_batch_and_unbatched_group_separate(self, tmp_path):
        _write_bug_file(tmp_path, "2026-01-01", [
            {"id": "B1", "status": "OPEN", "change": "change-a", "batch": "batch-1"},
            {"id": "B2", "status": "OPEN", "change": "change-a", "batch": ""},
        ])
        _write_todo_file(tmp_path, "2026-01", [
            {"id": "T1", "status": "OPEN", "change": "change-a", "batch": "batch-1"},
        ])
        _run_reindex(tmp_path)
        content = _read_index(tmp_path)

        assert "batch-1" in content
        assert "| B1 |" in content
        assert "| T1 |" in content
        assert "| B2 |" in content
        assert "未分组" in content

        # B1/T1 (batch-1) 应出现在 B2（未分组）之前的分组段落里
        batch_idx = content.index("batch-1")
        unbatched_idx = content.index("未分组")
        assert batch_idx < unbatched_idx

    def test_terminal_items_excluded_from_open_board_but_counted_in_closed_summary(
        self, tmp_path
    ):
        _write_bug_file(tmp_path, "2026-01-01", [
            {"id": "B1", "status": "OPEN", "change": "change-a", "batch": "batch-1"},
            {"id": "B2", "status": "FIXED", "change": "change-a", "batch": "batch-1"},
            {"id": "B3", "status": "WONTFIX", "change": "change-a", "batch": ""},
        ])
        _write_todo_file(tmp_path, "2026-01", [
            {"id": "T1", "status": "DONE", "change": "change-a", "batch": ""},
            {"id": "T2", "status": "OPEN", "change": "change-a", "batch": ""},
        ])
        _run_reindex(tmp_path)
        content = _read_index(tmp_path)

        open_section, _, closed_section = content.partition("已闭合")
        assert "B1" in open_section
        assert "T2" in open_section
        # 终态项不出现在 open 板段落里
        assert "B2" not in open_section
        assert "B3" not in open_section
        assert "T1" not in open_section
        # 已闭合摘要含总数（3 项：B2/B3/T1）
        assert "3" in closed_section

    def test_reindex_is_idempotent_byte_identical_on_rerun(self, tmp_path):
        _write_bug_file(tmp_path, "2026-01-01", [
            {"id": "B1", "status": "OPEN", "change": "change-a", "batch": "batch-1"},
            {"id": "B2", "status": "FIXED", "change": "change-a", "batch": "batch-1"},
        ])
        _write_todo_file(tmp_path, "2026-01", [
            {"id": "T1", "status": "OPEN", "change": "change-a", "batch": ""},
        ])
        _run_reindex(tmp_path)
        first = _read_index_bytes(tmp_path)
        _run_reindex(tmp_path)
        second = _read_index_bytes(tmp_path)
        assert first == second

    def test_reindex_raises_on_cross_pool_id_conflict(self, tmp_path):
        _write_bug_file(tmp_path, "2026-01-01", [
            {"id": "X1", "status": "OPEN", "change": "x", "batch": ""},
        ])
        _write_todo_file(tmp_path, "2026-01", [
            {"id": "X1", "status": "OPEN", "change": "x", "batch": ""},
        ])
        proc = subprocess.run(
            [sys.executable, SCRIPT, "--root", str(tmp_path), "reindex"],
            capture_output=True, text=True,
        )
        assert proc.returncode != 0
        assert proc.stderr.strip() != ""
        assert not (tmp_path / "openspec" / "issues" / "INDEX.md").exists()


class TestArgparseSkeleton:
    """argparse 骨架含 reindex/batch 两子命令（reindex 真实现见 Task 9；batch 真实现见 Task 10——
    仅 `batch` 不带任何子操作时仍应非静默报错，见 test_batch_subcommand_without_action_errors_non_silently）。"""

    def test_help_lists_reindex_and_batch(self):
        proc = subprocess.run(
            [sys.executable, SCRIPT, "--help"], capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert "reindex" in proc.stdout
        assert "batch" in proc.stdout

    def test_reindex_subcommand_runs_on_empty_root_and_creates_index(self, tmp_path):
        """Task 9：reindex 不再是占位——空 root（两池都无 dated 文件）应成功生成一份
        只含 banner + 空板 + 0 已闭合的 INDEX.md（非报错，占位行为已被真实现取代）。
        真正的报错场景（跨池 ID 冲突）见 TestReindexGeneratesIndexMd。"""
        proc = subprocess.run(
            [sys.executable, SCRIPT, "--root", str(tmp_path), "reindex"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert (tmp_path / "openspec" / "issues" / "INDEX.md").exists()

    def test_batch_subcommand_without_action_errors_non_silently(self, tmp_path):
        """`batch` 缺子操作（add/set-status/rename 三选一，Task 10 起为必填的嵌套 subparser）
        仍要非静默报错——不是 Task 8 那种"整条 batch 都占位"了，而是 argparse 层面的必填校验。"""
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


class TestBatchAdd:
    """Task 10：`batch add {key}` 新建 PLANNED 条目，成员空；人写字段按参数写，缺省留占位。"""

    def test_add_creates_planned_entry_with_empty_members_and_given_fields(self, tmp_path):
        _run_batch(tmp_path, ["add", "batch-1", "--title", "清理项",
                               "--优先级", "P1", "--计划", "先清 P0/P1"])
        content = _read_batches(tmp_path)
        assert "### batch-1 — 清理项" in content
        assert "状态: PLANNED" in content
        assert "成员: (生成)" in content
        assert "优先级: P1" in content
        assert "计划: 先清 P0/P1" in content

    def test_add_without_optional_fields_uses_placeholder_and_key_as_title(self, tmp_path):
        _run_batch(tmp_path, ["add", "batch-2"])
        content = _read_batches(tmp_path)
        assert "### batch-2 — batch-2" in content
        assert "状态: PLANNED" in content
        assert "优先级: <待填>" in content
        assert "计划: <待填>" in content

    def test_add_duplicate_key_errors_non_silently(self, tmp_path):
        _run_batch(tmp_path, ["add", "batch-1"])
        proc = _run_batch_raw(tmp_path, ["add", "batch-1"])
        assert proc.returncode != 0
        assert proc.stderr.strip() != ""
        # 不覆写——原条目仍在、只出现一次
        content = _read_batches(tmp_path)
        assert content.count("### batch-1") == 1

    def test_add_two_entries_both_present(self, tmp_path):
        _run_batch(tmp_path, ["add", "batch-1"])
        _run_batch(tmp_path, ["add", "batch-2"])
        content = _read_batches(tmp_path)
        assert "### batch-1 — batch-1" in content
        assert "### batch-2 — batch-2" in content


class TestBatchSetStatus:
    """Task 10：`batch set-status {key} {S}` 只改该条目的 `状态:` 生成行，不动人写行/成员行。"""

    def test_set_status_changes_status_line(self, tmp_path):
        _write_batches_md(tmp_path, [
            "### batch-1 — 清理项\n",
            "状态: PLANNED\n",
            "成员: (生成) B1, T2\n",
            "优先级: P1\n",
            "计划: 先清 P0/P1\n",
        ])
        _run_batch(tmp_path, ["set-status", "batch-1", "IN_PROGRESS"])
        content = _read_batches(tmp_path)
        assert "状态: IN_PROGRESS" in content
        assert "状态: PLANNED" not in content

    def test_set_status_does_not_touch_members_generated_line(self, tmp_path):
        _write_batches_md(tmp_path, [
            "### batch-1 — 清理项\n",
            "状态: PLANNED\n",
            "成员: (生成) B1, T2\n",
            "优先级: P1\n",
            "计划: 先清 P0/P1\n",
        ])
        _run_batch(tmp_path, ["set-status", "batch-1", "DONE"])
        content = _read_batches(tmp_path)
        # 成员行是另一条生成行，set-status（Task 10）不该碰它——那是 reindex（Task 11）的职责
        assert "成员: (生成) B1, T2" in content

    def test_set_status_unknown_key_errors(self, tmp_path):
        _write_batches_md(tmp_path, ["### batch-1 — x\n", "状态: PLANNED\n"])
        proc = _run_batch_raw(tmp_path, ["set-status", "nope", "DONE"])
        assert proc.returncode != 0
        assert proc.stderr.strip() != ""

    def test_set_status_invalid_status_code_errors(self, tmp_path):
        _write_batches_md(tmp_path, ["### batch-1 — x\n", "状态: PLANNED\n"])
        proc = _run_batch_raw(tmp_path, ["set-status", "batch-1", "WEIRD"])
        assert proc.returncode != 0


class TestBatchSetStatusPreservesHandwrittenLines:
    """Step 4（Q3 载重约束核心）：预置含 `优先级:`/`计划:` 的 batches.md，跑 `batch set-status`，
    断言人写行逐字保留——包括含中文标点、括号、# 等"看起来像会被误解析"的内容。"""

    def test_handwritten_lines_survive_set_status_verbatim(self, tmp_path):
        handwritten_priority = "优先级: P0（阻断发布，本周必须清）\n"
        handwritten_plan = "计划: 只清 B/T 里 P0/P1，其它挪到下个批次；备注见 #123，含冒号: 不能被拆坏\n"
        _write_batches_md(tmp_path, [
            "### batch-1 — 紧急清理\n",
            "状态: PLANNED\n",
            "成员: (生成) B1\n",
            handwritten_priority,
            handwritten_plan,
        ])
        _run_batch(tmp_path, ["set-status", "batch-1", "DONE"])
        content = _read_batches(tmp_path)
        assert handwritten_priority in content
        assert handwritten_plan in content
        assert "状态: DONE" in content

    def test_handwritten_lines_survive_two_consecutive_set_status_calls(self, tmp_path):
        """连续两次 set-status（PLANNED→IN_PROGRESS→DONE），人写行全程逐字未变。"""
        handwritten_priority = "优先级: P2\n"
        handwritten_plan = "计划: 一句范围，别改我\n"
        _write_batches_md(tmp_path, [
            "### batch-1 — 常规清理\n",
            "状态: PLANNED\n",
            "成员: (生成)\n",
            handwritten_priority,
            handwritten_plan,
        ])
        _run_batch(tmp_path, ["set-status", "batch-1", "IN_PROGRESS"])
        _run_batch(tmp_path, ["set-status", "batch-1", "DONE"])
        content = _read_batches(tmp_path)
        assert handwritten_priority in content
        assert handwritten_plan in content
        assert "状态: DONE" in content


class TestBatchRename:
    """Task 10：`batch rename {old} {new}` 改条目 key + 同步 item 池里所有 批次==old 的 tag（跨两池）。"""

    def test_rename_changes_key_and_preserves_handwritten_lines(self, tmp_path):
        _write_batches_md(tmp_path, [
            "### old-batch — 清理项\n",
            "状态: PLANNED\n",
            "成员: (生成) B1\n",
            "优先级: P1\n",
            "计划: 一句范围\n",
        ])
        _run_batch(tmp_path, ["rename", "old-batch", "new-batch"])
        content = _read_batches(tmp_path)
        assert "### new-batch — 清理项" in content
        assert "old-batch" not in content
        assert "优先级: P1" in content
        assert "计划: 一句范围" in content

    def test_rename_syncs_item_batch_tag_in_bug_pool_only_matching_items(self, tmp_path):
        _write_batches_md(tmp_path, [
            "### old-batch — 清理项\n", "状态: PLANNED\n", "成员: (生成)\n",
            "优先级: P1\n", "计划: x\n",
        ])
        _write_bug_file(tmp_path, "2026-01-01", [
            {"id": "B1", "status": "OPEN", "change": "x", "batch": "old-batch"},
            {"id": "B2", "status": "OPEN", "change": "x", "batch": "other-batch"},
        ])
        _run_batch(tmp_path, ["rename", "old-batch", "new-batch"])
        text = (tmp_path / "openspec" / "issues" / "buglist" / "2026-01-01-buglist.md").read_text(
            encoding="utf-8")
        b1_line = next(l for l in text.splitlines() if l.strip().startswith("| B1"))
        b2_line = next(l for l in text.splitlines() if l.strip().startswith("| B2"))
        assert "new-batch" in b1_line
        assert "old-batch" not in b1_line
        assert "other-batch" in b2_line  # 不同批次的项不受影响

    def test_rename_syncs_item_batch_tag_in_todo_pool(self, tmp_path):
        _write_batches_md(tmp_path, [
            "### old-batch — 清理项\n", "状态: PLANNED\n", "成员: (生成)\n",
            "优先级: P1\n", "计划: x\n",
        ])
        _write_todo_file(tmp_path, "2026-01", [
            {"id": "T1", "status": "OPEN", "change": "x", "batch": "old-batch"},
        ])
        _run_batch(tmp_path, ["rename", "old-batch", "new-batch"])
        text = (tmp_path / "openspec" / "issues" / "todolist" / "2026-01-todolist.md").read_text(
            encoding="utf-8")
        t1_line = next(l for l in text.splitlines() if l.strip().startswith("| T1"))
        assert "new-batch" in t1_line

    def test_rename_syncs_across_both_pools_in_one_call(self, tmp_path):
        _write_batches_md(tmp_path, [
            "### old-batch — 清理项\n", "状态: PLANNED\n", "成员: (生成)\n",
            "优先级: P1\n", "计划: x\n",
        ])
        _write_bug_file(tmp_path, "2026-01-01", [
            {"id": "B1", "status": "OPEN", "change": "x", "batch": "old-batch"},
        ])
        _write_todo_file(tmp_path, "2026-01", [
            {"id": "T1", "status": "OPEN", "change": "x", "batch": "old-batch"},
        ])
        _run_batch(tmp_path, ["rename", "old-batch", "new-batch"])
        bug_text = (tmp_path / "openspec" / "issues" / "buglist" / "2026-01-01-buglist.md").read_text(
            encoding="utf-8")
        todo_text = (tmp_path / "openspec" / "issues" / "todolist" / "2026-01-todolist.md").read_text(
            encoding="utf-8")
        assert "new-batch" in next(l for l in bug_text.splitlines() if l.strip().startswith("| B1"))
        assert "new-batch" in next(l for l in todo_text.splitlines() if l.strip().startswith("| T1"))

    def test_rename_does_not_flip_item_status(self, tmp_path):
        """rename 只改批次 tag，不该像 triage 那样顺带把未分诊开放态推成 PROPOSED——
        这是 rename 不复用 triage 子命令的原因（区别于其状态推进副作用）。"""
        _write_batches_md(tmp_path, [
            "### old-batch — 清理项\n", "状态: PLANNED\n", "成员: (生成)\n",
            "优先级: P1\n", "计划: x\n",
        ])
        _write_bug_file(tmp_path, "2026-01-01", [
            {"id": "B1", "status": "OPEN", "change": "x", "batch": "old-batch"},
        ])
        _run_batch(tmp_path, ["rename", "old-batch", "new-batch"])
        text = (tmp_path / "openspec" / "issues" / "buglist" / "2026-01-01-buglist.md").read_text(
            encoding="utf-8")
        b1_line = next(l for l in text.splitlines() if l.strip().startswith("| B1"))
        assert "| OPEN |" in b1_line

    def test_rename_unknown_old_key_errors_non_silently(self, tmp_path):
        _write_batches_md(tmp_path, ["### batch-1 — x\n", "状态: PLANNED\n"])
        proc = _run_batch_raw(tmp_path, ["rename", "nope", "new"])
        assert proc.returncode != 0
        assert proc.stderr.strip() != ""

    def test_rename_to_already_existing_key_errors_does_not_merge(self, tmp_path):
        _write_batches_md(tmp_path, [
            "### a — A\n", "状态: PLANNED\n", "成员: (生成)\n", "优先级: P1\n", "计划: x\n",
            "### b — B\n", "状态: PLANNED\n", "成员: (生成)\n", "优先级: P1\n", "计划: x\n",
        ])
        proc = _run_batch_raw(tmp_path, ["rename", "a", "b"])
        assert proc.returncode != 0
        content = _read_batches(tmp_path)
        # 两条目都还在，未被合并
        assert "### a — A" in content
        assert "### b — B" in content


class TestReindexSyncBatchesMembers:
    """Task 11 载重约束 1（成员填充）：reindex 按 item 的批次 tag 聚合成员，
    填 batches.md 每批的 `成员:` 生成行，成员 id 排序确定。"""

    def test_reindex_fills_members_line_sorted_by_id_across_both_pools(self, tmp_path):
        _write_batches_md(tmp_path, [
            "### batch-1 — 清理项\n", "状态: PLANNED\n", "成员: (生成)\n",
            "优先级: P1\n", "计划: x\n",
        ])
        _write_bug_file(tmp_path, "2026-01-01", [
            {"id": "B1", "status": "OPEN", "change": "x", "batch": "batch-1"},
        ])
        _write_todo_file(tmp_path, "2026-01", [
            {"id": "T2", "status": "OPEN", "change": "x", "batch": "batch-1"},
        ])
        _run_reindex(tmp_path)
        content = _read_batches(tmp_path)
        assert "成员: (生成) B1, T2" in content


class TestReindexBatchDoneCriterion:
    """Task 11 载重约束 2（D1 关键判据）：成员数 ≥1 且全部进入各自 pool 终态集
    （bug: FIXED/WONTFIX；todo: DONE/WONTDO）→ `状态:` 生成行同步为 DONE。"""

    def test_all_members_fixed_or_done_marks_batch_done(self, tmp_path):
        _write_batches_md(tmp_path, [
            "### batch-1 — 清理项\n", "状态: PLANNED\n", "成员: (生成)\n",
            "优先级: P1\n", "计划: x\n",
        ])
        _write_bug_file(tmp_path, "2026-01-01", [
            {"id": "B1", "status": "FIXED", "change": "x", "batch": "batch-1"},
        ])
        _write_todo_file(tmp_path, "2026-01", [
            {"id": "T1", "status": "DONE", "change": "x", "batch": "batch-1"},
        ])
        _run_reindex(tmp_path)
        content = _read_batches(tmp_path)
        assert "状态: DONE" in content
        assert "状态: PLANNED" not in content


class TestReindexBatchDoneCriterionIncludesWontVariants:
    """Task 11 载重约束 3：成员全是 FIXED/WONTFIX/DONE/WONTDO（含 WONT*）也算
    完成 → DONE（WONT* 是合法闭合）。"""

    def test_all_members_terminal_via_wont_variants_marks_done(self, tmp_path):
        _write_batches_md(tmp_path, [
            "### batch-1 — 清理项\n", "状态: PLANNED\n", "成员: (生成)\n",
            "优先级: P1\n", "计划: x\n",
        ])
        _write_bug_file(tmp_path, "2026-01-01", [
            {"id": "B1", "status": "WONTFIX", "change": "x", "batch": "batch-1"},
        ])
        _write_todo_file(tmp_path, "2026-01", [
            {"id": "T1", "status": "WONTDO", "change": "x", "batch": "batch-1"},
        ])
        _run_reindex(tmp_path)
        content = _read_batches(tmp_path)
        assert "状态: DONE" in content


class TestReindexZeroMemberBatchStaysPlanned:
    """Task 11 载重约束 2（D1 反例）：0 成员批次 MUST 保持 PLANNED——防 vacuous-truth
    假 DONE（全称量词对空集永真，必须显式排除成员数=0）。"""

    def test_zero_member_batch_not_marked_done(self, tmp_path):
        _write_batches_md(tmp_path, [
            "### batch-1 — 清理项\n", "状态: PLANNED\n", "成员: (生成)\n",
            "优先级: P1\n", "计划: x\n",
        ])
        # 无任何 item 引用 batch-1（两池都不写 dated 文件）
        _run_reindex(tmp_path)
        content = _read_batches(tmp_path)
        assert "状态: PLANNED" in content
        assert "状态: DONE" not in content
        assert "成员: (生成)" in content


class TestReindexDoesNotOverrideHumanDoneStatus:
    """Task 11 载重约束 4（Q3 不越权纠正）：批次 batches.md 里标了 DONE 但成员未全进
    终态（有 OPEN 等）→ reindex 只追加 `⚠️ 不一致` 警告，绝不改人写的 `状态:` 值。"""

    def test_appends_warning_but_keeps_human_done_value_unchanged(self, tmp_path):
        _write_batches_md(tmp_path, [
            "### batch-1 — 清理项\n", "状态: DONE\n", "成员: (生成)\n",
            "优先级: P1\n", "计划: x\n",
        ])
        _write_bug_file(tmp_path, "2026-01-01", [
            {"id": "B1", "status": "OPEN", "change": "x", "batch": "batch-1"},
        ])
        _run_reindex(tmp_path)
        content = _read_batches(tmp_path)
        assert "状态: DONE" in content  # 人写值不被改回 PLANNED/其它
        assert "⚠️ 不一致" in content


class TestReindexOrphanBatchTag:
    """Task 11 载重约束 5（Q2/D5 orphan）：item 有批次 tag 但 batches.md 无此 key →
    reindex stderr 显式报警、不静默生成 ghost 批次条目。"""

    def test_orphan_batch_tag_warns_on_stderr_without_creating_ghost_entry(self, tmp_path):
        _write_bug_file(tmp_path, "2026-01-01", [
            {"id": "B1", "status": "OPEN", "change": "x", "batch": "ghost-batch"},
        ])
        proc = _run_reindex(tmp_path)
        assert "ghost-batch" in proc.stderr
        assert "orphan" in proc.stderr
        # 不静默生成 ghost 条目：batches.md 压根不该被凭空建出来
        assert not (tmp_path / "openspec" / "issues" / "batches.md").exists()

    def test_orphan_batch_tag_when_batches_md_has_other_entries_does_not_add_ghost_key(
        self, tmp_path
    ):
        _write_batches_md(tmp_path, [
            "### batch-1 — 清理项\n", "状态: PLANNED\n", "成员: (生成)\n",
            "优先级: P1\n", "计划: x\n",
        ])
        _write_bug_file(tmp_path, "2026-01-01", [
            {"id": "B1", "status": "OPEN", "change": "x", "batch": "ghost-batch"},
        ])
        proc = _run_reindex(tmp_path)
        assert "ghost-batch" in proc.stderr
        content = _read_batches(tmp_path)
        assert "ghost-batch" not in content
        assert "### batch-1" in content


class TestReindexBatchesSyncIdempotent:
    """Task 11 载重约束 6：整体 reindex 幂等——连跑两次 batches.md 逐字节稳定，
    ⚠️ 不一致 行不累积重复。"""

    def test_warning_line_not_duplicated_and_batches_md_byte_stable_on_rerun(self, tmp_path):
        _write_batches_md(tmp_path, [
            "### batch-1 — 清理项\n", "状态: DONE\n", "成员: (生成)\n",
            "优先级: P1\n", "计划: x\n",
        ])
        _write_bug_file(tmp_path, "2026-01-01", [
            {"id": "B1", "status": "OPEN", "change": "x", "batch": "batch-1"},
        ])
        _run_reindex(tmp_path)
        first = _read_batches(tmp_path)
        _run_reindex(tmp_path)
        second = _read_batches(tmp_path)
        assert first == second
        assert first.count("⚠️ 不一致") == 1


class TestReindexStatusLineFullwidthColonCarry:
    """Task 11 载重约束 7（Task 10 carry）：`状态：`（全角冒号）人手误按也要被解析
    识别（放宽正则兼容全/半角），不静默留僵尸行（不会额外插入第二条状态行）。"""

    def test_fullwidth_colon_status_line_recognized_and_normalized_no_duplicate(
        self, tmp_path
    ):
        _write_batches_md(tmp_path, [
            "### batch-1 — 清理项\n", "状态： PLANNED\n", "成员: (生成)\n",
            "优先级: P1\n", "计划: x\n",
        ])
        _write_bug_file(tmp_path, "2026-01-01", [
            {"id": "B1", "status": "FIXED", "change": "x", "batch": "batch-1"},
        ])
        _run_reindex(tmp_path)
        content = _read_batches(tmp_path)
        status_lines = [l for l in content.splitlines() if l.startswith("状态")]
        assert len(status_lines) == 1
        assert status_lines[0] == "状态: DONE"


# ── fixtures ─────────────────────────────────────────────────────────────────

def _run_reindex(root):
    proc = subprocess.run(
        [sys.executable, SCRIPT, "--root", str(root), "reindex"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return proc


def _index_path(root):
    return Path(root) / "openspec" / "issues" / "INDEX.md"


def _read_index(root):
    return _index_path(root).read_text(encoding="utf-8")


def _read_index_bytes(root):
    return _index_path(root).read_bytes()


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


def _run_batch_raw(root, extra_args):
    return subprocess.run(
        [sys.executable, SCRIPT, "--root", str(root), "batch"] + extra_args,
        capture_output=True, text=True,
    )


def _run_batch(root, extra_args):
    proc = _run_batch_raw(root, extra_args)
    assert proc.returncode == 0, proc.stderr
    return proc


def _batches_path(root):
    return Path(root) / "openspec" / "issues" / "batches.md"


def _read_batches(root):
    return _batches_path(root).read_text(encoding="utf-8")


def _write_batches_md(root, lines):
    path = _batches_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")
