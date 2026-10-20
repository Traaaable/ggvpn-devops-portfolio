"""Check cross-resource contracts that `helm lint` does not validate."""
import hashlib
import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts/ggvpn-web"


def render(release="review", *options):
    result = subprocess.run(
        ["helm", "template", release, str(CHART), *options],
        text=True, capture_output=True, check=True,
    )
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def kind(docs, name):
    return next(doc for doc in docs if doc["kind"] == name)


class ChartContracts(unittest.TestCase):
    def test_configmap_references_follow_release_names(self):
        for release in ("ggvpn-web", "another-release", "r" * 53):
            for options in ((), ("-f", str(ROOT / "values-dev.yaml")),
                            ("--set", "fullnameOverride=custom-web")):
                with self.subTest(release=release, options=options):
                    docs = render(release, *options)
                    pod = kind(docs, "Deployment")["spec"]["template"]["spec"]
                    refs = [v["configMap"]["name"] for v in pod["volumes"] if "configMap" in v]
                    self.assertEqual(set(refs), {kind(docs, "ConfigMap")["metadata"]["name"]})

    def test_nginx_configuration_is_not_in_document_root(self):
        pod = kind(render(), "Deployment")["spec"]["template"]["spec"]
        mount = next(m for m in pod["containers"][0]["volumeMounts"] if m["mountPath"] == "/usr/share/nginx/html")
        volume = next(v for v in pod["volumes"] if v["name"] == mount["name"])
        self.assertEqual(volume["configMap"]["items"], [{"key": "index.html", "path": "index.html"}])

    def test_config_change_rolls_pods(self):
        first = kind(render(), "Deployment")["spec"]["template"]["metadata"]["annotations"]
        second = kind(render("review", "--set-string", "pageContent=updated"), "Deployment")["spec"]["template"]["metadata"]["annotations"]
        self.assertNotEqual(first["checksum/content"], second["checksum/content"])

    def test_service_port_is_independent_of_container_port(self):
        docs = render("review", "--set", "service.port=8081")
        self.assertEqual(kind(docs, "Service")["spec"]["ports"][0]["port"], 8081)
        container = kind(docs, "Deployment")["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["ports"][0]["containerPort"], 8080)

    def test_restricted_runtime_and_probes(self):
        pod = kind(render(), "Deployment")["spec"]["template"]["spec"]
        container = pod["containers"][0]
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertTrue(pod["securityContext"]["runAsNonRoot"])
        self.assertFalse(container["securityContext"]["allowPrivilegeEscalation"])
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertEqual(container["securityContext"]["capabilities"]["drop"], ["ALL"])
        for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
            self.assertIn(probe, container)
        self.assertNotIn("hostPath", str(pod["volumes"]))

    def test_hpa_owns_replicas_and_has_cpu_request(self):
        docs = render("review", "-f", str(ROOT / "values-hpa.yaml"))
        dep = kind(docs, "Deployment")
        self.assertNotIn("replicas", dep["spec"])
        self.assertTrue(dep["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"]["cpu"])
        self.assertEqual(kind(docs, "HorizontalPodAutoscaler")["spec"]["scaleTargetRef"]["name"], dep["metadata"]["name"])

    def test_ingress_resolves_to_service(self):
        docs = render("review", "-f", str(ROOT / "values-ingress.yaml"))
        backend = kind(docs, "Ingress")["spec"]["rules"][0]["http"]["paths"][0]["backend"]["service"]
        self.assertEqual(backend["name"], kind(docs, "Service")["metadata"]["name"])

    def test_hook_checks_actual_config_content(self):
        docs = render()
        checksum = hashlib.sha256(kind(docs, "ConfigMap")["data"]["index.html"].encode()).hexdigest()
        self.assertIn(checksum, kind(docs, "Pod")["spec"]["containers"][0]["args"][0])

    def test_invalid_replicas_are_rejected(self):
        for overrides in ("replicaCount=0", "autoscaling.enabled=true,autoscaling.minReplicas=4,autoscaling.maxReplicas=2"):
            result = subprocess.run(
                ["helm", "template", "review", str(CHART), "--set", overrides],
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
