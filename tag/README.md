# tag skill — Git 语义化版本标签管理

## 这个 Skill 是什么

**tag skill** 是一个 Git 版本标签助手。它让你在 Claude 对话里完成从"分析提交"到"打 tag、push"的全流程，无需切换终端、手敲命令或记忆 git 语法。

**核心价值**：辅助决策 + 代劳执行。

打 tag 最费脑的环节是"这次该升 patch 还是 minor？"——这需要回顾最近的提交、判断变更性质。Skill 会自动读取提交列表，根据内容给出带理由的版本建议，用户只需在对话中确认，Claude 随即执行 `git tag + push`，整个过程不离开聊天窗口。

对于正式 release，skill 还能根据提交内容自动草拟 annotated tag 的说明文字，用户微调后直接打出带说明的标签，适合生成 GitHub/GitLab Release 页面。

Skill 同时附带两个可独立使用的 bash 脚本，适合不想依赖 Claude 的场景（如 CI 脚本或习惯命令行的用户）。

---

## 解决什么问题

打 Git tag 听起来简单，实际上每次都要：

1. 查当前最新 tag 是什么（`git tag --list ... --sort=...`）
2. 心算下一个版本号（这次是 patch 还是 minor？）
3. 看一眼最近提交决定升哪一位
4. 手敲 `git tag vX.Y.Z`
5. 再敲 `git push origin vX.Y.Z`

这个流程不复杂，但足够烦人——尤其是步骤 2 和 3，需要停下来思考。遇到焦虑的发布节点，容易打错版本号，或者忘了 push。

**痛点**：重复、容易出错、打断心流。

---

## 为什么要用 Git 语义化版本标签

版本号不只是一个数字，它是对"这次变更影响范围"的公开承诺。

语义化版本（SemVer，`vMAJOR.MINOR.PATCH`）的三位数字各有含义：

| 位 | 何时升 | 传达的信息 |
|----|--------|-----------|
| **MAJOR** | 有不向下兼容的变更 | 调用方需要适配，升级有风险 |
| **MINOR** | 新增功能，向下兼容 | 可以安全升级，会有新东西可用 |
| **PATCH** | 修复 bug，无新功能 | 可以放心升级，只是修了问题 |

**对团队的价值**：

- **自动化工具读得懂**：CI/CD、依赖管理（`go.mod`、`package.json`）、changelog 生成工具都依赖语义化版本。不打 tag 就只能靠 commit hash，既不可读也无法表达稳定性
- **部署回滚有锚点**：生产出问题时，`git checkout v1.3.2` 直接回到已知稳定状态，比找 commit hash 快得多
- **沟通成本降低**："v1.4 有这个问题吗？"比"那个 3 周前的某个 commit 有没有这个问题"清晰太多
- **GitHub/GitLab Release 页面**：打了 annotated tag 后，平台会自动生成 Release 页面，包含下载链接和说明，是对外发布的标准形式

**轻量 tag（lightweight）vs annotated tag**：

- **lightweight**：只是一个指向 commit 的指针，适合内部开发节点、快速标记
- **annotated**：存储了打标人、时间、说明文字，有自己的 GPG 签名入口，是正式 release 的推荐形式。GitHub Release 页面也优先识别 annotated tag

---

## 设计思路与关键决策

### 决策一：由 Claude 做版本建议，用户在对话中确认

原始 `hack/tag.sh` 用 `read -rp` 在终端里等用户输入。这意味着 Claude 无法代劳整个流程——它只能告诉你"去跑这个命令"。

重新设计后，确认步骤放在对话里，Claude 直接执行 `git tag` 和 `git push`。这样整个流程在一次对话中完成，不需要切换到终端。

### 决策二：附带非交互式引擎脚本

Skill 内置了一个非交互式的 `scripts/tag.sh`，把原脚本的功能拆分为子命令（`info / create / push / delete / list`），供 Claude 用 Bash 工具调用。这样：
- Claude 负责：分析提交、建议版本、对话确认
- 脚本负责：执行 git 原子操作

逻辑和操作分离，各司其职。

### 决策三：基于提交内容给出版本建议理由

不只是"要升哪个？"，而是主动分析最近提交，给出带理由的建议（如"近期均为 fix/docs，建议 patch"）。减少用户的决策负担。

### 决策四：同时保留交互式脚本

有些场景用户希望不依赖 Claude、直接在终端操作（如 CI 脚本、习惯命令行的场景）。`tag-interactive.sh` 保留了完整的终端交互式体验，可复制到项目 `hack/` 目录独立使用。

---

## 功能一览

| 功能 | 说明 |
|------|------|
| 自动分析提交 | 读取自上个 tag 以来的提交列表 |
| 版本建议 | 根据提交内容建议 patch / minor / major，并说明理由 |
| 对话确认 | 在聊天中确认版本号，不需要切换终端 |
| Lightweight tag | 快速打标，适合内部节点 |
| Annotated tag | 带说明文字的正式 release，Claude 自动生成说明草稿 |
| 创建并推送 | 确认后自动执行 `git tag` + `git push origin` |
| 列出历史 tag | 展示最近 10 个 tag，标注类型（lightweight / annotated） |
| 删除 tag | 删除本地 + 远端，删前对话确认 |
| 直接指定版本 | 说"打 v2.0.0"直接跳过建议步骤 |

---

## 如何使用

### 触发方式

在任意项目目录里，对 Claude 说：

