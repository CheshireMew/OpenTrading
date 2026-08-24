#!/bin/bash

set -euo pipefail

case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)
        WIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -W)"
        cmd.exe //c "cd /d $WIN_ROOT && scripts\\start.bat --no-pause"
        exit $?
        ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/.."
FRONTEND_ROOT="$PROJECT_ROOT/frontend"
PYTHON_EXE="${PYTHON_EXE:-python}"

if [ -x "$PROJECT_ROOT/venv/bin/python" ]; then
    PYTHON_EXE="$PROJECT_ROOT/venv/bin/python"
fi

API_HOST=127.0.0.1
API_PORT=8000
FRONTEND_HOST=127.0.0.1
FRONTEND_PORT=4173
SERVICE_READY_TIMEOUT_SECONDS=45
POLL_INTERVAL_SECONDS=0.2

resolve_runtime_path() {
    local attribute="$1"
    (
        cd "$PROJECT_ROOT" &&
        "$PYTHON_EXE" -c "from config import settings; print(settings.${attribute})"
    )
}

ensure_directory() {
    mkdir -p "$1"
}

ensure_file() {
    local path="$1"
    mkdir -p "$(dirname "$path")"
    touch "$path"
}

read_pid_file() {
    local path="$1"
    if [ -f "$path" ]; then
        tr -d '[:space:]' < "$path"
    fi
}

write_pid_file() {
    local path="$1"
    local pid="$2"
    printf '%s\n' "$pid" > "$path"
}

clear_pid_file() {
    rm -f "$1"
}

