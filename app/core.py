"""Lógica de negócio: STT, TTS, screenshots e comunicação com o LM Studio."""

from __future__ import annotations

import asyncio
import base64
import os
import re
import subprocess
import tempfile
import threading
import time
from typing import Callable

import edge_tts
import numpy as np
import scipy.io.wavfile as wav
import sounddevice as sd
from faster_whisper import WhisperModel
from openai import APIConnectionError, OpenAI

from app.config import (
    API_KEY,
    BASE_URL,
    CHARS_POR_TOKEN,
    COMPACTAR_HISTORICO_LIMITE,
    COMPACTAR_MANTER_ULTIMAS,
    CONTEXTO_MAX_TOKENS,
    DIFICULDADE_PADRAO,
    FEEDBACK_PROMPT_TEMPLATE,
    GRAVACAO_MAX_SEG,
    IMAGEM_CUSTO_TOKENS,
    MODEL,
    NIVEIS_DIFICULDADE,
    PAUSA_PRONTO_SEG,
    RESPOSTA_MAX_TOKENS,
    SAMPLE_RATE,
    SCREENSHOT_MAX_DIM,
    STT_LANGUAGE,
    SYSTEM_PROMPT_TEMPLATE,
    VISION_MODEL,
    VOICE,
    WHISPER_MODEL_SIZE,
)

StatusCallback = Callable[[str], None]
AudioLevelCallback = Callable[[float], None]

_whisper: WhisperModel | None = None
_afplay_proc: subprocess.Popen[bytes] | None = None
_cancelar_fala = threading.Event()


def criar_cliente(base_url: str = BASE_URL, api_key: str = API_KEY) -> OpenAI:
    return OpenAI(base_url=base_url, api_key=api_key)


def mensagem_erro_amigavel(exc: Exception) -> str:
    """Traduz erros técnicos do LM Studio em mensagens acionáveis para o usuário."""
    texto = str(exc)
    baixo = texto.lower()

    if isinstance(exc, APIConnectionError) or "connection" in baixo:
        return (
            "Perdi a conexão com o LM Studio. Confirme que o servidor local está "
            "ligado em 'Local Server' (porta 1234) e tente de novo."
        )

    # Estouro de janela de contexto (n_ctx pequeno demais para o request).
    if "context" in baixo and ("exceed" in baixo or "context size" in baixo):
        tokens = re.search(r"\((\d+)\s*tokens?\)", texto)
        ctx = re.search(r"context size \((\d+)", texto)
        detalhe = ""
        if tokens and ctx:
            detalhe = f" (precisa de ~{tokens.group(1)} tokens, mas só há {ctx.group(1)})"
        return (
            f"A janela de contexto do modelo é pequena demais para esta conversa{detalhe}.\n\n"
            "Como resolver: no LM Studio, recarregue o modelo aumentando o "
            "'Context Length' (n_ctx) para 8192 ou mais (o Qwen3 suporta até 32768). "
            "Depois reinicie o servidor local e tente novamente."
        )

    return texto


def validar_servidor(client: OpenAI) -> tuple[bool, str]:
    try:
        client.models.list()
        return True, "Conectado ao LM Studio"
    except APIConnectionError:
        return (
            False,
            "Não foi possível conectar ao LM Studio. "
            "Abra o LM Studio, vá em 'Local Server' e clique em 'Start Server' (porta 1234).",
        )
    except Exception as exc:
        return False, f"Falha ao contatar o servidor: {exc}"


