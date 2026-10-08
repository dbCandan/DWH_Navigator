@echo off
rem DWH Navigator - tek tikla baslatma (Windows)
rem 1) calisan eski sunuculari durdurur  2) arayuzu tarayicida acar (indeks yoksa once kurulur)
rem Sohbet modeli bu makinede degil, DGX Spark sunucularinda calisir;
rem baglanti Yonetim -> Yapay zeka sayfasindan yapilir (ADR-032).
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8

if not exist ".venv\Scripts\vsa.exe" (
  echo [!] Sanal ortam yok. Once: python -m venv .venv ^&^& .venv\Scripts\pip install -e .
  pause & exit /b 1
)

rem Eski kodla calisan sunucu kalmasin: bu klasorun tum `vsa serve` surecleri durdurulur.
echo [1/2] Calisan sunucular durduruluyor...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop_servers.ps1" -Port 8765
if errorlevel 1 ( pause & exit /b 1 )

echo [2/2] Arayuz: http://127.0.0.1:8765  (kapatmak icin bu pencerede Ctrl+C)
echo       Model baglantisi: http://127.0.0.1:8765/admin -^> Yapay zeka
.venv\Scripts\vsa.exe serve --open
