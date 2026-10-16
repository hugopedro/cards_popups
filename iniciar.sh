#!/usr/bin/env bash
# ======================================================================
# MICROESTUDO OVERLAY — INICIALIZADOR E CONTROLADOR LINUX
# ======================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Habilita XWayland (XCB) para permitir arrasto livre e posicionamento em sessões Wayland
if [ -z "$QT_QPA_PLATFORM" ] && [ -n "$DISPLAY" ]; then
    export QT_QPA_PLATFORM=xcb
fi

exibir_ajuda() {
    echo "Uso: ./iniciar.sh [OPÇÕES]"
    echo ""
    echo "Inicializa ou controla o MicroEstudo Overlay em ambientes Linux (Wayland e X11)."
    echo ""
    echo "Opções de Inicialização:"
    echo "  (sem argumentos)            Inicia o overlay em modo interativo no terminal"
    echo "  -d, --daemon                Inicia o overlay em segundo plano (background/daemon)"
    echo "  -c, --conteudo <arquivo>    Especifica o arquivo Markdown de estudo (ex: conteudo.md)"
    echo "  --config <arquivo>          Especifica o arquivo de configuração INI (padrão: config.ini)"
    echo "  -h, --help                  Exibe esta mensagem de ajuda"
    echo ""
    echo "Opções de Controle (para enviar à instância em execução):"
    echo "  -n, --next                  Avança para o próximo card imediatamente"
    echo "  -x, --exclude               Descarta/exclui o card atual permanentemente"
    echo "  --reset-pos                 Restaura a posição padrão do overlay no canto da tela"
    echo "  --reset-excluded            Restaura todos os cards previamente descartados"
    echo "  -p, --pause                 Pausa ou retoma as exibições"
    echo "  --hide                      Oculta o card atual da tela"
    echo "  -r, --reload                Reprocessa o Markdown e recarrega os cards"
    echo "  -s, --status                Exibe o status atual e progresso do baralho (formato JSON)"
    echo "  -q, --quit                  Salva o progresso e encerra o aplicativo"
    echo ""
    echo "Exemplos:"
    echo "  ./iniciar.sh                                # Inicia com o conteúdo padrão"
    echo "  ./iniciar.sh --daemon                       # Inicia em segundo plano"
    echo "  ./iniciar.sh --conteudo conteudo_modelo.md  # Inicia com material específico"
    echo "  ./iniciar.sh --next                         # Avança o card via atalho/linha de comando"
    echo "  ./iniciar.sh --exclude                      # Descarta card inútil imediatamente"
    echo "  ./iniciar.sh --reset-pos                    # Restaura posição padrão do card"
    echo "  ./iniciar.sh --pause                        # Pausa/retoma o aplicativo"
}

# 1. Tratamento imediato de comandos de controle IPC
if [[ "$1" =~ ^(-n|--next|-x|--exclude|--reset-pos|--reset-excluded|-p|--pause|--hide|-r|--reload|-s|--status|-q|--quit)$ ]]; then
    if ! command -v python3 >/dev/null 2>&1; then
        echo "[ERRO] Python 3 não foi encontrado no sistema!" >&2
        exit 1
    fi
    exec python3 "$SCRIPT_DIR/overlay_linux.py" "$@"
fi

if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    exibir_ajuda
    exit 0
fi

# Parsing de argumentos para inicialização
IS_DAEMON=0
CONFIG_FILE="$SCRIPT_DIR/config.ini"
CONTEUDO_FILE=""
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        -d|--daemon|--background)
            IS_DAEMON=1
            shift
            ;;
        -c|--conteudo)
            CONTEUDO_FILE="$2"
            EXTRA_ARGS+=("--conteudo" "$2")
            shift 2
            ;;
        --config)
            CONFIG_FILE="$2"
            EXTRA_ARGS+=("--config" "$2")
            shift 2
            ;;
        -h|--help)
            exibir_ajuda
            exit 0
            ;;
        *)
            EXTRA_ARGS+=("$1")
            shift
            ;;
    esac
done

echo "======================================================================"
echo "          MICROESTUDO OVERLAY — APRENDIZAGEM EM SEGUNDO PLANO"
echo "                             (LINUX)"
echo "======================================================================"
echo ""

# 2. Verificação do Python 3
if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERRO] Python 3 não foi detectado no sistema!"
    echo "Instale o Python 3 utilizando o gerenciador de pacotes da sua distribuição:"
    echo "  - Fedora:   sudo dnf install python3"
    echo "  - Ubuntu:   sudo apt install python3"
    echo "  - Arch:     sudo pacman -S python"
    echo ""
    exit 1
