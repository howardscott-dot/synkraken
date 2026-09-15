#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUTPUT="${1:?Pass an output directory}"
mkdir -p "$OUTPUT"
BUILD="$(mktemp -d "${TMPDIR:-/tmp}/synkraken-mac.XXXXXX")"
APP="$BUILD/stage/SynKraken.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
"$ROOT/.venv/bin/python" -m PyInstaller --noconfirm --clean --name synkraken-engine --onedir --distpath "$BUILD/dist" --workpath "$BUILD/build" --specpath "$BUILD" --paths "$ROOT" --collect-all keyring --collect-all playwright --add-data "$ROOT/synkraken/static:synkraken/static" "$ROOT/synkraken/desktop.py"
cp -R "$BUILD/dist/synkraken-engine" "$APP/Contents/Resources/engine"
PLAYWRIGHT_BROWSERS_PATH="$APP/Contents/Resources/browsers" "$ROOT/.venv/bin/python" -m playwright install chromium --only-shell
swiftc "$ROOT/packaging/macos/Main.swift" -o "$APP/Contents/MacOS/SynKraken" -framework AppKit -framework WebKit
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>SynKraken</string>
<key>CFBundleIdentifier</key><string>org.synkraken.desktop</string>
<key>CFBundleName</key><string>SynKraken</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>0.1.0</string>
<key>LSMinimumSystemVersion</key><string>13.0</string>
<key>NSHighResolutionCapable</key><true/>
<key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict></plist>
PLIST
swift "$ROOT/packaging/macos/Icon.swift" "$BUILD/icon.png"
mkdir -p "$BUILD/AppIcon.iconset"
for size in 16 32 128 256 512; do
  sips -z "$size" "$size" "$BUILD/icon.png" --out "$BUILD/AppIcon.iconset/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  sips -z "$double" "$double" "$BUILD/icon.png" --out "$BUILD/AppIcon.iconset/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$BUILD/AppIcon.iconset" -o "$APP/Contents/Resources/AppIcon.icns"
/usr/libexec/PlistBuddy -c 'Add :CFBundleIconFile string AppIcon' "$APP/Contents/Info.plist"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"
ditto "$APP" "$OUTPUT/SynKraken.app"
ln -s /Applications "$BUILD/stage/Applications"
printf '%s\n' 'Drag SynKraken into Applications, then open it. Choose your provider and model in chat. This is an ad-hoc signed development build, not a notarized release. Closing the app stops its engine; scheduled background work is not included in this build.' > "$BUILD/stage/Read me.txt"
hdiutil create -volname SynKraken -srcfolder "$BUILD/stage" -ov -format UDZO "$OUTPUT/SynKraken-development.dmg"
printf 'Disk image saved in %s\n' "$OUTPUT"
