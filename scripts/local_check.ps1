# Morning second pass from a computer in Russia.
#
# GitHub's servers abroad cannot open some insurer sites (Согласие, sometimes
# Ренессанс). This script runs every morning from the owner's PC: it re-checks
# only those insurers, takes rules the owner saved by hand into the desktop
# folder «Новые правила КАСКО», updates answers the same way as the nightly
# job and publishes the result. Runs in its own clone, never in a working copy.

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$Git = "C:\Program Files\Git\cmd\git.exe"
$Python = Join-Path $Repo ".venv\Scripts\python.exe"
$Inbox = Join-Path ([Environment]::GetFolderPath("Desktop")) "Новые правила КАСКО"
$Log = Join-Path $Repo "work\local-check.log"
Set-Location $Repo
New-Item -ItemType Directory -Force (Join-Path $Repo "work") | Out-Null
Start-Transcript -Path $Log -Append | Out-Null
try {
    & $Git checkout -q main
    & $Git pull -q --ff-only origin main
    & $Python -m pip install -q -r requirements.txt anthropic pytest

    & $Python scripts\check_sources.py --only-unavailable --inbox $Inbox --downloads work\downloads
    $stamp = Get-Date -Format "yyyy-MM-dd"
    $summary = "data\auto-update-notes\$stamp-pc.md"
    & $Python scripts\auto_update.py --downloads work\downloads --summary $summary

    & $Git diff --quiet -- data/casco-comparison-master.json
    if ($LASTEXITCODE -ne 0) {
        & $Python -m pytest -q
        if ($LASTEXITCODE -ne 0) {
            & $Git checkout -- data/casco-comparison-master.json data/sources docs/source-urls.md
            Add-Content -Path $summary -Encoding UTF8 -Value "`n**Внимание:** после автообновления не прошли проверки сайта, новые ответы откатены."
        }
    }

    & $Git add -A -- data docs/source-urls.md
    & $Git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) {
        & $Git commit -q -m "Morning rules check from the owner PC"
        & $Git pull -q --rebase origin main
        & $Git push -q origin HEAD:main
    }
}
finally {
    Stop-Transcript | Out-Null
}
