#!/usr/bin/env bash
# Creates .env from .env.example with random secrets. Safe to re-run: it never
# overwrites an existing .env. The generated values are not printed; they are in
# .env (the sysadmin password is CKAN_SYSADMIN_PASSWORD).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [ -f .env ]; then
  echo ".env already exists; leaving it untouched."
  exit 0
fi

secret() { openssl rand -base64 33 | tr -d '/+=\n' | cut -c1-40; }

sed \
  -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(secret)|" \
  -e "s|^SESSION_SECRET=.*|SESSION_SECRET=$(secret)|" \
  -e "s|^JWT_SECRET=.*|JWT_SECRET=$(secret)|" \
  -e "s|^CKAN_SYSADMIN_PASSWORD=.*|CKAN_SYSADMIN_PASSWORD=$(secret)|" \
  .env.example > .env
chmod 600 .env
echo "Created .env with random secrets. Next: docker compose up -d --build"
