#!/bin/sh
set -e

# Bind-mounted ./uploads may be owned by root or the host user; ensure appuser can write.
# GCS mode does not require writable /app/uploads for user content (only optional
# debug artifacts when ENABLE_ARTIFACT_LOGGING=true).
mkdir -p /app/uploads/reference_materials /app/uploads/artifacts
chown -R appuser:appuser /app/uploads

run_as_appuser() {
  if [ "$(id -u)" = "0" ]; then
    exec su appuser -s /bin/sh -c "$1"
  fi
  exec /bin/sh -c "$1"
}

if [ "${WORKER_MODE}" = "true" ]; then
  WORKER_CMD=".venv/bin/python -c \"import os, subprocess, threading; from http.server import HTTPServer, BaseHTTPRequestHandler as B; H = type('H', (B,), {'do_GET': lambda s: (s.send_response(200), s.end_headers()), 'log_message': lambda *a: None}); threading.Thread(target=HTTPServer(('0.0.0.0', int(os.environ.get('PORT', '8001'))), H).serve_forever, daemon=True).start(); raise SystemExit(subprocess.call(['.venv/bin/procrastinate', '-a', 'src.api.batch.procrastinate_app.app', 'worker', '--concurrency', os.environ.get('WORKER_CONCURRENCY', '1')]))\""
  run_as_appuser "${WORKER_CMD}"
fi

if [ "$(id -u)" = "0" ]; then
  exec su appuser -s /bin/sh -c "$*"
fi

exec "$@"
