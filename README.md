# MicroEstudo Overlay — Microlições em Segundo Plano durante Jogos (Windows 11 e Linux)

Sistema universal e não invasivo de microaprendizagem sobreposto a jogos no **Windows 11** e **Linux** (Wayland e X11). O aplicativo extrai conceitos, tabelas, definições e mnemônicos de **qualquer arquivo Markdown de estudo** e os projeta discretamente na tela em janelas translúcidas com tecnologia *click-through* (cliques do mouse e comandos do teclado atravessam a janela sem tirar o foco da partida).

---

## 1. Estrutura do Projeto

```text
microestudo-overlay/
├── README.md                  # Manual completo de instalação, uso e diagnóstico
├── config.ini                 # Configurações do usuário (arquivo estritamente ASCII)
├── conteudo.md               # Conteúdo real de estudo (Direito Administrativo - 888 cards)
├── conteudo_modelo.md        # Modelo neutro demonstrativo (Astronomia)
├── iniciar.bat                # Inicializador automático para Windows (AutoHotkey)
├── iniciar.sh                 # Inicializador e controlador para Linux (PySide6)
├── overlay.ahk                # Interface gráfica sobreposta para Windows (AutoHotkey v2)
├── overlay_linux.py           # Interface gráfica sobreposta para Linux (PySide6 / Wayland / X11)
├── overlay.py                 # Atalho universal para o overlay no Linux
├── preparar_conteudo.py       # Conversor universal de Markdown para TSV (Python 3 padrão)
├── dados/
│   ├── cards.tsv              # Base normalizada de microlições em UTF-8
│   ├── relatorio_conversao.txt# Estatísticas de conversão, limites e avisos
│   └── progresso.json        # Estado de repetição espaçada entre sessões
└── testes/
    ├── testar_preparacao.py   # Suíte de testes do conversor de Markdown (17 testes)
    └── testar_overlay_linux.py# Suíte de testes do overlay e IPC no Linux (11 testes)
```

---

## 2. Pré-requisitos e Instalação

