#!/usr/bin/env bash
# laodao-skills setup — install/update skills into BOTH:
#   - Claude  ~/.claude/skills/
#   - Codex / Cursor   ~/.agents/skills/
# Idempotent. Unix: absolute symlink (layout-independent). Windows: copy + marker.
# Legacy ~/.codex/skills installs are migrated away after the new destination is live.
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_NAME="$(basename "$REPO_DIR")"

# Install destinations (explicit + absolute → independent of where the repo lives)
TARGET_DIRS=("$HOME/.claude/skills" "$HOME/.agents/skills")

# Platform detection
IS_WINDOWS=0
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*|Windows_NT) IS_WINDOWS=1 ;;
esac

# Counters (entries formatted "skill @ dest")
installed=()
skipped=()
cleaned=()

# These skills moved from sdflow-skills. Only these names may take over an
# existing sdflow-owned link or Windows marker copy; other foreign installs
# remain protected.
MIGRATED_SKILL_NAMES=" embedded-test-sop "
is_migrated_skill() {  # $1 = skill name
  case "$MIGRATED_SKILL_NAMES" in *" $1 "*) return 0 ;; esac
  return 1
}

is_our_marker_copy() {  # $1 = target directory
  local entry="$1" name
  name="$(basename "$entry")"
  [ -f "$entry/.laodao-skills" ] && return 0
  is_migrated_skill "$name" && [ -f "$entry/.sdflow-skills" ] && return 0
  return 1
}

# Content fingerprint: does this absolute path sit inside a laodao-skills checkout?
# Needed when the checkout directory is not literally named `laodao-skills`
# (e.g. a named worktree) so ownership checks stay symmetric across checkouts.
is_our_checkout_path() {  # $1 = readlink target
  local p="$1" d i=0
  [ -n "$p" ] || return 1
  case "$p" in /*) ;; *) return 1 ;; esac
  d="$p"
  while [ "$d" != "/" ] && [ -n "$d" ] && [ "$i" -lt 8 ]; do
    if [ -f "$d/setup.sh" ] && [ -f "$d/laodao-upgrade/SKILL.md" ]; then
      return 0
    fi
    d="$(dirname "$d")"
    i=$((i + 1))
  done
  return 1
}

is_ours_symlink() {  # $1 = target path, $2 = skill name
  local link_dest
  link_dest="$(readlink "$1" 2>/dev/null || true)"
  case "$link_dest" in
    "$REPO_NAME"/*|*/"$REPO_NAME"/*|*/laodao-skills/*|laodao-skills/*)
      return 0
      ;;
  esac

  if is_our_checkout_path "$link_dest"; then
    return 0
  fi

  if is_migrated_skill "$2"; then
    case "$link_dest" in
      */sdflow-skills/"$2"|*/sdflow-skills/"$2"/*|*/04-sdflow-skills/"$2"|*/04-sdflow-skills/"$2"/*)
        return 0
        ;;
    esac
  fi
  return 1
}

# ─── Install all skills into one destination ─────────────────
install_into() {
  local dest="$1"
  mkdir -p "$dest"
  for skill_dir in "$REPO_DIR"/*/; do
    [ -f "$skill_dir/SKILL.md" ] || continue
    local skill_name target
    skill_name="$(basename "$skill_dir")"
    target="$dest/$skill_name"

    if [ "$IS_WINDOWS" -eq 1 ]; then
      # Windows: copy + marker file
      if [ -d "$target" ] && [ ! -L "$target" ] && ! is_our_marker_copy "$target"; then
        skipped+=("$skill_name @ $dest")
        continue
      fi
      if [ -d "$target" ] && is_our_marker_copy "$target"; then
        rm -rf "$target"
      fi
      cp -r "$skill_dir" "$target"
      git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null > "$target/.laodao-skills" || echo "unknown" > "$target/.laodao-skills"
      installed+=("$skill_name @ $dest")
    else
      # Unix: absolute symlink. Only ever replace symlinks or our own marker
      # copies — never clobber a real directory we don't own (e.g. another
      # tool's skill of the same name).
      if [ -e "$target" ] && [ ! -L "$target" ]; then
        if is_our_marker_copy "$target"; then
          rm -rf "$target"
        else
          skipped+=("$skill_name @ $dest")
          continue
        fi
      fi
      if [ -L "$target" ] && ! is_ours_symlink "$target" "$skill_name"; then
        skipped+=("$skill_name @ $dest — foreign symlink, not overwritten")
        continue
      fi
      local old_link=""
      if [ -L "$target" ]; then
        old_link="$(readlink "$target" 2>/dev/null || true)"
      fi
      ln -snf "$REPO_DIR/$skill_name" "$target"
      if [ -n "$old_link" ] && [ "$old_link" != "$REPO_DIR/$skill_name" ]; then
        installed+=("$skill_name @ $dest — took over $old_link")
      else
        installed+=("$skill_name @ $dest")
      fi
    fi
  done
}

