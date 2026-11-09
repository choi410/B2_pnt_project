param([ValidateSet('Setup','Run','Team','AI')][string]$Mode='Run')
$ErrorActionPreference='Stop'
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
        } else { throw 'Install Python 3.12 64-bit, then run setup again.' }
        if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed. Install Python 3.12 64-bit.' }
    }
    & $packagePython -m pip install --disable-pip-version-check -r (Join-Path $serviceRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check Internet access.' }
    Write-Host 'Setup complete. Run 02 to start the service.'
    exit 0
}
if (-not (Test-Path -LiteralPath $packagePython)) { throw 'Run 01 setup first.' }
if ($Mode -eq 'AI') {
    & $packagePython -m pip install --disable-pip-version-check -r (Join-Path $packageRoot 'b2-model\requirements-ai.txt')
    if ($LASTEXITCODE -ne 0) { throw 'AI dependency installation failed.' }
    Write-Host 'AI environment installed. Model weights are NOT included. See README.md.'
    exit 0
}
if ($Mode -eq 'Team') {
    & (Join-Path $serviceRoot 'work\v17\start-team.ps1')
    exit $LASTEXITCODE
}
$env:B2_DEMO_MODE='1'
Remove-Item Env:B2_TEAM_LAN_IP,Env:B2_TEAM_LAN_CIDR,Env:B2_TEAM_DATA_DIR,Env:B2_TEAM_TESTING -ErrorAction SilentlyContinue
Write-Host 'Open http://127.0.0.1:8771/ in your browser.'
Write-Host 'Keep this window open. Ctrl+C stops the server.'
& $packagePython -m uvicorn work.v17.server:app --host 127.0.0.1 --port 8771 --no-proxy-headers --no-access-log
exit $LASTEXITCODE
