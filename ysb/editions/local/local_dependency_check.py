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
import subprocess
import sys
from pathlib import Path


def module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


MANGA_OCR_REQUIRED_MODULES = ["torch", "PIL", "transformers", "fugashi", "unidic_lite"]


def _same_path(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except Exception:
        return str(a) == str(b)


def _python_has_modules(python: Path, modules: list[str]) -> tuple[bool, list[str], str]:
    """Check whether *python* can import the required Manga OCR modules."""
    missing: list[str] = []
    if _same_path(python, Path(sys.executable)):
        for module_name in modules:
            if not module_available(module_name):
                missing.append(module_name)
        return len(missing) == 0, missing, "current"

    code = (
        "import importlib.util, json, sys; "
        "mods=" + repr(modules) + "; "
        "missing=[m for m in mods if importlib.util.find_spec(m) is None]; "
        "print(json.dumps(missing, ensure_ascii=False)); "
        "sys.exit(1 if missing else 0)"
    )
    try:
        proc = subprocess.run(
            [str(python), "-c", code],
            cwd=str(_app_root()),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        import json
        try:
            missing = list(json.loads((proc.stdout or "[]").strip() or "[]"))
        except Exception:
            missing = modules if proc.returncode else []
        return proc.returncode == 0, missing, (proc.stderr or proc.stdout or "").strip()
    except Exception as e:
        return False, modules, str(e)


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    try:
        return Path(__file__).resolve().parents[3]
    except Exception:
        return Path.cwd()


def _external_paddleocr_worker_file() -> Path:
    """Return the same external PaddleOCR worker path used by ysb.engines.ocr.paddle_ocr."""
    root = _app_root()
    preferred = root / "local_runtime" / "paddle" / "paddle_ocr_worker.py"
    if preferred.exists():
        return preferred
    return root / "local_runtime" / "paddle_ocr_worker.py"


def _external_paddleocr_python_candidates() -> list[Path]:
    """Return the same PaddleOCR Python runtime candidates used by the real OCR adapter."""
    root = _app_root()
    candidates: list[Path] = []
    env_python = os.environ.get("YSB_PADDLEOCR_PYTHON")
    if env_python:
        candidates.append(Path(env_python).expanduser())
    candidates.extend([
        root / "local_runtime" / "paddle" / "python" / "python.exe",
        root / "local_runtime" / "python" / "python.exe",
        root / "local_runtime" / "paddle_ocr_venv" / "Scripts" / "python.exe",
        root / "local_runtime" / "paddle_ocr_venv" / "bin" / "python",
        root / "local_runtime" / "ocr_venv" / "Scripts" / "python.exe",
        root / "local_runtime" / "ocr_venv" / "bin" / "python",
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
    ])
    if not getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable))
    return candidates


def external_paddleocr_worker_status() -> tuple[bool, str]:
    worker = _external_paddleocr_worker_file()
    python_candidates = _external_paddleocr_python_candidates()
    if not worker.exists():
        return False, f"External PaddleOCR worker not found: {worker}"
    for py in python_candidates:
        if py.exists():
            return True, f"External PaddleOCR worker ready: {py} / worker: {worker}"
    return False, "External PaddleOCR Python runtime not found. local_runtime/paddle/python/python.exe를 확인해 주세요."


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


def _manga_ocr_python_candidates() -> list[Path]:
    root = _app_root()
    env_python = os.environ.get("YSB_MANGA_OCR_PYTHON") or os.environ.get("YSB_PADDLEOCR_PYTHON")
    python_candidates: list[Path] = []
    if env_python:
        python_candidates.append(Path(env_python).expanduser())

    if not getattr(sys, "frozen", False):
        # Source/test mode: use the active venv/current interpreter first.
        # local_runtime is only the worker script location here, not a required
        # Python runtime folder.
        python_candidates.extend([
            Path(sys.executable),
            root / ".venv" / "Scripts" / "python.exe",
            root / ".venv" / "bin" / "python",
        ])
    else:
        # Packaged Local distribution: the frozen EXE needs a separate Python
        # runtime for the heavy Manga OCR stack.
        python_candidates.extend([
            root / "local_runtime" / "manga_ocr" / "python" / "python.exe",
            root / "local_runtime" / "python" / "python.exe",
        ])

    python_candidates.extend([
        # Optional / backward-compatible explicit runtimes.
        root / "local_runtime" / "manga_ocr_venv" / "Scripts" / "python.exe",
        root / "local_runtime" / "manga_ocr_venv" / "bin" / "python",
        root / "local_runtime" / "ocr_venv" / "Scripts" / "python.exe",
        root / "local_runtime" / "ocr_venv" / "bin" / "python",
    ])

    unique: list[Path] = []
    seen: set[str] = set()
    for py in python_candidates:
        try:
            key = str(py.resolve())
        except Exception:
            key = str(py)
        if key in seen:
            continue
        seen.add(key)
        unique.append(py)
    return unique


def external_manga_ocr_worker_status() -> tuple[bool, str]:
    root = _app_root()
    worker_candidates = [
        root / "local_runtime" / "manga_ocr" / "manga_ocr_worker.py",
        root / "local_runtime" / "manga_ocr_worker.py",
    ]
    worker = next((w for w in worker_candidates if w.exists()), None)
    if worker is None and getattr(sys, "frozen", False):
        return False, "External Manga OCR worker not found: local_runtime/manga_ocr/manga_ocr_worker.py"

    for py in _manga_ocr_python_candidates():
        if not py.exists():
            continue
        deps_ok, missing, detail = _python_has_modules(py, MANGA_OCR_REQUIRED_MODULES)
        if deps_ok:
            mode = "source/test current Python" if not getattr(sys, "frozen", False) and _same_path(py, Path(sys.executable)) else "external worker Python"
            if worker is not None:
                return True, f"Manga OCR ready via {mode}: {py}"
            return True, f"Manga OCR direct source/test ready: {py}"
        return False, (
            f"Manga OCR Python dependencies missing in {py}: {', '.join(missing)}. "
            "소스/테스트판은 setup_manga_ocr_v2_2_1.bat을 실행해 .venv에 설치해 주세요. "
            f"Detail: {detail}"
        )

    if getattr(sys, "frozen", False):
        return False, "External Manga OCR Python runtime not found. 배포판에서는 local_runtime/manga_ocr/python/python.exe를 확인해 주세요."
    return False, "Manga OCR source/test Python not found. .venv 또는 현재 Python 실행 상태를 확인해 주세요."


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
        "Manga OCR model not found. local_models/manga_ocr 또는 배포판의 local_runtime/manga_ocr/model_cache를 확인해 주세요. "
        f"Checked: {candidates}"
    )


def manga_ocr_available() -> bool:
    ok, _ = external_manga_ocr_worker_status()
    return ok


def manga_ocr_ready() -> tuple[bool, str]:
    runtime_ok, runtime_msg = external_manga_ocr_worker_status()
    if not runtime_ok:
        return False, runtime_msg
    model_ok, msg = manga_ocr_model_status()
    if not model_ok:
        return False, msg
    return True, f"{runtime_msg} / {msg}"
