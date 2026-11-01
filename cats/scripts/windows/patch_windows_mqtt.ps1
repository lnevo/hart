# Point Windows My JMRI Railroad MQTT at the Pi broker on ICS (192.168.137.2).
$ErrorActionPreference = 'Continue'
$Broker = '192.168.137.2'
$patched = 0

$roots = @(
  (Join-Path $env:APPDATA 'JMRI'),
  (Join-Path $env:USERPROFILE 'JMRI'),
  (Join-Path $env:USERPROFILE '.jmri')
) | Where-Object { $_ -and (Test-Path $_) }

foreach ($r in $roots) {
  Get-ChildItem $r -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like 'My_JMRI_Railroad*' } |
    ForEach-Object {
      $pf = Join-Path $_.FullName 'profile\profile.xml'
      if (-not (Test-Path $pf)) { return }
      $raw = Get-Content -Raw $pf
      if ($raw -notmatch 'MqttConnectionConfigXml') {
        Write-Host ("No MQTT in {0}" -f $pf)
        return
      }
      $orig = $raw

      # Replace address= on MQTT connection lines (attribute order varies)
      $raw = [regex]::Replace($raw, '(?s)(<connection\b[^>]*?\bclass="jmri\.jmrix\.mqtt\.configurexml\.MqttConnectionConfigXml"[^>]*?\baddress=")[^"]+(")',
        ('${1}' + $Broker + '${2}'))
      $raw = [regex]::Replace($raw, '(?s)(<connection\b[^>]*?\baddress=")[^"]+("[^>]*?\bclass="jmri\.jmrix\.mqtt\.configurexml\.MqttConnectionConfigXml")',
        ('${1}' + $Broker + '${2}'))

      $raw = [regex]::Replace($raw, 'reconnectMaxAttempts="\d+"', 'reconnectMaxAttempts="10"')
      $raw = [regex]::Replace($raw, 'reconnectMaxInterval="\d+"', 'reconnectMaxInterval="5"')

      if ($raw -ne $orig) {
        $bak = $pf + '.bak_pre_mqtt_fix'
        if (-not (Test-Path $bak)) { Copy-Item $pf $bak -Force }
        # Keep UTF-8 without BOM-ish issues; .NET Set-Content UTF8 writes BOM which JMRI accepts
        Set-Content -Path $pf -Value $raw -Encoding UTF8
        Write-Host ("Patched MQTT -> {0} : {1}" -f $Broker, $pf)
        $patched++
      } elseif ($raw -match [regex]::Escape('address="' + $Broker + '"')) {
        Write-Host ("MQTT already {0}: {1}" -f $Broker, $pf)
      } else {
        Write-Host ("MQTT present but address unchanged: {0}" -f $pf)
      }
    }
}

Write-Host ("patch_windows_mqtt done (changes={0})" -f $patched)
exit 0
