#!/usr/bin/env bash
#
# serve.sh — Unified DeerFlow service launcher
#
# Usage:
#   ./scripts/serve.sh [--dev|--prod] [--gateway] [--daemon] [--stop|--restart]
#
# Modes:
#   --dev       Development mode with hot-reload (default)
#   --prod      Production mode, pre-built frontend, no hot-reload
#   --gateway   Gateway mode (experimental): skip LangGraph server,
#               agent runtime embedded in Gateway API
#   --daemon    Run all services in background (nohup), exit after startup
#
# Actions:
#   --skip-install  Skip dependency installation (faster restart)
#   --stop      Stop all running services and exit
#   --restart   Stop all services, then start with the given mode flags
#
# Examples:
#   ./scripts/serve.sh --dev                 # Standard dev (4 processes)
#   ./scripts/serve.sh --dev --gateway       # Gateway dev  (3 processes)
#   ./scripts/serve.sh --prod --gateway      # Gateway prod (3 processes)
#   ./scripts/serve.sh --dev --daemon        # Standard dev, background
#   ./scripts/serve.sh --dev --gateway --daemon  # Gateway dev, background
#   ./scripts/serve.sh --stop                # Stop all services
#   ./scripts/serve.sh --restart --dev --gateway # Restart in gateway mode
#
# Must be run from the repo root directory.

set -e

REPO_ROOT="$(builtin cd "$(dirname "${BASH_SOURCE[0]}")/.." >/dev/null 2>&1 && pwd -P)"
cd "$REPO_ROOT"

# ── Load .env ────────────────────────────────────────────────────────────────

if [ -f "$REPO_ROOT/.env" ]; then
    set -a
    source "$REPO_ROOT/.env"
    set +a
fi

# ── Argument parsing ─────────────────────────────────────────────────────────

DEV_MODE=true
GATEWAY_MODE=false
DAEMON_MODE=false
SKIP_INSTALL=false
SKIP_NGINX=true
ACTION="start"   # start | stop | restart

for arg in "$@"; do
    case "$arg" in
        --dev)     DEV_MODE=true ;;
        --prod)    DEV_MODE=false ;;
        --gateway) GATEWAY_MODE=true ;;
        --daemon)  DAEMON_MODE=true ;;
        --no-nginx) SKIP_NGINX=true ;;
        --with-nginx) SKIP_NGINX=false ;;
        --skip-install) SKIP_INSTALL=true ;;
        --stop)    ACTION="stop" ;;
        --restart) ACTION="restart" ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: $0 [--dev|--prod] [--gateway] [--daemon] [--no-nginx|--with-nginx] [--skip-install] [--stop|--restart]"
            exit 1
            ;;
    esac
done
# 环境变量可覆盖：DEER_FLOW_USE_NGINX=1 表示启动 nginx；DEER_FLOW_NO_NGINX=1 表示不启动
if [ -n "${DEER_FLOW_USE_NGINX:-}" ] && [ "$DEER_FLOW_USE_NGINX" != "0" ]; then
    SKIP_NGINX=false
fi
if [ -n "${DEER_FLOW_NO_NGINX:-}" ] && [ "$DEER_FLOW_NO_NGINX" != "0" ]; then
    SKIP_NGINX=true
fi

# ── Ports (configurable) ─────────────────────────────────────────────────────
LANGGRAPH_PORT="${DEER_FLOW_LANGGRAPH_PORT:-2024}"
GATEWAY_PORT="${DEER_FLOW_GATEWAY_PORT:-18084}"
FRONTEND_PORT="${DEER_FLOW_FRONTEND_PORT:-18083}"
NGINX_PORT="${DEER_FLOW_NGINX_PORT:-2026}"

# ── Stop helper ──────────────────────────────────────────────────────────────

_is_repo_pid() {
    local pid=$1
    lsof -p "$pid" 2>/dev/null | grep -F "$REPO_ROOT" >/dev/null
}

