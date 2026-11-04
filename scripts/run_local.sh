#!/usr/bin/env bash
# Arranca el CRM de Felix Software en modo local: sin Meta, sin WhatsApp y (si no hay clave) sin IA real.
# Uso:  ./scripts/run_local.sh            -> http://localhost:8000
#       PORT=9000 ./scripts/run_local.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${PORT:-8000}"
if [ ! -d venv ]; then
  python3 -m venv venv
  ./venv/bin/pip install -q -r requirements.txt
fi

export MOCK_INTEGRATIONS=true
export DATABASE_URL="${DATABASE_URL:-sqlite+aiosqlite:///./local_crm.db}"
export BUSINESS_NAME="${BUSINESS_NAME:-Felix Software}"
export BUSINESS_ROLE="${BUSINESS_ROLE:-un estudio de desarrollo de software a la medida con rentas mensuales accesibles}"
export BUSINESS_DESCRIPTION="${BUSINESS_DESCRIPTION:-Software a la medida (CaaS) con renta mensual accesible. Asesoría gratuita.}"
export KB_SEED_FILE="${KB_SEED_FILE:-data/kb_felix_software.json}"
export BOOKING_URL="${BOOKING_URL:-https://calendar.google.com/ejemplo-de-enlace}"
export OWNER_WHATSAPP="${OWNER_WHATSAPP:-5210000000000}"
export PORT

echo "→ CRM local en http://localhost:${PORT}  (pestaña 🧪 Simulador para probar)"
exec ./venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port "$PORT"
