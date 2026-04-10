#!/usr/bin/env bash
# laodao-skills setup — install/update skills into ~/.claude/skills/
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_NAME="$(basename "$REPO_DIR")"
SKILLS_DIR="$(dirname "$REPO_DIR")"

# Platform detection
IS_WINDOWS=0
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*|Windows_NT) IS_WINDOWS=1 ;;
esac

# Counters
installed=()
skipped=()
cleaned=()

# ─── Install skills ──────────────────────────────────────────
for skill_dir in "$REPO_DIR"/*/; do
  [ -f "$skill_dir/SKILL.md" ] || continue
  skill_name="$(basename "$skill_dir")"
  target="$SKILLS_DIR/$skill_name"

  if [ "$IS_WINDOWS" -eq 1 ]; then
    # Windows: copy + marker file
    if [ -d "$target" ] && [ ! -f "$target/.laodao-skills" ] && [ ! -L "$target" ]; then
      skipped+=("$skill_name")
      continue
    fi
    # Remove old copy if it's ours
    if [ -d "$target" ] && [ -f "$target/.laodao-skills" ]; then
      rm -rf "$target"
    fi
    cp -r "$skill_dir" "$target"
    git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null > "$target/.laodao-skills" || echo "unknown" > "$target/.laodao-skills"
    installed+=("$skill_name")
  else
    # Unix: relative symlink
    if [ -e "$target" ] && [ ! -L "$target" ]; then
      # Real directory, not a symlink — check if it's our marker copy
      if [ -f "$target/.laodao-skills" ]; then
        rm -rf "$target"
      else
        skipped+=("$skill_name")
        continue
      fi
    fi
    ln -snf "$REPO_NAME/$skill_name" "$target"
    installed+=("$skill_name")
  fi
done

# ─── Orphan cleanup ──────────────────────────────────────────
for entry in "$SKILLS_DIR"/*/; do
  entry_name="$(basename "$entry")"
  [ "$entry_name" = "$REPO_NAME" ] && continue

  is_ours=0

  # Check symlink pointing to our repo
  if [ -L "$SKILLS_DIR/$entry_name" ]; then
    link_dest="$(readlink "$SKILLS_DIR/$entry_name" 2>/dev/null || true)"
    case "$link_dest" in
      "$REPO_NAME"/*|*/"$REPO_NAME"/*) is_ours=1 ;;
    esac
  fi

  # Check marker file (Windows copies)
  if [ -f "$entry/.laodao-skills" ]; then
    is_ours=1
  fi

  # If it's ours but the source no longer exists, clean up
  if [ "$is_ours" -eq 1 ] && [ ! -d "$REPO_DIR/$entry_name" ]; then
    rm -rf "$SKILLS_DIR/$entry_name"
    cleaned+=("$entry_name")
  fi
done

# ─── Summary ─────────────────────────────────────────────────
version="$(cat "$REPO_DIR/VERSION" 2>/dev/null || echo "unknown")"
echo ""
echo "laodao-skills v${version} ready."
echo ""

if [ ${#installed[@]} -gt 0 ]; then
  echo "  installed (${#installed[@]}):"
  for s in "${installed[@]}"; do echo "    ✓ $s"; done
fi

if [ ${#skipped[@]} -gt 0 ]; then
  echo ""
  echo "  skipped (${#skipped[@]}):"
  for s in "${skipped[@]}"; do echo "    ⚠ $s — already exists, not managed by laodao-skills"; done
fi

if [ ${#cleaned[@]} -gt 0 ]; then
  echo ""
  echo "  cleaned orphans (${#cleaned[@]}):"
  for s in "${cleaned[@]}"; do echo "    ✗ $s"; done
fi

if [ "$IS_WINDOWS" -eq 1 ]; then
  echo ""
  echo "  mode: copy (Windows)"
else
  echo ""
  echo "  mode: symlink (Unix)"
fi
