#!/usr/bin/env bash
# 隧道实例模板 —— 由 ssh-tunnel skill 生成，复制到项目 hack/ 目录后按需修改
#
# 用法：
#   bash hack/<服务名>-tunnel.sh start    # 启动隧道（后台运行）
#   bash hack/<服务名>-tunnel.sh stop     # 停止隧道
#   bash hack/<服务名>-tunnel.sh status   # 查看状态

# ── 连接参数 ──────────────────────────────────────────────────
export LOCAL_PORT="__LOCAL_PORT__"        # 本地监听端口
export JUMP_HOST="__JUMP_HOST__"          # 跳板机地址
export JUMP_PORT="__JUMP_PORT__"          # 跳板机 SSH 端口（默认 22）
export SSH_USER="__SSH_USER__"            # 跳板机登录用户（默认 root）
export REMOTE_HOST="__REMOTE_HOST__"      # 目标内网地址
export REMOTE_PORT="__REMOTE_PORT__"      # 目标内网端口

# ── 认证：取消注释其中一行 ────────────────────────────────────
export SSH_KEY_FILE="__SSH_KEY_FILE__"
# export SSH_PASSWORD="your_password"

# ── 启动引擎（无需修改）──────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export TUNNEL_SCRIPT="${BASH_SOURCE[0]}"
exec bash "${SCRIPT_DIR}/ssh-tunnel.sh" "$@"
