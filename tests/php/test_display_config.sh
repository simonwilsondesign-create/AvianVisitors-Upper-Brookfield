#!/usr/bin/env bash
set -euo pipefail

repo=$(cd "$(dirname "$0")/../.." && pwd)
temporary=$(mktemp -d)
port=18991
cleanup() {
  kill "${server_pid:-}" 2>/dev/null || true
  rm -rf "$temporary"
}
trap cleanup EXIT

AV_DISPLAY_SETTINGS_PATH="$temporary/settings.json" \
AV_DISPLAY_SETTINGS_TOKEN='test-display-token' \
php -S "127.0.0.1:$port" -t "$repo" >/dev/null 2>&1 &
server_pid=$!
for _ in {1..20}; do
  curl --silent --fail "http://127.0.0.1:$port/avian/api/display-config.php" >/dev/null && break
  sleep 0.1
done

get=$(curl --silent --write-out '\n%{http_code}' "http://127.0.0.1:$port/avian/api/display-config.php")
test "${get##*$'\n'}" = 200
node -e 'const x=JSON.parse(process.argv[1]); if(x.settings.default_hours!==1 || x.settings.timezone!=="Australia/Brisbane") process.exit(1)' "${get%$'\n'*}"

denied=$(curl --silent --output /dev/null --write-out '%{http_code}' -X POST \
  -H 'Content-Type: application/json' -H 'Authorization: Bearer arbitrary' --data '{"theme":"dark"}' \
  "http://127.0.0.1:$port/avian/api/display-config.php")
test "$denied" = 403

cross_origin=$(curl --silent --output /dev/null --write-out '%{http_code}' -X POST \
  -H 'Content-Type: application/json' -H 'Origin: https://attacker.example' \
  -H 'X-Avian-Display-Token: test-display-token' --data '{"theme":"dark"}' \
  "http://127.0.0.1:$port/avian/api/display-config.php")
test "$cross_origin" = 403

written=$(curl --silent --write-out '\n%{http_code}' -X POST \
  -H 'Content-Type: application/json' -H 'X-Avian-Display-Token: test-display-token' \
  --data '{"theme":"dark","labels":false,"expected_revision":0}' \
  "http://127.0.0.1:$port/avian/api/display-config.php")
test "${written##*$'\n'}" = 200
node -e 'const x=JSON.parse(process.argv[1]); if(!x.ok || x.settings.theme!=="dark" || x.settings.labels!==false || x.settings.revision!==1) process.exit(1)' "${written%$'\n'*}"
