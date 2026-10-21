# Morning second pass from a computer in Russia.
#
# GitHub's servers abroad cannot open some insurer sites (Согласие, sometimes
# Ренессанс). This script runs every morning from the owner's PC: it re-checks
# only those insurers, takes rules the owner saved by hand into the desktop
# folder «Новые правила КАСКО» and publishes the result. A changed rules file is
# pushed to data/incoming; GitHub analyses it (source-check.yml), so the PC needs
# no AI key. Runs in its own clone, never in a working copy.

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
    & $Python -m pip install -q -r requirements.txt

    # A changed file goes to data/incoming; pushing it starts the analysis on GitHub,
    # so no AI key is needed on this computer.
    & $Python scripts\check_sources.py --only-unavailable --inbox $Inbox --downloads data\incoming

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
