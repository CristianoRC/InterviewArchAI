"""Interface desktop macOS — setup inicial + janela flutuante compacta."""

from __future__ import annotations

import math
import sys
import threading

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.config import BASE_URL, DIFICULDADE_PADRAO, MODEL, PROBLEMA

OPCOES_SENIORIDADE = [
    ("junior", "Júnior"),
    ("pleno", "Pleno"),
    ("senior", "Sênior"),
    ("senior_plus", "Sênior+ / Staff"),
]
from app.core import (
    capturar_tela,
    criar_cliente,
    falar_texto,
    gravar_audio_ate_silencio,
    limpar_texto,
    montar_mensagem_usuario,
    montar_system_prompt,
    obter_resposta_ia,
    transcrever_audio,
    validar_servidor,
)

ESTILO_APP = """
QMainWindow, QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
}
QTextEdit, QLineEdit {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 8px;
    padding: 10px;
    font-size: 14px;
}
QPushButton {
    background-color: #89b4fa;
    color: #1e1e2e;
    border: none;
    border-radius: 8px;
    padding: 14px 24px;
    font-size: 15px;
    font-weight: bold;
}
QPushButton:hover { background-color: #b4befe; }
QPushButton:disabled { background-color: #45475a; color: #6c7086; }
QPushButton#mic {
    background-color: #f38ba8;
    border-radius: 28px;
    min-width: 56px;
    min-height: 56px;
    max-width: 56px;
    max-height: 56px;
    font-size: 24px;
    padding: 0;
}
QPushButton#mic:hover { background-color: #eba0ac; }
QPushButton#mic:disabled { background-color: #45475a; color: #6c7086; }
QPushButton#mic_gravando {
    background-color: #cba6f7;
    border-radius: 28px;
    min-width: 56px;
    min-height: 56px;
    max-width: 56px;
    max-height: 56px;
    font-size: 24px;
    padding: 0;
}
QPushButton#fechar {
    background-color: transparent;
    color: #6c7086;
    font-size: 16px;
    padding: 2px 8px;
    border-radius: 6px;
}
QPushButton#fechar:hover { background-color: #45475a; color: #f38ba8; }
"""

LARGURA_FLUTUANTE = 280
ALTURA_FLUTUANTE = 200
NUM_BARRAS_ONDA = 16


