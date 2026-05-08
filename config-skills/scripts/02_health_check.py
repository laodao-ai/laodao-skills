"""Step 2: preset 健康检查（v5：语义推荐版 — 触发条件检测 + 优先级状态）

真相源：
  skill — ~/.claude/skills/<name>/SKILL.md（用户级）+ catalog.skills_enriched（plugin 内置）
  plugin — ~/.claude/plugins/installed_plugins.json 顶层 plugins key

检测维度：
  phantom — preset 列了但真相源无（必须 sync 清理）
  missing — 真相源有但任一 preset 未列（可 sync 用 wildcard fallback，可 llm_recommend 升级）
  empty   — preset description 已填但 skills/plugins 子树为空（必须 llm_recommend 全表生成）
  drift   — preset description 与 _baseline 不一致（提示但不强制）

状态优先级（决策 13）：
  preset_in_sync > needs_sync > needs_llm_recommend > needs_sync_then_llm_recommend > deps_ok

  preset_in_sync                 — 全无变化
  needs_sync                     — 仅 phantom（不需 LLM）
  needs_llm_recommend            — 有 missing 或 empty
  needs_sync_then_llm_recommend  — phantom 与 (missing|empty) 同时存在
"""
import json
import os

PRESET_NAMES = ['content-creation', 'go-dev', 'embedded-dev', 'web-dev']
PRESET_DIR = os.path.expanduser('~/.claude/skills/laodao-skills/config-skills/presets/')


def load_all():
    with open(os.path.join(PRESET_DIR, 'all.json'), encoding='utf-8') as f:
        return json.load(f)


def load_catalog():
    p = os.path.join(PRESET_DIR, 'catalog.json')
    if not os.path.isfile(p):
        return {}
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def get_wildcard_defaults(rules):
    """从 rules 段取 wildcard fallback。决策 4：只有 1 条 wildcard 规则。"""
    skill_default = 'user-invocable-only'
    plugin_default = False
    for r in rules:
        if r.get('match') == '*':
            skill_default = r.get('skill_default', skill_default)
            plugin_default = r.get('plugin_default', plugin_default)
            break
    return skill_default, plugin_default


