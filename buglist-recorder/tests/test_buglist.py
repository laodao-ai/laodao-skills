"""
Tests for buglist.py's `doc`（关联文档）field: normalization, soft validation,
detail-block rendering, and change-based auto-default.
Run with: python3 -m pytest buglist-recorder/tests/ -v
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import buglist as buglist_mod
from buglist import normalize_doc_paths, auto_default_doc, validate_doc_paths, atomic_write

SCRIPT = str(Path(__file__).parent.parent / "scripts" / "buglist.py")


def run_add(root, payload):
    """通过真实 CLI 调 add 子命令（stdin 喂 JSON），返回 CompletedProcess。"""
    return subprocess.run(
        [sys.executable, SCRIPT, "--root", str(root), "add"],
        input=json.dumps(payload), capture_output=True, text=True,
    )


def base_payload(**overrides):
    payload = {
        "module": "data_publish.c:120",
        "summary": "envelope type 为空",
        "priority": "P1",
        "phenomenon": "服务端收到的 envelope.type 恒为空字符串",
    }
    payload.update(overrides)
    return payload


class TestNormalizeDocPaths:
    def test_bare_path_gets_prefix(self):
        assert normalize_doc_paths("changes/foo/design.md") == ["openspec/changes/foo/design.md"]

    def test_already_prefixed_path_unchanged(self):
        assert normalize_doc_paths("openspec/changes/foo/design.md") == ["openspec/changes/foo/design.md"]

    def test_list_input_normalizes_each(self):
        result = normalize_doc_paths(["changes/foo/design.md", "openspec/rules/database.md"])
        assert result == ["openspec/changes/foo/design.md", "openspec/rules/database.md"]

    def test_empty_or_none_returns_empty_list(self):
        assert normalize_doc_paths(None) == []
        assert normalize_doc_paths("") == []
        assert normalize_doc_paths([]) == []

    def test_non_md_path_kept_as_is_but_prefixed(self):
        assert normalize_doc_paths("rules/database.yaml") == ["openspec/rules/database.yaml"]


class TestDetailBlockRendering:
    def test_block_contains_doc_line_when_doc_given(self, tmp_path):
        payload = base_payload(doc=["changes/foo/design.md", "rules/database.md"])
        (tmp_path / "openspec" / "changes" / "foo").mkdir(parents=True)
        (tmp_path / "openspec" / "changes" / "foo" / "design.md").write_text("x", encoding="utf-8")
        (tmp_path / "openspec" / "rules").mkdir(parents=True)
        (tmp_path / "openspec" / "rules" / "database.md").write_text("x", encoding="utf-8")
        proc = run_add(tmp_path, payload)
        assert proc.returncode == 0, proc.stderr
        content = _buglist_content(tmp_path)
        assert "**关联文档**：`openspec/changes/foo/design.md`、`openspec/rules/database.md`" in content

    def test_no_doc_line_when_doc_absent(self, tmp_path):
        payload = base_payload(change="no-such-change")
        proc = run_add(tmp_path, payload)
        assert proc.returncode == 0, proc.stderr
        content = _buglist_content(tmp_path)
        assert "**关联文档**" not in content


class TestSoftValidation:
    def test_warns_but_still_records_nonexistent_doc(self, tmp_path):
        payload = base_payload(doc="changes/ghost/design.md")
        proc = run_add(tmp_path, payload)
        assert proc.returncode == 0, proc.stderr
        assert "WARNING" in proc.stderr
        assert "openspec/changes/ghost/design.md" in proc.stderr
        content = _buglist_content(tmp_path)
        assert "**关联文档**：`openspec/changes/ghost/design.md`" in content


class TestAutoDefaultDoc:
    def test_picks_design_over_proposal(self, tmp_path):
        d = tmp_path / "openspec" / "changes" / "foo"
        d.mkdir(parents=True)
        (d / "design.md").write_text("x", encoding="utf-8")
        (d / "proposal.md").write_text("x", encoding="utf-8")
        assert auto_default_doc(str(tmp_path), "foo") == ["openspec/changes/foo/design.md"]

    def test_finds_proposal_when_no_design(self, tmp_path):
        d = tmp_path / "openspec" / "changes" / "foo"
        d.mkdir(parents=True)
        (d / "proposal.md").write_text("x", encoding="utf-8")
        assert auto_default_doc(str(tmp_path), "foo") == ["openspec/changes/foo/proposal.md"]

    def test_finds_archived_change_via_glob(self, tmp_path):
        d = tmp_path / "openspec" / "changes" / "archive" / "2026-01-01-foo"
        d.mkdir(parents=True)
        (d / "design.md").write_text("x", encoding="utf-8")
        result = auto_default_doc(str(tmp_path), "foo")
        assert result == ["openspec/changes/archive/2026-01-01-foo/design.md"]

    def test_skips_when_multiple_archived_matches(self, tmp_path):
        for datestamp in ("2026-01-01", "2026-02-02"):
            d = tmp_path / "openspec" / "changes" / "archive" / f"{datestamp}-foo"
            d.mkdir(parents=True)
            (d / "design.md").write_text("x", encoding="utf-8")
        assert auto_default_doc(str(tmp_path), "foo") == []

    def test_empty_when_nothing_matches(self, tmp_path):
        assert auto_default_doc(str(tmp_path), "foo") == []

    def test_ambiguous_archive_dirs_skip_even_if_only_one_has_proposal(self, tmp_path):
        """回归 Finding 1：两个归档目录都匹配 `*-{change}`（目录级本就歧义），
        只有其中一个恰好带 proposal.md（另一个只有 design.md）。修复前的 bug：per-filename
        分别判断『唯一匹配』，导致 design.md 判定歧义（2 个）但 proposal.md 判定不歧义（1 个），
        从而错误地悄悄采用了那个歧义目录的 proposal.md。歧义检查必须在『目录』这一级只做一次：
        `*-{change}` glob 命中 2 个目录就该整层跳过，返回 []。"""
        d1 = tmp_path / "openspec" / "changes" / "archive" / "2026-01-01-foo"
        d1.mkdir(parents=True)
        (d1 / "design.md").write_text("x", encoding="utf-8")
        (d1 / "proposal.md").write_text("x", encoding="utf-8")
        d2 = tmp_path / "openspec" / "changes" / "archive" / "2026-02-02-foo"
        d2.mkdir(parents=True)
        (d2 / "design.md").write_text("x", encoding="utf-8")
        assert auto_default_doc(str(tmp_path), "foo") == []

    def test_empty_when_no_change(self, tmp_path):
        assert auto_default_doc(str(tmp_path), "") == []
        assert auto_default_doc(str(tmp_path), None) == []

    def test_add_auto_defaults_from_change_when_doc_missing(self, tmp_path):
        d = tmp_path / "openspec" / "changes" / "foo"
        d.mkdir(parents=True)
        (d / "design.md").write_text("x", encoding="utf-8")
        payload = base_payload(change="foo")
        proc = run_add(tmp_path, payload)
        assert proc.returncode == 0, proc.stderr
        content = _buglist_content(tmp_path)
        assert "**关联文档**：`openspec/changes/foo/design.md`" in content

    def test_explicit_doc_not_overridden_by_auto_default(self, tmp_path):
        d = tmp_path / "openspec" / "changes" / "foo"
        d.mkdir(parents=True)
        (d / "design.md").write_text("x", encoding="utf-8")
        payload = base_payload(change="foo", doc="rules/other.md")
        proc = run_add(tmp_path, payload)
        assert proc.returncode == 0, proc.stderr
        content = _buglist_content(tmp_path)
        assert "**关联文档**：`openspec/rules/other.md`" in content
        assert "changes/foo/design.md" not in content


class TestBatchColumn:
    def test_add_writes_批次_column_at_end(self, tmp_path):
        payload = base_payload()
        proc = run_add(tmp_path, payload)
        assert proc.returncode == 0, proc.stderr
        content = _buglist_content(tmp_path)
        header = [l for l in content.splitlines() if l.startswith("| ID |")][0]
        assert header.rstrip().endswith("| 批次 |")
        row = [l for l in content.splitlines() if l.startswith("| B1 ")][0]
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        assert len(cells) == 8 and cells[7] == ""

    def test_scan_old_7col_file_batch_none(self, tmp_path):
        """旧格式（无批次列，7 列）文件 scan 不报错，batch 读为 None（I8 向后兼容）。"""
        buglists_dir = tmp_path / "openspec" / "issues" / "buglist"
        buglists_dir.mkdir(parents=True)
        old_content = (
            "# 2026-01-01 Buglist\n\n"
            "> 来源：<未注明>\n"
            "> 创建日期：2026-01-01\n\n"
            "## 状态总览\n\n"
            "| ID | 模块 | 问题摘要 | 优先级 | 状态 | 时间 | 关联Change |\n"
            "|----|------|----------|--------|------|------|------------|\n"
            "| B1 | `foo.c:10` | 旧数据 | P1 | OPEN | 10:00 | - |\n\n"
            "---\n\n"
            "## B1: 旧数据\n\n"
            "| 属性 | 值 |\n"
            "|------|------|\n"
            "| 模块 | `foo.c:10` |\n"
            "| 优先级 | P1 |\n"
            "| 状态 | OPEN |\n\n"
            "**现象**：占位\n\n"
            "**根因**：<待分析>\n\n"
            "**修复方案**：\n- <待补充>\n\n"
            "**影响范围**：<待评估>\n"
        )
        (buglists_dir / "2026-01-01-buglist.md").write_text(old_content, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, SCRIPT, "--root", str(tmp_path), "scan", "--json"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        result = json.loads(proc.stdout)
        b1 = [b for b in result["bugs"] if b["id"] == "B1"][0]
        assert b1["batch"] is None
        assert result["problems"] == []

    def test_scan_reads_batch_when_present(self, tmp_path):
        payload = base_payload()
        proc = run_add(tmp_path, payload)
        assert proc.returncode == 0, proc.stderr
        # 手动把批次列写入刚新增的行（cmd_add 默认留空）
        path = tmp_path / "openspec" / "issues" / "buglist"
        files = list(path.glob("*-buglist.md"))
        content = files[0].read_text(encoding="utf-8")
        lines = content.splitlines(keepends=True)
        for i, ln in enumerate(lines):
            if ln.startswith("| B1 "):
                cells = [c.strip() for c in ln.strip().strip("|").split("|")]
                cells[7] = "batch-1"
                lines[i] = "| " + " | ".join(cells) + " |\n"
        files[0].write_text("".join(lines), encoding="utf-8")
        scan_proc = subprocess.run(
            [sys.executable, SCRIPT, "--root", str(tmp_path), "scan", "--json"],
            capture_output=True, text=True,
        )
        assert scan_proc.returncode == 0, scan_proc.stderr
        result = json.loads(scan_proc.stdout)
        b1 = [b for b in result["bugs"] if b["id"] == "B1"][0]
        assert b1["batch"] == "batch-1"


class TestAtomicWrite:
    def test_writes_content_and_creates_parent_dir(self, tmp_path):
        target = tmp_path / "sub" / "dir" / "file.md"
        atomic_write(str(target), "hello\nworld\n")
        assert target.read_text(encoding="utf-8") == "hello\nworld\n"

    def test_overwrites_existing_file(self, tmp_path):
        target = tmp_path / "file.md"
        target.write_text("old", encoding="utf-8")
        atomic_write(str(target), "new")
        assert target.read_text(encoding="utf-8") == "new"

    def test_overwrite_preserves_original_file_permissions(self, tmp_path):
        """回归：tempfile.mkstemp 固定以 0600 创建临时文件，os.replace 是纯 rename，
        若不显式对齐权限，覆写会让已存在文件的权限被静默从 0644 收紧到 0600。"""
        target = tmp_path / "file.md"
        target.write_text("old", encoding="utf-8")
        os.chmod(target, 0o644)
        atomic_write(str(target), "new")
        assert (os.stat(target).st_mode & 0o777) == 0o644

    def test_new_file_gets_default_permissions(self, tmp_path):
        target = tmp_path / "brand_new.md"
        atomic_write(str(target), "content")
        assert (os.stat(target).st_mode & 0o777) == 0o644

    def test_no_leftover_tmp_file_after_success(self, tmp_path):
        target = tmp_path / "file.md"
        atomic_write(str(target), "content")
        leftovers = [p for p in tmp_path.iterdir() if p.name != "file.md"]
        assert leftovers == []

    def test_original_file_unchanged_when_replace_fails(self, tmp_path, monkeypatch):
        """中途异常（这里模拟 os.replace 本身失败）：原文件必须原样保留，不能被截断/清空，
        且不留残留 .tmp 文件（finally 兜底清理）。"""
        target = tmp_path / "file.md"
        target.write_text("original content", encoding="utf-8")

        def boom(src, dst):
            raise OSError("simulated os.replace failure")

        monkeypatch.setattr(buglist_mod.os, "replace", boom)

        with pytest.raises(OSError):
            atomic_write(str(target), "new content that must not land")

        assert target.read_text(encoding="utf-8") == "original content"
        leftovers = [p for p in tmp_path.iterdir() if p.name != "file.md"]
        assert leftovers == []


def _buglist_content(root):
    d = root / "openspec" / "issues" / "buglist"
    files = list(d.glob("*-buglist.md"))
    assert len(files) == 1
    return files[0].read_text(encoding="utf-8")
