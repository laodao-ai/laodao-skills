"""重新生成 presets/catalog.json。安装/卸载 plugin 后运行一次。

扫描来源：
  plugin skills  — plugin 包内 skills/<name>/SKILL.md
  plugin commands — plugin 包内 commands/<name>.md（也以 plugin:cmd 形式暴露）
  user skills    — ~/.claude/skills/<name>/SKILL.md

输出（v4 → 语义版兼容）：
  plugins / plugin_skills / user_skills    — 旧字段，保留兼容
  skills_enriched[] / plugins_enriched[]   — 新字段，含 description 给 LLM 推荐用
"""
import json, os, glob, re, sys
from datetime import date

CACHE_ROOT = os.path.expanduser('~/.claude/plugins/cache')
SKILLS_DIR = os.path.expanduser('~/.claude/skills/')
OUT_PATH = os.path.expanduser('~/.claude/skills/laodao-skills/config-skills/presets/catalog.json')

DESC_HARD_LIMIT = 500
DESC_FALLBACK_THRESHOLD = 80
BODY_FALLBACK_LINES = 30

WARNINGS = []


def parse_frontmatter(content):
    """解析 SKILL.md 的 YAML frontmatter，返回 dict 或 None。
    用增强 regex 处理 description 的折叠（>/|）、引号、列表续行。
    """
    m = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not m:
        return None
    block = m.group(1)
    fm = {}
    # 简单 key: value 解析（够用）
    lines = block.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        kv = re.match(r'^([a-zA-Z_][\w-]*)\s*:\s*(.*)$', line)
        if not kv:
            i += 1
            continue
        key, val = kv.group(1), kv.group(2)
        val_stripped = val.strip()
        # 折叠语法：> 或 |
        if val_stripped in ('>', '|', '>-', '|-'):
            j = i + 1
            collected = []
            while j < len(lines) and (lines[j].startswith('  ') or lines[j].startswith('\t') or lines[j].strip() == ''):
                collected.append(lines[j].lstrip())
                j += 1
            sep = ' ' if val_stripped.startswith('>') else '\n'
            fm[key] = sep.join(c for c in collected if c).strip()
            i = j
            continue
        # 续行（缩进续）
        if val_stripped == '':
            j = i + 1
            collected = []
            while j < len(lines) and (lines[j].startswith('  ') or lines[j].startswith('\t')):
                collected.append(lines[j].strip())
                j += 1
            if collected:
                fm[key] = ' '.join(collected)
            i = j
            continue
        # 去引号
        if (val_stripped.startswith('"') and val_stripped.endswith('"')) or \
           (val_stripped.startswith("'") and val_stripped.endswith("'")):
            val_stripped = val_stripped[1:-1]
        # 多行值（下一行也缩进）
        j = i + 1
        while j < len(lines) and (lines[j].startswith('  ') or lines[j].startswith('\t')):
            val_stripped += ' ' + lines[j].strip()
            j += 1
        fm[key] = val_stripped
        i = j
    return fm


def get_body(content):
    """剥掉 frontmatter 后的正文。"""
    m = re.match(r'^---\n.*?\n---\n?', content, re.DOTALL)
    return content[m.end():] if m else content


def body_first_lines(body, n=BODY_FALLBACK_LINES):
    """取 body 前 n 行，去除空行 / 代码块标记 / 标题井号。"""
    lines = body.split('\n')
    keep = []
    in_code = False
    for line in lines:
        if line.startswith('```'):
            in_code = not in_code
            continue
        if in_code:
            continue
        stripped = line.strip()
        if not stripped:
            continue
        # 去 markdown 标题前缀
        stripped = re.sub(r'^#+\s+', '', stripped)
        keep.append(stripped)
        if len(keep) >= n:
            break
    return ' '.join(keep)


