"""Unit tests for the Piper TTS wrapper (FR-17).

The 79 MB voice model is not required — ``piper`` is fully mocked so the
module's load/unload/synth/resample logic is exercised without a download.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

from backend.core import piper_tts


class _Chunk:
    def __init__(self, audio_float_array):
        self.audio_float_array = audio_float_array


class _FakeVoice:
    """Mimics piper.PiperVoice enough for the wrapper."""
    sample_rate = 22050

    def __init__(self, outputs):
        self.config = type("C", (), {"sample_rate": self.sample_rate})()
        self.outputs = outputs
        self.syn_configs = []

    @classmethod
    def load(cls, model_path, espeak_data_dir=None, **kwargs):
        return cls([])

    def synthesize(self, text, syn_config=None):
        assert syn_config is not None  # determinism must be on
        self.syn_configs.append(syn_config)
        return iter(self.outputs)


class _FakeSynthesisConfig:
    def __init__(self, **kwargs):
        self.noise_scale = kwargs.get("noise_scale")
        self.noise_w_scale = kwargs.get("noise_w_scale")


def _install_fake(monkeypatch, fake_cls):
    fake_mod = type(
        "piper",
        (),
        {"PiperVoice": fake_cls, "SynthesisConfig": _FakeSynthesisConfig},
    )
    fake_mod.__file__ = "/fake/piper/__init__.py"
    monkeypatch.setitem(__import__("sys").modules, "piper", fake_mod)


def _sine_second(sr: int) -> np.ndarray:
    t = np.arange(sr, dtype=np.float32) / sr
    return (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


@pytest.fixture(autouse=True)
def _clean():
    piper_tts.unload()
    yield
    piper_tts.unload()


def test_synth_before_load_raises():
    with pytest.raises(RuntimeError, match="not loaded"):
        piper_tts.synth_wav("mug")


def test_load_unload_toggles_state(monkeypatch):
    _install_fake(monkeypatch, _FakeVoice)
    monkeypatch.setattr(piper_tts, "_espeak_data_dir", lambda: "/fake/espeak")
    assert not piper_tts.is_loaded()
    piper_tts.load("/fake/model.onnx")
    assert piper_tts.is_loaded()
    piper_tts.unload()
    assert not piper_tts.is_loaded()


def test_frozen_espeak_path_is_resolved_without_importing_piper(monkeypatch, tmp_path):
    data_dir = tmp_path / "piper" / "espeak-ng-data"
    data_dir.mkdir(parents=True)
    (data_dir / "phontab").write_bytes(b"test")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(
        piper_tts.importlib.util,
        "find_spec",
        lambda name: (_ for _ in ()).throw(AssertionError("must use _MEIPASS first")),
    )

    assert piper_tts._espeak_data_dir() == str(data_dir)


def test_load_overrides_stale_espeak_path_before_piper_use(monkeypatch):
    class _CheckingVoice(_FakeVoice):
        @classmethod
        def load(cls, model_path, espeak_data_dir=None, **kwargs):
            assert os.environ["ESPEAK_DATA_PATH"] == "/fake/espeak"
            assert espeak_data_dir == "/fake/espeak"
            return cls([])

    _install_fake(monkeypatch, _CheckingVoice)
    monkeypatch.setattr(piper_tts, "_espeak_data_dir", lambda: "/fake/espeak")
    monkeypatch.setenv("ESPEAK_DATA_PATH", "/stale/build-machine/path")

    piper_tts.load("/fake/model.onnx")
    assert os.environ["ESPEAK_DATA_PATH"] == "/fake/espeak"
    assert piper_tts.is_loaded()


def test_frozen_macos_uses_system_voice_without_loading_piper(monkeypatch):
    monkeypatch.setattr(piper_tts, "uses_system_voice", lambda: True)
    expected = _sine_second(16000)
    monkeypatch.setattr(piper_tts, "_synth_macos_say", lambda text: expected)

    piper_tts.load("")
    wav = piper_tts.synth_wav("teapot")

    assert piper_tts.is_loaded()
    assert wav is expected


def test_synth_resamples_to_16k(monkeypatch):
    voice = _FakeVoice([_Chunk(_sine_second(22050))])
    _install_fake(monkeypatch, _FakeVoice)
    monkeypatch.setattr(_FakeVoice, "load", classmethod(lambda cls, path, **kw: voice))
    monkeypatch.setattr(piper_tts, "_espeak_data_dir", lambda: "/fake/espeak")

    piper_tts.load("/fake/model.onnx")
    wav = piper_tts.synth_wav("mug")
    assert wav.dtype == np.float32
    assert wav.ndim == 1
    # 1 s @ 22050 -> ~1 s @ 16000 (librosa resample keeps ~same duration)
    assert abs(len(wav) - 16000) < 400
    assert float(np.abs(wav).max()) > 0.1  # tone survived resample
    assert voice.syn_configs, "synthesis must use an explicit config (determinism)"


def test_synth_no_audio_raises_value_error(monkeypatch):
    voice = _FakeVoice([])
    _install_fake(monkeypatch, _FakeVoice)
    monkeypatch.setattr(_FakeVoice, "load", classmethod(lambda cls, path, **kw: voice))
    monkeypatch.setattr(piper_tts, "_espeak_data_dir", lambda: "/fake/espeak")

    piper_tts.load("/fake/model.onnx")
    with pytest.raises(ValueError, match="no audio"):
        piper_tts.synth_wav("mug")
