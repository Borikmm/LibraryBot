param([ValidateSet('Setup', 'Run', 'Test', 'Stop')][string]$Action = 'Run')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$localDir = Join-Path $repoRoot '.local'
$pythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'
$pidFile = Join-Path $localDir 'bot.pid'
Set-Location -LiteralPath $repoRoot
New-Item -ItemType Directory -Path $localDir -Force | Out-Null
$pgFolder = Get-ChildItem -LiteralPath "$env:ProgramFiles\PostgreSQL" -Directory |
    Where-Object Name -Match '^\d+(\.\d+)?$' |
    Sort-Object { [int]($_.Name -split '\.')[0] } -Descending | Select-Object -First 1
if (-not $pgFolder) { throw 'Install PostgreSQL 18 before running this script.' }
$pgBin = Join-Path $pgFolder.FullName 'bin'
$pgData = Join-Path $localDir 'postgres'
function Invoke-Checked([string]$Executable, [string[]]$Arguments) {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Executable failed with exit code $LASTEXITCODE" }
}
if ($Action -eq 'Stop') {
    if (Test-Path -LiteralPath $pidFile) {
        $botProcessId = [int](Get-Content -LiteralPath $pidFile)
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$botProcessId" -ErrorAction SilentlyContinue
        if ($process -and $process.CommandLine.Contains($repoRoot) -and $process.CommandLine.Contains('main.py')) {
            Stop-Process -Id $botProcessId
        }
        Remove-Item -LiteralPath $pidFile -ErrorAction SilentlyContinue
    }
    & (Join-Path $pgBin 'pg_ctl.exe') -D $pgData status | Out-Null
    if ($LASTEXITCODE -eq 0) { Invoke-Checked (Join-Path $pgBin 'pg_ctl.exe') @('-D', $pgData, '-m', 'fast', '-w', 'stop') }
    exit
}
if (-not (Test-Path -LiteralPath $pythonExe)) {
    Invoke-Checked 'py' @('-3.12', '-m', 'venv', '.venv')
    Invoke-Checked $pythonExe @('-m', 'pip', 'install', '-r', 'requirements.lock')
}
if ($Action -eq 'Setup') { Invoke-Checked $pythonExe @('-m', 'pip', 'install', '-r', 'requirements.lock') }
$dbEnv = Join-Path $localDir 'db.env'
if (-not (Test-Path -LiteralPath (Join-Path $pgData 'PG_VERSION'))) {
    $dbPassword = [guid]::NewGuid().ToString('N')
    $passwordFile = Join-Path $localDir 'pg-password'
    Set-Content -LiteralPath $passwordFile -Value $dbPassword -Encoding ascii
    Set-Content -LiteralPath $dbEnv -Value "DATABASE_URL=postgresql://librarybot:$dbPassword@127.0.0.1:55432/librarybot" -Encoding ascii
    Invoke-Checked (Join-Path $pgBin 'initdb.exe') @('-D', $pgData, '-U', 'librarybot', '--auth-host=scram-sha-256', '--auth-local=scram-sha-256', "--pwfile=$passwordFile", '-E', 'UTF8', '--locale=C')
}
if (-not (Test-Path -LiteralPath $dbEnv)) { throw 'Local database settings are missing; preserve the cluster and restore .local/db.env.' }
$env:DATABASE_URL = (Get-Content -LiteralPath $dbEnv -Raw).Trim().Substring('DATABASE_URL='.Length)
& (Join-Path $pgBin 'pg_ctl.exe') -D $pgData status | Out-Null
if ($LASTEXITCODE -ne 0) { Invoke-Checked (Join-Path $pgBin 'pg_ctl.exe') @('-D', $pgData, '-l', (Join-Path $localDir 'postgres.log'), '-o', '-p 55432 -h 127.0.0.1', '-w', 'start') }
@'
import os, psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
info = conninfo_to_dict(os.environ['DATABASE_URL'])
info['dbname'] = 'postgres'
with psycopg.connect(make_conninfo(**info), autocommit=True) as c:
    if not c.execute("SELECT 1 FROM pg_database WHERE datname='librarybot'").fetchone():
        c.execute('CREATE DATABASE librarybot')
'@ | & $pythonExe -
if ($LASTEXITCODE -ne 0) { throw 'Could not prepare the local database.' }
if ($Action -eq 'Test') {
    Invoke-Checked $pythonExe @('-m', 'pip', 'install', '-r', 'requirements-dev.txt')
    $env:TEST_DATABASE_URL = $env:DATABASE_URL
    Invoke-Checked $pythonExe @('-m', 'pytest', '-q')
    exit
}
if ($Action -eq 'Setup') {
    Write-Output 'Local PostgreSQL is ready on 127.0.0.1:55432. Put BOT_TOKEN in .env, then run this script with -Action Run.'
    exit
}
if (Test-Path -LiteralPath $pidFile) {
    $runningId = [int](Get-Content -LiteralPath $pidFile)
    $running = Get-CimInstance Win32_Process -Filter "ProcessId=$runningId" -ErrorAction SilentlyContinue
    if ($running -and $running.CommandLine.Contains($repoRoot) -and $running.CommandLine.Contains('main.py')) {
        Write-Output 'LibraryBot is already running.'
        exit
    }
}
$env:LOCAL_PID_FILE = $pidFile
$started = Start-Process -FilePath $pythonExe -ArgumentList ('"' + (Join-Path $repoRoot 'main.py') + '"') -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $localDir 'bot.stdout.log') -RedirectStandardError (Join-Path $localDir 'bot.stderr.log')
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    Start-Sleep -Milliseconds 1000
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:10000/health' -TimeoutSec 2
        if ($health.ready -and (Test-Path -LiteralPath $pidFile)) {
            Write-Output 'LibraryBot is ready. Logs: .local/bot.stdout.log. Stop: scripts/local.ps1 -Action Stop.'
            exit
        }
    } catch { }
    if ($started.HasExited) { throw 'Bot exited. Inspect .local/bot.stderr.log.' }
}
throw 'Bot is not ready yet. Inspect .local/bot.stdout.log and .local/bot.stderr.log.'
