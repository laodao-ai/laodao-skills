"""
Tests for todolist.py's `doc`（关联文档）field: normalization, soft validation,
detail-block rendering, and change-based auto-default.
Run with: python3 -m pytest todolist-recorder/tests/ -v
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import todolist as todolist_mod
from todolist import normalize_doc_paths, auto_default_doc, validate_doc_paths

SCRIPT = str(Path(__file__).parent.parent / "scripts" / "todolist.py")


def run_add(root, payload):
    return subprocess.run(
        [sys.executable, SCRIPT, "--root", str(root), "add"],
        input=json.dumps(payload), capture_output=True, text=True,
    )


def base_payload(**overrides):
    payload = {
        "module": "meter_collect.c",
        "summary": "温度采样改 DMA 批量读取",
        "type": "性能优化",
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
        content = _todolist_content(tmp_path)
        assert "**关联文档**：`openspec/changes/foo/design.md`、`openspec/rules/database.md`" in content

    def test_no_doc_line_when_doc_absent(self, tmp_path):
        payload = base_payload(change="no-such-change")
        proc = run_add(tmp_path, payload)
        assert proc.returncode == 0, proc.stderr
        content = _todolist_content(tmp_path)
        assert "**关联文档**" not in content

    def test_doc_alone_builds_a_block_even_without_narrative_fields(self, tmp_path):
        """轻量项默认不建块；但一旦有 doc，必须建块才能承载 doc 行（doc 是 block-only 特性）。"""
        payload = base_payload(doc="rules/database.md")
        proc = run_add(tmp_path, payload)
        assert proc.returncode == 0, proc.stderr
        result = json.loads(proc.stdout)
        assert result["block"] is True
        content = _todolist_content(tmp_path)
        assert "**关联文档**：`openspec/rules/database.md`" in content


class TestSoftValidation:
    def test_warns_but_still_records_nonexistent_doc(self, tmp_path):
        payload = base_payload(doc="changes/ghost/design.md")
        proc = run_add(tmp_path, payload)
        assert proc.returncode == 0, proc.stderr
        assert "WARNING" in proc.stderr
        assert "openspec/changes/ghost/design.md" in proc.stderr
        content = _todolist_content(tmp_path)
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

    def test_add_auto_default_enriches_block_created_for_other_reason(self, tmp_path):
        """auto-default 探测到 doc，但只有在块已经因为别的理由（这里是 motivation）要建时，
        才把这个 doc 塞进去——不是 auto-default 自己触发建块。"""
        d = tmp_path / "openspec" / "changes" / "foo"
        d.mkdir(parents=True)
        (d / "design.md").write_text("x", encoding="utf-8")
        payload = base_payload(change="foo", motivation="降低采样耗时")
        proc = run_add(tmp_path, payload)
        assert proc.returncode == 0, proc.stderr
        result = json.loads(proc.stdout)
        assert result["block"] is True
        content = _todolist_content(tmp_path)
        assert "**关联文档**：`openspec/changes/foo/design.md`" in content
        assert "**动机**：降低采样耗时" in content

    def test_explicit_doc_not_overridden_by_auto_default(self, tmp_path):
        d = tmp_path / "openspec" / "changes" / "foo"
        d.mkdir(parents=True)
        (d / "design.md").write_text("x", encoding="utf-8")
        payload = base_payload(change="foo", doc="rules/other.md")
        proc = run_add(tmp_path, payload)
        assert proc.returncode == 0, proc.stderr
        content = _todolist_content(tmp_path)
        assert "**关联文档**：`openspec/rules/other.md`" in content
        assert "changes/foo/design.md" not in content

    def test_auto_default_alone_does_not_force_a_block(self, tmp_path):
        """回归 Finding 2：change 能解出已存在的 design.md，但没有显式 doc、也没有
        motivation/approach/note 时，auto-default 不应单独把一个轻量项升级成带块的项——
        条目应仍是总览表里的一行，不出现块，也不出现『关联文档』行。"""
        d = tmp_path / "openspec" / "changes" / "foo"
        d.mkdir(parents=True)
        (d / "design.md").write_text("x", encoding="utf-8")
        payload = base_payload(change="foo")
        proc = run_add(tmp_path, payload)
        assert proc.returncode == 0, proc.stderr
        result = json.loads(proc.stdout)
        assert result["block"] is False
        content = _todolist_content(tmp_path)
        assert "**关联文档**" not in content
        assert f"## {result['id']}:" not in content  # 没有该项的详细块标题
        assert "\n---\n" not in content  # 没有块分隔线（表头分隔行 |----| 不受影响）

    def test_explicit_doc_alone_still_forces_a_block(self, tmp_path):
        """回归护栏：显式传 doc（没有 motivation/approach/note）必须仍然强制建块并带上 doc 行，
        这是 Finding 2 修复前就有的行为，不应被这次改动破坏。"""
        payload = base_payload(doc="rules/other.md")
        proc = run_add(tmp_path, payload)
        assert proc.returncode == 0, proc.stderr
        result = json.loads(proc.stdout)
        assert result["block"] is True
        content = _todolist_content(tmp_path)
        assert "**关联文档**：`openspec/rules/other.md`" in content


class TestBatchColumn:
    def test_add_writes_批次_column_at_end(self, tmp_path):
        payload = base_payload()
        proc = run_add(tmp_path, payload)
        assert proc.returncode == 0, proc.stderr
        content = _todolist_content(tmp_path)
        header = [l for l in content.splitlines() if l.startswith("| ID |")][0]
        assert header.rstrip().endswith("| 批次 |")
        row = [l for l in content.splitlines() if l.startswith("| T1 ")][0]
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        assert len(cells) == 8 and cells[7] == ""

    def test_scan_old_7col_file_batch_none(self, tmp_path):
        """旧格式（无批次列，7 列）文件 scan 不报错，batch 读为 None（I8 向后兼容）。"""
        todolists_dir = tmp_path / "openspec" / "todolists"
        todolists_dir.mkdir(parents=True)
        old_content = (
            "# 2026-01 TODO\n\n"
            "> 项目：<未注明>\n\n"
            "## 状态总览\n\n"
            "| ID | 模块 | 描述 | 类型 | 状态 | 时间 | 关联Change |\n"
            "|----|------|------|------|------|------|------------|\n"
            "| T1 | `foo.c` | 旧数据 | 性能优化 | OPEN | 10:00 | - |\n"
        )
        (todolists_dir / "2026-01-todolist.md").write_text(old_content, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, SCRIPT, "--root", str(tmp_path), "scan", "--json"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        result = json.loads(proc.stdout)
        t1 = [b for b in result["items"] if b["id"] == "T1"][0]
        assert t1["batch"] is None
        assert result["problems"] == []

    def test_scan_reads_batch_when_present(self, tmp_path):
        payload = base_payload()
        proc = run_add(tmp_path, payload)
        assert proc.returncode == 0, proc.stderr
        # 手动把批次列写入刚新增的行（cmd_add 默认留空）
        path = tmp_path / "openspec" / "todolists"
        files = list(path.glob("*-todolist.md"))
        content = files[0].read_text(encoding="utf-8")
        lines = content.splitlines(keepends=True)
        for i, ln in enumerate(lines):
            if ln.startswith("| T1 "):
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
        t1 = [b for b in result["items"] if b["id"] == "T1"][0]
        assert t1["batch"] == "batch-1"


def _todolist_content(root):
    d = root / "openspec" / "todolists"
    files = list(d.glob("*-todolist.md"))
    assert len(files) == 1
    return files[0].read_text(encoding="utf-8")
