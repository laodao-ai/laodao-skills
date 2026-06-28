# Changelog

## 1.2.0 — 2026-06-28

- 新增 `/spec-review` skill：并行多镜的独立设计评审，操作化项目 `openspec/workflow/spec-review.md` 方法论
  - 主 session（强模型）协调 + 对抗裁决 + AskUserQuestion；fan-out 领域镜 / 对抗镜 / 接地镜 并行子 agent
  - 只审 prevention 焊不住的残差（Validation / 对抗 / 接地读码），与 gstack autoplan 互补、不重复（autoplan 已含 eng 镜）
  - 按本步性质选 model：综合判断/门禁 = 强模型，对抗/领域判断 = Sonnet，机械接地 = Haiku

## 1.1.0 — 2026-05-08

- config-skills v3 → v4 重构：渲染模型 + plugin 维度对称化 + 单文件 preset
- 9 个分散 preset 文件合并为 `presets/all.json`（含 presets / rules / detect 三段）
- 13 条 skill RULES + 4 条 detect 外置到 JSON，加新 preset 不再需改 Python
- 新增 plugin 维度的 health-check / 智能规则推断 / diff 展示 / sync / 矛盾态校验
- `06_apply.py` 加 `--dry-run` 预览模式
- 明确双层 settings 模型：settings.json 是渲染产物（git track），settings.local.json 是本机微调层（gitignore）
- 旧 9 个 preset 文件归档到 `presets/.archived/`，迁移脚本归档到 `scripts/.archived/`

## 1.0.0 — 2026-04-10

- 首次发布，包含 13 个自建 skill
- 新增 setup.sh 跨平台安装脚本（Linux/macOS symlink，Windows copy）
- 新增 /ld-update skill，支持在 Claude Code 内一键更新
