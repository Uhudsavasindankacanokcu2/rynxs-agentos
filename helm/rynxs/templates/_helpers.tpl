{{/*
Expand the name of the chart.
*/}}
{{- define "rynxs.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "rynxs.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "rynxs.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/*
Common labels
*/}}
{{- define "rynxs.labels" -}}
app.kubernetes.io/name: {{ include "rynxs.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | quote }}
{{- end -}}

{{/*
Selector labels
*/}}
{{- define "rynxs.selectorLabels" -}}
app.kubernetes.io/name: {{ include "rynxs.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Create the name of the service account to use
*/}}
{{- define "rynxs.serviceAccountName" -}}
{{- if .Values.rbac.create -}}
{{- default (include "rynxs.fullname" .) .Values.rbac.serviceAccountName -}}
{{- else -}}
{{- default "default" .Values.rbac.serviceAccountName -}}
{{- end -}}
{{- end -}}
