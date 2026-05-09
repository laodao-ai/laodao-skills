#!/usr/bin/env python3
"""
config_setup.py — Claude Code project-level settings manager.

Manages enabledPlugins and skillOverrides across three settings layers:
  - Layer 3: <proj>/.claude/settings.local.json  (local override, highest precedence)
  - Layer 4: <proj>/.claude/settings.json        (project-shared)
  - Layer 5: <user>/.claude/settings.json        (user global)

Usage: python3 config_setup.py [options]
"""

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# Task 1: Three-layer settings file reading
# ============================================================

def read_layer(path: Path) -> dict:
    """
    Read a single settings JSON file.

    Returns a dict with keys 'enabledPlugins' and 'skillOverrides'.
    Missing file → both are empty dicts.
    Malformed JSON → sys.exit(1) with an error message.
    Missing fields → empty dicts for those fields.
    """
    if not path.exists():
        return {"enabledPlugins": {}, "skillOverrides": {}}

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"ERROR: {path} contains malformed JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    return {
        "enabledPlugins": data.get("enabledPlugins") or {},
        "skillOverrides": data.get("skillOverrides") or {},
    }


def read_three_layers(proj_dir: Path, user_dir: Path) -> dict:
    """
    Read all three settings layers.

    Returns a dict with keys 'layer3', 'layer4', 'layer5', each being the
    result of read_layer() for that file.

    Layer 3: <proj>/.claude/settings.local.json
    Layer 4: <proj>/.claude/settings.json
    Layer 5: <user>/.claude/settings.json
    """
    layer3_path = proj_dir / ".claude" / "settings.local.json"
    layer4_path = proj_dir / ".claude" / "settings.json"
    layer5_path = user_dir / ".claude" / "settings.json"

    return {
        "layer3": read_layer(layer3_path),
        "layer4": read_layer(layer4_path),
        "layer5": read_layer(layer5_path),
    }


# ============================================================
# Task 2: enabledPlugins effective state (Solution A' asymmetric)
# ============================================================

def plugin_effective(layer3, layer4, layer5) -> bool:
    """
    Compute the effective enabledPlugins value from three layers.

    Algorithm (asymmetric):
    - layer3=True always wins (rescues a project-level False)
    - layer3=False is SILENTLY IGNORED (cannot suppress project True)
    - layer4 (any value) takes precedence over layer5
    - layer5 (any value) takes precedence over default
    - default: False (not enabled)
    """
    # Local True always rescues, regardless of project setting
    if layer3 is True:
        return True
    # Project-level value (layer4) takes precedence over user (layer5)
    if layer4 is not None:
        return layer4
    # User-level value (layer5)
    if layer5 is not None:
        return layer5
    # Default: not enabled
    return False


# ============================================================
# Task 3: skillOverrides effective state (strict symmetric)
# ============================================================

def skill_effective(layer3, layer4, layer5) -> str:
    """
    Compute the effective skillOverrides value from three layers.

    Algorithm (symmetric — first non-None wins):
    - layer3 wins if set
    - layer4 wins if set (layer3 is None)
    - layer5 wins if set (both layer3 and layer4 are None)
    - default: "on"

    Valid values: "on", "name-only", "user-invocable-only", "off"
    """
    for layer in (layer3, layer4, layer5):
        if layer is not None:
            return layer
    return "on"


# ============================================================
# Task 4: plugin.json discovery and rich info
# ============================================================

def _version_key(version_str: str) -> tuple:
    """
    Parse a version string into a tuple of ints for comparison.

    '2.1.0' → (2, 1, 0)
    Non-numeric parts become 0.
    """
    parts = version_str.split(".")
    result = []
    for part in parts:
        # Extract leading digits only
        m = re.match(r"^(\d+)", part)
        result.append(int(m.group(1)) if m else 0)
    return tuple(result)


