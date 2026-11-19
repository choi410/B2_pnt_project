$ErrorActionPreference = 'Stop'
$teamIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$teamPrincipal = [Security.Principal.WindowsPrincipal]::new($teamIdentity)
if (-not $teamPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $teamArguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '"'
    $teamAdminProcess = Start-Process -FilePath powershell.exe -Verb RunAs -WindowStyle Hidden -ArgumentList $teamArguments -Wait -PassThru
    exit $teamAdminProcess.ExitCode
}
$teamNetwork = Get-NetIPConfiguration | Where-Object {
    $_.IPv4DefaultGateway -and $_.IPv4Address -and $_.NetAdapter.Status -eq 'Up'
} | Sort-Object InterfaceIndex | Select-Object -First 1
if (-not $teamNetwork) { throw 'No connected LAN adapter was found.' }
$teamAddress = $teamNetwork.IPv4Address | Where-Object { $_.IPAddress -notlike '169.254.*' } | Select-Object -First 1
$teamParts = $teamAddress.IPAddress.Split('.')
$teamPrefix = [int]$teamAddress.PrefixLength
$teamOctets = for ($teamIndex=0; $teamIndex -lt 4; $teamIndex++) {
    $teamBits = [Math]::Min(8,[Math]::Max(0,$teamPrefix-8*$teamIndex))
    $teamMask = if ($teamBits -eq 0) { 0 } else { (255 -shl (8-$teamBits)) -band 255 }
    ([int]$teamParts[$teamIndex] -band $teamMask)
}
$teamSubnet = ($teamOctets -join '.') + '/' + $teamPrefix
# Match only this application's test port, current LAN interface and local subnet.
$teamRule = 'B2-Team-v17-TCP-8771'
$teamSettings = @{
    DisplayName='B2 v1.7 team test - local subnet only'
    Direction='Inbound';Action='Allow';Enabled='True';Profile='Any'
    Protocol='TCP';LocalPort=8771;LocalAddress=$teamAddress.IPAddress
    RemoteAddress=$teamSubnet;InterfaceAlias=$teamNetwork.InterfaceAlias
    EdgeTraversalPolicy='Block'
}
if (Get-NetFirewallRule -Name $teamRule -ErrorAction SilentlyContinue) {
    Set-NetFirewallRule -Name $teamRule @teamSettings
} else {
    New-NetFirewallRule -Name $teamRule @teamSettings | Out-Null
}
$teamRuleResult = Get-NetFirewallRule -Name $teamRule
if ($teamRuleResult.Enabled -ne 'True' -or $teamRuleResult.Action -ne 'Allow') { throw 'The scoped firewall rule was not enabled.' }
