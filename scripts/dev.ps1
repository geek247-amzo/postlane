$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) { throw 'Create the Python virtual environment and install requirements first; see README.md.' }
$env:DEMO_MODE = 'true'
$env:APP_ENV = 'development'
$env:APP_URL = 'http://127.0.0.1:5173'
$backendProcess = Start-Process -FilePath (Join-Path $projectRoot '.venv/Scripts/python.exe') -ArgumentList '-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', '8000' -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
try {
    npm run dev
} finally {
    if (-not $backendProcess.HasExited) { Stop-Process -Id $backendProcess.Id }
}
