#!/usr/bin/env bash
# Build hart-mqtt-race-fix.jar: JMRI 5.16's MqttAdapter with the listener-race fix from
# JMRI/JMRI#16004, compiled against the Mac's stock JMRI 5.16 jars. The jar is committed; rebuild
# only when MqttAdapter.java changes. JMRI_HOME defaults to /Applications/JMRI.
#
# Usage: tools/jmri/mqtt_overlay/build.sh [--check]   (--check: rebuild in a temp folder and
#        fail if the classes differ from the committed jar)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
JMRI_HOME="${JMRI_HOME:-/Applications/JMRI}"
JAR="$HERE/hart-mqtt-race-fix.jar"
# The one JMRI build this class was made from; install_overlay.py refuses any other.
BASE="5.16.0 909e15189e"

props="$(unzip -p "$JMRI_HOME/jmri.jar" jmri/Version.properties)"
have="$(awk -F= '/^release.major=/{a=$2}/^release.minor=/{b=$2}/^release.build=/{c=$2}/^release.revision_id=/{r=$2}END{print a"."b"."c" "r}' <<<"$props")"
[[ "$have" == "$BASE" ]] || { echo "build.sh: $JMRI_HOME is JMRI $have, not $BASE" >&2; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/classes" "$tmp/stub/javax/annotation" "$tmp/stubclasses"
# JMRI's release does not ship javax.annotation.Nonnull (compile-time only, CLASS retention,
# so the JVM ignores it at run time). A stub lets javac compile; it is not put in the jar.
cat >"$tmp/stub/javax/annotation/Nonnull.java" <<'EOF'
package javax.annotation;
public @interface Nonnull {}
EOF
javac -nowarn --release 11 -d "$tmp/stubclasses" "$tmp/stub/javax/annotation/Nonnull.java"
javac -nowarn --release 11 -encoding UTF-8 \
  -cp "$tmp/stubclasses:$JMRI_HOME/jmri.jar:$JMRI_HOME/lib/*" \
  -d "$tmp/classes" "$HERE/MqttAdapter.java"
printf 'Manifest-Version: 1.0\nHART-JMRI-Base: %s\nHART-Fix: JMRI/JMRI#16004\n' "$BASE" >"$tmp/MANIFEST.MF"
(cd "$tmp/classes" && jar --create --file "$tmp/out.jar" --manifest "$tmp/MANIFEST.MF" jmri)

if [[ "${1:-}" == "--check" ]]; then
  mkdir -p "$tmp/a" "$tmp/b"
  (cd "$tmp/a" && unzip -q "$tmp/out.jar") && (cd "$tmp/b" && unzip -q "$JAR")
  diff -r "$tmp/a" "$tmp/b" >/dev/null || { echo "build.sh: $JAR does not match MqttAdapter.java; run build.sh" >&2; exit 1; }
  echo "build.sh: committed jar matches the source"
else
  cp -f "$tmp/out.jar" "$JAR"
  echo "wrote $JAR"
  unzip -l "$JAR"
fi
