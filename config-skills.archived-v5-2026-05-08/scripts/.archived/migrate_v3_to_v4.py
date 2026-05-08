"""一次性迁移脚本：把 v3 的 9 个分散 preset 文件 + 硬编码 RULES + 硬编码 detect
合并为 v4 的单文件 presets/all.json。

执行：python3 migrate_v3_to_v4.py
- 读取 v3 的 4 个 <preset>.json + 4 个 enabled-plugins-<preset>.json
- 嵌入 v3 的 13 条 skill RULES + 4 条 detect 规则 + 新增的 plugin RULES
- 写入 presets/all.json
- 不删除原文件（由后续步骤手动归档）
"""
import json, os, sys

PRESET_DIR = os.path.expanduser('~/.claude/skills/laodao-skills/config-skills/presets/')
PRESET_NAMES = ['content-creation', 'go-dev', 'embedded-dev', 'web-dev']

# ── 读 v3 的 4 个 skill preset ──
preset_skills = {}
for p in PRESET_NAMES:
    with open(os.path.join(PRESET_DIR, f'{p}.json')) as f:
        preset_skills[p] = json.load(f)

# ── 读 v3 的 4 个 plugin preset ──
preset_plugins = {}
for p in PRESET_NAMES:
    with open(os.path.join(PRESET_DIR, f'enabled-plugins-{p}.json')) as f:
        preset_plugins[p] = json.load(f)

# ── 抄自 v3 02_health_check.py 的 13 条 skill RULES ──
SKILL_RULES = [
    {"keywords": ["commit", "git", "tag", "release"], "scope": "skill",
     "values": {p: "on" for p in PRESET_NAMES}},
    {"keywords": ["roadmap", "openspec", "sdd", "project-activate"], "scope": "skill",
     "values": {p: "on" for p in PRESET_NAMES}},
    {"keywords": ["lint", "code-review", "test-driven", "feature-dev", "debug", "refactor"],
     "scope": "skill",
     "values": {"content-creation": "off", "go-dev": "on", "embedded-dev": "on", "web-dev": "on"}},
    {"keywords": ["humanizer", "tech-writing", "mp-article"], "scope": "skill",
     "values": {"content-creation": "on", "go-dev": "off", "embedded-dev": "off",
                "web-dev": "user-invocable-only"}},
    {"keywords": ["embedded", "firmware", "mcu"], "scope": "skill",
     "values": {"content-creation": "off", "go-dev": "off", "embedded-dev": "on", "web-dev": "off"}},
    {"keywords": ["frontend", "ui-ux", "react", "vue", "svelte", "css", "design-html", "figma"],
     "scope": "skill",
     "values": {"content-creation": "user-invocable-only", "go-dev": "off",
                "embedded-dev": "off", "web-dev": "on"}},
    {"keywords": ["qa", "playwright", "chrome-devtools", "browse", "browser", "webapp-testing"],
     "scope": "skill",
     "values": {"content-creation": "user-invocable-only", "go-dev": "user-invocable-only",
                "embedded-dev": "off", "web-dev": "on"}},
    {"keywords": ["seo", "schema", "keyword-cluster"], "scope": "skill",
     "values": {"content-creation": "user-invocable-only", "go-dev": "off",
                "embedded-dev": "off", "web-dev": "user-invocable-only"}},
    {"keywords": ["research", "bilibili", "youtube", "zhihu", "x-research"], "scope": "skill",
     "values": {"content-creation": "user-invocable-only", "go-dev": "off",
                "embedded-dev": "off", "web-dev": "off"}},
    {"keywords": ["pdf", "docx", "xlsx", "pptx", "pdf2md", "docx2md", "xlsx2md", "make-pdf"],
     "scope": "skill",
     "values": {"content-creation": "user-invocable-only", "go-dev": "off",
                "embedded-dev": "off", "web-dev": "off"}},
    {"keywords": ["setup-", "init-", "configure-", "scaffold", "setting-up"], "scope": "skill",
     "values": {p: "off" for p in PRESET_NAMES}},
    {"keywords": ["update", "sync-"], "scope": "skill",
     "values": {p: "user-invocable-only" for p in PRESET_NAMES}},
    {"keywords": ["airflow", "dbt", "data-engineering", "warehouse", "lineage", "dag"],
     "scope": "skill",
     "values": {p: "off" for p in PRESET_NAMES}},
    {"keywords": ["mcp-builder", "mcp-server", "claude-api", "api"], "scope": "skill",
     "values": {p: "user-invocable-only" for p in PRESET_NAMES}},
]

