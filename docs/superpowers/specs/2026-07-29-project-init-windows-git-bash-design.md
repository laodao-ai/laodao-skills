# project-init Windows Git Bash 双代理支持设计

## 目标

扩展 `project-init`，让原生 Windows 仓库把 Git Bash 定义为唯一的项目脚本运行时，同时分别适配 Codex 与 Claude Code 的命令宿主差异，并让 Windows Python 的标准输入输出稳定使用 UTF-8。

最终约定：

- 仓库命令、`.sh`、路径、变量、管道和重定向采用 Bash/POSIX 语义。
- Codex 的后台命令若由 PowerShell 托管，显式通过 Git Bash 执行。
- Claude Code 直接使用其 Bash 工具，并固定到 Git for Windows 的 `bash.exe`；不在 Bash 工具中生成 PowerShell 包装语法。
- Python 子进程获得 `PYTHONUTF8=1` 和 `PYTHONIOENCODING=utf-8`。
- PowerShell 只用于无法合理经 Git Bash 完成的 Windows 主机或 bootstrap 操作，使用时必须说明原因。

## 现状与约束

当前 `project-init` 是声明式 skill，负责 `.editorconfig`、`.gitattributes`、`.claudeignore` 和 `openspec/rules/`，已有文件一律跳过。仓库中的 `AGENTS.md` 与 `CLAUDE.md` 各自包含由 `opsx-project-init` 维护的 `opsx-init` 托管块。

本能力不能：

- 修改或包住现有 `opsx-init` 托管块；
- 覆盖用户手写的 agent 指令；
- 把 Claude Code 的 Bash 工具误当成 PowerShell；
- 默认静默修改用户主目录配置；
- 把机器相关的 Git 安装路径提交到消费仓库。

## 方案比较

### A. 只扩写 SKILL.md

由执行 skill 的 agent 临场编辑文件。改动小，但托管块合并、配置诊断和幂等行为难以自动验证，不同 agent 的结果可能漂移。

### B. 独立、可测试的辅助脚本（采用）

保留 `project-init` 的声明式流程，新增一个聚焦 Windows shell 契约的 Python 辅助脚本。脚本负责确定性地注入托管块、诊断环境，并在显式子命令下合并用户配置。SKILL.md 负责判断何时调用与解释结果。

这能隔离复杂的文本合并逻辑，并允许对真实临时文件做回归测试。

### C. 把 project-init 全部重写为初始化器

统一性最好，但会把现有配置、规则、`.claudeignore` 自适配全部纳入本次重构，明显超出需求。

## 架构

```text
project-init/SKILL.md
        │
        ├── repo apply ────────────────┐
        │                              │
        ▼                              ▼
 project-init helper              repository
        │                     ┌─ AGENTS.md: Codex adapter
        │                     └─ CLAUDE.md: Claude adapter
        │
        ├── diagnose ───────────── Git Bash + Python encoding + user config
        │
        └── configure-user (explicit)
                              ┌─ ~/.codex/config.toml
                              └─ ~/.claude/settings.json
```

辅助脚本分为三个互不混杂的动作：

1. `apply-repo`：只修改目标仓库内的 agent 指令文件。
2. `diagnose`：只读检查 Git Bash、Python 编码和两端配置，返回可操作结果。
3. `configure-user`：只有用户明确授权时才合并用户级配置。

## 仓库级托管块

### AGENTS.md / Codex adapter

新增独立标记：

```text
<!-- project-init:windows-shell:start -->
...
<!-- project-init:windows-shell:end -->
```

内容声明共享的 Bash/POSIX 契约，并增加 Codex 特有规则：后台工具若由 PowerShell 托管，使用：

```powershell
& 'C:\Program Files\Git\bin\bash.exe' -lc '<command>'
```

该示例是宿主适配提示，不表示仓库脚本使用 PowerShell。复杂命令仍需按 PowerShell 外层和 Bash 内层分别正确引用。

### CLAUDE.md / Claude Code adapter

使用同名、文件内独立的托管块，声明相同的仓库契约，但适配规则改为：

- 直接使用 Claude Code 的 Bash 工具；
- 不在 Bash 工具里生成 PowerShell `& ...` 包装；
- Git Bash 缺失或不可定位时停止仓库命令并报告诊断；
- 不启用或依赖预览性质的 PowerShell 工具完成项目任务。

同名标记在两个不同文件中不会冲突。脚本仅替换标记内部；标记外内容和 `opsx-init` 块保持字节级不变。文件不存在时创建最小标题和托管块。

## 用户级环境配置

### Codex

合并到 `~/.codex/config.toml`：

```toml
[shell_environment_policy.set]
PYTHONUTF8 = "1"
PYTHONIOENCODING = "utf-8"
```

合并必须保留该表中的其他键。若检测到重复表、非字符串冲突值或无法安全保持现有结构，停止并报告，不重写整个 TOML。

