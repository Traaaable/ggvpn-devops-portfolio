#!/usr/bin/env bash
# Installs only into a fresh namespace, then removes that namespace.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${KUBE_CONTEXT:?Set KUBE_CONTEXT to an explicit test cluster context}"
namespace="portfolio-check-$(date +%s)-$$"
created=0
k=(kubectl --context "$KUBE_CONTEXT" -n "$namespace")
h=(helm --kube-context "$KUBE_CONTEXT" -n "$namespace")
cleanup() {
  status=$?
  if (( created )); then
    if (( status != 0 )); then
      "${k[@]}" get pods || true
      "${k[@]}" get events --sort-by=.lastTimestamp | tail -20 || true
    fi
    if [[ "${KEEP_NAMESPACE:-0}" != 1 ]]; then
      kubectl --context "$KUBE_CONTEXT" delete namespace "$namespace" --wait=false
    else
      echo "Kept namespace: $namespace"
    fi
  fi
  exit "$status"
}
trap cleanup EXIT
kubectl --context "$KUBE_CONTEXT" create namespace "$namespace"
created=1
kubectl --context "$KUBE_CONTEXT" label namespace "$namespace" \
  pod-security.kubernetes.io/enforce=restricted \
  pod-security.kubernetes.io/enforce-version=v1.27

"${h[@]}" install review-a charts/ggvpn-web -f values-dev.yaml --wait --timeout 180s
"${h[@]}" test review-a --logs --timeout 90s
"${h[@]}" install review-b charts/ggvpn-web -f values-dev.yaml --wait --timeout 180s
"${h[@]}" test review-b --logs --timeout 90s
"${h[@]}" uninstall review-b --wait --timeout 60s

test "$("${k[@]}" exec deploy/review-a-ggvpn-web -- id -u)" = 101
if "${k[@]}" exec deploy/review-a-ggvpn-web -- touch /etc/portfolio-write-test; then
  echo "ERROR: root filesystem is writable" >&2
  exit 1
fi

old_checksum=$("${k[@]}" get deploy review-a-ggvpn-web -o 'go-template={{index .spec.template.metadata.annotations "checksum/content"}}')
"${h[@]}" upgrade review-a charts/ggvpn-web -f values-dev.yaml \
  --set-string pageContent=release-v2 --set service.port=8081 --wait --timeout 180s
new_checksum=$("${k[@]}" get deploy review-a-ggvpn-web -o 'go-template={{index .spec.template.metadata.annotations "checksum/content"}}')
test "$old_checksum" != "$new_checksum"
"${h[@]}" test review-a --logs --timeout 90s

# Controlled failure: incompatible content image never becomes ready.
if "${h[@]}" upgrade review-a charts/ggvpn-web -f values-dev.yaml \
  --set image.tag=portfolio-deliberately-missing --set-string image.digest= \
  --wait --timeout 35s; then
  echo "ERROR: deliberate bad-image upgrade unexpectedly succeeded" >&2
  exit 1
fi
"${h[@]}" rollback review-a 1 --wait --timeout 180s
"${h[@]}" test review-a --logs --timeout 90s
"${h[@]}" history review-a
echo "PASS: isolated installs, two release names, restricted runtime, content upgrade, failed upgrade and rollback."
