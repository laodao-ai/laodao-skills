import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import tomllib
from typing import Callable, Literal, Mapping, Sequence


START = "<!-- project-init:windows-shell:start -->"
END = "<!-- project-init:windows-shell:end -->"

Status = Literal["created", "inserted", "updated", "unchanged"]
ConfigStatus = Literal["created", "updated", "unchanged"]

_CODEX_ENV_TABLE = "shell_environment_policy.set"
_CODEX_ENV_VALUES = {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
_CODEX_ENV_PATH = ("shell_environment_policy", "set")
_TOML_MARKER = "__project_init_value_marker__"


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
    existing_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    backup = path.with_name(f"{path.name}.bak") if path.exists() else None
    if backup is not None:
        shutil.copyfile(path, backup)

    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    made_writable = False
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as destination:
            destination.write(normalized)
        os.chmod(temporary, existing_mode)
        if path.exists() and not existing_mode & stat.S_IWRITE:
            os.chmod(path, existing_mode | stat.S_IWRITE)
            made_writable = True
        os.replace(temporary, path)
    except BaseException:
        if made_writable and path.exists():
            os.chmod(path, existing_mode)
        temporary.unlink(missing_ok=True)
        raise
    return backup


def _toml_multiline_starts(lines: list[str]) -> list[bool]:
    """Return whether each line starts outside a TOML multiline string."""
    delimiter: str | None = None
    starts: list[bool] = []
    for line in lines:
        starts.append(delimiter is None)
        index = 0
        while index < len(line):
            if delimiter == "'''":
                if line.startswith(delimiter, index):
                    delimiter = None
                    index += 3
                else:
                    index += 1
                continue
            if delimiter == '\"\"\"':
                if line[index] == "\\":
                    index += 2
                elif line.startswith(delimiter, index):
                    delimiter = None
                    index += 3
                else:
                    index += 1
                continue
            if line[index] == "#":
                break
            if line.startswith("'''", index) or line.startswith('\"\"\"', index):
                delimiter = line[index : index + 3]
                index += 3
                continue
            if line[index] in "'\"":
                quote = line[index]
                index += 1
                while index < len(line):
                    if quote == '"' and line[index] == "\\":
                        index += 2
                    elif line[index] == quote:
                        index += 1
                        break
                    else:
                        index += 1
                continue
            index += 1
    return starts


def _find_toml_marker(value: object, path: tuple[str, ...] = ()) -> tuple[str, ...] | None:
    if isinstance(value, dict):
        if value.get(_TOML_MARKER) == 1:
            return path
        for key, child in value.items():
            found = _find_toml_marker(child, (*path, key))
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_toml_marker(child, path)
            if found is not None:
                return found
    return None


def _toml_header_path(line: str) -> tuple[str, ...] | None:
    if not line.lstrip().startswith("["):
        return None
    try:
        parsed = tomllib.loads(f"{line.rstrip()}\n{_TOML_MARKER} = 1\n")
    except tomllib.TOMLDecodeError:
        return None
    return _find_toml_marker(parsed)


def _toml_key_path(source: str) -> tuple[str, ...] | None:
    try:
        parsed = tomllib.loads(f"{source} = 1")
    except tomllib.TOMLDecodeError:
        return None
    return _find_value_path(parsed, 1)


def _find_value_path(value: object, expected: object, path: tuple[str, ...] = ()) -> tuple[str, ...] | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if child == expected:
                return (*path, key)
            found = _find_value_path(child, expected, (*path, key))
            if found is not None:
                return found
    return None


def _toml_assignment_equal(line: str) -> int | None:
    quote: str | None = None
    escaped = False
    for index, character in enumerate(line):
        if quote == '"':
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
        elif quote == "'":
            if character == quote:
                quote = None
        elif character in "'\"":
            quote = character
        elif character == "#":
            return None
        elif character == "=":
            return index
    return None


def _complete_toml_assignment(lines: list[str], start: int, limit: int) -> int:
    for end in range(start + 1, limit + 1):
        try:
            tomllib.loads("".join(lines[start:end]))
        except tomllib.TOMLDecodeError:
            continue
        return end
    raise ValueError("unsafe multiline target assignment")


def _codex_toml_layout(content: str) -> tuple[list[str], list[tuple[int, tuple[str, ...]]]]:
    lines = content.splitlines(keepends=True)
    starts = _toml_multiline_starts(lines)
    headers = [
        (index, path)
        for index, line in enumerate(lines)
        if starts[index] and (path := _toml_header_path(line)) is not None
    ]
    targets = [item for item in headers if item[1] == _CODEX_ENV_PATH]
    if len(targets) > 1:
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
    if target is not None and not targets:
        raise ValueError(f"non-table {_CODEX_ENV_TABLE} structure")

    first_header = headers[0][0] if headers else len(lines)
    for index in range(first_header):
        if not starts[index] or (equal := _toml_assignment_equal(lines[index])) is None:
            continue
        if _toml_key_path(lines[index][:equal].strip()) == ("shell_environment_policy",):
            raise ValueError(f"non-table {_CODEX_ENV_TABLE} structure")
    return lines, headers


def merge_codex_config(path: Path) -> ConfigStatus:
    """Merge Python UTF-8 settings into Codex TOML without replacing user settings."""
    existed = path.exists()
    existing = path.read_text(encoding="utf-8") if existed else ""
    lines, headers = _codex_toml_layout(existing)
    table_indices = [index for index, path_parts in headers if path_parts == _CODEX_ENV_PATH]

    if table_indices:
        start = table_indices[0]
        end = next((index for index, _ in headers if index > start), len(lines))
        starts = _toml_multiline_starts(lines)
        replacements: list[tuple[int, int, str]] = []
        index = start + 1
        while index < end:
            equal = _toml_assignment_equal(lines[index]) if starts[index] else None
            key_path = _toml_key_path(lines[index][:equal].strip()) if equal is not None else None
            if key_path in {(key,) for key in _CODEX_ENV_VALUES}:
                key = key_path[0]
                assignment_end = _complete_toml_assignment(lines, index, end)
                replacements.append((index, assignment_end, key))
                index = assignment_end
            else:
                index += 1

        merged = lines[: start + 1]
        cursor = start + 1
        replaced: set[str] = set()
        for assignment_start, assignment_end, key in replacements:
            merged.extend(lines[cursor:assignment_start])
            merged.append(f'{key} = "{_CODEX_ENV_VALUES[key]}"\n')
            replaced.add(key)
            cursor = assignment_end
        merged.extend(lines[cursor:end])
        if merged and not merged[-1].endswith(("\n", "\r")):
            merged.append("\n")
        merged.extend(
            f'{key} = "{value}"\n'
            for key, value in _CODEX_ENV_VALUES.items()
            if key not in replaced
        )
        merged.extend(lines[end:])
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
    if existed:
        if not existing.strip():
            raise ValueError("invalid JSON settings")

        def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"duplicate JSON key: {key}")
                result[key] = value
            return result

        try:
            settings = json.loads(existing, object_pairs_hook=reject_duplicates)
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
