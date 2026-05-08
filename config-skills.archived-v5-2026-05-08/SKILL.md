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

# Config Skills v5 — 语义推荐器 + 渲染模型

> **推荐模型**：Sonnet（v5 的 LLM 推荐流程需要语义判断，比 v4 的纯执行复杂）。
> 触发前可用 `/model` 切换。日常 `/config-skills`（无新 plugin 时）仍可走 Haiku；
> 跑 LLM 推荐（`--refresh` 或新装 plugin）时建议 Sonnet。

## 渲染模型（先读这一节）

`config-skills` v5 把 `.claude/settings.json` 视为**渲染产物**，不是手写文件：

```
单一数据源                                                 渲染产物
─────────────                                              ─────────────
catalog.json (含 description)  ───┐
                                  │  ┌── 03_llm_recommend.py ──┐
presets/all.json                  ├──┤  emit-prompt + apply    │
  │ presets.<name>.description ──┘  └── (主对话 LLM 当推荐器) ──┘
  │ presets.<name>.skills          ─────────────────────────────▶ skillOverrides
  │ presets.<name>.plugins         ─────────────────────────────▶ enabledPlugins
  │ presets.<name>._baseline   ──→ 手改自动识别 + prompt_hash 防失效
  └ rules (1 条 wildcard)      ──→ LLM 未推荐时的 fallback
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
├── all.json                # ★ 单一数据源
│   ├── presets.<name>.description           # 场景说明（中文，给 LLM 看）
│   ├── presets.<name>.skills                # skill 三态（on/u-i-o/off）
│   ├── presets.<name>.plugins               # plugin 二态（true/false）
│   ├── presets.<name>._baseline             # 隐藏镜像：识别手改 + prompt_hash
│   ├── rules[]                              # 1 条 wildcard fallback（v5 已瘦身）
│   └── detect[]                             # 项目类型探测规则
├── catalog.json            # plugin / skill 清单（自动生成）
│   ├── installed_plugins / user_skills / plugin_skills / plugins  # 旧字段（兼容）
│   ├── skills_enriched[]                    # ★ 含 description（推荐器输入）
│   └── plugins_enriched[]                   # ★ 含 author + description
├── dependencies.json       # skill 调用依赖图 — caller → callees must be on
└── .archived/
    ├── v4-rules.json                        # 22 条 v4 关键字规则归档（回滚用）
    └── all.json.bak.migration-YYYYMMDD      # v4→v5 迁移备份

scripts/
├── 00_gen_catalog.py       # 重建 catalog.json（装/卸 plugin 后运行）
├── 01_scan.py              # Step 1: 扫描环境 + 探测项目类型
├── 02_health_check.py      # Step 2: 健康检查（preset_in_sync / needs_sync / needs_llm_recommend）
├── 02_sync.py              # Step 2 sync: 同步 missing/phantom（wildcard fallback）
├── 025_enforce_deps.py     # Step 2.5: 依赖闭包
├── 03_llm_recommend.py     # ★ Step 3 (v5): LLM 推荐器（emit-prompt + apply）
├── 04_diff.py              # Step 4: 双维度 diff
├── 06_apply.py             # Step 6: 备份 + 渲染
├── templates/
│   └── recommend.txt       # ★ LLM 推荐 prompt 模板（修改触发 prompt_hash 失效）
└── .archived/
    ├── migrate_v3_to_v4.py
    └── migrate_v4_to_semantic.py            # v4→v5 迁移（已跑过，归档）
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

### Step 2.7: LLM 推荐（v5 新增，仅在 needs_llm_recommend 时跑）

**触发条件**：health-check 输出 `STATUS: needs_llm_recommend` 或 `needs_sync_then_llm_recommend`。
- `needs_sync_then_llm_recommend`：先跑 02_sync 给 missing 项填 wildcard fallback，再跑 LLM 推荐升级
- `needs_llm_recommend`：直接跑 LLM 推荐（catalog 多新项 / preset 子树空）

**流程：**

```bash
# 1. 脚本生成 prompt（不调 API）
python3 $SCRIPTS/03_llm_recommend.py --preset <PRESET> --mode missing --emit-prompt > /tmp/reco-prompt.txt

# 2. Claude 主对话读 prompt → 输出严格 JSON 到 /tmp/reco.json
#    （由本对话的 LLM 当推荐器，不调外部 API）

