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

| Preset | 适用场景 | ON 数量（估）| 核心策略 |
|--------|----------|-------------|----------|
| `content-creation` | 写文章、博客、做封面/配图、SDD | ~21 | 关闭代码工程类，留 git/SDD/内容 |
| `go-dev` | Go 后端、CLI 项目 | ~24 | 开 code-review / feature-dev / debug |
| `embedded-dev` | 嵌入式 C/MCU 固件 | ~28 | 上加 embedded-lint / test-sop / TDD |
| `web-dev` | 前端、全栈、博客 QA | ~35 | 加 chrome-devtools / 前端 UI / QA |

四套共享的"基础 ON"：superpowers 核心入口、git commit 类、remember、OpenSpec/SDD 全套（`opsx:*`、`opsx-maintain` 等）。

## 工作流

### Step 1: 扫描环境

报告当前装了什么。**注意排除项目级 skill**（按设计前提）：

```bash
python3 << 'PYEOF'
import json, os

# Plugin 真相源
with open(os.path.expanduser('~/.claude/plugins/installed_plugins.json')) as f:
    plugin_data = json.load(f)
total_plugins = len(plugin_data.get('plugins', {}))

# 用户级 skill
local_skills_dir = os.path.expanduser('~/.claude/skills/')
local_skills = sorted([d for d in os.listdir(local_skills_dir)
                       if os.path.isdir(os.path.join(local_skills_dir, d))])

# 项目级 skill（仅统计、不进 skillOverrides）
project_skills_dir = '.claude/skills/'
project_skills = []
if os.path.isdir(project_skills_dir):
    project_skills = sorted([d for d in os.listdir(project_skills_dir)
                             if os.path.isdir(os.path.join(project_skills_dir, d))])

print(f'已装 plugin: {total_plugins}')
print(f'用户级 skill: {len(local_skills)}')
print(f'项目级 skill: {len(project_skills)}（走默认 ON，不进 settings.json）')
PYEOF
```

### Step 2: 检查项目 settings.json

```bash
if [ -f .claude/settings.json ]; then
  echo "✅ settings.json 已存在"
else
  echo "⚠️  settings.json 不存在，需先创建"
fi
```

如不存在，提示用户先建 → 帮其创建空 `{}`：
```bash
mkdir -p .claude && echo '{}' > .claude/settings.json
```

### Step 3: 询问用户选 preset

用 AskUserQuestion 工具，`header="工作模式"`，提供 4 选项：

```python
{
  "question": "选哪套 preset？",
  "header": "工作模式",
  "multiSelect": False,
  "options": [
    {"label": "content-creation", "description": "内容/博客/设计场景，关闭代码工程类（约 21 ON）"},
    {"label": "go-dev",           "description": "Go 后端/CLI，启用 code-review/debug（约 24 ON）"},
    {"label": "embedded-dev",     "description": "嵌入式 C/MCU，启用 embedded-lint/test-sop（约 28 ON）"},
    {"label": "web-dev",          "description": "前端/全栈，启用 chrome-devtools/UI（约 35 ON）"}
  ]
}
```

### Step 4: 应用 preset

```python
import json, os
from collections import Counter

preset_name = "<USER_CHOICE>"  # 替换为用户选择
preset_path = os.path.expanduser(f'~/.claude/skills/config-skills/presets/{preset_name}.json')
project_settings = '.claude/settings.json'

# 读现有 settings.json（保留 enabledPlugins/permissions/hooks 等）
with open(project_settings) as f:
    cur = json.load(f)

# 读 preset
with open(preset_path) as f:
    preset = json.load(f)

# 只覆盖 skillOverrides，其他字段不动
cur['skillOverrides'] = preset

# 写回
with open(project_settings, 'w') as f:
    json.dump(cur, f, indent=2, ensure_ascii=False)
    f.write('\n')

# 统计
c = Counter(preset.values())
print(f'✅ 已应用 {preset_name}')
print(f'   ON: {c["on"]} | user-invocable-only: {c["user-invocable-only"]} | off: {c["off"]}')
```

**只动 `skillOverrides`**：`enabledPlugins`、`permissions`、`hooks`、`env` 等其他字段全部保留。

### Step 5: 展示分类清单

按用户所选 preset 输出（见下方"各 Preset 概览"章节）。

### Step 6: 引导修改

告诉用户：

**修改某个 skill 的状态**
编辑 `.claude/settings.json`，找到对应 skill，改值：
- `"on"`：默认加载，AI 主动建议
- `"off"`：完全屏蔽，AI 不知道存在
- `"user-invocable-only"`：仅你 `/skill-name` 触发

**修改 preset 自身**
编辑 `~/.claude/skills/config-skills/presets/<name>.json`，重跑 `/config-skills` 应用。

