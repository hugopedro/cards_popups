#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
testar_preparacao.py - Suíte de Testes Automatizados para o Conversor de Conteúdo

Valida todos os critérios de aceitação estipulados na Seção 8.1 da especificação:
1. Documento com # / ## / ### e parágrafos extensos.
2. Listas com exemplos e definições.
3. Texto com acentos em português.
4. Outros idiomas, caracteres especiais e símbolos matemáticos.
5. Blocos de código, tabelas e diagramas.
6. Conteúdo vazio ou apenas espaços.
7. Documento com um único conceito muito curto.
8. Documento com múltiplos conceitos sem corte de ideias.
9. Sanitização contra quebra de TSV (tabs e quebras internas).
10. Tratamento estrito de dados (não execução de comandos ou HTML malicioso).
11. Seções ignoradas (exclusão de metadados como 'Mapeamento das Fontes').
12. Determinismo e estabilidade dos IDs gerados.
13. Sub-itens aninhados com negrito sem perda de asteriscos.
14. Parágrafos seguidos imediatamente por listas numeradas sem mescla indevida.
15. Quebra de sentenças longas no limite de palavras sem fatiamento arbitrário.
16. Hierarquia de subtemas com limite e sem acúmulo infinito.
17. Células de tabela com quebras <br> tratadas individualmente.
"""

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

# Adiciona o diretório pai ao sys.path para importar preparar_conteudo
script_dir = Path(__file__).resolve().parent
parent_dir = script_dir.parent
sys.path.insert(0, str(parent_dir))

import preparar_conteudo
from preparar_conteudo import ParserMarkdown, Card, limpar_markdown, gerar_id, quebrar_em_limite_de_palavra


class TestesConversorConteudo(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.caminho_temp = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _criar_arquivo_md(self, conteudo, nome="teste.md"):
        caminho = self.caminho_temp / nome
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(conteudo)
        return str(caminho)

    # 1. Documento com # / ## / ### e parágrafos extensos
    def test_01_hierarquia_titulos_e_paragrafos_extensos(self):
        md = """# Disciplina Geral
## Tema Principal A
### Subtema 1
Este é um parágrafo longo destinado a testar a divisão adequada em microlições. O objetivo do sistema de microestudo é garantir que ideias completas sejam agrupadas respeitando a pontuação da língua portuguesa sem cortar sentenças no meio. Cada card deve ter sentido autossuficiente e independente.
"""
        caminho = self._criar_arquivo_md(md)
        p = ParserMarkdown(min_chars=60, max_chars=180)
        p.processar_arquivo(caminho)

        self.assertGreaterEqual(len(p.cards), 1)
        for c in p.cards:
            self.assertEqual(c.assunto, "Tema Principal A")
            self.assertEqual(c.subtema, "Subtema 1")
            self.assertTrue(len(c.texto) >= 30)

    # 2. Listas com exemplos e definições
    def test_02_listas_com_definicoes(self):
        md = """# Conceitos Básicos
## Tópico de Regras
- **Legalidade**: O administrador público só pode agir nos limites estritos e expressos previstos pela lei formal.
- **Moralidade**: A conduta administrativa deve ser pautada pela ética, boa-fé e retidão incondicional no serviço.
"""
        caminho = self._criar_arquivo_md(md)
        p = ParserMarkdown(min_chars=40, max_chars=200)
        p.processar_arquivo(caminho)

        titulos = [c.titulo for c in p.cards]
        self.assertIn("Legalidade", titulos)
        self.assertIn("Moralidade", titulos)

    # 3. Texto com acentos em português
    def test_03_acentuacao_portugues(self):
        md = """# Ortografia
## Acentuação
- **Ação e Órgão**: Ação governamental e órgão administrativo sob a constituição e com coração dedicado ao serviço público.
"""
        caminho = self._criar_arquivo_md(md)
        p = ParserMarkdown(min_chars=30, max_chars=200)
        p.processar_arquivo(caminho)

        self.assertGreaterEqual(len(p.cards), 1)
        card = p.cards[0]
        self.assertIn("Ação", card.titulo)
        self.assertIn("constituição", card.texto)
        self.assertIn("coração", card.texto)

    # 4. Outro idioma e caracteres especiais
    def test_04_outros_idiomas_e_simbolos_matematicos(self):
        md = """# Simbologia
