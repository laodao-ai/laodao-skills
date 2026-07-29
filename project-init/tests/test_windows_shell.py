import json
from pathlib import Path
import stat
import subprocess
import sys
import tomllib

import pytest


sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from windows_shell import (
    END,
    START,
    apply_repo,
    atomic_write_with_backup,
    diagnose,
    discover_git_bash,
    main,
    merge_claude_settings,
    merge_codex_config,
    probe_python_utf8,
    replace_managed_block,
)


@pytest.fixture
def assets_dir() -> Path:
    return Path(__file__).parents[1] / "assets" / "snippets"


def test_cli_apply_repo_prints_json_summary(tmp_path, capsys):
    code = main(["apply-repo", "--root", str(tmp_path)])
    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert output["AGENTS.md"] == "created"


def test_cli_configure_user_requires_existing_git_bash(tmp_path, capsys):
    code = main(
        [
            "configure-user",
            "--home",
            str(tmp_path),
            "--bash",
            str(tmp_path / "missing.exe"),
        ]
    )
    assert code == 2
    assert "Git Bash" in capsys.readouterr().err


def test_cli_diagnose_is_read_only_and_returns_one_for_failed_checks(
    tmp_path, monkeypatch, capsys
):
    bash = tmp_path / "Git" / "bin" / "bash.exe"
    bash.parent.mkdir(parents=True)
    bash.touch()
    home = tmp_path / "home"
    settings = home / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        '{"env": {"CLAUDE_CODE_USE_POWERSHELL_TOOL": "1"}}\n', encoding="utf-8"
    )
    before = settings.read_bytes()
    monkeypatch.setenv("CLAUDE_CODE_GIT_BASH_PATH", str(bash))

    code = main(
        ["diagnose", "--root", str(tmp_path), "--home", str(home)]
    )
    output = json.loads(capsys.readouterr().out)

    assert code == 1
    assert output["ok"] is False
    assert settings.read_bytes() == before
    assert not (home / ".codex").exists()


def test_cli_configure_user_validates_both_configs_before_writing(tmp_path, capsys):
    bash = tmp_path / "Git" / "bin" / "bash.exe"
    bash.parent.mkdir(parents=True)
    bash.touch()
    home = tmp_path / "home"
    codex = home / ".codex" / "config.toml"
    codex.parent.mkdir(parents=True)
    codex.write_text('model = "gpt"\n', encoding="utf-8")
    before = codex.read_bytes()
    claude = home / ".claude" / "settings.json"
    claude.parent.mkdir(parents=True)
    claude.write_text("", encoding="utf-8")

    code = main(
        [
            "configure-user",
            "--home",
            str(home),
            "--bash",
            str(bash),
        ]
    )

    assert code == 2
    assert "invalid JSON" in capsys.readouterr().err
    assert codex.read_bytes() == before
    assert not codex.with_name("config.toml.bak").exists()


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


def test_discover_git_bash_rejects_wsl_launcher_from_claude_setting():
    assert (
        discover_git_bash(
            {"CLAUDE_CODE_GIT_BASH_PATH": r"C:\Windows\System32\bash.exe"},
            [],
            lambda _: None,
        )
        is None
    )


def test_probe_python_utf8_parses_machine_readable_output(tmp_path):
    bash = tmp_path / "bash.exe"
    bash.touch()
    completed = subprocess.CompletedProcess([], 0, '{"utf8_mode": 1, "stdout": "utf-8"}\n', "")

    result = probe_python_utf8(bash, runner=lambda *args, **kwargs: completed)

    assert result["ok"] is True


@pytest.mark.parametrize("output", ["null", "[]", '"utf-8"'])
def test_probe_python_utf8_returns_failed_check_for_non_object_json(tmp_path, output):
    bash = tmp_path / "bash.exe"
    bash.touch()
    completed = subprocess.CompletedProcess([], 0, output, "")

    result = probe_python_utf8(bash, runner=lambda *args, **kwargs: completed)

    assert result["ok"] is False
    assert result["error"] == "invalid JSON object"


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


