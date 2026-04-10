# Design Scout

从 62+ 个顶级品牌 DESIGN.md 中智能匹配推荐最佳设计方案。

## 使用方法

```bash
/design-scout 深色 SaaS 工具，专业但有温度
/design-scout 类似 Notion 但更暗一点
/design-scout 面向开发者的 API 文档网站
/design-scout                          # 无参数，交互式提问
```

## 工作原理

1. **索引预筛**：读取 `data/index.md`（~3000 tokens），根据标签和语义匹配筛选 4-8 个候选
2. **深度比较**：读取候选品牌的完整 DESIGN.md，多维度评估匹配度
3. **Top 3 推荐**：展示概览 → 支持查看详情 / 对比 / 应用到项目

## 数据来源

- 初始 54 个品牌来自 [awesome-design-md](https://github.com/VoltAgent/awesome-design-md)
- 额外 8 个品牌通过 [getdesign.md](https://getdesign.md) CLI 获取
- 使用 `/design-scout-sync` 同步更新

## 索引维度

每个品牌条目包含：类目、一句话描述、色调、风格、温度、暗色模式、字体策略、适合场景

## 相关 Skills

- `/design-scout-sync` — 从 getdesign.md 同步新品牌
- `/design-consultation` — 从零创建 DESIGN.md（可基于 scout 推荐的方案定制）
- `/taste-design` — 语义化 DESIGN.md 生成（Stitch 优化）
