import argparse
import copy
import json
import math
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
from typing import Callable, Literal, Mapping, Sequence


START = "<!-- project-init:windows-shell:start -->"
END = "<!-- project-init:windows-shell:end -->"

Status = Literal["created", "inserted", "updated", "unchanged"]
ConfigStatus = Literal["created", "updated", "unchanged"]
FileSnapshot = tuple[bytes | None, int | None]
FileFingerprint = tuple[bytes | None, int | None, int | None, int | None]

_CODEX_ENV_TABLE = "shell_environment_policy.set"
_CODEX_ENV_VALUES = {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
_CODEX_ENV_PATH = ("shell_environment_policy", "set")
_TOML_MARKER = "__project_init_value_marker__"
_DEFAULT_GIT_BASH_CANDIDATES = (
    Path(r"C:\Program Files\Git\bin\bash.exe"),
    Path(r"C:\Program Files\Git\usr\bin\bash.exe"),
)


def _is_wsl_launcher(path: Path) -> bool:
    normalized = str(path).replace("/", "\\").lower()
    return normalized.endswith(r"\windows\system32\bash.exe")


def _valid_git_bash(path: Path) -> bool:
    """Return whether path resolves to a regular Git-for-Windows bash.exe."""
    if path.name.lower() != "bash.exe" or _is_wsl_launcher(path):
        return False
    try:
        resolved = path.resolve(strict=True)
        metadata = resolved.stat()
    except (OSError, RuntimeError):
        return False
    return (
        resolved.name.lower() == "bash.exe"
        and not _is_wsl_launcher(resolved)
        and stat.S_ISREG(metadata.st_mode)
    )


def discover_git_bash(
    env: Mapping[str, str],
    candidates: Sequence[Path],
    which: Callable[[str], str | None],
) -> Path | None:
    """Find Git for Windows' bash without accepting the WSL launcher."""
    configured = env.get("CLAUDE_CODE_GIT_BASH_PATH")
    paths = ([Path(configured)] if configured else []) + list(candidates)
    for path in paths:
        if _valid_git_bash(path):
            return path

    found = which("bash.exe")
    if not found:
        return None
    path = Path(found)
    return path if _valid_git_bash(path) else None


def _regular_file_state(path: Path) -> os.stat_result | None:
    """lstat a path without following links; allow only regular files or absence."""
    if not os.path.lexists(path):
        return None
    try:
        metadata = os.lstat(path)
    except OSError as error:
        raise ValueError(f"could not safely inspect config path {path}") from error
    if stat.S_ISLNK(metadata.st_mode):
        raise ValueError(f"config path must not be a symbolic link: {path}")
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"config path must be a regular file or be absent: {path}")
    return metadata


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return left.st_dev == right.st_dev and left.st_ino == right.st_ino


def _require_unchanged_file_state(
    path: Path, expected: os.stat_result | None
) -> os.stat_result | None:
    current = _regular_file_state(path)
    if (expected is None) != (current is None):
        raise OSError(f"config path changed during update: {path}")
    if expected is not None and current is not None and not _same_file(expected, current):
        raise OSError(f"config path changed during update: {path}")
    return current


def _read_regular_bytes(path: Path, expected: os.stat_result) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or not _same_file(expected, opened):
            raise OSError(f"config path changed during read: {path}")
        with os.fdopen(descriptor, "rb") as source:
            descriptor = -1
            content = source.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    _require_unchanged_file_state(path, expected)
    return content


def _replace_sibling(
    temporary: Path, destination: Path, expected: os.stat_result | None
) -> None:
    current = _require_unchanged_file_state(destination, expected)
    previous_mode = stat.S_IMODE(current.st_mode) if current is not None else None
    made_writable = False
    try:
        if previous_mode is not None and not previous_mode & stat.S_IWRITE:
            os.chmod(destination, previous_mode | stat.S_IWRITE)
            made_writable = True
        os.replace(temporary, destination)
    except BaseException:
        if made_writable and previous_mode is not None:
            try:
                restored = _regular_file_state(destination)
            except ValueError:
                restored = None
            if restored is not None and current is not None and _same_file(current, restored):
                os.chmod(destination, previous_mode)
        raise


