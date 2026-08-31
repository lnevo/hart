# Run LCOS serial bridge from consolidation workspace (foreground).
param(
  [string]$Com = $env:HART_LCOS_COM,
  [string]$Broker = $env:HART_MQTT_BROKER
)
if (-not $env:HART_MQTT_PORT) { $Port = 1883 } else { $Port = [int]$env:HART_MQTT_PORT }

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Lcos = Join-Path $Root 'external\lcos-bridge'

if (-not $Com) { $Com = 'COM3' }
if (-not $Broker) { $Broker = 'minipc-e5h6x.local' }

Set-Location $Lcos
if (-not (Test-Path '.venv\Scripts\python.exe')) {
  python -m venv .venv
  .\.venv\Scripts\pip install -r requirements.txt
}

Write-Host "LCOS bridge: $Com -> mqtt://${Broker}:${Port} (foreground)"
.\.venv\Scripts\python -u serial_to_mqtt.py --com $Com --broker $Broker --mqtt-port $Port --verbose
