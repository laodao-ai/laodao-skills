---
name: embedded-lint
description: |
  对嵌入式 C 项目（ML307C / arm-none-eabi）运行静态分析，输出按代码审查清单分类的
  问题报告，并自动保存到当前活跃变更目录。自动检测可用工具，按 Tier 优先级选择：
    Tier 2: cppcheck（无需 cross-compiler，独立安装）
    Tier 3: clang-tidy（需要 compile_commands.json，由 CLion 生成）
  用法：/embedded-lint [路径或模块名]，例如：
    /embedded-lint                       → 扫描全部 custom/
    /embedded-lint app/src/task_lora.c   → 扫描单个文件
    /embedded-lint sys_app/src           → 扫描子目录
  工具选型参考：openspec/docs/static-analysis-tools.md
---

# embedded-lint：嵌入式静态分析 Skill

## 工作流程

### 第一步：确定扫描目标

从用户输入解析扫描路径：
- 无参数 → 扫描 `custom/`
- 文件路径 → 扫描指定文件
- 目录名（如 `app/src`）→ 扫描 `custom/<目录名>`
- 模块名（如 `task_lora`）→ 在 `custom/` 下查找匹配文件

### 第二步：检测可用工具，选择扫描路径

```bash
cd D:/20-Projects/4g/smartrelay-4g

# 检测 clang-tidy + compile_commands.json（Tier 3）
clang-tidy --version 2>/dev/null && echo "CLANGTIDY_OK" || echo "CLANGTIDY_MISSING"
test -f compile_commands.json && echo "COMPILE_DB_OK" || echo "COMPILE_DB_MISSING"

# 检测 cppcheck（Tier 2）
cppcheck --version 2>/dev/null && echo "CPPCHECK_OK" || echo "CPPCHECK_MISSING"
```

**工具选择逻辑**：

```
clang-tidy 可用 AND compile_commands.json 存在
  → Tier 3 路径：运行 clang-tidy（更深的分析）
  → 可选：同时跑 cppcheck 补充 null/leak 检查

只有 cppcheck 可用
  → Tier 2 路径：运行 cppcheck

两者都不可用
  → 提示安装，并做基础编译警告分析
```

**安装提示（若工具缺失）**：

```
cppcheck 未安装：
  scoop install cppcheck   或   winget install Cppcheck.Cppcheck

clang-tidy 未安装：
  scoop install llvm       （包含 clang-tidy）
  安装后验证：clang-tidy --version

compile_commands.json 未生成：
  在 CLion 中：Tools → Compilation Database → Generate a Compilation Database
  生成成功后文件位于项目根目录
  详见：openspec/docs/static-analysis-tools.md §CLion 生成章节
```

### 第三步 B：运行 clang-tidy（Tier 3，compile_commands.json 已存在时）

```bash
cd D:/20-Projects/4g/smartrelay-4g

# 单文件（先验证配置正确）
clang-tidy \
  -checks='bugprone-sizeof-expression,bugprone-macro-parentheses,bugprone-integer-division,cert-int30-c,cert-int31-c,clang-analyzer-core.NullDereference,clang-analyzer-core.uninitialized.Assign' \
  --extra-arg=--target=arm-none-eabi \
  --extra-arg=-D__GNUC__ \
  -p compile_commands.json \
  <扫描目标文件>

# 批量扫描（排除 clang-analyzer-unix.Malloc，因项目用 cm_calloc 非 malloc）
clang-tidy \
  -checks='bugprone-*,cert-int*,clang-analyzer-core.*,-clang-analyzer-unix.Malloc' \
  --extra-arg=--target=arm-none-eabi \
  --extra-arg=-D__GNUC__ \
  -p compile_commands.json \
  custom/app/src/*.c custom/sys_app/src/*.c 2>&1
```

**分类映射**：
```
bugprone-sizeof-expression           → 缓冲区安全
bugprone-macro-parentheses           → 宏安全（代码质量）
cert-int30-c                         → 整数安全（无符号回绕）
cert-int31-c                         → 整数安全（符号/无符号转换）
clang-analyzer-core.NullDereference  → 内存分配 NULL 处理
clang-analyzer-core.uninitialized.*  → 未初始化变量
```

---

### 第三步 A：运行 cppcheck（Tier 2 路径）

