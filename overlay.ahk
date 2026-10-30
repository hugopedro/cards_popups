#Requires AutoHotkey v2.0
#SingleInstance Force
Persistent(true)

OnError(LogAhkError)
OnExit(LogAhkExit)

LogAhkError(err, mode) {
    try FileAppend("Error: " . err.Message . " at " . err.Line . "`n", A_ScriptDir . "\dados\overlay.log")
    return 1
}

LogAhkExit(reason, code) {
    try FileAppend("Exit: " . reason . " code " . code . "`n", A_ScriptDir . "\dados\overlay.log")
}

; ====================================================================
; MicroEstudo Overlay - AutoHotkey v2
; Overlay universal de microaprendizagem sobreposto a jogos no Windows 11
; Click-through, sem roubo de foco, configurável via config.ini
; ====================================================================

; Diretório do script como base de trabalho
SetWorkingDir(A_ScriptDir)

; Configurações globais padrão
global Config := Map(
    "arquivo", "conteudo.md",
    "min_chars", 90,
    "max_chars", 220,
    "new_ratio", 70,
    "interval_seconds", 300,
    "visible_seconds", 30,
    "corner", "top_right",
    "margin_x", 30,
    "margin_y", 30,
    "width", 430,
    "height", 150,
    "font_size", 11,
    "opacity", 230,
    "bg_color", "14241F",
    "show_on_start", 1,
    "click_through", 0,
    "target_exes", "",
    "hide_when_target_inactive", 1,
    "remember_progress", 1
)

; Estado do aplicativo
global Cards := []
global Progresso := Map()
global Excluidos := Map()
global UltimoCardId := ""
global EstaPausado := false
global CardVisivel := false
global OverlayGui := ""
global CtrlAssunto := ""
global CtrlTitulo := ""
global CtrlTexto := ""
global CtrlOrigem := ""
global CustomPos := ""

; Inicialização do sistema
CarregarConfiguracoes()
CarregarExcluidos()
CarregarProgresso()
CarregarPosicao()
CarregarCards()
SincronizarProgressoComCards()
CriarInterface()
A_TrayMenu.Add()
A_TrayMenu.Add("Restaurar Posição Padrão", (*) => RedefinirPosicao())

; Hotkeys globais padrão
^!p::AlternarPausa()          ; Ctrl + Alt + P: Pausar / Retomar
^!n::ProximoCardManual()      ; Ctrl + Alt + N: Próximo card agora
^!x::ExcluirCardAtual()       ; Ctrl + Alt + X: Excluir card inútil
^!c::RedefinirPosicao()       ; Ctrl + Alt + C: Restaurar posição padrão
^!h::OcultarCardAtual()       ; Ctrl + Alt + H: Esconder card atual
^!r::RecarregarConteudo()     ; Ctrl + Alt + R: Reprocessar e recarregar
^!q::SairAplicativo()         ; Ctrl + Alt + Q: Sair e salvar

; Monitoramento periódico do foco do jogo (a cada 1 segundo)
SetTimer(MonitorarFocoJogo, 1000)

; Início automático
if (Config["show_on_start"] && Cards.Length > 0) {
    ExibirProximoCard()
} else if (Cards.Length > 0) {
    AgendarProximoCard(Config["interval_seconds"])
}

; --------------------------------------------------------------------
; Funções de Configuração e Validação
; --------------------------------------------------------------------

