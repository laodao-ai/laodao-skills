# Tasks: streamline-workflow-automation

> 追溯：本 change 无 `openspec/specs/` 能力 delta（process/tooling 变更），任务改**追溯到 design.md 决策 ID**（G/P/I/C）。
> **〔grill-amendment〕拆分已定案（OQ1）**：拆 3 相串行，各 § 已打 **【Phase A/B/C】** 标。**本 change 只执行 Phase A**（§1 §2 §3.1·3.2·3.4 §4 §7 骨架）；B/C 的 § 待各自 change dir 开工时迁入。相划分/依赖/必守约束见 [ROADMAP.md](./ROADMAP.md)。全部未勾 = 未实现。

## 1. 阶段二：spec-review 编排器（laodao-skills）　【Phase A】

- [ ] 1.1 `spec-review` 改为编排器：Step1 内跑 autoplan（吃其 findings + outside-voice）、Step2 spec-review fan-out、Step3 合并成**一份** report〔P2〕
- [ ] 1.2 删中途 `AskUserQuestion`，改**报告决策登记区**（自动决策/需拍板，带选项+推荐+两方后果）〔G2〕
- [ ] 1.3 评审 fan-out 以 fresh 子代理 dispatch，去掉对 `/clear` 的依赖〔G1〕
- [ ] 1.4 写入防重叠说明：autoplan 已含 eng 镜，spec-review 不重复跑 eng〔design §4.2〕
- [ ] 1.5 内部 2 次 checkpoint 提交（autoplan 子步、spec-review 子步）〔P2c〕
- [ ] 1.6 收敛口：结尾建议是否进设计 HARD-GATE

## 2. 阶段三：impl-review 编排器（laodao-skills）　【Phase A】（outside-voice 接入见 §6.4·Phase C）

- [ ] 2.1 `impl-review` 定为**每次全跑·独立冷视角·强制**主审；skill 描述从"高风险才跑"改写〔P3c〕
- [ ] 2.2 并入 gstack/review（scope-drift + 完成度）作为编排器一环〔P3c〕
- [ ] 2.3 fresh 子代理替代 `/clear`；能修的自动修 `[impl-review-fix]`、修不了/需拍板的 → buglist/todolist(defer) + 汇总 `code-review-report.md`〔G1/P3e〕
- [ ] 2.4 保留注入点B（domain 附 subagent-dev 终审）——写清"它有即时 fix+re-review 闭环、事后审无此"的存在理由，防后人优化掉〔P3b/design §7.2〕
- [ ] 2.5 阶段三**无人类门**：≥2 方案有把握自动选推荐(记理由)、拿不准 defer〔P3e〕

## 3. opsx-done 改造（laodao-skills）　【Phase A：3.1/3.2/3.4｜3.3 属 Phase B】

- [ ] 3.1 verify 保持在 opsx-done（所有修复之后，不前移进 impl-review）〔P3f〕
- [ ] 3.2 新增 **hand-off.md 产出步**：verify 之后、archive 之前；内容=done/not-done + 延后项 + 下阶段建议；随归档留档〔P3g〕
- [ ] 3.3 〔Phase B〕新增 **issues sweep 步**：`scan --status OPEN --源 {本change}` → 逐项分诊入批次 → 新批次写 batches.md(PLANNED) → hand-off 引用〔I5/I6〕
- [ ] 3.4 弃用官方 `/code-review` 作为独立 step（保留插件能力供历史镜/置信过滤内部借用）〔P3d〕

## 4. 提交自动化（laodao-skills：checkpoint 脚本源 + step prompt + hook 源）　【Phase A】

