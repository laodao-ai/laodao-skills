---
name: buglist-recorder
description: >
  自动把发现的 bug 记录进 openspec/buglists/YYYY-MM-DD-buglist.md（每天一文件，全局唯一 ID），
  并支持状态回写（OPEN→VERIFIED→FIXED…）与扫描列表。**只要在烧板验证、日志分析、代码审查、
  调试中发现了 bug 或缺陷，或用户说"记一下这个 bug / 这个问题记到 buglist / 标记 Bxx 已修 /
  列一下还没修的 bug"，就用本 skill**——不要手动拼 Markdown 表格和详细块，交给脚本保证 ID 不撞号、
  状态总览表与详细块双写一致、FIXED 必带根因和证据。本 skill 自包含整套 buglist 约定，是该约定的
  唯一真相源。Trigger with /buglist-recorder。
---

# buglist-recorder — 自动记录 / 回写 / 扫描 buglist

把"发现 bug → 落档 → 跟踪状态"这条易错的机械流程交给脚本兜底，模型只做判断。
**本 skill 自包含整套约定**（不依赖任何外部 rule 文件）。

> **为什么要脚本**：ID 全局唯一、状态总览表 ↔ 详细块 双写一致、FIXED 门禁——
> 这些手工做极易出错（撞号、改了表忘了块、FIXED 却没写根因）。脚本把它们变成确定性操作，
> 模型省下来的注意力用在真正需要判断的地方：这是不是真 bug、现象 vs 根因、定几级。

脚本：[scripts/buglist.py](scripts/buglist.py)（`python scripts/buglist.py --help`）。

---

## 何时用 / 何时不用

- ✅ **发现即记录**：烧板、日志分析、代码审查、调试中确认了 bug → 当天落档。
- ✅ **状态跟踪**：bug 被某 change 包入（PROPOSED）、修完（FIXED）、决定不修（WONTFIX）→ 回写。
- ✅ **盘点**：列出还没修的 bug、检查表与块是否一致。
- ⚠️ **change review 阶段发现的问题默认不进 buglist**：直接在该 change 内修掉即可。
  只有用户明确说"这个也记一笔"时才记——记之前先问一句确认，避免噪音。

## 三件事怎么做

### 1. 记录新 bug（add）

先判断（模型的活）：这是不是真 bug？**现象**（外在可观察）与**根因**（代码层因果）分开；
定**优先级**。然后把结构化内容交给脚本——它负责定位今日文件（缺则建目录+头部）、
扫描全局最大 ID 自增、把"总览表一行 + 详细块"一次写齐。

```bash
echo '{
  "module": "data_publish.c:120",
  "summary": "DATA/LOG envelope type 字段为空",
  "priority": "P1",
  "status": "OPEN",
  "phenomenon": "服务端收到的 envelope.type 恒为空字符串",
  "rootcause": "publish 前未从 ctx 取 type，结构体零值直接发出",
  "fix": ["发送前用 ctx->msg_type 填充 envelope.type", "加单测覆盖三种 type"],
  "impact": "所有 DATA/LOG 上行；server 侧无法路由",
  "source": "0628 烧板日志",
  "change": "add-envelope-type",
  "doc": ["changes/add-envelope-type/design.md", "rules/envelope-format.md"]
}' | python scripts/buglist.py add
```

- 输入走 **stdin 或 `--json <file>`**（多行内容用 JSON 天然安全）。
- 必填：`module` / `summary` / `priority` / `phenomenon`。`rootcause`/`fix`/`impact` 缺省留占位。
- `source` 只在**新建当日文件**时用作头部「来源」。
- 不传 `id` 则自动分配（默认前缀 `B`，要 `A`/其它分类用 `--prefix A`）。
- **时间**自动记录当前 `HH:MM`（当日文件已含日期，无需重复年月日），需要回填历史记录时用 `--time HH:MM` 覆盖。
- **关联Change**（`change` 字段，可选）：不传时脚本自动探测——优先取 `openspec/changes/` 下唯一未归档目录名，
  找不到再退化到当前 git branch 名（去掉 `feat/`/`fix/` 等前缀）；**多个 change 并行时脚本探测不到，
  这时模型应结合当前 session 上下文判断在哪个 change 里发现的 bug，显式传 `change` 字段覆盖**。
