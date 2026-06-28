---
name: impl-review
description: >
  独立按本项目 openspec/workflow/code-checklists/ 规则集审查一个 OpenSpec 变更的代码实现——
  并行多镜版（spec-review 的代码侧镜像）：主 session（强模型）协调，fan-out 多个独立子 agent 并行审
  （每命中领域一个 + 2-3 个对抗镜 + 1 个历史镜），每条 finding 经置信度打分过滤（<80 滤除），
  主 session 再对抗裁决 + AskUserQuestion 拍板 + 出报告。代码即 ground truth，故不设接地镜，
  改设①领域镜（逐条过 code-review-base + domains/<栈>）②对抗镜（证明运行期会爆：竞态/泄漏/错误路径）
  ③历史镜（git blame + 历史 PR 评论，借官方 code-review 插件）+ 置信过滤（杀 nitpick/假阳）。
  做 gstack/review 不碰的事（清单逐条 + 对抗 + 置信过滤），故与之互补、不重复
  （gstack/review 专做 scope-drift + 计划完成度审计）。出 impl-review-report.md，标注
  [impl-review-fix]。代码评审阶段使用（subagent-dev 完成 + /clear 之后）。Trigger with /impl-review。
---

# impl-review — 并行多镜的独立代码实现评审

把 `openspec/workflow/code-checklists/`（通用 base CR-01~09 + 领域 delta CR-*）操作化为一次
**并行多镜**代码评审：像官方 code-review 插件并行跑多镜 + 置信度打分一样，本 skill 并行跑
「领域镜 + 对抗镜 + 历史镜」并对每条 finding 打分过滤，但跑的是**本项目自己的清单**。
**与 gstack/review、官方 code-review 互补、不重复**：

- **gstack/review** 专做 scope-drift + 计划完成度审计（建的=计划的?）——本 skill 不碰。
- **官方 /code-review** 做高风险 PR 的 gh 回帖——本 skill 不碰。
- **本 skill** 做清单逐条 + 对抗 + 置信过滤的**主审**。

> 本 skill 是 `/spec-review` 的代码侧镜像。**唯一结构差异**：spec-review 有「接地镜」（读真实代码
> 验 spec 主张）；代码评审里**代码本身就是 ground truth**，接地镜失去意义 → 换成**历史镜 + 置信过滤**
> （借官方 code-review 插件，spec-review 没有的两件）。

> **独立性前提**：必须独立于"写这份代码的上下文"。理想在 subagent-dev 完成、`/clear` 之后跑。
> 子 agent 各自 fresh context = 盲区互补（瑞士奶酪），比单 session 顺序审更独立。

---

## 第零步：确认对象 + 读规则

1. 未指定变更则 `openspec list` 让用户确认。记 `{change_dir}` = `openspec/changes/{name}/`。
2. 确认代码已实现且在 feature 分支上（`git branch --show-current`）。算出 diff base：
   `git fetch origin <base> --quiet && DIFF_BASE=$(git merge-base origin/<base> HEAD)`。
3. 读 `openspec/workflow/code-checklists/README.md`（架构/选用规则）、`code-review-base.md`（CR-01~09）、
   `trigger-catalog.md`（触发）。无 `openspec/workflow/code-checklists/` 则降级通用代码审并提示。

## 第一步：规划镜头（主 session）

- 按 `{change_dir}` 实际命中的 TG/栈 → 决定开哪几个**领域镜**（backend·go / embedded·ml307c·esp32 / frontend）。
- 按风险定**对抗镜**数量：普通 2 个，高风险 3 个。
- 固定 1 个**历史镜**（git blame + 历史 PR 评论）。
- 只审命中的；linter/typechecker/编译器能抓的（导入、类型、格式、纯风格）不进任何镜——CI 会跑。

## 第二步：并行 fan-out 子 agent（一条消息内全部派出）

每个子 agent **fresh context、无用户交互、返回结构化 findings**（不调用 AskUserQuestion）：

| 镜 | 数量 | 干什么 | 建议 model |
|----|------|--------|-----------|
| **领域镜** | 每命中领域 1 个 | 读 `DIFF_BASE..HEAD` 的 diff + 相关真实代码，逐条过 `code-review-base.md` CR-01~09 + `domains/<栈>` 的 **CR-* 项**，列出违反/存疑项（带 `file:line` 证据） | Sonnet（判断） |
| **对抗镜** | 2-3 | 各从一个**不同角度**「证明这段代码会在运行期爆炸」：并发竞态 / 资源泄漏 / 错误路径未覆盖（CR-02/04/05 的对抗版）。默认 refuted=true，找到爆点才记 | Sonnet（对抗推理） |
| **历史镜** | 1 | `git blame` 改动行 + 读历史 PR 评论（`gh pr list`/相关 PR）：这块以前修过/revert 过吗？本次改动是否重蹈覆辙或忽略了旧 review 意见 | Haiku（机械） |

