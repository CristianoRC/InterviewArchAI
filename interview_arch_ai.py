"""
interview-arch-ai (CLI)
=======================
Versão terminal — mantida para compatibilidade.
Para a interface desktop, execute: python -m app.main
"""

import argparse
import sys
import threading

from openai import OpenAI

from app.config import DIFICULDADE_PADRAO, NIVEIS_DIFICULDADE, PROBLEMA
from app.core import (
    capturar_tela,
    criar_cliente,
    falar_texto,
    gravar_audio,
    limpar_texto,
    montar_mensagem_usuario,
    montar_system_prompt,
    obter_resposta_ia,
    transcrever_audio,
    validar_servidor,
)


def obter_entrada_usuario() -> tuple[str, str | None]:
    """Captura voz e tela via terminal (push-to-talk com ENTER)."""
    input("\n[Mic] Pressione ENTER para começar a gravar...")

    parar = threading.Event()
    caminho_audio: str | None = None

    def _gravar() -> None:
        nonlocal caminho_audio
        caminho_audio = gravar_audio(parar)

    thread = threading.Thread(target=_gravar, daemon=True)
    thread.start()
    input("[Mic] Ouvindo... pressione ENTER para parar.")
    parar.set()
    thread.join()

    texto = ""
    if caminho_audio:
        print("[STT] Transcrevendo...")
        texto = transcrever_audio(caminho_audio)

    if texto:
        print(f"\nVocê (transcrito): {texto}\n")

    print("[Tela] Capturando screenshot...")
    caminho_screenshot = capturar_tela()
    if caminho_screenshot:
        print("[Tela] Screenshot capturado.\n")
    else:
        print("[Tela] Falha ao capturar screenshot — seguindo sem imagem.\n")

    return texto, caminho_screenshot


def resolver_problema(problema_cli: str | None) -> str:
    problema = (problema_cli or PROBLEMA).strip()
    if problema:
        return problema
    print("Descreva o problema de system design para esta entrevista:")
    return input("> ").strip()


def loop_entrevista(client: OpenAI, problema: str, senioridade: str = DIFICULDADE_PADRAO) -> None:
    historico: list[dict] = []
    system_prompt = montar_system_prompt(problema, senioridade=senioridade)

    print("\n" + "=" * 60)
    print("  InterviewArchAI  —  System Design por voz")
    print("  Fale 'sair' a qualquer momento para encerrar.")
    print("=" * 60)
    print(f"\nProblema: {problema}\n")

    print("[Entrevistador está pensando...]\n")
    fala_entrevistador = limpar_texto(obter_resposta_ia(client, historico, system_prompt))

    while True:
        print(f"Entrevistador:\n{fala_entrevistador}\n")
        falar_texto(fala_entrevistador)
        historico.append({"role": "assistant", "content": fala_entrevistador})

        print("-" * 60)
        try:
            resposta_usuario, caminho_screenshot = obter_entrada_usuario()
        except EOFError:
            break

        if resposta_usuario.lower().strip().rstrip(".") == "sair":
            print("Entrevista encerrada. Até a próxima!\n")
            break

        if not resposta_usuario:
            fala_entrevistador = "Não consegui te ouvir. Pode repetir?"
            continue

        mensagem_usuario = montar_mensagem_usuario(resposta_usuario, caminho_screenshot)
        historico.append(mensagem_usuario)

        print("[Entrevistador está pensando...]\n")
        fala_entrevistador = limpar_texto(
            obter_resposta_ia(client, historico, system_prompt, caminho_screenshot)
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Entrevista de System Design por voz com modelo local (CLI).",
    )
    parser.add_argument(
        "--problema", "-p",
        default=None,
        help="Descrição do problema de system design.",
    )
    parser.add_argument(
        "--senioridade", "-s",
        default=DIFICULDADE_PADRAO,
        choices=list(NIVEIS_DIFICULDADE.keys()),
        help="Senioridade da vaga, calibra a dificuldade da entrevista.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    problema = resolver_problema(args.problema)
    if not problema:
        print("\n[ERRO] É necessário informar o problema da entrevista.\n")
        sys.exit(1)

    client = criar_cliente()
    ok, msg = validar_servidor(client)
    if not ok:
        print(f"\n[ERRO] {msg}\n")
        sys.exit(1)

    try:
        loop_entrevista(client, problema, args.senioridade)
    except KeyboardInterrupt:
        print("\n\nEntrevista interrompida. Até a próxima!\n")


if __name__ == "__main__":
    main()
