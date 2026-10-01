#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$BASE_DIR/terminal-ui.sh"
DEFAULT_DEST="$DEFAULT_BACKUP"
DEST="${1:-$DEFAULT_DEST}"
mkdir -p "$DEST"
DEST="$(cd -- "$DEST" && pwd)"
if ((EUID != 0)); then exec sudo env REC_LANG="$REC_LANG" bash "$BASE_DIR/backup-system.sh" "$DEST"; fi
umask 077
exec 9>"$DEST/.system-backup.lock"
flock -n 9 || { echo "$(ui_text "Другой system-бэкап уже работает." "Another system backup is running.")" >&2; exit 1; }
ui_header "$(ui_text "Снимок системных настроек" "System settings snapshot")"
echo "$(ui_text "Пакеты сохраняются отдельно: ./scripts/backup-packages.py" "Packages are backed up separately: ./scripts/backup-packages.py")"
ui_run --title "$(ui_text "Оценка объёма и подготовка исключений системы" "Estimating system size and preparing exclusions")" --log "$DEST/system-preflight.log" -- python3 "$BASE_DIR/backup-options.py" system "$DEST"
ui_run --title "$(ui_text "Архивация выбранных системных папок" "Archiving selected system folders")" --log "$DEST/system-backup.log" --watch "$DEST/system-config.tar.zst.part" -- tar --zstd --acls --xattrs -cvpf "$DEST/system-config.tar.zst.part" --exclude-from="$DEST/system-excludes.txt" -C / --null --verbatim-files-from -T "$DEST/system-files.list0"
mv -- "$DEST/system-config.tar.zst.part" "$DEST/system-config.tar.zst"
(cd "$DEST" && ui_run --hashes --total 1 --stdout-file "$DEST/SYSTEM-SHA256SUMS" --title "$(ui_text "Вычисление SHA256 системного архива" "Hashing the system archive")" --log "$DEST/system-checksum.log" -- sha256sum system-config.tar.zst)
ui_run --title "$(ui_text "Сохранение на накопитель" "Flushing data to storage")" --log "$DEST/system-sync.log" -- sync -f "$DEST"
ui_done "$(ui_text "Системный архив готов: $DEST/system-config.tar.zst. Скрипт закончил работу." "System archive ready: $DEST/system-config.tar.zst. Script finished.")"
