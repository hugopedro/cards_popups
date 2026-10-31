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
    "remember_progress", 1,
    "cloze_enabled", 1,
    "cloze_reveal_seconds", 4,
    "highlight_keywords", 1,
    "interleave_topics", 1
)

; Estado do aplicativo
global Cards := []
global Progresso := Map()
global Excluidos := Map()
global UltimoCardId := ""
global UltimoAssunto := ""
global UltimoSubtema := ""
global EstaPausado := false
global CardVisivel := false
global OverlayGui := ""
global CtrlAssunto := ""
global CtrlTitulo := ""
global CtrlTexto := ""
global CtrlOrigem := ""
global CustomPos := ""
global CardAtual := ""
global BtnLixeira := ""
global EstaEmOclusao := false
global RichEditCarregado := false
global HBrushFundo := ""

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
A_TrayMenu.Add("Revelar Termo Oculto (Ctrl+Alt+Espaço)", (*) => RevelarClozeAtual())

; Hotkeys globais padrão
^!p::AlternarPausa()          ; Ctrl + Alt + P: Pausar / Retomar
^!n::ProximoCardManual()      ; Ctrl + Alt + N: Próximo card agora
^!x::ExcluirCardAtual()       ; Ctrl + Alt + X: Excluir card inútil
^!c::RedefinirPosicao()       ; Ctrl + Alt + C: Restaurar posição padrão
^!h::OcultarCardAtual()       ; Ctrl + Alt + H: Esconder card atual
^!Space::RevelarClozeAtual()  ; Ctrl + Alt + Espaço: Revelar termo/resposta oculta
^!r::RecarregarConteudo()     ; Ctrl + Alt + R: Reprocessar e recarregar
^!q::SairAplicativo()         ; Ctrl + Alt + Q: Sair e salvar

; Hotkey de revelação quando o card estiver com foco
#HotIf (OverlayGui != "" && WinActive("ahk_id " . OverlayGui.Hwnd))
Space::RevelarClozeAtual()    ; Espaço: Revelar termo ocluso quando overlay está ativo
#HotIf

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

    LerBool(secao, chave, padrao) {
        try {
            val := StrLower(Trim(IniRead(iniFile, secao, chave, padrao)))
            if (val = "1" || val = "true" || val = "yes" || val = "sim")
                return 1
            if (val = "0" || val = "false" || val = "no" || val = "nao")
                return 0
            num := Integer(val)
            return num ? 1 : 0
        } catch {
            return padrao
        }
    }

    Config["arquivo"] := LerStr("Conteudo", "arquivo", Config["arquivo"])
    Config["min_chars"] := LerInt("Conteudo", "min_chars", Config["min_chars"], 30, 400)
    Config["max_chars"] := LerInt("Conteudo", "max_chars", Config["max_chars"], 60, 600)
    Config["new_ratio"] := LerInt("Conteudo", "new_ratio", Config["new_ratio"], 0, 100)
    Config["interleave_topics"] := LerBool("Conteudo", "interleave_topics", Config["interleave_topics"])

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
    Config["cloze_enabled"] := LerBool("Exibicao", "cloze_enabled", Config["cloze_enabled"])
    Config["cloze_reveal_seconds"] := LerInt("Exibicao", "cloze_reveal_seconds", Config["cloze_reveal_seconds"], 1, 60)
    Config["highlight_keywords"] := LerBool("Exibicao", "highlight_keywords", Config["highlight_keywords"])

    Config["target_exes"] := LerStr("Contexto", "target_exes", Config["target_exes"])
    Config["hide_when_target_inactive"] := LerInt("Contexto", "hide_when_target_inactive", Config["hide_when_target_inactive"], 0, 1)
    Config["remember_progress"] := LerInt("Estado", "remember_progress", Config["remember_progress"], 0, 1)
    AtualizarBrushFundo()
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
    global OverlayGui, RichEditCarregado
    try {
        hModule := DllCall("LoadLibrary", "Str", "msftedit.dll", "Ptr")
        if (hModule != 0)
            RichEditCarregado := true
    } catch {
        RichEditCarregado := false
    }

    AtualizarBrushFundo()

    ; Garante que nenhum controle pinte com fundo branco padrão
    OnMessage(0x0138, AoCtlColorOverlay) ; WM_CTLCOLORSTATIC
    OnMessage(0x0133, AoCtlColorOverlay) ; WM_CTLCOLOREDIT

    if (!Config["click_through"]) {
        OnMessage(0x0201, ArrastoJanelaAHK) ; WM_LBUTTONDOWN -> arrastar e revelar
        OnMessage(0x0200, AoMoverMouseOverlay) ; WM_MOUSEMOVE -> revelar ao passar o mouse
        OnMessage(0x0020, AoSetCursorOverlay) ; WM_SETCURSOR -> cursor de seta sobre o texto
    }
}

