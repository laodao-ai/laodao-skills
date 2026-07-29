#!/usr/bin/env python3
"""Safely upgrade laodao-skills and install it for Claude Code and Codex."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, NamedTuple, Sequence


class UpgradeError(RuntimeError):
    """Raised when an upgrade cannot continue without risking local state."""


class CommandError(UpgradeError):
    def __init__(self, command: Sequence[str], returncode: int, detail: str = ""):
        rendered = " ".join(str(part) for part in command)
        message = f"命令失败（exit {returncode}）：{rendered}"
        if detail.strip():
            message += f"\n{detail.strip()}"
        super().__init__(message)


class UpgradeResult(NamedTuple):
    before: str
    after: str
    updated: bool


Runner = Callable[[Sequence[str], Path, bool, bool], subprocess.CompletedProcess]


def _is_checkout(path: Path) -> bool:
    return (path / ".git").exists() and (path / "setup.sh").is_file()


def _ancestors(path: Path):
    current = path.resolve()
    if current.is_file():
        current = current.parent
    yield current
    yield from current.parents


def find_repo(
    explicit_repo: Path | str | None = None,
    *,
    home: Path | None = None,
    cwd: Path | None = None,
) -> Path:
    """Locate a laodao-skills checkout without guessing a writable destination."""
    if explicit_repo is not None:
        candidate = Path(explicit_repo).expanduser().resolve()
        if not _is_checkout(candidate):
            raise UpgradeError(f"不是有效的 laodao-skills 仓库：{candidate}")
        return candidate

    user_home = (home or Path.home()).resolve()
    working_dir = (cwd or Path.cwd()).resolve()
    script_checkout = Path(__file__).resolve().parents[2]

    candidates = []
    candidates.extend(_ancestors(working_dir))
    candidates.extend(
        [
            user_home / ".skills" / "laodao-skills",
            user_home / ".claude" / "skills" / "laodao-skills",
            user_home / ".codex" / "skills" / "laodao-skills",
            script_checkout,
        ]
    )

    seen = set()
    for raw_candidate in candidates:
        candidate = raw_candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        if _is_checkout(candidate):
            return candidate

    raise UpgradeError(
        "找不到 laodao-skills 源码仓库。请使用 --repo 指定仓库，"
        "或先克隆到 ~/.skills/laodao-skills。"
    )


def run_command(
    command: Sequence[str],
    cwd: Path,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess:
    completed = subprocess.run(
        [str(part) for part in command],
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=False,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr or completed.stdout or ""
        raise CommandError(command, completed.returncode, detail)
    return completed


def _capture(runner: Runner, command: Sequence[str], repo: Path) -> str:
    return runner(command, repo, True, True).stdout.strip()


def find_bash() -> str:
    found = shutil.which("bash")
    if found:
        return found

    roots = [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("LocalAppData"),
    ]
    suffixes = [Path("Git/bin/bash.exe"), Path("Programs/Git/bin/bash.exe")]
    for root in roots:
        if not root:
            continue
        for suffix in suffixes:
            candidate = Path(root) / suffix
            if candidate.is_file():
                return str(candidate)

    raise UpgradeError("找不到 bash。Windows 请先安装 Git for Windows，并确保 Git Bash 可用。")


def upgrade_repo(
    repo: Path | str,
    *,
    runner: Runner = run_command,
    bash_path: str | None = None,
) -> UpgradeResult:
    repo_path = Path(repo).resolve()
    if not _is_checkout(repo_path):
        raise UpgradeError(f"不是有效的 laodao-skills 仓库：{repo_path}")

    dirty = _capture(runner, ("git", "status", "--porcelain"), repo_path)
    if dirty:
        raise UpgradeError(
            "仓库存在未提交改动，已停止升级；请先提交或自行处理这些改动。\n" + dirty
        )

    branch = _capture(runner, ("git", "branch", "--show-current"), repo_path)
    if branch != "main":
        raise UpgradeError(f"当前分支是 {branch or 'detached HEAD'}，仅支持从 main 安全升级。")

    runner(("git", "fetch", "origin", "main"), repo_path, False, True)
    before = _capture(runner, ("git", "rev-parse", "HEAD"), repo_path)
    remote = _capture(runner, ("git", "rev-parse", "origin/main"), repo_path)

    updated = before != remote
    if updated:
        ancestor = runner(
            ("git", "merge-base", "--is-ancestor", "HEAD", "origin/main"),
            repo_path,
            False,
            False,
        )
        if ancestor.returncode != 0:
            raise UpgradeError("本地 main 与 origin/main 已分叉，无法快进；请先手动处理。")
        runner(("git", "merge", "--ff-only", "origin/main"), repo_path, False, True)

    bash = bash_path or find_bash()
    runner((bash, str((repo_path / "setup.sh").resolve())), repo_path, False, True)
    return UpgradeResult(before=before, after=remote, updated=updated)


def _read_version(repo: Path) -> str:
    version_file = repo / "VERSION"
    return version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else "unknown"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="升级 laodao-skills，并同步配置到 Claude Code 与 Codex。"
    )
    parser.add_argument("--repo", type=Path, help="laodao-skills 源码仓库路径")
    args = parser.parse_args(argv)

    try:
        repo = find_repo(args.repo)
        print(f"源码仓库：{repo}")
        result = upgrade_repo(repo)
    except UpgradeError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    state = "已更新" if result.updated else "已是最新版本"
    print(f"完成：laodao-skills {state}（v{_read_version(repo)}）")
    print("已运行 setup.sh，同步配置到 Claude Code 与 Codex。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
