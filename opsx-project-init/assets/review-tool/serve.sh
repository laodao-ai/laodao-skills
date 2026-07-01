#!/bin/sh
# Starts/stops a background static file server rooted at openspec/, regardless of the
# caller's cwd — review.html's root-relative asset paths (/tools/engine.js etc.) depend
# on the server root being exactly openspec/, so this always cd's to its own directory
# first. Runs the server detached (background) and prints a clickable link.
#
# Usage:
#   serve.sh start [port]     # default port 8000; no-op (prints link) if already running
#   serve.sh stop             # no-op if not running
#   serve.sh restart [port]   # stop then start; reuses the last port if none given

set -eu

DIR="$(cd "$(dirname "$0")" && pwd)"
KEY=$(printf '%s' "$DIR" | tr '/' '_')
PIDFILE="/tmp/openspec-review-serve-${KEY}.pid"
LOGFILE="/tmp/openspec-review-serve-${KEY}.log"
DEFAULT_PORT=8000

is_running() {
  [ -f "$PIDFILE" ] || return 1
  PID=$(sed -n '1p' "$PIDFILE")
  [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null
}

do_start() {
  PORT="${1:-$DEFAULT_PORT}"
  if is_running; then
    PID=$(sed -n '1p' "$PIDFILE")
    RUNNING_PORT=$(sed -n '2p' "$PIDFILE")
    echo "already running (pid $PID) -> http://localhost:${RUNNING_PORT}/review.html"
    return 0
  fi
  cd "$DIR"
  nohup python3 -m http.server "$PORT" >"$LOGFILE" 2>&1 &
  NEWPID=$!
  printf '%s\n%s\n' "$NEWPID" "$PORT" >"$PIDFILE"
  echo "started (pid $NEWPID), log: $LOGFILE"
  echo "http://localhost:${PORT}/review.html"
}

do_stop() {
  if ! is_running; then
    echo "not running"
    rm -f "$PIDFILE"
    return 0
  fi
  PID=$(sed -n '1p' "$PIDFILE")
  kill "$PID" 2>/dev/null || true
  rm -f "$PIDFILE"
  echo "stopped (pid $PID)"
}

do_restart() {
  PORT="${1:-}"
  if [ -z "$PORT" ] && [ -f "$PIDFILE" ]; then
    PORT=$(sed -n '2p' "$PIDFILE")
  fi
  do_stop
  do_start "${PORT:-$DEFAULT_PORT}"
}

case "${1:-}" in
  start) shift; do_start "${1:-}" ;;
  stop) do_stop ;;
  restart) shift; do_restart "${1:-}" ;;
  *)
    echo "usage: $0 {start [port]|stop|restart [port]}" >&2
    exit 2
    ;;
esac
