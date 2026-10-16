#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
overlay_linux.py - Overlay Universal de Microaprendizagem para Linux

Implementação nativa em Python 3 com PySide6 para Linux (Wayland e X11).
Oferece sobreposição click-through (não rouba foco, cliques passam através da janela),
transparência suave, repetição espaçada, System Tray, atalhos de terminal e controle via IPC.
"""

import os
import sys
import time
import json
import signal
import socket
import select
import random
import atexit
import argparse
import configparser
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any, Set

# Permitir execução headless em testes offscreen
os.environ.setdefault("QT_LOGGING_RULES", "*.debug=false")

# Em ambientes Linux com Wayland (como KDE Plasma ou GNOME), o protocolo xdg_shell
# bloqueia por especificação o reposicionamento arbitrário de janelas e o arrasto de cliente via move().
# Definir QT_QPA_PLATFORM=xcb quando DISPLAY estiver disponível (XWayland) permite
# o arrasto livre e a fixação exata das coordenadas entre múltiplos monitores.
if "QT_QPA_PLATFORM" not in os.environ and os.environ.get("DISPLAY"):
    os.environ["QT_QPA_PLATFORM"] = "xcb"

try:
    from PySide6.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QSystemTrayIcon, QMenu
    )
    from PySide6.QtCore import (
        Qt, QTimer, QObject, Signal, QRect, QPoint, QPointF, QSize
    )
    from PySide6.QtGui import (
        QColor, QPainter, QBrush, QPen, QFont, QIcon, QPixmap, QAction, QCursor
    )
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
except ImportError:
    print("[ERRO] PySide6 não foi encontrado no sistema!", file=sys.stderr)
    print("Para executar o overlay no Linux, instale o pacote PySide6:", file=sys.stderr)
    print("  - Fedora/RHEL:   sudo dnf install python3-pyside6", file=sys.stderr)
    print("  - Ubuntu/Debian: sudo apt install python3-pyside6", file=sys.stderr)
    print("  - Arch Linux:    sudo pacman -S python-pyside6", file=sys.stderr)
    print("  - Ou via pip:    pip install PySide6", file=sys.stderr)
    sys.exit(2)


# ====================================================================
# Gerenciamento de Terminal e Restauração de Modo Canônico
# ====================================================================

_terminal_old_settings = None
_terminal_fd = None


def restaurar_terminal() -> None:
    """Restaura as configurações originais do terminal caso tenham sido modificadas."""
    global _terminal_old_settings, _terminal_fd
    if _terminal_old_settings is not None and _terminal_fd is not None:
        try:
            import termios
            termios.tcsetattr(_terminal_fd, termios.TCSADRAIN, _terminal_old_settings)
        except Exception:
            pass
        _terminal_old_settings = None


atexit.register(restaurar_terminal)



# ====================================================================
# Utilitários de IPC e Caminho de Socket
# ====================================================================

def obter_socket_path() -> str:
    """Retorna o caminho do socket IPC UNIX para comunicação local."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir and os.path.isdir(runtime_dir):
        return os.path.join(runtime_dir, "microestudo_overlay.sock")
    uid = os.getuid() if hasattr(os, "getuid") else "1000"
    return f"/tmp/microestudo_overlay_{uid}.sock"


def enviar_comando_ipc(comando: str, timeout: float = 2.0) -> Optional[str]:
    """Envia um comando para a instância do overlay em execução."""
    sock_path = obter_socket_path()
    if not os.path.exists(sock_path):
        return None

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(sock_path)
            client.sendall((comando.strip() + "\n").encode("utf-8"))
            resposta = b""
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                resposta += chunk
                if b"\n" in chunk:
                    break
            return resposta.decode("utf-8", errors="replace").strip()
    except (socket.error, OSError):
        return None


# ====================================================================
# Modelo e Gerenciamento de Cards e Progresso
# ====================================================================

class Card:
    """Representa uma microlição individual estruturada."""
    def __init__(self, card_id: str, assunto: str, subtema: str, titulo: str, texto: str, origem: str):
        self.id = card_id.strip()
        self.assunto = assunto.strip() or "Estudo"
        self.subtema = subtema.strip() or ""
        self.titulo = titulo.strip() or "Conceito"
        self.texto = texto.strip()
        self.origem = origem.strip() or "Geral"

    def para_dict(self) -> Dict[str, str]:
        return {
            "id": self.id,
            "assunto": self.assunto,
            "subtema": self.subtema,
            "titulo": self.titulo,
            "texto": self.texto,
            "origem": self.origem
        }


class ConfigManager:
    """Carrega e valida as configurações do arquivo config.ini."""
    def __init__(self, ini_path: Path):
        self.ini_path = ini_path
        self.config: Dict[str, Any] = {
            "arquivo": "conteudo.md",
            "min_chars": 90,
            "max_chars": 220,
            "new_ratio": 70,
            "ignorar_secoes": "Mapeamento das Fontes e Rastreabilidade do Acervo Local;Mapeamento das Fontes",
            "interval_seconds": 300,
            "visible_seconds": 30,
            "corner": "top_right",
            "margin_x": 30,
            "margin_y": 30,
            "width": 430,
            "height": 150,
            "font_size": 11,
            "opacity": 230,
            "bg_color": "14241F",
            "show_on_start": 1,
            "click_through": 0,
            "target_exes": "",
            "hide_when_target_inactive": 1,
            "remember_progress": 1
        }
        self.carregar()

    def carregar(self) -> None:
        if not self.ini_path.is_file():
            return

        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(str(self.ini_path), encoding="ascii")
        except Exception:
            try:
                parser.read(str(self.ini_path), encoding="utf-8")
            except Exception:
                return

        def get_int(section: str, key: str, default: int, min_v: Optional[int] = None, max_v: Optional[int] = None) -> int:
            try:
                val = int(parser.get(section, key, fallback=str(default)).strip())
                if min_v is not None and val < min_v:
                    val = min_v
                if max_v is not None and val > max_v:
                    val = max_v
                return val
            except (ValueError, TypeError):
                return default

        def get_str(section: str, key: str, default: str) -> str:
            try:
                return parser.get(section, key, fallback=default).strip()
            except Exception:
                return default

        # [Conteudo]
        self.config["arquivo"] = get_str("Conteudo", "arquivo", self.config["arquivo"])
        self.config["min_chars"] = get_int("Conteudo", "min_chars", self.config["min_chars"], 30, 400)
        self.config["max_chars"] = get_int("Conteudo", "max_chars", self.config["max_chars"], 60, 600)
        self.config["new_ratio"] = get_int("Conteudo", "new_ratio", self.config["new_ratio"], 0, 100)
        self.config["ignorar_secoes"] = get_str("Conteudo", "ignorar_secoes", self.config["ignorar_secoes"])

        # [Exibicao]
        self.config["interval_seconds"] = get_int("Exibicao", "interval_seconds", self.config["interval_seconds"], 10, 3600)
        self.config["visible_seconds"] = get_int("Exibicao", "visible_seconds", self.config["visible_seconds"], 5, self.config["interval_seconds"])
        self.config["corner"] = get_str("Exibicao", "corner", self.config["corner"]).lower()
        self.config["margin_x"] = get_int("Exibicao", "margin_x", self.config["margin_x"], 0, 500)
        self.config["margin_y"] = get_int("Exibicao", "margin_y", self.config["margin_y"], 0, 500)
        self.config["width"] = get_int("Exibicao", "width", self.config["width"], 240, 1200)
        self.config["height"] = get_int("Exibicao", "height", self.config["height"], 100, 800)
        self.config["font_size"] = get_int("Exibicao", "font_size", self.config["font_size"], 10, 32)
        self.config["opacity"] = get_int("Exibicao", "opacity", self.config["opacity"], 20, 255)
        self.config["bg_color"] = get_str("Exibicao", "bg_color", self.config["bg_color"]).replace("#", "")
        self.config["show_on_start"] = get_int("Exibicao", "show_on_start", self.config["show_on_start"], 0, 1)
        self.config["click_through"] = get_int("Exibicao", "click_through", self.config["click_through"], 0, 1)

        # [Contexto]
        self.config["target_exes"] = get_str("Contexto", "target_exes", self.config["target_exes"])
        self.config["hide_when_target_inactive"] = get_int("Contexto", "hide_when_target_inactive", self.config["hide_when_target_inactive"], 0, 1)

        # [Estado]
        self.config["remember_progress"] = get_int("Estado", "remember_progress", self.config["remember_progress"], 0, 1)


