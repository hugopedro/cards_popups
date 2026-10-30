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
    chave = f"{assunto}|{subtema}|{titulo}|{texto}".encode('utf-8', errors='ignore')
    return hashlib.sha256(chave).hexdigest()[:12]


def quebrar_em_limite_de_palavra(texto, max_chars):
    """
    Quebra sentenças longas no limite de palavra ou oração mais próximo de max_chars.
    NUNCA divide palavras ao meio, evita cortar dentro de parênteses e trata cláusulas
    de exemplo sem deixar pontuações ou parênteses soltos.
    """
    texto = texto.strip()
    if len(texto) <= max_chars:
        return [texto]

    # Se há cláusula de exemplos como (ex: ...) que causa estouro, tenta quebrar antes dela
    match_ex = re.search(r'\s*\((?:ex|ex\.|exemplo|exemplos)\s*:\s*([^)]+)\)', texto, flags=re.IGNORECASE)
    if match_ex:
        pos_inicio_ex = match_ex.start()
        if 40 <= pos_inicio_ex <= max_chars:
            parte1 = texto[:pos_inicio_ex].strip().rstrip(' ,;:-–—(')
            if not parte1.endswith(('.', '!', '?')):
                parte1 += '.'
            conteudo_ex = match_ex.group(1).strip().rstrip('.) ')
            parte2 = f"Exemplos: {conteudo_ex}."
            return [parte1, parte2]

    padroes_subordinados = (
        r'^\s*(?:mas sim|bem como|assim como|ressalvada?s?|salvo|exceto|'
        r'desde que|sob pena de|a menos que|salvo se|n[ãa]o obstante)\b'
    )

    # 1. Tenta quebrar por pontuação de oração (;, —, –, ,) garantindo que NÃO esteja dentro de parênteses abertos
    # NOTA: ':' foi removido de propósito para evitar deixar 'ex:' ou termos suspensos
    pontuacoes = ['; ', ' — ', ' – ', ', ']
    melhor_pos = -1

    for pont in pontuacoes:
        idx = max_chars
        while idx > 45:
            pos = texto.rfind(pont, 0, idx)
            if pos < 45:
                break
            # Verifica balanceamento de parênteses
            abertos = texto[:pos].count('(') - texto[:pos].count(')')
            if abertos <= 0:
                # Se for vírgula seguida de conectivo que gera oração subordinada dependente, não quebra aqui
                if pont.strip() == ',':
                    resto = texto[pos + len(pont):]
                    if re.search(padroes_subordinados, resto, flags=re.IGNORECASE):
                        idx = pos
                        continue
                melhor_pos = pos + len(pont.rstrip())
                break
            idx = pos
        if melhor_pos != -1:
            break

    # 2. Se não houver pontuação intermediária fora de parênteses, quebra no último espaço fora de parênteses
    if melhor_pos == -1:
        idx = max_chars
        while idx > 40:
            pos = texto.rfind(' ', 0, idx)
            if pos < 40:
                break
            abertos = texto[:pos].count('(') - texto[:pos].count(')')
            if abertos <= 0:
                melhor_pos = pos
                break
            idx = pos

    # 3. Se ainda assim não encontrou, busca último espaço antes de max_chars
    if melhor_pos == -1:
        pos = texto.rfind(' ', 0, max_chars)
        if pos >= 40:
            melhor_pos = pos

    # 4. Fallback: procura o próximo espaço logo após max_chars
    if melhor_pos == -1:
        pos = texto.find(' ', max_chars)
        if pos != -1:
            melhor_pos = pos
        else:
            return [texto]

    parte1 = texto[:melhor_pos].strip().rstrip(' ,;:-–—(')
    parte2 = texto[melhor_pos:].strip().lstrip(' ,;:-–—)')

    parte2_limpa = re.sub(r'^(?:e|ou|de|que|com|para)\s+', '', parte2, flags=re.IGNORECASE).lstrip(',;:—– ')
    if re.search(padroes_subordinados, parte2_limpa, flags=re.IGNORECASE):
        return [texto]

    # Balancear parênteses
    if parte1.count('(') > parte1.count(')'):
        parte1 += ')'
    if parte2.count(')') > parte2.count('('):
        parte2 = parte2.rstrip(')')

    # Garantir que parte1 termine com ponto final se não tiver pontuação terminal
    if not parte1.endswith(('.', '!', '?')):
        parte1 += '.'

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
    Permite uma margem de tolerância para manter orações completas sem fatiamento artificial.
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
        p = re.sub(r'^[-*+>]\s+', '', p).strip()
        if p:
            p_limpo = limpar_markdown(p)
            limite = max(max_chars + 38, 305) if max_chars >= 180 else max_chars + 38
            if len(p_limpo) > limite:
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

        # NUNCA emitir card cujo texto termine com dois-pontos isolados (conteúdo cortado)
        if texto_limpo.endswith(":"):
            return

        # Limpar marcador de bullet inicial residual (- , * , + , > , 1. , 1) ) e artefatos de dois-pontos ou ponto-e-vírgula com hífen
        texto_limpo = re.sub(r'^(?:[-*+>]|\d+[\.\)]|[a-zA-Z][\.\)])\s+', '', texto_limpo).strip()
        texto_limpo = re.sub(r'[:;]\s*[-*+>]\s+', lambda m: m.group(0)[0] + ' ', texto_limpo)
        if not texto_limpo or len(texto_limpo) < 30:
            return

        # Balanceamento preventivo de parênteses no corpo do card
        if texto_limpo.count('(') > texto_limpo.count(')'):
            texto_limpo += ')'
        # Garantir início com letra maiúscula
        if texto_limpo and texto_limpo[0].islower():
            texto_limpo = texto_limpo[0].upper() + texto_limpo[1:]

        # Garantir pontuação final adequada (sem ponto-e-vírgula ou vírgula no fim)
        texto_limpo = texto_limpo.rstrip(' ,;:-–—')
        if not texto_limpo.endswith(('.', '!', '?')):
            texto_limpo += '.'

        # Ajuste de tamanho de assunto, subtema e título para evitar estouro no overlay
        assunto_fmt = encurtar_no_limite_de_palavra(limpar_markdown(assunto), 65)

        subtema_fmt = limpar_markdown(subtema)
        subtema_fmt = re.sub(r'^\d+[\.\)]\s+', '', subtema_fmt)
        if len(subtema_fmt) > 65:
            partes_sub = [p.strip() for p in subtema_fmt.split("›") if p.strip()]
            subtema_fmt = partes_sub[-1] if partes_sub else subtema_fmt
            subtema_fmt = encurtar_no_limite_de_palavra(subtema_fmt, 65)

        titulo_fmt = re.sub(r'^\d+[\.\)]\s+', '', limpar_markdown(titulo))
        titulo_fmt = encurtar_no_limite_de_palavra(titulo_fmt, 48)

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
                match_tem_negrito = re.match(r'^\*{1,2}([^:*]+)\*{1,2}(?:\s*[\(\[]([^:\)\]]+)[\)\]])?\s*(?::|-)\s*(.*)$', conteudo_item)

                # Se for item simples sem negrito e não terminal com ':', agrupa com os consecutivos se houver
                if not match_tem_negrito and not conteudo_item.endswith(":"):
                    itens_consecutivos = [conteudo_item]
                    k = i + 1
                    while k < total_linhas:
                        l_k = linhas[k].strip()
                        if not l_k:
                            if k + 1 < total_linhas and re.match(r'^(?:[-*+]|\d+[\.\)]|[a-zA-Z][\.\)])\s+', linhas[k+1].strip()):
                                k += 1
                                continue
                            break
                        if linhas[k].startswith("  ") or linhas[k].startswith("	"):
                            if itens_consecutivos:
                                itens_consecutivos[-1] += " " + l_k
                            k += 1
                            continue
                        m_k = re.match(r'^(?:[-*+]|\d+[\.\)]|[a-zA-Z][\.\)])\s+(.*)$', l_k)
                        if m_k:
                            texto_k = m_k.group(1).strip()
                            if re.match(r'^\*{1,2}[^:*]+\*{1,2}\s*(?::|-)', texto_k) or texto_k.endswith(":"):
                                break
                            itens_consecutivos.append(texto_k)
                            k += 1
                        else:
                            break

                    if len(itens_consecutivos) >= 2:
                        subtema_limpo = limpar_markdown(subtema_atual.split('›')[-1].strip())
                        subtema_limpo = re.sub(r'^\d+[\.\)]\s+', '', subtema_limpo)
                        tit_sint = encurtar_no_limite_de_palavra(subtema_limpo, 45)

                        itens_limpos = [limpar_markdown(it).rstrip(';.') for it in itens_consecutivos if it]
                        bloco_itens = []
                        bloco_atual = []
                        tam_atual = len(subtema_limpo) + 2

                        for idx_it, it_txt in enumerate(itens_limpos):
                            it_txt = re.sub(r'^(?:[-*+]|\d+[\.\)]|[a-zA-Z][\.\)])\s+', '', it_txt).strip()
                            item_fmt = f"{idx_it+1}) {it_txt}"
                            if tam_atual + len(item_fmt) + 2 <= self.max_chars + 35:
                                bloco_atual.append(item_fmt)
                                tam_atual += len(item_fmt) + 2
                            else:
                                if bloco_atual:
                                    bloco_itens.append(bloco_atual)
                                bloco_atual = [item_fmt]
                                tam_atual = len(subtema_limpo) + len(item_fmt) + 4
                        if bloco_atual:
                            bloco_itens.append(bloco_atual)

                        for b_idx, blk in enumerate(bloco_itens):
                            t_card = f"{subtema_limpo}: {'; '.join(blk)}."
                            sub_tit = tit_sint if len(bloco_itens) == 1 else f"{tit_sint} ({b_idx+1})"
                            self.adicionar_card(assunto_atual, subtema_atual, sub_tit, t_card, f"Linha {num_linha}")

                        i = k
                        continue

                sub_itens = []
                j = i + 1
                while j < total_linhas:
                    linha_prox = linhas[j]
                    linha_prox_strip = linha_prox.strip()

                    if not linha_prox_strip:
                        # Se for linha em branco, checa se a próxima é um sub-item indentado
                        if j + 1 < total_linhas:
                            prox_apos = linhas[j + 1]
                            if prox_apos.startswith("  ") or prox_apos.startswith("	"):
                                j += 1
                                continue
                        break

                    # Sub-itens indentados (2+ espaços ou tab)
                    if linha_prox.startswith("  ") or linha_prox.startswith("	"):
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

            # Checar se este parágrafo é uma introdução terminada em ':' seguida por uma lista
            idx_lista = j
            while idx_lista < total_linhas and not linhas[idx_lista].strip():
                idx_lista += 1

            if paragrafo.endswith(":") and idx_lista < total_linhas and re.match(r'^(?:[-*+]|\d+[\.\)]|[a-zA-Z][\.\)])\s+', linhas[idx_lista].strip()):
                k = idx_lista
                primeira_l = linhas[idx_lista].strip()
                eh_numerada = bool(re.match(r'^\d+[\.\)]', primeira_l))

                itens_lista_intro = []
                while k < total_linhas:
                    l_k = linhas[k].strip()
                    if not l_k:
                        k_cand = k + 1
                        while k_cand < total_linhas and not linhas[k_cand].strip():
                            k_cand += 1
                        if k_cand < total_linhas:
                            prox_l = linhas[k_cand]
                            prox_l_strip = prox_l.strip()
                            if prox_l.startswith("  ") or prox_l.startswith("\t"):
                                k = k_cand
                                continue
                            if eh_numerada and re.match(r'^\d+[\.\)]\s+', prox_l_strip):
                                k = k_cand
                                continue
                            if not eh_numerada and re.match(r'^[-*+]\s+', prox_l_strip) and not re.match(r'^[-*+]\s+\*{1,2}[^:*]+\*{1,2}\s*:', prox_l_strip):
                                k = k_cand
                                continue
                        break

                    if linhas[k].startswith("  ") or linhas[k].startswith("	"):
                        if itens_lista_intro:
                            l_k_limpo = re.sub(r'^(?:[-*+>]|\d+[\.\)]|[a-zA-Z][\.\)])\s+', '', l_k)
                            itens_lista_intro[-1] += " " + l_k_limpo
                        k += 1
                        continue

                    if eh_numerada and not re.match(r'^\d+[\.\)]\s+', l_k):
                        break
                    if not eh_numerada and re.match(r'^\d+[\.\)]\s+', l_k):
                        break
                    if l_k.startswith("#") or l_k.startswith(">") or l_k.startswith("|") or l_k.startswith("```"):
                        break

                    m_item = re.match(r'^(?:[-*+]|\d+[\.\)]|[a-zA-Z][\.\)])\s+(.*)$', l_k)
                    if m_item:
                        itens_lista_intro.append(m_item.group(1).strip())
                    else:
                        break
                    k += 1

                paragrafo_limpo = limpar_markdown(paragrafo).rstrip(':')
                tit_sint = encurtar_no_limite_de_palavra(re.sub(r'^\d+[\.\)]\s+', '', subtema_atual.split('›')[-1].strip()), 45)

                itens_com_def_longa = []
                for it in itens_lista_intro:
                    m_def = re.match(r'^\*{1,2}([^:*]+)\*{1,2}(?:\s*[\(\[]([^:\)\]]+)[\)\]])?\s*(?::|-)\s*(.+)$', it)
                    if m_def and len(m_def.group(3).strip()) >= 30:
                        itens_com_def_longa.append((m_def.group(1).strip(), m_def.group(3).strip(), it))

                if len(itens_com_def_longa) >= 2 and len(itens_com_def_longa) >= len(itens_lista_intro) // 2:
                    termos = [limpar_markdown(t[0]) for t in itens_com_def_longa]
                    sintese = f"{paragrafo_limpo}: " + "; ".join([f"{idx+1}) {t}" for idx, t in enumerate(termos)]) + "."
                    if len(sintese) <= self.max_chars + 40:
                        self.adicionar_card(assunto_atual, subtema_atual, tit_sint, sintese, f"Linha {num_linha}")

                    for idx_item, it_texto in enumerate(itens_lista_intro):
                        self._processar_item_lista(it_texto, [], assunto_atual, subtema_atual, num_linha + idx_item + 1)

                    i = k
                    continue

                itens_limpos = [limpar_markdown(it).rstrip(';.') for it in itens_lista_intro if it]
                bloco_itens = []
                bloco_atual = []
                tam_atual = len(paragrafo_limpo) + 2

                for idx_it, it_txt in enumerate(itens_limpos):
                    it_txt = re.sub(r'^(?:[-*+]|\d+[\.\)]|[a-zA-Z][\.\)])\s+', '', it_txt).strip()
                    item_fmt = f"{idx_it+1}) {it_txt}"
                    if tam_atual + len(item_fmt) + 2 <= self.max_chars + 35:
                        bloco_atual.append(item_fmt)
                        tam_atual += len(item_fmt) + 2
                    else:
                        if bloco_atual:
                            bloco_itens.append(bloco_atual)
                        bloco_atual = [item_fmt]
                        tam_atual = len(paragrafo_limpo) + len(item_fmt) + 4
                if bloco_atual:
                    bloco_itens.append(bloco_atual)

                for b_idx, blk in enumerate(bloco_itens):
                    t_card = f"{paragrafo_limpo}: {'; '.join(blk)}."
                    sub_tit = tit_sint if len(bloco_itens) == 1 else f"{tit_sint} ({b_idx+1})"
                    self.adicionar_card(assunto_atual, subtema_atual, sub_tit, t_card, f"Linha {num_linha}")

                i = k
                continue

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

        # Verifica se o item possui formato **Termo** [qualificador]: Explicação
        match_termo = re.match(r'^\*{1,2}([^:*]+)\*{1,2}(?:\s*[\(\[]([^:\)\]]+)[\)\]])?\s*(?::|-)\s*(.*)$', item_texto)
        if match_termo:
            termo = match_termo.group(1).strip()
            qualificador = match_termo.group(2)
            explicacao = match_termo.group(3).strip()

            titulo_base = termo
            if qualificador:
                qual_limpo = limpar_markdown(qualificador).strip()
                if len(f"{termo} ({qual_limpo})") <= 45:
                    titulo_base = f"{termo} ({qual_limpo})"
            titulo = encurtar_no_limite_de_palavra(titulo_base, 45)

            if explicacao and not explicacao.endswith(':'):
                sentencas = dividir_em_sentencas(explicacao, self.max_chars)
                grupos = agrupar_sentencas(sentencas, self.min_chars, self.max_chars)
                for grp in grupos:
                    self.adicionar_card(assunto, subtema, titulo, grp, origem)
            contexto_item = termo
        else:
            termo = None
            explicacao = ""
            # Item sem termo em negrito destacado
            if item_texto.endswith(":") and sub_itens:
                contexto_item = limpar_markdown(item_texto.rstrip(":"))
            else:
                sentencas = dividir_em_sentencas(item_texto, self.max_chars)
                grupos = agrupar_sentencas(sentencas, self.min_chars, self.max_chars)
                subtema_limpo = limpar_markdown(subtema.split('›')[-1].strip())
                titulo = encurtar_no_limite_de_palavra(subtema_limpo, 45)
                for grp in grupos:
                    texto_final = grp
                    if not grp.lower().startswith(subtema_limpo.lower()[:8]):
                        texto_final = f"{subtema_limpo}: {grp}"
                    self.adicionar_card(assunto, subtema, titulo, texto_final, origem)
                contexto_item = titulo

        # Processar sub-itens
        if sub_itens:
            item_limpo = limpar_markdown(item_texto).strip()
            item_eh_intro = (
                item_texto.strip().endswith(":") or
                item_limpo.endswith(":") or
                (match_termo and explicacao and explicacao.strip().endswith(":"))
            )

            if match_termo and explicacao:
                premissa_pai = f"{termo}: {explicacao}".rstrip(':').strip()
            elif match_termo:
                premissa_pai = termo.rstrip(':').strip()
            else:
                premissa_pai = item_limpo.rstrip(':').strip()

            tem_sub_intro_aninhada = any(s.strip().endswith(":") for s in sub_itens)

            # Se o item pai é introdutório e seus sub-itens são uma lista direta sem sub-intros aninhadas
            if item_eh_intro and not tem_sub_intro_aninhada:
                itens_com_def_longa = []
                for sub in sub_itens:
                    m_def = re.match(r'^\*{1,2}([^:*]+)\*{1,2}(?:\s*[\(\[]([^:\)\]]+)[\)\]])?\s*(?::|-)\s*(.+)$', sub.strip())
                    if m_def and len(m_def.group(3).strip()) >= 30:
                        itens_com_def_longa.append((m_def.group(1).strip(), m_def.group(3).strip(), sub))

                if len(itens_com_def_longa) >= 2 and len(itens_com_def_longa) >= len(sub_itens) // 2:
                    termos = [limpar_markdown(t[0]) for t in itens_com_def_longa]
                    tit_sint = encurtar_no_limite_de_palavra(premissa_pai, 45)
                    sintese = f"{premissa_pai}: " + "; ".join([f"{idx+1}) {t}" for idx, t in enumerate(termos)]) + "."
                    if len(sintese) <= self.max_chars + 40:
                        self.adicionar_card(assunto, subtema, tit_sint, sintese, origem)

                    for s_idx, sub in enumerate(sub_itens):
                        self._processar_item_lista(sub, [], assunto, subtema, linha_num + s_idx + 1)
                    return
                else:
                    filhos_limpos = []
                    for f in sub_itens:
                        f_l = limpar_markdown(f).rstrip(';.')
                        f_l = re.sub(r'^(?:[-*+]|\d+[\.\)]|[a-zA-Z][\.\)])\s+', '', f_l).strip()
                        if f_l:
                            filhos_limpos.append(f_l)

                    if filhos_limpos:
                        tit_sint = encurtar_no_limite_de_palavra(premissa_pai, 45)
                        bloco_atual = []
                        tam_atual = len(premissa_pai) + 2
                        lotes = []
                        for idx_f, f_item in enumerate(filhos_limpos):
                            item_fmt = f"{idx_f+1}) {f_item}"
                            if tam_atual + len(item_fmt) + 2 <= self.max_chars + 35:
                                bloco_atual.append(item_fmt)
                                tam_atual += len(item_fmt) + 2
                            else:
                                if bloco_atual:
                                    lotes.append(bloco_atual)
                                bloco_atual = [item_fmt]
                                tam_atual = len(premissa_pai) + len(item_fmt) + 4
                        if bloco_atual:
                            lotes.append(bloco_atual)

                        for l_idx, lote in enumerate(lotes):
                            t_lote = f"{premissa_pai}: {'; '.join(lote)}."
                            lote_tit = tit_sint if len(lotes) == 1 else f"{tit_sint} ({l_idx+1})"
                            self.adicionar_card(assunto, subtema, lote_tit, t_lote, origem)
                    return

            # Agrupar sub-itens em blocos lógicos reconhecendo itens introdutórios (terminados com ':')
            blocos_sub = []
            idx = 0
            while idx < len(sub_itens):
                item_s = sub_itens[idx].strip()
                if item_s.endswith(":") and idx + 1 < len(sub_itens):
                    intro_item = item_s
                    filhos = []
                    idx += 1
                    while idx < len(sub_itens):
                        prox_cand = sub_itens[idx].strip()
                        if prox_cand.endswith(":"):
                            break
                        filhos.append(prox_cand)
                        idx += 1
                    blocos_sub.append(("intro_com_filhos", intro_item, filhos))
                else:
                    blocos_sub.append(("item_simples", item_s, []))
                    idx += 1

            for b_idx, (tipo, cabecalho, filhos) in enumerate(blocos_sub):
                sub_origem = f"{origem} (sub-item {b_idx+1})"
                if tipo == "intro_com_filhos":
                    intro_limpo = limpar_markdown(cabecalho).rstrip(':')
                    match_tit = re.match(r'^\*{1,2}([^:*]+)\*{1,2}', cabecalho)
                    if match_tit:
                        t_extraido = limpar_markdown(match_tit.group(1)).strip()
                        if len(f"{contexto_item}: {t_extraido}") <= 45:
                            sub_tit = f"{contexto_item}: {t_extraido}"
                        else:
                            sub_tit = encurtar_no_limite_de_palavra(t_extraido, 45)
                    else:
                        sub_tit = encurtar_no_limite_de_palavra(contexto_item, 45)

                    filhos_limpos = []
                    for f in filhos:
                        f_l = limpar_markdown(f).rstrip(';.')
                        f_l = re.sub(r'^(?:[-*+]|\d+[\.\)]|[a-zA-Z][\.\)])\s+', '', f_l).strip()
                        if f_l:
                            filhos_limpos.append(f_l)

                    if not filhos_limpos:
                        continue

                    sintese_itens = [f"{i+1}) {f_item}" for i, f_item in enumerate(filhos_limpos)]
                    texto_sintese = f"{intro_limpo}: {'; '.join(sintese_itens)}."

                    if len(texto_sintese) <= self.max_chars + 40:
                        self.adicionar_card(assunto, subtema, sub_tit, texto_sintese, sub_origem)
                    else:
                        bloco_atual = []
                        tam_atual = len(intro_limpo) + 2
                        lotes = []
                        for idx_f, f_item in enumerate(filhos_limpos):
                            item_fmt = f"{idx_f+1}) {f_item}"
                            if tam_atual + len(item_fmt) + 2 <= self.max_chars + 35:
                                bloco_atual.append(item_fmt)
                                tam_atual += len(item_fmt) + 2
                            else:
                                if bloco_atual:
                                    lotes.append(bloco_atual)
                                bloco_atual = [item_fmt]
                                tam_atual = len(intro_limpo) + len(item_fmt) + 4
                        if bloco_atual:
                            lotes.append(bloco_atual)

                        for l_idx, lote in enumerate(lotes):
                            t_lote = f"{intro_limpo}: {'; '.join(lote)}."
                            lote_tit = sub_tit if len(lotes) == 1 else f"{sub_tit} ({l_idx+1})"
                            self.adicionar_card(assunto, subtema, lote_tit, t_lote, sub_origem)
                else:
                    # Item simples
                    sub = cabecalho
                    match_sub = re.match(r'^\*{1,2}([^:*]+)\*{1,2}(?:\s*[\(\[]([^:\)\]]+)[\)\]])?\s*(?::|-)\s*(.*)$', sub)
                    if match_sub:
                        sub_t = match_sub.group(1).strip()
                        sub_q = match_sub.group(2)
                        sub_e = match_sub.group(3).strip()
                        if sub_q:
                            sub_q_l = limpar_markdown(sub_q).strip()
                            if len(f"{sub_t} ({sub_q_l})") <= 35:
                                sub_t = f"{sub_t} ({sub_q_l})"
                        if len(sub_t) <= 45:
                            sub_tit = f"{contexto_item}: {sub_t}" if len(f"{contexto_item}: {sub_t}") <= 45 else sub_t
                        else:
                            sub_tit = encurtar_no_limite_de_palavra(sub_t, 45)

                        sentencas = dividir_em_sentencas(sub_e, self.max_chars)
                        grupos = agrupar_sentencas(sentencas, self.min_chars, self.max_chars)
                        for grp in grupos:
                            self.adicionar_card(assunto, subtema, sub_tit, grp, sub_origem)
                    else:
                        sub_limpo = re.sub(r'^(?:[-*+>]|\d+[\.\)]|[a-zA-Z][\.\)])\s+', '', sub).strip()
                        sentencas = dividir_em_sentencas(sub_limpo, self.max_chars)
                        grupos = agrupar_sentencas(sentencas, self.min_chars, self.max_chars)
                        sub_tit = encurtar_no_limite_de_palavra(contexto_item, 45)
                        for grp in grupos:
                            texto_final = grp
                            if not grp.lower().startswith(contexto_item.lower()[:8]):
                                texto_final = f"{contexto_item}: {grp}"
                            self.adicionar_card(assunto, subtema, sub_tit, texto_final, sub_origem)

    def _processar_paragrafo(self, paragrafo, assunto, subtema, linha_num):
        origem = f"Linha {linha_num}"

        match_inicio = re.match(r'^\*{1,2}([^:*]+)\*{1,2}(?:\s*[\(\[]([^:\)\]]+)[\)\]])?\s*(?::|-)\s*(.*)$', paragrafo)
        if match_inicio:
            titulo_raw = match_inicio.group(1).strip()
            qual_raw = match_inicio.group(2)
            restante = match_inicio.group(3).strip()
            if qual_raw:
                q_limpo = limpar_markdown(qual_raw).strip()
                if len(f"{titulo_raw} ({q_limpo})") <= 45:
                    titulo_raw = f"{titulo_raw} ({q_limpo})"
            titulo = encurtar_no_limite_de_palavra(titulo_raw, 45)
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
                itens_celula = re.split(r'<(?:br|BR)\s*/?>', cols_raw[1])
                for item_c in itens_celula:
                    item_c_limpo = item_c.strip()
                    if not item_c_limpo:
                        continue
                    sentencas = dividir_em_sentencas(item_c_limpo, self.max_chars)
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