> 每个子 agent 的 prompt 必须自带：`{change_dir}` 路径 + diff 范围、它负责的清单/角度、"返回结构化
> findings 列表（每条带：问题/CR 编号/证据 `file:line`/严重度/建议），不要 AskUserQuestion"。

## 第三步：置信过滤 + 综合 + 对抗裁决（主 session · 强模型）

1. 汇总各镜 findings，**去重**（同一问题多镜命中合并）。
2. **置信度过滤**（借官方 code-review rubric，可下放 Haiku 子 agent 逐条打分）：每条 finding 打 0–100，
   **滤掉 <80**。明确滤除：linter/typechecker/编译器能抓的 / 纯 nitpick / 未改动行的既有问题 /
   CLAUDE.md 没明令而仅凭主观的风格项 / 已被代码注释显式抑制的。
3. **对抗裁决**：对每条存活 finding 判"是否真的会在运行期出问题"——对抗镜的反驳若 ≥ 多数成立则采信；
   存疑的降级或标"需人确认"。

## 第四步：拍板（主 session · 仅此处可 AskUserQuestion）

- **≥2 种合理修复方案**，或核验不了的事实 → **AskUserQuestion** 让用户拍板。
- 子 agent 不能做这步（无交互、无 why），必须回到主 session。

## 第五步：产出

- 写 `{change_dir}/impl-review-report.md`（各镜 findings ≥80 + 置信过滤说明 + 裁决 + 拍板结论）。
- 据此修复代码，改动处标 `[impl-review-fix]`。
- 结尾一句：是否建议进 `/opsx-done`（用户批准 → verify/archive/commit/merge）。

---

## 报告格式（impl-review-report.md）

```
## impl-review 报告 — {change}
### 命中范围
  栈: backend·go / embedded·ml307c …   清单: CR-01~09 + CR-GO-* + …
### Findings（置信 ≥80）
  [严重度] CR-04 资源泄漏 | file.go:42 | 错误路径未释放 conn | 置信 90 | 建议…
### 裁决
  对抗镜反驳采信/驳回逐条说明；<80 滤除项一行带过（可审计，不静默丢）
### 结论
  □ 建议进 /opsx-done   □ 需先修 N 项   □ 需用户拍板 M 项
```

## 模型选择（按本步性质，逐步定）

```
  主 session（裁决 / AskUserQuestion / 出报告）   强模型(Opus/Sonnet) ← 这是门禁,弱模型=假绿
  领域镜 / 对抗镜（判断、对抗推理）               Sonnet
  历史镜 / 置信过滤（git blame/打分，机械）       Haiku
```

依据：评审是门禁，综合判断这层弱模型会"看着过其实没深究"；机械读 blame/打分可下放便宜模型。
**不要**把综合判断 / AskUserQuestion 委派给子 agent（子 agent 无交互、无 why）。

## 与 gstack/review、官方 code-review 的分工（别重复）

| | gstack/review | 官方 /code-review | 本 skill（impl-review） |
|---|---|---|---|
| 干什么 | scope-drift + 计划完成度审计 | 高风险 PR 的 gh 回帖 | 清单逐条 + 对抗 + 置信过滤（主审） |
| 驱动 | 自带类别 | 5 通用镜 + 置信打分 | 本项目 code-checklists/domains |
| 决策 | 自动 | 自动 + gh comment | 主 session 对抗裁决 + 全程 AskUserQuestion |
| 何时 | 可选（scope/计划核对） | 命中 R1/R2/R3 才跑 | 非平凡深审（主审） |

典型顺序：`subagent-dev → /clear → 〔可选〕gstack/review → /impl-review → 〔高风险〕官方 /code-review → /opsx-done`。

## 注意

- **置信过滤要可审计**：滤掉的 <80 项一行带过，不静默丢（静默 = "全过了"的假象）。
- **不重扫 CI 能抓的**：linter/typechecker/编译器范围内的不进镜。
- **代码即 ground truth**：直接读 diff 与真实代码，不设接地镜（这是与 spec-review 的唯一结构差异）。
- 项目无关：所有路径相对当前项目的 `openspec/workflow/`。
