# Spec 工作流（端到端总览）

> **定位**：从需求到实现的端到端流程总览，串起 `openspec/workflow/` 的全部规则。
> 本文给**流程骨架 + 每步归属哪条规则**；各步细则见对应规则文件，不在此重复。
> 这是 `workflow-serverside.md` M/L 路径的升级版（用 grill 替 brainstorming、autoplan 主审、接入 config、闭环用 opsx-done）。

---

## 一、完整流程

```
 〔问题模糊/方向未定〕opsx:explore       ③发散(条件,清晰则跳)
        │
  opsx:ff                                 生成 proposal/design/specs/tasks
   └─ prompt 第一步：若不在 feature 分支 → git checkout -b feat/{change}
   └─ 按 config.yaml + trigger-catalog 生成(结构①+约束②已固化)
        │
  grill-with-docs                         ③对抗压测：死磕分支 + 对齐术语 + 查代码 + 落 ADR
        │
  /clear  ← 安全点                        ⚠️ 给评审独立上下文(产物在盘上,context 清空)
        │
 〔高风险〕autoplan (CEO/design/eng/DX·双声)  广审(可选,自动决策)
        │
  /spec-review                            按 spec-review.md + 领域清单 深审(主审·我们的标准)
        │
 〔HARD-GATE：用户批准设计〕              未批准不进实现
        │
  writing-plans                           原子任务计划(TDD)
        │
  subagent-driven-development             并行子代理实现(内含 TDD + 两阶段审查)
   └─ 终审 dispatch 附 code-checklists/domains(注入点 B)→ 领域审前移进循环
        │
  /clear  ← 安全点                        ⚠️ 给评审独立上下文(代码在分支,context 清空)
        │
 〔可选〕gstack /review                    scope-drift + 计划完成度审计(建的=计划的?)
        │
 〔高风险〕/impl-review                    冷独立抽查(命中 TG 安全/并发/DB;普通变更信任注入点 B 循环内增强审)
        │
 〔命中 R1/R2/R3〕/code-review             PR 评审(高风险才跑·gh 回帖)
        │
  /opsx-done                              verify → archive(+delta 对码核验/同步) → commit → merge
```

## 二、逐步 prompt（可直接复制）

> `{change}` = 变更短名（如 `add-pagination`）；`{change dir}` = 变更目录的 `@` 引用（如 `@openspec/changes/add-pagination`）；`{topic}` = 探索主题。
> 注：D 约束 / 触发槽 / 画图 / 领域清单已由 `openspec/config.yaml` 的 rules **自动注入** opsx:ff——故 ff prompt 无需再内联这些（对比旧 M 路径大幅瘦身）。