def _write_bytes_to_sibling_temp(path: Path, content: bytes, prefix: str) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(prefix=prefix, dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as destination:
            destination.write(content)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def atomic_write_with_backup(path: Path, content: str) -> Path | None:
    """Atomically write UTF-8/LF content, preserving an existing file as .bak."""
    backup = path.with_name(f"{path.name}.bak")
    existing_state = _regular_file_state(path)
    backup_state = _regular_file_state(backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_mode = stat.S_IMODE(existing_state.st_mode) if existing_state is not None else 0o644
    backup_snapshot: FileSnapshot | None = None
    backup_owned: FileFingerprint | None = None
    if existing_state is not None:
        original = _read_regular_bytes(path, existing_state)
        backup_snapshot = _snapshot_file(backup)
        backup_temporary = _write_bytes_to_sibling_temp(
            backup, original, f".{backup.name}."
        )
        try:
            os.chmod(backup_temporary, existing_mode)
            _replace_sibling(backup_temporary, backup, backup_state)
            backup_owned = _fingerprint_file(backup)
        except BaseException:
            backup_temporary.unlink(missing_ok=True)
            raise

    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    temporary: Path | None = None
    try:
        temporary = _write_bytes_to_sibling_temp(
            path, normalized.encode("utf-8"), f".{path.name}."
        )
        os.chmod(temporary, existing_mode)
        _replace_sibling(temporary, path, existing_state)
    except BaseException as error:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if backup_snapshot is not None and backup_owned is not None:
            try:
                _restore_file(
                    backup,
                    backup_snapshot,
                    expected_current=backup_owned,
                )
            except (OSError, ValueError) as rollback_error:
                raise OSError(
                    f"{error}; backup rollback failed: {rollback_error}"
                ) from error
        raise
    return backup if existing_state is not None else None


def _snapshot_file(path: Path) -> FileSnapshot:
    metadata = _regular_file_state(path)
    if metadata is None:
        return None, None
    return _read_regular_bytes(path, metadata), stat.S_IMODE(metadata.st_mode)


def _fingerprint_file(path: Path) -> FileFingerprint:
    metadata = _regular_file_state(path)
    if metadata is None:
        return None, None, None, None
    return (
        _read_regular_bytes(path, metadata),
        stat.S_IMODE(metadata.st_mode),
        metadata.st_dev,
        metadata.st_ino,
    )


def _require_rollback_owner(path: Path, expected: FileFingerprint) -> None:
    try:
        current = _fingerprint_file(path)
    except (OSError, ValueError) as error:
        raise OSError(f"rollback conflict at {path}") from error
    if current != expected:
        raise OSError(f"rollback conflict at {path}")


def _restore_file(
    path: Path,
    snapshot: FileSnapshot,
    *,
    expected_current: FileFingerprint | None = None,
) -> None:
    if expected_current is not None:
        _require_rollback_owner(path, expected_current)
    content, mode = snapshot
    current = _regular_file_state(path)
    if content is None:
        if current is not None:
            current_mode = stat.S_IMODE(current.st_mode)
            made_writable = False
            if not current_mode & stat.S_IWRITE:
                os.chmod(path, current_mode | stat.S_IWRITE)
                made_writable = True
            try:
                path.unlink()
            except BaseException:
                if made_writable:
                    restored = _regular_file_state(path)
                    if restored is not None and _same_file(current, restored):
                        os.chmod(path, current_mode)
                raise
        return

    assert mode is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _write_bytes_to_sibling_temp(
        path, content, f".{path.name}.rollback."
    )
    try:
        os.chmod(temporary, mode)
        _replace_sibling(temporary, path, current)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _toml_multiline_starts(lines: list[str]) -> list[bool]:
    """Return whether each line starts outside strings, arrays, and inline tables."""
    delimiter: str | None = None
    square_depth = 0
    brace_depth = 0
    starts: list[bool] = []
    for line in lines:
        starts.append(delimiter is None and square_depth == 0 and brace_depth == 0)
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
            if line[index] == "[":
                square_depth += 1
            elif line[index] == "]":
                square_depth -= 1
            elif line[index] == "{":
                brace_depth += 1
            elif line[index] == "}":
                brace_depth -= 1
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


def _codex_toml_layout(
    content: str,
) -> tuple[list[str], list[tuple[int, tuple[str, ...]]], dict[str, object]]:
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
    if isinstance(target, dict):
        for key in _CODEX_ENV_VALUES:
            if key in target and not isinstance(target[key], str):
                raise ValueError(
                    f"conflicting required value {key} must be a string"
                )

    first_header = headers[0][0] if headers else len(lines)
    for index in range(first_header):
        if not starts[index] or (equal := _toml_assignment_equal(lines[index])) is None:
            continue
        if _toml_key_path(lines[index][:equal].strip()) == ("shell_environment_policy",):
            raise ValueError(f"non-table {_CODEX_ENV_TABLE} structure")
    return lines, headers, parsed


def _toml_semantically_equal(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _toml_semantically_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _toml_semantically_equal(left_item, right_item)
            for left_item, right_item in zip(left, right)
        )
    if isinstance(left, float) and math.isnan(left) and math.isnan(right):
        return True
    return left == right


def _verify_codex_update(updated: str, original: dict[str, object]) -> None:
    expected = copy.deepcopy(original)
    policy = expected.setdefault("shell_environment_policy", {})
    if not isinstance(policy, dict):
        raise ValueError(f"non-table {_CODEX_ENV_TABLE} structure")
    target = policy.setdefault("set", {})
    if not isinstance(target, dict):
        raise ValueError(f"non-table {_CODEX_ENV_TABLE} structure")
    target.update(_CODEX_ENV_VALUES)
    try:
        reparsed = tomllib.loads(updated)
    except tomllib.TOMLDecodeError as error:
        raise ValueError("unsafe updated TOML configuration") from error
    if not _toml_semantically_equal(reparsed, expected):
        raise ValueError("unsafe updated TOML changed unrelated semantic values")


def merge_codex_config(path: Path) -> ConfigStatus:
    """Merge Python UTF-8 settings into Codex TOML without replacing user settings."""
    existing_state = _regular_file_state(path)
    existed = existing_state is not None
    existing = (
        _read_regular_bytes(path, existing_state).decode("utf-8") if existing_state else ""
    )
    lines, headers, parsed = _codex_toml_layout(existing)
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

    _verify_codex_update(updated, parsed)
    if updated == existing:
        return "unchanged"
    atomic_write_with_backup(path, updated)
    return "updated" if existed else "created"


def _reject_json_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_claude_json(content: str) -> dict[str, object]:
    if not content.strip():
        raise ValueError("invalid JSON settings")
    try:
        settings = json.loads(content, object_pairs_hook=_reject_json_duplicates)
    except json.JSONDecodeError as error:
        raise ValueError("invalid JSON settings") from error
    if not isinstance(settings, dict):
        raise ValueError("Claude settings must be a JSON object")
    return settings


def merge_claude_settings(path: Path, bash: Path) -> ConfigStatus:
    """Merge required Claude environment variables while preserving user settings."""
    existing_state = _regular_file_state(path)
    existed = existing_state is not None
    existing = (
        _read_regular_bytes(path, existing_state).decode("utf-8") if existing_state else ""
    )
    if existed:
        settings = _load_claude_json(existing)
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
    if not isinstance(configured_bash, str) or not _valid_git_bash(Path(configured_bash)):
        if not _valid_git_bash(bash):
            raise ValueError("selected Git Bash must be a regular Git-for-Windows bash.exe")
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
    """Check the Git Bash Python runtime; this does not validate agent configs."""
    check_name = "git_bash_python_utf8"
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
        return {"name": check_name, "ok": False, "error": str(error)}

    if completed.returncode != 0:
        return {"name": check_name, "ok": False, "returncode": completed.returncode}
    try:
        output = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"name": check_name, "ok": False, "error": "invalid JSON output"}
    if not isinstance(output, dict):
        return {"name": check_name, "ok": False, "error": "invalid JSON object"}

    utf8_mode = output.get("utf8_mode")
    stdout = output.get("stdout")
    ok = utf8_mode == 1 and isinstance(stdout, str) and stdout.lower() == "utf-8"
    return {"name": check_name, "ok": ok, "utf8_mode": utf8_mode, "stdout": stdout}


def _diagnose_codex_config(path: Path) -> dict[str, object]:
    try:
        metadata = _regular_file_state(path)
        if metadata is None:
            return {
                "name": "codex_config",
                "ok": False,
                "error": "missing config.toml",
            }
        content = _read_regular_bytes(path, metadata).decode("utf-8")
        parsed = tomllib.loads(content)
    except tomllib.TOMLDecodeError:
        return {"name": "codex_config", "ok": False, "error": "invalid TOML"}
    except (OSError, UnicodeError, ValueError) as error:
        return {"name": "codex_config", "ok": False, "error": str(error)}

    policy = parsed.get("shell_environment_policy")
    target = policy.get("set") if isinstance(policy, dict) else None
    if not isinstance(target, dict):
        return {
            "name": "codex_config",
            "ok": False,
            "error": "missing shell_environment_policy.set table",
        }
    for key, expected in _CODEX_ENV_VALUES.items():
        if key not in target:
            return {
                "name": "codex_config",
                "ok": False,
                "error": f"missing {key}",
            }
        if not isinstance(target[key], str) or target[key] != expected:
            return {
                "name": "codex_config",
                "ok": False,
                "error": f'{key} must equal string "{expected}"',
            }
    return {"name": "codex_config", "ok": True}


def _diagnose_claude_settings(
    path: Path,
) -> tuple[dict[str, object], dict[str, object] | None]:
    try:
        metadata = _regular_file_state(path)
        if metadata is None:
            return (
                {
                    "name": "claude_settings",
                    "ok": False,
                    "error": "missing settings.json",
                },
                None,
            )
        content = _read_regular_bytes(path, metadata).decode("utf-8")
        settings = _load_claude_json(content)
    except (OSError, UnicodeError, ValueError) as error:
        return (
            {"name": "claude_settings", "ok": False, "error": str(error)},
            None,
        )

    env_settings = settings.get("env")
    if not isinstance(env_settings, dict):
        return (
            {
                "name": "claude_settings",
                "ok": False,
                "error": "Claude settings env must be a JSON object",
            },
            settings,
        )
    for key, expected in _CODEX_ENV_VALUES.items():
        if key not in env_settings:
            return (
                {
                    "name": "claude_settings",
                    "ok": False,
                    "error": f"missing {key}",
                },
                settings,
            )
        if not isinstance(env_settings[key], str) or env_settings[key] != expected:
            return (
                {
                    "name": "claude_settings",
                    "ok": False,
                    "error": f'{key} must equal string "{expected}"',
                },
                settings,
            )
    configured_bash = env_settings.get("CLAUDE_CODE_GIT_BASH_PATH")
    if not isinstance(configured_bash, str):
        return (
            {
                "name": "claude_settings",
                "ok": False,
                "error": "missing or non-string CLAUDE_CODE_GIT_BASH_PATH",
            },
            settings,
        )
    if not _valid_git_bash(Path(configured_bash)):
        return (
            {
                "name": "claude_settings",
                "ok": False,
                "error": "CLAUDE_CODE_GIT_BASH_PATH must name a valid Git Bash",
            },
            settings,
        )
    return {"name": "claude_settings", "ok": True}, settings


def diagnose(home: Path, env: Mapping[str, str]) -> tuple[list[dict[str, object]], bool]:
    """Independently validate Git Bash runtime and both agent configurations."""
    bash = discover_git_bash(env, _DEFAULT_GIT_BASH_CANDIDATES, shutil.which)
    checks: list[dict[str, object]] = []
    if bash is None:
        checks.append({"name": "git_bash", "ok": False, "hint": "Install Git for Windows."})
        checks.append(
            {
                "name": "git_bash_python_utf8",
                "ok": False,
                "error": "not run because Git Bash was not found",
            }
        )
    else:
        checks.append({"name": "git_bash", "ok": True, "path": str(bash)})
        checks.append(probe_python_utf8(bash))

    codex_config = home / ".codex" / "config.toml"
    checks.append(_diagnose_codex_config(codex_config))
    claude_settings = home / ".claude" / "settings.json"
    powershell_enabled = False
    claude_check, settings = _diagnose_claude_settings(claude_settings)
    checks.append(claude_check)
    if settings is not None:
        env_settings = settings.get("env")
        powershell_enabled = isinstance(env_settings, dict) and env_settings.get(
            "CLAUDE_CODE_USE_POWERSHELL_TOOL"
        ) == "1"
    if powershell_enabled:
        checks.append(
            {
                "name": "claude_powershell_tool",
                "ok": False,
                "warning": "CLAUDE_CODE_USE_POWERSHELL_TOOL=1 overrides Git Bash.",
            }
        )

    return checks, all(check["ok"] is True for check in checks)


def _plan_managed_block(
    path: Path, body: str, *, title: str
) -> tuple[str, str, Status]:
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
    return existing, updated, status


def _write_managed_block(path: Path, existing: str, updated: str) -> None:
    if updated != existing:
        with path.open("w", encoding="utf-8", newline="") as destination:
            destination.write(updated)


def replace_managed_block(path: Path, body: str, *, title: str = "# AGENTS") -> Status:
    """Create or replace the repository-managed Windows shell instruction block."""
    existing, updated, status = _plan_managed_block(path, body, title=title)
    _write_managed_block(path, existing, updated)
    return status


def apply_repo(root: Path, assets_dir: Path) -> dict[str, Status]:
    """Apply agent-specific Windows shell instructions to a repository root."""
    agents_body = (assets_dir / "agents-windows-shell.md").read_text(encoding="utf-8")
    claude_body = (assets_dir / "claude-windows-shell.md").read_text(encoding="utf-8")
    plans = {
        "AGENTS.md": (
            root / "AGENTS.md",
            _plan_managed_block(root / "AGENTS.md", agents_body, title="# AGENTS"),
        ),
        "CLAUDE.md": (
            root / "CLAUDE.md",
            _plan_managed_block(root / "CLAUDE.md", claude_body, title="# CLAUDE"),
        ),
    }
    results: dict[str, Status] = {}
    for name, (path, (existing, updated, status)) in plans.items():
        _write_managed_block(path, existing, updated)
        results[name] = status
    return results


def main(argv: Sequence[str] | None = None) -> int:
    """Run repository or user-level Windows shell setup operations."""
    parser = argparse.ArgumentParser(description="Configure Windows Git Bash agent support.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    apply_parser = subparsers.add_parser("apply-repo")
    apply_parser.add_argument("--root", default=".")

    diagnose_parser = subparsers.add_parser("diagnose")
    diagnose_parser.add_argument("--root", default=".")
    diagnose_parser.add_argument("--home", default=str(Path.home()))

    configure_parser = subparsers.add_parser("configure-user")
    configure_parser.add_argument("--root", default=".")
    configure_parser.add_argument("--home", default=str(Path.home()))
    configure_parser.add_argument("--bash")

    try:
        arguments = parser.parse_args(argv)
    except SystemExit as error:
        return int(error.code)

    root = Path(arguments.root).resolve()
    exit_code = 0
    try:
        if arguments.command == "apply-repo":
            assets_dir = Path(__file__).resolve().parents[1] / "assets" / "snippets"
            summary = apply_repo(root, assets_dir)
        elif arguments.command == "diagnose":
            checks, ok = diagnose(Path(arguments.home).resolve(), os.environ)
            summary = {"ok": ok, "checks": checks}
            exit_code = 0 if ok else 1
        else:
            home = Path(arguments.home).resolve()
            if arguments.bash:
                bash = discover_git_bash(
                    {"CLAUDE_CODE_GIT_BASH_PATH": arguments.bash}, [], lambda _: None
                )
            else:
                bash = discover_git_bash(
                    os.environ,
                    _DEFAULT_GIT_BASH_CANDIDATES,
                    shutil.which,
                )
            if bash is None:
                print("Git Bash was not found; install Git for Windows or pass --bash.", file=sys.stderr)
                return 2
            codex_config = home / ".codex" / "config.toml"
            claude_settings = home / ".claude" / "settings.json"
            rollback_paths = (
                codex_config,
                codex_config.with_name("config.toml.bak"),
                claude_settings,
                claude_settings.with_name("settings.json.bak"),
            )
            preflight_states = {
                path: _regular_file_state(path) for path in rollback_paths
            }
            with tempfile.TemporaryDirectory() as temporary_dir:
                temporary_home = Path(temporary_dir)
                temporary_codex = temporary_home / ".codex" / "config.toml"
                temporary_claude = temporary_home / ".claude" / "settings.json"
                for source, destination in (
                    (codex_config, temporary_codex),
                    (claude_settings, temporary_claude),
                ):
                    source_state = preflight_states[source]
                    if source_state is not None:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(_read_regular_bytes(source, source_state))
                merge_codex_config(temporary_codex)
                merge_claude_settings(temporary_claude, bash)
            snapshots = {path: _snapshot_file(path) for path in rollback_paths}
            rollback_owned: dict[Path, FileFingerprint] = {}
            try:
                codex_status = merge_codex_config(codex_config)
                if codex_status == "created":
                    rollback_owned[codex_config] = _fingerprint_file(codex_config)
                elif codex_status == "updated":
                    for changed_path in rollback_paths[:2]:
                        rollback_owned[changed_path] = _fingerprint_file(changed_path)
                claude_status = merge_claude_settings(claude_settings, bash)
            except (OSError, ValueError) as error:
                rollback_errors: list[str] = []
                for path, expected_current in rollback_owned.items():
                    try:
                        _restore_file(
                            path,
                            snapshots[path],
                            expected_current=expected_current,
                        )
                    except (OSError, ValueError) as rollback_error:
                        rollback_errors.append(f"{path}: {rollback_error}")
                if rollback_errors:
                    raise OSError(
                        f"{error}; rollback failed: {'; '.join(rollback_errors)}"
                    ) from error
                raise
            summary = {
                "git_bash": str(bash),
                "codex_config": codex_status,
                "claude_settings": claude_status,
            }
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print(json.dumps(summary, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
