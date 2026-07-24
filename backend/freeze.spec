# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the NativeLingo backend sidecar.

`--onedir` (NOT --onefile): torch / torchaudio / CTranslate2 dlopen many
shared libs by relative path at runtime; onedir keeps them in a stable folder.
onefile re-extracts to a temp dir on every launch — slow and known to break
the torch loader's relative-lib resolution.

Models are NOT bundled here: they download to ~/.cache (HuggingFace / torch
hub) on first use, per NFR-1 (local + offline after first run).

Bundled into the .app as a Tauri `resource` (not externalBin — externalBin
wants a single executable and fights the onedir folder shape). The shell
spawns `<resource_dir>/nativeLingoBackend/nativeLingoBackend` and the binary
inherits the same NATIVELINGO_TOKEN/PORT/HOST env-var contract as
`python -m backend.main`, so backend/main.py needs no changes.
"""
import os

from PyInstaller.utils.hooks import collect_all

SPECPATH = os.path.dirname(os.path.abspath(SPEC))   # .../backend
PROJROOT = os.path.dirname(SPECPATH)                 # project root (parent of backend/)

datas, binaries, hiddenimports = [], [], []

# Heavy / native-lib packages: pull their data files + binaries + submodules
# wholesale. Incomplete collection here is the main freeze failure mode
# (e.g. a missing torchaudio would silently disable forced alignment because
# backend/core/forced_align.py imports it inside a try/except).
for pkg in [
    "torch", "torchaudio", "transformers", "faster_whisper", "ctranslate2",
    "parselmouth", "soundfile", "librosa", "huggingface_hub", "tokenizers",
    "uvicorn", "anyio", "h11",
    # librosa transitively needs these at runtime (audio decode path):
    "sklearn", "numba", "llvmlite",
]:
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# faster-whisper / CTranslate2 backends + tokenizers are imported lazily.
hiddenimports += ["ctranslate2", "ctranslate2.convertors", "tokenizers"]

# Ship the fitted calibration map next to score_b.py — score_b loads it by a
# __file__-relative path, and PyInstaller does not auto-collect sibling .json
# data files. Without this the frozen app silently falls back to the manual map.
datas += [(os.path.join(PROJROOT, "backend", "core", "calibration.json"),
           os.path.join("backend", "core"))]

a = Analysis(
    [os.path.join(SPECPATH, "main.py")],
    pathex=[PROJROOT],          # so `from backend.core...` resolves at freeze time
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    # NOTE: sklearn is NOT excluded — librosa imports it at runtime. pyarrow /
    # onnxruntime are pure leakage when freezing from a venv that also holds the
    # calibration scripts (datasets -> pyarrow); they bloat the bundle by ~260MB
    # and the app never imports them. (Freezing from a clean .venv-freeze with
    # only requirements-runtime.txt removes them at the source; this is backup.)
    excludes=[
        "datasets", "torchcodec",
        "pyarrow", "arrow", "onnxruntime",
        "pytest", "matplotlib", "pandas", "IPython",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="nativeLingoBackend",
    debug=False,
    strip=False,
    upx=False,
    console=False,              # no Terminal window on launch; parent redirects stdout
    target_arch="arm64",
)

coll = COLLECT(exe, a.binaries, a.datas, name="nativeLingoBackend")