## Matemática e Idiomas
- **Símbolos**: A condição satisfaz x ≤ 100 → y ≥ 0, com variação diferencial α constante.
- **Japonês**: Este conceito em japonês é escrito como 日本語 e compreendido universalmente.
"""
        caminho = self._criar_arquivo_md(md)
        p = ParserMarkdown(min_chars=20, max_chars=200)
        p.processar_arquivo(caminho)

        textos_juntos = " ".join([c.texto for c in p.cards])
        self.assertIn("≤", textos_juntos)
        self.assertIn("→", textos_juntos)
        self.assertIn("α", textos_juntos)
        self.assertIn("日本語", textos_juntos)

    # 5. Blocos de código, tabelas e fórmulas
    def test_05_tabelas_e_blocos_codigo(self):
        md = """# Estruturas Complexas
## Teste de Tabela e Bloco
| Poder | Função Típica |
| :--- | :--- |
| **Executivo** | Administrar os serviços públicos e aplicar as diretrizes governamentais de forma regular. |
| **Judiciário** | Julgar com definitividade aplicando a lei aos litígios apresentados em juízo. |

```python
# Bloco de código exemplo
def soma(a, b):
    return a + b
```
"""
        caminho = self._criar_arquivo_md(md)
        p = ParserMarkdown(min_chars=30, max_chars=200)
        p.processar_arquivo(caminho)

        self.assertGreaterEqual(len(p.cards), 2)
        titulos = [c.titulo for c in p.cards]
        self.assertTrue(any("Executivo" in t for t in titulos))
        self.assertTrue(any("Judiciário" in t for t in titulos))
        # Verifica se o bloco de código gerou aviso de elemento complexo no relatório
        self.assertTrue(any("Bloco de código" in av for av in p.elementos_complexos))

    # 6. Conteúdo vazio
    def test_06_conteudo_vazio(self):
        md = "   \n\n   \t  \n"
        caminho = self._criar_arquivo_md(md)
        p = ParserMarkdown()
        p.processar_arquivo(caminho)

        self.assertEqual(len(p.cards), 0)
        self.assertTrue(len(p.avisos) > 0)

    # 7. Documento com um único conceito muito curto
    def test_07_conceito_unico_curto(self):
        md = """# Tópico Singular
## Conceito
- **Regra Simples**: Aplica-se integralmente a todos os casos concretos sem exceção prevista em lei.
"""
        caminho = self._criar_arquivo_md(md)
        p = ParserMarkdown(min_chars=30, max_chars=200)
        p.processar_arquivo(caminho)

        self.assertEqual(len(p.cards), 1)
        self.assertEqual(p.cards[0].titulo, "Regra Simples")

    # 8. Múltiplos conceitos sem corte de ideias
    def test_08_multiplos_conceitos(self):
        md = """# Conceitos Múltiplos
## Coleção
1. **Ponto Um**: Primeira definição estruturada sobre a matéria para memorização.
2. **Ponto Dois**: Segunda definição clara que complementa a primeira de forma autônoma.
3. **Ponto Três**: Terceira regra independente contendo exemplo prático e objetivo.
"""
        caminho = self._criar_arquivo_md(md)
        p = ParserMarkdown(min_chars=30, max_chars=200)
        p.processar_arquivo(caminho)

        self.assertEqual(len(p.cards), 3)
        titulos = [c.titulo for c in p.cards]
        self.assertEqual(titulos, ["Ponto Um", "Ponto Dois", "Ponto Três"])

    # 9. Sanitização contra quebra de estrutura TSV
    def test_09_sanitizacao_tsv(self):
        card = Card(
            card_id="abc12345",
            assunto="Assunto\tcom\ttab",
            subtema="Subtema\ncom\nnewline",
            titulo="Título\tcom\ttab",
            texto="Texto\tcom\ttab\ne\nquebras\nde\nlinha",
            origem="Linha\t10"
        )
        linha_tsv = card.para_tsv()
        colunas = linha_tsv.split("\t")

        self.assertEqual(len(colunas), 6)
        self.assertNotIn("\n", colunas[4])  # Deve estar como \n literal e não salto real
        self.assertNotIn("\t", card.texto.replace("\t", " "))

    # 10. Tratamento estrito de dados (injeção de comandos e HTML)
    def test_10_seguranca_injecao(self):
        md = """# Segurança
