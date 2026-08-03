#!/usr/bin/env bash
# Push the model set to a device for the Gate harness (app/src/androidTest).
#
# In production the models arrive as a Play install-time asset pack (NFR-4②),
# which Play unpacks into an app-private directory the app opens by path.
# Nothing in this repo can produce that, and the harness must not depend on Play
# to run, so the same *shape* is reproduced by hand: files in a directory the app
# owns, resolved by ModelRegistry through DirectoryModelSource.
#
# ### Why the two-step copy rather than one adb push
#
# The obvious destination — /sdcard/Android/data/<pkg>/files/models — does not
# work, and fails in the least helpful way possible. `adb push` succeeds, `adb
# shell ls` shows all seven files at full length, and the app still sees an empty
# directory: on API 30+ that path is a FUSE view, adb writes it through the shell
# namespace, and files landing there owned by uid `shell` are not readable by the
# app. The registry then correctly reports "未找到", which reads like a bug in the
# registry rather than a delivery problem.
#
# It was also the wrong destination for a second reason: `gradlew
# connectedAndroidTest` uninstalls both APKs when it finishes, and uninstalling
# takes /sdcard/Android/data/<pkg>/ with it — so the first run would delete the
# models the next one needs. (Hence scripts/run_device_gates.sh, which installs
# and instruments without uninstalling.)
#
# So: adb push to /data/local/tmp (mode 0771 shell:shell — the app UID *can*
# traverse it, and pushed files are 0666), then `run-as` the app to copy each
# file into its own filesDir and delete the staged copy immediately, so peak disk
# use is 935 MiB + one model rather than 1.9 GiB. Requires a debuggable build,
# which is exactly what the harness runs against.
#
# Byte lengths and SHA-256s are pinned in core-models ModelCatalog.kt; this
# script only moves files, and verifies the length of each copy — a truncated
# copy is caught by ModelRegistry.resolve() anyway, but catching it here says
# which step lost the bytes.
#
# Usage:
#   scripts/push_device_models.sh                 # install-time set (7 files, 935 MiB)
#   scripts/push_device_models.sh --with-tiny     # + tiny.en tier (1034 MiB)
#   scripts/push_device_models.sh --with-int8     # + rejected int8 SSL encoder (probe only)
#   scripts/push_device_models.sh -s emulator-5554
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG="com.nativelingo.app"
DEST="/data/data/$PKG/files/models"
STAGE="/data/local/tmp/nl-models"

ONNX="$ROOT/build/onnx"
SHERPA="${SHERPA_MODELS:-/tmp/sherpa-models}"

WITH_TINY=0
WITH_INT8=0
SERIAL=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --with-tiny) WITH_TINY=1; shift ;;
        --with-int8) WITH_INT8=1; shift ;;
        -s) SERIAL=(-s "$2"); shift 2 ;;
        -h|--help) sed -n '2,46p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

# The SDK is not at the default ~/Library/Android/sdk on this machine; take it
# from local.properties, which Gradle already reads.
if ! command -v adb >/dev/null 2>&1; then
    SDK="$(sed -n 's/^sdk\.dir=//p' "$ROOT/NativeLingoAndroid/local.properties" 2>/dev/null | head -1)"
    [[ -n "${SDK:-}" && -x "$SDK/platform-tools/adb" ]] || {
        echo "adb not on PATH and sdk.dir not usable in NativeLingoAndroid/local.properties" >&2
        exit 1
    }
    ADB="$SDK/platform-tools/adb"
else
    ADB="$(command -v adb)"
fi
adb() { "$ADB" "${SERIAL[@]+${SERIAL[@]}}" "$@"; }
as_app() { adb shell "run-as $PKG sh -c '$1'"; }

