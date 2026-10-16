@echo off
chcp 65001 >nul
title MicroEstudo Overlay - Inicializador

echo ======================================================================
echo           MICROESTUDO OVERLAY — APRENDIZAGEM EM SEGUNDO PLANO
echo ======================================================================
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: 1. Verificacao do Python 3
where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "PY_CMD=python"
    goto PYTHON_OK
)

where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "PY_CMD=py -3"
    goto PYTHON_OK
)

echo [ERRO] Python 3 nao foi detectado no sistema!
echo Para executar este aplicativo, instale o Python 3 oficial:
echo   - Download: https://www.python.org/downloads/windows/
echo   - Certifique-se de marcar a opcao "Add Python to PATH" durante a instalacao.
echo.
pause
exit /b 1

:PYTHON_OK
echo [+] Python detectado:
%PY_CMD% --version
echo.

:: 2. Verificacao do AutoHotkey v2
set "AHK_EXE="
where AutoHotkey64.exe >nul 2>nul
if %ERRORLEVEL% equ 0 set "AHK_EXE=AutoHotkey64.exe"

if not defined AHK_EXE (
    where AutoHotkey.exe >nul 2>nul
    if %ERRORLEVEL% equ 0 set "AHK_EXE=AutoHotkey.exe"
)

if not defined AHK_EXE (
    if exist "%ProgramFiles%\AutoHotkey\v2\AutoHotkey64.exe" (
        set "AHK_EXE=%ProgramFiles%\AutoHotkey\v2\AutoHotkey64.exe"
    ) else if exist "%ProgramFiles%\AutoHotkey\v2\AutoHotkey32.exe" (
        set "AHK_EXE=%ProgramFiles%\AutoHotkey\v2\AutoHotkey32.exe"
    ) else if exist "%ProgramFiles%\AutoHotkey\AutoHotkey64.exe" (
        set "AHK_EXE=%ProgramFiles%\AutoHotkey\AutoHotkey64.exe"
    ) else if exist "%ProgramFiles%\AutoHotkey\AutoHotkey.exe" (
        set "AHK_EXE=%ProgramFiles%\AutoHotkey\AutoHotkey.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\AutoHotkey\v2\AutoHotkey64.exe" (
        set "AHK_EXE=%LOCALAPPDATA%\Programs\AutoHotkey\v2\AutoHotkey64.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\AutoHotkey\v2\AutoHotkey32.exe" (
        set "AHK_EXE=%LOCALAPPDATA%\Programs\AutoHotkey\v2\AutoHotkey32.exe"
    ) else if exist "%ProgramFiles(x86)%\AutoHotkey\v2\AutoHotkey32.exe" (
        set "AHK_EXE=%ProgramFiles(x86)%\AutoHotkey\v2\AutoHotkey32.exe"
    )
)

if not defined AHK_EXE (
    echo [ERRO] AutoHotkey v2 nao foi encontrado no sistema!
    echo Para executar o overlay transparente sobre os jogos, instale o AutoHotkey v2:
    echo   - Download oficial: https://www.autohotkey.com/
    echo   - Selecione a versao "v2" durante o download.
    echo.
    pause
    exit /b 2
)

echo [+] AutoHotkey detectado: "%AHK_EXE%"
echo.

:: 3. Conversao do conteudo Markdown em Cards
echo [+] Preparando microlicoes a partir do Markdown...
%PY_CMD% "%SCRIPT_DIR%preparar_conteudo.py" --config "%SCRIPT_DIR%config.ini"

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERRO] Falha ao processar o conteudo Markdown.
    echo Verifique o relatorio de erro ou a sintaxe do arquivo de conteudo.
    echo.
    pause
    exit /b 3
)

echo.
echo [+] Conteudo processado com sucesso!
echo [+] Iniciando overlay sobreposto aos jogos...
echo [+] Atalhos globais disponiveis:
echo     Ctrl + Alt + P : Pausar / Retomar exibicoes
echo     Ctrl + Alt + N : Proximo card imediatamente
echo     Ctrl + Alt + H : Ocultar card atual
echo     Ctrl + Alt + R : Reprocessar conteudo e recarregar
echo     Ctrl + Alt + Q : Sair do aplicativo
echo.

start "" "%AHK_EXE%" "%SCRIPT_DIR%overlay.ahk"

echo [+] Overlay em execucao em segundo plano.
timeout /t 4 >nul
exit /b 0