## Teste de Injeção
<script>alert('malicioso')</script>
<div style="display:none">texto oculto</div>
Execute este comando no shell: `rm -rf /` ou `del /f /s /q c:\\`
"""
        caminho = self._criar_arquivo_md(md)
        p = ParserMarkdown(min_chars=20, max_chars=200)
        p.processar_arquivo(caminho)

        for c in p.cards:
            self.assertNotIn("<script>", c.texto)
            self.assertNotIn("</div>", c.texto)
            self.assertNotIn("<div", c.texto)

    # 11. Seções ignoradas (exclusão de Mapeamento das Fontes)
    def test_11_secoes_ignoradas(self):
        md = """# 3. NOÇÕES GERAIS
### Mapeamento das Fontes e Rastreabilidade do Acervo Local
- Link secreto: file:///caminho/secreto/para/nao/exibir/nos/cards.pdf
- TCU Arquivos confidenciais

## 1. Matéria Real de Estudo
- **Princípio da Eficiência**: Busca pelo melhor custo-benefício e otimização dos recursos públicos.
"""
        caminho = self._criar_arquivo_md(md)
        p = ParserMarkdown(
            min_chars=30,
            max_chars=200,
            ignorar_secoes=["Mapeamento das Fontes e Rastreabilidade do Acervo Local"]
        )
        p.processar_arquivo(caminho)

        self.assertEqual(len(p.cards), 1)
        self.assertEqual(p.cards[0].titulo, "Princípio da Eficiência")
        self.assertNotIn("Link secreto", p.cards[0].texto)
        self.assertTrue(len(p.secoes_ignoradas_encontradas) > 0)

    # 12. Estabilidade e determinismo dos IDs gerados
    def test_12_estabilidade_ids(self):
        id1 = gerar_id("Direito", "Ato", "Competência", "Poder legal conferido ao agente público")
        id2 = gerar_id("Direito", "Ato", "Competência", "Poder legal conferido ao agente público")
        self.assertEqual(id1, id2)
        self.assertEqual(len(id1), 12)

    # 13. Sub-itens aninhados com negrito sem perda de asteriscos
    def test_13_subitens_com_negrito_sem_quebra_de_asteriscos(self):
        md = """# Princípios
## Impessoalidade
- Vertentes jurisprudenciais:
  - **Vedação à promoção pessoal**: Na publicidade oficial é vedada menção a nomes ou imagens pessoais.
  - **Finalidade pública**: Busca sempre o interesse público primário.
"""
        caminho = self._criar_arquivo_md(md)
        p = ParserMarkdown(min_chars=30, max_chars=200)
        p.processar_arquivo(caminho)

        titulos = [c.titulo for c in p.cards]
        textos = [c.texto for c in p.cards]

        self.assertTrue(any("Vedação à promoção pessoal" in t for t in titulos))
        self.assertTrue(any("Finalidade pública" in t for t in titulos))
        for t in textos:
            self.assertNotIn("**", t)

    # 14. Parágrafo imediatamente seguido de lista numerada sem fusão indevida
    def test_14_paragrafo_seguido_de_lista_numerada(self):
        md = """# Princípios Estruturantes
## Binômio
Todo o direito administrativo repousa sobre duas vigas mestras opostas e complementares:
1. **Supremacia do Interesse Público**: Confere prerrogativas ao Estado sobre o particular.
2. **Indisponibilidade do Interesse Público**: Impõe sujeições e limites intransponíveis ao gestor.
"""
        caminho = self._criar_arquivo_md(md)
        p = ParserMarkdown(min_chars=30, max_chars=200)
        p.processar_arquivo(caminho)

        titulos = [c.titulo for c in p.cards]
        self.assertTrue(any("Supremacia" in t for t in titulos))
        self.assertTrue(any("Indisponibilidade" in t for t in titulos))
        for c in p.cards:
            self.assertNotIn("contratos, desapropriação). 2.", c.texto)

    # 15. Quebra de sentença longa no limite de palavra sem fatiamento arbitrário
    def test_15_quebra_de_sentenca_sem_cortar_palavras(self):
        texto_longo = (
            "Impõe freios e limites rigorosos à atuação do administrador público, que não é proprietário "
            "da coisa pública, mas mero gestor fiduciário dos interesses coletivos da sociedade, como "
            "exigência inafastável de concurso público e obrigatoriedade de licitação administrativa."
        )
        partes = quebrar_em_limite_de_palavra(texto_longo, max_chars=120)
        self.assertGreater(len(partes), 1)
        for parte in partes:
            # Nenhuma palavra deve terminar truncada ou começar com conectivo órfão
            self.assertFalse(parte.endswith(" de li"))
            self.assertFalse(parte.endswith(" adm"))
            self.assertFalse(parte.startswith("ou "))
            self.assertFalse(parte.startswith("e "))

    # 16. Profundidade de subtemas sem concatenação infinita
    def test_16_profundidade_subtemas_nao_acumula_infinitamente(self):
        md = """# Direito Administrativo
