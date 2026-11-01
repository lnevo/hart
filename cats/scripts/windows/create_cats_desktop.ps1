$ErrorActionPreference = 'Stop'
# Desktop shortcuts: CATS CTC + CATS ABS (HOLD_ONLY; JMRI SML owns aspects)
$Work = $PSScriptRoot
$Desktop = [Environment]::GetFolderPath('Desktop')
# CATS has no JMRI home: it opens real paths, so its files live in JMRI_UserFiles\cats.
$CatsHome = Join-Path $env:USERPROFILE 'JMRI_UserFiles\cats'
$PanelDir = Join-Path $CatsHome 'panels'
$Launch = Join-Path $CatsHome 'launch'
New-Item -ItemType Directory -Force -Path $PanelDir | Out-Null
New-Item -ItemType Directory -Force -Path $Launch | Out-Null

foreach ($helper in @(
  'resolve_jmri_profile.ps1',
  'patch_windows_mqtt.ps1',
  'kill_cats.ps1',
  'launch_cats_ctc.bat',
  'launch_cats_abs.bat',
  'launch_cats_desktop.bat',
  'CATS.ICO'
)) {
  Copy-Item (Join-Path $Work $helper) (Join-Path $Launch $helper) -Force
}

# Deploy has already pointed the panels' button paths at JMRI_UserFiles.
$PanelSrc = Join-Path $Work '..\..\panels'
foreach ($panel in @('HART_CTC.xml', 'HART_ABS.xml')) {
  Copy-Item (Join-Path $PanelSrc $panel) (Join-Path $PanelDir $panel) -Force
}

foreach ($legacy in @(
  'HART Master', 'HART Master ABS', 'HART Master ABS-RO', 'CATS',
  'CATS CTC SML', 'CATS ABS-RO'
)) {
  $legacyLnk = Join-Path $Desktop ($legacy + '.lnk')
  if (Test-Path $legacyLnk) {
    Remove-Item $legacyLnk -Force
    Write-Host ("Removed legacy: {0}" -f $legacyLnk)
  }
}

$iconDst = Join-Path $Launch 'CATS.ICO'
$Wsh = New-Object -ComObject WScript.Shell

$shortcuts = @(
  @{
    Name = 'CATS CTC'
    Bat  = 'launch_cats_ctc.bat'
    Desc = 'CATS Digicon CTC (HOLD_ONLY; JMRI SML aspects)'
  },
  @{
    Name = 'CATS ABS'
    Bat  = 'launch_cats_abs.bat'
    Desc = 'CATS Digicon ABS (HOLD_ONLY; JMRI SML aspects)'
  }
)

foreach ($s in $shortcuts) {
  $batLocal = Join-Path $Launch $s.Bat
  if (-not (Test-Path $batLocal)) { throw "Missing $batLocal" }

  $lnkPath = Join-Path $Desktop ($s.Name + '.lnk')
  if (Test-Path $lnkPath) { Remove-Item $lnkPath -Force }
  $Sc = $Wsh.CreateShortcut($lnkPath)
  $Sc.TargetPath = $batLocal
  $Sc.WorkingDirectory = $Launch
  $Sc.WindowStyle = 1
  $Sc.Description = $s.Desc
  if (Test-Path $iconDst) { $Sc.IconLocation = "$iconDst,0" }
  $Sc.Save()
  Write-Host ("Desktop: {0} -> {1}" -f $lnkPath, $batLocal)
}

Write-Host 'DONE - Desktop has CATS CTC and CATS ABS'
