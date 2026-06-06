"""Interface desktop macOS — setup inicial + janela flutuante compacta."""

from __future__ import annotations

import math
import sys
import threading
from ctypes import c_void_p
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QIcon,
    QLinearGradient,
    QPainter,
)
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.config import (
    BASE_URL,
    COMPACTAR_HISTORICO_LIMITE,
    DIFICULDADE_PADRAO,
    MODEL,
    PROBLEMA,
)

OPCOES_SENIORIDADE = [
    ("junior", "Júnior"),
    ("pleno", "Pleno"),
    ("senior", "Sênior"),
    ("senior_plus", "Sênior+ / Staff"),
]
from app.core import (
    capturar_tela,
    compactar_historico,
    criar_cliente,
    falar_texto,
    gerar_feedback_final,
    gravar_audio_ate_silencio,
    indice_microfone_padrao,
    limpar_texto,
    listar_microfones,
    montar_mensagem_usuario,
    montar_system_prompt,
    obter_resposta_ia,
    parar_fala,
    transcrever_audio,
    validar_servidor,
)

ACCENT = "#0A84FF"


def fonte_sistema() -> str:
    """Família da fonte de interface do sistema (San Francisco no macOS).

    Usar a família real evita o custo de o Qt resolver aliases para nomes
    inexistentes como "SF Pro Text" (gera o aviso qt.qpa.fonts).
    """
    familia = QFontDatabase.systemFont(
        QFontDatabase.SystemFont.GeneralFont
    ).family()
    return familia or "Helvetica Neue"

CAMINHO_ICONE = Path(__file__).resolve().parent.parent / "assets" / "app_icon.png"


def carregar_icone() -> QIcon:
    """Carrega o ícone do app (vazio se o arquivo não existir)."""
    if CAMINHO_ICONE.exists():
        return QIcon(str(CAMINHO_ICONE))
    return QIcon()

