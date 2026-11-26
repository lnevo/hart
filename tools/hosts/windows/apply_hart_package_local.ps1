# Apply the HART package in a temporary drop folder into JMRI_UserFiles, the profile's user files.
# Called by sync_hart_package.sh --win over SSH, which removes the drop afterwards.
param([Parameter(Mandatory = $true)][string]$Hart, [string]$OverwriteOps = '1', [string]$UserFiles = '')
$ErrorActionPreference = 'Stop'
# The deploy passes HART_WIN_USERFILES here, so install, panel paths, stamp and deploy_status agree.
if (-not $UserFiles) { $UserFiles = Join-Path $env:USERPROFILE 'JMRI_UserFiles' }
$UserFiles = $UserFiles -replace '/', '\'

# Win32-OpenSSH 10.x starts ssh sessions with the machine PATH only. Python is installed
# per user, so put the user PATH first (GetEnvironmentVariable expands it) so that per-user
# Python wins over any other python on the machine PATH.
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath) {
  $first = @($userPath -split ';' | Where-Object { $_ })
  $norm = @($first | ForEach-Object { $_.TrimEnd('\') })
  $rest = @($env:Path -split ';' | Where-Object { $_ -and ($norm -notcontains $_.TrimEnd('\')) })
  $env:Path = (@($first) + @($rest)) -join ';'
}

# Pick a Python 3: the py launcher, then python, then python3. python.exe and python3.exe
# under WindowsApps are Microsoft Store stubs that do not run scripts, so they are skipped,
# and each candidate must start a Python 3 (py -3 with no runtime installed fails here).
function Find-Python {
  foreach ($c in @(@('py', '-3'), @('python'), @('python3'))) {
    $cmd = Get-Command $c[0] -CommandType Application -ErrorAction SilentlyContinue |
      Where-Object { $_.Source -notmatch '\\WindowsApps\\' } | Select-Object -First 1
    if ($cmd) {
      $pre = @($c | Select-Object -Skip 1)
      & $cmd.Source @pre -c 'import sys; sys.exit(0 if sys.version_info[0] == 3 else 1)' 2>$null
      if ($LASTEXITCODE -eq 0) {
        return [pscustomobject]@{ Exe = $cmd.Source; Pre = $pre }
      }
    }
  }
  return $null
}
$python = Find-Python

$src = Join-Path $hart 'tables.xml'
if (Test-Path $src) {
  $dests = New-Object System.Collections.Generic.List[string]
  [void]$dests.Add((Join-Path $UserFiles 'tables.xml'))
  foreach ($d in ($dests | Select-Object -Unique)) {
    $dir = Split-Path $d -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    Copy-Item $src $d -Force
    Write-Host ("tables.xml -> {0}" -f $d)
  }
} else {
  Write-Host 'No tables.xml in the drop (skip tables)'
}

# Operations Pro files (ADR-015). The repo wins; OverwriteOps 0 skips them while JMRI runs.
$opsSrc = Join-Path $hart 'operations'
if (Test-Path $opsSrc) {
  $opsDest = Join-Path $UserFiles 'operations'
  if ($OverwriteOps -ne '1' -and (Get-Process java -ErrorAction SilentlyContinue)) {
    Write-Host 'SKIP Operations files: JMRI is running and would overwrite them. Deploy again with it closed.'
  } else {
    New-Item -ItemType Directory -Force -Path $opsDest | Out-Null
    Get-ChildItem $opsDest -Filter 'Operations*.xml' -File -ErrorAction SilentlyContinue |
      Where-Object { Test-Path (Join-Path $opsSrc $_.Name) } | ForEach-Object {
        $backup = Join-Path $opsDest 'backups\pre_deploy'
        New-Item -ItemType Directory -Force -Path $backup | Out-Null
        Copy-Item $_.FullName $backup -Force
      }
    Copy-Item (Join-Path $opsSrc '*.xml') $opsDest -Force
    Write-Host ("Operations files -> {0}" -f $opsDest)
  }
}

# The DecoderPro roster (ADR-039 amendment 2026-11-26): roster.xml and the entry files it names. The repo wins, as
# for the Operations files: what it replaces is kept in backups\roster\pre_deploy_<time>. Windows has no unpulled
# check (its roster is a copy; the Pi's is the one DecoderPro programs), so its own edits live only in that backup.
# Files roster.xml does not name (JMRI's *.bak, old entry files) are left as they are.
$rosterPkg = Join-Path $hart 'roster'
$rosterIndex = Join-Path $rosterPkg 'roster.xml'
if (-not (Test-Path $rosterIndex)) { throw "No roster\roster.xml in the drop $hart; the roster was not installed" }
$rosterNames = @([regex]::Matches([System.IO.File]::ReadAllText($rosterIndex), '<locomotive [^>]*fileName="([^"]*)"') |
  ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
if ($rosterNames.Count -eq 0) { throw "roster.xml in the drop names no locomotive file; the roster was not installed" }
foreach ($n in $rosterNames) {
  if ($n -match '[\\/]' -or $n.StartsWith('.') -or -not $n.EndsWith('.xml')) {
    throw "roster.xml in the drop names '$n', which is not a plain roster\*.xml file name; the roster was not installed"
  }
  if (-not (Test-Path (Join-Path $rosterPkg ('roster\' + $n)))) {
    throw "roster.xml in the drop names roster\$n, which the drop lacks; the roster was not installed"
  }
}
$rosterDest = Join-Path $UserFiles 'roster'
$rosterRel = @('roster.xml') + @($rosterNames | ForEach-Object { 'roster\' + $_ })
function Test-RosterCurrent {
  foreach ($n in $rosterRel) {
    $live = Join-Path $UserFiles $n
    if (-not (Test-Path $live)) { return $false }
    if ((Get-FileHash (Join-Path $rosterPkg $n) -Algorithm SHA256).Hash -ne (Get-FileHash $live -Algorithm SHA256).Hash) { return $false }
  }
  return $true
}
if (Test-RosterCurrent) {
  Write-Host ("DecoderPro roster already current -> {0}" -f $UserFiles)
} else {
  New-Item -ItemType Directory -Force -Path $rosterDest | Out-Null
  $rosterBackup = Join-Path $UserFiles ('backups\roster\pre_deploy_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
  New-Item -ItemType Directory -Force -Path (Join-Path $rosterBackup 'roster') | Out-Null
  $liveIndex = Join-Path $UserFiles 'roster.xml'
  if (Test-Path $liveIndex) { Copy-Item $liveIndex $rosterBackup -Force }
  foreach ($n in $rosterNames) {
    $live = Join-Path $rosterDest $n
    if (Test-Path $live) { Copy-Item $live (Join-Path $rosterBackup 'roster') -Force }
    Copy-Item (Join-Path $rosterPkg ('roster\' + $n)) $live -Force
  }
  # roster.xml last: JMRI reads the index first, so it only names files already in place.
  Copy-Item $rosterIndex $liveIndex -Force
  if (-not (Test-RosterCurrent)) { throw "after the install the roster in $UserFiles is not the repo's; what it replaced is in $rosterBackup" }
  Write-Host ("DecoderPro roster -> {0} ({1} locos; backup {2})" -f $UserFiles, $rosterNames.Count, $rosterBackup)
}

$homeHtml = Join-Path $hart 'cats\resources\jmri-web\servlet\home\Home.html'
# STS and the LCOS mimic run on the Pi: the home page links there by the Pi's own mDNS
# name (its avahi, so it works while JMRI is down).
$PiHost = 'RPi-JMRI.local'
if (Test-Path $homeHtml) {
  $html = [System.IO.File]::ReadAllText($homeHtml)
  $marker = 'var HART_APPS_HOST = "";'
  if ($html.Contains($marker)) {
    $html = $html.Replace($marker, ('var HART_APPS_HOST = "' + $PiHost + '";'))
  } else {
    Write-Warning "Home.html has no '$marker' line; STS and mimic links follow this host"
  }
  $roots = New-Object System.Collections.Generic.List[string]
  [void]$roots.Add($UserFiles)
  foreach ($r in ($roots | Select-Object -Unique)) {
    if (-not (Test-Path $r)) { continue }
    $hd = Join-Path $r 'web\servlet\home'
    New-Item -ItemType Directory -Force -Path $hd | Out-Null
    [System.IO.File]::WriteAllText((Join-Path $hd 'Home.html'), $html, (New-Object System.Text.UTF8Encoding($false)))
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
  [void]$roots.Add($UserFiles)
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

$miscSrc = Join-Path $hart 'cats\resources\misc'
if (Test-Path $miscSrc) {
  $roots = New-Object System.Collections.Generic.List[string]
  [void]$roots.Add($UserFiles)
  foreach ($r in ($roots | Select-Object -Unique)) {
    if (-not (Test-Path $r)) { continue }
    $dest = Join-Path $r 'resources\misc'
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    Copy-Item (Join-Path $miscSrc '*') $dest -Force
    Write-Host ("panel background -> {0}" -f $dest)
  }
}

$rosterSrc = Join-Path $hart 'cats\resources\roster'
if (Test-Path $rosterSrc) {
  $roots = New-Object System.Collections.Generic.List[string]
  [void]$roots.Add($UserFiles)
  foreach ($r in ($roots | Select-Object -Unique)) {
    if (-not (Test-Path $r)) { continue }
    $dest = Join-Path $r 'resources\roster'
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    Copy-Item (Join-Path $rosterSrc '*.jpg') $dest -Force
    Write-Host ("roster photos -> {0}" -f $dest)
  }
}

$ussSrc = Join-Path $hart 'cats\resources\icons\USS\sensor'
if (Test-Path $ussSrc) {
  $roots = New-Object System.Collections.Generic.List[string]
  [void]$roots.Add($UserFiles)
  $gifs = @(Get-ChildItem $ussSrc -Filter 'yellow-*.gif' -ErrorAction SilentlyContinue)
  foreach ($r in ($roots | Select-Object -Unique)) {
    # tables.xml loads these through preference:, so the profile copy must exist.
    $dest = Join-Path $r 'resources\icons\USS\sensor'
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    foreach ($g in $gifs) {
      Copy-Item $g.FullName $dest -Force
    }
    Write-Host ("USS sensor icons -> {0}\resources\icons\USS\sensor" -f $r)
  }
}

$ctcSrc = Join-Path $hart 'ctc'
if (Test-Path (Join-Path $ctcSrc 'icons')) {
  $roots = New-Object System.Collections.Generic.List[string]
  [void]$roots.Add($UserFiles)
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
  # A parked USS CTC machine (hartlib.parked) ships no icons: the installed copies stay as they are.
  Write-Host 'No ctc icons in the drop (parked or absent): ctc left as it is'
}

$jythonSrc = @(
  (Join-Path $hart 'jmri\layouts\hart\scripts\hide_cats_desk_windows.py'),
  (Join-Path $hart 'jmri\layouts\hart\scripts\hide_band_panels.py'),
  (Join-Path $hart 'jmri\layouts\hart\scripts\panel_status.py'),
  # panel_status.py's PARTS: installed beside it, not Start Up items.
  (Join-Path $hart 'jmri\layouts\hart\scripts\panel_status_clicks.py'),
  (Join-Path $hart 'jmri\layouts\hart\scripts\panel_status_turnouts.py'),
  (Join-Path $hart 'jmri\layouts\hart\scripts\jmri_cmd_watcher.py'),
  (Join-Path $hart 'jmri\scripts\signal_coordinator.py'),
  # signal_coordinator.py's SIBLING_MODULES: installed beside it, not Start Up items.
  (Join-Path $hart 'jmri\scripts\sml_beans.py'),
  (Join-Path $hart 'jmri\scripts\sml_claims.py'),
  (Join-Path $hart 'jmri\scripts\sml_handoff.py'),
  (Join-Path $hart 'jmri\scripts\sml_events.py'),
  (Join-Path $hart 'jmri\scripts\sml_quit.py'),
  (Join-Path $hart 'jmri\scripts\sml_ui.py'),
  # The loader signal_coordinator.py and panel_status.py import their siblings with: not a Start Up item.
  (Join-Path $hart 'jmri\scripts\jython_siblings.py')
)
$trainInfoSrc = Join-Path $hart 'jmri\layouts\hart\dispatcher\traininfo'
$roots = New-Object System.Collections.Generic.List[string]
[void]$roots.Add($UserFiles)
foreach ($r in ($roots | Select-Object -Unique)) {
  if (-not (Test-Path $r)) { continue }
  $dest = Join-Path $r 'jython'
  New-Item -ItemType Directory -Force -Path $dest | Out-Null
  foreach ($src in $jythonSrc) {
    if (Test-Path $src) {
      Copy-Item $src (Join-Path $dest (Split-Path $src -Leaf)) -Force
    }
    # Jython's compiled copy of a module it imported: Copy-Item keeps the source's time, so a class
    # not older than the new .py (a rollback, a clock skew) would be reused.
    $compiled = Join-Path $dest ([System.IO.Path]::GetFileNameWithoutExtension($src) + '$py.class')
    if (Test-Path -LiteralPath $compiled) { Remove-Item -LiteralPath $compiled -Force }
  }
  Write-Host ("preference:jython scripts -> {0}\jython" -f $r)
  if (Test-Path $trainInfoSrc) {
    $trainInfoDest = Join-Path $r 'dispatcher\traininfo'
    New-Item -ItemType Directory -Force -Path $trainInfoDest | Out-Null
    # /PURGE: the profile mirrors the repo, so routes from old names do not linger in the Dispatcher picker.
    & robocopy $trainInfoSrc $trainInfoDest *.xml /PURGE /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
    if ($LASTEXITCODE -ge 8) {
      throw ("robocopy traininfo failed ({0}) -> {1}" -f $LASTEXITCODE, $trainInfoDest)
    }
    Write-Host ("Dispatcher traininfo -> {0}\dispatcher\traininfo" -f $r)
  } else {
    # A parked Dispatcher System (hartlib.parked) ships no traininfo: the installed copies stay as they are.
    Write-Host ("Dispatcher traininfo not in the package (parked): {0}\dispatcher left as it is" -f $r)
  }
}

$retargetNames = @(
  'panel_status.py',
  'signal_coordinator.py',
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
# Start Up entries for retired scripts stay in an old profile.xml until stripped: the shared one and each
# per-computer profile\<node id>\profile.xml, which JMRI reads first.
$retiredStartup = @('apply_maintain_mqtt.py', 'apply_mqtt_retain_at_startup.py', 'prepare_nx_sml_paths.py')
foreach ($r in ($profileRoots | Select-Object -Unique)) {
  $profiles = @(Join-Path $r 'profile\profile.xml') + @(Get-ChildItem (Join-Path $r 'profile') -Directory -ErrorAction SilentlyContinue | ForEach-Object { Join-Path $_.FullName 'profile.xml' })
  foreach ($px in $profiles) {
    if (-not (Test-Path -LiteralPath $px)) { continue }
    $txt = Get-Content -Raw -Encoding UTF8 -LiteralPath $px
    $orig = $txt
    foreach ($name in $retiredStartup) {
      $txt = [regex]::Replace($txt, ('\r?\n[ \t]*<perform\b[^>]*' + [regex]::Escape($name) + '[^>]*/>'), '')
    }
    if ($txt -ne $orig) {
      Set-Content -LiteralPath $px -Value $txt -Encoding UTF8 -NoNewline
      Write-Host ("startup: removed retired Start Up scripts -> {0}" -f $px)
    }
  }
}
foreach ($r in ($profileRoots | Select-Object -Unique)) {
  $prof = Join-Path $r 'profile\profile.xml'
  if (-not (Test-Path $prof)) { continue }
  if (Test-Path $patchPy) {
    if (-not $python) {
      Write-Warning ("Start Up retarget skipped: no Python 3 found (py -3, python, python3); check the Start Up list by hand ({0})" -f $prof)
    } else {
      $pyArgs = @($python.Pre) + @($patchPy, 'retarget-jython', '--profile', $prof)
      foreach ($name in $retargetNames) {
        $pyArgs += @('--script', $name)
      }
      & $python.Exe @pyArgs
      if ($LASTEXITCODE -ne 0) { throw ("Start Up retarget failed: {0} exited {1} ({2})" -f $python.Exe, $LASTEXITCODE, $prof) }
      Write-Host ("Start Up retargeted -> preference:jython ({0})" -f $prof)
    }
  }
}

# JMRI's MQTT startup race overlay, loaded by every JMRI app through %USERPROFILE%\JMRI\jmri.conf
# (ADR-034). It installs only over the JMRI build it was made from; on any other it takes itself out.
$overlayPy = Join-Path $hart 'jmri\mqtt_overlay\install_overlay.py'
if (Test-Path $overlayPy) {
  $jmriHome = @('C:\Program Files\JMRI', 'C:\Program Files (x86)\JMRI', 'C:\JMRI', (Join-Path $env:USERPROFILE 'JMRI')) |
    Where-Object { Test-Path (Join-Path $_ 'jmri.jar') } | Select-Object -First 1
  if (-not $python) {
    Write-Host 'WARNING MQTT overlay: no Python 3 found; not installed'
  } elseif (-not $jmriHome) {
    Write-Host 'WARNING MQTT overlay: no JMRI install with jmri.jar found; not installed'
  } else {
    $pre = @($python.Pre)
    & $python.Exe @pre $overlayPy --jar (Join-Path $hart 'jmri\mqtt_overlay\hart-mqtt-race-fix.jar') `
      --settings-dir (Join-Path $env:USERPROFILE 'JMRI') --jmri-home $jmriHome
    if ($LASTEXITCODE -ne 0) { Write-Host "WARNING MQTT overlay: install_overlay.py exited $LASTEXITCODE" }
  }
}

Write-Host 'apply_hart_package_local done'

$desk = Join-Path $hart 'cats\scripts\windows\create_cats_desktop.ps1'
if (Test-Path $desk) {
  & $desk -UserFiles $UserFiles
}

# Last, so the stamp names a deploy only once everything above has been installed.
$stamp = Join-Path $hart 'cats\deploy_stamp.txt'
if (Test-Path $stamp) {
  $catsHome = Join-Path $UserFiles 'cats'
  New-Item -ItemType Directory -Force -Path $catsHome | Out-Null
  Copy-Item $stamp (Join-Path $catsHome 'deploy_stamp.txt') -Force
  Write-Host ("deploy stamp -> {0}\deploy_stamp.txt" -f $catsHome)
}
