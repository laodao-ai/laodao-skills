"""LLM 推荐器（v1：emit-prompt + apply 双模式，零 API 依赖）。

模式：
  --emit-prompt  — 读 catalog + 当前 preset → 渲染 prompt 到 stdout
                   Claude 主对话读 prompt → 输出 JSON 到 /tmp/reco.json
  --apply <path> — 读 JSON → 校验 → 跨字段一致性纠正 → 跑依赖闭包 → 写回 all.json + _baseline

用法：
  python3 03_llm_recommend.py --preset content-creation --mode missing --emit-prompt > /tmp/prompt.txt
  python3 03_llm_recommend.py --preset content-creation --apply /tmp/reco.json

零外部依赖：仅 Python 标准库；不导入 anthropic / openai；不发 socket 连接；不读 ANTHROPIC_API_KEY。
"""
import argparse
import copy
import hashlib
import json
import os
import string
import sys
from datetime import datetime, timezone

CONFIG_DIR = os.path.expanduser('~/.claude/skills/laodao-skills/config-skills/')
PRESET_DIR = os.path.join(CONFIG_DIR, 'presets')
ALL_PATH = os.path.join(PRESET_DIR, 'all.json')
CATALOG_PATH = os.path.join(PRESET_DIR, 'catalog.json')
TEMPLATE_PATH = os.path.join(CONFIG_DIR, 'scripts', 'templates', 'recommend.txt')
DEPS_PATH = os.path.join(PRESET_DIR, 'dependencies.json')

DESC_LIST_LIMIT = 200
SKILL_VALID_VALUES = {'on', 'user-invocable-only', 'off'}


# ─────────────────────────────────────────────
# 共享：读文件
# ─────────────────────────────────────────────

def load_all():
    with open(ALL_PATH, encoding='utf-8') as f:
        return json.load(f)


def load_catalog():
    with open(CATALOG_PATH, encoding='utf-8') as f:
        return json.load(f)


def load_template():
    with open(TEMPLATE_PATH, encoding='utf-8') as f:
        return f.read()


def load_deps():
    if not os.path.isfile(DEPS_PATH):
        return {}
    with open(DEPS_PATH, encoding='utf-8') as f:
        d = json.load(f)
    return {k: v.get('calls', []) for k, v in d.get('dependencies', {}).items()}


