#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
helm lint charts/ggvpn-web --strict
helm lint charts/ggvpn-web --strict -f values-dev.yaml
helm lint charts/ggvpn-web --strict -f values-ingress.yaml -f values-hpa.yaml --set networkPolicy.enabled=true
python3 -m unittest discover -s tests -v
docker compose config --quiet
sh -n examples/dnstt/entrypoint.sh
python3 scripts/check_public_files.py
