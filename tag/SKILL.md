---
name: tag
description: >
  在任意 Git 仓库中打语义化版本 tag（SemVer）并推送到远端。
  支持 patch/minor/major 自动递增、直接指定版本号、查看历史 tag、删除 tag。
  当用户说"打 tag"、"打版本标签"、"发版"、"发布版本"、"tag 一下"、"给代码打标签"、
  "release"、"升版本"、"打个 patch/minor/major"，或使用 /tag 时，必须触发此 skill。
---

# Git 版本 Tag Skill

> **推荐模型**：本 skill 逻辑简单（规则明确的执行类任务），使用 **Haiku** 即可，速度更快、成本更低。
> Skill 本身无法指定模型，请在触发前用 `/model` 切换到 Haiku。

## 工具脚本

本 skill 附带两个脚本，用途不同：

| 脚本 | 用途 | 使用者 |
|------|------|--------|
| `scripts/tag.sh` | 非交互式引擎，拆分为子命令 | Claude 通过 Bash 工具调用 |
| `scripts/tag-interactive.sh` | 完整交互式脚本（含终端确认） | 用户直接在终端运行，或复制到项目 `hack/` 目录 |

> 在 Claude Code 中，skill 路径为 `~/.claude/skills/tag/scripts/`。

### 用户想把脚本复制到项目时

如果用户说"把 tag 脚本放到我的项目里"或"我想直接在终端打 tag"，复制交互式版本：

```bash
cp ~/.claude/skills/tag/scripts/tag-interactive.sh hack/tag.sh
chmod +x hack/tag.sh
```

用法：
```bash
bash hack/tag.sh           # patch +1（默认）
bash hack/tag.sh minor     # minor +1
bash hack/tag.sh major     # major +1
bash hack/tag.sh v1.5.0    # 直接指定版本
bash hack/tag.sh --list    # 列出最近 tag
bash hack/tag.sh --delete v0.1.0  # 删除 tag
```

---

## 工作流程

### 第一步：读取仓库状态

运行以下命令获取上下文（在**用户当前工作目录**中执行）：

```bash
bash ~/.claude/skills/tag/scripts/tag.sh info
```

输出格式：
```
latest_tag=v0.3.1
commit_count=4
next_patch=v0.3.2
next_minor=v0.4.0
next_major=v1.0.0
---commits---
abc1234 fix(auth): 修复登录超时问题
def5678 docs: 更新 README
```

同时可选运行查看历史：
```bash
bash ~/.claude/skills/tag/scripts/tag.sh list
```

### 第二步：分析并建议版本

根据提交内容给出建议，说明理由：

| 情况 | 建议 |
|------|------|
| 仅 fix/docs/chore/refactor | patch |
| 新增功能、新 API（向下兼容） | minor |
| Breaking change、不兼容变更 | major |

向用户展示：
```
当前最新 tag：v0.3.1
距上次发版：4 条提交

  abc1234 fix(auth): 修复登录超时问题
  def5678 docs: 更新 README

建议：patch → v0.3.2（均为 bug fix 和文档）
也可升 minor → v0.4.0 或 major → v1.0.0

确认打 v0.3.2 吗？（或告诉我你想要的版本）
```

### 第三步：用户确认（含 tag 类型选择）

等待用户在对话中确认版本号。根据版本类型决定默认行为：

| 版本类型 | 默认行为 |
|---------|---------|
| patch | lightweight（无需说明，直接打） |
| minor | **annotated（需要说明文字，自动生成草稿请用户确认）** |
| major | **annotated（需要说明文字，自动生成草稿请用户确认）** |

- 用户确认 minor / major 版本后，**不要立即打 tag**，先自动根据提交列表生成说明草稿展示给用户
- 用户明确说"不用说明"、"lightweight"时，minor / major 也可跳过
- patch 若用户主动说"加说明"，则进入 annotated 流程

**不要在未经确认的情况下直接打 tag 或 push。**

### 第四步：执行打标签

**Lightweight tag（patch 默认，或用户明确要求）：**

```bash
bash ~/.claude/skills/tag/scripts/tag.sh create v0.3.2
bash ~/.claude/skills/tag/scripts/tag.sh push v0.3.2
```

**Annotated tag（minor / major 默认）：**

用户确认版本号后，先根据提交列表自动生成说明草稿，展示给用户确认或修改：

```
建议说明文字：
  Release v0.4.0 - 新增用户权限模块，优化登录流程

直接使用还是修改？
```

用户确认后：

```bash
# 说明文字通过第三个参数传入（如含空格需加引号）
bash ~/.claude/skills/tag/scripts/tag.sh create v0.4.0 "Release v0.4.0 - 新增用户权限模块，优化登录流程"
bash ~/.claude/skills/tag/scripts/tag.sh push v0.4.0
```

执行后告知用户结果及 tag 类型，例如：
```
✓ 已创建并推送 annotated tag: v0.4.0 → origin
  说明：Release v0.4.0 - 新增用户权限模块，优化登录流程
```

---

## 其他操作

### 列出最近 tag

```bash
bash ~/.claude/skills/tag/scripts/tag.sh list
```

### 删除 tag

用户说"删除 tag v0.1.0"时，**必须先确认**再执行（删除远端 tag 不可逆）：

```
即将删除 tag: v0.1.0（本地 + 远端 origin）
确认删除吗？
```

用户确认后：
```bash
bash ~/.claude/skills/tag/scripts/tag.sh delete v0.1.0
```

### 直接指定版本

用户说"打 v2.0.0"时，跳过版本建议步骤，直接确认后执行。

---

## 注意事项

- 始终在**用户的项目目录**（当前工作目录）中执行 git 命令
- push 之前必须先在对话中得到用户明确确认
- 如果仓库没有 remote `origin`，告知用户 push 会失败，询问是否只创建本地 tag
- 项目若有自己的 `hack/tag.sh`，可告知用户两种方式都可以，本 skill 是通用替代
