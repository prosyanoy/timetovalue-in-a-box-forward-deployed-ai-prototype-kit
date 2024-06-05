{{- define "ttv.labels" -}}
app.kubernetes.io/part-of: ttv
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "ttv.commonEnv" -}}
- name: SCENARIO
  value: {{ .Values.scenario | quote }}
- name: BUS_URL
  value: "nats://nats:4222"
- name: SEED
  value: {{ .Values.generator.seed | quote }}
{{- end -}}
