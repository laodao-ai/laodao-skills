import json
from pathlib import Path
import shutil
import subprocess
from typing import Callable, Literal, Mapping, Sequence


START = "<!-- project-init:windows-shell:start -->"
END = "<!-- project-init:windows-shell:end -->"

Status = Literal["created", "inserted", "updated", "unchanged"]


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
