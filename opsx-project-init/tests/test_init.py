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

    def test_root_review_html_substitutes_project_name(self, tmp_path):
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        copy_review_tool(str(project_dir))
        osroot = project_dir / "openspec"
        content = (osroot / "review.html").read_text(encoding="utf-8")
        template = (osroot / "tools" / "review-stub.html").read_text(encoding="utf-8")
        # The template source (as copied into openspec/tools/) must stay RAW/un-substituted —
        # it's read by the other two producers (change-review-stub.py hook, gen_review_stub.py)
        # as their own substitution source, so it must still contain the literal token.
        assert "__PROJECT_NAME__" in template
        # The generated root review.html, in contrast, must have the token substituted with
        # the project's directory basename — and be otherwise byte-identical to the template.
        assert "__PROJECT_NAME__" not in content
        assert content == template.replace("__PROJECT_NAME__", "my-project")

    def test_serve_sh_is_executable(self, tmp_path):
        copy_review_tool(str(tmp_path))
        mode = (tmp_path / "openspec" / "serve.sh").stat().st_mode
        assert mode & stat.S_IXUSR

    def test_idempotent_rerun_overwrites_cleanly(self, tmp_path):
        project_dir = tmp_path / "another-project"
        project_dir.mkdir()
        copy_review_tool(str(project_dir))
        copy_review_tool(str(project_dir))  # update-mode re-run
        osroot = project_dir / "openspec"
        assert (osroot / "review.html").is_file()
        content = (osroot / "review.html").read_text(encoding="utf-8")
        template = (osroot / "tools" / "review-stub.html").read_text(encoding="utf-8")
        # still a clean substituted copy, not duplicated/appended, not re-substituted-twice
        assert content == template.replace("__PROJECT_NAME__", "another-project")


class TestEnsureGlobalHooks:
    def _settings_path(self, home):
        return home / "settings.json"

    def test_installs_and_registers_a_new_hook_spec(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home))
        src = tmp_path / "myhook.py"
        src.write_text("print('hi')\n", encoding="utf-8")
        spec = {
            "name": "myhook.py",
            "src": str(src),
            "event": "PostToolUse",
            "matcher": "Bash",
            "cmd": 'python3 "$HOME/.claude/hooks/myhook.py"',
        }
        msg = init_mod.ensure_global_hook(spec)
        assert "安装" in msg
        assert (home / "hooks" / "myhook.py").is_file()
        data = json.loads(self._settings_path(home).read_text(encoding="utf-8"))
        assert data["hooks"]["PostToolUse"][0]["matcher"] == "Bash"
        assert "myhook.py" in data["hooks"]["PostToolUse"][0]["hooks"][0]["command"]

    def test_rerun_is_idempotent_no_duplicate_registration(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home))
        src = tmp_path / "myhook.py"
        src.write_text("print('hi')\n", encoding="utf-8")
        spec = {
            "name": "myhook.py",
            "src": str(src),
            "event": "PostToolUse",
            "matcher": "Bash",
            "cmd": 'python3 "$HOME/.claude/hooks/myhook.py"',
        }
        init_mod.ensure_global_hook(spec)
        init_mod.ensure_global_hook(spec)
        data = json.loads(self._settings_path(home).read_text(encoding="utf-8"))
        assert len(data["hooks"]["PostToolUse"]) == 1

    def test_two_different_hooks_land_in_their_own_event_lists(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home))
        pre_src = tmp_path / "pre.py"
        pre_src.write_text("print('pre')\n", encoding="utf-8")
        post_src = tmp_path / "post.py"
        post_src.write_text("print('post')\n", encoding="utf-8")
        init_mod.ensure_global_hook({
            "name": "pre.py", "src": str(pre_src), "event": "PreToolUse",
            "matcher": "Bash", "cmd": 'python3 "$HOME/.claude/hooks/pre.py"',
        })
        init_mod.ensure_global_hook({
            "name": "post.py", "src": str(post_src), "event": "PostToolUse",
            "matcher": "Bash", "cmd": 'python3 "$HOME/.claude/hooks/post.py"',
        })
        data = json.loads(self._settings_path(home).read_text(encoding="utf-8"))
        assert len(data["hooks"]["PreToolUse"]) == 1
        assert len(data["hooks"]["PostToolUse"]) == 1

    def test_preexisting_single_hook_registration_still_recognized(self, tmp_path, monkeypatch):
        """Backward compat: a settings.json written by the OLD single-hook ensure_global_hook()
        must still be recognized as 'already registered' by the new generalized version."""
        home = tmp_path / "home"
        home.mkdir()
        (home / "hooks").mkdir()
        src = tmp_path / "ff0.py"
        src.write_text("print('ff0')\n", encoding="utf-8")
        (home / "hooks" / "ff0.py").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home))
        (self._settings_path(home)).write_text(json.dumps({
            "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
                {"type": "command", "command": 'python3 "$HOME/.claude/hooks/ff0.py"'}
            ]}]}
        }), encoding="utf-8")
        spec = {
            "name": "ff0.py", "src": str(src), "event": "PreToolUse",
            "matcher": "Bash", "cmd": 'python3 "$HOME/.claude/hooks/ff0.py"',
        }
        msg = init_mod.ensure_global_hook(spec)
        assert "已注册" in msg
        data = json.loads(self._settings_path(home).read_text(encoding="utf-8"))
        assert len(data["hooks"]["PreToolUse"]) == 1  # not duplicated
