# -*- coding: utf-8 -*-
"""Local Manga OCR adapter.

Manga OCR is a recognition-only OCR model for Japanese manga text.  It does
not return detection boxes, so YSB uses the Local text detector for
regions/masks and applies Manga OCR only to cropped text regions.

In source/dev mode, Manga OCR is loaded directly from the current .venv and uses
local_models/manga_ocr as the model cache.  In packaged Local builds, Manga OCR
runs through local_runtime/manga_ocr_worker.py so transformers/tokenizers do not
need to be frozen into the main EXE.
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
_EXTERNAL_WORKER_CLIENTS: dict[str, "_ExternalMangaOcrWorkerClient"] = {}

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


def _packaged_runtime_root() -> Path:
    return _app_root() / ("local_runtime_exe" if getattr(sys, "frozen", False) else "local_runtime")


def _runtime_manga_ocr_root() -> Path:
    return _packaged_runtime_root() / "manga_ocr"


def _managed_torch_runtime_python() -> Path | None:
    """Return the program-managed Torch CUDA runtime Python when installed.

    BAT/source and EXE builds now install CUDA runtimes into local_runtime_bat
    or local_runtime_exe from the UI. Manga OCR is Torch-backed, so it must
    share that Torch runtime instead of silently falling back to the main .venv.
    """
    candidates: list[Path] = []
    env_value = os.environ.get("YSB_TORCH_CUDA_PYTHON") or os.environ.get("YSB_LOCAL_PYTHON")
    if env_value:
        candidates.append(Path(env_value).expanduser())
    try:
        from ysb.editions.local.cuda_runtime_installer import runtime_python_path
        candidates.append(runtime_python_path("torch"))
    except Exception:
        pass
    root = _app_root()
    bases = [root / "local_runtime_exe"] if getattr(sys, "frozen", False) else [root / "local_runtime_bat", root / "local_runtime_exe"]
    for base in bases:
        if os.name == "nt":
            candidates.append(base / "torch_cuda_venv" / "Scripts" / "python.exe")
        else:
            candidates.append(base / "torch_cuda_venv" / "bin" / "python")
        candidates.append(base / "manga_ocr" / "python" / "python.exe")
        candidates.append(base / "paddle" / "python" / "python.exe")
        candidates.append(base / "bootstrap_python" / "python.exe")
        candidates.append(base / "torch_cuda" / "python" / "python.exe")
        candidates.append(base / "torch" / "python" / "python.exe")
    seen: set[str] = set()
    for candidate in candidates:
        try:
            key = str(candidate.resolve())
        except Exception:
            key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            return candidate
    return None


def _managed_torch_runtime_ready() -> bool:
    return _managed_torch_runtime_python() is not None






def _apply_managed_torch_runtime_env(env: dict[str, str]) -> dict[str, str]:
    try:
        from ysb.editions.local.cuda_runtime_installer import runtime_subprocess_env
        return runtime_subprocess_env("torch", env)
    except Exception:
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        return env

def manga_ocr_runtime_model_root() -> Path:
    return _runtime_manga_ocr_root() / "model_cache"


def manga_ocr_legacy_model_root() -> Path:
    return _app_root() / "local_models" / "manga_ocr"


def _manga_ocr_cache_ready(root: Path) -> bool:
    """True when a Manga OCR HF cache exists under *root*.

    The expected cache root is one of:
        local_runtime/manga_ocr/model_cache
        local_models/manga_ocr

    Both contain:
        huggingface/hub/models--kha-white--manga-ocr-base/...
    """
    try:
        model_dir = root / "huggingface" / "hub" / "models--kha-white--manga-ocr-base"
        if not model_dir.exists():
            return False
        snapshots = model_dir / "snapshots"
        if snapshots.exists() and any(snapshots.iterdir()):
            return True
        return any(model_dir.rglob("*.safetensors")) or any(model_dir.rglob("*.bin"))
    except Exception:
        return False


def _manga_ocr_candidate_model_roots() -> list[Path]:
    roots: list[Path] = []
    env_root = os.environ.get("YSB_MANGA_OCR_MODEL_ROOT")
    if env_root:
        roots.append(Path(env_root).expanduser())
    roots.append(manga_ocr_runtime_model_root())
    roots.append(manga_ocr_legacy_model_root())

    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        try:
            key = str(root.resolve())
        except Exception:
            key = str(root)
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def manga_ocr_model_root() -> Path:
    """Return the active Manga OCR model root.

    Priority:
    1. Explicit YSB_MANGA_OCR_MODEL_ROOT.
    2. Runtime-bundled cache when it actually contains the model.
    3. Shared local_models/manga_ocr cache when it actually contains the model.
    4. A writable default for first download/cache creation.

    This is intentionally more forgiving than the old layout.  If a user deletes
    local_runtime/manga_ocr/model_cache but keeps local_models/manga_ocr, Manga
    OCR should still work instead of trying to use the empty runtime cache.
    """
    candidates = _manga_ocr_candidate_model_roots()
    for root in candidates:
        if _manga_ocr_cache_ready(root):
            return root

    legacy_root = manga_ocr_legacy_model_root()
    # Prefer local_models for a new cache because it is easy for users to find,
    # replace, or delete without touching the worker runtime.  Runtime cache is
    # still used above when it actually contains a ready model.
    return legacy_root


def manga_ocr_hf_home() -> Path:
    return manga_ocr_model_root() / "huggingface"


def manga_ocr_hub_cache() -> Path:
    return manga_ocr_hf_home() / "hub"


def manga_ocr_transformers_cache() -> Path:
    return manga_ocr_hf_home() / "transformers"


def manga_ocr_model_exists() -> bool:
    """True when the selected Manga OCR Hugging Face cache is ready."""
    return _manga_ocr_cache_ready(manga_ocr_model_root())


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
    base = _packaged_runtime_root()
    preferred = base / "manga_ocr" / "manga_ocr_worker.py"
    if preferred.exists():
        return preferred
    return base / "manga_ocr_worker.py"


def _external_worker_python(device: str | None = None) -> Path | None:
    norm_device = _normalize_device(device)
    strict_cuda = norm_device == "cuda"
    explicit_cpu = norm_device == "cpu"

    # Auto/CUDA may use the program-managed Torch CUDA runtime.  Explicit CPU
    # must not: it should go straight to a CPU-safe runtime/direct loader.
    if not explicit_cpu:
        managed = _managed_torch_runtime_python()
        if managed is not None:
            return managed

    if strict_cuda:
        # Device=CUDA is strict.  Missing managed Torch runtime must fail instead
        # of falling back to .venv/current Python.  Environment overrides are
        # intentionally ignored in strict CUDA mode for the same reason.
        return None

    env_python = os.environ.get("YSB_MANGA_OCR_PYTHON")
    if env_python:
        candidate = Path(env_python).expanduser()
        if candidate.exists():
            return candidate

    root = _app_root()
    base = _packaged_runtime_root()
    if getattr(sys, "frozen", False):
        candidates = [
            base / "manga_ocr" / "python" / "python.exe",
            base / "python" / "python.exe",
        ]
    else:
        candidates = [
            base / "manga_ocr" / "python" / "python.exe",
            base / "manga_ocr_venv" / "Scripts" / "python.exe",
            base / "manga_ocr_venv" / "bin" / "python",
            base / "python" / "python.exe",
            base / "ocr_venv" / "Scripts" / "python.exe",
            base / "ocr_venv" / "bin" / "python",
            root / ".venv" / "Scripts" / "python.exe",
            root / ".venv" / "bin" / "python",
        ]
        candidates.append(Path(sys.executable))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _should_use_external_worker(device: str | None = None) -> bool:
    if os.environ.get("YSB_MANGA_OCR_INTERNAL", "").strip().lower() in ("1", "true", "yes"):
        return False
    norm_device = _normalize_device(device)
    worker_ready = _external_worker_file().exists() and _external_worker_python(device) is not None
    if norm_device == "cuda":
        return worker_ready
    if norm_device == "cpu":
        # Source/dev CPU mode should use the direct CPU loader unless the user
        # explicitly asks for the worker.  Packaged builds can still use a
        # CPU-safe bundled worker if present.
        if not getattr(sys, "frozen", False):
            forced = os.environ.get("YSB_MANGA_OCR_USE_WORKER", "").strip().lower()
            return worker_ready and forced in ("1", "true", "yes")
        return worker_ready
    # Auto is the only non-strict mode that may prefer managed CUDA when ready.
    if _managed_torch_runtime_ready():
        return worker_ready
    if not getattr(sys, "frozen", False):
        forced = os.environ.get("YSB_MANGA_OCR_USE_WORKER", "").strip().lower()
        if forced not in ("1", "true", "yes"):
            return False
    return worker_ready


class _ExternalMangaOcrWorkerClient:
    def __init__(self, device: str = "auto"):
        self.device = _normalize_device(device)
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
        python = _external_worker_python(self.device)
        if not worker.exists():
            raise RuntimeError(f"External Manga OCR worker not found: {worker}")
        if python is None:
            if _normalize_device(self.device) == "cuda":
                raise RuntimeError("Manga OCR CUDA 런타임을 찾을 수 없습니다. 설정 -> 로컬 CUDA 진단에서 Torch CUDA 런타임 설치/복구를 실행해 주세요.")
            raise RuntimeError("External Manga OCR Python runtime not found. 배포판은 local_runtime_exe/manga_ocr/python/python.exe, 소스 테스트는 .venv/현재 Python을 확인해 주세요.")

        env = os.environ.copy()
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env = _apply_managed_torch_runtime_env(env)
        ensure_manga_ocr_local_cache_env()
        model_root = manga_ocr_model_root()
        env["YSB_MANGA_OCR_MODEL_ROOT"] = str(model_root)
        env["HF_HOME"] = str(model_root / "huggingface")
        env["HF_HUB_CACHE"] = str(model_root / "huggingface" / "hub")
        env["TRANSFORMERS_CACHE"] = str(model_root / "huggingface" / "transformers")
        env["YSB_MANGA_OCR_DEVICE"] = self.device

        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_handle = open(self.log_path, "a", encoding="utf-8", errors="replace")
            self.log_handle.write("\n=== YSB External Manga OCR worker start ===\n")
            self.log_handle.write(f"python={python}\nworker={worker}\napp_root={_app_root()}\nmodel_root={manga_ocr_model_root()}\ndevice={self.device}\n")
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
            self.proc.stdin.write(json.dumps({"image_path": image_path, "device": self.device}, ensure_ascii=False) + "\n")
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


def _get_external_worker_client(device: str = "auto") -> _ExternalMangaOcrWorkerClient:
    key = _normalize_device(device)
    client = _EXTERNAL_WORKER_CLIENTS.get(key)
    if client is None:
        client = _ExternalMangaOcrWorkerClient(device=key)
        _EXTERNAL_WORKER_CLIENTS[key] = client
    return client


def _close_external_worker() -> None:
    global _EXTERNAL_WORKER_CLIENTS
    for client in list(_EXTERNAL_WORKER_CLIENTS.values()):
        try:
            client.close()
        except Exception:
            pass
    _EXTERNAL_WORKER_CLIENTS = {}


atexit.register(_close_external_worker)



def _normalize_device(value: str | None) -> str:
    v = str(value or "auto").strip().lower()
    if v in ("gpu", "cuda:0", "cuda"):
        return "cuda"
    if v in ("cpu", "mps"):
        return v
    return "auto"

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

    Source/test mode normally uses this direct loader.  Packaged Local builds use
    local_runtime/manga_ocr_worker.py instead.  This loader avoids older
    manga-ocr package code that calls
    AutoFeatureExtractor and fail with current manga-ocr-base metadata.
    """

    def __init__(self, device: str = "auto"):
        self.requested_device = _normalize_device(device)
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
        selected = self.requested_device
        if selected == "cuda":
            if not torch.cuda.is_available() or torch.cuda.device_count() <= 0:
                raise RuntimeError("Manga OCR CUDA를 사용할 수 없습니다. Torch CUDA 런타임/드라이버 상태를 확인해 주세요.")
            self.model.cuda()
        elif selected == "cpu":
            self.model.to("cpu")
        elif selected == "mps":
            if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
                self.model.to("mps")
            else:
                self.model.to("cpu")
        elif torch.cuda.is_available() and torch.cuda.device_count() > 0:
            self.model.cuda()
        elif getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            self.model.to("mps")
        else:
            self.model.to("cpu")
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


def _get_engine(device: str = "auto"):
    global _ENGINE
    key = _normalize_device(device)
    if not isinstance(_ENGINE, dict):
        _ENGINE = {}
    if key not in _ENGINE:
        # Heavy import/model load stays lazy so Lite/API workflows are not touched.
        _ENGINE[key] = _DirectMangaOcr(device=key)
    return _ENGINE[key]


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

            if _should_use_external_worker(self.device):
                return _get_external_worker_client(self.device).run_image(temp_path)

            if _normalize_device(self.device) == "cuda":
                raise RuntimeError("Manga OCR CUDA 런타임을 찾을 수 없습니다. 설정 -> 로컬 CUDA 진단에서 Torch CUDA 런타임 설치/복구를 실행해 주세요.")
            try:
                text = str(_get_engine(self.device)(temp_path) or "").strip()
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
