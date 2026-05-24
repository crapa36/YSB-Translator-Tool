# -*- coding: utf-8 -*-
"""Local dependency checker.

PaddleOCR is run through an external worker in the Local package, not imported
inside the frozen EXE.  Therefore the runtime check accepts either an importable
source-environment paddleocr module or the packaged worker + portable Python
runtime pair.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


def module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    try:
        return Path(__file__).resolve().parents[3]
    except Exception:
        return Path.cwd()


def external_paddleocr_worker_status() -> tuple[bool, str]:
    root = _app_root()
    worker = root / "local_runtime" / "paddle_ocr_worker.py"
    env_python = os.environ.get("YSB_PADDLEOCR_PYTHON")
    python_candidates = []
    if env_python:
        python_candidates.append(Path(env_python).expanduser())
    python_candidates.extend([
        root / "local_runtime" / "python" / "python.exe",
        root / "local_runtime" / "ocr_venv" / "Scripts" / "python.exe",
        root / "local_runtime" / "ocr_venv" / "bin" / "python",
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
    ])
    if not worker.exists():
        return False, f"External PaddleOCR worker not found: {worker}"
    for py in python_candidates:
        if py.exists():
            return True, f"External PaddleOCR worker ready: {py}"
    return False, "External PaddleOCR Python runtime not found. local_runtime/python/python.exe를 확인해 주세요."


def paddleocr_available() -> bool:
    ok, _ = external_paddleocr_worker_status()
    if ok:
        return True
    return module_available("paddleocr")


def comic_text_detector_required_modules() -> list[str]:
    return ["torch", "torchvision", "cv2", "numpy", "pyclipper", "shapely", "tqdm", "PIL", "yaml"]


def comic_text_detector_runtime_status() -> tuple[bool, list[str]]:
    missing: list[str] = []
    for module_name in comic_text_detector_required_modules():
        if not module_available(module_name):
            missing.append(module_name)
    return len(missing) == 0, missing


def external_manga_ocr_worker_status() -> tuple[bool, str]:
    root = _app_root()
    worker_candidates = [
        # Final Local distribution layout.
        root / "local_runtime" / "manga_ocr" / "manga_ocr_worker.py",
        # Backward-compatible layout from old test builds.
        root / "local_runtime" / "manga_ocr_worker.py",
    ]
    env_python = os.environ.get("YSB_MANGA_OCR_PYTHON") or os.environ.get("YSB_PADDLEOCR_PYTHON")
    python_candidates = []
    if env_python:
        python_candidates.append(Path(env_python).expanduser())
    python_candidates.extend([
        # Final Local distribution uses a separate Manga OCR runtime.
        root / "local_runtime" / "manga_ocr" / "python" / "python.exe",
        # Source/dev optional Manga OCR runtime.
        root / "local_runtime" / "manga_ocr_venv" / "Scripts" / "python.exe",
        root / "local_runtime" / "manga_ocr_venv" / "bin" / "python",
        # Backward-compatible fallbacks from old test builds.
        root / "local_runtime" / "python" / "python.exe",
        root / "local_runtime" / "ocr_venv" / "Scripts" / "python.exe",
        root / "local_runtime" / "ocr_venv" / "bin" / "python",
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
    ])
    worker = next((w for w in worker_candidates if w.exists()), None)
    if worker is None:
        return False, "External Manga OCR worker not found: local_runtime/manga_ocr/manga_ocr_worker.py"
    for py in python_candidates:
        if py.exists():
            return True, f"External Manga OCR worker ready: {py}"
    return False, "External Manga OCR Python runtime not found. local_runtime/manga_ocr/python/python.exe를 확인해 주세요."


def _manga_model_dir_ready(model_dir: Path) -> bool:
    if not model_dir.exists():
        return False
    snapshots = model_dir / "snapshots"
    try:
        if snapshots.exists() and any(snapshots.iterdir()):
            return True
    except Exception:
        pass
    try:
        if any(model_dir.rglob("*.safetensors")) or any(model_dir.rglob("*.bin")):
            return True
    except Exception:
        pass
    return False


def manga_ocr_model_status() -> tuple[bool, str]:
    root = _app_root()
    model_rel = Path("huggingface") / "hub" / "models--kha-white--manga-ocr-base"
    candidates = [
        # Final Local distribution: model is bundled inside the Manga OCR runtime.
        root / "local_runtime" / "manga_ocr" / "model_cache" / model_rel,
        # Source/dev and old test layout fallback.
        root / "local_models" / "manga_ocr" / model_rel,
    ]
    for model_dir in candidates:
        if _manga_model_dir_ready(model_dir):
            return True, f"Manga OCR model found: {model_dir}"
    return False, (
        "Manga OCR model not found. 배포판에서는 local_runtime/manga_ocr/model_cache 안의 모델을 확인해 주세요. "
        f"Checked: {candidates[0]}"
    )


def manga_ocr_available() -> bool:
    ok, _ = external_manga_ocr_worker_status()
    if ok:
        return True
    return module_available("manga_ocr")


def manga_ocr_ready() -> tuple[bool, str]:
    worker_ok, worker_msg = external_manga_ocr_worker_status()
    import_ok = module_available("manga_ocr")
    if not worker_ok and not import_ok:
        return False, "manga-ocr 실행 환경을 찾을 수 없습니다. local_runtime/python 또는 .venv 설치 상태를 확인해 주세요."
    model_ok, msg = manga_ocr_model_status()
    if not model_ok:
        return False, msg
    return True, worker_msg if worker_ok else msg
