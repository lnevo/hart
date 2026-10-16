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
    $stale = Join-Path $r 'web\sts.html'
    if (Test-Path $stale) { Remove-Item $stale -Force }
    Write-Host ("web home -> {0}\web" -f $r)
  }
} else {
  Write-Host 'No jmri-web Home.html (skip web)'
}

$btnSrc = Join-Path $hart 'cats\resources\buttons'
if (Test-Path $btnSrc) {
  $roots = New-Object System.Collections.Generic.List[string]
  [void]$roots.Add((Join-Path $env:USERPROFILE 'JMRI_UserFiles'))
  $jmri = Join-Path $env:USERPROFILE 'JMRI'
  if (Test-Path $jmri) {
    Get-ChildItem $jmri -Directory -Filter '*.jmri' -ErrorAction SilentlyContinue | ForEach-Object {
      [void]$roots.Add($_.FullName)
    }
  }
  $pngs = @()
  $pngs += Get-ChildItem $btnSrc -Filter 'triangle_*.png' -ErrorAction SilentlyContinue
  $pngs += Get-ChildItem $btnSrc -Filter 'lamp_*.png' -ErrorAction SilentlyContinue
  foreach ($r in ($roots | Select-Object -Unique)) {
    if (-not (Test-Path $r)) { continue }
    $dest = Join-Path $r 'resources\buttons'
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    foreach ($p in $pngs) {
      Copy-Item $p.FullName $dest -Force
    }
    Write-Host ("button icons -> {0}\resources\buttons" -f $r)
  }
}

$ussSrc = Join-Path $hart 'cats\resources\icons\USS\sensor'
if (Test-Path $ussSrc) {
  $roots = New-Object System.Collections.Generic.List[string]
  [void]$roots.Add((Join-Path $env:USERPROFILE 'JMRI_UserFiles'))
  $jmri = Join-Path $env:USERPROFILE 'JMRI'
  if (Test-Path $jmri) {
    Get-ChildItem $jmri -Directory -Filter '*.jmri' -ErrorAction SilentlyContinue | ForEach-Object {
      [void]$roots.Add($_.FullName)
    }
  }
  $gifs = @(Get-ChildItem $ussSrc -Filter 'yellow-*.gif' -ErrorAction SilentlyContinue)
  foreach ($r in ($roots | Select-Object -Unique)) {
    if (-not (Test-Path $r)) { continue }
    $dest = Join-Path $r 'resources\icons\USS\sensor'
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    foreach ($g in $gifs) {
      Copy-Item $g.FullName $dest -Force
    }
    Write-Host ("USS sensor icons -> {0}\resources\icons\USS\sensor" -f $r)
  }
  foreach ($prog in @(
    'C:\Program Files (x86)\JMRI\resources\icons\USS\sensor',
    'C:\Program Files\JMRI\resources\icons\USS\sensor'
  )) {
    $parent = Split-Path $prog -Parent
    if (Test-Path $parent) {
      New-Item -ItemType Directory -Force -Path $prog | Out-Null
      foreach ($g in $gifs) {
        Copy-Item $g.FullName $prog -Force
      }
      Write-Host ("USS sensor icons (program) -> {0}" -f $prog)
    }
  }
}

$ctcSrc = Join-Path $hart 'ctc'
if (Test-Path (Join-Path $ctcSrc 'icons')) {
  $roots = New-Object System.Collections.Generic.List[string]
  foreach ($p in @(
    (Join-Path $env:USERPROFILE 'JMRI_UserFiles'),
    (Join-Path $env:USERPROFILE 'JMRI'),
    (Join-Path $env:USERPROFILE 'Documents\JMRI')
  )) {
    if (Test-Path $p) { [void]$roots.Add($p) }
  }
  foreach ($root in @(
    (Join-Path $env:USERPROFILE 'JMRI'),
    (Join-Path $env:USERPROFILE 'Documents\JMRI'),
    (Join-Path $env:USERPROFILE '.jmri'),
    (Join-Path $env:APPDATA 'JMRI')
  )) {
    if (Test-Path $root) {
      Get-ChildItem $root -Directory -Filter '*.jmri' -ErrorAction SilentlyContinue | ForEach-Object {
        [void]$roots.Add($_.FullName)
      }
    }
  }
  foreach ($r in ($roots | Select-Object -Unique)) {
    $dest = Join-Path $r 'ctc\icons'
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    Copy-Item (Join-Path $ctcSrc 'icons\*') $dest -Force
    $gui = Join-Path $ctcSrc 'GUIObjects.xml'
    if (Test-Path $gui) {
      New-Item -ItemType Directory -Force -Path (Join-Path $r 'ctc') | Out-Null
      Copy-Item $gui (Join-Path $r 'ctc\GUIObjects.xml') -Force
    }
    Write-Host ("ctc icons -> {0}\ctc" -f $r)
  }
} else {
  Write-Host 'No hart\ctc\icons (skip CTC icons)'
}

