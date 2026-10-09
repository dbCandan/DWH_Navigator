#!/usr/bin/env bash
# Regression test of helm/dwhnavigator/deploy-hooks.sh against a fake kubectl on PATH
# (specs/application-foundation/PRDs/002-kubernetes-delivery Requirement 7, Acceptance 1).
# Needs bash and openssl only; the fake stores Secret values as files and records every argv, so the
# test proves that no value reaches a command argument, stdout or stderr.
# Run: tests/helm/deploy-hooks.test.sh
set -euo pipefail

root="$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)"
hook="$root/helm/dwhnavigator/deploy-hooks.sh"
layer="$root/helm/dwhnavigator/values-project.yaml"
scratch="$(mktemp -d "${TMPDIR:-/tmp}/deploy-hooks-test.XXXXXXXX")"
trap 'rm -rf -- "$scratch"' EXIT
failures=0
current=""

# --- fake kubectl ----------------------------------------------------------------------------------
mkdir "$scratch/bin"
cat > "$scratch/bin/kubectl" <<'FAKE'
#!/usr/bin/env bash
# Minimal kubectl for the hook: Secrets live in $FAKE_STATE/secrets/<name>/<key> as raw values.
set -euo pipefail
printf '%s\n' "$*" >> "$FAKE_STATE/argv.log"
args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace) shift 2 ;;
    *) args+=("$1"); shift ;;
  esac
done
set -- "${args[@]}"
store="$FAKE_STATE/secrets"
case "$1 $2" in
  "get secret")
    [[ -z "${FAKE_GET_FAILS:-}" ]] || { echo 'Error from server (Forbidden)' >&2; exit 1; }
    name="$3"; key=""
    for arg in "$@"; do
      case "$arg" in jsonpath=*) key="${arg#jsonpath=\{.data.}"; key="${key%\}}" ;; esac
    done
    if [[ -f "$store/$name/$key" ]]; then base64 < "$store/$name/$key" | tr -d '\n'; fi
    ;;
  "create secret")
    name="$4"; shift 4
    printf 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: %s\ndata:\n' "$name"
    for arg in "$@"; do
      case "$arg" in
        --from-file=*) spec="${arg#--from-file=}"
          printf '  %s: %s\n' "${spec%%=*}" "$(base64 < "${spec#*=}" | tr -d '\n')" ;;
      esac
    done
    ;;
  "apply --filename")
    [[ -z "${FAKE_APPLY_FAILS:-}" ]] || exit 1
    name="$(sed -n 's/^  name: //p' "$3")"
    mkdir -p "$store/$name"
    sed -n '/^data:/,$p' "$3" | sed -n 's/^  \([A-Z0-9_]*\): \(.*\)$/\1 \2/p' | \
      while read -r key value; do printf '%s' "$value" | base64 --decode > "$store/$name/$key"; done
    echo applied >> "$FAKE_STATE/apply.log"
    ;;
  "get deployment")
    cat "$FAKE_STATE/deployments" 2>/dev/null || true
    ;;
  "rollout restart") echo "$3" >> "$FAKE_STATE/restart.log" ;;
  "rollout status") ;;
  *) echo "fake kubectl: unexpected call: $*" >&2; exit 97 ;;
esac
FAKE
chmod +x "$scratch/bin/kubectl"

# --- helpers ---------------------------------------------------------------------------------------
new_state() {
  current="$scratch/state-$1"
  mkdir -p "$current/secrets"
  : > "$current/argv.log"
}

# run_hook [VAR=value ...]: runs the hook in a clean environment; sets status, captures output.
run_hook() {
  status=0
  env -i PATH="$scratch/bin:$PATH" HOME="$scratch" TMPDIR="$scratch" FAKE_STATE="$current" \
    KT_DEPLOY_RELEASE=dwhnavigator KT_DEPLOY_NAMESPACE=dwhnavigator \
    KT_DEPLOY_CHART_DIR="$root/helm/dwhnavigator" KT_DEPLOY_IMAGE_TAG="${tag:-$(printf 'a%.0s' {1..40})}" \
    KT_DEPLOY_DATABASE_ENABLED=true "$@" \
    bash "$hook" > "$current/stdout" 2> "$current/stderr" || status=$?
}