class CardsDeck:
    """Gerencia a coleção de cards e o algoritmo de repetição espaçada."""
    def __init__(self, raiz_projeto: Path, config_mgr: ConfigManager, conteudo_custom: Optional[str] = None):
        self.raiz_projeto = raiz_projeto
        self.config_mgr = config_mgr
        self.conteudo_custom = conteudo_custom
        self.cards: List[Card] = []
        self.progresso: Dict[str, Dict[str, int]] = {}
        self.excluidos: Set[str] = set()
        self.ultimo_card_id: str = ""
        self.carregar_excluidos()
        self.carregar_progresso()
        self.carregar_cards()
        self.sincronizar_progresso()

    @property
    def tsv_path(self) -> Path:
        return self.raiz_projeto / "dados" / "cards.tsv"

    @property
    def progresso_path(self) -> Path:
        return self.raiz_projeto / "dados" / "progresso.json"

    @property
    def excluidos_path(self) -> Path:
        return self.raiz_projeto / "dados" / "excluidos.json"

    def carregar_excluidos(self) -> None:
        self.excluidos = set()
        exc_file = self.excluidos_path
        if not exc_file.is_file():
            return
        try:
            with open(exc_file, "r", encoding="utf-8") as f:
                dados = json.load(f)
                if isinstance(dados, list):
                    self.excluidos = set(str(cid).strip() for cid in dados if str(cid).strip())
                elif isinstance(dados, dict):
                    self.excluidos = set(str(cid).strip() for cid in dados.keys() if str(cid).strip())
        except Exception:
            self.excluidos = set()

    def salvar_excluidos(self) -> None:
        exc_file = self.excluidos_path
        exc_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            temp_file = exc_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(sorted(list(self.excluidos)), f, indent=2)
            temp_file.replace(exc_file)
        except Exception as e:
            print(f"[AVISO] Falha ao salvar excluidos: {e}", file=sys.stderr)

    def excluir_card(self, card_id: str) -> bool:
        if not card_id:
            return False
        cid = card_id.strip()
        self.excluidos.add(cid)
        self.cards = [c for c in self.cards if c.id != cid]
        if cid in self.progresso:
            del self.progresso[cid]
            self.salvar_progresso()
        if self.ultimo_card_id == cid:
            self.ultimo_card_id = ""
        self.salvar_excluidos()
        return True

    def resetar_excluidos(self) -> None:
        self.excluidos.clear()
        if self.excluidos_path.is_file():
            try:
                self.excluidos_path.unlink()
            except OSError:
                pass
        self.carregar_cards()
        self.sincronizar_progresso()

    def carregar_cards(self, forcar_recompilacao: bool = False) -> bool:
        tsv = self.tsv_path
        if forcar_recompilacao or not tsv.is_file() or self.conteudo_custom:
            self.executar_conversor_python()

        if not tsv.is_file():
            return False

        cards_novos: List[Card] = []
        try:
            with open(tsv, "r", encoding="utf-8", errors="replace") as f:
                for idx, linha in enumerate(f):
                    linha = linha.strip()
                    if not linha:
                        continue
                    campos = linha.split("\t")
                    if len(campos) < 6:
                        continue
                    if idx == 0 and campos[0] == "id" and campos[1] == "assunto":
                        continue
                    cid = campos[0].strip()
                    if cid in self.excluidos:
                        continue
                    # Decodificar quebras reais
                    texto_real = campos[4].replace("\\n", "\n")
                    card = Card(
                        card_id=cid,
                        assunto=campos[1],
                        subtema=campos[2],
                        titulo=campos[3],
                        texto=texto_real,
                        origem=campos[5]
                    )
                    cards_novos.append(card)
            self.cards = cards_novos
            return len(self.cards) > 0
        except Exception as e:
            print(f"[AVISO] Erro ao carregar cards.tsv: {e}", file=sys.stderr)
            return False

    def carregar_progresso(self) -> None:
        self.progresso = {}
        if not self.config_mgr.config.get("remember_progress"):
            return

        prog_file = self.progresso_path
        if not prog_file.is_file():
            return

        try:
            with open(prog_file, "r", encoding="utf-8") as f:
                dados = json.load(f)
                if isinstance(dados, dict):
                    for k, v in dados.items():
                        if isinstance(v, dict) and "exibicoes" in v and "ultima" in v:
                            self.progresso[str(k)] = {
                                "exibicoes": int(v["exibicoes"]),
                                "ultima": int(v["ultima"])
                            }
        except Exception:
            self.progresso = {}

    def sincronizar_progresso(self) -> None:
        if not self.config_mgr.config.get("remember_progress") or not self.cards:
            return

        ids_validos = {c.id for c in self.cards}
        ids_para_remover = [cid for cid in self.progresso if cid not in ids_validos]

        for cid in ids_para_remover:
            del self.progresso[cid]

        if ids_para_remover:
            self.salvar_progresso()

    def salvar_progresso(self) -> None:
        if not self.config_mgr.config.get("remember_progress"):
            return

        prog_file = self.progresso_path
        prog_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            temp_file = prog_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.progresso, f, ensure_ascii=True, indent=2)
            temp_file.replace(prog_file)
        except Exception as e:
            print(f"[AVISO] Falha ao salvar progresso: {e}", file=sys.stderr)

    def selecionar_proximo_card(self) -> Optional[Card]:
        """
        Algoritmo de repetição espaçada:
        - 70% novos cards em ordem sequencial de apresentação
        - 30% revisões dos cards já vistos com menor número de exibições
        - Evita repetir consecutivamente o mesmo card
        """
        if not self.cards:
            return None

        if len(self.cards) == 1:
            return self.cards[0]

        nao_vistos = [
            c for c in self.cards
            if c.id not in self.progresso or self.progresso[c.id]["exibicoes"] == 0
        ]
        ja_vistos = [
            c for c in self.cards
            if c.id in self.progresso and self.progresso[c.id]["exibicoes"] > 0
        ]

        sorteio = random.randint(1, 100)
        novo_ratio = self.config_mgr.config.get("new_ratio", 70)

        # Se houver novos e (sorteio favorece novos ou ainda não temos material visto para revisar):
        if nao_vistos and (sorteio <= novo_ratio or not ja_vistos):
            card_escolhido = nao_vistos[0]
        else:
            # Revisão: selecionar prioritariamente entre os já vistos (ou todos, se todos já foram vistos)
            fonte = ja_vistos if ja_vistos else self.cards
            candidatos = [c for c in fonte if c.id != self.ultimo_card_id]
            if not candidatos:
                if nao_vistos:
                    card_escolhido = nao_vistos[0]
                    self.ultimo_card_id = card_escolhido.id
                    agora = int(time.time())
                    if card_escolhido.id not in self.progresso:
                        self.progresso[card_escolhido.id] = {"exibicoes": 1, "ultima": agora}
                    else:
                        self.progresso[card_escolhido.id]["exibicoes"] += 1
                        self.progresso[card_escolhido.id]["ultima"] = agora
                    self.salvar_progresso()
                    return card_escolhido
                candidatos = fonte

            # Menor contagem de exibições, priorizando mais antigos em caso de empate
            card_escolhido = min(
                candidatos,
                key=lambda c: (
                    self.progresso.get(c.id, {}).get("exibicoes", 0),
                    self.progresso.get(c.id, {}).get("ultima", 0)
                )
            )

        self.ultimo_card_id = card_escolhido.id

        # Atualizar estatísticas de progresso
        agora = int(time.time())
        if card_escolhido.id not in self.progresso:
            self.progresso[card_escolhido.id] = {"exibicoes": 1, "ultima": agora}
        else:
            self.progresso[card_escolhido.id]["exibicoes"] += 1
            self.progresso[card_escolhido.id]["ultima"] = agora

        self.salvar_progresso()
        return card_escolhido

    def executar_conversor_python(self) -> bool:
        conversor = self.raiz_projeto / "preparar_conteudo.py"
        if not conversor.is_file():
            return False

        ini_path = self.config_mgr.ini_path
        cmd = [sys.executable, str(conversor), "--config", str(ini_path)]
        if self.conteudo_custom:
            cmd.extend(["--conteudo", str(self.conteudo_custom)])

        try:
            res = subprocess.run(cmd, cwd=str(self.raiz_projeto), capture_output=True, text=True, timeout=30)
            return res.returncode == 0
        except Exception as e:
            print(f"[ERRO] Falha ao invocar preparar_conteudo.py: {e}", file=sys.stderr)
            return False


