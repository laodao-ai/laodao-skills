import configparser
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tomllib

import pytest


sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

import windows_shell

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


def _write_valid_agent_configs(home: Path, bash: Path) -> None:
    codex = home / ".codex" / "config.toml"
    codex.parent.mkdir(parents=True, exist_ok=True)
    codex.write_text(
        '[shell_environment_policy.set]\n'
        'PYTHONUTF8 = "1"\n'
        'PYTHONIOENCODING = "utf-8"\n',
        encoding="utf-8",
    )
    claude = home / ".claude" / "settings.json"
    claude.parent.mkdir(parents=True, exist_ok=True)
    claude.write_text(
        json.dumps(
            {
                "env": {
                    "CLAUDE_CODE_GIT_BASH_PATH": str(bash),
                    "PYTHONUTF8": "1",
                    "PYTHONIOENCODING": "utf-8",
                }
            }
        ),
        encoding="utf-8",
    )


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlinks are unavailable: {error}")


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


@pytest.mark.parametrize("codex_exists", [False, True])
def test_cli_configure_user_rolls_back_first_write_when_second_write_fails(
    tmp_path, monkeypatch, capsys, codex_exists
):
    bash = tmp_path / "Git" / "bin" / "bash.exe"
    bash.parent.mkdir(parents=True)
    bash.touch()
    home = tmp_path / "home"
    codex = home / ".codex" / "config.toml"
    backup = codex.with_name("config.toml.bak")
    codex.parent.mkdir(parents=True)
    if codex_exists:
        codex.write_bytes(b'model = "before"\r\n')
        codex.chmod(0o444)
    backup.write_bytes(b"pre-existing backup\r\n")
    backup.chmod(0o644)
    codex_before = codex.read_bytes() if codex_exists else None
    codex_mode = stat.S_IMODE(codex.stat().st_mode) if codex_exists else None
    backup_before = backup.read_bytes()
    backup_mode = stat.S_IMODE(backup.stat().st_mode)
    real_merge = windows_shell.merge_claude_settings
    calls = 0

    def fail_real_user_write(path, selected_bash):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected second write failure")
        return real_merge(path, selected_bash)

    monkeypatch.setattr(windows_shell, "merge_claude_settings", fail_real_user_write)

    code = main(
        ["configure-user", "--home", str(home), "--bash", str(bash)]
    )

    assert code == 2
    assert "injected second write failure" in capsys.readouterr().err
    assert codex.exists() is codex_exists
    if codex_exists:
        assert codex.read_bytes() == codex_before
        assert stat.S_IMODE(codex.stat().st_mode) == codex_mode
    assert backup.read_bytes() == backup_before
    assert stat.S_IMODE(backup.stat().st_mode) == backup_mode


def test_cli_configure_user_does_not_overwrite_concurrent_change_during_rollback(
    tmp_path, monkeypatch, capsys
):
    """Catches rollback restoring a snapshot over a regular file changed concurrently."""
    bash = tmp_path / "Git" / "bin" / "bash.exe"
    bash.parent.mkdir(parents=True)
    bash.touch()
    home = tmp_path / "home"
    _write_valid_agent_configs(home, bash)
    codex = home / ".codex" / "config.toml"
    codex.write_bytes(b'model = "before"\n')
    concurrent = b'model = "concurrent"\n'
    real_merge = windows_shell.merge_claude_settings
    calls = 0

    def fail_after_concurrent_change(path, selected_bash):
        nonlocal calls
        calls += 1
        if calls == 2:
            codex.write_bytes(concurrent)
            raise OSError("injected second write failure")
        return real_merge(path, selected_bash)

    monkeypatch.setattr(
        windows_shell, "merge_claude_settings", fail_after_concurrent_change
    )

    code = main(["configure-user", "--home", str(home), "--bash", str(bash)])

    assert code == 2
    assert "rollback conflict" in capsys.readouterr().err
    assert codex.read_bytes() == concurrent


def test_cli_configure_user_rejects_nonregular_backup_before_either_write(
    tmp_path, capsys
):
    """Catches preflight that overlooks an unsafe second-config backup path."""
    bash = tmp_path / "Git" / "bin" / "bash.exe"
    bash.parent.mkdir(parents=True)
    bash.touch()
    home = tmp_path / "home"
    _write_valid_agent_configs(home, bash)
    codex = home / ".codex" / "config.toml"
    codex_before = codex.read_bytes()
    claude_backup = home / ".claude" / "settings.json.bak"
    claude_backup.mkdir()

    code = main(["configure-user", "--home", str(home), "--bash", str(bash)])

    assert code == 2
    assert "regular file" in capsys.readouterr().err
    assert codex.read_bytes() == codex_before
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


