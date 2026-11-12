# Point Windows My JMRI Railroad MQTT at the Pi broker (10.0.0.150 on the home LAN; no ICS since 2026-11-11).
# Patches the shared profile\profile.xml and each per-computer profile\<node id>\profile.xml (JMRI reads that first).
# Only the MQTT <connection> start tag is changed. -Root is for tests; it replaces the usual JMRI settings folders.
param([string[]]$Root)
$ErrorActionPreference = 'Continue'
$Broker = '10.0.0.150'
$patched = 0
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

if (-not $Root) {
  $Root = @(
    (Join-Path $env:APPDATA 'JMRI'),
    (Join-Path $env:USERPROFILE 'JMRI'),
    (Join-Path $env:USERPROFILE '.jmri')
  )
}
$roots = $Root | Where-Object { $_ -and (Test-Path $_) }

$fixMqttTag = [System.Text.RegularExpressions.MatchEvaluator] {
  param($m)
  $tag = $m.Value
  if ($tag -notmatch 'class="jmri\.jmrix\.mqtt\.configurexml\.MqttConnectionConfigXml"') { return $tag }
  $tag = $tag -replace '\baddress="[^"]*"', ('address="' + $Broker + '"')
  $tag = $tag -replace '\breconnectMaxAttempts="\d+"', 'reconnectMaxAttempts="10"'
  $tag = $tag -replace '\breconnectMaxInterval="\d+"', 'reconnectMaxInterval="5"'
  return $tag
}

$files = @()
foreach ($r in $roots) {
  foreach ($railroad in (Get-ChildItem $r -Directory -ErrorAction SilentlyContinue |
                         Where-Object { $_.Name -like 'My_JMRI_Railroad*' })) {
    $profileDir = Join-Path $railroad.FullName 'profile'
    $shared = Join-Path $profileDir 'profile.xml'
    if (Test-Path $shared) { $files += [pscustomobject]@{ Path = $shared; Shared = $true } }
    foreach ($node in (Get-ChildItem $profileDir -Directory -ErrorAction SilentlyContinue)) {
      $pf = Join-Path $node.FullName 'profile.xml'
      if (Test-Path $pf) { $files += [pscustomobject]@{ Path = $pf; Shared = $false } }
    }
  }
}

foreach ($f in $files) {
  $pf = $f.Path
  $raw = [System.IO.File]::ReadAllText($pf, $utf8NoBom)
  if ($raw -notmatch 'MqttConnectionConfigXml') {
    if ($f.Shared) { Write-Host ("No MQTT in {0}" -f $pf) }
    continue
  }
  $new = [regex]::Replace($raw, '<connection\b[^>]*>', $fixMqttTag)
  if ($new -ne $raw) {
    $bak = $pf + '.bak_pre_mqtt_fix'
    if (-not (Test-Path $bak)) { Copy-Item $pf $bak -Force }
    [System.IO.File]::WriteAllText($pf, $new, $utf8NoBom)
    Write-Host ("Patched MQTT -> {0} : {1}" -f $Broker, $pf)
    $patched++
  } else {
    Write-Host ("MQTT already {0}: {1}" -f $Broker, $pf)
  }
}

Write-Host ("patch_windows_mqtt done (changes={0})" -f $patched)
exit 0
