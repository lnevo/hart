# Install cats-masts appearances from %USERPROFILE%\hart into JMRI profiles.
$ErrorActionPreference = 'Stop'
$src = Join-Path $env:USERPROFILE 'hart\cats\resources\signals\cats-masts'
if (-not (Test-Path $src)) { throw "Missing $src" }

$dests = New-Object System.Collections.Generic.List[string]
[void]$dests.Add((Join-Path $env:USERPROFILE 'JMRI_UserFiles\resources\signals\cats-masts'))
$jmri = Join-Path $env:USERPROFILE 'JMRI'
if (Test-Path $jmri) {
  Get-ChildItem $jmri -Directory -Filter '*.jmri' -ErrorAction SilentlyContinue | ForEach-Object {
    [void]$dests.Add((Join-Path $_.FullName 'resources\signals\cats-masts'))
  }
}
foreach ($d in ($dests | Select-Object -Unique)) {
  New-Item -ItemType Directory -Force -Path $d | Out-Null
  Copy-Item (Join-Path $src '*') $d -Force
  Write-Host ("cats-masts -> {0}" -f $d)
}