def test_apply_repo_preflights_both_instruction_files_before_writing(tmp_path, assets_dir):
    """Catches updating AGENTS.md before discovering malformed CLAUDE.md markers."""
    agents = tmp_path / "AGENTS.md"
    agents.write_text(f"# AGENTS\n\n{START}\nold body\n{END}\n", encoding="utf-8")
    before = agents.read_bytes()
    (tmp_path / "CLAUDE.md").write_text(
        f"# CLAUDE\n\n{START}\nbroken\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="unbalanced managed markers"):
        apply_repo(tmp_path, assets_dir)

    assert agents.read_bytes() == before


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


def test_discover_git_bash_rejects_missing_which_result(tmp_path):
    """Catches accepting a PATH lookup string that is not a regular executable file."""
    missing = tmp_path / "Git" / "bin" / "bash.exe"

    assert discover_git_bash({}, [], lambda _: str(missing)) is None


def test_discover_git_bash_rejects_symlink_resolving_to_wsl_launcher(tmp_path):
    """Catches validating only the link spelling while its target is the WSL launcher."""
    wsl = tmp_path / "Windows" / "System32" / "bash.exe"
    wsl.parent.mkdir(parents=True)
    wsl.touch()
    link = tmp_path / "Git" / "bin" / "bash.exe"
    link.parent.mkdir(parents=True)
    _symlink_or_skip(link, wsl)

    assert discover_git_bash({}, [link], lambda _: None) is None


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


def test_diagnose_separately_validates_exact_agent_config_values(
    tmp_path, monkeypatch
):
    """Catches treating a successful Bash probe as proof that both configs are valid."""
    bash = tmp_path / "Git" / "bin" / "bash.exe"
    bash.parent.mkdir(parents=True)
    bash.touch()
    _write_valid_agent_configs(tmp_path, bash)
    monkeypatch.setattr(
        windows_shell,
        "probe_python_utf8",
        lambda _: {"name": "git_bash_python_utf8", "ok": True},
    )

    checks, ok = diagnose(tmp_path, {"CLAUDE_CODE_GIT_BASH_PATH": str(bash)})
    by_name = {check["name"]: check for check in checks}

    assert ok is True
    assert by_name["git_bash_python_utf8"]["ok"] is True
    assert by_name["codex_config"]["ok"] is True
    assert by_name["claude_settings"]["ok"] is True


def test_diagnose_fails_when_agent_configs_are_missing_despite_good_bash_probe(
    tmp_path, monkeypatch
):
    """Catches reporting readiness from the runtime probe while config files are absent."""
    bash = tmp_path / "Git" / "bin" / "bash.exe"
    bash.parent.mkdir(parents=True)
    bash.touch()
    monkeypatch.setattr(
        windows_shell,
        "probe_python_utf8",
        lambda _: {"name": "git_bash_python_utf8", "ok": True},
    )

    checks, ok = diagnose(tmp_path, {"CLAUDE_CODE_GIT_BASH_PATH": str(bash)})
    by_name = {check["name"]: check for check in checks}

    assert ok is False
    assert by_name["codex_config"] == {
        "name": "codex_config",
        "ok": False,
        "error": "missing config.toml",
    }
    assert by_name["claude_settings"] == {
        "name": "claude_settings",
        "ok": False,
        "error": "missing settings.json",
    }


def test_diagnose_always_reports_probe_check_when_git_bash_is_missing(
    tmp_path, monkeypatch
):
    """Catches omitting the runtime probe result instead of reporting it was not run."""
    bash = tmp_path / "Git" / "bin" / "bash.exe"
    bash.parent.mkdir(parents=True)
    bash.touch()
    _write_valid_agent_configs(tmp_path, bash)
    monkeypatch.setattr(windows_shell, "discover_git_bash", lambda *args: None)

    checks, ok = diagnose(tmp_path, {})
    by_name = {check["name"]: check for check in checks}

    assert ok is False
    assert by_name["git_bash_python_utf8"] == {
        "name": "git_bash_python_utf8",
        "ok": False,
        "error": "not run because Git Bash was not found",
    }


@pytest.mark.parametrize("configured_kind", ["missing", "non_bash", "wsl"])
def test_diagnose_rejects_missing_or_invalid_claude_git_bash_path(
    tmp_path, monkeypatch, configured_kind
):
    """Catches declaring Claude settings healthy without a valid Git Bash path."""
    bash = tmp_path / "Git" / "bin" / "bash.exe"
    bash.parent.mkdir(parents=True)
    bash.touch()
    _write_valid_agent_configs(tmp_path, bash)
    settings_path = tmp_path / ".claude" / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    if configured_kind == "missing":
        settings["env"].pop("CLAUDE_CODE_GIT_BASH_PATH")
    elif configured_kind == "non_bash":
        invalid = tmp_path / "cmd.exe"
        invalid.touch()
        settings["env"]["CLAUDE_CODE_GIT_BASH_PATH"] = str(invalid)
    else:
        invalid = tmp_path / "Windows" / "System32" / "bash.exe"
        invalid.parent.mkdir(parents=True)
        invalid.touch()
        settings["env"]["CLAUDE_CODE_GIT_BASH_PATH"] = str(invalid)
    settings_path.write_text(json.dumps(settings), encoding="utf-8")
    monkeypatch.setattr(
        windows_shell,
        "probe_python_utf8",
        lambda _: {"name": "git_bash_python_utf8", "ok": True},
    )

    checks, ok = diagnose(tmp_path, {"CLAUDE_CODE_GIT_BASH_PATH": str(bash)})
    check = next(item for item in checks if item["name"] == "claude_settings")

    assert ok is False
    assert check["ok"] is False
    assert "CLAUDE_CODE_GIT_BASH_PATH" in check["error"]


@pytest.mark.parametrize(
    ("content", "expected_error"),
    [
        ("broken = [\n", "invalid TOML"),
        ('model = "gpt"\n', "missing shell_environment_policy.set"),
        (
            '[shell_environment_policy.set]\nPYTHONUTF8 = 1\n'
            'PYTHONIOENCODING = "utf-8"\n',
            "PYTHONUTF8 must equal string",
        ),
        (
            '[shell_environment_policy.set]\nPYTHONUTF8 = "1"\n'
            'PYTHONIOENCODING = "UTF-8"\n',
            "PYTHONIOENCODING must equal string",
        ),
    ],
)
def test_diagnose_reports_malformed_or_wrong_codex_config(
    tmp_path, monkeypatch, content, expected_error
):
    """Catches presence-only Codex checks that ignore parse and semantic failures."""
    bash = tmp_path / "Git" / "bin" / "bash.exe"
    bash.parent.mkdir(parents=True)
    bash.touch()
    _write_valid_agent_configs(tmp_path, bash)
    (tmp_path / ".codex" / "config.toml").write_text(content, encoding="utf-8")
    monkeypatch.setattr(
        windows_shell,
        "probe_python_utf8",
        lambda _: {"name": "git_bash_python_utf8", "ok": True},
    )

    checks, ok = diagnose(tmp_path, {"CLAUDE_CODE_GIT_BASH_PATH": str(bash)})
    check = next(item for item in checks if item["name"] == "codex_config")

    assert ok is False
    assert check["ok"] is False
    assert expected_error in check["error"]


@pytest.mark.parametrize(
    ("content", "expected_error"),
    [
        ("{", "invalid JSON"),
        ("[]", "JSON object"),
        ('{"env": []}', "env must be a JSON object"),
        ('{"env": {}}', "missing PYTHONUTF8"),
        (
            '{"env": {"PYTHONUTF8": 1, "PYTHONIOENCODING": "utf-8"}}',
            "PYTHONUTF8 must equal string",
        ),
        (
            '{"env": {"PYTHONUTF8": "1", "PYTHONIOENCODING": "UTF-8"}}',
            "PYTHONIOENCODING must equal string",
        ),
    ],
)
def test_diagnose_reports_malformed_nonobject_or_wrong_claude_settings(
    tmp_path, monkeypatch, content, expected_error
):
    """Catches malformed Claude settings escaping as tracebacks or healthy checks."""
    bash = tmp_path / "Git" / "bin" / "bash.exe"
    bash.parent.mkdir(parents=True)
    bash.touch()
    _write_valid_agent_configs(tmp_path, bash)
    (tmp_path / ".claude" / "settings.json").write_text(content, encoding="utf-8")
    monkeypatch.setattr(
        windows_shell,
        "probe_python_utf8",
        lambda _: {"name": "git_bash_python_utf8", "ok": True},
    )

    checks, ok = diagnose(tmp_path, {"CLAUDE_CODE_GIT_BASH_PATH": str(bash)})
    check = next(item for item in checks if item["name"] == "claude_settings")

    assert ok is False
    assert check["ok"] is False
    assert expected_error in check["error"]


def test_cli_diagnose_returns_structured_failure_for_nonobject_claude_settings(
    tmp_path, monkeypatch, capsys
):
    """Catches a non-object JSON root escaping the CLI as an AttributeError traceback."""
    bash = tmp_path / "Git" / "bin" / "bash.exe"
    bash.parent.mkdir(parents=True)
    bash.touch()
    _write_valid_agent_configs(tmp_path, bash)
    (tmp_path / ".claude" / "settings.json").write_text("[]", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CODE_GIT_BASH_PATH", str(bash))
    monkeypatch.setattr(
        windows_shell,
        "probe_python_utf8",
        lambda _: {"name": "git_bash_python_utf8", "ok": True},
    )

    code = main(["diagnose", "--root", str(tmp_path), "--home", str(tmp_path)])
    captured = capsys.readouterr()
    output = json.loads(captured.out)

    assert code == 1
    assert output["ok"] is False
    assert captured.err == ""
    assert next(
        check for check in output["checks"] if check["name"] == "claude_settings"
    )["ok"] is False


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


def test_merge_codex_config_does_not_treat_nested_array_items_as_headers(tmp_path):
    """Catches inserting target keys into the middle of a nested multiline array."""
    path = tmp_path / "config.toml"
    path.write_text(
        "[shell_environment_policy.set]\n"
        "KEEP = [\n"
        "  [1]\n"
        "]\n",
        encoding="utf-8",
    )

    merge_codex_config(path)

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    assert data["shell_environment_policy"]["set"] == {
        "KEEP": [[1]],
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    }


@pytest.mark.parametrize(
    "assignment",
    [
        "PYTHONUTF8 = 1\n",
        "PYTHONUTF8 = true\n",
        "PYTHONUTF8 = [\"1\"]\n",
        "PYTHONUTF8 = { value = \"1\" }\n",
    ],
)
def test_merge_codex_config_rejects_nonstring_required_values_without_writing(
    tmp_path, assignment
):
    """Catches silently replacing a semantically conflicting non-string value."""
    path = tmp_path / "config.toml"
    path.write_text(
        f"[shell_environment_policy.set]\n{assignment}KEEP = \"yes\"\n",
        encoding="utf-8",
    )
    before = path.read_bytes()

    with pytest.raises(ValueError, match="PYTHONUTF8.*string"):
        merge_codex_config(path)

    assert path.read_bytes() == before
    assert not path.with_name("config.toml.bak").exists()


@pytest.mark.parametrize(
    "content",
    [
        (
            "[shell_environment_policy.set]\n"
            "PYTHONIOENCODING.name = \"utf-8\"\n"
        ),
        (
            "[shell_environment_policy.set]\n"
            "KEEP = \"yes\"\n"
            "[shell_environment_policy.set.PYTHONUTF8]\n"
            "value = \"1\"\n"
        ),
    ],
)
def test_merge_codex_config_rejects_dotted_or_subtable_conflicts_without_writing(
    tmp_path, content
):
    """Catches emitting invalid TOML over a dotted-key or subtable conflict."""
    path = tmp_path / "config.toml"
    path.write_text(content, encoding="utf-8")
    before = path.read_bytes()

    with pytest.raises(ValueError, match="conflicting|required.*string"):
        merge_codex_config(path)

    assert path.read_bytes() == before
    assert not path.with_name("config.toml.bak").exists()


def test_merge_codex_config_reports_created_when_only_stale_backup_exists(tmp_path):
    """Catches a stale backup changing the status for a missing config file."""
    path = tmp_path / "config.toml"
    path.with_name("config.toml.bak").write_text("old backup\n", encoding="utf-8")

    assert merge_codex_config(path) == "created"

    assert path.with_name("config.toml.bak").read_text(encoding="utf-8") == "old backup\n"


def test_merge_claude_settings_preserves_existing_fields_and_valid_bash(tmp_path):
    """Catches a merge that overwrites a user's permissions or working Bash path."""
    existing = tmp_path / "existing" / "bash.exe"
    existing.parent.mkdir()
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


@pytest.mark.parametrize("configured_name", ["cmd.exe", "sh.exe"])
def test_merge_claude_settings_replaces_existing_non_bash_file(
    tmp_path, configured_name
):
    """Catches preserving an arbitrary existing file as the Git Bash executable."""
    configured = tmp_path / configured_name
    configured.touch()
    selected = tmp_path / "Git" / "bin" / "bash.exe"
    selected.parent.mkdir(parents=True)
    selected.touch()
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"env": {"CLAUDE_CODE_GIT_BASH_PATH": str(configured)}}),
        encoding="utf-8",
    )

    merge_claude_settings(path, selected)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["env"]["CLAUDE_CODE_GIT_BASH_PATH"] == str(selected)