## 1. Atos Administrativos
### 1.1 Elementos
#### Competência
A competência administrativa decorre de lei e é irrenunciável.
#### Finalidade
A finalidade deve sempre atender ao interesse público.
#### Forma
A forma escrita é a regra geral no direito público brasileiro.
"""
        caminho = self._criar_arquivo_md(md)
        p = ParserMarkdown(min_chars=20, max_chars=200)
        p.processar_arquivo(caminho)

        for c in p.cards:
            self.assertLessEqual(len(c.subtema), 65)
            self.assertLessEqual(len(c.titulo), 50)
            self.assertNotIn("Competência - Finalidade - Forma", c.subtema)

    # 17. Tabela com quebras <br> tratadas como itens individuais
    def test_17_tabela_com_br_gera_cards_individuais(self):
        md = """# Funções
## Tabela de Poderes
| Poder | Atribuições |
| :--- | :--- |
| **Executivo** | Administrar serviços públicos.<br>Editar decretos regulamentares. |
"""
        caminho = self._criar_arquivo_md(md)
        p = ParserMarkdown(min_chars=20, max_chars=200)
        p.processar_arquivo(caminho)

        textos = [c.texto for c in p.cards]
        self.assertTrue(any("Administrar serviços públicos" in t for t in textos))
        self.assertTrue(any("Editar decretos regulamentares" in t for t in textos))

    # 18. Parágrafos introdutórios e ausência de cards terminados com ':'
    def test_18_sem_cards_com_dois_pontos_finais(self):
        md = """# Direito Administrativo
## Binômio Estruturante
Todo o Direito Administrativo repousa sobre duas vigas mestras opostas e complementares:
1. **Supremacia do Interesse Público**: Confere prerrogativas ao Estado sobre o particular.
2. **Indisponibilidade do Interesse Público**: Impõe limites ao gestor público.
"""
        caminho = self._criar_arquivo_md(md)
        p = ParserMarkdown(min_chars=30, max_chars=220)
        p.processar_arquivo(caminho)

        self.assertGreater(len(p.cards), 0)
        for c in p.cards:
            self.assertFalse(c.texto.endswith(":"), f"Card {c.id} terminou com ':'!")

    # 19. Cláusulas de exemplo e balanceamento de parênteses
    def test_19_clausula_exemplo_sem_parenteses_abertos(self):
        md = """# Conceitos
## Poderes
1. **Poder de Polícia**: Restringe e condiciona o uso de bens e liberdades individuais em favor do interesse público (ex: fiscalização sanitária de restaurantes, apreensão de mercadorias adulteradas e interdição de estabelecimentos irregulares).
"""
        caminho = self._criar_arquivo_md(md)
        p = ParserMarkdown(min_chars=30, max_chars=180)
        p.processar_arquivo(caminho)

        self.assertGreater(len(p.cards), 0)
        for c in p.cards:
            self.assertEqual(c.texto.count('('), c.texto.count(')'), f"Card {c.id} possui parênteses desbalanceados: {c.texto}")
    # 20. Sub-itens introdutórios aninhados e ausência de ponto-e-vírgula residual
    def test_20_subitens_introdutorios_e_sem_ponto_e_virgula(self):
        md = """# Princípios
## Publicidade
4. **Princípio da Publicidade**:
   - Regra geral: todo ato administrativo deve ser público e transparente.
   - *Exceções constitucionais ao dever de publicidade* (art. 5º, X e XXXIII, CF):
     - Atos que envolvam a segurança da sociedade e do Estado;
     - Defesa da intimidade, vida privada, honra e imagem dos cidadãos.
