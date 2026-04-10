---
name: x-research
description: X/Twitter搜索词调研与选题分析工具。当用户提到"X调研"、"Twitter调研"、"X上有什么讨论"、"帮我看看推特"、"X关键词"、"twitter keyword"、"海外社区讨论"、"KOL观点调研"，或者用户正在做内容策划且想了解英文技术社区的讨论热度时，触发此skill。也适用于：用户想找某个技术话题的KOL和关键观点，或想知道X上什么话题正在被讨论。
---

# X/Twitter 搜索词调研

对种子关键词进行 X/Twitter 搜索调研，发现关键人物(KOL)和热门讨论，分析话题热度和观点分布，输出结构化选题池。

## X 平台特点

X 和 B站/YouTube/知乎 完全不同。它的核心价值不是"内容沉淀"，而是：

| 维度 | X 的独特价值 |
|------|------------|
| **KOL 发现** | 找到某个话题的关键人物和意见领袖 |
| **观点捕捉** | 捕捉最新的行业观点和争论 |
| **信号前哨** | 某个话题在X上热议 → 几周后出现在知乎/B站 |
| **内容灵感** | KOL 的一条推文可以扩展成一篇知乎文章或一条B站视频 |
| **社交互动** | 回复/引用 KOL 可以获得曝光 |

**X 在你的内容矩阵中的角色：** 不是主要发布平台，而是**情报站 + 灵感源 + 互动工具**。

## 技术限制

X 页面 JS 渲染，WebFetch 超时。依赖 WebSearch：
- **WebSearch site:x.com** — 发现帖子，获取内容摘要、作者和 URL
- 能获取：帖子内容、作者名和 handle、帖子 URL
- 无法自动获取：点赞数、转发数、回复数
- KOL 粉丝数需手动验证

## 输入

通过参数接收种子关键词（英文为主，X 以英文内容为主），格式灵活：
- 逗号分隔：`spec driven development, claude code, vibe coding`
- 或直接在对话中提供

## 调研流程

### Phase 1: 多维度搜索

对每个种子词，做 4 次 WebSearch：

**搜索 1 — 发现热门讨论和 KOL：**
```
WebSearch: "site:x.com \"{种子词}\""
```
引号搜索确保精确匹配，找到直接讨论该话题的帖子。

**搜索 2 — 发现近期讨论（趋势信号）：**
```
WebSearch: "site:x.com {种子词} {当前年份}"
```

**搜索 3 — 发现争议和批评（内容灵感）：**
```
WebSearch: "site:x.com {种子词} problem OR limitation OR wrong OR overrated"
```
争议性内容在 X 上传播最快，也是最好的内容灵感来源。

**搜索 4 — 发现实践者分享（实战信号）：**
```
WebSearch: "site:x.com {种子词} built OR shipped OR tried OR experience"
```
找到真正在用这个技术/方法的人，他们的分享比概念讨论更有价值。

### Phase 2: KOL 识别

从 Phase 1 的搜索结果中，识别关键人物：

**KOL 分类：**
- **创造者（Creators）** — 工具/框架的作者（如 Boris Cherny 之于 Claude Code）
- **布道者（Evangelists）** — 持续发帖推广某个方法论的人
- **批评者（Critics）** — 公开质疑或批评的人（他们的观点是你内容的差异化素材）
- **实践者（Practitioners）** — 分享真实使用经验的人

```markdown
### KOL Map: {种子词}

| # | Name | Handle | Role | Key Tweet | URL |
|---|------|--------|------|-----------|-----|
| 1 | Boris Cherny | @bcherny | Creator | Claude Code tips from the team | https://x.com/... |
| 2 | ... | @... | Evangelist | ... | ... |
```

**关注指标（需手动验证）：**
- 帖子互动量（点赞+转发 > 100 = 高影响力帖子）
- 作者粉丝数（> 10K = KOL，> 100K = 大V）
- 帖子是否被引用/讨论（thread 或 quote tweet）

### Phase 3: 观点图谱

将搜索到的帖子按观点分类，形成话题的"观点光谱"：

```
观点光谱: {种子词}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
支持/看好                        反对/质疑
├─ "game changer"               ├─ "overhyped"
├─ "production ready"           ├─ "looks like waterfall"
├─ "{具体观点}"                  ├─ "{具体观点}"
└─ by @handle                   └─ by @handle
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
中立/实践者视角:
├─ "works for X but not Y"
└─ by @handle
```

**争议点就是内容金矿。** 每一个争议都可以变成一条视频的标题："SDD 是不是就是瀑布模型？让我用实验告诉你"。

### Phase 4: 内容灵感提取

从观点图谱中提取可以转化为视频/文章的灵感：

