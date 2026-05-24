# -*- coding: utf-8 -*-
"""Local Manga OCR adapter.

Manga OCR is a recognition-only OCR model for Japanese manga text.  It does
not return detection boxes, so YSB uses the Local text detector for
regions/masks and applies Manga OCR only to cropped text regions.

In packaged Local builds, Manga OCR runs through local_runtime/manga_ocr_worker.py
so transformers/tokenizers do not need to be frozen into the main EXE.  In
source/dev mode, it can also fall back to importing manga_ocr directly from the
current Python environment.
"""

from __future__ import annotations

import atexit
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from ysb.engines.ocr.base import OcrRequest, OcrResult

_ENGINE = None
_EXTERNAL_WORKER_CLIENT = None

MODEL_ID = "kha-white/manga-ocr-base"


def _hidden_worker_popen_kwargs() -> dict[str, Any]:
    if os.name != "nt":
        return {}
    kwargs: dict[str, Any] = {}
    try:
        flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if flags:
            kwargs["creationflags"] = flags
    except Exception:
        pass
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo
    except Exception:
        pass
    return kwargs


def _app_root() -> Path:
    """Return the project/app root so local_models works in source and frozen builds."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    try:
        return Path(__file__).resolve().parents[3]
    except Exception:
        return Path.cwd()


def _runtime_manga_ocr_root() -> Path:
    return _app_root() / "local_runtime" / "manga_ocr"


def manga_ocr_runtime_model_root() -> Path:
    return _runtime_manga_ocr_root() / "model_cache"


def manga_ocr_legacy_model_root() -> Path:
    return _app_root() / "local_models" / "manga_ocr"


def manga_ocr_model_root() -> Path:
    """Return the active Manga OCR model root.

    Packaged Local builds keep the model inside the Manga OCR runtime:
        local_runtime/manga_ocr/model_cache

    Source/dev mode may still use:
        local_models/manga_ocr
    """
    runtime_root = manga_ocr_runtime_model_root()
    legacy_root = manga_ocr_legacy_model_root()
    runtime_model_dir = runtime_root / "huggingface" / "hub" / "models--kha-white--manga-ocr-base"
    legacy_model_dir = legacy_root / "huggingface" / "hub" / "models--kha-white--manga-ocr-base"
    if runtime_model_dir.exists():
        return runtime_root
    if legacy_model_dir.exists():
        return legacy_root
    if (_runtime_manga_ocr_root() / "python" / "python.exe").exists():
        return runtime_root
    return legacy_root


def manga_ocr_hf_home() -> Path:
    return manga_ocr_model_root() / "huggingface"


def manga_ocr_hub_cache() -> Path:
    return manga_ocr_hf_home() / "hub"


def manga_ocr_transformers_cache() -> Path:
    return manga_ocr_hf_home() / "transformers"


def manga_ocr_model_exists() -> bool:
    """True when the Manga OCR Hugging Face model is already under local_models."""
    hub = manga_ocr_hub_cache()
    model_dir = hub / "models--kha-white--manga-ocr-base"
    if not model_dir.exists():
        return False
    snapshots = model_dir / "snapshots"
    if snapshots.exists() and any(snapshots.iterdir()):
        return True
    return any(model_dir.rglob("*.safetensors")) or any(model_dir.rglob("*.bin"))


def ensure_manga_ocr_local_cache_env() -> Path:
    """Force manga-ocr/transformers cache into project local_models."""
    root = manga_ocr_model_root()
    hf_home = manga_ocr_hf_home()
    hub_cache = manga_ocr_hub_cache()
    transformers_cache = manga_ocr_transformers_cache()
    for d in (root, hf_home, hub_cache, transformers_cache):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    os.environ["HF_HOME"] = str(hf_home)
    os.environ["HF_HUB_CACHE"] = str(hub_cache)
    os.environ["TRANSFORMERS_CACHE"] = str(transformers_cache)
    os.environ.setdefault("PYTHONUTF8", "1")
    return root


def _external_worker_file() -> Path:
    root = _app_root()
    preferred = root / "local_runtime" / "manga_ocr" / "manga_ocr_worker.py"
    if preferred.exists():
        return preferred
    return root / "local_runtime" / "manga_ocr_worker.py"


def _external_worker_python() -> Path | None:
    env_python = os.environ.get("YSB_MANGA_OCR_PYTHON")
    if env_python:
        candidate = Path(env_python).expanduser()
        if candidate.exists():
            return candidate
    root = _app_root()
    candidates = [
        # Final Local distribution uses its own Manga OCR runtime, separate from PaddleOCR.
        root / "local_runtime" / "manga_ocr" / "python" / "python.exe",

        # Source/dev optional Manga OCR runtime.
        root / "local_runtime" / "manga_ocr_venv" / "Scripts" / "python.exe",
        root / "local_runtime" / "manga_ocr_venv" / "bin" / "python",

        # Backward-compatible fallbacks from older test builds.
        root / "local_runtime" / "python" / "python.exe",
        root / "local_runtime" / "ocr_venv" / "Scripts" / "python.exe",
        root / "local_runtime" / "ocr_venv" / "bin" / "python",
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
    ]
    if not getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _should_use_external_worker() -> bool:
    if os.environ.get("YSB_MANGA_OCR_INTERNAL", "").strip().lower() in ("1", "true", "yes"):
        return False
    return _external_worker_file().exists() and _external_worker_python() is not None


class _ExternalMangaOcrWorkerClient:
    def __init__(self):
        self.proc: subprocess.Popen[str] | None = None
        self.log_handle = None
        self.log_path = _app_root() / "ysb_manga_ocr_worker.log"

    def close(self) -> None:
        proc = self.proc
        self.proc = None
        try:
            if proc and proc.poll() is None and proc.stdin:
                proc.stdin.write(json.dumps({"cmd": "shutdown"}, ensure_ascii=False) + "\n")
                proc.stdin.flush()
        except Exception:
            pass
        try:
            if proc and proc.poll() is None:
                proc.terminate()
        except Exception:
            pass
        try:
            if self.log_handle:
                self.log_handle.close()
        except Exception:
            pass
        self.log_handle = None

    def _start(self) -> None:
        if self.proc and self.proc.poll() is None:
            return
        worker = _external_worker_file()
        python = _external_worker_python()
        if not worker.exists():
            raise RuntimeError(f"External Manga OCR worker not found: {worker}")
        if python is None:
            raise RuntimeError("External Manga OCR Python runtime not found. local_runtime/manga_ocr/python/python.exe를 확인해 주세요.")

        env = os.environ.copy()
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        ensure_manga_ocr_local_cache_env()
        env["HF_HOME"] = str(manga_ocr_hf_home())
        env["HF_HUB_CACHE"] = str(manga_ocr_hub_cache())
        env["TRANSFORMERS_CACHE"] = str(manga_ocr_transformers_cache())

        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_handle = open(self.log_path, "a", encoding="utf-8", errors="replace")
            self.log_handle.write("\n=== YSB External Manga OCR worker start ===\n")
            self.log_handle.write(f"python={python}\nworker={worker}\napp_root={_app_root()}\n")
            self.log_handle.flush()
        except Exception:
            self.log_handle = subprocess.DEVNULL  # type: ignore[assignment]

        self.proc = subprocess.Popen(
            [str(python), str(worker), "--server"],
            cwd=str(_app_root()),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.log_handle if self.log_handle is not None else subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            **_hidden_worker_popen_kwargs(),
        )
        if self.proc.stdout is None:
            raise RuntimeError("External Manga OCR worker stdout pipe was not created.")
        ready_line = self.proc.stdout.readline().strip()
        try:
            ready = json.loads(ready_line)
        except Exception:
            ready = {}
        if not ready.get("ready"):
            raise RuntimeError(f"External Manga OCR worker did not become ready: {ready_line}")

    def run_image(self, image_path: str) -> OcrResult:
        self._start()
        assert self.proc is not None and self.proc.stdin is not None and self.proc.stdout is not None
        try:
            self.proc.stdin.write(json.dumps({"image_path": image_path}, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("External Manga OCR worker stopped without response.")
            data = json.loads(line)
            return OcrResult(
                ok=bool(data.get("ok")),
                engine="manga_ocr_external",
                lines=list(data.get("lines") or []),
                error=str(data.get("error") or ""),
                raw=data.get("raw", data),
            )
        except Exception as e:
            self.close()
            return OcrResult(ok=False, engine="manga_ocr_external", error=str(e), raw=None)


def _get_external_worker_client() -> _ExternalMangaOcrWorkerClient:
    global _EXTERNAL_WORKER_CLIENT
    if _EXTERNAL_WORKER_CLIENT is None:
        _EXTERNAL_WORKER_CLIENT = _ExternalMangaOcrWorkerClient()
    return _EXTERNAL_WORKER_CLIENT


def _close_external_worker() -> None:
    global _EXTERNAL_WORKER_CLIENT
    if _EXTERNAL_WORKER_CLIENT is not None:
        try:
            _EXTERNAL_WORKER_CLIENT.close()
        except Exception:
            pass
    _EXTERNAL_WORKER_CLIENT = None


atexit.register(_close_external_worker)


def _direct_model_cache_ready() -> bool:
    try:
        return manga_ocr_model_exists()
    except Exception:
        return False


def _post_process_manga_ocr_text(text: str) -> str:
    import re
    text = "".join(str(text or "").split())
    text = text.replace("…", "...")
    text = re.sub(r"['’`´]", "'", text)
    return text.strip()


class _DirectMangaOcr:
    """Direct Manga OCR loader for source/dev fallback.

    The packaged Local edition normally uses local_runtime/manga_ocr_worker.py.
    This fallback avoids older manga-ocr package loaders that call
    AutoFeatureExtractor and fail with current manga-ocr-base metadata.
    """

    def __init__(self):
        ensure_manga_ocr_local_cache_env()
        import torch
        from PIL import Image
        from transformers import AutoTokenizer, VisionEncoderDecoderModel, ViTImageProcessor
        try:
            from transformers.generation import GenerationMixin
        except Exception:
            GenerationMixin = object  # type: ignore

        class MangaOcrModel(VisionEncoderDecoderModel, GenerationMixin):  # type: ignore[misc, valid-type]
            pass

        self.torch = torch
        self.Image = Image
        local_only = _direct_model_cache_ready()
        self.processor = ViTImageProcessor.from_pretrained(MODEL_ID, local_files_only=local_only)
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, local_files_only=local_only)
        self.model = MangaOcrModel.from_pretrained(MODEL_ID, local_files_only=local_only)
        if torch.cuda.is_available():
            self.model.cuda()
        elif getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            self.model.to("mps")
        self.model.eval()

    def __call__(self, img_or_path):
        if isinstance(img_or_path, (str, Path)):
            img = self.Image.open(img_or_path)
        else:
            img = img_or_path
        img = img.convert("L").convert("RGB")
        pixel_values = self.processor(img, return_tensors="pt").pixel_values
        with self.torch.no_grad():
            out = self.model.generate(pixel_values.to(self.model.device), max_length=300)[0].cpu()
        text = self.tokenizer.decode(out, skip_special_tokens=True)
        return _post_process_manga_ocr_text(text)


def _get_engine():
    global _ENGINE
    if _ENGINE is None:
        # Heavy import/model load stays lazy so Lite/API workflows are not touched.
        _ENGINE = _DirectMangaOcr()
    return _ENGINE


def _write_temp_image(image_bgr: np.ndarray | None, image_path: str | None) -> tuple[str, bool]:
    if image_bgr is None:
        if not image_path:
            raise ValueError("Manga OCR 입력 이미지가 없습니다.")
        return image_path, False
    img = np.asarray(image_bgr)
    if img.size <= 0:
        raise ValueError("Manga OCR 입력 crop이 비어 있습니다.")
    fd, temp_path = tempfile.mkstemp(prefix="ysb_manga_ocr_", suffix=".png")
    os.close(fd)
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise ValueError("Manga OCR 임시 이미지 인코딩 실패")
    with open(temp_path, "wb") as f:
        f.write(buf.tobytes())
    return temp_path, True


class MangaOcrEngine:
    name = "manga_ocr"

    def __init__(self, language: str = "ja", device: str = "auto"):
        self.language = language or "ja"
        self.device = device or "auto"

    def run(self, request: OcrRequest) -> OcrResult:
        image_bgr = request.options.get("image_bgr") if isinstance(request.options, dict) else None
        image_path = request.image_path
        scale = float((request.options or {}).get("scale", 1.0) or 1.0)
        temp_path = ""
        should_delete = False
        try:
            img_for_ocr = image_bgr
            if img_for_ocr is not None and scale > 1.01:
                h, w = img_for_ocr.shape[:2]
                img_for_ocr = cv2.resize(
                    img_for_ocr,
                    (max(1, int(w * scale)), max(1, int(h * scale))),
                    interpolation=cv2.INTER_CUBIC,
                )
            temp_path, should_delete = _write_temp_image(img_for_ocr, image_path)

            if _should_use_external_worker():
                return _get_external_worker_client().run_image(temp_path)

            try:
                text = str(_get_engine()(temp_path) or "").strip()
            finally:
                pass
            if not text:
                return OcrResult(ok=True, engine=self.name, lines=[], raw=text)
            if img_for_ocr is not None:
                hh, ww = img_for_ocr.shape[:2]
            else:
                img = cv2.imdecode(np.fromfile(temp_path, np.uint8), cv2.IMREAD_COLOR)
                hh, ww = img.shape[:2] if img is not None else (1, 1)
            lines = [{
                "text": text,
                "confidence": 1.0,
                "points": [[0, 0], [int(ww), 0], [int(ww), int(hh)], [0, int(hh)]],
            }]
            return OcrResult(ok=True, engine=self.name, lines=lines, raw=text)
        except Exception as e:
            return OcrResult(ok=False, engine=self.name, error=str(e))
        finally:
            if should_delete and temp_path:
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
