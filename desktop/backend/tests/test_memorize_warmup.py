"""Lifecycle regression tests for on-demand Memorizing model loading."""
from __future__ import annotations

import threading
import time

from backend.core import memorize_warmup, parts, scenario, vision


def test_release_cancels_an_inflight_generation(monkeypatch):
    scenario_started = threading.Event()
    allow_scenario_finish = threading.Event()
    parts_loaded = threading.Event()
    scenario_unloads = []

    monkeypatch.setattr(vision, "_load", lambda: object())

    def slow_scenario_load():
        scenario_started.set()
        assert allow_scenario_finish.wait(timeout=2)
        return object()

    monkeypatch.setattr(scenario, "_load", slow_scenario_load)
    monkeypatch.setattr(scenario, "unload", lambda: scenario_unloads.append(True))
    monkeypatch.setattr(parts, "_load", lambda: parts_loaded.set())
    monkeypatch.setattr(parts, "unload", lambda: None)

    memorize_warmup.release()
    scenario_unloads.clear()
    memorize_warmup.start()
    assert scenario_started.wait(timeout=2)
    memorize_warmup.release()
    allow_scenario_finish.set()

    deadline = time.time() + 2
    while len(scenario_unloads) < 2 and time.time() < deadline:
        time.sleep(0.01)

    assert not parts_loaded.is_set()
    assert len(scenario_unloads) >= 2  # release + stale worker cleanup
    assert memorize_warmup.status() == {
        "running": False,
        "stage": "idle",
        "yolo_ready": False,
        "llm_ready": False,
        "florence_ready": False,
        "error": None,
    }
