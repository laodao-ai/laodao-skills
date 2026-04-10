---
name: pdf-to-markdown
description: >
  将 PDF 文件转换为 Markdown 格式，同时提取并保留所有图片。
  当用户要求"PDF转markdown"、"把PDF转成md"、"将PDF文档转换为文本"、
  "提取PDF内容"、"PDF转文字保留图片"等操作时触发此 skill。
  也适用于：用户提到需要将 PDF 需求文档、技术文档、报告等转为可编辑的 Markdown 格式。
  注意：如果用户只是想读取 PDF 内容而不需要保存为 Markdown 文件，不需要触发此 skill。
---

# PDF to Markdown 转换

将 PDF 文件转换为结构化 Markdown，提取文本（保留标题层级、表格、加粗等格式）并导出所有嵌入图片。

## 依赖

转换脚本需要 `pymupdf` 和 `Pillow`。如果未安装，先执行：

```bash
pip install pymupdf Pillow
```

## 使用方式

运行 skill 自带的转换脚本：

```bash
python <skill-dir>/scripts/pdf2md.py <input.pdf> [--output <output.md>] [--image-dir <dir>]
```

参数说明：
- `input`: PDF 文件路径（必填）
- `--output / -o`: 输出 Markdown 路径（默认在 PDF 同级创建 `<pdf_stem>/` 子目录）
- `--image-dir / -i`: 图片保存目录（默认 `<pdf_stem>/images/`）

### 默认输出结构

```
原始目录/
├── 文档.pdf               # 原 PDF（不动）
└── 文档/                   # 自动创建的输出目录
    ├── 文档.md             # 转换后的 Markdown
    └── images/             # 提取的图片
        ├── doc_p1_1_a3f2c1b4.png
        └── doc_p2_1_b7e8d2f1.jpg
```

## 工作流程

### 步骤 1：检查依赖

运行 `python -c "import pymupdf"` 确认 pymupdf 已安装，未安装则 `pip install pymupdf Pillow`

### 步骤 2：执行脚本转换

运行 `pdf2md.py` 脚本，它会自动完成：
- 逐页解析 PDF 文本块，根据字体大小推断标题层级（H1-H3）
- 识别并提取表格，转为 Markdown 表格语法
- 提取所有嵌入图片，保存到图片目录，在 Markdown 中用 `![image](filename)` 引用
- 跳过极小的装饰性图片（< 20x20px），大图自动压缩到 1600px 以内

脚本内置的自动后处理（`postprocess_markdown`）会修复：
- 清理零宽空格（U+200B 等不可见字符）
- 删除 PDF 渲染产生的"代码块"标签文字
- 自动识别 ASCII art（box-drawing 字符）并包裹在 ``` 代码块中
- 自动识别 JSON 块并包裹在 ```json 代码块中
- 剥离代码块和 JSON 块中混入的行号（独立数字行）
- 修复列表项被误判为标题的情况（`### • xxx` → `- xxx`）
- 修复子列表被误判为标题（`## ◦ xxx` → `   - xxx`）
- 清除分页产生的多余 `---` 分隔线
- 清理连续空行

### 步骤 3：LLM 语义后处理（重要）

脚本的自动后处理能修复大部分格式问题，但以下语义级问题需要你（LLM）读取生成的 Markdown 并手动修正：

1. **跨页断裂的表格** — PDF 分页可能将一个表格拆成两段，需要合并为一个完整表格
2. **标题层级不一致** — 同级内容可能因字体大小微差被判为不同层级，需要统一
3. **重复标题** — 文档标题可能同时出现为 H1 和 H2，删除重复的
4. **断裂的段落** — 同一段文字被 PDF 换行拆成多个块，需要合并
5. **接口路径中的空格** — PDF 渲染可能在 URL 中插入空格（如 `/qry/all? c=modellist` → `/qry/all?_c=modellist`）
6. **表格中缺失的数据行** — 跨页的表格可能丢失行，对照原 PDF 补全

执行方法：
1. 用 Read 工具读取生成的 `.md` 文件
2. 逐节检查上述问题
3. 用 Edit 工具修正

询问用户是否需要执行这一步。如果用户表示"自动修复"或"帮我修好"，则直接执行而无需逐项确认。

## 图片处理

- 图片以 `{prefix}_p{page}_{index}_{hash}.{ext}` 命名，带内容哈希防重复
- 默认保存在输出目录下的 `images/` 子目录
- Markdown 中使用相对路径引用：`![image](images/xxx.png)`

## 注意事项

- 扫描件 PDF（图片型，非文字型）无法提取文本，需要先 OCR
- 复杂排版（多栏、文字环绕图片）可能导致段落顺序不完全准确
- 脚本自动处理能解决约 80% 的格式问题，剩余 20% 的语义问题由 LLM 后处理修正
