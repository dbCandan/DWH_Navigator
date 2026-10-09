# Stops every running DWH Navigator web server (`vsa serve`) of this folder, and whatever
# still listens on the app's port, so baslat.bat always starts the current code.
# Other vsa commands (index, ask, eval) are left alone.
param([int]$Port = 8765)

$ErrorActionPreference = "SilentlyContinue"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

# vsa.exe starts a chain of processes (launcher -> venv python -> base python); each one's
# command line names "vsa ... serve", and each one's executable or arguments point here.
$servers = @(Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -match 'vsa(\.exe)?"?\s+serve\b' -and
    ("$($_.ExecutablePath) $($_.CommandLine)").IndexOf($root, [StringComparison]::OrdinalIgnoreCase) -ge 0
})
# A server of this app started some other way still holds the port.
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port | ForEach-Object {
    Get-CimInstance Win32_Process -Filter "ProcessId = $($_.OwningProcess)"
} | Where-Object { $_.Name -match '^(python|pythonw|vsa)(\.exe)?$' })

$targets = @($servers + $listeners | Sort-Object ProcessId -Unique)
if ($targets.Count -eq 0) {
    Write-Host "      calisan sunucu yok"
    exit 0
}
foreach ($p in $targets) {
    Stop-Process -Id $p.ProcessId -Force
    Write-Host ("      durduruldu: PID {0} ({1})" -f $p.ProcessId, $p.Name)
}

# Wait for the port to be released before the new server binds it.
for ($i = 0; $i -lt 20; $i++) {
    if (-not (Get-NetTCPConnection -State Listen -LocalPort $Port)) { exit 0 }
    Start-Sleep -Milliseconds 500
}
Write-Host "[!] Port $Port hala dolu; baska bir uygulama kullaniyor olabilir."
exit 1
