{{/*
Expand the name of the chart.
*/}}
{{- define "slo-scout.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "slo-scout.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "slo-scout.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "slo-scout.labels" -}}
helm.sh/chart: {{ include "slo-scout.chart" . }}
{{ include "slo-scout.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: slo-scout
environment: {{ .Values.global.environment }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "slo-scout.selectorLabels" -}}
app.kubernetes.io/name: {{ include "slo-scout.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "slo-scout.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "slo-scout.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Get the namespace
*/}}
{{- define "slo-scout.namespace" -}}
{{- default .Release.Namespace .Values.namespaceOverride }}
{{- end }}

{{/*
Image pull policy
*/}}
{{- define "slo-scout.imagePullPolicy" -}}
{{- if .Values.global.imageRegistry }}
{{- printf "%s" .Values.global.imageRegistry }}
{{- else }}
{{- printf "docker.io" }}
{{- end }}
{{- end }}

{{/*
Kafka bootstrap servers
*/}}
{{- define "slo-scout.kafkaBootstrapServers" -}}
{{- if .Values.kafka.enabled }}
{{- printf "%s-kafka:9092" .Release.Name }}
{{- else }}
{{- required "External Kafka bootstrap servers required when kafka.enabled=false" .Values.externalKafka.bootstrapServers }}
{{- end }}
{{- end }}

{{/*
Database host
*/}}
{{- define "slo-scout.databaseHost" -}}
{{- if .Values.timescaledb.enabled }}
{{- printf "%s-timescaledb" .Release.Name }}
{{- else }}
{{- required "External database host required when timescaledb.enabled=false" .Values.externalDatabase.host }}
{{- end }}
{{- end }}

{{/*
MinIO endpoint
*/}}
{{- define "slo-scout.minioEndpoint" -}}
{{- if .Values.minio.enabled }}
{{- printf "http://%s-minio:9000" .Release.Name }}
{{- else }}
{{- required "External S3 endpoint required when minio.enabled=false" .Values.externalS3.endpoint }}
{{- end }}
{{- end }}

{{/*
Milvus host
*/}}
{{- define "slo-scout.milvusHost" -}}
{{- if .Values.milvus.enabled }}
{{- printf "%s-milvus" .Release.Name }}
{{- else }}
{{- required "External Milvus host required when milvus.enabled=false" .Values.externalMilvus.host }}
{{- end }}
{{- end }}

{{/*
Common environment variables for all components
*/}}
{{- define "slo-scout.commonEnv" -}}
- name: ENVIRONMENT
  value: {{ .Values.global.environment | quote }}
- name: LOG_LEVEL
  valueFrom:
    configMapKeyRef:
      name: slo-scout-config
      key: LOG_LEVEL
- name: KAFKA_BOOTSTRAP_SERVERS
  value: {{ include "slo-scout.kafkaBootstrapServers" . | quote }}
{{- end }}
