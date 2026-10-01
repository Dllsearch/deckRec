#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$BASE_DIR/terminal-ui.sh"
WITH_SETTINGS=false
PACKAGE_ARGS=()
SETTINGS_ARGS=()
while (($#)); do
  case "$1" in
    --with-settings) WITH_SETTINGS=true; shift ;;
    --backup)
      PACKAGE_ARGS+=(--backup "${2:?Specify backup directory}")
      SETTINGS_ARGS+=(--backup "$2"); shift 2 ;;
    --yes) PACKAGE_ARGS+=(--yes); shift ;;
    -h|--help)
      echo "Usage: $0 [--backup DIR] [--yes] [--with-settings]"
      echo 'Install packages; optionally restore missing home files and user Flatpak data.'
      exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done
if $WITH_SETTINGS && ((EUID == 0)); then echo 'Use without sudo for home restoration.' >&2; exit 1; fi
ui_header "$(ui_text "Полное восстановление" "Full restore")"
bash "$BASE_DIR/restore-system.sh" "${PACKAGE_ARGS[@]}"
if $WITH_SETTINGS; then bash "$BASE_DIR/restore-settings.sh" "${SETTINGS_ARGS[@]}"; fi

ui_done "$(ui_text "Все выбранные этапы завершены. Можно закрыть терминал." "All selected stages completed. You can close the terminal.")"
