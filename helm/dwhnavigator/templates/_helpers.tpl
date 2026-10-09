{{- define "generated.resourceName" -}}
{{- $root := index . 0 -}}
{{- $component := index . 1 -}}
{{- $release := $root.Release.Name | trunc 18 | trimSuffix "-" -}}
{{- $slug := $root.Chart.Name | trunc 18 | trimSuffix "-" -}}
{{- $identity := printf "%s/%s/%s/%s" $root.Release.Namespace $root.Release.Name $root.Chart.Name $component -}}
{{- printf "%s-%s-%s-%s" $release $slug $component (sha256sum $identity | trunc 12) | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{- define "generated.workloadLabels" -}}
app.kubernetes.io/name: {{ .root.Chart.Name | quote }}
app.kubernetes.io/part-of: {{ .root.Chart.Name | quote }}
app.kubernetes.io/instance: {{ .root.Release.Name | quote }}
app.kubernetes.io/component: {{ .component | quote }}
scaffold.kt.internal/workload: {{ include "generated.resourceName" (list .root .component) | quote }}
{{- end }}

{{- define "generated.annotations" -}}
scaffold.kt.internal/product-name: {{ index .Chart.Annotations "scaffold.kt.internal/product-name" | quote }}
scaffold.kt.internal/product-slug: {{ .Chart.Name | quote }}
scaffold.kt.internal/release-namespace: {{ .Release.Namespace | quote }}
{{- end }}

{{- define "generated.image" -}}
{{- $component := index . 0 -}}
{{- $image := index . 1 -}}
{{- $repository := required (printf "%s.image.repository is required" $component) $image.repository -}}
{{- $digest := default "" $image.digest -}}
{{- if $digest -}}
{{- if not (regexMatch "^sha256:[0-9a-f]{64}$" $digest) -}}
{{- fail (printf "%s.image.digest must be a lowercase sha256 digest" $component) -}}
{{- end -}}
{{- printf "%s@%s" $repository $digest -}}
{{- else -}}
{{- $tag := required (printf "%s.image.tag is required when digest is empty" $component) $image.tag -}}
{{- if not (regexMatch "^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$" $tag) -}}
{{- fail (printf "%s.image.tag must be a valid OCI tag" $component) -}}
{{- end -}}
{{- printf "%s:%s" $repository $tag -}}
{{- end -}}
{{- end }}

{{- define "generated.postgresImage" -}}
{{- $image := .Values.postgres.image -}}
{{- $repository := required "postgres.image.repository is required" $image.repository -}}
{{- $digest := required "postgres.image.digest must pin the PostgreSQL image when postgres.enabled" $image.digest -}}
{{- if not (regexMatch "^sha256:[0-9a-f]{64}$" $digest) -}}
{{- fail "postgres.image.digest must be a lowercase sha256 digest" -}}
{{- end -}}
{{- printf "%s@%s" $repository $digest -}}
{{- end }}

{{- define "generated.validateMigration" -}}
{{- if not .Values.postgres.enabled -}}
{{- fail "migration.enabled requires postgres.enabled; the migration Job reaches only the in-chart PostgreSQL" -}}
{{- end -}}
{{- end }}

{{- define "generated.validateDatabase" -}}
{{- if not .Values.migration.enabled -}}
{{- fail "postgres.enabled requires migration.enabled; the migration Job creates the runtime role the backend connects with" -}}
{{- end -}}
{{- end }}

{{/*
Secrets of the in-chart database. The chart only names them; deploy.sh generates their values once
and reuses them from the cluster. The database and the migration own the schema owner connection;
the backend sees only the DML-only runtime connection.
*/}}
{{- define "generated.postgresSecret" -}}
{{- printf "%s-postgres" .Release.Name -}}
{{- end }}

{{- define "generated.migrationSecret" -}}
{{- printf "%s-migration" .Release.Name -}}
{{- end }}

{{- define "generated.databaseSecret" -}}
{{- printf "%s-database" .Release.Name -}}
{{- end }}

{{/*
Migration mode. "upgrade" when an earlier release already created the migration NetworkPolicy, so
the database exists and the Job runs as a pre-upgrade hook before any new backend pod. Otherwise
"bootstrap": the Job is an ordinary release resource created together with the database (fresh
install, or the first upgrade that adds the database), so nothing waits on backend readiness first.
helm template sees no cluster and always renders "bootstrap".
*/}}
{{- define "generated.migrationMode" -}}
{{- if lookup "networking.k8s.io/v1" "NetworkPolicy" .Release.Namespace (include "generated.resourceName" (list . "migration")) -}}
upgrade
{{- else -}}
bootstrap
{{- end -}}
{{- end }}

{{/*
backend.config carries only non-secret, prefixed settings; secrets and the database connection
arrive through envFrom, which an env entry would otherwise override.
*/}}
{{- define "generated.validateBackendConfig" -}}
{{- range $key, $value := .Values.backend.config -}}
{{- if not (regexMatch "^DWHNAVIGATOR_[A-Z0-9_]+$" $key) -}}
{{- fail (printf "backend.config key %s must be an upper-case DWHNAVIGATOR_ setting" $key) -}}
{{- end -}}
{{- if regexMatch "PASSW|SECRET|CREDENTIAL|PRIVATE_KEY|API_KEY|DATABASE_URL|DSN|(TOKEN|KEY)$" $key -}}
{{- fail (printf "backend.config key %s looks secret; put it in the project Secret" $key) -}}
{{- end -}}
{{- if kindIs "map" $value -}}
{{- fail (printf "backend.config value of %s must be a scalar" $key) -}}
{{- end -}}
{{- if kindIs "slice" $value -}}
{{- fail (printf "backend.config value of %s must be a scalar" $key) -}}
{{- end -}}
{{- end -}}
{{- end }}

{{/*
backend.strategy is optional. Empty keeps the Kubernetes default rolling update. A backend that
keeps in-process job state sets {type: Recreate}, so an upgrade never runs two backend pods at once.
*/}}
{{- define "generated.backendStrategy" -}}
{{- $strategy := .Values.backend.strategy | default dict -}}
{{- if not (kindIs "map" $strategy) -}}
{{- fail "backend.strategy must be a mapping" -}}
{{- end -}}
{{- if $strategy -}}
{{- range $key, $value := $strategy -}}
{{- if not (has $key (list "type" "rollingUpdate")) -}}
{{- fail (printf "backend.strategy key %s is not supported; use type and rollingUpdate" $key) -}}
{{- end -}}
{{- end -}}
{{- $type := $strategy.type | default "" | toString -}}
{{- if not (has $type (list "RollingUpdate" "Recreate")) -}}
{{- fail "backend.strategy.type must be RollingUpdate or Recreate" -}}
{{- end -}}
{{- if hasKey $strategy "rollingUpdate" -}}
{{- if eq $type "Recreate" -}}
{{- fail "backend.strategy.rollingUpdate is allowed only with type RollingUpdate" -}}
{{- end -}}
{{- $rolling := $strategy.rollingUpdate -}}
{{- if not (kindIs "map" $rolling) -}}
{{- fail "backend.strategy.rollingUpdate must be a mapping" -}}
{{- end -}}
{{- range $key, $value := $rolling -}}
{{- if not (has $key (list "maxSurge" "maxUnavailable")) -}}
{{- fail (printf "backend.strategy.rollingUpdate key %s is not supported; use maxSurge and maxUnavailable" $key) -}}
{{- end -}}
{{- if kindIs "string" $value -}}
{{- if not (regexMatch "^[0-9]{1,3}%$" $value) -}}
{{- fail (printf "backend.strategy.rollingUpdate.%s must be a whole number or a percentage" $key) -}}
{{- end -}}
{{- else if not (regexMatch "^[0-9]{1,6}$" (toString $value)) -}}
{{- fail (printf "backend.strategy.rollingUpdate.%s must be a whole number or a percentage" $key) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- toYaml $strategy -}}
{{- end -}}
{{- end }}

{{/*
frontend.ingress.annotations adds non-secret settings for the ingress controller, for example a
larger request body limit. The scaffold.kt.internal/ identity and Helm's own keys stay generated,
and configuration snippets, which run inside the shared controller, are refused.
*/}}
{{- define "generated.ingressAnnotations" -}}
{{- $annotations := .Values.frontend.ingress.annotations | default dict -}}
{{- if not (kindIs "map" $annotations) -}}
{{- fail "frontend.ingress.annotations must be a mapping" -}}
{{- end -}}
{{- range $key, $value := $annotations }}
{{- if not (regexMatch "^([a-z0-9]([-a-z0-9]*[a-z0-9])?(\\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*/)?[A-Za-z0-9]([-A-Za-z0-9_.]{0,61}[A-Za-z0-9])?$" $key) }}
{{- fail (printf "frontend.ingress.annotations key %s is not a valid annotation name" $key) }}
{{- end }}
{{- if or (hasPrefix "scaffold.kt.internal/" $key) (hasPrefix "helm.sh/" $key) (hasPrefix "meta.helm.sh/" $key) }}
{{- fail (printf "frontend.ingress.annotations key %s is generated by the chart and cannot be set" $key) }}
{{- end }}
{{- if regexMatch "(?i)snippet$" $key }}
{{- fail (printf "frontend.ingress.annotations key %s runs configuration inside the shared ingress controller and is refused" $key) }}
{{- end }}
{{- if or (kindIs "map" $value) (kindIs "slice" $value) }}
{{- fail (printf "frontend.ingress.annotations value of %s must be a scalar" $key) }}
{{- end }}
{{ $key }}: {{ $value | toString | quote }}
{{- end }}
{{- end }}
