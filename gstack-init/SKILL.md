---
name: gstack-init
description: >
  配置 gstack 把 design docs / health reports 等"过程文档"接入主仓 .gstack/project/，
  让它们随主仓 git 一起版本化、跨机器同步、跟着 PR review，同时 gstack 自身完全无感
  （通过反向软链）。当用户说"配置 gstack 项目级"、"gstack 文档归集"、"让 gstack design doc 入 git"、
  "gstack 项目化"、"clone 后恢复 gstack"、"gstack 跨机器同步"，或使用 /gstack-init 时，必须触发此 skill。
  也适用于：用户跑完 office-hours 想把 design doc 入库、用户 clone 一个已配置过 mode D 的主仓后第一次启动。
---

# gstack-init Skill

> **推荐模型**：本 skill 属于参数收集 + 执行类任务（探测状态 → 决策 → 执行预定义子命令），使用 **Haiku** 即可，速度更快、成本更低。
> Skill 本身无法指定模型，请在触发前用 `/model` 切换到 Haiku。

## 这个 skill 解决什么

详见同目录 `README.md` 的"为什么要做这个 skill"段。一句话：**让 gstack 的项目级产出（design docs）住进主仓 git 仓库，把 home 的 ~/.gstack/ 留给跨项目共享状态**。机制是反向软链，对 gstack 自身完全透明。

## Skill 内置文件

```
~/.claude/skills/laodao-skills/gstack-init/
├── SKILL.md                    （本文件，Claude 入口）
├── README.md                   （用户向使用文档 + 设计动机 + 注意事项）
└── scripts/
    ├── gstack-init.sh          主引擎，子命令式（detect/apply-d/restore/...）
    └── setup-gstack.sh         模板，部署到主仓 scripts/ 给跨机器恢复
```

## 工作流

### Phase 1：探测当前状态

```bash
GSTACK_INIT="$HOME/.claude/skills/laodao-skills/gstack-init/scripts/gstack-init.sh"
state=$("$GSTACK_INIT" detect 2>&1) || { echo "探测失败"; echo "$state" >&2; exit 1; }
echo "$state"
eval "$state"
```

`detect` 输出 8 个 KEY=VALUE 行，其中最关键的是：

- `MODE=D` —— 已配置反向软链（无事可做，可以跳到 verify）
- `MODE=Dpre` —— 旧的"正向软链"中间状态，需要转换成真正的 mode D（rm 软链 + mv 数据 + 反向软链）
- `MODE=none` —— gstack 跑过但还没接入主仓（home 是真实目录），可以 `apply-d`
- `MODE=fresh` —— gstack 从未在此项目跑过（home 和 repo 都没目录），可以 `apply-d` 起步
- `MODE=unknown` —— 状态异常，需要人工排查

### Phase 2：根据 mode 决策（AskUserQuestion）

**如果 MODE=D**：直接跑 `verify`，告诉用户"已配置好，无需操作"，结束。

**如果 MODE=fresh / none / Dpre**：用 AskUserQuestion 询问用户要做什么：

```
D1 — 是否启用 gstack 项目级文档归集？
Project/branch: <REPO_ROOT 名> / main
ELI10: gstack 默认把 design docs 写到 ~/.gstack/，跟项目失联——换台机器就看不到，PR 也带不走。
       开启 mode D 后这些 .md 文档会住进主仓 .gstack/project/，跟 git 一起版本化。
       但 gstack 自身完全无感（通过反向软链，工具链路看到的还是 ~/.gstack/...）。
Stakes: 不开启就要每次手动 cp 副本到 openspec/changes/...，且容易 stale。
Recommendation: A 因为 design docs 入 git 是 90% 项目想要的能力，且本 skill 有 verify 兜底
Pros / cons:
A) 启用 mode D（推荐）
  ✅ design doc 自动随 git，跨机器/PR review 无障碍
  ✅ gstack 内部完全透明，所有 23 个 specialist skill 不变
  ❌ 跨机器 clone 后必须先跑 scripts/setup-gstack.sh 重建反向软链，否则数据会沉默分叉
B) 仅 cp 单次副本（保守）
  ✅ 零结构改动，不引入跨机器复杂度
  ❌ 每次 office-hours 后要手动 cp，容易遗忘且副本会 stale
Net: A 是一次性 setup 长期收益，B 是逐次手动归档但持续摩擦
```

