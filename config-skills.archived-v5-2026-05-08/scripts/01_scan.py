"""Step 1: 扫描环境 + 探测项目类型（v4：detect 规则从 all.json 读）"""
import json, os

PRESET_DIR = os.path.expanduser('~/.claude/skills/laodao-skills/config-skills/presets/')

with open(os.path.join(PRESET_DIR, 'all.json')) as f:
    ALL = json.load(f)
DETECT = ALL.get('detect', [])

# ── plugin 列表 ──
with open(os.path.expanduser('~/.claude/plugins/installed_plugins.json')) as f:
    plugin_data = json.load(f)
plugins = sorted(plugin_data.get('plugins', {}).keys())

# ── 用户级 skill ──
local_dir = os.path.expanduser('~/.claude/skills/')
local_skills = sorted([d for d in os.listdir(local_dir)
                       if os.path.isdir(os.path.join(local_dir, d))
                       and d != 'laodao-skills'])

# ── 项目级 skill ──
project_skills = []
if os.path.isdir('.claude/skills/'):
    project_skills = sorted([d for d in os.listdir('.claude/skills/')
                             if os.path.isdir(os.path.join('.claude/skills/', d))])

# ── 项目类型探测（按 detect 规则顺序匹配） ──
files = set(os.listdir('.'))
detected, reason = None, ''
for rule in DETECT:
    matched = False
    matched_kw = ''
    if any(f in files for f in rule.get('files', [])):
        matched = True
        matched_kw = next(f for f in rule['files'] if f in files)
    elif rule.get('extensions'):
        for f in files:
            if any(f.endswith(ext) for ext in rule['extensions']):
                matched = True
                matched_kw = f
                break
    # package.json 含特定依赖
    if matched and rule.get('package_deps') and 'package.json' in files:
        try:
            pkg = json.load(open('package.json'))
            deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}
            if not any(k in deps for k in rule['package_deps']):
                matched = False
        except Exception:
            matched = False
    if matched:
        detected = rule['preset']
        reason = f'命中 {matched_kw}'
        break

# ── settings.json 现状 ──
settings_exists = os.path.isfile('.claude/settings.json')
cur_count = 0
if settings_exists:
    try:
        cur = json.load(open('.claude/settings.json'))
        cur_count = len(cur.get('skillOverrides', {}))
    except Exception:
        pass

print(f'已装 plugin: {len(plugins)}')
for p in plugins[:5]:
    print(f'   - {p}')
if len(plugins) > 5:
    print(f'   ... 另外 {len(plugins) - 5} 个')
print(f'用户级 skill: {len(local_skills)}')
print(f'项目级 skill: {len(project_skills)}（走默认 ON）')
print(f'探测项目类型: {detected or "未匹配"}（{reason or "请手动选"}）')
print(f'settings.json: {"存在，含 " + str(cur_count) + " 条 skillOverrides" if settings_exists else "不存在"}')
