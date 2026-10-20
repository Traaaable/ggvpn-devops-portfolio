"""Optional lab-only checks. Requires ingress, metrics-server and policy enforcement.

Creates two temporary namespaces; uses up to 3 app Pods and bounded CPU load.
"""
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
context = os.environ["KUBE_CONTEXT"]
ingress_class = os.environ.get("INGRESS_CLASS", "traefik")
ingress_namespace = os.environ.get("INGRESS_NAMESPACE", "kube-system")
ingress_service = os.environ.get("INGRESS_SERVICE", "traefik")
local_port = int(os.environ.get("PORTFOLIO_INGRESS_PORT", "18083"))
namespace = f"portfolio-options-{int(time.time())}"
other = namespace + "-outside"
base = ["kubectl", "--context", context]
k = base + ["-n", namespace]
h = ["helm", "--kube-context", context, "-n", namespace]
created = []
forward = None
load = None


def run(args, **kwargs):
    result = subprocess.run(args, cwd=root, text=True, capture_output=True, **kwargs)
    if result.returncode:
        raise RuntimeError(f"{args}: {result.stderr or result.stdout}")
    return result.stdout


try:
    for ns in (namespace, other):
        run(base + ["create", "namespace", ns])
        created.append(ns)
    run(base + ["label", "namespace", namespace, "pod-security.kubernetes.io/enforce=restricted"])
    print(run(h + ["install", "feature", "charts/ggvpn-web",
                   "-f", "values-hpa.yaml", "-f", "values-ingress.yaml",
                   "--set", f"autoscaling.maxReplicas=3,ingress.className={ingress_class},networkPolicy.enabled=true,networkPolicy.ingressNamespace={ingress_namespace}",
                   "--wait", "--timeout", "180s"]), flush=True)
    print(run(h + ["test", "feature", "--logs", "--timeout", "90s"]), flush=True)
    print(run(k + ["wait", "--for=condition=ScalingActive", "hpa/feature-ggvpn-web", "--timeout=120s"]), flush=True)
    forward = subprocess.Popen(base + ["-n", ingress_namespace, "port-forward", "--address", "127.0.0.1", "svc/" + ingress_service, f"{local_port}:80"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Retry only while the port-forward starts.
    for attempt in range(20):
        try:
            request = urllib.request.Request(f"http://127.0.0.1:{local_port}/", headers={"Host": "portfolio.example.test"})
            with urllib.request.urlopen(request, timeout=3) as response:
                assert "GG VPN DevOps lab" in response.read().decode()
            break
        except Exception:
            if attempt == 19:
                raise
            time.sleep(1)
    print("PASS: Ingress HTTP via configured controller, with NetworkPolicy enabled.", flush=True)
    image = "nginx:1.30.6-alpine-slim@sha256:3028fc1419f99b95c1c69f844bbaf49dc1b881750c51b497fc721ac4f02a14e6"
    address = run(k + ["get", "svc", "feature-ggvpn-web", "-o", "jsonpath={.spec.clusterIP}"]).strip()
    pod = {
        "apiVersion": "v1", "kind": "Pod",
        "metadata": {"name": "denied-client", "namespace": other},
        "spec": {
            "restartPolicy": "Never", "automountServiceAccountToken": False,
            "activeDeadlineSeconds": 40,
            "containers": [{
                "name": "client", "image": image,
                "command": ["sh", "-ec", f"if wget -T 5 -qO /dev/null http://{address}/; then exit 1; else exit 0; fi"],
                "resources": {"requests": {"cpu": "10m", "memory": "8Mi"}, "limits": {"cpu": "100m", "memory": "32Mi"}},
            }],
        },
    }
    run(base + ["apply", "-f", "-"], input=json.dumps(pod))
    run(base + ["-n", other, "wait", "--for=jsonpath={.status.phase}=Succeeded", "pod/denied-client", "--timeout=60s"])
    print("PASS: same-namespace Helm test allowed; direct-IP request from outside namespace denied.", flush=True)
    # One bounded CPU load process in one test Pod. Container has a 200m CPU limit.
    load = subprocess.Popen(k + ["exec", "deploy/feature-ggvpn-web", "--", "sh", "-c", "timeout 65 yes >/dev/null"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 110
    while time.monotonic() < deadline:
        status = json.loads(run(k + ["get", "hpa", "feature-ggvpn-web", "-o", "json"]))["status"]
        if status.get("desiredReplicas", 0) >= 3:
            run(k + ["rollout", "status", "deploy/feature-ggvpn-web", "--timeout=120s"])
            replicas = run(k + ["get", "deploy", "feature-ggvpn-web", "-o", "jsonpath={.status.readyReplicas}"])
            assert int(replicas) == 3, replicas
            print("PASS: HPA scaled 2 -> 3 ready replicas under bounded synthetic CPU load.", flush=True)
            break
        time.sleep(5)
    else:
        raise RuntimeError("HPA did not scale within 110 seconds")
    print(run(k + ["get", "hpa,pdb,ingress,networkpolicy"]), flush=True)
finally:
    for process in (forward, load):
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
    for ns in reversed(created):
        subprocess.run(base + ["delete", "namespace", ns, "--wait=false"], check=False)
