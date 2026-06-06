#!/bin/bash
# run.sh — ativa o ambiente virtual e inicia a entrevista

set -e

# Verifica se o venv existe
if [ ! -d ".venv" ]; then
    echo "[ERRO] Ambiente virtual não encontrado."
    echo "  → Execute primeiro: ./install.sh"
    exit 1
fi

source .venv/bin/activate
python3 -m app.main "$@"