def montar_estilo(fonte: str) -> str:
    return f"""
* {{
    font-family: "{fonte}";
    outline: none;
}}
QMainWindow {{
    background: transparent;
}}
QWidget#root {{
    background: transparent;
}}
QWidget#setup {{
    background-color: qlineargradient(
        x1: 0, y1: 0, x2: 0.4, y2: 1,
        stop: 0 #20222B, stop: 1 #14151B
    );
}}
QScrollArea#setupScroll, QScrollArea#setupScroll > QWidget > QWidget {{
    background: transparent;
    border: none;
}}
QWidget#setupConteudo {{
    background: transparent;
}}
QWidget#flutuante {{
    background-color: rgba(26, 27, 34, 0.92);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 22px;
}}

QLabel {{
    color: rgba(255, 255, 255, 0.92);
    background: transparent;
    font-size: 13px;
}}
QLabel#titulo {{
    font-size: 30px;
    font-weight: 700;
    color: #ffffff;
    letter-spacing: -0.5px;
}}
QLabel#subtitulo {{
    font-size: 14px;
    color: rgba(235, 235, 245, 0.55);
}}
QLabel#fieldLabel {{
    font-size: 11px;
    font-weight: 600;
    color: rgba(235, 235, 245, 0.5);
    text-transform: uppercase;
    letter-spacing: 0.6px;
}}

QFrame#card {{
    background-color: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 18px;
}}

QLineEdit, QTextEdit, QComboBox {{
    background-color: rgba(255, 255, 255, 0.07);
    color: #ffffff;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 11px;
    padding: 11px 13px;
    font-size: 14px;
    selection-background-color: {ACCENT};
    selection-color: #ffffff;
}}
QLineEdit:hover, QTextEdit:hover, QComboBox:hover {{
    background-color: rgba(255, 255, 255, 0.10);
    border: 1px solid rgba(255, 255, 255, 0.18);
}}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
    background-color: rgba(255, 255, 255, 0.11);
    border: 1px solid rgba(10, 132, 255, 0.85);
}}
QComboBox::drop-down {{
    border: none;
    width: 28px;
}}
QComboBox QAbstractItemView {{
    background-color: #26262e;
    color: #ffffff;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 12px;
    padding: 5px;
    selection-background-color: {ACCENT};
    selection-color: #ffffff;
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    border-radius: 8px;
    padding: 7px 9px;
    min-height: 22px;
}}

QPushButton#primario {{
    background-color: {ACCENT};
    color: #ffffff;
    border: none;
    border-radius: 13px;
    padding: 15px 24px;
    font-size: 15px;
    font-weight: 600;
}}
QPushButton#primario:hover {{ background-color: #2E96FF; }}
QPushButton#primario:pressed {{ background-color: #0066D6; }}
QPushButton#primario:disabled {{
    background-color: rgba(255, 255, 255, 0.10);
    color: rgba(255, 255, 255, 0.35);
}}

QPushButton#mic {{
    background-color: rgba(255, 255, 255, 0.11);
    color: #ffffff;
    border: 1px solid rgba(255, 255, 255, 0.20);
    border-radius: 24px;
    min-width: 48px;
    min-height: 48px;
    max-width: 48px;
    max-height: 48px;
    font-size: 21px;
    padding: 0;
}}
QPushButton#mic:hover {{
    background-color: rgba(255, 255, 255, 0.17);
    border: 1px solid rgba(255, 255, 255, 0.30);
}}
QPushButton#mic:disabled {{
    background-color: rgba(255, 255, 255, 0.04);
    color: rgba(255, 255, 255, 0.22);
    border: 1px solid rgba(255, 255, 255, 0.07);
}}
QPushButton#mic_gravando {{
    background-color: rgba(255, 69, 58, 0.88);
    color: #ffffff;
    border: 1px solid rgba(255, 130, 120, 0.45);
    border-radius: 24px;
    min-width: 48px;
    min-height: 48px;
    max-width: 48px;
    max-height: 48px;
    font-size: 21px;
    padding: 0;
}}

QPushButton#pronto {{
    background-color: rgba(10, 132, 255, 0.18);
    color: rgba(90, 200, 250, 0.55);
    border: 1px solid rgba(10, 132, 255, 0.30);
    border-radius: 20px;
    min-width: 72px;
    min-height: 40px;
    max-height: 40px;
    font-size: 13px;
    font-weight: 600;
    padding: 0 12px;
}}
QPushButton#pronto:disabled {{
    background-color: rgba(255, 255, 255, 0.04);
    color: rgba(255, 255, 255, 0.22);
    border: 1px solid rgba(255, 255, 255, 0.08);
}}
QPushButton#pronto_piscando {{
    background-color: rgba(10, 132, 255, 0.55);
    color: #ffffff;
    border: 1px solid rgba(90, 200, 250, 0.85);
    border-radius: 20px;
    min-width: 72px;
    min-height: 40px;
    max-height: 40px;
    font-size: 13px;
    font-weight: 600;
    padding: 0 12px;
}}
QPushButton#pronto_piscando:hover {{
    background-color: rgba(10, 132, 255, 0.70);
    border: 1px solid rgba(90, 200, 250, 1.0);
}}

QPushButton#telaToggle {{
    background-color: rgba(255, 255, 255, 0.08);
    color: rgba(255, 255, 255, 0.55);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 20px;
    min-width: 40px;
    min-height: 40px;
    max-width: 40px;
    max-height: 40px;
    font-size: 17px;
    padding: 0;
}}
QPushButton#telaToggle:hover {{
    background-color: rgba(255, 255, 255, 0.13);
    border: 1px solid rgba(255, 255, 255, 0.24);
}}
QPushButton#telaToggle:disabled {{
    background-color: rgba(255, 255, 255, 0.03);
    color: rgba(255, 255, 255, 0.18);
    border: 1px solid rgba(255, 255, 255, 0.06);
}}
QPushButton#telaToggle_ativo {{
    background-color: rgba(10, 132, 255, 0.22);
    color: #5AC8FA;
    border: 1px solid rgba(10, 132, 255, 0.65);
    border-radius: 20px;
    min-width: 40px;
    min-height: 40px;
    max-width: 40px;
    max-height: 40px;
    font-size: 17px;
    padding: 0;
}}
QPushButton#telaToggle_ativo:hover {{
    background-color: rgba(10, 132, 255, 0.30);
    border: 1px solid rgba(10, 132, 255, 0.85);
}}

QPushButton#finalizar {{
    background-color: rgba(48, 209, 88, 0.16);
    color: #30D158;
    border: 1px solid rgba(48, 209, 88, 0.45);
    border-radius: 20px;
    min-width: 40px;
    min-height: 40px;
    max-width: 40px;
    max-height: 40px;
    font-size: 17px;
    padding: 0;
}}
QPushButton#finalizar:hover {{
    background-color: rgba(48, 209, 88, 0.26);
    border: 1px solid rgba(48, 209, 88, 0.70);
}}
QPushButton#finalizar:disabled {{
    background-color: rgba(255, 255, 255, 0.03);
    color: rgba(255, 255, 255, 0.18);
    border: 1px solid rgba(255, 255, 255, 0.06);
}}

QPushButton#fechar {{
    background-color: transparent;
    color: rgba(235, 235, 245, 0.55);
    font-size: 14px;
    font-weight: 600;
    padding: 0;
    border-radius: 11px;
}}
QPushButton#fechar:hover {{
    background-color: rgba(255, 69, 58, 0.22);
    color: #FF453A;
}}

QTextEdit#falaBox {{
    color: rgba(255, 255, 255, 0.92);
    font-size: 11px;
    padding: 7px 9px;
    background-color: rgba(255, 255, 255, 0.07);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 10px;
    selection-background-color: rgba(10, 132, 255, 0.35);
}}
QTextEdit#falaBox:focus {{
    border: 1px solid rgba(255, 255, 255, 0.10);
}}
QLabel#statusPill {{
    color: rgba(235, 235, 245, 0.7);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.4px;
}}

QFrame#conexaoPill_aguardando {{
    background-color: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 13px;
}}
QFrame#conexaoPill_ok {{
    background-color: rgba(48, 209, 88, 0.09);
    border: 1px solid rgba(48, 209, 88, 0.28);
    border-radius: 13px;
}}
QFrame#conexaoPill_erro {{
    background-color: rgba(255, 69, 58, 0.09);
    border: 1px solid rgba(255, 69, 58, 0.28);
    border-radius: 13px;
}}
QLabel#conexaoServico {{
    font-size: 11px;
    font-weight: 600;
    color: rgba(235, 235, 245, 0.45);
    letter-spacing: 0.5px;
}}
QLabel#conexaoMsg {{
    font-size: 13px;
    font-weight: 500;
    color: rgba(255, 255, 255, 0.88);
}}

QScrollBar:vertical {{
    background: transparent;
    width: 9px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: rgba(255, 255, 255, 0.18);
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: rgba(255, 255, 255, 0.30); }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
"""

LARGURA_FLUTUANTE = 300
ALTURA_FLUTUANTE = 242
NUM_BARRAS_ONDA = 18