- [ ] 4.1 新增 `hack/checkpoint-commit.sh`：接步骤名参数，`git add -A` + 固定 Conventional message；规避本机三坑（禁 `\`+heredoc / core.fileMode / CRLF）〔G4〕
- [ ] 4.2 workflow.md 各 step prompt 末尾追加"完成后 checkpoint-commit"（skill 之间边界）〔G4/P1〕
- [ ] 4.3 grill 多轮中途**不**提交，仅收敛后一次〔P1〕
- [ ] 4.4 可选：SessionEnd/Stop 警告 hook（检测 `issues/` 或 change 有未提交产物只告警、不提交）〔G4 §5.3〕
- [ ] 4.5 不 squash（确认 opsx-done commit 步兼容"实现期已逐 commit"）〔G5〕

## 5. issues 池与批次管理（laodao-skills toolkit：约定 + 脚本；数据迁移属下游 §9）　【Phase B】

- [ ] 5.1 **定义 issues 结构标准**并写进两 recorder skill 的"约定速查"段（唯一真相源）：`issues/{buglist,todolist}/` 子目录 + 生成的 `INDEX.md` + `batches.md`；bug 按日/todo 按月 cadence；命名；sweep 协议；批次生命周期〔I1/I13〕
- [ ] 5.2 recorder 表加 `批次` 列；源/批次/status 三维度分家；status 回归干净（不再塞批次）〔I3〕
- [ ] 5.3 recorder 脚本：路径默认改 `issues/{buglist,todolist}/`；scan 加 `--源/--批次/--open-ungrouped`；加 `triage` 命令（赋批次+转 PROPOSED）〔I4/I9〕
- [ ] 5.4 新增 `reindex` 命令 → 生成 `issues/INDEX.md`（join item+batches，**禁手改**；摊清 open×批次 + 标 DONE；**同步批次状态**：成员全 DONE→批次 DONE、不一致标出；**不做逾期催办**）〔I2/I12·grill-amendment〕
- [ ] 5.5 新增 `issues/batches.md` 注册表 + `batch` 命令（add/set-status，跨 bug+todo；PLANNED→IN_PROGRESS→DONE；条目薄）〔I11〕
- [ ] 5.6 per-file 状态总览表保留；旧文件无 `批次` 列时脚本兼容留空〔I8〕
- [ ] 5.7 更新 review UI（`tools/engine.js`、`review.html`、`review-stub.html`）读 `issues/` 新路径（可选：改读 INDEX.md）〔I10〕

## 6. 跨模型 outside voice（laodao-skills + trigger-catalog）　【Phase C】

- [ ] 6.1 新增 codex outside-voice **共享 helper**（自包含重写，不引用 gstack）：preflight 探针（command -v + 试跑+超时+catch-all）、codex exec 包装（5min）、"找漏"+文件系统边界 prompt 模板、off-switch（env/config.yaml）〔C1/C6〕
- [ ] 6.2 fallback 到原生 Task 子代理（非 ready/报错/超时；5min 封顶；非阻塞）〔C6〕
- [ ] 6.3 spec-review 接入：**复用** autoplan 的设计 outside voice = **读 autoplan 产出的 `gstack-review.md` 里 outside-voice findings**（gstack 原生产的，不重实现）+ 命中 HR-TG 单开领域 cross-model（走自制机制）〔C2/C7〕
- [ ] 6.4 impl-review 接入：自带 code outside voice（自制机制）+ 命中 HR-TG 单开领域 cross-model〔C3〕
- [ ] 6.5 两 skill 规划镜头步加 **HR-TG 判定**（命中集 ∩ {TG-04/06/07/08/09/16/17/26} ≠ ∅）+ 报告留痕〔C4〕
- [ ] 6.6 tension 适配：spec→报告决策登记、impl→自动裁决/defer；守 user sovereignty〔C5〕
- [ ] 6.7 `trigger-catalog.md`（bundle 源）新增 **TG-26 并发/共享可变状态**（回填四列 + 各消费方引用）〔C4〕
- [ ] 6.8 **gstack 边界守恒**：不动 autoplan/gstack review 的原生 outside voice；自制机制只驱动自制 skill〔C7〕

## 7. workflow bundle 源改写（laodao-skills `opsx-project-init/assets/`，非消费仓副本）　【Phase A 骨架｜见约束】

> 〔grill-amendment〕**7.1 `workflow.md` 被 A/B/C 各增量改一次**（A 骨架 + checkpoint/hand-off 引用；B 追加 sweep 步引用；C 追加 outside-voice 步引用）——A 不能一次写完。**7.5 的 TG-26 部分属 Phase C**；INDEX 同步各相收尾各做本相规则变更。见 [ROADMAP.md](./ROADMAP.md) 约束 1/2。

- [ ] 7.1 改写 `assets/workflow/workflow.md`：三阶段连续化新骨架、step 表更新、去 2 个 `/clear`、去 step14、加 checkpoint/hand-off/sweep/outside-voice〔全 G/P；G6〕
- [ ] 7.2 改写 `assets/workflow/reference/quality-layering.md` §五：impl-review 从"高风险冷抽查"→"每次全跑独立强制主审"〔P3c〕
- [ ] 7.3 **review UI 归位**：源 `assets/review-tool/{tools/,serve.sh}` → `assets/workflow/{tools/,serve.sh}`；改 opsx-project-init 部署逻辑（`openspec/tools/` → `openspec/workflow/tools/`）+ serve.sh/review.html/CLAUDE.md 的 `tools/` 路径引用〔B1〕
- [ ] 7.4 checkpoint 脚本源 + 可选 SessionEnd 警告 hook 源进 `assets/`（随 bundle 部署到消费仓 hack/）〔G4〕
- [ ] 7.5 同步 laodao-skills 自身 `openspec/INDEX.md`（新增 TG-26 + workflow 规则变更）〔Compliance〕

## 8. 验证（不改实现，仅核对本 change 产物自洽）　【按相分摊：8.1→A · 8.2→B · 8.3/8.4→C · 8.5 跨相】

- [ ] 8.1 决策表 G/P/I/C/B 每条在 bundle/skill 改动中有对应落点，无悬空
- [ ] 8.2 `reindex` 生成的 INDEX.md 与 dated 文件 + batches.md 一致（表↔块↔INDEX 三处自检）
- [ ] 8.3 outside voice 在"无 codex / 无 gstack"下能回落 Claude 子代理、审查不中断（fallback 冒烟）
- [ ] 8.4 gstack 原生 outside voice 未被本 change 触碰（C7 边界核验）
- [ ] 8.5 其它使用 laodao-skills 的项目迁移影响已确认（OQ3）

## 9. 下游消费仓采纳（**不在本 change 内**，仅登记；各消费仓 update 后各自做）　【不在任何相内·routine，节奏随相：A 后拉 bundle / B 后迁 issues / C 后开 voice】

- [ ] 9.1 〔下游〕消费仓跑 `opsx-project-init update` 重拉新 bundle（workflow/tools 归位、新 step prompt）
- [ ] 9.2 〔下游〕迁移各仓 `openspec/{buglists,todolists}/` 数据 → `issues/{buglist,todolist}/`，跑 `reindex` 建 INDEX/batches（走 destructive-commands 规则）
- [ ] 9.3 〔下游〕改各仓 `config.yaml` / `CLAUDE.md` 的 issues·tools 路径引用