_kill_repo_processes() {
    local pattern=$1
    local pid
    local pids=""

    while IFS= read -r pid; do
        if [ -n "$pid" ] && _is_repo_pid "$pid"; then
            case " $pids " in
                *" $pid "*) ;;
                *) pids="$pids $pid" ;;
            esac
        fi
    done < <(pgrep -f "$pattern" 2>/dev/null || true)

    if [ -n "$pids" ]; then
        kill $pids 2>/dev/null || true
    fi
}

_kill_repo_port() {
    local port=$1
    local pid
    local pids=""

    while IFS= read -r pid; do
        if [ -n "$pid" ] && _is_repo_pid "$pid"; then
            case " $pids " in
                *" $pid "*) ;;
                *) pids="$pids $pid" ;;
            esac
        fi
    done < <(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true)

    if [ -n "$pids" ]; then
        kill -9 $pids 2>/dev/null || true
    fi
}

_is_port_listening() {
    local port=$1

    if command -v lsof >/dev/null 2>&1; then
        if lsof -nP -iTCP:"$port" -sTCP:LISTEN -t >/dev/null 2>&1; then
            return 0
        fi
    fi

    if command -v ss >/dev/null 2>&1; then
        if ss -ltn "( sport = :$port )" 2>/dev/null | tail -n +2 | grep -q .; then
            return 0
        fi
    fi

    if command -v netstat >/dev/null 2>&1; then
        if netstat -ltn 2>/dev/null | awk '{print $4}' | grep -Eq "(^|[.:])${port}$"; then
            return 0
        fi
    fi

    return 1
}

_is_repo_nginx_pid() {
    local pid=$1
    local command
    local args

    command=$(ps -p "$pid" -o comm= 2>/dev/null) || return 1
    case "$command" in
        nginx|*/nginx) ;;
        *) return 1 ;;
    esac

    args=$(ps -p "$pid" -o args= 2>/dev/null) || return 1
    case "$args" in
        *"$REPO_ROOT/docker/nginx/nginx.local.conf"*|*"$REPO_ROOT"*) return 0 ;;
    esac

    _is_repo_pid "$pid"
}

_kill_repo_nginx() {
    local pid
    local pids=""

    if [ -f "$REPO_ROOT/logs/nginx.pid" ]; then
        read -r pid < "$REPO_ROOT/logs/nginx.pid" || true
        if [ -n "$pid" ] && _is_repo_nginx_pid "$pid"; then
            pids="$pids $pid"
        fi
    fi

    while IFS= read -r pid; do
        if [ -n "$pid" ] && _is_repo_nginx_pid "$pid"; then
            case " $pids " in
                *" $pid "*) ;;
                *) pids="$pids $pid" ;;
            esac
        fi
    done < <(pgrep -f nginx 2>/dev/null || true)

    if [ -n "$pids" ]; then
        kill -9 $pids 2>/dev/null || true
    fi
}

_kill_port() {
    local port=$1
    local pid
    pid=$(lsof -ti :"$port" 2>/dev/null) || true
    if [ -n "$pid" ]; then
        kill -9 $pid 2>/dev/null || true
    fi
}


stop_all() {
    echo "Stopping all services..."
    # 仅结束本仓库的 workflow worker，避免旧进程仍用旧代码抢跑任务
    pkill -f "${REPO_ROOT}/backend.*extensions._core.workflow.runtime.run_worker" 2>/dev/null || true
    pkill -f "langgraph dev" 2>/dev/null || true
    pkill -f "uvicorn app.gateway.app:app" 2>/dev/null || true
    pkill -f "next dev" 2>/dev/null || true
    pkill -f "next start" 2>/dev/null || true
    pkill -f "next-server" 2>/dev/null || true
    nginx -c "$REPO_ROOT/docker/nginx/nginx.local.conf" -p "$REPO_ROOT" -s quit 2>/dev/null || true
    sleep 1
    pkill -9 nginx 2>/dev/null || true
    # Force-kill any survivors still holding the service ports
    _kill_port 2024
    _kill_port 8001
    _kill_port 3000
    ./scripts/cleanup-containers.sh deer-flow-sandbox 2>/dev/null || true
    echo "✓ All services stopped"
}


# ── Action routing ───────────────────────────────────────────────────────────

