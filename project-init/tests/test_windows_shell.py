from pathlib import Path
import subprocess
import sys

import pytest


sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from windows_shell import (
    END,
    START,
    apply_repo,
    diagnose,
    discover_git_bash,
    probe_python_utf8,
    replace_managed_block,
)


@pytest.fixture
def assets_dir() -> Path:
    return Path(__file__).parents[1] / "assets" / "snippets"


def test_apply_repo_creates_agent_specific_files(tmp_path, assets_dir):
    result = apply_repo(tmp_path, assets_dir)
    agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    claude = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "PowerShell" in agents and "bash.exe" in agents
    assert "Claude Code's Bash tool" in claude
    assert "& 'C:\\Program Files" not in claude
    assert claude.startswith("# CLAUDE\n")
    assert "Bash/POSIX" in agents and "Bash/POSIX" in claude
    assert "quote" in agents
    assert "Git Bash is missing or cannot be located" in claude
    assert "preview PowerShell tool" in claude
    assert result == {"AGENTS.md": "created", "CLAUDE.md": "created"}


def test_apply_repo_preserves_user_and_opsx_content_and_is_idempotent(tmp_path, assets_dir):
    original = "# AGENTS\n\nuser text\n\n<!-- opsx-init:start -->\nopsx\n<!-- opsx-init:end -->\n"
    agents_path = tmp_path / "AGENTS.md"
    agents_path.write_text(original, encoding="utf-8")
    original_bytes = agents_path.read_bytes()
    apply_repo(tmp_path, assets_dir)
    once = agents_path.read_bytes()
    apply_repo(tmp_path, assets_dir)
    twice = agents_path.read_bytes()
    assert once.startswith(original_bytes)
    assert once == twice


def test_replace_managed_block_rejects_unbalanced_markers(tmp_path):
    path = tmp_path / "AGENTS.md"
    path.write_text("before\n<!-- project-init:windows-shell:start -->\nbroken\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unbalanced managed markers"):
        replace_managed_block(path, "body")


def test_replace_managed_block_preserves_trailing_user_whitespace_on_insert(tmp_path):
    path = tmp_path / "AGENTS.md"
    original = b"# AGENTS\r\n\r\nuser text\r\n \t\r\n"
    path.write_bytes(original)

    assert replace_managed_block(path, "body") == "inserted"

    assert path.read_bytes().startswith(original)


def test_replace_managed_block_preserves_crlf_bytes_outside_updated_block(tmp_path):
    path = tmp_path / "AGENTS.md"
    prefix = b"# AGENTS\r\nbefore \t\r\n"
    suffix = b"\r\nafter \t\r\n"
    path.write_bytes(prefix + START.encode() + b"\r\nold\r\n" + END.encode() + suffix)

    assert replace_managed_block(path, "new body") == "updated"

    updated = path.read_bytes()
    assert updated.startswith(prefix)
    assert updated.endswith(suffix)


@pytest.mark.parametrize(
    "content",
    [
        f"before\n{END}\nwrong order\n{START}\nafter\n",
        f"{START}\none\n{END}\n{START}\ntwo\n{END}\n",
    ],
)
def test_replace_managed_block_rejects_misordered_or_duplicate_markers(tmp_path, content):
    path = tmp_path / "AGENTS.md"
    path.write_text(content, encoding="utf-8", newline="")

    with pytest.raises(ValueError, match="unbalanced managed markers"):
        replace_managed_block(path, "body")


def test_discover_git_bash_prefers_valid_claude_setting(tmp_path):
    configured = tmp_path / "configured" / "bash.exe"
    standard = tmp_path / "standard" / "bash.exe"
    configured.parent.mkdir()
    standard.parent.mkdir()
    configured.touch()
    standard.touch()

    found = discover_git_bash(
        {"CLAUDE_CODE_GIT_BASH_PATH": str(configured)},
        [standard],
        lambda _: None,
    )

    assert found == configured


def test_discover_git_bash_ignores_wsl_launcher():
    assert discover_git_bash({}, [], lambda _: r"C:\\Windows\\System32\\bash.exe") is None


def test_probe_python_utf8_parses_machine_readable_output(tmp_path):
    bash = tmp_path / "bash.exe"
    bash.touch()
    completed = subprocess.CompletedProcess([], 0, '{"utf8_mode": 1, "stdout": "utf-8"}\n', "")

    result = probe_python_utf8(bash, runner=lambda *args, **kwargs: completed)

    assert result["ok"] is True


def test_diagnose_warns_when_claude_prefers_powershell(tmp_path):
    bash = tmp_path / "Git" / "bin" / "bash.exe"
    bash.parent.mkdir(parents=True)
    bash.touch()
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(
        '{"env": {"CLAUDE_CODE_USE_POWERSHELL_TOOL": "1"}}', encoding="utf-8"
    )

    checks, ok = diagnose(tmp_path, {"CLAUDE_CODE_GIT_BASH_PATH": str(bash)})

    assert ok is False
    assert any(check["name"] == "claude_powershell_tool" and check["ok"] is False for check in checks)