| 步骤 | command/skill | prompt（可复制） | 产出物 | 规则·条件 |
|----|----|----|----|----|
| 1 | /opsx:explore | `/opsx:explore {topic}` | — | generation-process ③发散；**问题模糊才跑** |
| 2 | /opsx:ff | `/opsx:ff {change}。若不在 feature 分支则先 git checkout -b feat/{change}。` | proposal/design/specs/tasks | ff-generation-constraints(FF-0)+config；**必跑** |
| 3 | /grill-with-docs | `/grill-with-docs 逐分支死磕 {change dir} 的 design.md：拷问到共识、对齐术语、边界场景压测、代码与主张不符即揭穿、落 ADR/术语。ADR 写 docs/gstack/，勿新建 docs/adr/。文档标注 [grill-amendment]。` | design/ADR 更新 | generation-process ③对抗；非平凡变更 |
| 4 | /clear | `/clear` | — | spec-review 原则1（独立性）；**评审前必做** |
| 5 | /autoplan | `/autoplan {change dir}` | 多镜评审结论 | gstack 广审（CEO/design/eng/DX·自动决策，跑自己的流程、prompt 不注入）；**高风险才跑** |
| 6 | /spec-review | `/spec-review 独立审查 {change dir}` | spec-review-report.md | 自制 skill：按 spec-review.md ①②③ + 命中领域 spec-checklists/domains 深审；**非平凡必跑（主审）** |
| 7 | HARD-GATE | （人工：批准设计后才进实现） | — | generation-process 门；**必跑** |
| 8 | /writing-plans | `/writing-plans 按 {change dir} 的 design.md 与评审结论生成原子任务清单 superpowers-plan.md，每任务 TDD，参考 tasks.md 分组；有测试计划则附测试覆盖图。把 design 的领域约束逐字写进 plan 的 Global Constraints（注入点 A）。生成后自动以 subagent-driven-development 执行实现，自动完成全部任务，每任务完成跑测试套件，确认无 warning。` | superpowers-plan.md + 代码 | superpowers + quality-layering 注入点 A；**必跑（计划→实现自动化）** |
| 9 | /subagent-driven-development | `/subagent-driven-development 按 {change dir}/superpowers-plan.md 实现，每任务完成跑测试套件，确认无 warning。final whole-branch 终审 dispatch 时，把 @openspec/workflow/code-checklists/domains/<命中栈> 作为额外 review lens 附给 reviewer（注入点 B，勿改插件文件）。` | 代码 | 由步骤 8 自动触发；quality-layering 注入点 B（领域审前移进生成循环） |
| 10 | /clear | `/clear` | — | spec-review 原则1（独立性）；**代码评审前必做**（实现完才清，子 agent 调度中禁清） |
| 11 | gstack /review | `/review 检查 {change dir} 的代码变更是否有 scope-drift（顺手多改）与计划完成度缺口（建的=计划的?），出文字结论。` | scope/计划核对 | gstack/review 专长（scope-drift + 计划审计）；**可选** |
| 12 | /impl-review | `/impl-review 独立审查 {change dir} 的代码变更，按 @openspec/workflow/code-checklists/code-review-base.md + 命中领域 domains/<栈>（backend·go / embedded·ml307c·esp32）逐条过 CR-* 查错误处理/资源/并发/数据安全 + 对抗（证明运行期会爆）+ 历史镜（git blame/旧 PR 意见）+ 置信过滤（<80 滤除）；出 impl-review-report.md 并修复，改动标 [impl-review-fix]。` | impl-review-report.md | 自制 skill：清单逐条 + 对抗 + 置信过滤；**高风险才跑·冷独立抽查**（命中 TG 安全/并发/DB；普通变更信任注入点 B 的循环内增强审，见 reference/quality-layering.md §五） |
| 13 | /code-review | `/code-review:code-review 审查当前 PR，出 code-review-report.md 到 {change dir}。` | code-review-report.md | 命中 R1/R2/R3 才跑 |
| 14 | /opsx-done | `/opsx-done` | verify-report + 归档 + 提交 + 合并 | opsx-done skill；**必跑（闭环）** |

## 三、关键设计决策

1. **git 分支在 ff prompt 内做（带守卫）= 规则 FF-0**：`若不在 feature 分支则 git checkout -b feat/{change}`。
   省一个手动步，分支恰在生成开始时创建，spec 文件随分支落地。已在分支上则跳过，幂等。
   强制规则见 [ff-generation-constraints.md](./ff-generation-constraints.md) §前置强制动作（FF-0）。