stored() { cat "$current/secrets/dwhnavigator-runtime/$1" 2>/dev/null; }
has_key() { [[ -f "$current/secrets/dwhnavigator-runtime/$1" ]]; }

check() {
  local description="$1"; shift
  if "$@"; then
    echo "ok   $description"
  else
    echo "FAIL $description"
    failures=$((failures + 1))
  fi
}

# No value may reach stdout, stderr or any kubectl argument.
never_printed() {
  local value="$1"
  ! grep -qF -- "$value" "$current/stdout" "$current/stderr" "$current/argv.log"
}

valid_p256_key() {
  local text
  text="$(openssl pkey -in "$current/secrets/dwhnavigator-runtime/DWHNAVIGATOR_JWT_PRIVATE_KEY" \
    -pubout 2>/dev/null | openssl pkey -pubin -noout -text 2>/dev/null)" || return 1
  [[ "$text" == *prime256v1* || "$text" == *P-256* ]]
}

# The settings encryption key: standard base64 of exactly 32 bytes.
valid_encryption_key() {
  local value bytes
  value="$(stored DWHNAVIGATOR_SETTINGS_ENCRYPTION_KEY)" || return 1
  [[ "$value" =~ ^[A-Za-z0-9+/]{43}=$ ]] || return 1
  bytes="$(printf '%s' "$value" | openssl base64 -d -A | wc -c)"
  [[ "${bytes//[[:space:]]/}" == 32 ]]
}

# Not a usable password of any environment; shell metacharacters, spaces and non-ASCII letters prove
# the value reaches the Secret byte for byte.
# shellcheck disable=SC2016 # the literal $(...) and backticks are the point
admin_password='test-başlangıç $(yok) `x` "q" parolası 42'

# --- cases -----------------------------------------------------------------------------------------
new_state first-run
run_hook
check 'first run without pipeline secrets succeeds' test "$status" -eq 0
check 'first run generates a P-256 signing key' valid_p256_key
check 'first run writes only the two generated keys' \
  test "$(find "$current/secrets/dwhnavigator-runtime" -type f -exec basename {} \; | sort | tr '\n' ' ')" \
  = 'DWHNAVIGATOR_JWT_PRIVATE_KEY DWHNAVIGATOR_SETTINGS_ENCRYPTION_KEY '
check 'first run writes no super admin start-up password' eval '! has_key DWHNAVIGATOR_BOOTSTRAP_SUPER_ADMIN_PASSWORD'
check 'an absent DWHNAVIGATOR_ADMIN_PASSWORD is reported by key name' \
  grep -q 'DWHNAVIGATOR_BOOTSTRAP_SUPER_ADMIN_PASSWORD not provided; DWHNAVIGATOR_ADMIN_PASSWORD is absent' "$current/stdout"
check 'first run reports the generated key by name' grep -q 'DWHNAVIGATOR_JWT_PRIVATE_KEY generated' "$current/stdout"
check 'no private key material is printed' never_printed 'PRIVATE KEY'
check 'no private key material reaches kubectl arguments' never_printed "$(sed -n 2p "$current/secrets/dwhnavigator-runtime/DWHNAVIGATOR_JWT_PRIVATE_KEY")"
first_key="$(stored DWHNAVIGATOR_JWT_PRIVATE_KEY)"
check 'first run generates a 32-byte settings encryption key' valid_encryption_key
check 'first run reports the generated encryption key by name' \
  grep -q 'DWHNAVIGATOR_SETTINGS_ENCRYPTION_KEY generated' "$current/stdout"
first_encryption_key="$(stored DWHNAVIGATOR_SETTINGS_ENCRYPTION_KEY)"
check 'the encryption key is never printed or passed as an argument' never_printed "$first_encryption_key"
check 'the encryption key reaches kubectl only as a file' \
  grep -q -- '--from-file=DWHNAVIGATOR_SETTINGS_ENCRYPTION_KEY=/' "$current/argv.log"