# Confirm the new destination already has our install, then drop the legacy
# ~/.codex/skills copies. Same-name third-party entries are left alone.
cleanup_legacy_codex_skills() {
  local old="$HOME/.codex/skills" new="$HOME/.agents/skills"
  local entry name
  [ -d "$old" ] || return 0
  for entry in "$old"/*; do
    [ -e "$entry" ] || [ -L "$entry" ] || continue
    name="$(basename "$entry")"
    if [ -L "$new/$name" ]; then
      [ "$(readlink "$new/$name")" = "$REPO_DIR/$name" ] || continue
    elif ! is_our_marker_copy "$new/$name"; then
      continue
    fi
    if [ -L "$entry" ]; then
      is_ours_symlink "$entry" "$name" || continue
    elif ! is_our_marker_copy "$entry"; then
      continue
    fi
    if rm -rf "$entry"; then
      cleaned+=("$name @ $old — migrated to $new")
    else
      skipped+=("$name @ $old — legacy cleanup failed")
    fi
  done
}

# ─── Remove our orphaned links (source skill deleted) ────────
cleanup_orphans() {
  local dest="$1"
  [ -d "$dest" ] || return 0
  local entry
  while IFS= read -r entry; do
    [ -n "$entry" ] || continue
    local entry_name="$(basename "$entry")"
    [ "$entry_name" = "$REPO_NAME" ] && continue

    local is_ours=0
    # Symlink pointing into our repo (absolute or relative form)
    if [ -L "$dest/$entry_name" ]; then
      local link_dest
      link_dest="$(readlink "$dest/$entry_name" 2>/dev/null || true)"
      case "$link_dest" in
        "$REPO_NAME"/*|*/"$REPO_NAME"/*|*/laodao-skills/*|laodao-skills/*) is_ours=1 ;;
        *) is_our_checkout_path "$link_dest" && is_ours=1 ;;
      esac
    fi
    # Marker file (Windows copies)
    is_our_marker_copy "$entry" && is_ours=1

    # Ours, but no longer an installable skill → clean up.
    # Criterion mirrors install_into (dir must contain SKILL.md): a leftover
    # directory without SKILL.md must not keep a global install forever.
    # Probe SKILL.md through the link so valid nested sub-skills are kept.
    if [ "$is_ours" -eq 1 ]; then
      local gone=0
      if [ -L "$dest/$entry_name" ]; then
        if [ ! -e "$dest/$entry_name" ]; then
          gone=1                                        # dangling symlink
        elif [ ! -f "$dest/$entry_name/SKILL.md" ]; then
          gone=1                                        # resolves, but no longer a skill
        fi
      elif [ ! -f "$REPO_DIR/$entry_name/SKILL.md" ]; then
        gone=1                                          # Windows marker copy, source gone / no longer a skill
      fi
      if [ "$gone" -eq 1 ]; then
        rm -rf "$dest/$entry_name"
        cleaned+=("$entry_name @ $dest")
      fi
    fi
  done < <(find "$dest" -mindepth 1 -maxdepth 1)
}

for d in "${TARGET_DIRS[@]}"; do
  install_into "$d"
  cleanup_orphans "$d"
done
cleanup_legacy_codex_skills
# Sweep legacy root for our orphans that were never reinstalled under .agents
# (e.g. renamed/retired skills that still had ~/.codex/skills links).
cleanup_orphans "$HOME/.codex/skills"

# ─── Summary ─────────────────────────────────────────────────
version="$(git -C "$REPO_DIR" describe --tags --always --dirty 2>/dev/null || echo "unknown")"
echo ""
echo "laodao-skills ${version} ready → ${TARGET_DIRS[*]}"
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

echo ""
if [ "$IS_WINDOWS" -eq 1 ]; then
  echo "  mode: copy (Windows)"
else
  echo "  mode: symlink (Unix)"
fi
