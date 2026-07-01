"""
Tests for init.py's review-tool copying + generalized hook installer.
Run with: python3 -m pytest opsx-project-init/tests/test_init.py -v
"""
import json
import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import init as init_mod
from init import copy_review_tool


class TestCopyReviewTool:
    def test_copies_tools_dir_and_serve_sh_and_generates_root_review_html(self, tmp_path):
        n = copy_review_tool(str(tmp_path))
        osroot = tmp_path / "openspec"
        assert (osroot / "tools" / "engine.js").is_file()
        assert (osroot / "tools" / "engine.css").is_file()
        assert (osroot / "tools" / "review-stub.html").is_file()
        assert (osroot / "tools" / "vendor" / "marked.min.js").is_file()
        assert (osroot / "serve.sh").is_file()
        assert (osroot / "review.html").is_file()
        assert n > 0

    def test_root_review_html_has_empty_scope(self, tmp_path):
        copy_review_tool(str(tmp_path))
        content = (tmp_path / "openspec" / "review.html").read_text(encoding="utf-8")
        assert 'window.__OPENSPEC_REVIEW_SCOPE__ = "";' in content
        assert "__SCOPE__" not in content

    def test_serve_sh_is_executable(self, tmp_path):
        copy_review_tool(str(tmp_path))
        mode = (tmp_path / "openspec" / "serve.sh").stat().st_mode
        assert mode & stat.S_IXUSR

    def test_idempotent_rerun_overwrites_cleanly(self, tmp_path):
        copy_review_tool(str(tmp_path))
        copy_review_tool(str(tmp_path))  # update-mode re-run
        osroot = tmp_path / "openspec"
        assert (osroot / "review.html").is_file()
        content = (osroot / "review.html").read_text(encoding="utf-8")
        assert content.count("__OPENSPEC_REVIEW_SCOPE__") == 1  # not duplicated/appended