: > "$current/apply.log"
run_hook
check 'second run succeeds' test "$status" -eq 0
check 'second run reuses the signing key from the cluster' test "$(stored DWHNAVIGATOR_JWT_PRIVATE_KEY)" = "$first_key"
check 'second run reuses the encryption key from the cluster' \
  test "$(stored DWHNAVIGATOR_SETTINGS_ENCRYPTION_KEY)" = "$first_encryption_key"
check 'second run leaves the Secret unchanged' grep -q 'unchanged' "$current/stdout"
check 'second run writes nothing' test ! -s "$current/apply.log"

new_state admin-password
: > "$current/apply.log"
run_hook DWHNAVIGATOR_ADMIN_PASSWORD="$admin_password"
check 'a pipeline super admin start-up password is accepted' test "$status" -eq 0
check 'DWHNAVIGATOR_ADMIN_PASSWORD maps to DWHNAVIGATOR_BOOTSTRAP_SUPER_ADMIN_PASSWORD' \
  test "$(stored DWHNAVIGATOR_BOOTSTRAP_SUPER_ADMIN_PASSWORD)" = "$admin_password"
check 'the start-up password reaches kubectl only as a file' \
  grep -q -- '--from-file=DWHNAVIGATOR_BOOTSTRAP_SUPER_ADMIN_PASSWORD=/' "$current/argv.log"
check 'the start-up password is never printed or passed as an argument' never_printed "$admin_password"
check 'the start-up password is reported by key name only' \
  grep -q 'DWHNAVIGATOR_BOOTSTRAP_SUPER_ADMIN_PASSWORD set from DWHNAVIGATOR_ADMIN_PASSWORD' "$current/stdout"
: > "$current/apply.log"
run_hook
check 'a later run without DWHNAVIGATOR_ADMIN_PASSWORD succeeds' test "$status" -eq 0
check 'absent DWHNAVIGATOR_ADMIN_PASSWORD keeps the cluster value' \
  test "$(stored DWHNAVIGATOR_BOOTSTRAP_SUPER_ADMIN_PASSWORD)" = "$admin_password"
check 'a kept start-up password rewrites nothing' test ! -s "$current/apply.log"
check 'a kept start-up password is never printed' never_printed "$admin_password"

new_state unresolved-macro
# shellcheck disable=SC2016 # unresolved Azure macros are literal text
run_hook DWHNAVIGATOR_ADMIN_PASSWORD='$(DWHNAVIGATOR_ADMIN_PASSWORD)' \
  JWT_PRIVATE_KEY='$(JWT_PRIVATE_KEY)'
check 'unresolved Azure macros do not stop the deployment' test "$status" -eq 0
check 'an unresolved JWT_PRIVATE_KEY macro falls back to a generated key' valid_p256_key
check 'an unresolved start-up password macro is never stored' \
  eval '! has_key DWHNAVIGATOR_BOOTSTRAP_SUPER_ADMIN_PASSWORD'
check 'an unresolved macro is reported by name' \
  grep -q 'DWHNAVIGATOR_ADMIN_PASSWORD is an unresolved Azure variable' "$current/stdout"

new_state read-failure
: > "$current/apply.log"
run_hook FAKE_GET_FAILS=1 DWHNAVIGATOR_ADMIN_PASSWORD="$admin_password"
check 'an unreadable Secret stops the hook' test "$status" -ne 0
check 'an unreadable Secret is never overwritten' test ! -s "$current/apply.log"
check 'an unreadable Secret does not print the value' never_printed "$admin_password"

new_state write-failure
run_hook FAKE_APPLY_FAILS=1 DWHNAVIGATOR_ADMIN_PASSWORD="$admin_password"
check 'a failed write stops the hook' test "$status" -ne 0
check 'a failed write does not print the value' never_printed "$admin_password"