AtualizarBrushFundo() {
    global HBrushFundo, Config
    if (HBrushFundo != "") {
        try DllCall("DeleteObject", "Ptr", HBrushFundo)
    }
    hexColor := Config["bg_color"]
    r := Integer("0x" . SubStr(hexColor, 1, 2))
    g := Integer("0x" . SubStr(hexColor, 3, 2))
    b := Integer("0x" . SubStr(hexColor, 5, 2))
    bgr := (b << 16) | (g << 8) | r
    HBrushFundo := DllCall("CreateSolidBrush", "UInt", bgr, "Ptr")
}

AoCtlColorOverlay(wParam, lParam, msg, hwnd) {
    global HBrushFundo, Config
    hexColor := Config["bg_color"]
    r := Integer("0x" . SubStr(hexColor, 1, 2))
    g := Integer("0x" . SubStr(hexColor, 3, 2))
    b := Integer("0x" . SubStr(hexColor, 5, 2))
    bgr := (b << 16) | (g << 8) | r
    DllCall("SetBkColor", "Ptr", wParam, "UInt", bgr)
    return HBrushFundo
}

AoSetCursorOverlay(wParam, lParam, msg, hwnd) {
    global CtrlTexto
    if (CtrlTexto != "" && (hwnd == CtrlTexto.Hwnd || (IsObject(CtrlTexto) && hwnd == CtrlTexto))) {
        DllCall("SetCursor", "Ptr", DllCall("LoadCursor", "Ptr", 0, "Int", 32512, "Ptr")) ; IDC_ARROW
        return true
    }
}

AoMoverMouseOverlay(wParam, lParam, msg, hwnd) {
    global OverlayGui, EstaEmOclusao
    if (EstaEmOclusao && OverlayGui != "") {
        if (hwnd == OverlayGui.Hwnd || DllCall("IsChild", "Ptr", OverlayGui.Hwnd, "Ptr", hwnd)) {
            RevelarClozeAtual()
        }
    }
}

DefinirCorFundoRichEdit(ctrl, hexColor) {
    r := Integer("0x" . SubStr(hexColor, 1, 2))
    g := Integer("0x" . SubStr(hexColor, 3, 2))
    b := Integer("0x" . SubStr(hexColor, 5, 2))
    bgr := (b << 16) | (g << 8) | r
    hCtrl := (ctrl is Integer) ? ctrl : (IsObject(ctrl) && ctrl.HasProp("Hwnd") ? ctrl.Hwnd : ctrl)
    DllCall("SendMessageW", "Ptr", hCtrl, "UInt", 0x0443, "UPtr", 0, "UPtr", bgr, "Ptr") ; EM_SETBKGNDCOLOR
}

AtualizarRichEditText(ctrl, rtfText) {
    DefinirCorFundoRichEdit(ctrl, Config["bg_color"])
    st := Buffer(8, 0)
    NumPut("UInt", 0, st, 0)
    NumPut("UInt", 1200, st, 4)
    hCtrl := (ctrl is Integer) ? ctrl : (IsObject(ctrl) && ctrl.HasProp("Hwnd") ? ctrl.Hwnd : ctrl)
    DllCall("SendMessageW", "Ptr", hCtrl, "UInt", 0x0461, "Ptr", st.Ptr, "WStr", rtfText, "Ptr") ; EM_SETTEXTEX
    DllCall("SendMessageW", "Ptr", hCtrl, "UInt", 0x00B1, "Ptr", -1, "Ptr", -1, "Ptr") ; EM_SETSEL
    DllCall("HideCaret", "Ptr", hCtrl)
    DefinirCorFundoRichEdit(ctrl, Config["bg_color"])
}