def discover_plugins(cache_dir: Path) -> list:
    """
    Discover all installed plugins in the plugin cache directory.

    Cache structure:
      <cache_dir>/<org>/<name>/<version>/.claude-plugin/plugin.json
      (also checks .codex-plugin/ as fallback)

    Plugin ID format: <name>@<org>  (note: path is <org>/<name>/, key reverses it)

    Rules:
    - Skip org directories starting with 'temp_git_'
    - For multi-version installs, pick the latest by version number
    - description missing → '<plugin-id> (no description)'
    - link priority: homepage > repository > None
    """
    if not cache_dir.exists():
        return []

    # Group versions by (org, name) to pick the latest
    # Structure: {(org, name): {version_str: plugin_json_path}}
    candidates: dict = {}

    for org_dir in cache_dir.iterdir():
        if not org_dir.is_dir():
            continue
        # Filter temp_git_* directories
        if org_dir.name.startswith("temp_git_"):
            continue

        for name_dir in org_dir.iterdir():
            if not name_dir.is_dir():
                continue

            key = (org_dir.name, name_dir.name)
            if key not in candidates:
                candidates[key] = {}

            for ver_dir in name_dir.iterdir():
                if not ver_dir.is_dir():
                    continue

                # Check .claude-plugin first, then .codex-plugin as fallback
                plugin_json = None
                for subdir in (".claude-plugin", ".codex-plugin"):
                    candidate = ver_dir / subdir / "plugin.json"
                    if candidate.exists():
                        plugin_json = candidate
                        break

                if plugin_json is not None:
                    candidates[key][ver_dir.name] = plugin_json

    plugins = []
    for (org, name), versions in candidates.items():
        if not versions:
            continue

        # Pick the latest version
        latest_version = max(versions.keys(), key=_version_key)
        plugin_json_path = versions[latest_version]

        try:
            raw = json.loads(plugin_json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        plugin_id = f"{name}@{org}"
        description = raw.get("description") or f"{plugin_id} (no description)"
        homepage = raw.get("homepage")
        repository = raw.get("repository")

        # Link priority: homepage > repository > None
        link = homepage if homepage else (repository if repository else None)

        plugins.append({
            "id": plugin_id,
            "name": raw.get("name", name),
            "description": description,
            "link": link,
            "homepage": homepage,
            "repository": repository,
        })

    return plugins


# ============================================================
# Task 5: Custom skill discovery + SKILL.md parsing
# ============================================================

def parse_skill_description(skill_md_path: Path) -> "str | None":
    """
    Parse YAML-style frontmatter from SKILL.md for the 'description:' field.

    Simple line-based parsing (no YAML library needed).
    Returns the description string if found, None otherwise.
    """
    try:
        text = skill_md_path.read_text(encoding="utf-8")
    except OSError:
        return None

    lines = text.splitlines()

    # Frontmatter must start with '---' on the first line
    if not lines or lines[0].strip() != "---":
        return None

    # Find the closing '---'
    in_frontmatter = True
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            in_frontmatter = False
            break
        # Look for description: field
        m = re.match(r"^description:\s*(.+)$", line)
        if m:
            return m.group(1).strip()

    return None


def discover_skills(proj_dir: Path, user_dir: Path, plugin_cache: Path) -> list:
    """
    Discover custom skills at user-level and project-level.

    Scans:
    - User-level: <user>/.claude/skills/**  (up to 2 levels deep)
    - Project-level: <proj>/.claude/skills/**  (up to 2 levels deep)

    Each result dict has:
    - name: directory name
    - description: from SKILL.md frontmatter (or None)
    - path: absolute path to skill directory
    - level: "user" or "project"

    Excludes:
    - Directories without SKILL.md
    - Directories under plugin_cache
    """
    skills = []
    plugin_cache_resolved = plugin_cache.resolve() if plugin_cache.exists() else None

    def _scan_skills_dir(skills_root: Path, level: str):
        """Scan a skills root directory up to 2 levels deep for SKILL.md."""
        if not skills_root.exists():
            return

        # Level 1: <skills_root>/<skill-name>/SKILL.md
        for item in skills_root.iterdir():
            if not item.is_dir():
                continue

            # Exclude plugin-bundled skills
            if plugin_cache_resolved:
                try:
                    item.resolve().relative_to(plugin_cache_resolved)
                    continue  # Under plugin cache, skip
                except ValueError:
                    pass  # Not under plugin cache, OK

            skill_md = item / "SKILL.md"
            if skill_md.exists():
                description = parse_skill_description(skill_md)
                skills.append({
                    "name": item.name,
                    "description": description,
                    "path": str(item),
                    "level": level,
                })
            else:
                # Level 2: <skills_root>/<group>/<skill-name>/SKILL.md
                for nested in item.iterdir():
                    if not nested.is_dir():
                        continue

                    # Exclude plugin-bundled skills
                    if plugin_cache_resolved:
                        try:
                            nested.resolve().relative_to(plugin_cache_resolved)
                            continue
                        except ValueError:
                            pass

                    nested_skill_md = nested / "SKILL.md"
                    if nested_skill_md.exists():
                        description = parse_skill_description(nested_skill_md)
                        skills.append({
                            "name": nested.name,
                            "description": description,
                            "path": str(nested),
                            "level": level,
                        })

    user_skills_root = user_dir / ".claude" / "skills"
    proj_skills_root = proj_dir / ".claude" / "skills"

    _scan_skills_dir(user_skills_root, "user")
    _scan_skills_dir(proj_skills_root, "project")

    return skills


# ============================================================
# Task 6: Backup + atomic write
# ============================================================

def _rotate_backups(settings_path: Path, keep: int = 3):
    """
    Keep only the most recent `keep` backups for the given settings file.

    Backup naming pattern: <name>.bak.<ISO8601>
    Rotation: delete oldest backups by mtime, keeping `keep` most recent.
    """
    parent = settings_path.parent
    backup_pattern = f"{settings_path.name}.bak."
    backups = sorted(
        [f for f in parent.iterdir() if f.name.startswith(backup_pattern)],
        key=lambda f: f.stat().st_mtime,
        reverse=True,  # newest first
    )

    # Delete old backups beyond the keep limit
    for old_backup in backups[keep:]:
        old_backup.unlink(missing_ok=True)


def backup_and_write(settings_path: Path, new_content: str):
    """
    Write new_content to settings_path with backup and atomic write.

    Flow:
    1. Clean residual .tmp files
    2. If original exists and content unchanged → skip (no backup, no write)
    3. If original exists → backup to <name>.bak.<ISO8601>
    4. Atomic write: write to .tmp then os.replace to target
    5. Rotate backups (keep most recent 3 by mtime)
    """
    tmp_path = settings_path.with_suffix(settings_path.suffix + ".tmp")

    # Step 1: Clean residual .tmp files
    if tmp_path.exists():
        tmp_path.unlink()

    # Step 2: Check if content is unchanged
    if settings_path.exists():
        existing_content = settings_path.read_text(encoding="utf-8")
        if existing_content == new_content:
            return  # Content unchanged, no action needed

        # Step 3: Backup original (microsecond precision avoids collisions within same second)
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%dT%H%M%S") + f"{now.microsecond:06d}Z"
        backup_path = settings_path.parent / f"{settings_path.name}.bak.{timestamp}"
        shutil.copy2(settings_path, backup_path)

    # Step 4: Atomic write via .tmp then os.replace
    tmp_path.write_text(new_content, encoding="utf-8")
    os.replace(tmp_path, settings_path)

    # Step 5: Rotate backups
    _rotate_backups(settings_path, keep=3)


# ============================================================
# Task 7: Merge-style write boundary protection
# ============================================================

def merge_and_write_settings(settings_path: Path, field: str, changes: dict):
    """
    Merge changes into a specific field of a settings JSON file.

    Flow:
    1. Read full settings.json (or start from {} if missing)
    2. Get field dict (or {} if field missing)
    3. For each change: None → remove key, else set key
    4. Write back with json.dumps(indent=2, sort_keys=True, ensure_ascii=False) + '\\n'
    5. Use backup_and_write for the actual write

    Other fields in settings.json are preserved unchanged.
    """
    # Step 1: Read existing settings (or start fresh)
    if settings_path.exists():
        try:
            full_data = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            full_data = {}
    else:
        full_data = {}

    # Step 2: Get the target field dict
    field_data = dict(full_data.get(field) or {})

    # Step 3: Apply changes
    for key, value in changes.items():
        if value is None:
            # Remove the key if it exists
            field_data.pop(key, None)
        else:
            field_data[key] = value

    # Update the full data with the modified field
    full_data[field] = field_data

    # Step 4: Serialize
    new_content = json.dumps(full_data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"

    # Step 5: Backup and write
    backup_and_write(settings_path, new_content)


# ============================================================
# Task 8: plugins status CLI
# ============================================================

def _plugin_annotation(layer3, layer4, layer5, effective) -> str:
    """
    Compute a human-readable annotation for a plugin's effective state.

    Returns:
    - "⚠ 项目级翻盘"    when layer4=False, layer5=True, layer3 is not True
    - "⚠ 本机救回"       when layer3=True, layer4=False
    - "⚠ local OFF 被忽略" when layer3=False and (layer4=True or (layer4 is None and layer5=True))
    - ""                 otherwise
    """
    # 本机救回: layer3=True 救回 layer4=False
    if layer3 is True and layer4 is False:
        return "⚠ 本机救回"
    # local OFF 被忽略: layer3=False 被忽略（无法抑制 project/user 的 True）
    if layer3 is False and (layer4 is True or (layer4 is None and layer5 is True)):
        return "⚠ local OFF 被忽略"
    # 项目级翻盘: project False 推翻 user True，且无本机救回
    if layer4 is False and layer5 is True and layer3 is not True:
        return "⚠ 项目级翻盘"
    return ""


def cmd_plugins_status(proj_dir: Path, user_dir: Path, plugin_cache: Path) -> list:
    """
    Return status list for all discovered plugins.

    Each dict contains:
    - id, description, link, layer5, layer4, layer3, effective, annotation
    """
    layers = read_three_layers(proj_dir, user_dir)
    plugins = discover_plugins(plugin_cache)

    result = []
    for plugin in plugins:
        pid = plugin["id"]
        l3 = layers["layer3"]["enabledPlugins"].get(pid)
        l4 = layers["layer4"]["enabledPlugins"].get(pid)
        l5 = layers["layer5"]["enabledPlugins"].get(pid)
        eff = plugin_effective(l3, l4, l5)
        ann = _plugin_annotation(l3, l4, l5, eff)
        result.append({
            "id": pid,
            "description": plugin["description"],
            "link": plugin["link"],
            "layer5": l5,
            "layer4": l4,
            "layer3": l3,
            "effective": eff,
            "annotation": ann,
        })

    return result


# ============================================================
# Task 9: plugins detail + apply CLI
# ============================================================

def cmd_plugins_detail(plugin_id: str, proj_dir: Path, user_dir: Path, plugin_cache: Path) -> dict:
    """
    Return full detail dict for a single plugin.

    sys.exit(1) if the plugin is not found.
    """
    plugins = discover_plugins(plugin_cache)
    plugin = next((p for p in plugins if p["id"] == plugin_id), None)
    if plugin is None:
        print(f"ERROR: plugin '{plugin_id}' not found", file=sys.stderr)
        sys.exit(1)

    layers = read_three_layers(proj_dir, user_dir)
    l3 = layers["layer3"]["enabledPlugins"].get(plugin_id)
    l4 = layers["layer4"]["enabledPlugins"].get(plugin_id)
    l5 = layers["layer5"]["enabledPlugins"].get(plugin_id)
    eff = plugin_effective(l3, l4, l5)
    ann = _plugin_annotation(l3, l4, l5, eff)

    return {
        "id": plugin["id"],
        "name": plugin["name"],
        "description": plugin["description"],
        "homepage": plugin["homepage"],
        "repository": plugin["repository"],
        "link": plugin["link"],
        "layer5": l5,
        "layer4": l4,
        "layer3": l3,
        "effective": eff,
        "annotation": ann,
    }


def cmd_plugins_apply(proj_dir: Path, changes: dict):
    """
    Apply enabledPlugins changes to the project settings.json.

    Empty changes → return immediately (no write).
    """
    if not changes:
        return

    settings_path = proj_dir / ".claude" / "settings.json"
    merge_and_write_settings(settings_path, "enabledPlugins", changes)


# ============================================================
# Task 10: skills status/detail/apply CLI
# ============================================================

def _skill_annotation(layer3, layer4, layer5) -> str:
    """
    Compute a human-readable annotation for a skill's effective state.

    Returns:
    - "⚠ 项目级翻盘" when layer4 and layer5 differ and layer3 is None
    - "⚠ 本机覆盖"   when layer3 and layer4 differ and both have values
    - ""              otherwise
    """
    # 本机覆盖: layer3 overrides layer4 (both set, different)
    if layer3 is not None and layer4 is not None and layer3 != layer4:
        return "⚠ 本机覆盖"
    # 项目级翻盘: project (layer4) overrides user (layer5), no local override
    if layer3 is None and layer4 is not None and layer5 is not None and layer4 != layer5:
        return "⚠ 项目级翻盘"
    return ""


def cmd_skills_status(proj_dir: Path, user_dir: Path, plugin_cache: Path) -> list:
    """
    Return status list for all discovered custom skills.

    Each dict contains:
    - name, description, path, level, layer5, layer4, layer3, effective, annotation
    """
    layers = read_three_layers(proj_dir, user_dir)
    skills = discover_skills(proj_dir, user_dir, plugin_cache)

    result = []
    for skill in skills:
        sname = skill["name"]
        l3 = layers["layer3"]["skillOverrides"].get(sname)
        l4 = layers["layer4"]["skillOverrides"].get(sname)
        l5 = layers["layer5"]["skillOverrides"].get(sname)
        eff = skill_effective(l3, l4, l5)
        ann = _skill_annotation(l3, l4, l5)
        result.append({
            "name": sname,
            "description": skill["description"],
            "path": skill["path"],
            "level": skill["level"],
            "layer5": l5,
            "layer4": l4,
            "layer3": l3,
            "effective": eff,
            "annotation": ann,
        })

    return result


def cmd_skills_detail(skill_name: str, proj_dir: Path, user_dir: Path, plugin_cache: Path) -> dict:
    """
    Return full detail dict for a single skill.

    sys.exit(1) if the skill is not found.
    """
    skills = discover_skills(proj_dir, user_dir, plugin_cache)
    skill = next((s for s in skills if s["name"] == skill_name), None)
    if skill is None:
        print(f"ERROR: skill '{skill_name}' not found", file=sys.stderr)
        sys.exit(1)

    layers = read_three_layers(proj_dir, user_dir)
    l3 = layers["layer3"]["skillOverrides"].get(skill_name)
    l4 = layers["layer4"]["skillOverrides"].get(skill_name)
    l5 = layers["layer5"]["skillOverrides"].get(skill_name)
    eff = skill_effective(l3, l4, l5)
    ann = _skill_annotation(l3, l4, l5)

    return {
        "name": skill["name"],
        "description": skill["description"],
        "path": skill["path"],
        "level": skill["level"],
        "layer5": l5,
        "layer4": l4,
        "layer3": l3,
        "effective": eff,
        "annotation": ann,
    }


def cmd_skills_apply(proj_dir: Path, changes: dict):
    """
    Apply skillOverrides changes to the project settings.json.

    Empty changes → return immediately (no write).
    """
    if not changes:
        return

    settings_path = proj_dir / ".claude" / "settings.json"
    merge_and_write_settings(settings_path, "skillOverrides", changes)


# ============================================================
# Task 11: argparse CLI entry point
# ============================================================

def _add_common_args(parser):
    """Add common directory arguments to a subparser."""
    parser.add_argument(
        "--proj-dir",
        type=Path,
        default=Path.cwd(),
        help="Project directory (default: cwd)",
    )
    parser.add_argument(
        "--user-dir",
        type=Path,
        default=Path.home(),
        help="User home directory (default: ~)",
    )
    parser.add_argument(
        "--plugin-cache",
        type=Path,
        default=Path.home() / ".claude" / "plugins" / "cache",
        help="Plugin cache directory (default: ~/.claude/plugins/cache)",
    )


def _handle_plugins_status(args):
    result = cmd_plugins_status(args.proj_dir, args.user_dir, args.plugin_cache)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def _handle_plugins_detail(args):
    result = cmd_plugins_detail(args.id, args.proj_dir, args.user_dir, args.plugin_cache)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def _handle_plugins_apply(args):
    try:
        changes = json.loads(args.changes)
    except json.JSONDecodeError as exc:
        print(f"ERROR: --changes is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(1)
    cmd_plugins_apply(args.proj_dir, changes)


def _handle_skills_status(args):
    result = cmd_skills_status(args.proj_dir, args.user_dir, args.plugin_cache)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def _handle_skills_detail(args):
    result = cmd_skills_detail(args.id, args.proj_dir, args.user_dir, args.plugin_cache)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def _handle_skills_apply(args):
    try:
        changes = json.loads(args.changes)
    except json.JSONDecodeError as exc:
        print(f"ERROR: --changes is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(1)
    cmd_skills_apply(args.proj_dir, changes)


def _handle_templates_not_implemented(args):
    print(json.dumps({"error": "not implemented"}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(
        description="Claude Code project-level settings manager"
    )
    parser.add_argument("--version", action="version", version="config_setup 0.2.0")

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    # ── plugins ──────────────────────────────────────────────
    plugins_parser = subparsers.add_parser("plugins", help="Manage plugins")
    plugins_sub = plugins_parser.add_subparsers(dest="subcommand", metavar="SUBCOMMAND")

    # plugins status
    ps_parser = plugins_sub.add_parser("status", help="Show plugin status")
    ps_parser.add_argument("--json", action="store_true", help="Output as JSON")
    _add_common_args(ps_parser)
    ps_parser.set_defaults(handler=_handle_plugins_status)

    # plugins detail
    pd_parser = plugins_sub.add_parser("detail", help="Show plugin detail")
    pd_parser.add_argument("id", help="Plugin ID (name@org)")
    pd_parser.add_argument("--json", action="store_true", help="Output as JSON")
    _add_common_args(pd_parser)
    pd_parser.set_defaults(handler=_handle_plugins_detail)

    # plugins apply
    pa_parser = plugins_sub.add_parser("apply", help="Apply plugin changes")
    pa_parser.add_argument("--changes", required=True, help="JSON dict of changes")
    pa_parser.add_argument(
        "--proj-dir",
        type=Path,
        default=Path.cwd(),
        help="Project directory (default: cwd)",
    )
    pa_parser.set_defaults(handler=_handle_plugins_apply)

    # ── skills ───────────────────────────────────────────────
    skills_parser = subparsers.add_parser("skills", help="Manage skills")
    skills_sub = skills_parser.add_subparsers(dest="subcommand", metavar="SUBCOMMAND")

    # skills status
    ss_parser = skills_sub.add_parser("status", help="Show skill status")
    ss_parser.add_argument("--json", action="store_true", help="Output as JSON")
    _add_common_args(ss_parser)
    ss_parser.set_defaults(handler=_handle_skills_status)

    # skills detail
    sd_parser = skills_sub.add_parser("detail", help="Show skill detail")
    sd_parser.add_argument("id", help="Skill name")
    sd_parser.add_argument("--json", action="store_true", help="Output as JSON")
    _add_common_args(sd_parser)
    sd_parser.set_defaults(handler=_handle_skills_detail)

    # skills apply
    sa_parser = skills_sub.add_parser("apply", help="Apply skill changes")
    sa_parser.add_argument("--changes", required=True, help="JSON dict of changes")
    sa_parser.add_argument(
        "--proj-dir",
        type=Path,
        default=Path.cwd(),
        help="Project directory (default: cwd)",
    )
    sa_parser.set_defaults(handler=_handle_skills_apply)

    # ── templates ────────────────────────────────────────────
    tpl_parser = subparsers.add_parser("templates", help="Manage templates (not implemented)")
    tpl_sub = tpl_parser.add_subparsers(dest="subcommand", metavar="SUBCOMMAND")

    for tpl_cmd in ("list", "load", "save", "match"):
        tp = tpl_sub.add_parser(tpl_cmd, help=f"Template {tpl_cmd} (not implemented)")
        tp.set_defaults(handler=_handle_templates_not_implemented)

    # ── dispatch ─────────────────────────────────────────────
    args = parser.parse_args()

    if not hasattr(args, "handler"):
        # No subcommand given — print help
        parser.print_help()
        sys.exit(0)

    args.handler(args)


if __name__ == "__main__":
    main()
