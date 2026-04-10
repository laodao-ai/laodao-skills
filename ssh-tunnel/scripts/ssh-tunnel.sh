#!/usr/bin/env bash
# SSH 本地端口转发隧道
#
# 所有参数均通过环境变量配置，支持同时运行多个实例：
#
#   JUMP_HOST      跳板机地址         （启动时必填）
#   JUMP_PORT      跳板机 SSH 端口    （默认 22）
#   SSH_USER       跳板机登录用户     （默认 root）
#   LOCAL_PORT     本地监听端口       （默认 6432）
#   REMOTE_HOST    目标内网地址       （启动时必填）
#   REMOTE_PORT    目标内网端口       （默认同 LOCAL_PORT）
#
# 认证模式（二选一，证书优先，启动时必填）：
#   SSH_KEY_FILE   私钥路径 → 证书模式
#   SSH_PASSWORD   登录密码 → 密码模式（需安装 sshpass）
#
# Usage:
#   ./hack/ssh-tunnel.sh start        # 启动隧道（后台运行）
#   ./hack/ssh-tunnel.sh stop         # 停止隧道（仅需 LOCAL_PORT）
#   ./hack/ssh-tunnel.sh status       # 查看隧道状态（仅需 LOCAL_PORT）

set -euo pipefail

LOCAL_PORT="${LOCAL_PORT:-6432}"       # 本地监听端口（stop/status 只需要这个）
PID_FILE="/tmp/ssh-tunnel-${LOCAL_PORT}.pid"

# ── 停止后台隧道（不需要认证参数）────────────────────────────
stop_tunnel() {
    if [[ -f "$PID_FILE" ]]; then
        local pid
        pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "停止隧道 (PID: $pid, 本地端口: $LOCAL_PORT)..."
            kill "$pid"
        else
            echo "隧道进程不存在 (PID: $pid 已退出)"
        fi
        rm -f "$PID_FILE"
    else
        echo "未找到运行中的隧道 (${PID_FILE} 不存在)"
    fi
}

# ── 查看隧道状态（不需要认证参数）────────────────────────────
status_tunnel() {
    local jump_host="${JUMP_HOST:-?}"
    local jump_port="${JUMP_PORT:-22}"
    local jump_user="${SSH_USER:-root}"
    local remote_host="${REMOTE_HOST:-?}"
    local remote_port="${REMOTE_PORT:-${LOCAL_PORT}}"

    echo "── SSH 隧道状态 ──────────────────────────────"
    echo "  路由：localhost:${LOCAL_PORT} → ${jump_user}@${jump_host}:${jump_port} → ${remote_host}:${remote_port}"

    # 1. 检查 PID 文件
    echo ""
    if [[ -f "$PID_FILE" ]]; then
        local pid
        pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "  进程：运行中 (PID: $pid)"
        else
            echo "  进程：PID 文件存在但进程已退出 (PID: $pid，可能已崩溃)"
        fi
    else
        echo "  进程：未通过本脚本启动（无 PID 文件）"
    fi

    # 2. 检查本地端口是否在监听（兼容 Linux ss/lsof 和 Windows netstat）
    echo ""
    if ss -tlnp "sport = :${LOCAL_PORT}" 2>/dev/null | grep -q LISTEN; then
        echo "  端口：localhost:${LOCAL_PORT} 正在监听 ✓"
    elif lsof -i ":${LOCAL_PORT}" 2>/dev/null | grep -q LISTEN; then
        echo "  端口：localhost:${LOCAL_PORT} 正在监听 ✓"
    elif netstat -ano 2>/dev/null | grep -q ":${LOCAL_PORT}.*LISTENING"; then
        echo "  端口：localhost:${LOCAL_PORT} 正在监听 ✓"
    else
        echo "  端口：localhost:${LOCAL_PORT} 未监听 ✗"
    fi

    # 3. 查找 SSH 进程（兼容 Linux pgrep 和 Windows tasklist）
    echo ""
    local ssh_procs=""
    if command -v pgrep &>/dev/null; then
        ssh_procs=$(pgrep -a ssh 2>/dev/null | grep "${remote_host}:${remote_port}" || true)
    fi
    if [[ -n "$ssh_procs" ]]; then
        echo "  SSH 进程："
        echo "$ssh_procs" | while read -r line; do echo "    $line"; done
    elif [[ -f "$PID_FILE" ]]; then
        local pid
        pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            # Windows 下用 tasklist 显示进程详情
            local proc_info
            proc_info=$(tasklist /FI "PID eq $pid" /FO LIST 2>/dev/null | grep -E "^(映像名称|Image Name|PID)" || true)
            echo "  SSH 进程：PID $pid 运行中"
            [[ -n "$proc_info" ]] && echo "$proc_info" | while read -r line; do echo "    $line"; done
        fi
    else
        echo "  SSH 进程：无法查询（pgrep 不可用）"
    fi
    echo "──────────────────────────────────────────────"
}