- **关联文档**（`doc` 字段，可选，string 或 list[string]）：记录时如果这个 bug 关联某个 openspec 文档
  （design/proposal/rule 等），尽量把该文档路径填进 `doc` 字段——填对格式后在 review 工具里能直接点开。
  路径不带 `openspec/` 前缀也会被自动补上；写进详细块的 **关联文档** 行（多个路径用「、」分隔），
  不会出现在总览表里。路径不存在只警告不阻断。不传时，若能从 `change` 探测到
  `design.md`/`proposal.md`（含已归档的 `changes/archive/*-{change}/`），会自动带上。
- 脚本回 `{"id","file","status","time","change"}`——把分到的 ID 告诉用户。

**摘要 vs 标题**：表里 `summary` 一句话讲现象（不是根因）；详细块标题默认取 summary，
要不同可加 `"title"`。需要额外字段（触发路径/时序/前置条件/验证方式）放 `"optional": {...}`。

### 2. 回写状态（set-status）

状态变更**双写**（总览表 + 详细块属性）并**追加一条历史**（不删旧状态）。带门禁：

```bash
python scripts/buglist.py set-status --id B17 --to FIXED --evidence "commit a1b2c3d"
python scripts/buglist.py set-status --id B9  --to PROPOSED --evidence "change add-envelope-type"
python scripts/buglist.py set-status --id B4  --to WONTFIX --reason "硬件限制，3.0 板子才有"
```

- **FIXED 门禁**：必须 `--evidence`（commit/change）且详细块**根因已补全**（非空、非 `<...>` 占位）——
  挡住"只写已修、没写为什么"。若根因还空，先用编辑补根因再回写。
- **WONTFIX 门禁**：必须 `--reason`，理由进历史。
- 状态码：`OPEN VERIFIED PROPOSED IN_PROGRESS FIXED WONTFIX BLOCKED`。

### 3. 扫描 / 盘点（scan）

```bash
python scripts/buglist.py scan                 # 全部，按优先级排
python scripts/buglist.py scan --status OPEN   # 只看未修
python scripts/buglist.py scan --json          # 机器可读
```

末尾自动做**表↔块一致性自检**（缺块/缺行/状态对不上都会报）。盘点或交接前先跑一次。

## 约定速查（本 skill 即真相源）

**文件**：`openspec/buglists/YYYY-MM-DD-buglist.md`，每天一个，当天所有 bug 追加进去，不拆分。
**结构**：头部元信息 → `## 状态总览`（表，7 列：ID/模块/问题摘要/优先级/状态/**时间**/**关联Change**）
→ 各 bug 的 `---` 分隔详细块。时间与关联Change **只记在总览表**，不进详细块——每条 bug 都会有，
便于事后追溯"哪天几点、在哪个 change 里发现的"。

**优先级**

| 级 | 定义 |
|----|------|
| P0 | 阻塞交付 / 不可用（Silent Reset、数据全丢） |
| P1 | 严重功能缺陷（核心异常、栈溢出风险、数据错误） |
| P2 | 中等 / 有绕过（精度偏差、需服务端配合） |
| P3 | 低 / 已知豁免（spec/impl 不一致、编译警告） |
| P4 | hygiene（残留、风格、纯清理） |

**状态码**

| 状态 | 含义 |
|------|------|
| OPEN | 已识别，未排期 |
| VERIFIED | 已扫描/复现确认是真 bug |
| PROPOSED | 已被某 OpenSpec change 包入 scope（注明 change） |
| IN_PROGRESS | 实现进行中 |
| FIXED | 已 commit + 验证（注明 commit/change） |
| WONTFIX | 评估后不修（保留理由） |
| BLOCKED | 等外部依赖（硬件/上游 SDK/业务决策） |

**铁律**（脚本已替你守住大半）：① ID 全局唯一（脚本自增）；② 表 ↔ 块双写一致（脚本双写）；
③ 状态追加式、不删历史（脚本追加历史行）；④ FIXED 必带根因 + 证据（脚本门禁）；
⑤ 清单先行——表和块同时落（脚本一次写齐）。

## 注意

- 脚本默认在 **git 仓根**下找 `openspec/buglists/`；不在 git 仓时退化为 `--root` 指定目录。
- 一个 bug 一条 ID；同一 bug 后续进展走 `set-status`，不要新开 ID。
- 模型的核心价值在**判断**：拒绝把 review 期琐碎问题、或还没确认的猜测当 bug 记进去（噪音比漏记更难清理）。