CarregarConfiguracoes() {
    iniFile := A_ScriptDir . "\config.ini"
    if !FileExist(iniFile)
        return

    LerInt(secao, chave, padrao, minVal := "", maxVal := "") {
        try {
            val := IniRead(iniFile, secao, chave, padrao)
            num := Integer(val)
            if (minVal !== "" && num < minVal)
                num := minVal
            if (maxVal !== "" && num > maxVal)
                num := maxVal
            return num
        } catch {
            return padrao
        }
    }

    LerStr(secao, chave, padrao) {
        try {
            val := IniRead(iniFile, secao, chave, padrao)
            return Trim(val)
        } catch {
            return padrao
        }
    }

    Config["arquivo"] := LerStr("Conteudo", "arquivo", Config["arquivo"])
    Config["min_chars"] := LerInt("Conteudo", "min_chars", Config["min_chars"], 30, 400)
    Config["max_chars"] := LerInt("Conteudo", "max_chars", Config["max_chars"], 60, 600)
    Config["new_ratio"] := LerInt("Conteudo", "new_ratio", Config["new_ratio"], 0, 100)

    Config["interval_seconds"] := LerInt("Exibicao", "interval_seconds", Config["interval_seconds"], 10, 3600)
    Config["visible_seconds"] := LerInt("Exibicao", "visible_seconds", Config["visible_seconds"], 5, Config["interval_seconds"])
    Config["corner"] := LerStr("Exibicao", "corner", Config["corner"])
    Config["margin_x"] := LerInt("Exibicao", "margin_x", Config["margin_x"], 0, 500)
    Config["margin_y"] := LerInt("Exibicao", "margin_y", Config["margin_y"], 0, 500)
    Config["width"] := LerInt("Exibicao", "width", Config["width"], 240, 1200)
    Config["height"] := LerInt("Exibicao", "height", Config["height"], 100, 800)
    Config["font_size"] := LerInt("Exibicao", "font_size", Config["font_size"], 10, 32)
    Config["opacity"] := LerInt("Exibicao", "opacity", Config["opacity"], 20, 255)
    Config["bg_color"] := LerStr("Exibicao", "bg_color", Config["bg_color"])
    Config["show_on_start"] := LerInt("Exibicao", "show_on_start", Config["show_on_start"], 0, 1)
    Config["click_through"] := LerInt("Exibicao", "click_through", Config["click_through"], 0, 1)

    Config["target_exes"] := LerStr("Contexto", "target_exes", Config["target_exes"])
    Config["hide_when_target_inactive"] := LerInt("Contexto", "hide_when_target_inactive", Config["hide_when_target_inactive"], 0, 1)
    Config["remember_progress"] := LerInt("Estado", "remember_progress", Config["remember_progress"], 0, 1)
}

CarregarExcluidos() {
    global Excluidos
    Excluidos := Map()
    excFile := A_ScriptDir . "\dados\excluidos.json"
    if !FileExist(excFile)
        return

    try {
        conteudo := FileRead(excFile, "UTF-8")
        pos := 1
        while RegExMatch(conteudo, '`"([a-f0-9]+)`"', &m, pos) {
            Excluidos[m[1]] := true
            pos := m.Pos + m.Len
        }
    } catch {
        Excluidos := Map()
    }
}

CarregarCards() {
    global Cards, Excluidos
    Cards := []
    tsvFile := A_ScriptDir . "\dados\cards.tsv"

    if !FileExist(tsvFile) {
        ExecutarConversorPython()
    }

    if !FileExist(tsvFile) {
        MsgBox("Arquivo 'dados/cards.tsv' não encontrado. Execute iniciar.bat ou preparar_conteudo.py.", "MicroEstudo Overlay", 48)
        return
    }

    conteudoTsv := FileRead(tsvFile, "UTF-8")
    linhas := StrSplit(conteudoTsv, "`n", "`r")

    for idx, linha in linhas {
        linha := Trim(linha)
        if (linha == "")
            continue

        campos := StrSplit(linha, "`t")
        if (campos.Length < 6)
            continue

        ; Ignorar linha de cabeçalho
        if (idx == 1 && campos[1] == "id" && campos[2] == "assunto")
            continue

        cId := campos[1]
        if (Excluidos.Has(cId))
            continue

        ; Decodificar \n literal em quebra real
        textoDecodificado := StrReplace(campos[5], "\n", "`n")

        Cards.Push(Map(
            "id", cId,
            "assunto", campos[2],
            "subtema", campos[3],
            "titulo", campos[4],
            "texto", textoDecodificado,
            "origem", campos[6]
        ))
    }
}

CarregarProgresso() {
    global Progresso
    Progresso := Map()
    if (!Config["remember_progress"])
        return

    progFile := A_ScriptDir . "\dados\progresso.json"
    if !FileExist(progFile)
        return

    try {
        jsonStr := FileRead(progFile, "UTF-8")
        padraoBloco := '`"([a-f0-9]+)`":\s*\{([^}]+)\}'
        pos := 1
        while RegExMatch(jsonStr, padraoBloco, &match, pos) {
            cId := match[1]
            corpo := match[2]
            exib := 1
            ult := 0
            if RegExMatch(corpo, '`"exibicoes`":\s*(\d+)', &mExib)
                exib := Integer(mExib[1])
            if RegExMatch(corpo, '`"ultima`":\s*(\d+)', &mUlt)
                ult := Integer(mUlt[1])
            Progresso[cId] := Map("exibicoes", exib, "ultima", ult)
            pos := match.Pos + match.Len
        }
    } catch {
        ; Ignora erros de JSON corrompido
    }
}