| # | X 上的观点/讨论 | 转化为什么内容 | 目标平台 |
|---|---------------|-------------|---------|
| 1 | "@xxx: SDD looks like waterfall" | 视频：SDD 和瀑布模型到底什么区别？ | B站+YouTube |
| 2 | "@xxx: vibe coding会产生vibe debt" | 文章：AI写代码的"氛围债务"是什么？ | 知乎 |

### Phase 5: 分析判断

**话题热度（基于讨论密度和KOL参与度）：**
- 高：搜索结果 >15条相关帖子，有知名 KOL 参与讨论
- 中：搜索结果 5-15条，有一些讨论
- 低：搜索结果 <5条，话题在 X 上还很新

**争议度（内容潜力信号）：**
- 高：明显的支持/反对对立，多人参与辩论 → 最佳内容素材
- 中：有一些不同观点但没有激烈争论
- 低：大家观点一致 → 内容差异化困难

**时效性：**
- 正在热议（最近1周内多条讨论）→ 立即出内容
- 持续讨论（过去1-3个月稳定有帖子）→ 常青选题
- 已冷却（只有旧帖子）→ 需要新角度激活

## 输出

### 输出文件

文件名格式：`选题池-X-{日期}.md`
默认路径：与其他调研文件同级目录（如 `02-output/`）。

### 输出格式

```markdown
# X/Twitter 选题池（数据驱动）

> Research Date: {YYYY-MM-DD}
> Method: X keyword research (WebSearch site:x.com)
> Seeds: {list all seed keywords}
> Data Note: Like/repost counts need manual verification on X

---

## Overview

| Keyword | Discussion Heat | Controversy | Timeliness | Content Potential |
|---------|----------------|-------------|------------|-------------------|
| ... | High/Mid/Low | High/Mid/Low | Hot/Steady/Cold | High/Mid/Low |

---

## KOL Map

### {种子词1}

| # | Name | Handle | Role | Followers (est.) | Key Post | URL |
|---|------|--------|------|-----------------|----------|-----|
| 1 | ... | @... | Creator | — | "..." | https://x.com/... |

**Worth following:** {推荐关注的 2-3 个 handle}
**Worth engaging:** {推荐互动（回复/引用）的帖子}

---

## 观点光谱

### {种子词1}

```
支持/看好                        反对/质疑
├─ "{观点}" by @handle           ├─ "{观点}" by @handle
└─ URL                          └─ URL
中立/实践者:
├─ "{观点}" by @handle
```

---

## ★ 内容灵感（从X讨论转化）

| # | X 上的讨论/观点 | 转化形式 | 目标平台 | 标题草稿 |
|---|---------------|---------|---------|---------|
| 1 | ... | 视频 | B站+YouTube | ... |
| 2 | ... | 文章 | 知乎+公众号 | ... |
| 3 | ... | 推文thread | X | ... |

---

## 你的 X 发帖策略

基于调研结果，建议的 X 内容：

**Thread 选题（每周1-2条，每条5-10条推文）：**
1. {thread 主题} — {理由}

**互动策略（每天5-10分钟）：**
1. 关注 {KOL handles}
2. 对热门帖子有价值地回复（不是空洞的"great post!"）
3. 引用转发时加自己的观点

**B站视频 → X 联动：**
每次发B站视频时，在X上发一条英文摘要帖（配终端截图），引导到YouTube版本。

---

## 跨平台信号

（与B站/YouTube/知乎调研数据对比）

| 话题 | X 状态 | B站 | YouTube | 知乎 | 信号 |
|------|--------|-----|---------|------|------|
| ... | 热议中 | 空白 | 空白 | 少量 | X→B站/YouTube 搬运机会 |
| ... | 冷却 | 红海 | 红海 | 饱和 | 话题已过热，不追 |

---

## Next Steps

**立即可做（5分钟/条）：**
1. 关注 {3-5 个 KOL handles}
2. 回复 {1-2 条高价值帖子}

**本周可做：**
1. 写一条 X thread: {主题}

**内容联动：**
1. {B站视频} → X 英文摘要 → YouTube 链接

> X 调研建议每两周做一次。X 上的讨论节奏比其他平台快得多。
```

## 执行注意事项

- 每个种子词 4 次 WebSearch，并行执行。
- X 的互动数据（点赞、转发）**无法自动获取**，需手动验证。但帖子内容和 URL 可以获取。
- X 搜索结果的 URL 格式：`https://x.com/{handle}/status/{id}`。从 URL 可以推断作者 handle。
- **KOL 识别是 X 调研的核心价值。** 其他平台关注的是"什么内容有流量"，X 关注的是"谁在说什么"。
- 如果用户同时做了其他平台调研，在输出中增加跨平台信号对比。
- X 上的内容碎片化且时效性强。调研频率应高于其他平台（每2周一次 vs 每月一次）。
- **争议性帖子是金矿。** 搜索 3（problem/limitation/wrong）的结果往往比搜索 1 更有内容转化价值。
