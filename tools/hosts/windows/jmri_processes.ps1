# The Java processes that are JMRI apps or CATS, found by command line (not every java.exe is one).
# Dot-sourced by kill_cats.ps1 and apply_hart_package_local.ps1: . (Join-Path $PSScriptRoot 'jmri_processes.ps1')
$JmriProcessPattern = 'cats\.apps\.Crandic|apps\.PanelPro|jmri\.PanelPro|apps\.gui3\.dp3\.DecoderPro3|apps\.DecoderPro|apps\.DispatcherPro|[\\/]cats\.jar|LaunchJMRI|designer\.gui'

function Get-JmriProcesses {
  param([string]$Names = '^(java|javaw|javaws)\.exe$')
  Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match $Names -and $_.CommandLine -and $_.CommandLine -match $JmriProcessPattern }
}

# "PID 123 javaw.exe, PID 456 java.exe" for a skip message.
function Format-JmriProcesses {
  param($Processes)
  (@($Processes) | ForEach-Object { 'PID {0} {1}' -f $_.ProcessId, $_.Name }) -join ', '
}
