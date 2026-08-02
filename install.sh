#!/usr/bin/env bash
# OpenWallStreet local installer.  It intentionally never asks for or writes
# broker credentials, and it leaves execution locked.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USER_BIN="${HOME}/.local/bin"
CONFIG_DIR="${HOME}/.config/mmr"
UI_CONFIG_DIR="${HOME}/.config/openwallstreet"

say() { printf '\n==> %s\n' "$*"; }
fail() { printf 'error: %s\n' "$*" >&2; exit 1; }

command -v python3 >/dev/null || fail "Python 3.12 or newer is required."
python3 - <<'PY' || fail "Python 3.12 or newer is required."
import sys
raise SystemExit(sys.version_info < (3, 12))
PY

if ! command -v uv >/dev/null; then
    fail "uv is required. Install it with: python3 -m pip install --user uv"
fi

say "Creating protected configuration directories"
install -d -m 700 "$CONFIG_DIR" "$UI_CONFIG_DIR" "$USER_BIN"
if [ ! -f "$CONFIG_DIR/trader.yaml" ]; then
    install -m 600 "$ROOT/config_defaults/trader.yaml" "$CONFIG_DIR/trader.yaml"
    printf 'Created %s (choose paper or live during auth; execution is locked and the IB client is read-only).\n' "$CONFIG_DIR/trader.yaml"
else
    chmod 600 "$CONFIG_DIR/trader.yaml"
    printf 'Kept existing %s.\n' "$CONFIG_DIR/trader.yaml"
fi

say "Installing Python dependencies"
(cd "$ROOT" && uv sync --extra test --extra dev)

say "Installing local launcher"
ln -sfn "$ROOT/scripts/openwallstreet" "$USER_BIN/openwallstreet"

# A user-local command is safer than requiring sudo or modifying /usr/local.
# Make it discoverable in both login and interactive bash shells. Markers make
# this idempotent and avoid changing a user's PATH more than once.
ensure_path_file() {
    local file="$1"
    [ -f "$file" ] || touch "$file"
    if ! grep -Fq '# OpenWallStreet user commands' "$file"; then
        cat >> "$file" <<'PATH_BLOCK'

# OpenWallStreet user commands
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) export PATH="$HOME/.local/bin:$PATH" ;;
esac
PATH_BLOCK
    fi
}
ensure_path_file "$HOME/.profile"
ensure_path_file "$HOME/.bashrc"
if [ "$(basename "${SHELL:-}")" = zsh ]; then
    ensure_path_file "$HOME/.zshrc"
fi

printf '\nOpenWallStreet is installed in monitor-only mode.\n\n'
printf 'Next steps:\n'
printf '  1. Open a new terminal, or run: export PATH="%s:$PATH"\n' "$USER_BIN"
printf '  2. Run: openwallstreet auth\n'
printf '     This prompts locally for IB Gateway credentials, waits for MFA,\n'
printf '     asks you to choose paper or live monitoring, starts read-only services, then opens the terminal.\n\n'
printf 'No credentials were collected. Execution remains locked and the Gateway API stays read-only.\n'
