#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3.12+ is required and was not found on PATH." >&2
  exit 1
fi

"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit(f"Python 3.12+ is required. Found {sys.version.split()[0]}.")
PY

if [[ ! -d .venv ]]; then
  echo "Creating .venv..."
  "$PYTHON_BIN" -m venv .venv
fi

VENV_PYTHON="$REPO_ROOT/.venv/bin/python"
VENV_PIP="$REPO_ROOT/.venv/bin/pip"

echo "Upgrading pip..."
"$VENV_PYTHON" -m pip install --upgrade pip

echo "Installing Veteran Access Bridge + dev dependencies..."
"$VENV_PIP" install -e ".[dev]"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example."
else
  echo ".env already exists; leaving it unchanged."
fi

echo "Verifying import..."
"$VENV_PYTHON" -c "import veteran_access_bridge; print('Veteran Access Bridge import OK')"

echo
echo "Setup complete."
echo "Activate with: source .venv/bin/activate"
echo "Run tests with: pytest"
echo "Start the demo with: veteran-access-demo"
