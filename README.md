<p align="center">
  <img src="assets/app_icon.png" alt="InterviewArchAI logo" width="200"/>
</p>

<h1 align="center">InterviewArchAI</h1>

<p align="center">
  Simule entrevistas de System Design por voz com IA rodando <strong>100% local</strong> via <a href="https://lmstudio.ai">LM Studio</a>.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/macOS-only-lightgrey?logo=apple" alt="macOS"/>
  <img src="https://img.shields.io/badge/Python-3.9+-blue?logo=python" alt="Python 3.9+"/>
  <img src="https://img.shields.io/badge/LM%20Studio-local%20LLM-blueviolet" alt="LM Studio"/>
  <img src="https://img.shields.io/badge/licença-MIT-green" alt="MIT License"/>
</p>

## O que é

**InterviewArchAI** é um entrevistador de System Design que funciona **100% offline** na sua máquina. Ele usa um modelo de linguagem com visão (via LM Studio), reconhecimento de voz local (Whisper) e síntese de voz em PT-BR (Edge TTS) para conduzir entrevistas técnicas interativas por voz.

Disponível como **app desktop para macOS** (interface gráfica) ou via **terminal (CLI)**.

---

## Como funciona

1. O entrevistador (IA local) faz uma pergunta — o texto aparece na tela e é **falado em PT-BR** via Edge TTS.
2. Você clica em **Gravar Resposta** e fala no microfone.
3. O Whisper local transcreve sua fala automaticamente.
4. Um **screenshot da sua tela** é capturado e enviado junto com o texto para o modelo analisar diagramas ou código visíveis.
5. O ciclo se repete até você encerrar a entrevista ou falar "sair".

---

## Pré-requisitos

| Requisito | Versão / Observação |
|-----------|-------------------|
| macOS | Qualquer — usa `screencapture` e `afplay` nativos |
| Python | 3.9+ |
| LM Studio | Com Local Server na porta 1234 |
| Modelo carregado | Com suporte a visão — recomendado: `qwen/qwen3-vl-8b` |
| PortAudio | Necessário para captura de microfone |

---

## Instalação

```bash
./scripts/install.sh
```

Ou manualmente:

```bash
brew install portaudio
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Execução

### App desktop (recomendado)

```bash
./scripts/run.sh
```

Ou:

```bash
source .venv/bin/activate
python3 -m app.main
```

### Versão terminal (CLI)

```bash
source .venv/bin/activate
python3 interview_arch_ai.py
```

---

## Interface desktop

### Tela inicial

- Informe seu **nome**
- Descreva o **problema** da entrevista
- Clique em **Começar**

### Janela flutuante (durante a entrevista)

Após iniciar, o app vira uma janela compacta que **fica sempre visível** no canto da tela:

- O entrevistador fala e o texto aparece na janela
- Quando for sua vez, clique no **botão do microfone** e fale — a gravação para automaticamente ao detectar silêncio
- Screenshot da tela é capturado e o ciclo continua
- Arraste pela barra superior para reposicionar a janela

> Antes de iniciar, abra o LM Studio, carregue um modelo com visão e inicie o Local Server na porta 1234.

---

## Configuração

Edite `app/config.py` para alterar voz, modelo Whisper ou problema padrão:

```python
VOICE = "pt-BR-FranciscaNeural"  # feminina (padrão)
MODEL = "qwen/qwen3-vl-8b"
WHISPER_MODEL_SIZE = "tiny"
SCREENSHOT_MAX_DIM = 1024  # maior dimensão (px) do screenshot enviado ao modelo
```

O screenshot é redimensionado (via `sips`) para que sua maior dimensão não passe de `SCREENSHOT_MAX_DIM` antes de ser enviado. Como os "tokens de visão" escalam com a resolução da imagem, esse limite é o principal fator para não estourar a janela de contexto. Diminua para `768` se ainda estourar; aumente para `1280+` se precisar de mais detalhe nos diagramas.
ENSHOT_MAX_DIM` em `app/config.py`.

---

## Estrutura do projeto

```
talk-system-design/
├── app/
│   ├── config.py               # Configurações padrão
│   ├── core.py                 # STT, TTS, screenshots, API
│   ├── gui.py                  # Interface desktop
│   └── main.py                 # Ponto de entrada do app
├── assets/
│   └── app_icon_v2.png         # Logo do projeto
├── interview_arch_ai.py        # Versão CLI (terminal)
├── requirements.txt
├── scripts/
│   ├── install.sh              # Instalação do ambiente
│   └── run.sh                  # Inicia o app desktop
└── README.md
```

---

## Aviso

> **Aviso:** Este projeto é um **experimento de estudo** sobre o uso de IA rodando localmente e suas possibilidades. Ele funciona, mas ainda apresenta limitações — principalmente o modelo de exemplo (`qwen/qwen3-vl-8b`) alucinando em entrevistas mais longas por ter uma janela de contexto pequena. Não espere um produto finalizado: é um ponto de partida para explorar o que dá pra fazer com LLMs 100% offline.

---

## Licença

Este projeto está licenciado sob a [MIT License](LICENSE).
