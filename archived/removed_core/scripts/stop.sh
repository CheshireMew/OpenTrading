#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$SCRIPT_DIR/.."
PYTHON_EXE="${PYTHON_EXE:-python}"

if [ -x "$PROJECT_ROOT/venv/bin/python" ]; then
    PYTHON_EXE="$PROJECT_ROOT/venv/bin/python"
fi

resolve_runtime_path() {
    local attribute="$1"
    (
        cd "$PROJECT_ROOT" &&
        "$PYTHON_EXE" -c "from config import settings; print(settings.${attribute})"
    )
}

read_pid_file() {
    local path="$1"
    if [ -f "$path" ]; then
        tr -d '[:space:]' < "$path"
    fi
}

stop_pid_file() {
    local path="$1"
    local pid
    pid="$(read_pid_file "$path")"
    rm -f "$path"
    if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
        return 0
    fi
    return 1
}

echo "Stopping Heimdall services..."

TEMP_DIR="$(resolve_runtime_path TEMP_DIR)"
BACKEND_PID_FILE="$TEMP_DIR/backend.pid"
BACKGROUND_PID_FILE="$TEMP_DIR/background.pid"
FRONTEND_PID_FILE="$TEMP_DIR/frontend.pid"

FRONTEND_STOPPED=0
BACKGROUND_STOPPED=0
BACKEND_STOPPED=0

if stop_pid_file "$FRONTEND_PID_FILE"; then
    FRONTEND_STOPPED=1
fi

if stop_pid_file "$BACKGROUND_PID_FILE"; then
    BACKGROUND_STOPPED=1
fi

if stop_pid_file "$BACKEND_PID_FILE"; then
    BACKEND_STOPPED=1
fi

if [ "$FRONTEND_STOPPED" -eq 1 ]; then
    echo "Frontend stopped."
else
    echo "Frontend was not running."
fi

if [ "$BACKGROUND_STOPPED" -eq 1 ]; then
    echo "Background runtime stopped."
else
    echo "Background runtime was not running."
fi

if [ "$BACKEND_STOPPED" -eq 1 ]; then
    echo "Backend stopped."
else
    echo "Backend was not running."
fi
