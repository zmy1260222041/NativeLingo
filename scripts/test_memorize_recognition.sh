#!/usr/bin/env bash
# Test the Memorizing (识物) object-recognition feature end-to-end on a device.
#
# This is the frozen manual/automated test flow for FR-13. It is deliberately
# one command so the flow is repeatable and the pitfalls are documented once:
#
#   1. build the debug APKs
#   2. install app + test APK (with `-r -g`; NOT a full uninstall/reinstall —
#      see run_device_gates.sh for why that wipes pushed models)
#   3. push YOLOE_DETECT alone (the only model recognition touches; the full
#      push_device_models.sh set belongs to the Speaking-track gates)
#   4. run the recognition gates/smokes on-device:
#        - MemorizePipelineDeviceTest  — cat photo → canonicalize → YOLOE → 'cat'
#        - YoloDetectorDeviceTest      — model loads; 640px + 1920px multiscale
#          run inside the 15s UX deadline
#        - ReferenceClipSourceDeviceTest — bundled Piper reference clips load and
#          decode (the 跟读 reference path the recognition screen depends on)
#   5. (--ui) stage a REAL photo into the emulator's media library for manual UI
#      testing — and CLEAN UP the /sdcard screenshots that otherwise shadow it
#
# ### The media-library pitfall this script encodes (why --ui cleans /sdcard)
#
# Every `adb shell screencap` run during manual testing leaves a PNG in
# /sdcard. The Android Photo Picker indexes /sdcard, so the "first photo" the
# picker offers is usually the LAST SCREENSHOT — i.e. a picture of the app's own
# UI. Choosing it feeds a screenshot of the recognition screen into the
# recognizer, which detects UI chrome ("plaque", "screen") instead of a real
# object. Symptoms: the app appears to "recognise the app itself", and the
# result never includes the intended object. Fix encoded here: before staging
# the test photo, delete every stray *.png on /sdcard and anything in
# /sdcard/Pictures except the staged fixtures, then rescan the media store.
#
# Usage:
#   scripts/test_memorize_recognition.sh                # build + install + push + gates
#   scripts/test_memorize_recognition.sh --ui           # also stage a real photo for manual UI check
#   scripts/test_memorize_recognition.sh --skip-build   # reuse existing APKs
#   scripts/test_memorize_recognition.sh -s emulator-5554
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GRADLE_DIR="$ROOT/NativeLingoAndroid"
PKG="com.nativelingo.app"
TEST_PKG="$PKG.test"
RUNNER="androidx.test.runner.AndroidJUnitRunner"

UI=0
SKIP_BUILD=0
SERIAL=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --ui) UI=1; shift ;;
        --skip-build) SKIP_BUILD=1; shift ;;
        -s) SERIAL=(-s "$2"); shift 2 ;;
        -h|--help) sed -n '2,48p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

if ! command -v adb >/dev/null 2>&1; then
    SDK="$(sed -n 's/^sdk\.dir=//p' "$GRADLE_DIR/local.properties" 2>/dev/null | head -1)"
    ADB="$SDK/platform-tools/adb"
else
    ADB="$(command -v adb)"
fi
[[ -x "$ADB" ]] || { echo "adb not found" >&2; exit 1; }
adb() { "$ADB" "${SERIAL[@]+${SERIAL[@]}}" "$@"; }

# ── 1. build ──────────────────────────────────────────────────────────────────
if [[ $SKIP_BUILD -eq 0 ]]; then
    echo "== building APKs"
    ( cd "$GRADLE_DIR" && JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@17}" \
        ./gradlew --quiet :app:assembleDebug :app:assembleDebugAndroidTest )
fi

APP_APK="$GRADLE_DIR/app/build/outputs/apk/debug/app-debug.apk"
TEST_APK="$GRADLE_DIR/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"
for f in "$APP_APK" "$TEST_APK"; do [[ -f "$f" ]] || { echo "missing $f" >&2; exit 1; }; done

# ── 2. install ────────────────────────────────────────────────────────────────
echo "== installing"
adb install -r -g "$APP_APK" >/dev/null
adb install -r -g "$TEST_APK" >/dev/null

# ── 3. push models ────────────────────────────────────────────────────────────
# The recognition flow needs exactly one model: YOLOE_DETECT. The full
# push_device_models.sh set (Whisper/VAD/MMS/espeak) is required only by the
# Speaking-track gates, and pulling 600+ MiB of it here would make the frozen
# flow depend on models this feature never touches. Push YOLOE alone, using the
# same run-as delivery path as push_device_models.sh (see its header for why
# /sdcard/Android/data is wrong).
echo "== pushing YOLOE_DETECT model"
STAGE=/data/local/tmp/nl-yoloe
YOLOE="$ROOT/models/yoloe-26s-pf/yoloe-26s-pf.onnx"
[[ -f "$YOLOE" ]] || { echo "missing $YOLOE (see ModelCatalog.YOLOE_DETECT)" >&2; exit 1; }
adb wait-for-device
adb shell "run-as $PKG true" >/dev/null 2>&1 || {
    echo "run-as $PKG failed — install the debug APK first." >&2; exit 1
}
adb shell "mkdir -p $STAGE" >/dev/null
adb shell "run-as $PKG mkdir -p /data/data/$PKG/files/models" >/dev/null
want="$(stat -f%z "$YOLOE")"
have="$(adb shell "run-as $PKG stat -c%s /data/data/$PKG/files/models/yoloe-26s-pf.onnx 2>/dev/null || echo 0" | tr -d '\r')"
if [[ "$have" != "$want" ]]; then
    adb push "$YOLOE" "$STAGE/yoloe-26s-pf.onnx" >/dev/null
    adb shell "run-as $PKG cp $STAGE/yoloe-26s-pf.onnx /data/data/$PKG/files/models/yoloe-26s-pf.onnx" >/dev/null
    adb shell "rm -f $STAGE/yoloe-26s-pf.onnx" >/dev/null
    got="$(adb shell "run-as $PKG stat -c%s /data/data/$PKG/files/models/yoloe-26s-pf.onnx" | tr -d '\r')"
    [[ "$got" == "$want" ]] || { echo "YOLOE push truncated ($got/$want)" >&2; exit 1; }
