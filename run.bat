@echo off
title Super Prospectador Paviani
echo =========================================================
echo       SUPER PROSPECTADOR PAVIANI - INICIANDO SISTEMA
echo =========================================================
echo.

cd /d "%~dp0"

:: Check if virtual env exists
if not exist venv (
    echo [INFO] Ambiente virtual nao encontrado. Criando venv...
    python -m venv venv
    if errorlevel 1 (
        echo [ERRO] Nao foi possivel criar o ambiente virtual. Verifique a instalacao do Python 3.
        pause
        exit /b 1
    )
)

echo [INFO] Ativando ambiente virtual...
:: call .\venv\Scripts\activate.bat

echo [INFO] Verificando dependencias...
.\venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERRO] Erro ao instalar dependencias do requirements.txt.
    pause
    exit /b 1
)

echo.
echo =========================================================
echo  [SUCESSO] Servidor ligando!
echo  O painel abrira automaticamente no seu navegador.
echo  Caso nao abra, acesse: http://127.0.0.1:5000/
echo =========================================================
echo.

:: Open browser after 2 seconds
timeout /t 2 /nobreak > NUL
start http://127.0.0.1:5000/

:: Run Flask server
.\venv\Scripts\python.exe app.py

pause