if [ "$ACTION" = "stop" ]; then
    stop_all
    exit 0
fi

ALREADY_STOPPED=false
if [ "$ACTION" = "restart" ]; then
    stop_all
    sleep 1
    ALREADY_STOPPED=true
fi

# ── Derive runtime flags ────────────────────────────────────────────────────

if $GATEWAY_MODE; then
    export SKIP_LANGGRAPH_SERVER=1
fi

# Mode label for banner
if $DEV_MODE && $GATEWAY_MODE; then
    MODE_LABEL="DEV + GATEWAY (experimental)"
elif $DEV_MODE; then
    MODE_LABEL="DEV (hot-reload enabled)"
elif $GATEWAY_MODE; then
    MODE_LABEL="PROD + GATEWAY (experimental)"
else
    MODE_LABEL="PROD (optimized)"
fi

if $DAEMON_MODE; then
    MODE_LABEL="$MODE_LABEL [daemon]"
fi

# Frontend → Gateway wiring (SSR rewrites + trusted origins for auth proxy)
INTERNAL_GATEWAY_URL="http://127.0.0.1:${GATEWAY_PORT}"
TRUSTED_ORIGINS="http://localhost:${FRONTEND_PORT},http://127.0.0.1:${FRONTEND_PORT},http://localhost:${NGINX_PORT},http://127.0.0.1:${NGINX_PORT}"
FRONTEND_RUNTIME_ENV="DEER_FLOW_INTERNAL_GATEWAY_BASE_URL=${INTERNAL_GATEWAY_URL} DEER_FLOW_TRUSTED_ORIGINS=${TRUSTED_ORIGINS}"

# Turbopack is unstable on this project path (non-ASCII/spaces) + Node mismatch:
# it intermittently fails with stale runtime chunks, missing build-manifest, and
# cannot resolve pnpm-symlinked deps (e.g. mermaid -> d3). Use webpack for reliability.
# Trade-off: webpack HMR may 404 on Next 16, so code edits can need a manual refresh.
if $SKIP_NGINX; then
    FRONTEND_DEV_BIN="node scripts/next-with-root-env.mjs next dev --webpack -p ${FRONTEND_PORT}"
else
    FRONTEND_DEV_BIN="node scripts/next-with-root-env.mjs next dev --webpack -p ${FRONTEND_PORT}"
fi

# Frontend command
if $DEV_MODE; then
    FRONTEND_CMD="env ${FRONTEND_RUNTIME_ENV} ${FRONTEND_DEV_BIN}"
else
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="python3"
    elif command -v python >/dev/null 2>&1; then
        PYTHON_BIN="python"
    else
        echo "Python is required to generate BETTER_AUTH_SECRET."
        exit 1
    fi
    # Local prod mode: dev server by default (no compile). Set DEER_FLOW_PROD_FRONTEND=1
    # and run `cd frontend && pnpm run build` once to serve an existing .next build.
    _FRONTEND_BUILD_ID="$REPO_ROOT/frontend/.next/BUILD_ID"
    if [ "${DEER_FLOW_PROD_FRONTEND:-0}" = "1" ] && [ -f "$_FRONTEND_BUILD_ID" ]; then
        FRONTEND_CMD="env NODE_ENV=production ${FRONTEND_RUNTIME_ENV} BETTER_AUTH_SECRET=$($PYTHON_BIN -c 'import secrets; print(secrets.token_hex(16))') PORT=${FRONTEND_PORT} pnpm run start"
    else
        if [ -f "$_FRONTEND_BUILD_ID" ] && [ "${DEER_FLOW_PROD_FRONTEND:-0}" != "1" ]; then
            echo "⚠ Frontend: using next dev (no compile). Set DEER_FLOW_PROD_FRONTEND=1 to serve the existing production build."
        elif [ ! -f "$_FRONTEND_BUILD_ID" ]; then
            echo "⚠ Frontend: no production build (frontend/.next/BUILD_ID missing); using next dev."
            echo "  For optimized static serving: cd frontend && pnpm run build && DEER_FLOW_PROD_FRONTEND=1 make start"
        fi
        FRONTEND_CMD="env ${FRONTEND_RUNTIME_ENV} BETTER_AUTH_SECRET=$($PYTHON_BIN -c 'import secrets; print(secrets.token_hex(16))') ${FRONTEND_DEV_BIN}"
    fi