new_state invalid-key
: > "$current/apply.log"
run_hook JWT_PRIVATE_KEY='not-a-pem-key-value'
check 'an invalid JWT_PRIVATE_KEY stops the hook' test "$status" -ne 0
check 'an invalid JWT_PRIVATE_KEY is never written' test ! -s "$current/apply.log"
check 'an invalid JWT_PRIVATE_KEY is not echoed' never_printed 'not-a-pem-key-value'

new_state pipeline-key
openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$scratch/pipeline.pem" 2>/dev/null
run_hook JWT_PRIVATE_KEY="$(cat "$scratch/pipeline.pem")"
check 'a pipeline JWT_PRIVATE_KEY is used' test "$(stored DWHNAVIGATOR_JWT_PRIVATE_KEY)" = "$(cat "$scratch/pipeline.pem")"

new_state pipeline-encryption-key
pipeline_encryption_key="$(openssl rand -base64 32 | tr -d '\n')"
run_hook SETTINGS_ENCRYPTION_KEY="$pipeline_encryption_key"
check 'a pipeline SETTINGS_ENCRYPTION_KEY is accepted' test "$status" -eq 0
check 'a pipeline SETTINGS_ENCRYPTION_KEY is used' \
  test "$(stored DWHNAVIGATOR_SETTINGS_ENCRYPTION_KEY)" = "$pipeline_encryption_key"
check 'a pipeline SETTINGS_ENCRYPTION_KEY is never printed or passed as an argument' \
  never_printed "$pipeline_encryption_key"
# shellcheck disable=SC2016 # an unresolved Azure macro is literal text
run_hook SETTINGS_ENCRYPTION_KEY='$(SETTINGS_ENCRYPTION_KEY)'
check 'an unresolved SETTINGS_ENCRYPTION_KEY macro keeps the cluster key' \
  test "$(stored DWHNAVIGATOR_SETTINGS_ENCRYPTION_KEY)" = "$pipeline_encryption_key"

for invalid_encryption_key in 'not-a-key-value' "$(openssl rand -base64 16 | tr -d '\n')" \
  "$(openssl rand -base64 48 | tr -d '\n')"; do
  new_state "invalid-encryption-key-${#invalid_encryption_key}"
  : > "$current/apply.log"
  run_hook SETTINGS_ENCRYPTION_KEY="$invalid_encryption_key"
  check "an invalid SETTINGS_ENCRYPTION_KEY (${#invalid_encryption_key} characters) stops the hook" \
    test "$status" -ne 0
  check 'an invalid SETTINGS_ENCRYPTION_KEY is never written' test ! -s "$current/apply.log"
  check 'an invalid SETTINGS_ENCRYPTION_KEY is not echoed' never_printed "$invalid_encryption_key"
done

new_state restart-same-tag
tag="$(printf 'b%.0s' {1..40})"
printf 'dwhnavigator-dwhnavigator-backend-f5594230b40d\texample.test/dwhnavigator-backend:%s\n' "$tag" \
  > "$current/deployments"
run_hook
check 'a changed Secret restarts a backend that keeps its image tag' \
  grep -qx 'deployment/dwhnavigator-dwhnavigator-backend-f5594230b40d' "$current/restart.log"
: > "$current/restart.log"
run_hook
check 'an unchanged Secret restarts nothing' test ! -s "$current/restart.log"

new_state restart-new-tag
printf 'dwhnavigator-dwhnavigator-backend-f5594230b40d\texample.test/dwhnavigator-backend:%s\n' \
  "$(printf 'c%.0s' {1..40})" > "$current/deployments"
run_hook
check 'a backend moving to a new image tag is left to Helm' test ! -e "$current/restart.log"
unset tag

check 'the hook writes the Secret values-project.yaml names' \
  grep -qx '  existingSecret: dwhnavigator-runtime' "$layer"
check 'the hook parses' bash -n "$hook"

if [[ "$failures" -ne 0 ]]; then
  echo "deploy-hooks: $failures check(s) failed" >&2
  exit 1
fi
echo 'deploy-hooks: all checks passed'