def limpar_texto(texto: str) -> str:
    texto = re.sub(r"\x1b\[[0-9;]*m", "", texto)
    # Remove o "raciocínio" que modelos como o Qwen3 emitem (<think>...</think>).
    # Cobre também o caso de a tag de abertura vir cortada/ausente.
    texto = re.sub(r"<think>[\s\S]*?</think>", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"^[\s\S]*?</think>", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"```[\s\S]*?```", "", texto)
    texto = re.sub(r"`([^`]+)`", r"\1", texto)
    texto = re.sub(r"\*\*([^*]+)\*\*", r"\1", texto)
    texto = re.sub(r"\*([^*]+)\*", r"\1", texto)
    texto = re.sub(r"__([^_]+)__", r"\1", texto)
    texto = re.sub(r"_([^_]+)_", r"\1", texto)
    texto = re.sub(r"^#{1,6}\s+", "", texto, flags=re.MULTILINE)
    texto = re.sub(r"^[\-*+]\s+", "", texto, flags=re.MULTILINE)
    texto = re.sub(r"^\d+\.\s+", "", texto, flags=re.MULTILINE)
    texto = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", texto)
    texto = re.sub(r"[#*_`~|>]", "", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def parar_fala() -> None:
    """Interrompe a reprodução TTS em andamento (ex.: ao fechar o app)."""
    global _afplay_proc
    _cancelar_fala.set()
    if _afplay_proc is not None and _afplay_proc.poll() is None:
        _afplay_proc.terminate()
        try:
            _afplay_proc.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            _afplay_proc.kill()
    _afplay_proc = None


def sintetizar_audio(texto: str) -> str | None:
    """Sintetiza ``texto`` com edge-tts e retorna o caminho do .mp3 gerado.

    Retorna None se o texto estiver vazio ou se a síntese for cancelada.
    O chamador é responsável por apagar o arquivo após a reprodução.
    """
    texto_limpo = limpar_texto(texto)
    if not texto_limpo:
        return None

    async def _sintetizar() -> str | None:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            caminho = tmp.name
        try:
            communicate = edge_tts.Communicate(texto_limpo, VOICE)
            await communicate.save(caminho)
        except Exception:
            if os.path.exists(caminho):
                os.remove(caminho)
            return None
        return caminho

    return asyncio.run(_sintetizar())


def reproduzir_mp3(
    caminho: str,
    on_status: StatusCallback | None = None,
    on_inicio: Callable[[], None] | None = None,
    on_fim: Callable[[], None] | None = None,
) -> None:
    """Reproduz um arquivo .mp3 já sintetizado via ``afplay`` e o apaga ao fim."""
    global _afplay_proc
    _cancelar_fala.clear()

    if on_status:
        on_status("Reproduzindo áudio...")

    reproduzindo = False
    if on_inicio:
        on_inicio()
        reproduzindo = True
    try:
        _afplay_proc = subprocess.Popen(["afplay", caminho])
        _afplay_proc.wait()
    finally:
        _afplay_proc = None
        if reproduzindo and on_fim:
            on_fim()
        if os.path.exists(caminho):
            os.remove(caminho)


def falar_texto(
    texto: str,
    on_status: StatusCallback | None = None,
    on_inicio: Callable[[], None] | None = None,
    on_fim: Callable[[], None] | None = None,
) -> None:
    texto_limpo = limpar_texto(texto)
    if not texto_limpo:
        return

    _cancelar_fala.clear()

    if on_status:
        on_status("Reproduzindo áudio...")

    async def _gerar_e_reproduzir() -> None:
        global _afplay_proc
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            caminho = tmp.name
        try:
            communicate = edge_tts.Communicate(texto_limpo, VOICE)
            await communicate.save(caminho)
            if _cancelar_fala.is_set():
                return

            reproduzindo = False
            if on_inicio:
                on_inicio()
                reproduzindo = True
            try:
                _afplay_proc = subprocess.Popen(["afplay", caminho])
                _afplay_proc.wait()
            finally:
                _afplay_proc = None
                if reproduzindo and on_fim:
                    on_fim()
        finally:
            if os.path.exists(caminho):
                os.remove(caminho)

    asyncio.run(_gerar_e_reproduzir())


def capturar_tela(display: int | None = None) -> str | None:
    """Captura um screenshot via `screencapture`.

    Se ``display`` for informado (índice 1-based do monitor), captura apenas
    aquele monitor. Caso contrário, captura a tela inteira (todos os monitores).
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()

    comando = ["screencapture", "-x", "-T", "0"]
    if display is not None:
        comando += ["-D", str(display)]
    comando.append(tmp.name)

    resultado = subprocess.run(comando, capture_output=True)

    if resultado.returncode != 0 or not os.path.getsize(tmp.name):
        os.remove(tmp.name)
        return None

    return tmp.name


def redimensionar_imagem(caminho: str, max_dim: int = SCREENSHOT_MAX_DIM) -> None:
    """Reduz a maior dimensão da imagem para ``max_dim`` px, in-place.

    Usa o ``sips`` nativo do macOS — sem dependências extras. Os tokens de
    visão de modelos como o Qwen3-VL escalam com a resolução, então reduzir a
    imagem é o que evita estourar a janela de contexto do LM Studio. Falhas
    são ignoradas: no pior caso, segue com a imagem original.
    """
    try:
        subprocess.run(
            ["sips", "-Z", str(max_dim), caminho],
            capture_output=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass


def imagem_para_base64(caminho: str) -> str:
    with open(caminho, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def listar_microfones() -> list[tuple[int, str]]:
    """Retorna dispositivos de entrada (índice, nome) disponíveis no sistema."""
    dispositivos: list[tuple[int, str]] = []
    for indice, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            dispositivos.append((indice, dev["name"]))
    return dispositivos


def indice_microfone_padrao() -> int | None:
    """Índice do microfone padrão do sistema, ou None se indisponível."""
    try:
        entrada = sd.default.device[0]
        if isinstance(entrada, (list, tuple)):
            return int(entrada[0]) if entrada else None
        return int(entrada)
    except Exception:
        return None


def carregar_whisper(on_status: StatusCallback | None = None) -> WhisperModel:
    global _whisper
    if _whisper is None:
        if on_status:
            on_status(f"Carregando Whisper '{WHISPER_MODEL_SIZE}'...")
        _whisper = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
        if on_status:
            on_status("Whisper pronto")
    return _whisper


def gravar_audio_ate_silencio(
    on_status: StatusCallback | None = None,
    on_nivel: AudioLevelCallback | None = None,
    on_falou: Callable[[], None] | None = None,
    on_silencio: Callable[[], None] | None = None,
    on_voz: Callable[[], None] | None = None,
    parar_evento: threading.Event | None = None,
    dispositivo: int | None = None,
    duracao_max: float = GRAVACAO_MAX_SEG,
    pausa_seg: float = PAUSA_PRONTO_SEG,
    limiar_rms: float = 0.008,
) -> str | None:
    """Grava até o candidato clicar em "Pronto" (parar_evento) ou atingir o
    limite de segurança `duracao_max`. NUNCA encerra automaticamente por silêncio.

    Callbacks de pausa:
    - on_falou: disparado uma vez quando a voz é detectada pela primeira vez.
    - on_silencio: disparado quando o silêncio (após falar) atinge `pausa_seg`,
      sinalizando uma pausa (momento de ativar o botão "Pronto").
    - on_voz: disparado quando o candidato volta a falar depois de uma pausa já
      sinalizada (momento de desativar o botão "Pronto")."""
    if on_status:
        on_status("Ouvindo... fale agora.")

    frames: list[np.ndarray] = []
    bloco = int(SAMPLE_RATE * 0.04)

    def callback(indata: np.ndarray, _f, _t, _s) -> None:
        frames.append(indata.copy())
        if on_nivel:
            on_nivel(float(np.sqrt(np.mean(indata**2))))

    inicio = time.time()
    silencio_desde: float | None = None
    falou = False
    pausa_sinalizada = False

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        callback=callback,
        blocksize=bloco,
        device=dispositivo,
    ):
        while time.time() - inicio < duracao_max:
            if parar_evento is not None and parar_evento.is_set():
                break
            time.sleep(0.08)
            if not frames:
                continue
            recente = np.concatenate(frames[-3:])
            rms = float(np.sqrt(np.mean(recente**2)))
            if rms >= limiar_rms:
                if not falou:
                    falou = True
                    if on_falou:
                        on_falou()
                if pausa_sinalizada:
                    # Voltou a falar depois de uma pausa: desativa o "Pronto".
                    pausa_sinalizada = False
                    if on_voz:
                        on_voz()
                silencio_desde = None
            elif falou:
                if silencio_desde is None:
                    silencio_desde = time.time()
                elif not pausa_sinalizada:
                    dur_silencio = time.time() - silencio_desde
                    if dur_silencio >= pausa_seg:
                        # Pausa detectada: ativa o botão "Pronto". A gravação NÃO
                        # encerra por silêncio — só pelo botão (parar_evento) ou
                        # pelo limite de segurança (duracao_max).
                        pausa_sinalizada = True
                        if on_silencio:
                            on_silencio()

    if not frames or not falou:
        return None

    audio = (np.concatenate(frames) * 32767).astype(np.int16)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    wav.write(tmp.name, SAMPLE_RATE, audio)
    return tmp.name


def gravar_audio(
    parar_evento: threading.Event,
    dispositivo: int | None = None,
) -> str | None:
    frames: list[np.ndarray] = []

    def callback(indata: np.ndarray, _f, _t, _s) -> None:
        if not parar_evento.is_set():
            frames.append(indata.copy())

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        callback=callback,
        device=dispositivo,
    ):
        parar_evento.wait()

    if not frames:
        return None

    audio = (np.concatenate(frames) * 32767).astype(np.int16)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    wav.write(tmp.name, SAMPLE_RATE, audio)
    return tmp.name


def transcrever_audio(caminho: str, on_status: StatusCallback | None = None) -> str:
    if on_status:
        on_status("Transcrevendo...")
    modelo = carregar_whisper(on_status)
    segments, _ = modelo.transcribe(caminho, language=STT_LANGUAGE)
    texto = " ".join(s.text for s in segments).strip()
    os.remove(caminho)
    return texto


def montar_mensagem_usuario(texto: str, caminho_imagem: str | None) -> dict:
    if not caminho_imagem:
        return {"role": "user", "content": texto}

    redimensionar_imagem(caminho_imagem)
    imagem_b64 = imagem_para_base64(caminho_imagem)
    os.remove(caminho_imagem)

    return {
        "role": "user",
        "content": [
            {"type": "text", "text": texto},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{imagem_b64}"},
            },
        ],
    }


def montar_system_prompt(
    problema: str,
    nome: str = "Candidato",
    senioridade: str = DIFICULDADE_PADRAO,
) -> str:
    instrucao_dificuldade = NIVEIS_DIFICULDADE.get(
        senioridade, NIVEIS_DIFICULDADE[DIFICULDADE_PADRAO]
    )
    return SYSTEM_PROMPT_TEMPLATE.format(
        problema=problema, nome=nome, dificuldade=instrucao_dificuldade
    )


def montar_feedback_prompt(
    problema: str,
    nome: str = "Candidato",
    senioridade: str = DIFICULDADE_PADRAO,
) -> str:
    instrucao_dificuldade = NIVEIS_DIFICULDADE.get(
        senioridade, NIVEIS_DIFICULDADE[DIFICULDADE_PADRAO]
    )
    return FEEDBACK_PROMPT_TEMPLATE.format(
        problema=problema, nome=nome, dificuldade=instrucao_dificuldade
    )


def gerar_feedback_final(
    client: OpenAI,
    historico: list[dict],
    problema: str,
    nome: str = "Candidato",
    senioridade: str = DIFICULDADE_PADRAO,
    model: str = MODEL,
) -> str:
    feedback_system = montar_feedback_prompt(problema, nome, senioridade)
    gatilho = (
        "A entrevista terminou. Saindo do papel de entrevistador provocador, me dê "
        "agora o seu feedback final completo e honesto sobre o meu desempenho, "
        "seguindo a estrutura combinada."
    )
    # O feedback é mais longo: reservamos uma fatia maior do contexto para a saída
    # e encaixamos o histórico no que sobrar.
    reserva_feedback = min(CONTEXTO_MAX_TOKENS // 2, 1200)
    historico = garantir_contexto(
        historico,
        feedback_system,
        client=client,
        model=model,
        reserva_resposta=reserva_feedback + estimar_tokens_texto(gatilho),
    )
    mensagens = (
        [{"role": "system", "content": feedback_system}]
        + historico
        + [{"role": "user", "content": gatilho}]
    )
    resposta = client.chat.completions.create(
        model=model, messages=mensagens, max_tokens=reserva_feedback
    )
    return resposta.choices[0].message.content.strip()


RESUMO_PREFIXO = "Resumo da entrevista até aqui (contexto para você manter a linha de raciocínio):"


def _tem_imagem(msg: dict) -> bool:
    content = msg.get("content")
    return isinstance(content, list) and any(
        bloco.get("type") == "image_url" for bloco in content
    )


def _texto_da_mensagem(msg: dict) -> str:
    content = msg.get("content")
    if isinstance(content, list):
        for bloco in content:
            if bloco.get("type") == "text":
                return bloco.get("text", "")
        return ""
    return content or ""


def estimar_tokens_texto(texto: str) -> int:
    """Estimativa grosseira (conservadora) de tokens para um texto."""
    if not texto:
        return 0
    return int(len(texto) / CHARS_POR_TOKEN) + 1


def estimar_tokens_mensagem(msg: dict) -> int:
    """Estima os tokens de uma mensagem, somando o custo da imagem se houver."""
    total = estimar_tokens_texto(_texto_da_mensagem(msg))
    if _tem_imagem(msg):
        total += IMAGEM_CUSTO_TOKENS
    return total + 4  # pequena folga por mensagem (papel, separadores do template)


def estimar_tokens(mensagens: list[dict]) -> int:
    return sum(estimar_tokens_mensagem(m) for m in mensagens)


def _eh_resumo(msg: dict) -> bool:
    return (
        msg.get("role") == "system"
        and isinstance(msg.get("content"), str)
        and msg["content"].startswith(RESUMO_PREFIXO)
    )


def _remover_imagens_antigas(historico: list[dict]) -> list[dict]:
    """Mantém a imagem apenas na última mensagem que tem imagem; nas anteriores
    substitui o anexo por um marcador de texto, para poupar tokens de visão."""
    idx_ultima = -1
    for i, msg in enumerate(historico):
        if _tem_imagem(msg):
            idx_ultima = i
    if idx_ultima == -1:
        return historico

    novo: list[dict] = []
    for i, msg in enumerate(historico):
        if _tem_imagem(msg) and i != idx_ultima:
            texto = _texto_da_mensagem(msg).strip()
            marcador = "[diagrama enviado antes, removido do histórico]"
            texto = f"{texto} {marcador}".strip() if texto else marcador
            novo.append({"role": msg.get("role", "user"), "content": texto})
        else:
            novo.append(msg)
    return novo


def _mensagens_para_transcricao(mensagens: list[dict]) -> str:
    linhas: list[str] = []
    for msg in mensagens:
        if _eh_resumo(msg):
            continue
        papel = "Entrevistadora" if msg.get("role") == "assistant" else "Candidato"
        texto = _texto_da_mensagem(msg).strip()
        if _tem_imagem(msg):
            texto = f"{texto} [enviou um diagrama]".strip()
        if texto:
            linhas.append(f"{papel}: {texto}")
    return "\n".join(linhas)


def _resumir_trecho(
    client: OpenAI,
    resumo_atual: str,
    mensagens_antigas: list[dict],
    model: str,
) -> str:
    instrucao = (
        "Você resume entrevistas de System Design para preservar o contexto sem estourar "
        "a memória do modelo. Gere um resumo objetivo em português, em tópicos curtos, do "
        "que JÁ aconteceu na entrevista: o problema, requisitos e escala definidos, decisões "
        "e componentes que o candidato propôs, justificativas dadas, pontos fortes e fracos "
        "já observados e o que ficou pendente. Preserve fatos e números exatos. Não invente "
        "nada que não tenha sido dito. Seja conciso."
    )
    partes: list[str] = []
    if resumo_atual:
        partes.append("Resumo anterior (já consolidado):\n" + resumo_atual)
    partes.append(
        "Novas mensagens da entrevista a incorporar ao resumo:\n"
        + _mensagens_para_transcricao(mensagens_antigas)
    )
    mensagens = [
        {"role": "system", "content": instrucao},
        {"role": "user", "content": "\n\n".join(partes)},
    ]
    resposta = client.chat.completions.create(model=model, messages=mensagens)
    resumo = resposta.choices[0].message.content.strip()
    return f"{RESUMO_PREFIXO}\n{resumo}"


def compactar_historico(
    client: OpenAI,
    historico: list[dict],
    model: str = MODEL,
    limite: int = COMPACTAR_HISTORICO_LIMITE,
    manter_ultimas: int = COMPACTAR_MANTER_ULTIMAS,
    orcamento_tokens: int | None = None,
) -> list[dict]:
    """Evita estourar o contexto em entrevistas longas.

    1) Descarta imagens antigas (mantém só o último diagrama).
    2) Se o histórico passa do limite de mensagens OU do orçamento de tokens,
       resume as mensagens mais antigas num único bloco e mantém apenas as
       últimas `manter_ultimas` literais.
    Retorna um novo histórico (não muta o original)."""
    historico = _remover_imagens_antigas(list(historico))

    passou_limite = len(historico) > limite
    passou_orcamento = (
        orcamento_tokens is not None and estimar_tokens(historico) > orcamento_tokens
    )
    if not passou_limite and not passou_orcamento:
        return historico

    resumo_atual = ""
    corpo = historico
    if historico and _eh_resumo(historico[0]):
        resumo_atual = historico[0]["content"]
        corpo = historico[1:]

    if len(corpo) <= manter_ultimas:
        cabeca = [{"role": "system", "content": resumo_atual}] if resumo_atual else []
        return cabeca + corpo

    antigas = corpo[:-manter_ultimas]
    recentes = corpo[-manter_ultimas:]

    try:
        novo_resumo = _resumir_trecho(client, resumo_atual, antigas, model)
    except Exception:
        # Se a sumarização falhar, ainda devolvemos o histórico sem imagens
        # antigas para não travar a entrevista por causa da compactação.
        return historico

    return [{"role": "system", "content": novo_resumo}] + recentes


def _forcar_caber(mensagens: list[dict], orcamento: int) -> list[dict]:
    """Última linha de defesa: derruba mensagens (das mais antigas para as mais
    recentes) até o conjunto caber no orçamento, sempre preservando o system
    prompt (primeiro item) e a última mensagem. Evita o erro 400 a todo custo."""
    if estimar_tokens(mensagens) <= orcamento or len(mensagens) <= 2:
        return mensagens

    cabeca = [mensagens[0]]  # system prompt
    miolo = mensagens[1:-1]
    cauda = [mensagens[-1]]  # mensagem mais recente (a fala atual)

    while miolo and estimar_tokens(cabeca + miolo + cauda) > orcamento:
        miolo.pop(0)

    return cabeca + miolo + cauda


def garantir_contexto(
    historico: list[dict],
    system_prompt: str,
    client: OpenAI | None = None,
    model: str = MODEL,
    max_contexto: int = CONTEXTO_MAX_TOKENS,
    reserva_resposta: int = RESPOSTA_MAX_TOKENS,
) -> list[dict]:
    """Garante que system prompt + histórico caibam na janela do modelo.

    Calcula o orçamento disponível (janela menos a reserva para a resposta e o
    custo do system prompt) e compacta o histórico até caber. Se ainda não
    couber após resumir, derruba as rodadas mais antigas. Retorna o histórico
    ajustado (não muta o original)."""
    orcamento_historico = max(
        0, max_contexto - reserva_resposta - estimar_tokens_texto(system_prompt) - 8
    )

    ajustado = list(historico)
    if client is not None:
        ajustado = compactar_historico(
            client, ajustado, model=model, orcamento_tokens=orcamento_historico
        )
    else:
        ajustado = _remover_imagens_antigas(ajustado)

    return _forcar_caber(
        [{"role": "system", "content": system_prompt}] + ajustado,
        max_contexto - reserva_resposta,
    )[1:]


def obter_resposta_ia(
    client: OpenAI,
    historico: list[dict],
    system_prompt: str,
    caminho_imagem: str | None = None,
    model: str = MODEL,
    vision_model: str = VISION_MODEL,
    nome: str = "",
) -> str:
    if historico:
        historico = garantir_contexto(historico, system_prompt, client=client, model=model)
        mensagens = [{"role": "system", "content": system_prompt}] + historico
    else:
        alvo = f" com {nome}" if nome else ""
        gatilho = (
            f"Comece a entrevista{alvo}. Saudação curtíssima pelo nome e enuncie o problema "
            "em no máximo duas frases. NÃO liste requisitos, NÃO dê detalhes de escala ou "
            "escopo e NÃO faça perguntas de início. Termine no enunciado do problema e pare. "
            "NÃO escreva nenhuma frase dizendo que está passando a vez, aguardando ou ouvindo "
            "(nada de 'passo a palavra', 'agora é com você', 'fico no aguardo')."
        )
        mensagens = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": gatilho},
        ]

    modelo_escolhido = vision_model if caminho_imagem else model

    resposta = client.chat.completions.create(
        model=modelo_escolhido,
        messages=mensagens,
        max_tokens=RESPOSTA_MAX_TOKENS,
        temperature=0.4,
    )
    escolha = resposta.choices[0]
    texto = (escolha.message.content or "").strip()
    # Se o modelo bateu no teto de tokens (finish_reason="length"), a fala foi
    # cortada no meio. Em vez de mandar uma frase quebrada pro TTS, aparamos até
    # a última frase completa para nunca soar truncado.
    if getattr(escolha, "finish_reason", None) == "length":
        texto = _aparar_frase_incompleta(texto)
    return texto


def _aparar_frase_incompleta(texto: str) -> str:
    """Remove uma última frase incompleta (corte por limite de tokens).

    Mantém o texto até o último terminador de frase (. ! ? … ou nova linha). Se
    não houver nenhum terminador (a resposta inteira é uma frase só, cortada),
    devolve o texto original — melhor uma frase incompleta do que nada."""
    if not texto:
        return texto
    terminadores = ".!?…\n"
    ultimo = max(texto.rfind(c) for c in terminadores)
    if ultimo == -1:
        return texto
    return texto[: ultimo + 1].strip()
