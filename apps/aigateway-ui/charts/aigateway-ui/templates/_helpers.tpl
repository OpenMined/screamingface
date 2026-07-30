{{- define "aigateway-ui.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "aigateway-ui.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "aigateway-ui.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "aigateway-ui.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "aigateway-ui.labels" -}}
helm.sh/chart: {{ include "aigateway-ui.chart" . }}
app.kubernetes.io/name: {{ include "aigateway-ui.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: screamingface
{{- end -}}

{{- define "aigateway-ui.selectorLabels" -}}
app.kubernetes.io/name: {{ include "aigateway-ui.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "aigateway-ui.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "aigateway-ui.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "aigateway-ui.image" -}}
{{- printf "%s:%s" .Values.image.repository (default .Chart.AppVersion .Values.image.tag) -}}
{{- end -}}

{{/*
The admin API's address — the ONE place this chart decides where the gateway is.

An explicit `aigateway.baseUrl` wins outright; otherwise the in-cluster Service DNS is built from
the parts. Resolving it in a helper rather than at each use means the ConfigMap and any future
consumer cannot disagree about where the gateway is.

The fully-qualified `.svc.cluster.local` form is deliberate over the short name: the short name
resolves only via the Pod's `search` domains, which differ between a same-namespace and a
cross-namespace install, so the same value would mean two things. The FQDN means one.
*/}}
{{- define "aigateway-ui.gatewayBaseUrl" -}}
{{- if .Values.aigateway.baseUrl -}}
{{- .Values.aigateway.baseUrl | trimSuffix "/" -}}
{{- else -}}
{{- $ns := .Values.aigateway.namespace | default .Release.Namespace -}}
{{- printf "http://%s.%s.svc.cluster.local:%v" (required "aigateway.serviceName is required when aigateway.baseUrl is not set — the console has no admin API to call without it" .Values.aigateway.serviceName) $ns .Values.aigateway.port -}}
{{- end -}}
{{- end -}}

{{/*
Refuse the one configuration that hands anyone the admin surface.

INVARIANT: the console trusts `X-User-Email` because the mesh gateway verifies Cloudflare Access
and injects it, stripping any client-supplied copy. An Ingress straight to this Service removes
that guarantee — the port becomes directly reachable, and a single
`curl -H 'X-User-Email: <an allowlisted admin>'` is full admin impersonation: create tenants,
attach provider API keys, enumerate every account.

The chart cannot verify that a mesh exists. It CAN refuse the combination that is unsafe on its
face, which is what aigateway's own `validateAuth` does for the same reason.
*/}}
{{- define "aigateway-ui.validateExposure" -}}
{{- if .Values.ingress.enabled -}}
{{- fail "ingress.enabled=true — the console trusts the X-User-Email header the mesh injects, so publishing an Ingress straight to it means any caller can set that header and become any admin (create tenants, attach provider API keys, read every account). There is no safe way to enable this: route the console through the same mesh gateway that authenticates Cloudflare Access and injects identity." -}}
{{- end -}}
{{- end -}}