def test_merge_codex_config_preserves_other_keys(tmp_path):
    """Catches a merge that replaces a user's unrelated TOML settings."""
    path = tmp_path / "config.toml"
    path.write_text(
        'model = "gpt"\n\n[shell_environment_policy.set]\nKEEP = "yes"\n',
        encoding="utf-8",
    )

    assert merge_codex_config(path) == "updated"

    text = path.read_text(encoding="utf-8")
    assert 'model = "gpt"' in text
    assert 'KEEP = "yes"' in text
    assert 'PYTHONUTF8 = "1"' in text
    assert 'PYTHONIOENCODING = "utf-8"' in text
    assert path.with_name("config.toml.bak").read_text(encoding="utf-8") == (
        'model = "gpt"\n\n[shell_environment_policy.set]\nKEEP = "yes"\n'
    )


def test_merge_codex_config_rejects_duplicate_target_table(tmp_path):
    """Catches an ambiguous merge that silently chooses one duplicate table."""
    path = tmp_path / "config.toml"
    path.write_text(
        "[shell_environment_policy.set]\nA='1'\n"
        "[shell_environment_policy.set]\nB='2'\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate"):
        merge_codex_config(path)


def test_merge_codex_config_rejects_inline_parent_structure(tmp_path):
    """Catches adding a child table to an inline parent table."""
    path = tmp_path / "config.toml"
    path.write_text('shell_environment_policy = { KEEP = "yes" }\n', encoding="utf-8")

    with pytest.raises(ValueError, match="non-table"):
        merge_codex_config(path)


def test_merge_codex_config_updates_semantically_equivalent_quoted_keys(tmp_path):
    """Catches treating quoted target table/key spellings as unrelated TOML."""
    path = tmp_path / "config.toml"
    path.write_text(
        '["shell_environment_policy".\'set\']\n'
        '\'PYTHONUTF8\' = "0"\n'
        '"PYTHONIOENCODING" = "ascii"\n'
        'KEEP = "yes"\n',
        encoding="utf-8",
    )

    merge_codex_config(path)

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    env = data["shell_environment_policy"]["set"]
    assert env == {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "KEEP": "yes"}


def test_merge_codex_config_replaces_entire_multiline_target_value(tmp_path):
    """Catches replacing only the first line and leaving TOML continuation text."""
    path = tmp_path / "config.toml"
    path.write_text(
        '[shell_environment_policy.set]\nPYTHONUTF8 = """old\ncontinued\n"""\nKEEP = "yes"\n',
        encoding="utf-8",
    )

    merge_codex_config(path)

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    assert data["shell_environment_policy"]["set"] == {
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "KEEP": "yes",
    }


def test_merge_codex_config_ignores_table_text_inside_multiline_string(tmp_path):
    """Catches parsing table-looking user text inside a multiline string."""
    path = tmp_path / "config.toml"
    note = 'example\n[shell_environment_policy.set]\nPYTHONUTF8 = "fake"\n'
    path.write_text(
        'note = """' + note + '"""\n'
        '[shell_environment_policy.set]\nKEEP = "yes"\n',
        encoding="utf-8",
    )

    merge_codex_config(path)

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    assert data["note"] == note
    assert data["shell_environment_policy"]["set"]["PYTHONUTF8"] == "1"


def test_merge_codex_config_reports_created_when_only_stale_backup_exists(tmp_path):
    """Catches a stale backup changing the status for a missing config file."""
    path = tmp_path / "config.toml"
    path.with_name("config.toml.bak").write_text("old backup\n", encoding="utf-8")

    assert merge_codex_config(path) == "created"

    assert path.with_name("config.toml.bak").read_text(encoding="utf-8") == "old backup\n"