fi

# Extra flags for uvicorn/langgraph
LANGGRAPH_EXTRA_FLAGS="--no-reload"
if $DEV_MODE && ! $DAEMON_MODE; then
    GATEWAY_EXTRA_FLAGS="--reload --reload-include='*.yaml' --reload-include='.env' --reload-exclude='*.pyc' --reload-exclude='__pycache__' --reload-exclude='sandbox/' --reload-exclude='.deer-flow/'"
else
    GATEWAY_EXTRA_FLAGS=""
fi

# ── Stop existing services (skip if restart already did it) ──────────────────

if ! $ALREADY_STOPPED; then
    stop_all
    sleep 1
fi

# ── Config check ─────────────────────────────────────────────────────────────

if ! { \
        [ -n "$DEER_FLOW_CONFIG_PATH" ] && [ -f "$DEER_FLOW_CONFIG_PATH" ] || \
        [ -f backend/config.yaml ] || \
        [ -f config.yaml ]; \
    }; then
    echo "✗ No DeerFlow config file found."
    echo "  Run 'make setup' (recommended) or 'make config' to generate config.yaml."
    exit 1
fi

"$REPO_ROOT/scripts/config-upgrade.sh"

# ── Install dependencies ────────────────────────────────────────────────────

# Pick a Python for the extras detector. Falls back to plain `python` for
# Windows/Git Bash where only `python` is on PATH.
if command -v python3 >/dev/null 2>&1; then
    DETECT_PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
    DETECT_PYTHON="python"
else
    DETECT_PYTHON=""
fi

# Resolve uv extras (postgres, etc.) from UV_EXTRAS or config.yaml so that
# `uv sync` does not wipe out optional dependencies on every restart. See
# scripts/detect_uv_extras.py and Issue #2754 for context. The detector
# whitelists extra names against `^[A-Za-z][A-Za-z0-9_-]*$`, so the unquoted
# splat below only sees valid uv argument tokens.
#
# Stderr is intentionally NOT redirected so the user sees:
#   - whitelist warnings (e.g. "ignoring invalid UV_EXTRAS entry ';'");
#   - detector crashes (e.g. unexpected Python error).
# `|| true` keeps `set -e` from killing dev startup on a detector failure;
# the result is just an empty UV_EXTRAS_FLAGS, which means "no extras".
UV_EXTRAS_FLAGS=""
if [ -n "$DETECT_PYTHON" ]; then
    UV_EXTRAS_FLAGS=$("$DETECT_PYTHON" "$REPO_ROOT/scripts/detect_uv_extras.py" || { echo "[serve.sh] detect_uv_extras.py failed (exit $?) — proceeding without extras" >&2; echo ""; })
fi

if ! $SKIP_INSTALL; then
    echo "Syncing dependencies..."
    if [ -n "$UV_EXTRAS_FLAGS" ]; then
        echo "  • uv extras: $UV_EXTRAS_FLAGS"
    fi
    # `--all-packages` propagates extras into workspace members (deerflow-harness
    # in particular). Required for postgres extras — see PR #2584.
    # Intentionally unquoted to splat multiple `--extra X` pairs.
    (cd backend && uv sync --quiet --all-packages $UV_EXTRAS_FLAGS) || { echo "✗ Backend dependency install failed"; exit 1; }
    (cd frontend && pnpm install --silent) || { echo "✗ Frontend dependency install failed"; exit 1; }
    echo "✓ Dependencies synced"
else
    echo "⏩ Skipping dependency install (--skip-install)"
fi

# ── Sync frontend .env.local ─────────────────────────────────────────────────
# Next.js .env.local takes precedence over process env vars.
# The script manages the NEXT_PUBLIC_LANGGRAPH_BASE_URL line to ensure
# the frontend routes match the active backend mode.

