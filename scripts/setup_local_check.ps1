# One-time setup of the morning check on the owner's PC (see scripts/local_check.ps1).
# Creates a separate clone, its Python environment, the desktop folder for rules
# downloaded by hand and a Windows Task Scheduler task at 06:30 every day.

$ErrorActionPreference = "Stop"
$Git = "C:\Program Files\Git\cmd\git.exe"
$Clone = Join-Path $env:USERPROFILE "insurance-comparator-auto"
$Python = Join-Path $env:LOCALAPPDATA "Python\pythoncore-3.14-64\python.exe"

if (-not (Test-Path $Clone)) {
    & $Git clone -q https://github.com/vilvetti-cloud/insurance-comparator.git $Clone
}
if (-not (Test-Path (Join-Path $Clone ".venv"))) {
    & $Python -m venv (Join-Path $Clone ".venv")
}
& (Join-Path $Clone ".venv\Scripts\python.exe") -m pip install -q -r (Join-Path $Clone "requirements.txt") anthropic pytest

# Folder per insurer for rules downloaded by hand.
$Inbox = Join-Path ([Environment]::GetFolderPath("Desktop")) "Новые правила КАСКО"
$Names = "РЕСО-Гарантия","ВСК","Ингосстрах","Ренессанс Страхование","АльфаСтрахование","Согласие",
         "Росгосстрах","Т-Страхование","СберСтрахование","Совкомбанк Страхование","Югория"
foreach ($name in $Names) { New-Item -ItemType Directory -Force (Join-Path $Inbox $name) | Out-Null }
Set-Content -Encoding UTF8 -Path (Join-Path $Inbox "Как пользоваться.txt") -Value @"
Если сайт страховой не даёт проверить правила автоматически (например, Югория),
скачайте файл правил КАСКО с её сайта и положите его в папку с названием компании.
Утренняя проверка сама сравнит его с прежними правилами и при необходимости обновит ответы на сайте.
"@

$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Clone\scripts\local_check.ps1`""
$Trigger = New-ScheduledTaskTrigger -Daily -At "06:30"
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName "Insurance comparator morning check" -Action $Action -Trigger $Trigger `
    -Settings $Settings -Description "Проверка правил КАСКО с российского адреса (Согласие, Ренессанс) и разбор файлов из папки «Новые правила КАСКО»." -Force | Out-Null

Write-Host "Готово: копия $Clone, папка $Inbox, задача в планировщике на 06:30."