### No Windows 11:
1. **Python 3 (3.8+)**: [python.org/downloads/windows](https://www.python.org/downloads/windows/) (marque a opção *"Add python.exe to PATH"*).
2. **AutoHotkey v2**: [autohotkey.com](https://www.autohotkey.com/) (versão v2.0+).

### No Linux (Fedora, Ubuntu, Debian, Arch, KDE, GNOME, etc.):
1. **Python 3**: Nativo na maioria das distribuições.
2. **PySide6** (Qt 6 para Python):
   - **Fedora / RHEL**: `sudo dnf install python3-pyside6`
   - **Ubuntu / Debian**: `sudo apt install python3-pyside6`
   - **Arch Linux**: `sudo pacman -S python-pyside6`
   - **Via Pip**: `pip install PySide6`

---

## 3. Como Usar

### No Linux:
Abra o terminal na pasta do projeto e execute:
```bash
./iniciar.sh
```

Ou aponte diretamente para outro arquivo de conteúdo:
```bash
./iniciar.sh --conteudo conteudo_modelo.md
```

Ou execute em segundo plano (modo daemon):
```bash
./iniciar.sh --daemon
```

O script:
1. Verifica automaticamente o Python 3 e o PySide6.
2. Executa o conversor `preparar_conteudo.py` sobre o seu `conteudo.md` (ou arquivo passado via `--conteudo`).
3. Inicia a janela sobreposta translúcida com ícone na bandeja do sistema (*System Tray*).
4. Oferece controles interativos imediatos no terminal e via socket IPC.

### No Windows 11:
Basta dar um duplo clique no arquivo:
```cmd
iniciar.bat
```

---

## 4. Atalhos e Controles

### Controles no Linux:

O overlay no Linux suporta 4 canais simultâneos de controle:

#### 1. Interação Direta com o Mouse (Modo Interativo):
- **Arrastar o Card**: Clique e segure com o botão esquerdo em qualquer ponto do card para arrastá-lo e reposicioná-lo livremente na tela. A nova posição é memorizada automaticamente entre cards e sessões.
- **Revelar Termo Ocluso**: Clique sobre o card ou simplesmente passe o cursor do mouse (hover) por cima para revelar antecipadamente qualquer termo ocluso em modo Active Recall (`[...]`).
- **Botão de Lixeira 🗑️**: Localizado no canto superior direito do card. Clique nele para descartar permanentemente o card atual caso o considere inútil. O card é excluído do baralho e o próximo card é exibido imediatamente.

#### 2. Atalhos Rápidos no Terminal Interativo (quando executado via `./iniciar.sh`):
Pressione uma única tecla no terminal (sem necessidade de pressionar Enter):
- `Espaço` : **Revelar Termo Ocluso** (Active Recall) imediatamente
- `p` : **Pausar / Retomar** as notificações
- `n` : **Avançar** para o próximo card imediatamente
- `x` : **Excluir / Descartar** o card atual do baralho (ação da lixeira)
- `h` : **Ocultar** o card atual da tela
- `r` : **Reprocessar** o Markdown e recarregar os cards
- `s` : **Status** e estatísticas do baralho no terminal
- `q` : **Sair** e salvar o progresso com segurança

#### 3. Bandeja do Sistema (System Tray Icon):
Um ícone estilizado é adicionado à barra de tarefas (KDE Plasma, GNOME com AppIndicator, XFCE). Clique com o botão direito para:
- 💡 Revelar Termo Oculto (Espaço)
- ⏯️ Pausar / Retomar
- ⏭️ Próximo Card
- 🗑️ Excluir Card Atual
- 👁️ Ocultar Card Atual
- 📍 Restaurar Posição Padrão
- 🔄 Recarregar Conteúdo
- ℹ️ Status do Baralho
- ❌ Sair

#### 4. Linha de Comando / IPC (permite vincular a atalhos globais do sistema):
Você pode enviar comandos instantâneos a partir de qualquer terminal ou script para a instância em execução:
```bash
./iniciar.sh --next            # Avança para o próximo card
./iniciar.sh --reveal          # Revela imediatamente o termo ocluso (Active Recall)
./iniciar.sh --exclude         # Descarta o card atual (lixeira)
./iniciar.sh --reset-pos       # Restaura posição padrão do card na tela
./iniciar.sh --reset-excluded  # Restaura todos os cards previamente descartados
./iniciar.sh --pause           # Pausa ou retoma o ciclo
./iniciar.sh --hide            # Esconde o card atual
./iniciar.sh --reload          # Reprocessa o Markdown e recarrega
./iniciar.sh --status          # Consulta o status em formato JSON
./iniciar.sh --quit            # Encerra o overlay
```

#### 5. Como configurar Atalhos Globais no Linux:
- **KDE Plasma**: Vá em *Configurações do Sistema > Atalhos > Atalhos Personalizados > Editar > Novo > Atalho Global > Comando/URL*. Defina o atalho desejado (ex: `Ctrl+Alt+N`) e aponte para `/caminho/do/projeto/iniciar.sh --next`. Repita para `--reveal` (`Ctrl+Alt+Espaço`), `--exclude` (`Ctrl+Alt+X`), `--pause` (`Ctrl+Alt+P`), etc.
- **GNOME**: Vá em *Configurações > Teclado > Atalhos de Teclado > Personalizar Atalhos*. Adicione comando `/caminho/do/projeto/iniciar.sh --next` e vincule ao atalho desejado.

---

### Atalhos no Windows 11 (AutoHotkey v2):

- **Arrastar o Card**: Clique e arraste o card com o botão esquerdo para qualquer posição desejada na tela. O card memoriza a coordenada e continua gerando no mesmo local para todos os cards e sessões subsequentes.
- **Revelar Termo Ocluso**: Clique no card ou passe o mouse para revelar termos oclusos antecipadamente.
- **Botão de Lixeira 🗑️**: Clique para descartar o card atual permanentemente.
- **Bandeja do Sistema**: Clique com o botão direito no ícone da bandeja para acessar "Restaurar Posição Padrão" ou "Revelar Termo Oculto".

| Atalho | Ação | Descrição |
| :--- | :--- | :--- |
| `Ctrl + Alt + Espaço` | **Revelar Termo Oculto** | Revela a resposta ou termo ocluso em modo Active Recall (`[...]`). |
| `Ctrl + Alt + P` | **Pausar / Retomar** | Oculta o card e congela o cronômetro. Ao retomar, reinicia o ciclo sem acúmulo de atrasos. |
| `Ctrl + Alt + N` | **Avançar Card** | Exibe imediatamente a próxima microlição, reiniciando o timer de visibilidade. |
| `Ctrl + Alt + X` | **Excluir Card** | Descarta permanentemente a microlição atual (lixeira 🗑️) e avança para a próxima. |
| `Ctrl + Alt + C` | **Restaurar Posição** | Restaura o card para o canto configurado padrão no `config.ini`. |
| `Ctrl + Alt + H` | **Esconder Card** | Oculta o card atual da tela imediatamente, mantendo o intervalo do próximo intacto. |
| `Ctrl + Alt + R` | **Recarregar Conteúdo** | Reprocessa o Markdown e atualiza o baralho de cards em tempo real. |
| `Ctrl + Alt + Q` | **Sair do Aplicativo** | Salva o histórico em `dados/progresso.json` e encerra o processo. |

---

## 5. Como Trocar de Matéria

O aplicativo é **100% agnóstico e universal**: ele não possui código fixo para Direito ou qualquer tema específico. Mudar de matéria exige apenas:

1. Colocar o seu texto Markdown no arquivo `conteudo.md` (ou apontar outro arquivo no `config.ini`).
2. Pressionar `r` / `Ctrl + Alt + R` ou executar `./iniciar.sh --reload`.

### Testando com o modelo neutro:
Para testar o modelo demonstrativo de Astronomia incluído:
- **Via linha de comando direto:**
  ```bash
  ./iniciar.sh --conteudo conteudo_modelo.md
  ```
- **Ou via config.ini:**
  1. Abra `config.ini`.
  2. Altere `arquivo=conteudo.md` para `arquivo=conteudo_modelo.md`.
  3. Pressione `r` ou `./iniciar.sh --reload`. O overlay exibirá instantaneamente as microlições sobre planetas e movimentos celestes.

---

## 6. Personalização via `config.ini`

O arquivo `config.ini` utiliza estritamente codificação **ASCII** para garantir total compatibilidade multiplataforma.

```ini
[Conteudo]
arquivo=conteudo.md              ; Nome ou caminho do seu Markdown
min_chars=90                     ; Tamanho mínimo de caracteres no corpo do card
max_chars=220                    ; Tamanho máximo de caracteres no corpo do card
new_ratio=70                     ; Proporção de cards novos vs. revisões (70 = 70% novos)
ignorar_secoes=Mapeamento das Fontes e Rastreabilidade do Acervo Local ; Seções excluídas

[Exibicao]
interval_seconds=300             ; Intervalo entre o início de cada card (300s = 5 minutos)
visible_seconds=30               ; Tempo que o card permanece na tela (padrão: 30 segundos)
corner=top_right                 ; Canto: top_right, top_left, bottom_right, bottom_left
margin_x=30                      ; Recuo horizontal da borda do monitor (pixels)
margin_y=30                      ; Recuo vertical da borda do monitor (pixels)
width=430                        ; Largura do card (pixels lógicos)
height=150                       ; Altura do card (pixels lógicos)
font_size=11                     ; Tamanho da fonte do corpo principal
opacity=230                      ; Opacidade da janela (20 a 255)
bg_color=14241F                  ; Cor de fundo em hexadecimal (RGB)
show_on_start=1                  ; Exibir card teste ao abrir (1=sim, 0=não)
click_through=0                  ; 0 = Interativo (arrastável com mouse e lixeira 🗑️), 1 = Passivo
cloze_enabled=1                  ; 1 = Ativar modo Active Recall / Cloze Deletion (0 = desativado)
cloze_reveal_seconds=4           ; Segundos de oclusão com [...] antes da revelação automática
highlight_keywords=1             ; 1 = Destacar prazos (âmbar) e vedações jurídicas (coral)

[Contexto]
target_exes=                     ; Lista de executáveis (ex: jogo.exe,cs2). Vazio = todos
hide_when_target_inactive=1      ; Ocultar se o jogo perder foco

[Estado]
remember_progress=1              ; Salvar cards já vistos para repetição espaçada
```

---

## 7. Modo Active Recall e Destaque Visual Inteligente

O MicroEstudo Overlay inclui dois mecanismos pedagógicos avançados projetados para turbinar a memorização de alto rendimento durante partidas:

### A. Modo Active Recall / Cloze Deletion (Oclusão de Termos)
- **Como Funciona**: Em vez de ler a resposta passivamente, o termo-chave é inicialmente ocultado com `[...]` durante os primeiros segundos (padrão: 4s configuráveis em `cloze_reveal_seconds`). Isso força o cérebro a recuperar ativamente a informação da memória antes da confirmação.
- **Marcação Manual**: Suporta a sintaxe `{{termo_oculto}}` no texto do Markdown. O conversor preserva rigorosamente a marcação e o overlay se encarrega de ocluir o termo.
- **Detecção Inteligente para Conceitos**: Reconhece automaticamente estruturas de definições em cards de conceito (ex: `Conceito: Definição`, títulos repetidos no início do texto ou construções `Sujeito é / são / consiste em`), ocluindo o termo-chave sem que você precise editar manualmente centenas de cards.
- **Revelação sob Demanda**: Além do temporizador automático, o termo oculto pode ser revelado instantaneamente:
  - No **Windows**: Pelo atalho global `Ctrl + Alt + Espaço`, clicando no card, ou passando o cursor do mouse (hover) por cima.
  - No **Linux**: Pressionando `Espaço` no terminal interativo, passando o mouse sobre o card, clicando/arrastando, ou via comando `./iniciar.sh --reveal`.

### B. Renderização Visual com Destaque de Prazos e Palavras-Chave
- **Prazos e Períodos (Âmbar Suave - `#FFD266`)**: Destaque automático para quantidades temporais e prazos jurídicos cruciais (ex: `15 dias`, `5 anos`, `24 horas`, `prazo recursal`, `prazo prescricional`, `quinquênio`).
- **Palavras de Corte e Vedações (Coral Suave - `#FF7A7A`)**: Alerta visual instantâneo para termos restritivos que definem questões de prova (ex: `vedado`, `proibido`, `salvo`, `não cabe`, `nulo`, `inconstitucional`, `exceção`, `imprescritível`).
- **Respostas de Active Recall (Ciano Suave - `#7EC8E3`)**: Os termos oclusos e respostas reveladas recebem destaque nítido e sublinhado.
- **Desempenho Sem Flicker**: Implementado via controle nativo *RichEdit 5.0* no AutoHotkey v2 (Windows) e via HTML renderizado no PySide6 (Linux), garantindo consumo nulo de GPU e sem qualquer impacto na taxa de quadros (FPS) de jogos competitivos.

---

## 8. Comportamento em Jogos e Segurança

- **Click-Through Total ou Modo Interativo**:
  - No Windows: Suporte a `WS_EX_TRANSPARENT` ou arrasto nativo com botão de lixeira caso interativo.
  - No Linux: Suporta modo interativo (`click_through=0`, padrão) com arrasto suave e botão vetorial de lixeira 🗑️, ou passivo (`click_through=1`) com `Qt.WindowTransparentForInput` + `WA_TransparentForMouseEvents`.
- **Sem Perda de Foco**:
  - No Windows: `Show("NoActivate")` com estilo `0x08000000`.
  - No Linux: `Qt.WindowDoesNotAcceptFocus` + `WA_ShowWithoutActivating`. O jogo nunca perde a mira, o cursor ou o controle do teclado.
- **Modo de Tela Recomendado**: Configure o seu jogo para **Janela Sem Bordas (Borderless Window)** ou **Janela em Tela Cheia**. Jogos em modo exclusivo tradicional (*Exclusive Fullscreen*) monopolizam o buffer de renderização de vídeo e podem ocultar sobreposições do sistema.
- **100% Seguro contra Anticheat**: O MicroEstudo Overlay opera estritamente no espaço do usuário. Ele **NÃO injeta DLLs**, **NÃO lê nem escreve memória de processos**, **NÃO usa ganchos de teclado (hooks) no jogo**, **NÃO automatiza cliques** e **NÃO altera arquivos do jogo**.

---

## 9. Verificação e Testes Automatizados

O projeto conta com suíte completa de testes automatizados com cobertura do conversor e do overlay:

```bash
# Executar todos os testes automatizados (Linux ou Windows):
python -m unittest discover -s testes -p "testar_*.py" -v
```

### Resultados da Suíte:
- **`testes/testar_preparacao.py`**: 28 testes automatizados cobrindo hierarquia de títulos, definições, acentos UTF-8, símbolos matemáticos, tabelas, sanitização TSV, determinismo de IDs, integridade e preservação de tags de Cloze `{{...}}`, quebra de sentenças sem fragmentação de oclusões, heurística de detecção inteligente de conceitos e renderização formatada de HTML com destaque de prazos e vedações.
- **`testes/testar_overlay_linux.py`**: Suíte de testes da interface gráfica e lógica Linux (carregamento de configurações e clamping de limites, carregamento e parsing de TSV com `\n`, algoritmo de repetição 70/30, persistência e sincronização de progresso, flags de janela e sem foco, cálculo de posição nos 4 cantos da tela, servidor de comandos IPC e status, arrasto livre com mouse e persistência de coordenadas, botão vetorial de lixeira e exclusão permanente, elisão de texto e ausência de sobreposição sobre rodapé).

---

## 10. Limitações Conhecidas e Escopo

- **Imagens e Diagramas Complexos**: Caixas ASCII multidimensionais e diagramas visuais não cabem esteticamente no formato de microlições de 440×160 pixels. O conversor extrai os mnemônicos lineares e registra aviso detalhado em `dados/relatorio_conversao.txt`.
- **Tela Cheia Exclusiva**: Em títulos que utilizam DirectX ou Vulkan exclusivo sem repasse para o compositor de janelas, é necessário alterar o jogo nas opções de vídeo para "Janela sem bordas" (Borderless).
- **Proposta Pedagógica**: O MicroEstudo Overlay foi criado para **exposição incidental e revisão espaçada**. Ele não substitui o estudo aprofundado, mas maximiza a retenção de conceitos cruciais, prazos de leis e mnemônicos durante os momentos de lazer.