def aplicar_vibrancia(window: QWidget, escuro: bool = True, raio: float = 0.0) -> None:
    """Aplica vidro translúcido nativo (NSVisualEffectView) no macOS — estilo Tahoe."""
    if sys.platform != "darwin":
        return
    try:
        import objc
        from AppKit import (
            NSAppearance,
            NSColor,
            NSVisualEffectView,
            NSWindowBelow,
        )

        # Constantes (valores estáveis do AppKit; usados direto para evitar
        # incompatibilidades de import entre versões do pyobjc).
        material = 18  # NSVisualEffectMaterialUnderWindowBackground
        blending_behind = 0  # NSVisualEffectBlendingModeBehindWindow
        state_active = 1  # NSVisualEffectStateActive
        autoresize = (1 << 1) | (1 << 4)  # width + height sizable

        view = objc.objc_object(c_void_p=int(window.winId()))
        ns_window = view.window()
        if ns_window is None:
            return

        content = ns_window.contentView()
        bounds = content.bounds()

        effect = NSVisualEffectView.alloc().initWithFrame_(bounds)
        effect.setAutoresizingMask_(autoresize)
        effect.setBlendingMode_(blending_behind)
        effect.setMaterial_(material)
        effect.setState_(state_active)

        if raio > 0:
            effect.setWantsLayer_(True)
            layer = effect.layer()
            if layer is not None:
                layer.setCornerRadius_(raio)
                layer.setMasksToBounds_(True)

        content.addSubview_positioned_relativeTo_(effect, NSWindowBelow, None)

        ns_window.setOpaque_(False)
        ns_window.setBackgroundColor_(NSColor.clearColor())

        nome = "NSAppearanceNameDarkAqua" if escuro else "NSAppearanceNameAqua"
        ns_window.setAppearance_(NSAppearance.appearanceNamed_(nome))

        if raio > 0:
            content.setWantsLayer_(True)
            c_layer = content.layer()
            if c_layer is not None:
                c_layer.setCornerRadius_(raio)
                c_layer.setMasksToBounds_(True)
    except Exception:
        pass