def test_merge_claude_settings_preserves_existing_fields_and_valid_bash(tmp_path):
    """Catches a merge that overwrites a user's permissions or working Bash path."""
    existing = tmp_path / "existing-bash.exe"
    existing.touch()
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "permissions": {"allow": ["Read"]},
                "env": {
                    "CLAUDE_CODE_GIT_BASH_PATH": str(existing),
                    "KEEP": "yes",
                },
            }
        ),
        encoding="utf-8",
    )

    assert merge_claude_settings(path, tmp_path / "other-bash.exe") == "updated"

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["permissions"] == {"allow": ["Read"]}
    assert data["env"]["CLAUDE_CODE_GIT_BASH_PATH"] == str(existing)
    assert data["env"]["KEEP"] == "yes"
    assert data["env"]["PYTHONUTF8"] == "1"
    assert data["env"]["PYTHONIOENCODING"] == "utf-8"


def test_merge_claude_settings_replaces_invalid_bash_path(tmp_path):
    """Catches retaining a configured Bash executable that no longer exists."""
    bash = tmp_path / "Git" / "bash.exe"
    bash.parent.mkdir()
    bash.touch()
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"env": {"CLAUDE_CODE_GIT_BASH_PATH": "C:/missing/bash.exe"}}),
        encoding="utf-8",
    )

    merge_claude_settings(path, bash)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["env"]["CLAUDE_CODE_GIT_BASH_PATH"] == str(bash)


def test_merge_claude_settings_reports_created_when_only_stale_backup_exists(tmp_path):
    """Catches a stale backup changing the status for missing Claude settings."""
    path = tmp_path / "settings.json"
    path.with_name("settings.json.bak").write_text("old backup\n", encoding="utf-8")

    assert merge_claude_settings(path, tmp_path / "bash.exe") == "created"

    assert path.with_name("settings.json.bak").read_text(encoding="utf-8") == "old backup\n"


@pytest.mark.parametrize(
    "content",
    [
        '{"env": {}, "env": {}}',
        '{"env": {"KEEP": "first", "KEEP": "second"}}',
        '{"permissions": {"allow": [], "allow": ["Read"]}}',
    ],
)
def test_merge_claude_settings_rejects_duplicate_keys_at_any_level(tmp_path, content):
    """Catches silently accepting an ambiguous duplicate JSON object key."""
    path = tmp_path / "settings.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate"):
        merge_claude_settings(path, tmp_path / "bash.exe")


@pytest.mark.parametrize("content", ["", " \t\r\n"])
def test_merge_claude_settings_rejects_existing_blank_file(tmp_path, content):
    """Catches interpreting a present but blank settings file as a new object."""
    path = tmp_path / "settings.json"
    path.write_text(content, encoding="utf-8", newline="")

    with pytest.raises(ValueError, match="invalid JSON"):
        merge_claude_settings(path, tmp_path / "bash.exe")


def test_atomic_write_with_backup_creates_backup_before_replacing_file(tmp_path):
    """Catches losing the prior user configuration during a write."""
    path = tmp_path / "settings.json"
    path.write_text("old\r\n", encoding="utf-8", newline="")

    backup = atomic_write_with_backup(path, "new\n")

    assert backup == path.with_name("settings.json.bak")
    assert backup.read_bytes() == b"old\r\n"
    assert path.read_bytes() == b"new\n"


def test_atomic_write_with_backup_preserves_existing_mode(tmp_path):
    """Catches atomic replacement resetting existing permission metadata."""
    path = tmp_path / "settings.json"
    path.write_text("old\n", encoding="utf-8")
    path.chmod(0o444)
    original_mode = stat.S_IMODE(path.stat().st_mode)

    atomic_write_with_backup(path, "new\n")

    assert stat.S_IMODE(path.stat().st_mode) == original_mode


def test_atomic_write_with_backup_normalizes_all_newlines_to_lf(tmp_path):
    """Catches retaining carriage returns despite the helper's LF contract."""
    path = tmp_path / "settings.json"

    atomic_write_with_backup(path, "one\r\ntwo\rthree\n")

    assert path.read_bytes() == b"one\ntwo\nthree\n"
