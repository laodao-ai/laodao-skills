---
name: design-scout-sync
description: |
  从 getdesign.md 同步更新 design-scout 的设计库数据。检测新品牌、下载 DESIGN.md、
  自动生成索引条目、更新 CHANGELOG。当用户说"同步设计库"、"更新 design scout"、
  "design scout sync"，或使用 /design-scout-sync 时触发。
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Bash
  - AskUserQuestion
---

# Design Scout Sync — 设计库数据同步

你的任务是从 getdesign.md CLI 同步最新的品牌 DESIGN.md 数据到 design-scout 的本地数据目录。

## 数据位置

- 设计文件目录：`~/.claude/skills/design-scout/data/design-md/`
- 索引文件：`~/.claude/skills/design-scout/data/index.md`
- 更新记录：`~/.claude/skills/design-scout/CHANGELOG.md`

## 工作流

### 步骤 1：获取远端品牌列表

```bash
npx getdesign@latest list
```

解析输出，提取每个品牌的名称和一句话描述。如果命令失败，报告错误并提示用户检查网络和 Node.js 环境。

### 步骤 2：确定同步范围

**全量同步**（无参数）：比较远端列表和本地 `data/design-md/` 目录下的文件。

**指定品牌同步**（有参数）：只处理指定的品牌名。

品牌名到文件名的转换规则：将 `.` 替换为 `-`（如 `linear.app` → `linear-app.md`）。

### 步骤 3：差异检测

用 Glob 扫描 `~/.claude/skills/design-scout/data/design-md/*.md`，列出本地已有文件。

对比远端列表，识别：
- 新增品牌（远端有、本地无）
- 已有品牌（远端有、本地有）

输出差异报告：
```
远端共 N 个品牌，本地已有 M 个
🆕 新增 K 个：brand1, brand2, ...
✅ 已同步 M 个
```

如果无新增，报告"已是最新，无需更新"并结束。

如果有新增，用 AskUserQuestion 确认是否下载。

### 步骤 4：下载新品牌

对每个新品牌执行：

```bash
npx getdesign@latest add <brand> --out ~/.claude/skills/design-scout/data/design-md/<filename>.md
```

其中 `<filename>` 是品牌名中 `.` 替换为 `-` 后的结果。

下载后验证文件存在：
```bash
ls ~/.claude/skills/design-scout/data/design-md/<filename>.md
```

每完成一个输出 `✓ 已下载 <brand>`。如果下载失败，跳过并报告。

### 步骤 5：生成索引条目

对每个新下载的品牌：

1. 读取其 DESIGN.md 的前 30 行（Visual Theme & Atmosphere 段落）
2. 结合 getdesign list 的一句话描述
3. 生成结构化索引条目，格式与 index.md 中现有条目一致：

```markdown
## {filename-without-extension}
- **类目**: {AI & ML / Dev Tools / Infra & Cloud / Design & Productivity / Fintech & Crypto / Enterprise & Consumer}
- **一句话**: {英文描述}
- **色调**: {light/dark} | {主色} | {辅色}
- **风格**: {3-5 个关键词}
- **温度**: {warm / cool / neutral / warm-neutral / cool-neutral}
- **暗色**: {dark-first / has-dark / light-only}
- **字体策略**: {custom/system} ({字体名})
- **适合**: {中文，15-25字}
```

4. 追加到 `data/index.md` 文件末尾
5. 更新 index.md 头部的品牌总数和日期

### 步骤 6：更新 CHANGELOG

在 `~/.claude/skills/design-scout/CHANGELOG.md` 中追加新版本条目：

```markdown
## vX.Y.0 (YYYY-MM-DD)

- 新增 K 个品牌：brand1, brand2, ...
- 数据源：getdesign vX.X.X
- 品牌总数：M → N
```

版本号规则：minor 版本自增（如 v1.0.0 → v1.1.0）。从 CHANGELOG.md 中读取最近版本号推算。

### 步骤 7：输出完成摘要

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Design Scout Sync 完成
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  新增品牌：K 个 (brand1, brand2, ...)
  品牌总数：N
  index.md：已更新
  CHANGELOG：vX.Y.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## 重要规则

- 下载后必须验证文件存在
- 只处理新增品牌，不覆盖已有品牌（除非用户明确要求）
- 无新增时不写 CHANGELOG
- 索引条目格式必须与 index.md 现有格式完全一致