def read_description_enriched(md_path, label_for_warning):
    """返回 {description, fallback_used, fm_name}。

    规则：
    - 抓 frontmatter description；< 80 字符则补 body 前 30 行（fallback_used=True）
    - frontmatter 解析失败：直接取 body 前 30 行（fallback_used=True）
    - 硬截 500 字符
    - fm_name：frontmatter 的 name 字段（运行时识别用），缺失返回 ''
    """
    try:
        with open(md_path, encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        WARNINGS.append(f'{label_for_warning}: 读取失败 {e}')
        return {"description": "", "fallback_used": True, "fm_name": ""}

    fm = parse_frontmatter(content)
    if fm is None:
        WARNINGS.append(f'{label_for_warning}: frontmatter 缺失或解析失败，降级取 body')
        body = get_body(content)
        return {"description": body_first_lines(body)[:DESC_HARD_LIMIT], "fallback_used": True, "fm_name": ""}

    fm_name = fm.get('name', '').strip()
    desc = fm.get('description', '').strip()
    if len(desc) >= DESC_FALLBACK_THRESHOLD:
        return {"description": desc[:DESC_HARD_LIMIT], "fallback_used": False, "fm_name": fm_name}

    # description 太短或缺失，补 body
    body = get_body(content)
    body_part = body_first_lines(body)
    combined = (desc + ' ' + body_part).strip() if desc else body_part
    return {"description": combined[:DESC_HARD_LIMIT], "fallback_used": True, "fm_name": fm_name}


def read_plugin_description(plugin_dir):
    """读 plugin.json 的 description。"""
    pj = os.path.join(plugin_dir, '.claude-plugin', 'plugin.json')
    if not os.path.isfile(pj):
        return ""
    try:
        with open(pj, encoding='utf-8') as f:
            data = json.load(f)
        return (data.get('description') or '').strip()[:DESC_HARD_LIMIT]
    except Exception as e:
        WARNINGS.append(f'plugin {plugin_dir}: plugin.json 解析失败 {e}')
        return ""


def latest_version_dir(base_dirs):
    """从 glob 结果中取版本号最新的路径。"""
    return sorted(base_dirs)[-1] if base_dirs else None


# ── 加载已装 plugin 列表 ──
with open(os.path.expanduser('~/.claude/plugins/installed_plugins.json')) as f:
    installed = json.load(f)

plugin_entries = {}
plugins_top = {}
plugins_enriched = []
skills_enriched = []

for plugin_id in installed.get('plugins', {}):
    name_part = plugin_id.split('@')[0]
    author = '@'.join(plugin_id.split('@')[1:])
    plugins_top[plugin_id] = {
        "name": name_part,
        "author": author,
        "has_skills": False,
        "has_commands": False,
    }

    # ── plugin.json description（取最新版本目录）──
    plugin_version_dirs = glob.glob(f'{CACHE_ROOT}/{author}/{name_part}/*/')
    plugin_version_dir = latest_version_dir(plugin_version_dirs)
    plugin_desc = read_plugin_description(plugin_version_dir) if plugin_version_dir else ""
    plugins_enriched.append({
        "name": plugin_id,
        "plain_name": name_part,
        "author": author,
        "description": plugin_desc,
    })

    # ── skills/<name>/SKILL.md ──
    # 路径兼容两种：标准 <v>/skills/ 与 <v>/.claude/skills/（社区作者打包习惯）
    skill_base_dirs = (
        glob.glob(f'{CACHE_ROOT}/{author}/{name_part}/*/skills/')
        or glob.glob(f'{CACHE_ROOT}/{author}/{name_part}/*/.claude/skills/')
    )
    if skill_base_dirs:
        latest = latest_version_dir(skill_base_dirs)
        for skill_dir_name in sorted(os.listdir(latest)):
            skill_path = os.path.join(latest, skill_dir_name)
            skill_md = os.path.join(skill_path, 'SKILL.md')
            if os.path.isdir(skill_path) and os.path.isfile(skill_md):
                default_skill_id = f"{name_part}:{skill_dir_name}"
                enriched = read_description_enriched(skill_md, default_skill_id)
                # skill ID 优先用 frontmatter name（运行时识别准确）；不含 ':' 的才用，
                # 含 ':' 视为内部子模块（如 ckm:design）— 不是顶层 skill，跳过
                fm_name = enriched.get("fm_name", "")
                if fm_name and ':' in fm_name:
                    continue
                skill_id = f"{name_part}:{fm_name}" if fm_name else default_skill_id
                # 旧字段（兼容）
                plugin_entries[skill_id] = {
                    "type": "plugin-skill",
                    "plugin": plugin_id,
                    "description": enriched["description"][:120]  # 旧字段保持原 120 截断
                }
                # 新字段
                skills_enriched.append({
                    "name": skill_id,
                    "source": "plugin",
                    "owner_plugin": plugin_id,
                    "description": enriched["description"],
                    "fallback_used": enriched["fallback_used"],
                })
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
            enriched = read_description_enriched(cmd_path, skill_id)
            plugin_entries[skill_id] = {
                "type": "plugin-command",
                "plugin": plugin_id,
                "description": enriched["description"][:120]
            }
            # plugin-command 也进 enriched（与 plugin-skill 同等可推荐）
            skills_enriched.append({
                "name": skill_id,
                "source": "plugin",
                "owner_plugin": plugin_id,
                "description": enriched["description"],
                "fallback_used": enriched["fallback_used"],
            })
            plugins_top[plugin_id]["has_commands"] = True

# ── 用户级 skills（不含项目级，已天然过滤）──
user_entries = {}
for d in sorted(os.listdir(SKILLS_DIR)):
    full = os.path.join(SKILLS_DIR, d)
    skill_md = os.path.join(full, 'SKILL.md')
    if not (os.path.isdir(full) and os.path.isfile(skill_md)):
        continue
    if d == 'laodao-skills':
        continue
    enriched = read_description_enriched(skill_md, f'user:{d}')
    user_entries[d] = {
        "type": "user",
        "description": enriched["description"][:120]
    }
    skills_enriched.append({
        "name": d,
        "source": "user",
        "owner_plugin": None,
        "description": enriched["description"],
        "fallback_used": enriched["fallback_used"],
    })

catalog = {
    "_meta": {
        "generated": str(date.today()),
        "note": "Auto-generated. Regenerate with: python3 scripts/00_gen_catalog.py",
        "schema_version": 2,
    },
    "plugins": plugins_top,
    "plugin_skills": plugin_entries,
    "user_skills": user_entries,
    "skills_enriched": skills_enriched,
    "plugins_enriched": plugins_enriched,
}

# ── 原子写入 ──
tmp = OUT_PATH + '.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
    json.dump(catalog, f, indent=2, ensure_ascii=False)
    f.write('\n')
os.replace(tmp, OUT_PATH)

skill_count = sum(1 for v in plugin_entries.values() if v['type'] == 'plugin-skill')
cmd_count = sum(1 for v in plugin_entries.values() if v['type'] == 'plugin-command')
fallback_count = sum(1 for s in skills_enriched if s['fallback_used'])
print(f'✅ catalog.json 已生成')
print(f'   旧字段：{skill_count} plugin-skills + {cmd_count} plugin-commands + {len(user_entries)} user skills')
print(f'   enriched: {len(skills_enriched)} skills (fallback={fallback_count}) + {len(plugins_enriched)} plugins')
if WARNINGS:
    print(f'\n⚠️  {len(WARNINGS)} 条 warning:')
    for w in WARNINGS[:10]:
        print(f'   {w}')
    if len(WARNINGS) > 10:
        print(f'   ... 及其余 {len(WARNINGS) - 10} 条')
