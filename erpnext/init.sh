#!/usr/bin/env bash

set -euo pipefail

if (( EUID != 0 )); then
  echo "This script must be run as root." >&2
  exit 1
fi

############################################################

SERVICE_USERNAME="${SERVICE_USERNAME:-erpnext}"
SERVICE_HOME="/srv/$SERVICE_USERNAME"

export DB_PASSWORD="${DB_PASSWORD:-$(openssl rand -hex 32)}"
export GUNICORN_WORKERS="${GUNICORN_WORKERS:-$(( $(nproc) * 2 + 1 ))}"
export SITE="${SITE:?SITE environment variable cannot be empty}"

############################################################

# Create user
if id "$SERVICE_USERNAME" &>/dev/null; then
  echo "User '$SERVICE_USERNAME' already exists!"
  exit 1
else
  useradd \
    --system \
    --add-subids-for-system \
    --user-group \
    --shell /usr/sbin/nologin \
    --home-dir "$SERVICE_HOME" \
    --create-home \
    "$SERVICE_USERNAME"

  loginctl enable-linger "$SERVICE_USERNAME"
fi

############################################################

# Generate .env
env_path="$SERVICE_HOME/.env"
create_env_file=1

if [[ -e "$env_path" ]]; then
    read -r -p "'$env_path' already exists. Overwrite? (y/N): " answer
    if [[ "$answer" != [yY] ]]; then
      create_env_file=0
    fi
fi

if (( create_env_file )); then
  # shellcheck disable=SC2016
  envsubst '$DB_PASSWORD $GUNICORN_WORKERS $SITE' < template.env > "$env_path"
  chmod 600 "$env_path"
fi

############################################################

# Copy files
cp -r ./frappe_docker "$SERVICE_HOME"
cp apps.json "$SERVICE_HOME"

############################################################

# Correct owner:group
chown -R "$SERVICE_USERNAME:$SERVICE_USERNAME" \
  "$SERVICE_HOME/frappe_docker" \
  "$SERVICE_HOME/apps.json" \
  "$SERVICE_HOME/.env"