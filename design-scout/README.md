# Design Scout

从 62+ 个顶级品牌 DESIGN.md 中智能匹配推荐最佳设计方案。支持 preview 可视化对比。

## 使用方法

```bash
/design-scout 深色 SaaS 工具，专业但有温度
/design-scout 类似 Notion 但更暗一点
/design-scout 面向开发者的 API 文档网站
/design-scout                          # 无参数，交互式提问
```

## 工作原理

1. **索引预筛**：读取 `data/index.md`（~3000 tokens），根据标签和语义匹配筛选 6-8 个候选
2. **深度比较**：读取候选品牌的完整 DESIGN.md，多维度评估匹配度
3. **Top 3 推荐**：展示概览 → 支持查看详情 / 对比 / 应用到项目
4. **可视化对比**（Tier A 品牌）：详情展示时附带 preview.html 和 preview-dark.html 文件路径，可直接在浏览器打开
5. **应用到项目**：支持单选或多选——所有选中方案进 `<project>/design-system/ref/<brand>/` 独立子目录，其中"主方案"的 `DESIGN.md` 额外复制到项目根作为工作文件

## 应用到项目的布局

支持单选和多选。多选时可持续保留多个参考方案做对比。

**多选示例**（选了 stripe、airbnb、linear.app，stripe 为主方案）：

```
projectname/
├── DESIGN.md                       ← 工作真相源（来自主方案 stripe，可适配）
└── design-system/
    └── ref/
        ├── stripe/                 ← ★ 主方案
        │   ├── DESIGN.md
        │   ├── README.md
        │   ├── preview.html
        │   └── preview-dark.html
        ├── airbnb/                 ← 参考方案
        │   └── (4 files)
        └── linear.app/             ← 参考方案
            └── (4 files)
```

**选择语法：**
- `应用 1` → 单选，自动为主方案
- `应用 1 2 3` → 多选，默认第一个为主方案
- `应用 1 2 3 主=2` → 多选，显式指定第 2 个为主方案

**为什么这样设计：**
- `<project>/DESIGN.md` 在根目录，保持作为 `frontend-design` / `design-consultation` 等下游 skill 的"真相源"
- `<project>/design-system/ref/<brand>/` 每个品牌独立子目录，支持同时保留多个参考方案做持续对比
- 子目录隔离避免品牌 `README.md` 覆盖项目自己的 README
- 路径 `design-system/ref/` 与项目约定的 `design-system/` 命名空间一致
- 适配（换品牌名）只改根目录 DESIGN.md，`design-system/ref/` 下所有方案保持原始底稿

## 数据结构（v2.0.0+）

每个品牌采用目录布局，保留原始命名（含 `.`）：

```
data/design-md/
├── airbnb/                 # Tier A
│   ├── DESIGN.md
│   ├── README.md
│   ├── preview.html        # 浅色主题可视化
│   └── preview-dark.html   # 深色主题可视化
├── linear.app/             # 品牌名保留原始 "."
│   └── ... 4 files
├── binance/                # Tier B：仅 DESIGN.md
│   └── DESIGN.md
└── ...
```

### 品牌分层（Tier）

- **Tier A (54 brands)**：含完整 preview 素材。推荐时附带两个 HTML 链接供浏览器可视化对比，同时可作为 `frontend-design` 等下游 skill 的设计参考
- **Tier B (8 brands)**：仅 DESIGN.md（binance, ferrari, lamborghini, meta, nike, renault, shopify, tesla）。scout 展示时只显示 DESIGN.md 路径，不伪造 preview 链接。待后续 `preview-html-fetcher` 工具从 getdesign.md 网站抓取补齐

## 数据来源

- **Tier A (54)**：来自 VoltAgent/awesome-design-md gut 前的历史快照（gut 后上游只剩 stub README.md）
- **Tier B (8)**：通过 `npx getdesign@latest` CLI 下载
- 使用 `/design-scout-sync` 添加新品牌（作为 Tier B）

## 索引维度

每个品牌条目包含以下字段：

- `tier` — A 或 B
- `hasPreview` — true / false
- `类目` — 6 大行业分类
- `一句话` — 英文描述（20-35 词）
- `色调` — light/dark/binary + 主色 + 辅色
- `风格` — 3-5 个英文关键词
- `温度` — warm / cool / neutral / warm-neutral / cool-neutral
- `暗色` — light-only / has-dark / dark-first
- `字体策略` — custom / system + 字体名
- `complexity` — minimal / balanced / rich
- `industry-fit` — 1-4 个封闭词表标签（20 个预定义标签）
- `适合` — 15-25 字中文描述

## 相关 Skills

- `/design-scout-sync` — 同步新品牌（两阶段模式：初始化迁移 + CLI 增量）
- `/design-consultation` — 从零创建 DESIGN.md（可基于 scout 推荐的方案定制）
- `/taste-design` — 语义化 DESIGN.md 生成（Stitch 优化）

## 版本历史

见 [CHANGELOG.md](./CHANGELOG.md)。最近重大变更：**v2.0.0** 迁移到目录结构、扩展索引维度、引入 Tier A/B 分层。
