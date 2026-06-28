---
name: spec-review
description: >
  独立按本项目 openspec/workflow/spec-review.md 方法论审查一个 OpenSpec 变更的设计（spec/design）——
  并行多镜版（"我们标准版的 autoplan"）：主 session（强模型）协调，fan-out 多个独立子 agent 并行审
  （每命中领域一个 + 2-3 个对抗镜 + 1 个接地读码），主 session 再对抗裁决 + AskUserQuestion 拍板 + 出报告。
  只审 prevention（config 固化的结构/约束）焊不住的残差：①Validation ②对抗（证明实现期会爆炸）
  ③接地（读真实代码核验函数名/字段/API 路径）。做 gstack autoplan 不碰的事（本项目 spec-review.md +
  spec-checklists/domains），故 autoplan 之后跑不重复 eng 镜。出 spec-review-report.md，标注
  [spec-review-amendment]。设计审查阶段使用（/clear 之后）。Trigger with /spec-review。
---

# spec-review — 并行多镜的独立设计评审

把 `openspec/workflow/spec-review.md`（Detection 方法论）+ `spec-checklists/domains/`（领域 R 项）
操作化为一次**并行多镜**评审：像 autoplan 并行跑四镜一样，本 skill 并行跑「领域镜 + 对抗镜 + 接地镜」，
但跑的是**本项目自己的标准**。**与 autoplan 互补、不重复**（autoplan 已含 eng 镜）。

> **独立性前提**：必须独立于"写这份 spec 的上下文"。理想在 `/clear` 之后跑。子 agent 各自 fresh context
> = 盲区互补（瑞士奶酪），比单 session 顺序审更独立。

---

## 第零步：确认对象 + 读规则

1. 未指定变更则 `openspec list` 让用户确认。记 `{change_dir}` = `openspec/changes/{name}/`。
2. 读 `openspec/workflow/spec-review.md`（方法论）、`trigger-catalog.md`（触发）。无 `openspec/workflow/` 则降级通用评审并提示。

## 第一步：规划镜头（主 session）

- 按 `{change_dir}` 实际涉及的栈 + 内容判命中的 TG/领域 → 决定开哪几个**领域镜**（backend·go / embedded·ml307c·esp32 / frontend）。
- 按风险定**对抗镜**数量：普通 2 个，高风险 3 个。
- 固定 1 个**接地镜**（机械读码核验）。
- 只审命中的；config 已固化的结构/占位/一致性（T/S）不进任何镜。

## 第二步：并行 fan-out 子 agent（一条消息内全部派出）

每个子 agent **fresh context、无用户交互、返回结构化 findings**（不调用 AskUserQuestion）：

| 镜 | 数量 | 干什么 | 建议 model |
|----|------|--------|-----------|
| **领域镜** | 每命中领域 1 个 | 读 `{change_dir}` design/specs + 相关真实代码，逐条过 `spec-checklists/domains/<栈>` 的 **R 项**，列出违反/存疑项（带文件:行证据） | Sonnet（判断） |
| **对抗镜** | 2-3 | 各从一个**不同角度**「证明这份 spec 会在实现期爆炸」：隐藏假设 / 失败模式 / 乐观估计与边界。默认 refuted=true，找不到爆点才放过 | Sonnet（对抗推理） |
| **接地镜** | 1 | grep/读真实代码，核验 spec 里**所有代码事实**（函数名/字段/API 路径/schema）是否真实存在且一致，列出不符项 | Haiku（机械） |

> 每个子 agent 的 prompt 必须自带：`{change_dir}` 路径、它负责的清单/角度、"返回结构化 findings 列表（每条带：问题/证据 file:line/**置信度(高/中/低)**/严重度/建议），不要 AskUserQuestion"。

## 第三步：综合 + 对抗裁决（主 session · 强模型）

- 汇总各镜 findings，**去重**（同一问题多镜命中合并）。
- **对抗裁决**：对每条 finding 判"是否真的会在实现期出问题"——对抗镜的反驳若 ≥ 多数成立则采信；存疑的降级或标"需人确认"。
- **标注、不丢弃（escalate-not-drop）**：按置信度分流——高=直接采信、中=标"需人确认"进第四步、低=**仍上抛（一行带过），绝不静默滤除**。**不照搬 impl-review 的数值 <80 一刀切**：设计漏掉的代价高（会传导进实现），spec 评审优化召回而非精度；对抗裁决（强模型带上下文）已是比数值打分更强的过滤。
- 按 `design-diagrams.md`：命中触发的图**只验证存在/正确/未过时**，缺失/过时标记，不重画。

## 第四步：拍板（主 session · 仅此处可 AskUserQuestion）

- 不确定的技术事实（核验不了的函数名/字段/API 路径）或 **≥2 种合理修复/方案** → **AskUserQuestion** 让用户拍板。
- 子 agent 不能做这步（无交互、无 why），必须回到主 session。

## 第五步：产出

- 写 `{change_dir}/spec-review-report.md`（各镜 findings〔带置信/严重度〕 + 裁决 + 拍板结论；低置信项一行带过、可审计，不静默丢）。
- 据此更新 design/specs，改动处标 `[spec-review-amendment]`。
- 结尾一句：是否建议进 HARD-GATE（用户批准 → writing-plans）。

---

## 模型选择（按本步性质，逐步定）

```
  主 session（协调/对抗裁决/AskUserQuestion/出报告）  强模型(Opus/Sonnet) ← 这是门禁,弱模型=假绿
  领域镜 / 对抗镜（判断、对抗推理）                    Sonnet
  接地镜（grep/读码核验，机械）                        Haiku
```

依据：评审是门禁，综合判断这层弱模型会"看着过其实没深究"；机械读码可下放便宜模型。
**不要**把综合判断 / AskUserQuestion 委派给子 agent（子 agent 无交互、无 why）。

## 与 autoplan 的分工（别重复）

| | autoplan | 本 skill（spec-review） |
|---|---|---|
| 镜 | CEO/design/eng/DX + 双声 | 领域镜 + 对抗镜 + 接地镜（我们的标准） |
| 清单 | 四个 gstack skill 各自的 | 本项目 spec-checklists/domains |
| 决策 | 自动决策，末尾 gate | 主 session 对抗裁决 + 全程 AskUserQuestion |
| 何时 | 高风险广审（可选） | 非平凡深审（主审） |

典型顺序：`/clear → 〔高风险〕autoplan → /spec-review → HARD-GATE`。

## 注意

- **只做 prevention 焊不住的残差**（T/S 项交给 config/lint，不重扫）。
- **必须读真实代码**，不得只验 spec 自洽（接地镜专司此事）。
- 项目无关：所有路径相对当前项目的 `openspec/workflow/`。
