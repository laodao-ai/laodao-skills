---
name: project-init
description: >
  初始化项目通用约定：.editorconfig（UTF-8 + 缩进）、.gitattributes（LF 换行）、
  .claudeignore（AI 上下文排除）、openspec/rules/ 下的通用规则（文件格式、脚本标点容错、
  上下文排除、提问讨论规范）。普通已有配置和规则文件跳过不覆盖；project-init 自有托管块可幂等刷新。
  当用户说"初始化项目约定"、"铺项目规范"、"project-init"、"给新项目加上 editorconfig"、
  "配一下 claudeignore"，或使用 /project-init 时触发。
  与 sdflow-init（OpenSpec 工作流）互补不重叠：sdflow-init 管 spec 工作流，
  本 skill 管项目通用约定。推荐在 sdflow-init 之后执行（依赖 openspec/rules/ 目录已建好）。
---

# project-init

初始化项目通用约定（编码、换行、上下文排除、AI 协作规范）。

## 职责边界

| 托管方 | 托管边界 |
|---|---|
| `project-init` | `.editorconfig`、`.gitattributes`、`.claudeignore`、`openspec/rules/` 通用规则，以及 CLAUDE.md / AGENTS.md 中的 `project-init:windows-shell` 托管块 |
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

### Step 2: 铺配置文件

对每个配置文件（`.editorconfig`、`.gitattributes`、`.claudeignore`）：

- **不存在** → 从 `assets/` 复制模板，按项目实际情况调整（见下方「项目适配」）
- **已存在** → **跳过，不覆盖**。报告跳过原因，提示用户手动对比模板

### Step 3: 铺规则文件

对每个 rule 文件：

- **不存在** → 从 `assets/rules/` 复制
- **已存在** → **跳过，不覆盖**

### Step 4: .claudeignore 项目适配

`.claudeignore` 的排除列表需要**按项目实际目录结构调整**，不能照搬模板：

1. 扫描项目根，识别存在的大目录（`du -sh */` 看体积）
2. 对照模板的推荐排除目标，保留实际存在的、去掉不存在的
3. 补充项目特有的应排除目录（如项目有 `vendor/`、`build/` 等）

### Step 5: .gitattributes 落地后处理

如果新建了 `.gitattributes`（之前没有），需要归一化已有文件：

```bash
git add --renormalize .
git checkout-index -f -a
```

提示用户这会修改工作区文件的换行符，建议先 commit 当前改动。

### Step 6: INDEX.md 同步

如果项目有 `openspec/INDEX.md`，把新增的 rule 登记到「设计强制规范（rules/）」表格。

### Step 7: 完成报告

完成报告必须分成四类：

- **仓库变更**：创建或跳过了哪些文件，AGENTS.md / CLAUDE.md 中的 `project-init:windows-shell` 托管块是插入、刷新还是未变化，`.claudeignore` 适配了哪些目录，以及是否需要 renormalize。
- **诊断结果**：分别列出 Git Bash、Git Bash 内 Python UTF-8 探针、Codex TOML 和 Claude JSON 的检查结论。
- **用户配置变更**：列出 `configure-user` 对两端配置的变更；未获明确授权或未执行时也要明确写出“无变更”。
- **剩余人工处理**：列出仍需安装、修复、授权或手动核对的事项；没有时写“无”。

## 项目适配指南

### .editorconfig 缩进调整

模板预设了常见语言的缩进。按项目技术栈调整：

- 有 Go → 保留 `*.go` tab 缩进
- 有前端（JS/TS/Svelte）→ 保留 2 空格
- 有 Python → 保留默认的 4 空格（`indent_size = 4`）
- 有 C/C++ → 按项目惯例（通常 4 空格或 tab）

读项目的 `go.mod`、`package.json`、`pyproject.toml` 等判断技术栈，不要问用户。

### .claudeignore 排除决策

按以下优先级决定是否排除一个目录：

1. **体积大（>5M）且日常开发不读** → 排除
2. **文件多（>100）且是历史/生成产物** → 排除
3. **是活跃的源码/文档/配置** → 不排除
4. **不确定** → 不排除（宁可多加载，不可漏重要文件）

## 幂等保证

- 普通配置文件和 rule 文件「不存在才创建、已存在则跳过」
- AGENTS.md / CLAUDE.md 中仅 `project-init:windows-shell` 托管块会被插入或刷新，托管块之外的用户内容和 `opsx-init` 块保持不变
- 输入模板未变化时重复执行，托管块也保持不变
- INDEX.md 同步前检查是否已登记，避免重复条目

## 与其他 skill 的关系

- **sdflow-init**：先跑 sdflow-init（建 openspec 骨架），再跑 project-init（铺通用约定）
- **gstack-project-init**：管 `docs/gstack/` 镜像规则，与本 skill 不重叠
