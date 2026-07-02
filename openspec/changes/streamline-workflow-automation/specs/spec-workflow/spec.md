# spec-workflow Specification (delta)

> 本 delta 把 `openspec/workflow/` 端到端流程的**规范性行为**固化为可验证 Requirement。
> 详细设计与决策追溯见 change 的 design.md（G/P/I/C 系列）。

## ADDED Requirements

### Requirement: 评审独立性由 fresh 子代理提供，不依赖会话重置

工作流 SHALL 通过 fresh-context 子代理 dispatch 获得评审独立性，MUST NOT 依赖 `/clear` 会话重置来隔离评审上下文，从而使评审阶段可连续自动运行。

#### Scenario: 设计评审无需先 /clear
- **WHEN** spec-review 编排器在生成/grill 上下文之后运行
- **THEN** 它以 fresh 子代理 fan-out 领域镜/对抗镜/接地镜，主 session 无需先 `/clear`

#### Scenario: 代码评审无需先 /clear
- **WHEN** impl-review 编排器在 subagent-dev 实现之后运行
- **THEN** 它以 fresh 子代理 fan-out 各镜，主 session 无需先 `/clear`

### Requirement: 评审决策登记进报告，不中途打断

评审编排器 SHALL 把决策点（自动决策与需人拍板）连同选项、推荐、各分支后果登记进评审报告，MUST NOT 在评审中途以 `AskUserQuestion` 打断，使一遍评审能自主跑到完成。

#### Scenario: spec-review 遇到 ≥2 合理方案
- **WHEN** 某评审镜发现一个有 ≥2 合理方案或核验不了的事实的决策点
- **THEN** 编排器把它写入 spec-review-report.md 决策登记区并继续，不中途弹 AskUserQuestion

### Requirement: 阶段二产出单一合并报告

阶段二 SHALL 由 `spec-review` 编排器串起 autoplan 与 spec-review 并产出**单一** `spec-review-report.md`，MUST NOT 要求人工手动合并多份报告。

#### Scenario: 阶段二收尾
- **WHEN** autoplan 与 spec-review 镜均完成
- **THEN** 编排器输出一份已去重合并、含决策登记区的 spec-review-report.md，供设计 HARD-GATE 人工一次性评审

### Requirement: impl-review 为每次全跑的独立强制主审

阶段三的 `impl-review` MUST 每次全跑、以独立冷视角作为强制代码评审主审（依据实测能抓真问题），SHALL NOT 因 subagent-dev 内部已评审而降级为高风险才跑的残差抽查。

#### Scenario: 普通变更也跑 impl-review
- **WHEN** 一个非高风险变更完成实现
- **THEN** impl-review 编排器仍全跑（领域镜+对抗镜+历史镜+置信过滤+scope-drift），产出 code-review-report.md

### Requirement: 阶段三过设计门后连续自动跑到 merge

阶段三 SHALL 在阶段二设计门之后无任何阻塞人类门地连续运行 `writing-plans → subagent-dev → impl-review → opsx-done`；能修的自动修，修不了或需拍板的 MUST 进 buglist/todolist 延后并由 hand-off 引导另开 change 清理。

#### Scenario: 修不了的问题延后而非阻塞
- **WHEN** impl-review 发现一个本 change 修不掉的问题
- **THEN** 它进 buglist/todolist(defer) 并写入 hand-off，流程继续跑到 opsx-done，不设人类门阻塞

### Requirement: verify 为收尾最终门，位于所有修复之后

`opsx-done` 的 verify MUST 在本 change 全部修复之后运行作为最终完整性门，SHALL NOT 前移进 impl-review（否则修复后 verify 结果 stale）。

#### Scenario: 修复后才 verify
- **WHEN** impl-review 及其修复循环全部完成
- **THEN** opsx-done 先跑 verify（产 verify-report.md）再 archive

### Requirement: hand-off 交接产物替代人工核对清单

`opsx-done` SHALL 在 verify 之后、archive 之前产出 `hand-off.md`（done/not-done + 延后项 + 下阶段建议）随归档留档，作为人类异步再入口与下个 cleanup change 的输入种子；MUST NOT 保留旧的人工核对清单 `code-review-verify.md`。