FRONTEND_ENV_LOCAL="$REPO_ROOT/frontend/.env.local"

_upsert_env_local() {
    local key=$1
    local value=$2
    if [ -f "$FRONTEND_ENV_LOCAL" ] && grep -q "^${key}=" "$FRONTEND_ENV_LOCAL"; then
        sed -i.bak "s|^${key}=.*|${key}=${value}|" "$FRONTEND_ENV_LOCAL" && rm -f "${FRONTEND_ENV_LOCAL}.bak"
    else
        echo "${key}=${value}" >> "$FRONTEND_ENV_LOCAL"
    fi
}

sync_frontend_env() {
    _upsert_env_local "DEER_FLOW_INTERNAL_GATEWAY_BASE_URL" "$INTERNAL_GATEWAY_URL"
    _upsert_env_local "DEER_FLOW_TRUSTED_ORIGINS" "$TRUSTED_ORIGINS"

    ENV_KEY="NEXT_PUBLIC_LANGGRAPH_BASE_URL"
    # Unified nginx entry: browser calls same-origin /api (Gateway embeds LangGraph runtime).
    if $GATEWAY_MODE || ! $SKIP_NGINX; then
        _upsert_env_local "$ENV_KEY" "/api"
    elif [ -f "$FRONTEND_ENV_LOCAL" ] && grep -q "^${ENV_KEY}=" "$FRONTEND_ENV_LOCAL"; then
        sed -i.bak "/^${ENV_KEY}=/d" "$FRONTEND_ENV_LOCAL" && rm -f "${FRONTEND_ENV_LOCAL}.bak"
    fi
}

sync_frontend_env

# ── Banner ───────────────────────────────────────────────────────────────────

echo ""
echo "=========================================="
echo "  Starting DeerFlow"
echo "=========================================="
echo ""
echo "  Mode: $MODE_LABEL"
echo ""
echo "  Services:"
if ! $GATEWAY_MODE; then
    echo "    LangGraph   → localhost:2024  (agent runtime)"
fi
echo "    Gateway     → localhost:${GATEWAY_PORT}  (REST API$(if $GATEWAY_MODE; then echo " + agent runtime"; fi))"
echo "    Frontend    → localhost:${FRONTEND_PORT}  (Next.js)"
echo "    Nginx       → localhost:${NGINX_PORT}  (reverse proxy)"
echo ""

# ── Cleanup handler ──────────────────────────────────────────────────────────

cleanup() {
    local status="${1:-0}"
    trap - INT TERM
    echo ""
    stop_all
    exit "$status"
}

trap 'cleanup 130' INT
trap 'cleanup 143' TERM

# ── Helper: start a service ──────────────────────────────────────────────────

# run_service NAME COMMAND PORT TIMEOUT
# In daemon mode, wraps with nohup. Waits for port to be ready.
run_service() {
    local name="$1" cmd="$2" port="$3" timeout="$4"

    if _is_port_listening "$port"; then
        echo "✗ $name cannot start because port $port is already in use."
        echo "  If it belongs to this worktree, run 'make stop'; otherwise free the port manually."
        cleanup 1
    fi

    echo "Starting $name..."
    if $DAEMON_MODE; then
        nohup sh -c "$cmd" > /dev/null 2>&1 &
    else
        sh -c "$cmd" &
    fi

    ./scripts/wait-for-port.sh "$port" "$timeout" "$name" || {
        local logfile="logs/$(echo "$name" | tr '[:upper:]' '[:lower:]' | tr ' ' '-').log"
        echo "✗ $name failed to start."
        [ -f "$logfile" ] && tail -20 "$logfile"
        cleanup 1
    }
    echo "✓ $name started on localhost:$port"
}

# ── Start services ───────────────────────────────────────────────────────────

mkdir -p logs
mkdir -p temp/client_body_temp temp/proxy_temp temp/fastcgi_temp temp/uwsgi_temp temp/scgi_temp

if $DEV_MODE; then
    LANGGRAPH_EXTRA_FLAGS="--no-reload"
    GATEWAY_EXTRA_FLAGS="--reload --reload-include='*.yaml' --reload-include='.env' --reload-exclude='*.pyc' --reload-exclude='__pycache__' --reload-exclude='sandbox/' --reload-exclude='.deer-flow/'"
