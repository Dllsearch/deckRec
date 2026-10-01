#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$BASE_DIR/terminal-ui.sh"
BACKUP="$DEFAULT_BACKUP"
while (($#)); do
  case "$1" in
    --backup) BACKUP="${2:?Specify backup directory}"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [--backup DIR]"
      echo 'Restore missing home files only, preserving all existing files. Run as your regular user.'
      exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done
((EUID != 0)) || { echo 'Run as the home owner, without sudo.' >&2; exit 1; }
BACKUP="$(cd -- "$BACKUP" && pwd)"
ui_header "$(ui_text "Восстановление отсутствующих файлов home" "Restoring missing home files")"
UI_LOG=$(mktemp /tmp/rec-settings.XXXXXX)
(cd "$BACKUP" && ui_run --checksums --total "$(wc -l < "$BACKUP/HOME-SHA256SUMS")" --title "$(ui_text "Проверка контрольных сумм" "Verifying checksums")" --log "$UI_LOG.sha256" -- sha256sum --check HOME-SHA256SUMS)
ui_run --title "$(ui_text "Распаковка настроек: существующие файлы сохраняются" "Extracting settings: existing files preserved")" --log "$UI_LOG.extract" -- tar --zstd --acls --xattrs --skip-old-files --no-same-owner \
  -xvpf "$BACKUP/home-settings.tar.zst" -C "$HOME"
if [[ -f "$BACKUP/home-empty-files.tar" ]]; then
  ui_run --title "$(ui_text "Восстановление пустых файлов Steam" "Restoring empty Steam placeholders")" --log "$UI_LOG.empty" -- tar --skip-old-files --no-same-owner -xvpf "$BACKUP/home-empty-files.tar" -C "$HOME"
fi
ui_run --title "$(ui_text "Сохранение на накопитель" "Flushing data to storage")" --log "$UI_LOG.sync" -- sync -f "$HOME"
ui_done "$(ui_text "Файлы восстановлены. Существующие настройки сохранены. Скрипт закончил работу." "Files restored. Existing settings preserved. Script finished.")"