# Names on the device must match ModelSpec.fileName exactly — the registry looks
# files up by name, not by glob.
FILES=(
    "$ONNX/w2v2_base_69_fp16.onnx"                      # R-5  SSL encoder
    "$ONNX/mms_fa_int8_transformer.onnx"                # R-6  forced aligner
    "$ONNX/espeak_cv_ft_int8.onnx"                      # R-7  phoneme MDD (FR-11)
    "$SHERPA/silero_vad.onnx"                           # VAD
    "$SHERPA/sherpa-onnx-whisper-base.en/base.en-encoder.int8.onnx"
    "$SHERPA/sherpa-onnx-whisper-base.en/base.en-decoder.int8.onnx"
    "$SHERPA/sherpa-onnx-whisper-base.en/base.en-tokens.txt"
    # FR-13 (识物) — YOLOE-26S-PF detection export. Sourced from models/ (an
    # Ultralytics export, not one of our quantized re-exports — see
    # ModelCatalog.YOLOE_DETECT for the pin).
    "$ROOT/models/yoloe-26s-pf/yoloe-26s-pf.onnx"
)
if [[ $WITH_TINY -eq 1 ]]; then
    # The latency fallback tier (R-11): shipped-tier candidate rejected, kept as
    # a runtime downgrade for slow devices. Only needed when a gate measures it.
    FILES+=(
        "$SHERPA/sherpa-onnx-whisper-tiny.en/tiny.en-encoder.int8.onnx"
        "$SHERPA/sherpa-onnx-whisper-tiny.en/tiny.en-decoder.int8.onnx"
        "$SHERPA/sherpa-onnx-whisper-tiny.en/tiny.en-tokens.txt"
    )
fi
if [[ $WITH_INT8 -eq 1 ]]; then
    # The *rejected* candidate, deliberately not in ModelCatalog. It was the
    # shipped export through the desktop gates and lost the SSL encoder slot on
    # device: arm64 int8 kernels put speaker invariance at 0.18323 (bar 0.18) and
    # the worst golden cosine at 0.98297 (bar 0.985), where fp16 measures 0.16917
    # and 0.990-0.997. Pushed only so SslPrecisionProbeDeviceTest can keep
    # reporting both rows, which is what makes the +43.9 MiB auditable rather than
    # asserted. The probe skips when it is absent; the gates never look for it.
    FILES+=("$ONNX/w2v2_base_69_int8_transformer.onnx")
fi

missing=()
for f in "${FILES[@]}"; do [[ -f "$f" ]] || missing+=("$f"); done
if [[ ${#missing[@]} -gt 0 ]]; then
    printf 'missing source files:\n'
    printf '  %s\n' "${missing[@]}"
    echo
    echo "ONNX exports come from scripts/onnx_export_spike.py and scripts/onnx_export_mms.py."
    echo "Whisper/VAD come from the k2-fsa releases (see docs/reviews R-10); set"
    echo "SHERPA_MODELS=<dir> if they live somewhere other than $SHERPA."
    exit 1
fi

adb wait-for-device
ABI="$(adb shell getprop ro.product.cpu.abi | tr -d '\r')"
[[ "$ABI" == "arm64-v8a" ]] || {
    echo "device ABI is '$ABI', not arm64-v8a — the app is arm64-only (NFR-4①)." >&2
    exit 1
}
# run-as needs the app installed and debuggable; without it the copy step fails
# per-file with a message nobody reads.
adb shell "run-as $PKG true" >/dev/null 2>&1 || {
    echo "run-as $PKG failed — install the debug APK first (scripts/run_device_gates.sh does this)." >&2
    exit 1
}

adb shell "mkdir -p '$STAGE'"
as_app "mkdir -p '$DEST'"

total=0
for f in "${FILES[@]}"; do total=$((total + $(stat -f%z "$f"))); done
printf 'delivering %d files, %.1f MiB, to %s\n' "${#FILES[@]}" "$(echo "$total/1048576" | bc -l)" "$DEST"

for f in "${FILES[@]}"; do
    name="$(basename "$f")"
    want="$(stat -f%z "$f")"
    have="$(as_app "stat -c%s '$DEST/$name' 2>/dev/null || echo 0" | tr -d '\r')"
    if [[ "$have" == "$want" ]]; then
        printf '  = %-40s %10s B (already there)\n' "$name" "$want"
        continue
    fi
    printf '  → %-40s %10s B ... ' "$name" "$want"
    adb push "$f" "$STAGE/$name" >/dev/null
    # cp then rm the staged copy, so peak extra disk is one model, not the set.
    as_app "cp '$STAGE/$name' '$DEST/$name'" >/dev/null
    adb shell "rm -f '$STAGE/$name'"
    got="$(as_app "stat -c%s '$DEST/$name'" | tr -d '\r')"
    if [[ "$got" != "$want" ]]; then
        echo "TRUNCATED (app-private copy is $got B)"
        exit 1
    fi
    echo "ok"
done

adb shell "rmdir '$STAGE' 2>/dev/null || true"
echo
echo "done. Run the harness with:"
echo "  scripts/run_device_gates.sh --skip-build"
