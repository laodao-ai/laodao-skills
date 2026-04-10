# Design Scout Sync

从 getdesign.md 同步更新 design-scout 的设计库数据。

## 使用方法

```bash
/design-scout-sync                     # 全量同步
/design-scout-sync tesla nike shopify   # 只同步指定品牌
```

## 工作原理

1. 执行 `npx getdesign@latest list` 获取远端品牌列表
2. 对比本地 `~/.claude/skills/design-scout/data/design-md/` 已有文件
3. 输出差异报告，确认后下载新品牌
4. 自动生成索引条目，追加到 `data/index.md`
5. 更新 `CHANGELOG.md`

## 依赖

- Node.js（用于 `npx getdesign@latest`）
- 网络连接

## 相关 Skills

- `/design-scout` — 设计方案智能推荐（使用本 skill 同步的数据）