#### Scenario: 收尾产出 hand-off
- **WHEN** verify 通过
- **THEN** opsx-done 生成 hand-off.md 并纳入归档

### Requirement: 每步提交由显式收尾动作驱动，不用 hook

工作流的 checkpoint 提交 MUST 由显式收尾动作（step prompt 追加指令 / 编排 skill 内置步）经共享脚本驱动，SHALL NOT 用 hook 驱动提交本身（hook 看不见逻辑步骤边界）；grill 多轮中途 MUST NOT 提交，仅收敛后一次。

#### Scenario: grill 收敛后才提交
- **WHEN** grill 多轮对话进行中
- **THEN** 不产生 checkpoint 提交；仅在 grill 收敛后一次性提交 design/ADR 更新

### Requirement: 债务池统一 issues 结构且 INDEX 只生成

buglist/todolist SHALL 统一到 `issues/{buglist,todolist}/` 结构，并由 `reindex` 生成 `issues/INDEX.md`（全池 open 项 × 批次状态的物化板）；`INDEX.md` MUST NOT 手工维护（避免第三漂移源）。

#### Scenario: INDEX 由脚本重建
- **WHEN** 债务池条目或批次状态变化
- **THEN** `reindex` 从 dated 文件 + batches.md 重建 INDEX.md，与两者保持一致

### Requirement: 批次注册表与逾期主动催办

工作流 SHALL 以 `issues/batches.md` 给清理批次第一类身份（PLANNED→IN_PROGRESS→DONE，成员生成、条目薄），并在 INDEX 生成时 MUST 主动标记逾期 PLANNED 批次，堵住"分诊到清理"时间差的遗忘。

#### Scenario: 每 change 完成分诊入批
- **WHEN** 一个 change 经 opsx-done 收尾
- **THEN** sweep 把本 change 新增的 OPEN 项分诊入批次并登记 batches.md(PLANNED)，INDEX 后续重建会催逾期批次

### Requirement: 跨模型 outside voice 默认开且可 fallback

spec-review 与 impl-review SHALL 默认运行跨模型 outside voice（复用 autoplan 的或自带），机制自包含、MUST NOT 引用 gstack，且 MUST NOT 改动 gstack 自身（autoplan / gstack review）的原生 outside voice——spec-review 的"复用"指读取 autoplan 已产出的 outside-voice findings，不重实现；任一失败（未装/未认证/超时/报错）MUST 非阻塞地回落到 fresh Claude 子代理。

#### Scenario: codex 不可用时回落
- **WHEN** codex CLI 未安装、未认证或运行超时
- **THEN** outside voice 回落到 fresh Claude 子代理（保独立性、丢跨模型），审查不中断

#### Scenario: gstack 边界不越界
- **WHEN** spec-review 复用 autoplan 的 outside voice
- **THEN** 它读取 autoplan 产出的 gstack-review.md 里的 outside-voice findings，MUST NOT 改动或接管 gstack 原生机制

### Requirement: workflow bundle 改在权威源、经部署下发

workflow bundle（workflow.md / trigger-catalog.md / quality-layering.md / review UI / hooks / checkpoint 脚本）与自制 skill 的改动 MUST 在权威源（laodao-skills 的 `opsx-project-init/assets/` 与 skill 目录）进行；消费仓的 `openspec/workflow/` 等 SHALL 经 `opsx-project-init update` 重拉刷新，MUST NOT 只改消费仓副本。

#### Scenario: 修改 workflow 规则
- **WHEN** 需要修改 workflow.md
- **THEN** 改 laodao-skills 权威源 `assets/workflow/workflow.md`，消费仓走 `update` 采纳，不直接编辑消费仓的部署副本

### Requirement: 高风险由 HR-TG 子集判定

工作流 MUST 以命中 HR-TG 子集 `{TG-04, TG-06, TG-07, TG-08, TG-09, TG-16, TG-17, TG-26}` 作为"高风险"的判据，命中即在复用/自带 outside voice 之上单开领域专属 cross-model；SHALL NOT 新造独立风险分级代号。

#### Scenario: 命中 DB schema 变更
- **WHEN** 变更命中 TG-04（DB schema 迁移）
- **THEN** 评审的规划镜头步判为高风险，额外 dispatch 领域专属 cross-model，并在报告留痕
