---
name: design-scout-sync
description: |
  从 getdesign.md 同步更新 design-scout 的设计库数据。支持两种模式：
  (1) 初始化迁移——从本地项目快照拷贝 Tier A 品牌（含完整 preview）；
  (2) 增量同步——CLI 新品牌作为 Tier B 下载 DESIGN.md。
  当用户说"同步设计库"、"更新 design scout"、"design scout sync"，或使用 /design-scout-sync 时触发。
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Bash
  - AskUserQuestion
---

# Design Scout Sync — 设计库数据同步

你的任务是同步 design-scout 的本地数据目录。根据当前数据状态，有两种模式：

- **初始化迁移**：从本地项目快照 `D:/01-laodao/design-system/awesome-design-md/design-md/` 拷贝 Tier A 完整品牌（含 4 文件）
- **增量同步**：从 `getdesign` CLI 下载新品牌作为 Tier B（仅 DESIGN.md）

## 数据结构

```
~/.claude/skills/design-scout/data/
├── index.md                     # 预构建索引（含 tier、hasPreview 等扩展字段）
├── design-md/
│   ├── airbnb/                  # Tier A：完整 4 文件
│   │   ├── DESIGN.md
│   │   ├── README.md
│   │   ├── preview.html
│   │   └── preview-dark.html
│   ├── linear.app/              # 品牌名保留原始 "."
│   │   └── ... 4 files
│   ├── binance/                 # Tier B：仅 DESIGN.md
│   │   └── DESIGN.md
│   └── ...
└── .backup-<timestamp>/         # 迁移备份，用于回滚
```

**重要约束：**
- 品牌目录名保留原始命名，包含 `.` 的品牌（如 `linear.app`、`mistral.ai`、`x.ai`、`together.ai`、`opencode.ai`）必须带点，**禁止**替换为 `-`
- Tier B 目录下只能有 `DESIGN.md`，**禁止**创建空的 `preview.html` / `preview-dark.html` 占位文件
- 所有文件位置检测必须基于 `data/design-md/<brand>/DESIGN.md` 目录结构，禁止基于扁平 `<brand>.md` 文件

## 模式检测

在开始同步前，首先检测当前数据状态：

```bash
# 检查是否存在任何 <brand>/DESIGN.md
ls ~/.claude/skills/design-scout/data/design-md/*/DESIGN.md 2>/dev/null | head -1
```

- **如果存在任一 `<brand>/DESIGN.md`** → 数据已是目录结构，进入**增量同步模式**
- **如果只存在扁平 `<brand>.md` 或目录为空** → 进入**初始化迁移模式**

## 模式 A：初始化迁移

### 步骤 A1：前置检查

```bash
# 验证快照路径存在且含足够品牌
SNAPSHOT="D:/01-laodao/design-system/awesome-design-md/design-md"
COUNT=$(ls -d "$SNAPSHOT"/*/ 2>/dev/null | wc -l)
```

如果快照路径不存在或子目录 < 50，**必须中止**并报错：
```
错误：快照路径不可用或不完整（${SNAPSHOT}，发现 ${COUNT} 个子目录）
初始化迁移需要快照作为 Tier A 数据源，请恢复快照后重试。
```

### 步骤 A2：备份现有数据

```bash
TS=$(date +%Y%m%d-%H%M%S)
BACKUP="~/.claude/skills/design-scout/data/.backup-${TS}"
mkdir -p "${BACKUP}/design-md"
cp ~/.claude/skills/design-scout/data/design-md/*.md "${BACKUP}/design-md/" 2>/dev/null
cp ~/.claude/skills/design-scout/data/index.md "${BACKUP}/" 2>/dev/null
```

报告备份位置，告知用户这是回滚点。

### 步骤 A3：拷贝 Tier A 品牌

```bash
cp -r "${SNAPSHOT}"/* ~/.claude/skills/design-scout/data/design-md/
```

### 步骤 A4：验证完整性

对每个拷贝过来的目录，验证它包含 4 个文件（DESIGN.md、README.md、preview.html、preview-dark.html）。输出异常目录的清单（如有）。

### 步骤 A5：清理旧扁平文件

```bash
rm ~/.claude/skills/design-scout/data/design-md/*.md
```

### 步骤 A6：进入增量同步

继续执行模式 B，为 CLI 有但快照没有的品牌补齐 Tier B DESIGN.md。

## 模式 B：增量同步

### 步骤 B1：获取远端品牌列表

```bash
npx getdesign@latest list
```

解析输出，提取品牌名和一句话描述。如果命令失败，报告错误并提示用户检查网络和 Node.js 环境。

### 步骤 B2：差异检测

用 Glob 扫描 `~/.claude/skills/design-scout/data/design-md/*/DESIGN.md`，列出本地已有品牌（目录名即品牌名）。

**禁止**扫描 `*.md`——那是旧扁平结构的残留。

对比远端列表：
- 新增品牌（远端有、本地无）→ 标记为待下载
- 已有品牌（本地无论 Tier A 还是 Tier B）→ 跳过

