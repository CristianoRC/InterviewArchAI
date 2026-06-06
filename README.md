# local-arch-interviewer

Simule entrevistas de System Design por voz usando um modelo de linguagem com visão rodando **100% local** via [LM Studio](https://lmstudio.ai).

Disponível como **app desktop para macOS** (interface gráfica) ou via terminal (CLI).

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
./install.sh
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
./run.sh
```

Ou:

```bash
source .venv/bin/activate
python3 -m app.main
```

### Versão terminal (CLI)

```bash
source .venv/bin/activate
python3 local_arch_interviewer.py
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

Antes de iniciar, abra o LM Studio, carregue um modelo com visão e inicie o Local Server na porta 1234.

---

## Configuração

Edite `app/config.py` para alterar voz, modelo Whisper ou problema padrão:

```python
VOICE = "pt-BR-FranciscaNeural"  # feminina (padrão)
MODEL = "qwen/qwen3-vl-8b"
WHISPER_MODEL_SIZE = "tiny"
```

---

## Estrutura do projeto

```
talk-system-design/
├── app/
│   ├── config.py               # Configurações padrão
│   ├── core.py                 # STT, TTS, screenshots, API
│   ├── gui.py                  # Interface desktop
│   └── main.py                 # Ponto de entrada do app
├── local_arch_interviewer.py   # Versão CLI (terminal)
├── requirements.txt
├── install.sh
├── run.sh
└── README.md
```

---

## Licença

MIT
