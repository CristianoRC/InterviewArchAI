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
    DIFICULDADE_PADRAO,
    MODEL,
    NIVEIS_DIFICULDADE,
    SAMPLE_RATE,
    STT_LANGUAGE,
    SYSTEM_PROMPT_TEMPLATE,
    VISION_MODEL,
    VOICE,
    WHISPER_MODEL_SIZE,
)

StatusCallback = Callable[[str], None]

_whisper: WhisperModel | None = None


def criar_cliente(base_url: str = BASE_URL, api_key: str = API_KEY) -> OpenAI:
    return OpenAI(base_url=base_url, api_key=api_key)


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


def falar_texto(
    texto: str,
    on_status: StatusCallback | None = None,
    on_inicio: Callable[[], None] | None = None,
    on_fim: Callable[[], None] | None = None,
) -> None:
    texto_limpo = limpar_texto(texto)
    if not texto_limpo:
        return

    if on_status:
        on_status("Reproduzindo áudio...")

    async def _gerar_e_reproduzir() -> None:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            caminho = tmp.name
        communicate = edge_tts.Communicate(texto_limpo, VOICE)
        await communicate.save(caminho)
        if on_inicio:
            on_inicio()
        try:
            subprocess.run(["afplay", caminho], check=True)
        finally:
            if on_fim:
                on_fim()
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


def imagem_para_base64(caminho: str) -> str:
    with open(caminho, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


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
    duracao_max: float = 90.0,
    silencio_seg: float = 2.0,
    limiar_rms: float = 0.008,
) -> str | None:
    """Grava até detectar silêncio após fala — um clique no mic basta."""
    if on_status:
        on_status("Ouvindo... fale agora.")

    frames: list[np.ndarray] = []
    bloco = int(SAMPLE_RATE * 0.1)

    def callback(indata: np.ndarray, _f, _t, _s) -> None:
        frames.append(indata.copy())

    inicio = time.time()
    silencio_desde: float | None = None
    falou = False

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        callback=callback,
        blocksize=bloco,
    ):
        while time.time() - inicio < duracao_max:
            time.sleep(0.15)
            if not frames:
                continue
            recente = np.concatenate(frames[-5:])
            rms = float(np.sqrt(np.mean(recente**2)))
            if rms >= limiar_rms:
                falou = True
                silencio_desde = None
            elif falou:
                if silencio_desde is None:
                    silencio_desde = time.time()
                elif time.time() - silencio_desde >= silencio_seg:
                    break

    if not frames or not falou:
        return None

    audio = (np.concatenate(frames) * 32767).astype(np.int16)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    wav.write(tmp.name, SAMPLE_RATE, audio)
    return tmp.name


def gravar_audio(parar_evento: threading.Event) -> str | None:
    frames: list[np.ndarray] = []

    def callback(indata: np.ndarray, _f, _t, _s) -> None:
        if not parar_evento.is_set():
            frames.append(indata.copy())

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=callback):
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
        mensagens = [{"role": "system", "content": system_prompt}] + historico
    else:
        if nome:
            gatilho = (
                f"Pode começar a entrevista com {nome}. "
                "Apresente o problema e faça a primeira pergunta."
            )
        else:
            gatilho = "Pode começar a entrevista. Apresente o problema e faça a primeira pergunta."
        mensagens = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": gatilho},
        ]

    modelo_escolhido = vision_model if caminho_imagem else model

    resposta = client.chat.completions.create(
        model=modelo_escolhido,
        messages=mensagens,
    )
    return resposta.choices[0].message.content.strip()
