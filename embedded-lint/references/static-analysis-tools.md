# 嵌入式 C 静态分析工具选型指南

> **适用项目**：ML307C / arm-none-eabi 交叉编译 / Windows / scons 构建系统
> **目标**：帮助选择合适的工具组合，而非盲目全部引入

---

## 工具能力对比

三类主流工具找的是**不同类型**的问题，不互相替代：

| 能力维度 | gcc -Wflags | cppcheck | clang-tidy | clang analyzer |
|----------|:-----------:|:--------:|:----------:|:--------------:|
| 整数类型转换（-Wconversion） | ✓✓✓ | ✗ | ✓✓ | ✗ |
| 有符号/无符号比较 | ✓✓✓ | ✗ | ✓✓ | ✗ |
| 空指针解引用（路径敏感） | △ | ✓✓ | ✓ | ✓✓✓ |
| 内存泄漏（含 early-return） | △ | ✓✓ | ✓ | ✓✓✓ |
| 缓冲区溢出 | △ | ✓ | ✓✓ | ✓✓✓ |
| 函数调用链分析 | ✗ | △ | ✓✓ | ✓✓ |
| CERT-C / MISRA 规则 | ✗ | △ | ✓✓✓ | ✗ |
| API 语义误用 | ✗ | △ | ✓✓ | ✓ |
| 未初始化变量 | ✓（-Wall） | ✓ | ✓ | ✓✓ |

---

## 本项目可行性分析

本项目特殊约束：**arm-none-eabi 交叉编译 + Windows + scons**

| 工具 | Windows 可行性 | 配置难度 | 需要 cross-compiler | 适合现阶段 |
|------|:-----------:|:------:|:-----------:|:--------:|
| gcc -Wextra / -Wconversion | ✓✓ 改一行 | 极低 | ✓（已有） | ✓✓✓ |
| cppcheck | ✓✓✓ 独立运行 | 低 | 否 | ✓✓✓ |
| clang-tidy | ✓（CLion 生成 compile_commands.json） | 中 | 需 --extra-arg 模拟 | ✓ 可跟进 |
| clang analyzer (scan-build) | ✗ | 高 | 需大量配置 | ✗ |
| PC-lint / Polyspace | 商业 | 高 | 需配置 | 不建议 |

---

## `-isystem` 前置说明

添加 `-Wconversion` 前必须处理的问题：SCons 把所有 `CPPPATH` 路径都转为 `-I`，
第三方库（cJSON / mbedtls）会产生大量噪音警告，把真实问题淹没。

解决方案：把第三方目录从 `CPPPATH`（`-I` 处理）移至 `CCFLAGS`（`-isystem` 处理）：

```python
# EnvironConfig.py 或 ModuleBuild.py 中
# 第三方路径改用 -isystem（GCC 会完全静默这些路径下的警告）
THIRD_PARTY_SYSTEM_INCS = [
    '../third-party/cJSONFiles/cJSON',
    '../third-party/mbedtls/include',
    '../third-party/mbedtls/include/mbedtls',
]
# 在 CCFLAGS 中添加（而非 CPPPATH）：
# ['-isystem', path] for path in THIRD_PARTY_SYSTEM_INCS
```

效果：
```
-I custom/app/inc              → 产生 -Wconversion 警告（✓ 我们的代码）
-isystem .../cJSONFiles/cJSON  → 完全静默（✓ 第三方噪音消除）
```

---

## 推荐分层引入策略

```
Tier 0（已有）
  gcc -Wall
  已开启，直接生效

Tier 1（改一行 EnvironConfig.py + -isystem 前置处理）
  gcc -Wextra -Wconversion -Wsign-compare
  ──────────────────────────────────────────────────
  抓到：uint8_t/uint16_t 隐式提升、有符号/无符号比较、窄化赋值
  前置：先把第三方 include 改为 -isystem（否则噪音太多）
  成本：低（纯构建配置修改）

Tier 2（独立工具，10 分钟安装即用）
  cppcheck --enable=warning,error --std=c11 custom/
  ──────────────────────────────────────────────────
  抓到：内存泄漏路径、null 解引用路径、缓冲区越界
  补充 gcc 的盲区（gcc 不做路径分析）
  无需 cross-compiler，直接扫 custom/ 源码
  可封装为 Claude Code skill（/embedded-lint）

Tier 3（通过 CLion 生成 compile_commands.json 解锁）
  clang-tidy（bugprone + cert-int + clang-analyzer-core）
  ──────────────────────────────────────────────────
  抓到：宏参数缺括号、sizeof 误用、无符号回绕、符号转换
        路径敏感 null 解引用（比 cppcheck 更深）
  前提：CLion 生成 compile_commands.json（见下文）
  注意：需要 --extra-arg=--target=arm-none-eabi 处理交叉编译
```

