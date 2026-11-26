$ErrorActionPreference = 'Stop'
$src = Join-Path $env:TEMP 'hart-roster-stage'
$dst = Join-Path $env:USERPROFILE 'JMRI_UserFiles'
New-Item -ItemType Directory -Force -Path (Join-Path $dst 'roster') | Out-Null
Copy-Item -Force (Join-Path $src 'roster.xml') (Join-Path $dst 'roster.xml')
Get-ChildItem (Join-Path $src 'roster') -File |
  Where-Object { $_.Name -notlike '._*' } |
  Copy-Item -Destination (Join-Path $dst 'roster') -Force
# Fail loudly instead of reporting success: every staged file must now match its copy.
$staged = @(Get-ChildItem (Join-Path $src 'roster') -File | Where-Object { $_.Name -notlike '._*' })
if ($staged.Count -eq 0) { throw "no roster files were staged in $src\roster (tar path problem?)" }
foreach ($f in $staged) {
  $copy = Join-Path (Join-Path $dst 'roster') $f.Name
  if ((Get-FileHash $f.FullName).Hash -ne (Get-FileHash $copy).Hash) { throw "roster file differs after copy: $($f.Name)" }
}
if ((Get-FileHash (Join-Path $src 'roster.xml')).Hash -ne (Get-FileHash (Join-Path $dst 'roster.xml')).Hash) { throw "roster.xml differs after copy" }
$n = (Select-String -Path (Join-Path $dst 'roster.xml') -Pattern '<locomotive ' -SimpleMatch).Count
Write-Output "win_roster_ok locos=$n files=$((Get-ChildItem (Join-Path $dst 'roster') -File | Where-Object { $_.Name -notlike '._*' }).Count)"
Remove-Item -LiteralPath $src -Recurse -Force
