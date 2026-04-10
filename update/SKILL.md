---
name: ld-update
description: |
  更新 laodao-skills 到最新版本。执行 git pull 拉取更新，运行 setup.sh 安装，
  显示版本号和最新变更日志。当用户说"更新 laodao skills"、"ld-update"、
  "update laodao skills"、"更新自建 skill"，或使用 /ld-update 时触发。
allowed-tools:
  - Bash
  - Read
---

# /ld-update

更新 laodao-skills 到最新版本。

## 执行步骤

### Step 1: 定位仓库

```bash
# 尝试通过 symlink 或已知路径定位
REPO_DIR=""
if [ -d "$HOME/.claude/skills/laodao-skills" ]; then
  REPO_DIR="$HOME/.claude/skills/laodao-skills"
fi
```

如果找不到仓库目录，提示用户先安装：
```
cd ~/.claude/skills
git clone https://github.com/laodao-ai/laodao-skills.git
cd laodao-skills && bash setup.sh
```

### Step 2: 拉取更新

```bash
cd "$REPO_DIR"
git fetch origin
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)
```

如果 `$LOCAL` == `$REMOTE`，告诉用户"已是最新版本"并显示当前版本号，然后结束。

否则：
```bash
git pull origin main
```

显示更新的 commit 摘要（`git log $LOCAL..HEAD --oneline`）。

如果 git pull 失败（网络问题或冲突），显示错误信息并提示用户手动解决。

### Step 3: 运行 setup.sh

```bash
bash "$REPO_DIR/setup.sh"
```

展示 setup.sh 的输出。

### Step 4: 显示版本和变更日志

读取 `$REPO_DIR/VERSION` 显示当前版本号。

读取 `$REPO_DIR/CHANGELOG.md`，提取最新版本块（从第一个 `## ` 到第二个 `## ` 之间的内容），展示给用户。

输出格式：
```
✓ laodao-skills 已更新到 v<版本号>

最新变更：
<CHANGELOG 最新版本块内容>
```
