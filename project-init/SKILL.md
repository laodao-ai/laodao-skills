---
name: project-init
description: >
  初始化项目通用约定：.editorconfig（UTF-8 + 缩进）、.gitattributes（LF 换行）、
  .claudeignore（AI 上下文排除）、openspec/rules/ 下的通用规则（文件格式、脚本标点容错、
  上下文排除、提问讨论规范）。幂等执行，已有配置智能合并。
  当用户说"初始化项目约定"、"铺项目规范"、"project-init"、"给新项目加上 editorconfig"、
  "配一下 claudeignore"，或使用 /project-init 时触发。
  与 sdflow-init（OpenSpec 工作流）互补不重叠：sdflow-init 管 spec 工作流，
  本 skill 管项目通用约定。推荐在 sdflow-init 之后执行（依赖 openspec/rules/ 目录已建好）。
---

# project-init

初始化项目通用约定（编码、换行、上下文排除、AI 协作规范）。

## 职责边界

| 本 skill 管 | sdflow-init 管 |
|---|---|
| `.editorconfig`（编码 + 缩进） | `openspec/workflow/`（规则集 bundle） |
| `.gitattributes`（LF 换行） | `openspec/config.yaml` |
| `.claudeignore`（AI 上下文排除） | CLAUDE.md / AGENTS.md 的 OpenSpec 托管块 |
| `openspec/rules/` 下的通用 rule | `openspec/INDEX.md` 的 workflow 规则区块 |

## 产物清单

### 配置文件（项目根）

| 文件 | 作用 |
|---|---|
| `.editorconfig` | UTF-8 编码、LF 换行、缩进风格（Go=tab, 前端=2空格） |
| `.gitattributes` | git 层 LF 归一化 + 二进制标记 |
| `.claudeignore` | 排除归档 change、impl-reports、hack、drafts |

### 规则文件（`openspec/rules/`）

| 文件 | 作用 |
|---|---|
| `file-format-convention.md` | UTF-8 + LF 两层保证规范 |
| `script-punctuation-resilience.md` | py/sh 脚本解析中文文档时的标点容错 |
| `context-exclusion.md` | AI 上下文排除列表及理由 |
| `question-discussion-convention.md` | 禁 AskUserQuestion、多问题先总览再逐个讨论 |

## 执行流程

### Step 1: 前置检查

1. 确认当前目录是 git 仓库（不是则提示先 `git init`）
2. 检查 `openspec/rules/` 目录是否存在（不存在则创建）
3. 确定 SKILL 资产目录路径（`$SKILL_DIR/assets/`）

### Step 2: 铺规则文件（直接复制）

用 `cp -n`（不覆盖已有）把 4 个规则文件从 `$SKILL_DIR/assets/rules/` 复制到 `openspec/rules/`：

```bash
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"  # 或用实际解析到的 skill 路径
cp -n "$SKILL_DIR/assets/rules/"*.md openspec/rules/
```

- **不存在** → 复制落地
- **已存在** → `cp -n` 自动跳过，不覆盖

### Step 3: 铺配置文件（智能合并）

对 `.editorconfig`、`.gitattributes`、`.claudeignore` 三个文件，**不再跳过已有文件**，
而是检查是否包含必需配置，缺什么补什么。

#### .editorconfig

