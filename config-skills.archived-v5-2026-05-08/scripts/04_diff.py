"""Step 4: 校验 + 算双维度 Diff（skill + plugin）+ 幂等检查（v4）。
用法: python3 04_diff.py <preset>
"""
import json, os, sys
from collections import Counter

if len(sys.argv) < 2:
    print('用法: python3 04_diff.py <preset>')
    sys.exit(1)

PRESET = sys.argv[1]
PRESET_DIR = os.path.expanduser('~/.claude/skills/laodao-skills/config-skills/presets/')

with open(os.path.join(PRESET_DIR, 'all.json')) as f:
    ALL = json.load(f)
if PRESET not in ALL['presets']:
    print(f'❌ 未知 preset: {PRESET}（合法: {list(ALL["presets"].keys())}）')
    sys.exit(1)

target_skills = ALL['presets'][PRESET].get('skills', {})
target_plugins = ALL['presets'][PRESET].get('plugins', {})

# ── skill 校验：bare name 必须在本地存在；plugin:skill 走 catalog ──
local_dir = os.path.expanduser('~/.claude/skills/')
existing_local = set(os.listdir(local_dir)) if os.path.isdir(local_dir) else set()

catalog_path = os.path.join(PRESET_DIR, 'catalog.json')
catalog_plugin_skills = set()
if os.path.isfile(catalog_path):
    catalog_plugin_skills = set(json.load(open(catalog_path)).get('plugin_skills', {}).keys())

phantom_skill = []
clean_skills = {}
for k, v in target_skills.items():
    if ':' in k:
        if k in catalog_plugin_skills:
            clean_skills[k] = v
        else:
            phantom_skill.append(k)
    elif k in existing_local:
        clean_skills[k] = v
    else:
        phantom_skill.append(k)

# ── 当前 settings.json ──
cur_skills, cur_plugins = {}, {}
if os.path.isfile('.claude/settings.json'):
    cur = json.load(open('.claude/settings.json'))
    cur_skills = cur.get('skillOverrides', {})
    cur_plugins = cur.get('enabledPlugins', {})

# ── skill diff ──
all_skill_keys = set(clean_skills) | set(cur_skills)
skill_changes = {}
for k in all_skill_keys:
    cur_v = cur_skills.get(k, 'on')
    new_v = clean_skills.get(k, 'on')
    if cur_v != new_v:
        skill_changes[k] = (cur_v, new_v)

# ── plugin diff ──
all_plugin_keys = set(target_plugins) | set(cur_plugins)
plugin_changes = {}
for k in all_plugin_keys:
    cur_v = cur_plugins.get(k, True)
    new_v = target_plugins.get(k, True)
    if cur_v != new_v:
        plugin_changes[k] = (cur_v, new_v)

if not skill_changes and not plugin_changes:
    print('STATUS: already_up_to_date')
    print(f'当前 settings.json 与 {PRESET} preset 一致（skill + plugin 双维度），无需变更。')
    if phantom_skill:
        print(f'⚠️  仍有 {len(phantom_skill)} 项 phantom skill（preset 列了但本地/catalog 找不到）')
    sys.exit(0)

print('STATUS: needs_update')
print(f'\n📊 Diff 摘要（{PRESET}）')
print(f'   将变更 skill 数:  {len(skill_changes)}')
print(f'   将变更 plugin 数: {len(plugin_changes)}')

if skill_changes:
    by_target = Counter(t for _, t in skill_changes.values())
    print('\n📊 Skill 变更')
    for t in ['on', 'user-invocable-only', 'off']:
        if t in by_target:
            print(f'   → {t}: {by_target[t]} 项')
    if phantom_skill:
        print(f'\n⚠️  本地未找到 skill（已跳过 {len(phantom_skill)} 项）:')
        for p in phantom_skill[:10]:
            print(f'   - {p}')
        if len(phantom_skill) > 10:
            print(f'   ... 及其余 {len(phantom_skill) - 10} 项')

    print('\n📋 Skill 变更明细（前 20 项）:')
    for k, (old, new) in list(skill_changes.items())[:20]:
        print(f'   {k:50} {str(old):25} → {new}')
    if len(skill_changes) > 20:
        print(f'   ... 及其余 {len(skill_changes) - 20} 项')

if plugin_changes:
    by_target = Counter('enable' if t else 'disable' for _, t in plugin_changes.values())
    print('\n📊 Plugin 变更')
    for t in ['enable', 'disable']:
        if t in by_target:
            print(f'   → {t}: {by_target[t]} 项')

    print('\n📋 Plugin 变更明细（前 20 项）:')
    for k, (old, new) in list(plugin_changes.items())[:20]:
        print(f'   {k:50} {str(old):8} → {new}')
    if len(plugin_changes) > 20:
        print(f'   ... 及其余 {len(plugin_changes) - 20} 项')
