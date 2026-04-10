# Design Scout Changelog

## v2.0.0 (2026-04-10) — BREAKING: 迁移到目录结构 + 扩展索引维度

**重大变更（BREAKING）：**

- **数据布局**：`data/design-md/` 从扁平 `{brand}.md` 迁移到目录结构 `{brand}/{DESIGN.md, README.md, preview.html, preview-dark.html}`
- **品牌命名**：标识符保留原始 `.`（`linear.app` 替代 `linear-app`、`mistral.ai` 替代 `mistral-ai` 等）
- **索引格式**：`index.md` 从零重建，新增字段 `tier`、`hasPreview`、`complexity`、`industry-fit`

**新增能力：**

- **Tier A / Tier B 分层**：
  - Tier A (54 brands)：完整 4 文件（DESIGN.md + README.md + preview.html + preview-dark.html）
  - Tier B (8 brands)：仅 DESIGN.md（binance, ferrari, lamborghini, meta, nike, renault, shopify, tesla）
- **推荐展示优雅降级**：Tier A 附带 preview 链接供浏览器可视化对比，Tier B 仅展示 DESIGN.md 路径
- **多选 + 主方案的应用到项目机制**：
  - 支持单选或多选 Top 3 中的任意几个方案
  - 所有选中方案进 `<project>/design-system/ref/<brand>/` 独立子目录，每个品牌一个
  - 指定一个作为"主方案"（默认第一个，可用 `主=N` / `primary=N` 覆盖），其 `DESIGN.md` 额外复制到 `<project>/DESIGN.md` 作为工作真相源
  - 路径 `design-system/ref/` 与项目约定的 `design-system/` 命名空间一致
  - 子目录隔离避免品牌 `README.md` 覆盖项目自己的 README
- **扩展维度索引**：`complexity`（minimal/balanced/rich）、`industry-fit`（20 个封闭标签词表）
- **sync 两阶段模式**：初始化迁移（从本地快照）+ 增量同步（CLI 新品牌）

**迁移来源：**

- 54 个 Tier A 品牌来自 `D:/01-laodao/design-system/awesome-design-md/design-md/`（gut 前的历史快照）
- 8 个 Tier B 品牌来自 `npx getdesign@latest`

**数据统计：**

- 品牌总数：62 (Tier A: 54, Tier B: 8)
- index.md: 874 行
- 数据源：本地快照 + getdesign v0.6.0

**备份：**

- 旧扁平结构备份在 `~/.claude/skills/design-scout/data/.backup-20260410-145228/`

**后续：**

- Tier B 品牌的 preview 素材将由独立变更 `preview-html-fetcher` 从 getdesign.md 网站抓取补齐

**应用影响：**

- 项目中已用 design-scout 生成的 DESIGN.md 不受影响（它们是用户资产）
- 新的 scout 调用从目录结构读取数据，命名规范变化

---

## v1.0.0 (2026-04-10)

- 初始版本
- 收录 62 个品牌 DESIGN.md
  - 54 个来自 awesome-design-md 仓库
  - 8 个通过 getdesign.md CLI 下载（binance, ferrari, lamborghini, meta, nike, renault, shopify, tesla）
- 预构建 index.md 索引（62 条，含类目/色调/风格/温度/暗色/字体/适合场景）
- 数据源：awesome-design-md repo + getdesign v0.6.0