```bash
cd D:/20-Projects/4g/smartrelay-4g

# 基础扫描，输出到 stderr（便于捕获）
cppcheck \
  --enable=warning,style \
  --std=c11 \
  --suppress=missingIncludeSystem \
  -I custom/inc \
  -I custom/app/inc \
  -I custom/sys_app/inc \
  -I custom/sys_app/ops_channel/inc \
  -I custom/sys_app/data_channel/inc \
  -I custom/sys_app/config/inc \
  -I custom/sys_app/log/inc \
  -I custom/sys_app/gpio/inc \
  -I custom/sys_app/adapter/inc \
  -I custom/sys_app/network/inc \
  -I custom/sys_app/data_pack/inc \
  -I custom/sys_app/uart/inc \
  -I custom/utils/inc \
  <扫描目标路径> \
  2>&1
```

> 注意：`--suppress=missingIncludeSystem` 压制"找不到系统头文件"的误报
>（因为 SDK 头文件在 include/ 下，不在标准路径中）

### 第四步：解析输出并分类

cppcheck 输出格式：`文件:行:列: 级别: 消息 [规则ID]`

将发现的问题按**代码审查清单维度**分类输出：

```
分类映射：
  nullPointer, nullPointerRedundantCheck → 内存分配失败处理（§2）
  memleak, resourceLeak                  → 内存泄漏（§2）
  uninitvar, uninitStructMember          → 未初始化变量（§5 线程安全）
  bufferAccessOutOfBounds, arrayIndexOutOfBounds → 缓冲区安全（通用）
  infiniteRecursion                      → 递归禁止（§栈深度）
  unusedReturnValue                      → 错误路径（§8 错误处理）
  其他 error/warning                     → 其他问题
```

### 第五步：输出报告

输出格式：

```
## embedded-lint 报告
扫描目标：<路径>
工具：cppcheck <版本>
日期：<YYYY-MM-DD>
发现：<error数> 个错误，<warning数> 个警告，<style数> 个 style

---

### 🔴 逻辑 Bug（必须修复）
[按文件:行号分组]

### 🟡 警告（建议修复）
[按文件:行号分组]

### ℹ️ Style（可选）
[按文件:行号分组，仅列代表性条目]

---

### 对照代码审查清单
| 清单维度 | 发现数 | 代表问题 |
|---------|-------|---------|
| 内存分配 NULL 处理 | N | ... |
| 内存泄漏路径 | N | ... |
| ...    |   |   |

---

### 下一步建议
- [具体可操作的修复建议，按优先级排列]
```

---

### 第六步：保存报告到 change 目录

**检测活跃变更**：

```bash
cd D:/20-Projects/4g/smartrelay-4g
# 列出 openspec/changes/ 下的子目录，排除 archive
ls openspec/changes/ | grep -v "^archive$"
```

**保存路径选择逻辑**：

```
发现 1 个活跃变更目录
  → 保存到 openspec/changes/<name>/lint-report.md

发现多个活跃变更目录
  → 保存到最近修改的那个（按 mtime）
  → 报告头部注明："本报告关联变更：<name>"

openspec/changes/ 下无活跃变更（仅有 archive/）
  → 保存到 openspec/lint-reports/lint-<YYYYMMDD>.md
  → 若该目录不存在则先创建

```

使用 **Write 工具**将完整报告写入目标路径。

写入后告知用户：

```
报告已保存至：openspec/changes/<name>/lint-report.md
```

---

## 当 cppcheck 未安装时的替代分析

若 cppcheck 不可用，可以做**编译警告分析**：

```bash
cd D:/20-Projects/4g/smartrelay-4g

# 查看上次编译产生的警告（若有构建日志）
# 或提示用户手动运行：
scons 2>&1 | grep -E "warning:|error:" | head -50
```

同时告知用户：编译器警告只覆盖部分问题（整数类型、未使用变量等），
路径敏感问题（内存泄漏、null 解引用链路）需要 cppcheck 才能检测。

---

## 局限性说明

每次运行结束时，附加说明：

```
【静态工具盲区 → 运行 /review 补充语义检查】
以下项目 cppcheck/clang-tidy 无法检测，但 LLM 代码审查可以覆盖：

- §1 受限回调上下文  → /review 检查 osTimerNew 回调调用链
                        是否含 LOG_* / cm_calloc / osMutexAcquire / osDelay
- §5 线程初始化顺序  → /review 检查 initialized 标志是否在 osThreadNew 之前置 true
- §6 Volatile 正确性 → /review 检查 ISR/timer 与普通线程间共享变量的 volatile 修饰

运行方式：/review <文件或模块>
审查清单：openspec/docs/code-review-checklist.md（ML307C 专属）
          openspec/docs/code-review-checklist-embedded.md（通用嵌入式）
```
