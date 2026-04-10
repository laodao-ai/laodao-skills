---
name: youtube-research
description: YouTube搜索词调研与选题分析工具。当用户提到"YouTube调研"、"YouTube关键词"、"youtube keyword research"、"帮我看看YouTube上有什么"、"YouTube竞品分析"、"英文内容调研"，或者用户正在做面向海外/英文市场的内容策划时，触发此skill。也适用于：用户想了解某个选题在YouTube的竞争情况，或想知道英文技术视频的热度。
---

# YouTube 搜索词调研

对种子关键词进行 YouTube 搜索调研，分析搜索热度和竞争度，输出结构化选题池文档。

## 技术限制说明

YouTube 页面使用 JS 渲染，WebFetch 无法直接抓取搜索页或视频页的结构化数据（播放量、频道等）。本 skill 使用以下组合方案：

1. **WebSearch**（主力）— 多维度搜索发现 YouTube 视频，获取标题和 URL
2. **WebFetch 第三方聚合站**（补充）— 抓取排名/推荐类文章，获取播放量等数据
3. **手动验证**（必要时）— 对关键视频在 YouTube 上确认精确数据

因此，输出中的播放量可能不完整。标注"—"的需要用户手动验证。

## 输入

通过参数接收种子关键词（英文为主），格式灵活：
- 逗号分隔：`spec driven development, claude code tutorial, vibe coding`
- 或直接在对话中提供

如果用户没有提供关键词，先问用户要。

## 调研流程

### Phase 1: 多维度搜索

对每个种子词，做 3 次 WebSearch：

**搜索 1 — 发现热门视频：**
```
WebSearch: "{种子词} youtube"
```
从结果中提取 youtube.com 链接、视频标题。

**搜索 2 — 发现近期内容（竞争度信号）：**
```
WebSearch: "{种子词} youtube {当前年份}"
```

**搜索 3 — 发现聚合/排名页面（富数据来源）：**
```
WebSearch: "best {种子词} youtube videos" OR "{种子词} tutorial ranking"
```
如果搜索结果中包含第三方聚合页面（如 medium.com 的排名文章、课程推荐站等），用 WebFetch 抓取以获取播放量等额外数据。

**可选 搜索 4 — 中文竞品（如果用户同时做中英文内容）：**
```
WebSearch: "{种子词} tutorial 中文 youtube"
```

### Phase 2: 第三方聚合站数据补充

如果 Phase 1 中发现了排名/推荐类文章（如 "Best X tutorials"、"Top X videos ranked"），用 WebFetch 抓取：

```
WebFetch:
  url: {聚合站 URL}
  prompt: Extract ALL videos/tutorials listed. For each, get: 1. Title 2. Creator/channel 3. View count 4. Duration 5. YouTube URL. Return as markdown table sorted by views.
```

这些聚合站通常包含播放量、频道名等 YouTube 页面直接抓不到的数据。

### Phase 3: 数据整理

对每个种子词，合并所有来源的数据，去重后整理成表格：

```markdown
### Keyword: {种子词}

**Top Videos (by relevance):**

| # | Title | Views | Channel | Date | Duration | URL |
|---|-------|-------|---------|------|----------|-----|
| 1 | ... | 853K | xxx | 2026-03 | 15:30 | https://www.youtube.com/watch?v=xxx |
| 2 | ... | — | xxx | 2026-02 | 22:00 | https://www.youtube.com/watch?v=xxx |

Data sources: WebSearch + {聚合站名称 if used}
```

URL 格式统一为 `https://www.youtube.com/watch?v=xxx`。
播放量无法获取时标记"—"，并在表格下方注明"标记—的需在YouTube手动验证"。

### Phase 4: 分析判断

**搜索热度（基于可获取的数据）：**
- 高：搜索结果丰富（>15条相关视频），有聚合排名文章，头部视频播放量 >100K
- 中：搜索结果中等（5-15条），部分视频播放量 10K-100K
- 低：搜索结果稀少（<5条），播放量普遍 <10K
- 无法判断：播放量数据不足

**竞争度（基于近期内容密度）：**
- 高：2026年有 >5条新视频，且有知名频道参与
- 中：2026年有 2-5 条新视频
- 低：2026年 <2 条新视频，或该话题在 YouTube 上很新
- 无法判断：时间数据不足

