@echo off
rem DWH Navigator - tek tikla baslatma (Windows, LM Studio kurulu makine)
rem 1) calisan eski sunuculari durdurur  2) LM Studio sunucusunu acar  3) modelleri yukler
rem 4) arayuzu tarayicida acar
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

rem Eski kodla calisan sunucu kalmasin: bu klasorun tum `vsa serve` surecleri durdurulur.
echo [1/4] Calisan sunucular durduruluyor...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop_servers.ps1" -Port 8765
if errorlevel 1 ( pause & exit /b 1 )

rem Hakem modeli ayarlardan okunur; hakem bulutta ise yerelde yalniz embedding yuklenir.
for /f "usebackq delims=" %%m in (`.venv\Scripts\python -c "from vsa.config import load_settings as l; s=l(); print(s.llm.model if s.llm.enabled and s.llm.provider == 'local' else '')"`) do set CHAT_MODEL=%%m
rem Analist akisi (ADR-029) tum tablo katalogunu okur (~65k token): yerel model genis baglamla yuklenir.
set CHAT_CTX=8192
for /f "usebackq delims=" %%c in (`.venv\Scripts\python -c "from vsa.config import load_settings as l; print(98304 if l().analyst.enabled else 8192)"`) do set CHAT_CTX=%%c

if exist "%LMS%" (
  echo [2/4] LM Studio sunucusu baslatiliyor...
  "%LMS%" server start >nul 2>&1
  echo [3/4] Modeller yukleniyor: %EMBED_MODEL% %CHAT_MODEL%
  rem Zaten yukluyse tekrar yukleme (her calistirmada yeni bir kopya aciliyordu).
  "%LMS%" ps 2>nul | findstr /b /c:"%EMBED_MODEL% " >nul || "%LMS%" load %EMBED_MODEL% -y >nul 2>&1
  if defined CHAT_MODEL (
    echo       baglam: %CHAT_CTX% token
    "%LMS%" unload %CHAT_MODEL% >nul 2>&1
    "%LMS%" load %CHAT_MODEL% --context-length %CHAT_CTX% --gpu max -y >nul 2>&1
  )
) else (
  echo [i] LM Studio bulunamadi; uygulama LLM'siz ^(yalniz kural tabanli^) calisacak.
)

if not exist "data\index\meta.json" (
  echo [i] Indeks yok, kuruluyor...
  .venv\Scripts\vsa.exe index
)

echo [4/4] Arayuz: http://127.0.0.1:8765  (kapatmak icin bu pencerede Ctrl+C)
.venv\Scripts\vsa.exe serve --open
