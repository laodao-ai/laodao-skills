# ssh-tunnel skill — SSH 本地端口转发隧道管理

## 这个 Skill 是什么

**ssh-tunnel skill** 是一个 SSH 本地端口转发（`ssh -L`）的配置生成和管理助手。它帮你在任意项目中快速建立"本地端口 → 跳板机 → 内网服务"的安全通道，让开发环境可以访问只对内网开放的数据库、缓存或 API。

**核心价值**：一次配置，长期复用；引导信息收集，生成即可用的脚本。

SSH 隧道命令本身不难，但每次都要记跳板机 IP、内网地址、端口、认证方式，拼出一长串命令，还得自己管 PID 才能停掉。Skill 的核心价值在于把这些信息收集起来，生成结构清晰的实例脚本，存到项目 `hack/` 目录后，以后只需 `bash hack/pg-tunnel.sh start/stop/status` 三个命令搞定一切。

设计遵循"引擎与实例分离"模式：通用的启停逻辑（引擎）和具体的连接参数（实例配置）彻底拆开，多个隧道共享同一份引擎，各自独立管理。Skill 内置引擎脚本，按需复制到项目，不依赖外部安装。

---

## 解决什么问题

开发时访问内网服务（数据库、Redis、内部 API）是日常操作，但往往需要通过跳板机做端口转发。每次手敲 SSH 命令繁琐且容易出错：

```bash
# 每次都要记住这一长串
ssh -i ~/.ssh/key.pem -p 22 -N \
  -L 5432:172.16.0.100:5432 \
  -o StrictHostKeyChecking=accept-new \
  -o ServerAliveInterval=30 \
  root@47.x.x.x &
```

命令打完还要记 PID 才能停掉，或者杀错进程。换个项目、换台机器，又要重新配置一遍。

**痛点**：
- SSH 隧道命令长、难记、容易打错
- 多个隧道同时运行时管理混乱（如何停掉特定的那个？）
- 每个项目的配置散落在各处，没有统一管理
- 新人加入项目，不知道怎么配本地开发环境

---

## 设计思路与关键决策

### 决策一：两层分离——引擎与实例配置

核心设计是把"通用逻辑"和"项目配置"彻底分开：

- **`ssh-tunnel.sh`（引擎）**：处理 start/stop/status 全部逻辑，所有项目共用同一份
- **`<服务名>-tunnel.sh`（实例）**：只有几行环境变量，描述"这个隧道连哪里"

好处是实例文件极简（10 行左右），新人看一眼就明白这个隧道是连什么的；引擎文件则由 skill 统一维护，bug 修复只需更新一处。

### 决策二：以 LOCAL_PORT 作为隧道标识

PID 文件命名为 `/tmp/ssh-tunnel-<LOCAL_PORT>.pid`，stop/status 只需要知道端口号就能找到对应进程。这样多个隧道同时运行时互不干扰——你可以同时开 PostgreSQL（5432）、Redis（6379）、MySQL（3306）三条隧道，各自独立管理。

### 决策三：引擎打包进 skill，按需复制到项目

Skill 内置完整的引擎脚本。第一次在某个项目里用 ssh-tunnel skill 时，Claude 会把引擎复制到项目的 `hack/` 目录。后续在同一项目添加新隧道，复用已有引擎，不重复复制。

这样既实现了跨项目通用（引擎集中管理），又保持了各项目的自包含性（项目目录下有完整脚本，不依赖全局路径）。

### 决策四：实例配置加入 .gitignore

隧道配置文件包含跳板机 IP、私钥路径等敏感或环境相关信息，不应该提交到 git。Skill 会自动检查并提示（或帮你）把 `hack/*-tunnel.sh` 加入 `.gitignore`。

---

## 功能一览

| 功能 | 说明 |
|------|------|
| 生成实例配置文件 | 根据用户提供的参数，生成 `hack/<服务名>-tunnel.sh` |
| 复制引擎脚本 | 自动把 `ssh-tunnel.sh` 复制到项目 `hack/` 目录 |
| 证书 / 密码双模式 | 支持私钥文件（推荐）或 sshpass 密码认证 |
| 多隧道并发 | 每条隧道用不同 LOCAL_PORT，互不干扰 |
| 启动（后台运行） | `bash hack/<服务名>-tunnel.sh start` |
| 停止 | `bash hack/<服务名>-tunnel.sh stop` |
| 状态检查 | 端口监听检测 + PID 验证 + SSH 进程查找 |
| .gitignore 提示 | 自动检测并提示保护敏感配置 |
| 常见服务端口提示 | PG/Redis/MySQL/MongoDB 等默认端口参考 |

---

## 如何使用

### 触发方式

在任意项目目录里，对 Claude 说：

```
帮我建个连数据库的 SSH 隧道
我需要访问内网的 Redis，通过跳板机
建个 pg-tunnel，连 172.16.0.100:5432，跳板机是 47.x.x.x
/ssh-tunnel
```

### 典型对话流程

