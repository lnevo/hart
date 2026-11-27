$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'jmri_processes.ps1')
$hits = Get-JmriProcesses

if (-not $hits) {
  Write-Host 'No CATS/Crandic/PanelPro Java processes found.'
  exit 0
}

Write-Host 'Stopping:'
foreach ($p in $hits) {
  $clip = $p.CommandLine
  if ($clip.Length -gt 140) { $clip = $clip.Substring(0, 140) + '...' }
  Write-Host ("  PID {0} {1}" -f $p.ProcessId, $p.Name)
  Write-Host ("    {0}" -f $clip)
  Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 1
foreach ($p in $hits) {
  if (Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue) {
    & taskkill.exe /F /PID $p.ProcessId 2>$null | Out-Null
  }
}

$left = Get-JmriProcesses -Names '^(java|javaw)\.exe$'
if ($left) {
  Write-Host 'WARNING: still running:'
  $left | ForEach-Object { Write-Host ("  PID {0}" -f $_.ProcessId) }
  exit 1
}

Write-Host 'Done. CATS/Crandic stopped.'
exit 0
