import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import tomllib
from typing import Callable, Literal, Mapping, Sequence


START = "<!-- project-init:windows-shell:start -->"
END = "<!-- project-init:windows-shell:end -->"

Status = Literal["created", "inserted", "updated", "unchanged"]
ConfigStatus = Literal["created", "updated", "unchanged"]

_CODEX_ENV_TABLE = "shell_environment_policy.set"
_CODEX_ENV_HEADER = re.compile(
    r"^\s*\[\s*shell_environment_policy\s*\.\s*set\s*\]\s*(?:#.*)?$"
)
_CODEX_POLICY_ASSIGNMENT = re.compile(r"^\s*shell_environment_policy\s*=")
_TABLE_HEADER = re.compile(r"^\s*\[")
_CODEX_ENV_KEY = re.compile(r"^\s*(PYTHONUTF8|PYTHONIOENCODING)\s*=")
_CODEX_ENV_VALUES = {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


def _is_wsl_launcher(path: Path) -> bool:
    normalized = str(path).replace("/", "\\").lower()
    return normalized.endswith(r"\windows\system32\bash.exe")


def discover_git_bash(
    env: Mapping[str, str],
    candidates: Sequence[Path],
    which: Callable[[str], str | None],
) -> Path | None:
    """Find Git for Windows' bash without accepting the WSL launcher."""
    configured = env.get("CLAUDE_CODE_GIT_BASH_PATH")
    paths = ([Path(configured)] if configured else []) + list(candidates)
    for path in paths:
        if path.name.lower() == "bash.exe" and not _is_wsl_launcher(path) and path.is_file():
            return path

    found = which("bash.exe")
    if not found:
        return None
    path = Path(found)
    if path.name.lower() != "bash.exe" or _is_wsl_launcher(path):
        return None
    return path


def atomic_write_with_backup(path: Path, content: str) -> Path | None:
    """Atomically write UTF-8/LF content, preserving an existing file as .bak."""
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_name(f"{path.name}.bak") if path.exists() else None
    if backup is not None:
        shutil.copyfile(path, backup)

    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as destination:
            destination.write(content)
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return backup


def _validate_codex_environment_table(content: str) -> list[str]:
    lines = content.splitlines(keepends=True)
    matches = [index for index, line in enumerate(lines) if _CODEX_ENV_HEADER.match(line)]
    if len(matches) > 1:
        raise ValueError(f"duplicate {_CODEX_ENV_TABLE} table")
    try:
        parsed = tomllib.loads(content)
    except tomllib.TOMLDecodeError as error:
        raise ValueError("invalid TOML configuration") from error

    policy = parsed.get("shell_environment_policy")
    target = policy.get("set") if isinstance(policy, dict) else None
    if policy is not None and not isinstance(policy, dict):
        raise ValueError(f"non-table {_CODEX_ENV_TABLE} structure")
    if isinstance(policy, dict) and "set" in policy and not isinstance(target, dict):
        raise ValueError(f"non-table {_CODEX_ENV_TABLE} structure")
    if target is not None and not matches:
        raise ValueError(f"non-table {_CODEX_ENV_TABLE} structure")
    if not matches and any(_CODEX_POLICY_ASSIGNMENT.match(line) for line in lines):
        raise ValueError(f"non-table {_CODEX_ENV_TABLE} structure")
    return lines


def merge_codex_config(path: Path) -> ConfigStatus:
    """Merge Python UTF-8 settings into Codex TOML without replacing user settings."""
    existed = path.exists()
    existing = path.read_text(encoding="utf-8") if existed else ""
    lines = _validate_codex_environment_table(existing)
    table_indices = [index for index, line in enumerate(lines) if _CODEX_ENV_HEADER.match(line)]

    if table_indices:
        start = table_indices[0]
        end = next(
            (index for index in range(start + 1, len(lines)) if _TABLE_HEADER.match(lines[index])),
            len(lines),
        )
        replacements: set[str] = set()
        merged = lines[:]
        for index in range(start + 1, end):
            match = _CODEX_ENV_KEY.match(merged[index])
            if match:
                key = match.group(1)
                merged[index] = f'{key} = "{_CODEX_ENV_VALUES[key]}"\n'
                replacements.add(key)
        missing = [key for key in _CODEX_ENV_VALUES if key not in replacements]
        merged[end:end] = [f'{key} = "{_CODEX_ENV_VALUES[key]}"\n' for key in missing]
        updated = "".join(merged)
    else:
        separator = "" if not existing or existing.endswith("\n") else "\n"
        updated = (
            f"{existing}{separator}[{_CODEX_ENV_TABLE}]\n"
            'PYTHONUTF8 = "1"\n'
            'PYTHONIOENCODING = "utf-8"\n'
        )

    if updated == existing:
        return "unchanged"
    atomic_write_with_backup(path, updated)
    return "updated" if existed else "created"


def merge_claude_settings(path: Path, bash: Path) -> ConfigStatus:
    """Merge required Claude environment variables while preserving user settings."""
    existed = path.exists()
    existing = path.read_text(encoding="utf-8") if existed else ""
    if existing:
        try:
            settings = json.loads(existing)
        except json.JSONDecodeError as error:
            raise ValueError("invalid JSON settings") from error
        if not isinstance(settings, dict):
            raise ValueError("Claude settings must be a JSON object")
    else:
        settings = {}

    env = settings.get("env")
    if env is None:
        env = {}
        settings["env"] = env
    if not isinstance(env, dict):
        raise ValueError("Claude settings env must be a JSON object")

    merged = dict(env)
    merged["PYTHONUTF8"] = "1"
    merged["PYTHONIOENCODING"] = "utf-8"
    configured_bash = merged.get("CLAUDE_CODE_GIT_BASH_PATH")
    if not isinstance(configured_bash, str) or not Path(configured_bash).is_file():
        merged["CLAUDE_CODE_GIT_BASH_PATH"] = str(bash)

    if merged == env:
        return "unchanged"
    settings["env"] = merged
    atomic_write_with_backup(path, json.dumps(settings, indent=2) + "\n")
    return "updated" if existed else "created"


def probe_python_utf8(
    bash: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, object]:
    """Run a machine-readable UTF-8 check through Git Bash."""
    probe = (
        "python -c 'import json,sys; "
        "print(json.dumps({\"utf8_mode\":sys.flags.utf8_mode,"
        "\"stdout\":sys.stdout.encoding}))'"
    )
    try:
        completed = runner(
            [str(bash), "-lc", probe], text=True, encoding="utf-8", capture_output=True
        )
    except OSError as error:
        return {"name": "python_utf8", "ok": False, "error": str(error)}

    if completed.returncode != 0:
        return {"name": "python_utf8", "ok": False, "returncode": completed.returncode}
    try:
        output = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"name": "python_utf8", "ok": False, "error": "invalid JSON output"}
    if not isinstance(output, dict):
        return {"name": "python_utf8", "ok": False, "error": "invalid JSON object"}

    utf8_mode = output.get("utf8_mode")
    stdout = output.get("stdout")
    ok = utf8_mode == 1 and isinstance(stdout, str) and stdout.lower() == "utf-8"
    return {"name": "python_utf8", "ok": ok, "utf8_mode": utf8_mode, "stdout": stdout}


