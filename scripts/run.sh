#!/bin/bash
# run.sh — ativa o ambiente virtual e inicia a entrevista

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Verifica se o venv existe
if [ ! -d ".venv" ]; then
    echo "[ERRO] Ambiente virtual não encontrado."
    echo "  → Execute primeiro: ./scripts/install.sh"
    exit 1
fi

source .venv/bin/activate
python3 -m app.main "$@"