SincronizarProgressoComCards() {
    global Progresso, Cards
    if (!Config["remember_progress"] || Cards.Length == 0)
        return

    idsValidos := Map()
    for c in Cards {
        idsValidos[c["id"]] := true
    }

    idsParaRemover := []
    for cId, _ in Progresso {
        if (!idsValidos.Has(cId)) {
            idsParaRemover.Push(cId)
        }
    }

    for cId in idsParaRemover {
        Progresso.Delete(cId)
    }

    if (idsParaRemover.Length > 0) {
        SalvarProgresso()
    }
}

SalvarProgresso() {
    if (!Config["remember_progress"])
        return

    progFile := A_ScriptDir . "\dados\progresso.json"
    sb := "{"
    primeiro := true
    for cId, dados in Progresso {
        if (!primeiro)
            sb .= ","
        primeiro := false
        sb .= '`"' . cId . '`":{"exibicoes":' . dados["exibicoes"] . ',"ultima":' . dados["ultima"] . '}'
    }
    sb .= "}"

    try {
        if FileExist(progFile)
            FileDelete(progFile)
        FileAppend(sb, progFile, "UTF-8")
    } catch {
        ; Falha de escrita silenciosa
    }
}

; --------------------------------------------------------------------
; Interface Gráfica do Overlay (Transparente a Cliques e Sem Foco)
; --------------------------------------------------------------------

CriarInterface() {
    global OverlayGui
    if (!Config["click_through"]) {
        OnMessage(0x0201, ArrastoJanelaAHK) ; WM_LBUTTONDOWN -> arrastar
    }
}

RenderizarCard(card) {
    global OverlayGui, Config, CustomPos, CtrlAssunto, CtrlTitulo, CtrlTexto, CtrlOrigem

    if (OverlayGui != "") {
        try OverlayGui.Destroy()
    }

    ; Configuração de modo interativo vs click-through
    if (Config["click_through"]) {
        estilos := "+AlwaysOnTop +ToolWindow -Caption +E0x20 +E0x08000000"
        OverlayGui := Gui(estilos, "MicroEstudoOverlay")
        OnMessage(0x0084, (*) => -1) ; HTTRANSPARENT
    } else {
        estilos := "+AlwaysOnTop +ToolWindow -Caption +E0x08000000"
        OverlayGui := Gui(estilos, "MicroEstudoOverlay")
    }

    bgColor := Config["bg_color"]
    OverlayGui.BackColor := bgColor
    OverlayGui.MarginX := 16
    OverlayGui.MarginY := 12

    fSize := Config["font_size"]
    fSub := Max(8.5, fSize - 2.5)
    fTit := Max(12.0, fSize + 1.5)
    wBox := Config["width"] - 32

    assuntoTxt := card["assunto"]
    if (card["subtema"] != "" && card["subtema"] != card["assunto"])
        assuntoTxt .= "  ›  " . card["subtema"]

    origemTxt := card["origem"] . "  •  ID: " . SubStr(card["id"], 1, 8)

    ; Cabeçalho: Assunto / Subtema e Botão de Lixeira
    if (!Config["click_through"]) {
        wBtn := 22
        wAssunto := wBox - wBtn - 8
        OverlayGui.SetFont("s" . fSub . " bold c88A89A", "Segoe UI")
        CtrlAssunto := OverlayGui.Add("Text", "+Disabled w" . wAssunto . " r1", SubStr(assuntoTxt, 1, 75))

        OverlayGui.SetFont("s10 bold c88A89A", "Segoe UI")
        btnLixeira := OverlayGui.Add("Text", "x+" . 4 . " yp w" . wBtn . " h18 Center +0x200 BackgroundTrans", "🗑")
        btnLixeira.OnEvent("Click", (*) => ExcluirCardAtual())
    } else {
        OverlayGui.SetFont("s" . fSub . " bold c88A89A", "Segoe UI")
        CtrlAssunto := OverlayGui.Add("Text", "+Disabled +E0x20 w" . wBox . " r1", SubStr(assuntoTxt, 1, 75))
    }

    ; Título em destaque (permite acomodar título completo)
    OverlayGui.SetFont("s" . fTit . " bold cFFFFFF", "Segoe UI")
    CtrlTitulo := OverlayGui.Add("Text", "xm y+4 +Disabled w" . wBox, card["titulo"])

    ; Texto da microlição com auto-dimensionamento exato (sem corte vertical!)
    OverlayGui.SetFont("s" . fSize . " norm cE4EDE7", "Segoe UI")
    CtrlTexto := OverlayGui.Add("Text", "xm y+6 +Disabled w" . wBox, card["texto"])

    ; Rodapé discreto com origem (sempre visível na base)
    OverlayGui.SetFont("s" . (fSub - 0.5) . " c5E7A6E", "Segoe UI")
    CtrlOrigem := OverlayGui.Add("Text", "xm y+6 +Disabled w" . wBox . " r1", origemTxt)

    ; Mede dimensões ideais com AutoSize
    OverlayGui.Show("AutoSize Hide")
    OverlayGui.GetPos(,, &gw, &gh)

    ; Garante altura mínima configurada (confortável)
    minH := Config["height"] > 0 ? Config["height"] : 150
    if (gh < minH)
        gh := minH

    ; Posiciona a janela dinamicamente com base nas dimensões reais
    CalcularPosicao(&x, &y, gw, gh)
    OverlayGui.Move(x, y, gw, gh)

    ; Transparência suave da janela inteira
    WinSetTransparent(Config["opacity"], OverlayGui.Hwnd)

    ; Exibe sem roubar foco
    OverlayGui.Show("NoActivate")
}