输出差异报告：
```
远端共 N 个品牌，本地已有 M 个
🆕 新增 K 个（作为 Tier B）：brand1, brand2, ...
✅ 已同步 M 个（Tier A: X, Tier B: Y）
```

如无新增，报告"已是最新"并结束。
如有新增，用 AskUserQuestion 确认是否下载。

### 步骤 B3：下载新品牌

对每个新品牌：

```bash
BRAND="<brand>"
TARGET_DIR="~/.claude/skills/design-scout/data/design-md/${BRAND}"
mkdir -p "${TARGET_DIR}"
npx getdesign@latest add "${BRAND}" --out "${TARGET_DIR}/DESIGN.md" --force
```

**重要：**
- 品牌名保留原始形式（包括 `.`），**禁止**做 `.` → `-` 转换
- 下载后只能有 `DESIGN.md`，**禁止**创建空 preview 占位

每完成一个输出 `✓ 已下载 <brand> (Tier B)`。失败时跳过并报告。

### 步骤 B4：生成索引条目

对每个新下载的品牌：

1. 读取其 DESIGN.md 的 "Visual Theme & Atmosphere" 段落和 "Color Palette" 段落
2. 结合 `getdesign list` 的一句话描述
3. 按以下字段集生成索引条目：

```markdown
## <brand>
- **tier**: B
- **hasPreview**: false
- **类目**: {AI & ML | Dev Tools | Infra & Cloud | Design & Productivity | Fintech & Crypto | Enterprise & Consumer}
- **一句话**: {20-35 words English}
- **色调**: {light|dark|binary} | {primary color} | {secondary color}
- **风格**: {3-5 comma-separated keywords}
- **温度**: {warm | cool | neutral | warm-neutral | cool-neutral}
- **暗色**: {light-only | has-dark | dark-first}
- **字体策略**: {custom|system} ({font names})
- **complexity**: {minimal | balanced | rich}
- **industry-fit**: [{tag1}, {tag2}, ...]
- **适合**: {15-25 中文字符}
```

**industry-fit 封闭词表**（只能从这里选，禁止创造新标签）：
```
saas, devtools, docs, ai-ml, fintech, crypto, ecommerce, marketplace,
content-cms, productivity, analytics, infra, design-tool, collaboration,
enterprise, consumer, media, automotive, luxury, retail
```

**complexity 判定**：
- `minimal` — 极简克制，大留白，少装饰，色彩克制
- `balanced` — 信息密度适中，装饰适度，有层次感但不拥挤
- `rich` — 高密度信息或装饰密集，戏剧化视觉

### 步骤 B5：追加到 index.md

把新条目追加到 `~/.claude/skills/design-scout/data/index.md`。更新文件头部的品牌总数、Tier A/B 数和更新日期。

**重要：**
- Tier A 数不变（本次不新增 Tier A）
- Tier B 数 += 本次新增数

### 步骤 B6：更新 CHANGELOG

在 `~/.claude/skills/design-scout/CHANGELOG.md` 顶部追加新版本条目：

```markdown
## vX.Y.0 (YYYY-MM-DD)

- 新增 K 个品牌（Tier B）：brand1, brand2, ...
- 数据源：getdesign vX.X.X
- 品牌总数：M → N（Tier A: X, Tier B: Y → Z）
```

版本号规则：minor 版本自增（如 v2.0.0 → v2.1.0）。从 CHANGELOG.md 读取最近版本号推算。

如无新增，**禁止**写空 CHANGELOG 条目。

### 步骤 B7：输出完成摘要

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Design Scout Sync 完成
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  模式：{初始化迁移 + 增量同步 | 仅增量同步}
  新增品牌：K 个 Tier B (brand1, brand2, ...)
  品牌总数：N (Tier A: X, Tier B: Y)
  index.md：已更新
  CHANGELOG：vX.Y.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## 重要规则

- **品牌目录名保留原名**：`linear.app` 不是 `linear-app`
- **基于目录而非文件检测**：用 `<brand>/DESIGN.md` 而非 `<brand>.md`
- **下载后只有 DESIGN.md**：不伪造空 preview 占位
- **只处理新增品牌**，不覆盖已有品牌（除非用户明确要求）
- **初始化迁移幂等**：如果数据已是目录结构，跳过迁移直接进增量同步
- **无新增时不写 CHANGELOG**
- **索引条目的 industry-fit 必须使用封闭词表**
- **tier 与 hasPreview 必须一致**：A↔true, B↔false

## 与 design-scout 的"应用到项目"协议

注意 sync 只负责维护 skill 数据目录，不涉及"应用到项目"。但要知道 design-scout 的应用规则对 sync 的约束：

- 品牌目录下存在的文件会被 design-scout 复制到用户项目 `<project>/design-system/ref/<brand>/`（每个选中品牌一个独立子目录，支持多选应用）
- Tier A 必须保持 4 文件完整性（DESIGN.md + README.md + preview.html + preview-dark.html），否则下游的复制会缺文件
- Tier B 必须严格只有 DESIGN.md，**禁止**创建空 preview 占位文件，否则会在用户项目的 `design-system/ref/<brand>/` 里产生垃圾空文件
