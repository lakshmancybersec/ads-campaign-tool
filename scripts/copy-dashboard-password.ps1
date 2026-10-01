$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$envPath = Join-Path $projectRoot '.env'
# Read only the dashboard credential; never print it to the terminal.
$dashboardPassword = & $pythonPath -c "import sys; from dotenv import dotenv_values; value=dotenv_values(sys.argv[1]).get('API_ADMIN_KEY') or ''; sys.stdout.write(value)" $envPath
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($dashboardPassword)) {
    throw 'Could not read the dashboard password from .env.'
}
Set-Clipboard -Value $dashboardPassword
$dashboardPassword = $null
Write-Output 'Dashboard password copied. Paste it into the dashboard login box. Copy something else afterward to replace it on your clipboard.'