CarregarPosicao() {
    global CustomPos
    posFile := A_ScriptDir . "\dados\posicao.json"
    if !FileExist(posFile)
        return

    try {
        conteudo := FileRead(posFile, "UTF-8")
        if (RegExMatch(conteudo, '`"x`":\s*(-?\d+)', &mx) && RegExMatch(conteudo, '`"y`":\s*(-?\d+)', &my)) {
            CustomPos := Map("x", Integer(mx[1]), "y", Integer(my[1]))
        }
    }
}

SalvarPosicao(x, y) {
    posFile := A_ScriptDir . "\dados\posicao.json"
    try {
        DirCreate(A_ScriptDir . "\dados")
        jsonContent := "{\n  `"x`": " . x . ",\n  `"y`": " . y . "\n}\n"
        if FileExist(posFile)
            FileDelete(posFile)
        FileAppend(jsonContent, posFile, "UTF-8")
    }
}

RedefinirPosicao() {
    global CustomPos, OverlayGui, CardVisivel
    CustomPos := ""
    posFile := A_ScriptDir . "\dados\posicao.json"
    try {
        if FileExist(posFile)
            FileDelete(posFile)
    }
    if (CardVisivel && OverlayGui != "") {
        OverlayGui.GetPos(,, &gw, &gh)
        CalcularPosicao(&x, &y, gw, gh)
        OverlayGui.Move(x, y)
    }
    ToolTip("Posição padrão restaurada.")
    SetTimer(() => ToolTip(), -2000)
}

ArrastoJanelaAHK(wParam, lParam, msg, hwnd) {
    global OverlayGui, Config, CustomPos
    if (Config["click_through"])
        return
    if (OverlayGui != "" && hwnd == OverlayGui.Hwnd) {
        ; SendMessage bloqueia de forma síncrona durante o arrasto interativo do Windows
        SendMessage(0xA1, 2,,, "ahk_id " . OverlayGui.Hwnd)
        ; Ao soltar o mouse, grava a nova coordenada exata e persiste no disco
        WinGetPos(&x, &y, , , "ahk_id " . OverlayGui.Hwnd)
        CustomPos := Map("x", x, "y", y)
        SalvarPosicao(x, y)
    }
}

CalcularPosicao(&posX, &posY, gw := 0, gh := 0) {
    global CustomPos, Config
    if (CustomPos != "") {
        posX := CustomPos["x"]
        posY := CustomPos["y"]
        return
    }

    w := (gw > 0) ? gw : Config["width"]
    h := (gh > 0) ? gh : Config["height"]
    mx := Config["margin_x"]
    my := Config["margin_y"]
    corner := StrLower(Trim(Config["corner"]))

    sWidth := A_ScreenWidth
    sHeight := A_ScreenHeight

    switch corner {
        case "top_left", "superior_esquerdo", "superior-esquerdo":
            posX := mx
            posY := my
        case "bottom_left", "inferior_esquerdo", "inferior-esquerdo":
            posX := mx
            posY := sHeight - h - my
        case "bottom_right", "inferior_direito", "inferior-direito":
            posX := sWidth - w - mx
            posY := sHeight - h - my
        default: ; top_right, superior_direito, superior-direito
            posX := sWidth - w - mx
            posY := my
    }
}