process_is_alive() {
    local pid="$1"
    [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null
}

listener_pids() {
    local port="$1"
    lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
}

port_in_use() {
    local port="$1"
    [ -n "$(listener_pids "$port")" ]
}

test_http_endpoint() {
    local url="$1"
    curl --silent --show-error --fail --max-time 4 "$url" >/dev/null 2>&1
}

wait_service_ready() {
    local pid="$1"
    local name="$2"
    local probe_url="$3"
    local log_path="$4"
    local deadline=$((SECONDS + SERVICE_READY_TIMEOUT_SECONDS))

    while [ "$SECONDS" -lt "$deadline" ]; do
        if ! process_is_alive "$pid"; then
            echo "$name startup failed. Process exited before startup completed. PID=$pid" >&2
            if [ -f "$log_path" ]; then
                tail -n 40 "$log_path" >&2 || true
            fi
            return 1
        fi

        if test_http_endpoint "$probe_url"; then
            return 0
        fi

        sleep "$POLL_INTERVAL_SECONDS"
    done

    echo "$name startup failed. Service did not become ready within ${SERVICE_READY_TIMEOUT_SECONDS}s. Probe=$probe_url" >&2
    if [ -f "$log_path" ]; then
        tail -n 40 "$log_path" >&2 || true
    fi
    return 1
}

resolve_healthy_tracked_service() {
    local pid_file="$1"
    local probe_url="$2"
    local tracked_pid

    tracked_pid="$(read_pid_file "$pid_file")"
    if [ -z "${tracked_pid:-}" ]; then
        return 1
    fi

    if ! process_is_alive "$tracked_pid"; then
        clear_pid_file "$pid_file"
        return 1
    fi

    if ! test_http_endpoint "$probe_url"; then
        return 1
    fi

    printf '%s\n' "$tracked_pid"
}

stop_tracked_service() {
    local pid_file="$1"
    local tracked_pid

    tracked_pid="$(read_pid_file "$pid_file")"
    clear_pid_file "$pid_file"
    if [ -n "${tracked_pid:-}" ] && process_is_alive "$tracked_pid"; then
        kill "$tracked_pid" 2>/dev/null || true
        wait "$tracked_pid" 2>/dev/null || true
    fi
}

start_backend() {
    local log_path="$1"

    (
        cd "$PROJECT_ROOT"
        "$PYTHON_EXE" scripts/prepare_db.py >> "$log_path" 2>&1
        HEIMDALL_API_HOST="$API_HOST" \
        HEIMDALL_API_PORT="$API_PORT" \
        APP_RUNTIME_ROLE=api \
        PYTHONIOENCODING=utf-8 \
        PYTHONUTF8=1 \
        exec "$PYTHON_EXE" -m uvicorn app.main:app \
            --host "$API_HOST" \
            --reload \
            --reload-dir app \
            --reload-dir config \
            --reload-dir utils \
            --reload-exclude "data/*" \
            --reload-exclude "logs/*" \
            --reload-exclude "frontend/dist/*" \
            --port "$API_PORT" >> "$log_path" 2>&1
    ) &
    printf '%s\n' "$!"
}

start_background() {
    local log_path="$1"

    (
        cd "$PROJECT_ROOT"
        APP_RUNTIME_ROLE=background \
        PYTHONIOENCODING=utf-8 \
        PYTHONUTF8=1 \
        exec "$PYTHON_EXE" scripts/run_background_runtime.py >> "$log_path" 2>&1
    ) &
    printf '%s\n' "$!"
}

start_frontend() {
    local log_path="$1"

    (
        cd "$FRONTEND_ROOT"
        HEIMDALL_API_HOST="$API_HOST" \
        HEIMDALL_API_PORT="$API_PORT" \
        HEIMDALL_FRONTEND_HOST="$FRONTEND_HOST" \
        HEIMDALL_FRONTEND_PORT="$FRONTEND_PORT" \
        exec npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" >> "$log_path" 2>&1
    ) &
    printf '%s\n' "$!"
}

ensure_service_running() {
    local name="$1"
    local pid_file="$2"
    local port="$3"
    local probe_url="$4"
    local log_path="$5"
    local start_function="$6"
    local tracked_pid
    local new_pid

    tracked_pid="$(resolve_healthy_tracked_service "$pid_file" "$probe_url" || true)"
    if [ -n "${tracked_pid:-}" ]; then
        printf '%s|%s\n' "$tracked_pid" "reused"
        return 0
    fi

    stop_tracked_service "$pid_file"
    if port_in_use "$port"; then
        echo "$name port $port is already in use by another process." >&2
        return 1
    fi

    new_pid="$($start_function "$log_path")"
    if ! wait_service_ready "$new_pid" "$name" "$probe_url" "$log_path"; then
        kill "$new_pid" 2>/dev/null || true
        wait "$new_pid" 2>/dev/null || true
        return 1
    fi

    write_pid_file "$pid_file" "$new_pid"
    printf '%s|%s\n' "$new_pid" "started"
}

ensure_background_running() {
    local pid_file="$1"
    local log_path="$2"
    local tracked_pid
    local new_pid

    tracked_pid="$(read_pid_file "$pid_file")"
    if [ -n "${tracked_pid:-}" ] && process_is_alive "$tracked_pid"; then
        printf '%s|%s\n' "$tracked_pid" "reused"
        return 0
    fi

    stop_tracked_service "$pid_file"
    new_pid="$(start_background "$log_path")"
    sleep 1
    if ! process_is_alive "$new_pid"; then
        echo "Background runtime startup failed. PID=$new_pid" >&2
        if [ -f "$log_path" ]; then
            tail -n 40 "$log_path" >&2 || true
        fi
        return 1
    fi

    write_pid_file "$pid_file" "$new_pid"
    printf '%s|%s\n' "$new_pid" "started"
}

echo "Launching Heimdall development environment..."

LOG_DIR="$(resolve_runtime_path LOG_DIR)"
TEMP_DIR="$(resolve_runtime_path TEMP_DIR)"
BACKEND_LOG="$LOG_DIR/backend.log"
BACKGROUND_LOG="$LOG_DIR/background.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"
BACKEND_PID_FILE="$TEMP_DIR/backend.pid"
BACKGROUND_PID_FILE="$TEMP_DIR/background.pid"
FRONTEND_PID_FILE="$TEMP_DIR/frontend.pid"

ensure_directory "$LOG_DIR"
ensure_directory "$TEMP_DIR"
ensure_file "$BACKEND_LOG"
ensure_file "$BACKGROUND_LOG"
ensure_file "$FRONTEND_LOG"

backend_result=""
background_result=""
frontend_result=""

cleanup_on_failure() {
    if [ -n "${frontend_result:-}" ] && [[ "$frontend_result" == *"|started" ]]; then
        kill "${frontend_result%%|*}" 2>/dev/null || true
        wait "${frontend_result%%|*}" 2>/dev/null || true
        clear_pid_file "$FRONTEND_PID_FILE"
    fi

    if [ -n "${background_result:-}" ] && [[ "$background_result" == *"|started" ]]; then
        kill "${background_result%%|*}" 2>/dev/null || true
        wait "${background_result%%|*}" 2>/dev/null || true
        clear_pid_file "$BACKGROUND_PID_FILE"
    fi

    if [ -n "${backend_result:-}" ] && [[ "$backend_result" == *"|started" ]]; then
        kill "${backend_result%%|*}" 2>/dev/null || true
        wait "${backend_result%%|*}" 2>/dev/null || true
        clear_pid_file "$BACKEND_PID_FILE"
    fi
}

trap cleanup_on_failure ERR

backend_result="$(ensure_service_running "Backend" "$BACKEND_PID_FILE" "$API_PORT" "http://${API_HOST}:$API_PORT/health" "$BACKEND_LOG" start_backend)"
background_result="$(ensure_background_running "$BACKGROUND_PID_FILE" "$BACKGROUND_LOG")"
frontend_result="$(ensure_service_running "Frontend" "$FRONTEND_PID_FILE" "$FRONTEND_PORT" "http://${FRONTEND_HOST}:$FRONTEND_PORT/" "$FRONTEND_LOG" start_frontend)"

backend_pid="${backend_result%%|*}"
background_pid="${background_result%%|*}"
frontend_pid="${frontend_result%%|*}"
backend_state="${backend_result##*|}"
background_state="${background_result##*|}"
frontend_state="${frontend_result##*|}"

if [ "$backend_state" = "started" ]; then
    echo "Backend started. PID $backend_pid"
else
    echo "Backend already running. PID $backend_pid"
fi

if [ "$frontend_state" = "started" ]; then
    echo "Frontend started. PID $frontend_pid"
else
    echo "Frontend already running. PID $frontend_pid"
fi

if [ "$background_state" = "started" ]; then
    echo "Background runtime started. PID $background_pid"
else
    echo "Background runtime already running. PID $background_pid"
fi

echo "Backend PID:  $backend_pid"
echo "Background PID: $background_pid"
echo "Frontend PID: $frontend_pid"
echo "Backend API:  http://${API_HOST}:$API_PORT"
echo "Frontend:     http://${FRONTEND_HOST}:$FRONTEND_PORT"
echo "API docs:     http://${API_HOST}:$API_PORT/docs"
echo "Backend log:  $BACKEND_LOG"
echo "Background log: $BACKGROUND_LOG"
echo "Frontend log: $FRONTEND_LOG"
echo "Stop command: scripts/stop.sh"
