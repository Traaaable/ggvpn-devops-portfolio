#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
name="portfolio-dnstt-check-$$"
image=ggvpn-portfolio-dnstt:1.0.0
trap 'docker rm -f "$name" >/dev/null 2>&1 || true' EXIT
docker build -t "$image" examples/dnstt
# No host ports, host mounts, credentials or persistent keys.
docker run -d --name "$name" --read-only \
  --tmpfs /data:rw,noexec,nosuid,size=4m \
  --tmpfs /run:rw,nosuid,size=1m \
  --tmpfs /tmp:rw,noexec,nosuid,size=4m \
  --memory 96m --cpus 0.2 -e DNSTT_KEY_ROTATION_DAYS=0 "$image" >/dev/null
for attempt in $(seq 1 20); do
  if docker exec "$name" sh -ec '
    test "$(stat -c %a /data/dnstt/server.key)" = 600
    grep -q ":14B4 " /proc/net/udp /proc/net/udp6
    grep -q ":0438 " /proc/net/tcp /proc/net/tcp6
  ' 2>/dev/null; then
    docker stop -t 10 "$name" >/dev/null
    test "$(docker inspect "$name" --format '{{.State.ExitCode}}')" = 0
    echo "PASS: DNSTT/Dante listeners, key permissions and graceful shutdown."
    exit 0
  fi
  sleep 1
done
echo "FAIL: expected DNSTT/Dante listeners did not appear" >&2
exit 1