```
用户：帮我建一个连 PostgreSQL 的隧道，跳板机是 47.116.21.17，
      目标是 172.16.0.100:5432，用私钥 ~/.ssh/prod.pem

Claude：
  好的，以下是配置信息：

  本地端口：5432（PostgreSQL 默认）
  跳板机：root@47.116.21.17:22
  目标：172.16.0.100:5432
  认证：私钥 ~/.ssh/prod.pem

  将生成 hack/pg-tunnel.sh，确认吗？

用户：确认

Claude：
  ✓ 已复制引擎：hack/ssh-tunnel.sh
  ✓ 已生成配置：hack/pg-tunnel.sh
  ✓ 已将 hack/*-tunnel.sh 加入 .gitignore

  使用方式：
    启动：bash hack/pg-tunnel.sh start
    停止：bash hack/pg-tunnel.sh stop
    状态：bash hack/pg-tunnel.sh status
```

### 生成的实例文件示例

```bash
#!/usr/bin/env bash
# 隧道实例：PostgreSQL
#   localhost:5432 → root@47.116.21.17:22 → 172.16.0.100:5432

export LOCAL_PORT="5432"
export JUMP_HOST="47.116.21.17"
export JUMP_PORT="22"
export SSH_USER="root"
export REMOTE_HOST="172.16.0.100"
export REMOTE_PORT="5432"

export SSH_KEY_FILE="$HOME/.ssh/prod.pem"
# export SSH_PASSWORD="your_password"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export TUNNEL_SCRIPT="${BASH_SOURCE[0]}"
exec bash "${SCRIPT_DIR}/ssh-tunnel.sh" "$@"
```

### 同时运行多个隧道

```bash
bash hack/pg-tunnel.sh start      # PostgreSQL on :5432
bash hack/redis-tunnel.sh start   # Redis on :6379

# 各自独立管理
bash hack/pg-tunnel.sh status
bash hack/redis-tunnel.sh stop
```

---

## 注意事项与限制

### 密码模式需要 sshpass

密码认证依赖 `sshpass` 工具：
- Ubuntu/Debian：`sudo apt install sshpass`
- macOS：`brew install sshpass`
- Windows Git Bash：通常已内置，否则需要单独安装

证书模式（推荐）无此依赖。

### 首次连接需要确认 SSH 指纹

引擎使用了 `-o StrictHostKeyChecking=accept-new`，首次连接会自动接受跳板机指纹并记录到 `~/.ssh/known_hosts`，后续不再询问。如果跳板机 IP 更换了（指纹变了），可能需要手动清除旧记录：

```bash
ssh-keygen -R <跳板机IP>
```

### Windows 环境的端口检测

`status` 命令的端口监听检测优先使用 `ss`（Linux），回退到 `lsof`，再回退到 `netstat`（Windows）。在 Windows Git Bash 环境下，`ss` 通常不可用，会使用 `netstat`，兼容性良好但输出格式稍有不同。

### 私钥路径在 Windows 下的写法

在 Windows 环境，私钥路径可以用正斜杠或双反斜杠，bash 脚本中均能识别：

```bash
# 以下写法均可
export SSH_KEY_FILE="D:/keys/prod.pem"
export SSH_KEY_FILE="D:\\keys\\prod.pem"
export SSH_KEY_FILE="$HOME/.ssh/prod.pem"
```

### 隧道会在终端关闭后继续运行

`start` 命令让隧道在后台运行（`&` + PID 文件），关闭终端窗口不会停止隧道。需要停止时必须显式执行 `stop`，或者重启系统。

### LOCAL_PORT 冲突

如果你在两个项目中都建了连接同一端口的隧道（比如都用 5432 连 PG），它们不能同时运行。选择不同的 `LOCAL_PORT` 来规避冲突（如一个用 5432，另一个用 15432）。

---

## 优势与劣势评价

### 优势

- **一次配置，长期使用**：生成的实例文件永久保存在项目里，团队成员克隆仓库后只需补充自己的私钥路径即可（引擎会被提交，实例文件被 gitignore）
- **多隧道并发，互不干扰**：基于端口号的 PID 管理让多条隧道可以独立控制
- **引擎功能完整**：start/stop/status 三个命令覆盖日常所需，状态检查跨平台兼容（Linux/macOS/Windows）
- **跨项目通用**：任何项目都能用，不限框架或语言
- **配置即文档**：实例文件顶部的注释清晰描述了隧道路由，新人看一眼就懂

### 劣势

- **不支持多跳跳板机**：目前只支持一层跳板机。如果网络架构是"本地 → 跳板A → 跳板B → 目标"，需要手动配置 ProxyJump，skill 暂不支持
- **无自动重连**：如果隧道因网络中断而断开，不会自动重连（`ServerAliveCountMax=3` 超时后进程退出，需要手动 restart）。生产环境建议用 autossh 替代
- **Windows 下 pgrep 不可用**：`status` 命令中的 SSH 进程搜索功能在 Windows 上受限，只能显示 PID 是否存活，无法展示完整的 ssh 进程命令行
- **敏感信息在文件中**：虽然加了 `.gitignore`，私钥路径和 IP 仍以明文存在本地文件中。对安全要求极高的场景，应该考虑用环境变量或密钥管理工具

### 与直接写 ssh 命令相比

| | 裸 ssh 命令 | ssh-tunnel skill |
|---|---|---|
| 启动命令长度 | 一长串，难记 | `bash hack/xx-tunnel.sh start` |
| 停止方式 | 记 PID 或 pkill | `bash hack/xx-tunnel.sh stop` |
| 多隧道管理 | 混乱 | 各自独立 PID 文件 |
| 团队共享配置 | 靠文档 / 口口相传 | 实例文件即配置 |
| 首次配置成本 | 低（直接敲） | 需要 Claude 引导生成 |