fi

PY_VER=$(python3 --version 2>&1)
echo "[+] Python detectado: $PY_VER"

# 3. Verificação do PySide6
if ! python3 -c "import PySide6" >/dev/null 2>&1; then
    echo ""
    echo "[ERRO] O módulo PySide6 não foi encontrado no Python!"
    echo "Para exibir o overlay flutuante translúcido no Linux, instale o PySide6:"
    echo "  - Fedora/RHEL:   sudo dnf install python3-pyside6"
    echo "  - Ubuntu/Debian: sudo apt install python3-pyside6"
    echo "  - Arch Linux:    sudo pacman -S python-pyside6"
    echo "  - Ou via pip:    pip install PySide6"
    echo ""
    exit 2
fi

echo "[+] PySide6 detectado com sucesso."
echo ""

# 4. Verificação de instância prévia em execução
if python3 "$SCRIPT_DIR/overlay_linux.py" --status >/dev/null 2>&1; then
    echo "[!] O MicroEstudo Overlay já está em execução no sistema!"
    echo ""
    echo "Status da sessão ativa:"
    python3 "$SCRIPT_DIR/overlay_linux.py" --status
    echo ""
    echo "Comandos disponíveis:"
    echo "  ./iniciar.sh --next      : Avançar card"
    echo "  ./iniciar.sh --pause     : Pausar / Retomar"
    echo "  ./iniciar.sh --hide      : Ocultar card atual"
    echo "  ./iniciar.sh --reload    : Reprocessar e recarregar"
    echo "  ./iniciar.sh --quit      : Sair do aplicativo"
    exit 0
fi

# 5. Processamento e compilação do conteúdo Markdown
echo "[+] Preparando microlições a partir do Markdown..."
PREP_CMD=(python3 "$SCRIPT_DIR/preparar_conteudo.py" --config "$CONFIG_FILE")
if [[ -n "$CONTEUDO_FILE" ]]; then
    PREP_CMD+=(--conteudo "$CONTEUDO_FILE")
fi

"${PREP_CMD[@]}"

if [ $? -ne 0 ]; then
    echo ""
    echo "[ERRO] Falha ao processar o conteúdo Markdown."
    echo "Verifique o arquivo de configuração ou a sintaxe do arquivo de estudo."
    exit 3
fi

echo ""
echo "[+] Conteúdo processado com sucesso!"
echo "[+] Iniciando overlay sobreposto aos jogos..."

# 6. Inicialização do Overlay (Modo Daemon ou Interativo)
mkdir -p "$SCRIPT_DIR/dados"

# Monta argumentos para o overlay
OVERLAY_CMD=(python3 "$SCRIPT_DIR/overlay_linux.py" --config "$CONFIG_FILE")
if [[ -n "$CONTEUDO_FILE" ]]; then
    OVERLAY_CMD+=(--conteudo "$CONTEUDO_FILE")
fi
for arg in "${EXTRA_ARGS[@]}"; do
    if [[ "$arg" != "--config" && "$arg" != "$CONFIG_FILE" && "$arg" != "--conteudo" && "$arg" != "$CONTEUDO_FILE" ]]; then
        OVERLAY_CMD+=("$arg")
    fi
done

if [[ $IS_DAEMON -eq 1 ]]; then
    LOG_FILE="$SCRIPT_DIR/dados/overlay.log"
    nohup "${OVERLAY_CMD[@]}" < /dev/null > "$LOG_FILE" 2>&1 &
    OVERLAY_PID=$!
    disown "$OVERLAY_PID" 2>/dev/null || true

    sleep 0.5
    if kill -0 "$OVERLAY_PID" 2>/dev/null; then
        echo "[+] Overlay iniciado com sucesso em segundo plano (PID: $OVERLAY_PID)"
        echo "[+] Log de execução: file://$LOG_FILE"
        echo "[+] Utilize os atalhos de controle via: ./iniciar.sh --next | --pause | --quit"
        exit 0
    else
        echo "[ERRO] O overlay encerrou inesperadamente ao iniciar." >&2
        if [[ -f "$LOG_FILE" ]]; then
            echo "--- Detalhes do log ($LOG_FILE) ---" >&2
            cat "$LOG_FILE" >&2
        fi
        exit 4
    fi
else
    # Execução em primeiro plano com atalhos de terminal interativos
    exec "${OVERLAY_CMD[@]}"
fi
