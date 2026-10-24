# laodao-skills

老刀AI码场自建 Claude Code Skills 统一管理仓库。

> **从旧版迁移**：本仓历史已重建，`/laodao-upgrade` 会报「已分叉」。
> 已有安装请看 [迁移指引](docs/migrate-to-v2.md)。

## Skills 列表

| 分类 | Skill | 说明 |
|------|-------|------|
| 内容创作 | bilibili-research | B站搜索词调研与选题分析 |
| 内容创作 | x-research | X/Twitter 调研 |
| 内容创作 | youtube-research | YouTube 调研 |
| 内容创作 | zhihu-research | 知乎调研 |
| 开发工具 | commit-message | Git commit 信息生成 |
| 开发工具 | tag | Git 语义化版本标签 |
| 嵌入式 | embedded-lint | C 语言静态分析 |
| 嵌入式 | embedded-test-sop | 为嵌入式固件功能生成手动测试 SOP 与日志自动分析规则 |
| 文档归档 | chatgpt-share-download | 下载 ChatGPT 共享对话，保存原始消息、本地图片与媒体恢复状态 |
| 文档转换 | docx2md | Word 转 Markdown |
| 文档转换 | pdf2md | PDF 转 Markdown |
| 文档转换 | xlsx2md | Excel 转 CSV |
| 元工具 | laodao-upgrade | 升级并同步配置 laodao-skills |
| 元工具 | matt-pocock-upgrade | 管理 Matt Pocock skills 的源码、安装副本、备份及 Claude 符号链接 |
| 元工具 | claude-upgrade | 绕过官方脚本下载并安装 Claude Code 原生二进制 |

> **迁入说明**：`embedded-test-sop` 已从 sdflow-skills
> 迁入本仓。运行 `bash setup.sh` 时，这个名称可安全接管仍指向旧仓的软链接或
> Windows `.sdflow-skills` 标记副本；其他第三方同名 skill 不会被覆盖。

## 安装

```bash
cd ~/.claude/skills
git clone https://github.com/laodao-ai/laodao-skills.git
cd laodao-skills
bash setup.sh
```

## 更新

在 Claude Code 中直接使用：

```
/laodao-upgrade
```

在 Codex 中直接使用：

```
$laodao-upgrade
```

或手动更新：

```bash
cd ~/.claude/skills/laodao-skills
git pull
bash setup.sh
```

## 工作原理

- **Linux/macOS**：setup.sh 为每个 skill 创建绝对路径 symlink，目标同时含
  `~/.claude/skills/` 与 `~/.agents/skills/`（Codex / Cursor 共享落点）；
  仍留在 `~/.codex/skills/` 的本仓旧安装项会在新落点就绪后清掉
- **Windows**：setup.sh 将 skill 目录复制到上述两个目录下，并写入 `.laodao-skills` 标记文件用于更新检测

---

## 许可

Apache License 2.0，见 [LICENSE](LICENSE)。
