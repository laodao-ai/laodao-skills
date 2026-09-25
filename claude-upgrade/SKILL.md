---
name: claude-upgrade
description: 绕过官方安装脚本，直接从 downloads.claude.ai 下载并安装 Claude Code 原生二进制（macOS/Linux 装进 versions 目录并重建软链，Windows 原位替换 claude.exe）。当用户说"升级 claude"、"更新 Claude Code"、"claude 官方升级下载失败"、"装指定版本的 claude"，或使用 /claude-upgrade 时触发。
---

# Claude Upgrade

`scripts/upgrade.py` 完成全部步骤：读 `latest` 取版本 → 读该版本 `manifest.json` 取本平台文件名、sha256、大小 → curl 下载（失败自动续传重试）→ 校验 → 安装 → 用新二进制跑 `--version` 确认。

| 平台 | 安装方式 |
|---|---|
| macOS / Linux | 写入 `~/.local/share/claude/versions/<版本号>`，`chmod 755`，`~/.local/bin/claude` 软链指向它；旧版本文件保留 |
| Windows | 原位替换 PATH 上的 `claude.exe`（找不到则 `%USERPROFILE%\.local\bin\claude.exe`）；旧文件改名为 `claude.exe.old` |

## Workflow

1. 在本 skill 目录执行（`python` 不存在时用 `python3`）：

   ```bash
   python scripts/upgrade.py
   ```

   用户要指定版本时加 `--version <x.y.z>`；只想看有没有新版时加 `--check`；同版本重装加 `--force`。

2. 向用户报告脚本输出里的平台、旧版本 → 新版本。脚本以 `升级完成` 结尾才算成功。
3. 提醒用户：当前会话仍在跑旧版本，退出后重开 `claude` 才是新版本。

## 失败处理

| 情况 | 处理 |
|---|---|
| curl 连接失败 / 超时 | 检查 `HTTPS_PROXY` 是否设置且代理可用；同一命令重跑即可续传 |
| sha256 或大小不符 | 脚本已删掉坏文件；重跑一次，仍不符则把两个校验值报给用户，停止 |
| Windows 找不到 `claude.exe` | 询问用户 claude.exe 所在目录；该情况多为 npm 安装，本 skill 只管原生二进制 |
| 安装后 `--version` 不符 | 报告实际输出，不再重试 |
