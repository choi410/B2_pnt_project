$ErrorActionPreference = 'Stop'
$teamRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$teamPython = (Resolve-Path (Join-Path $teamRoot '..\b2-model\.venv\Scripts\python.exe')).Path
$teamNetwork = Get-NetIPConfiguration | Where-Object {
    $_.IPv4DefaultGateway -and $_.IPv4Address -and $_.NetAdapter.Status -eq 'Up'
} | Sort-Object InterfaceIndex | Select-Object -First 1
if (-not $teamNetwork) { throw 'No connected LAN adapter with an IPv4 gateway was found.' }
$teamAddress = $teamNetwork.IPv4Address | Where-Object {
    $_.IPAddress -notlike '169.254.*'
} | Select-Object -First 1
if (-not $teamAddress) { throw 'No LAN IPv4 address was found.' }
$env:B2_TEAM_LAN_IP = $teamAddress.IPAddress
$env:B2_TEAM_LAN_CIDR = $teamAddress.IPAddress + '/' + $teamAddress.PrefixLength
$env:B2_DEMO_MODE = '1'
$teamExisting = Get-NetTCPConnection -State Listen -LocalPort 8771 -ErrorAction SilentlyContinue
if ($teamExisting) {
    try { $teamHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:8771/api/health' -TimeoutSec 3 } catch { throw 'Port 8771 is in use by another service.' }
    if ($teamHealth.workspace -ne 'b2-team-v1.7') { throw 'Port 8771 is in use by another service.' }
    Write-Host ('B2 ' + $teamHealth.version + ' is already running.')
    Write-Host ('Team URL: ' + $teamHealth.lan_url)
    Start-Process 'http://127.0.0.1:8771/'
    exit 0
}
Write-Host 'B2 v2.0 - 4 person team trial'
Write-Host 'This PC: http://127.0.0.1:8771/'
Write-Host ('Team URL: http://' + $teamAddress.IPAddress + ':8771/')
Write-Host 'Keep this window open while the team is testing. Ctrl+C stops the server.'
Set-Location -LiteralPath $teamRoot
& $teamPython -m uvicorn work.v17.server:app --host 0.0.0.0 --port 8771 --no-proxy-headers --no-access-log
exit $LASTEXITCODE
