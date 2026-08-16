$ErrorActionPreference = 'Stop'
# Desktop shortcuts: CATS CTC / CATS ABS / CATS ABS-RO
# Panels: HART_Master.xml (CTC), HART_Master_ABS.xml, HART_Master_ABS_hold.xml
# Prefer local %USERPROFILE%\hart (deployed via SSH sync_hart_package.sh --win).
$Work = $PSScriptRoot
$Desktop = [Environment]::GetFolderPath('Desktop')
$PanelDir = Join-Path $env:USERPROFILE 'hart\cats\panels'
$Hart = Join-Path $env:USERPROFILE 'hart'
New-Item -ItemType Directory -Force -Path $PanelDir | Out-Null
New-Item -ItemType Directory -Force -Path $Hart | Out-Null

foreach ($helper in @(
  'resolve_jmri_profile.ps1',
  'patch_windows_mqtt.ps1',
  'kill_cats.ps1',
  'launch_hart_master.bat',
  'launch_hart_master_abs.bat',
  'launch_hart_master_abs_hold.bat',
  'launch_cats_desktop.bat',
  'crandic.gif',
  'CATS.ICO'
)) {
  $from = Join-Path $Work $helper
  if (Test-Path $from) {
    Copy-Item $from (Join-Path $Hart $helper) -Force
  }
}

foreach ($panel in @(
  'HART_Master.xml',
  'HART_Master_ABS.xml',
  'HART_Master_ABS_hold.xml',
  'HART_sheet_West_Yard.xml'
)) {
  $src = Join-Path $Work $panel
  if (Test-Path $src) {
    Copy-Item $src (Join-Path $PanelDir $panel) -Force
  }
}

# Yard-ladder button icons (Digicon BUTTON paths must exist locally)
$BtnDir = Join-Path $env:USERPROFILE 'hart\cats\resources\buttons'
New-Item -ItemType Directory -Force -Path $BtnDir | Out-Null
$BtnSrc = Join-Path $Work 'buttons'
if (Test-Path $BtnSrc) {
  Copy-Item (Join-Path $BtnSrc '*') $BtnDir -Force
}
# Rewrite Mac absolute icon paths → this Windows hart root (forward slashes OK for Java)
$WinRoot = (Join-Path $env:USERPROFILE 'hart') -replace '\\', '/'
foreach ($panel in @('HART_Master.xml', 'HART_Master_ABS.xml', 'HART_Master_ABS_hold.xml')) {
  $p = Join-Path $PanelDir $panel
  if (-not (Test-Path $p)) { continue }
  $txt = Get-Content -Raw -LiteralPath $p
  $txt2 = [regex]::Replace(
    $txt,
    '(PRIMARY|ALTERNATE)="[^"]*?[/\\]cats[/\\]resources[/\\]buttons[/\\]([^"]+)"',
    { param($m) '{0}="{1}/cats/resources/buttons/{2}"' -f $m.Groups[1].Value, $WinRoot, $m.Groups[2].Value }
  )
  if ($txt2 -ne $txt) {
    Set-Content -LiteralPath $p -Value $txt2 -NoNewline -Encoding UTF8
    Write-Host ("Rewrote button icon paths in {0}" -f $panel)
  }
}

# Remove legacy HART Master* / bare CATS shortcuts if present
foreach ($legacy in @('HART Master', 'HART Master ABS', 'HART Master ABS-RO', 'CATS')) {
  $legacyLnk = Join-Path $Desktop ($legacy + '.lnk')
  if (Test-Path $legacyLnk) {
    Remove-Item $legacyLnk -Force
    Write-Host ("Removed legacy: {0}" -f $legacyLnk)
  }
}

$iconDst = Join-Path $Hart 'CATS.ICO'
$Wsh = New-Object -ComObject WScript.Shell

$shortcuts = @(
  @{
    Name = 'CATS CTC'
    Bat  = 'launch_hart_master.bat'
    Desc = 'CATS Digicon - CTC (HART_Master.xml)'
  },
  @{
    Name = 'CATS ABS'
    Bat  = 'launch_hart_master_abs.bat'
    Desc = 'CATS Digicon - ABS open house (HART_Master_ABS.xml)'
  },
  @{
    Name = 'CATS ABS-RO'
    Bat  = 'launch_hart_master_abs_hold.bat'
    Desc = 'CATS Digicon - ABS-RO hold/listen (HART_Master_ABS_hold.xml)'
  }
)

foreach ($s in $shortcuts) {
  $batLocal = Join-Path $Work $s.Bat
  if (-not (Test-Path $batLocal)) { throw "Missing $batLocal" }

  $lnkPath = Join-Path $Desktop ($s.Name + '.lnk')
  if (Test-Path $lnkPath) { Remove-Item $lnkPath -Force }
  $Sc = $Wsh.CreateShortcut($lnkPath)
  $Sc.TargetPath = $batLocal
  $Sc.WorkingDirectory = $Work
  $Sc.WindowStyle = 1
  $Sc.Description = $s.Desc
  if (Test-Path $iconDst) { $Sc.IconLocation = "$iconDst,0" }
  $Sc.Save()
  Write-Host ("Desktop: {0} -> {1}" -f $lnkPath, $batLocal)
}

Write-Host 'DONE - Desktop has CATS CTC, CATS ABS, CATS ABS-RO only'
