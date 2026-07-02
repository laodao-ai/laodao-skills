# Spec 工作流自动化 (Spec-Workflow Automation)

本项目的领域即 **spec 工作流本身**：一个 OpenSpec 变更从生成 → 设计审 → 实现 → 代码审 → 收尾 merge 的连续自动流水线，以及支撑它的评审机制、债务池、跨模型第二意见。此文件是该工作流的**统一术语表**（glossary），只定义语言，不放实现细节。

## Language

**假✅ (False Green)**:
verify / 评审报告把一条**根本没落实**的需求标成 ✅ 通过。是本工作流的头号失效模式——阶段三去人类门后，假✅ 会让不完整的活静默 merge，还被 hand-off 当"已完成"固化。
_Avoid_: 误判、错标（要专指"该红标绿"这一方向，不含"该绿标红"）

**假红 (False Red)**:
与假✅ 相反——确实做了、但因缺可机验痕迹被判成 gap。可当场补锚点纠正，后果远轻于假✅。

**证据锚点 (Evidence Anchor)**:
挂在一条 ✅ 判定上的**可机验凭据**：测试名 / commit hash / 文件行号。无锚点的 ✅ 一律降级为 gap。是堵假✅ 的机制核心。
_Avoid_: 证据、备注（要强调"可被机器/独立复核校验"）

**人类门 (HARD-GATE)**:
需要人类判断才能放行的阻塞点。本工作流刻意只保留在**阶段二设计门**（批设计）一处；阶段三过设计门后无任何阻塞人类门。
_Avoid_: 审批、确认（人类门特指"阻塞、非人不放行"，区别于异步非阻塞的 hand-off）

**verify 终门 (Verify Gate)**:
阶段三去人类门后，opsx-done 内的 verify 步成为**唯一**判定变更完整性的门。它不靠人盯，靠证据锚点硬约束 + 强模型冷启来自证可信。

**延后 / defer (Defer)**:
把"修不了 / 需拍板拿不准"的残差记进 buglist/todolist，本 change 不处理，交由 hand-off 引导另开清理 change。区别于"当场自动修"。

**镜 (Review Lens)**:
并行评审里一个**聚焦单一角度的独立 reviewer 子代理**。fan-out 时每个镜 fresh context、只审一个面向：领域镜（过某领域清单 R/CR 项）/ 对抗镜（从一个角度证明会爆）/ 接地镜（读真实代码核验 spec 主张，spec 侧专有）/ 历史镜（git blame + 旧 PR 意见，code 侧专有）。autoplan 的"四镜"（CEO/design/eng/DX）同源。英文原词 `review lens`（镜 = 镜头 = lens），价值在多镜盲区互补（瑞士奶酪的洞错开），比单 session 顺序审更独立。
_Avoid_: 镜子 / mirror（是"镜头 / lens"，聚焦单一角度，非映照）；reviewer（太泛——镜特指"一个角度"，非泛指审查者）

**Outside Voice（外部第二意见）**:
换**模型家族**（Claude ↔ GPT via codex）做的独立"找漏"评审——不是重跑清单，而是不受清单约束的整体第二意见。价值在跨家族盲区结构性错开。区别于同模型 fresh-context 子代理（只换上下文、盲区同处）。

**复用产出物 vs 依赖内部 (Reuse Output vs Depend on Internals)**:
自制 skill 与 gstack/superpowers 的合规边界线。**读它们产出的文件（output artifact，如 `gstack-review.md`）= 复用产出物，合法**；**调用它们的内部 bin / 探针 / config = 依赖内部，非法**（须自包含重写）。见 `adr/0002`。
_Avoid_: 笼统说"不依赖 gstack"（会误伤合法的产出物复用）

**自包含重写 (Self-contained Rewrite)**:
把某能力（如 codex outside-voice 的探针 / exec 包装 / prompt 模板）重写进自己仓的共享 helper，**只依赖外部 CLI 本身**（codex），不继承上游插件修复。是"依赖内部非法"的落地手段。

**反静默守卫 (Anti-silent Guard)**:
复用产出物时，若读不到 / 解析不出 / 结果为 0 → **显式降级 + 回落自带机制**，绝不静默当"本次无此层"跑过。防"捞到 0 条 ≠ 本次真没有"这类假绿同构。

**反静默压制 (Anti-silent Suppression)**:
热主 session 做对抗裁决时，对 reviewer 子代理的 finding **只能降级 / 批注、不得静默丢弃**；判"不成立"的也须连理由落入报告"已裁掉"区，供人类/审计复核。防热合成层在 finding 到达人眼前暗箱吞掉。

> **元原则（贯穿 假✅ / 反静默守卫 / 反静默压制）**：**任何一层评审覆盖不得无声蒸发。** 一层结论要么到达人眼、要么留下可审计痕迹；"没找到 / 被裁掉 / 没落实"都必须显形，绝不静默通过。见 `adr/0001`、`adr/0002`。

**批次 (Batch)**:
一组归到同一个"清理 change"里一起清的债务 item 的容器；本质是"一个还没出生的 change"。有独立生命周期 `PLANNED → IN_PROGRESS → DONE`，登记在 `batches.md`。是独立于"源"与"status"的第三维度。
_Avoid_: 把批次塞进 item 的 status 列（三维度须分家）

**三维度分家 (源 / 批次 / status)**:
一条债务 item 的三个正交字段：**源 change**（哪个 change 发现的，provenance，不可变）/ **批次**（归入哪个清理 change，triage 结果，可变）/ **status**（`OPEN→PROPOSED→DONE` 生命周期，回归干净、不塞批次）。混用是旧 smell 的根因。

**分诊 / sweep (Triage / Sweep)**:
把 OPEN 债务 item 归入某批次并转 PROPOSED 的动作。挂在 opsx-done 生成 hand-off 那步，每 change 完成后**只诊本 change 新增**的 OPEN 项（老项各自 change 时已诊过）。

**reindex（重建索引）**:
从 dated 文件 + batches.md 重建 `issues/INDEX.md` 的命令。INDEX 只生成禁手改，杜绝第三漂移源；reindex 顺带**拿 item 池当 ground truth 同步批次状态**（成员全 DONE→批次 DONE、不一致标出）。

## Flagged ambiguities

- 「门」曾笼统指一切停顿——已分 **人类门（阻塞、需人判断）** vs **verify 终门（自动、机验）** vs **hand-off（异步、非阻塞的人类再入口）** 三种，勿混（见 `adr/0001-phase3-no-gate-verify-anchors.md`）。
- 「✅」在评审/verify 语境下曾被无条件信任——现约束为**必附证据锚点**方成立，否则是假✅。
- 「镜」单字曾可能被误读成「镜子/mirror」——已钉死为「镜头/**review lens**」（聚焦单一角度的独立 reviewer 子代理），非映照。
