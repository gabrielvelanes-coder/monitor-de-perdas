@echo off
REM Monitor de Perdas — clique duas vezes neste arquivo para abrir o app.
cd /d "%~dp0"
echo Iniciando o Monitor de Perdas...
echo Vai abrir no navegador em http://localhost:8501
echo Feche esta janela preta para parar o app.
streamlit run app.py --server.port 8501
pause
