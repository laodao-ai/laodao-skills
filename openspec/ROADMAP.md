# ROADMAP — laodao-skills 工作流演进登记表

> **活文档（living registry）**：登记从 `streamline-workflow-automation`（Phase A，已归档）派生的全部 phased / spawned change，及其状态、依赖、决策出处。
> 原始 3 相拆分（A/B/C）的详细「待迁任务与 Requirement」见归档 [changes/archive/2026-07-02-streamline-workflow-automation/ROADMAP.md](./changes/archive/2026-07-02-streamline-workflow-automation/ROADMAP.md)。
> 本文是其**前向续表**：承接 A/B/C + 登记后续 grill 中新派生的架构 change。

## 全部 change 登记

| change | 状态 | 覆盖 | 依赖 | 决策出处 |
|---|---|---|---|---|
| `streamline-workflow-automation`（Phase A） | ✅ 已归档 / merged | 三阶段连续化骨架 + 提交自动化 + bundle 骨架 + review UI 半归位(B1) | — | 归档 design G/P + `adr/0001`,`adr/0002` |
| `issues-pool-batch-mgmt`（Phase B） | 🔵 进行中（propose + grill） | 债务池 issues 结构 + 批次管理（I1–I13） | A | 归档 design §8 + 本 change design + grill B-Q1 |
| `cross-model-outside-voice`（Phase C） | ⚪ 待开 | 跨模型 outside voice（C1–C7）+ TG-26 | A | 归档 design §9 + 归档 ROADMAP「Phase C 待迁」 |
| `minimize-repo-footprint` | ⚪ 待开（本轮 grill 新派生） | 规则全局解析 + 消费仓最小副本 + hack 全局 | A（修 G6 复制模型） | **`adr/0003`** |
| `opsx-ship-orchestrator` | ⚪ 待开（本轮 grill 新派生） | 阶段三窄编排 orchestrator（`opsx-ship`） | A（阶段三链就位） | **`adr/0004`** |

> **待开的都暂不建目录**（避免 openspec 挂 stale pending change，同设计"反无声堆积"洁癖）；各自开工时再 materialize proposal/design/tasks/spec。B/C 互不依赖、与两个新 change 也互不依赖，均只依赖 A，先后随意。

---

## 本轮 grill 新派生的两个 change（详情）

### `minimize-repo-footprint`（见 `adr/0003`）

把 opsx-project-init 的部署从"整 bundle 复制进消费仓"改为**按内容性质分层**，减少消费仓污染：

- **规则**（`workflow/*.md` + `spec-checklists/` + `code-checklists/`，≈28 文件）→ **全局唯一**，skills 全局解析、消费仓不复制。
- **review UI 机械**（`tools/` + `serve.sh` + `review.html`，≈5 文件）→ **留 `openspec/` 最小**（服务器根=openspec/ 约束，不落地即 404）。
- **`hack/checkpoint-commit.sh`** → **全局**（同 ff0-branch-guard / change-review-stub 两个全局 hook；顺带根治 `core.fileMode=false` 的 exec 位坑）。
- **`config.yaml` / `changes/` / `specs/`** → 仓内（本体）。
- **明确接受的代价**：消费仓失去按仓 pin 工作流规则（跟随全局 HEAD）。
- **未决（留其 design 定）**：全局 bundle 路径解析机制——固定 `~/.skills/laodao-skills/…` 约定 vs env var；建议默认约定 + env var 覆盖。

### `opsx-ship-orchestrator`（见 `adr/0004`）

补**编排层连续**（设计层连续 Phase A 已达成）：新 skill `opsx-ship`（暂名，备选 opsx-deliver / opsx-run），**窄 scope = 阶段三 5.5→9 一次驱动到 merge**。

- **边界**：不跨 grill（step 3）/ 设计门（step 5）两个人类点；orchestrator 只从**过设计门后**起跑。
- **尊重子步门禁**：`opsx-done` verify FAIL / `impl-review` 真 blocker → 停并上抛；仅"能修自动修 / 拿不准 defer"才继续（防假✅）。
- **meta-orchestrator**：chain `embedded-test-sop`(条件)→`writing-plans`(→subagent-dev)→`impl-review`→`opsx-done`，**不取代**它们；`workflow.md` 阶段三 step 表即其内部序列。

---

## 相关决策记录（ADR）与术语

- `adr/0003-deploy-footprint-global-rules-minimal-repo-copy.md` — 部署 footprint 分层
- `adr/0004-opsx-ship-stage3-orchestrator.md` — opsx-ship 阶段三窄编排
- `CONTEXT.md` 新术语：**设计层连续 vs 编排层连续**（区分"无强制中断"与"无手动逐步触发"）；**终态集**（批次完成判据，B-Q1）