"""
        caminho = self._criar_arquivo_md(md)
        p = ParserMarkdown(min_chars=30, max_chars=220)
        p.processar_arquivo(caminho)

        self.assertGreater(len(p.cards), 0)
        for c in p.cards:
            self.assertFalse(c.texto.endswith(";"), f"Card {c.id} terminou com ';'!")
            self.assertFalse(c.texto.endswith(":"), f"Card {c.id} terminou com ':'!")
            self.assertTrue(c.texto.endswith(('.', '!', '?')), f"Card {c.id} não possui pontuação terminal!")

        # Verifica se as exceções foram agrupadas com contexto
        textos = [c.texto for c in p.cards]
        excecao_encontrada = any("segurança da sociedade e do Estado" in t and "Exceções constitucionais" in t for t in textos)
        self.assertTrue(excecao_encontrada, "Exceções constitucionais não foram devidamente sintetizadas com seu cabeçalho!")

    # 21. Preservação íntegra de orações jurídicas com ressalvas (salvo...)
    def test_21_oracao_com_ressalva_mantida_integra(self):
        md = """# Jurisprudência
## Súmula Vinculante 13
> **Exceção Consolidada no STF**: A vedação da SV 13 não se aplica, em regra, à nomeação para cargos políticos (Ministro de Estado, Secretário Estadual ou Municipal), salvo nos casos de comprovada fraude à lei ou evidente falta de qualificação técnica para a função.
"""
        caminho = self._criar_arquivo_md(md)
        p = ParserMarkdown(min_chars=60, max_chars=220)
        p.processar_arquivo(caminho)

        self.assertEqual(len(p.cards), 1, "A oração com ressalva deveria ter sido mantida íntegra em um único card!")
        self.assertIn("salvo nos casos de comprovada fraude à lei", p.cards[0].texto)
        self.assertTrue(p.cards[0].texto.endswith("."))


    # 22. Cláusulas subordinadas em listas sem negrito preservam premissa introdutória
    def test_22_oracoes_subordinadas_em_listas_com_premissa(self):
        md = """# Direito Administrativo
## Atos Administrativos
#### Dever de Motivação dos Atos Administrativos (Art. 50)
Os atos administrativos deverão ser motivados, com indicação expressa dos fatos e dos fundamentos jurídicos, quando:
1. Neguem, limitem ou afetem direitos ou interesses;
2. Imponham ou agravem deveres, encargos ou sanções;
3. Decidam recursos administrativos;
4. Decorram de reexame de ofício;
5. Deixem de aplicar jurisprudência firmada sobre a questão;
6. Veiculem decisão de revogação, anulação ou suspensão de ato administrativo.
- *Motivação Aliunde*: É válida a motivação que consistir na expressa concordância com fundamentos de pareceres anteriores.
"""
        caminho = self._criar_arquivo_md(md)
        p = ParserMarkdown(min_chars=50, max_chars=260)
        p.processar_arquivo(caminho)

        textos = [c.texto for c in p.cards]
        # Nenhum card pode ser apenas a cláusula subordinada órfã
        for t in textos:
            self.assertNotEqual(t.strip(), "Imponham ou agravem deveres, encargos ou sanções.")
            self.assertNotEqual(t.strip(), "Neguem, limitem ou afetem direitos ou interesses.")

        # O item 2 deve estar acompanhado da oração principal (quando:)
        card_com_imponham = [t for t in textos if "Imponham ou agravem deveres" in t]
        self.assertTrue(len(card_com_imponham) > 0, "O item 'Imponham...' deve existir nos cards!")
        self.assertIn("deverão ser motivados", card_com_imponham[0])
        self.assertIn("quando:", card_com_imponham[0])

        # O item de Motivação Aliunde deve ser processado independentemente
        card_aliunde = [t for t in textos if "Motivação Aliunde" in t or "concordância com fundamentos" in t]
        self.assertTrue(len(card_aliunde) > 0, "O item 'Motivação Aliunde' deve ter seu próprio card!")

        # Também deve funcionar quando houver linha em branco entre a premissa e a lista
        md_com_linha_branca = """# Direito Administrativo
## Atos
#### Dever de Motivação
Os atos administrativos deverão ser motivados, quando:

1. Neguem direitos;
2. Imponham sanções.
"""
        caminho2 = self._criar_arquivo_md(md_com_linha_branca, "teste_branca.md")
        p2 = ParserMarkdown(min_chars=30, max_chars=200)
        p2.processar_arquivo(caminho2)
        textos2 = [c.texto for c in p2.cards]
        self.assertTrue(any("deverão ser motivados, quando:" in t and "Imponham sanções" in t for t in textos2))

    # 23. Sub-itens sob premissa introdutória em lista preservam contexto e IDs únicos sem bullets órfãos
    def test_23_itens_de_lista_com_premissa_e_subitens_sem_perda_de_contexto(self):
        md = """# Proteção de Dados
## Sanções Administrativas
- **Sanções Aplicadas pela Autoridade (Art. 52)**:
  1. Advertência, com fixação de prazo para medidas corretivas;
  2. Multa simples de até 2% do faturamento da pessoa jurídica de direito privado, limitada a 50 milhões de reais;
  3. Bloqueio dos dados pessoais objeto da infração.
- Não sendo possível resposta imediata, o órgão tem 20 dias para:
  1. Fornecer a informação requerida;
  2. Comunicar que não possui a informação e indicar o órgão competente para fornecê-la de forma tempestiva.
"""
        caminho = self._criar_arquivo_md(md, "teste_subitens.md")
        p = ParserMarkdown(min_chars=30, max_chars=220)
        p.processar_arquivo(caminho)

        self.assertGreater(len(p.cards), 0)
        ids = [c.id for c in p.cards]
        self.assertEqual(len(ids), len(set(ids)), "Todos os cards gerados devem ter IDs únicos sem colisão!")

        for c in p.cards:
            self.assertFalse(c.texto.startswith(("- ", "* ", "+ ")), f"Card {c.id} possui bullet inicial órfão: {c.texto}")
            if "Multa simples" in c.texto:
                self.assertIn("Sanções Aplicadas pela Autoridade", c.texto, "Card de sanção não deve perder a premissa introdutória!")
            if "Comunicar que não possui" in c.texto:
                self.assertIn("órgão tem 20 dias", c.texto, "Card de prazo não deve perder a premissa introdutória!")

    # 24. Cláusulas coordenadas/subordinadas ('mas sim', 'bem como', 'desde que') não viram fragmentos órfãos
    def test_24_oracoes_com_conectivos_subordinados_nao_geram_fragmentos_orfaos(self):
        md = """# Direito Administrativo
## Poderes
#### 1. Poderes Administrativos e Finalidades
Os poderes administrativos não são privilégios, mas sim verdadeiros poderes-deveres irrenunciáveis para que o Estado atinja o bem comum.
- **Súmula Vinculante 5**: A presença de advogado é facultativa no PAD, ressalvada a obrigatoriedade de defensor dativo se o acusado for revel.
- **Licitação Deserta**: Permite contratação direta por dispensa, desde que mantidas todas as condições pré-fixadas no edital originário.
- **Setor Obrigatório**: Aplica-se a órgãos da administração direta, bem como a autarquias e fundações públicas.
"""
        caminho = self._criar_arquivo_md(md, "teste_subordinadas.md")
        p = ParserMarkdown(min_chars=30, max_chars=220)
        p.processar_arquivo(caminho)

        self.assertGreater(len(p.cards), 0)
        for c in p.cards:
            self.assertFalse(re.search(r'^(?:mas sim|bem como|ressalvada|desde que)\b', c.texto, flags=re.IGNORECASE),
                             f"Card {c.id} gerou fragmento subordinado órfão: '{c.texto}'")
            self.assertFalse(c.texto.startswith(("1. ", "1) ")), f"Card {c.id} iniciou com numeração residual: '{c.texto}'")
            self.assertFalse(c.titulo.startswith(("1. ", "1) ")), f"Título {c.id} iniciou com numeração residual: '{c.titulo}'")

        textos = [c.texto for c in p.cards]
        self.assertTrue(any("não são privilégios, mas sim" in t for t in textos), "A oração com 'mas sim' não foi preservada íntegra!")
        self.assertTrue(any("facultativa no PAD, ressalvada" in t for t in textos), "A oração com 'ressalvada' não foi preservada íntegra!")


if __name__ == "__main__":
    unittest.main()


