#!/usr/bin/env bash
# Regression test of the opt-in local-egress Compose profile
# (specs/application-foundation/PRDs/002-kubernetes-delivery Requirement 17, Decision 14).
# Without the profile nothing in the local stack reaches outside it; with COMPOSE_PROFILES=local-egress
# in the env file, only the gate joins an outbound network, the backend reaches it alone under the
# model server's host name, and the gate forwards one port to one address.
# Needs Docker with Compose and python3. It reads neither app/infra/.env nor app/infra/.data and
# prints no configuration value. Run: tests/infra/local-egress.test.sh
set -euo pipefail

root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
infra="$root/app/infra"
gate_conf="$infra/nginx/nginx.local-egress.conf"
scratch="$(mktemp -d "${TMPDIR:-/tmp}/local-egress-test.XXXXXXXX")"
trap 'rm -rf -- "$scratch"' EXIT
failures=0

check() {
  local description="$1"; shift
  if "$@"; then
    echo "ok   $description"
  else
    echo "FAIL $description"
    failures=$((failures + 1))
  fi
}

# model <env file>: the merged Compose model the stack would run with that env file, as JSON.
# Placeholder secrets satisfy the required variables; the developer's own .env is not read.
model() {
  env -u COMPOSE_PROFILES -u COMPOSE_PROJECT_NAME \
    POSTGRES_PASSWORD=placeholder JWT_PRIVATE_KEY=placeholder REDIS_PASSWORD=placeholder \
    GRAFANA_ADMIN_PASSWORD=placeholder \
    docker compose --project-directory "$infra" --env-file "$1" -p local-egress-test \
    -f "$infra/docker-compose.local.yml" -f "$infra/docker-compose.observability.yml" \
    config --format json
}

: > "$scratch/off.env"
printf 'COMPOSE_PROFILES=local-egress\nLOCAL_EGRESS_MODEL_PORT=1234\n' > "$scratch/on.env"
printf 'COMPOSE_PROFILES=local-egress\nLOCAL_EGRESS_MODEL_HOST=llm.lab.internal\nLOCAL_EGRESS_MODEL_ADDRESS=10.20.30.40\nLOCAL_EGRESS_MODEL_PORT=443\n' > "$scratch/named.env"
model "$scratch/off.env" > "$scratch/off.json"
model "$scratch/on.env" > "$scratch/on.json"
model "$scratch/named.env" > "$scratch/named.json"

# assert <model> <name>: one structural rule over the model; exits non-zero when it does not hold.
assert() {
  python3 - "$1" "$2" <<'PY'
import json
import sys

model = json.load(open(sys.argv[1], encoding="utf-8"))
rule = sys.argv[2]
services = model["services"]
networks = model.get("networks", {})


def attached(service):
    return set((services[service].get("networks") or {"default": None}).keys())


def members(network):
    return {name for name in services if network in attached(name)}


outbound = {name for name, spec in networks.items() if not spec.get("internal")}
gate = services.get("local-egress", {})
environment = gate.get("environment") or {}
aliases = (gate.get("networks", {}).get("host-gate") or {}).get("aliases")

rules = {
    "no-gate": "local-egress" not in services,
    "no-egress-network": "egress" not in networks,
    "only-edge-is-outbound": outbound == {"edge"},
    "edge-only-proxy-and-dashboard": members("edge") == {"nginx", "grafana"},
    "gate-present": gate.get("profiles") == ["local-egress"],
    "outbound-edge-and-egress": outbound == {"edge", "egress"},
    "egress-only-gate": members("egress") == {"local-egress"},
    "backend-internal-only": attached("backend") <= {"default", "host-gate"}
    and all(networks[name].get("internal") for name in attached("backend")),
    "host-gate-backend-only": members("host-gate") == {"backend"},
    "host-gate-backend-and-gate": members("host-gate") == {"backend", "local-egress"},
    "gate-default-alias": aliases == ["host.docker.internal"],
    "gate-named-alias": aliases == ["llm.lab.internal"],
    "gate-one-target": environment == {"MODEL_PORT": "1234", "MODEL_ADDRESS": ""},
    "gate-named-target": environment == {"MODEL_PORT": "443", "MODEL_ADDRESS": "10.20.30.40"},
    "gate-networks": set(gate.get("networks", {})) == {"host-gate", "egress"},
    "gate-no-ports": not gate.get("ports") and not gate.get("expose"),
    "gate-hardened": gate.get("read_only") is True
    and gate.get("cap_drop") == ["ALL"]
    and gate.get("user") not in (None, "", "0", "root")
    and "no-new-privileges:true" in (gate.get("security_opt") or []),
    "gate-no-dns": gate.get("dns") == ["127.0.0.1"],
    "gate-host-mapping": gate.get("extra_hosts") == ["host.docker.internal=host-gateway"],
    "gate-pinned-image": gate.get("image") == services["nginx"].get("image")
    and "@sha256:" in gate.get("image", ""),
}
sys.exit(0 if rules[rule] else 1)
PY
}

# --- default: the profile is off -------------------------------------------------------------------
check 'default stack has no local-egress gate' assert "$scratch/off.json" no-gate
check 'default stack creates no outbound egress network' assert "$scratch/off.json" no-egress-network
check 'default stack has only the host-facing edge bridge as a non-internal network' \
  assert "$scratch/off.json" only-edge-is-outbound
