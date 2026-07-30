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
    # video.py decodes via PyAV directly (replaces the ffmpeg CLI subprocess):
    "av",
    # Memorizing module: photo decode/crop (vision.py). PIL's native JPEG/PNG
    # codec plugins must be collected or image decode silently fails post-freeze.
    "PIL",
    # Qwen GGUF runtime, including libllama + Metal dylibs/resources.
    "llama_cpp",
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
# Curated YOLOE labels plus COCO translations and Florence part translations.
# The ONNX weight is staged separately below.
for _coco in ("coco_names.txt", "coco_zh.json", "yoloe_labels.json", "parts_zh.json"):
    datas += [(os.path.join(PROJROOT, "backend", "core", _coco),
               os.path.join("backend", "core"))]

# Pre-bundle the Whisper base.en model (141MB) so transcription runs offline —
# no first-run download. transcribe.py resolves it via a __file__-relative path.
# Conditional: if the model wasn't staged (clean dev), skip and fall back to HF.
# models/ lives at the repo root (one level above desktop/, shared with Android),
# so reach one level above PROJROOT (PROJROOT == desktop/).
_whisper_model = os.path.join(os.path.dirname(PROJROOT), "models", "whisper-base.en")
if os.path.isdir(_whisper_model):
    datas += [(_whisper_model, "models/whisper-base.en")]

# Pre-bundle the detection-only YOLOE-26S-PF ONNX export (FR-13) so broad
# object recognition runs offline. vision.py resolves it via a __file__-
# relative path; models/ is one level above PROJROOT (== desktop/).
_yolo_model = os.path.join(os.path.dirname(PROJROOT), "models", "yoloe-26s-pf")
if os.path.isdir(_yolo_model):
    datas += [(_yolo_model, "models/yoloe-26s-pf")]

a = Analysis(
    [os.path.join(SPECPATH, "main.py")],
    pathex=[PROJROOT],          # so `from backend.core...` resolves at freeze time
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    # NOTE: sklearn is NOT excluded — librosa imports it at runtime. onnxruntime
    # is NOT excluded either — faster-whisper's VAD (vad_filter=True, see
    # transcribe.py) needs it; excluding it makes transcription fail with
    # "Applying the VAD filter requires the onnxruntime package". Only the
    # genuinely scripts-only / never-imported deps stay out.
    excludes=[
        "datasets", "torchcodec",
        "pyarrow", "arrow",
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
