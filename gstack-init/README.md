# gstack-init

> 把 gstack 跑出来的 design docs / health reports 这类"过程文档"接入主仓 `.gstack/project/`，让它们随主仓 git 一起版本化、跨机器同步、跟着 PR 一起 review。同时 gstack 自身完全无感，所有原有 binary 和 skill 都正常工作。

---

## 为什么要做这个 skill

### 问题：gstack 默认把所有产出物写到 `~/.gstack/`，跟项目失联

[gstack](https://github.com/garrytan/gstack) 是 Garry Tan 的 Claude Code 工作流套件，提供 23 个 specialist skill（`/office-hours` / `/qa` / `/ship` / `/review` / `/plan-eng-review` 等）。它每次跑一个 skill，会把产出物写到 `~/.gstack/projects/<slug>/`：

- **design docs**（office-hours 写的设计文档，几 KB 到几十 KB 的 markdown）
- **health-history.jsonl**（health 跑分历史）
- **timeline.jsonl**（每次 skill 调用的时间线）
- **builder-profile.jsonl**（跨项目的"成长轨迹"）
- **learnings.jsonl**（从代码观察到的可复用 insight）
- **checkpoints / ceo-plans / reviews**（plan-* 系列 skill 写的工件）

这些文件**有不同的归属**：
- "设计文档"应该跟项目代码一起活——和 PR review、跨机器开发、多人协作绑定
- "成长轨迹"应该跨项目共享——builder-profile.jsonl 累积所有项目的 office-hours 记录，是个人级状态
- "运行时缓存"（timeline / repo-mode）是 ephemeral 的——不该入库

但 gstack 默认把它们**全部混在 `~/.gstack/`**，结果就是：
1. 我跑 `/office-hours` 写了个 design doc 到 `~/.gstack/projects/<slug>/cheneyzhao-main-design-*.md`
2. 我换台机器 / 让同事看 / 走 PR review，**这份 doc 完全访问不到**——它不在主仓里
3. 我手动 `cp` 一份到 `openspec/changes/<change>/design.md`——但下次 skill 跑会再写一份新的，cp 副本立刻 stale

这就是这个 skill 要解决的核心问题：**让"项目级产出"住进主仓，"全局级状态"留在 home，机制对 gstack 完全透明**。

### 4 种解决思路（演进过程）

| 方案 | 实现 | 缺点 | 选用 |
|---|---|---|---|
| 方案 1 | `export GSTACK_HOME=/path/to/repo/.gstack`，搬整个 home 到项目 | 跨项目状态（builder-profile / config）丢失，多项目情境 builder profile 被切碎 | ❌ |
| 方案 2 | 项目内建正向软链 `.gstack/project → ~/.gstack/projects/<slug>` | 软链入不了 git（`git add` 跨软链触发 `fatal: pathspec is beyond a symbolic link`，git 2.x CVE-2017-1000117 后的安全保护）| ❌ |
| 方案 3 | 每次跑完 skill 手动 `cp` design doc 到主仓 | 要记得 cp，且 health-history / timeline 这种持续追加文件没法跟 | △ 应急可用 |
| **方案 D** | **反向软链**：物理目录 mv 进主仓 `.gstack/project/`，再从 `~/.gstack/projects/<slug>` 软链回来 | 跨机器 clone 后要重做反向软链一次（`scripts/setup-gstack.sh` 解决） | ✅ **选用** |

方案 D 的本质：**让"home 视角"和"repo 视角"看到的同一份数据有不同身份**。
- gstack 的 binary 永远走 `~/.gstack/...`，OS 软链解析透明地落到主仓——gstack 不知道
- git 看到的是主仓真实文件，正常 add/commit/push——git 不知道有 home 视角

这是 Unix 软链最经典的"职责分层"——一个工具看到 home 路径，另一个工具看到 repo 路径，但物理数据只有一份。

---

## 解决了什么具体问题

✅ **设计文档随主仓 git 一起版本化**——`/office-hours` 写出的 design doc 直接 `git add .gstack/project/*.md` 入库，跟着 PR review。

✅ **跨机器同步**——clone 主仓到新机器，跑一次 `bash scripts/setup-gstack.sh` 就完成所有 gstack 项目状态恢复。`.md` 进 git 自动同步，`.jsonl` 等运行时缓存重新生成即可。

✅ **gstack 自身零侵入**——所有 binary、skill、preamble、telemetry 都不需要改，因为 `~/.gstack/projects/<slug>` 这个路径在 OS 视角下仍然有效。

✅ **运行时 noise 不污染 git status**——`timeline.jsonl` / `health-history.jsonl` / `repo-mode.json` 等持续追加的文件不会出现在 `git status` 里，但仍然能被 gstack 写入。

✅ **跨项目共享状态保留**——`~/.gstack/builder-profile.jsonl` / `~/.gstack/.config.json` / `~/.gstack/sessions/` 等全局级文件不动，多项目情境下"成长轨迹"和"配置"仍统一管理。

---

## ⚠️ 注意事项

### 1. clone 后必须先跑 setup 脚本，否则数据会沉默分叉

新机器 clone 主仓后，`~/.gstack/projects/<slug>` 这个反向软链不存在。**第一次跑任何 gstack skill** 之前必须先跑：

```bash
bash scripts/setup-gstack.sh
```

否则会发生：gstack 第一次启动会自动 mkdir `~/.gstack/projects/<slug>` 一个空目录，把新 design doc 写到这个**空目录**里——主仓内的 `.gstack/project/` 旧 design doc 还在，但和 gstack 的视角失联了。这是**沉默的数据分叉**，错误不会立刻显现，等你下次发现 design doc 不更新才意识到，那时已经分叉了。

**保险做法**：在主仓 `README.md` 的"clone 后做什么"段加一行：
```markdown
## 开发环境初始化

```bash
git clone ...
cd 01-laodao
bash scripts/setup-gstack.sh   # 必须！恢复 gstack 反向软链
```
```

### 2. 不要 `git add -f .gstack/project/`（会触发跨软链 fatal）

如果某个 gstack 内部状态文件你确实想入库（比如 builder-profile 的某次重要 entry），**不能用 `-f` 绕过 ignore**——git 默认拒绝跨软链 pathspec（CVE-2017-1000117 加固）。

正确做法：**`cp` 出来一份到主仓真实路径**，比如 `cp .gstack/project/learnings.jsonl docs/decisions/learnings-snapshot-2026-05-05.jsonl`，再 `git add` 这份副本。

### 3. 多项目共用一个 gstack home，但每个项目独立反向软链

如果你有多个项目都跑 mode D（比如 `01-laodao` + `examples/ai-shorurl`），每个项目都会在 `~/.gstack/projects/<unique-slug>` 创建一个反向软链。slug 由 git remote 推导，不会冲突。

但 `~/.gstack/builder-profile.jsonl` 是**所有项目共享**的——`/office-hours` 在哪个项目跑，都会追加同一个 jsonl。这是设计意图（Garry 的"跨项目成长轨迹"理念）。如果你不希望某个项目的活动累积到全局 profile，那个项目应该用方案 1（独立 GSTACK_HOME）而不是方案 D。

### 4. `apply-d` 会移动数据，跑前要确认

`gstack-init.sh apply-d` 在某些状态下会执行 `mv ~/.gstack/projects/<slug>/ → .gstack/project/`——这是数据移动，不是复制。如果你担心，先 `cp -r` 一份做 backup：

```bash
cp -r ~/.gstack/projects/<slug> /tmp/gstack-backup-$(date +%s)
```

恢复方法：删主仓 `.gstack/project`、删反向软链、把 backup 复原回 `~/.gstack/projects/<slug>`。

### 5. `enableCodeCopy` / `repo-mode.json` 这种 gstack 内部 config 不要 track

默认 .gitignore 规则只让 `*.md` 入库，其它扩展名（`.json` / `.jsonl` / `.txt`）默认忽略。如果你心血来潮想 track 某个 jsonl（比如想记录某次 health-history 的快照），用 `cp` 出来到一个非 .gstack/ 的真实路径再 add，**不要**修改 .gitignore 让某个 jsonl 入库——因为 jsonl 是 append-only，每次 gstack 写新行就 dirty，git 会持续 noisy。

---

## 用法速查

### 在新项目首次配置（一次性）

```bash
cd /path/to/your-project
~/.claude/skills/laodao-skills/gstack-init/scripts/gstack-init.sh apply-d
~/.claude/skills/laodao-skills/gstack-init/scripts/gstack-init.sh write-gitignore
~/.claude/skills/laodao-skills/gstack-init/scripts/gstack-init.sh write-setup-script
~/.claude/skills/laodao-skills/gstack-init/scripts/gstack-init.sh verify
```

或者通过 Claude Code 触发：跟 Claude 说"配置 gstack 项目级"或"`/gstack-init`"。

### 跨机器 clone 后恢复

```bash
git clone <your-repo>
cd <your-repo>
bash scripts/setup-gstack.sh
```

### 验证当前状态

```bash
~/.claude/skills/laodao-skills/gstack-init/scripts/gstack-init.sh detect
# 输出 KEY=VALUE，可 eval

~/.claude/skills/laodao-skills/gstack-init/scripts/gstack-init.sh verify
# 跑全套校验
```

### 卸载 mode D（恢复 gstack 默认行为）

```bash
# 1. 把主仓内的真实目录搬回 home
SLUG=$(~/.claude/skills/gstack/bin/gstack-slug | awk -F= '/SLUG=/{print $2}')
rm ~/.gstack/projects/$SLUG  # 删反向软链
mv .gstack/project ~/.gstack/projects/$SLUG  # 搬回 home

# 2. 把 .gitignore 改回简单 .gstack/ 规则
# 编辑 .gitignore 删掉 negate 块，恢复 .gstack/

# 3. 删主仓 scripts/setup-gstack.sh（如有）
rm -f scripts/setup-gstack.sh
```

---

## 常见问题

### `apply-d` 报错"unknown / ambiguous state"

意味着 home 路径和主仓 .gstack/project 处于既不全空也不规范的状态。手动 `ls -la ~/.gstack/projects/<slug>` 和 `ls -la .gstack/project` 看下，决定是要保留 home 还是 repo 那份的数据。

### 我已经手动 cp 过 design doc 到 openspec change，现在再做 mode D 会重复吗？

会同时存在两份：`.gstack/project/*.md`（mode D 主源）+ `openspec/changes/<change>/*.md`（手动副本）。它们职责不同——前者是 gstack 持续写入的真实状态，后者是 OpenSpec change 的 spec 起点。两份**不会**自动同步，但你可以决定保留还是删除手动副本。

### gstack 升级后这个 skill 还能用吗？

只要 gstack 仍然把 `~/.gstack/projects/<slug>` 作为项目数据落点（这是 gstack 的根本约定），这个 skill 就一直有效。如果未来 gstack 自己加了"项目级模式"开关，可以平滑迁移过去。

### 这个 skill 能反向跟踪 `~/.claude/skills/gstack/` 本身的更新吗？

不能也没必要——`~/.claude/skills/gstack/` 是 gstack 的代码仓库（`./setup` 拉的），由 `/gstack-upgrade` 命令管。这个 skill 只管 `~/.gstack/`（gstack 的运行时数据目录），跟代码仓不冲突。

---

## 设计参考

- [gstack 官方仓](https://github.com/garrytan/gstack)
- [git CVE-2017-1000117（pathspec is beyond a symbolic link 的来源）](https://github.com/git/git/commit/1a7fd1fb29790cd6dde43ddf4fda7eba03a3ec00)
- [Linus Torvalds 在 Linux kernel 仓里如何用软链做"职责分层"](https://github.com/torvalds/linux/blob/master/tools/) — `tools/` 目录用软链而非 submodule 的设计哲学

---

## 相关 skill

- `/gstack-init` — 本 skill，项目级配置
- `/office-hours` — gstack 自带，写 design docs
- `/health` — gstack 自带，跑代码质量评分（写 health-history.jsonl）
- `/plan-eng-review` — gstack 自带，工程评审
