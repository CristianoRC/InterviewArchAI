#!/bin/bash
# install.sh — configura o ambiente completo do local-arch-interviewer

set -e

echo ""
echo "======================================================"
echo "  local-arch-interviewer — Instalação"
echo "======================================================"
echo ""

# Verifica se o Homebrew está instalado
if ! command -v brew &>/dev/null; then
    echo "[ERRO] Homebrew não encontrado."
    echo "  → Instale em: https://brew.sh"
    exit 1
fi

# Instala o PortAudio (dependência nativa do sounddevice)
echo "[1/4] Instalando PortAudio via Homebrew..."
brew install portaudio

# Cria o ambiente virtual
echo "[2/4] Criando ambiente virtual (.venv)..."
python3 -m venv .venv

# Ativa o venv
source .venv/bin/activate

# Instala as dependências Python
echo "[3/4] Instalando dependências Python..."
pip install --upgrade pip --quiet
pip install -r requirements.txt

echo "[4/4] Pronto!"
echo ""
echo "======================================================"
echo "  Instalação concluída."
echo ""
echo "  Próximos passos:"
echo "  1. Abra o LM Studio e inicie o Local Server (porta 1234)"
echo "  2. Carregue um modelo com visão (ex: qwen/qwen3-vl-8b)"
echo "  3. Edite o SYSTEM_PROMPT em local_arch_interviewer.py"
echo "  4. Execute: ./run.sh  (abre o app desktop)"
echo "     Ou via CLI: python3 local_arch_interviewer.py"
echo "======================================================"
echo ""
