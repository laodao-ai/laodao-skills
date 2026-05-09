---
name: config-setup
description: 模版驱动的项目级 settings 编排——分析项目类型、匹配/生成模版、串行完成 plugin→skill 配置，是进新项目的一站式设置入口
---

# /config-setup — 项目设置编排器

模版驱动的串行编排入口。分析当前项目、匹配或生成推荐模版，依次完成 plugin 配置和 skill 配置，最后可选保存为可复用模版。

---

## 角色分工

本 skill 同时扮演两个角色：

| 角色 | 何时激活 | 职责 |
|------|---------|------|
| **UI 中继** | 全程始终 | 渲染表格、翻译命令输出、展示 diff、格式化用户操作 |
| **推荐引擎** | 本 skill 专属 | 分析项目特征、匹配模版、生成个性化推荐 |

**决策权永远归用户**——所有推荐都是建议，用户可以逐条覆盖或完全忽略。Claude 不会静默应用任何设置。

---

## 8 步串行流程

### Step 01 — 项目分析

扫描当前项目目录，识别项目特征信号：

| 信号文件 / 目录 | 项目类型推断 |
|----------------|------------|
| `hugo.toml` / `hugo.yaml` | Hugo 静态博客 |
| `go.mod` | Go 项目 |
| `package.json` | Node.js / 前端 |
| `content/` + `themes/` | Hugo 内容站点 |
| `cmd/` + `internal/` | Go 服务端 |
| `pyproject.toml` / `requirements.txt` | Python 项目 |
| `Dockerfile` / `docker-compose.yml` | 容器化项目 |
| `openspec/` | SDD / OpenSpec 工作区 |
| `CLAUDE.md` 已有自定义段 | 有团队规范 |

Claude 综合以上信号生成项目简报，展示给用户确认，再进入下一步。

---

### Step 02 — 模版匹配 / 生成

调用 CLI：

```bash
python3 ~/.claude/skills/laodao-skills/config-setup/config_setup.py templates match --json --proj-dir .
```

根据输出走三条路径之一：

**Path A — 自动匹配到模版**

```
找到模版：hugo-blog（相似度 87%）
描述：Hugo 博客 + Blowfish 主题，启用 firecrawl / playwright，关闭 slack
是否加载这个模版？[Y/n]
```

加载后，推荐列直接使用模版中的配置值。

**Path B — 未匹配到模版**

Claude 根据 Step 01 的项目特征 + 各 plugin / skill 的 description，现场生成推荐值，展示在表格"推荐"列中。

**Path C — 用户主动描述**

用户说明项目用途（如"这是个爬虫脚本，需要浏览器自动化"）→ Claude 根据描述生成推荐。

**三条路径最终都展示推荐表格，由用户决定：**
1. 接受模版 / 推荐作为起点（可逐条修改）
2. 忽略推荐，全手动配置
3. 跳过推荐，直接进入当前状态

---

### Step 03 — 用户确认

自动匹配的模版**必须经用户明确确认**后才能作为推荐基准。

Claude 不得静默加载模版。即使相似度 100%，也要展示摘要并等待确认。

---

### Step 04 — Plugin 配置：状态展示

调用 CLI：

```bash
python3 ~/.claude/skills/laodao-skills/config-setup/config_setup.py plugins status --json
```

渲染带"推荐"列的完整表格：

```
 #   plugin                              effective   推荐     description
 1   firecrawl@claude-plugins-official   ✗ off       ← on    Web scraping & crawling
 2   playwright@official                 ✓ on        ✓       Browser automation
 3   slack@official                      ✓ on        ← off   Slack integration
 4   github@official                     ✗ off               GitHub operations
```

图例：
- `✓` 当前已启用 / 推荐启用
- `✗` 当前已禁用 / 推荐禁用
- `← on` / `← off` 推荐与当前不一致，建议变更方向
- 推荐列空白 = 无模版推荐，保持现状

---

### Step 05 — Plugin 配置：交互

使用 `/config-plugins` 协议处理用户输入：

| 指令 | 效果 |
|------|------|
| `iN` | 查询第 N 行详细说明（i = info） |
| `Non` | 将第 N 行设为 on（仅排队，不写入） |
| `Noff` | 将第 N 行设为 off |
| `pending` | 显示当前所有待定变更 |
| `undo` | 撤销最后一次变更 |
| `done` | 结束 plugin 阶段，进入写入确认 |

**推荐值不会自动应用。** 用户未明确操作的行保持当前状态不变。

用户可以说"按推荐应用全部"——Claude 将所有与推荐不一致的行排队，展示 pending 列表，等待二次确认后才继续。

---

### Step 06 — Plugin 配置：写入

用户输入 `done` 后：

1. 展示 dry-run diff（新旧 `enabledPlugins` 对比）
2. 等待用户确认（Y/n）
3. 调用 CLI 写入：

```bash
python3 ~/.claude/skills/laodao-skills/config-setup/config_setup.py plugins set '<JSON>'
```

4. 调用 `plugins status --json` 验证写入结果，渲染最终状态表格

---

### Step 07 — Skill 配置

与 Step 04–06 结构相同，使用 `/config-skills` 协议（四态：on / name-only / user-invocable-only / off）。

调用 CLI：

```bash
python3 ~/.claude/skills/laodao-skills/config-setup/config_setup.py skills status --json
```

渲染带"推荐"列的 skill 表格，列出当前有效状态 + 推荐值 + 描述。

