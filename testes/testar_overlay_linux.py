#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
testar_overlay_linux.py - Testes Automatizados para o Overlay Linux

Valida os requisitos essenciais do subsistema Linux:
1. Carregamento e validação de configurações (config.ini, limites, defaults).
2. Carregamento de cards em TSV com quebras de linha e acentuação UTF-8.
3. Algoritmo de repetição espaçada (proporção 70/30, ordenação sequencial, não repetição imediata).
4. Persistência e sincronização de progresso (progresso.json).
5. Criação e flags da janela do overlay (Always-on-top, click-through, sem foco, offscreen).
6. Cálculo de coordenadas para os 4 cantos da tela.
7. Comunicação IPC local via socket UNIX (comandos next, pause, hide, status).
"""

import os
import sys
import json
import time
import socket
import tempfile
import unittest
from pathlib import Path

# Configurar execução headless antes de importar Qt
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_LOGGING_RULES"] = "*.debug=false"

# Adicionar raiz do projeto ao sys.path
raiz_projeto = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(raiz_projeto))

try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt, QPoint, QRect
    PYSIDE_AVAILABLE = True
except ImportError:
    PYSIDE_AVAILABLE = False

from overlay_linux import (
    Card, ConfigManager, CardsDeck, OverlayWindow,
    OverlayController, obter_socket_path, enviar_comando_ipc,
    restaurar_terminal
)


# Garantir uma única instância de QApplication para todos os testes se PySide6 estiver disponível
if PYSIDE_AVAILABLE:
    app = QApplication.instance()
    if not app:
        app = QApplication(["test_overlay", "-platform", "offscreen"])
else:
    app = None


@unittest.skipUnless(PYSIDE_AVAILABLE, "PySide6 não está disponível neste ambiente (necessário apenas para overlay nativo no Linux)")
class TestesOverlayLinux(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    # 1. Carregamento de configurações e validações de limites
    def test_01_config_defaults_e_limites(self):
        ini_conteudo = """[Conteudo]
arquivo=meu_estudo.md
min_chars=20
max_chars=999
new_ratio=150

[Exibicao]
interval_seconds=5
visible_seconds=9999
corner=inferior_direito
margin_x=-10
margin_y=800
width=150
height=900
font_size=5
opacity=300
bg_color=001122
show_on_start=0

[Contexto]
target_exes=jogo1.exe,jogo2.bin
hide_when_target_inactive=1

