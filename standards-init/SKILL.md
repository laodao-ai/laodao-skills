---
name: standards-init
description: >
  初始化项目通用约定：.editorconfig（UTF-8 + 缩进）、.gitattributes（LF 换行）、
  .claudeignore（AI 上下文排除）、openspec/rules/ 下的通用规则（文件格式、脚本标点容错、
  上下文排除、提问讨论规范）。幂等执行：已有配置智能合并，standards-init 自有托管块可安全刷新。
  当用户说"初始化项目约定"、"铺项目规范"、"standards-init"、"给新项目加上 editorconfig"、
  "配一下 claudeignore"，或使用 /standards-init 时触发。（本 skill 曾名 project-init，2026-08-21 改名）
  与 sdflow-init（OpenSpec 工作流）互补不重叠：sdflow-init 管 spec 工作流，
  本 skill 管项目通用约定。推荐在 sdflow-init 之后执行（依赖 openspec/rules/ 目录已建好）。
---

# standards-init

初始化项目通用约定（编码、换行、上下文排除、AI 协作规范）。曾名 `project-init`。

## 职责边界

| 托管方 | 托管边界 |
|---|---|
| `standards-init` | `.editorconfig`、`.gitattributes`、`.claudeignore`、`openspec/rules/` 通用规则，以及 CLAUDE.md / AGENTS.md 中的 `standards-init:windows-shell` 托管块（旧名 `project-init:windows-shell` 哨兵在 apply-repo 时自动原位升级） |
| `opsx-project-init` | 仅 CLAUDE.md / AGENTS.md 中的 `opsx-init` 托管块 |

## 产物清单

### 配置文件（项目根）

| 文件 | 作用 |
|---|---|
| `.editorconfig` | UTF-8 编码、LF 换行、缩进风格（Go=tab, 前端/Shell=2空格, Python=4空格） |
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

### Windows Git Bash 双代理支持

**仅当目标仓库直接运行在原生 Windows（非 WSL），并采用 Git for Windows 的 `bash.exe` 作为仓库 Bash 运行时时，才激活本节。** 非 Windows、WSL 或未采用 Git for Windows 的仓库跳过本节并报告原因。

默认流程在仓库根目录依次执行 `apply-repo`、`diagnose`；脚本通过自身位置读取 `assets/snippets/`，不会改变当前进程的工作目录：

```bash
python <skill-dir>/scripts/windows_shell.py apply-repo --root .
python <skill-dir>/scripts/windows_shell.py diagnose --root .
```

`diagnose` 分别报告 Git Bash 内 Python UTF-8 探针、Codex TOML 和 Claude JSON 的检查结果；探针成功不代表两端 agent 配置已经正确。

只有用户明确授权修改本机用户配置后，才额外执行：

```bash
python <skill-dir>/scripts/windows_shell.py configure-user --root .
```

`configure-user` 会修改用户主目录中的 Codex 与 Claude 配置；Git Bash 无法发现时可显式传入 `--bash <path-to-bash.exe>`。未获得授权时不得执行，并在完成报告中写明“未授权、未修改”。所有命令向标准输出打印机器可读 JSON，配置或调用错误写入标准错误。

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

完成报告必须分成四类：

- **仓库变更**：列出首次创建、智能合并、已符合及跳过的文件；说明 `.claudeignore` / `.editorconfig` 的项目适配、AGENTS.md / CLAUDE.md 中 `standards-init:windows-shell` 托管块的状态（含旧哨兵是否被原位升级），以及是否需要 renormalize。
- **诊断结果**：分别列出 Git Bash、Git Bash 内 Python UTF-8 探针、Codex TOML 和 Claude JSON 的检查结论。
- **用户配置变更**：列出 `configure-user` 对两端配置的变更；未获明确授权或未执行时也要明确写出“无变更”。
- **剩余人工处理**：列出仍需安装、修复、授权或手动核对的事项；没有时写“无”。

## 幂等保证

- 规则文件使用 `cp -n`，不覆盖已有文件
- 配置文件只补缺失的必需配置，不修改已有配置项的值
- AGENTS.md / CLAUDE.md 中仅 `standards-init:windows-shell` 托管块会被插入或刷新（读到改名前注入的旧哨兵 `project-init:windows-shell` 时自动原位升级为新哨兵，不产生重复块），托管块之外的用户内容和 `opsx-init` 块保持不变
- 输入模板未变化时重复执行，托管块也保持不变
- INDEX.md 按文件名去重，不重复登记
- 反复执行结果一致——第二次执行全部报告「已符合」或「未变化」

## 与其他 skill 的关系

- **sdflow-init**：先跑 sdflow-init（建 openspec 骨架），再跑 standards-init（铺通用约定）
- **gstack-project-init**：管 `docs/gstack/` 镜像规则，与本 skill 不重叠
