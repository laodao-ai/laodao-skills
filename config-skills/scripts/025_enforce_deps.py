"""Step 2.5: 依赖校验 — 对所有 preset 做传递闭包，将子 skill 强制升为 on。
规则：preset 中值为 'on' 或 'user-invocable-only' 的 skill，
      其 dependencies.json 中 calls 列表的所有 callee 必须为 'on'。
"""
import json, os

PRESET_NAMES = ['content-creation', 'go-dev', 'embedded-dev', 'web-dev']
PRESET_DIR = os.path.expanduser('~/.claude/skills/laodao-skills/config-skills/presets/')

with open(os.path.join(PRESET_DIR, 'dependencies.json')) as f:
    dep_data = json.load(f)
deps = {k: v.get('calls', []) for k, v in dep_data.get('dependencies', {}).items()}

total_fixed = 0
for preset_name in PRESET_NAMES:
    path = os.path.join(PRESET_DIR, f'{preset_name}.json')
    with open(path) as f:
        preset = json.load(f)

    fixed = {}
    changed = True
    while changed:
        changed = False
        for skill, value in list(preset.items()):
            if value in ('on', 'user-invocable-only') and skill in deps:
                for callee in deps[skill]:
                    if preset.get(callee) != 'on':
                        old = preset.get(callee, '(未列出)')
                        preset[callee] = 'on'
                        fixed[callee] = old
                        changed = True

    if fixed:
        tmp = path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(preset, f, indent=2, ensure_ascii=False)
            f.write('\n')
        os.replace(tmp, path)
        print(f'  {preset_name}: 强制升 on → {list(fixed.keys())}')
        total_fixed += len(fixed)

if total_fixed == 0:
    print('STATUS: deps_ok — 所有依赖已满足，无需调整')
else:
    print(f'\n共强制升级 {total_fixed} 项')