def diagnose(home: Path, env: Mapping[str, str]) -> tuple[list[dict[str, object]], bool]:
    """Read the relevant user settings and report Git Bash runtime readiness."""
    candidates = [
        Path(r"C:\Program Files\Git\bin\bash.exe"),
        Path(r"C:\Program Files\Git\usr\bin\bash.exe"),
    ]
    bash = discover_git_bash(env, candidates, shutil.which)
    checks: list[dict[str, object]] = []
    if bash is None:
        checks.append({"name": "git_bash", "ok": False, "hint": "Install Git for Windows."})
    else:
        checks.append({"name": "git_bash", "ok": True, "path": str(bash)})
        checks.append(probe_python_utf8(bash))

    codex_config = home / ".codex" / "config.toml"
    checks.append({"name": "codex_config", "ok": True, "present": codex_config.is_file()})
    claude_settings = home / ".claude" / "settings.json"
    powershell_enabled = False
    if claude_settings.is_file():
        try:
            settings = json.loads(claude_settings.read_text(encoding="utf-8"))
            env_settings = settings.get("env", {})
            powershell_enabled = isinstance(env_settings, dict) and env_settings.get(
                "CLAUDE_CODE_USE_POWERSHELL_TOOL"
            ) == "1"
        except (OSError, json.JSONDecodeError):
            checks.append({"name": "claude_settings", "ok": False, "error": "invalid JSON"})
        else:
            checks.append({"name": "claude_settings", "ok": True, "present": True})
    else:
        checks.append({"name": "claude_settings", "ok": True, "present": False})
    if powershell_enabled:
        checks.append(
            {
                "name": "claude_powershell_tool",
                "ok": False,
                "warning": "CLAUDE_CODE_USE_POWERSHELL_TOOL=1 overrides Git Bash.",
            }
        )

    return checks, all(check["ok"] is True for check in checks)


def replace_managed_block(path: Path, body: str, *, title: str = "# AGENTS") -> Status:
    """Create or replace the repository-managed Windows shell instruction block."""
    if path.exists():
        with path.open(encoding="utf-8", newline="") as source:
            existing = source.read()
    else:
        existing = ""
    start_count = existing.count(START)
    end_count = existing.count(END)
    markers_misordered = start_count == end_count == 1 and existing.index(START) > existing.index(END)
    if start_count != end_count or start_count > 1 or markers_misordered:
        raise ValueError(f"unbalanced managed markers in {path}")

    block = f"{START}\n{body.rstrip()}\n{END}"
    if START in existing:
        prefix, tail = existing.split(START, 1)
        _, suffix = tail.split(END, 1)
        updated = f"{prefix}{block}{suffix}"
        status: Status = "unchanged" if updated == existing else "updated"
    else:
        updated = f"{existing}\n\n{block}\n" if existing else f"{title}\n\n{block}\n"
        status = "inserted" if existing else "created"

    if updated != existing:
        with path.open("w", encoding="utf-8", newline="") as destination:
            destination.write(updated)
    return status


def apply_repo(root: Path, assets_dir: Path) -> dict[str, Status]:
    """Apply agent-specific Windows shell instructions to a repository root."""
    agents_body = (assets_dir / "agents-windows-shell.md").read_text(encoding="utf-8")
    claude_body = (assets_dir / "claude-windows-shell.md").read_text(encoding="utf-8")
    return {
        "AGENTS.md": replace_managed_block(root / "AGENTS.md", agents_body),
        "CLAUDE.md": replace_managed_block(root / "CLAUDE.md", claude_body, title="# CLAUDE"),
    }
