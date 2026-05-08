---
name: config-skills
description: >
  扫描已安装的 plugin 和用户级 skill，按工作场景一键配置项目级 .claude/settings.json
  的 skillOverrides 与 enabledPlugins 字段。
  内置 4 套 preset：content-creation（内容/博客/设计）、go-dev（Go 后端/CLI）、
  embedded-dev（嵌入式 C/MCU）、web-dev（前端/全栈）。

  当用户说"配置 skill"、"配 settings.json"、"调 skillOverrides"、"切换 skill 模式"、
  "切到内容/Go/嵌入式/Web 模式"、"加载 preset"、"换工作模式"、"配置 plugin"、
  "skill 太多了清理一下"、"新项目第一次配 settings"、"批量启用禁用 skill"、
  "config-skills"，或使用 /config-skills 时**必须**触发此 skill。

  即使用户没明确说"preset"或"模式"，只要表达"想调整一组 skill 的开关"、"按场景配置"、
  "skill 加载策略"、"上下文太满想精简 skill"，也应主动触发本 skill 询问是否套用 preset。
---

# Config Skills v4 — 渲染模型 + plugin 对称化

> **推荐模型**：Haiku（流程明确的执行类任务，不需要 Opus 的推理深度）。
> 触发前可用 `/model` 切换。Skill 本身无法指定模型，这是当前的变通方案。

## 渲染模型（先读这一节）

`config-skills` v4 把 `.claude/settings.json` 视为**渲染产物**，不是手写文件：

```
单一数据源                                  渲染产物
─────────────                              ─────────────
presets/all.json  ──── /config-skills ────▶ <project>/.claude/settings.json
（用户级，跨机器共享）                       （项目级，每次 apply 全量覆盖）
   │ presets.<name>.skills   ──→ skillOverrides
   │ presets.<name>.plugins  ──→ enabledPlugins
   └ rules / detect          ──→ 智能默认值与项目类型探测
```

**关键约束：每次 apply 会全量覆盖 `skillOverrides` 与 `enabledPlugins` 两个字段。** 其他字段（`permissions` / `hooks` / `env` / `output_style` 等）保留不变。

### 双层 settings 模型

| 文件 | 谁负责 | git | 跨机器 | 用途 |
|------|--------|-----|--------|------|
| `.claude/settings.json` | **本 skill 渲染** | track | ✅ 共享 preset 选择 | "本项目走 X preset" 的事实 |
| `.claude/settings.local.json` | **用户手维护** | gitignore | ❌ 本机独有 | 单项目临时微调 |

**该改哪个？判断标准：**
- "项目永久要这样、其他机器也要" → 改 `presets/all.json` 对应 preset（跨机生效）
- "本机临时这样、不希望同步" → 改 `.claude/settings.local.json`（刻意不跨机器）
- 边界模糊 → 默认改 preset，更可持续

> ⚠️ **`.claude/settings.local.json` 是本机独有的**。如果你在公司 Mac 上把某 skill 调成 `on`，回家用 MacBook 打开同一项目时**不会自动继承**这条修改。

## 设计前提

Claude Code 的 skill 来自三个层级。本 skill **只覆盖其中两类**，按"项目目录是真相源"原则：

| 层级 | 路径 | 本 skill 处理 | 原因 |
|------|------|---------------|------|
| 项目级 skill | `<project>/.claude/skills/<name>/` | ❌ 不动 | 拷到项目就是"我要用"的承诺，走默认 ON |
| 项目级命令 | `<project>/.claude/commands/<ns>/` | ❌ 不动 | 暴露为 `ns:cmd` 形式，默认 ON，绝不写入 preset |
| 用户级 | `~/.claude/skills/<name>/` | ✅ 显式收紧 | "装了备用"，需 skillOverrides 主动控制 |
| Plugin 内 | plugin 包内置 | ✅ 用 `plugin:skill` 形式控制 | 装 plugin 顺带的，多数收紧 |

## 维护文件

```
presets/
├── all.json              # ★ 单一数据源（presets / rules / detect 三段）
│   ├── presets.<name>.{description, skills, plugins}
│   ├── rules[]           # skill / plugin 的智能默认值规则（含 scope）
│   └── detect[]          # 项目类型探测规则（files / extensions / package_deps）
├── catalog.json          # 已装 plugin / skill / command 清单（自动生成）
├── dependencies.json     # skill 调用依赖图 — caller → callees must be on
└── .archived/            # v3 旧 9 个 preset 文件归档（只读保留）

scripts/
├── 00_gen_catalog.py     # 重建 catalog.json（安装/卸载 plugin 后运行）
├── 01_scan.py            # Step 1: 扫描环境 + 探测项目类型
├── 02_health_check.py    # Step 2: 双维度 health-check（skill + plugin）
├── 02_sync.py            # Step 2 sync: 同步 missing/phantom 到 all.json
├── 025_enforce_deps.py   # Step 2.5: 依赖闭包，子 skill 强制升 on
├── 04_diff.py            # Step 4: 双维度 diff（skill + plugin）+ 幂等检查
├── 06_apply.py           # Step 6: 备份 + 渲染（支持 --dry-run）
└── .archived/migrate_v3_to_v4.py  # 一次性迁移脚本（已用过，归档保留）
```

