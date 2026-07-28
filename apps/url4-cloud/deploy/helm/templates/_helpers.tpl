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

{{/* Runner image defaults to the App image (one image, two entrypoints — spec §1.1). */}}
{{- define "url4-cloud.runnerImage" -}}
{{- default (include "url4-cloud.image" .) .Values.runner.image -}}
{{- end -}}

{{/* Name of the Secret holding the JWT signing secret (created here or supplied). */}}
{{- define "url4-cloud.authSecretName" -}}
{{- if .Values.auth.create -}}
{{- include "url4-cloud.fullname" . -}}
{{- else -}}
{{- required "auth.existingSecret is required when auth.create is false" .Values.auth.existingSecret -}}
{{- end -}}
{{- end -}}
