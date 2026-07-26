#!/usr/bin/env bash
# Run the device-side gate suite (app/src/androidTest) on a connected device.
#
# Why this exists instead of `./gradlew :app:connectedDebugAndroidTest`:
# that task uninstalls both APKs when it finishes, and uninstalling an app
# deletes /sdcard/Android/data/<pkg>/ with it — including the ~891 MiB of pushed
# weights. So the very first Gradle run wipes the models the *next* one needs,
# and the failure reads as "模型未就绪" no matter how many times you push.
#
# Order here is install → push → instrument, with no uninstall, which is also
# what the production path looks like: the app is installed, then Play's
# install-time asset pack materialises the models beside it.
#
# Usage:
#   scripts/run_device_gates.sh                              # everything
#   scripts/run_device_gates.sh -c ...gates.SslEncoderDeviceTest
#   scripts/run_device_gates.sh -s emulator-5554 --skip-build
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GRADLE_DIR="$ROOT/NativeLingoAndroid"
PKG="com.nativelingo.app"
TEST_PKG="$PKG.test"
RUNNER="androidx.test.runner.AndroidJUnitRunner"

CLASS=""
SKIP_BUILD=0
SERIAL=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        -c|--class) CLASS="$2"; shift 2 ;;
        --skip-build) SKIP_BUILD=1; shift ;;
        -s) SERIAL=(-s "$2"); shift 2 ;;
        -h|--help) sed -n '2,18p' "${BASH_SOURCE[0]}"; exit 0 ;;
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

if [[ $SKIP_BUILD -eq 0 ]]; then
    echo "== building APKs"
    ( cd "$GRADLE_DIR" && JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@17}" \
        ./gradlew --quiet :app:assembleDebug :app:assembleDebugAndroidTest )
fi

APP_APK="$GRADLE_DIR/app/build/outputs/apk/debug/app-debug.apk"
TEST_APK="$GRADLE_DIR/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"
for f in "$APP_APK" "$TEST_APK"; do [[ -f "$f" ]] || { echo "missing $f" >&2; exit 1; }; done

echo "== installing"
# -r keeps existing data; -g pre-grants runtime permissions so a future
# RECORD_AUDIO gate does not stop on a dialog.
adb install -r -g "$APP_APK" >/dev/null
adb install -r -g "$TEST_APK" >/dev/null

echo "== pushing models"
"$ROOT/scripts/push_device_models.sh" "${SERIAL[@]+${SERIAL[@]}}"

echo "== running gates"
adb logcat -c || true
ARGS=(-w -e package com.nativelingo.app.gates)
[[ -n "$CLASS" ]] && ARGS=(-w -e class "$CLASS")
set +e
adb shell am instrument "${ARGS[@]}" "$TEST_PKG/$RUNNER" 2>&1 | tee /tmp/nl-gates-instrument.txt
STATUS=$?
set -e

echo
echo "== NLGates measurements (logcat)"
adb logcat -d -s NLGates:I | sed 's/^/  /'

grep -qE '^OK \(|Tests run: .*Failures: 0' /tmp/nl-gates-instrument.txt || STATUS=1
exit $STATUS