def test_merge_claude_settings_replaces_existing_wsl_launcher(tmp_path):
    """Catches preserving System32's WSL launcher merely because it exists."""
    configured = tmp_path / "Windows" / "System32" / "bash.exe"
    configured.parent.mkdir(parents=True)
    configured.touch()
    selected = tmp_path / "Git" / "bin" / "bash.exe"
    selected.parent.mkdir(parents=True)
    selected.touch()
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"env": {"CLAUDE_CODE_GIT_BASH_PATH": str(configured)}}),
        encoding="utf-8",
    )

    merge_claude_settings(path, selected)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["env"]["CLAUDE_CODE_GIT_BASH_PATH"] == str(selected)


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

    bash = tmp_path / "bash.exe"
    bash.touch()

    assert merge_claude_settings(path, bash) == "created"

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


def test_atomic_write_with_backup_rejects_primary_symlink_without_touching_target(
    tmp_path,
):
    """Catches following a primary config symlink into external user data."""
    external = tmp_path / "external.toml"
    external.write_bytes(b"external\r\n")
    path = tmp_path / "config.toml"
    _symlink_or_skip(path, external)

    with pytest.raises(ValueError, match="symbolic link"):
        atomic_write_with_backup(path, "new\n")

    assert path.is_symlink()
    assert external.read_bytes() == b"external\r\n"