---

## cppcheck 快速上手

### 安装（Windows）

```bash
# 方式 A：scoop
scoop install cppcheck

# 方式 B：官网下载安装包
# https://cppcheck.sourceforge.io/

# 验证
cppcheck --version
```

### 扫描命令

```bash
# 基础扫描（custom/ 目录，c11 标准）
cppcheck --enable=all --std=c11 \
  -I custom/inc -I custom/app/inc -I custom/sys_app/inc \
  custom/

# 只显示 error 和 warning（过滤 style/performance 噪音）
cppcheck --enable=warning,error --std=c11 custom/

# 输出到文件（便于 agent 分析）
cppcheck --enable=all --std=c11 custom/ 2> cppcheck_report.txt
```

### 结果解读

cppcheck 输出格式：`文件:行号: 级别: 消息 [规则ID]`

| 级别 | 含义 | 建议处理 |
|------|------|---------|
| `error` | 确定性 bug（null 解引用、内存泄漏） | 必须修复 |
| `warning` | 可能的 bug（uninit 变量、函数不匹配） | 优先查看 |
| `style` | 代码风格问题 | 可忽略 |
| `performance` | 性能建议 | 可忽略 |
| `information` | 信息性提示 | 可忽略 |

---

## 与 Code Review Checklist 的映射

| Checklist 维度 | 最有效的工具 |
|--------------|------------|
| 整数类型安全 | gcc -Wconversion -Wsign-compare |
| Volatile 正确性 | 人工检查（工具支持弱） |
| 内存分配失败（NULL）处理 | cppcheck (nullPointer) |
| 内存泄漏（early-return） | cppcheck (memleak) |
| 缓冲区溢出 | cppcheck (bufferAccessOutOfBounds) |
| 未初始化变量 | gcc -Wuninitialized（-Wall 已包含） |
| 受限回调上下文违规 | 人工检查（工具不理解业务语义） |
| 递归函数 | cppcheck (infiniteRecursion) |
| 函数返回值忽略 | gcc -Wunused-result / clang-tidy |

---

## clang-tidy 详解

### 检查族分类

clang-tidy 的规则按"族"组织，对这个项目的价值不同：

| 检查族 | 代表规则 | 对本项目价值 |
|--------|---------|------------|
| `bugprone-*` | sizeof-expression、macro-parentheses、integer-division | ✓✓✓ 高 |
| `cert-int*` | cert-int30-c（无符号回绕）、cert-int31-c（符号转换） | ✓✓✓ 高 |
| `clang-analyzer-core.*` | NullDereference、uninitialized.Assign | ✓✓ 中高 |
| `cert-err33-c` | stdlib 函数返回值未检查 | ✓ 中（部分适用） |
| `misc-misplaced-const` | const char* 与 char* const 混淆 | ✓ 中 |
| `clang-analyzer-unix.Malloc` | malloc/free 对 | ✗ 跳过（项目用 cm_calloc） |
| `readability-*` | 代码风格 | ✗ 跳过 |
| `modernize-*` | C++ 现代化 | ✗ 跳过（C 项目） |

**最有价值的具体规则**：

```
bugprone-sizeof-expression
  → 抓 sizeof(ptr) 误用（常见嵌入式 bug：memset(buf, 0, sizeof(buf))
    当 buf 是指针而非数组时，sizeof 返回指针大小而非缓冲区大小）

bugprone-macro-parentheses
  → 抓 #define MAX(a,b) a>b?a:b 缺括号
    应写 ((a)>(b)?(a):(b))

cert-int30-c
  → 抓无符号整数回绕：uint8_t x = 0; x--;  → x 变成 255
  → uint8_t count; if(--count > 0) 的循环终止条件陷阱

cert-int31-c
  → 抓符号/无符号转换：int len = strlen(buf);（size_t 赋给 int）
  → 类似 gcc -Wsign-compare 但更精确

clang-analyzer-core.NullDereference
  → 路径敏感分析：追踪"在某条路径上指针可能为 NULL 但未检查就解引用"
  → 比 cppcheck 的 nullPointer 检查更深，能跨函数追踪
```

