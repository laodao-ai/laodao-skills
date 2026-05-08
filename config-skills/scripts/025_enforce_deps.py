"""Step 2.5: 依赖校验 — 对所有 preset 做传递闭包，将子 skill 强制升为 on。
规则：preset 中值为 'on' 或 'user-invocable-only' 的 skill，
      其 dependencies.json 中 calls 列表的所有 callee 必须为 'on'。

v4: 数据源切换到 presets/all.json（presets.<name>.skills 子树）。
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
            if value in ('on', 'user-invocable-only') and skill in deps:
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
