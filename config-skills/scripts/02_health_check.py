"""Step 2: preset 健康检查（v4：双维度 — skill + plugin）

真相源：
  skill — ~/.claude/skills/<name>/SKILL.md（用户级）+ catalog.plugin_skills（plugin 内置）
  plugin — ~/.claude/plugins/installed_plugins.json 顶层 plugins key

检测：
  missing — 真相源有但所有 4 个 preset 未列
  phantom — preset 列了但真相源无
"""
import json, os

PRESET_NAMES = ['content-creation', 'go-dev', 'embedded-dev', 'web-dev']
PRESET_DIR = os.path.expanduser('~/.claude/skills/laodao-skills/config-skills/presets/')


def load_all():
    with open(os.path.join(PRESET_DIR, 'all.json')) as f:
        return json.load(f)


def infer_default(name, scope, rules):
    """按 name 关键字匹配 rules 中 scope='skill'/'plugin'/'any' 的条目，返回 4-preset 映射。"""
    name_lower = name.lower()
    skill_part = name_lower.split(':')[-1] if ':' in name_lower else name_lower
    plugin_plain = name_lower.split('@')[0] if '@' in name_lower else name_lower

    haystack = skill_part if scope == 'skill' else plugin_plain
    fallback_skill = {p: 'user-invocable-only' for p in PRESET_NAMES}
    fallback_plugin = {p: False for p in PRESET_NAMES}

    for rule in rules:
        if rule.get('scope') not in (scope, 'any'):
            continue
        for kw in rule.get('keywords', []):
            if kw in name_lower or kw in haystack:
                matched = ','.join(k for k in rule['keywords'] if k in name_lower or k in haystack)
                return rule['values'], matched
    return (fallback_skill if scope == 'skill' else fallback_plugin), '未匹配'


def main():
    ALL = load_all()
    presets = ALL['presets']
    rules = ALL.get('rules', [])

    # ── 现有 preset 中的 keys ──
    all_skill_keys = set()
    all_plugin_keys = set()
    for p in PRESET_NAMES:
        all_skill_keys |= set(presets[p].get('skills', {}).keys())
        all_plugin_keys |= set(presets[p].get('plugins', {}).keys())

    # ── 真相源：skill 维度 ──
    local_dir = os.path.expanduser('~/.claude/skills/')
    local_user_skills = set()
    for d in os.listdir(local_dir):
        full = os.path.join(local_dir, d)
        if d == 'laodao-skills':
            continue
        if os.path.isdir(full) and os.path.isfile(os.path.join(full, 'SKILL.md')):
            local_user_skills.add(d)

    catalog_path = os.path.join(PRESET_DIR, 'catalog.json')
    catalog_plugin_skills = set()
    if os.path.isfile(catalog_path):
        with open(catalog_path) as f:
            catalog = json.load(f)
        catalog_plugin_skills = set(catalog.get('plugin_skills', {}).keys())

    bare_keys = {k for k in all_skill_keys if ':' not in k}
    plugin_skill_keys = {k for k in all_skill_keys if ':' in k}

    missing_user = local_user_skills - bare_keys
    missing_plugin_skill = catalog_plugin_skills - plugin_skill_keys
    phantom_user = bare_keys - local_user_skills
    phantom_plugin_skill = plugin_skill_keys - catalog_plugin_skills

    # ── 真相源：plugin 维度 ──
    with open(os.path.expanduser('~/.claude/plugins/installed_plugins.json')) as f:
        installed = set(json.load(f).get('plugins', {}).keys())

    missing_plugin = installed - all_plugin_keys
    phantom_plugin = all_plugin_keys - installed

    missing_skills = missing_user | missing_plugin_skill
    phantom_skills = phantom_user | phantom_plugin_skill

    if not (missing_skills or phantom_skills or missing_plugin or phantom_plugin):
        print('STATUS: preset_in_sync')
        print('所有 4 个 preset 与本地 skill / catalog / installed_plugins 一致，无需同步。')
        return

    print('STATUS: needs_sync')

    if missing_user:
        print(f'\n📥 用户级 skill 待加入 preset（{len(missing_user)} 项）:')
        for s in sorted(missing_user):
            mapping, matched = infer_default(s, 'skill', rules)
            vals = '/'.join(f'{p[0]}:{mapping[p][:3]}' for p in PRESET_NAMES)
            print(f'   + {s:40} 规则: {matched:30} → {vals}')
    if missing_plugin_skill:
        print(f'\n📥 Plugin skill 待加入 preset（{len(missing_plugin_skill)} 项）:')
        for s in sorted(missing_plugin_skill):
            mapping, matched = infer_default(s, 'skill', rules)
            vals = '/'.join(f'{p[0]}:{mapping[p][:3]}' for p in PRESET_NAMES)
            print(f'   + {s:50} 规则: {matched:30} → {vals}')
    if missing_plugin:
        print(f'\n📥 Plugin 待加入 preset（{len(missing_plugin)} 项）:')
        for s in sorted(missing_plugin):
            mapping, matched = infer_default(s, 'plugin', rules)
            vals = '/'.join(f'{p[0]}:{"T" if mapping[p] else "F"}' for p in PRESET_NAMES)
            print(f'   + {s:50} 规则: {matched:30} → {vals}')
    if phantom_user:
        print(f'\n🗑️  用户级 phantom skill（{len(phantom_user)} 项）:')
        for s in sorted(phantom_user):
            print(f'   - {s}')
    if phantom_plugin_skill:
        print(f'\n🗑️  Plugin phantom skill（{len(phantom_plugin_skill)} 项）:')
        for s in sorted(phantom_plugin_skill):
            print(f'   - {s}')
    if phantom_plugin:
        print(f'\n🗑️  Phantom plugin（{len(phantom_plugin)} 项）:')
        for s in sorted(phantom_plugin):
            print(f'   - {s}')

    print(f'\nMISSING_SKILLS_JSON={json.dumps(sorted(missing_skills))}')
    print(f'PHANTOM_SKILLS_JSON={json.dumps(sorted(phantom_skills))}')
    print(f'MISSING_PLUGINS_JSON={json.dumps(sorted(missing_plugin))}')
    print(f'PHANTOM_PLUGINS_JSON={json.dumps(sorted(phantom_plugin))}')


if __name__ == '__main__':
    main()
