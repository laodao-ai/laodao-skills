#!/usr/bin/env bash
# setup-gstack.sh — 跨机器 clone 主仓后的 gstack 反向软链恢复脚本
#
# 由 ~/.claude/skills/laodao-skills/gstack-init/ 部署到主仓 scripts/setup-gstack.sh
# clone 后在新机器跑一次：bash scripts/setup-gstack.sh
#
# 这个脚本做一件事：在 ~/.gstack/projects/<slug> 重建指向主仓 .gstack/project 的软链，
# 让 gstack 内部的 home 路径访问能透明落到主仓内的真实目录。
#
# 不跑这个脚本的后果：第一次跑 gstack 任何 skill 时，gstack 会在 ~/.gstack/projects/<slug>
# 重新 mkdir 一个空目录，然后把新 design doc 写到那个空目录里——主仓内的旧 design doc
# 就跟它失联了（沉默的数据分叉，最难调试的那种）。

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GSTACK_HOME="${GSTACK_HOME:-$HOME/.gstack}"
GSTACK_BIN="$HOME/.claude/skills/gstack/bin"

# 前置检查
[ -d "$REPO_ROOT/.gstack/project" ] || {
  echo "ERROR: $REPO_ROOT/.gstack/project not found." >&2
  echo "       This repo wasn't initialized for gstack mode D, or .gstack/ wasn't cloned." >&2
  echo "       If you need to set up mode D from scratch:" >&2
  echo "         /Users/$USER/.claude/skills/laodao-skills/gstack-init/scripts/gstack-init.sh apply-d" >&2
  exit 1
}

if [ ! -x "$GSTACK_BIN/gstack-slug" ]; then
  echo "ERROR: gstack not installed at $GSTACK_BIN" >&2
  echo "       Install it first: cd ~/.claude/skills/gstack && ./setup" >&2
  exit 1
fi

# 取 slug
SLUG=$(cd "$REPO_ROOT" && "$GSTACK_BIN/gstack-slug" 2>/dev/null | awk -F= '/^SLUG=/{print $2}')
[ -n "$SLUG" ] || {
  echo "ERROR: gstack-slug returned empty (no git remote? wrong cwd?)" >&2
  exit 1
}

HOME_PATH="$GSTACK_HOME/projects/$SLUG"

mkdir -p "$(dirname "$HOME_PATH")"

# 4 种状态分别处理
if [ -L "$HOME_PATH" ]; then
  EXISTING=$(readlink "$HOME_PATH")
  if [ "$EXISTING" = "$REPO_ROOT/.gstack/project" ]; then
    echo "✓ Reverse symlink already correct: $HOME_PATH"
    echo "  → $EXISTING"
    exit 0
  fi
  echo "Existing symlink points elsewhere: $EXISTING"
  echo "Replacing with correct target..."
  rm "$HOME_PATH"
elif [ -d "$HOME_PATH" ]; then
  echo "ERROR: $HOME_PATH is a real directory (not a symlink)." >&2
  echo "       This usually means a gstack skill was run before this setup script," >&2
  echo "       which auto-mkdir'd the home path." >&2
  echo "" >&2
  echo "  Inspect contents:" >&2
  echo "    ls -la \"$HOME_PATH\"" >&2
  echo "" >&2
  echo "  If empty or only has stale data, remove and re-run this script:" >&2
  echo "    rm -rf \"$HOME_PATH\"" >&2
  echo "    bash $0" >&2
  echo "" >&2
  echo "  If it has work you want to keep, manually merge into $REPO_ROOT/.gstack/project/" >&2
  echo "  before removing." >&2
  exit 1
fi

ln -s "$REPO_ROOT/.gstack/project" "$HOME_PATH"

echo "✓ Reverse symlink created"
echo "  $HOME_PATH"
echo "  → $REPO_ROOT/.gstack/project"
echo ""
echo "Next: run any gstack skill (/health, /office-hours, etc.) — files will land in repo automatically."
