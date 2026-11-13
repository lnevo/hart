# Fast resolve: prefer cached id; light scan of AppData only.
param(
  [string]$OutFile = $(Join-Path $PSScriptRoot 'jmri_profile_id.txt'),
  [switch]$Force,
  [switch]$SetActive
)

$ErrorActionPreference = 'Continue'

function Get-CachedId {
  if ((Test-Path $OutFile) -and -not $Force) {
    $id = (Get-Content $OutFile -Raw).Trim()
    if ($id -match '^My_JMRI_Railroad\.') { return $id }
  }
  return $null
}

function Find-ProfileId {
  $roots = @(
    (Join-Path $env:APPDATA 'JMRI'),
    (Join-Path $env:USERPROFILE 'JMRI'),
    (Join-Path $env:USERPROFILE '.jmri')
  ) | Where-Object { $_ -and (Test-Path $_) }

  foreach ($r in $roots) {
    $px = Join-Path $r 'profiles.xml'
    if (Test-Path $px) {
      try {
        $x = [xml](Get-Content -Raw $px)
        $hit = @($x.profileConfig.profiles.profile) |
          Where-Object { $_.id -like 'My_JMRI_Railroad*' -or $_.path -like '*My_JMRI_Railroad*' } |
          Select-Object -First 1
        if ($hit) { return [string]$hit.id }
      } catch {}
    }
    Get-ChildItem $r -Directory -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -like 'My_JMRI_Railroad*' } |
      ForEach-Object {
        $f = Join-Path $_.FullName 'profile\profile.properties'
        if (Test-Path $f) {
          $line = Select-String -Path $f -Pattern '^profile\.id=(.+)$' | Select-Object -First 1
          if ($line) { return $line.Matches[0].Groups[1].Value.Trim() }
        }
      }
  }
  return $null
}

$id = Get-CachedId
if (-not $id) { $id = Find-ProfileId }

if (-not $id) {
  Write-Host 'ERROR: My JMRI Railroad profile not found.'
  exit 2
}

New-Item -ItemType Directory -Force -Path (Split-Path $OutFile -Parent) | Out-Null
Set-Content -Path $OutFile -Value $id -Encoding ASCII
Write-Host ("PROFILE_ID={0}" -f $id)

if ($SetActive) {
  foreach ($r in @(
    (Join-Path $env:APPDATA 'JMRI'),
    (Join-Path $env:USERPROFILE 'JMRI'),
    (Join-Path $env:USERPROFILE '.jmri')
  )) {
    if (-not (Test-Path $r)) { continue }
    $cfg = Join-Path $r 'PanelProConfig2.properties'
    $xml = @"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE properties SYSTEM "http://java.sun.com/dtd/properties.dtd">
<properties>
<entry key="activeProfile">$id</entry>
<entry key="autoStart">true</entry>
<entry key="autoStartTimeout">3</entry>
</properties>
"@
    Set-Content -Path $cfg -Value $xml.Trim() -Encoding UTF8
  }
}

Write-Output $id
exit 0