def prompt_hash():
    """读 prompt 模板算 SHA256 前 12 字符。"""
    with open(TEMPLATE_PATH, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()[:12]


def atomic_write(path, content):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(content)
    os.replace(tmp, path)


# ─────────────────────────────────────────────
# emit-prompt 模式
# ─────────────────────────────────────────────

def compute_targets(preset_data, catalog, mode):
    """根据 mode 返回 (target_skills, target_plugins)。
    mode=missing — 仅 catalog 有但 preset 子树没列的项
    mode=all     — preset 子树的全部项
    """
    catalog_skills = {s['name'] for s in catalog.get('skills_enriched', [])}
    catalog_plugins = {p['name'] for p in catalog.get('plugins_enriched', [])}

    preset_skills = set(preset_data.get('skills', {}).keys())
    preset_plugins = set(preset_data.get('plugins', {}).keys())

    if mode == 'missing':
        target_skills = catalog_skills - preset_skills
        target_plugins = catalog_plugins - preset_plugins
    else:  # all
        target_skills = preset_skills | catalog_skills
        target_plugins = preset_plugins | catalog_plugins

    return target_skills, target_plugins


def render_skill_line(s_entry):
    desc = (s_entry.get('description') or '').replace('\n', ' ')[:DESC_LIST_LIMIT]
    return f"- {s_entry['name']} | {s_entry['source']} | {desc}"


def render_plugin_line(p_entry):
    desc = (p_entry.get('description') or '').replace('\n', ' ')[:DESC_LIST_LIMIT]
    return f"- {p_entry['name']} | {p_entry.get('author', '?')} | {desc}"


def render_current_state(preset_data, target_skills, target_plugins, mode):
    if mode == 'missing':
        return '（missing 模式，无当前状态参考——这些项在 preset 中尚未列出）'
    skills = preset_data.get('skills', {})
    plugins = preset_data.get('plugins', {})
    lines = ['当前状态片段（参考，不是答案——LLM 应根据 description 重判断）：', '']
    lines.append('skills（部分）：')
    for k in sorted(target_skills)[:30]:
        if k in skills:
            lines.append(f'  {k}: {skills[k]}')
    if len(target_skills) > 30:
        lines.append(f'  ... 及其余 {len(target_skills) - 30} 项 skill')
    lines.append('plugins（全部）：')
    for k in sorted(target_plugins):
        if k in plugins:
            lines.append(f'  {k}: {plugins[k]}')
    return '\n'.join(lines)


def emit_prompt(preset_name, mode):
    all_data = load_all()
    catalog = load_catalog()

    if preset_name not in all_data['presets']:
        sys.exit(f'❌ preset 不存在: {preset_name}')

    preset = all_data['presets'][preset_name]
    target_skills, target_plugins = compute_targets(preset, catalog, mode)

    if not target_skills and not target_plugins:
        sys.exit(f'⚠️  preset={preset_name} mode={mode} 没有目标项，无需生成 prompt')

    skills_idx = {s['name']: s for s in catalog.get('skills_enriched', [])}
    plugins_idx = {p['name']: p for p in catalog.get('plugins_enriched', [])}

    skill_list_lines = [render_skill_line(skills_idx[n]) for n in sorted(target_skills) if n in skills_idx]
    plugin_list_lines = [render_plugin_line(plugins_idx[n]) for n in sorted(target_plugins) if n in plugins_idx]

    template = load_template()
    rendered = string.Template(template).safe_substitute(
        preset_name=preset_name,
        preset_description=preset.get('description', '(无描述)'),
        skill_count=len(skill_list_lines),
        plugin_count=len(plugin_list_lines),
        skill_list='\n'.join(skill_list_lines),
        plugin_list='\n'.join(plugin_list_lines),
        mode=mode,
        current_state_block=render_current_state(preset, target_skills, target_plugins, mode),
    )
    sys.stdout.write(rendered)


# ─────────────────────────────────────────────
# apply 模式
# ─────────────────────────────────────────────

def validate_schema(data, preset_name):
    """严格 schema 校验。返回错误列表（空 = 通过）。"""
    errors = []
    if not isinstance(data, dict):
        return ['顶层不是 JSON 对象']
    if data.get('preset') != preset_name:
        errors.append(f'preset 字段不匹配：期望 {preset_name}，实际 {data.get("preset")}')
    skills = data.get('skills', {})
    plugins = data.get('plugins', {})
    if not isinstance(skills, dict):
        errors.append('skills 字段不是对象')
    else:
        for k, v in skills.items():
            if v not in SKILL_VALID_VALUES:
                errors.append(f'skills["{k}"] 值非法：{v!r}（期望 on / user-invocable-only / off）')
    if not isinstance(plugins, dict):
        errors.append('plugins 字段不是对象')
    else:
        for k, v in plugins.items():
            if not isinstance(v, bool):
                errors.append(f'plugins["{k}"] 值不是布尔：{v!r}（期望 true / false）')
    return errors


def reconcile_plugin_skill_consistency(skills, plugins):
    """跨字段一致性纠正：plugin=False 时其下属 skill 强制 off。
    返回受影响的 skill 名列表。
    """
    disabled_plugin_plain = set()
    for plugin_name, val in plugins.items():
        if val is False:
            plain = plugin_name.split('@')[0]
            disabled_plugin_plain.add(plain)
    fixed = []
    for skill_name, val in list(skills.items()):
        if val == 'off' or ':' not in skill_name:
            continue
        owner = skill_name.split(':')[0]
        if owner in disabled_plugin_plain and val != 'off':
            skills[skill_name] = 'off'
            fixed.append(skill_name)
    return fixed


def enforce_dependencies(skills, deps):
    """对 skills dict 做依赖闭包（与 025_enforce_deps 等价）。
    返回升级数量。
    """
    fixed_count = 0
    changed = True
    while changed:
        changed = False
        for skill, value in list(skills.items()):
            if value in ('on', 'user-invocable-only') and skill in deps:
                for callee in deps[skill]:
                    if skills.get(callee) != 'on':
                        skills[callee] = 'on'
                        fixed_count += 1
                        changed = True
    return fixed_count


def apply(preset_name, json_path):
    if not os.path.isfile(json_path):
        sys.exit(f'❌ JSON 文件不存在: {json_path}')

    with open(json_path, encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            sys.exit(f'❌ JSON 解析失败: {e}')

    # 1. 严格 schema 校验（任务 3.3）
    errors = validate_schema(data, preset_name)
    if errors:
        print('❌ schema 校验失败:', file=sys.stderr)
        for e in errors:
            print(f'   {e}', file=sys.stderr)
        sys.exit(1)

    new_skills = data['skills']
    new_plugins = data['plugins']

    # 2. 跨字段一致性纠正（任务 3.8）
    fixed_skills = reconcile_plugin_skill_consistency(new_skills, new_plugins)
    if fixed_skills:
        print(f'⚠️  自动纠正 {len(fixed_skills)} 项 plugin↔skill 矛盾（plugin=False → skill=off）')
        for s in fixed_skills[:10]:
            print(f'   {s}')
        if len(fixed_skills) > 10:
            print(f'   ... 及其余 {len(fixed_skills) - 10} 项')

    # 3. 加载 all.json 与 deps（任务 3.9）
    all_data = load_all()
    if preset_name not in all_data['presets']:
        sys.exit(f'❌ preset 不存在: {preset_name}')
    deps = load_deps()

    preset = all_data['presets'][preset_name]
    # 写 LLM 推荐到 preset
    preset['skills'] = new_skills
    preset['plugins'] = new_plugins

    # 跑依赖闭包
    enforced_count = enforce_dependencies(new_skills, deps)
    if enforced_count:
        print(f'⚠️  依赖闭包强升 {enforced_count} 项 skill 到 on')

    # 4. 刷新 _baseline = enforce 后快照（决策 8）+ prompt_hash（决策 12）
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    preset['_baseline'] = {
        'skills': copy.deepcopy(new_skills),
        'plugins': copy.deepcopy(new_plugins),
        'ts': now_iso,
        'prompt_hash': prompt_hash(),
    }

    # 5. 原子写回（任务 3.4）
    tmp = ALL_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)
        f.write('\n')
    os.replace(tmp, ALL_PATH)

    # 摘要
    skill_summary = {'on': 0, 'user-invocable-only': 0, 'off': 0}
    for v in new_skills.values():
        skill_summary[v] = skill_summary.get(v, 0) + 1
    plugin_enabled = sum(1 for v in new_plugins.values() if v)
    plugin_disabled = sum(1 for v in new_plugins.values() if not v)
    print()
    print(f'✅ 已应用 LLM 推荐到 preset={preset_name}')
    print(f'   skills: ON={skill_summary["on"]} | u-i-o={skill_summary["user-invocable-only"]} | off={skill_summary["off"]}')
    print(f'   plugins: enabled={plugin_enabled} | disabled={plugin_disabled}')
    print(f'   _baseline.prompt_hash={preset["_baseline"]["prompt_hash"]}')


# ─────────────────────────────────────────────
# main
# ─────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description='LLM 语义推荐器（emit-prompt + apply）')
    p.add_argument('--preset', required=True, help='目标 preset 名（如 content-creation）')
    p.add_argument('--mode', choices=['missing', 'all'], default='all',
                   help='推荐范围：missing=仅缺失项，all=全表')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--emit-prompt', action='store_true', help='输出 prompt 到 stdout')
    g.add_argument('--apply', metavar='JSON_PATH', help='应用 LLM 输出 JSON 到 all.json')
    args = p.parse_args()

    if args.emit_prompt:
        emit_prompt(args.preset, args.mode)
    elif args.apply:
        apply(args.preset, args.apply)


if __name__ == '__main__':
    main()
