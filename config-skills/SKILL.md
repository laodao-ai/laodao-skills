---
name: config-skills
description: >
  扫描已安装的 plugin 和用户级 skill，按工作场景一键配置项目级 .claude/settings.json 的 skillOverrides 字段。
  内置 4 套 preset：content-creation（内容/博客/设计）、go-dev（Go 后端/CLI）、
  embedded-dev（嵌入式 C/MCU）、web-dev（前端/全栈）。

  当用户说"配置 skill"、"配 settings.json"、"调 skillOverrides"、"切换 skill 模式"、
  "切到内容/Go/嵌入式/Web 模式"、"加载 preset"、"换工作模式"、"配置 plugin"、
  "skill 太多了清理一下"、"新项目第一次配 settings"、"批量启用禁用 skill"、
  "config-skills"，或使用 /config-skills 时**必须**触发此 skill。

  即使用户没明确说"preset"或"模式"，只要表达"想调整一组 skill 的开关"、"按场景配置"、
  "skill 加载策略"、"上下文太满想精简 skill"，也应主动触发本 skill 询问是否套用 preset。
---

# Config Skills - 按场景一键配置 plugin/skill

> **推荐模型**：Haiku（流程明确的执行类任务，不需要 Opus 的推理深度）。
> 触发前可用 `/model` 切换。Skill 本身无法指定模型，这是当前的变通方案。

## 设计前提（先读）

Claude Code 的 skill 来自三个层级。本 skill **只覆盖其中两类**，按"项目目录是真相源"原则：

| 层级 | 路径 | 本 skill 处理 | 原因 |
|------|------|---------------|------|
| 项目级 | `<project>/.claude/skills/<name>/` | ❌ **不动** | 拷到项目就是"我要用"的承诺，走默认 ON |
| 用户级 | `~/.claude/skills/<name>/` | ✅ 显式收紧 | "装了备用"，需 skillOverrides 主动控制 |
| Plugin 内 | plugin 包内置 | ✅ 用 `plugin:skill` 形式控制 | 装 plugin 顺带的，多数收紧 |

**Why**：项目级 skill 是用户主动拷到该项目目录的，本身就是"在这个项目里用它"的承诺。在 settings.json 里再写 `"on"` 是冗余、写 `"user-invocable-only"` 反而违背刚才的安装动作。

## 4 套 Preset 简介

| Preset | 适用场景 | 探测特征文件 | ON 数量 |
|--------|----------|-------------|---------|
| `content-creation` | 写文章、博客、做封面/配图、SDD | `hugo.toml/yaml` | ~21 |
| `go-dev` | Go 后端、CLI 项目 | `go.mod` | ~24 |
| `embedded-dev` | 嵌入式 C/MCU 固件 | `CMakeLists.txt` 或 `.c/.h` | ~28 |
| `web-dev` | 前端、全栈、博客 QA | `package.json` + react/vue/next/svelte | ~35 |

四套共享的"基础 ON"：superpowers 核心入口、git commit 类、remember、OpenSpec/SDD 全套。

## 工作流（v2：含安全三件套 + 自动探测）

> **设计原则**：先扫描 → 用户确认 → 备份 → 原子写。**绝不**跳过备份/确认直接覆盖。

### Step 1: 扫描环境 + 探测项目类型

一次性收集：plugin 数量、用户级 skill、项目类型推断、settings.json 现状。