else
    LANGGRAPH_EXTRA_FLAGS="--no-reload"
    GATEWAY_EXTRA_FLAGS=""
fi

echo "Starting LangGraph server..."
# Free port 2024 in case a previous run left a process that did not match "langgraph dev"
for pid in $(lsof -ti:"$LANGGRAPH_PORT" 2>/dev/null); do kill -9 "$pid" 2>/dev/null; done
sleep 1
if [ "${SKIP_LANGGRAPH_SERVER:-0}" != "1" ]; then
    # Read log_level from config.yaml, fallback to env var, then to "info"
    CONFIG_LOG_LEVEL=$(grep -m1 '^log_level:' config.yaml 2>/dev/null | awk '{print $2}' | tr -d ' ')
    LANGGRAPH_LOG_LEVEL="${LANGGRAPH_LOG_LEVEL:-${CONFIG_LOG_LEVEL:-info}}"
    LANGGRAPH_JOBS_PER_WORKER="${LANGGRAPH_JOBS_PER_WORKER:-10}"
    LANGGRAPH_ALLOW_BLOCKING="${LANGGRAPH_ALLOW_BLOCKING:-0}"
    LANGGRAPH_ALLOW_BLOCKING_FLAG=""
    if [ "$LANGGRAPH_ALLOW_BLOCKING" = "1" ]; then
        LANGGRAPH_ALLOW_BLOCKING_FLAG="--allow-blocking"
    fi
    run_service "LangGraph" \
        "cd backend && NO_COLOR=1 CLICOLOR=0 CLICOLOR_FORCE=0 PY_COLORS=0 TERM=dumb uv run langgraph dev --no-browser $LANGGRAPH_ALLOW_BLOCKING_FLAG --n-jobs-per-worker $LANGGRAPH_JOBS_PER_WORKER --server-log-level $LANGGRAPH_LOG_LEVEL $LANGGRAPH_EXTRA_FLAGS 2>&1 | LC_ALL=C LC_CTYPE=C LANG=C perl -pe 's/\e\[[0-9;]*[[:alpha:]]//g' > ../logs/langgraph.log" \
        "$LANGGRAPH_PORT" 60
else
    echo "⏩ Skipping LangGraph (Gateway mode — runtime embedded in Gateway)"
fi

