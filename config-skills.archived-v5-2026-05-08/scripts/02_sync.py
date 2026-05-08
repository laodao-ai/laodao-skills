"""Step 2 sync: 把 missing/phantom 同步到 all.json 的 4 个 preset（skill + plugin 双维度）。

用法:
  python3 02_sync.py <MISSING_SKILLS_JSON> <PHANTOM_SKILLS_JSON> [MISSING_PLUGINS_JSON] [PHANTOM_PLUGINS_JSON]
"""
import json, os, sys

PRESET_NAMES = ['content-creation', 'go-dev', 'embedded-dev', 'web-dev']
PRESET_DIR = os.path.expanduser('~/.claude/skills/laodao-skills/config-skills/presets/')
ALL_PATH = os.path.join(PRESET_DIR, 'all.json')

if len(sys.argv) < 3:
    print('用法: python3 02_sync.py <MISSING_SKILLS_JSON> <PHANTOM_SKILLS_JSON> [MISSING_PLUGINS_JSON] [PHANTOM_PLUGINS_JSON]')
    sys.exit(1)

missing_skills = set(json.loads(sys.argv[1]))
phantom_skills = set(json.loads(sys.argv[2]))
missing_plugins = set(json.loads(sys.argv[3])) if len(sys.argv) > 3 else set()
phantom_plugins = set(json.loads(sys.argv[4])) if len(sys.argv) > 4 else set()

with open(ALL_PATH) as f:
    ALL = json.load(f)
rules = ALL.get('rules', [])
presets = ALL['presets']


def get_wildcard_default(scope):
    """从 rules 找 wildcard ('*' match) 规则的默认值；与 health-check 文案保持一致。"""
    for rule in rules:
        if rule.get('match') == '*':
            if scope == 'skill':
                return {p: rule.get('skill_default', 'name-only') for p in PRESET_NAMES}
            return {p: rule.get('plugin_default', False) for p in PRESET_NAMES}
    # 硬编码兜底（v5 策略：name-only 是安全默认，避免切断协作链）
    return ({p: 'name-only' for p in PRESET_NAMES} if scope == 'skill'
            else {p: False for p in PRESET_NAMES})


def infer_default(name, scope):
    name_lower = name.lower()
    skill_part = name_lower.split(':')[-1] if ':' in name_lower else name_lower
    plugin_plain = name_lower.split('@')[0] if '@' in name_lower else name_lower
    haystack = skill_part if scope == 'skill' else plugin_plain
    # 关键字规则匹配（v4 兼容）
    for rule in rules:
        if rule.get('scope') not in (scope, 'any'):
            continue
        for kw in rule.get('keywords', []):
            if kw in name_lower or kw in haystack:
                return rule['values']
    # wildcard fallback（与 health-check 文案的"name-only"承诺一致）
    return get_wildcard_default(scope)


added_skill = added_plugin = removed_skill = removed_plugin = 0
for p in PRESET_NAMES:
    skills = presets[p].setdefault('skills', {})
    plugins = presets[p].setdefault('plugins', {})

    for s in missing_skills:
        if s not in skills:
            skills[s] = infer_default(s, 'skill')[p]
            added_skill += 1
    for s in phantom_skills:
        if s in skills:
            del skills[s]
            removed_skill += 1
    for pl in missing_plugins:
        if pl not in plugins:
            plugins[pl] = infer_default(pl, 'plugin')[p]
            added_plugin += 1
    for pl in phantom_plugins:
        if pl in plugins:
            del plugins[pl]
            removed_plugin += 1

tmp = ALL_PATH + '.tmp'
with open(tmp, 'w') as f:
    json.dump(ALL, f, indent=2, ensure_ascii=False)
    f.write('\n')
os.replace(tmp, ALL_PATH)

print('✅ all.json 已同步')
print(f'   skill  — 新增 {added_skill // 4 if added_skill else 0} 项 ×4 preset / 移除 {removed_skill // 4 if removed_skill else 0} 项 ×4 preset')
print(f'   plugin — 新增 {added_plugin // 4 if added_plugin else 0} 项 ×4 preset / 移除 {removed_plugin // 4 if removed_plugin else 0} 项 ×4 preset')
