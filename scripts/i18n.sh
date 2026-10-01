# Shared locale selection. Also used by the launcher before a terminal exists.
I18N_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${REC_LANG:-}" != ru && "${REC_LANG:-}" != en ]]; then
  REC_LANG=$(python3 "$I18N_DIR/i18n.py")
fi
export REC_LANG
ui_text() { if [[ "$REC_LANG" == ru ]]; then printf '%s' "$1"; else printf '%s' "$2"; fi; }
