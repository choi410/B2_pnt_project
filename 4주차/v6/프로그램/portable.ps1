param(
    [ValidateSet('Setup','Run','AI','Models','Check')][string]$Mode='Run',
    [string]$Python='',
    [switch]$NoBrowser,
    [switch]$StrictAI
)
$ErrorActionPreference='Stop'
$env:PYTHONUTF8='1'
$programRoot=$PSScriptRoot
$serviceRoot=Join-Path $programRoot 'b2-service'
$environmentRoot=Join-Path $programRoot 'b2-model\.venv'
$packagePython=Join-Path $environmentRoot 'Scripts\python.exe'
Set-Location -LiteralPath $serviceRoot
if ($Mode -eq 'Setup') {
    if (-not (Test-Path -LiteralPath $packagePython)) {
        $chosenPython=$null
        $versionCheck="import sys,struct; assert sys.version_info[:2]==(3,12) and struct.calcsize('P')==8; print(sys.executable)"
        if ($Python) {
            if (-not (Test-Path -LiteralPath $Python)) { throw 'The specified Python executable does not exist.' }
            $probe=& $Python -c $versionCheck
            if ($LASTEXITCODE -eq 0) { $chosenPython=([string]($probe | Select-Object -Last 1)).Trim() }
        } else {
            if (Get-Command py -ErrorAction SilentlyContinue) {
                try {
                    $probe=& py -3.12 -c $versionCheck 2>$null
                    if ($LASTEXITCODE -eq 0) { $chosenPython=([string]($probe | Select-Object -Last 1)).Trim() }
                } catch { $chosenPython=$null }
            }
            if (-not $chosenPython -and (Get-Command python -ErrorAction SilentlyContinue)) {
                try {
                    $probe=& python -c $versionCheck 2>$null
                    if ($LASTEXITCODE -eq 0) { $chosenPython=([string]($probe | Select-Object -Last 1)).Trim() }
                } catch { $chosenPython=$null }
            }
        }
        if (-not $chosenPython) { throw 'Install Python 3.12 64-bit, then run 01 again. See README.md.' }
        & $chosenPython -m venv $environmentRoot
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the local Python environment.' }
    }
    & $packagePython -c "import sys,struct; assert sys.version_info[:2]==(3,12) and struct.calcsize('P')==8"
    if ($LASTEXITCODE -ne 0) { throw 'This folder needs a fresh Python 3.12 64-bit environment.' }
    # requirements-dev.txt = requirements.txt + pytest, httpx, numpy (service, Supabase, automated tests)
    & $packagePython -m pip install --disable-pip-version-check -r (Join-Path $serviceRoot 'requirements-dev.txt') -c (Join-Path $serviceRoot 'requirements-lock.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Installation failed. Check Internet access and retry 01.' }
    Write-Host 'Setup complete (service + test tools). Run 02. AI preparation: 03, 04, then 05.'
    exit 0
}
if (-not (Test-Path -LiteralPath $packagePython)) { throw 'Run 01 setup first.' }
if ($Mode -eq 'AI') {
    & $packagePython -m pip install --disable-pip-version-check -r (Join-Path $programRoot 'b2-model\requirements-ai.txt')
    if ($LASTEXITCODE -ne 0) { throw 'AI installation failed. Check Internet access and GPU requirements.' }
    Write-Host 'AI libraries installed. Run 04 to download the models, then 05.'
    exit 0
}
if ($Mode -eq 'Models') {
    & $packagePython (Join-Path $programRoot 'b2-model\download_models.py')
    if ($LASTEXITCODE -ne 0) { throw 'Model download failed. Run 03 first, then retry 04.' }
    exit 0
}
if ($Mode -eq 'Check') {
    if ($StrictAI) { & $packagePython (Join-Path $programRoot 'check_environment.py') --require-ai }
    else { & $packagePython (Join-Path $programRoot 'check_environment.py') }
    exit $LASTEXITCODE
}
if ($NoBrowser) { & $packagePython (Join-Path $programRoot 'start.py') --no-browser }
else { & $packagePython (Join-Path $programRoot 'start.py') }
exit $LASTEXITCODE