# ── 新增 plugin RULES（按观察到的 4 个 enabled-plugins-*.json 的取值模式总结） ──
PLUGIN_RULES = [
    {"keywords": ["data-engineering", "airflow", "dbt"], "scope": "plugin",
     "values": {p: False for p in PRESET_NAMES}},
    {"keywords": ["gopls"], "scope": "plugin",
     "values": {"content-creation": False, "go-dev": True, "embedded-dev": False, "web-dev": False}},
    {"keywords": ["clangd"], "scope": "plugin",
     "values": {"content-creation": False, "go-dev": False, "embedded-dev": True, "web-dev": False}},
    {"keywords": ["typescript-lsp", "pyright"], "scope": "plugin",
     "values": {"content-creation": False, "go-dev": False, "embedded-dev": False, "web-dev": True}},
    {"keywords": ["frontend", "figma", "playwright", "chrome-devtools", "ui-ux"], "scope": "plugin",
     "values": {"content-creation": False, "go-dev": False, "embedded-dev": False, "web-dev": True}},
    {"keywords": ["code-review", "feature-dev", "pr-review", "semgrep"], "scope": "plugin",
     "values": {"content-creation": False, "go-dev": True, "embedded-dev": True, "web-dev": True}},
    {"keywords": ["seo"], "scope": "plugin",
     "values": {"content-creation": True, "go-dev": False, "embedded-dev": False, "web-dev": True}},
    {"keywords": ["ui-ux-pro-max"], "scope": "plugin",
     "values": {"content-creation": False, "go-dev": False, "embedded-dev": False, "web-dev": True}},
]

# ── 抄自 v3 01_scan.py 的 detect 规则 ──
DETECT = [
    {"preset": "go-dev", "files": ["go.mod"]},
    {"preset": "embedded-dev", "files": ["CMakeLists.txt"], "extensions": [".c", ".h"]},
    {"preset": "content-creation", "files": ["hugo.toml", "hugo.yaml"]},
    {"preset": "web-dev", "files": ["package.json"],
     "package_deps": ["react", "vue", "next", "nuxt", "svelte", "@vue", "@react"]},
]

PRESET_DESC = {
    "content-creation": "写文章、博客、做封面/配图、SDD",
    "go-dev": "Go 后端、CLI 项目",
    "embedded-dev": "嵌入式 C/MCU 固件",
    "web-dev": "前端、全栈、博客 QA",
}

all_json = {
    "$schema_version": "v4",
    "_meta": {
        "note": "config-skills 的单一数据源。加新 preset 只动此文件 + SKILL.md，不动 .py 脚本。",
        "structure": "presets.<name>.{description, skills, plugins} | rules[] | detect[]",
    },
    "presets": {
        p: {
            "description": PRESET_DESC[p],
            "skills": preset_skills[p],
            "plugins": preset_plugins[p],
        }
        for p in PRESET_NAMES
    },
    "rules": SKILL_RULES + PLUGIN_RULES,
    "detect": DETECT,
}

out_path = os.path.join(PRESET_DIR, 'all.json')
tmp = out_path + '.tmp'
with open(tmp, 'w') as f:
    json.dump(all_json, f, indent=2, ensure_ascii=False)
    f.write('\n')
os.replace(tmp, out_path)

# 摘要输出
print(f'✅ 已生成 {out_path}')
for p in PRESET_NAMES:
    s = len(all_json['presets'][p]['skills'])
    pl = len(all_json['presets'][p]['plugins'])
    print(f'   {p:18} skills={s:3}  plugins={pl:3}')
print(f'   skill rules: {len(SKILL_RULES)} | plugin rules: {len(PLUGIN_RULES)} | detect: {len(DETECT)}')
