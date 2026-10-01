#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$BASE_DIR/scripts/i18n.sh"
IN_TERMINAL=false
if [[ "${1:-}" == --in-terminal ]]; then IN_TERMINAL=true; shift; fi
NONINTERACTIVE=false
for arg in "$@"; do
  case "$arg" in --status|-h|--help) NONINTERACTIVE=true ;; esac
done
if ! $NONINTERACTIVE && { [[ ! -t 0 ]] || [[ ! -t 1 ]]; }; then
  if $IN_TERMINAL; then
    echo "$(ui_text 'Не удалось получить терминал для меню.' 'Could not open a terminal for the menu.')" >&2
    exit 1
  fi
  if command -v konsole >/dev/null && [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
    exec konsole --separate -e /bin/bash "$BASE_DIR/rec.sh" --in-terminal "$@"
  fi
  echo "$(ui_text 'Для меню нужен терминал. Откройте Deck Recovery.desktop или запустите ./rec.sh в Konsole.' 'The menu needs a terminal. Open Deck Recovery.desktop or run ./rec.sh in Konsole.')" >&2
  exit 1
fi
exec python3 "$BASE_DIR/scripts/menu.py" "$@"