fi
echo "  yoloe-26s-pf.onnx ($want B) ready"

# ── 4. run recognition gates/smokes ───────────────────────────────────────────
# One class per instrument invocation, NOT a comma-joined class list: YOLOE
# loads ~45 MiB into the process per test class, and three classes sharing the
# emulator's CPU made the multiscale path blow the time budget. Serial runs give
# each class the whole CPU and the timing is stable.
echo "== running recognition tests (serial)"
adb logcat -c || true
STATUS=0
for cls in \
    com.nativelingo.app.gates.YoloDetectorDeviceTest \
    com.nativelingo.app.smoke.MemorizePipelineDeviceTest \
    com.nativelingo.app.gates.ReferenceClipSourceDeviceTest; do
    echo "  → $cls"
    set +e
    adb shell am instrument -w -e class "$cls" "$TEST_PKG/$RUNNER" 2>&1 | tee /tmp/nl-recognition-instrument.txt
    s=$?
    set -e
    grep -qE '^OK \(|Tests run: .*Failures: 0' /tmp/nl-recognition-instrument.txt || s=1
    [[ $s -eq 0 ]] || { echo "$cls FAILED (see above)" >&2; STATUS=1; }
done
[[ $STATUS -eq 0 ]] || { echo "recognition tests FAILED" >&2; exit 1; }

# ── 5. (--ui) stage a real photo for manual UI checks ─────────────────────────
if [[ $UI -eq 1 ]]; then
    echo "== cleaning media library (screenshot pollution) and staging test photo"
    # Delete every stray screenshot; keep only our staged fixtures. Without this
    # the Photo Picker's "first photo" is the last screencap — a picture of the
    # app's own UI — and recognition then detects UI chrome, not the object.
    adb shell "rm -f /sdcard/*.png" >/dev/null 2>&1 || true
    adb shell "find /sdcard/Pictures /sdcard/Download -name '*.png' -delete 2>/dev/null" || true
    adb shell "find /sdcard/Pictures -name '*.jpg' ! -name 'test_cat.jpg' -delete 2>/dev/null" || true
    # Stage a REAL object photo (same fixture the gates use) into the media
    # library so the Photo Picker offers it. It is also the only jpg left.
    adb push "$GRADLE_DIR/app/src/androidTest/assets/test_cat.jpg" \
        /sdcard/Pictures/test_cat.jpg >/dev/null
    adb shell "am broadcast -a android.intent.action.MEDIA_MOUNTED -d file:///sdcard/Pictures" >/dev/null 2>&1 || true

    echo "== launching app on the Memorizing module (manual UI check)"
    adb shell "am force-stop $PKG"
    adb shell "am start -n $PKG/.MainActivity" >/dev/null
    sleep 2
    # Tap the 识物 module in the top-bar switcher (found via uiautomator bounds).
    adb shell "uiautomator dump /sdcard/.nl-ui.xml" >/dev/null 2>&1 || true
    B="$(adb shell "cat /sdcard/.nl-ui.xml" 2>/dev/null | tr '>' '\n' | grep '识物"' | grep -oE 'bounds="\[[0-9]+,[0-9]+\]\[[0-9]+,[0-9]+\]"' | head -1 | grep -oE '[0-9]+' | tr '\n' ' ')"
    adb shell "rm -f /sdcard/.nl-ui.xml" >/dev/null 2>&1 || true  # never leave dump files in /sdcard
    if [[ -n "$B" && $(echo "$B" | wc -w) -eq 4 ]]; then
        X=$(( ($(echo "$B" | cut -d' ' -f1) + $(echo "$B" | cut -d' ' -f3)) / 2 ))
        Y=$(( ($(echo "$B" | cut -d' ' -f2) + $(echo "$B" | cut -d' ' -f4)) / 2 ))
        adb shell "input tap $X $Y"
        echo "launched on 识物 — pick 选择照片 → test_cat.jpg and verify the flow."
    else
        echo "识物 switcher not found on screen; the app is open on the default module."
    fi
    echo "IMPORTANT: after manual checks, run 'adb shell rm -f /sdcard/*.png'"
    echo "before the next --ui run — screenshots repollute the picker."
fi

echo
echo "OK — recognition flow verified."
