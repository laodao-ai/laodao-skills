"""一次性迁移：v4 关键字规则版 → 语义推荐版。

做的事：
  1. 备份 all.json → all.json.bak.migration-YYYYMMDD（已存在则中止）
  2. 4 preset description 升级为详细中文版（给 LLM 推荐器看）
  3. 每个 preset 加 _baseline（深拷贝 skills/plugins + ts + prompt_hash 占位）
  4. 22 条关键字 rules 归档到 presets/.archived/v4-rules.json
  5. rules 段瘦身为 1 条 wildcard fallback
  6. 全量内存构造 + 单次 os.replace 原子写入（决策 9）

运行一次即可。已迁移过会因 .bak 已存在而中止。
"""
import json, os, copy, sys
from datetime import date, datetime, timezone

PRESETS_DIR = os.path.expanduser('~/.claude/skills/laodao-skills/config-skills/presets/')
ALL_PATH = os.path.join(PRESETS_DIR, 'all.json')
BAK_PATH = os.path.join(PRESETS_DIR, f'all.json.bak.migration-{date.today():%Y%m%d}')
ARCHIVED_RULES = os.path.join(PRESETS_DIR, '.archived', 'v4-rules.json')

# 4 preset 的详细中文 description 初稿（任务 2.2）
DESCRIPTIONS = {
    'content-creation': (
        '写文章、博客（Hugo + Blowfish）、做封面/配图、SDD（Spec-Driven Development）流程；'
        '常用 OpenSpec 管理变更、技术写作、内容审稿、公众号排版、Obsidian vault 工作流；'
        '不写后端代码、不调外部 API；偶尔涉及前端预览与设计系统调试。'
    ),
    'go-dev': (
        'Go 后端 / CLI 项目开发；包含 go build / go test / go mod 工作流；'
        '可能涉及数据库、HTTP server、命令行工具；'
        '需要单元测试驱动、依赖管理、性能 profiling 等开发能力；'
        '不主要做前端 UI，但可能调试 API 端点。'
    ),
    'embedded-dev': (
        '嵌入式 C / MCU 固件开发；常用 CMakeLists.txt + clangd-lsp；'
        '面向硬件交互、寄存器操作、中断处理、外设驱动；'
        '不需要 web/API/数据库相关 skill，需要底层调试与代码审查能力。'
    ),
    'web-dev': (
        '前端 / 全栈 web 开发；React / Vue / Next.js / Svelte 等 SPA 框架；'
        '可能涉及 Tailwind / shadcn 样式、Playwright / Chrome DevTools 调试；'
        '需要 UI 设计、可访问性审计、性能优化能力；'
        '常用 npm / bun / yarn 包管理；可能涉及部署到 Cloudflare / Vercel 等平台。'
    ),
}

# 旧版 prompt_hash 占位值；下次 --refresh 时自动识别为 hash 不匹配
LEGACY_PROMPT_HASH = 'v4-legacy-no-prompt'

# 1 条 wildcard fallback（决策 4）
WILDCARD_FALLBACK = [{
    'match': '*',
    'scope': 'any',
    'skill_default': 'user-invocable-only',
    'plugin_default': False,
    'comment': '未被 LLM 推荐覆盖时的保守 fallback（v4 22 条关键字规则已归档至 .archived/v4-rules.json）',
}]


def main():
    # 步骤 0：检查 .bak 不存在（避免重复迁移）
    if os.path.exists(BAK_PATH):
        sys.exit(f'❌ 备份文件已存在: {BAK_PATH}\n'
                 f'   表明之前已跑过迁移；如需重跑请先 rm 该备份并 git checkout all.json')

    # 步骤 1：读 all.json
    with open(ALL_PATH, encoding='utf-8') as f:
        d = json.load(f)

    # 步骤 2：内存构造完整新 dict（决策 9 — 一次性原子写）
    presets = d.get('presets', {})
    expected_presets = set(DESCRIPTIONS.keys())
    actual_presets = set(presets.keys())
    if expected_presets != actual_presets:
        sys.exit(f'❌ preset 集合不匹配：期望 {expected_presets}，实际 {actual_presets}')

    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    new_presets = {}
    for name, body in presets.items():
        skills = body.get('skills', {})
        plugins = body.get('plugins', {})
        new_presets[name] = {
            'description': DESCRIPTIONS[name],
            'skills': skills,
            'plugins': plugins,
            '_baseline': {
                'skills': copy.deepcopy(skills),
                'plugins': copy.deepcopy(plugins),
                'ts': now_iso,
                'prompt_hash': LEGACY_PROMPT_HASH,
            },
        }

    # 步骤 3：归档 22 条 rules
    archived_rules = d.get('rules', [])
    archived_payload = {
        '_meta': {
            'archived_from': 'all.json.rules',
            'archived_at': now_iso,
            'note': 'v4 关键字规则版的 rules 段。语义推荐版（v5）仅保留 1 条 wildcard fallback；本文件保留作回滚 / 历史参考用。',
        },
        'rules': archived_rules,
    }

    # 步骤 4：组装新 all.json
    new_all = {
        '$schema_version': d.get('$schema_version'),
        '_meta': {
            **(d.get('_meta', {})),
            'migrated_at': now_iso,
            'migration_note': 'v4 → 语义推荐版 (semantic-skill-recommender)',
        },
        'presets': new_presets,
        'rules': WILDCARD_FALLBACK,
        'detect': d.get('detect', []),
    }

    # 步骤 5：备份原文件
    with open(ALL_PATH, encoding='utf-8') as f:
        original = f.read()
    with open(BAK_PATH, 'w', encoding='utf-8') as f:
        f.write(original)
    print(f'✅ 备份：{BAK_PATH}')

    # 步骤 6：归档 rules（先写 .archived，失败时 .bak 仍可恢复 all.json）
    os.makedirs(os.path.dirname(ARCHIVED_RULES), exist_ok=True)
    tmp = ARCHIVED_RULES + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(archived_payload, f, indent=2, ensure_ascii=False)
        f.write('\n')
    os.replace(tmp, ARCHIVED_RULES)
    print(f'✅ 归档 22 条 rules → {ARCHIVED_RULES}')

    # 步骤 7：原子写 all.json
    tmp = ALL_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(new_all, f, indent=2, ensure_ascii=False)
        f.write('\n')
    os.replace(tmp, ALL_PATH)
    print(f'✅ 已写回 {ALL_PATH}')

    # 摘要
    print()
    print('=== 迁移摘要 ===')
    for name in DESCRIPTIONS:
        p = new_presets[name]
        print(f'  {name}: {len(p["skills"])} skills + {len(p["plugins"])} plugins | desc={len(p["description"])} 字')
    print(f'  rules: 22 → 1 (wildcard fallback)')
    print(f'  下一步：跑 06_apply.py content-creation 验证渲染等价')


if __name__ == '__main__':
    main()
