#!/usr/bin/env bash

set -euo pipefail

export DB_PASSWORD=${DB_PASSWORD:-"$(openssl rand -hex 32)"}
export GUNICORN_WORKERS=${GUNICORN_WORKERS:-$(( $(nproc) * 2 + 1 ))}
export SITE=${SITE:?SITE environment variable cannot be empty}

if [[ -e .env ]]; then
    read -r -p "File exists. Overwrite? (y/N): " answer
    [[ "$answer" == [yY] ]] || exit 0
fi

# shellcheck disable=SC2016
envsubst '$DB_PASSWORD $GUNICORN_WORKERS $SITE' < template.env > .env

chmod 600 .env