RegexEscape(str) {
    return RegExReplace(str, "([\\.\$\^\*\+\?\(\)\[\]\{\}\|])", "\$1")
}

EscaparRTF(str) {
    str := StrReplace(str, "\", "\\")
    str := StrReplace(str, "{", "\{")
    str := StrReplace(str, "}", "\}")
    str := StrReplace(str, "`r`n", "\line ")
    str := StrReplace(str, "`n", "\line ")
    res := ""
    Loop Parse str {
        code := Ord(A_LoopField)
        if (code > 32767) {
            res .= "\u" . (code - 65536) . " "
        } else if (code > 127) {
            res .= "\u" . code . " "
        } else {
            res .= A_LoopField
        }
    }
    return res
}

GerarRTF(textoBruto, titulo, emOclusao, destacarKeywords, fontSize, &teveCloze) {
    textoProcessado := textoBruto
    teveCloze := false
    clozes := []

    ; 1. Cloze Manual: extrai todas as tags {{...}}
    while RegExMatch(textoProcessado, "\{\{([^}]+)\}\}", &mManual) {
        teveCloze := true
        idx := clozes.Length
        clozes.Push(mManual[1])
        textoProcessado := RegExReplace(textoProcessado, "\{\{[^}]+\}\}", Chr(3) . "CLOZE_" . idx . Chr(3), , 1)
    }

    ; 2. Cloze Inteligente para cards de conceito/definição (se não houver marcação manual)
    if (!teveCloze && Config["cloze_enabled"]) {
        titLimpo := Trim(RegExReplace(titulo, "^\d+[\.\)]\s*", ""))
        mColon := ""
        mTit := ""
        mDef := ""

        if RegExMatch(textoProcessado, "(*UCP)^([^:]{3,40}):\s+(.+)$", &mColon) {
            termoC := Trim(mColon[1])
            if !RegExMatch(termoC, "i)^(?:\*+|_+)?(?:ex|exemplo|exemplos|obs|nota|art\.?)\b") {
                teveCloze := true
                clozes.Push(termoC)
                textoProcessado := Chr(3) . "CLOZE_0" . Chr(3) . ": " . mColon[2]
            }
        }
        else if (StrLen(titLimpo) >= 4 && RegExMatch(textoProcessado, "i)(*UCP)\b(" . RegexEscape(titLimpo) . ")\b", &mTit)) {
            teveCloze := true
            clozes.Push(mTit[1])
            textoProcessado := RegExReplace(textoProcessado, "i)(*UCP)\b" . RegexEscape(titLimpo) . "\b", Chr(3) . "CLOZE_0" . Chr(3), , 1)
        }
        else if RegExMatch(textoProcessado, "i)(*UCP)^((?:O|A|Os|As|Um|Uma)?\s*[\p{L}\w\-]+(?:\s+[\p{L}\w\-]+){0,3})\s+(é|são|consiste em|compreende)\b", &mDef) {
            teveCloze := true
            clozes.Push(Trim(mDef[1]))
            resto := SubStr(textoProcessado, StrLen(mDef[0]) + 1)
            textoProcessado := Chr(3) . "CLOZE_0" . Chr(3) . " " . mDef[2] . resto
        }
    }

    ; 3. Destaque de Prazos e Vedações (somente fora dos clozes protegidos)
    if (destacarKeywords) {
        padraoPrazos := "i)(*UCP)\b(?:\d+|(?:um|dois|três|tres|quatro|cinco|seis|sete|oito|nove|dez|quinze|vinte|trinta|quarenta|cinquenta|sessenta|noventa|cento e vinte))\s*(?:dias\s+úteis|dias|dia|meses|mês|mes|anos|ano|horas|hora|minutos|minuto)\b"
        padraoPrazos .= "|\b(?:prazos?\s+prescriciona(?:l|is)|prazos?\s+decadencia(?:l|is)|prazos?\s+recursais?|quinquênio|triênio|biênio|prescrição\s+quinquenal)\b"

        padraoVedacoes := "i)(*UCP)\b(?:vedado|vedada|vedados|vedadas|vedação|vedações|proibido|proibida|proibidos|proibidas|proibição|proibições|salvo\s+se|salvo|não\s+cabe|nao\s+cabe|não\s+caberá|não\s+cabem|nulo|nula|nulos|nulas|nulidade|nulidades|inconstitucional|inconstitucionais|inconstitucionalidade|exceção|exceções|excecao|excecoes|defeso|defesa|indeferimento|indeferido|indeferida|imprescritível|imprescritibilidade|indelegável|indelegabilidade|irrenunciável|irrenunciabilidade|inafastável)\b"

        textoProcessado := RegExReplace(textoProcessado, padraoPrazos, Chr(1) . "PRAZO:$0" . Chr(2))
        textoProcessado := RegExReplace(textoProcessado, padraoVedacoes, Chr(1) . "VEDACAO:$0" . Chr(2))
    }

    ; 4. Substituição das tags de Cloze pelo marcador formatado
    Loop clozes.Length {
        idx := A_Index - 1
        termoCloze := clozes[A_Index]
        placeholder := Chr(3) . "CLOZE_" . idx . Chr(3)
        if (emOclusao) {
            textoProcessado := StrReplace(textoProcessado, placeholder, Chr(1) . "CLOZE_PH" . Chr(2))
        } else {
            textoProcessado := StrReplace(textoProcessado, placeholder, Chr(1) . "CLOZE_REV:" . termoCloze . Chr(2))
        }
    }

    fsHalf := Round(fontSize * 2)
    header := "{\rtf1\ansi\deff0{\fonttbl{\f0\fswiss\fprq2\fcharset0 Segoe UI;}}"
    header .= "{\colortbl;\red228\green237\blue231;\red255\green210\blue102;\red255\green122\blue122;\red126\green200\blue227;}"
    header .= "\f0\fs" . fsHalf . "\uc0\cf1 "

    rtfCorpo := ""
    pos := 1
    padraoTags := "\x01([A-Z_]+)(?::([^\x02]*))?\x02"

    while RegExMatch(textoProcessado, padraoTags, &match, pos) {
        partePre := SubStr(textoProcessado, pos, match.Pos - pos)
        rtfCorpo .= EscaparRTF(partePre)

        tagTipo := match[1]
        tagVal := match[2]

        if (tagTipo == "CLOZE_PH") {
            rtfCorpo .= "\b\cf4 [...]\b0\cf1 "
        } else if (tagTipo == "CLOZE_REV") {
            rtfCorpo .= "\b\ul\cf4 " . EscaparRTF(tagVal) . "\ul0\b0\cf1 "
        } else if (tagTipo == "PRAZO") {
            rtfCorpo .= "\b\cf2 " . EscaparRTF(tagVal) . "\b0\cf1 "
        } else if (tagTipo == "VEDACAO") {
            rtfCorpo .= "\b\cf3 " . EscaparRTF(tagVal) . "\b0\cf1 "
        }

        pos := match.Pos + match.Len
    }
    rtfCorpo .= EscaparRTF(SubStr(textoProcessado, pos))

    return header . rtfCorpo . "}"
}

RevelarClozeAtual() {
    global EstaEmOclusao, CtrlTexto, CardAtual, Config, CardVisivel, RichEditCarregado
    if (!EstaEmOclusao || CardAtual == "" || CtrlTexto == "" || !CardVisivel)
        return

    SetTimer(RevelarClozeAtual, 0)
    EstaEmOclusao := false

    if (RichEditCarregado) {
        teveCloze := false
        rtfRevelado := GerarRTF(CardAtual["texto"], CardAtual["titulo"], false, Config["highlight_keywords"], Config["font_size"], &teveCloze)
        AtualizarRichEditText(CtrlTexto, rtfRevelado)
    } else {
        textoLimpo := RegExReplace(CardAtual["texto"], "\{\{([^}]+)\}\}", "$1")
        try CtrlTexto.Value := textoLimpo
    }
}

RenderizarCard(card) {
    global OverlayGui, Config, CustomPos, CtrlAssunto, CtrlTitulo, CtrlTexto, CtrlOrigem, BtnLixeira, CardAtual, EstaEmOclusao, RichEditCarregado

    SetTimer(RevelarClozeAtual, 0)
    EstaEmOclusao := false
    CardAtual := card

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

    ; Cabeçalho: Assunto / Subtema e Botão de Lixeira (sem truncamento por 75 caracteres)
    if (!Config["click_through"]) {
        wBtn := 22
        wAssunto := wBox - wBtn - 8
        OverlayGui.SetFont("s" . fSub . " bold c88A89A", "Segoe UI")
        CtrlAssunto := OverlayGui.Add("Text", "xm ym +Disabled w" . wAssunto, assuntoTxt)

        OverlayGui.SetFont("s10 bold c88A89A", "Segoe UI")
        BtnLixeira := OverlayGui.Add("Text", "x" . (wBox + 16 - wBtn) . " y12 w" . wBtn . " h18 Center +0x200 BackgroundTrans", "🗑")
        BtnLixeira.OnEvent("Click", (*) => ExcluirCardAtual())

        CtrlAssunto.GetPos(&ax, &ay, &aw, &ah)
        yTit := Max(ay + ah + 4, 12 + 18 + 4)
    } else {
        OverlayGui.SetFont("s" . fSub . " bold c88A89A", "Segoe UI")
        CtrlAssunto := OverlayGui.Add("Text", "xm ym +Disabled +E0x20 w" . wBox, assuntoTxt)
        CtrlAssunto.GetPos(&ax, &ay, &aw, &ah)
        yTit := ay + ah + 4
    }

    ; Título em destaque (posicionado logo após o cabeçalho completo, permite quebras de linha sem truncamento)
    OverlayGui.SetFont("s" . fTit . " bold cFFFFFF", "Segoe UI")
    CtrlTitulo := OverlayGui.Add("Text", "xm y" . yTit . " +Disabled w" . wBox, card["titulo"])

    ; Texto da microlição com auto-dimensionamento exato e suporte a RichEdit e Cloze
    emOclusao := Config["cloze_enabled"] ? true : false
    teveCloze := false

    if (RichEditCarregado) {
        ; Mede altura necessária utilizando label invisível com mesma fonte e largura
        OverlayGui.SetFont("s" . fSize . " norm cE4EDE7", "Segoe UI")
        dummyMedidor := OverlayGui.Add("Text", "xm y+6 +Hidden w" . wBox, card["texto"])

        OverlayGui.Show("AutoSize Hide")
        dummyMedidor.GetPos(&tx, &ty, &tw, &th)
        th := Max(th + 6, 30)
        dummyMedidor.Visible := false

        rtfConteudo := GerarRTF(card["texto"], card["titulo"], emOclusao, Config["highlight_keywords"], fSize, &teveCloze)
        EstaEmOclusao := teveCloze

        ; Adiciona controle RichEdit 5.0 (multiline, sem borda, somente leitura — NÃO usar +Disabled para manter o fundo escuro)
        CtrlTexto := OverlayGui.Add("Custom", "x" . tx . " y" . ty . " w" . tw . " h" . th . " ClassRICHEDIT50W +0x0004 +ReadOnly -Border -HScroll -VScroll")
        DllCall("SendMessageW", "Ptr", CtrlTexto.Hwnd, "UInt", 0x00D3, "UPtr", 3, "UPtr", 0, "Ptr") ; EM_SETMARGINS
        AtualizarRichEditText(CtrlTexto, rtfConteudo)

        ; Rodapé discreto com origem posicionado logo após o RichEdit
        OverlayGui.SetFont("s" . (fSub - 0.5) . " c5E7A6E", "Segoe UI")
        CtrlOrigem := OverlayGui.Add("Text", "x" . tx . " y" . (ty + th + 6) . " +Disabled w" . wBox . " r1", origemTxt)

        ; Atualiza dimensionamento da janela considerando o rodapé e o RichEdit completo
        OverlayGui.Show("AutoSize Hide")

        if (EstaEmOclusao) {
            SetTimer(RevelarClozeAtual, -(Config["cloze_reveal_seconds"] * 1000))
        }
    } else {
        textoFallback := card["texto"]
        if (emOclusao && InStr(textoFallback, "{{") && InStr(textoFallback, "}}")) {
            textoFallback := RegExReplace(textoFallback, "\{\{[^}]+\}\}", "[...]")
            EstaEmOclusao := true
        } else if (emOclusao && Config["cloze_enabled"]) {
            titLimpo := Trim(RegExReplace(card["titulo"], "^\d+[\.\)]\s*", ""))
            if RegExMatch(textoFallback, "(*UCP)^([^:]{3,40}):\s+(.+)$", &mColon) && !RegExMatch(mColon[1], "i)^(?:\*+|_+)?(?:ex|exemplo|exemplos|obs|nota|art\.?)\b") {
                textoFallback := "[...]: " . mColon[2]
                EstaEmOclusao := true
            } else if (StrLen(titLimpo) >= 4 && RegExMatch(textoFallback, "i)(*UCP)\b(" . RegexEscape(titLimpo) . ")\b", &mTit)) {
                textoFallback := RegExReplace(textoFallback, "i)(*UCP)\b" . RegexEscape(titLimpo) . "\b", "[...]", , 1)
                EstaEmOclusao := true
            } else if RegExMatch(textoFallback, "i)(*UCP)^((?:O|A|Os|As|Um|Uma)?\s*[\p{L}\w\-]+(?:\s+[\p{L}\w\-]+){0,3})\s+(é|são|consiste em|compreende)\b", &mDef) {
                resto := SubStr(textoFallback, StrLen(mDef[0]) + 1)
                textoFallback := "[...] " . mDef[2] . resto
                EstaEmOclusao := true
            }
        } else {
            textoFallback := RegExReplace(textoFallback, "\{\{([^}]+)\}\}", "$1")
        }
        OverlayGui.SetFont("s" . fSize . " norm cE4EDE7", "Segoe UI")
        CtrlTexto := OverlayGui.Add("Text", "xm y+6 +Disabled w" . wBox, textoFallback)

        OverlayGui.SetFont("s" . (fSub - 0.5) . " c5E7A6E", "Segoe UI")
        CtrlOrigem := OverlayGui.Add("Text", "xm y+6 +Disabled w" . wBox . " r1", origemTxt)

        OverlayGui.Show("AutoSize Hide")

        if (EstaEmOclusao) {
            SetTimer(RevelarClozeAtual, -(Config["cloze_reveal_seconds"] * 1000))
        }
    }

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
        jsonContent := "{`n  `"x`": " . x . ",`n  `"y`": " . y . "`n}`n"
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
    global OverlayGui, Config, CustomPos, EstaEmOclusao, BtnLixeira
    if (Config["click_through"])
        return
    if (OverlayGui != "") {
        pertence := (hwnd == OverlayGui.Hwnd || DllCall("IsChild", "Ptr", OverlayGui.Hwnd, "Ptr", hwnd))
        if (!pertence)
            return
        if (BtnLixeira != "" && hwnd == BtnLixeira.Hwnd)
            return

        if (EstaEmOclusao)
            RevelarClozeAtual()
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
    global Cards, Progresso, UltimoCardId, UltimoAssunto, UltimoSubtema, Config
    if (Cards.Length == 0)
        return ""

    if (Cards.Length == 1)
        return Cards[1]

    ; 1. Separar cards não vistos e já vistos
    naoVistos := []
    jaVistos := []
    for idx, c in Cards {
        cId := c["id"]
        if (!Progresso.Has(cId) || Progresso[cId]["exibicoes"] == 0) {
            naoVistos.Push(c)
        } else {
            jaVistos.Push(c)
        }
    }

    sorteio := Random(1, 100)
    novoRatio := Config["new_ratio"]
    intercalar := Config["interleave_topics"]

    ; Decide se busca card novo ou revisão
    queroNovo := (naoVistos.Length > 0) && (jaVistos.Length == 0 || sorteio <= novoRatio || UltimoCardId == "")

    cardEscolhido := ""

    if (queroNovo) {
        if (intercalar) {
            ; Agrupa os cards não vistos por assunto (preservando ordem pedagógica interna de cada tópico)
            assuntosMap := Map()
            assuntosLista := []
            for c in naoVistos {
                ass := c["assunto"]
                if (!assuntosMap.Has(ass)) {
                    assuntosMap[ass] := []
                    assuntosLista.Push(ass)
                }
                assuntosMap[ass].Push(c)
            }

            ; Filtra assuntos diferentes do último assunto exibido para evitar repetição do mesmo tema
            candidatosAssuntos := []
            for ass in assuntosLista {
                if (ass != UltimoAssunto) {
                    candidatosAssuntos.Push(ass)
                }
            }
            if (candidatosAssuntos.Length == 0)
                candidatosAssuntos := assuntosLista

            ; Sorteia um assunto dentre os disponíveis
            idxAssuntoSorteado := Random(1, candidatosAssuntos.Length)
            assuntoEscolhido := candidatosAssuntos[idxAssuntoSorteado]

            ; Pega o próximo card novo desse assunto
            cardsDoAssunto := assuntosMap[assuntoEscolhido]
            cardEscolhido := cardsDoAssunto[1]

            ; Se houver mais de um card no assunto e o primeiro coincidir com UltimoSubtema, tenta alternar
            if (cardsDoAssunto.Length > 1 && cardEscolhido["subtema"] == UltimoSubtema && UltimoSubtema != "") {
                for cCand in cardsDoAssunto {
                    if (cCand["subtema"] != UltimoSubtema) {
                        cardEscolhido := cCand
                        break
                    }
                }
            }
        } else {
            cardEscolhido := naoVistos[1]
        }
    } else {
        ; 2. Revisão real: escolher exclusivamente dentre os JÁ VISTOS
        candidatos := []
        for c in jaVistos {
            if (c["id"] != UltimoCardId) {
                candidatos.Push(c)
            }
        }
        if (candidatos.Length == 0)
            candidatos := (jaVistos.Length > 0 ? jaVistos : Cards)

        ; Se intercalação ativa, prefere cards de assunto diferente do último
        if (intercalar) {
            candidatosOutros := []
            for c in candidatos {
                if (c["assunto"] != UltimoAssunto) {
                    candidatosOutros.Push(c)
                }
            }
            if (candidatosOutros.Length > 0)
                candidatos := candidatosOutros
        }

        ; Encontra o menor número de exibições
        menorExib := 999999
        for c in candidatos {
            cId := c["id"]
            exib := Progresso.Has(cId) ? Progresso[cId]["exibicoes"] : 0
            if (exib < menorExib) {
                menorExib := exib
            }
        }

        ; Filtra os cards empatados na menor exibição
        menosExibidos := []
        for c in candidatos {
            cId := c["id"]
            exib := Progresso.Has(cId) ? Progresso[cId]["exibicoes"] : 0
            if (exib == menorExib) {
                menosExibidos.Push(c)
            }
        }

        ; Desempata pelo mais antigo (menor timestamp 'ultima')
        menorTimestamp := 2147483647000
        for c in menosExibidos {
            cId := c["id"]
            ts := Progresso.Has(cId) ? Progresso[cId]["ultima"] : 0
            if (ts < menorTimestamp) {
                menorTimestamp := ts
            }
        }
        maisAntigos := []
        for c in menosExibidos {
            cId := c["id"]
            ts := Progresso.Has(cId) ? Progresso[cId]["ultima"] : 0
            if (ts == menorTimestamp) {
                maisAntigos.Push(c)
            }
        }

        if (maisAntigos.Length > 0) {
            idxSort := Random(1, maisAntigos.Length)
            cardEscolhido := maisAntigos[idxSort]
        } else {
            cardEscolhido := candidatos[1]
        }
    }

    if (cardEscolhido != "") {
        UltimoCardId := cardEscolhido["id"]
        UltimoAssunto := cardEscolhido["assunto"]
        UltimoSubtema := cardEscolhido["subtema"]
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
    UltimoAssunto := card["assunto"]
    UltimoSubtema := card["subtema"]

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
    global CardVisivel, OverlayGui, EstaEmOclusao
    SetTimer(RevelarClozeAtual, 0)
    EstaEmOclusao := false
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
