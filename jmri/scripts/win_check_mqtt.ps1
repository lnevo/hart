Write-Host '=== profile script entries ==='
Get-ChildItem "$env:USERPROFILE\.jmri" -Recurse -Filter profile.xml -ErrorAction SilentlyContinue | ForEach-Object {
  $hits = Select-String -Path $_.FullName -Pattern 'mqtt_signalhead|apply_maintain|sync_yard'
  if ($hits) {
    Write-Host $_.FullName
    $hits | ForEach-Object { Write-Host ('  ' + $_.Line.Trim()) }
  }
}
Write-Host '=== mosquitto_sub ==='
foreach ($p in @(
  'C:\Program Files\mosquitto\mosquitto_sub.exe',
  'C:\Program Files (x86)\mosquitto\mosquitto_sub.exe'
)) {
  if (Test-Path $p) { Write-Host "found $p" } else { Write-Host "missing $p" }
}
Write-Host '=== companion scripts ==='
@(
  'C:\Users\lnevo\hart\jmri\layouts\hart\scripts\apply_maintain_mqtt.py',
  'C:\Users\lnevo\hart\jmri\layouts\hart\scripts\sync_turnout_buttons.py',
  'C:\Users\lnevo\hart\jmri\scripts\mqtt_signalhead_publisher.py'
) | ForEach-Object {
  if (Test-Path $_) {
    $i = Get-Item $_
    Write-Host ("OK {0} bytes={1} mtime={2}" -f $_, $i.Length, $i.LastWriteTime)
  } else {
    Write-Host "MISSING $_"
  }
}
