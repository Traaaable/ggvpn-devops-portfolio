#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
project="portfolio-check-$$"
dc=(docker compose -p "$project")
trap '"${dc[@]}" down --timeout 10' EXIT
"${dc[@]}" up -d --build --wait --wait-timeout 60
"${dc[@]}" exec -T web sh -ec '
  test "$(id -u)" = 101
  test "$(wget -qO- http://127.0.0.1:8080/healthz)" = ok
  wget -qO- http://127.0.0.1:8080/ | grep -q "GG VPN DevOps lab"
  if touch /etc/should-not-write 2>/dev/null; then exit 1; fi
'
echo "PASS: Docker build, healthcheck, HTTP, UID 101 and read-only root filesystem."
