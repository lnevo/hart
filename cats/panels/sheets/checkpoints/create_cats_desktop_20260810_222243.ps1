$ErrorActionPreference = 'Stop'
# Desktop shortcuts only: CATS / CATS ABS / CATS ABS-RO
# Panels: HART_Master.xml (CTC), HART_Master_ABS.xml, HART_Master_ABS_hold.xml
# Prefer Dropbox pack so sync updates apply immediately.
$Work = $PSScriptRoot
$Desktop = [Environment]::GetFolderPath('Desktop')
$PanelDir = Join-Path $env:USERPROFILE 'hart\cats\panels\sheets'
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

# Remove legacy HART Master* shortcuts if present
foreach ($legacy in @('HART Master', 'HART Master ABS', 'HART Master ABS-RO')) {
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
    Name = 'CATS'
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
  $batDropbox = Join-Path $Work $s.Bat
  if (-not (Test-Path $batDropbox)) { throw "Missing $batDropbox" }

  $lnkPath = Join-Path $Desktop ($s.Name + '.lnk')
  if (Test-Path $lnkPath) { Remove-Item $lnkPath -Force }
  $Sc = $Wsh.CreateShortcut($lnkPath)
  $Sc.TargetPath = $batDropbox
  $Sc.WorkingDirectory = $Work
  $Sc.WindowStyle = 1
  $Sc.Description = $s.Desc
  if (Test-Path $iconDst) { $Sc.IconLocation = "$iconDst,0" }
  $Sc.Save()
  Write-Host ("Desktop: {0} -> {1}" -f $lnkPath, $batDropbox)
}

Write-Host 'DONE - Desktop has CATS, CATS ABS, CATS ABS-RO only'
