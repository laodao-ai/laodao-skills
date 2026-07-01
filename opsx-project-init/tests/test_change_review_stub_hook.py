"""
Tests for the change-review-stub.py PostToolUse hook.
Run with: python3 -m pytest opsx-project-init/tests/test_change_review_stub_hook.py -v
"""
import json
import subprocess
import sys
from pathlib import Path

HOOK = str(Path(__file__).parent.parent / "assets" / "hooks" / "change-review-stub.py")


def run_hook(payload, cwd):
    return subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps(payload),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=5,
    )


def make_project(tmp_path, with_review_tool=True):
    osroot = tmp_path / "openspec"
    (osroot / "changes" / "add-widget").mkdir(parents=True)
    if with_review_tool:
        (osroot / "tools").mkdir(parents=True, exist_ok=True)
        (osroot / "tools" / "review-stub.html").write_text(
            '<script>window.__OPENSPEC_REVIEW_SCOPE__ = "__SCOPE__";</script>', encoding="utf-8"
        )
        (osroot / "review.html").write_text("root", encoding="utf-8")
    return tmp_path


class TestChangeReviewStubHook:
    def test_writes_stub_when_change_dir_and_review_tool_exist(self, tmp_path):
        make_project(tmp_path)
        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": "openspec new change add-widget"},
            "cwd": str(tmp_path),
        }
        result = run_hook(payload, tmp_path)
        assert result.returncode == 0
        stub = tmp_path / "openspec" / "changes" / "add-widget" / "review.html"
        assert stub.is_file()
        assert 'window.__OPENSPEC_REVIEW_SCOPE__ = "changes/add-widget/";' in stub.read_text(encoding="utf-8")

    def test_skips_silently_when_review_tool_not_installed(self, tmp_path):
        make_project(tmp_path, with_review_tool=False)
        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": "openspec new change add-widget"},
            "cwd": str(tmp_path),
        }
        result = run_hook(payload, tmp_path)
        assert result.returncode == 0
        assert not (tmp_path / "openspec" / "changes" / "add-widget" / "review.html").exists()

    def test_skips_silently_when_change_dir_does_not_exist(self, tmp_path):
        make_project(tmp_path)
        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": "openspec new change never-created"},
            "cwd": str(tmp_path),
        }
        result = run_hook(payload, tmp_path)
        assert result.returncode == 0
        assert not (tmp_path / "openspec" / "changes" / "never-created").exists()

    def test_ignores_non_bash_tools(self, tmp_path):
        make_project(tmp_path)
        payload = {"tool_name": "Write", "tool_input": {}, "cwd": str(tmp_path)}
        result = run_hook(payload, tmp_path)
        assert result.returncode == 0

    def test_ignores_unrelated_bash_commands(self, tmp_path):
        make_project(tmp_path)
        payload = {"tool_name": "Bash", "tool_input": {"command": "git status"}, "cwd": str(tmp_path)}
        result = run_hook(payload, tmp_path)
        assert result.returncode == 0

    def test_idempotent_rerun_does_not_error(self, tmp_path):
        make_project(tmp_path)
        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": "openspec new change add-widget"},
            "cwd": str(tmp_path),
        }
        run_hook(payload, tmp_path)
        result = run_hook(payload, tmp_path)
        assert result.returncode == 0

    def test_handles_garbage_stdin_by_exiting_zero(self, tmp_path):
        make_project(tmp_path)
        result = subprocess.run(
            [sys.executable, HOOK], input="not json", cwd=str(tmp_path),
            capture_output=True, text=True, timeout=5,
        )
        assert result.returncode == 0
