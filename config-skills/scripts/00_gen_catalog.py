"""重新生成 presets/catalog.json。安装/卸载 plugin 后运行一次。

扫描来源：
  plugin skills  — plugin 包内 skills/<name>/SKILL.md
  plugin commands — plugin 包内 commands/<name>.md（也以 plugin:cmd 形式暴露）
  user skills    — ~/.claude/skills/<name>/SKILL.md
"""
import json, os, glob, re

CACHE_ROOT = os.path.expanduser('~/.claude/plugins/cache')
SKILLS_DIR = os.path.expanduser('~/.claude/skills/')
OUT_PATH = os.path.expanduser('~/.claude/skills/laodao-skills/config-skills/presets/catalog.json')

with open(os.path.expanduser('~/.claude/plugins/installed_plugins.json')) as f:
    installed = json.load(f)

def read_description(md_path):
    try:
        with open(md_path) as f:
            content = f.read()
        m = re.search(r'^---\n(.*?)\n---', content, re.DOTALL)
        if m:
            d = re.search(r'^description:\s*[>|]?\s*\n?\s*(.+)', m.group(1), re.MULTILINE)
            if d:
                return d.group(1).strip().rstrip('"').lstrip('"')[:120]
        h = re.search(r'^#\s+(.+)', content, re.MULTILINE)
        if h:
            return h.group(1).strip()[:120]
    except:
        pass
    return ""

def latest_version_dir(base_dirs):
    """从 glob 结果中取版本号最新的路径。"""
    return sorted(base_dirs)[-1] if base_dirs else None

plugin_entries = {}
plugins_top = {}
for plugin_id in installed.get('plugins', {}):
    name_part = plugin_id.split('@')[0]
    author = '@'.join(plugin_id.split('@')[1:])
    plugins_top[plugin_id] = {
        "name": name_part,
        "author": author,
        "has_skills": False,
        "has_commands": False,
    }

    # ── skills/<name>/SKILL.md ──
    skill_base_dirs = glob.glob(f'{CACHE_ROOT}/{author}/{name_part}/*/skills/')
    if skill_base_dirs:
        latest = latest_version_dir(skill_base_dirs)
        for skill_dir_name in sorted(os.listdir(latest)):
            skill_path = os.path.join(latest, skill_dir_name)
            skill_md = os.path.join(skill_path, 'SKILL.md')
            if os.path.isdir(skill_path) and os.path.isfile(skill_md):
                skill_id = f"{name_part}:{skill_dir_name}"
                plugin_entries[skill_id] = {
                    "type": "plugin-skill",
                    "plugin": plugin_id,
                    "description": read_description(skill_md)
                }
                plugins_top[plugin_id]["has_skills"] = True

    # ── commands/<name>.md ──
    cmd_base_dirs = glob.glob(f'{CACHE_ROOT}/{author}/{name_part}/*/commands/')
    if cmd_base_dirs:
        latest = latest_version_dir(cmd_base_dirs)
        for cmd_file in sorted(os.listdir(latest)):
            if not cmd_file.endswith('.md'):
                continue
            cmd_name = cmd_file[:-3]  # strip .md
            cmd_path = os.path.join(latest, cmd_file)
            skill_id = f"{name_part}:{cmd_name}"
            plugin_entries[skill_id] = {
                "type": "plugin-command",
                "plugin": plugin_id,
                "description": read_description(cmd_path)
            }
            plugins_top[plugin_id]["has_commands"] = True

user_entries = {}
for d in sorted(os.listdir(SKILLS_DIR)):
    full = os.path.join(SKILLS_DIR, d)
    skill_md = os.path.join(full, 'SKILL.md')
    if not (os.path.isdir(full) and os.path.isfile(skill_md)):
        continue
    if d == 'laodao-skills':
        continue
    user_entries[d] = {
        "type": "user",
        "description": read_description(skill_md)
    }

from datetime import date
catalog = {
    "_meta": {
        "generated": str(date.today()),
        "note": "Auto-generated. Regenerate with: python3 scripts/00_gen_catalog.py"
    },
    "plugins": plugins_top,
    "plugin_skills": plugin_entries,
    "user_skills": user_entries
}

with open(OUT_PATH, 'w') as f:
    json.dump(catalog, f, indent=2, ensure_ascii=False)
    f.write('\n')

skill_count = sum(1 for v in plugin_entries.values() if v['type'] == 'plugin-skill')
cmd_count = sum(1 for v in plugin_entries.values() if v['type'] == 'plugin-command')
print(f'✅ catalog.json 已生成: {skill_count} plugin-skills + {cmd_count} plugin-commands + {len(user_entries)} user skills')
