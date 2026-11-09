#!/usr/bin/env bash
# Install everything the browser diagram needs, in one command:
#   - Python packages for the diagram API (src/backend/requirements.txt) in the project venv
#   - Node.js (pinned version, unpacked into .tools/node; no sudo, system untouched)
#     unless a recent enough Node is already installed
#   - frontend packages (src/frontend/package-lock.json) and the production build
#
# Usage:  bash scripts/setup_web.sh
# Safe to run again (e.g. after git pull) to update packages and rebuild.
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/src/frontend"
BACKEND_DIR="$PROJECT_ROOT/src/backend"
NODE_VERSION="v22.23.4"          # pinned; bump deliberately
NODE_MIN_MAJOR=20
TOOLS_DIR="$PROJECT_ROOT/.tools"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    sed -n '2,10p' "$0"
    exit 0
fi

# --- Python packages ---------------------------------------------------------------------
if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
elif [[ -x "$PROJECT_ROOT/venv/bin/python" ]]; then
    PYTHON_BIN="$PROJECT_ROOT/venv/bin/python"
elif [[ -x "$PROJECT_ROOT/../venv/bin/python" ]]; then
    PYTHON_BIN="$PROJECT_ROOT/../venv/bin/python"
else
    printf 'Creating project virtual environment...\n'
    if ! python3 -m venv "$PROJECT_ROOT/.venv" 2>/dev/null; then
        sudo apt-get install -y python3-venv
        python3 -m venv "$PROJECT_ROOT/.venv"
    fi
    PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
fi
printf 'Installing diagram API packages into %s...\n' "$(dirname "$(dirname "$PYTHON_BIN")")"
"$PYTHON_BIN" -m pip install --quiet -r "$BACKEND_DIR/requirements.txt"

# --- Node.js -----------------------------------------------------------------------------
node_major() { "$1" -v 2>/dev/null | sed -E 's/^v([0-9]+).*/\1/'; }

NODE_BIN=""
if command -v node >/dev/null 2>&1 && [[ "$(node_major node)" -ge "$NODE_MIN_MAJOR" ]]; then
    NODE_BIN="$(command -v node)"
    printf 'Using installed Node.js %s\n' "$(node -v)"
else
    case "$(uname -m)" in
        x86_64) NODE_ARCH="x64" ;;
        aarch64 | arm64) NODE_ARCH="arm64" ;;
        *) printf 'Unsupported CPU architecture: %s\n' "$(uname -m)" >&2; exit 1 ;;
    esac
    NODE_HOME="$TOOLS_DIR/node-$NODE_VERSION-linux-$NODE_ARCH"
    if [[ ! -x "$NODE_HOME/bin/node" ]]; then
        printf 'Downloading Node.js %s into %s...\n' "$NODE_VERSION" "$TOOLS_DIR"
        mkdir -p "$TOOLS_DIR"
        ARCHIVE="node-$NODE_VERSION-linux-$NODE_ARCH.tar.xz"
        curl -fsSL "https://nodejs.org/dist/$NODE_VERSION/$ARCHIVE" -o "$TOOLS_DIR/$ARCHIVE"
        curl -fsSL "https://nodejs.org/dist/$NODE_VERSION/SHASUMS256.txt" -o "$TOOLS_DIR/SHASUMS256.txt"
        (cd "$TOOLS_DIR" && grep " $ARCHIVE\$" SHASUMS256.txt | sha256sum -c -)
        tar -xJf "$TOOLS_DIR/$ARCHIVE" -C "$TOOLS_DIR"
        rm -f -- "${TOOLS_DIR:?}/${ARCHIVE:?}" "${TOOLS_DIR:?}/SHASUMS256.txt"
    fi
    NODE_BIN="$NODE_HOME/bin/node"
    printf 'Using project Node.js %s\n' "$("$NODE_BIN" -v)"
fi
export PATH="$(dirname "$NODE_BIN"):$PATH"

# --- Frontend packages and build ---------------------------------------------------------
printf 'Installing frontend packages...\n'
(cd "$FRONTEND_DIR" && npm ci --no-audit --no-fund --loglevel=error)
printf 'Building the frontend...\n'
(cd "$FRONTEND_DIR" && npm run build --silent)

printf '\nBrowser diagram ready. From %s start it with:\n  %s src/backend/server.py\n' \
    "$PROJECT_ROOT" "${PYTHON_BIN#"$PROJECT_ROOT/"}"