> 定义变量 `SCRIPTS=~/.claude/skills/laodao-skills/config-skills/scripts`，下文所有脚本引用均使用此路径。

**依赖原则**：`user-invocable-only` 可能阻止 Skill tool 的程序化调用。因此只要 skill A 的任意代码路径会调用 skill B，无论是否必须，B 都必须是 `on`。`dependencies.json` 记录所有已知调用关系，Step 2.5 自动执行传递闭包。新增依赖时只需编辑 `dependencies.json`。

## 4 套 Preset 简介

| Preset | 适用场景 | 探测特征文件 |
|--------|----------|-------------|
| `content-creation` | 写文章、博客、做封面/配图、SDD | `hugo.toml/yaml` |
| `go-dev` | Go 后端、CLI 项目 | `go.mod` |
| `embedded-dev` | 嵌入式 C/MCU 固件 | `CMakeLists.txt` 或 `.c/.h` |
| `web-dev` | 前端、全栈、博客 QA | `package.json` + react/vue/next/svelte |

四套共享的"基础 ON"：superpowers 核心入口、git commit 类、remember、OpenSpec/SDD 全套。

## 工作流

> **设计原则**：先告知 → 扫描 → 用户确认 → 备份 → 原子写。**绝不**跳过备份/确认直接覆盖。

### Step 0: 运行告知（**首次进入流程时必读给用户**）

进入流程前，AI 必须明确告诉用户以下 4 件事：

1. **将备份**当前 `.claude/settings.json` 至 `.bak.YYYYMMDD-HHMMSS`（保留最近 3 份）
2. **将全量覆盖** `skillOverrides` 与 `enabledPlugins` 两个字段；其他字段（`permissions` / `hooks` / `env` 等）**保持不变**
3. 如已存在临时项目级微调，请写入 `.claude/settings.local.json`（本 skill 不会触碰它，且已被 gitignore）
4. settings.json 不存在时改为告知"将创建新的 settings.json"

### Step 1: 扫描环境 + 探测项目类型

```bash
python3 $SCRIPTS/01_scan.py
```

输出：已装 plugin 数（含前 5 个名）、用户级 skill 数、项目级 skill 数（只统计，不进 skillOverrides）、探测到的 preset 类型、settings.json 现状。

### Step 2: 双维度健康检查 + 自动同步

扫描 4 个 preset 的 keys，对比真相源（用户级 skill + catalog plugin_skills + installed_plugins）：
- **missing**：真相源有但 4 个 preset 全都未列 → 4 个 preset 都加，值由智能规则推断
- **phantom**：preset 列了但真相源找不到 → 4 个 preset 都删

```bash
python3 $SCRIPTS/02_health_check.py
```

**如果 STATUS: needs_sync** → 用 AskUserQuestion 询问：

```python
{
  "question": "同步 preset？将加 N 项、删 M 项（含 skill + plugin 两个维度）",
  "header": "preset 同步",
  "multiSelect": False,
  "options": [
    {"label": "自动同步（推荐）", "description": "改 all.json：missing 加默认值，phantom 删除"},
    {"label": "跳过", "description": "保持 preset 不变，继续后续流程"}
  ]
}
```

**如果用户选自动同步**，从 `02_health_check.py` 输出中提取 4 个 JSON 行，然后：

```bash
python3 $SCRIPTS/02_sync.py '<MISSING_SKILLS>' '<PHANTOM_SKILLS>' '<MISSING_PLUGINS>' '<PHANTOM_PLUGINS>'
```

**智能规则**：v3 的 14 条 skill RULES + 8 条 plugin RULES 全部存放在 `presets/all.json.rules`。新增/修改规则只需编辑 JSON，**无需改 Python**。

### Step 2.5: 依赖校验 — 子 skill 强制升 `on`

```bash
python3 $SCRIPTS/025_enforce_deps.py
```

读取 `presets/dependencies.json`，对每个 preset 做传递闭包：凡是值为 `on`/`user-invocable-only` 的 skill，其 `calls` 列表里的子 skill 全部强制升为 `on`。

### Step 3: 检查 settings.json

如果 Step 1 显示 settings.json 不存在：

```bash
mkdir -p .claude && echo '{}' > .claude/settings.json
```

### Step 4: 询问用户选 preset

用 AskUserQuestion，`header="工作模式"`：

- **如果 Step 1 探测到了 preset**：把探测出的 preset 放**第一位**并标"（推荐 - 检测到 X）"
- **如果未探测**：4 个 preset 按 content/go/embedded/web 顺序

