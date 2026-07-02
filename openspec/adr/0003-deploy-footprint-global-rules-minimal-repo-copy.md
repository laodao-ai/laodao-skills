# 部署 footprint：规则走全局、消费仓只留最小副本

opsx-project-init 曾把整个 workflow bundle（≈34 文件）复制进每个消费仓的 `openspec/workflow/`。规则文件从不按仓定制（定制只在 `config.yaml`），却在每个消费仓留一份可观的副本。改按"内容性质"分层部署，把纯机械/纯规则的部分收归全局，消费仓只留**本身需要在仓里**的最小集。

- **规则（`workflow/*.md` + `spec-checklists/` + `code-checklists/`，≈28 文件）→ 全局唯一**：skills（spec-review / impl-review / opsx-done / recorder / opsx-ship）从全局 toolkit 解析，消费仓**不再复制**。
- **review UI 机械（`tools/` + `serve.sh` + `review.html`，≈5 文件）→ 仍复制进 `openspec/`（尽量少）**：review 服务器根 = `openspec/` + 根相对 `/workflow/tools/`，不落地即 404（见 adr/其它 与决策表 B1 的服务器根锚模型）。故 tools/ 是唯一不得不留的机械副本。
- **`hack/checkpoint-commit.sh` → 全局**：纯 git 包装、无按仓定制、无 pin 价值，与 `ff0-branch-guard.py` / `change-review-stub.py` 两个全局 hook 同款，装一次跨仓生效。顺带根治 `core.fileMode=false` 致 exec 位丢失的坑（全局装时一次设好）。
- **`config.yaml` / `changes/` / `specs/` → 仓内**：本项目配置 + spec 内容本体，天然属仓。

**明确接受的代价**：消费仓**失去按仓 pin 工作流规则**——所有仓跟随全局 toolkit HEAD，规则一改即刻影响所有仓（不再靠 `update` 显式采纳）。用户明确选此方向（footprint 干净 > 按仓 pin）：规则是 dev 工作流、非构建产物，latest-is-fine 可接受。

## Considered Options

- **规则全局 + tools 最小副本 + hack 全局（选中）**：消费仓污染从 ≈34 → ≈5 文件；代价 = 失按仓 pin + skills 须能解析全局 bundle 路径。务实——tools 留副本免去重写 serve.sh。
- **复制全量（现状）**：按仓 pin + 自包含可读 + skills 仓相对路径最简；代价 = 每个消费仓持续背 ≈34 文件纯机械副本。
- **纯激进（连 tools 也不落地，自制全局路由 server）**：消费仓零 review 文件；代价 = 重写 serve.sh 弃 `python -m http.server`、review.html 项目名改由 server 注入。评估后取"tools 留最小副本"更务实（省 serve.sh 重写），故未选。

## Consequences

- skills 里所有 `openspec/workflow/...` 读点改为**全局解析 + 缺失显式降级**（不静默当"无此层"，同"反静默守卫"精神）。
- opsx-project-init：`copy_bundle` 去掉规则部分，只保留 tools/serve/review 复制 + `ensure_dirs` + `config`；`copy_hack` 改为全局安装（同 hooks 路径）。
- 消费仓 `update` 不再拉规则（规则全局自动最新），仍 `update` 刷 tools/。
- **失 pin = 已知限制**：若某仓需固定旧规则行为，本模型不支持（须显式 opt-out 或另法），记录在案。
- **未决实现细节（留落地 change 的 design 定）**：全局 bundle 路径解析机制——固定 `~/.skills/laodao-skills/...` 约定（CLAUDE.md 已把此当安装位）vs env var vs resolver；建议默认固定约定 + env var 覆盖。
- **落地 change**：`minimize-repo-footprint`（承 Phase A 的 G6 复制模型修正，不改归档 umbrella，新 change 的 design 引本 ADR）。
