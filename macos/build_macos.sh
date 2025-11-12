#!/usr/bin/env bash
set -euo pipefail

# --- Directory setup --------------------------------------------------------
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$ROOT_DIR/macos/build"

CLEAN=${1:-true}
if [[ "$CLEAN" == "true" ]]; then
  echo "🧹 Cleaning old builds..."
  rm -rf "$BUILD_DIR/MDtoText2QTI.app" "$BUILD_DIR/Text2QTItoMD.app"
fi

mkdir -p "$BUILD_DIR"

# --- Helper: build a droplet icon from PNG ----------------------------------
build_icon() {
  local ICON_SRC="$1"          # e.g., macos/MDtoText2QTI/resources/icon.png
  local ICON_DST="$2"          # e.g., macos/build/MDtoText2QTI.app/Contents/Resources/dropleticon.icns

  # Make a temp iconset directory (must end with .iconset for iconutil)
  local TMPROOT
  TMPROOT=$(mktemp -d)
  local ICONSET="$TMPROOT/dropleticon.iconset"
  mkdir -p "$ICONSET"

  echo "Building icon from $ICON_SRC → $ICON_DST"

  # Generate the required sizes into the .iconset folder
  sips -z 16 16     "$ICON_SRC" --out "$ICONSET/icon_16x16.png" >/dev/null
  sips -z 32 32     "$ICON_SRC" --out "$ICONSET/icon_16x16@2x.png" >/dev/null
  sips -z 32 32     "$ICON_SRC" --out "$ICONSET/icon_32x32.png" >/dev/null
  sips -z 64 64     "$ICON_SRC" --out "$ICONSET/icon_32x32@2x.png" >/dev/null
  sips -z 128 128   "$ICON_SRC" --out "$ICONSET/icon_128x128.png" >/dev/null
  sips -z 256 256   "$ICON_SRC" --out "$ICONSET/icon_128x128@2x.png" >/dev/null
  sips -z 256 256   "$ICON_SRC" --out "$ICONSET/icon_256x256.png" >/dev/null
  sips -z 512 512   "$ICON_SRC" --out "$ICONSET/icon_256x256@2x.png" >/dev/null
  sips -z 512 512   "$ICON_SRC" --out "$ICONSET/icon_512x512.png" >/dev/null

  # @2x for 512x512 must be 1024x1024. If your source is 1024x1024, just copy it.
  # Otherwise, upscale explicitly with sips.
  cp "$ICON_SRC" "$ICONSET/icon_512x512@2x.png"
  # If your source isn't 1024x1024, use:
  # sips -z 1024 1024 "$ICON_SRC" --out "$ICONSET/icon_512x512@2x.png" >/dev/null

  # Package the .icns
  iconutil -c icns "$ICONSET" -o "$ICON_DST"

  # Cleanup
  rm -rf "$TMPROOT"
}

# --- Helpers for customizing Plist file -------------------------------------------

# Quietly set a plist key to a value, adding it if missing.
plist_set() {
  local PLIST="$1"   # path to Info.plist
  local KEY="$2"     # e.g., CFBundleIdentifier
  local TYPE="$3"    # string | integer | bool | array | dict
  local VALUE="$4"   # value (omit for array/dict adds)

  if /usr/libexec/PlistBuddy -c "Print :$KEY" "$PLIST" >/dev/null 2>&1; then
    /usr/libexec/PlistBuddy -c "Set :$KEY $VALUE" "$PLIST"
  else
    /usr/libexec/PlistBuddy -c "Add :$KEY $TYPE $VALUE" "$PLIST"
  fi
}

# Convenience setter for icon keys (and optional CFBundleIcons structure)
patch_plist() {
  local APP="$1"            # e.g., "$BUILD_DIR/MDtoText2QTI.app"
  local BID="$2"            # e.g., "com.tpavlic.md2qti.MDtoText2QTI"
  local NAME="$3"           # e.g., "MDtoText2QTI"
  local SVERSION="$4"       # e.g., "0.1.0"
  local BVERSION="$5"       # e.g., "101"

  local ICON_BASENAME="dropleticon"       # e.g., "md2t2qti" (no .icns)

  local PLIST="$APP/Contents/Info.plist"

  plist_set "$PLIST" CFBundleIdentifier        string "$BID"
  plist_set "$PLIST" CFBundleName              string "$NAME"
  plist_set "$PLIST" CFBundleDisplayName       string "$NAME"
  plist_set "$PLIST" CFBundleShortVersionString string "$SVERSION"
  plist_set "$PLIST" CFBundleVersion           string "$BVERSION"

  # Icon pointers
  plist_set "$PLIST" CFBundleIconFile          string "$ICON_BASENAME"
  plist_set "$PLIST" CFBundleIconName          string "$ICON_BASENAME"

  # Bump build number to force Finder to refresh
  cur=$(/usr/libexec/PlistBuddy -c "Print :CFBundleVersion" "$PLIST" 2>/dev/null || echo "0")
  next=$(( ${cur//[^0-9]/} + 1 ))
  /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $next" "$PLIST" \
    || /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $next" "$PLIST"

  # Touch the bundle so LaunchServices notices
  touch "$APP"
}

# --- Build each droplet -----------------------------------------------------

echo "Compiling AppleScript droplets..."

# MDtoText2QTI
osacompile -o "$BUILD_DIR/MDtoText2QTI.app" \
  "$ROOT_DIR/macos/MDtoText2QTI/main.applescript"

# Text2QTItoMD
osacompile -o "$BUILD_DIR/Text2QTItoMD.app" \
  "$ROOT_DIR/macos/Text2QTItoMD/main.applescript"

echo "Injecting Python scripts and resources..."

# Copy Python scripts
cp "$ROOT_DIR/md2t2qti.py" "$BUILD_DIR/MDtoText2QTI.app/Contents/Resources/Scripts/md2t2qti.py"
cp "$ROOT_DIR/t2qti2md.py" "$BUILD_DIR/Text2QTItoMD.app/Contents/Resources/Scripts/t2qti2md.py"

# Build icons
# - icon.png should be square [1024x1024, but 512x512 possible if update build_icon above]
# - icon.png should have a transparent background
build_icon "$ROOT_DIR/macos/MDtoText2QTI/resources/icon.png" \
            "$BUILD_DIR/MDtoText2QTI.app/Contents/Resources/dropleticon.icns"

build_icon "$ROOT_DIR/macos/Text2QTItoMD/resources/icon.png" \
            "$BUILD_DIR/Text2QTItoMD.app/Contents/Resources/dropleticon.icns"

# Update Plist files
patch_plist "$BUILD_DIR/MDtoText2QTI.app" "com.tedpavlic.md2qti.MDtoText2QTI" "MDtoText2QTI" "0.1.0" "100"
patch_plist "$BUILD_DIR/Text2QTItoMD.app" "com.tedpavlic.md2qti.Text2QTItoMD" "Text2QTItoMD" "0.1.0" "100"

# Delete the stock droplet icons provided by osascript
rm "$BUILD_DIR/MDtoText2QTI.app/Contents/Resources/droplet.icns"
rm "$BUILD_DIR/Text2QTItoMD.app/Contents/Resources/droplet.icns"

# --- Package apps into ZIPs -------------------------------------------------
echo "Packaging droplet apps..."
( cd "$BUILD_DIR" && zip -r9 MDtoText2QTI.app.zip MDtoText2QTI.app >/dev/null )
( cd "$BUILD_DIR" && zip -r9 Text2QTItoMD.app.zip Text2QTItoMD.app >/dev/null )

echo "✅ Build complete!"
echo "Artifacts are in: $BUILD_DIR"