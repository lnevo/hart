#!/bin/bash
# Reproduce the JMRI MQTT startup race on a bare profile and a private broker.
# Nothing here touches the layout broker, the real profile or JMRI_UserFiles.
#
# usage: run.sh N RETAIN(0|1) RUNS TAG
#   N       sensors and turnouts each in the generated tables.xml (2N beans)
#   RETAIN  1 publishes one retained message per bean before the runs
#   RUNS    JMRI starts for this setting
#   TAG     results folder name
# env: WORK (default: a temp dir), JFR=1 records every thrown exception,
#      JMRI_DIR (default /Applications/JMRI), PORT (default 18830, never 1883),
#      PY (a python with paho-mqtt; default the repo .venv)
# See docs/jmri/MQTT_STARTUP_RACE.md.
set -u
N=$1; RET=$2; RUNS=$3; TAG=$4
HERE=$(cd "$(dirname "$0")" && pwd)
WORK=${WORK:-${TMPDIR:-/tmp}/mqtt-race-repro}
JMRI_DIR=${JMRI_DIR:-/Applications/JMRI}
PORT=${PORT:-18830}
PY=${PY:-$HERE/../../../.venv/bin/python}
[ "$PORT" = 1883 ] && { echo "PORT 1883 is the layout broker port; pick another" >&2; exit 2; }
PROFILE=Repro.1a2b3c4d
mkdir -p "$WORK/settings/Repro.jmri/profile" "$WORK/userfiles" "$WORK/broker" "$WORK/results/$TAG"

cat > "$WORK/settings/profiles.xml" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<profileConfig>
  <profiles><profile id="$PROFILE" path="settings:Repro.jmri/" /></profiles>
  <searchPaths><path path="settings:" default="true" /></searchPaths>
</profileConfig>
EOF
cat > "$WORK/settings/Repro.jmri/profile/profile.properties" <<EOF
profile.name=Repro
profile.id=$PROFILE
jmri-implementation.user-files=$WORK/userfiles/
jmri-web-server.port=12180
jmri-jmris-simpleserver.port=2148
jmri-server-json.port=2156
EOF
# One MQTT connection with stock options, one startup action: load tables.xml.
cat > "$WORK/settings/Repro.jmri/profile/profile.xml" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<auxiliary-configuration xmlns="http://www.netbeans.org/ns/auxiliary-configuration/1">
    <connections xmlns="http://jmri.org/xml/schema/auxiliary-configuration/connections-2-9-6.xsd">
        <connection xmlns="" address="127.0.0.1" class="jmri.jmrix.mqtt.configurexml.MqttConnectionConfigXml" disabled="no" manufacturer="MQTT" mdnsConfigure="false" port="$PORT" systemPrefix="M" userName="MQTT">
            <options/>
        </connection>
    </connections>
    <startup xmlns="http://jmri.org/xml/schema/auxiliary-configuration/startup-4-3-5.xsd">
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformFileModelXml" enabled="yes" name="preference:tables.xml" type="XmlFile"/>
    </startup>
</auxiliary-configuration>
EOF
python3 "$HERE/gen_tables.py" "$N" > "$WORK/userfiles/tables.xml"

# One broker per WORK and PORT; its config path carries the port.
CONF="$WORK/broker/mosquitto-$PORT.conf"
if ! pgrep -f "mosquitto -c $CONF" >/dev/null; then
  printf 'listener %s 127.0.0.1\nallow_anonymous true\npersistence false\n' "$PORT" > "$CONF"
  mosquitto -c "$CONF" -d
  sleep 1
fi
# Retained messages are set from Python, never by a shell publish (AGENTS.md).
"$PY" "$HERE/retain.py" "$PORT" "$([ "$RET" = 1 ] && echo "$N" || echo 0)" || { echo "broker on $PORT not answering" >&2; exit 1; }

# Exception recording: the stock default.jfc with JavaExceptionThrow on.
if [ -n "${JFR:-}" ] && [ ! -f "$WORK/exc.jfc" ]; then
  JH=$(/usr/libexec/java_home 2>/dev/null || dirname "$(dirname "$(readlink -f "$(command -v java)")")")
  python3 - "$JH/lib/jfr/default.jfc" "$WORK/exc.jfc" <<'EOF' || exit 1
import re, sys
t = open(sys.argv[1]).read()
t, n = re.subn(r'(<event name="jdk.JavaExceptionThrow">\s*<setting name="enabled"[^>]*>)false', r'\1true', t)
if n != 1:
    sys.exit(f"could not turn on jdk.JavaExceptionThrow in {sys.argv[1]}")
open(sys.argv[2], 'w').write(t)
EOF
fi

cd "$JMRI_DIR" || exit 1
for r in $(seq 1 "$RUNS"); do
  JFROPT=""
  [ -n "${JFR:-}" ] && JFROPT="-J-XX:StartFlightRecording=filename=$WORK/results/$TAG/rec$r.jfr,settings=$WORK/exc.jfc,dumponexit=true"
  rm -f "$WORK/settings/log/session.log"
  ./JmriFaceless.command $JFROPT --settingsdir="$WORK/settings" --profile=$PROFILE > "$WORK/results/$TAG/out$r.txt" 2>&1 &
  for _ in $(seq 1 60); do grep -q "Loading file" "$WORK/settings/log/session.log" 2>/dev/null && break; sleep 1; done
  sleep 14
  pkill -f "jmri.prefsdir=$WORK/settings"
  # A clean exit writes the JFR file, so give it time before a hard kill.
  for _ in $(seq 1 30); do pgrep -f "jmri.prefsdir=$WORK/settings" >/dev/null || break; sleep 1; done
  pkill -9 -f "jmri.prefsdir=$WORK/settings" 2>/dev/null
  [ -n "${JFR:-}" ] && [ ! -s "$WORK/results/$TAG/rec$r.jfr" ] && echo "$TAG run $r: WARNING no JFR recording"
  L="$WORK/results/$TAG/session$r.log"
  cp "$WORK/settings/log/session.log" "$L" 2>/dev/null || : > "$L"
  if ! grep -q "Loading file" "$L" || ! grep -q "MQTT starting connect" "$L"; then
    echo "$TAG run $r: FAILED, JMRI did not connect and load tables.xml; not a result"
    continue
  fi
  echo "$TAG run $r: lost=$(grep -c 'Lost MQTT broker connection' "$L") CME=$(grep -c ConcurrentModificationException "$L") cantsub=$(grep -c "Can't subscribe" "$L") reconnect=$(grep -c 'Succeeded to reconnect' "$L")"
done
echo "results in $WORK/results/$TAG; stop the broker with: pkill -f 'mosquitto -c $CONF'"
