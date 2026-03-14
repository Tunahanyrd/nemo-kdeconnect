#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR=$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)

EXTENSIONS_DIR_DEFAULT="${XDG_DATA_HOME:-$HOME/.local/share}/nemo-python/extensions"
EXTENSIONS_DIR="${NEMO_EXTENSIONS_DIR:-$EXTENSIONS_DIR_DEFAULT}"
LOCALE_SOURCE_DIR="${REPO_DIR}/src/nemo-kdeconnect/locale"
LOCALE_TARGET_DIR="${EXTENSIONS_DIR}/nemo-kdeconnect/locale"
PLUGIN_TARGET="${EXTENSIONS_DIR}/nemo-kdeconnect.py"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/nemo-kdeconnect"
CONFIG_FILE="${CONFIG_DIR}/config.json"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/nemo-kdeconnect"
STATE_FILE="${CACHE_DIR}/sidebar_state.json"
BOOKMARKS_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/gtk-3.0/bookmarks"

RESTART_NEMO=0
CONFIGURE_KDECONNECT_HANDLER=1
LANGUAGE_OVERRIDE=""
CLEAR_LANGUAGE=0
UNINSTALL=0

print_usage() {
    cat <<'EOF'
Usage: sh scripts/install.sh [options]

Options:
    --uninstall                Remove extension files and managed settings
  --restart-nemo             Restart Nemo after install
  --language <locale>        Force extension language (e.g. tr, en, de, tr_TR.UTF-8)
  --clear-language           Remove forced language and use system locale again
  --skip-kdeconnect-handler  Do not set kdeconnect:// URI handler
  -h, --help                 Show this help
EOF
}

validate_language() {
    language_value=$1
    case "$language_value" in
        "")
            echo "error: --language value cannot be empty"
            exit 1
            ;;
        *[!A-Za-z0-9._@-]*)
            echo "error: invalid language value '$language_value'"
            echo "allowed characters: letters, numbers, dot, underscore, dash, at"
            exit 1
            ;;
    esac
}

configure_kdeconnect_handler() {
    if [ "${CONFIGURE_KDECONNECT_HANDLER}" -eq 0 ]; then
        return
    fi

    if ! command -v xdg-mime >/dev/null 2>&1; then
        echo "warning: xdg-mime is missing, skipping kdeconnect:// handler setup"
        return
    fi

    handler_desktop=""
    for candidate in org.kde.kdeconnect.handler.desktop kdeconnect-handler.desktop; do
        if [ -f "$HOME/.local/share/applications/$candidate" ] || [ -f "/usr/share/applications/$candidate" ]; then
            handler_desktop="$candidate"
            break
        fi
    done

    if [ -z "$handler_desktop" ]; then
        echo "warning: KDE Connect handler desktop entry was not found, skipping URI handler setup"
        return
    fi

    xdg-mime default "$handler_desktop" x-scheme-handler/kdeconnect >/dev/null 2>&1 || true
    current_default=$(xdg-mime query default x-scheme-handler/kdeconnect 2>/dev/null || true)

    if [ "$current_default" = "$handler_desktop" ]; then
        echo "Configured kdeconnect:// URI handler: $handler_desktop"
    else
        echo "warning: failed to set kdeconnect:// handler (current: ${current_default:-none})"
    fi
}

configure_language_override() {
    if [ "${CLEAR_LANGUAGE}" -eq 1 ]; then
        rm -f "$CONFIG_FILE"
        echo "Cleared language override (system locale will be used)."
        return
    fi

    if [ -z "$LANGUAGE_OVERRIDE" ]; then
        return
    fi

    install -d "$CONFIG_DIR"
    printf '{\n  "language": "%s"\n}\n' "$LANGUAGE_OVERRIDE" > "$CONFIG_FILE"
    echo "Configured extension language: $LANGUAGE_OVERRIDE"
}

cleanup_managed_sidebar_bookmarks() {
    if [ ! -f "${STATE_FILE}" ] || [ ! -f "${BOOKMARKS_FILE}" ]; then
        return
    fi

    if ! command -v python3 >/dev/null 2>&1; then
        echo "warning: python3 is missing, cannot cleanup managed sidebar bookmarks automatically"
        return
    fi

    python3 - "${STATE_FILE}" "${BOOKMARKS_FILE}" <<'PY'
import json
import sys

state_file = sys.argv[1]
bookmarks_file = sys.argv[2]

try:
    with open(state_file, "r", encoding="utf-8") as file_handle:
        state = json.load(file_handle)
except (OSError, ValueError, TypeError):
    sys.exit(0)

managed_uris = state.get("managed_uris", []) if isinstance(state, dict) else []
if not isinstance(managed_uris, list) or not managed_uris:
    sys.exit(0)

managed_uri_set = {uri for uri in managed_uris if isinstance(uri, str)}
if not managed_uri_set:
    sys.exit(0)

try:
    with open(bookmarks_file, "r", encoding="utf-8") as file_handle:
        lines = [line.rstrip("\n") for line in file_handle]
except OSError:
    sys.exit(0)

updated_lines = []
for line in lines:
    if not line.strip():
        continue
    uri = line.split(" ", 1)[0].strip()
    if uri in managed_uri_set:
        continue
    updated_lines.append(line)

try:
    with open(bookmarks_file, "w", encoding="utf-8") as file_handle:
        if updated_lines:
            file_handle.write("\n".join(updated_lines))
            file_handle.write("\n")
except OSError:
    pass
PY
}

