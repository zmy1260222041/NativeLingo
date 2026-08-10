"""Survival on-device store (R-14 G1/G2 corpus collection).

The regression these guard: /recordings uses tempfile.mkdtemp, which is right
for a scratch buffer and fatal for corpus collection — a restart erases it. The
whole reason the beta build exists is to accumulate recordings, so
test_game_dir_follows_data_dir_env and test_survives_a_fresh_process pin the
storage root to NATIVELINGO_DATA_DIR.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import os
import subprocess
import sys

import pytest

from backend.core import game_store

# Same gate-by-path resolution as test_game_scenario: scripts/ is not an
# installed package, and we want the same file the product matcher is pinned to.
_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
)
_GATE = os.path.join(_REPO, "scripts", "game_delivery_gate.py")


@pytest.fixture()
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("NATIVELINGO_DATA_DIR", str(tmp_path))
    return str(tmp_path)


def test_game_dir_follows_data_dir_env(root):
    d = game_store.game_dir()
    assert d == os.path.join(root, "game")
    assert os.path.isdir(os.path.join(d, "attempts"))
    assert os.path.isdir(os.path.join(d, "corrections"))
    # never a temp dir — that is the whole point (红线 2)
    assert "tmp" not in os.path.relpath(d, root)


def test_dir_is_stable_across_calls_and_never_a_temp_dir(monkeypatch, tmp_path):
    """mkdtemp's failure mode is a *new* directory per process, so pin the
    property that actually matters: the path is a pure function of the data dir.
    Checked both with the env var set and with the dev fallback."""
    import tempfile

    monkeypatch.setenv("NATIVELINGO_DATA_DIR", str(tmp_path))
    assert game_store.game_dir() == game_store.game_dir()

    # The dev fallback is asserted without invoking it — calling game_dir() with
    # no env var would create <repo>/game/ in the working tree.
    monkeypatch.delenv("NATIVELINGO_DATA_DIR", raising=False)
    here = os.path.dirname(os.path.abspath(game_store.__file__))
    expected_root = os.path.abspath(os.path.join(here, "..", "..", ".."))
    assert not expected_root.startswith(tempfile.gettempdir())
    assert os.path.isdir(expected_root)


def test_save_and_load_attempt_roundtrip(root):
    aid = game_store.new_attempt_id()
    game_store.save_attempt(aid, {
        "created_at": "2026-08-10T00:00:00+00:00",
        "scenario_id": "food-ask-bread",
        "tier": "infant",
        "transcript": "me want bread",
        "delivery": 85.0,
        "delivered": True,
    })
    loaded = game_store.load_attempt(aid)
    assert loaded["transcript"] == "me want bread"
    assert loaded["attempt_id"] == aid
    assert loaded["store_version"] == game_store.STORE_VERSION


def test_correction_is_a_separate_file(root):
    """The attempt keeps what the instrument heard; the correction keeps what the
    human says was said. Merging them would erase the (A)/(B) distinction."""
    aid = game_store.new_attempt_id()
    game_store.save_attempt(aid, {"transcript": "me want bit", "delivery": 42.5})
    game_store.save_correction(aid, {"corrected_text": "me want bread",
                                     "asr_text": "me want bit"})
    attempt = game_store.load_attempt(aid)
    assert attempt["transcript"] == "me want bit"  # untouched by the correction
    assert "corrected_text" not in attempt
    assert game_store.load_correction(aid)["corrected_text"] == "me want bread"


def test_load_correction_absent_is_none(root):
    aid = game_store.new_attempt_id()
    game_store.save_attempt(aid, {"transcript": "x"})
    assert game_store.load_correction(aid) is None


@pytest.mark.parametrize("bad", ["../escape", "a/b", "", "x" * 65, "a b", "a.json"])
def test_invalid_attempt_ids_are_rejected_not_sanitised(root, bad):
    """These arrive from a URL path; a silently-rewritten id would read or
    overwrite a different attempt."""
    with pytest.raises(ValueError):
        game_store.attempt_json_path(bad)


def test_list_attempts_sorted_and_skips_corrupt(root):
    for i, ts in enumerate(["2026-08-10T00:00:02+00:00",
                            "2026-08-10T00:00:01+00:00",
                            "2026-08-10T00:00:03+00:00"]):
        game_store.save_attempt(f"aid{i}", {"created_at": ts, "transcript": str(i)})
    bad = os.path.join(game_store.game_dir(), "attempts", "broken.json")
    with open(bad, "w", encoding="utf-8") as fh:
        fh.write("{ truncated")
    rows = game_store.list_attempts()
    assert [r["transcript"] for r in rows] == ["1", "0", "2"]
    assert all("correction" in r for r in rows)


def test_export_leaves_human_columns_empty(root):
    """A gate must not grade its own homework: `delivered`, `expected_keywords`
    and `well_pronounced` are made by listening, never prefilled from the ASR."""
    aid = game_store.new_attempt_id()
    game_store.save_attempt(aid, {
        "created_at": "2026-08-10T00:00:00+00:00",
        "scenario_id": "food-ask-bread",
        "tier": "infant",
        "transcript": "me want bit",
        "delivery": 42.5,
        "delivered": False,
    })
    game_store.save_correction(aid, {"corrected_text": "me want bread"})

    export = game_store.export_rows()
    assert export["count"] == 1 and export["corrected_count"] == 1
    row = export["delivery_rows"][0]
    assert row["response_text"] == "me want bit"     # production path output
    assert row["corrected_text"] == "me want bread"  # kept in its own column
    assert row["delivered"] == ""                    # human ground truth, unfilled
    assert row["origin"] == ""                       # attested by a human, not by us
    assert row["collection"] == "beta-collect"       # route stays visible
    entry = export["asr_manifest"][0]
    assert entry["clip"] == f"{aid}.wav"
    assert entry["expected_keywords"] == [] and entry["well_pronounced"] == []
    assert entry["intended"] == "me want bread"
    assert export["annotation_todo"]


def test_export_columns_match_the_gate_harness_readers(root):
    """G1's load_rows requires these exact column names; drift here means the
    export stops feeding the harness."""
    game_store.save_attempt(game_store.new_attempt_id(), {"transcript": "x"})
    row = game_store.export_rows()["delivery_rows"][0]
    assert {"scenario_id", "response_text", "delivered", "origin"} <= set(row)
    entry = game_store.export_rows()["asr_manifest"][0]
    assert {"clip", "scenario", "tier", "expected_keywords", "well_pronounced"} <= set(entry)


def test_unattested_origin_is_what_g1_treats_as_blocking(root, tmp_path):
    """The export leaves `origin` blank on purpose. That is only safe while G1
    reads blank as "not real" and withholds its verdict -- if a refactor ever
    made blank default to `real`, every un-listened beta row would silently earn
    a verdict. Pin the gate's own reader against our own export."""
    if not os.path.isfile(_GATE):
        pytest.skip(f"G1 harness not present: {_GATE}")
    spec = importlib.util.spec_from_file_location("g1_origin_probe", _GATE)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)

    game_store.save_attempt(game_store.new_attempt_id(), {
        "scenario_id": "food-ask-bread", "tier": "infant", "transcript": "i want bread",
    })
    export = game_store.export_rows()
    csv_path = tmp_path / "responses.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(export["delivery_rows"][0]))
        writer.writeheader()
        for row in export["delivery_rows"]:
            writer.writerow({**row, "delivered": "1"})  # only the truth column filled

    rows = gate.load_rows(str(csv_path))
    assert rows, "the gate must still be able to parse our export"
    assert rows[0]["origin"] != "real"
    # ...and that is precisely the condition the gate blocks a verdict on.
    assert sum(1 for r in rows if r["origin"] != "real") == len(rows)