; --------------------------------------------------------------------
; Algoritmo de Seleção e Exibição de Cards
; --------------------------------------------------------------------

SelecionarCard() {
    global Cards, Progresso, UltimoCardId
    if (Cards.Length == 0)
        return ""

    if (Cards.Length == 1)
        return Cards[1]

    ; 1. Separar cards não vistos
    naoVistos := []
    for idx, c in Cards {
        if (!Progresso.Has(c["id"]) || Progresso[c["id"]]["exibicoes"] == 0) {
            naoVistos.Push(c)
        }
    }

    sorteio := Random(1, 100)
    novoRatio := Config["new_ratio"]

    ; Se houver novos e (o sorteio favorecer novos OU for o primeiro card exibido nesta sessão)
    if (naoVistos.Length > 0 && (sorteio <= novoRatio || UltimoCardId == "" || Progresso.Count == 0)) {
        return naoVistos[1]
    }

    ; 2. Revisão: escolher dentre os já vistos com menor número de exposições
    candidatos := []
    for idx, c in Cards {
        if (c["id"] != UltimoCardId) {
            candidatos.Push(c)
        }
    }

    if (candidatos.Length == 0)
        candidatos := Cards

    menorExib := 999999
    cardEscolhido := candidatos[1]

    for c in candidatos {
        cId := c["id"]
        exib := Progresso.Has(cId) ? Progresso[cId]["exibicoes"] : 0
        if (exib < menorExib) {
            menorExib := exib
            cardEscolhido := c
        }
    }

    return cardEscolhido
}

ExibirProximoCard() {
    global Cards, Progresso, UltimoCardId, CardVisivel

    if (EstaPausado || Cards.Length == 0)
        return

    ; Verificar se há filtro de executável ativo
    if (!JogoAlvoEstaAtivo()) {
        ; Tenta novamente em 5 segundos sem queimar o card
        SetTimer(ExibirProximoCard, -5000)
        return
    }

    card := SelecionarCard()
    if (card == "")
        return

    UltimoCardId := card["id"]

    ; Atualizar estatísticas de progresso
    agora := A_NowUTC
    tempoEpoch := Integer(DateDiff(agora, "19700101000000", "Seconds"))
    if (!Progresso.Has(card["id"])) {
        Progresso[card["id"]] := Map("exibicoes", 1, "ultima", tempoEpoch)
    } else {
        Progresso[card["id"]]["exibicoes"] += 1
        Progresso[card["id"]]["ultima"] := tempoEpoch
    }
    SalvarProgresso()

    ; Renderizar interface dinamicamente ajustada ao conteúdo
    RenderizarCard(card)
    CardVisivel := true

    ; Temporizador de permanência (padrão: 30 segundos)
    SetTimer(OcultarCard, -(Config["visible_seconds"] * 1000))

    ; Temporizador de ciclo: contado a partir do INÍCIO deste card (padrão: 300 segundos = 5 minutos)
    SetTimer(ExibirProximoCard, -(Config["interval_seconds"] * 1000))
}

OcultarCard() {
    global CardVisivel, OverlayGui
    if (CardVisivel && OverlayGui != "") {
        OverlayGui.Hide()
        CardVisivel := false
    }
}

AgendarProximoCard(segundos) {
    SetTimer(ExibirProximoCard, -(segundos * 1000))
}

ExcluirCardAtual() {
    global Cards, UltimoCardId, CardVisivel, OverlayGui, Progresso
    if (!CardVisivel || UltimoCardId == "" || Cards.Length == 0)
        return

    cIdParaExcluir := UltimoCardId
    novosCards := []
    for c in Cards {
        if (c["id"] != cIdParaExcluir)
            novosCards.Push(c)
    }
    Cards := novosCards

    if (Progresso.Has(cIdParaExcluir)) {
        Progresso.Delete(cIdParaExcluir)
        SalvarProgresso()
    }

    SalvarExcluido(cIdParaExcluir)

    ; Avançar para o próximo card imediatamente
    SetTimer(OcultarCard, 0)
    SetTimer(ExibirProximoCard, -100)
}