uninstall_extension() {
    echo "Uninstalling nemo-kdeconnect from: ${EXTENSIONS_DIR}"

    cleanup_managed_sidebar_bookmarks

    rm -f "${PLUGIN_TARGET}"
    rm -rf "${EXTENSIONS_DIR}/nemo-kdeconnect"

    if [ -d "${EXTENSIONS_DIR}/__pycache__" ]; then
        find "${EXTENSIONS_DIR}/__pycache__" -type f -name 'nemo-kdeconnect*.pyc' -delete >/dev/null 2>&1 || true
        rmdir "${EXTENSIONS_DIR}/__pycache__" >/dev/null 2>&1 || true
    fi

    rm -f "${STATE_FILE}"
    rm -f "${CONFIG_FILE}"
    rmdir "${CACHE_DIR}" >/dev/null 2>&1 || true
    rmdir "${CONFIG_DIR}" >/dev/null 2>&1 || true

    echo "Uninstallation completed. kdeconnect:// URI handler setting was left unchanged."
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --uninstall)
            UNINSTALL=1
            shift
            ;;
        --restart-nemo)
            RESTART_NEMO=1
            shift
            ;;
        --language)
            if [ "$#" -lt 2 ]; then
                echo "error: --language requires a value"
                exit 1
            fi
            validate_language "$2"
            LANGUAGE_OVERRIDE="$2"
            shift 2
            ;;
        --clear-language)
            CLEAR_LANGUAGE=1
            shift
            ;;
        --skip-kdeconnect-handler)
            CONFIGURE_KDECONNECT_HANDLER=0
            shift
            ;;
        -h|--help)
            print_usage
            exit 0
            ;;
        *)
            echo "error: unknown argument '$1'"
            print_usage
            exit 1
            ;;
    esac
done

if [ "$CLEAR_LANGUAGE" -eq 1 ] && [ -n "$LANGUAGE_OVERRIDE" ]; then
    echo "error: --language and --clear-language cannot be used together"
    exit 1
fi

if [ "${UNINSTALL}" -eq 1 ] && { [ -n "${LANGUAGE_OVERRIDE}" ] || [ "${CLEAR_LANGUAGE}" -eq 1 ]; }; then
    echo "error: --uninstall cannot be combined with --language or --clear-language"
    exit 1
fi

if [ "${UNINSTALL}" -eq 1 ]; then
    uninstall_extension

    if [ "${RESTART_NEMO}" -eq 1 ]; then
        nemo -q >/dev/null 2>&1 || true
    fi

    exit 0
fi

echo "Installing nemo-kdeconnect into: ${EXTENSIONS_DIR}"
install -d "${EXTENSIONS_DIR}"
install -m 0644 "${REPO_DIR}/src/nemo-kdeconnect.py" "${PLUGIN_TARGET}"

rm -rf "${EXTENSIONS_DIR}/nemo-kdeconnect"
install -d "${LOCALE_TARGET_DIR}"

MSGFMT_BIN=""
if command -v msgfmt >/dev/null 2>&1; then
    MSGFMT_BIN=$(command -v msgfmt)
else
    echo "warning: msgfmt not found, .mo files will not be generated (install gettext)."
fi

LOCALE_PREFIX="${LOCALE_SOURCE_DIR}/"
find "${LOCALE_SOURCE_DIR}" -type f -name '*.po' | while IFS= read -r po_file; do
    relative_path=${po_file#"${LOCALE_PREFIX}"}
    lang_dir=$(dirname "${relative_path}")
    target_dir="${LOCALE_TARGET_DIR}/${lang_dir}"

    install -d "${target_dir}"
    install -m 0644 "${po_file}" "${target_dir}/nemo-kdeconnect.po"

    if [ -n "${MSGFMT_BIN}" ]; then
        "${MSGFMT_BIN}" -f -o "${target_dir}/nemo-kdeconnect.mo" "${po_file}"
    fi
done

configure_kdeconnect_handler
configure_language_override

if [ "${RESTART_NEMO}" -eq 1 ]; then
    nemo -q >/dev/null 2>&1 || true
fi

echo "Installation completed. Restart Nemo with: nemo -q && nemo"
