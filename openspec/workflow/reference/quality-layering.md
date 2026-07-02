# 质量分层：Prevention / Inline Detection / Residual（shift-left）

> **定位**：回答"代码生成质量很高，后面还要那么多次 review 吗？"——不是砍 review，而是
> **把标准前移进生成期已有的审查口，让事后 review 缩成残差**。与 [`spec-review.md`](../spec-review.md)
> §一（review 只做 prevention 焊不住的残差）同一条铁律，在**代码层**的展开。

---

## 一、生成期已经焊进三层 review（不是裸生成）

`superpowers:subagent-driven-development` 内部**自带**一条多层评审流水线（读其 SKILL + 模板得出）：

```
每任务:  implementer TDD + 自审 + commit
         → task-reviewer(fresh 子agent, "Do Not Trust the Report")出双判决: spec 合规 + 代码质量
         → Critical/Important 进 fix 循环, re-review 到 Approved
全任务后: final whole-branch reviewer(最强模型, fresh context)
```

**关键**：这些 reviewer 都是 **fresh-context 独立子 agent**。所以"独立性"——我们一直强调的卖点——
**生成期内部已经有了**。事后 `/clear + /impl-review` 再加的独立性只是"脱离 controller 的全冷独立"，边际收益。

## 二、但它们查的是**通用 rubric**，不是我们的领域清单

task-reviewer / final-reviewer 的检查项是 `clean separation / error handling / DRY / edge cases /
tests verify real behavior / architecture / security`——**纯通用**。它们**完全不碰**
`code-checklists/domains/` 的领域 CR-*（嵌入式看门狗/flash 寿命/ISR、芯片 AT 超时、并发锁序…）。

| 维度 | 生成期已做? | 事后 review 重复? |
|---|---|---|
| spec 合规（建的=要的） | ✅ task-reviewer Part 1 | gstack/review **部分重复** |
| 通用代码质量（CR-01~09 base） | ✅ 三层都查 | /impl-review base **大幅重复** |
| **领域规则（CR-EMB/ML307C/ESP32/GO）** | ❌ 通用 rubric 盲区 | **真残差** ← 唯一不可替代 |
| scope-drift / 计划完成度 | ⚠️ 部分 | gstack/review 补全 |
| 全冷独立（脱离 controller） | ❌ 终审仍 controller 裁决 | /impl-review 补，但边际 |
| PR 级 DB/API/Auth 改动 | ❌ | 官方 code-review |

**结论**：后置 review 的**通用质量部分是冗余**；真正残差只剩 **领域规则 + scope-drift + PR 风险 + 一点冷独立**。

## 三、机会：两个 shift-left 注入点（把标准前移进生成期）

`writing-plans` / `subagent-driven-development` **自带两个官方注入口**：

```
注入点 A:  plan 的 Global Constraints
           writing-plans 把 spec 的项目级约束逐字拷进每个任务，implementer + task-reviewer 都看得到
           → 既是 prevention（按约束写）又是逐任务 inline detection（每任务审 + fix 循环）
           ★ 我们的 spec 已被 /spec-review 按 spec-checklists/domains 审过 → 好的 spec 自带领域约束
             → 自动流进 Global Constraints。这条已半通：保证 design 的领域约束确实进了 plan 即可。
           ⚠️ 边界：SKILL 明确反对往【逐任务】reviewer 塞【宽泛清单】（"global-constraints 要 verbatim
             绑定项，不是 rubric；宽 rubric 留给终审"）。故注入点 A 只塞【该任务相关的具体领域约束】（逐字）。

注入点 B:  final whole-branch reviewer 的 rubric  ← 最大杠杆
           subagent-driven-development 终审默认用 requesting-code-review 的【通用】模板；
           dispatch 时把 rubric 增强为「通用模板 + 命中栈的 code-checklists/domains/<栈>」
           → 领域审在循环内、终审一次做掉，而非事后再单独跑 /impl-review。
```

## 三点五、如何注入 + 升级安全（绝不改插件）

**铁律：绝不编辑 superpowers 插件文件。** 注入发生在 **dispatch 时**，指令放**我们自己的仓**。

```
✗ 改 ~/.claude/plugins/cache/.../superpowers/<version>/skills/.../code-reviewer.md
   → 插件升级换版本目录(cache 里已有 5.1.0 / 6.0.3 两份)，改动被覆盖丢失
✓ 内容(code-checklists/) + 指令(workflow.md step prompt) 都在本仓 → 升级动不到
```

- **注入点 A（搭便车，零额外动作）**：`writing-plans` 本就把 spec 约束逐字拷进 plan 的
  Global Constraints，`task-reviewer` 自动可见。我们只需保证 design 的领域约束确实写进 plan，不碰插件。
- **注入点 B（在 step prompt 加一句）**：终审 dispatch 由 **controller（跑 skill 的主 session）组装**，
  `code-reviewer.md` 只是模板。在 `workflow.md` step-9 prompt 写「终审 dispatch 附
  `@openspec/workflow/code-checklists/domains/<命中栈>` 作额外 review lens」即可——SKILL 自己也说
  宽 rubric 属终审（逐任务才禁塞宽清单），是顺着设计做。

**升级安全三重保险**：① 内容+指令都在本仓，升级只换插件自己的版本目录；② 与 `config.yaml`
升级安全同构（定制在自己侧，不改上游包）；③ 指令按**行为**措辞（"凡跑终审就附清单"），
不绑死插件内部文件路径——未来插件重构终审，只要还有"终审"步，指令依旧成立。

## 四、与 spec 侧同构（同一个元模式）

```
        Prevention(建对)             Inline Detection(循环内抓)          Residual(冷,事后)
 spec:  config.yaml 结构+D 约束      grill / 生成对话                    spec-review(validation+对抗+接地)
 code:  plan Global Constraints+TDD   逐任务双判审 + 终审(subagent-dev)    impl-review(领域+冷独立+scope)
                                      ↑ 把 code-checklists 注入 B ↑       ↓ 于是这里缩成薄残差 ↓
```

设计侧用 config 固化结构/约束（prevention），让 spec-review 只做残差；
代码侧把领域清单注入 plan 约束 + 终审 rubric（prevention + inline detection），让 impl-review 只做残差。
**同一手法，两层对称。**

## 五、对 workflow 的影响：事后 review 改 trigger 分级

注入点 B 落地后，领域审已在生成循环内 → **事后 `/impl-review` 不再"非平凡必跑"，改为风险分级**：

- **普通变更**：信任生成期增强审（终审已含领域清单）；事后只跑 gstack/review（scope）+ 命中才跑官方（PR 风险）。
- **高风险变更**（命中 TG 安全/并发/DB 等）：加跑 `/impl-review` 做**全冷独立抽查**——
  脱离 controller 的彻底独立，专抓 controller 在循环内可能被说服放过的领域残差。

与"不分 S/M/L、TG 驱动"哲学一致：深度由命中的 TG + 风险决定，不是每次全量。

## 六、检查清单（用 superpowers 跑实现时）

- [ ] design 的领域约束是否确实进了 plan 的 **Global Constraints**（注入点 A）？
- [ ] 终审 dispatch 是否把 rubric 增强为 **通用模板 + 命中栈 code-checklists/domains**（注入点 B）？
- [ ] 普通变更是否**没有**重复跑事后全量 /impl-review（信任循环内增强审）？
- [ ] 高风险变更（命中 TG）是否在 `/clear` 后跑了**冷独立** /impl-review？

*方法论 v1 · 项目无关 · 配套 spec-review.md（设计侧残差）/ code-checklists/（领域清单）/ workflow.md（编排）*