交互指令与 plugin 阶段相同，但状态值扩展为四态：

| 指令 | 效果 |
|------|------|
| `Non` | 第 N 行设为 on |
| `Nname` | 第 N 行设为 name-only |
| `Nuser` | 第 N 行设为 user-invocable-only |
| `Noff` | 第 N 行设为 off |

写入指令：

```bash
python3 ~/.claude/skills/laodao-skills/config-setup/config_setup.py skills set '<JSON>'
```

---

### Step 08 — 模版保存（可选）

根据路径和变更情况决定是否提示：

**来自 Path A（加载了已有模版）且有修改：**

列出与原模版的差异，提供三选项：
1. 更新原模版（覆盖写入）
2. 另存为新模版
3. 不保存

**来自 Path B / C（现场生成推荐）：**

提示是否保存为新模版。Claude 建议模版名称、描述和识别信号，用户可调整后确认。

**来自 Path A 且无修改：**

不提示，静默跳过。

保存命令：

```bash
python3 ~/.claude/skills/laodao-skills/config-setup/config_setup.py templates save '<JSON>'
```

JSON 格式：

```json
{
  "name": "hugo-blog",
  "description": "Hugo 博客 + Blowfish 主题",
  "signals": ["hugo.toml", "themes/", "content/"],
  "plugins": { "firecrawl@claude-plugins-official": true },
  "skills": { "firecrawl:firecrawl-scrape": "on" }
}
```

---

## CLI 完整参考

```bash
# 模版操作
python3 ~/.claude/skills/laodao-skills/config-setup/config_setup.py templates list
python3 ~/.claude/skills/laodao-skills/config-setup/config_setup.py templates match --json --proj-dir <path>
python3 ~/.claude/skills/laodao-skills/config-setup/config_setup.py templates show <name>
python3 ~/.claude/skills/laodao-skills/config-setup/config_setup.py templates save '<JSON>'
python3 ~/.claude/skills/laodao-skills/config-setup/config_setup.py templates delete <name>

# Plugin 操作
python3 ~/.claude/skills/laodao-skills/config-setup/config_setup.py plugins status --json
python3 ~/.claude/skills/laodao-skills/config-setup/config_setup.py plugins set '<JSON>'

# Skill 操作
python3 ~/.claude/skills/laodao-skills/config-setup/config_setup.py skills status --json
python3 ~/.claude/skills/laodao-skills/config-setup/config_setup.py skills set '<JSON>'
```

---

## 与原生 UI 的层级关系

本工具写入**第 4 层**（团队共享基线），与其他配置层互补而非替代：

| 层级 | 工具 | 写入位置 | 用途 |
|------|------|---------|------|
| 5（最高优先） | `/plugins` | 用户全局配置 | 跨项目个人偏好 |
| 4 | `/config-setup` | 项目 settings.json | 团队共享基线 |
| 3 | `/skills` | 项目本地配置 | 临时本地覆盖 |
| 1–2 | 系统默认 | 内置 | 出厂默认值 |

三个工具同时使用时，高层级设置覆盖低层级。`/config-setup` 的设置会被 `/plugins`（层 5）覆盖，但会覆盖 `/skills` 的临时设置（层 3）。

---

## 完整使用示例

```
用户：/config-setup

Claude：正在分析项目目录……

  检测到：hugo.toml ✓  content/ ✓  themes/blowfish ✓
  项目类型：Hugo 静态博客（Blowfish 主题）

  正在匹配模版……

  匹配到模版：hugo-blog（相似度 92%）
  描述：Hugo 博客，启用 firecrawl + playwright，关闭 slack

  是否加载这个模版作为推荐基准？[Y/n]

用户：Y

Claude：
  === Plugin 配置 ===

   #   plugin                              effective   推荐     description
   1   firecrawl@claude-plugins-official   ✗ off       ← on    Web scraping
   2   playwright@official                 ✓ on        ✓       Browser automation
   3   slack@official                      ✓ on        ← off   Slack integration

  输入操作（iN 查询 / Non/Noff 调整 / done 完成）：

用户：1on 3off

Claude：
  待定变更：
   - firecrawl@claude-plugins-official: off → on
   - slack@official: on → off

  继续操作或输入 done 写入：

用户：done

Claude：
  Dry-run diff：
  + firecrawl@claude-plugins-official
  - slack@official

  确认写入？[Y/n]

用户：Y

Claude：
  Plugin 配置写入完成。

  === Skill 配置 ===
  （渲染 skill 表格……）

  输入操作：

用户：done

Claude：
  Skill 配置无变更，跳过写入。

  === 模版保存 ===
  与原模版 hugo-blog 的差异：
   - slack@official: on → off（原模版为 on）

  1. 更新原模版 hugo-blog
  2. 另存为新模版
  3. 不保存

用户：1

Claude：
  模版 hugo-blog 已更新。

  /config-setup 完成。当前项目配置已与模版 hugo-blog（已更新）同步。
```

---

## 边界说明

- 本 skill 不直接修改 CLAUDE.md，不处理 hooks，不涉及 git 操作
- plugin / skill 名称以 CLI 返回的标识符为准，Claude 不得自行猜测或补全
- 用户输入的模版名称若与已有模版冲突，Claude 须提示并请用户决定覆盖或重命名
- 如果 CLI 调用失败，展示原始错误信息，不要包装或隐藏
