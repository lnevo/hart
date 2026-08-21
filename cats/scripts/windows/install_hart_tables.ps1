$ErrorActionPreference = 'Stop'
$Work = $PSScriptRoot
$src = Join-Path $Work 'tables.xml'
if (-not (Test-Path $src)) {
  throw ("Missing {0} - run from hart package dir (or use sync_hart_package.sh --win from Mac)" -f $src)
}

# Quit only JMRI/CATS Java (leave other Java apps alone)
Write-Host 'Stopping CATS/JMRI Java processes only...'
$catsPatterns = @(
  'cats\.apps\.Crandic',
  'cats\.apps\.',
  'apps\.PanelPro',
  'jmri\.PanelPro',
  'apps\.DecoderPro',
  'apps\.DispatcherPro',
  'apps\.SoundPro',
  'apps\.LccPro',
  'jmri\.jmrit',
  'LaunchJMRI',
  '[\\/]cats\.jar',
  '[\\/]designer\.jar',
  'designer\.gui',
  'TrainStat'
)
$rx = [string]::Join('|', $catsPatterns)
$killed = @()
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    $_.Name -match '^(java|javaw|javaws)\.exe$' -and
    $_.CommandLine -and
    $_.CommandLine -match $rx
  } |
  ForEach-Object {
    Write-Host ("  kill PID {0} {1}" -f $_.ProcessId, $_.Name)
    Write-Host ("    {0}" -f ($_.CommandLine.Substring(0, [Math]::Min(160, $_.CommandLine.Length))))
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    $killed += $_.ProcessId
  }
if ($killed.Count -gt 0) {
  Start-Sleep -Seconds 2
  foreach ($procId in $killed) {
    if (Get-Process -Id $procId -ErrorAction SilentlyContinue) {
      & taskkill.exe /F /PID $procId 2>$null | Out-Null
    }
  }
  Start-Sleep -Seconds 1
  Write-Host ("Stopped {0} CATS/JMRI process(es)." -f $killed.Count)
} else {
  Write-Host 'No CATS/JMRI Java processes running.'
}

$srcFull = (Resolve-Path $src).Path
$workFull = (Resolve-Path $Work).Path
$len = (Get-Item $src).Length
Write-Host ("Source: {0} ({1} bytes)" -f $srcFull, $len)
if (-not (Select-String -Path $src -Pattern 'My Layout' -SimpleMatch -Quiet)) {
  throw 'tables.xml missing My Layout LogixNG marker'
}
Write-Host 'LogixNG My Layout minimize: OK'