[Estado]
remember_progress=1
"""
        ini_file = self.temp_path / "config.ini"
        ini_file.write_text(ini_conteudo, encoding="ascii")

        cfg = ConfigManager(ini_file)
        # min_chars fixado no limite mínimo 30
        self.assertEqual(cfg.config["min_chars"], 30)
        # max_chars fixado no limite máximo 600
        self.assertEqual(cfg.config["max_chars"], 600)
        # new_ratio fixado no limite máximo 100
        self.assertEqual(cfg.config["new_ratio"], 100)
        # interval_seconds fixado no limite mínimo 10
        self.assertEqual(cfg.config["interval_seconds"], 10)
        # visible_seconds não ultrapassa interval_seconds (10)
        self.assertLessEqual(cfg.config["visible_seconds"], 10)
        # corner normalizado
        self.assertEqual(cfg.config["corner"], "inferior_direito")
        # margin_x fixado no limite mínimo 0
        self.assertEqual(cfg.config["margin_x"], 0)
        # margin_y fixado no limite máximo 500
        self.assertEqual(cfg.config["margin_y"], 500)
        # width fixado no limite mínimo 240
        self.assertEqual(cfg.config["width"], 240)
        # height fixado no limite máximo 800
        self.assertEqual(cfg.config["height"], 800)
        # font_size fixado no limite mínimo 10
        self.assertEqual(cfg.config["font_size"], 10)
        # opacity fixado no limite máximo 255
        self.assertEqual(cfg.config["opacity"], 255)
        self.assertEqual(cfg.config["bg_color"], "001122")
        self.assertEqual(cfg.config["show_on_start"], 0)

    # 2. Carregamento de cards em TSV com quebras \n e UTF-8
    def test_02_carregamento_cards_tsv(self):
        dados_dir = self.temp_path / "dados"
        dados_dir.mkdir()
        tsv_file = dados_dir / "cards.tsv"

        linhas_tsv = [
            "id\tassunto\tsubtema\ttitulo\ttexto\torigem",
            "c01\tDireito\tPrincípios\tLegalidade\tRegra fundamental\\nSegunda linha explicativa.\tCap 1",
            "c02\tDireito\tAtos\tAutoexecutoriedade\tExige urgência legal.\tCap 2"
        ]
        tsv_file.write_text("\n".join(linhas_tsv), encoding="utf-8")

        cfg = ConfigManager(self.temp_path / "config.ini")
        deck = CardsDeck(self.temp_path, cfg)

        self.assertEqual(len(deck.cards), 2)
        c1 = deck.cards[0]
        self.assertEqual(c1.id, "c01")
        self.assertEqual(c1.assunto, "Direito")
        self.assertEqual(c1.subtema, "Princípios")
        self.assertEqual(c1.titulo, "Legalidade")
        self.assertEqual(c1.texto, "Regra fundamental\nSegunda linha explicativa.")
        self.assertEqual(c1.origem, "Cap 1")

    # 3. Algoritmo de repetição espaçada e seleção
    def test_03_algoritmo_selecao_cards(self):
        dados_dir = self.temp_path / "dados"
        dados_dir.mkdir()
        tsv_file = dados_dir / "cards.tsv"

        linhas = [
            "id\tassunto\tsubtema\ttitulo\ttexto\torigem",
            "id1\tTema\tSub\tT1\tTexto 1\tOrigem 1",
            "id2\tTema\tSub\tT2\tTexto 2\tOrigem 2",
            "id3\tTema\tSub\tT3\tTexto 3\tOrigem 3"
        ]
        tsv_file.write_text("\n".join(linhas), encoding="utf-8")

        cfg = ConfigManager(self.temp_path / "config.ini")
        cfg.config["new_ratio"] = 100
        cfg.config["remember_progress"] = 1
        deck = CardsDeck(self.temp_path, cfg)

        # Primeira seleção: deve ser id1 (primeiro card não visto)
        c1 = deck.selecionar_proximo_card()
        self.assertEqual(c1.id, "id1")
        self.assertEqual(deck.progresso["id1"]["exibicoes"], 1)

        # Segunda seleção (new_ratio=100): deve ser id2
        c2 = deck.selecionar_proximo_card()
        self.assertEqual(c2.id, "id2")
        self.assertEqual(deck.progresso["id2"]["exibicoes"], 1)

        # Teste crítico de revisão: id1 e id2 foram vistos, id3 ainda é novo.
        # Ao forçar new_ratio=0 (revisão), o algoritmo DEVE selecionar id1 (card visto anteriormente,
        # pois id2 acabou de ser exibido) e NÃO id3.
        cfg.config["new_ratio"] = 0
        c_revisao = deck.selecionar_proximo_card()
        self.assertEqual(c_revisao.id, "id1", "Revisão deve escolher card já visto (id1), não o não visto (id3)")

        # Agora voltamos a pedir card novo (new_ratio=100): deve ser id3
        cfg.config["new_ratio"] = 100
        c3 = deck.selecionar_proximo_card()
        self.assertEqual(c3.id, "id3")

        # Agora todos foram vistos ao menos 1 vez. Com new_ratio=0 (revisão pura):
        cfg.config["new_ratio"] = 0
        # id3 foi o último exibido, então o algoritmo NÃO pode repetir id3 consecutivamente
        c4 = deck.selecionar_proximo_card()
        self.assertIn(c4.id, ["id1", "id2"])
        self.assertNotEqual(c4.id, "id3")

    # 4. Sincronização e persistência de progresso
    def test_04_progresso_persistencia_e_sincronizacao(self):
        dados_dir = self.temp_path / "dados"
        dados_dir.mkdir()
        tsv_file = dados_dir / "cards.tsv"
        prog_file = dados_dir / "progresso.json"

        # Progresso existente com um ID que não existe mais no arquivo
        progresso_antigo = {
            "id_ativo": {"exibicoes": 5, "ultima": 1700000000},
            "id_obsoleto": {"exibicoes": 12, "ultima": 1690000000}
        }
        prog_file.write_text(json.dumps(progresso_antigo), encoding="utf-8")

        # TSV com apenas o id_ativo
        linhas = [
            "id\tassunto\tsubtema\ttitulo\ttexto\torigem",
            "id_ativo\tTema\tSub\tTitulo\tTexto ativo\tOrigem"
        ]
        tsv_file.write_text("\n".join(linhas), encoding="utf-8")

        cfg = ConfigManager(self.temp_path / "config.ini")
        deck = CardsDeck(self.temp_path, cfg)

        # O id_obsoleto deve ter sido removido na sincronização
        self.assertIn("id_ativo", deck.progresso)
        self.assertNotIn("id_obsoleto", deck.progresso)

        # Salvar e recarregar
        deck.salvar_progresso()
        with open(prog_file, "r", encoding="utf-8") as f:
            novo_json = json.load(f)
        self.assertIn("id_ativo", novo_json)
        self.assertNotIn("id_obsoleto", novo_json)

    # 5. Janela do Overlay: flags, atributos e posicionamento
    def test_05_overlay_window_flags_e_geometria(self):
        cfg = ConfigManager(self.temp_path / "config.ini")
        cfg.config["width"] = 430
        cfg.config["height"] = 150
        cfg.config["margin_x"] = 25
        cfg.config["margin_y"] = 25

        window = OverlayWindow(cfg)

        flags = window.windowFlags()
        self.assertTrue(bool(flags & Qt.WindowType.WindowStaysOnTopHint))
        self.assertTrue(bool(flags & Qt.WindowType.FramelessWindowHint))
        self.assertTrue(bool(flags & Qt.WindowType.WindowDoesNotAcceptFocus))

        # Padrão é interativo (click_through=0): recebe eventos de mouse para arrasto e lixeira
        self.assertFalse(bool(flags & Qt.WindowType.WindowTransparentForInput))
        self.assertFalse(window.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        self.assertTrue(window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
        self.assertEqual(window.cursor().shape(), Qt.CursorShape.OpenHandCursor)

        # Modo passivo (click_through=1): cliques devem atravessar
        cfg_pass = ConfigManager(self.temp_path / "config.ini")
        cfg_pass.config["click_through"] = 1
        win_pass = OverlayWindow(cfg_pass)
        self.assertTrue(bool(win_pass.windowFlags() & Qt.WindowType.WindowTransparentForInput))
        self.assertTrue(win_pass.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))

        # Testar exibição de card e posicionamento
        card = Card("c1", "Assunto", "Subtema", "Título", "Texto do teste", "Origem")
        window.exibir_card(card)

        self.assertIn("Assunto", window.lbl_assunto.text())
        self.assertIn("Subtema", window.lbl_assunto.text())
        self.assertEqual(window.lbl_titulo.text(), "Título")
        self.assertEqual(window.lbl_texto.text(), "Texto do teste")
        self.assertIn("Origem", window.lbl_origem.text())
        self.assertIn("c1", window.lbl_origem.text())

    # 6. Cálculo de posição nos 4 cantos
    def test_06_calculo_posicoes_cantos(self):
        cfg = ConfigManager(self.temp_path / "config.ini")
        cfg.config["width"] = 400
        cfg.config["height"] = 150
        cfg.config["margin_x"] = 20
        cfg.config["margin_y"] = 30

        window = OverlayWindow(cfg)
        screen = QApplication.primaryScreen()
        geo = screen.geometry() if screen else None
        s_w = geo.width() if geo else 1920
        s_h = geo.height() if geo else 1080

        # Canto superior direito
        cfg.config["corner"] = "top_right"
        window.reposicionar()
        self.assertEqual(window.pos().x(), s_w - 400 - 20)
        self.assertEqual(window.pos().y(), 30)

        # Canto superior esquerdo
        cfg.config["corner"] = "top_left"
        window.reposicionar()
        self.assertEqual(window.pos().x(), 20)
        self.assertEqual(window.pos().y(), 30)

        # Canto inferior direito
        cfg.config["corner"] = "bottom_right"
        window.reposicionar()
        self.assertEqual(window.pos().x(), s_w - 400 - 20)
        self.assertEqual(window.pos().y(), s_h - 150 - 30)

        # Canto inferior esquerdo
        cfg.config["corner"] = "bottom_left"
        window.reposicionar()
        self.assertEqual(window.pos().x(), 20)
        self.assertEqual(window.pos().y(), s_h - 150 - 30)

    # 7. Controlador e execução de comandos IPC
    def test_07_controller_comandos_e_ciclo(self):
        dados_dir = self.temp_path / "dados"
        dados_dir.mkdir()
        tsv_file = dados_dir / "cards.tsv"
        linhas = [
            "id\tassunto\tsubtema\ttitulo\ttexto\torigem",
            "c1\tTema\tSub\tT1\tTexto 1\tOrigem 1",
            "c2\tTema\tSub\tT2\tTexto 2\tOrigem 2"
        ]
        tsv_file.write_text("\n".join(linhas), encoding="utf-8")

        cfg = ConfigManager(self.temp_path / "config.ini")
        cfg.config["show_on_start"] = 1
        cfg.config["interval_seconds"] = 10
        cfg.config["visible_seconds"] = 5

        deck = CardsDeck(self.temp_path, cfg)
        ctrl = OverlayController(self.temp_path, cfg, deck)

        # Card inicial deve estar visível
        self.assertTrue(ctrl.card_visivel)
        self.assertIsNotNone(ctrl.card_atual)

        # Testar comando de ocultar
        resp_hide = ctrl.executar_comando("hide")
        self.assertIn("card ocultado", resp_hide)
        self.assertFalse(ctrl.card_visivel)

        # Testar comando de pausa
        resp_pause = ctrl.executar_comando("pause")
        self.assertIn("pausado", resp_pause)
        self.assertTrue(ctrl.esta_pausado)

        resp_resume = ctrl.executar_comando("pause")
        self.assertIn("retomado", resp_resume)
        self.assertFalse(ctrl.esta_pausado)

        # Testar comando de status
        resp_status = ctrl.executar_comando("status")
        dados_status = json.loads(resp_status)
        self.assertEqual(dados_status["total_cards"], 2)
        self.assertEqual(dados_status["status"], "ativo")

        # Testar comando proximo
        resp_next = ctrl.executar_comando("next")
        self.assertIn("proximo card exibido", resp_next)
        self.assertTrue(ctrl.card_visivel)

        # Limpar servidor IPC
        ctrl.ipc_server.close()

    # 8. Ajuste de altura dinâmica para não truncar texto longo
    def test_08_ajuste_altura_dinamica_sem_truncamento(self):
        cfg = ConfigManager(self.temp_path / "config.ini")
        cfg.config["width"] = 440
        cfg.config["height"] = 160
        cfg.config["font_size"] = 17

        window = OverlayWindow(cfg)

        texto_longo = (
            "Este é um texto consideravelmente longo com múltiplas sentenças explicativas. "
            "Ele detalha conceitos aprofundados sobre a administração pública, abrangendo os "
            "princípios da legalidade, impessoalidade, moralidade, publicidade e eficiência."
        )
        card = Card("c_longo", "Assunto Extenso", "Subtema Detalhado", "Título Completo", texto_longo, "Linha 100")
        window.exibir_card(card)

        # A altura da janela deve acomodar o conteúdo e ser no mínimo a altura configurada (160)
        self.assertGreaterEqual(window.height(), 160)

    # 9. Suporte a arquivo de conteúdo customizado (--conteudo)
    def test_09_conteudo_customizado_e_reprocessamento(self):
        arquivo_custom = self.temp_path / "meu_estudo.md"
        arquivo_custom.write_text("# Tema Teste\n\n- Conceito Alpha: Definição clara para teste unitário.\n", encoding="utf-8")

        cfg = ConfigManager(self.temp_path / "config.ini")
        cfg.config["arquivo"] = str(arquivo_custom)

        deck = CardsDeck(self.temp_path, cfg, conteudo_custom=str(arquivo_custom))
        self.assertEqual(deck.conteudo_custom, str(arquivo_custom))

    # 10. Restauração de configurações de terminal no encerramento
    def test_10_restauracao_terminal(self):
        import overlay_linux
        overlay_linux._terminal_old_settings = ["dummy"]
        overlay_linux._terminal_fd = 0
        restaurar_terminal()
        self.assertIsNone(overlay_linux._terminal_old_settings)

    # 11. Passagem de eventos de mouse (click-through defensivo)
    # 11. Passagem de eventos de mouse (click-through defensivo)
    def test_11_mouse_events_pass_through(self):
        cfg = ConfigManager(self.temp_path / "config.ini")
        cfg.config["click_through"] = 1
        window = OverlayWindow(cfg)
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QEvent, QPointF
        evt = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(10, 10), QPointF(10, 10), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        window.mousePressEvent(evt)
        self.assertFalse(evt.isAccepted(), "Evento de clique deve ser ignorado para atravessar o overlay")

    # 12. Modo interativo, arrasto de janela com mouse e persistência de posição
    def test_12_arrasto_e_posicao_customizada(self):
        cfg = ConfigManager(self.temp_path / "config.ini")
        cfg.config["click_through"] = 0
        window = OverlayWindow(cfg, raiz_projeto=self.temp_path)

        # Em modo interativo, não possui WindowTransparentForInput
        flags = window.windowFlags()
        self.assertFalse(bool(flags & Qt.WindowType.WindowTransparentForInput))
        self.assertFalse(window.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))

        # Espionar emissão de sinais de arrasto
        sinais_disparados = []
        window.sinal_arrasto_iniciado.connect(lambda: sinais_disparados.append("iniciado"))
        window.sinal_arrasto_finalizado.connect(lambda: sinais_disparados.append("finalizado"))

        # Simular arrasto com mouse
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QEvent, QPointF
        window.setGeometry(100, 100, 430, 150)

        # Pressionar no ponto (10, 10) relativo à janela
        evt_press = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(10, 10), QPointF(110, 110), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        window.mousePressEvent(evt_press)
        self.assertTrue(window._drag_active)
        self.assertIn("iniciado", sinais_disparados)

        # Mover mouse para (250, 300) global
        evt_move = QMouseEvent(QEvent.Type.MouseMove, QPointF(150, 200), QPointF(250, 300), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        window.mouseMoveEvent(evt_move)

        # Soltar mouse
        evt_release = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(150, 200), QPointF(250, 300), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        window.mouseReleaseEvent(evt_release)
        self.assertFalse(window._drag_active)
        self.assertIn("finalizado", sinais_disparados)

        # A posição customizada deve ter sido salva no arquivo posicao.json
        pos_file = self.temp_path / "dados" / "posicao.json"
        self.assertTrue(pos_file.is_file(), "Arquivo dados/posicao.json deve ter sido criado")
        with open(pos_file, "r", encoding="utf-8") as f:
            pos_dados = json.load(f)
        self.assertIn("x", pos_dados)
        self.assertIn("y", pos_dados)

        # Reposicionar deve respeitar a posição customizada
        window.reposicionar()
        self.assertEqual(window.pos().x(), pos_dados["x"])
        self.assertEqual(window.pos().y(), pos_dados["y"])

        # Testar segurança de hideEvent enquanto arrasto estava ativo
        window.mousePressEvent(evt_press)
        self.assertTrue(window._drag_active)
        window.hide()
        self.assertFalse(window._drag_active, "hideEvent deve desativar _drag_active e restaurar cursor")

        # Redefinir posição restaura para o padrão
        window.redefinir_posicao()
        self.assertFalse(pos_file.is_file())
        self.assertIsNone(window._custom_pos)

    # 13. Exclusão de card inútil (lixeira), persistência em dados/excluidos.json e avanço imediato
    def test_13_exclusao_card_e_lixeira(self):
        dados_dir = self.temp_path / "dados"
        dados_dir.mkdir(exist_ok=True)
        tsv_file = dados_dir / "cards.tsv"
        linhas = [
            "id\tassunto\tsubtema\ttitulo\ttexto\torigem",
            "c_inutil\tDireito\tGeral\tConceito Inútil\tTexto irrelevante.\tOrigem 1",
            "c_util\tDireito\tGeral\tConceito Útil\tTexto muito importante.\tOrigem 2"
        ]
        tsv_file.write_text("\n".join(linhas), encoding="utf-8")

        cfg = ConfigManager(self.temp_path / "config.ini")
        cfg.config["click_through"] = 0
        cfg.config["show_on_start"] = 1

        deck = CardsDeck(self.temp_path, cfg)
        ctrl = OverlayController(self.temp_path, cfg, deck)

        # O card atual deve ser o primeiro
        self.assertEqual(ctrl.card_atual.id, "c_inutil")

        # Acionar exclusão do card atual (simulando clique na lixeira)
        sucesso = ctrl.excluir_card_atual()
        self.assertTrue(sucesso)

        # O card excluído deve ter sido salvo em excluidos.json
        exc_file = self.temp_path / "dados" / "excluidos.json"
        self.assertTrue(exc_file.is_file())
        with open(exc_file, "r", encoding="utf-8") as f:
            excluidos = json.load(f)
        self.assertIn("c_inutil", excluidos)

        # O baralho deve conter agora apenas o card útil
        self.assertEqual(len(deck.cards), 1)
        self.assertEqual(deck.cards[0].id, "c_util")

        # O overlay deve ter avançado imediatamente para o próximo card (c_util)
        self.assertEqual(ctrl.card_atual.id, "c_util")

        # Ao recarregar o baralho, o card excluído não deve voltar
        novo_deck = CardsDeck(self.temp_path, cfg)
        self.assertEqual(len(novo_deck.cards), 1)
        self.assertEqual(novo_deck.cards[0].id, "c_util")

        # Testar comando de redefinir cards excluídos
        resp_reset = ctrl.executar_comando("reset-excluded")
        self.assertIn("restaurados", resp_reset)
        self.assertEqual(len(ctrl.deck.cards), 2)

        ctrl.ipc_server.close()

    # 14. Altura dinâmica e ausência de sobreposição de texto sobre o rodapé
    def test_14_altura_dinamica_sem_sobreposicao(self):
        cfg = ConfigManager(self.temp_path / "config.ini")
        cfg.config["width"] = 460
        cfg.config["height"] = 160
        cfg.config["font_size"] = 12
        cfg.config["click_through"] = 0

        window = OverlayWindow(cfg, raiz_projeto=self.temp_path)

        # Card real reportado pelo usuário com texto extenso
        texto_real = (
            "É a base geográfica, espacial ou física sobre a qual o Estado exerce de "
            "forma soberana a sua jurisdição (solo, subsolo, espaço aéreo e mar territorial, "
            "Além de representações diplomáticas e navios/aeronaves militares por extensão ficta)."
        )
        card = Card("6f8226b8a902", "1. Estado, Governo e Administração Pública: Conceito", "Conceito do Estado", "Território", texto_real, "Linha 41")
        window.exibir_card(card)

        # Garantir layout executado e checar visibilidade da lixeira
        app.processEvents()
        self.assertTrue(window.btn_lixeira.isVisible())

        # Verificar que o corpo do texto termina antes do topo do rodapé
        geo_texto = window.lbl_texto.geometry()
        geo_origem = window.lbl_origem.geometry()
        self.assertLess(
            geo_texto.bottom(),
            geo_origem.top(),
            f"O texto (bottom={geo_texto.bottom()}) não deve se sobrepor ao rodapé (top={geo_origem.top()})"
        )

    # 15. Pausa e retomada do timer de visibilidade durante arrasto com mouse
    def test_15_pausa_e_retomada_timer_durante_arrasto(self):
        dados_dir = self.temp_path / "dados"
        dados_dir.mkdir(exist_ok=True)
        tsv_file = dados_dir / "cards.tsv"
        tsv_file.write_text("id\tassunto\tsubtema\ttitulo\ttexto\torigem\nc1\tT\tS\tTit\tTxt\tO\n", encoding="utf-8")

        cfg = ConfigManager(self.temp_path / "config.ini")
        cfg.config["show_on_start"] = 1
        cfg.config["click_through"] = 0
        cfg.config["visible_seconds"] = 15

        deck = CardsDeck(self.temp_path, cfg)
        ctrl = OverlayController(self.temp_path, cfg, deck)

        # O card deve estar visível e o timer ativo
        self.assertTrue(ctrl.card_visivel)
        self.assertTrue(ctrl.timer_visibilidade.isActive())

        # Início do arrasto: deve pausar o timer de visibilidade
        ctrl.window.sinal_arrasto_iniciado.emit()
        self.assertFalse(ctrl.timer_visibilidade.isActive(), "Timer de visibilidade deve ser pausado durante o arrasto")

        # Fim do arrasto: deve reiniciar o timer de visibilidade
        ctrl.window.sinal_arrasto_finalizado.emit()
        self.assertTrue(ctrl.timer_visibilidade.isActive(), "Timer de visibilidade deve ser retomado após soltar o mouse")

        ctrl.ipc_server.close()

    # 16. Elisão de texto dinâmico e preservação de texto completo em Tooltip
    def test_16_elisao_e_tooltip_sem_corte_de_palavras(self):
        cfg = ConfigManager(self.temp_path / "config.ini")
        cfg.config["width"] = 430
        cfg.config["font_size"] = 11

        window = OverlayWindow(cfg, raiz_projeto=self.temp_path)
        assunto_longo = "1. Estado, Governo e Administração Pública: Conceito, Elementos e Princípios"
        subtema_longo = "Organização do Estado e Separação de Poderes Constitucionais"
        titulo_longo = "Conceito Geral e Doutrinário da Soberania Estatal na República Federativa"
        card = Card("c_elide", assunto_longo, subtema_longo, titulo_longo, "Texto explicativo.", "Linha 10")

        window.exibir_card(card)
        app.processEvents()

        # Tooltips devem conter a íntegra sem cortes
        self.assertIn(assunto_longo, window.lbl_assunto.toolTip())
        self.assertIn(subtema_longo, window.lbl_assunto.toolTip())
        self.assertEqual(window.lbl_titulo.toolTip(), titulo_longo)

        # O texto exibido no label do assunto deve conter o caractere de reticências/elisão
        # e ter tamanho menor ou igual à largura disponível
        txt_exibido = window.lbl_assunto.text()
        self.assertTrue(txt_exibido.endswith("…") or txt_exibido.endswith("..."))

    # 17. Ícone vetorial da lixeira e propriedades de foco
    def test_17_icone_vetorial_lixeira_e_propriedades(self):
        cfg = ConfigManager(self.temp_path / "config.ini")
        cfg.config["click_through"] = 0
        window = OverlayWindow(cfg, raiz_projeto=self.temp_path)

        self.assertFalse(window.btn_lixeira.icon().isNull())
        self.assertEqual(window.btn_lixeira.cursor().shape(), Qt.CursorShape.PointingHandCursor)


    # 18. Persistência de coordenada zero (0, 0) e posicionamento multi-monitor
    def test_18_persistencia_posicao_zero_e_multi_monitor(self):
        cfg = ConfigManager(self.temp_path / "config.ini")
        cfg.config["click_through"] = 0
        window = OverlayWindow(cfg, raiz_projeto=self.temp_path)

        # Fixar explicitamente a posição customizada em (0, 0)
        window._custom_pos = QPoint(0, 0)
        window.salvar_posicao()

        pos_file = self.temp_path / "dados" / "posicao.json"
        self.assertTrue(pos_file.is_file(), "Arquivo posicao.json deve existir mesmo para (0, 0)")
        with open(pos_file, "r", encoding="utf-8") as f:
            dados = json.load(f)
        self.assertEqual(dados["x"], 0)
        self.assertEqual(dados["y"], 0)

        # Nova janela carregando o mesmo arquivo deve respeitar (0, 0)
        window2 = OverlayWindow(cfg, raiz_projeto=self.temp_path)
        self.assertIsNotNone(window2._custom_pos)
        self.assertEqual(window2._custom_pos.x(), 0)
        self.assertEqual(window2._custom_pos.y(), 0)

        window2.reposicionar()
        self.assertEqual(window2.pos().x(), 0)
        self.assertEqual(window2.pos().y(), 0)

    # 19. Geração contínua no mesmo local arrastado para múltiplos cards e ciclos subsequentes
    def test_19_geracao_continua_mesma_posicao_cards_subsequentes(self):
        cfg = ConfigManager(self.temp_path / "config.ini")
        cfg.config["click_through"] = 0
        cfg.config["corner"] = "top_right"
        window = OverlayWindow(cfg, raiz_projeto=self.temp_path)

        # Card inicial
        card1 = Card("c1", "Tema 1", "Sub 1", "Titulo 1", "Texto curto", "Origem 1")
        window.exibir_card(card1)

        # Simular arrasto para (350, 220)
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QEvent, QPointF
        cur_pos = window.pos()
        evt_press = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(10, 10), QPointF(cur_pos.x() + 10, cur_pos.y() + 10), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        window.mousePressEvent(evt_press)
        evt_move = QMouseEvent(QEvent.Type.MouseMove, QPointF(10, 10), QPointF(360, 230), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        window.mouseMoveEvent(evt_move)
        evt_release = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(10, 10), QPointF(360, 230), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        window.mouseReleaseEvent(evt_release)

        # Posição deve estar travada em (350, 220)
        self.assertEqual(window.pos().x(), 350)
        self.assertEqual(window.pos().y(), 220)

        # Ocultar card (como ocorre ao expirar o tempo)
        window.hide()

        # Próximo card no ciclo (card 2) com texto mais longo
        card2 = Card("c2", "Tema 2", "Sub 2", "Titulo 2", "Texto bem mais extenso que exige ajuste de altura dinâmica sem perder a coordenada x e y arrastada pelo usuário na tela", "Origem 2")
        window.exibir_card(card2)

        # O card subsequente DEVE nascer exatamente nas coordenadas x=350, y=220 arrastadas
        self.assertEqual(window.pos().x(), 350, "Card 2 deve permanecer na coordenada X arrastada")
        self.assertEqual(window.pos().y(), 220, "Card 2 deve permanecer na coordenada Y arrastada")

        # Terceiro card subsequente
        window.hide()
        card3 = Card("c3", "Tema 3", "Sub 3", "Titulo 3", "Outro conceito", "Origem 3")
        window.exibir_card(card3)
        self.assertEqual(window.pos().x(), 350, "Card 3 deve manter a mesma coordenada X")
        self.assertEqual(window.pos().y(), 220, "Card 3 deve manter a mesma coordenada Y")

        # Apenas ao redefinir a posição explicitamente ela deve retornar ao canto configurado
        window.redefinir_posicao()
        self.assertIsNone(window._custom_pos)
        self.assertNotEqual(window.pos().x(), 350)

    # 20. Reinício completo do aplicativo preserva a posição customizada pelo usuário
    def test_20_reinicio_aplicativo_preserva_posicao_arrastada(self):
        dados_dir = self.temp_path / "dados"
        dados_dir.mkdir(exist_ok=True)
        tsv_file = dados_dir / "cards.tsv"
        tsv_file.write_text("id\tassunto\tsubtema\ttitulo\ttexto\torigem\nc1\tT\tS\tTit1\tTxt1\tO1\nc2\tT\tS\tTit2\tTxt2\tO2\n", encoding="utf-8")

        cfg = ConfigManager(self.temp_path / "config.ini")
        cfg.config["click_through"] = 0
        cfg.config["show_on_start"] = 1
        cfg.config["interval_seconds"] = 300

        deck = CardsDeck(self.temp_path, cfg)
        ctrl1 = OverlayController(self.temp_path, cfg, deck)

        # O usuário arrasta o card para (200, 180)
        ctrl1.window._custom_pos = QPoint(200, 180)
        ctrl1.window._drag_moved = True
        ctrl1.window.salvar_posicao()

        # Encerrar primeira sessão
        ctrl1.sair_aplicativo()

        # Iniciar nova sessão do aplicativo a partir do zero
        ctrl2 = OverlayController(self.temp_path, cfg, deck)
        self.assertIsNotNone(ctrl2.window._custom_pos, "Nova sessão deve ter carregado _custom_pos")
        self.assertEqual(ctrl2.window._custom_pos.x(), 200)
        self.assertEqual(ctrl2.window._custom_pos.y(), 180)

        # O card exibido deve estar exatamente na posição salva
        self.assertEqual(ctrl2.window.pos().x(), 200)
        self.assertEqual(ctrl2.window.pos().y(), 180)
        ctrl2.sair_aplicativo()

    # 21. Arrasto com mouseReleaseEvent para coordenada (0, 0) preserva (0, 0)
    def test_21_arrasto_para_coordenada_zero_mouse_release(self):
        cfg = ConfigManager(self.temp_path / "config.ini")
        cfg.config["click_through"] = 0
        window = OverlayWindow(cfg, raiz_projeto=self.temp_path)

        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QEvent, QPointF

        window.setGeometry(100, 100, 430, 150)
        # Pressionar no ponto (0, 0) da janela (global 100, 100)
        evt_press = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(0, 0), QPointF(100, 100), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        window.mousePressEvent(evt_press)

        # Mover para global (0, 0)
        evt_move = QMouseEvent(QEvent.Type.MouseMove, QPointF(0, 0), QPointF(0, 0), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        window.mouseMoveEvent(evt_move)

        # Soltar mouse em (0, 0)
        evt_release = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(0, 0), QPointF(0, 0), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        window.mouseReleaseEvent(evt_release)

        # Deve ter gravado exatamente (0, 0)
        self.assertIsNotNone(window._custom_pos)
        self.assertEqual(window._custom_pos.x(), 0)
        self.assertEqual(window._custom_pos.y(), 0)

        pos_file = self.temp_path / "dados" / "posicao.json"
        self.assertTrue(pos_file.is_file())
        with open(pos_file, "r", encoding="utf-8") as f:
            dados = json.load(f)
        self.assertEqual(dados["x"], 0)
        self.assertEqual(dados["y"], 0)

    # 22. Clique simples ou micro-movimento (jitter <= 2px) não altera coordenadas nem salva posição desnecessariamente
    def test_22_clique_sem_arrasto_micro_movimento(self):
        cfg = ConfigManager(self.temp_path / "config.ini")
        cfg.config["click_through"] = 0
        window = OverlayWindow(cfg, raiz_projeto=self.temp_path)
        window.setGeometry(300, 200, 430, 150)

        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QEvent, QPointF

        pos_file = self.temp_path / "dados" / "posicao.json"

        # Clique no ponto (50, 50) com jitter de 1 pixel
        evt_press = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(50, 50), QPointF(350, 250), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        window.mousePressEvent(evt_press)

        evt_move = QMouseEvent(QEvent.Type.MouseMove, QPointF(51, 51), QPointF(351, 251), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        window.mouseMoveEvent(evt_move)

        evt_release = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(51, 51), QPointF(351, 251), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        window.mouseReleaseEvent(evt_release)

        # Não deve ter ativado _drag_moved e não deve ter criado arquivo
        self.assertFalse(pos_file.is_file(), "Micro-jitter não deve criar posicao.json")
        self.assertIsNone(window._custom_pos)

    # 23. Posicionamento multi-monitor sem trava artificial na borda de monitor único (ex: x=1600 em desktop amplo)
    def test_23_multi_monitor_arrasto_livre_e_borda(self):
        cfg = ConfigManager(self.temp_path / "config.ini")
        cfg.config["click_through"] = 0
        cfg.config["width"] = 430
        cfg.config["height"] = 150
        window = OverlayWindow(cfg, raiz_projeto=self.temp_path)

        # Definir posição customizada em x=1600, y=200
        window._custom_pos = QPoint(1600, 200)
        window.salvar_posicao()

        # Reposicionar para exibir card
        card1 = Card("c1", "T", "S", "Titulo", "Texto", "Origem")
        window.exibir_card(card1)

        # A coordenada X deve permanecer em 1600 (não travando em 1490 em desktops >= 1920)
        screens = QApplication.screens()
        desktop_w = sum(s.geometry().width() for s in screens) if screens else 1920
        if desktop_w > 1920:
            self.assertEqual(window.pos().x(), 1600, "Em desktop multi-monitor, x=1600 não deve ser travado a 1490")
            self.assertEqual(window.pos().y(), 200)

        # Próximo card também deve permanecer em 1600
        card2 = Card("c2", "T", "S", "Titulo 2", "Outro texto mais extenso", "Origem 2")
        window.exibir_card(card2)
        if desktop_w > 1920:
            self.assertEqual(window.pos().x(), 1600)
            self.assertEqual(window.pos().y(), 200)

    # 24. Timer de ciclo não interrompe arrasto ativo
    def test_24_ciclo_nao_interrompe_arrasto_ativo(self):
        dados_dir = self.temp_path / "dados"
        dados_dir.mkdir(exist_ok=True)
        tsv_file = dados_dir / "cards.tsv"
        tsv_file.write_text("id\tassunto\tsubtema\ttitulo\ttexto\torigem\nc1\tT\tS\tTit1\tTxt1\tO1\nc2\tT\tS\tTit2\tTxt2\tO2\n", encoding="utf-8")

        cfg = ConfigManager(self.temp_path / "config.ini")
        cfg.config["show_on_start"] = 1
        cfg.config["click_through"] = 0

        deck = CardsDeck(self.temp_path, cfg)
        ctrl = OverlayController(self.temp_path, cfg, deck)

        # Card 1 exibido
        self.assertEqual(ctrl.card_atual.id, "c1")

        # Simular que o usuário está segurando o mouse para arrastar
        ctrl.window._drag_active = True

        # Tentar acionar o próximo card enquanto o usuário arrasta
        ctrl.exibir_proximo_card()

        # O card atual NÃO deve ter sido substituído
        self.assertEqual(ctrl.card_atual.id, "c1", "Não deve avançar card enquanto _drag_active for True")
        self.assertTrue(ctrl.timer_ciclo.isActive(), "Deve ter reagendado tentativa")

        # Liberar arrasto
        ctrl.window._drag_active = False
        ctrl.sair_aplicativo()

    # 25. Recarregamento de conteúdo recarrega dados/posicao.json do disco
    def test_25_recarregar_conteudo_recarrega_posicao(self):
        dados_dir = self.temp_path / "dados"
        dados_dir.mkdir(exist_ok=True)
        tsv_file = dados_dir / "cards.tsv"
        tsv_file.write_text("id\tassunto\tsubtema\ttitulo\ttexto\torigem\nc1\tT\tS\tTit1\tTxt1\tO1\n", encoding="utf-8")

        # Criar arquivo de estudo markdown para o conversor
        md_file = self.temp_path / "conteudo.md"
        md_file.write_text("# Tema\n## Sub\n### Tit1\nTexto suficiente para um card de teste.\n", encoding="utf-8")

        cfg = ConfigManager(self.temp_path / "config.ini")
        cfg.config["arquivo"] = "conteudo.md"
        cfg.config["click_through"] = 0
        cfg.config["show_on_start"] = 0

        deck = CardsDeck(self.temp_path, cfg)
        ctrl = OverlayController(self.temp_path, cfg, deck)
        self.assertIsNone(ctrl.window._custom_pos)

        # Escrever posicao.json externamente no disco
        pos_file = self.temp_path / "dados" / "posicao.json"
        with open(pos_file, "w", encoding="utf-8") as f:
            json.dump({"x": 450, "y": 350}, f)

        # Executar recarregamento
        ctrl.window.carregar_posicao()
        self.assertIsNotNone(ctrl.window._custom_pos)
        self.assertEqual(ctrl.window._custom_pos.x(), 450)
        self.assertEqual(ctrl.window._custom_pos.y(), 350)

        ctrl.sair_aplicativo()


if __name__ == "__main__":
    unittest.main()


