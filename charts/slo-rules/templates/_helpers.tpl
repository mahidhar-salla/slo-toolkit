{{- define "slo-rules.name" -}}
{{- printf "%s-slo" .Values.service | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "slo-rules.labels" -}}
app.kubernetes.io/name: {{ include "slo-rules.name" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: slo-toolkit
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}
