$ErrorActionPreference = 'Stop'
$src = Join-Path $env:TEMP 'hart-roster-stage'
$dst = Join-Path $env:USERPROFILE 'JMRI\My_JMRI_Railroad.jmri'
New-Item -ItemType Directory -Force -Path (Join-Path $dst 'roster'), (Join-Path $dst 'operations') | Out-Null
Copy-Item -Force (Join-Path $src 'roster.xml') (Join-Path $dst 'roster.xml')
Get-ChildItem (Join-Path $src 'roster') -File |
  Where-Object { $_.Name -notlike '._*' } |
  Copy-Item -Destination (Join-Path $dst 'roster') -Force
Copy-Item -Force (Join-Path $src 'operations\*.xml') (Join-Path $dst 'operations')
$n = (Select-String -Path (Join-Path $dst 'roster.xml') -Pattern '<locomotive ' -SimpleMatch).Count
Write-Output "win_roster_ok locos=$n files=$((Get-ChildItem (Join-Path $dst 'roster') -File | Where-Object { $_.Name -notlike '._*' }).Count)"
Remove-Item -LiteralPath $src -Recurse -Force