```bash
python3 << 'PYEOF'
import json, os

# 1. Plugin 真相源
with open(os.path.expanduser('~/.claude/plugins/installed_plugins.json')) as f:
    plugin_data = json.load(f)
total_plugins = len(plugin_data.get('plugins', {}))

# 2. 用户级 skill（含 symlink）
local_dir = os.path.expanduser('~/.claude/skills/')
local_skills = sorted([d for d in os.listdir(local_dir)
                       if os.path.isdir(os.path.join(local_dir, d))])

# 3. 项目级 skill（仅统计、不进 skillOverrides）
project_skills = []
if os.path.isdir('.claude/skills/'):
    project_skills = sorted([d for d in os.listdir('.claude/skills/')
                             if os.path.isdir(os.path.join('.claude/skills/', d))])

# 4. 项目类型探测
files = os.listdir('.')
detected, reason = None, ''
if 'go.mod' in files:
    detected, reason = 'go-dev', '检测到 go.mod'
elif 'CMakeLists.txt' in files or any(f.endswith(('.c', '.h')) for f in files):
    detected, reason = 'embedded-dev', '检测到 CMakeLists.txt 或 .c/.h 文件'
elif 'hugo.toml' in files or 'hugo.yaml' in files:
    detected, reason = 'content-creation', '检测到 hugo.toml/yaml'
elif 'package.json' in files:
    try:
        pkg = json.load(open('package.json'))
        deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}
        if any(k in deps for k in ['react', 'vue', 'next', 'nuxt', 'svelte', '@vue', '@react']):
            detected, reason = 'web-dev', '检测到 package.json 含前端框架'
    except: pass

# 5. settings.json 现状
settings_exists = os.path.isfile('.claude/settings.json')
cur_count = 0
if settings_exists:
    try:
        cur = json.load(open('.claude/settings.json'))
        cur_count = len(cur.get('skillOverrides', {}))
    except: pass

print(f'已装 plugin: {total_plugins}')
print(f'用户级 skill: {len(local_skills)}')
print(f'项目级 skill: {len(project_skills)}（走默认 ON）')
print(f'探测项目类型: {detected or "未匹配"}（{reason or "请手动选"}）')
print(f'settings.json: {"存在，含 " + str(cur_count) + " 条 skillOverrides" if settings_exists else "不存在"}')
PYEOF
```

### Step 2: 检查 settings.json

如果 Step 1 显示 settings.json 不存在：

```bash
mkdir -p .claude && echo '{}' > .claude/settings.json
```

### Step 3: 询问用户选 preset（默认推荐探测结果）

用 AskUserQuestion，`header="工作模式"`：

- **如果 Step 1 探测到了 preset**：把探测出的 preset 放**第一位**并标"（推荐 - 检测到 X）"，其他 3 个按原顺序排第 2-4 位
- **如果未探测**：4 个 preset 按 content/go/embedded/web 顺序

```python
# AskUserQuestion 选项示例（探测到 go-dev 时）
{
  "question": "选哪套 preset？",
  "header": "工作模式",
  "multiSelect": False,
  "options": [
    {"label": "go-dev",            "description": "（推荐 - 检测到 go.mod）Go 后端/CLI（约 24 ON）"},
    {"label": "content-creation",  "description": "内容/博客/设计（约 21 ON）"},
    {"label": "embedded-dev",      "description": "嵌入式 C/MCU（约 28 ON）"},
    {"label": "web-dev",           "description": "前端/全栈（约 35 ON）"}
  ]
}
```

### Step 4: 校验 + 算 Diff + 幂等检查