SalvarExcluido(cId) {
    excFile := A_ScriptDir . "\dados\excluidos.json"
    excluidos := Map()
    if (FileExist(excFile)) {
        try {
            conteudo := FileRead(excFile, "UTF-8")
            for item in StrSplit(conteudo, ["`n", "`r", ",", "[", "]", '"', " "]) {
                if (Trim(item) != "")
                    excluidos[Trim(item)] := true
            }
        }
    }
    excluidos[cId] := true
    sb := "["
    primeiro := true
    for id, _ in excluidos {
        if (!primeiro)
            sb .= ","
        primeiro := false
        sb .= '`"' . id . '`"'
    }
    sb .= "]"
    try {
        if FileExist(excFile)
            FileDelete(excFile)
        FileAppend(sb, excFile, "UTF-8")
    }
}

JogoAlvoEstaAtivo() {
    alvos := Trim(Config["target_exes"])
    if (alvos == "" || !Config["hide_when_target_inactive"])
        return true

    try {
        processoAtivo := WinGetProcessName("A")
        listaAlvos := StrSplit(alvos, ",")
        for alvo in listaAlvos {
            alvoLimpo := Trim(alvo)
            if (alvoLimpo != "" && InStr(processoAtivo, alvoLimpo))
                return true
        }
        return false
    } catch {
        return true
    }
}

MonitorarFocoJogo() {
    alvos := Trim(Config["target_exes"])
    if (alvos == "" || !Config["hide_when_target_inactive"])
        return

    if (!JogoAlvoEstaAtivo()) {
        if (CardVisivel) {
            ; Esconde imediatamente se o jogo alvo perder o foco enquanto o card estava ativo
            OcultarCard()
        }
    }
}

; --------------------------------------------------------------------
; Comandos de Atalhos e Controle
; --------------------------------------------------------------------

AlternarPausa() {
    global EstaPausado
    EstaPausado := !EstaPausado

    if (EstaPausado) {
        OcultarCard()
        SetTimer(OcultarCard, 0)
        SetTimer(ExibirProximoCard, 0)
        ToolTip("MicroEstudo Overlay: PAUSADO`n(Pressione Ctrl+Alt+P para retomar)")
        SetTimer(() => ToolTip(), -2500)
    } else {
        ToolTip("MicroEstudo Overlay: RETOMADO")
        SetTimer(() => ToolTip(), -2000)
        ExibirProximoCard()
    }
}

ProximoCardManual() {
    if (EstaPausado)
        return

    SetTimer(OcultarCard, 0)
    SetTimer(ExibirProximoCard, 0)
    ExibirProximoCard()
}

OcultarCardAtual() {
    SetTimer(OcultarCard, 0)
    OcultarCard()
}

RecarregarConteudo() {
    ToolTip("MicroEstudo: Reprocessando conteúdo...")
    sucesso := ExecutarConversorPython()

    if (sucesso) {
        CarregarConfiguracoes()
        CarregarPosicao()
        CarregarCards()
        SincronizarProgressoComCards()
        CriarInterface()
        ToolTip("MicroEstudo: " . Cards.Length . " cards recarregados com sucesso!")
        SetTimer(() => ToolTip(), -3000)
        ProximoCardManual()
    } else {
        ToolTip("MicroEstudo: Erro ao reprocessar. Mantido o baralho atual.")
        SetTimer(() => ToolTip(), -4000)
    }
}

ExecutarConversorPython() {
    scriptPython := A_ScriptDir . "\preparar_conteudo.py"
    if !FileExist(scriptPython)
        return false

    iniPath := A_ScriptDir . "\config.ini"
    comandos := [
        'python "' . scriptPython . '" --config "' . iniPath . '"',
        'py -3 "' . scriptPython . '" --config "' . iniPath . '"',
        'py "' . scriptPython . '" --config "' . iniPath . '"'
    ]

    for cmd in comandos {
        try {
            codigoSaida := RunWait(cmd, A_ScriptDir, "Hide")
            if (codigoSaida == 0)
                return true
        } catch {
            continue
        }
    }
    return false
}

SairAplicativo() {
    SalvarProgresso()
    OcultarCard()
    ToolTip("MicroEstudo Overlay finalizado.")
    SetTimer(() => ToolTip(), -1500)
    Sleep(500)
    ExitApp()
}
