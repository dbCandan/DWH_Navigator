#!/usr/bin/env bash
# Project chart test: the nonprod render of helm/dwhnavigator with values-project.yaml, exactly as
# `deploy.sh --render` produces it (specs/application-foundation/PRDs/002-kubernetes-delivery
# Requirement 1, 2, 3, 8, 10, 11; Acceptance 1), together with the release image facts the values
# depend on: the model trust store path and the shutdown budget. The factory structure checks run
# separately in scripts/render-charts.sh; this test pins the project's own values.
# Needs helm and the pinned kt-iskelet CLI on PATH (its Python carries PyYAML, as for
# scripts/render-charts.sh). Run: tests/helm/values-project.test.sh
set -euo pipefail

root="$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)"
scaffold_bin="$(command -v kt-iskelet || true)"
[[ -n "$scaffold_bin" ]] || { echo 'kt-iskelet must be on PATH' >&2; exit 2; }
python_bin="$(sed -n '1s/^#!//p' "$scaffold_bin")"
[[ -x "$python_bin" ]] || { echo 'the kt-iskelet Python could not be resolved' >&2; exit 2; }
scratch="$(mktemp -d "${TMPDIR:-/tmp}/values-project-test.XXXXXXXX")"
trap 'rm -rf -- "$scratch"' EXIT

env -u IMAGE_TAG -u BUILD_SOURCEVERSION -u TF_BUILD \
  "$root/helm/dwhnavigator/deploy.sh" --render > "$scratch/rendered.yaml" 2> "$scratch/lint.log" \
  || { cat "$scratch/lint.log" >&2; echo 'deploy.sh --render failed' >&2; exit 1; }

"$python_bin" - "$scratch/rendered.yaml" "$root/helm/dwhnavigator/values-project.yaml" "$root" <<'PY'
import json
import re
import sys
from pathlib import Path

import yaml

rendered_path, layer_path, root = sys.argv[1], sys.argv[2], Path(sys.argv[3])
documents = [d for d in yaml.safe_load_all(open(rendered_path, encoding="utf-8")) if d]
layer = yaml.safe_load(open(layer_path, encoding="utf-8"))
failures = 0


def check(description: str, condition: bool) -> None:
    global failures
    print(("ok   " if condition else "FAIL ") + description)
    failures += 0 if condition else 1


def component(kind: str, name: str) -> list[dict]:
    return [
        d
        for d in documents
        if d["kind"] == kind
        and d["metadata"].get("labels", {}).get("app.kubernetes.io/component") == name
    ]


host = "dwhnavigator.ailab-test.kuveytturk.com.tr"
kinds = sorted(d["kind"] for d in documents)
check(
    "the render holds exactly the PRD workloads, services, one Ingress and four NetworkPolicies",
    kinds
    == sorted(
        ["Deployment"] * 2
        + ["StatefulSet", "Job", "Ingress"]
        + ["Service"] * 3
        + ["NetworkPolicy"] * 4
    ),
)
check("no Secret is rendered", "Secret" not in kinds)
check(
    "every object sits in the dwhnavigator namespace or carries none",
    all(d["metadata"].get("namespace") in (None, "dwhnavigator") for d in documents),
)

(backend,) = component("Deployment", "backend")
pod = backend["spec"]["template"]["spec"]
(container,) = pod["containers"]
check("backend runs one replica", backend["spec"]["replicas"] == 1)
check(
    "backend resources follow Decision 10",
    container["resources"]
    == {"requests": {"cpu": "100m", "memory": "512Mi"}, "limits": {"cpu": "1000m", "memory": "2Gi"}},
)
# Shutdown budget: on SIGTERM uvicorn first waits for open responses (an analysis event stream
# stays open), at most --timeout-graceful-shutdown seconds; then the application ends analysis jobs
# and term lists as interrupted within their own waits. All of it must fit the pod's grace period
# (Kubernetes default 30 s unless the chart sets one).
grace = pod.get("terminationGracePeriodSeconds", 30)
dockerfile = (root / "app/infra/Dockerfile.backend.release").read_text(encoding="utf-8")
(entrypoint,) = re.findall(r"^ENTRYPOINT (\[.*\])$", dockerfile, re.MULTILINE)
command = json.loads(entrypoint)
uvicorn_wait = (
    float(command[command.index("--timeout-graceful-shutdown") + 1])
    if "--timeout-graceful-shutdown" in command
    else float("inf")
)


def shutdown_wait(relative: str) -> float:
    source = (root / "app/backend/app" / relative).read_text(encoding="utf-8")
    (value,) = re.findall(r"^SHUTDOWN_WAIT_SECONDS = ([0-9.]+)$", source, re.MULTILINE)
    return float(value)