```bash
python3 << 'PYEOF'
import json, os
from collections import Counter

PRESET = '<USER_CHOICE>'  # 替换为用户选的
preset_path = os.path.expanduser(f'~/.claude/skills/config-skills/presets/{PRESET}.json')
with open(preset_path) as f:
    preset = json.load(f)

# 1. Skill ID 校验：preset 里某些 skill 在本地不存在 → phantom（写进去也无用）
local_dir = os.path.expanduser('~/.claude/skills/')
existing_local = set(os.listdir(local_dir)) if os.path.isdir(local_dir) else set()

phantom = []
clean = {}
for k, v in preset.items():
    # plugin:skill 格式由 plugin 提供，不校验
    # bare name 必须在 ~/.claude/skills/ 存在
    if ':' in k or k in existing_local:
        clean[k] = v
    else:
        phantom.append(k)

# 2. 算 Diff（preset 里有但 cur 里没有的，cur 视作默认 'on'）
cur = {}
if os.path.isfile('.claude/settings.json'):
    cur = json.load(open('.claude/settings.json')).get('skillOverrides', {})

will_change = {k: (cur.get(k, 'on'), v) for k, v in clean.items()
               if cur.get(k, 'on') != v}

# 3. 幂等检查
if not will_change:
    print('STATUS: already_up_to_date')
    print(f'当前 skillOverrides 已与 {PRESET} preset 一致，无需变更。')
    if phantom:
        print(f'⚠️  仍有 {len(phantom)} 项 phantom skill（preset 列了但本地没装）')
else:
    print('STATUS: needs_update')
    print(f'\n📊 Diff 摘要（{PRESET}）')
    print(f'   将变更 skill 数: {len(will_change)}')
    by_target = Counter(target for _, target in will_change.values())
    for t in ['on', 'user-invocable-only', 'off']:
        if t in by_target:
            print(f'   → {t}: {by_target[t]} 项')

    if phantom:
        print(f'\n⚠️  本地未找到 skill（已跳过 {len(phantom)} 项）:')
        for p in phantom[:10]:
            print(f'   - {p}')
        if len(phantom) > 10: print(f'   ... 及其余 {len(phantom)-10} 项')

    # 详细变更（最多 20 项）
    print(f'\n📋 详细变更（前 20 项）:')
    for k, (old, new) in list(will_change.items())[:20]:
        print(f'   {k:50} {old:25} → {new}')
    if len(will_change) > 20:
        print(f'   ... 及其余 {len(will_change)-20} 项')
PYEOF
```

**如果 STATUS: already_up_to_date** → 直接结束（跳过 Step 5-6），告知用户"已是最新状态"。

### Step 5: 展示 Diff + 用户确认

用 AskUserQuestion，2 选 1：

```python
{
  "question": f"应用 {PRESET} preset？将变更 N 项 skill",
  "header": "应用变更",
  "multiSelect": False,
  "options": [
    {"label": "确认应用", "description": "备份当前 settings.json 后写入新配置"},
    {"label": "取消",     "description": "什么都不做"}
  ]
}
```

如果用户选"取消"，输出"已取消"并结束。

### Step 6: 备份 + 原子写回

```bash
python3 << 'PYEOF'
import json, os, shutil, datetime, glob

PRESET = '<USER_CHOICE>'
settings_path = '.claude/settings.json'

# 1. 时间戳备份，保留最近 3 份
ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
bak = settings_path + f'.bak.{ts}'
shutil.copy2(settings_path, bak)
for old in sorted(glob.glob(settings_path + '.bak.*'))[:-3]:
    os.remove(old)

# 2. 读 settings.json + preset
with open(settings_path) as f:
    cur = json.load(f)
with open(os.path.expanduser(f'~/.claude/skills/config-skills/presets/{PRESET}.json')) as f:
    preset = json.load(f)

# 3. 只覆盖 skillOverrides，其他字段不动
cur['skillOverrides'] = preset

# 4. 原子写回（tmp + replace 防写一半崩溃）
tmp = settings_path + '.tmp'
with open(tmp, 'w') as f:
    json.dump(cur, f, indent=2, ensure_ascii=False)
    f.write('\n')
os.replace(tmp, settings_path)

# 5. 统计
from collections import Counter
c = Counter(preset.values())
print(f'✅ 已应用 {PRESET}')
print(f'   备份: {bak}')
print(f'   ON: {c["on"]} | user-invocable-only: {c["user-invocable-only"]} | off: {c["off"]}')
PYEOF
```

**只动 `skillOverrides`**：`enabledPlugins` / `permissions` / `hooks` / `env` 等其他字段全部保留。

### Step 7: 展示分类清单

按用户所选 preset 输出（见下方"各 Preset 概览"章节）。

### Step 8: 引导修改 + 重载提示

告诉用户：

