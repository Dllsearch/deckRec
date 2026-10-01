#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$BASE_DIR/terminal-ui.sh"
BACKUP="$DEFAULT_BACKUP"
DRY_RUN=false
YES=()
while (($#)); do
  case "$1" in
    --backup) BACKUP="${2:?Specify backup directory}"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    --yes) YES=(--noconfirm); shift ;;
    -h|--help)
      echo "Usage: $0 [--backup DIR] [--dry-run] [--yes]"
      echo 'Restore all packages offline. Equal/newer installed versions are skipped.'
      echo 'Home settings are preserved; configuration archives are not extracted automatically.'
      exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done
BACKUP="$(cd -- "$BACKUP" && pwd)"
[[ -f "$BACKUP/COMPLETE" ]] || { echo "Incomplete backup: $BACKUP" >&2; exit 1; }
read -r EXPECTED marker < "$BACKUP/COMPLETE"
[[ "$EXPECTED" =~ ^[1-9][0-9]*$ && "$marker" == packages ]] || { echo 'Invalid completion marker' >&2; exit 1; }
[[ $(wc -l < "$BACKUP/packages.tsv") -eq $EXPECTED && $(wc -l < "$BACKUP/SHA256SUMS") -eq $EXPECTED ]] || { echo 'Incomplete manifest' >&2; exit 1; }
command -v vercmp >/dev/null
command -v pacman >/dev/null
ui_header "$(ui_text "Восстановление пакетов" "Restoring packages")"
UI_LOG=$(mktemp /tmp/rec-packages.XXXXXX)
ui_step "$(ui_text "Проверка целостности архивов" "Verifying archive integrity")"
(cd -- "$BACKUP" && ui_run --checksums --total "$EXPECTED" --title "$(ui_text "Проверка SHA256 всех пакетов" "Checking SHA256 of all packages")" --log "$UI_LOG.sha256" -- sha256sum --check SHA256SUMS)
declare -A INSTALLED=() SEEN=()
installed_text=$(pacman -Q)
while read -r name version; do
  [[ -n "$name" ]] && INSTALLED["$name"]="$version"
done <<< "$installed_text"
PACKAGES=()
DEPS=()
CHECKED=0
SKIPPED=0
ui_step "$(ui_text "Сравнение версий пакетов" "Comparing package versions")"
while IFS=$'\t' read -r name version reason file; do
  [[ -n "$name" && -n "$version" && "$file" == packages/* && "$file" != *..* ]] || exit 1
  [[ ! -v "SEEN[$name]" ]] || { echo "Duplicate package: $name" >&2; exit 1; }
  SEEN["$name"]=1
  metadata=$(pacman -Qp -- "$BACKUP/$file")
  read -r archive_name archive_version <<< "$metadata"
  [[ "$archive_name" == "$name" && "$archive_version" == "$version" ]] || exit 1
  CHECKED=$((CHECKED + 1))
  ui_progress "$CHECKED" "$EXPECTED" "$(ui_text "Метаданные и версия: $name $version" "Metadata and version: $name $version")"
  if [[ -v "INSTALLED[$name]" ]] && (( $(vercmp "${INSTALLED[$name]}" "$version") >= 0 )); then
    SKIPPED=$((SKIPPED + 1))
    [[ -t 1 ]] || printf 'SKIP %s (installed %s, backup %s)\n' "$name" "${INSTALLED[$name]}" "$version"
    continue
  fi
  [[ -t 1 ]] || printf 'INSTALL %s %s\n' "$name" "$version"
  PACKAGES+=("$BACKUP/$file")
  if [[ ! -v "INSTALLED[$name]" && "$reason" == 1 ]]; then DEPS+=("$name"); fi
done < "$BACKUP/packages.tsv"
echo "Packages to install: ${#PACKAGES[@]}"
echo "$(ui_text "Уже актуальны: $SKIPPED; к установке: ${#PACKAGES[@]}" "Already current: $SKIPPED; to install: ${#PACKAGES[@]}")"
if $DRY_RUN; then ui_done "$(ui_text "Проверка завершена; система не изменялась." "Check complete; system unchanged.")"; exit 0; fi
if ((${#PACKAGES[@]} == 0)); then ui_done "$(ui_text "Все пакеты уже актуальны. Скрипт закончил работу." "All packages are current. Script finished.")"; exit 0; fi
if ((EUID != 0)); then
  exec sudo env REC_LANG="$REC_LANG" bash "$BASE_DIR/restore-system.sh" --backup "$BACKUP" "${YES[@]/--noconfirm/--yes}"
fi
ui_step "$(ui_text "Подготовка SteamOS и ключей pacman" "Preparing SteamOS and pacman keys")"
# Already running as root via sudo: equivalent to sudo steamos-devmode enable.
if command -v steamos-devmode >/dev/null; then ui_exec steamos-devmode enable; fi
if command -v steamos-readonly >/dev/null; then ui_exec steamos-readonly disable; fi
if [[ $(findmnt -n -o FSTYPE /) == btrfs ]]; then ui_exec btrfs filesystem resize max /; fi
ui_exec pacman-key --init
for ring in archlinux holo; do
  if [[ -f "/usr/share/pacman/keyrings/$ring.gpg" ]]; then ui_exec pacman-key --populate "$ring"; fi
done
# Expanded options retain the real DB/keyring, but no sync repositories.
# Missing dependencies fail locally instead of triggering network downloads.
OFFLINE_DIR=$(mktemp -d)
OFFLINE_CONFIG="$OFFLINE_DIR/pacman.conf"
trap 'ui_exit; rm -f -- "$OFFLINE_CONFIG" "$OFFLINE_CONFIG.all"; rmdir -- "$OFFLINE_DIR"' EXIT
pacman-conf > "$OFFLINE_CONFIG.all"
awk '/^\[/ && $0 != "[options]" {exit} {print}' "$OFFLINE_CONFIG.all" > "$OFFLINE_CONFIG"
ui_step "$(ui_text "Установка пакетов — дождитесь завершения транзакции" "Installing packages — wait for the transaction to finish")"
ui_exec pacman --config "$OFFLINE_CONFIG" -U --needed --overwrite '*' "${YES[@]}" -- "${PACKAGES[@]}"
if ((${#DEPS[@]})); then ui_exec pacman -D --asdeps -- "${DEPS[@]}"; fi
ui_run --title "$(ui_text "Сохранение на накопитель" "Flushing data to storage")" --log "$UI_LOG.sync" -- sync -f /
ui_done "$(ui_text "Пакеты восстановлены. Существующие настройки home сохранены. Скрипт закончил работу." "Packages restored. Existing home settings preserved. Script finished.")"
