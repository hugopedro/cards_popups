#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
preparar_conteudo.py - Conversor Universal de Markdown para Microlições (Cards)

Converte qualquer arquivo de estudo Markdown em microlições estruturadas em dados/cards.tsv,
com resumo em dados/relatorio_conversao.txt. Sem dependências externas além do Python 3 padrão.
"""

import os
import sys
import re
import html
import hashlib
import argparse
import configparser
from pathlib import Path


class Card:
    """Representa uma microlição individual para o overlay."""
    def __init__(self, card_id, assunto, subtema, titulo, texto, origem):
        self.id = card_id.strip()
        self.assunto = assunto.strip() or "Estudo"
        self.subtema = subtema.strip() or "Geral"
        self.titulo = titulo.strip() or "Conceito"
        self.texto = texto.strip()
        self.origem = origem.strip() or "Geral"

    def para_tsv(self):
        def limpar_campo(val):
            val = val.replace("\t", " ")
            val = val.replace("\r\n", "\n").replace("\r", "\n")
            val = val.replace("\n", "\\n")
            return val.strip()

        return (
            f"{limpar_campo(self.id)}\t"
            f"{limpar_campo(self.assunto)}\t"
            f"{limpar_campo(self.subtema)}\t"
            f"{limpar_campo(self.titulo)}\t"
            f"{limpar_campo(self.texto)}\t"
            f"{limpar_campo(self.origem)}"
        )


def limpar_markdown(texto):
    """Converte Markdown inline em texto simples, legível e limpo, sem artefatos."""
    if not texto:
        return ""

    # Links e imagens
    texto = re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'\1', texto)
    texto = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', texto)
    texto = re.sub(r'<(https?://[^>]+)>', r'\1', texto)

    # Quebras de linha e tags HTML
    texto = re.sub(r'<(?:br|BR)\s*/?>', ' ', texto)
    texto = re.sub(r'<[^>]+>', '', texto)
    texto = html.unescape(texto)

    # Formatação de ênfase em pares
    texto = re.sub(r'\*\*\*([^*]+)\*\*\*', r'\1', texto)
    texto = re.sub(r'\*\*([^*]+)\*\*', r'\1', texto)
    texto = re.sub(r'\*([^*]+)\*', r'\1', texto)
    texto = re.sub(r'___([^_]+)___', r'\1', texto)
    texto = re.sub(r'__([^_]+)__', r'\1', texto)
    texto = re.sub(r'_([^_]+)_', r'\1', texto)

    # Código inline e tachado
    texto = re.sub(r'`([^`]+)`', r'\1', texto)
    texto = re.sub(r'~~([^~]+)~~', r'\1', texto)

    # Limpeza de asteriscos, sublinhados ou crases órfãs residuais
    texto = re.sub(r'\*+', '', texto)
    texto = re.sub(r'_+', '', texto)
    texto = re.sub(r'`+', '', texto)

    # Normalizar espaços
    texto = re.sub(r'[ \t]+', ' ', texto)
    return texto.strip()


def gerar_id(assunto, subtema, titulo, texto):
    """Gera um hash estável e determinístico de 12 caracteres hexadecimais."""
    chave = f"{assunto}|{subtema}|{titulo}|{texto[:80]}".encode('utf-8', errors='ignore')
    return hashlib.sha256(chave).hexdigest()[:12]


def quebrar_em_limite_de_palavra(texto, max_chars):
    """
    Quebra sentenças longas no limite de palavra ou oração mais próximo de max_chars.
    NUNCA divide palavras ao meio nem faz fatiamento arbitrário por índice.
    """
    texto = texto.strip()
    if len(texto) <= max_chars:
        return [texto]

    # 1. Tenta quebrar por pontuação de oração (;, —, –, ,, :) dentro do limite
    pontuacoes = ['; ', ' — ', ' – ', ', ', ': ']
    melhor_pos = -1

    for pont in pontuacoes:
        pos = texto.rfind(pont, 0, max_chars)
        if pos >= 50:  # Garante pelo menos 50 caracteres no primeiro fragmento
            melhor_pos = pos + len(pont.rstrip())
            break

    # 2. Se não houver pontuação intermediária, quebra no último espaço antes de max_chars
    if melhor_pos == -1:
        pos = texto.rfind(' ', 0, max_chars)
        if pos >= 40:
            melhor_pos = pos

    # 3. Se ainda assim não encontrou (palavra muito longa), procura o próximo espaço logo após max_chars
    if melhor_pos == -1:
        pos = texto.find(' ', max_chars)
        if pos != -1:
            melhor_pos = pos
        else:
            return [texto]

    parte1 = texto[:melhor_pos].strip()
    parte2 = texto[melhor_pos:].strip()

    # Sanitiza parte2: remove conectivos ou pontuações órfãs no início
    parte2 = re.sub(r'^(?:e|ou|de|que|com|para)\s+', '', parte2, flags=re.IGNORECASE)
    parte2 = parte2.lstrip(',;:—– ')
    if parte2:
        parte2 = parte2[0].upper() + parte2[1:]

    resultado = [parte1]
    if parte2 and len(parte2) >= 20:
        if len(parte2) > max_chars:
            resultado.extend(quebrar_em_limite_de_palavra(parte2, max_chars))
        else:
            resultado.append(parte2)

    return resultado


def encurtar_no_limite_de_palavra(texto: str, max_chars: int) -> str:
    """
    Encurta texto no limite de palavras mais próximo, evitando fatiar palavras no meio.
    NUNCA quebra um termo ao meio (ex: 'Elemento...' em vez de 'Elementos').
    """
    texto = texto.strip()
    if len(texto) <= max_chars:
        return texto
    limite = max_chars - 3
    ultimo_espaco = texto[:limite].rfind(" ")
    if ultimo_espaco > limite // 2:
        return texto[:ultimo_espaco].rstrip(" ,;:.-–—") + "..."
    return texto[:limite].rstrip(" ,;:.-–—") + "..."



def dividir_em_sentencas(texto, max_chars=220):
    """
    Divide texto em sentenças respeitando abreviações doutrinárias e pontuação jurídica.
    Evita quebras indevidas em artigos de lei, números de processos e siglas.
    """
    abrevs = [
        (r'\bart\.', 'art@@'),
        (r'\barts\.', 'arts@@'),
        (r'\bnº\.', 'nº@@'),
        (r'\bno\.', 'no@@'),
        (r'\bex\.', 'ex@@'),
        (r'\bp\. ?ex\.', 'p@@ex@@'),
        (r'\binc\.', 'inc@@'),
        (r'\bal\.', 'al@@'),
        (r'\bfls\.', 'fls@@'),
        (r'\bprof\.', 'prof@@'),
        (r'\bdr\.', 'dr@@'),
        (r'\bdra\.', 'dra@@'),
        (r'\bsv\.', 'sv@@'),
        (r'\bv\. ?g\.', 'v@@g@@'),
        (r'\bc/c\.', 'c@@c@@'),
        (r'\bpar\.', 'par@@'),
        (r'(\d+)\.(\d+)', r'\1@@\2')
    ]
    temp = texto
    for padrao, subst in abrevs:
        temp = re.sub(padrao, subst, temp, flags=re.IGNORECASE)

    partes = re.split(r'(?<=[.!?])\s+', temp)

    resultado = []
    for parte in partes:
        p = parte.replace('@@', '.')
        p = p.strip()
        if p:
            if len(p) > max_chars:
                resultado.extend(quebrar_em_limite_de_palavra(p, max_chars))
            else:
                resultado.append(p)
    return resultado


def agrupar_sentencas(sentencas, min_chars, max_chars):
    """
    Agrupa sentenças sucessivas para atingir a faixa ideal de caracteres (90-220).
    Evita fragmentos soltos ou parágrafos longos demais.
    """
    grupos = []
    atual = ""

    for s in sentencas:
        s = s.strip()
        if not s:
            continue

        if not atual:
            atual = s
        else:
            combinado = f"{atual} {s}"
            if len(combinado) <= max_chars:
                atual = combinado
            else:
                if len(atual) >= min_chars:
                    grupos.append(atual)
                    atual = s
                else:
                    if len(combinado) <= max_chars + 35:
                        grupos.append(combinado)
                        atual = ""
                    else:
                        grupos.append(atual)
                        atual = s

    if atual:
        if grupos and len(atual) < min_chars and (len(grupos[-1]) + len(atual) + 1 <= max_chars + 35):
            grupos[-1] = f"{grupos[-1]} {atual}"
        else:
            grupos.append(atual)

    return grupos


class ParserMarkdown:
    """Parser robusto orientado a estudo para microaprendizagem."""
    def __init__(self, min_chars=90, max_chars=220, ignorar_secoes=None):
        self.min_chars = min_chars
        self.max_chars = max_chars
        self.ignorar_secoes = [s.strip().lower() for s in (ignorar_secoes or []) if s.strip()]
        self.cards = []
        self.avisos = []
        self.secoes_ignoradas_encontradas = []
        self.elementos_complexos = []

    def deve_ignorar_secao(self, titulo_secao):
        titulo_lower = titulo_secao.strip().lower()
        for ign in self.ignorar_secoes:
            if ign in titulo_lower:
                return True
        return False

    def adicionar_card(self, assunto, subtema, titulo, texto, origem):
        texto_limpo = limpar_markdown(texto)
        if not texto_limpo or len(texto_limpo) < 30:
            return

        # Ignorar fragmentos puramente introdutórios sem conteúdo substantivo
        if texto_limpo.endswith(":") and len(texto_limpo) < 55:
            return

        # Ajuste de tamanho de assunto, subtema e título para evitar estouro no overlay
        assunto_fmt = encurtar_no_limite_de_palavra(limpar_markdown(assunto), 65)

        subtema_fmt = limpar_markdown(subtema)
        if len(subtema_fmt) > 65:
            partes_sub = [p.strip() for p in subtema_fmt.split("›") if p.strip()]
            subtema_fmt = partes_sub[-1] if partes_sub else subtema_fmt
            subtema_fmt = encurtar_no_limite_de_palavra(subtema_fmt, 65)

        titulo_fmt = encurtar_no_limite_de_palavra(limpar_markdown(titulo), 48)

        cid = gerar_id(assunto_fmt, subtema_fmt, titulo_fmt, texto_limpo)
        card = Card(
            card_id=cid,
            assunto=assunto_fmt,
            subtema=subtema_fmt,
            titulo=titulo_fmt,
            texto=texto_limpo,
            origem=origem
        )
        self.cards.append(card)

    def processar_arquivo(self, caminho_arquivo):
        if not os.path.isfile(caminho_arquivo):
            raise FileNotFoundError(f"Arquivo não encontrado: {caminho_arquivo}")

        with open(caminho_arquivo, "r", encoding="utf-8", errors="replace") as f:
            linhas = f.readlines()

        if not linhas or all(not l.strip() for l in linhas):
            self.avisos.append("Arquivo vazio ou contendo apenas linhas em branco.")
            return

        assunto_doc = "Estudo"
        assunto_atual = "Geral"
        subtema_base = "Visão Geral"
        subtema_atual = "Visão Geral"
        nivel_ignorado = None

        bloco_codigo = []
        em_bloco_codigo = False
        linha_inicio_codigo = 0

        tabela_linhas = []
        em_tabela = False
        linha_inicio_tabela = 0

        i = 0
        total_linhas = len(linhas)

        while i < total_linhas:
            linha_raw = linhas[i]
            num_linha = i + 1
            linha = linha_raw.strip()

            # 1. Cercas de código (fenced code blocks ```)
            if linha.startswith("```"):
                if not em_bloco_codigo:
                    em_bloco_codigo = True
                    linha_inicio_codigo = num_linha
                    bloco_codigo = []
                else:
                    em_bloco_codigo = False
                    if nivel_ignorado is None:
                        self._processar_bloco_codigo(
                            bloco_codigo, assunto_atual, subtema_atual, linha_inicio_codigo
                        )
                    bloco_codigo = []
                i += 1
                continue

            if em_bloco_codigo:
                bloco_codigo.append(linha_raw)
                i += 1
                continue

            # 2. Tabelas Markdown (| col1 | col2 |)
            if linha.startswith("|") and linha.endswith("|"):
                if not em_tabela:
                    em_tabela = True
                    linha_inicio_tabela = num_linha
                    tabela_linhas = [linha]
                else:
                    tabela_linhas.append(linha)
                i += 1
                continue
            elif em_tabela:
                em_tabela = False
                if nivel_ignorado is None:
                    self._processar_tabela(
                        tabela_linhas, assunto_atual, subtema_atual, linha_inicio_tabela
                    )
                tabela_linhas = []

            # 3. Cabeçalhos (#)
            if linha.startswith("#"):
                match_header = re.match(r'^(#{1,6})\s+(.*)$', linha)
                if match_header:
                    hashes, header_text = match_header.groups()
                    nivel = len(hashes)
                    header_text = limpar_markdown(header_text).strip()

                    if nivel_ignorado is not None:
                        if nivel <= nivel_ignorado:
                            nivel_ignorado = None
                        else:
                            i += 1
                            continue

                    if self.deve_ignorar_secao(header_text):
                        nivel_ignorado = nivel
                        self.secoes_ignoradas_encontradas.append(f"Linha {num_linha}: '{header_text}'")
                        i += 1
                        continue

                    if nivel == 1:
                        assunto_doc = header_text
                        assunto_atual = header_text
                        subtema_base = "Visão Geral"
                        subtema_atual = "Visão Geral"
                    elif nivel == 2:
                        assunto_atual = header_text
                        subtema_base = "Visão Geral"
                        subtema_atual = "Visão Geral"
                    elif nivel == 3:
                        subtema_base = header_text
                        subtema_atual = header_text
                    elif nivel >= 4:
                        if subtema_base and subtema_base != "Visão Geral" and len(f"{subtema_base} › {header_text}") <= 55:
                            subtema_atual = f"{subtema_base} › {header_text}"
                        else:
                            subtema_atual = header_text
                    i += 1
                    continue

            if nivel_ignorado is not None:
                i += 1
                continue

            if not linha or re.match(r'^-{3,}$', linha):
                i += 1
                continue

            # 4. Callouts e Citações (> **Nota de Prova**: ...)
            if linha.startswith(">"):
                texto_quote = re.sub(r'^>\s*', '', linha)
                j = i + 1
                while j < total_linhas and linhas[j].strip().startswith(">"):
                    texto_quote += " " + re.sub(r'^>\s*', '', linhas[j].strip())
                    j += 1
                i = j - 1

                self._processar_citacao(texto_quote, assunto_atual, subtema_atual, num_linha)
                i += 1
                continue

            # 5. Itens de Lista / Definições (- / * / + / 1. / 1) / a))
            match_lista = re.match(r'^(?:[-*+]|\d+[\.\)]|[a-zA-Z][\.\)])\s+(.*)$', linha)
            if match_lista:
                conteudo_item = match_lista.group(1).strip()
                sub_itens = []
                j = i + 1
                while j < total_linhas:
                    linha_prox = linhas[j]
                    linha_prox_strip = linha_prox.strip()

                    if not linha_prox_strip:
                        # Se for linha em branco, checa se a próxima é um sub-item indentado
                        if j + 1 < total_linhas:
                            prox_apos = linhas[j + 1]
                            if prox_apos.startswith("  ") or prox_apos.startswith("\t"):
                                j += 1
                                continue
                        break

                    # Sub-itens indentados (2+ espaços ou tab)
                    if linha_prox.startswith("  ") or linha_prox.startswith("\t"):
                        # Extrai o sub-item preservando a formatação de negrito inicial
                        sub_str = re.sub(r'^(?:[-*+]|\d+[\.\)]|[a-zA-Z][\.\)]|>)\s+', '', linha_prox_strip)
                        if sub_str:
                            sub_itens.append(sub_str)
                        j += 1
                    else:
                        break
                i = j - 1

                self._processar_item_lista(conteudo_item, sub_itens, assunto_atual, subtema_atual, num_linha)
                i += 1
                continue

            # 6. Parágrafos Normais
            paragrafo = linha
            j = i + 1
            while j < total_linhas:
                linha_seg = linhas[j].strip()
                # Interrompe se encontrar nova estrutura (cabeçalho, lista, tabela, bloco etc.)
                if (not linha_seg or linha_seg.startswith("#") or linha_seg.startswith("-") or
                    linha_seg.startswith("*") or linha_seg.startswith("+") or linha_seg.startswith(">") or
                    linha_seg.startswith("|") or linha_seg.startswith("```") or
                    re.match(r'^\d+[\.\)]\s+', linha_seg) or
                    re.match(r'^[a-zA-Z][\.\)]\s+', linha_seg)):
                    break
                paragrafo += " " + linha_seg
                j += 1
            i = j - 1

            self._processar_paragrafo(paragrafo, assunto_atual, subtema_atual, num_linha)
            i += 1

        if em_tabela and tabela_linhas and nivel_ignorado is None:
            self._processar_tabela(tabela_linhas, assunto_atual, subtema_atual, linha_inicio_tabela)

    def _processar_citacao(self, texto_quote, assunto, subtema, linha_num):
        origem = f"Linha {linha_num}"
        match_termo = re.match(r'^\*{1,2}([^:*]+)\*{1,2}\s*:\s*(.*)$', texto_quote)
        if match_termo:
            rotulo = match_termo.group(1).strip()
            corpo = match_termo.group(2).strip()
            titulo = encurtar_no_limite_de_palavra(rotulo, 45)
            sentencas = dividir_em_sentencas(corpo, self.max_chars)
            grupos = agrupar_sentencas(sentencas, self.min_chars, self.max_chars)
            for grp in grupos:
                self.adicionar_card(assunto, subtema, titulo, grp, origem)
        else:
            titulo = "Destaque"
            sentencas = dividir_em_sentencas(texto_quote, self.max_chars)
            grupos = agrupar_sentencas(sentencas, self.min_chars, self.max_chars)
            for grp in grupos:
                self.adicionar_card(assunto, subtema, titulo, grp, origem)

    def _processar_item_lista(self, item_texto, sub_itens, assunto, subtema, linha_num):
        origem = f"Linha {linha_num}"

        # Verifica se o item possui formato **Termo**: Explicação
        match_termo = re.match(r'^\*{1,2}([^:*]+)\*{1,2}\s*(?::|-)\s*(.*)$', item_texto)
        if match_termo:
            termo = match_termo.group(1).strip()
            explicacao = match_termo.group(2).strip()
            titulo = encurtar_no_limite_de_palavra(termo, 45)

            if explicacao:
                sentencas = dividir_em_sentencas(explicacao, self.max_chars)
                grupos = agrupar_sentencas(sentencas, self.min_chars, self.max_chars)
                for grp in grupos:
                    self.adicionar_card(assunto, subtema, titulo, grp, origem)
            contexto_item = termo
        else:
            # Item sem termo em negrito destacado
            if item_texto.endswith(":") and sub_itens:
                contexto_item = limpar_markdown(item_texto.rstrip(":"))
            else:
                sentencas = dividir_em_sentencas(item_texto, self.max_chars)
                grupos = agrupar_sentencas(sentencas, self.min_chars, self.max_chars)
                titulo = encurtar_no_limite_de_palavra(subtema.split('›')[-1].strip(), 45)
                for grp in grupos:
                    self.adicionar_card(assunto, subtema, titulo, grp, origem)
                contexto_item = titulo

        # Processar sub-itens
        if sub_itens:
            # Caso 1: Sub-itens pequenos que formam lista de hipóteses (ex: requisitos ou itens curtos)
            comprimentos = [len(s) for s in sub_itens]
            media_len = sum(comprimentos) / len(comprimentos) if comprimentos else 0

            if media_len < 55 and not any(re.match(r'^\*{1,2}[^:*]+\*{1,2}\s*(?::|-)', s) for s in sub_itens):
                agrupados = []
                bloco_atual = []
                tamanho_atual = 0

                for s in sub_itens:
                    s_limpo = limpar_markdown(s).rstrip(';.')
                    if not s_limpo:
                        continue
                    if tamanho_atual + len(s_limpo) + 2 <= self.max_chars:
                        bloco_atual.append(s_limpo)
                        tamanho_atual += len(s_limpo) + 2
                    else:
                        if bloco_atual:
                            agrupados.append("; ".join(bloco_atual) + ".")
                        bloco_atual = [s_limpo]
                        tamanho_atual = len(s_limpo)
                if bloco_atual:
                    agrupados.append("; ".join(bloco_atual) + ".")

                for g_idx, grp_texto in enumerate(agrupados):
                    sub_titulo = f"{contexto_item}" if len(agrupados) == 1 else f"{contexto_item} ({g_idx+1})"
                    self.adicionar_card(assunto, subtema, sub_titulo, grp_texto, f"{origem} (sub-itens)")
            else:
                # Caso 2: Sub-itens estruturados ou extensos
                for s_idx, sub in enumerate(sub_itens):
                    sub_origem = f"{origem} (sub-item {s_idx+1})"
                    match_sub = re.match(r'^\*{1,2}([^:*]+)\*{1,2}\s*(?::|-)\s*(.*)$', sub)
                    if match_sub:
                        sub_t = match_sub.group(1).strip()
                        sub_e = match_sub.group(2).strip()
                        if len(sub_t) <= 45:
                            sub_tit = f"{contexto_item}: {sub_t}" if len(f"{contexto_item}: {sub_t}") <= 45 else sub_t
                        else:
                            sub_tit = encurtar_no_limite_de_palavra(sub_t, 45)

                        sentencas = dividir_em_sentencas(sub_e, self.max_chars)
                        grupos = agrupar_sentencas(sentencas, self.min_chars, self.max_chars)
                        for grp in grupos:
                            self.adicionar_card(assunto, subtema, sub_tit, grp, sub_origem)
                    else:
                        sentencas = dividir_em_sentencas(sub, self.max_chars)
                        grupos = agrupar_sentencas(sentencas, self.min_chars, self.max_chars)
                        sub_tit = encurtar_no_limite_de_palavra(contexto_item, 45)
                        for grp in grupos:
                            self.adicionar_card(assunto, subtema, sub_tit, grp, sub_origem)

    def _processar_paragrafo(self, paragrafo, assunto, subtema, linha_num):
        origem = f"Linha {linha_num}"

        match_inicio = re.match(r'^\*{1,2}([^:*]+)\*{1,2}\s*(?::|-)\s*(.*)$', paragrafo)
        if match_inicio:
            titulo = match_inicio.group(1).strip()
            restante = match_inicio.group(2).strip()
            titulo = encurtar_no_limite_de_palavra(titulo, 45)
            sentencas = dividir_em_sentencas(restante, self.max_chars)
            grupos = agrupar_sentencas(sentencas, self.min_chars, self.max_chars)
            for grp in grupos:
                self.adicionar_card(assunto, subtema, titulo, grp, origem)
            return

        sentencas = dividir_em_sentencas(paragrafo, self.max_chars)
        grupos = agrupar_sentencas(sentencas, self.min_chars, self.max_chars)
        titulo = encurtar_no_limite_de_palavra(subtema.split('›')[-1].strip(), 45)
        for grp in grupos:
            self.adicionar_card(assunto, subtema, titulo, grp, origem)

    def _processar_tabela(self, linhas_tabela, assunto, subtema, linha_num):
        linhas_uteis = [l.strip() for l in linhas_tabela if not re.match(r'^\|(?:\s*:?-+:?\s*\|)+$', l.strip())]
        if len(linhas_uteis) < 2:
            return

        header_line = linhas_uteis[0]
        data_lines = linhas_uteis[1:]

        headers = [limpar_markdown(c.strip()) for c in header_line.split("|")[1:-1]]
        if not headers or not data_lines:
            return

        origem = f"Tabela linha {linha_num}"
        self.elementos_complexos.append(
            f"Tabela com {len(headers)} colunas e {len(data_lines)} linhas na linha {linha_num}."
        )

        for l_idx, dl in enumerate(data_lines):
            cols_raw = dl.split("|")[1:-1]
            if len(cols_raw) != len(headers):
                continue

            entidade = limpar_markdown(cols_raw[0].strip())
            if not entidade:
                continue

            sub_origem = f"{origem} (linha {l_idx+1})"

            # Caso 1: Tabela de 2 colunas (Termo x Definição)
            if len(headers) == 2:
                titulo = f"{entidade} ({headers[1]})" if len(entidade) < 32 else entidade
                sentencas = dividir_em_sentencas(cols_raw[1], self.max_chars)
                grupos = agrupar_sentencas(sentencas, self.min_chars, self.max_chars)
                for grp in grupos:
                    self.adicionar_card(assunto, subtema, titulo, grp, sub_origem)

            # Caso 2: Tabela de 3 ou mais colunas
            else:
                for col_idx in range(1, len(cols_raw)):
                    val_raw = cols_raw[col_idx].strip()
                    if not val_raw:
                        continue
                    col_hdr = headers[col_idx]
                    titulo = f"{entidade}: {col_hdr}"

                    # Se a célula tiver quebras <br>, processa cada item individualmente
                    itens_celula = re.split(r'<(?:br|BR)\s*/?>', val_raw)
                    for item_c in itens_celula:
                        item_c_limpo = limpar_markdown(item_c).strip()
                        if not item_c_limpo:
                            continue
                        sentencas = dividir_em_sentencas(item_c_limpo, self.max_chars)
                        grupos = agrupar_sentencas(sentencas, self.min_chars, self.max_chars)
                        for grp in grupos:
                            self.adicionar_card(assunto, subtema, titulo, grp, f"{sub_origem} col {col_idx+1}")

    def _processar_bloco_codigo(self, bloco, assunto, subtema, linha_num):
        conteudo = "".join(bloco).strip()
        origem = f"Linha {linha_num}"

        # Mnemônicos com setas (───►, -->, ->)
        if "───►" in conteudo or "-->" in conteudo or "->" in conteudo:
            linhas_mne = []
            for l in conteudo.split("\n"):
                l = l.strip()
                if "───►" in l or "-->" in l or "->" in l:
                    partes = re.split(r'───►|-->|->', l)
                    if len(partes) == 2:
                        linhas_mne.append(f"{partes[0].strip()}: {partes[1].strip()}")
            if linhas_mne:
                texto_mne = "; ".join(linhas_mne) + "."
                titulo = f"Mnemônico: {subtema.split('›')[-1].strip()}"
                self.adicionar_card(assunto, subtema, titulo, texto_mne, origem)
                return

        # Diagramas de caixa ASCII 2D complexos
        caracteres_caixa = set("┌┐└┘├┤┬┴┼─│═║╔╗╚╝╠╣")
        if any(c in caracteres_caixa for c in conteudo):
            self.elementos_complexos.append(
                f"Diagrama ASCII conceitual preservado/registrado na linha {linha_num} (conteúdo não linear omitido do pop-up para manter legibilidade)."
            )
            return

        self.elementos_complexos.append(f"Bloco de código ou sintaxe preservado/omitido na linha {linha_num}.")


def carregar_configuracao(caminho_config):
    config = {
        "arquivo": "conteudo.md",
        "min_chars": 90,
        "max_chars": 220,
        "new_ratio": 70,
        "ignorar_secoes": ["Mapeamento das Fontes e Rastreabilidade do Acervo Local", "Mapeamento das Fontes"]
    }

    if not os.path.isfile(caminho_config):
        return config

    cp = configparser.ConfigParser(interpolation=None)
    try:
        cp.read(caminho_config, encoding="ascii")
        if cp.has_section("Conteudo"):
            if cp.has_option("Conteudo", "arquivo"):
                config["arquivo"] = cp.get("Conteudo", "arquivo").strip()
            if cp.has_option("Conteudo", "min_chars"):
                config["min_chars"] = cp.getint("Conteudo", "min_chars")
            if cp.has_option("Conteudo", "max_chars"):
                config["max_chars"] = cp.getint("Conteudo", "max_chars")
            if cp.has_option("Conteudo", "new_ratio"):
                config["new_ratio"] = cp.getint("Conteudo", "new_ratio")
            if cp.has_option("Conteudo", "ignorar_secoes"):
                ign_raw = cp.get("Conteudo", "ignorar_secoes")
                config["ignorar_secoes"] = [s.strip() for s in ign_raw.split(";") if s.strip()]
    except Exception as e:
        print(f"[Aviso] Falha ao ler {caminho_config} ({e}). Usando padrões.", file=sys.stderr)

    return config


def main():
    parser = argparse.ArgumentParser(description="Conversor Universal de Markdown em Microlições para Jogos.")
    parser.add_argument("--conteudo", "-c", help="Caminho do arquivo Markdown de estudo.")
    parser.add_argument("--config", default="config.ini", help="Caminho do arquivo de configuração INI.")
    parser.add_argument("--saida", "-o", default="dados/cards.tsv", help="Caminho do arquivo TSV de saída.")
    parser.add_argument("--relatorio", "-r", default="dados/relatorio_conversao.txt", help="Caminho do relatório de conversão.")
    parser.add_argument("--min-chars", type=int, help="Tamanho mínimo de caracteres do texto.")
    parser.add_argument("--max-chars", type=int, help="Tamanho máximo de caracteres do texto.")
    parser.add_argument("--ignorar-secao", action="append", help="Nome de seção para ignorar (pode ser repetido).")

    args = parser.parse_args()

    cfg = carregar_configuracao(args.config)

    caminho_conteudo = args.conteudo or cfg["arquivo"]
    min_chars = args.min_chars or cfg["min_chars"]
    max_chars = args.max_chars or cfg["max_chars"]
    ignorar_secoes = args.ignorar_secao if args.ignorar_secao else cfg["ignorar_secoes"]

    if not os.path.isabs(caminho_conteudo) and not os.path.exists(caminho_conteudo):
        script_dir = Path(__file__).resolve().parent
        candidato = script_dir / caminho_conteudo
        if candidato.exists():
            caminho_conteudo = str(candidato)

    print(f"[+] Lendo conteúdo de: {caminho_conteudo}")
    print(f"[+] Configuração: min_chars={min_chars}, max_chars={max_chars}")
    print(f"[+] Seções ignoradas: {ignorar_secoes}")

    if not os.path.exists(caminho_conteudo):
        print(f"[-] Erro fatal: arquivo '{caminho_conteudo}' não encontrado.", file=sys.stderr)
        sys.exit(1)

    p = ParserMarkdown(min_chars=min_chars, max_chars=max_chars, ignorar_secoes=ignorar_secoes)
    try:
        p.processar_arquivo(caminho_conteudo)
    except Exception as e:
        print(f"[-] Erro ao processar arquivo Markdown: {e}", file=sys.stderr)
        sys.exit(2)

    total_cards = len(p.cards)
    print(f"[+] Microlições geradas: {total_cards}")

    if total_cards == 0:
        print("[-] Nenhum card foi gerado a partir do material fornecido.", file=sys.stderr)
        sys.exit(3)

    saida_path = Path(args.saida)
    relatorio_path = Path(args.relatorio)
    saida_path.parent.mkdir(parents=True, exist_ok=True)
    relatorio_path.parent.mkdir(parents=True, exist_ok=True)

    with open(saida_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("id\tassunto\tsubtema\ttitulo\ttexto\torigem\n")
        for card in p.cards:
            f.write(card.para_tsv() + "\n")

    print(f"[+] Cards gravados com sucesso em: {saida_path}")

    comprimentos = [len(c.texto) for c in p.cards]
    media_comp = sum(comprimentos) / total_cards if total_cards else 0
    min_comp = min(comprimentos) if comprimentos else 0
    max_comp = max(comprimentos) if comprimentos else 0

    assuntos_count = {}
    for c in p.cards:
        assuntos_count[c.assunto] = assuntos_count.get(c.assunto, 0) + 1

    with open(relatorio_path, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("RELATÓRIO DE CONVERSÃO DE CONTEÚDO — MICROESTUDO OVERLAY\n")
        f.write("=" * 70 + "\n\n")
        f.write(f"Arquivo de origem:     {caminho_conteudo}\n")
        f.write(f"Total de cards:        {total_cards}\n")
        f.write(f"Faixa de caracteres:   min={min_comp}, media={media_comp:.1f}, max={max_comp}\n")
        f.write(f"Faixa configurada:     min_chars={min_chars}, max_chars={max_chars}\n\n")

        f.write("-" * 70 + "\n")
        f.write("DISTRIBUIÇÃO DE CARDS POR ASSUNTO:\n")
        f.write("-" * 70 + "\n")
        for ass, qte in sorted(assuntos_count.items(), key=lambda x: x[1], reverse=True):
            f.write(f"• {ass}: {qte} cards\n")
        f.write("\n")

        f.write("-" * 70 + "\n")
        f.write("SEÇÕES IGNORADAS CONFORME ESPECIFICAÇÃO:\n")
        f.write("-" * 70 + "\n")
        if p.secoes_ignoradas_encontradas:
            for s in p.secoes_ignoradas_encontradas:
                f.write(f"• {s}\n")
        else:
            f.write("Nenhuma seção ignorada encontrada no documento.\n")
        f.write("\n")

        f.write("-" * 70 + "\n")
        f.write("ELEMENTOS ESPECIAIS E LIMITAÇÕES REGISTRADAS:\n")
        f.write("-" * 70 + "\n")
        if p.elementos_complexos:
            for el in p.elementos_complexos:
                f.write(f"• {el}\n")
        else:
            f.write("Nenhum elemento complexo que exigisse descarte foi identificado.\n")
        f.write("\n")

        if p.avisos:
            f.write("-" * 70 + "\n")
            f.write("AVISOS DO PROCESSADOR:\n")
            f.write("-" * 70 + "\n")
            for av in p.avisos:
                f.write(f"• [Aviso] {av}\n")
            f.write("\n")

        f.write("=" * 70 + "\n")
        f.write("FIM DO RELATÓRIO\n")
        f.write("=" * 70 + "\n")

    print(f"[+] Relatório detalhado salvo em: {relatorio_path}")


if __name__ == "__main__":
    main()