# ====================================================================
# Interface Gráfica do Overlay (PySide6)
# ====================================================================

def criar_icone_lixeira(tamanho: int = 18) -> QIcon:
    """Cria ícone vetorial de lixeira estilizado e independente de fontes de emoji do sistema."""
    def desenhar(cor: str) -> QPixmap:
        pix = QPixmap(tamanho, tamanho)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(cor), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))

        # Alça e tampa da lixeira
        p.drawLine(QPointF(tamanho * 0.38, tamanho * 0.16), QPointF(tamanho * 0.62, tamanho * 0.16))
        p.drawLine(QPointF(tamanho * 0.20, tamanho * 0.28), QPointF(tamanho * 0.80, tamanho * 0.28))

        # Cesto trapezoidal
        caminho = [
            QPointF(tamanho * 0.26, tamanho * 0.32),
            QPointF(tamanho * 0.30, tamanho * 0.85),
            QPointF(tamanho * 0.70, tamanho * 0.85),
            QPointF(tamanho * 0.74, tamanho * 0.32)
        ]
        p.drawPolyline(caminho)

        # Ranhuras verticais do cesto
        p.drawLine(QPointF(tamanho * 0.42, tamanho * 0.42), QPointF(tamanho * 0.42, tamanho * 0.75))
        p.drawLine(QPointF(tamanho * 0.58, tamanho * 0.42), QPointF(tamanho * 0.58, tamanho * 0.75))
        p.end()
        return pix

    icon = QIcon()
    icon.addPixmap(desenhar("#88A89A"), QIcon.Mode.Normal)
    icon.addPixmap(desenhar("#FF6B6B"), QIcon.Mode.Active)
    return icon


