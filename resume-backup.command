#!/bin/zsh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_FILE="$PROJECT_DIR/YOMAMA LANDING PAGE PROTOTYPE.code-workspace"
PORT=3000
URL="http://localhost:${PORT}/index.html?ts=$(date +%s)"
LOG_FILE="$PROJECT_DIR/.local3000.log"
PID_FILE="$PROJECT_DIR/.local3000.pid"

listener_info="$(lsof -nP -iTCP:${PORT} -sTCP:LISTEN -Fpc 2>/dev/null || true)"
existing_pid="$(printf "%s\n" "${listener_info}" | awk '/^p/{print substr($0,2); exit}')"
existing_cmd="$(printf "%s\n" "${listener_info}" | awk '/^c/{print substr($0,2); exit}')"
known_pid="$(cat "${PID_FILE}" 2>/dev/null || true)"

if [[ -n "${existing_pid}" ]]; then
  if [[ -n "${known_pid}" && "${existing_pid}" == "${known_pid}" ]]; then
    if ! kill "${existing_pid}" 2>/dev/null; then
      echo "Could not stop the previous server on port ${PORT}."
      echo "Close the app using port ${PORT}, then run this launcher again."
      exit 1
    fi
    sleep 1
  elif [[ "${existing_cmd}" == "Python" || "${existing_cmd}" == "python" || "${existing_cmd}" == "python3" ]]; then
    if ! kill "${existing_pid}" 2>/dev/null; then
      echo "Port ${PORT} is busy, and this launcher cannot stop it automatically."
      echo "Close the app using port ${PORT}, then run this launcher again."
      exit 1
    fi
    sleep 1
  else
    echo "Port ${PORT} is already in use."
    echo "If this is your old local server, stop it first and run this again."
    exit 1
  fi
fi

{ nohup python3 -m http.server "${PORT}" --directory "${PROJECT_DIR}" >"${LOG_FILE}" 2>&1 < /dev/null & } 2>/dev/null
server_pid="$!"
echo "${server_pid}" > "${PID_FILE}"
sleep 1

if ! kill -0 "${server_pid}" 2>/dev/null; then
  echo "Failed to start local server on port ${PORT}."
  echo "Check ${LOG_FILE} for details."
  exit 1
fi

if [[ -f "${WORKSPACE_FILE}" ]]; then
  open -a "Visual Studio Code" "${WORKSPACE_FILE}" >/dev/null 2>&1 || open "${WORKSPACE_FILE}" >/dev/null 2>&1 || true
else
  open -a "Visual Studio Code" "${PROJECT_DIR}" >/dev/null 2>&1 || open "${PROJECT_DIR}" >/dev/null 2>&1 || true
fi

open -a "Visual Studio Code" \
  "${PROJECT_DIR}/index.html" \
  "${PROJECT_DIR}/styles.css" \
  "${PROJECT_DIR}/app.js" \
  >/dev/null 2>&1 || true

open "${URL}" >/dev/null 2>&1 || true

echo ""
echo "Backup project is live:"
echo "Folder: ${PROJECT_DIR}"
echo "URL:    http://localhost:${PORT}/index.html"
echo ""
echo "Tip: double-click this file anytime: resume-backup.command"
