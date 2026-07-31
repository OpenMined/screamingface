{{/*
Name helpers + k8s recommended labels (app.kubernetes.io/*) — spec §9 / docs/protocol.md §9.
*/}}

{{- define "url4-cloud.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "url4-cloud.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "url4-cloud.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "url4-cloud.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Common labels: k8s recommended set (name/instance/version/managed-by/part-of) + chart. */}}
{{- define "url4-cloud.labels" -}}
helm.sh/chart: {{ include "url4-cloud.chart" . }}
{{ include "url4-cloud.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: screamingface
app.kubernetes.io/component: control-plane
{{- end -}}

{{/* Selector labels: the immutable identity subset (name + instance). */}}
{{- define "url4-cloud.selectorLabels" -}}
app.kubernetes.io/name: {{ include "url4-cloud.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "url4-cloud.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "url4-cloud.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "url4-cloud.image" -}}
{{- printf "%s:%s" .Values.image.repository (default .Chart.AppVersion .Values.image.tag) -}}
{{- end -}}

{{/*
The image a Runner Job runs. Defaults to the App's own image (one artifact, two modes); a
deployment may override it to ship a Job-only payload the control plane must not carry.

The ONLY intended override is a benchmark image (`Dockerfile.benchmark`), which layers a dataset
— including the private rubrics — onto the base. The Runner executes the run and needs them; the
control plane terminates client connections and must never hold a rubric on disk.

WHY `tag` falls back to the APP's resolved tag rather than to `latest`: a benchmark image is built
`FROM` a specific base tag, so the two are a matched pair. Overriding `repository` alone therefore
keeps the Job and the App on one version — which is the drift protection the merged-image design
was built for, kept intact while allowing the split payload.
*/}}
{{- define "url4-cloud.runnerImage" -}}
{{- $override := (.Values.runner).image | default dict -}}
{{- $repo := $override.repository | default .Values.image.repository -}}
{{- $tag := $override.tag | default (default .Chart.AppVersion .Values.image.tag) -}}
{{- printf "%s:%s" $repo $tag -}}
{{- end -}}

{{/*
Where the App reaches NATS.

WHY a helper and not a plain value: the previous default hardcoded `nats://url4-cloud-nats:4222`,
which only resolves when the release happens to be named `url4-cloud` — the subchart's Service is
`<release>-nats`. Enabling the subchart under any other release name pointed the App at a Service
that does not exist, and nothing caught it until a live connect failed.

We deliberately do NOT derive this from the subchart's own `nats.fullname` helper: that reaches
into another chart's private template names and breaks on a dependency bump. Instead the operator
states the Service name once (`nats.fullnameOverride`) and this fails at render time — at
`helm install`, not on the first publish — if neither source is present.
*/}}
{{- define "url4-cloud.natsUrl" -}}
{{- if .Values.config.natsUrl -}}
{{- .Values.config.natsUrl -}}
{{- else if .Values.nats.enabled -}}
{{- $n := required "nats.fullnameOverride is required when nats.enabled=true (it fixes the Service name this URL is built from) — or set config.natsUrl explicitly" .Values.nats.fullnameOverride -}}
{{- printf "nats://%s:4222" $n -}}
{{- else -}}
{{- fail "config.natsUrl is required when nats.enabled=false — the App has no bus to reach otherwise" -}}
{{- end -}}
{{- end -}}

{{/* Name of the Secret holding the JWT signing secret (created here or supplied). */}}
{{- define "url4-cloud.authSecretName" -}}
{{- if .Values.auth.create -}}
{{- include "url4-cloud.fullname" . -}}
{{- else -}}
{{- required "auth.existingSecret is required when auth.create is false" .Values.auth.existingSecret -}}
{{- end -}}
{{- end -}}

{{/*
Name of the Secret holding the Tavily web-tools key. An `existingSecret` wins (bring-your-own,
the prod shape); otherwise the chart creates `<fullname>-tavily` from `tavily.apiKey`.
Only referenced when `tavily.enabled` — the App names this Secret in each Runner Job's env and
never reads it itself.
*/}}
{{- define "url4-cloud.tavilySecretName" -}}
{{- if .Values.tavily.existingSecret -}}
{{- .Values.tavily.existingSecret -}}
{{- else -}}
{{- printf "%s-tavily" (include "url4-cloud.fullname" .) -}}
{{- end -}}
{{- end -}}
