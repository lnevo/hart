# Apply HART package already under %USERPROFILE%\hart into JMRI locations.
# Called by sync_hart_package.sh --win over SSH.
$ErrorActionPreference = 'Stop'
$hart = Join-Path $env:USERPROFILE 'hart'

$src = Join-Path $hart 'tables.xml'
if (Test-Path $src) {
  $dests = New-Object System.Collections.Generic.List[string]
  [void]$dests.Add((Join-Path $env:USERPROFILE 'JMRI_UserFiles\tables.xml'))
  $jmri = Join-Path $env:USERPROFILE 'JMRI'
  if (Test-Path $jmri) {
    Get-ChildItem $jmri -Directory -Filter '*.jmri' -ErrorAction SilentlyContinue | ForEach-Object {
      [void]$dests.Add((Join-Path $_.FullName 'tables.xml'))
    }
  }
  foreach ($d in ($dests | Select-Object -Unique)) {
    $dir = Split-Path $d -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    Copy-Item $src $d -Force
    Write-Host ("tables.xml -> {0}" -f $d)
  }
} else {
  Write-Host 'No hart\tables.xml (skip tables)'
}

$homeHtml = Join-Path $hart 'cats\resources\jmri-web\servlet\home\Home.html'
$stsHtml = Join-Path $hart 'cats\resources\jmri-web\sts.html'
if (Test-Path $homeHtml) {
  $roots = New-Object System.Collections.Generic.List[string]
  [void]$roots.Add((Join-Path $env:USERPROFILE 'JMRI_UserFiles'))
  $jmri = Join-Path $env:USERPROFILE 'JMRI'
  if (Test-Path $jmri) {
    Get-ChildItem $jmri -Directory -Filter '*.jmri' -ErrorAction SilentlyContinue | ForEach-Object {
      [void]$roots.Add($_.FullName)
    }
  }
  foreach ($r in ($roots | Select-Object -Unique)) {
    if (-not (Test-Path $r)) { continue }
    $hd = Join-Path $r 'web\servlet\home'
    New-Item -ItemType Directory -Force -Path $hd | Out-Null
    Copy-Item $homeHtml (Join-Path $hd 'Home.html') -Force
    if (Test-Path $stsHtml) {
      New-Item -ItemType Directory -Force -Path (Join-Path $r 'web') | Out-Null
      Copy-Item $stsHtml (Join-Path $r 'web\sts.html') -Force
    }
    Write-Host ("web STS -> {0}\web" -f $r)
  }
} else {
  Write-Host 'No jmri-web Home.html (skip web)'
}

Write-Host 'apply_hart_package_local done'