**蓝海信号：**
- 英文内容是否空白或稀缺
- 是否有中文创作者用英文覆盖该话题（你的潜在竞品）
- 是否有聚合文章但实际视频很少（说明需求存在但供给不足）

**与B站对比（如果同时做了 /bilibili-research）：**
- 哪些话题在 YouTube 更热 / B站更热
- 哪些话题是"YouTube 有但 B站 没有"（可以搬运/改编）

### Phase 5: 2x2 矩阵分类

同 bilibili-research 的分类逻辑：

```
                 搜索量高                搜索量低
            ┌──────────────────┬──────────────────┐
竞争少      │  ★ Gold Mine      │  Niche Content   │
            │  Priority         │  Low traffic     │
            ├──────────────────┼──────────────────┤
竞争多      │  Need Edge        │  Skip            │
            │  Find your angle  │                  │
            └──────────────────┴──────────────────┘
```

## 输出

### 输出文件

文件名格式：`选题池-YouTube-{日期}.md`
默认路径：与 bilibili-research 同级目录（如 `02-output/`）。

### 输出格式

```markdown
# YouTube 选题池（数据驱动）

> Research Date: {YYYY-MM-DD}
> Method: YouTube keyword research (WebSearch + aggregator sites)
> Seeds: {list all seed keywords}
> Data Note: View counts marked "—" need manual verification on YouTube

---

## Overview

| Keyword | Search Volume | Competition | Category | Blue Ocean Signal |
|---------|--------------|-------------|----------|-------------------|
| ... | High/Mid/Low | High/Mid/Low | Gold Mine/Edge/Niche/Skip | Yes/No |

---

## ★ Gold Mine (High demand + Low competition)

### {keyword}

**Volume:** High | **Competition:** Low | **Blue Ocean:** {description}

| # | Title | Views | Channel | Date | Duration | URL |
|---|-------|-------|---------|------|----------|-----|
| 1 | ... | ... | ... | ... | ... | https://www.youtube.com/watch?v=xxx |

**Title Ideas:** {1-2 English title drafts based on search patterns}
**B站 Cross-reference:** {如果做了B站调研，对比两个平台的差异}

---

## Need Differentiation (High demand + High competition)

### {keyword}
...

**Differentiation Angle:** {具体的差异化建议}

---

## Niche Content (Low demand + Low competition)
...

---

## Skip
| Keyword | Reason |
|---------|--------|
| ... | Low demand + high competition |

---

## High-Value Title Patterns

YouTube 技术视频的高效标题模式（从搜索结果中提取）：

| Pattern | Example | Frequency |
|---------|---------|-----------|
| ... | ... | ... |

---

## B站 vs YouTube Cross-Analysis

（仅当同时存在 B站调研数据时生成此部分）

| Topic | B站 Status | YouTube Status | Opportunity |
|-------|-----------|---------------|-------------|
| ... | 红海 | 蓝海 | YouTube优先 |
| ... | 蓝海 | 红海 | B站优先 |

---

## Next Steps

Top 3 recommended video topics for YouTube:
1. {topic} — {reason}
2. {topic} — {reason}
3. {topic} — {reason}

> Recommend re-running this research monthly to track keyword trends.
> For precise view counts, manually verify top candidates on YouTube.
```

## 执行注意事项

- 每个种子词 3 次 WebSearch + 可选 WebFetch，总搜索量可控。可以并行搜索不同种子词。
- YouTube 的播放量和频道数据**不一定能完整获取**。数据缺失时标记"—"，不要编造。
- 第三方聚合站（Medium 排名文章、课程推荐站等）是获取播放量数据的最佳来源。搜索结果中发现这类页面时优先用 WebFetch 抓取。
- 如果用户同时做了 `/bilibili-research`，在输出中增加 B站 vs YouTube 对比分析。检查当前项目中是否存在 `选题池-*.md` 文件来判断。
- 英文标题建议遵循 YouTube 技术频道的常见模式：动作词开头（"Build"、"How I"）、数字（"5 mistakes"）、对比（"X vs Y"）、时间框架（"in 10 minutes"）。
