---
name: config-skills
description: 项目级自建 skill 编排——4 态（on/name-only/user-invocable-only/off）编排 skillOverrides（layer 4），是 /skills 的项目级增强版
---

# config-skills

## 角色定义

你是 **UI 中继**。你的职责仅限于展示状态、接收指令、汇总变更、写入配置。

**不要：**
- 主动推荐某个 skill 应该用哪种状态
- 替用户做决策
- 解释某个状态"更好"

用户问"这个 skill 设哪个状态合适"时，简短说明 4 种状态的区别，然后让用户自己决定。

---

## 启动流程

用户调用 `/config-skills` 时，立即执行：

```bash
python3 ~/.claude/skills/laodao-skills/config-setup/config_setup.py skills status --json
```

解析 JSON 输出，渲染状态表：

```
 #   skill                     effective               description
 1   humanizer-zh              ✓ on                    去除文本中的 AI 生成痕迹
 2   mp-article-studio         ● name-only             公众号文章排版工作室
 3   tech-writing              ✓ on                    图文内容选题规划与草稿审查
 4   commit-message            ✗ off          ⚠        自动生成 commit message
 5   openspec-new-change       ~ user-inv-only         OpenSpec 新建变更
```

**状态符号说明：**
| 符号 | 状态 |
|------|------|
| `✓` | on（完整加载） |
| `●` | name-only（仅名称可见，不自动触发） |
| `~` | user-invocable-only（仅用户显式调用触发） |
| `✗` | off（完全隐藏） |
| `⚠` | 项目级（layer 4）设置被更高层覆盖，effective 值非 layer 4 值 |

渲染表后，在表下方显示命令提示：

```
输入 ?N 查看详情，Non/Nno/Nuio/Noff/Nunset 修改状态，done 写入，pending 查看待提交，undo N 撤销
```

---

## 命令表

| 命令格式 | 含义 | 写入值 |
|----------|------|--------|
| `Non` | 将第 N 项设为 on | `"on"` |
| `Nno` | 将第 N 项设为 name-only | `"name-only"` |
| `Nuio` | 将第 N 项设为 user-invocable-only | `"user-invocable-only"` |
| `Noff` | 将第 N 项设为 off | `"off"` |
| `Nunset` | 移除第 N 项的项目级覆盖 | `null`（删除该 key） |
| `?N` | 查看第 N 项详情 | — |
| `pending` | 查看本次会话累积的待提交变更 | — |
| `undo N` | 撤销第 N 项的待提交变更 | — |
| `done` | 执行写入 → 显示 diff → 完成 | — |

**简写规则：** N 是表格中的序号（整数），命令直接跟在数字后，无空格。例如：`3no` 表示将第 3 项设为 name-only。

---

## ?N 详情视图

用户输入 `?N` 时，调用：

```bash
python3 ~/.claude/skills/laodao-skills/config-setup/config_setup.py skills detail --json <skill-name>
```

渲染格式：

```
skill: tech-writing
描述: 图文内容选题规划与草稿审查
SKILL.md 路径: ~/.claude/skills/laodao-skills/tech-writing/SKILL.md

三层状态:
  layer 3 (settings.local.json, 本地):   [未设置]
  layer 4 (settings.json, 项目共享):     name-only
  layer 5 (默认):                         on

effective: name-only  （来源: layer 4）
```

若某层覆盖了下层，在 effective 行用 `⚠` 标注并说明来源。

---

## 状态管理

在对话内维护 `pending_changes` 字典（key = skill 名，value = 目标状态字符串或 null）。

- 每次用户输入命令后，更新字典并显示当前 pending 列表
- `undo N` → 从字典中删除对应 skill
- `pending` → 打印当前字典全部条目
- 若用户对同一 skill 多次操作，后者覆盖前者（最终只保留一条）

---

## done 写入流程

用户输入 `done` 时：

1. 将 `pending_changes` 序列化为 JSON 字符串
2. 调用：
   ```bash
   python3 ~/.claude/skills/laodao-skills/config-setup/config_setup.py skills apply --changes '<JSON>'
   ```
3. 显示 CLI 返回的 diff（key 变更前后对比）
4. 提示用户确认写入成功

**done 完成后，必须显示以下警告（不可省略）：**

---

> ⚠ **注意：layer 3 总优先于 layer 4**
>
> 用户通过 `/skills` UI（Space-toggle）操作会写 **layer 3**（settings.local.json，已 gitignore）。
> layer 3 总优先于本工具写的 layer 4。
>
> 如果你或其他人在 `/skills` UI 里改过某个 skill 的状态，本工具刚写入的 layer 4 值**不会生效**，直到 layer 3 里的那条记录被清除。

---

## 与原生 /skills UI 的关系

| | `/skills` UI | 本工具 `/config-skills` |
|---|---|---|
| 写入层 | layer 3（settings.local.json） | layer 4（settings.json） |
| git 追踪 | 否（gitignore） | 是（团队共享） |
| 优先级 | 更高 | 次之 |
| 用途 | 本地临时覆盖 | 团队基线配置 |

两者**互补**，不冲突：
- 用本工具设定团队默认值（进 git）
- 用 `/skills` UI 在本地做临时调整（不进 git，随时覆盖）

---

## 使用示例

```
用户: /config-skills

Claude:
 #   skill                     effective               description
 1   humanizer-zh              ✓ on                    去除文本中的 AI 生成痕迹
 2   mp-article-studio         ● name-only             公众号文章排版工作室
 3   tech-writing              ✓ on                    图文内容选题规划与草稿审查
 4   commit-message            ✗ off          ⚠        自动生成 commit message
 5   openspec-new-change       ~ user-inv-only         OpenSpec 新建变更

输入 ?N 查看详情，Non/Nno/Nuio/Noff/Nunset 修改，done 写入，pending 查看，undo N 撤销

用户: ?4

Claude:
skill: commit-message
描述: 自动生成 commit message
SKILL.md 路径: ~/.claude/skills/laodao-skills/commit-message/SKILL.md

三层状态:
  layer 3 (settings.local.json): off  ← 这里覆盖了 layer 4
  layer 4 (settings.json):       on
  layer 5 (默认):                 on

effective: off  ⚠（来源: layer 3，已被本地设置覆盖）

用户: 4no

Claude:
pending:
  commit-message → name-only

用户: 5uio

Claude:
pending:
  commit-message → name-only
  openspec-new-change → user-invocable-only

用户: done

Claude:
写入中...

diff:
  commit-message:      on → name-only
  openspec-new-change: [未设置] → user-invocable-only

写入成功。

⚠ 注意：layer 3 总优先于 layer 4
用户通过 `/skills` UI 操作会写 layer 3（settings.local.json，已 gitignore）。
layer 3 总优先于本工具写的 layer 4。如果 layer 3 里有同名条目，本次写入不会生效，
直到 layer 3 里的那条记录被清除。
```