模板中的**必需配置**（`[*]` 段）：

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true
```

检查逻辑：

1. **不存在** → 从 `assets/.editorconfig` 复制，然后做项目适配（见下方）
2. **已存在** → 逐项检查：
   - 文件是否有 `root = true` → 没有则在文件头部加
   - `[*]` 段是否包含 `charset = utf-8` → 没有则在 `[*]` 段补
   - `[*]` 段是否包含 `end_of_line = lf` → 没有则补
   - `[*]` 段是否包含 `insert_final_newline = true` → 没有则补
   - `[*]` 段是否包含 `trim_trailing_whitespace = true` → 没有则补
   - **不动已有的语言段**（`[*.go]`、`[*.py]` 等）——那是项目自己的缩进选择
3. 如果已存在且必需配置全有 → 报告「已符合」，不做任何修改

#### .gitattributes

模板中的**必需配置**：

```
* text=auto eol=lf
```

检查逻辑：

1. **不存在** → 从 `assets/.gitattributes` 复制
2. **已存在** → 检查是否包含 `* text=auto eol=lf`（或等价的 `* text=auto` + 各类型 `eol=lf`）：
   - **有全局 `* text=auto eol=lf`** → 符合，不改
   - **有 `* text=auto` 但没 `eol=lf`** → 提示用户：当前依赖 `core.autocrlf`，建议加 `eol=lf` 显式声明
   - **没有任何全局 text/eol 设置** → 在文件末尾追加必需配置段（保留已有的 per-type 规则）
   - 同时检查是否有 `*.bat`/`*.ps1` 的 CRLF 例外——没有则追加

#### .claudeignore

模板中的**必需排除项**：

```
openspec/changes/archive/
**/impl-reports/
```

检查逻辑：

1. **不存在** → 从 `assets/.claudeignore` 复制，然后做项目适配（见下方）
2. **已存在** → 逐行检查是否包含必需排除项：
   - 缺 `openspec/changes/archive/` → 追加
   - 缺 `**/impl-reports/` → 追加
   - **不删除项目已有的其他排除项**

### Step 4: .claudeignore 项目适配

对 `.claudeignore`（无论新建还是已有），按实际目录结构调整：

1. 扫描项目根（`du -sh */`），识别存在的大目录
2. 模板中的推荐排除目录，实际不存在的**删掉**（新建时）或**不追加**（已有时）
3. 按以下优先级判断是否排除：
   - **体积大（>5M）且日常开发不读** → 排除
   - **文件多（>100）且是历史/生成产物** → 排除
   - **是活跃的源码/文档/配置** → 不排除
   - **不确定** → 不排除（宁可多加载，不可漏重要文件）

### Step 5: .editorconfig 项目适配

仅对**新建**的 `.editorconfig` 做技术栈适配（已有的不动语言段）：

- 有 Go（`go.mod` 存在）→ 保留 `[*.go]` tab 缩进
- 无 Go → 删掉 `[*.go]` 段
- 有 Python（`*.py` 文件或 `pyproject.toml`）→ Python 缩进改 4 空格
- 有前端（`package.json`）→ 保留 2 空格

读项目的 `go.mod`、`package.json`、`pyproject.toml` 等判断技术栈，不要问用户。

### Step 6: .gitattributes 落地后处理

如果**新建**了 `.gitattributes`（之前没有），或**追加**了全局 `eol=lf` 配置，
需要归一化已有文件：

```bash
git add --renormalize .
git checkout-index -f -a
```

提示用户这会修改工作区文件的换行符，建议先 commit 当前改动。

### Step 7: INDEX.md 同步

如果项目有 `openspec/INDEX.md`，把新增的 rule 登记到「设计规则」表格。
检查每条 rule 是否已在表格中（按文件名匹配），已有则跳过。

### Step 8: 完成报告

报告：

| 类别 | 内容 |
|---|---|
| 新建 | 哪些文件是首次创建 |
| 合并 | 哪些已有文件补了哪些缺失配置 |
| 已符合 | 哪些已有文件无需任何修改 |
| 适配 | `.claudeignore` 和 `.editorconfig` 做了哪些项目适配 |
| 后处理 | 是否需要 renormalize |

## 幂等保证

- 规则文件：`cp -n` 不覆盖已有
- 配置文件：只补缺失配置，不修改已有配置项的值
- INDEX.md：按文件名去重，不重复登记
- 反复执行结果一致——第二次跑全部报告「已符合」

## 与其他 skill 的关系

- **sdflow-init**：先跑 sdflow-init（建 openspec 骨架），再跑 project-init（铺通用约定）
- **gstack-project-init**：管 `docs/gstack/` 镜像规则，与本 skill 不重叠
