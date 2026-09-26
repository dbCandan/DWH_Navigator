@echo off
rem DWH Navigator - tek tikla baslatma (Windows, LM Studio kurulu makine)
rem 1) LM Studio sunucusunu acar  2) modelleri yukler  3) arayuzu tarayicida acar
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set LMS=%USERPROFILE%\.lmstudio\bin\lms.exe
set CHAT_MODEL=
set EMBED_MODEL=text-embedding-bge-m3

if not exist ".venv\Scripts\vsa.exe" (
  echo [!] Sanal ortam yok. Once: python -m venv .venv ^&^& .venv\Scripts\pip install -e .
  pause & exit /b 1
)

rem Hakem modeli ayarlardan okunur; hakem bulutta ise yerelde yalniz embedding yuklenir.
for /f "usebackq delims=" %%m in (`.venv\Scripts\python -c "from vsa.config import load_settings as l; s=l(); print(s.llm.model if s.llm.enabled and s.llm.provider == 'local' else '')"`) do set CHAT_MODEL=%%m

if exist "%LMS%" (
  echo [1/3] LM Studio sunucusu baslatiliyor...
  "%LMS%" server start >nul 2>&1
  echo [2/3] Modeller yukleniyor: %EMBED_MODEL% %CHAT_MODEL%
  "%LMS%" load %EMBED_MODEL% -y >nul 2>&1
  if defined CHAT_MODEL "%LMS%" load %CHAT_MODEL% --context-length 8192 --gpu max -y >nul 2>&1
) else (
  echo [i] LM Studio bulunamadi; uygulama LLM'siz ^(yalniz kural tabanli^) calisacak.
)

if not exist "data\index\meta.json" (
  echo [i] Indeks yok, kuruluyor...
  .venv\Scripts\vsa.exe index
)

echo [3/3] Arayuz: http://127.0.0.1:8765  (kapatmak icin bu pencerede Ctrl+C)
.venv\Scripts\vsa.exe serve --open