def main():
    ALL = load_all()
    presets = ALL['presets']
    rules = ALL.get('rules', [])
    catalog = load_catalog()

    skill_default, plugin_default = get_wildcard_defaults(rules)

    # ── 现有 preset 中的 keys ──
    all_skill_keys = set()
    all_plugin_keys = set()
    for p in PRESET_NAMES:
        all_skill_keys |= set(presets[p].get('skills', {}).keys())
        all_plugin_keys |= set(presets[p].get('plugins', {}).keys())

    # ── 真相源：catalog enriched + installed_plugins ──
    catalog_skills = {s['name'] for s in catalog.get('skills_enriched', [])}
    catalog_plugins = {p['name'] for p in catalog.get('plugins_enriched', [])}

    # 兼容旧字段（若 enriched 缺失）
    if not catalog_skills and catalog:
        catalog_skills = set(catalog.get('plugin_skills', {}).keys()) | set(catalog.get('user_skills', {}).keys())
    if not catalog_plugins and catalog:
        catalog_plugins = set(catalog.get('plugins', {}).keys())

    with open(os.path.expanduser('~/.claude/plugins/installed_plugins.json')) as f:
        installed = set(json.load(f).get('plugins', {}).keys())
    catalog_plugins |= installed  # 双源保险

    # ── missing / phantom ──
    missing_skills = catalog_skills - all_skill_keys
    phantom_skills = all_skill_keys - catalog_skills
    missing_plugins = catalog_plugins - all_plugin_keys
    phantom_plugins = all_plugin_keys - catalog_plugins

    # ── 触发条件 2：empty preset（description 已填但 skills/plugins 空）──
    empty_presets = []
    for name in PRESET_NAMES:
        body = presets[name]
        desc = (body.get('description') or '').strip()
        if desc and (not body.get('skills') or not body.get('plugins')):
            empty_presets.append(name)

    # ── 触发条件 3：description 漂移检测 ──
    drift_presets = []
    for name in PRESET_NAMES:
        body = presets[name]
        baseline = body.get('_baseline', {})
        # 我们没在 baseline 存 description（节省空间），用 prompt_hash 对比代替；
        # 此处仅记录"baseline 存在但 description 字段被改"的情况——v1 不实现，留作未来
        # 仅检查：baseline 不存在 = 还没跑过 LLM 推荐 = description 必然 drift（提示用户跑 --refresh）
        if not baseline:
            drift_presets.append((name, 'no-baseline'))
        elif baseline.get('prompt_hash', '').startswith('v4-legacy'):
            drift_presets.append((name, 'legacy-prompt-hash'))

    # ── 状态决策（决策 13）──
    has_phantom = bool(phantom_skills or phantom_plugins)
    has_missing_or_empty = bool(missing_skills or missing_plugins or empty_presets)

    if not has_phantom and not has_missing_or_empty:
        status = 'preset_in_sync'
    elif has_phantom and has_missing_or_empty:
        status = 'needs_sync_then_llm_recommend'
    elif has_phantom:
        status = 'needs_sync'
    else:  # has_missing_or_empty
        status = 'needs_llm_recommend'

    print(f'STATUS: {status}')

    if status == 'preset_in_sync':
        print('所有 4 个 preset 与 catalog / installed_plugins 一致；无 missing / phantom / empty。')

    if missing_skills:
        print(f'\n📥 missing skills（catalog 有但 preset 未列，{len(missing_skills)} 项）:')
        for s in sorted(missing_skills)[:15]:
            print(f'   + {s}  → fallback={skill_default}（或跑 LLM 推荐升级）')
        if len(missing_skills) > 15:
            print(f'   ... 及其余 {len(missing_skills) - 15} 项')

    if missing_plugins:
        print(f'\n📥 missing plugins（installed 但 preset 未列，{len(missing_plugins)} 项）:')
        for p in sorted(missing_plugins):
            print(f'   + {p}  → fallback={plugin_default}（或跑 LLM 推荐升级）')

    if phantom_skills:
        print(f'\n🗑️  phantom skills（preset 列了但 catalog 无，{len(phantom_skills)} 项）:')
        for s in sorted(phantom_skills)[:15]:
            print(f'   - {s}')
        if len(phantom_skills) > 15:
            print(f'   ... 及其余 {len(phantom_skills) - 15} 项')

    if phantom_plugins:
        print(f'\n🗑️  phantom plugins（preset 列了但未 installed，{len(phantom_plugins)} 项）:')
        for p in sorted(phantom_plugins):
            print(f'   - {p}')

    if empty_presets:
        print(f'\n📭 empty presets（description 已填但 skills/plugins 空，需 LLM 全表生成）:')
        for name in empty_presets:
            print(f'   ⚠️  {name}')

    if drift_presets:
        print(f'\n💡 提示（不阻断流程）:')
        for name, reason in drift_presets:
            if reason == 'no-baseline':
                print(f'   {name}: 无 _baseline；建议跑 /config-skills --refresh {name}')
            elif reason == 'legacy-prompt-hash':
                print(f'   {name}: prompt_hash 为 v4-legacy 占位；首次 --refresh 时所有项视为 LLM 自动管理')

    # 机器可读 JSON 输出（02_sync.py 等下游会解析）
    print(f'\nMISSING_SKILLS_JSON={json.dumps(sorted(missing_skills))}')
    print(f'PHANTOM_SKILLS_JSON={json.dumps(sorted(phantom_skills))}')
    print(f'MISSING_PLUGINS_JSON={json.dumps(sorted(missing_plugins))}')
    print(f'PHANTOM_PLUGINS_JSON={json.dumps(sorted(phantom_plugins))}')
    print(f'EMPTY_PRESETS_JSON={json.dumps(empty_presets)}')


if __name__ == '__main__':
    main()