check 'only the reverse proxy and the dashboard join the edge bridge' \
  assert "$scratch/off.json" edge-only-proxy-and-dashboard
check 'backend joins internal networks only' assert "$scratch/off.json" backend-internal-only
check 'nothing but the backend is on host-gate, so the model name does not resolve' \
  assert "$scratch/off.json" host-gate-backend-only

# --- opt-in: COMPOSE_PROFILES=local-egress in the env file -----------------------------------------
check 'the env-file setting starts the gate' assert "$scratch/on.json" gate-present
check 'the gate is the only new outbound member' assert "$scratch/on.json" outbound-edge-and-egress
check 'only the gate joins the egress bridge' assert "$scratch/on.json" egress-only-gate
check 'backend still joins internal networks only' assert "$scratch/on.json" backend-internal-only
check 'only the backend and the gate share host-gate' assert "$scratch/on.json" host-gate-backend-and-gate
check 'the gate answers as host.docker.internal by default' assert "$scratch/on.json" gate-default-alias
check 'the gate forwards the one configured port to this computer' assert "$scratch/on.json" gate-one-target
check 'the gate answers under the configured model host name' assert "$scratch/named.json" gate-named-alias
check 'the gate forwards to the configured address and port' assert "$scratch/named.json" gate-named-target
check 'the gate joins exactly host-gate and egress' assert "$scratch/on.json" gate-networks
check 'the gate publishes no port' assert "$scratch/on.json" gate-no-ports
check 'the gate runs read-only, unprivileged and without capabilities' \
  assert "$scratch/on.json" gate-hardened
check 'the gate resolves no names' assert "$scratch/on.json" gate-no-dns
check 'the gate maps host.docker.internal to this computer' assert "$scratch/on.json" gate-host-mapping
check 'the gate uses the pinned reverse proxy image' assert "$scratch/on.json" gate-pinned-image

# --- gate configuration ----------------------------------------------------------------------------
check 'the gate has exactly one listener and one forward' bash -c '
  test "$(grep -cE "^[[:space:]]*listen[[:space:]]" "$1")" = 1 &&
  test "$(grep -cE "^[[:space:]]*proxy_pass[[:space:]]" "$1")" = 1 &&
  grep -qE "^[[:space:]]*listen MODEL_PORT;" "$1" &&
  grep -qE "^[[:space:]]*proxy_pass MODEL_ADDRESS:MODEL_PORT;" "$1"
' _ "$gate_conf"
image="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["services"]["local-egress"]["image"])' "$scratch/on.json")"
sed -e 's/MODEL_ADDRESS/10.20.30.40/' -e 's/MODEL_PORT/1234/g' "$gate_conf" > "$scratch/gate.conf"
check 'the rendered gate configuration is valid for the pinned image' \
  docker run --rm --network none --user 101:101 --read-only --tmpfs /tmp --entrypoint nginx \
  -v "$scratch/gate.conf:/etc/nginx/local-egress.conf:ro" "$image" -q -t -c /etc/nginx/local-egress.conf
# The rendered model keeps Compose's "$$" escape; the container receives a single "$".
entrypoint="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["services"]["local-egress"]["entrypoint"][2].replace("$$", "$"))' "$scratch/on.json")"
# gate_run <port> <address> [docker options]: the gate entrypoint in a container without network.
gate_run() {
  local port="$1" address="$2"; shift 2
  docker run "$@" --network none --user 101:101 --read-only --tmpfs /tmp \
    --sysctl net.ipv4.ip_unprivileged_port_start=0 \
    -e "MODEL_PORT=$port" -e "MODEL_ADDRESS=$address" \
    -v "$gate_conf:/etc/nginx/local-egress.conf:ro" --entrypoint /bin/sh "$image" \
    -ec "$entrypoint"
}
# refuses <port> <address>: the entrypoint stops with its own message before nginx starts.
refuses() {
  local output
  if output="$(gate_run "$1" "$2" --rm 2>&1)"; then
    return 1
  fi
  grep -q '^local-egress: LOCAL_EGRESS_MODEL_' <<< "$output"
}
# forwards <port> <address>: nginx runs and relays exactly that port to that address.
forwards() {
  local name="local-egress-test-$$" status rendered
  gate_run "$1" "$2" -d --name "$name" >/dev/null
  sleep 2
  status="$(docker inspect -f '{{.State.Status}}' "$name")"
  rendered="$(docker exec "$name" cat /tmp/local-egress.conf 2>/dev/null || true)"
  docker rm -f "$name" >/dev/null
  [[ "$status" == running ]] &&
    grep -qE "^[[:space:]]*listen $1;" <<< "$rendered" &&
    grep -qE "^[[:space:]]*proxy_pass $2:$1;" <<< "$rendered"
}
check 'the gate relays one port to one address' forwards 443 10.20.30.40
check 'the gate refuses a missing port' refuses '' 10.20.30.40
check 'the gate refuses a port out of range' refuses 70000 10.20.30.40
check 'the gate refuses an address that is not IPv4' refuses 1234 'llm.lab.internal'
check 'the gate refuses an injected configuration' refuses 1234 '10.0.0.1;daemon on'
check '.env.example documents the setting' grep -qx '# COMPOSE_PROFILES=local-egress' "$infra/.env.example"

if [[ "$failures" -ne 0 ]]; then
  echo "local-egress: $failures check(s) failed" >&2
  exit 1
fi
echo 'local-egress: all checks passed'