# 3. 脚本校验 + 自动纠正 + 写回
python3 $SCRIPTS/03_llm_recommend.py --preset <PRESET> --apply /tmp/reco.json
```

**`--apply` 自动做的事：**
- 严格 schema 校验（值域、字段名、preset 匹配）
- 跨字段一致性纠正（`plugin=False` 时其下属 skill 强制 off）
- 依赖闭包（`dependencies.json` 强升 callee 到 on）
- 写回 all.json + 刷新 `_baseline` + 写入当前 prompt_hash

**模式说明：**
- `--mode missing`：仅推荐 catalog 有但 preset 没列的新项（**默认**）
- `--mode all`：全表重算（`--refresh` 走这个，见下文）

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

## --refresh 工作流（v5 新增）

`/config-skills --refresh <preset>` 让 LLM 全表重算该 preset，差异化处理手改项与 LLM 自动管理项。

**何时跑 `--refresh`：**
- 改了 preset description（场景定义变了）
- 觉得当前 preset 推荐质量不够好，想让 LLM 重新评估
- prompt 模板调过（hash 不一致会自动检测）

**流程：**

1. **prompt_hash 一致性检查**
   ```bash
   python3 -c "import hashlib,json,os; \
     t=open(os.path.expanduser('~/.claude/skills/laodao-skills/config-skills/scripts/templates/recommend.txt'),'rb').read(); \
     a=json.load(open(os.path.expanduser('~/.claude/skills/laodao-skills/config-skills/presets/all.json'))); \
     print('prompt:', hashlib.sha256(t).hexdigest()[:12], 'baseline:', a['presets']['<PRESET>']['_baseline'].get('prompt_hash'))"
   ```
   两 hash 不一致时 → UI 提示"prompt 模板已演化，本次刷新视全表为 LLM 自动管理项"。

2. **生成 prompt（mode=all）**
   ```bash
   python3 $SCRIPTS/03_llm_recommend.py --preset <PRESET> --mode all --emit-prompt > /tmp/reco-prompt.txt
   ```

3. **Claude 主对话读 prompt → 输出 JSON 到 /tmp/reco-new.json**

4. **手改识别 + 逐项 yes/no 确认（在主对话内）**

   读 `all.json.presets.<PRESET>` 与新 JSON 对比 + `_baseline` 对比，给每项打标签：
   - `手改项`：当前值 ≠ `_baseline` 对应值 → **默认保留当前值**
   - `LLM 自动管理项`：当前值 == `_baseline` 对应值 → **默认接受新推荐**

   用 AskUserQuestion **分批询问，每批 ≤ 10 项**，区分两类用不同文案：

   ```python
   # 手改项 — 默认保留
   {"label": "保留我的手改 (foo: on)（默认）", "description": "..."}
   {"label": "接受 LLM 新推 (foo: u-i-o)", "description": "..."}
   {"label": "跳过", "description": "保留当前值"}

   # LLM 自动管理项 — 默认接受
   {"label": "接受 LLM 新推 (bar: off)（默认）", "description": "..."}
   {"label": "保留当前值 (bar: u-i-o)", "description": "..."}
   {"label": "跳过", "description": "保留当前值"}
   ```

5. **中断 = 整次丢弃**

   所有 yes/no 决定累积在内存中。任何中断（用户 Ctrl+C / 关闭对话 / AskUserQuestion 选 Other）都视为整次取消，**不创建中间状态文件**，下次 `--refresh` 从第一批重头开始。

6. **全部确认后一次写回**

   把累积的最终决定打成 JSON 喂给 `--apply`：
   ```bash
   python3 $SCRIPTS/03_llm_recommend.py --preset <PRESET> --apply /tmp/reco-final.json
   ```

   `--apply` 自动刷新 `_baseline` = LLM 推荐快照（不是用户确认后的最终值），保证下次 `--refresh` 仍能识别新一轮手改。

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

**v5 极简流程**（相比 v4 不再需要手填 4×N 表）：

1. **编辑 `presets/all.json`**：
   ```json
   "python-dev": {
     "description": "Python 后端 / 数据科学项目开发；常用 pytest / poetry / pyproject.toml；可能涉及 FastAPI / Django / Pandas / Jupyter Notebook；不主要做前端。",
     "skills": {},
     "plugins": {}
   }
   ```
   `skills` 与 `plugins` 留空 — health-check 会识别为 `empty preset`，触发 LLM 全表生成。
2. **可选**：`detect` 数组加项目类型探测（`pyproject.toml` / `requirements.txt`）。
3. **改本 SKILL.md**：Step 4 的 AskUserQuestion 选项加一项；"Preset 简介"表格加一行。
4. **跑 `/config-skills`**：选 python-dev → 自动跑 LLM 推荐 → 一次性给 200+ 项 skill 与 41 项 plugin 推荐值。

### 用户改 preset description 后（v5 新增）

**改 description 不会自动触发重算**（避免误触）。流程：

1. 改 `all.json.presets.<preset>.description`
2. 跑 `/config-skills` 时 health-check 会输出"💡 提示：description 已变，建议跑 --refresh"
3. 手动跑 `/config-skills --refresh <preset>` 让 LLM 按新场景重新推荐

### 用户改 preset skills/plugins 后（v5 新增）

`_baseline` 镜像**自动识别**手改：

- 改了某项 skill 值 → 下次 `--refresh` 时被识别为手改 → 默认保留你的修改
- 删了某项 → health-check 视为 missing，下次 `/config-skills` 用 fallback 或 LLM 推荐补回（你可再次确认）
- 没改的项 → 视为 LLM 自动管理项，`--refresh` 时默认接受新推荐

**无需手动打标签** — 镜像差异法自动透明工作。

### 添加新 skill 依赖
编辑 `presets/dependencies.json` → `dependencies` 节添加条目 → 下次 `/config-skills` 时 Step 2.5 自动生效。

### 安装/卸载 plugin 后
跑一次 `python3 $SCRIPTS/00_gen_catalog.py` 重建 `catalog.json`（含顶层 `plugins` 字段），再跑 `/config-skills` 让 health-check 把新 plugin 补进 4 个 preset 的 `plugins` 段。