def test_atomic_write_with_backup_rejects_broken_primary_symlink(tmp_path):
    """Catches treating a broken primary symlink as an absent safe path."""
    missing = tmp_path / "missing.toml"
    path = tmp_path / "config.toml"
    _symlink_or_skip(path, missing)

    with pytest.raises(ValueError, match="symbolic link"):
        atomic_write_with_backup(path, "new\n")

    assert os.path.lexists(path)
    assert path.is_symlink()


def test_atomic_write_with_backup_rejects_backup_symlink_without_touching_target(
    tmp_path,
):
    """Catches copyfile following a .bak symlink and overwriting external data."""
    path = tmp_path / "config.toml"
    path.write_bytes(b"original\n")
    external = tmp_path / "external.bak"
    external.write_bytes(b"external\r\n")
    backup = path.with_name("config.toml.bak")
    _symlink_or_skip(backup, external)

    with pytest.raises(ValueError, match="symbolic link"):
        atomic_write_with_backup(path, "new\n")

    assert backup.is_symlink()
    assert external.read_bytes() == b"external\r\n"
    assert path.read_bytes() == b"original\n"


def test_atomic_write_with_backup_rejects_broken_backup_symlink(tmp_path):
    """Catches following or replacing a broken .bak symlink."""
    path = tmp_path / "config.toml"
    path.write_bytes(b"original\n")
    backup = path.with_name("config.toml.bak")
    _symlink_or_skip(backup, tmp_path / "missing.bak")

    with pytest.raises(ValueError, match="symbolic link"):
        atomic_write_with_backup(path, "new\n")

    assert os.path.lexists(backup)
    assert backup.is_symlink()
    assert path.read_bytes() == b"original\n"