**添加新 preset**
在 `presets/` 加 `<new-name>.json`，在本 SKILL.md Step 3 的 AskUserQuestion 加选项。

**生效**：必须执行 `/reload-plugins` 才生效。

---

## 各 Preset 概览（Step 5 输出模板）

### content-creation 概览（约 21 ON）

**主动加载**
- `superpowers`: using-superpowers / brainstorming / verification-before-completion（流程入口 + 创意 + 验证）
- OpenSpec: `opsx:*` × 11（SDD 完整流程）+ `opsx-maintain` / `opsx-roadmap-planner` / `project-activate`
- git: `commit-commands:commit` / `commit-message` / `tag`
- 其他: `remember:remember` / `laodao-skills`

**手动 /xxx 触发**
- 设计: frontend-design / ui-ux-pro-max / design-review
- SEO: `searchfit-seo:*` × 17（需要时 `/seo-audit` 等）
- 浏览器: `chrome-devtools-mcp:*` × 6 / playwright
- 调研: bilibili / youtube / x / zhihu-research
- 转换: pdf2md / docx2md / xlsx2md / make-pdf
- gstack 偶用: codex / qa / qa-only / browse / ship

**已屏蔽**
- 代码工程: code-review / feature-dev / debug / TDD / pr-review-toolkit
- 嵌入式: embedded-* / goframe-v2
- 设计重型: design-html / design-shotgun / design-consultation
- 极少用: cso / learn / find-skills / careful / freeze 等

### go-dev 概览（约 24 ON）

**主动加载** = content-creation 的 21 + 增 3
- `code-review:code-review`、`feature-dev:feature-dev`（PR 审查 + 功能开发）
- `superpowers:systematic-debugging`（系统化调试）

**手动 /xxx 触发**
- TDD: `superpowers:test-driven-development`
- 代码 review 协作: requesting/receiving-code-review
- 并行/隔离: subagent-driven / dispatching-parallel / using-git-worktrees / finishing-a-development-branch
- pr-review-toolkit:review-pr
- gstack: codex / qa / browse / ship / health / investigate
- GoFrame: goframe-v2（仅当用 GoFrame）

**已屏蔽**
- 前端/UI: frontend-design / ui-ux-pro-max / `chrome-devtools-mcp:*` × 6
- SEO 全套（17 个）
- 内容研究/转换
- 设计重型 / design-review
- 嵌入式

### embedded-dev 概览（约 28 ON）

**主动加载** = go-dev 的 24 + 增 4
- `embedded-test-sop`（手动测试 SOP 文档生成）
- `embedded-test-sop-workspace`
- `embedded-lint`（C 静态分析：cppcheck / clang-tidy）
- `superpowers:test-driven-development`（嵌入式 TDD 提级到 ON）

**手动 /xxx 触发**
- pr-review-toolkit:review-pr
- 代码 review 协作: requesting/receiving-code-review
- gstack: codex / health / investigate

**已屏蔽**
- 同 go-dev，并加 `goframe-v2` off（嵌入式 C 不用 Go 框架）
- 前端/UI/SEO/内容研究/转换/设计

### web-dev 概览（约 35 ON）

**主动加载** = go-dev 的 24 + 增 11
- 前端核心: `frontend-design`、`ui-ux-pro-max`
- 浏览器: `chrome-devtools-mcp:*` × 6（troubleshooting / LCP / CLI / memory-leak / chrome-devtools / a11y）
- QA 流: `qa`、`qa-only`、`browse`

**手动 /xxx 触发**
- SEO: `searchfit-seo:*` × 17（按需 `/seo-audit` 等）
- 设计: design-review / plan-design-review / design-html / design-shotgun
- TDD: `superpowers:test-driven-development`
- 代码 review 协作

**已屏蔽**
- 嵌入式: embedded-* / goframe-v2
- 内容研究/转换

---

## 边界情况

### 用户不要 4 个 preset 中任何一个
让他选 "Other"（AskUserQuestion 的兜底选项）→ 引导直接改 `.claude/settings.json`，参考各 preset 文件做差异调整。

### 项目里没 .claude/settings.json
先创建空文件：`mkdir -p .claude && echo '{}' > .claude/settings.json`，然后进 Step 4。

### preset 文件不存在
报错并列出 `presets/` 实际有哪些 JSON：
```bash
ls ~/.claude/skills/config-skills/presets/
```

### 用户已有重要自定义 skillOverrides
应用 preset 会**完全覆盖**现有 `skillOverrides`。先建议备份：
```bash
cp .claude/settings.json .claude/settings.json.bak
```

### 跨项目复用 preset
本 skill 装在用户级 `~/.claude/skills/config-skills/`，所有项目都能 `/config-skills`，preset 跟着用户级走，不需要每个项目重装。
