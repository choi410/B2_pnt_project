# 팀 시연용: Cloudflare 빠른 터널을 열고, 그 주소만 허용하도록 PNT v5 서비스를 실행합니다.
# 06_팀시연_외부공개.cmd 에서 실행됩니다. 이 창을 닫거나 Ctrl+C를 누르면 서비스와 터널이 함께 꺼집니다.
$ErrorActionPreference = 'Stop'
$programRoot = $PSScriptRoot
$cloudflared = Join-Path $programRoot 'cloudflared\cloudflared.exe'
$log = Join-Path $programRoot 'cloudflared\tunnel.log'

if (-not (Test-Path -LiteralPath $cloudflared)) {
    throw ('cloudflared.exe가 없습니다. https://github.com/cloudflare/cloudflared/releases 에서 ' +
           'cloudflared-windows-amd64.exe 를 받아 "' + $cloudflared + '" 이름으로 넣어 주세요.')
}
$probe = New-Object Net.Sockets.TcpClient
try { $probe.Connect('127.0.0.1', 8776); $busy = $true } catch { $busy = $false } finally { $probe.Close() }
if ($busy) { throw '8776 포트가 이미 사용 중입니다. 02_서비스실행 창이나 다른 시연 창을 먼저 닫은 뒤 다시 실행해 주세요.' }

Remove-Item -LiteralPath $log -ErrorAction SilentlyContinue
# -NoNewWindow: cloudflared shares this console, so closing the window also ends the tunnel.
$tunnel = Start-Process -FilePath $cloudflared -PassThru -NoNewWindow `
    -ArgumentList @('tunnel', '--no-autoupdate', '--url', 'http://127.0.0.1:8776') `
    -RedirectStandardError $log
try {
    $publicHost = $null
    for ($i = 0; $i -lt 60 -and -not $publicHost; $i++) {
        Start-Sleep -Milliseconds 500
        if ($tunnel.HasExited) { throw ('터널을 열지 못했습니다. 인터넷 연결을 확인하거나 로그를 확인해 주세요: ' + $log) }
        if (Test-Path -LiteralPath $log) {
            $m = Select-String -LiteralPath $log -Pattern 'https://([a-z0-9-]+\.trycloudflare\.com)' | Select-Object -First 1
            if ($m) { $publicHost = $m.Matches[0].Groups[1].Value }
        }
    }
    if (-not $publicHost) { throw ('30초 안에 터널 주소를 받지 못했습니다. 로그: ' + $log) }
    $url = 'https://' + $publicHost
    try { Set-Clipboard -Value $url; $copied = ' (클립보드에 복사됨)' } catch { $copied = '' }
    Write-Host ''
    Write-Host '=================================================================' -ForegroundColor Cyan
    Write-Host ('  팀 공유 주소: ' + $url + $copied) -ForegroundColor Cyan
    Write-Host '  처음 30초 정도는 접속이 안 될 수 있습니다.'
    Write-Host '  비밀번호가 없으니 팀 안에서만 공유하세요.'
    Write-Host '  이 창을 닫거나 Ctrl+C를 누르면 서비스와 터널이 함께 꺼집니다.'
    Write-Host '=================================================================' -ForegroundColor Cyan
    Write-Host ''
    $env:B2_PUBLIC_HOST = $publicHost
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $programRoot 'portable.ps1') -Mode Run
}
finally {
    Remove-Item Env:B2_PUBLIC_HOST -ErrorAction SilentlyContinue
    if (-not $tunnel.HasExited) { Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue }
    Write-Host '터널을 닫았습니다.'
}
