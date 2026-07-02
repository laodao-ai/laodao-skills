# 设计：issues 债务池与批次管理（Phase B）

> **本 change = `streamline-workflow-automation` 拆分的 Phase B**（见归档 [ROADMAP.md](../archive/2026-07-02-streamline-workflow-automation/ROADMAP.md)）。
> **决策真相源 = 归档 umbrella [design.md](../archive/2026-07-02-streamline-workflow-automation/design.md) §八「阶段三配套：债务池与批次管理」+ 决策速查表 I1–I13**。
> 本文只做「Phase B 落地导航 + 与 umbrella 的 delta」，**不重复推导**已 grill 到共识（✅ 定）的决策；I* 决策若需追溯，读 umbrella §8 / 决策速查表。

## 一、依赖与前置

- **依赖 Phase A**：sweep 挂靠点 = opsx-done 生成 hand-off 那步（I5）。Phase A 已 merge，`opsx-done` SKILL 留有〔Phase B 补〕占位，Phase B 落地时填。
- **本仓当前无 issues 数据**（`openspec/buglists`/`todolists` 均不存在）→ laodao-skills 自身无一次性迁移负担；迁移影响主要在下游消费仓（§Non-Goals：routine，不在本 change）。

## 二、命中触发（TG，起手判定）

| TG | 命中点 | 落地要求（真相源） |
|---|---|---|
| **TG-05** 数据对象 + 生命周期 | issues item 三维度 schema（源/批次/status）+ batch 实体 | 数据模型见 umbrella §8.2 结构 / §8.3 三维度分家 |
| **TG-09** 多状态生命周期 | item `OPEN→PROPOSED→DONE` · batch `PLANNED→IN_PROGRESS→DONE` | 状态机见 umbrella §8.3（item）/ §8.5（batch，含 reindex 同步）——**已画 ASCII，本 change 不重画** |
| **TG-19** 多需求 | I1–I13 | 见 tasks.md 分节 |
| **TG-20** 外部影响方 | laodao-skills 共享 toolkit → 其它项目迁移 | 见 proposal Stakeholders（OQ3） |

- **TG-23（≥2 合理方案）**：I* 系列的方案取舍已在 umbrella design + `adr/` 记录，**Phase B 不新增 ADR**（决策全 ✅ 定，无新分叉）。

## 三、决策（引用 umbrella §8 / 速查表 I1–I13，不复制）

落地遵循已定：结构 **I1**（`issues/{buglist,todolist}/` + `INDEX.md` + `batches.md`）· INDEX 只生成禁手改 **I2** · 三维度分家 **I3** · 批次 key = 清理 change 名 **I4** · sweep 时机 = opsx-done hand-off 步 **I5** · sweep 范围 = 只本 change 新增 **I6** · cadence bug按日/todo按月 **I7** · per-file 表保留 **I8** · 生效 = toolkit 新标准 **I9** · 连带 review UI/脚本 **I10** · batches.md 第一类身份 **I11** · 标准归属 = recorder 约定段 **I13**。

## 四、Phase B 唯一须显式守住的 delta（别回退）

**I12 债务闭环 = 被动 + reindex 同步状态〔grill-amendment / Q5〕**——这是本 change 最易被"优化回旧稿"的一条：

- ❌ **不做「逾期主动催办」**：早前旧稿曾想让 INDEX 主动标记逾期 PLANNED 批次（原 spec 需求标题一度含"逾期主动催办"，是 **Q5 前旧版**）；grill Q5 判「逾期」判据难定、且属投机机器，**删除**。
- ✅ **改被动**：`INDEX.md` 只把 open 项 × 批次**摊清、标 DONE**，剩下的 open 项在**下次清 bug/todo 时自然纳入**；不设逾期计算、不主动喊。
- ✅ **reindex 同步批次状态**（焊死 `batches.md` 状态漂移）：reindex 填成员时**拿 item 池当 ground truth** 校验/同步批次 `状态`——成员全 DONE/FIXED → 批次判/标 DONE；仍有成员 OPEN/PROPOSED 却手标 DONE → reindex **标不一致纠正**（不静默信手写状态）。`PLANNED→IN_PROGRESS` 仍由人起 cleanup change 时设。

> 落地口径见 umbrella §8.5（grill-amendment）+ 决策速查表 I2/I12。spec delta 的第 2 条 Requirement 即固化此被动版。

## 五、ROADMAP 约束落地（拆开必守）

- **约束1（workflow.md 增量改一次）**：本 change 给 `workflow.md` **只追加 sweep 步引用**，不碰 Phase A 写的连续化骨架、不预写 Phase C 的 outside-voice 步。
- **约束2（验证按相分摊）**：本 change 只验本相产物自洽 = §8.2「reindex 生成 INDEX + dated 文件 + batches.md 三处一致」（表↔块↔INDEX 自检）；不验 A/C 的产物。
- **约束3（下游采纳不在相内）**：消费仓迁移 issues 数据是下游 routine（proposal Non-Goals）。

## 六、不做（Phase B Non-Goals，见 proposal）

不含连续化（A 已交付）/ 跨模型 outside voice（C）；不清空既有债务（迁移结构即可）；不逾期催办（I12）；不含消费仓采纳（下游）；不另起 rules 文件（I13）。