$jythonSrc = @(
  (Join-Path $hart 'jmri\layouts\hart\scripts\hide_cats_desk_windows.py'),
  (Join-Path $hart 'jmri\layouts\hart\scripts\sync_layout_button.py'),
  (Join-Path $hart 'jmri\layouts\hart\scripts\jmri_cmd_watcher.py'),
  (Join-Path $hart 'jmri\scripts\mqtt_signalhead_publisher.py')
)
$trainInfoSrc = Join-Path $hart 'jmri\layouts\hart\dispatcher\traininfo'
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
  $dest = Join-Path $r 'jython'
  New-Item -ItemType Directory -Force -Path $dest | Out-Null
  foreach ($src in $jythonSrc) {
    if (Test-Path $src) {
      Copy-Item $src (Join-Path $dest (Split-Path $src -Leaf)) -Force
    }
  }
  $staleNx = Join-Path $dest 'prepare_nx_sml_paths.py'
  if (Test-Path $staleNx) { Remove-Item $staleNx -Force }
  foreach ($stale in @('hart_dispatcher_startup.py', 'patch_dispatcher_facing.py')) {
    $stalePath = Join-Path $dest $stale
    if (Test-Path $stalePath) { Remove-Item $stalePath -Force }
  }
  Write-Host ("preference:jython scripts -> {0}\jython" -f $r)
  if (Test-Path $trainInfoSrc) {
    $trainInfoDest = Join-Path $r 'dispatcher\traininfo'
    New-Item -ItemType Directory -Force -Path $trainInfoDest | Out-Null
    & robocopy $trainInfoSrc $trainInfoDest *.xml /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
    if ($LASTEXITCODE -ge 8) {
      throw ("robocopy traininfo failed ({0}) -> {1}" -f $LASTEXITCODE, $trainInfoDest)
    }
    Write-Host ("Dispatcher traininfo -> {0}\dispatcher\traininfo" -f $r)
  }
}

$retired = @('apply_maintain_mqtt.py', 'apply_mqtt_retain_at_startup.py', 'prepare_nx_sml_paths.py')
$retargetNames = @(
  'sync_layout_button.py',
  'mqtt_signalhead_publisher.py',
  'jmri_cmd_watcher.py'
)
$patchPy = Join-Path $hart 'cats\scripts\patch_jmri_startup.py'
$profileRoots = New-Object System.Collections.Generic.List[string]
foreach ($p in @(
  (Join-Path $env:USERPROFILE 'JMRI'),
  (Join-Path $env:USERPROFILE 'Documents\JMRI'),
  (Join-Path $env:USERPROFILE '.jmri')
)) {
  if (Test-Path $p) {
    Get-ChildItem $p -Directory -Filter '*.jmri' -ErrorAction SilentlyContinue | ForEach-Object {
      [void]$profileRoots.Add($_.FullName)
    }
  }
}
foreach ($r in ($profileRoots | Select-Object -Unique)) {
  $prof = Join-Path $r 'profile\profile.xml'
  if (-not (Test-Path $prof)) { continue }
  $txt = Get-Content -Raw -Encoding UTF8 $prof
  $orig = $txt
  foreach ($name in $retired) {
    $txt = [regex]::Replace($txt, ('\r?\n[ \t]*<perform\b[^>]*' + [regex]::Escape($name) + '[^>]*/>'), '')
  }
  if ($txt -ne $orig) {
    Set-Content -Path $prof -Value $txt -Encoding UTF8 -NoNewline
    Write-Host ("startup: removed MQTT retain scripts -> {0}" -f $prof)
  }
  if (Test-Path $patchPy) {
    $pyArgs = @($patchPy, 'retarget-jython', '--profile', $prof)
    foreach ($name in $retargetNames) {
      $pyArgs += @('--script', $name)
    }
    & python @pyArgs
    Write-Host ("Start Up retargeted -> preference:jython ({0})" -f $prof)
  }
}

$masts = Join-Path $hart 'cats\scripts\windows\install_cats_masts.ps1'
if (Test-Path $masts) {
  & $masts
}

Write-Host 'apply_hart_package_local done'

$desk = Join-Path $hart 'cats\scripts\windows\create_hart_master_desktop.ps1'
if (Test-Path $desk) {
  & $desk
}