# ── 检查端口是否已被占用 ──────────────────────────────────────
check_port() {
    if ss -tlnp "sport = :${LOCAL_PORT}" 2>/dev/null | grep -q LISTEN || \
       lsof -i ":${LOCAL_PORT}" 2>/dev/null | grep -q LISTEN || \
       netstat -ano 2>/dev/null | grep -q ":${LOCAL_PORT}.*LISTENING"; then
        echo "警告：本地端口 ${LOCAL_PORT} 已被占用，可能隧道已在运行"
        echo "  使用 '$0 stop' 先停止旧隧道，或 '$0 status' 查看详情"
        exit 1
    fi
}

# ── 初始化连接参数（仅启动时调用）────────────────────────────
init_connect_params() {
    JUMP_HOST="${JUMP_HOST:-}"
    JUMP_PORT="${JUMP_PORT:-22}"
    JUMP_USER="${SSH_USER:-root}"
    REMOTE_HOST="${REMOTE_HOST:-}"
    REMOTE_PORT="${REMOTE_PORT:-${LOCAL_PORT}}"

    if [[ -z "$JUMP_HOST" ]]; then
        echo "错误：必须设置 JUMP_HOST（跳板机地址）"
        exit 1
    fi
    if [[ -z "$REMOTE_HOST" ]]; then
        echo "错误：必须设置 REMOTE_HOST（目标内网地址）"
        exit 1
    fi

    # 认证模式：证书优先，其次密码，否则报错
    AUTH_LABEL=""
    SSH_CMD="ssh"
    SSH_AUTH_OPTS=()

    if [[ -n "${SSH_KEY_FILE:-}" ]]; then
        if [[ ! -f "${SSH_KEY_FILE}" ]]; then
            echo "错误：证书文件不存在：${SSH_KEY_FILE}"
            exit 1
        fi
        AUTH_LABEL="证书：${SSH_KEY_FILE}"
        SSH_AUTH_OPTS=(
            -i "${SSH_KEY_FILE}"
            -o PreferredAuthentications=publickey
            -o PasswordAuthentication=no
        )
    elif [[ -n "${SSH_PASSWORD:-}" ]]; then
        if ! command -v sshpass &>/dev/null; then
            echo "错误：密码模式需要安装 sshpass"
            echo "  Ubuntu/Debian: sudo apt install sshpass"
            echo "  macOS:         brew install sshpass"
            exit 1
        fi
        AUTH_LABEL="密码模式（sshpass）"
        export SSHPASS="${SSH_PASSWORD}"
        SSH_CMD="sshpass -e ssh"
        SSH_AUTH_OPTS=(
            -o PreferredAuthentications=password
            -o PubkeyAuthentication=no
        )
    else
        echo "错误：未配置认证方式，请设置以下任一环境变量："
        echo "  证书模式：export SSH_KEY_FILE=~/.ssh/your_private_key"
        echo "  密码模式：export SSH_PASSWORD=your_password"
        exit 1
    fi

    SSH_OPTS=(
        "${SSH_AUTH_OPTS[@]}"
        -p "${JUMP_PORT}"
        -N
        -L "${LOCAL_PORT}:${REMOTE_HOST}:${REMOTE_PORT}"
        -o StrictHostKeyChecking=accept-new
        -o ServerAliveInterval=30
        -o ServerAliveCountMax=3
        -o ExitOnForwardFailure=yes
        "${JUMP_USER}@${JUMP_HOST}"
    )
}

# ── 入口逻辑 ──────────────────────────────────────────────────
case "${1:-}" in
    status)
        status_tunnel
        ;;
    stop)
        stop_tunnel
        ;;
    start)
        init_connect_params
        check_port
        echo "启动 SSH 隧道..."
        echo "  ${JUMP_USER}@${JUMP_HOST}:${JUMP_PORT}  →  localhost:${LOCAL_PORT} ⇒ ${REMOTE_HOST}:${REMOTE_PORT}"
        echo "  认证：${AUTH_LABEL}"
        ${SSH_CMD} "${SSH_OPTS[@]}" &
        echo $! > "$PID_FILE"
        sleep 1
        if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            echo "隧道已启动 (PID: $(cat "$PID_FILE"))"
            echo "  查看状态：${TUNNEL_SCRIPT:-$0} status"
            echo "  停止命令：${TUNNEL_SCRIPT:-$0} stop"
        else
            echo "隧道启动失败，请检查 SSH 连接或端口占用"
            rm -f "$PID_FILE"
            exit 1
        fi
        ;;
    *)
        echo "用法: $0 {start|stop|status}"
        exit 1
        ;;
esac