def test_partial_write_cannot_leave_a_corrupt_attempt(root):
    """Writes go through a temp file + rename, so an attempt file is either the
    previous version or the new one — never half of either."""
    aid = game_store.new_attempt_id()
    game_store.save_attempt(aid, {"transcript": "first"})
    path = game_store.attempt_json_path(aid)
    game_store.save_attempt(aid, {"transcript": "second"})
    assert json.load(open(path, encoding="utf-8"))["transcript"] == "second"
    leftovers = [n for n in os.listdir(os.path.dirname(path)) if n.endswith(".tmp")]
    assert leftovers == []


def test_survives_a_fresh_process(root):
    """The acceptance criterion behind 红线 2: a restart must not lose corpus."""
    aid = game_store.new_attempt_id()
    game_store.save_attempt(aid, {"created_at": "2026-08-10T00:00:00+00:00",
                                  "transcript": "still here"})
    backend = os.path.dirname(os.path.dirname(os.path.abspath(game_store.__file__)))
    out = subprocess.run(
        [sys.executable, "-c",
         "from backend.core import game_store as g;"
         "print(g.load_attempt(__import__('sys').argv[1])['transcript'])", aid],
        cwd=os.path.dirname(backend),
        env={**os.environ, "NATIVELINGO_DATA_DIR": root,
             "PYTHONPATH": os.path.dirname(backend)},
        capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stderr
    assert "still here" in out.stdout