@pytest.mark.parametrize(
    ("unsafe_name", "broken"),
    [
        ("config.toml", False),
        ("config.toml", True),
        ("config.toml.bak", False),
        ("config.toml.bak", True),
    ],
)
def test_atomic_write_fail_closed_for_symlink_state_when_host_cannot_create_links(
    tmp_path, monkeypatch, unsafe_name, broken
):
    """Exercises lstat/lexists link handling even on locked-down Windows hosts."""
    path = tmp_path / "config.toml"
    backup = path.with_name("config.toml.bak")
    unsafe = tmp_path / unsafe_name
    if unsafe != path:
        path.write_bytes(b"original\n")
    if not broken:
        unsafe.write_bytes(b"link placeholder\n")
    primary_before = path.read_bytes() if path.is_file() else None
    unsafe_before = unsafe.read_bytes() if unsafe.is_file() else None
    real_lexists = windows_shell.os.path.lexists
    real_lstat = windows_shell.os.lstat

    def fake_lexists(candidate):
        if Path(candidate) == unsafe:
            return True
        return real_lexists(candidate)

    def fake_lstat(candidate, *args, **kwargs):
        if Path(candidate) == unsafe:
            return os.stat_result((stat.S_IFLNK | 0o777, 0, 0, 0, 0, 0, 0, 0, 0, 0))
        return real_lstat(candidate, *args, **kwargs)

    monkeypatch.setattr(windows_shell.os.path, "lexists", fake_lexists)
    monkeypatch.setattr(windows_shell.os, "lstat", fake_lstat)

    with pytest.raises(ValueError, match="symbolic link"):
        atomic_write_with_backup(path, "new\n")

    if primary_before is None:
        assert not path.exists()
    else:
        assert path.read_bytes() == primary_before
    if unsafe_before is not None:
        assert unsafe.read_bytes() == unsafe_before
    elif unsafe == backup:
        assert not backup.exists()


