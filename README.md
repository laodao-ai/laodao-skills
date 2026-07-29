# laodao-skills

老刀AI码场自建 Claude Code Skills 统一管理仓库。

## Skills 列表

| 分类 | Skill | 说明 |
|------|-------|------|
| 内容创作 | bilibili-research | B站搜索词调研与选题分析 |
| 内容创作 | x-research | X/Twitter 调研 |
| 内容创作 | youtube-research | YouTube 调研 |
| 内容创作 | zhihu-research | 知乎调研 |
| 开发工具 | commit-message | Git commit 信息生成 |
| 开发工具 | ssh-tunnel | SSH 隧道管理 |
| 开发工具 | tag | Git 语义化版本标签 |
| OpenSpec | opsx-maintain | OpenSpec 目录维护 |
| 嵌入式 | embedded-lint | C 语言静态分析 |
| 文档转换 | docx2md | Word 转 Markdown |
| 文档转换 | pdf2md | PDF 转 Markdown |
| 文档转换 | xlsx2md | Excel 转 CSV |
| 元工具 | laodao-upgrade | 升级并同步配置 laodao-skills |

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

- **Linux/macOS**：setup.sh 在 `~/.claude/skills/` 下为每个 skill 创建相对路径 symlink
- **Windows**：setup.sh 将 skill 目录复制到 `~/.claude/skills/`，并写入 `.laodao-skills` 标记文件用于更新检测

---

## 许可

MIT
