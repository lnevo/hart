$ErrorActionPreference = 'Stop'
# Create Desktop shortcuts for HART Master (CTC) and HART Master ABS.
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
  'launch_cats_desktop.bat',
  'crandic.gif',
  'CATS.ICO'
)) {
  $from = Join-Path $Work $helper
  if (Test-Path $from) {
    Copy-Item $from (Join-Path $Hart $helper) -Force
  }
}

foreach ($panel in @('HART_Master.xml', 'HART_Master_ABS.xml', 'HART_sheet_West_Yard.xml')) {
  $src = Join-Path $Work $panel
  if (Test-Path $src) {
    Copy-Item $src (Join-Path $PanelDir $panel) -Force
  }
}

$iconDst = Join-Path $Hart 'CATS.ICO'
$Wsh = New-Object -ComObject WScript.Shell

$shortcuts = @(
  @{
    Name = 'HART Master'
    Bat  = 'launch_hart_master.bat'
    Desc = 'CATS Digicon - HART Master (CTC)'
  },
  @{
    Name = 'HART Master ABS'
    Bat  = 'launch_hart_master_abs.bat'
    Desc = 'CATS Digicon - HART Master ABS (open house)'
  },
  @{
    Name = 'CATS'
    Bat  = 'launch_hart_master.bat'
    Desc = 'CATS Digicon - HART Master (CTC) default'
  }
)

foreach ($s in $shortcuts) {
  $batDropbox = Join-Path $Work $s.Bat
  $batLocal = Join-Path $Hart $s.Bat
  if (-not (Test-Path $batDropbox)) { throw "Missing $batDropbox" }
  $target = if (Test-Path $batDropbox) { $batDropbox } else { $batLocal }

  $lnkPath = Join-Path $Desktop ($s.Name + '.lnk')
  if (Test-Path $lnkPath) { Remove-Item $lnkPath -Force }
  $Sc = $Wsh.CreateShortcut($lnkPath)
  $Sc.TargetPath = $target
  $Sc.WorkingDirectory = $Work
  $Sc.WindowStyle = 1
  $Sc.Description = $s.Desc
  if (Test-Path $iconDst) { $Sc.IconLocation = "$iconDst,0" }
  $Sc.Save()
  Write-Host ("Desktop: {0} -> {1}" -f $lnkPath, $target)
}

Write-Host 'DONE - Desktop has HART Master, HART Master ABS, and CATS'
