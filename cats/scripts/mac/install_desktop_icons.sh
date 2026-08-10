#!/usr/bin/env bash
# Install /Applications icons: CATS (Master CTC) and CATS ABS (open house).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
ICNS="$ROOT/cats/resources/CATS.icns"
APPS="/Applications"
DESKTOP="${HOME}/Desktop"

if [[ ! -f "$ICNS" ]]; then
  echo "Missing icon: $ICNS" >&2
  exit 1
fi

make_app() {
  local name="$1"
  local panel="$2"
  local app="${APPS}/${name}.app"
  rm -rf "$app"
  mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
  cp "$ICNS" "$app/Contents/Resources/AppIcon.icns"
  cat > "$app/Contents/MacOS/CatsLaunch" <<EOF
#!/usr/bin/env bash
exec "$ROOT/cats/scripts/launch_cats.sh" "$ROOT/cats/panels/sheets/${panel}"
EOF
  chmod +x "$app/Contents/MacOS/CatsLaunch"
  local id="${name// /}"
  cat > "$app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>CatsLaunch</string>
  <key>CFBundleIdentifier</key>
  <string>com.hart.cats.${id}</string>
  <key>CFBundleName</key>
  <string>${name}</string>
  <key>CFBundleDisplayName</key>
  <string>${name}</string>
  <key>CFBundleIconFile</key>
  <string>AppIcon</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0</string>
  <key>CFBundleVersion</key>
  <string>20260810</string>
  <key>LSMinimumSystemVersion</key>
  <string>12.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST
  xattr -cr "$app" 2>/dev/null || true
  touch "$app"
  echo "Applications: $app -> $panel"
}

make_app "CATS" "HART_Master.xml"
make_app "CATS ABS" "HART_Master_ABS.xml"

# Remove prior Desktop copies / HART_Master .command launchers if present
rm -rf "${DESKTOP}/CATS.app" "${DESKTOP}/CATS ABS.app"
rm -f "${DESKTOP}/HART_Master.command" "${DESKTOP}/HART_Master_ABS.command"
/usr/bin/osascript -e 'tell application "Finder" to update desktop' 2>/dev/null || true
echo "DONE"
