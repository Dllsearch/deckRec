source "$BASE_DIR/i18n.sh"
# Shared terminal presentation. Source after BASE_DIR has been set.
UI_STARTED=$SECONDS
ui_header() { printf '\n[ DECK / REC ] %s\n' "$*"; }
ui_step() { printf '\n[>] %s\n' "$*"; }
ui_done() { printf "$(ui_text '\n[OK] %s · %s сек.\n' '\n[OK] %s · %s s.\n')" "$*" "$((SECONDS - UI_STARTED))"; }
ui_exit() {
  local code=$?
  if ((code)); then printf "$(ui_text '\n[!] Работа не завершена (код %s). Проверьте ошибку выше.\n' '\n[!] Operation incomplete (exit code %s). Check the error above.\n')" "$code" >&2; fi
}
trap ui_exit EXIT
ui_run() { python3 "$BASE_DIR/terminal-ui.py" "$@"; }
ui_progress() {
  local done=$1 total=$2 detail=${3:-} filled percent bar line width
  [[ -t 1 ]] || return 0
  percent=$((done * 100 / total)); filled=$((percent / 5))
  printf -v bar '%*s' "$filled" ''; bar=${bar// /#}
  printf -v line "$(ui_text '[%-20s] %3s%% %s/%s · %s сек. · %s' '[%-20s] %3s%% %s/%s · %s s. · %s')" "$bar" "$percent" "$done" "$total" "$((SECONDS - UI_STARTED))" "$detail"
  width=${COLUMNS:-80}
  printf '\r\033[2K%.*s' "$((width - 1))" "$line"
  ((done != total)) || printf '\n'
}

REC_ROOT="$BASE_DIR"
[[ "${BASE_DIR##*/}" != scripts ]] || REC_ROOT="$(dirname -- "$BASE_DIR")"
DEFAULT_BACKUP="$REC_ROOT/backups/current"
[[ ! -f "$REC_ROOT/packages.tsv" ]] || DEFAULT_BACKUP="$REC_ROOT"

# Commands needing interactive stdin (pacman/sudo) keep their native output.
ui_exec() {
  printf '\n[CMD] '
  if (($# > 16)); then
    printf '%q ' "${@:1:8}"
    printf "$(ui_text '… [ещё %s аргументов; список файлов показан pacman]\n' '… [%s more arguments; pacman displays the file list]\n')" "$(($# - 8))"
  else
    printf '%q ' "$@"
    printf '\n'
  fi
  "$@"
}
