#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$BASE_DIR/terminal-ui.sh"

readonly DROPIN_DIR="/etc/systemd/logind.conf.d"
readonly DROPIN_FILE="${DROPIN_DIR}/zz-steamdeck-powerkey-suspend.conf"

usage() {
    cat <<'EOF'
Steam Deck power-button suspend patch

Usage:
  fix-steamdeck-power-button.sh [install|status|remove]

Commands:
  install  Make a short power-button press call system suspend (default).
  status   Show whether the patch is installed and the effective setting.
  remove   Remove the patch and restore SteamOS handling after a reboot.
EOF
}

effective_value() {
    systemd-analyze cat-config systemd/logind.conf 2>/dev/null \
        | awk -F= '/^[[:space:]]*HandlePowerKey[[:space:]]*=/{value=$2} END {
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
            print value
        }'
}

status() {
    if [[ -f "${DROPIN_FILE}" ]]; then
        echo "Patch file: installed (${DROPIN_FILE})"
    else
        echo "Patch file: not installed"
    fi

    local value
    value="$(effective_value)"
    echo "Effective HandlePowerKey: ${value:-default}"

    if [[ "${value}" == "suspend" ]]; then
        echo "Result: patched"
        return 0
    fi

    echo "Result: not patched"
    return 1
}

install_patch() {
    ui_header "$(ui_text "Кнопка питания → сон" "Power button → suspend")"
    local temporary
    temporary="$(mktemp)"
    trap 'ui_exit; rm -f "${temporary}"' EXIT

    printf '%s\n' '[Login]' 'HandlePowerKey=suspend' >"${temporary}"
    sudo install -D -m 0644 "${temporary}" "${DROPIN_FILE}"

    echo "Installed ${DROPIN_FILE}"
    status
    ui_done "$(ui_text "Настройка установлена. Перезагрузите Steam Deck для применения." "Setting installed. Reboot Steam Deck to apply.")"
}

remove_patch() {
    if [[ ! -e "${DROPIN_FILE}" ]]; then
        echo "Patch is already absent."
        return 0
    fi

    sudo rm -- "${DROPIN_FILE}"
    echo "Removed ${DROPIN_FILE}"
    ui_done "$(ui_text "Настройка удалена. Перезагрузите Steam Deck для применения." "Setting removed. Reboot Steam Deck to apply.")"
}

case "${1:-install}" in
    install|apply)
        install_patch
        ;;
    status)
        status
        ;;
    remove|uninstall)
        remove_patch
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac
