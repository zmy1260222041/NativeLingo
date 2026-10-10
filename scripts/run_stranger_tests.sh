#!/usr/bin/env bash
# Offline regression gate for the Stranger 2D branch (T1-07).
#
# Runs every offline Godot suite under each UI locale with its own fresh
# user:// directory, then the speech-service Python suite and the launcher
# test once, prints a summary table and exits non-zero when anything fails.
#
# Never runs Live*/test_live_*/CloudActivationLiveTest (network, paid APIs) and
# never passes capture flags, so committed docs/reviews screenshots stay intact.
#
# Usage:
#   scripts/run_stranger_tests.sh                  # all suites, en + zh_CN, python
#   scripts/run_stranger_tests.sh NovelTest test_game_state   # named suites only
#   scripts/run_stranger_tests.sh python           # only the Python lane
#   GODOT_BIN=/path/to/Godot scripts/run_stranger_tests.sh
#
# Env:
#   GODOT_BIN      Godot 4.6.3 binary (default: macOS app, then `godot` on PATH)
#   PYTHON         Python for the speech suite (default: .venv/bin/python, then python3)
#   LOCALES        UI locales to run (default: "en zh_CN")
#   SKIP_PYTHON=1  skip the Python lane of a full run
#   SUITE_TIMEOUT  seconds per Godot suite (default: 300)
#   OUT_DIR        log directory (default: build/stranger-tests/<timestamp>)

set -o pipefail  # bash 3.2 (macOS) compatible: no -u with empty arrays

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GAME_DIR="$ROOT/game"
GODOT_BIN="${GODOT_BIN:-}"
if [[ -z "$GODOT_BIN" ]]; then
  if [[ -x /Applications/Godot-4.6.app/Contents/MacOS/Godot ]]; then
    GODOT_BIN=/Applications/Godot-4.6.app/Contents/MacOS/Godot
  else
    GODOT_BIN="$(command -v godot || true)"
  fi
fi
if [[ -z "$GODOT_BIN" || ! -x "$GODOT_BIN" ]]; then
  echo "run_stranger_tests: Godot not found; set GODOT_BIN=/path/to/Godot" >&2
  exit 2
fi
PYTHON="${PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then PYTHON="$ROOT/.venv/bin/python"; else PYTHON="$(command -v python3 || true)"; fi
fi
LOCALES="${LOCALES:-en zh_CN}"
SUITE_TIMEOUT="${SUITE_TIMEOUT:-300}"
OUT_DIR="${OUT_DIR:-$ROOT/build/stranger-tests/$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$OUT_DIR"

# Scene suites (.tscn) and SceneTree script suites (--script). 2D first; the
# last three scenes are 3D-era smoke suites that still gate the old builds.
SCENE_SUITES=(
  NovelTest NovelEverydayTest NovelInteractionTest NovelKeyboardTest NovelReplyAudioTest
  NovelSurvivalTest NovelVoiceStatusTest TownBelongingTest SocialDialogueTest
  CampusTest CampusInteractionTest CampusArtTest
  NpcVoiceTest VocabularyTest WordAcquisitionTest WordPracticeTest GuidedWordPracticeTest
  VoiceTargetCancelTest CloudVoiceTest
  HudTest WebBetaNoVoiceTest DesktopBetaNoVoiceTest
)
SCRIPT_SUITES=(
  test_game_state test_save_migration test_voice_gated_rewards test_item_usage
  test_npc_dialogue_assets test_onboarding
)

SELECTED=()
RUN_PYTHON=0
for suite in "$@"; do
  if [[ "$suite" == python ]]; then RUN_PYTHON=1; else SELECTED+=("$suite"); fi
done
if [[ $# -eq 0 ]]; then
  SELECTED=("${SCENE_SUITES[@]}" "${SCRIPT_SUITES[@]}")
  [[ "${SKIP_PYTHON:-0}" != "1" ]] && RUN_PYTHON=1
fi
for suite in ${SELECTED[@]+"${SELECTED[@]}"}; do
  if [[ "$suite" == Live* || "$suite" == test_live_* || "$suite" == *LiveTest || "$suite" == test_mira_live ]]; then
    echo "run_stranger_tests: $suite needs the network and is not part of this gate" >&2
    exit 2
  fi
done

TIMEOUT_CMD=()
if command -v timeout >/dev/null 2>&1; then TIMEOUT_CMD=(timeout "$SUITE_TIMEOUT")
elif command -v gtimeout >/dev/null 2>&1; then TIMEOUT_CMD=(gtimeout "$SUITE_TIMEOUT"); fi

# A fresh clone has no import cache; import once before any suite loads assets.
if [[ ! -d "$GAME_DIR/.godot/imported" || "${STRANGER_TEST_IMPORT:-0}" == "1" ]]; then
  echo "importing project…"
  XDG_DATA_HOME="$OUT_DIR/xdg-import" "$GODOT_BIN" --headless --path "$GAME_DIR" --import > "$OUT_DIR/import.log" 2>&1
fi

ROWS=()
FAILED=0
for locale in $LOCALES; do
  case "$locale" in
    zh*) lang="zh_CN.UTF-8" ;;
    *) lang="en_US.UTF-8" ;;
  esac
  for suite in ${SELECTED[@]+"${SELECTED[@]}"}; do
    log="$OUT_DIR/$locale-$suite.log"
    xdg="$OUT_DIR/xdg-$locale-$suite"
    rm -rf "$xdg"; mkdir -p "$xdg"
    target=(res://tests/$suite.tscn)
    if [[ "$suite" == test_* ]]; then target=(--script "res://tests/$suite.gd"); fi
    if [[ ! -f "$GAME_DIR/tests/$suite.tscn" && ! -f "$GAME_DIR/tests/$suite.gd" ]]; then
      ROWS+=("$(printf '%-28s %-6s %-6s %s' "$suite" "$locale" "MISS" "no such suite")")
      FAILED=1
      continue
    fi
    started=$SECONDS
    # --language pins the OS locale on every platform (macOS ignores LANG).
    env XDG_DATA_HOME="$xdg" LANG="$lang" LC_ALL="$lang" \
      ${TIMEOUT_CMD[@]+"${TIMEOUT_CMD[@]}"} "$GODOT_BIN" --headless --language "$locale" --path "$GAME_DIR" "${target[@]}" > "$log" 2>&1
    rc=$?
    seconds=$((SECONDS - started))
    status="PASS"
    detail=""
    if [[ $rc -eq 124 ]]; then status="FAIL"; detail="timeout after ${SUITE_TIMEOUT}s"
    elif [[ $rc -ne 0 ]]; then status="FAIL"; detail="exit $rc"
    elif grep -q "SCRIPT ERROR\|Parse Error\|^FAIL" "$log"; then status="FAIL"; detail="script error"; fi
    if [[ "$status" == "FAIL" ]]; then
      FAILED=1
      first="$(grep -m1 "FAIL\|ERROR" "$log" | cut -c1-90)"
      [[ -n "$first" ]] && detail="$detail · $first"
    fi
    row="$(printf '%-28s %-6s %-6s %4ss %s' "$suite" "$locale" "$status" "$seconds" "$detail")"
    ROWS+=("$row")
    echo "$row"
  done
done

python_lane() {
  local name="$1" log="$OUT_DIR/$2.log"
  shift 2
  (cd "$ROOT" && "$PYTHON" "$@") > "$log" 2>&1
  local rc=$? ran result status="PASS"
  ran="$(grep -m1 '^Ran ' "$log")"
  result="$(tail -n 3 "$log" | grep -E '^(OK|FAILED)' | head -1)"
  if [[ $rc -ne 0 ]]; then
    status="FAIL"; FAILED=1
    result="$result · $(grep -E '^(ERROR|FAIL): ' "$log" | head -4 | sed -E 's/^(ERROR|FAIL): //; s/ \(.*//' | paste -sd ',' -)"
  fi
  row="$(printf '%-28s %-6s %-6s %s' "$name" "-" "$status" "$ran · $result")"
  ROWS+=("$row")
  echo "$row"
}

if [[ $RUN_PYTHON -eq 1 ]]; then
  if [[ -z "$PYTHON" ]]; then
    ROWS+=("$(printf '%-28s %-6s %-6s %s' "python" "-" "FAIL" "python not found; set PYTHON")")
    FAILED=1
  else
    python_lane "speech_service (python)" python -m unittest discover -s game/speech_service -p 'test_*.py'
    # The launcher test imports the `game` package, so it runs as a module from the root.
    python_lane "launcher (python)" launcher -m unittest game.test_run_novel
  fi
fi

echo
echo "Stranger offline regression · logs: $OUT_DIR"
printf '%-28s %-6s %-6s %s\n' "SUITE" "LOCALE" "RESULT" "TIME / DETAIL"
printf '%s\n' "${ROWS[@]}"
if [[ $FAILED -ne 0 ]]; then
  echo "RESULT: FAIL"
  exit 1
fi
echo "RESULT: PASS"