```python
# 示例（探测到 go-dev 时）
{
  "question": "选哪套 preset？",
  "header": "工作模式",
  "multiSelect": False,
  "options": [
    {"label": "go-dev",            "description": "（推荐 - 检测到 go.mod）Go 后端/CLI"},
    {"label": "content-creation",  "description": "内容/博客/设计"},
    {"label": "embedded-dev",      "description": "嵌入式 C/MCU"},
    {"label": "web-dev",           "description": "前端/全栈"}
  ]
}
```

### Step 5: 双维度 Diff + 幂等检查

```bash
python3 $SCRIPTS/04_diff.py <PRESET>
```

输出包含 **Skill 变更** 与 **Plugin 变更** 两节，按 ON / user-invocable-only / off 三类汇总 skill 数，按 enable / disable 汇总 plugin 数。

**如果 STATUS: already_up_to_date**（双维度均无变更）→ 直接结束，告知"已是最新状态"。

### Step 6: 展示 Diff + 用户确认

用 AskUserQuestion：

```python
{
  "question": f"应用 {PRESET} preset？将变更 N 项 skill + M 项 plugin",
  "header": "应用变更",
  "multiSelect": False,
  "options": [
    {"label": "确认应用", "description": "备份当前 settings.json 后渲染新配置"},
    {"label": "取消",     "description": "什么都不做"}
  ]
}
```

如果用户选"取消"，输出"已取消"并结束。

### Step 7: 备份 + 原子渲染

```bash
python3 $SCRIPTS/06_apply.py <PRESET>
# 或预览（不写文件）：
python3 $SCRIPTS/06_apply.py --dry-run <PRESET>
```

只覆盖 `skillOverrides` 与 `enabledPlugins`：`permissions` / `hooks` / `env` / `output_style` 等其他字段全部保留。如检测到 plugin↔plugin:skill 矛盾态（plugin 被禁但其 skill = on），输出 warning 但不阻断。

### Step 8: 引导修改 + 重载提示

**修改某项 skill/plugin**：
- **跨机器永久** → 编辑 `~/.claude/skills/laodao-skills/config-skills/presets/all.json`，重跑 `/config-skills` 应用
- **本机临时** → 编辑 `.claude/settings.local.json`（不跨机器、不被覆盖）

**回滚**：最近 3 份备份在 `.claude/settings.json.bak.YYYYMMDD-HHMMSS`：
```bash
cp .claude/settings.json.bak.YYYYMMDD-HHMMSS .claude/settings.json
```

**生效**：必须执行 `/reload-plugins` 才生效。

## 边界情况

### 用户手改了 settings.json
**会被覆盖**。下次 `/config-skills` 重新渲染时，手改内容全部消失（仅 `skillOverrides` 与 `enabledPlugins` 字段）。
- 想跨机器永久 → 改 `all.json`
- 想本机临时 → 改 `settings.local.json`（永远不被本 skill 触碰）

### 用户不要 4 个 preset 中任何一个
让用户选 "Other"（AskUserQuestion 兜底）→ 引导直接改 `.claude/settings.local.json`。

### 项目里没 .claude/settings.json
Step 3 处理：自动创建空 `{}`。

### 探测出错（如 package.json 损坏）
`01_scan.py` 的 try/except 已兜底，回到"未匹配"分支让用户全自由选。

### 用户已有重要自定义 skillOverrides
v4 设计的核心就是这件事——把临时定制写到 `settings.local.json`，与 preset 渲染层物理隔离。`06_apply.py` 同时保留 `.bak.YYYYMMDD-HHMMSS` 备份兜底（保留最近 3 份）。

### 跨项目复用 preset
本 skill 装在用户级（实体 `~/.claude/skills/laodao-skills/config-skills/`，symlink 接入 `~/.claude/skills/config-skills/`），所有项目都能 `/config-skills`。`presets/all.json` 是单点真相源。

### 添加新 preset（如 python-dev）
**完全不动 Python**，仅编辑 JSON + 文档：

1. **编辑 `presets/all.json`**：
   - `presets` 顶层加 `"python-dev": { "description": "...", "skills": {}, "plugins": {} }`（空也行，下次跑 `/config-skills` 会被 health-check 自动补全）
   - `rules` 数组的每条规则的 `values` 都加上 `"python-dev"` 列
   - `detect` 数组加 `{ "preset": "python-dev", "files": ["pyproject.toml", "requirements.txt"] }`
2. **改本 SKILL.md**：
   - "4 套 Preset 简介"表格加一行
   - Step 4 的 AskUserQuestion 选项加一项
3. **跑 `/config-skills`**：health-check 自动给新 preset 补齐所有 skill/plugin 默认值

### 添加新 skill 依赖
编辑 `presets/dependencies.json` → `dependencies` 节添加条目 → 下次 `/config-skills` 时 Step 2.5 自动生效。

### 安装/卸载 plugin 后
跑一次 `python3 $SCRIPTS/00_gen_catalog.py` 重建 `catalog.json`（含顶层 `plugins` 字段），再跑 `/config-skills` 让 health-check 把新 plugin 补进 4 个 preset 的 `plugins` 段。
