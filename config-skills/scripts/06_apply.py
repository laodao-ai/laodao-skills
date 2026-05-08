"""Step 6: 备份 + 渲染 settings.json（v4：单源 all.json + 双维度 + dry-run）。

用法:
  python3 06_apply.py <preset>            # 正常应用
  python3 06_apply.py --dry-run <preset>  # 渲染并打印，不写文件、不备份

数据流：
  source = presets/all.json[<preset>] → 渲染产物 .claude/settings.json
  仅覆盖 skillOverrides 与 enabledPlugins 两个字段；其他字段（permissions / hooks / env / output_style 等）保留不变。
  绝不读取也不写入 .claude/settings.local.json（本机微调层由用户独立维护）。
"""
import json, os, sys, shutil, datetime, glob
from collections import Counter

DRY_RUN = False
args = sys.argv[1:]
if '--dry-run' in args:
    DRY_RUN = True
    args.remove('--dry-run')

if not args:
    print('用法: python3 06_apply.py [--dry-run] <preset>')
    sys.exit(1)

PRESET = args[0]
PRESET_DIR = os.path.expanduser('~/.claude/skills/laodao-skills/config-skills/presets/')
SETTINGS_PATH = '.claude/settings.json'

with open(os.path.join(PRESET_DIR, 'all.json')) as f:
    ALL = json.load(f)
if PRESET not in ALL['presets']:
    print(f'❌ 未知 preset: {PRESET}')
    sys.exit(1)

new_skills = ALL['presets'][PRESET].get('skills', {})
new_plugins = ALL['presets'][PRESET].get('plugins', {})

# ── 读现状 ──
cur = {}
if os.path.isfile(SETTINGS_PATH):
    with open(SETTINGS_PATH) as f:
        cur = json.load(f)
elif not DRY_RUN:
    os.makedirs('.claude', exist_ok=True)

# ── 矛盾态校验（warning，不阻断） ──
warnings = []
for skill_key, skill_val in new_skills.items():
    if ':' not in skill_key:
        continue
    if skill_val not in ('on', 'name-only', 'user-invocable-only'):
        continue
    plugin_name = skill_key.split(':', 1)[0]
    matched_plugin = next((k for k in new_plugins if k.split('@')[0] == plugin_name), None)
    if matched_plugin and new_plugins[matched_plugin] is False:
        warnings.append((skill_key, matched_plugin))

if warnings:
    print('⚠️  矛盾态 warning（plugin 被禁但其 skill = on/u-i-o，实际不会生效）:')
    for s, p in warnings[:10]:
        print(f'   - {s:50} ← plugin {p} = false')
    if len(warnings) > 10:
        print(f'   ... 及其余 {len(warnings) - 10} 项')
    print()

# ── invariant 校验（决策 11 / brainstorm-amendment）：所有用户级与 plugin 级 skill 必须显式列出 ──
catalog_path = os.path.expanduser('~/.claude/skills/laodao-skills/config-skills/presets/catalog.json')
if os.path.isfile(catalog_path):
    with open(catalog_path, encoding='utf-8') as f:
        _catalog = json.load(f)
    _expected = set(_catalog.get('user_skills', {}).keys()) | set(_catalog.get('plugin_skills', {}).keys())
    _actual = set(new_skills.keys())
    _missing_in_overrides = _expected - _actual
    if _missing_in_overrides:
        print(f'❌ invariant 校验失败：catalog 中 {len(_missing_in_overrides)} 项 skill 未出现在 skillOverrides，'
              f'违反决策 11（禁止 omit）')
        for s in sorted(_missing_in_overrides)[:10]:
            print(f'   - {s}')
        if len(_missing_in_overrides) > 10:
            print(f'   ... 及其余 {len(_missing_in_overrides) - 10} 项')
        sys.exit(1)

# ── 渲染 ──
new_settings = dict(cur)
new_settings['skillOverrides'] = new_skills
new_settings['enabledPlugins'] = new_plugins

if DRY_RUN:
    print('=== DRY-RUN 渲染结果 ===')
    print(json.dumps(new_settings, indent=2, ensure_ascii=False))
    print('\nDRY-RUN: no files written')
    sys.exit(0)

# ── 备份（仅在文件已存在时） ──
bak = None
if os.path.isfile(SETTINGS_PATH):
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = SETTINGS_PATH + f'.bak.{ts}'
    shutil.copy2(SETTINGS_PATH, bak)
    for old in sorted(glob.glob(SETTINGS_PATH + '.bak.*'))[:-3]:
        os.remove(old)

# ── 原子写 ──
tmp = SETTINGS_PATH + '.tmp'
with open(tmp, 'w') as f:
    json.dump(new_settings, f, indent=2, ensure_ascii=False)
    f.write('\n')
os.replace(tmp, SETTINGS_PATH)

sc = Counter(new_skills.values())
pc = Counter(new_plugins.values())
print(f'✅ 已应用 {PRESET}')
if bak:
    print(f'   备份: {bak}')
print(f'   skillOverrides — ON: {sc.get("on", 0)} | name-only: {sc.get("name-only", 0)} | u-i-o: {sc.get("user-invocable-only", 0)} | off: {sc.get("off", 0)}')
print(f'   enabledPlugins — enabled: {pc.get(True, 0)} | disabled: {pc.get(False, 0)}')
if warnings:
    print(f'   ⚠️  含 {len(warnings)} 项 plugin↔skill 矛盾态（见上方 warning）')
