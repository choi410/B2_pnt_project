param([Parameter(Mandatory=$true)][string]$Source,[Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference='Stop'
$previewWord = New-Object -ComObject Word.Application
$previewWord.Visible=$false
$previewWord.DisplayAlerts=0
$previewWord.AutomationSecurity=3
$previewWord.Options.UpdateLinksAtOpen=$false
try {
  $previewDoc=$previewWord.Documents.Open($Source,$false,$true)
  try { $previewDoc.ExportAsFixedFormat($Destination,17) } finally { $previewDoc.Close(0) }
} finally {
  $previewWord.Quit()
  [System.Runtime.InteropServices.Marshal]::ReleaseComObject($previewWord) | Out-Null
}
