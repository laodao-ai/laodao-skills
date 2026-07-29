---
name: laodao-upgrade
description: Use when 用户要求升级、更新或重新安装 laodao-skills，或需要把仓库中的 skills 同步配置到 Claude Code 与 Codex。
---

# Laodao Upgrade

## Overview

使用 `scripts/upgrade.py` 执行可重复的安全升级。脚本负责定位源码仓库、保护本地改动、快进到 `origin/main`，并调用仓库的 `setup.sh` 同步 Claude Code 与 Codex。

## Workflow

1. 告知用户该操作会访问 Git 远端，并写入 Claude Code 与 Codex 的用户级 skills 目录。若运行环境要求批准，直接为升级命令申请批准。
2. 从本 skill 目录执行：

   ```bash
   python scripts/upgrade.py
   ```

   若当前解释器命令是 `python3`，使用 `python3 scripts/upgrade.py`。
3. 默认定位失败时，让用户提供源码仓库路径，随后执行：

   ```bash
   python scripts/upgrade.py --repo <laodao-skills-repo>
   ```

4. 保留并向用户展示脚本及 `setup.sh` 的输出。成功时报告版本、是否拉到新提交，以及 Claude Code/Codex 同步结果。

## Safety Contract

- 仓库有未提交或未跟踪改动时停止。报告 `git status --short` 结果；不要自动 stash、reset、clean、commit 或覆盖。
- 仅允许 `main` 快进到 `origin/main`。分支错误、detached HEAD、历史分叉或命令失败时停止并报告。
- 找不到源码仓库时停止并请求 `--repo`；不要自行选择位置 clone。
- 安装只调用仓库自带 `setup.sh`。不要绕过其受管标记和同名目录保护逻辑。
- 不删除仓库外目录；孤儿 skill 的清理由 `setup.sh` 自己处理。

## Failure Handling

| 情况 | 处理 |
|---|---|
| 未提交改动 | 停止，列出改动，等待用户处理 |
| 非 `main` 或历史分叉 | 停止，给出当前状态，不自动切分支或改历史 |
| 网络或权限失败 | 保留原错误；按运行环境申请权限后重试同一命令 |
| 找不到 Bash | 提示 Windows 安装 Git for Windows，其他平台确保 `bash` 在 PATH |
| 同名 skill 未受 laodao 管理 | 尊重 `setup.sh` 的 skipped 结果，不覆盖 |