class OndaVoz(QWidget):
    """Visualizador de onda de voz — animado (IA) ou reativo ao microfone (usuário)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(44)
        self._ativo = False
        self._ao_vivo = False
        self._fase = 0.0
        self._nivel_atual = 0.0
        self._niveis = [0.12] * NUM_BARRAS_ONDA
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animar)
        self.hide()

    def set_ativo(self, ativo: bool, ao_vivo: bool = False) -> None:
        self._ativo = ativo
        self._ao_vivo = ao_vivo
        if ativo:
            self._nivel_atual = 0.0
            self._niveis = [0.12] * NUM_BARRAS_ONDA
            self.show()
            intervalo = 16 if ao_vivo else 45
            self._timer.start(intervalo)
        else:
            self._timer.stop()
            self._fase = 0.0
            self._nivel_atual = 0.0
            self._ao_vivo = False
            self.hide()
            self.update()

    def set_nivel(self, rms: float) -> None:
        if not self._ativo or not self._ao_vivo:
            return
        alvo = min(1.0, (rms / 0.018) ** 0.65)
        if alvo > self._nivel_atual:
            self._nivel_atual += (alvo - self._nivel_atual) * 0.75
        else:
            self._nivel_atual += (alvo - self._nivel_atual) * 0.35

    def _atualizar_barras_ao_vivo(self) -> None:
        centro = (NUM_BARRAS_ONDA - 1) / 2
        for i in range(NUM_BARRAS_ONDA):
            dist = abs(i - centro) / max(centro, 1)
            envelope = 1.0 - dist * 0.25
            variacao = 0.7 + 0.3 * abs(
                math.sin(self._fase + i * 0.85) + math.sin(self._fase * 1.4 + i * 0.5)
            )
            alvo = self._nivel_atual * envelope * variacao
            atual = self._niveis[i]
            fator = 0.7 if alvo > atual else 0.4
            self._niveis[i] = atual + (alvo - atual) * fator

    def _animar(self) -> None:
        if self._ao_vivo:
            self._fase += 0.55
            self._atualizar_barras_ao_vivo()
        else:
            self._fase += 0.22
        self.update()

    def paintEvent(self, _event) -> None:
        if not self._ativo:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        margem = 14
        area_w = w - 2 * margem
        bar_w = max(3, area_w // (NUM_BARRAS_ONDA * 2))
        gap = bar_w

        for i in range(NUM_BARRAS_ONDA):
            if self._ao_vivo:
                altura_norm = 0.12 + 0.88 * self._niveis[i]
            else:
                t = self._fase + i * 0.55
                altura_norm = (math.sin(t) + math.sin(t * 1.7 + 0.4)) / 2
                altura_norm = 0.25 + 0.75 * abs(altura_norm)
            bar_h = max(5, int(altura_norm * (h - 4)))
            x = margem + i * (bar_w + gap)
            y = (h - bar_h) // 2

            grad = QLinearGradient(0, y, 0, y + bar_h)
            grad.setColorAt(0.0, QColor("#5AC8FA"))
            grad.setColorAt(1.0, QColor("#0A84FF"))
            painter.setBrush(grad)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(x, y, bar_w, bar_h, bar_w // 2, bar_w // 2)


class TelaInicial(QWidget):
    def __init__(self, parent: "InterviewApp") -> None:
        super().__init__()
        self.app = parent
        self.setObjectName("setup")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # A tela inteira rola: assim, com problemas longos ou janela menor,
        # o conteúdo nunca é cortado.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setObjectName("setupScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        conteudo = QWidget()
        conteudo.setObjectName("setupConteudo")
        scroll.setWidget(conteudo)

        layout = QVBoxLayout(conteudo)
        layout.setContentsMargins(44, 40, 44, 36)
        layout.setSpacing(0)

        titulo = QLabel("Local Arch Interviewer")
        titulo.setObjectName("titulo")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(titulo)

        subtitulo = QLabel("Simulador de entrevista de System Design por voz")
        subtitulo.setObjectName("subtitulo")
        subtitulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitulo)
        layout.addSpacing(26)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 22, 22, 22)
        card_layout.setSpacing(7)

        card_layout.addWidget(self._rotulo("Seu nome"))
        self.nome_entry = QLineEdit()
        self.nome_entry.setPlaceholderText("Ex: Cristiano")
        card_layout.addWidget(self.nome_entry)
        card_layout.addSpacing(8)

        card_layout.addWidget(self._rotulo("Senioridade da vaga"))
        self.senioridade_combo = QComboBox()
        for chave, rotulo in OPCOES_SENIORIDADE:
            self.senioridade_combo.addItem(rotulo, chave)
        idx_padrao = self.senioridade_combo.findData(DIFICULDADE_PADRAO)
        if idx_padrao >= 0:
            self.senioridade_combo.setCurrentIndex(idx_padrao)
        card_layout.addWidget(self.senioridade_combo)
        card_layout.addSpacing(8)

        card_layout.addWidget(self._rotulo("Tela a capturar"))
        self.tela_combo = QComboBox()
        self._popular_telas()
        card_layout.addWidget(self.tela_combo)
        card_layout.addSpacing(8)

        card_layout.addWidget(self._rotulo("Microfone"))
        self.mic_combo = QComboBox()
        self._popular_microfones()
        card_layout.addWidget(self.mic_combo)
        card_layout.addSpacing(8)

        card_layout.addWidget(self._rotulo("Problema da entrevista"))
        self.problema_text = QTextEdit()
        self.problema_text.setPlainText(PROBLEMA)
        self.problema_text.setMinimumHeight(170)
        card_layout.addWidget(self.problema_text)

        layout.addWidget(card)
        layout.addSpacing(18)

        self.conexao_pill = QFrame()
        self.conexao_pill.setObjectName("conexaoPill_aguardando")
        pill_layout = QHBoxLayout(self.conexao_pill)
        pill_layout.setContentsMargins(16, 13, 16, 13)
        pill_layout.setSpacing(12)

        self.conexao_indicador = QLabel("●")
        self.conexao_indicador.setFixedWidth(14)
        self.conexao_indicador.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.conexao_indicador.setStyleSheet(
            "color: rgba(235,235,245,0.45); font-size: 10px; padding-top: 2px;"
        )
        pill_layout.addWidget(self.conexao_indicador)

        texto_col = QVBoxLayout()
        texto_col.setSpacing(3)
        self.conexao_servico = QLabel("LM Studio")
        self.conexao_servico.setObjectName("conexaoServico")
        self.conexao_msg = QLabel("Verificando conexão...")
        self.conexao_msg.setObjectName("conexaoMsg")
        self.conexao_msg.setWordWrap(True)
        texto_col.addWidget(self.conexao_servico)
        texto_col.addWidget(self.conexao_msg)
        pill_layout.addLayout(texto_col, 1)

        layout.addWidget(self.conexao_pill)

        layout.addSpacing(14)
        self.btn_comecar = QPushButton("Começar entrevista")
        self.btn_comecar.setObjectName("primario")
        self.btn_comecar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_comecar.clicked.connect(self.app._iniciar_entrevista)
        layout.addWidget(self.btn_comecar)

    @staticmethod
    def _rotulo(texto: str) -> QLabel:
        lbl = QLabel(texto)
        lbl.setObjectName("fieldLabel")
        return lbl

    def atualizar_conexao(self, ok: bool, msg: str) -> None:
        if ok:
            estado = "ok"
            cor_indicador = "#30D158"
            cor_msg = "#a6e3a1"
        else:
            estado = "erro"
            cor_indicador = "#FF453A"
            cor_msg = "#f38ba8"

        self.conexao_pill.setObjectName(f"conexaoPill_{estado}")
        self.conexao_pill.setStyle(self.conexao_pill.style())
        self.conexao_indicador.setStyleSheet(
            f"color: {cor_indicador}; font-size: 10px; padding-top: 2px;"
        )
        self.conexao_msg.setText(msg)
        self.conexao_msg.setStyleSheet(f"color: {cor_msg}; font-size: 13px; font-weight: 500;")

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

    def _popular_microfones(self) -> None:
        """Lista os microfones de entrada. Data = índice do dispositivo no PortAudio."""
        selecionado = self.mic_combo.currentData() if hasattr(self, "mic_combo") else None
        self.mic_combo.clear()

        dispositivos = listar_microfones()
        if not dispositivos:
            self.mic_combo.addItem("Nenhum microfone detectado", None)
            self.mic_combo.setEnabled(False)
            return

        self.mic_combo.setEnabled(True)
        padrao = indice_microfone_padrao()
        for indice, nome in dispositivos:
            marca = " — padrão" if indice == padrao else ""
            self.mic_combo.addItem(f"{nome}{marca}", indice)

        if selecionado is not None:
            idx = self.mic_combo.findData(selecionado)
            if idx >= 0:
                self.mic_combo.setCurrentIndex(idx)
                return

        if padrao is not None:
            idx = self.mic_combo.findData(padrao)
            if idx >= 0:
                self.mic_combo.setCurrentIndex(idx)


class BarraTitulo(QWidget):
    def __init__(self, app: "InterviewApp", parent=None) -> None:
        super().__init__(parent)
        self.app = app
        self._offset = None
        self.setFixedHeight(26)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        ponto = QLabel("●")
        ponto.setStyleSheet("color: #30D158; font-size: 9px;")
        layout.addWidget(ponto)

        self.lbl_candidato = QLabel("Entrevista")
        self.lbl_candidato.setStyleSheet(
            "font-size: 12px; font-weight: 600; color: rgba(255,255,255,0.92);"
        )
        layout.addWidget(self.lbl_candidato)
        layout.addStretch()

        btn_fechar = QPushButton("✕")
        btn_fechar.setObjectName("fechar")
        btn_fechar.setFixedSize(22, 22)
        btn_fechar.setCursor(Qt.CursorShape.PointingHandCursor)
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
        self.setObjectName("flutuante")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 12)
        root.setSpacing(6)

        self.barra_titulo = BarraTitulo(self.app)
        root.addWidget(self.barra_titulo)

        self.onda_voz = OndaVoz()
        root.addWidget(self.onda_voz)

        self.ultima_fala = QTextEdit()
        self.ultima_fala.setObjectName("falaBox")
        self.ultima_fala.setReadOnly(True)
        self.ultima_fala.setFrameShape(QFrame.Shape.NoFrame)
        self.ultima_fala.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.ultima_fala.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.ultima_fala.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.ultima_fala.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.ultima_fala.setPlainText("Aguardando...")
        self.ultima_fala.setFixedHeight(56)
        root.addWidget(self.ultima_fala)

        self.status_label = QLabel("Pronto")
        self.status_label.setObjectName("statusPill")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.status_label)

        root.addSpacing(0)
        mic_row = QHBoxLayout()
        mic_row.addStretch()
        self.btn_mic = QPushButton("🎙")
        self.btn_mic.setObjectName("mic")
        self.btn_mic.setEnabled(False)
        self.btn_mic.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mic.clicked.connect(self.app._ao_clicar_mic)
        mic_row.addWidget(self.btn_mic)
        mic_row.addSpacing(8)
        self.btn_pronto = QPushButton("Pronto")
        self.btn_pronto.setObjectName("pronto")
        self.btn_pronto.setEnabled(False)
        self.btn_pronto.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pronto.setToolTip(
            "Encerra sua fala e passa a vez.\n"
            "Ativa depois que o microfone detecta sua voz."
        )
        self.btn_pronto.clicked.connect(self.app._ao_clicar_pronto)
        self.btn_pronto.hide()
        mic_row.addWidget(self.btn_pronto)
        self._timer_piscar_pronto = QTimer(self)
        self._timer_piscar_pronto.timeout.connect(self._alternar_piscar_pronto)
        mic_row.addSpacing(10)
        self.btn_tela = QPushButton("🖥")
        self.btn_tela.setObjectName("telaToggle")
        self.btn_tela.setCheckable(True)
        self.btn_tela.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tela.setToolTip(
            "Anexar a tela nas mensagens enquanto estiver ligado.\n"
            "Desligado = mais rápido (só texto). Ligue para mostrar o diagrama."
        )
        self.btn_tela.clicked.connect(self.app._ao_alternar_tela)
        mic_row.addWidget(self.btn_tela)
        mic_row.addSpacing(10)
        self.btn_finalizar = QPushButton("🏁")
        self.btn_finalizar.setObjectName("finalizar")
        self.btn_finalizar.setEnabled(False)
        self.btn_finalizar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_finalizar.setToolTip(
            "Encerrar a entrevista e receber o feedback final da entrevistadora:\n"
            "resumo do papo, pontos fortes e fracos e o que estudar."
        )
        self.btn_finalizar.clicked.connect(self.app._encerrar_com_feedback)
        mic_row.addWidget(self.btn_finalizar)
        mic_row.addStretch()
        root.addLayout(mic_row)

    def atualizar_toggle_tela(self, ativo: bool) -> None:
        self.btn_tela.setObjectName("telaToggle_ativo" if ativo else "telaToggle")
        self.btn_tela.setChecked(ativo)
        self.btn_tela.setStyle(self.btn_tela.style())

    def atualizar_ultima_fala(self, texto: str) -> None:
        self.ultima_fala.setPlainText(texto)
        barra = self.ultima_fala.verticalScrollBar()
        barra.setValue(barra.maximum())

    def set_onda_ativa(self, ativo: bool, ao_vivo: bool = False) -> None:
        self.onda_voz.set_ativo(ativo, ao_vivo=ao_vivo)

    def mostrar_pronto(self, visivel: bool, habilitado: bool = False) -> None:
        if visivel:
            self.btn_pronto.show()
            self.btn_pronto.setEnabled(habilitado)
            self.btn_pronto.setObjectName("pronto")
            self.btn_pronto.setStyle(self.btn_pronto.style())
        else:
            self.parar_piscar_pronto()
            self.btn_pronto.hide()

    def iniciar_piscar_pronto(self) -> None:
        self.btn_pronto.setEnabled(True)
        self.btn_pronto.setObjectName("pronto_piscando")
        self.btn_pronto.setStyle(self.btn_pronto.style())
        self._timer_piscar_pronto.start(500)

    def parar_piscar_pronto(self) -> None:
        self._timer_piscar_pronto.stop()
        self.btn_pronto.setObjectName("pronto")
        self.btn_pronto.setStyle(self.btn_pronto.style())

    def _alternar_piscar_pronto(self) -> None:
        nome = (
            "pronto"
            if self.btn_pronto.objectName() == "pronto_piscando"
            else "pronto_piscando"
        )
        self.btn_pronto.setObjectName(nome)
        self.btn_pronto.setStyle(self.btn_pronto.style())


class InterviewApp(QMainWindow):
    status_changed = pyqtSignal(str)
    ultima_fala_changed = pyqtSignal(str)
    habilitar_mic = pyqtSignal(bool)
    mic_gravando = pyqtSignal(bool)
    onda_ativa = pyqtSignal(bool, bool)
    onda_nivel = pyqtSignal(float)
    mostrar_erro = pyqtSignal(str)
    conexao_atualizada = pyqtSignal(bool, str)
    voltar_setup = pyqtSignal()
    feedback_pronto = pyqtSignal(str)
    habilitar_finalizar = pyqtSignal(bool)
    falou_detectado = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Local Arch Interviewer")
        self.setWindowIcon(carregar_icone())
        self.resize(720, 880)
        self.setMinimumSize(640, 640)

        self.client = criar_cliente()
        self.historico: list[dict] = []
        self.system_prompt = ""
        self.fala_entrevistador = ""
        self.nome_candidato = ""
        self.problema = ""
        self.senioridade = DIFICULDADE_PADRAO
        self.entrevista_ativa = False
        self.processando_mic = False
        self._gerando_feedback = False
        self.anexar_tela = False
        self.display_captura: int | None = None
        self.dispositivo_microfone: int | None = None
        self._topo_pausado = False
        self._parar_gravacao = threading.Event()

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self.stack = QStackedWidget()
        self.stack.setObjectName("root")
        self.tela_inicial = TelaInicial(self)
        self.tela_flutuante = TelaFlutuante(self)
        self.stack.addWidget(self.tela_inicial)
        self.stack.addWidget(self.tela_flutuante)
        self.setCentralWidget(self.stack)

        self.setStyleSheet(montar_estilo(fonte_sistema()))
        self._conectar_sinais()
        self._verificar_conexao()

    def _aplicar_glass(self, raio: float = 0.0) -> None:
        """Reservado para vidro nativo. Desativado: o NSVisualEffectView cobria
        o conteúdo renderizado pelo Qt. Mantemos o visual glass via stylesheet."""
        return

    def _conectar_sinais(self) -> None:
        self.status_changed.connect(self.tela_flutuante.status_label.setText)
        self.ultima_fala_changed.connect(self.tela_flutuante.atualizar_ultima_fala)
        self.habilitar_mic.connect(self._on_habilitar_mic)
        self.mic_gravando.connect(self._on_mic_gravando)
        self.onda_ativa.connect(self.tela_flutuante.set_onda_ativa)
        self.onda_nivel.connect(self.tela_flutuante.onda_voz.set_nivel)
        self.mostrar_erro.connect(lambda msg: QMessageBox.critical(self, "Erro", msg))
        self.conexao_atualizada.connect(self._on_conexao_atualizada)
        self.voltar_setup.connect(self._on_voltar_setup)
        self.feedback_pronto.connect(self._on_feedback_pronto)
        self.habilitar_finalizar.connect(
            self.tela_flutuante.btn_finalizar.setEnabled
        )
        self.falou_detectado.connect(self._on_falou_detectado)

    def _on_conexao_atualizada(self, ok: bool, msg: str) -> None:
        self.tela_inicial.atualizar_conexao(ok, msg)

    def _on_habilitar_mic(self, habilitado: bool) -> None:
        self.tela_flutuante.btn_mic.setEnabled(habilitado and not self.processando_mic)

    def _on_mic_gravando(self, gravando: bool) -> None:
        btn = self.tela_flutuante.btn_mic
        flutuante = self.tela_flutuante
        if gravando:
            btn.setObjectName("mic_gravando")
            btn.setEnabled(False)
            self.onda_ativa.emit(True, True)
            flutuante.mostrar_pronto(True, habilitado=False)
        else:
            btn.setObjectName("mic")
            self.onda_ativa.emit(False, False)
            flutuante.mostrar_pronto(False)
        btn.setStyle(btn.style())

    def _on_falou_detectado(self) -> None:
        self._set_status("Ouvindo... clique Pronto quando terminar.")
        self.tela_flutuante.iniciar_piscar_pronto()

    def _ao_clicar_pronto(self) -> None:
        self._parar_gravacao.set()

    def _set_status(self, texto: str) -> None:
        self.status_changed.emit(texto)

    def _falar_entrevistador(self, texto: str) -> None:
        falar_texto(
            texto,
            on_status=self._set_status,
            on_inicio=lambda: self.onda_ativa.emit(True, False),
            on_fim=lambda: self.onda_ativa.emit(False, False),
        )

    def _verificar_conexao(self) -> None:
        def _checar() -> None:
            ok, msg = validar_servidor(self.client)
            self.conexao_atualizada.emit(ok, msg)

        threading.Thread(target=_checar, daemon=True).start()

    def _ativar_modo_flutuante(self) -> None:
        self._topo_pausado = False
        # Esconde antes de trocar as flags: alterar flags numa janela visível
        # dispara um show() reentrante no plugin cocoa (aviso
        # "qt.qpa.window: Already setting window visible!").
        self.hide()
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(LARGURA_FLUTUANTE, ALTURA_FLUTUANTE)

        tela = QApplication.primaryScreen()
        if tela:
            geo = tela.availableGeometry()
            self.move(geo.right() - LARGURA_FLUTUANTE - 16, geo.top() + 16)

        self.stack.setCurrentWidget(self.tela_flutuante)
        self.show()
        self.raise_()
        self.activateWindow()
        self._aplicar_glass(raio=22.0)

        # Qt só aplica o nível nativo depois de processar o evento de show,
        # por isso reforçamos logo após (singleShot 0) para o nosso nível vencer.
        self._forcar_sempre_no_topo()
        QTimer.singleShot(0, self._forcar_sempre_no_topo)

        # Reaplica periodicamente: ao trocar de Space/app o macOS pode
        # rebaixar o nível da janela, então mantemos a elevação ativa.
        if not hasattr(self, "_timer_topo"):
            self._timer_topo = QTimer(self)
            self._timer_topo.timeout.connect(self._forcar_sempre_no_topo)
        self._timer_topo.start(1500)

    def _forcar_sempre_no_topo(self) -> None:
        """Eleva a NSWindow nativa acima de tudo no macOS (apps, tela cheia, Spaces)."""
        if sys.platform != "darwin" or not self.entrevista_ativa or self._topo_pausado:
            return
        try:
            import objc
            from AppKit import (
                NSScreenSaverWindowLevel,
                NSWindowCollectionBehaviorCanJoinAllSpaces,
                NSWindowCollectionBehaviorFullScreenAuxiliary,
                NSWindowCollectionBehaviorStationary,
            )

            view = objc.objc_object(c_void_p=int(self.winId()))
            ns_window = view.window()
            if ns_window is None:
                return

            ns_window.setLevel_(NSScreenSaverWindowLevel)
            ns_window.setCollectionBehavior_(
                NSWindowCollectionBehaviorCanJoinAllSpaces
                | NSWindowCollectionBehaviorFullScreenAuxiliary
                | NSWindowCollectionBehaviorStationary
            )
            # Sem isso, a janela "Tool" (NSPanel) some quando o app perde o
            # foco — é o que acontece ao dar Cmd+Tab para outro aplicativo.
            ns_window.setHidesOnDeactivate_(False)
        except Exception:
            # Em caso de falta de pyobjc ou erro nativo, mantemos o hint do Qt.
            pass

    def _iniciar_entrevista(self) -> None:
        nome = self.tela_inicial.nome_entry.text().strip()
        problema = self.tela_inicial.problema_text.toPlainText().strip()
        senioridade = self.tela_inicial.senioridade_combo.currentData()
        self.display_captura = self.tela_inicial.tela_combo.currentData()
        self.dispositivo_microfone = self.tela_inicial.mic_combo.currentData()

        if not nome:
            QMessageBox.warning(self, "Nome", "Informe seu nome para começar.")
            return
        if not problema:
            QMessageBox.warning(self, "Problema", "Descreva o problema da entrevista.")
            return
        if self.dispositivo_microfone is None:
            QMessageBox.warning(
                self,
                "Microfone",
                "Nenhum microfone foi detectado. Conecte um microfone e tente novamente.",
            )
            return

        self.client = criar_cliente(base_url=BASE_URL)
        ok, msg = validar_servidor(self.client)
        if not ok:
            QMessageBox.critical(self, "LM Studio", msg)
            return

        self.nome_candidato = nome
        self.problema = problema
        self.senioridade = senioridade
        self.entrevista_ativa = True
        self._gerando_feedback = False
        self.historico = []
        self.anexar_tela = False
        self.tela_flutuante.atualizar_toggle_tela(False)
        self.system_prompt = montar_system_prompt(problema, nome, senioridade)

        self.tela_flutuante.barra_titulo.lbl_candidato.setText(nome)
        self.tela_flutuante.atualizar_ultima_fala("Aguardando entrevistador...")
        self._ativar_modo_flutuante()
        self._set_status("Pensando...")
        self.habilitar_mic.emit(False)
        self.habilitar_finalizar.emit(False)

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
            if not self.entrevista_ativa:
                return
            self.habilitar_mic.emit(True)
            self.habilitar_finalizar.emit(True)
            self._set_status("Sua vez")
        except Exception as exc:
            if not self.entrevista_ativa:
                return
            self.mostrar_erro.emit(str(exc))
            self.voltar_setup.emit()

    def _ao_alternar_tela(self) -> None:
        self.anexar_tela = not self.anexar_tela
        self.tela_flutuante.atualizar_toggle_tela(self.anexar_tela)

    def _ao_clicar_mic(self) -> None:
        if self.processando_mic or not self.entrevista_ativa or self._gerando_feedback:
            return
        self.processando_mic = True
        self._parar_gravacao.clear()
        self.habilitar_mic.emit(False)
        self.habilitar_finalizar.emit(False)
        self.mic_gravando.emit(True)
        threading.Thread(target=self._processar_fala, daemon=True).start()

    def _processar_fala(self) -> None:
        try:
            caminho_audio = gravar_audio_ate_silencio(
                on_status=self._set_status,
                on_nivel=lambda rms: self.onda_nivel.emit(rms),
                on_falou=lambda: self.falou_detectado.emit(),
                parar_evento=self._parar_gravacao,
                dispositivo=self.dispositivo_microfone,
            )
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
                if not self.entrevista_ativa:
                    return
                self.processando_mic = False
                self.habilitar_mic.emit(True)
                self.habilitar_finalizar.emit(True)
                self._set_status("Sua vez")
                return

            caminho_screenshot = None
            if self.anexar_tela:
                self._set_status("Capturando tela...")
                caminho_screenshot = capturar_tela(self.display_captura)

            mensagem = montar_mensagem_usuario(texto, caminho_screenshot)
            self.historico.append({"role": "assistant", "content": self.fala_entrevistador})
            self.historico.append(mensagem)

            # Em entrevistas longas o histórico cresce e pode estourar o contexto
            # do modelo local: resumimos as rodadas antigas e descartamos imagens
            # velhas antes de chamar a IA.
            if len(self.historico) > COMPACTAR_HISTORICO_LIMITE:
                self._set_status("Organizando o contexto...")
                self.historico = compactar_historico(
                    self.client, self.historico, model=MODEL
                )

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
            if not self.entrevista_ativa:
                return
            self.processando_mic = False
            self.habilitar_mic.emit(True)
            self.habilitar_finalizar.emit(True)
            self._set_status("Sua vez")
        except Exception as exc:
            if not self.entrevista_ativa:
                return
            self.mic_gravando.emit(False)
            self.onda_ativa.emit(False, False)
            self.processando_mic = False
            self.mostrar_erro.emit(str(exc))
            self.habilitar_mic.emit(True)
            self.habilitar_finalizar.emit(True)

    def _rebaixar_nivel_janela(self) -> None:
        """Volta a janela ao nível normal para que diálogos apareçam à frente."""
        if sys.platform != "darwin":
            return
        try:
            import objc
            from AppKit import NSNormalWindowLevel

            view = objc.objc_object(c_void_p=int(self.winId()))
            ns_window = view.window()
            if ns_window is not None:
                ns_window.setLevel_(NSNormalWindowLevel)
        except Exception:
            pass

    def _pausar_topo(self) -> None:
        self._topo_pausado = True
        if hasattr(self, "_timer_topo"):
            self._timer_topo.stop()
        self._rebaixar_nivel_janela()

    def _retomar_topo(self) -> None:
        self._topo_pausado = False
        if self.entrevista_ativa:
            self._forcar_sempre_no_topo()
            if hasattr(self, "_timer_topo"):
                self._timer_topo.start(1500)

    def _encerrar_entrevista(self) -> None:
        # Pausa o "sempre no topo": senão o diálogo abre atrás da janela
        # flutuante e fica inacessível (não dá para mover nem confirmar).
        self._pausar_topo()

        dialogo = QMessageBox(self)
        dialogo.setWindowTitle("Encerrar")
        dialogo.setText("Deseja encerrar a entrevista?")
        dialogo.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        dialogo.setDefaultButton(QMessageBox.StandardButton.No)
        dialogo.setWindowFlags(
            dialogo.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )
        dialogo.raise_()
        dialogo.activateWindow()
        resp = dialogo.exec()

        if resp == QMessageBox.StandardButton.Yes:
            self._finalizar_entrevista()
        else:
            self._retomar_topo()

    def _encerrar_com_feedback(self) -> None:
        if not self.entrevista_ativa or self._gerando_feedback:
            return

        # Pausa o "sempre no topo" para o diálogo não abrir atrás da flutuante.
        self._pausar_topo()

        dialogo = QMessageBox(self)
        dialogo.setWindowTitle("Finalizar entrevista")
        dialogo.setText("Encerrar a entrevista e pedir o feedback final?")
        dialogo.setInformativeText(
            "A entrevistadora vai resumir como foi o papo, apontar pontos fortes e "
            "fracos e sugerir o que estudar e aprofundar."
        )
        dialogo.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        dialogo.setDefaultButton(QMessageBox.StandardButton.Yes)
        dialogo.setWindowFlags(
            dialogo.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )
        dialogo.raise_()
        dialogo.activateWindow()
        resp = dialogo.exec()

        if resp != QMessageBox.StandardButton.Yes:
            self._retomar_topo()
            return

        self._gerando_feedback = True
        parar_fala()
        self.processando_mic = False
        self.habilitar_mic.emit(False)
        self.habilitar_finalizar.emit(False)
        self.onda_ativa.emit(False, False)
        self.ultima_fala_changed.emit("Gerando seu feedback final...")
        self._set_status("Preparando feedback...")

        # Garante que a última fala da entrevistadora entre no histórico antes
        # de pedir o resumo (ela só é anexada no início do próximo turno).
        if self.fala_entrevistador and (
            not self.historico or self.historico[-1].get("role") == "user"
        ):
            self.historico.append(
                {"role": "assistant", "content": self.fala_entrevistador}
            )

        threading.Thread(target=self._loop_feedback, daemon=True).start()

    def _loop_feedback(self) -> None:
        try:
            texto = gerar_feedback_final(
                self.client,
                self.historico,
                self.problema,
                self.nome_candidato,
                self.senioridade,
                model=MODEL,
            )
        except Exception as exc:
            self._gerando_feedback = False
            if not self.entrevista_ativa:
                return
            self.mostrar_erro.emit(f"Não consegui gerar o feedback: {exc}")
            self.habilitar_mic.emit(True)
            self.habilitar_finalizar.emit(True)
            self._set_status("Sua vez")
            self._retomar_topo()
            return

        self.feedback_pronto.emit(texto)

        # Lê o feedback em voz alta (versão limpa, sem markdown).
        fala = limpar_texto(texto)
        if fala and self.entrevista_ativa:
            self._falar_entrevistador(fala)

    def _on_feedback_pronto(self, texto: str) -> None:
        self._gerando_feedback = False
        self._set_status("Feedback")
        self.ultima_fala_changed.emit("Feedback final pronto. Veja a janela ao lado.")

        dialogo = QDialog(self)
        dialogo.setWindowTitle("Feedback final da entrevista")
        dialogo.setModal(True)
        dialogo.setMinimumSize(560, 560)
        dialogo.setWindowFlags(
            dialogo.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )

        layout = QVBoxLayout(dialogo)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        titulo = QLabel("Feedback da entrevistadora")
        titulo.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(titulo)

        corpo = QTextEdit()
        corpo.setReadOnly(True)
        corpo.setPlainText(texto)
        layout.addWidget(corpo)

        btn = QPushButton("Encerrar entrevista")
        btn.setObjectName("primario")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(dialogo.accept)
        layout.addWidget(btn)

        dialogo.raise_()
        dialogo.activateWindow()
        dialogo.exec()

        self._finalizar_entrevista()

    def closeEvent(self, event) -> None:
        self.entrevista_ativa = False
        parar_fala()
        event.accept()

    def _finalizar_entrevista(self) -> None:
        self.entrevista_ativa = False
        parar_fala()
        self.processando_mic = False
        self.onda_ativa.emit(False, False)
        self.ultima_fala_changed.emit("Entrevista encerrada.")
        self._set_status("Encerrada")
        self.habilitar_mic.emit(False)
        self.voltar_setup.emit()

    def _on_voltar_setup(self) -> None:
        if hasattr(self, "_timer_topo"):
            self._timer_topo.stop()
        self.hide()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setWindowFlags(Qt.WindowType.Window)
        self.setMinimumSize(640, 640)
        self.setMaximumSize(16777215, 16777215)
        self.resize(720, 880)
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(
                geo.center().x() - self.width() // 2,
                geo.center().y() - self.height() // 2,
            )
        self.tela_inicial._popular_telas()
        self.tela_inicial._popular_microfones()
        self.stack.setCurrentWidget(self.tela_inicial)
        self.show()
        self._aplicar_glass(raio=0.0)
        self._verificar_conexao()


def run() -> None:
    app = QApplication(sys.argv)
    app.aboutToQuit.connect(parar_fala)
    app.setWindowIcon(carregar_icone())
    font = QFont(fonte_sistema())
    font.setPointSize(13)
    app.setFont(font)

    window = InterviewApp()
    window.show()
    window._aplicar_glass(raio=0.0)
    sys.exit(app.exec())
