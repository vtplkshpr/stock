#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

show_help() {
    cat <<'EOF'
Set up the stock database on Ubuntu/Debian.

Usage:
  bash scripts/setup_database.sh

The script requests sudo when needed, installs MySQL Server if no MySQL or
MariaDB server is installed, creates the database and application user, installs
mysql-connector-python in a project virtual environment, and creates the tables.

Optional environment variables:
  MYSQL_DATABASE  Database name (default: stock_market)
  MYSQL_USER      Application user (default: stock_app)
  MYSQL_HOST      Connection host (default: localhost)
  MYSQL_PORT      Connection port (default: 3306)
  MYSQL_PASSWORD  Optional app password; otherwise a random one is generated
EOF
}

case "${1:-}" in
    -h|--help)
        show_help
        exit 0
        ;;
    "")
        ;;
    *)
        printf 'Unknown argument: %s\n' "$1" >&2
        show_help >&2
        exit 2
        ;;
esac

if [[ "$(. /etc/os-release && printf '%s' "$ID")" != "ubuntu" && "$(. /etc/os-release && printf '%s' "$ID_LIKE")" != *debian* ]]; then
    printf 'This setup script supports Ubuntu and Debian-based systems only.\n' >&2
    exit 1
fi

DATABASE="${MYSQL_DATABASE:-stock_market}"
APP_USER="${MYSQL_USER:-stock_app}"
DB_HOST="${MYSQL_HOST:-localhost}"
DB_PORT="${MYSQL_PORT:-3306}"
APP_PASSWORD="${MYSQL_PASSWORD:-}"

if [[ ! "$DATABASE" =~ ^[A-Za-z0-9_]+$ || ! "$APP_USER" =~ ^[A-Za-z0-9_]+$ ]]; then
    printf 'Database and user names may contain only letters, digits, and underscores.\n' >&2
    exit 1
fi
if [[ ! "$DB_PORT" =~ ^[0-9]+$ ]]; then
    printf 'MYSQL_PORT must be a number.\n' >&2
    exit 1
fi

if (( EUID == 0 )); then
    SUDO=()
else
    if ! command -v sudo >/dev/null 2>&1; then
        printf 'sudo is required to install/start the database server and create its user.\n' >&2
        exit 1
    fi
    SUDO=(sudo)
    "${SUDO[@]}" -v
fi

is_installed() {
    dpkg-query -W -f='${db:Status-Status}' "$1" 2>/dev/null | grep -qx installed
}

if is_installed mariadb-server; then
    SERVICE_NAME=mariadb
elif is_installed mysql-server || is_installed mysql-server-8.0; then
    SERVICE_NAME=mysql
else
    printf 'No MySQL/MariaDB server package found; installing mysql-server...\n'
    "${SUDO[@]}" apt-get update
    "${SUDO[@]}" env DEBIAN_FRONTEND=noninteractive apt-get install -y mysql-server
    SERVICE_NAME=mysql
fi

if ! systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    if ! "${SUDO[@]}" systemctl enable --now "$SERVICE_NAME" >/dev/null 2>&1; then
        if ! command -v service >/dev/null 2>&1 || ! "${SUDO[@]}" service "$SERVICE_NAME" start; then
            printf 'Could not start %s. Check that systemd or the service command is available.\n' "$SERVICE_NAME" >&2
            exit 1
        fi
    fi
fi

if command -v mariadb >/dev/null 2>&1; then
    ADMIN_CLIENT=mariadb
elif command -v mysql >/dev/null 2>&1; then
    ADMIN_CLIENT=mysql
else
    printf 'MySQL/MariaDB command-line client was not found after installation.\n' >&2
    exit 1
fi

if [[ -z "$APP_PASSWORD" ]]; then
    APP_PASSWORD="$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')"
fi
if [[ ! "$APP_PASSWORD" =~ ^[A-Za-z0-9_-]{16,}$ ]]; then
    printf 'MYSQL_PASSWORD must be at least 16 characters using letters, digits, _ or -.\n' >&2
    exit 1
fi

printf 'Creating database and application user...\n'
"${SUDO[@]}" "$ADMIN_CLIENT" --protocol=socket <<SQL
CREATE DATABASE IF NOT EXISTS \`${DATABASE}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${APP_USER}'@'localhost' IDENTIFIED BY '${APP_PASSWORD}';
ALTER USER '${APP_USER}'@'localhost' IDENTIFIED BY '${APP_PASSWORD}';
GRANT ALL PRIVILEGES ON \`${DATABASE}\`.* TO '${APP_USER}'@'localhost';
SQL

if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
elif [[ -x "$PROJECT_ROOT/venv/bin/python" ]]; then
    PYTHON_BIN="$PROJECT_ROOT/venv/bin/python"
elif [[ -x "$PROJECT_ROOT/../venv/bin/python" ]]; then
    PYTHON_BIN="$PROJECT_ROOT/../venv/bin/python"
else
    printf 'Creating project virtual environment...\n'
    "${SUDO[@]}" apt-get install -y python3-venv
    python3 -m venv "$PROJECT_ROOT/.venv"
    PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
fi

printf 'Installing Python MySQL connector...\n'
"$PYTHON_BIN" -m pip install mysql-connector-python

CONFIG_FILE="$PROJECT_ROOT/.env"
umask 077
printf 'MYSQL_HOST=%s\nMYSQL_PORT=%s\nMYSQL_USER=%s\nMYSQL_PASSWORD=%s\nMYSQL_DATABASE=%s\n' \
    "$DB_HOST" "$DB_PORT" "$APP_USER" "$APP_PASSWORD" "$DATABASE" > "$CONFIG_FILE"
chmod 600 "$CONFIG_FILE"

export MYSQL_HOST="$DB_HOST"
export MYSQL_PORT="$DB_PORT"
export MYSQL_USER="$APP_USER"
export MYSQL_PASSWORD="$APP_PASSWORD"
export MYSQL_DATABASE="$DATABASE"

printf 'Creating database tables...\n'
"$PYTHON_BIN" "$SCRIPT_DIR/init_database.py" --skip-create-database
printf '\nDatabase setup complete. Private connection settings saved to:\n%s\n' "$CONFIG_FILE"