@pytest.mark.parametrize("unsafe_name", ["config.toml", "config.toml.bak"])
def test_atomic_write_with_backup_rejects_nonregular_primary_or_backup(
    tmp_path, unsafe_name
):
    """Catches treating a directory or other non-regular config path as writable."""
    path = tmp_path / "config.toml"
    unsafe = tmp_path / unsafe_name
    if unsafe == path:
        unsafe.mkdir()
    else:
        path.write_bytes(b"original\n")
        unsafe.mkdir()

    with pytest.raises(ValueError, match="regular file"):
        atomic_write_with_backup(path, "new\n")

    assert unsafe.is_dir()
    if path.is_file():
        assert path.read_bytes() == b"original\n"


def test_atomic_write_with_backup_preserves_old_backup_when_backup_replace_fails(
    tmp_path, monkeypatch
):
    """Catches overwriting a backup in place before its atomic replacement succeeds."""
    path = tmp_path / "config.toml"
    path.write_bytes(b"original\n")
    backup = path.with_name("config.toml.bak")
    backup.write_bytes(b"older backup\r\n")

    def fail_replace(source, destination):
        raise OSError("injected backup replace failure")

    monkeypatch.setattr(windows_shell.os, "replace", fail_replace)

    with pytest.raises(OSError, match="injected backup replace failure"):
        atomic_write_with_backup(path, "new\n")

    assert path.read_bytes() == b"original\n"
    assert backup.read_bytes() == b"older backup\r\n"
    assert list(tmp_path.glob(".config.toml.*")) == []


def test_atomic_write_with_backup_restores_old_backup_when_target_replace_fails(
    tmp_path, monkeypatch
):
    """Catches a target replacement failure leaving a partially updated backup."""
    path = tmp_path / "config.toml"
    path.write_bytes(b"original\n")
    backup = path.with_name("config.toml.bak")
    backup.write_bytes(b"older backup\r\n")
    real_replace = windows_shell.os.replace

    def fail_target_replace(source, destination):
        if Path(destination) == path:
            raise OSError("injected target replace failure")
        return real_replace(source, destination)

    monkeypatch.setattr(windows_shell.os, "replace", fail_target_replace)

    with pytest.raises(OSError, match="injected target replace failure"):
        atomic_write_with_backup(path, "new\n")

    assert path.read_bytes() == b"original\n"
    assert backup.read_bytes() == b"older backup\r\n"
    assert list(tmp_path.glob(".config.toml.*")) == []


def test_editorconfig_gives_python_four_spaces_and_shell_two_spaces():
    """Catches applying the shell's two-space policy to Python files."""
    path = Path(__file__).parents[1] / "assets" / ".editorconfig"
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string("[global]\n" + path.read_text(encoding="utf-8"))

    assert parser["*.py"]["indent_style"] == "space"
    assert parser["*.py"]["indent_size"] == "4"
    assert parser["*.{sh,bash}"]["indent_style"] == "space"
    assert parser["*.{sh,bash}"]["indent_size"] == "2"
