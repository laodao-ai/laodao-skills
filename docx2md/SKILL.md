---
name: docx-to-markdown
description: >
  将 DOCX 文件转换为 Markdown 格式，同时提取并保留所有图片。
  当用户要求"DOCX转markdown"、"把Word文档转成md"、"将docx转换为文本"、
  "提取Word内容"、"Word转Markdown保留图片"、"docx转md"等操作时触发此 skill。
  也适用于：用户提到需要将 Word 需求文档、技术文档、报告等转为可编辑的 Markdown 格式，
  或者需要从 DOCX 中提取图片。即使用户只说"转换这个Word文件"也应触发。
  注意：如果用户只是想读取或编辑 DOCX 的 XML 内容（不需要转为 Markdown），不需要触发此 skill。
---

# DOCX to Markdown 转换

将 DOCX（Word）文件转换为结构化 Markdown，提取文本（保留标题层级、列表、表格、粗体/斜体等格式）并导出所有嵌入图片。

## 依赖

转换脚本仅使用 Python 标准库（zipfile、xml.etree），**无需安装任何第三方依赖**。

## 使用方式

运行 skill 自带的转换脚本：

```bash
python <skill-dir>/scripts/docx2md.py <input.docx> [--output-dir <dir>] [--images-dir <name>]
```

参数说明：
- `input`: DOCX 文件路径（必填）
- `--output-dir / -o`: 输出目录（默认在 DOCX 同级创建以文件名命名的子目录）
- `--images-dir / -i`: 图片子目录名（默认 `images`）

## 工作流程

1. **执行转换** — 运行 `docx2md.py` 脚本，它会：
   - 解压 DOCX（本质是 ZIP），解析 `word/document.xml`
   - 解析 relationship 文件，建立图片 rId 到文件路径的映射
   - 遍历 XML 树，将各元素转为对应的 Markdown 语法
   - 提取 `word/media/` 中的所有图片到输出目录
   - 在 Markdown 中用相对路径 `![alt](images/xxx.png)` 引用图片
2. **后处理**（可选）— 如果自动转换结果需要调整：
   - 修正标题层级
   - 合并被错误拆分的段落
   - 调整表格格式
   - 修正列表缩进

## 支持的格式元素

| Word 元素 | Markdown 输出 |
| --- | --- |
| Heading 1-6 / Title / Subtitle | `# ~ ######` |
| 粗体 `<w:b>` | `**text**` |
| 斜体 `<w:i>` | `*text*` |
| 删除线 `<w:strike>` | `~~text~~` |
| 等宽字体 (Consolas/Courier) | `` `code` `` |
| 无序列表 | `- item` |
| 有序列表 | `1. item` |
| 嵌套列表 | 缩进 `  - item` |
| 超链接 | `[text](url)` |
| 表格 | Markdown 表格语法 |
| 嵌入图片（drawing/VML） | `![alt](images/file.png)` |
| 分页符 | `---` |

## 图片处理

- 图片从 `word/media/` 中原样提取，保留原始文件名和格式
- 默认保存在输出目录的 `images/` 子目录
- 支持 Drawing（新格式）和 VML/pict（旧格式）两种嵌入方式
- 自动提取图片的 alt 描述文字（如果有）

## 输出示例

```markdown
# 文档标题

## 第一章 概述

这是正文内容，**加粗文字** 和 *斜体* 会被保留。

![示意图](images/image1.png)

| 列A | 列B | 列C |
| --- | --- | --- |
| 1   | 2   | 3   |

## 第二章 详细说明

1. 第一点
2. 第二点
   - 子项目 A
   - 子项目 B
```

## 注意事项

- 仅处理 `.docx` 格式（Office 2007+），不支持旧版 `.doc` 格式
- 复杂排版（文本框、艺术字、SmartArt）可能无法完整转换
- 嵌套表格会被扁平化处理
- 脚注/尾注暂不支持