**如果 MODE=unknown**：跑 `detect` 输出全部状态，让用户人工判断而不是盲目 apply。

### Phase 3：执行选定动作

**A 启用 mode D（用户选 A 后顺序执行 4 步）**：

```bash
"$GSTACK_INIT" apply-d              # 1. mv 物理目录到主仓 + 反向软链
"$GSTACK_INIT" write-gitignore      # 2. 智能合并 .gitignore negate 规则
"$GSTACK_INIT" write-setup-script   # 3. 在主仓 scripts/setup-gstack.sh 写恢复脚本
"$GSTACK_INIT" verify               # 4. 跑全套验证
```

**B 仅 cp 单次副本**（用户选 B）：

要求用户提供目标路径，或推荐放到 `openspec/changes/<change>/gstack-design.md`：

```bash
"$GSTACK_INIT" apply-a "openspec/changes/<change>/gstack-design.md"
```

### Phase 4：报告 + 提示

执行完后给用户简洁报告：

- 已生效的物理状态（哪些文件落到主仓、哪些仍在 home）
- 下一步建议（commit + push）
- ⚠️ 跨机器风险提醒：clone 后必须跑 `bash scripts/setup-gstack.sh`，否则数据沉默分叉
- 提示用户在主仓 README.md 加一行"clone 后初始化"说明

## 特殊场景

### 场景 1：clone 主仓到新机器后初始化

用户在新机器 clone 完主仓后，直接说"恢复 gstack"或"clone 完了"，跳过 Phase 2 直接：

```bash
"$GSTACK_INIT" restore
"$GSTACK_INIT" verify
```

或者更地道地告诉用户：项目内已经有 `scripts/setup-gstack.sh`（之前 `write-setup-script` 部署的），直接 `bash scripts/setup-gstack.sh` 即可。

### 场景 2：用户想知道当前是什么状态

跑 `detect`，把输出格式化呈现给用户：

```
当前状态：
  项目根：/Users/.../01-laodao
  Slug：zhaocheng-Laodao-AI-Coding-Workshop
  Mode：D（反向软链已配置）
  Home 软链：~/.gstack/projects/zhaocheng-... → /Users/.../.gstack/project
  Repo 路径：/Users/.../.gstack/project（真实目录）
```

### 场景 3：apply-d 报错 "unknown / ambiguous state"

不要盲目重试。跑 `detect` 输出全部状态，让用户判断：

- home 是 dir 但 repo 是 dir：两边都有真实目录，需要人工合并
- home 是 symlink 但 target 不对：旧软链残留
- 等等

让用户决定保留哪份后再手动操作。

## 不做的事

- **不**修改用户的 git config / gstack-config（gstack-init 不应改 gstack 自身配置）
- **不**触碰 ~/.gstack/builder-profile.jsonl / sessions/ / analytics/ 等 home 全局状态文件
- **不**自动 commit `.gstack/project/*.md`（让用户自己决定 commit 时机和 message）
- **不**自动 push（绝不）

## 错误处理

| 错误 | 处理 |
|---|---|
| 不在 git repo | 报错退出，让用户 cd 到正确目录 |
| `gstack-slug` binary 不存在 | 提示先装 gstack：`cd ~/.claude/skills/gstack && ./setup` |
| `~/.gstack/projects/<slug>/` 既不是 dir 也不是 symlink，但有数据 | 报错并显示 `ls -la` 结果，让用户人工判断 |
| `apply-d` 后 verify 失败 | 不要盲目重试，把 verify 错误信息呈现给用户 |
| 主仓已有 `.gstack/project` 但与 home slug 不匹配 | 报错，可能是误用（多 slug 共用？），让用户排查 |

## Completion Status

完成后报告：

- **DONE** — apply-d + write-gitignore + write-setup-script + verify 全过
- **DONE_WITH_CONCERNS** — apply 完成但用户跨机器恢复 flow 还没测过（建议提示用户走一遍 clone → setup-gstack.sh 验证）
- **BLOCKED** — 状态 unknown 需要人工干预
- **NEEDS_CONTEXT** — 用户没说清是要 apply 还是 restore，问澄清问题