budget = uvicorn_wait + shutdown_wait("services/analysis/jobs.py") + shutdown_wait(
    "services/term_lists.py"
)
check(
    f"backend shutdown ({budget:g} s) fits the pod grace period ({grace} s)",
    budget < grace,
)
check(
    "backend reads the runtime Secret the hook prepares",
    {"secretRef": {"name": "dwhnavigator-runtime"}} in container["envFrom"],
)
env = {item["name"]: item["value"] for item in container["env"]}
check(
    "backend settings carry the nonprod origin, proxy network and admin name",
    env.get("DWHNAVIGATOR_ENVIRONMENT") == "staging"
    and env.get("DWHNAVIGATOR_PUBLIC_ORIGIN") == f"https://{host}"
    and env.get("DWHNAVIGATOR_CORS_ALLOW_ORIGINS") == f"https://{host}"
    and env.get("DWHNAVIGATOR_TRUSTED_PROXY_CIDRS") == "10.42.0.0/16"
    and env.get("DWHNAVIGATOR_BOOTSTRAP_SUPER_ADMIN_USERNAME") == "admin"
    and env.get("DWHNAVIGATOR_OTEL_EXPORTER_OTLP_ENDPOINT") == "",
)
model_settings = {"DWHNAVIGATOR_LLM_MAX_CONCURRENT_CALLS", "DWHNAVIGATOR_LLM_CA_BUNDLE"}
check(
    "backend settings carry no model address, model name or key",
    not any(key.startswith("DWHNAVIGATOR_LLM_") and key not in model_settings for key in env),
)
copied = re.findall(
    r"^COPY app/backend/certs/corporate-inference-root\.crt (\S+)$", dockerfile, re.MULTILINE
)
check(
    "the model trust store is the root CA file the release image carries",
    copied == [env.get("DWHNAVIGATOR_LLM_CA_BUNDLE")],
)

(backend_policy,) = component("NetworkPolicy", "backend")
egress = backend_policy["spec"]["egress"]
dns = {
    "to": [
        {
            "namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "kube-system"}},
            "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}},
        }
    ],
    "ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}],
}
database = {
    "to": [
        {
            "podSelector": {
                "matchLabels": {
                    "app.kubernetes.io/instance": "dwhnavigator",
                    "app.kubernetes.io/part-of": "dwhnavigator",
                    "app.kubernetes.io/component": "database",
                }
            }
        }
    ],
    "ports": [{"protocol": "TCP", "port": 5432}],
}
model = {"to": [{"ipBlock": {"cidr": "10.14.3.99/32"}}], "ports": [{"protocol": "TCP", "port": 443}]}
check("backend egress is exactly DNS, its own database and the model server", egress == [dns, database, model])
(database_pod,) = component("StatefulSet", "database")
labels = database_pod["spec"]["template"]["metadata"]["labels"]
check(
    "the database egress peer selects the release's database pod",
    all(labels.get(k) == v for k, v in database["to"][0]["podSelector"]["matchLabels"].items()),
)

(claim,) = database_pod["spec"]["volumeClaimTemplates"]
check(
    "PostgreSQL keeps 10Gi on nfs-sc",
    claim["spec"]["storageClassName"] == "nfs-sc"
    and claim["spec"]["resources"]["requests"]["storage"] == "10Gi",
)

(ingress,) = [d for d in documents if d["kind"] == "Ingress"]
check(
    "the Ingress serves the nonprod host with ailab-tls on the nginx class",
    ingress["spec"]["ingressClassName"] == "nginx"
    and ingress["spec"]["tls"] == [{"hosts": [host], "secretName": "ailab-tls"}]
    and [rule["host"] for rule in ingress["spec"]["rules"]] == [host],
)

# The update strategy and the ingress body limit reach the rendered objects exactly.
check(
    "the layer asks for the Recreate update strategy",
    layer["backend"].get("strategy") == {"type": "Recreate"},
)
check(
    "the layer asks for a 20 MB ingress body limit",
    layer["frontend"]["ingress"].get("annotations")
    == {"nginx.ingress.kubernetes.io/proxy-body-size": "20m"},
)
check(
    "a rendered backend strategy is Recreate",
    backend["spec"].get("strategy") == {"type": "Recreate"},
)
body_size = ingress["metadata"].get("annotations", {}).get(
    "nginx.ingress.kubernetes.io/proxy-body-size"
)
check("a rendered ingress body limit is 20 MB", body_size == "20m")

if failures:
    print(f"values-project: {failures} check(s) failed", file=sys.stderr)
    sys.exit(1)
print("values-project: all checks passed")
PY