class OverlayWindow(QWidget):
    """
    Janela translúcida, flutuante, Always-On-Top e sem roubo de foco.
    Suporta modo interativo (arrastável livremente com mouse e botão de lixeira para descarte)
    ou modo click-through passivo configurável via config.ini.
    """
    sinal_excluir_solicitado = Signal()
    sinal_arrasto_iniciado = Signal()
    sinal_arrasto_finalizado = Signal()

    def __init__(self, config_mgr: ConfigManager, raiz_projeto: Optional[Path] = None):
        super().__init__()
        self.config_mgr = config_mgr
        self.raiz_projeto = raiz_projeto or (config_mgr.ini_path.parent if getattr(config_mgr, "ini_path", None) else Path(__file__).resolve().parent)

        self.click_through = bool(config_mgr.config.get("click_through", 0))

        # Configurar flags do sistema de janelas:
        # - WindowStaysOnTopHint: sempre visível sobre qualquer janela
        # - FramelessWindowHint: sem bordas do gerenciador de janelas
        # - Tool: utilitário sem ícone separado na barra de tarefas
        # - WindowDoesNotAcceptFocus: jamais rouba o foco de jogos ou editores
        # - WindowTransparentForInput: apenas no modo click-through passivo
        flags = (
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        if self.click_through:
            flags |= Qt.WindowType.WindowTransparentForInput
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        else:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            self.setCursor(Qt.CursorShape.OpenHandCursor)

        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Estado de arrasto e posicionamento customizado
        self._drag_active = False
        self._drag_moved = False
        self._drag_start_mouse_pos = QPoint()
        self._drag_offset = QPoint()
        self._drag_start_pos = QPoint()
        self._custom_pos: Optional[QPoint] = None
        self._card_assunto_completo = ""
        self._card_titulo_completo = ""
        self.carregar_posicao()

        self.layout_principal = QVBoxLayout(self)
        self.layout_principal.setContentsMargins(15, 10, 15, 10)
        self.layout_principal.setSpacing(3)

        # Cabeçalho horizontal: Assunto + Botão de Lixeira
        self.layout_header = QHBoxLayout()
        self.layout_header.setContentsMargins(0, 0, 0, 0)
        self.layout_header.setSpacing(6)

        # Rótulo de Assunto / Subtema
        self.lbl_assunto = QLabel("")
        self.lbl_assunto.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        # Botão de Lixeira vetorial (excluir card inútil)
        self.btn_lixeira = QPushButton()
        self.btn_lixeira.setFixedSize(22, 22)
        self.btn_lixeira.setIcon(criar_icone_lixeira(18))
        self.btn_lixeira.setIconSize(QSize(18, 18))
        self.btn_lixeira.setToolTip("Descartar este card permanentemente (não exibir novamente)")
        self.btn_lixeira.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_lixeira.clicked.connect(self.sinal_excluir_solicitado.emit)
        if self.click_through:
            self.btn_lixeira.hide()

        self.layout_header.addWidget(self.lbl_assunto, 1)
        self.layout_header.addWidget(self.btn_lixeira, 0, Qt.AlignmentFlag.AlignRight)

        # Rótulo de Título em destaque
        self.lbl_titulo = QLabel("")
        self.lbl_titulo.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        # Rótulo do Texto explicativo principal
        self.lbl_texto = QLabel("")
        self.lbl_texto.setWordWrap(True)
        self.lbl_texto.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        # Rótulo do Rodapé / Origem
        self.lbl_origem = QLabel("")
        self.lbl_origem.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.layout_principal.addLayout(self.layout_header)
        self.layout_principal.addWidget(self.lbl_titulo)
        self.layout_principal.addWidget(self.lbl_texto, 1)
        self.layout_principal.addWidget(self.lbl_origem)

        self.atualizar_estilos()

    @property
    def posicao_path(self) -> Path:
        return self.raiz_projeto / "dados" / "posicao.json"

    def carregar_posicao(self) -> None:
        pos_file = self.posicao_path
        if not pos_file.is_file():
            return
        try:
            with open(pos_file, "r", encoding="utf-8") as f:
                dados = json.load(f)
                if isinstance(dados, dict) and "x" in dados and "y" in dados:
                    self._custom_pos = QPoint(int(dados["x"]), int(dados["y"]))
        except Exception:
            self._custom_pos = None

    def salvar_posicao(self) -> None:
        if self._custom_pos is None:
            return
        pos_file = self.posicao_path
        pos_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            dados = {"x": self._custom_pos.x(), "y": self._custom_pos.y()}
            temp_file = pos_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(dados, f, indent=2)
            temp_file.replace(pos_file)
        except Exception as e:
            print(f"[AVISO] Falha ao salvar posicao: {e}", file=sys.stderr)

    def redefinir_posicao(self) -> None:
        self._custom_pos = None
        pos_file = self.posicao_path
        if pos_file.is_file():
            try:
                pos_file.unlink()
            except OSError:
                pass
        self.reposicionar()

    def atualizar_estilos(self) -> None:
        cfg = self.config_mgr.config
        f_size = cfg.get("font_size", 11)
        f_sub = max(8.5, f_size - 2.5)
        f_tit = max(12.0, f_size + 1.5)
        f_foot = max(8.0, f_size - 3.0)

        font_family = "system-ui, 'Segoe UI', 'Noto Sans', 'DejaVu Sans', sans-serif"

        self.lbl_assunto.setStyleSheet(
            f"color: #88A89A; font-family: {font_family}; font-size: {f_sub}pt; "
            f"font-weight: bold; background: transparent;"
        )
        self.lbl_titulo.setStyleSheet(
            f"color: #FFFFFF; font-family: {font_family}; font-size: {f_tit}pt; "
            f"font-weight: bold; background: transparent;"
        )
        self.lbl_texto.setStyleSheet(
            f"color: #E4EDE7; font-family: {font_family}; font-size: {f_size}pt; "
            f"background: transparent;"
        )
        self.lbl_origem.setStyleSheet(
            f"color: #5E7A6E; font-family: {font_family}; font-size: {f_foot}pt; "
            f"background: transparent;"
        )
        self.btn_lixeira.setStyleSheet(
            "QPushButton { background: transparent; border: none; border-radius: 4px; padding: 1px; } "
            "QPushButton:hover { background: rgba(239, 68, 68, 0.25); } "
            "QPushButton:pressed { background: rgba(239, 68, 68, 0.45); }"
        )

        self.resize(cfg.get("width", 430), cfg.get("height", 150))
        self.atualizar_textos_elididos()

    def paintEvent(self, event) -> None:
        """Pinta um fundo translúcido escuro de vidro com bordas arredondadas suaves."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cfg = self.config_mgr.config
        bg_hex = cfg.get("bg_color", "14241F")
        opacity = cfg.get("opacity", 230)

        cor_base = QColor(f"#{bg_hex}")
        cor_com_alfa = QColor(cor_base.red(), cor_base.green(), cor_base.blue(), opacity)

        painter.setBrush(QBrush(cor_com_alfa))
        # Borda sutil reflexiva em vidro
        painter.setPen(QPen(QColor(255, 255, 255, 25), 1.0))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10.0, 10.0)

    def mousePressEvent(self, event) -> None:
        if self.click_through:
            event.ignore()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_active = True
            self._drag_moved = False
            self._drag_start_mouse_pos = event.globalPosition().toPoint()
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            self._drag_start_pos = self._drag_offset
            QApplication.setOverrideCursor(Qt.CursorShape.ClosedHandCursor)
            self.sinal_arrasto_iniciado.emit()

            # Em Wayland nativo (se XCB não estiver em uso), startSystemMove aciona o compositor para mover a janela
            if "wayland" in QApplication.platformName().lower():
                wh = self.windowHandle()
                if wh and hasattr(wh, "startSystemMove"):
                    try:
                        wh.startSystemMove()
                    except Exception:
                        pass

            event.accept()
        else:
            event.ignore()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        if getattr(self, "_drag_active", False):
            self._drag_moved = True
            self._custom_pos = self.pos()

    def mouseReleaseEvent(self, event) -> None:
        if self.click_through:
            event.ignore()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._drag_active:
            self._drag_active = False
            try:
                QApplication.restoreOverrideCursor()
            except Exception:
                pass
            if self._drag_moved or getattr(self, "_custom_pos", None) is not None:
                if self._custom_pos is None or self._drag_moved:
                    self._custom_pos = self.pos()
                self.salvar_posicao()
                self._drag_moved = False
            self.sinal_arrasto_finalizado.emit()
            event.accept()
        else:
            event.ignore()

    def hideEvent(self, event) -> None:
        if self._drag_active:
            self._drag_active = False
            try:
                QApplication.restoreOverrideCursor()
            except Exception:
                pass
            if self._drag_moved:
                if self._custom_pos is None:
                    self._custom_pos = self.pos()
                self.salvar_posicao()
                self._drag_moved = False
            self.sinal_arrasto_finalizado.emit()
        super().hideEvent(event)

    def hide(self) -> None:
        if self._drag_active:
            self._drag_active = False
            try:
                QApplication.restoreOverrideCursor()
            except Exception:
                pass
            if self._drag_moved:
                if self._custom_pos is None:
                    self._custom_pos = self.pos()
                self.salvar_posicao()
                self._drag_moved = False
            self.sinal_arrasto_finalizado.emit()
        super().hide()

    def mouseMoveEvent(self, event) -> None:
        if self.click_through:
            event.ignore()
            return
        if self._drag_active and (event.buttons() & Qt.MouseButton.LeftButton):
            delta = event.globalPosition().toPoint() - self._drag_start_mouse_pos
            if not self._drag_moved:
                if abs(delta.x()) <= 2 and abs(delta.y()) <= 2:
                    event.accept()
                    return
                self._drag_moved = True

            nova_pos = event.globalPosition().toPoint() - self._drag_offset
            mouse_pt = event.globalPosition().toPoint()

            # Obter limites globais de todos os monitores conectados
            screens = QApplication.screens()
            if screens:
                desktop_geo = screens[0].geometry()
                for s in screens[1:]:
                    desktop_geo = desktop_geo.united(s.geometry())

                # Permitir deslocamento horizontal livre pelo desktop multi-monitor
                clamped_x = max(desktop_geo.x(), min(nova_pos.x(), desktop_geo.x() + desktop_geo.width() - self.width()))

                # O clamp vertical respeita a altura da tela onde o mouse se encontra
                cur_screen = QApplication.screenAt(mouse_pt) or QApplication.screenAt(nova_pos)
                if cur_screen:
                    s_geo = cur_screen.geometry()
                    clamped_y = max(s_geo.y(), min(nova_pos.y(), s_geo.y() + s_geo.height() - self.height()))
                else:
                    clamped_y = max(desktop_geo.y(), min(nova_pos.y(), desktop_geo.y() + desktop_geo.height() - self.height()))
            else:
                clamped_x, clamped_y = nova_pos.x(), nova_pos.y()

            target_pos = QPoint(clamped_x, clamped_y)
            self.move(target_pos)
            self._custom_pos = target_pos
            event.accept()
        else:
            event.ignore()

    def atualizar_textos_elididos(self) -> None:
        cfg = self.config_mgr.config
        w = self.width() if self.width() > 50 else cfg.get("width", 430)
        margins = self.layout_principal.contentsMargins()
        btn_w = self.btn_lixeira.width() if self.btn_lixeira.isVisible() else 0
        w_disponivel_header = max(80, w - margins.left() - margins.right() - btn_w - 10)

        assunto_completo = getattr(self, "_card_assunto_completo", "")
        if assunto_completo:
            fm_sub = self.lbl_assunto.fontMetrics()
            self.lbl_assunto.setText(fm_sub.elidedText(assunto_completo, Qt.TextElideMode.ElideRight, w_disponivel_header))

        titulo_completo = getattr(self, "_card_titulo_completo", "")
        if titulo_completo:
            w_disponivel_corpo = max(80, w - margins.left() - margins.right())
            fm_tit = self.lbl_titulo.fontMetrics()
            self.lbl_titulo.setText(fm_tit.elidedText(titulo_completo, Qt.TextElideMode.ElideRight, w_disponivel_corpo))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.atualizar_textos_elididos()

    def reposicionar(self) -> None:
        """Calcula as coordenadas exatas na tela conforme o canto, margens e altura do conteúdo."""
        cfg = self.config_mgr.config
        w = cfg.get("width", 430)
        cfg_h = cfg.get("height", 150)
        mx = cfg.get("margin_x", 30)
        my = cfg.get("margin_y", 30)
        corner = cfg.get("corner", "top_right").lower()

        # Ajusta largura fixa e calcula altura dinâmica necessária para não truncar texto
        self.setFixedWidth(w)
        self.layout_principal.activate()
        h_necessario = self.layout_principal.heightForWidth(w)
        h = max(cfg_h, h_necessario, self.sizeHint().height())

        # Se houver posição customizada salva pelo usuário via arrasto
        if self._custom_pos is not None:
            target_pt = self._custom_pos
            card_center = QPoint(target_pt.x() + w // 2, target_pt.y() + h // 2)

            screens = QApplication.screens()
            if screens:
                desktop_geo = screens[0].geometry()
                for s in screens[1:]:
                    desktop_geo = desktop_geo.united(s.geometry())

                # Encontra a tela onde a posição salva reside
                screen = QApplication.screenAt(card_center) or QApplication.screenAt(target_pt)
                if not screen:
                    card_rect = QRect(target_pt.x(), target_pt.y(), w, h)
                    maior_area = 0
                    melhor_tela = None
                    for s in screens:
                        inter = s.geometry().intersected(card_rect)
                        area = inter.width() * inter.height()
                        if area > maior_area:
                            maior_area = area
                            melhor_tela = s
                    screen = melhor_tela

                # Se a tela ou o monitor não existir mais (ex: monitor desconectado),
                # cai no fallback seguro da tela primária
                if not screen:
                    screen = QApplication.primaryScreen()
                    geo = screen.geometry() if screen else desktop_geo
                    pos_x = max(geo.x(), min(target_pt.x(), geo.x() + geo.width() - w))
                    pos_y = max(geo.y(), min(target_pt.y(), geo.y() + geo.height() - h))
                else:
                    geo = screen.geometry()
                    # Mantém a coordenada X exata definida pelo usuário (limitando apenas ao desktop global)
                    pos_x = max(desktop_geo.x(), min(target_pt.x(), desktop_geo.x() + desktop_geo.width() - w))
                    # Ajusta Y apenas se a nova altura do card ultrapassar a borda inferior daquela tela
                    pos_y = max(geo.y(), min(target_pt.y(), geo.y() + geo.height() - h))
            else:
                pos_x, pos_y = target_pt.x(), target_pt.y()

            self.setGeometry(pos_x, pos_y, w, h)
            self.atualizar_textos_elididos()
            return

        cursor_screen = QApplication.screenAt(QCursor.pos())
        screen = cursor_screen or QApplication.primaryScreen()
        if screen:
            geo = screen.geometry()
            s_w = geo.width()
            s_h = geo.height()
            s_x = geo.x()
            s_y = geo.y()
        else:
            s_w, s_h, s_x, s_y = 1920, 1080, 0, 0

        if corner in ("top_left", "superior_esquerdo", "superior-esquerdo"):
            pos_x = s_x + mx
            pos_y = s_y + my
        elif corner in ("bottom_left", "inferior_esquerdo", "inferior-esquerdo"):
            pos_x = s_x + mx
            pos_y = s_y + s_h - h - my
        elif corner in ("bottom_right", "inferior_direito", "inferior-direito"):
            pos_x = s_x + s_w - w - mx
            pos_y = s_y + s_h - h - my
        else:  # top_right, superior_direito, superior-direito
            pos_x = s_x + s_w - w - mx
            pos_y = s_y + my

        self.setGeometry(pos_x, pos_y, w, h)
        self.atualizar_textos_elididos()

    def exibir_card(self, card: Card) -> None:
        assunto_txt = card.assunto
        if card.subtema and card.subtema != card.assunto:
            assunto_txt += f"  ›  {card.subtema}"

        self._card_assunto_completo = assunto_txt
        self._card_titulo_completo = card.titulo

        self.lbl_assunto.setToolTip(assunto_txt)
        self.lbl_titulo.setToolTip(card.titulo)
        self.lbl_texto.setText(card.texto)
        self.lbl_origem.setText(f"{card.origem}  •  ID: {card.id[:8]}")

        self.reposicionar()
        self.show()


# ====================================================================
# Controlador Central do Aplicativo e Agendamento
# ====================================================================

class OverlayController(QObject):
    """Orquestra os ciclos de exibição, servidor IPC, System Tray e atalhos."""
    sinal_comando = Signal(str)

    def __init__(self, raiz_projeto: Path, config_mgr: ConfigManager, deck: CardsDeck):
        super().__init__()
        self.raiz_projeto = raiz_projeto
        self.config_mgr = config_mgr
        self.deck = deck
        self.window = OverlayWindow(config_mgr, raiz_projeto=raiz_projeto)
        self.window.sinal_excluir_solicitado.connect(self.excluir_card_atual)
        self.window.sinal_arrasto_iniciado.connect(self.pausar_temporizador_visibilidade)
        self.window.sinal_arrasto_finalizado.connect(self.retomar_temporizador_visibilidade)

        self.esta_pausado = False
        self.card_visivel = False
        self.card_atual: Optional[Card] = None

        # Temporizadores Qt
        self.timer_visibilidade = QTimer(self)
        self.timer_visibilidade.setSingleShot(True)
        self.timer_visibilidade.timeout.connect(self.ocultar_card)

        self.timer_ciclo = QTimer(self)
        self.timer_ciclo.setSingleShot(True)
        self.timer_ciclo.timeout.connect(self.exibir_proximo_card)

        self.timer_foco = QTimer(self)
        self.timer_foco.setInterval(1000)
        self.timer_foco.timeout.connect(self.monitorar_foco_alvo)
        self.timer_foco.start()

        # Servidor de IPC via QLocalServer
        self.ipc_server = QLocalServer(self)
        self.iniciar_servidor_ipc()

        # System Tray Icon
        self.tray_icon = self.criar_system_tray()

        # Conectar sinal de comando para execução thread-safe na UI thread
        self.sinal_comando.connect(self.executar_comando)

        # Inicialização automática se configurado
        if self.config_mgr.config.get("show_on_start") and self.deck.cards:
            self.exibir_proximo_card()
        elif self.deck.cards:
            self.agendar_proximo_card(self.config_mgr.config.get("interval_seconds", 300))

    def criar_system_tray(self) -> Optional[QSystemTrayIcon]:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return None

        # Gerar ícone estilizado em memória (32x32)
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Fundo do ícone
        painter.setBrush(QBrush(QColor(0x14, 0x24, 0x1F)))
        painter.setPen(QPen(QColor(0x88, 0xA8, 0x9A), 1.5))
        painter.drawRoundedRect(QRect(2, 2, 28, 28), 6.0, 6.0)

        # Símbolo do livro / card
        painter.setPen(QPen(QColor(0xE4, 0xED, 0xE7), 2.0))
        painter.drawLine(8, 11, 24, 11)
        painter.drawLine(8, 16, 24, 16)
        painter.drawLine(8, 21, 18, 21)
        painter.end()

        tray = QSystemTrayIcon(QIcon(pixmap), self)
        tray.setToolTip("MicroEstudo Overlay (Linux)")

        menu = QMenu()
        self.acao_pausa = menu.addAction("⏯️  Pausar / Retomar")
        self.acao_pausa.triggered.connect(self.alternar_pausa)

        acao_proximo = menu.addAction("⏭️  Próximo Card")
        acao_proximo.triggered.connect(self.proximo_card_manual)

        acao_excluir = menu.addAction("🗑️  Excluir Card Atual")
        acao_excluir.triggered.connect(self.excluir_card_atual)

        acao_ocultar = menu.addAction("👁️  Ocultar Card Atual")
        acao_ocultar.triggered.connect(self.ocultar_card)

        acao_reset_pos = menu.addAction("📍  Restaurar Posição Padrão")
        acao_reset_pos.triggered.connect(self.window.redefinir_posicao)

        acao_recarregar = menu.addAction("🔄  Recarregar Conteúdo")
        acao_recarregar.triggered.connect(self.recarregar_conteudo)

        menu.addSeparator()
        acao_status = menu.addAction("ℹ️  Status do Baralho")
        acao_status.triggered.connect(self.exibir_status_notificacao)

        menu.addSeparator()
        acao_sair = menu.addAction("❌  Sair")
        acao_sair.triggered.connect(self.sair_aplicativo)

        tray.setContextMenu(menu)
        tray.show()
        return tray

    def notificar(self, titulo: str, mensagem: str, tempo_ms: int = 2500) -> None:
        """Exibe notificação na bandeja ou via notify-send."""
        if self.tray_icon and self.tray_icon.isVisible():
            self.tray_icon.showMessage(titulo, mensagem, QSystemTrayIcon.MessageIcon.Information, tempo_ms)
        else:
            # Fallback para notify-send se disponível
            try:
                subprocess.run(
                    ["notify-send", "-a", "MicroEstudo", "-t", str(tempo_ms), titulo, mensagem],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=0.5
                )
            except Exception:
                pass

    def iniciar_servidor_ipc(self) -> None:
        sock_path = obter_socket_path()
        # Limpar socket anterior se estiver órfão
        QLocalServer.removeServer(sock_path)
        if os.path.exists(sock_path):
            try:
                os.remove(sock_path)
            except OSError:
                pass

        if not self.ipc_server.listen(sock_path):
            print(f"[AVISO] Não foi possível iniciar servidor IPC no socket: {sock_path}", file=sys.stderr)
        else:
            self.ipc_server.newConnection.connect(self._tratar_conexao_ipc)
            # Garantir permissão 0600 no socket
            try:
                os.chmod(sock_path, 0o600)
            except OSError:
                pass

    def _tratar_conexao_ipc(self) -> None:
        while self.ipc_server.hasPendingConnections():
            socket_cli = self.ipc_server.nextPendingConnection()
            if not socket_cli:
                continue

            def processar_socket(s=socket_cli):
                dados = s.readAll().data().decode("utf-8", errors="replace").strip()
                if dados:
                    resposta = self.executar_comando(dados)
                    s.write((resposta + "\n").encode("utf-8"))
                    s.flush()
                s.disconnectFromServer()

            socket_cli.disconnected.connect(socket_cli.deleteLater)
            socket_cli.errorOccurred.connect(lambda *_: socket_cli.deleteLater())

            if socket_cli.bytesAvailable() > 0:
                processar_socket(socket_cli)
            else:
                socket_cli.readyRead.connect(processar_socket)

    def executar_comando(self, comando: str) -> str:
        cmd = comando.strip().lower()
        if cmd in ("next", "proximo", "p"):
            self.proximo_card_manual()
            return "OK: proximo card exibido"
        elif cmd in ("delete", "excluir", "discard", "lixeira", "x"):
            sucesso = self.excluir_card_atual()
            return "OK: card excluido do baralho" if sucesso else "AVISO: nenhum card ativo para excluir"
        elif cmd in ("reset-pos", "reset_pos"):
            self.window.redefinir_posicao()
            return "OK: posicao da janela redefinida para o padrao"
        elif cmd in ("reset-excluded", "reset_excluded"):
            self.deck.resetar_excluidos()
            return f"OK: cards excluidos restaurados ({len(self.deck.cards)} cards disponiveis)"
        elif cmd in ("pause", "pausa", "pausar"):
            self.alternar_pausa()
            return f"OK: overlay {'pausado' if self.esta_pausado else 'retomado'}"
        elif cmd in ("hide", "ocultar", "h"):
            self.ocultar_card()
            return "OK: card ocultado"
        elif cmd in ("reload", "recarregar", "r"):
            sucesso = self.recarregar_conteudo()
            return f"OK: recarregamento {'concluido' if sucesso else 'falhou'}"
        elif cmd in ("status", "s"):
            return self.obter_status_json()
        elif cmd in ("quit", "sair", "exit", "q"):
            QTimer.singleShot(100, self.sair_aplicativo)
            return "OK: encerrando overlay"
        else:
            return f"ERRO: comando desconhecido '{cmd}'. Comandos validos: next, delete, reset-pos, reset-excluded, pause, hide, reload, status, quit"

    def excluir_card_atual(self) -> bool:
        if not self.card_atual:
            return False

        card_excluido = self.card_atual
        card_id = card_excluido.id
        titulo = card_excluido.titulo
        self.card_atual = None

        sucesso = self.deck.excluir_card(card_id)
        if sucesso:
            print(f"\n[🗑️] Card excluído do baralho: [{card_excluido.assunto}] {titulo} (ID: {card_id[:8]})")
            self.notificar("MicroEstudo", f"Card descartado:\n{titulo[:40]}")
            # Avançar imediatamente para o próximo card
            self.timer_visibilidade.stop()
            self.timer_ciclo.stop()
            self.exibir_proximo_card()
            return True
        return False

    def obter_status_json(self) -> str:
        total = len(self.deck.cards)
        vistos = len([c for c in self.deck.cards if self.deck.progresso.get(c.id, {}).get("exibicoes", 0) > 0])
        dados = {
            "status": "pausado" if self.esta_pausado else "ativo",
            "card_visivel": self.card_visivel,
            "total_cards": total,
            "cards_vistos": vistos,
            "cards_excluidos": len(self.deck.excluidos),
            "card_atual": self.card_atual.para_dict() if self.card_atual else None,
            "interval_seconds": self.config_mgr.config.get("interval_seconds"),
            "visible_seconds": self.config_mgr.config.get("visible_seconds")
        }
        return json.dumps(dados, ensure_ascii=False)

    def exibir_status_notificacao(self) -> None:
        total = len(self.deck.cards)
        vistos = len([c for c in self.deck.cards if self.deck.progresso.get(c.id, {}).get("exibicoes", 0) > 0])
        excluidos = len(self.deck.excluidos)
        status_txt = f"Baralho: {total} cards ({vistos} vistos, {excluidos} descartados)\nStatus: {'Pausado' if self.esta_pausado else 'Em execução'}"
        self.notificar("MicroEstudo — Progresso", status_txt, 4000)

    def alvo_esta_ativo(self) -> bool:
        alvos_str = self.config_mgr.config.get("target_exes", "").strip()
        if not alvos_str or not self.config_mgr.config.get("hide_when_target_inactive", 1):
            return True

        lista_alvos = [a.strip().lower() for a in alvos_str.split(",") if a.strip()]
        if not lista_alvos:
            return True

        # Tenta verificar via xprop se disponível
        try:
            res_id = subprocess.run(["xprop", "-root", "_NET_ACTIVE_WINDOW"], capture_output=True, text=True, timeout=1)
            if res_id.returncode == 0 and "window id #" in res_id.stdout:
                win_id = res_id.stdout.split("window id #")[-1].strip().split()[0]
                res_class = subprocess.run(["xprop", "-id", win_id, "WM_CLASS"], capture_output=True, text=True, timeout=1)
                saida = (res_class.stdout or "").lower()
                for alvo in lista_alvos:
                    if alvo in saida:
                        return True
        except Exception:
            pass

        # Fallback: verificar se o processo está em execução no sistema (/proc)
        try:
            for alvo in lista_alvos:
                res_pgrep = subprocess.run(["pgrep", "-i", "-f", alvo], capture_output=True, timeout=1)
                if res_pgrep.returncode == 0:
                    return True
        except Exception:
            pass

        return False

    def monitorar_foco_alvo(self) -> None:
        alvos_str = self.config_mgr.config.get("target_exes", "").strip()
        if not alvos_str or not self.config_mgr.config.get("hide_when_target_inactive", 1):
            return

        if not self.alvo_esta_ativo() and self.card_visivel:
            self.ocultar_card()

    def exibir_proximo_card(self) -> None:
        if self.esta_pausado or not self.deck.cards:
            self.card_atual = None
            self.ocultar_card()
            return

        if self.window._drag_active:
            # Não interrompe nem move o card enquanto o usuário estiver arrastando
            self.timer_ciclo.start(2000)
            return

        if not self.alvo_esta_ativo():
            # Reagenda tentativa em 5 segundos sem perder o ciclo
            self.timer_ciclo.start(5000)
            return

        card = self.deck.selecionar_proximo_card()
        if not card:
            self.card_atual = None
            self.ocultar_card()
            return

        self.card_atual = card
        self.window.exibir_card(card)
        self.card_visivel = True

        # Timer de visibilidade (padrão: 30 segundos)
        vis_ms = self.config_mgr.config.get("visible_seconds", 30) * 1000
        self.timer_visibilidade.start(vis_ms)

        # Timer de ciclo a partir do INÍCIO deste card (padrão: 300 segundos = 5 minutos)
        int_ms = self.config_mgr.config.get("interval_seconds", 300) * 1000
        self.timer_ciclo.start(int_ms)

        print(f"\n[+] Card Exibido: [{card.assunto}] {card.titulo} ({card.origem})")

    def ocultar_card(self) -> None:
        self.timer_visibilidade.stop()
        if self.card_visivel:
            self.window.hide()
            self.card_visivel = False

    def pausar_temporizador_visibilidade(self) -> None:
        """Pausa o fechamento automático enquanto o usuário está ativamente arrastando o card."""
        if self.timer_visibilidade.isActive():
            self.timer_visibilidade.stop()

    def retomar_temporizador_visibilidade(self) -> None:
        """Reinicia o tempo de permanência do card após soltar o mouse."""
        if self.card_visivel and not self.esta_pausado:
            vis_ms = self.config_mgr.config.get("visible_seconds", 30) * 1000
            self.timer_visibilidade.start(vis_ms)

    def agendar_proximo_card(self, segundos: int) -> None:
        self.timer_ciclo.start(segundos * 1000)

    def alternar_pausa(self) -> None:
        self.esta_pausado = not self.esta_pausado
        if self.esta_pausado:
            self.ocultar_card()
            self.timer_visibilidade.stop()
            self.timer_ciclo.stop()
            self.notificar("MicroEstudo Overlay", "PAUSADO\n(Use 'p' ou atalho para retomar)")
            print("\n[!] Overlay PAUSADO.")
        else:
            self.notificar("MicroEstudo Overlay", "RETOMADO")
            print("\n[+] Overlay RETOMADO.")
            self.exibir_proximo_card()

    def proximo_card_manual(self) -> None:
        if self.esta_pausado:
            return
        self.timer_visibilidade.stop()
        self.timer_ciclo.stop()
        self.exibir_proximo_card()

    def recarregar_conteudo(self) -> bool:
        print("\n[+] Reprocessando conteúdo Markdown...")
        self.notificar("MicroEstudo", "Reprocessando conteúdo Markdown...")
        sucesso = self.deck.executar_conversor_python()

        if sucesso:
            self.config_mgr.carregar()
            self.deck.carregar_progresso()
            self.deck.carregar_cards()
            self.deck.sincronizar_progresso()
            self.window.atualizar_estilos()
            self.window.carregar_posicao()
            msg = f"{len(self.deck.cards)} cards recarregados com sucesso!"
            self.notificar("MicroEstudo", msg)
            print(f"[+] {msg}")
            self.proximo_card_manual()
            return True
        else:
            msg = "Falha ao reprocessar. Mantido o baralho atual."
            self.notificar("MicroEstudo", msg)
            print(f"[ERRO] {msg}", file=sys.stderr)
            return False

    def sair_aplicativo(self) -> None:
        print("\n[+] Encerrando MicroEstudo Overlay...")
        restaurar_terminal()
        self.deck.salvar_progresso()
        self.ocultar_card()
        sock_path = obter_socket_path()
        try:
            if os.path.exists(sock_path):
                os.remove(sock_path)
        except OSError:
            pass
        QApplication.instance().quit()


# ====================================================================
# Leitor de Teclado Interativo no Terminal
# ====================================================================

def iniciar_leitor_terminal(controller: OverlayController) -> None:
    """Lê teclas únicas sem exigir pressionar Enter quando em modo interativo."""
    if not sys.stdin.isatty():
        return

    global _terminal_old_settings, _terminal_fd
    import threading
    try:
        import termios
        import tty
    except ImportError:
        return

    fd = sys.stdin.fileno()
    try:
        _terminal_fd = fd
        _terminal_old_settings = termios.tcgetattr(fd)
        tty.setcbreak(fd)
    except Exception:
        return

    def thread_input():
        try:
            while True:
                rlist, _, _ = select.select([sys.stdin], [], [], 0.5)
                if rlist:
                    ch = sys.stdin.read(1)
                    if not ch:
                        break
                    ch_lower = ch.lower()
                    if ch == "\x03" or ch_lower == "q":  # Ctrl+C ou q
                        controller.sinal_comando.emit("quit")
                        break
                    elif ch_lower == "p":
                        controller.sinal_comando.emit("pause")
                    elif ch_lower == "n":
                        controller.sinal_comando.emit("next")
                    elif ch_lower in ("x", "d"):
                        controller.sinal_comando.emit("delete")
                    elif ch_lower in ("c", "o"):
                        controller.sinal_comando.emit("reset-pos")
                    elif ch_lower == "h":
                        controller.sinal_comando.emit("hide")
                    elif ch_lower == "r":
                        controller.sinal_comando.emit("reload")
                    elif ch_lower == "s":
                        controller.sinal_comando.emit("status")
        except Exception:
            pass
        finally:
            restaurar_terminal()

    t = threading.Thread(target=thread_input, daemon=True)
    t.start()


# ====================================================================
# Ponto de Entrada Principal
# ====================================================================

def main():
    parser = argparse.ArgumentParser(description="MicroEstudo Overlay - Linux")
    parser.add_argument("--config", default="config.ini", help="Caminho do arquivo config.ini")
    parser.add_argument("--conteudo", "-f", help="Caminho do arquivo Markdown de estudo (ex: conteudo.md)")
    parser.add_argument("--command", "-c", choices=["next", "pause", "hide", "reload", "status", "quit", "delete", "reset-pos", "reset-excluded"], help="Envia comando para instância ativa")
    parser.add_argument("--next", "-n", action="store_true", help="Avança para o próximo card")
    parser.add_argument("--exclude", "-x", action="store_true", help="Descarta/exclui o card atual permanentemente")
    parser.add_argument("--reset-pos", action="store_true", help="Restaura a posição padrão do overlay na tela")
    parser.add_argument("--reset-excluded", action="store_true", help="Restaura todos os cards previamente descartados")
    parser.add_argument("--pause", "-p", action="store_true", help="Pausa ou retoma as exibições")
    parser.add_argument("--hide", action="store_true", help="Oculta o card atual")
    parser.add_argument("--reload", "-r", action="store_true", help="Reprocessa e recarrega o conteúdo")
    parser.add_argument("--status", "-s", action="store_true", help="Exibe status da instância ativa")
    parser.add_argument("--quit", "-q", action="store_true", help="Encerra a instância em execução")
    parser.add_argument("--offscreen", action="store_true", help="Executa sem interface gráfica (modo headless)")

    args = parser.parse_args()

    # Verificar se foi solicitado um comando para a instância em execução
    comando_solicitado = None
    if args.command:
        comando_solicitado = args.command
    elif args.next:
        comando_solicitado = "next"
    elif args.exclude:
        comando_solicitado = "delete"
    elif args.reset_pos:
        comando_solicitado = "reset-pos"
    elif args.reset_excluded:
        comando_solicitado = "reset-excluded"
    elif args.pause:
        comando_solicitado = "pause"
    elif args.hide:
        comando_solicitado = "hide"
    elif args.reload:
        comando_solicitado = "reload"
    elif args.status:
        comando_solicitado = "status"
    elif args.quit:
        comando_solicitado = "quit"

    if comando_solicitado:
        resp = enviar_comando_ipc(comando_solicitado)
        if resp is not None:
            print(resp)
            sys.exit(0)
        else:
            print(f"[ERRO] Não foi possível comunicar com o overlay. Verifique se o aplicativo está em execução.", file=sys.stderr)
            sys.exit(1)

    # Verificar se já existe uma instância ativa antes de iniciar uma nova
    resp_ativa = enviar_comando_ipc("status")
    if resp_ativa is not None:
        print("[!] Uma instância do MicroEstudo Overlay já está em execução no sistema.")
        print(f"Status atual: {resp_ativa}")
        print("Para enviar comandos, utilize: ./iniciar.sh --next | --exclude | --reset-pos | --pause | --hide | --reload | --quit")
        sys.exit(0)

    # Iniciar aplicação gráfica Qt
    app_args = sys.argv[:1]
    if args.offscreen or os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        app_args.extend(["-platform", "offscreen"])

    app = QApplication(app_args)
    app.setApplicationName("MicroEstudo Overlay")
    app.setQuitOnLastWindowClosed(False)

    raiz = Path(__file__).resolve().parent
    cfg_path = Path(args.config)
    if not cfg_path.is_absolute():
        cfg_path = raiz / cfg_path

    config_mgr = ConfigManager(cfg_path)
    if args.conteudo:
        config_mgr.config["arquivo"] = args.conteudo

    deck = CardsDeck(raiz, config_mgr, conteudo_custom=args.conteudo)

    controller = OverlayController(raiz, config_mgr, deck)

    # Tratamento de sinais POSIX (Ctrl+C e SIGTERM)
    def tratar_sinal(sig, frame):
        controller.sinal_comando.emit("quit")

    signal.signal(signal.SIGINT, tratar_sinal)
    signal.signal(signal.SIGTERM, tratar_sinal)

    # Timer para manter o loop de eventos Python ativo para sinais
    timer_sig = QTimer()
    timer_sig.setInterval(500)
    timer_sig.timeout.connect(lambda: None)
    timer_sig.start()

    # Banner informativo no terminal
    print("=" * 68)
    print("      MICROESTUDO OVERLAY — APRENDIZAGEM EM SEGUNDO PLANO (LINUX)")
    print("=" * 68)
    print(f"[+] Total de microlições carregadas: {len(deck.cards)}")
    if deck.excluidos:
        print(f"[+] Microlições descartadas/ignoradas: {len(deck.excluidos)}")
    print(f"[+] Intervalo entre cards: {config_mgr.config.get('interval_seconds')}s (Visibilidade: {config_mgr.config.get('visible_seconds')}s)")
    print(f"[+] Posicionamento: {config_mgr.config.get('corner')} (Dimensões: {config_mgr.config.get('width')}x{config_mgr.config.get('height')})")
    print(f"[+] Socket de controle IPC: {obter_socket_path()}")
    print("\n[+] Controles rápidos disponíveis:")
    print("    No Terminal interativo:  [p] Pausa  |  [n] Próximo  |  [x] Excluir card  |  [c] Resetar posição  |  [h] Ocultar  |  [r] Recarregar  |  [q] Sair")
    print("    Interação com o Mouse:   Arraste o card livremente na tela com o mouse")
    print("                             Clique no botão 🗑️ para descartar cards inúteis")
    print("    Na Bandeja do Sistema:   Clique com botão direito no ícone de estudo para acessar o menu")
    print("    Via Linha de Comando:    ./iniciar.sh --next  |  --exclude  |  --reset-pos  |  --pause  |  --quit")
    print("=" * 68)

    iniciar_leitor_terminal(controller)

    try:
        ret = app.exec()
    finally:
        restaurar_terminal()

    sys.exit(ret)


if __name__ == "__main__":
    main()
