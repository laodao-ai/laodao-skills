#!/usr/bin/env bash
# gstack-init.sh — 项目级 gstack 文档归集引擎
#
# 把 ~/.gstack/projects/<slug>/ 接入主仓 .gstack/project/，让 design docs (*.md)
# 可以被 git 追踪，同时 gstack 内部完全无感（通过反向软链）。
#
# 子命令：
#   detect              输出当前状态（KEY=VALUE 形式，可 eval）
#   apply-d             方案 D：反向软链（推荐）
#   apply-a             方案 A：cp 副本到指定路径（手动归档模式）
#   restore             clone 后重建反向软链
#   write-gitignore     智能合并 .gitignore negate 规则
#   write-setup-script  在主仓写 scripts/setup-gstack.sh 给跨机器恢复
#   verify              跑全套验证
#   help                显示用法
#
# 设计原则：
#   - 幂等：重复跑不会破坏既有状态
#   - 边界处理：能识别 home/repo 路径的 4 种状态（none/dir/symlink/wrong-target）
#   - 不破坏数据：移动目录前必检查目标位置不存在或为空，否则 abort

set -euo pipefail

GSTACK_BIN="$HOME/.claude/skills/gstack/bin"
GSTACK_HOME="${GSTACK_HOME:-$HOME/.gstack}"
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"

# ---------------------------------------------------------------------------
# 辅助：检测当前状态
# ---------------------------------------------------------------------------
_detect() {
  local repo_root slug home_path repo_path home_kind home_target repo_kind mode

  repo_root=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "ERROR: not in a git repo (cwd=$PWD)" >&2
    return 1
  }

  if [ ! -x "$GSTACK_BIN/gstack-slug" ]; then
    echo "ERROR: gstack-slug binary not found at $GSTACK_BIN/gstack-slug" >&2
    echo "       Did you install gstack? See ~/.claude/skills/gstack/" >&2
    return 1
  fi

  slug=$(cd "$repo_root" && "$GSTACK_BIN/gstack-slug" 2>/dev/null | awk -F= '/^SLUG=/{print $2}')
  [ -n "$slug" ] || { echo "ERROR: gstack-slug returned empty" >&2; return 1; }

  home_path="$GSTACK_HOME/projects/$slug"
  repo_path="$repo_root/.gstack/project"

  if [ -L "$home_path" ]; then
    home_kind=symlink
    home_target=$(readlink "$home_path")
  elif [ -d "$home_path" ]; then
    home_kind=dir
    home_target=""
  else
    home_kind=none
    home_target=""
  fi

  if [ -L "$repo_path" ]; then
    repo_kind=symlink
  elif [ -d "$repo_path" ]; then
    repo_kind=dir
  else
    repo_kind=none
  fi

  # 推断当前 mode
  if [ "$home_kind" = symlink ] && [ "$home_target" = "$repo_path" ] && [ "$repo_kind" = dir ]; then
    mode=D
  elif [ "$home_kind" = dir ] && [ "$repo_kind" = symlink ]; then
    mode=Dpre  # 旧的"正向软链"中间状态（office-hours 期间临时方案）
  elif [ "$home_kind" = dir ] && [ "$repo_kind" = none ]; then
    mode=none  # gstack 默认状态：home 真实目录，主仓未引入
  elif [ "$home_kind" = none ] && [ "$repo_kind" = none ]; then
    mode=fresh  # 全新项目，gstack 从未跑过
  else
    mode=unknown
  fi

  cat <<EOF
REPO_ROOT=$repo_root
SLUG=$slug
HOME_PATH=$home_path
REPO_PATH=$repo_path
HOME_KIND=$home_kind
HOME_TARGET=$home_target
REPO_KIND=$repo_kind
MODE=$mode
EOF
}

# ---------------------------------------------------------------------------
# 子命令：detect
# ---------------------------------------------------------------------------
cmd_detect() {
  _detect
}

# ---------------------------------------------------------------------------
# 子命令：apply-d
# ---------------------------------------------------------------------------
cmd_apply_d() {
  local state mode repo_path home_path
  state=$(_detect) || return 1
  eval "$state"

  case "$MODE" in
    D)
      echo "✓ Already mode D, nothing to do."
      echo "  $HOME_PATH → $REPO_PATH"
      return 0
      ;;
    Dpre)
      # 主仓是旧"正向软链"，home 是真实目录 → 反过来
      echo "Detected pre-D state (forward symlink). Converting to true mode D..."
      rm "$REPO_PATH"
      mv "$HOME_PATH" "$REPO_PATH"
      ln -s "$REPO_PATH" "$HOME_PATH"
      ;;
    none)
      # home 是真实目录，主仓还没建
      echo "Moving real directory from home to repo, creating reverse symlink..."
      mkdir -p "$REPO_ROOT/.gstack"
      mv "$HOME_PATH" "$REPO_PATH"
      ln -s "$REPO_PATH" "$HOME_PATH"
      ;;
    fresh)
      # 全新项目，home/repo 都不存在
      echo "Fresh project — creating empty .gstack/project + reverse symlink..."
      mkdir -p "$REPO_ROOT/.gstack" "$(dirname "$HOME_PATH")"
      mkdir -p "$REPO_PATH"
      ln -s "$REPO_PATH" "$HOME_PATH"
      ;;
    *)
      echo "ERROR: unknown / ambiguous state (MODE=$MODE)" >&2
      echo "  HOME_KIND=$HOME_KIND  REPO_KIND=$REPO_KIND" >&2
      echo "  Manual inspection required." >&2
      return 1
      ;;
  esac

  echo ""
  echo "✓ mode D applied:"
  echo "  Repo:  $REPO_PATH (real directory)"
  echo "  Home:  $HOME_PATH → $REPO_PATH (reverse symlink)"
}

