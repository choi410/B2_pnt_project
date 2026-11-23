param()
$ErrorActionPreference='Stop'
$env:PYTHONUTF8='1'
$packageRoot=$PSScriptRoot
$workspaceRoot=Split-Path (Split-Path (Split-Path $packageRoot -Parent) -Parent) -Parent
$modelRoot=Join-Path $workspaceRoot 'b2-model'
$demoPython=Join-Path $modelRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $demoPython)) { throw 'The local b2-model Python environment was not found.' }
foreach ($key in @('B2_TEAM_LAN_IP','B2_TEAM_LAN_CIDR','B2_TEAM_TESTING','B2_AI_DEBUG','B2_DATABASE','B2_SAMPLE_DOCX')) {
    [Environment]::SetEnvironmentVariable($key,$null,'Process')
}
$env:B2_DEMO_MODE='1'
$env:B2_TEAM_DATA_DIR=Join-Path $packageRoot 'b2-service\data\demo'
$probe=[System.Net.Sockets.TcpClient]::new()
try { $attempt=$probe.ConnectAsync('127.0.0.1',8772);$null=$attempt.Wait(500);$portBusy=$probe.Connected } catch { $portBusy=$false } finally { $probe.Dispose() }
if ($portBusy) { throw 'Port 8772 is already in use. Open http://127.0.0.1:8772/ or stop that server first.' }
Set-Location -LiteralPath (Join-Path $packageRoot 'b2-service')
Write-Host 'PNT B2 presentation build / http://127.0.0.1:8772/'
Write-Host 'Separate data from V3. Keep this window open; Ctrl+C stops the server.'
& $demoPython -m uvicorn work.v3.server:app --host 127.0.0.1 --port 8772 --no-proxy-headers --no-access-log
exit $LASTEXITCODE
