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
export NGINX_PROXY_HOSTS="${NGINX_PROXY_HOSTS:?NGINX_PROXY_HOSTS environment variable cannot be empty}"

create_user() {
  if id "$SERVICE_USERNAME" &>/dev/null; then
    echo "User '$SERVICE_USERNAME' already exists!"
    exit 1
  else
    useradd \
      --user-group \
      --shell /usr/sbin/nologin \
      --home-dir "$SERVICE_HOME" \
      --create-home \
      "$SERVICE_USERNAME"

    loginctl enable-linger "$SERVICE_USERNAME"
  fi
}

generate_env() {
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
    envsubst '$DB_PASSWORD $GUNICORN_WORKERS $FRAPPE_SITE_NAME_HEADER $NGINX_PROXY_HOSTS' < template.env > "$env_path"
    chmod 600 "$env_path"
  fi
}

copy_files() {
  cp -r ./frappe_docker "$SERVICE_HOME"
  cp apps.json "$SERVICE_HOME"
  correct_owner
}

correct_owner() {
  chown -R "$SERVICE_USERNAME:$SERVICE_USERNAME" \
    "$SERVICE_HOME/frappe_docker" \
    "$SERVICE_HOME/apps.json" \
    "$SERVICE_HOME/.env"
}

init() {
  create_user
  generate_env
  copy_files
}

usage() {
  cat <<EOF
Usage: $0 [OPTIONS]

Options:
  -h, --help
  --create-user
  --generate-env
  --copy-files

With no options, all functions are executed.
EOF
}

main() {
  local -a functions=()
  local function
  local arg

  for arg in "$@"; do
    if [[ "$arg" == "--help" || "$arg" == "-h" ]]; then
      usage
      return 0
    fi
  done

  for arg in "$@"; do
    case "$arg" in
      --create-user)
        functions+=(create_user)
        ;;
      --generate-env)
        functions+=(generate_env)
        ;;
      --copy-files)
        functions+=(copy_files)
        ;;
      *)
        printf 'Unknown option: %s\n\n' "$arg" >&2
        usage >&2
        exit 1
        ;;
    esac
  done

  if (( ${#functions[@]} == 0 )); then
    init
  fi

  for function in "${functions[@]}"; do
    "$function"
  done
}

main "$@"
