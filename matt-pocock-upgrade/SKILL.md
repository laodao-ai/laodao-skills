---
name: matt-pocock-upgrade
description: 安装、更新或迁移 Matt Pocock skills；管理 ~/.skills 源码仓库、~/.agents/skills 安装副本及 ~/.claude/skills 符号链接。
---

# Matt Pocock Upgrade

使用 `scripts/upgrade.py`，不手工覆盖安装目录。此脚本面向 macOS/Linux 的符号链接布局。

## 执行

使用脚本的绝对路径，从安装目录外运行：

```bash
python3 ~/.agents/skills/matt-pocock-upgrade/scripts/upgrade.py
```

默认 clone 或快进更新 `~/.skills/mattpocock-skills`，只同步已受管 skills 到 `~/.agents/skills/<name>`，并为 Claude 创建指向安装副本的相对符号链接。源码、安装副本与链接分别管理。不会运行上游 skill 或项目配置流程。

- 新安装或新增 skill：先展示候选名称，由用户选择后使用可重复的 `--skill NAME`。不自动安装所有上游新增项。
- 首次接管旧安装：先运行 `--adopt-existing --dry-run`。读取现有安装与上游的实际差异，报告本地定制及来源冲突。用户明确同意接管后运行 `--adopt-existing`；它只备份、记录现有基线、移交锁文件条目并退出，不更新内容。用户已明确授权接管同一范围时不重复确认。
- 接管后首次更新会替换与上游不同的内容，因此必须先确认这些差异可被替换；不能将“同意接管”理解为“同意丢弃本地定制”。
- `--dry-run` 不修改安装内容和安装记录，但会创建进程锁，也可能 clone/fetch/快进源码。完全本地预览使用 `--offline --dry-run`。
- `--repo PATH` 指定源码位置。`--home PATH` 仅用于隔离验证，不能改变真实用户的 HOME 环境变量。

## 保护与恢复

- 源码有本地改动、非默认分支、origin 不匹配、历史分叉、安装副本被修改或同名目录属于其他来源时停止，不自动 stash/reset/覆盖。
- 接管仅接受 `.agents/.skill-lock.json` 明确标记为 `mattpocock/skills` 且目录仍存在的条目。不恢复已删除的历史安装。
- 接管成功后，仅移除旧锁文件中已接管的条目，其余来源与已缺失目录的记录不动。后续由 `.agents/.matt-pocock-upgrade.json` 管理，避免两个更新器同时管理同一批文件。
- 上游删除或改名只报告，保留旧安装。新增名称需显式选择，不自动推断改名。
- 备份在 `.agents/matt-pocock-backups/`，不自动清理。更新保留旧目录与元数据；中断时保留 `.matt-pocock-upgrade-pending.json` 并阻止继续更新。
- 遇到 pending：读取其中的备份位置，核对安装和旧元数据，提出具体恢复方案。不要直接删除 pending 后重跑；新增目录和链接也要纳入恢复核对。
- 网络或用户目录写入受沙盒限制时，为相同命令申请相应权限，不改用其他工具绕过。

完成后报告源码 commit、更新或接管的名称、未处理的新增/移除项、备份位置及验证结果。重复运行同一版本应不再写入文件。不要自动 commit/push，也不要同步修改用户项目文档。