# ---------------------------------------------------------------------------
# 子命令：apply-a
# ---------------------------------------------------------------------------
cmd_apply_a() {
  local target="${1:-}"
  if [ -z "$target" ]; then
    echo "Usage: gstack-init.sh apply-a <target-path>" >&2
    echo "  e.g. apply-a openspec/changes/<change>/gstack-design.md" >&2
    return 1
  fi

  local state
  state=$(_detect) || return 1
  eval "$state"

  if [ "$HOME_KIND" != dir ]; then
    echo "ERROR: $HOME_PATH not a real directory (kind=$HOME_KIND)" >&2
    echo "  Mode A copies from a real source dir; current state requires apply-d or restore first." >&2
    return 1
  fi

  # 找最新的 design doc
  local newest
  newest=$(ls -t "$HOME_PATH"/*-design-*.md 2>/dev/null | head -1)
  [ -n "$newest" ] || { echo "ERROR: no design doc found in $HOME_PATH" >&2; return 1; }

  local target_full="$REPO_ROOT/$target"
  mkdir -p "$(dirname "$target_full")"
  cp "$newest" "$target_full"
  echo "✓ Copied: $newest → $target_full"
}

# ---------------------------------------------------------------------------
# 子命令：restore (clone 后重建反向软链)
# ---------------------------------------------------------------------------
cmd_restore() {
  local state
  state=$(_detect) || return 1
  eval "$state"

  if [ "$REPO_KIND" != dir ]; then
    echo "ERROR: $REPO_PATH not a directory. Did you clone the repo and is mode D set up?" >&2
    return 1
  fi

  case "$HOME_KIND" in
    symlink)
      if [ "$HOME_TARGET" = "$REPO_PATH" ]; then
        echo "✓ Reverse symlink already correct: $HOME_PATH → $REPO_PATH"
        return 0
      fi
      echo "Existing symlink points to $HOME_TARGET, replacing..."
      rm "$HOME_PATH"
      ;;
    dir)
      echo "ERROR: $HOME_PATH is a real directory (not a symlink)." >&2
      echo "  Possible causes:" >&2
      echo "  - You ran a gstack skill before this restore script (it auto-mkdir'd)" >&2
      echo "  - Old gstack data from another setup" >&2
      echo "  Inspect contents and decide whether to remove or merge:" >&2
      echo "    ls -la $HOME_PATH" >&2
      return 1
      ;;
    none)
      ;;  # ok, 直接创建
  esac

  mkdir -p "$(dirname "$HOME_PATH")"
  ln -s "$REPO_PATH" "$HOME_PATH"
  echo "✓ Reverse symlink restored: $HOME_PATH → $REPO_PATH"
}

# ---------------------------------------------------------------------------
# 子命令：write-gitignore
# ---------------------------------------------------------------------------
cmd_write_gitignore() {
  local state
  state=$(_detect) || return 1
  eval "$state"

  local gitignore="$REPO_ROOT/.gitignore"

  if grep -qF '!.gstack/project/*.md' "$gitignore" 2>/dev/null; then
    echo "✓ .gitignore already has gstack negate pattern, skipping"
    return 0
  fi

  # 如果存在裸的 .gstack/ 行，替换它；否则追加
  if grep -qE '^\.gstack/$' "$gitignore" 2>/dev/null; then
    local tmp
    tmp=$(mktemp)
    awk '
      /^\.gstack\/$/ {
        print "# gstack 工作目录：默认全部忽略，但允许项目级 design docs (*.md) 入库"
        print "# .gstack/project/ 是 ~/.gstack/projects/<slug>/ 的反向软链物理目录"
        print "# 跨机器 clone 后用 scripts/setup-gstack.sh 重建反向软链"
        print ".gstack/*"
        print "!.gstack/project/"
        print ".gstack/project/*"
        print "!.gstack/project/*.md"
        next
      }
      { print }
    ' "$gitignore" > "$tmp"
    mv "$tmp" "$gitignore"
    echo "✓ Replaced bare .gstack/ rule with negate pattern"
  else
    cat >> "$gitignore" <<'EOF'

# gstack 工作目录：允许 design docs (*.md) 入库，其它 ignore
# .gstack/project/ 是 ~/.gstack/projects/<slug>/ 的反向软链物理目录
.gstack/*
!.gstack/project/
.gstack/project/*
!.gstack/project/*.md
EOF
    echo "✓ Appended gstack negate pattern to .gitignore"
  fi
}

# ---------------------------------------------------------------------------
# 子命令：write-setup-script
# ---------------------------------------------------------------------------
cmd_write_setup_script() {
  local state
  state=$(_detect) || return 1
  eval "$state"

  local script_dir="$REPO_ROOT/scripts"
  local script="$script_dir/setup-gstack.sh"

  mkdir -p "$script_dir"
  if [ -f "$script" ]; then
    echo "✓ $script already exists, skipping"
    return 0
  fi

  if [ -f "$SKILL_DIR/setup-gstack.sh" ]; then
    cp "$SKILL_DIR/setup-gstack.sh" "$script"
  else
    echo "ERROR: template $SKILL_DIR/setup-gstack.sh not found" >&2
    return 1
  fi

  chmod +x "$script"
  echo "✓ Wrote $script (run after clone on a new machine to restore reverse symlink)"
}

# ---------------------------------------------------------------------------
# 子命令：verify
# ---------------------------------------------------------------------------
cmd_verify() {
  local state
  state=$(_detect) || return 1
  eval "$state"

  echo "=== Detected state ==="
  echo "$state" | sed 's/^/  /'
  echo ""

  if [ "$MODE" != D ]; then
    echo "✗ Not in mode D (current: $MODE)" >&2
    return 1
  fi

  # gstack 仍能正常工作
  "$GSTACK_BIN/gstack-slug" >/dev/null 2>&1 || { echo "✗ gstack-slug failed" >&2; return 1; }
  "$GSTACK_BIN/gstack-paths" >/dev/null 2>&1 || { echo "✗ gstack-paths failed" >&2; return 1; }
  echo "✓ gstack-slug + gstack-paths work"

  # 通过 home 路径写入能落到主仓
  local test_file="$HOME_PATH/.gstack-init-verify-$$"
  touch "$test_file"
  if [ -f "$REPO_PATH/$(basename "$test_file")" ]; then
    rm -f "$test_file"
    echo "✓ Reverse symlink writes pass through to repo"
  else
    rm -f "$test_file"
    echo "✗ Writing via home path didn't reach repo" >&2
    return 1
  fi

  # gitignore 规则正确（cd 进 repo 才能用 git check-ignore）
  cd "$REPO_ROOT"

  if git check-ignore -q .gstack/project/foo.md 2>/dev/null; then
    echo "✗ .md files are still ignored — .gitignore negate pattern not working" >&2
    return 1
  else
    echo "✓ .md files NOT ignored (as expected)"
  fi

  if git check-ignore -q .gstack/project/timeline.jsonl 2>/dev/null; then
    echo "✓ jsonl files ignored (as expected)"
  else
    echo "✗ jsonl noise files are NOT ignored — .gitignore needs review" >&2
    return 1
  fi

  echo ""
  echo "✓ All verifications passed."
}

# ---------------------------------------------------------------------------
# 子命令：help
# ---------------------------------------------------------------------------
cmd_help() {
  cat <<'USAGE'
gstack-init.sh — 项目级 gstack 文档归集

Usage: gstack-init.sh <subcommand> [args]

Subcommands:
  detect              探测当前 mode（输出 KEY=VALUE，可 eval）
  apply-d             执行方案 D：反向软链（推荐）
  apply-a <path>      执行方案 A：cp 最新 design doc 到指定相对路径
  restore             clone 后在新机器重建反向软链
  write-gitignore     智能写入 .gitignore negate 规则
  write-setup-script  在主仓 scripts/ 写 setup-gstack.sh
  verify              跑全套验证
  help                显示此说明

典型使用流（新项目首次配置）：
  $ cd /path/to/your-project
  $ gstack-init.sh apply-d
  $ gstack-init.sh write-gitignore
  $ gstack-init.sh write-setup-script
  $ gstack-init.sh verify

跨机器 clone 后：
  $ cd /path/to/your-project
  $ scripts/setup-gstack.sh   # 或 gstack-init.sh restore
USAGE
}

# ---------------------------------------------------------------------------
# 主路由
# ---------------------------------------------------------------------------
main() {
  local cmd="${1:-help}"
  shift || true

  case "$cmd" in
    detect)              cmd_detect "$@" ;;
    apply-d)             cmd_apply_d "$@" ;;
    apply-a)             cmd_apply_a "$@" ;;
    restore)             cmd_restore "$@" ;;
    write-gitignore)     cmd_write_gitignore "$@" ;;
    write-setup-script)  cmd_write_setup_script "$@" ;;
    verify)              cmd_verify "$@" ;;
    help|--help|-h)      cmd_help ;;
    *)
      echo "Unknown subcommand: $cmd" >&2
      cmd_help >&2
      exit 1
      ;;
  esac
}

main "$@"