# macOS + uv(0.11.x) 在含非 ASCII / 空格的项目路径下，会把 venv 里的 .pth 文件标记为 UF_HIDDEN，
# 而 CPython 的 site 模块会跳过 hidden 的 .pth（`python -v` 可见 "Skipping hidden .pth file"），
# 导致 deerflow-harness 的 editable 安装失效 → `ModuleNotFoundError: No module named 'deerflow'`。
# 翻转点：import zstandard（经 httpx）。每个 uv-run 的 Python 进程启动前清一次即可
# （进程 import 期间 .pth 是干净态，import 成功后即便被重标也不影响已运行的进程）。
unhide_venv_pth() {
    command -v chflags >/dev/null 2>&1 || return 0   # 仅 macOS 需要 chflags
    chflags nohidden "${REPO_ROOT}"/backend/.venv/lib/python*/site-packages/*.pth 2>/dev/null || true
}

echo "Starting Gateway API..."
unhide_venv_pth
# Ensure gateway uses repo-root config.yaml (for ragflow, etc.) even when cwd is backend/
(cd backend && PYTHONPATH=. DEER_FLOW_CONFIG_PATH="${REPO_ROOT}/config.yaml" uv run uvicorn app.gateway.app:app --host 0.0.0.0 --port "$GATEWAY_PORT" $GATEWAY_EXTRA_FLAGS > ../logs/gateway.log 2>&1) &
./scripts/wait-for-port.sh "$GATEWAY_PORT" 30 "Gateway API" || {
    echo "✗ Gateway API failed to start. Last log output:"
    tail -60 logs/gateway.log
    echo ""
    echo "Likely configuration errors:"
    grep -E "Failed to load configuration|Environment variable .* not found|config\.yaml.*not found" logs/gateway.log | tail -5 || true
    echo ""
    echo "  Hint: Try running 'make config-upgrade' to update your config.yaml with the latest fields."
    cleanup
}
echo "✓ Gateway API started on localhost:${GATEWAY_PORT}"

echo "Starting Workflow Worker..."
pkill -f "${REPO_ROOT}/backend.*extensions._core.workflow.runtime.run_worker" 2>/dev/null || true
sleep 0.5
unhide_venv_pth
(cd backend && uv run python -m extensions._core.workflow.runtime.run_worker > ../logs/workflow-worker.log 2>&1) &
echo "✓ Workflow worker started (logs/workflow-worker.log)"

echo "Starting Frontend..."
(cd frontend && $FRONTEND_CMD > ../logs/frontend.log 2>&1) &
./scripts/wait-for-port.sh "$FRONTEND_PORT" 120 "Frontend" || {
    echo "  See logs/frontend.log for details"
    tail -20 logs/frontend.log
    cleanup
}
echo "✓ Frontend started on localhost:${FRONTEND_PORT}"

if $SKIP_NGINX; then
    echo "Skipping Nginx (DEER_FLOW_NO_NGINX or --no-nginx). Use Gateway ${GATEWAY_PORT}, Frontend ${FRONTEND_PORT} directly or your server nginx to proxy."
    NGINX_PID=""
else
    echo "Starting Nginx reverse proxy..."
    nginx -g 'daemon off;' -c "$REPO_ROOT/docker/nginx/nginx.local.conf" -p "$REPO_ROOT" > logs/nginx.log 2>&1 &
    NGINX_PID=$!
    ./scripts/wait-for-port.sh "$NGINX_PORT" 10 "Nginx" || {
        echo "  See logs/nginx.log for details"
        tail -10 logs/nginx.log
        cleanup
    }
    echo "✓ Nginx started on localhost:${NGINX_PORT}"
fi

# ── Ready ────────────────────────────────────────────────────────────────────

echo ""
echo "=========================================="
echo "  ✓ DeerFlow is running!  [$MODE_LABEL]"
echo "=========================================="
echo ""
if $SKIP_NGINX; then
    echo "  🌐 Frontend:   http://localhost:${FRONTEND_PORT}"
    echo "  📡 API Gateway: http://localhost:${GATEWAY_PORT}"
    echo "  🤖 LangGraph:   http://localhost:${LANGGRAPH_PORT} (or proxy via your nginx)"
else
    echo "  🌐 Application: http://localhost:${NGINX_PORT}"
    echo "  📡 API Gateway: http://localhost:${NGINX_PORT}/api/*"
    if [ "${SKIP_LANGGRAPH_SERVER:-0}" = "1" ]; then
        echo "  🤖 LangGraph: skipped (SKIP_LANGGRAPH_SERVER=1)"
    else
        echo "  🤖 LangGraph: http://localhost:${NGINX_PORT}/api/langgraph/* (served by langgraph dev)"
    fi
    echo "  🧪 Gateway LangGraph API: http://localhost:${NGINX_PORT}/api/threads/* (SDK base URL /api)"
    if [ "${SKIP_LANGGRAPH_SERVER:-0}" = "1" ]; then
        echo ""
        echo "  💡 Gateway mode sets NEXT_PUBLIC_LANGGRAPH_BASE_URL=/api in frontend/.env.local"
    fi
fi
echo "           /api/*              →  Gateway REST API (8001)"
echo ""
echo "  📋 Logs:"
echo "     - LangGraph: logs/langgraph.log"
echo "     - Gateway:   logs/gateway.log"
echo "     - Frontend:  logs/frontend.log"
if ! $SKIP_NGINX; then
    echo "     - Nginx:     logs/nginx.log"
fi
echo ""

if $DAEMON_MODE; then
    echo "  🛑 Stop: make stop"
    # Detach — trap is no longer needed
    trap - INT TERM
else
    echo "  Press Ctrl+C to stop all services"
    wait
fi