2. **两处 `/clear` 保独立（最关键）**：① grill→autoplan 之间、② subagent-dev→代码评审之间。两次审查（autoplan 审 spec、impl-review 审代码）若在"刚做完"的同上下文里跑 = 自己审自己、不独立；`/clear` 后产物/代码在盘上，读盘重审 = 真独立（瑞士奶酪的洞才错开）。**注意**：子 agent 调度（subagent-dev）运行中禁 `/clear`，必须跑完再清。
3. **HARD-GATE 在 autoplan 之后**：brainstorming 被 grill 取代后，它自带的「未批准不实现」门移到此处。
4. **闭环用 `opsx-done`**：它 = verify → archive → commit → merge，且 archive 子代理拿 delta **对真实代码核验后再同步** spec——顺带吃掉了旧 `opsx:apply` 的「spec 对齐」。故尾部不再需要单独 apply/verify/archive。
5. **评审两层、不重复（设计侧）**：`/spec-review`（自制 skill，按本项目 spec-review.md + 领域清单，**主审**，非平凡必跑）+ `/autoplan`（gstack 广审 CEO/design/eng/DX，**高风险加跑**）。**autoplan 已含 plan-eng-review（eng 镜），故第二层用自制 spec-review 而非再跑 plan-eng-review**——避免重复；spec-review 做 autoplan 不碰的事（我们的标准 + 接地读码 + 全程 AskUserQuestion）。
   **代码侧（生成期已三层审，事后只做残差）**：`subagent-driven-development` 内部已含三层 fresh-context 审（自审 + 逐任务 spec/质量双判审 + 终审），且**注入点 B 把 code-checklists/domains 附给终审** → 领域审前移进循环。故事后 `gstack /review`（scope-drift·可选）+ `/impl-review`（**高风险才跑·冷独立抽查**，非全量主审）+ `/code-review`（官方 PR 回帖·R1/R2/R3 才跑）。详见 [quality-layering.md](./reference/quality-layering.md)。
6. **深度按 TG / 风险**：explore（模糊才跑）、autoplan（高风险才跑）、impl-review（高风险才跑）、code-review（命中 R1/R2/R3 才跑）；不分 S/M/L 档。
7. **质量 shift-left（代码层）**：标准前移进生成期两个注入口——A 领域约束进 plan Global Constraints（逐任务 prevention+inline 审）、B 领域清单附终审 rubric（循环内领域审）；于是事后 impl-review 从"全量领域审"缩成"高风险冷独立抽查"。注入**只在本仓的 step prompt + checklist**，不改 superpowers 插件（升级安全）。与设计侧 config 固化结构/约束让 spec-review 只做残差**同构**。见 [quality-layering.md](./reference/quality-layering.md)。

## 四、生成 ↔ 评审 的对称

```
  生成侧(Prevention)            评审侧(Detection)
  ──────────────────────────────────────────────
  ①结构 → config 槽       ┐
  ②约束 → config rules/D  ├─ ff 产出       autoplan 独立审(spec-review.md)
  ③过程 → grill(对抗磨硬) ┘                impl-review 审代码(清单驱动)
                                          /opsx-done 闭环
  两侧共用 trigger-catalog(TG) 决定深度
```

## 五、与规则集的关系

- 本文是**流程编排**；不重复各规则文件的内容，只引用。
- `config.yaml` 在生成时自动守①②；本文负责把 explore/grill/autoplan/spec-review/impl-review/opsx-done **排成序**。
- [reference/quality-layering.md](./reference/quality-layering.md) 管**质量分层 + shift-left 注入点**（生成期三层审、领域清单注入终审、事后 review 为何缩成残差）；本文据其结论把 impl-review 设为高风险才跑（说明类，删之不影响执行——操作指令已内联在上方 step prompt）。
- 旧 `workflow-serverside.md` 的 M/L 路径表中，仍内联已删 checklist 的引用——以本文为新主干，那份待简化为「按 config + trigger-catalog + 本文流程」。

## 六、检查清单（跑一个变更时）

- [ ] 问题清晰否？不清晰先 `opsx:explore`
- [ ] ff 是否在 feature 分支上生成（prompt 内建或手动）？
- [ ] grill 之后、评审之前是否 `/clear`（保独立）？
- [ ] subagent-dev 之后、代码评审之前是否 `/clear`（保独立）？
- [ ] `/impl-review` 是否过了命中领域 code-checklists、做了对抗 + 置信过滤？
- [ ] `/spec-review` 是否读了真实代码、做了对抗式追问、过了命中领域清单？
- [ ] 高风险变更是否加跑了 `/autoplan`（广审四镜）？
- [ ] 设计是否过 HARD-GATE（用户批准）才进 writing-plans？
- [ ] 收尾是否用 `/opsx-done`（而非手动 apply/verify/archive）？

*流程 v1 · 配套 generation-process.md（生成）/ spec-review.md（评审）/ trigger-catalog.md（深度）*