**修改某个 skill 的状态**：编辑 `.claude/settings.json`，找到对应 skill，改值
- `"on"`：默认加载，AI 主动建议
- `"off"`：完全屏蔽
- `"user-invocable-only"`：仅 `/skill-name` 触发

**修改 preset 自身**：编辑 `~/.claude/skills/config-skills/presets/<name>.json`，重跑 `/config-skills` 应用。

**回滚**：最近 3 份备份在 `.claude/settings.json.bak.YYYYMMDD-HHMMSS`：
```bash
cp .claude/settings.json.bak.YYYYMMDD-HHMMSS .claude/settings.json
```

**生效**：必须执行 `/reload-plugins` 才生效。

---

## 各 Preset 概览（Step 7 输出模板）

### content-creation 概览（约 21 ON）

**主动加载**
- `superpowers`: using-superpowers / brainstorming / verification-before-completion
- OpenSpec: `opsx:*` × 11 + `opsx-maintain` / `opsx-roadmap-planner` / `project-activate`
- git: `commit-commands:commit` / `commit-message` / `tag`
- 其他: `remember:remember` / `laodao-skills`

**手动 /xxx 触发**：设计 / SEO / 浏览器 / 调研 / 转换 / gstack 偶用

**已屏蔽**：代码工程类 / 嵌入式 / 设计重型

### go-dev 概览（约 24 ON）

= content-creation + 增 3：
- `code-review:code-review` / `feature-dev:feature-dev` / `superpowers:systematic-debugging`

**手动 /xxx 触发**：TDD / 代码 review 协作 / pr-review-toolkit / gstack code 类

**已屏蔽**：前端/UI / SEO 全套 / 内容研究/转换 / 嵌入式

### embedded-dev 概览（约 28 ON）

= go-dev + 增 4：
- `embedded-test-sop` / `embedded-test-sop-workspace` / `embedded-lint`
- `superpowers:test-driven-development`（嵌入式 TDD 提级到 ON）

### web-dev 概览（约 35 ON）

= go-dev + 增 11：
- 前端: `frontend-design` / `ui-ux-pro-max`
- 浏览器: `chrome-devtools-mcp:*` × 6
- QA: `qa` / `qa-only` / `browse`

---

## 边界情况

### 用户不要 4 个 preset 中任何一个
让他选 "Other"（AskUserQuestion 兜底）→ 引导直接改 `.claude/settings.json`。

### 项目里没 .claude/settings.json
Step 2 已处理：自动创建空 `{}`。

### 探测出错（如 package.json 损坏）
Step 1 try/except 已兜底，回到"未匹配"分支让用户全自由选。

### 用户已有重要自定义 skillOverrides
Step 6 自动备份到 `.bak.YYYYMMDD-HHMMSS`，保留最近 3 份。

### 跨项目复用 preset
本 skill 装在用户级（实体 `~/.claude/skills/laodao-skills/config-skills/`，symlink 接入 `~/.claude/skills/config-skills/`），所有项目都能 `/config-skills`。

### 添加新 preset
在 `~/.claude/skills/laodao-skills/config-skills/presets/` 加 `<new-name>.json`，在本 SKILL.md Step 3 的 AskUserQuestion 加选项 + Step 1 探测规则。

---

## 致敬：从 project-activate 借鉴的设计

本 skill v2 大量借鉴 `project-activate` 的设计：

- **自动探测**（Step 1）：源自 project-activate 的特征文件检测
- **Diff 计算 + 用户确认**（Step 4-5）：源自 project-activate 的"展示变更，确认/取消/调整"
- **备份机制**（Step 6）：`.bak.timestamp` + 保留最近 3 份
- **原子写回**（Step 6）：`tmp + os.replace`
- **Plugin/Skill ID 校验**（Step 4）：跳过 phantom

差异：本 skill 只管 `skillOverrides`（按用户决策），project-activate 管 `enabledPlugins` + MCP + skills 提示。
