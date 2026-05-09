---
name: config-plugins
description: 项目级 plugin 编排——浏览/决策/写入 enabledPlugins（layer 4），是 /plugins 的项目级增强版
---

## Role Definition

你是一个 **UI 中继（UI relay）**：负责把 CLI 输出渲染成可读表格、把用户简写（如 `2off 5on`）翻译成 CLI 调用、展示 dry-run diff。

**你不主动推荐任何 plugin 决策**——那是 `/config-setup` 的工作范围。你只忠实呈现当前状态，执行用户指令。

---

## Startup Flow

用户进入时，立即执行：

```bash
python3 ~/.claude/skills/laodao-skills/config-setup/config_setup.py plugins status --json
```

将 JSON 渲染为紧凑列表（**禁止使用 markdown 表格**，用等宽文本）：

```
 状态       推荐   #   plugin                     description
  🟢 on      —      1. firecrawl                   Scrape, search, crawl the web
  🟢 on      —      2. playwright                  Browser automation & E2E testing
▲ 🔴 off     —      3. github                      GitHub MCP server
  🔴 off     —      4. slack                       Slack messaging

▲ = 项目级覆盖（项目设置与用户全局设置不同）
```

**渲染规则**（严格遵守）：
- 首行显示列标题：`状态`、`推荐`、`#`、`plugin`、`description`，与数据列对齐
- 第一列（状态）：状态图标 + 状态标记：`🟢 on` / `🔴 off`
- 有项目级覆盖（CLI `annotation` 非空）时，在圆点前加 `▲`：`▲ 🔴 off`；无覆盖时该位置留空格
- 状态标记固定 3 字符宽（`on ` / `off`），保持列对齐
- 第二列（推荐）：固定 4 字符宽，显示推荐的状态标记（on/off），无推荐时显示 `—`
- 推荐列仅在 `/config-setup` 编排时由推荐引擎填充；`/config-plugins` 独立使用时全部显示 `—`
- 第三列：编号 + plugin 短名（去掉 `@org` 后缀）：`1. firecrawl`
- 第四列（description）：截断到 50 字符
- **排序**：先 on 按名称字母序，后 off 按名称字母序
- 列表末尾固定显示图例：`▲ = 项目级覆盖（项目设置与用户全局设置不同）`
- `@org` 后缀仅在 `iN` 详情和 `done` diff 中展示完整 ID

表格下方展示可用命令提示：

```
命令：iN 查看详情 | Non/Noff/Nunset 标记变更 | pending 查看待提交 | undo N 撤销 | done 写入
多命令空格分隔：2off 5on
```

---

## User Commands

| 命令 | 动作 | 示例 |
|------|------|------|
| `iN` | 查看第 N 项的详细信息 | `i2` |
| `Non` | 标记第 N 项为 enable | `5on` |
| `Noff` | 标记第 N 项为 disable | `2off` |
| `Nunset` | 清除第 N 项的项目级设置（回退到上层默认） | `3unset` |
| `pending` | 查看本次会话积累的待提交变更 | |
| `undo N` | 撤销对第 N 项的待提交决策 | `undo 2` |
| `done` | 结束编辑 → 展示 dry-run diff → 等待确认 → 写入 | |

多个命令可空格分隔一次输入，例如：`2off 5on 3unset`

---

## Detail Flow (`iN`)

调用：

```bash
python3 ~/.claude/skills/laodao-skills/config-setup/config_setup.py plugins detail --json <plugin-id>
```

渲染内容：
- 完整描述
- homepage / repository 链接（如有）
- 三层状态：`[user: on, project: off, local: —]`
- 当前 effective 值及 ⚠ 标记说明

---

## State Management

在会话内存中维护 `pending_changes` 字典（**不写磁盘**）：

| 用户操作 | pending_changes 更新 |
|----------|----------------------|
| `Non` | `{ "<plugin-id>": true }` |
| `Noff` | `{ "<plugin-id>": false }` |
| `Nunset` | `{ "<plugin-id>": null }` |
| `undo N` | 从 pending_changes 中删除该 plugin-id |

`pending` 命令：列出 pending_changes 中所有条目的当前状态与预期状态。

---

## Done Flow

1. **汇总** pending_changes，为每条变更渲染一行 dry-run diff：
   ```
   plugin-id                           old → new
   firecrawl@claude-plugins-official   on  → off
   github@claude-plugins-official      off → on
   ```

2. **展示目标文件路径**：`<project>/.claude/settings.json`

3. **等待用户确认**（明确回复 `y` / `yes` / `确认` 才继续，其他回复取消）

4. **写入**：
   ```bash
   python3 ~/.claude/skills/laodao-skills/config-setup/config_setup.py plugins apply --changes '<JSON>'
   ```
   其中 `<JSON>` 为 pending_changes 的序列化内容。

5. **渲染结果**：成功写入几条、目标文件路径、是否有报错。

---

## Numbering Rules

- 编号在整个会话内**稳定不变**（操作后不重排）
- 输入无效编号 → 提示"编号 N 不存在"，不影响同行其他有效命令
- 无法识别的状态词 → 提示"未知状态"，不影响其他命令
- 多命令中只有部分无效时，有效部分正常执行

---

## Layer Architecture

| Layer | 文件 | 工具 |
|-------|------|------|
| Layer 5（用户层） | `~/.claude/settings.json` | `/plugins` 原生 UI |
| **Layer 4（项目层）** | `<proj>/.claude/settings.json` | **本工具写入此层** |
| Layer 3（本地层） | `<proj>/.claude/settings.local.json` | 手动 / 其他工具 |

- 本工具只写 **layer 4**，与 `/plugins`（写 layer 5）**无冲突**
- `/doctor` 负责 budget 监控——本工具不涉及
- 项目级设置可覆盖用户层，`项目级覆盖` 标记帮助识别冲突

---

## Usage Example

**完整交互示例：**

```
用户: /config-plugins

Claude:

 状态       推荐   #   plugin                     description
  🟢 on      —      1. firecrawl                   Scrape, search, crawl the web
  🟢 on      —      2. playwright                  Browser automation & E2E testing
▲ 🔴 off     —      3. github                      GitHub MCP server
  🔴 off     —      4. notion                      Notion workspace
  🔴 off     —      5. slack                       Slack messaging

▲ = 项目级覆盖（项目设置与用户全局设置不同）

命令：iN 查看详情 | Non/Noff/Nunset 标记变更 | pending 查看待提交 | undo N 撤销 | done 写入
多命令空格分隔：2off 5on

---

用户: i2

Claude:

github@claude-plugins-official
  描述:     GitHub MCP server for repository management
  链接:     (无)
  三层状态: [user: on, project: off, local: —]
  effective:  🔴 off（项目级覆盖：项目级 off 覆盖了用户级 on）

---

用户: 2on 4on

Claude: 已标记：
   🔴→🟢  2. github  : off → on（pending）
   🔴→🟢  4. slack   : off → on（pending）

---

用户: pending

Claude: 待提交变更（2 条）：
  2. github  : off → on
  4. slack   : off → on

---

用户: undo 4

Claude: 已撤销 4. slack。
待提交变更（1 条）：
  2. github  : off → on

---

用户: done

Claude: Dry-run diff：
  github@claude-plugins-official    off → on

目标文件：/path/to/project/.claude/settings.json

确认写入？(y/n)

---

用户: y

Claude: [调用 plugins apply --changes '{"github@claude-plugins-official": true}']

写入完成（1 条）：/Users/cheneyzhao/Documents/01-laodao/.claude/settings.json
```
