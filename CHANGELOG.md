# Changelog

## 1.5.0 — 2026-06-28

- 新增 `/buglist-recorder` skill：自动记录/回写/扫描 buglist（`openspec/buglists/YYYY-MM-DD-buglist.md`）
  - 脚本兜底确定性：全局 ID 自增、今日文件/目录创建、状态总览表↔详细块双写一致、FIXED 门禁（必带根因+证据）、扫描+一致性自检
  - 自包含整套约定（原 openspec rule 已删，skill 成唯一真相源）
- 新增 `/todolist-recorder` skill：buglist 的姊妹版，记录优化想法/技术债/改进（`openspec/todolists/YYYY-MM-todolist.md`）
  - 差异：每月一文件、T 前缀、按类型分类、详细块可选（轻量优先）、DONE 门禁（必带关联 change/commit）
  - 与 buglist-recorder 明确分工：缺陷用 buglist，改进用 todolist

## 1.4.0 — 2026-06-28

- 新增 `/impl-review` skill：并行多镜的独立**代码实现**评审，是 `/spec-review` 的代码侧镜像，操作化 `openspec/workflow/code-checklists/`（CR-01~09 + 领域 delta）
  - 镜头：领域镜（逐条过 code-checklists）+ 对抗镜（证明运行期会爆：竞态/泄漏/错误路径）+ 历史镜（git blame + 旧 PR 意见）+ 置信过滤（<80 滤除 nitpick/假阳，借官方 code-review 插件 rubric）
  - **与 spec-review 唯一结构差异**：代码即 ground truth，去掉接地镜，换成历史镜 + 置信过滤
  - 与 gstack/review（scope-drift + 计划审计）、官方 /code-review（PR 回帖）**互补不重复**；自制 skill 做清单逐条 + 对抗的主审
  - 按本步性质选 model：裁决/门禁 = 强模型，对抗/领域 = Sonnet，blame/打分 = Haiku
  - 出 `impl-review-report.md`，改动标 `[impl-review-fix]`
- `/spec-review` 微调：finding 加**置信/严重度标注**，明确 **escalate-not-drop**（不确定项上抛而非静默丢）；注明与 impl-review 数值过滤是**有意的不对称**（设计漏掉代价高→优化召回，代码优化精度）

## 1.3.0 — 2026-06-28

- 补提交 `/domain-availability-check` skill（早先创建未入库）：跨 .com/.dev/.io 等查域名可用性 + 反查持有者，用于品牌/产品命名排查（trademark-basic-search 的配套）
  - 含 `scripts/check_domains.py`、`scripts/domain_owner.py`
- `.gitignore` 忽略 `*-workspace/`（skill 优化/eval 运行时 scratch）

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
