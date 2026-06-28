---
name: todolist-recorder
description: >
  自动把优化想法 / 技术债 / 改进点等**非缺陷**项记录进 openspec/todolists/YYYY-MM-todolist.md
  （每月一文件，全局唯一 T-ID），并支持状态回写（OPEN→PROPOSED→DONE…）与扫描列表。**只要冒出一个
  "以后可以改进 / 这里能优化 / 这是个技术债 / 记个 TODO / 加进待办池"的想法，或用户说"记一下这个优化、
  这个改进想法存一下、标记 Txx 已完成、列一下待办"，就用本 skill**——别手动拼 Markdown，交给脚本保证
  T-ID 不撞号、轻量项只记一行、DONE 必带关联 change/commit。注意：这是攒"没坏但可以更好"的池子，
  已确认的 bug（坏了的东西）该用 buglist-recorder 而不是本 skill。本 skill 自包含整套 todolist 约定，
  是该约定的唯一真相源。Trigger with /todolist-recorder。
---

# todolist-recorder — 自动记录 / 回写 / 扫描 todolist

把"冒出改进想法 → 落进收集池 → 实施时回写"这条易丢的流程交给脚本兜底。
todolist 是**优化/技术债/改进**的收集池（没坏但能更好），实施时再走 OpenSpec change 落地。
**本 skill 自包含整套约定**（不依赖任何外部 rule）。

> **和 buglist 的分工**：buglist 记**已确认的缺陷**（坏了，需根因+修复）；todolist 记**改进想法**
> （没坏，按价值/成本排，不紧迫）。发现的是 bug → 用 `buglist-recorder`；是"可以更好" → 用本 skill。

> **为什么要脚本**：T-ID 全局唯一、表↔块一致、DONE 必带关联 change——手工易错。脚本兜住这些，
> 模型专注判断：这值不值得记、归哪个类型、要不要写动机/思路。

脚本：[scripts/todolist.py](scripts/todolist.py)（`python scripts/todolist.py --help`）。

---

## 何时用 / 何时不用

- ✅ **随手记录**：发现可优化点、技术债、想做的增强 → 当月落池，别靠记忆。
- ✅ **状态跟踪**：某项被 change 包入（PROPOSED）、做完（DONE）、决定不做（WONTDO）→ 回写。
- ✅ **盘点**：列出还没做的 TODO、按类型筛、检查一致性。
- ⚠️ **change review 阶段冒出的改进默认不进 todolist**：直接在该 change 内处理或写进它的 deferred 列表。
  只有用户明确说"这个也存一笔"才记——记前先确认。
- ⚠️ **已确认的 bug 不要记这里** → 用 `buglist-recorder`。

## 三件事怎么做

### 1. 记录新 TODO（add）

先判断（模型的活）：这值得记吗？归哪个**类型**？需不需要写动机/思路？然后交给脚本——
它定位当月文件（缺则建）、扫描全局最大 T-ID 自增、写总览表行；**只有给了动机/思路/备注才建详细块**
（轻量优先，简单项就一行）。

```bash
# 简单项：只记一行，不建块
echo '{"module":"meter_collect.c","summary":"温度采样改 DMA 批量读取","type":"性能优化","project":"smartrelay-4g"}' \
  | python scripts/todolist.py add

# 需要说明的项：带动机/思路 → 自动建详细块
echo '{
  "module":"meter_collect.c","summary":"温度采样改 DMA 批量读取","type":"性能优化",
  "motivation":"当前 4 步逐次 ADC 读取 ~1.2s，DMA 可降至 <100ms",
  "approach":"配置 ADC DMA 连续转换，一次读 4 通道",
  "note":"需确认 ML307C ADC 是否支持 DMA"
}' | python scripts/todolist.py add
```

- 输入走 **stdin 或 `--json <file>`**。必填：`module` / `summary`（描述）/ `type`。
- **类型**（受控词表）：`性能优化` `可观测性` `代码质量` `功能增强` `基础设施`。
- 可选块字段：`motivation`（动机）/ `approach`（思路）/ `note`（备注）——任一存在才建块。
- `project` 只在**新建当月文件**时写入头部。不传 `id` 则自动分配（默认前缀 `T`）。

### 2. 回写状态（set-status）

```bash
python scripts/todolist.py set-status --id T1 --to PROPOSED --evidence "change dma-sampling"
python scripts/todolist.py set-status --id T1 --to DONE     --evidence "commit a1b2c3d"
python scripts/todolist.py set-status --id T7 --to WONTDO   --reason "ROI 太低，硬件下一版才支持"
```

- **DONE 门禁**：必须 `--evidence`（关联的 change 名或 commit）——挡住"只标完成、不留线索"。
- **WONTDO 门禁**：必须 `--reason`，理由留痕。
- 状态码：`OPEN PROPOSED DONE WONTDO`。
- 机制：更新总览表状态列；**有详细块**则同步块状态 + 追加历史行；**无块但有证据/理由**则补一个
  最小块留痕（保证 DONE/WONTDO 的关联线索不丢）。

### 3. 扫描 / 盘点（scan）

```bash
python scripts/todolist.py scan                      # 全部，按状态排
python scripts/todolist.py scan --status OPEN        # 只看没做的
python scripts/todolist.py scan --type 性能优化       # 按类型筛
python scripts/todolist.py scan --json               # 机器可读
```

末尾自动做**表↔块一致性自检**（块缺表行、状态对不上都会报；块本身可选，不报"缺块"）。

## 约定速查（本 skill 即真相源）

**文件**：`openspec/todolists/YYYY-MM-todolist.md`，每月一个，当月所有 TODO 追加进去。
**结构**：头部 → `## 状态总览`（表）→ 各项 `---` 分隔详细块（**可选**，简单项只表行）。

**类型标签**

| 类型 | 含义 |
|------|------|
| 性能优化 | 提速 / 降资源占用 |
| 可观测性 | 日志 / metrics / 诊断增强 |
| 代码质量 | 重构 / 命名 / 结构改进 |
| 功能增强 | 新能力 / 扩展现有功能 |
| 基础设施 | 构建 / CI / 工具链 |

**状态码**

| 状态 | 含义 |
|------|------|
| OPEN | 已记录，未排期 |
| PROPOSED | 已被某 OpenSpec change 包入 scope |
| DONE | 已完成（注明 change/commit） |
| WONTDO | 评估后放弃（保留理由） |

**铁律**（脚本守住大半）：① T-ID 全局唯一（自增）；② 轻量优先——简单项只一行，要说明动机/思路才建块；
③ DONE 必带关联 change/commit（门禁）；④ 实施走 change——todolist 只是收集池，真做时通过 OpenSpec
change 落地，不在此直接改代码；⑤ 状态追加式、不删历史。

## 注意

- 脚本默认在 **git 仓根**下找 `openspec/todolists/`；不在 git 仓时用 `--root` 指定。
- 一个想法一条 T-ID；后续进展走 `set-status`，不要新开 ID。
- 模型的价值在**判断**：把噪音（太琐碎、重复、其实是 bug 的）挡在池子外，比记全更重要。
