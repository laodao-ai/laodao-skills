#!/usr/bin/env python3
"""管理 Matt Pocock skills 的源码、安装副本和 Claude 符号链接。"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

SOURCE = "mattpocock/skills"
URL = "https://github.com/mattpocock/skills.git"


class UpgradeError(RuntimeError):
    pass


def git(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if result.returncode:
        raise UpgradeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def read_json(path, default):
    if path.is_symlink():
        raise UpgradeError(f"元数据不能是符号链接：{path}")
    return json.loads(path.read_text()) if path.exists() else default


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    os.replace(temporary, path)


def snapshot(path):
    if path.is_symlink() or not path.is_dir():
        raise UpgradeError(f"需要真实目录：{path}")
    result = {}
    for item in sorted(path.rglob("*")):
        if item.is_symlink():
            raise UpgradeError(f"skill 内含符号链接，停止复制：{item}")
        if item.is_file():
            result[item.relative_to(path).as_posix()] = {
                "sha256": hashlib.sha256(item.read_bytes()).hexdigest(),
                "executable": bool(item.stat().st_mode & 0o111),
            }
        elif not item.is_dir():
            raise UpgradeError(f"不支持的文件类型：{item}")
    return result


def discover(repo):
    skills = {}
    for entry in sorted((repo / "skills").rglob("SKILL.md")):
        name = entry.parent.name
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            raise UpgradeError(f"非法 skill 名称：{name}")
        if name in skills:
            raise UpgradeError(f"重复 skill 名称：{name}")
        if entry.parent.is_symlink() or not entry.resolve().is_relative_to(repo.resolve()):
            raise UpgradeError(f"源码路径越界：{entry}")
        skills[name] = entry.parent
    if not skills:
        raise UpgradeError("源码仓库没有可识别的 skills")
    return skills


def prepare_repo(repo, offline=False):
    if not repo.exists():
        if offline:
            raise UpgradeError("--offline 要求源码仓库已存在")
        repo.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(["git", "clone", URL, str(repo)])
        if result.returncode:
            raise UpgradeError("clone 失败；保留现场，不自动删除")
    if repo.is_symlink() or not (repo / ".git").is_dir():
        raise UpgradeError(f"不是独立 Git checkout：{repo}")
    origin = git(repo, "remote", "get-url", "origin")
    if origin not in {URL, "https://github.com/mattpocock/skills", "git@github.com:mattpocock/skills.git"}:
        raise UpgradeError(f"origin 不是 Matt Pocock 官方仓库：{origin}")
    dirty = git(repo, "status", "--porcelain", "--untracked-files=all")
    if dirty:
        raise UpgradeError("源码仓库有本地改动：\n" + dirty)
    branch = git(repo, "branch", "--show-current")
    remote_head = git(repo, "symbolic-ref", "refs/remotes/origin/HEAD")
    expected = remote_head.removeprefix("refs/remotes/origin/")
    if not branch or branch != expected:
        raise UpgradeError(f"仅允许默认分支 {expected}，当前为 {branch or 'detached HEAD'}")
    if not offline:
        git(repo, "fetch", "origin", f"refs/heads/{branch}:refs/remotes/origin/{branch}")
        git(repo, "merge-base", "--is-ancestor", "HEAD", f"origin/{branch}")
        git(repo, "merge", "--ff-only", f"origin/{branch}")
    return git(repo, "rev-parse", "HEAD")


def check_link(link, destination):
    if link.is_symlink():
        if link.resolve() != destination.resolve():
            raise UpgradeError(f"Claude 同名链接属于其他来源：{link}")
    elif link.exists():
        raise UpgradeError(f"Claude 同名路径不是受管链接：{link}")


def execute(home, repo, commit, *, names=(), adopt=False, dry_run=False):
    agents = home / ".agents"
    installs = agents / "skills"
    claude = home / ".claude" / "skills"
    state_path = agents / ".matt-pocock-upgrade.json"
    lock_path = agents / ".skill-lock.json"
    pending = agents / ".matt-pocock-upgrade-pending.json"
    if pending.exists() or pending.is_symlink():
        raise UpgradeError(f"上次执行中断，请先依据事务记录恢复：{pending}")
    state = read_json(state_path, {"version": 1, "skills": {}})
    if state.get("version") != 1:
        raise UpgradeError("不支持的安装清单版本")
    legacy = read_json(lock_path, {"version": 3, "skills": {}})
    available = discover(repo)
    managed = state["skills"]
    for name in set(managed) | set(names):
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            raise UpgradeError(f"非法 skill 名称：{name}")
    candidates = {
        name for name, entry in legacy["skills"].items()
        if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)
        and entry.get("source") == SOURCE and (installs / name).is_dir()
    }
    selected = set(names) if names else (candidates if adopt else set(managed))
    print("未纳入管理的上游 skills：" + ", ".join(sorted(set(available) - set(managed))))
    missing = selected - set(available)
    if missing:
        print("上游已移除，保留本地：" + ", ".join(sorted(missing)))
    if adopt:
        selected -= set(managed)
        if selected - candidates:
            raise UpgradeError("只能接管锁文件明确标记为 mattpocock/skills 的现有安装")
    else:
        if set(names) - set(available):
            raise UpgradeError("显式指定的 skill 在上游不存在")
        selected -= missing
    if not selected:
        if not managed:
            raise UpgradeError("尚无受管 skill。用 --adopt-existing 接管现有安装，或 --skill NAME 选择新安装")
        print("无需更新")
        return
    plans = []
    # 所有目标先检查，再开始任何安装修改，避免遇到后面的冲突时已有部分覆盖。
    for name in sorted(selected):
        target = installs / name
        link = claude / name
        check_link(link, target)
        old = snapshot(target) if target.exists() or target.is_symlink() else None
        if adopt:
            upstream = snapshot(available[name]) if name in available else None
            print(f"接管 {name}：" + ("与上游一致" if old == upstream else "与上游不同；保留当前内容作为基线"))
            plans.append((name, old, old, False))
            continue
        if name in legacy["skills"]:
            raise UpgradeError(f"{name} 仍由 .skill-lock.json 管理；先显式接管，避免双重管理")
        if name in managed:
            if old != managed[name]["files"]:
                raise UpgradeError(f"安装副本被修改或删除，停止：{target}")
        elif old is not None:
            raise UpgradeError(f"同名安装不受本脚本管理，停止：{target}")
        new = snapshot(available[name])
        plans.append((name, old, new, old != new))
    for name, _, _, changed in plans:
        print(f"{name}: " + ("接管（不更新内容）" if adopt else "更新" if changed else "内容无变化"))
    if dry_run:
        print("预览完成，未修改安装目录和安装记录")
        return
    agents.mkdir(parents=True, exist_ok=True)
    installs.mkdir(parents=True, exist_ok=True)
    claude.mkdir(parents=True, exist_ok=True)
    metadata_change = adopt or any(
        changed or not (claude / name).is_symlink() or managed.get(name, {}).get("commit") != commit
        for name, _, _, changed in plans
    )
    if not metadata_change:
        print("无需更新（文件、版本记录与链接均一致）")
        return
    backup = agents / "matt-pocock-backups" / (str(time.time_ns()))
    backup.mkdir(parents=True)
    for path in (state_path, lock_path):
        if path.exists():
            shutil.copy2(path, backup / path.name)
    write_json(pending, {"backup": str(backup), "skills": [p[0] for p in plans], "adopt": adopt})
    for name, old, new, changed in plans:
        target = installs / name
        if old is not None and (changed or adopt):
            shutil.copytree(target, backup / name)
        if changed:
            stage = Path(tempfile.mkdtemp(prefix=f".{name}-", dir=installs))
            shutil.copytree(available[name], stage, dirs_exist_ok=True)
            if snapshot(stage) != new:
                raise UpgradeError(f"复制校验失败：{stage}")
            if target.exists():
                # 原目录移入备份，不删除用户文件；中断时按 pending 记录恢复。
                target.rename(backup / f"{name}.original")
            stage.rename(target)
        link = claude / name
        if not link.is_symlink():
            link.symlink_to(os.path.relpath(target, claude), target_is_directory=True)
        managed[name] = {
            "files": new,
            "commit": None if adopt else commit,
            "path": available[name].relative_to(repo).as_posix() if name in available else None,
        }
        if adopt:
            del legacy["skills"][name]
        if snapshot(target) != new:
            raise UpgradeError(f"安装后校验失败：{target}")
        check_link(link, target)
    write_json(state_path, state)
    if adopt:
        write_json(lock_path, legacy)
    pending.unlink()
    print(f"完成；备份：{backup}")
    if adopt:
        print("接管仅记录现有内容并移交锁文件所有权；下一次运行才同步上游。请先确认差异中的本地定制可被替换。")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, help="默认 ~/.skills/mattpocock-skills")
    parser.add_argument("--home", type=Path, default=Path.home(), help="安装根目录；用于隔离验证")
    parser.add_argument("--skill", action="append", default=[], help="显式选择 skill，可重复")
    parser.add_argument("--adopt-existing", action="store_true", help="接管现有安装，保留内容并退出")
    parser.add_argument("--dry-run", action="store_true", help="预览安装；仍会更新源码 checkout")
    parser.add_argument("--offline", action="store_true", help="使用已有干净 checkout，不访问远端")
    args = parser.parse_args(argv)
    try:
        home = args.home.expanduser().absolute()
        repo = args.repo.expanduser().absolute() if args.repo else home / ".skills/mattpocock-skills"
        for root in (home / ".agents/skills", home / ".claude/skills"):
            if repo.resolve().is_relative_to(root.resolve()) or root.resolve().is_relative_to(repo.resolve()):
                raise UpgradeError("源码仓库与安装目录不能互相包含")
        # 使用系统锁，避免两个升级进程在预检查后同时覆盖安装和清单。
        lock_dir = home / ".agents"
        lock_dir.mkdir(parents=True, exist_ok=True)
        guard = lock_dir / ".matt-pocock-upgrade.lock"
        if guard.is_symlink():
            raise UpgradeError(f"进程锁不能是符号链接：{guard}")
        with guard.open("a") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise UpgradeError("另一个升级进程正在运行")
            commit = prepare_repo(repo, args.offline)
            print(f"源码：{repo}\n版本：{commit}")
            execute(home, repo, commit, names=args.skill, adopt=args.adopt_existing, dry_run=args.dry_run)
    except (UpgradeError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