```
打个 tag
发版
升个 minor
打 v1.5.0
列出最近的 tag
删除 tag v0.1.0
打个带说明的 tag
```

或使用斜杠命令：`/tag`

### 典型对话流程

**Lightweight tag（日常发版）：**

```
用户：打个 tag

Claude：
  当前最新 tag：v0.3.1
  距上次发版：4 条提交

    abc1234 fix(auth): 修复登录超时
    def5678 docs: 更新 README

  建议：patch → v0.3.2（均为 bug fix 和文档）
  确认吗？

用户：确认

Claude：
  ✓ 已创建并推送 lightweight tag: v0.3.2 → origin
```

**Annotated tag（正式 release）：**

```
用户：升个 minor，打个带说明的 tag

Claude：
  当前最新 tag：v0.3.2，建议 minor → v0.4.0

  自动生成说明草稿：
    Release v0.4.0 - 新增短信验证码登录，优化权限管理模块

  使用此说明还是修改？

用户：改成"新增短信登录功能，修复若干认证问题"

Claude：
  确认打 v0.4.0（annotated），说明：新增短信登录功能，修复若干认证问题？

用户：确认

Claude：
  ✓ 已创建并推送 annotated tag: v0.4.0 → origin
    说明：新增短信登录功能，修复若干认证问题
```

### 内置脚本说明

Skill 附带两个脚本，功能互补：

| 脚本 | 定位 |
|------|------|
| `scripts/tag.sh` | 非交互式引擎，供 Claude 调用 |
| `scripts/tag-interactive.sh` | 完整交互式脚本，供用户直接使用或复制到项目 |

**`tag.sh`（非交互式）** 可直接在命令行调用：

```bash
bash ~/.claude/skills/tag/scripts/tag.sh info                        # 查看当前状态
bash ~/.claude/skills/tag/scripts/tag.sh list                        # 列出最近 tag（含类型）
bash ~/.claude/skills/tag/scripts/tag.sh create v1.2.3               # lightweight tag
bash ~/.claude/skills/tag/scripts/tag.sh create v1.2.3 "说明文字"    # annotated tag
bash ~/.claude/skills/tag/scripts/tag.sh push v1.2.3
bash ~/.claude/skills/tag/scripts/tag.sh delete v0.1.0
```

**`tag-interactive.sh`（交互式）** 可复制到项目 `hack/` 目录独立使用：

```bash
# 复制到项目
cp ~/.claude/skills/tag/scripts/tag-interactive.sh hack/tag.sh
chmod +x hack/tag.sh

# 使用
bash hack/tag.sh                      # patch +1，lightweight
bash hack/tag.sh minor                # minor +1
bash hack/tag.sh v1.5.0               # 指定版本
bash hack/tag.sh --annotated          # patch +1，annotated（交互输入说明）
bash hack/tag.sh minor --annotated    # minor +1，annotated
bash hack/tag.sh --list               # 列出最近 tag（含类型）
bash hack/tag.sh --delete v0.1.0      # 删除 tag
```

---

## 注意事项与限制

### 必须在 git 仓库目录中
Skill 直接运行 `git` 命令，当前工作目录必须是 git 仓库根目录或其子目录。

### 需要配置远端 origin
`push` 步骤要求仓库有名为 `origin` 的远端。如果没有，push 会失败，Claude 会提示只创建本地 tag。

### 版本建议基于 Conventional Commits 风格
分析提交时，Claude 根据 `fix:` / `feat:` / `BREAKING CHANGE` 等前缀推断版本类型。如果团队不使用 Conventional Commits，建议仍有参考价值，但准确度会下降。

### tag 命名约定
本 skill 只处理 `vX.Y.Z` 格式的项目 tag。本仓库同时存在框架 tag（`fw/vX.Y.Z`）的场景下，`info` 命令用 `--match 'v[0-9]*'` 过滤，不会受框架 tag 干扰。

### 删除是不可逆操作
删除远端 tag 后，其他人已经 `fetch` 的 tag 不会自动消失。删除前务必确认。

---

## 优势与劣势评价

### 优势

- **减少上下文切换**：不需要开终端、查命令、手敲，在对话里完成全流程
- **带理由的建议**：不只告诉你"选哪个"，还告诉你"为什么"，帮助决策
- **自动生成 annotated tag 说明**：Claude 读取提交列表后草拟说明，用户只需微调
- **通用**：不依赖项目内的任何脚本，在任意 git 仓库都能用
- **安全**：push 前对话确认，删除前也要确认，不会误操作

### 劣势

- **无法批量操作**：一次只能打一个 tag
- **版本建议不总是准确**：如果提交信息写得随意（没有规范前缀），建议会失准，需要用户自己判断
- **依赖 Bash 工具权限**：Claude 需要有执行 `git` 命令的权限，在严格的权限模式下需要用户手动批准每条命令

### 与直接手工操作相比

| | 手工打 tag | tag skill |
|---|---|---|
| 项目依赖 | 无 | 无（通用） |
| 查上一个 tag | 手动 `git tag --sort=...` | 自动读取 |
| 决定升哪位 | 靠记忆和经验 | Claude 分析后给建议 |
| Annotated 说明 | 手写 | Claude 草拟，用户微调 |
| 交互方式 | 终端命令 | 对话 + 自动执行 |
| 适用范围 | 任意 git 仓库 | 任意 git 仓库 |
