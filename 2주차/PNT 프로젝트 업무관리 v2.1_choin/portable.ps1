param([ValidateSet('Setup','Run','AI','Models','Check')][string]$Mode='Run')
$ErrorActionPreference='Stop'
$env:PYTHONUTF8='1'
$packageRoot=$PSScriptRoot
$serviceRoot=Join-Path $packageRoot 'b2-service'
$environmentRoot=Join-Path $packageRoot 'b2-model\.venv'
$packagePython=Join-Path $environmentRoot 'Scripts\python.exe'
Set-Location -LiteralPath $serviceRoot
if ($Mode -eq 'Setup') {
    if (-not (Test-Path -LiteralPath $packagePython)) {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            & py -3.12 -m venv $environmentRoot
        } elseif (Get-Command python -ErrorAction SilentlyContinue) {
            & python -c "import sys,struct; assert sys.version_info[:2]==(3,12) and struct.calcsize('P')==8, 'Python 3.12 64-bit required'"
            if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 64-bit first.' }
            & python -m venv $environmentRoot
        } else { throw 'Install Python 3.12 64-bit, then run 01 again.' }
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python 3.12 environment.' }
    }
    & $packagePython -c "import sys,struct; assert sys.version_info[:2]==(3,12) and struct.calcsize('P')==8, 'Python 3.12 64-bit required'"
    if ($LASTEXITCODE -ne 0) { throw 'This package needs Python 3.12 64-bit.' }
    & $packagePython -m pip install --disable-pip-version-check -r (Join-Path $serviceRoot 'requirements.txt') -c (Join-Path $serviceRoot 'requirements-lock.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check Internet access and retry 01.' }
    Write-Host 'Setup complete. Run 02 to start. AI setup is optional; see README.md.'
    exit 0
}
if (-not (Test-Path -LiteralPath $packagePython)) { throw 'Run 01 setup first.' }
if ($Mode -eq 'AI') {
    Write-Host 'Installing the CUDA AI environment. Several GB may be downloaded.'
    & $packagePython -m pip install --disable-pip-version-check -r (Join-Path $packageRoot 'b2-model\requirements-ai.txt')
    if ($LASTEXITCODE -ne 0) { throw 'AI dependency installation failed.' }
    Write-Host 'AI libraries installed. Run 04 to download the model files, then 05 to check.'
    exit 0
}
if ($Mode -eq 'Models') {
    & $packagePython (Join-Path $packageRoot 'b2-model\download_models.py')
    if ($LASTEXITCODE -ne 0) { throw 'Model download failed. Check Internet access and retry 04.' }
    exit 0
}
if ($Mode -eq 'Check') {
    & $packagePython (Join-Path $packageRoot 'check_environment.py')
    exit $LASTEXITCODE
}
# Each clone has its own local data. Never inherit another workspace's paths/network.
$env:B2_DEMO_MODE='1'
foreach ($key in @('B2_TEAM_LAN_IP','B2_TEAM_LAN_CIDR','B2_TEAM_DATA_DIR','B2_TEAM_TESTING','B2_AI_DEBUG','B2_DATABASE','B2_SAMPLE_DOCX')) {
    [Environment]::SetEnvironmentVariable($key,$null,'Process')
}
$probe=[System.Net.Sockets.TcpClient]::new()
try {
    $attempt=$probe.ConnectAsync('127.0.0.1',8772)
    $null=$attempt.Wait(500)
    $portBusy=$probe.Connected
} catch { $portBusy=$false } finally { $probe.Dispose() }
if ($portBusy) { throw 'Port 8772 is already in use. Stop the old server in its own window with Ctrl+C, then run 02 again.' }
Write-Host 'PNT workspace v2.1_choin'
Write-Host 'Open http://127.0.0.1:8772/ in your browser.'
Write-Host 'Keep this window open. Ctrl+C stops this server.'
Write-Host 'Each PC saves its own data. This is NOT an Internet-hosted shared server.'
& $packagePython -m uvicorn work.v17.server:app --host 127.0.0.1 --port 8772 --no-proxy-headers --no-access-log
exit $LASTEXITCODE
