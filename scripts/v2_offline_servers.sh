#!/usr/bin/env bash
# Start OFFLINE TEST MODE servers for local demos and browser tests.
#   :8000  in-memory Supabase double + label test extractor
#   :8001  same, but the REAL GeminiExtractor with no API key (provider-failure path)
# Requires ADMIN_PASSWORD in the environment. Ctrl+C stops both.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${ADMIN_PASSWORD:?Set ADMIN_PASSWORD for the local admin console}"
export VENDORFLOW_OFFLINE_MODE=1 COOKIE_SECURE=0
unset SUPABASE_URL SUPABASE_SECRET_KEY SUPABASE_SERVICE_ROLE_KEY
.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
env -u GEMINI_API_KEY VENDORFLOW_OFFLINE_EXTRACTOR=gemini \
  .venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8001 &
trap 'kill $(jobs -p) 2>/dev/null' EXIT INT TERM
wait
