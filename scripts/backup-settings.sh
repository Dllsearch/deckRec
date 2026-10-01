#!/usr/bin/env bash
set -euo pipefail
umask 077
((EUID != 0)) || { echo "Run without sudo to back up your own home." >&2; exit 1; }
BASE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$BASE_DIR/terminal-ui.sh"
DEFAULT_DEST="$DEFAULT_BACKUP"
DEST="${1:-$DEFAULT_DEST}"
mkdir -p "$DEST"
DEST="$(cd -- "$DEST" && pwd)"
exec 9>"$DEST/.home-backup.lock"
flock -n 9 || { echo "$(ui_text "Другой home-бэкап уже работает." "Another home backup is running.")" >&2; exit 1; }
ui_header "$(ui_text "Снимок настроек домашнего каталога" "Home settings snapshot")"
ui_step "$(ui_text "Подготовка списка файлов" "Preparing file list")"
ui_run --title "$(ui_text "Оценка объёма и подготовка исключений home" "Estimating home size and preparing exclusions")" --log "$DEST/home-preflight.log" -- python3 "$BASE_DIR/backup-options.py" home "$DEST"
python3 "$BASE_DIR/backup-empty-files.py" "$DEST" home-empty-files.tar.part
if command -v flatpak >/dev/null; then
  flatpak list --columns=application,arch,branch,origin,installation > "$DEST/flatpak-list.txt"
  flatpak remotes --show-details > "$DEST/flatpak-remotes.txt"
fi
# Exit 1 means a live file changed: retain archive but explicitly mark as not a consistent snapshot.
set +e
ui_run --allow-changed --title "$(ui_text "Архивация home" "Archiving home")" --log "$DEST/home-backup.log" --watch "$DEST/home-settings.tar.zst.part" -- tar --zstd --acls --xattrs -cvpf "$DEST/home-settings.tar.zst.part" \
  --exclude-from="$DEST/home-excludes.txt" -C "$HOME" \
  --null --verbatim-files-from -T "$DEST/home-files.list0"
status=$?
set -e
if ((status > 1)); then echo "Backup failed; see $DEST/home-backup.log" >&2; exit "$status"; fi
mv -- "$DEST/home-empty-files.tar.part" "$DEST/home-empty-files.tar"
mv -- "$DEST/home-settings.tar.zst.part" "$DEST/home-settings.tar.zst"
(cd "$DEST" && ui_run --hashes --total 2 --stdout-file "$DEST/HOME-SHA256SUMS" --title "$(ui_text "Вычисление SHA256 домашних архивов" "Hashing home archives")" --log "$DEST/home-checksum.log" -- sha256sum home-settings.tar.zst home-empty-files.tar)
ui_run --title "$(ui_text "Сохранение на накопитель" "Flushing data to storage")" --log "$DEST/home-sync.log" -- sync -f "$DEST"
printf '%s\n' "$status" > "$DEST/home-backup-status.txt"
if ((status == 1)); then
  ui_done "$(ui_text "Архив сохранён, но файлы менялись во время чтения. Проверьте $DEST/home-backup.log" "Archive saved, but files changed during reading. Check $DEST/home-backup.log")"
else
  ui_done "$(ui_text "Настройки сохранены: $DEST/home-settings.tar.zst. Скрипт закончил работу." "Settings saved: $DEST/home-settings.tar.zst. Script finished.")"
fi
if ((status == 1)); then exit 3; fi
exit "$status"