function Is-SyncPackPath([string]$path) {
  if (-not $path) { return $false }
  $p = $path.ToLowerInvariant().Replace('/', '\')
  $w = $workFull.ToLowerInvariant().Replace('/', '\')
  return $p.StartsWith($w)
}

$candidates = @()
foreach ($root in @($env:USERPROFILE, 'C:\Users\Lee', 'C:\Users\lnevo') | Select-Object -Unique) {
  if (Test-Path $root) {
    $candidates += Get-ChildItem -Path $root -Filter 'tables.xml' -Recurse -Depth 7 -ErrorAction SilentlyContinue |
      Where-Object {
        $_.FullName -notmatch '\\AppData\\Local\\Temp\\' -and
        -not (Is-SyncPackPath $_.FullName)
      } |
      Select-Object -ExpandProperty FullName
  }
}
$candidates = $candidates | Select-Object -Unique
Write-Host 'Existing tables.xml:'
$candidates | ForEach-Object { Write-Host ("  {0}" -f $_) }

$dests = New-Object System.Collections.Generic.List[string]
foreach ($c in $candidates) { [void]$dests.Add($c) }
foreach ($p in @(
  (Join-Path $env:USERPROFILE 'JMRI_UserFiles\tables.xml'),
  (Join-Path $env:USERPROFILE 'JMRI\tables.xml'),
  (Join-Path $env:USERPROFILE 'Documents\JMRI\tables.xml')
)) {
  $parent = Split-Path $p -Parent
  if ((Test-Path $parent) -and -not (Is-SyncPackPath $p)) { [void]$dests.Add($p) }
}
foreach ($root in @(
  (Join-Path $env:USERPROFILE '.jmri'),
  (Join-Path $env:APPDATA 'JMRI'),
  (Join-Path $env:USERPROFILE 'JMRI')
)) {
  if (Test-Path $root) {
    Get-ChildItem $root -Directory -ErrorAction SilentlyContinue | ForEach-Object {
      $p = Join-Path $_.FullName 'tables.xml'
      if (-not (Is-SyncPackPath $p)) { [void]$dests.Add($p) }
    }
  }
}
$dests = $dests | Select-Object -Unique
if (-not $dests) {
  $fallback = Join-Path $env:USERPROFILE 'JMRI_UserFiles'
  New-Item -ItemType Directory -Force -Path $fallback | Out-Null
  $dests = @(Join-Path $fallback 'tables.xml')
  Write-Host ("No existing tables; using {0}" -f $fallback)
}

$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
foreach ($d in $dests) {
  $dir = Split-Path $d -Parent
  if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }

  $destFull = $d
  if (Test-Path $d) { $destFull = (Resolve-Path $d).Path }
  if ($destFull.ToLowerInvariant() -eq $srcFull.ToLowerInvariant()) {
    Write-Host ("Skip (same file): {0}" -f $d)
    continue
  }
  if (Is-SyncPackPath $d) {
    Write-Host ("Skip (sync pack): {0}" -f $d)
    continue
  }

  if (Test-Path $d) {
    $bak = '{0}.bak_pre_pi_{1}' -f $d, $ts
    Copy-Item $d $bak -Force
    Write-Host ("Backup: {0}" -f $bak)
  }
  Copy-Item $src $d -Force
  Write-Host ("Wrote: {0}" -f $d)
}

$hart = Join-Path $env:USERPROFILE 'hart\cats\panels\sheets'
New-Item -ItemType Directory -Force -Path $hart | Out-Null
$panelSrc = Join-Path $Work 'HART_sheet_West_Yard.xml'
$panelDst = Join-Path $hart 'HART_sheet_West_Yard.xml'
Copy-Item $panelSrc $panelDst -Force
Write-Host ("Panel -> {0}" -f $panelDst)

# Always install to a user-writable JMRI home (no admin needed).
$userJmri = Join-Path $env:USERPROFILE 'JMRI'
New-Item -ItemType Directory -Force -Path $userJmri | Out-Null

$jmriHomes = @(
  $userJmri,
  'C:\JMRI',
  'C:\Program Files\JMRI',
  'C:\Program Files (x86)\JMRI'
) | Where-Object { Test-Path $_ } | Select-Object -Unique
Write-Host 'JMRI homes:'
$jmriHomes | ForEach-Object { Write-Host ("  {0}" -f $_) }

$jarOk = 0
$jarSkip = 0
foreach ($jh in $jmriHomes) {
  foreach ($jar in @('cats.jar', 'designer.jar')) {
    $from = Join-Path $Work $jar
    if (-not (Test-Path $from)) { continue }
    $to = Join-Path $jh $jar
    try {
      if (Test-Path $to) {
        Copy-Item $to ('{0}.bak_pre_pi_{1}' -f $to, $ts) -Force -ErrorAction Stop
      }
      Copy-Item $from $to -Force -ErrorAction Stop
      Write-Host ("Installed {0}" -f $to)
      $jarOk++
    } catch {
      Write-Host ("Skip (need Admin for Program Files): {0}" -f $to)
      Write-Host ("  {0}" -f $_.Exception.Message)
      $jarSkip++
    }
  }
  $batFrom = Join-Path $Work 'cats.bat'
  if (Test-Path $batFrom) {
    try {
      Copy-Item $batFrom (Join-Path $jh 'cats.bat') -Force -ErrorAction Stop
    } catch {
      Write-Host ("Skip cats.bat: {0}" -f $jh)
    }
  }
}
if ($jarOk -eq 0) {
  throw 'Could not install cats.jar anywhere. Check permissions.'
}
Write-Host ("Jar install OK={0} skipped={1} (desktop CATS uses %USERPROFILE%\JMRI)" -f $jarOk, $jarSkip)

# Resolve THIS PC's My JMRI Railroad profile id (Windows hash differs from Mac)
$resolver = Join-Path $Work 'resolve_jmri_profile.ps1'
$idFile = Join-Path $env:USERPROFILE 'hart\jmri_profile_id.txt'
New-Item -ItemType Directory -Force -Path (Split-Path $idFile -Parent) | Out-Null
Copy-Item $resolver (Join-Path $env:USERPROFILE 'hart\resolve_jmri_profile.ps1') -Force

$profileId = $null
if (Test-Path $resolver) {
  Write-Host 'Resolving Windows JMRI profile id...'
  & powershell -NoProfile -ExecutionPolicy Bypass -File $resolver -OutFile $idFile -SetActive
  if (Test-Path $idFile) {
    $profileId = (Get-Content $idFile -Raw).Trim()
  }
}
if (-not $profileId) {
  throw 'Could not resolve My JMRI Railroad profile id on this Windows machine. Open PanelPro once, select that profile, then re-run.'
}
Write-Host ("Using profile id: {0}" -f $profileId)

# Copy helper scripts into %%USERPROFILE%%\hart
foreach ($helper in @('resolve_jmri_profile.ps1', 'patch_windows_mqtt.ps1', 'kill_cats.ps1', 'launch_cats_desktop.bat')) {
  $from = Join-Path $Work $helper
  if (Test-Path $from) {
    Copy-Item $from (Join-Path $env:USERPROFILE "hart\$helper") -Force
  }
}

# MQTT: Pi broker on ICS, not minipc-e5h6x.local (Windows self / long hang)
$mqttPatch = Join-Path $Work 'patch_windows_mqtt.ps1'
if (Test-Path $mqttPatch) {
  Write-Host 'Patching Windows MQTT broker address -> 192.168.137.2 ...'
  & powershell -NoProfile -ExecutionPolicy Bypass -File $mqttPatch
}

# Ensure tables.xml is in the matching *.jmri profile folder(s)
$jmriRoots = @(
  (Join-Path $env:APPDATA 'JMRI'),
  (Join-Path $env:USERPROFILE '.jmri'),
  (Join-Path $env:USERPROFILE 'JMRI')
) | Where-Object { Test-Path $_ } | Select-Object -Unique
Get-ChildItem 'C:\Users' -Directory -ErrorAction SilentlyContinue | ForEach-Object {
  foreach ($rel in @('AppData\Roaming\JMRI', '.jmri', 'JMRI')) {
    $p = Join-Path $_.FullName $rel
    if (Test-Path $p) { $jmriRoots += $p }
  }
}
$jmriRoots = $jmriRoots | Select-Object -Unique

foreach ($r in $jmriRoots) {
  $profDir = Get-ChildItem $r -Directory -ErrorAction SilentlyContinue |
    Where-Object {
      $_.Name -like 'My_JMRI_Railroad*' -or
      (Test-Path (Join-Path $_.FullName 'profile\profile.properties') -and
        (Select-String -Path (Join-Path $_.FullName 'profile\profile.properties') -Pattern 'profile\.name=My JMRI Railroad' -Quiet))
    } |
    Select-Object -First 1
  if ($profDir) {
    $profTables = Join-Path $profDir.FullName 'tables.xml'
    if ($profTables.ToLowerInvariant() -ne $srcFull.ToLowerInvariant()) {
      Copy-Item $src $profTables -Force
      Write-Host ("Wrote profile tables: {0}" -f $profTables)
    }
  }
}

# Desktop launcher + CATS shortcut (local hart copy)
$launchSrc = Join-Path $Work 'launch_cats_desktop.bat'
if (-not (Test-Path $launchSrc)) { throw 'Missing launch_cats_desktop.bat in package dir' }
$launchLines = Get-Content $launchSrc | Where-Object { $_ -notmatch '^\s*REM\b' -and $_ -notmatch '^\s*::' }
$join = ($launchLines -join "`n")
if ($join -match 'LaunchJMRI\.exe.*--profile') {
  throw 'launch_cats_desktop.bat still passes --profile to LaunchJMRI'
}
if ($join -notmatch 'LaunchJMRI\.exe\s+/profile\b') {
  throw 'launch_cats_desktop.bat missing LaunchJMRI /profile'
}
$launchDst = Join-Path $env:USERPROFILE 'hart\launch_cats_desktop.bat'
Copy-Item $launchSrc $launchDst -Force
Write-Host ("Launcher pack: {0}" -f $launchSrc)
Write-Host ("Launcher copy: {0}" -f $launchDst)

$iconSrc = Join-Path $Work 'CATS.ICO'
$iconDst = Join-Path $env:USERPROFILE 'hart\CATS.ICO'
if (Test-Path $iconSrc) { Copy-Item $iconSrc $iconDst -Force }

$Desktop = [Environment]::GetFolderPath('Desktop')
$LnkPath = Join-Path $Desktop 'CATS.lnk'
if (Test-Path $LnkPath) { Remove-Item $LnkPath -Force }
$Wsh = New-Object -ComObject WScript.Shell
$Sc = $Wsh.CreateShortcut($LnkPath)
$Sc.TargetPath = $launchDst
$Sc.WorkingDirectory = (Split-Path $launchDst -Parent)
$Sc.WindowStyle = 1
$Sc.Description = 'CATS Digicon - HART'
if (Test-Path $iconDst) { $Sc.IconLocation = ($iconDst + ',0') }
$Sc.Save()
Write-Host ("Desktop shortcut: {0}" -f $LnkPath)
Write-Host ("Shortcut target:  {0}" -f $launchDst)

# JMRI web home override — STS link (Shipper-driven Traffic Simulator)
$webSrc = Join-Path $Work 'jmri-web'
if (-not (Test-Path $webSrc)) {
  $webSrc = Join-Path $Work 'cats\resources\jmri-web'
}
if (Test-Path (Join-Path $webSrc 'servlet\home\Home.html')) {
  $webDests = New-Object System.Collections.Generic.List[string]
  foreach ($p in @(
    (Join-Path $env:USERPROFILE 'JMRI_UserFiles'),
    (Join-Path $env:USERPROFILE 'JMRI'),
    (Join-Path $env:USERPROFILE 'Documents\JMRI')
  )) {
    if (Test-Path $p) { [void]$webDests.Add($p) }
  }
  foreach ($r in $jmriRoots) {
    Get-ChildItem $r -Directory -ErrorAction SilentlyContinue | ForEach-Object {
      if ($_.Name -like '*.jmri' -or $_.Name -like 'My_JMRI_Railroad*') {
        [void]$webDests.Add($_.FullName)
      }
    }
  }
  $webDests = $webDests | Select-Object -Unique
  foreach ($root in $webDests) {
    $homeDir = Join-Path $root 'web\servlet\home'
    New-Item -ItemType Directory -Force -Path $homeDir | Out-Null
    Copy-Item (Join-Path $webSrc 'servlet\home\Home.html') (Join-Path $homeDir 'Home.html') -Force
    if (Test-Path (Join-Path $webSrc 'sts.html')) {
      New-Item -ItemType Directory -Force -Path (Join-Path $root 'web') | Out-Null
      Copy-Item (Join-Path $webSrc 'sts.html') (Join-Path $root 'web\sts.html') -Force
    }
    Write-Host ("JMRI web STS override -> {0}\web" -f $root)
  }
} else {
  Write-Host 'Skip JMRI web override (jmri-web/ not in pack)'
}

# JMRI Start Up Python → %USERPROFILE%\hart\jmri\... (profile uses home:hart/jmri/...)
$hartJmri = Join-Path $env:USERPROFILE 'hart\jmri'
$layoutDst = Join-Path $hartJmri 'layouts\hart\scripts'
$pubDst = Join-Path $hartJmri 'scripts'
New-Item -ItemType Directory -Force -Path $layoutDst | Out-Null
New-Item -ItemType Directory -Force -Path $pubDst | Out-Null

function Copy-PackScript([string]$name, [string]$destDir) {
  $candidates = @(
    (Join-Path $Work "jmri\layouts\hart\scripts\$name"),
    (Join-Path $Work "jmri\scripts\$name"),
    (Join-Path $Work "jmri_scripts\$name"),
    (Join-Path $Work $name)
  )
  foreach ($c in $candidates) {
    if (Test-Path $c) {
      Copy-Item $c (Join-Path $destDir $name) -Force
      Write-Host ("JMRI script -> {0}\{1}" -f $destDir, $name)
      return $true
    }
  }
  Write-Host ("Skip missing script: {0}" -f $name)
  return $false
}

foreach ($s in @(
  'discover_sml.py',
  'sync_yard_ladder_buttons.py',
  'add_yard_ladder_le_icons.py',
  'install_yl_windows.py'
)) {
  [void](Copy-PackScript $s $layoutDst)
}
[void](Copy-PackScript 'mqtt_signalhead_publisher.py' $pubDst)
if (Test-Path (Join-Path $Work 'signal_wiring.csv')) {
  $dataDir = Join-Path $env:USERPROFILE 'hart\cats\data'
  New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
  Copy-Item (Join-Path $Work 'signal_wiring.csv') (Join-Path $dataDir 'signal_wiring.csv') -Force
  Write-Host ("signal_wiring.csv -> {0}" -f $dataDir)
}

Write-Host 'DONE - restart JMRI/CATS to load tables.xml / web home / startup scripts'
pause
