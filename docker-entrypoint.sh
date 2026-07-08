#!/bin/sh
set -e

# Bind-mounted ./uploads may be owned by root or the host user; ensure appuser can write.
# GCS mode does not require writable /app/uploads for user content (only optional
# debug artifacts when ENABLE_ARTIFACT_LOGGING=true).
mkdir -p /app/uploads/reference_materials /app/uploads/artifacts
chown -R appuser:appuser /app/uploads

if [ "$(id -u)" = "0" ]; then
  exec su appuser -s /bin/sh -c "$*"
fi

exec "$@"
