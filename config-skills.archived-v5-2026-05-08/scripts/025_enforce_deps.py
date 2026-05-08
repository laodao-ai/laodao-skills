"""Step 2.5: 依赖校验 — 对所有 preset 做传递闭包，将子 skill 强制升为 on。
规则：preset 中值为 'on' 的 skill（会被模型自动触发），其 dependencies.json
      中 calls 列表的所有 callee 必须为 'on'。

设计前提：caller 是 name-only / user-invocable-only / off 时，模型不会自动调它，
也就没有"突然调用 callee"的风险，callee 不必预先 on。这避免了把 name-only 的
gstack/office-hours 等聚合入口的 callee 全部强制升回 on，让降级真正生效。

v4: 数据源切换到 presets/all.json（presets.<name>.skills 子树）。
v5.2: 规则收窄到 value == 'on'（之前是 != 'off'，过严）。
"""
import json, os

PRESET_NAMES = ['content-creation', 'go-dev', 'embedded-dev', 'web-dev']
PRESET_DIR = os.path.expanduser('~/.claude/skills/laodao-skills/config-skills/presets/')
ALL_PATH = os.path.join(PRESET_DIR, 'all.json')

with open(os.path.join(PRESET_DIR, 'dependencies.json')) as f:
    dep_data = json.load(f)
deps = {k: v.get('calls', []) for k, v in dep_data.get('dependencies', {}).items()}

with open(ALL_PATH) as f:
    all_data = json.load(f)

total_fixed = 0
for preset_name in PRESET_NAMES:
    skills = all_data['presets'][preset_name]['skills']

    fixed = {}
    changed = True
    while changed:
        changed = False
        for skill, value in list(skills.items()):
            if value == 'on' and skill in deps:
                for callee in deps[skill]:
                    if skills.get(callee) != 'on':
                        old = skills.get(callee, '(未列出)')
                        skills[callee] = 'on'
                        fixed[callee] = old
                        changed = True

    if fixed:
        print(f'  {preset_name}: 强制升 on → {list(fixed.keys())}')
        total_fixed += len(fixed)

if total_fixed > 0:
    tmp = ALL_PATH + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)
        f.write('\n')
    os.replace(tmp, ALL_PATH)
    print(f'\n共强制升级 {total_fixed} 项')
else:
    print('STATUS: deps_ok — 所有依赖已满足，无需调整')