### 交叉编译适应性

项目分三层，clang-tidy 的适应性不同：

```
应用层 custom/app/src/*.c        ← 完全适合，无平台扩展
系统层 custom/sys_app/src/*.c    ← 基本适合，少量 __attribute__ 需忽略
SDK 头 include/cmiot/*.h         ← 用 -isystem 隔离，不扫描
第三方 third-party/              ← 排除扫描
```

**结论：只扫 `custom/` 层，适应性很好。**

### 通过 CLion 生成 compile_commands.json

CLion（已用于此项目，`.idea/` 已存在）通过**构建拦截**生成 compile_commands.json：

```
操作路径：Tools → Compilation Database → Generate a Compilation Database

原理：
  scons 构建 ──► arm-none-eabi-gcc -std=gnu11 -Wall -I... -c task_lora.c
                          ↓ CLion 构建拦截器监听所有 gcc 调用
               compile_commands.json（保存在项目根目录）
               { "file": "custom/app/src/task_lora.c",
                 "command": "arm-none-eabi-gcc -std=gnu11 ...",
                 "directory": "D:/20-Projects/4g/smartrelay-4g" }
```

生成成功后，clang-tidy 就可以读取它了。

### clang-tidy 调用方式

生成 compile_commands.json 后，运行方式：

```bash
# 扫描单个文件（推荐先试单文件）
clang-tidy \
  -checks='bugprone-sizeof-expression,bugprone-macro-parentheses,cert-int30-c,cert-int31-c,clang-analyzer-core.NullDereference' \
  --extra-arg=--target=arm-none-eabi \
  --extra-arg=-D__GNUC__ \
  -p compile_commands.json \
  custom/app/src/task_lora.c

# 扫描全部 custom/（排除第三方和 SDK）
clang-tidy \
  -checks='bugprone-*,cert-int*,clang-analyzer-core.*' \
  --extra-arg=--target=arm-none-eabi \
  --extra-arg=-D__GNUC__ \
  -p compile_commands.json \
  custom/app/src/*.c custom/sys_app/src/*.c
```

**`--extra-arg` 说明**：
- `--target=arm-none-eabi`：告诉 Clang 前端按 ARM 架构解析，避免 ARM 类型宽度误判
- `-D__GNUC__`：让代码中 `#ifdef __GNUC__` 分支被正确展开（部分 SDK 宏依赖此定义）

### 固化配置：`.clang-tidy` 文件

可在项目根目录放置 `.clang-tidy`，运行时自动读取，无需每次传命令行参数：

```yaml
# .clang-tidy（放在项目根目录）
# 阶段 1：稳定、误报极少的检查
Checks: >
  bugprone-sizeof-expression,
  bugprone-macro-parentheses,
  bugprone-integer-division,
  bugprone-suspicious-memset-usage,
  cert-int30-c,
  cert-int31-c,
  misc-misplaced-const,
  -clang-analyzer-unix.Malloc

# 阶段 2（待 Tier 1 稳定后取消注释）：
# clang-analyzer-core.NullDereference,
# clang-analyzer-core.uninitialized.Assign,

ExtraArgs:
  - --target=arm-none-eabi
  - -D__GNUC__

# 排除第三方和 SDK（这些路径的文件不报告警告）
HeaderFilterRegex: 'custom/.*'
```

### 分阶段启用

```
阶段 1（CLion 生成 compile_commands.json 后立即可做）
  bugprone-sizeof-expression        sizeof(ptr) 误用
  bugprone-macro-parentheses        宏参数缺括号
  cert-int30-c                      无符号回绕
  cert-int31-c                      符号/无符号转换
  ────────────────────────────────────────────────
  这些规则不依赖 ARM 平台知识，Clang 前端完全能处理，误报极少

阶段 2（确认阶段 1 稳定后）
  clang-analyzer-core.NullDereference      路径敏感 null 追踪
  clang-analyzer-core.uninitialized.Assign 未初始化赋值
  ────────────────────────────────────────────────
  路径敏感分析更强，偶尔对 SDK 宏展开产生误报，需人工确认

永久跳过
  clang-analyzer-unix.Malloc  项目用 cm_calloc，不用标准 malloc，全是误报
  readability-*, modernize-*  不适用（C 项目，非代码风格清理阶段）
```