class OndaVoz(QWidget):
    """Visualizador animado de onda de voz enquanto a IA fala."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(40)
        self._ativo = False
        self._fase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animar)
        self.hide()

    def set_ativo(self, ativo: bool) -> None:
        self._ativo = ativo
        if ativo:
            self.show()
            self._timer.start(45)
        else:
            self._timer.stop()
            self._fase = 0.0
            self.hide()
            self.update()

    def _animar(self) -> None:
        self._fase += 0.22
        self.update()

    def paintEvent(self, _event) -> None:
        if not self._ativo:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        margem = 12
        area_w = w - 2 * margem
        bar_w = max(3, area_w // (NUM_BARRAS_ONDA * 2))
        gap = bar_w
        cor = QColor("#89b4fa")

        for i in range(NUM_BARRAS_ONDA):
            t = self._fase + i * 0.55
            altura_norm = (math.sin(t) + math.sin(t * 1.7 + 0.4)) / 2
            altura_norm = 0.25 + 0.75 * abs(altura_norm)
            bar_h = max(4, int(altura_norm * (h - 8)))
            x = margem + i * (bar_w + gap)
            y = (h - bar_h) // 2
            painter.setBrush(cor)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(x, y, bar_w, bar_h, 2, 2)


class TelaInicial(QWidget):
    def __init__(self, parent: "InterviewApp") -> None:
        super().__init__()
        self.app = parent
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(12)

        titulo = QLabel("Local Arch Interviewer")
        titulo.setStyleSheet("font-size: 26px; font-weight: bold;")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(titulo)

        subtitulo = QLabel("Simulador de entrevista de System Design por voz")
        subtitulo.setStyleSheet("color: #a6adc8; font-size: 14px;")
        subtitulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitulo)
        layout.addSpacing(16)

        layout.addWidget(QLabel("Seu nome"))
        self.nome_entry = QLineEdit()
        self.nome_entry.setPlaceholderText("Ex: Cristiano")
        layout.addWidget(self.nome_entry)

        layout.addWidget(QLabel("Senioridade da vaga"))
        self.senioridade_combo = QComboBox()
        for chave, rotulo in OPCOES_SENIORIDADE:
            self.senioridade_combo.addItem(rotulo, chave)
        idx_padrao = self.senioridade_combo.findData(DIFICULDADE_PADRAO)
        if idx_padrao >= 0:
            self.senioridade_combo.setCurrentIndex(idx_padrao)
        layout.addWidget(self.senioridade_combo)

        layout.addWidget(QLabel("Tela a capturar"))
        self.tela_combo = QComboBox()
        self._popular_telas()
        layout.addWidget(self.tela_combo)

        layout.addWidget(QLabel("Problema da entrevista"))
        self.problema_text = QTextEdit()
        self.problema_text.setPlainText(PROBLEMA)
        self.problema_text.setMinimumHeight(220)
        layout.addWidget(self.problema_text)

        self.status_conexao = QLabel("Verificando conexão com LM Studio...")
        self.status_conexao.setStyleSheet("color: #a6adc8; font-size: 12px;")
        self.status_conexao.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_conexao)

        layout.addSpacing(8)
        self.btn_comecar = QPushButton("Começar")
        self.btn_comecar.clicked.connect(self.app._iniciar_entrevista)
        layout.addWidget(self.btn_comecar)

    def _popular_telas(self) -> None:
        """Lista os monitores conectados. Data = índice 1-based (None = tudo)."""
        self.tela_combo.clear()
        self.tela_combo.addItem("Tela inteira (todos os monitores)", None)

        primaria = QApplication.primaryScreen()
        for indice, screen in enumerate(QApplication.screens(), start=1):
            geo = screen.geometry()
            marca = " — principal" if screen is primaria else ""
            rotulo = f"{indice}. {screen.name()} ({geo.width()}x{geo.height()}){marca}"
            self.tela_combo.addItem(rotulo, indice)


class BarraTitulo(QWidget):
    def __init__(self, app: "InterviewApp", parent=None) -> None:
        super().__init__(parent)
        self.app = app
        self._offset = None
        self.setFixedHeight(28)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_candidato = QLabel("Entrevista")
        self.lbl_candidato.setStyleSheet("font-size: 11px; font-weight: bold; color: #a6adc8;")
        layout.addWidget(self.lbl_candidato)
        layout.addStretch()

        btn_fechar = QPushButton("✕")
        btn_fechar.setObjectName("fechar")
        btn_fechar.setFixedSize(24, 24)
        btn_fechar.clicked.connect(self.app._encerrar_entrevista)
        layout.addWidget(btn_fechar)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._offset = event.globalPosition().toPoint() - self.app.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if self._offset is not None:
            self.app.move(event.globalPosition().toPoint() - self._offset)

    def mouseReleaseEvent(self, event) -> None:
        self._offset = None


class TelaFlutuante(QWidget):
    def __init__(self, parent: "InterviewApp") -> None:
        super().__init__()
        self.app = parent

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 6, 10, 8)
        root.setSpacing(4)

        self.barra_titulo = BarraTitulo(self.app)
        root.addWidget(self.barra_titulo)

        self.onda_voz = OndaVoz()
        root.addWidget(self.onda_voz)

        self.ultima_fala = QLabel("Aguardando...")
        self.ultima_fala.setWordWrap(True)
        self.ultima_fala.setStyleSheet(
            "color: #cdd6f4; font-size: 12px; padding: 6px; "
            "background-color: #313244; border-radius: 6px;"
        )
        self.ultima_fala.setMaximumHeight(56)
        root.addWidget(self.ultima_fala)

        self.status_label = QLabel("Pronto")
        self.status_label.setStyleSheet("color: #6c7086; font-size: 10px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.status_label)

        mic_row = QHBoxLayout()
        mic_row.addStretch()
        self.btn_mic = QPushButton("🎙")
        self.btn_mic.setObjectName("mic")
        self.btn_mic.setEnabled(False)
        self.btn_mic.clicked.connect(self.app._ao_clicar_mic)
        mic_row.addWidget(self.btn_mic)
        mic_row.addStretch()
        root.addLayout(mic_row)

    def atualizar_ultima_fala(self, texto: str) -> None:
        self.ultima_fala.setText(texto)

    def set_onda_ativa(self, ativo: bool) -> None:
        self.onda_voz.set_ativo(ativo)


class InterviewApp(QMainWindow):
    status_changed = pyqtSignal(str)
    ultima_fala_changed = pyqtSignal(str)
    habilitar_mic = pyqtSignal(bool)
    mic_gravando = pyqtSignal(bool)
    onda_ativa = pyqtSignal(bool)
    mostrar_erro = pyqtSignal(str)
    conexao_atualizada = pyqtSignal(bool, str)
    voltar_setup = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Local Arch Interviewer")
        self.resize(520, 620)
        self.setMinimumSize(480, 560)

        self.client = criar_cliente()
        self.historico: list[dict] = []
        self.system_prompt = ""
        self.fala_entrevistador = ""
        self.nome_candidato = ""
        self.entrevista_ativa = False
        self.processando_mic = False
        self.display_captura: int | None = None

        self.stack = QStackedWidget()
        self.tela_inicial = TelaInicial(self)
        self.tela_flutuante = TelaFlutuante(self)
        self.stack.addWidget(self.tela_inicial)
        self.stack.addWidget(self.tela_flutuante)
        self.setCentralWidget(self.stack)

        self.setStyleSheet(ESTILO_APP)
        self._conectar_sinais()
        self._verificar_conexao()

    def _conectar_sinais(self) -> None:
        self.status_changed.connect(self.tela_flutuante.status_label.setText)
        self.ultima_fala_changed.connect(self.tela_flutuante.atualizar_ultima_fala)
        self.habilitar_mic.connect(self._on_habilitar_mic)
        self.mic_gravando.connect(self._on_mic_gravando)
        self.onda_ativa.connect(self.tela_flutuante.set_onda_ativa)
        self.mostrar_erro.connect(lambda msg: QMessageBox.critical(self, "Erro", msg))
        self.conexao_atualizada.connect(self._on_conexao_atualizada)
        self.voltar_setup.connect(self._on_voltar_setup)

    def _on_conexao_atualizada(self, ok: bool, msg: str) -> None:
        cor = "#a6e3a1" if ok else "#f38ba8"
        self.tela_inicial.status_conexao.setText(msg)
        self.tela_inicial.status_conexao.setStyleSheet(f"color: {cor}; font-size: 12px;")

    def _on_habilitar_mic(self, habilitado: bool) -> None:
        self.tela_flutuante.btn_mic.setEnabled(habilitado and not self.processando_mic)

    def _on_mic_gravando(self, gravando: bool) -> None:
        btn = self.tela_flutuante.btn_mic
        if gravando:
            btn.setObjectName("mic_gravando")
            btn.setEnabled(False)
        else:
            btn.setObjectName("mic")
        btn.setStyle(btn.style())

    def _set_status(self, texto: str) -> None:
        self.status_changed.emit(texto)

    def _falar_entrevistador(self, texto: str) -> None:
        falar_texto(
            texto,
            on_status=self._set_status,
            on_inicio=lambda: self.onda_ativa.emit(True),
            on_fim=lambda: self.onda_ativa.emit(False),
        )

    def _verificar_conexao(self) -> None:
        def _checar() -> None:
            ok, msg = validar_servidor(self.client)
            self.conexao_atualizada.emit(ok, msg)

        threading.Thread(target=_checar, daemon=True).start()

    def _ativar_modo_flutuante(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedSize(LARGURA_FLUTUANTE, ALTURA_FLUTUANTE)

        tela = QApplication.primaryScreen()
        if tela:
            geo = tela.availableGeometry()
            self.move(geo.right() - self.width() - 16, geo.bottom() - self.height() - 16)

        self.stack.setCurrentWidget(self.tela_flutuante)
        self.show()
        self.raise_()
        self.activateWindow()

    def _iniciar_entrevista(self) -> None:
        nome = self.tela_inicial.nome_entry.text().strip()
        problema = self.tela_inicial.problema_text.toPlainText().strip()
        senioridade = self.tela_inicial.senioridade_combo.currentData()
        self.display_captura = self.tela_inicial.tela_combo.currentData()

        if not nome:
            QMessageBox.warning(self, "Nome", "Informe seu nome para começar.")
            return
        if not problema:
            QMessageBox.warning(self, "Problema", "Descreva o problema da entrevista.")
            return

        self.client = criar_cliente(base_url=BASE_URL)
        ok, msg = validar_servidor(self.client)
        if not ok:
            QMessageBox.critical(self, "LM Studio", msg)
            return

        self.nome_candidato = nome
        self.entrevista_ativa = True
        self.historico = []
        self.system_prompt = montar_system_prompt(problema, nome, senioridade)

        self.tela_flutuante.barra_titulo.lbl_candidato.setText(nome)
        self.tela_flutuante.ultima_fala.setText("Aguardando entrevistador...")
        self._ativar_modo_flutuante()
        self._set_status("Pensando...")
        self.habilitar_mic.emit(False)

        threading.Thread(target=self._loop_primeira_fala, daemon=True).start()

    def _loop_primeira_fala(self) -> None:
        try:
            fala = limpar_texto(
                obter_resposta_ia(
                    self.client,
                    self.historico,
                    self.system_prompt,
                    model=MODEL,
                    vision_model=MODEL,
                    nome=self.nome_candidato,
                )
            )
            self.fala_entrevistador = fala
            self.ultima_fala_changed.emit(fala)
            self._falar_entrevistador(fala)
            self.habilitar_mic.emit(True)
            self._set_status("Sua vez")
        except Exception as exc:
            self.mostrar_erro.emit(str(exc))
            self.voltar_setup.emit()

    def _ao_clicar_mic(self) -> None:
        if self.processando_mic or not self.entrevista_ativa:
            return
        self.processando_mic = True
        self.habilitar_mic.emit(False)
        self.mic_gravando.emit(True)
        threading.Thread(target=self._processar_fala, daemon=True).start()

    def _processar_fala(self) -> None:
        try:
            caminho_audio = gravar_audio_ate_silencio(on_status=self._set_status)
            self.mic_gravando.emit(False)

            texto = ""
            if caminho_audio:
                texto = transcrever_audio(caminho_audio, on_status=self._set_status)

            if texto:
                self.ultima_fala_changed.emit(f"Você: {texto}")

            if texto.lower().strip().rstrip(".") == "sair":
                self._finalizar_entrevista()
                return

            if not texto:
                self.fala_entrevistador = "Não consegui te ouvir. Tente de novo."
                self.ultima_fala_changed.emit(self.fala_entrevistador)
                self._falar_entrevistador(self.fala_entrevistador)
                self.processando_mic = False
                self.habilitar_mic.emit(True)
                self._set_status("Sua vez")
                return

            self._set_status("Capturando tela...")
            caminho_screenshot = capturar_tela(self.display_captura)

            mensagem = montar_mensagem_usuario(texto, caminho_screenshot)
            self.historico.append({"role": "assistant", "content": self.fala_entrevistador})
            self.historico.append(mensagem)

            self._set_status("Pensando...")

            fala = limpar_texto(
                obter_resposta_ia(
                    self.client,
                    self.historico,
                    self.system_prompt,
                    caminho_screenshot,
                    model=MODEL,
                    vision_model=MODEL,
                )
            )
            self.fala_entrevistador = fala
            self.ultima_fala_changed.emit(fala)
            self._falar_entrevistador(fala)
            self.processando_mic = False
            self.habilitar_mic.emit(True)
            self._set_status("Sua vez")
        except Exception as exc:
            self.mic_gravando.emit(False)
            self.onda_ativa.emit(False)
            self.processando_mic = False
            self.mostrar_erro.emit(str(exc))
            self.habilitar_mic.emit(True)

    def _encerrar_entrevista(self) -> None:
        resp = QMessageBox.question(
            self,
            "Encerrar",
            "Deseja encerrar a entrevista?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if resp == QMessageBox.StandardButton.Yes:
            self._finalizar_entrevista()

    def _finalizar_entrevista(self) -> None:
        self.entrevista_ativa = False
        self.processando_mic = False
        self.onda_ativa.emit(False)
        self.ultima_fala_changed.emit("Entrevista encerrada.")
        self._set_status("Encerrada")
        self.habilitar_mic.emit(False)
        self.voltar_setup.emit()

    def _on_voltar_setup(self) -> None:
        self.setWindowFlags(Qt.WindowType.Window)
        self.setMinimumSize(480, 560)
        self.setMaximumSize(16777215, 16777215)
        self.resize(520, 620)
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(
                geo.center().x() - self.width() // 2,
                geo.center().y() - self.height() // 2,
            )
        self.tela_inicial._popular_telas()
        self.stack.setCurrentWidget(self.tela_inicial)
        self.show()
        self._verificar_conexao()


def run() -> None:
    app = QApplication(sys.argv)
    font = QFont()
    font.setPointSize(13)
    app.setFont(font)

    window = InterviewApp()
    window.show()
    sys.exit(app.exec())