### Claude Code

合并到 `~/.claude/settings.json` 的 `env`：

```json
{
  "env": {
    "CLAUDE_CODE_GIT_BASH_PATH": "C:\\Program Files\\Git\\bin\\bash.exe",
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8"
  }
}
```

JSON 合并保留其他顶层字段与 `env` 键。若已有 `CLAUDE_CODE_GIT_BASH_PATH` 指向另一个存在的 `bash.exe`，保留用户值。若设置了 `CLAUDE_CODE_USE_POWERSHELL_TOOL=1`，诊断给出警告，不擅自删除。

`CLAUDE_CODE_GIT_BASH_PATH` 属于机器配置，不写入仓库的 `.claude/settings.json`。

### ~/.bashrc

`.bashrc` 只服务交互式 Git Bash，不是两个 agent 后台环境的权威来源。本次不自动编辑它；诊断可提示用户补充两个 Python 变量。由于 `bash -lc` 读取 login profile 而不保证读取 `.bashrc`，不能以 `.bashrc` 作为 Codex 正确性的前提。

## Git Bash 定位

按以下顺序确定 `bash.exe`：

1. 已有且有效的 `CLAUDE_CODE_GIT_BASH_PATH`；
2. `C:\Program Files\Git\bin\bash.exe`；
3. `C:\Program Files\Git\usr\bin\bash.exe`；
4. `PATH` 中的 `bash.exe`，但排除明显的 WSL 转发器。

找不到时诊断失败并给出安装 Git for Windows 的提示，不回退为项目 PowerShell 语义。

## 文件格式与脚本验证

- 新增的 `.py`、`.md` 和测试文件使用 UTF-8、LF。
- 现有 `.gitattributes` 模板的 `* text=auto eol=lf` 已覆盖 `.sh`；额外增加 `*.sh text eol=lf` 可把意图写明。
- 任何新增或修改的 `.sh` 必须包含 `#!/usr/bin/env bash` 并通过 `bash -n`。
- 本能力自身不需要新增 shell 脚本，避免仅为包装 `bash.exe` 再引入一层引用问题。

## 错误处理和安全性

- `apply-repo` 幂等：首次插入，重复执行只刷新自己的托管块。
- 发现只有起始或结束标记时停止，避免吞掉用户内容。
- `diagnose` 不写文件，使用非零退出码表示关键条件未满足。
- `configure-user` 必须是独立显式动作；写入前创建同目录备份，并采用临时文件后原子替换。
- 配置解析失败、结构冲突或目标路径不明确时 fail closed，报告人工修复建议。
- 输出不得包含令牌、密钥或无关环境变量值。

## 测试策略

使用 Python 标准库 `unittest` 或仓库已有的 pytest 环境，对临时目录中的真实文件执行测试：

1. 空仓库创建两个 agent 文件和正确适配块。
2. 已有用户内容及 `opsx-init` 块保持不变。
3. 重复执行不产生重复块。
4. 半截托管标记拒绝修改。
5. Codex TOML 表新增、已有键保留、目标值更新、冲突结构拒绝。
6. Claude JSON 深度合并、已有有效 Git Bash 路径保留、无效 JSON 拒绝。
7. Git Bash 路径发现优先级。
8. 诊断在 Python UTF-8 正确和错误时分别返回明确结果。
9. 完整 `project-init` 测试集与仓库相关测试保持通过。

实现遵循测试先行：每个行为先写失败测试并确认失败原因，再加入最小实现。

## SKILL.md 调整

`project-init` 的职责表更新为：

- `opsx-project-init` 拥有 `AGENTS.md`/`CLAUDE.md` 中的 `opsx-init` 块；
- `project-init` 拥有两个文件中的 `project-init:windows-shell` 块；
- 默认执行仓库级应用与只读诊断；
- 用户级写入仅在用户明确要求配置本机环境时执行；
- 完成报告分别列出仓库变更、诊断结果、用户配置变更和仍需人工处理的项目。

## 非目标

- 不支持以 WSL 作为本仓库的规范运行时。
- 不修改 VS Code/Codex 集成终端的 shell 选择。
- 不安装 Git for Windows、Python、Codex 或 Claude Code。
- 不把所有现有 `project-init` 行为重写成统一 CLI。
- 不改变 OpenSpec workflow bundle 或当前 `minimize-repo-footprint` change。

## 完成标准

- 新仓库与已有 OpenSpec 仓库都能安全获得两端专用指令。
- Codex 和 Claude Code 在同一仓库中遵循同一 Bash/POSIX 契约，却采用各自正确的宿主调用方式。
- 两端启动的 Windows Python 均可被诊断为 UTF-8 模式。
- 重复执行不改变结果，用户内容与其他托管块不受影响。
- 用户主目录只有在显式配置动作下才会改变。
