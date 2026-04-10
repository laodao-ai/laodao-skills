---
name: ssh-tunnel
description: >
  在任意项目中创建和管理 SSH 本地端口转发隧道（ssh -L），支持跳板机跳转、证书/密码认证。
  帮用户生成隧道实例配置脚本，复制通用引擎到项目 hack/ 目录，并提供启动/停止/状态命令。
  当用户说"建个 SSH 隧道"、"连数据库"、"端口转发"、"打通内网"、"访问远端服务"、
  "连 Redis/PG/MySQL/内网服务"、"ssh -L"、"跳板机"、"tunnel"，或 /ssh-tunnel 时，必须触发此 skill。
---

# SSH Tunnel Skill

> **推荐模型**：本 skill 属于参数收集 + 模板生成类任务，使用 **Haiku** 即可，速度更快、成本更低。
> Skill 本身无法指定模型，请在触发前用 `/model` 切换到 Haiku。

## 设计理念

**两层分离**：
- `ssh-tunnel.sh`：通用引擎，处理启动/停止/状态逻辑，所有项目共用
- `<服务名>-tunnel.sh`：实例配置，只存环境变量，每个隧道一个文件

这样多个隧道可以同时运行，配置清晰，且实例文件可以加入 `.gitignore` 保护敏感信息。

## Skill 内置文件

```
~/.claude/skills/ssh-tunnel/scripts/
├── ssh-tunnel.sh       # 通用引擎（直接复制到项目）
└── tunnel.example.sh  # 实例配置模板
```

---

## 工作流程

### 第一步：了解用户需求

询问（或从上下文推断）：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| 服务名称 | 如 pg、redis、mysql（用于命名文件） | 必填 |
| 跳板机地址 | `JUMP_HOST` | 必填 |
| 跳板机端口 | `JUMP_PORT` | 22 |
| 跳板机用户 | `SSH_USER` | root |
| 本地端口 | `LOCAL_PORT` | 服务默认端口 |
| 目标内网地址 | `REMOTE_HOST` | 必填 |
| 目标内网端口 | `REMOTE_PORT` | 同 LOCAL_PORT |
| 认证方式 | 私钥路径 或 密码 | 必填 |

如果用户只说"帮我连数据库"而没有提供参数，先问清楚再继续。已知参数直接用，不要反复确认。

**常见服务默认端口参考**：

| 服务 | 端口 |
|------|------|
| PostgreSQL | 5432 |
| PgBouncer | 6432 |
| MySQL / MariaDB | 3306 |
| Redis | 6379 |
| MongoDB | 27017 |
| HTTP | 80 / 8080 |
| HTTPS | 443 |

### 第二步：确定目标目录

优先把文件放在项目的 `hack/` 目录（这是既有约定）。如果当前目录没有 `hack/`，询问用户想放哪里，或直接放当前目录。

```bash
# 检查当前项目是否有 hack/ 目录
ls hack/ 2>/dev/null && echo "有 hack 目录" || echo "无 hack 目录"
```

### 第三步：复制引擎脚本（如果目标目录还没有）

```bash
# 检查引擎是否已存在
if [[ ! -f hack/ssh-tunnel.sh ]]; then
    cp ~/.claude/skills/ssh-tunnel/scripts/ssh-tunnel.sh hack/ssh-tunnel.sh
    chmod +x hack/ssh-tunnel.sh
    echo "已复制引擎：hack/ssh-tunnel.sh"
fi
```

### 第四步：生成实例配置文件

根据用户提供的参数，生成 `hack/<服务名>-tunnel.sh`：

```bash
# 示例：根据用户参数生成文件
cat > hack/pg-tunnel.sh << 'EOF'
#!/usr/bin/env bash
# 隧道实例：PostgreSQL
#   localhost:5432 → root@47.x.x.x:22 → 172.16.0.100:5432

export LOCAL_PORT="5432"
export JUMP_HOST="47.x.x.x"
export JUMP_PORT="22"
export SSH_USER="root"
export REMOTE_HOST="172.16.0.100"
export REMOTE_PORT="5432"

# 认证：取消注释其中一行
export SSH_KEY_FILE="$HOME/.ssh/id_ed25519"
# export SSH_PASSWORD="your_password"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export TUNNEL_SCRIPT="${BASH_SOURCE[0]}"
exec bash "${SCRIPT_DIR}/ssh-tunnel.sh" "$@"
EOF
chmod +x hack/pg-tunnel.sh
```

文件命名规则：`hack/<服务名>-tunnel.sh`（小写，用连字符）

### 第五步：提示 .gitignore

隧道配置文件包含 IP 地址和密钥路径，建议加入 `.gitignore`：

```bash
# 检查 .gitignore 是否已包含
if [[ -f .gitignore ]] && grep -q '\*-tunnel.sh' .gitignore; then
    echo ".gitignore 已包含 *-tunnel.sh"
else
    echo ""
    echo "建议将以下规则加入 .gitignore（隧道配置含敏感信息）："
    echo "  hack/*-tunnel.sh"
fi
```

如果用户同意，自动添加：
```bash
echo "hack/*-tunnel.sh" >> .gitignore
```

### 第六步：告知使用命令

```
隧道已配置完成！

启动：bash hack/pg-tunnel.sh start
停止：bash hack/pg-tunnel.sh stop
状态：bash hack/pg-tunnel.sh status

首次启动会提示 SSH 指纹确认，输入 yes 接受即可。
```

---

## 其他操作

### 查看/停止当前运行的隧道

```bash
bash hack/<服务名>-tunnel.sh status
bash hack/<服务名>-tunnel.sh stop
```

### 同时运行多个隧道

每个实例使用不同的 `LOCAL_PORT`，PID 文件以端口号区分（`/tmp/ssh-tunnel-<PORT>.pid`），互不干扰。

### 密码模式

密码模式需要 `sshpass`：
- Ubuntu/Debian：`sudo apt install sshpass`
- macOS：`brew install sshpass`
- Windows Git Bash：通常内置

---

## 注意事项

- 私钥路径在 Windows 下使用正斜杠或双反斜杠均可（bash 脚本中均支持）
- 如果端口被占用，`start` 会报错并提示先 `stop`
- `ssh-tunnel.sh` 引擎可以被多个实例共享，无需重复复制
- 实例文件（`*-tunnel.sh`）包含 IP 和密钥路径，应加入 `.gitignore`
