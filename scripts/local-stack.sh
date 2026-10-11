#!/usr/bin/env bash
# Run the demo stack without Docker, using local prometheus / grafana binaries.
# Usage: PROMETHEUS=/path/to/prometheus GRAFANA_HOME=/path/to/grafana scripts/local-stack.sh up|down
# Grafana is optional; without GRAFANA_HOME only the service and Prometheus start.
set -euo pipefail
cd "$(dirname "$0")/.."
STATE=.local-stack
PROMETHEUS=${PROMETHEUS:-$(command -v prometheus || true)}
PY=${PYTHON:-python3}

up() {
  [[ -x "$PROMETHEUS" ]] || { echo "prometheus binary not found; set PROMETHEUS=" >&2; exit 1; }
  mkdir -p "$STATE"/{prom-data,grafana-data,grafana-prov/datasources,grafana-prov/dashboards,dashboards}
  sed 's/demo:8080/localhost:8080/; s#/etc/prometheus/rules#'"$PWD"'/examples/http-api/out#' \
    deploy/prometheus/prometheus.yml > "$STATE/prometheus.yml"
  PORT=8080 nohup "$PY" demo/service.py > "$STATE/demo.log" 2>&1 & echo $! > "$STATE/demo.pid"
  nohup "$PROMETHEUS" --config.file="$STATE/prometheus.yml" --storage.tsdb.path="$STATE/prom-data" --storage.tsdb.retention.time="${RETENTION:-400d}" \
    --web.enable-lifecycle > "$STATE/prometheus.log" 2>&1 & echo $! > "$STATE/prometheus.pid"
  if [[ -n "${GRAFANA_HOME:-}" ]]; then
    sed 's#http://prometheus:9090#http://localhost:9090#' deploy/grafana/provisioning/datasources/prometheus.yaml \
      > "$STATE/grafana-prov/datasources/prometheus.yaml"
    sed 's#/var/lib/grafana/dashboards#'"$PWD/$STATE"'/dashboards#' deploy/grafana/provisioning/dashboards/slo.yaml \
      > "$STATE/grafana-prov/dashboards/slo.yaml"
    cp examples/http-api/out/*.dashboard.json "$STATE/dashboards/"
    GF_PATHS_DATA="$PWD/$STATE/grafana-data" GF_PATHS_PROVISIONING="$PWD/$STATE/grafana-prov" \
    GF_AUTH_ANONYMOUS_ENABLED=true GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer \
    nohup "$GRAFANA_HOME/bin/grafana" server --homepath "$GRAFANA_HOME" > "$STATE/grafana.log" 2>&1 &
    echo $! > "$STATE/grafana.pid"
  fi
  echo "demo :8080  prometheus :9090${GRAFANA_HOME:+  grafana :3000}   (logs in $STATE/)"
}

down() {
  for pidfile in "$STATE"/*.pid; do
    [[ -e "$pidfile" ]] && kill "$(cat "$pidfile")" 2>/dev/null || true
    rm -f "$pidfile"
  done
  echo "stopped"
}

"${1:-up}"
