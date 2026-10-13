---
name: xlsx-to-csv
description: >
  将 XLSX 文件转换为 CSV 格式，同时提取所有嵌入图片。
  当用户要求"XLSX转CSV"、"把Excel转成csv"、"将xlsx转换为csv"、
  "提取Excel内容"、"Excel转文本"、"xlsx转csv"等操作时触发此 skill。
  也适用于：用户提到需要将 Excel 数据导出为 CSV 格式，或需要从 XLSX 中提取图片。
  即使用户只说"转换这个Excel文件"也应触发。
  注意：如果用户想创建、编辑或操作 XLSX 文件（而非转换为 CSV），不需要触发此 skill。
---

# XLSX to CSV 转换

将 XLSX（Excel）文件转换为 CSV 格式，支持多 sheet 导出，同时提取所有嵌入图片。

## 依赖

转换脚本仅使用 Python 标准库（zipfile、xml.etree、csv），**无需安装任何第三方依赖**。

## 使用方式

运行 skill 自带的转换脚本：

```bash
python <skill-dir>/scripts/xlsx2csv.py <input.xlsx> [--output-dir <dir>] [--images-dir <name>] [--sheet <name_or_index>] [--encoding <enc>]
```

参数说明：
- `input`: XLSX 文件路径（必填）
- `--output-dir / -o`: 输出目录（默认在 XLSX 同级创建以文件名命名的子目录）
- `--images-dir / -i`: 图片子目录名（默认 `images`）
- `--sheet / -s`: 指定导出的 sheet（名称或从 0 开始的索引），不指定则导出全部
- `--encoding / -e`: CSV 文件编码（默认 `utf-8-sig`，Excel 友好的带 BOM 的 UTF-8）

## 工作流程

1. **执行转换** — 运行 `xlsx2csv.py` 脚本，它会：
   - 解压 XLSX（本质是 ZIP），解析 workbook 和各 sheet XML
   - 读取共享字符串表（`xl/sharedStrings.xml`）
   - 逐行逐单元格提取数据，写入 CSV
   - 多 sheet 时每个 sheet 生成一个独立的 CSV 文件
   - 提取 `xl/media/` 中的所有图片到输出目录
2. **后处理**（可选）— 如果需要调整：
   - 修改 CSV 分隔符或编码
   - 合并多个 sheet 的 CSV

## 多 Sheet 处理

- 单 sheet 的 XLSX：输出 `<name>.csv`
- 多 sheet 的 XLSX：每个 sheet 输出 `<name>__<sheet_name>.csv`
- 可通过 `--sheet` 参数仅导出指定 sheet

## 图片处理

- 图片从 `xl/media/` 中原样提取，保留原始文件名和格式
- 默认保存在输出目录的 `images/` 子目录
- 脚本会报告提取的图片数量

## 输出示例

```
input.xlsx (3 sheets: 数据, 配置, 图表)
→ input/
    ├── input__数据.csv
    ├── input__配置.csv
    ├── input__图表.csv
    └── images/
        ├── image1.png
        └── image2.png
```

## 注意事项

- 仅处理 `.xlsx` 格式（Office 2007+），不支持旧版 `.xls`
- 公式单元格导出的是缓存值（最后一次计算的结果），而非公式本身
- 合并单元格只有左上角有值，其余为空
- 日期单元格会尝试转换为 `YYYY-MM-DD` 或 `YYYY-MM-DD HH:MM:SS` 格式
- 默认使用 `utf-8-sig` 编码（带 BOM），确保 Excel 直接打开 CSV 时中文不乱码
