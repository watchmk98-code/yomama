#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
CURRENT_DIR="$(pwd -P)"
HAS_ISSUES=0

pass() {
  printf '[PASS] %s\n' "$1"
}

warn() {
  printf '[WARN] %s\n' "$1"
}

printf 'YOMAMA pre-change check\n'
printf 'project root: %s\n' "$PROJECT_ROOT"
printf 'terminal cwd: %s\n' "$CURRENT_DIR"

if [[ "$CURRENT_DIR" == "$PROJECT_ROOT" ]]; then
  pass "Terminal is in the correct project folder."
else
  warn "Terminal is not in project root. Run: cd \"$PROJECT_ROOT\""
  HAS_ISSUES=1
fi

LISTENER_PID="$(lsof -tiTCP:3000 -sTCP:LISTEN 2>/dev/null | head -n 1 || true)"
if [[ -z "$LISTENER_PID" ]]; then
  warn "No local server is listening on 127.0.0.1:3000."
  warn "Start it from project root: python3 -m http.server 3000 --bind 127.0.0.1"
  HAS_ISSUES=1
else
  SERVER_CWD="$(lsof -a -p "$LISTENER_PID" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1 || true)"
  printf 'server pid: %s\n' "$LISTENER_PID"
  printf 'server cwd: %s\n' "${SERVER_CWD:-unknown}"
  if [[ -n "$SERVER_CWD" && "$SERVER_CWD" == "$PROJECT_ROOT" ]]; then
    pass "localhost:3000 is serving this exact project."
  else
    warn "localhost:3000 is serving a different folder."
    warn "Restart server from: $PROJECT_ROOT"
    HAS_ISSUES=1
  fi
fi

if command -v node >/dev/null 2>&1; then
  if node --check "$PROJECT_ROOT/app.js" >/dev/null 2>&1; then
    pass "app.js syntax check passed."
  else
    warn "app.js syntax check failed."
    HAS_ISSUES=1
  fi
fi

printf 'browser note: use Cmd+Shift+R after JS/CSS edits.\n'

if [[ "$HAS_ISSUES" -eq 0 ]]; then
  printf 'status: READY\n'
  exit 0
fi

printf 'status: NOT READY (fix warnings above)\n'
exit 1
