# -*- coding: utf-8 -*-
"""Local PaddleOCR adapter.

Heavy PaddleOCR/PaddlePaddle imports are intentionally lazy so Lite builds can
scan this package without pulling Local-only dependencies.
"""

from __future__ import annotations

import ast
import json
import atexit
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from ysb.utils.runtime_logger import append_log, exception_text, file_size, format_bytes, image_size, log_dir, memory_text

from .base import OcrRequest, OcrResult


_ENGINE_CACHE: dict[tuple[Any, ...], Any] = {}


_EXTERNAL_WORKER_CLIENTS: dict[tuple[str, str], "_ExternalPaddleWorkerClient"] = {}


def _hidden_worker_popen_kwargs() -> dict[str, Any]:
    """Return Windows-only Popen kwargs that keep the external OCR worker invisible.

    The Local edition starts PaddleOCR in a separate Python process.  On Windows,
    launching python.exe without these flags can briefly show a black console
    window.  Keep stdin/stdout pipes available, but do not show a console.
    """
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
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    try:
        return Path(__file__).resolve().parents[3]
    except Exception:
        return Path.cwd()


def _packaged_runtime_root() -> Path:
    return _app_root() / ("local_runtime_exe" if getattr(sys, "frozen", False) else "local_runtime")


def _external_worker_file() -> Path:
    base = _packaged_runtime_root()
    preferred = base / "paddle" / "paddle_ocr_worker.py"
    if preferred.exists():
        return preferred
    return base / "paddle_ocr_worker.py"


def _is_explicit_cuda_device(value: Any) -> bool:
    return _normalize_device(str(value or "auto")) == "gpu"


def _canonical_worker_device(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text.startswith("gpu") or text.startswith("cuda"):
        return "cuda"
    if text.startswith("cpu"):
        return "cpu"
    if text in ("error", "unavailable"):
        return text
    return "unknown"


def _resolved_from_device_info(info: dict[str, Any]) -> str:
    for key in ("resolved_device", "actual_device", "paddle_current_device"):
        value = info.get(key)
        resolved = _canonical_worker_device(value)
        if resolved not in ("unknown", ""):
            return resolved
    return "unknown"




def _apply_managed_paddle_runtime_env(env: dict[str, str]) -> dict[str, str]:
    try:
        from ysb.editions.local.cuda_runtime_installer import runtime_subprocess_env
        return runtime_subprocess_env("paddle", env)
    except Exception:
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        return env

def _external_worker_python(device: str | None = None) -> Path | None:
    root = _app_root()
    norm_device = _normalize_device(str(device or "auto"))
    strict_cuda = norm_device == "gpu"
    explicit_cpu = norm_device == "cpu"
    candidates: list[Path] = []

    # Explicit Device=CUDA is strict: only the program-managed Paddle GPU
    # runtime is allowed.  Never fall back to .venv/current Python, because
    # Paddle may silently print "Switching to CPU instead" and still return a
    # successful OCR result.
    if strict_cuda or norm_device == "auto":
        try:
            from ysb.editions.local.cuda_runtime_installer import runtime_python_path
            managed_gpu = runtime_python_path("paddle")
            if managed_gpu.exists():
                candidates.append(managed_gpu)
        except Exception:
            pass
    if strict_cuda:
        return candidates[0] if candidates else None

    # Explicit Device=CPU must be a direct CPU path.  Do not probe or reuse the
    # managed Paddle GPU venv, and do not honor the GPU-specific override.
    # Auto is the only mode that may prefer the managed CUDA runtime above.
    env_keys = ("YSB_PADDLEOCR_PYTHON",) if explicit_cpu else ("YSB_PADDLEOCR_PYTHON", "YSB_PADDLE_GPU_PYTHON")
    for key_name in env_keys:
        env_python = os.environ.get(key_name)
        if env_python:
            candidate = Path(env_python).expanduser()
            if candidate.exists():
                candidates.append(candidate)

    base = _packaged_runtime_root()
    if getattr(sys, "frozen", False):
        candidates.extend([
            base / "paddle" / "python" / "python.exe",
            base / "python" / "python.exe",
        ])
    else:
        candidates.extend([
            base / "paddle" / "python" / "python.exe",
            base / "python" / "python.exe",
            base / "paddle_ocr_venv" / "Scripts" / "python.exe",
            base / "paddle_ocr_venv" / "bin" / "python",
            base / "ocr_venv" / "Scripts" / "python.exe",
            base / "ocr_venv" / "bin" / "python",
            root / ".venv" / "Scripts" / "python.exe",
            root / ".venv" / "bin" / "python",
        ])
        candidates.append(Path(sys.executable))
    seen: set[str] = set()
    for candidate in candidates:
        try:
            key = str(candidate.resolve()).lower()
        except Exception:
            key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            return candidate
    return None


def _should_use_external_worker(device: str | None = None) -> bool:
    if os.environ.get("YSB_PADDLEOCR_INTERNAL", "").strip().lower() in ("1", "true", "yes"):
        return False
    return _external_worker_file().exists() and _external_worker_python(device) is not None


class _ExternalPaddleWorkerClient:
    """Persistent JSON-line client for local_runtime/paddle_ocr_worker.py."""

    def __init__(self, language: str, device: str):
        self.language = language
        self.device = device
        self.proc: subprocess.Popen[str] | None = None
        self.log_handle = None
        try:
            self.log_path = log_dir() / "ysb_paddle_ocr_worker.log"
        except Exception:
            self.log_path = _app_root() / "ysb_paddle_ocr_worker.log"

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
            raise RuntimeError(f"External PaddleOCR worker not found: {worker}")
        if python is None:
            if _is_explicit_cuda_device(self.device):
                raise RuntimeError("PaddleOCR CUDA 런타임을 찾을 수 없습니다. 설정 -> 로컬 CUDA 진단에서 Paddle GPU 런타임 설치/복구를 실행해 주세요.")
            raise RuntimeError("External PaddleOCR Python runtime not found. local_runtime_exe/paddle/python/python.exe를 확인해 주세요.")

        env = os.environ.copy()
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env = _apply_managed_paddle_runtime_env(env)
        env.setdefault("FLAGS_use_mkldnn", "0")
        env.setdefault("FLAGS_use_onednn", "0")
        model_dir = _app_root() / "local_models" / "paddleocr"
        if model_dir.exists():
            env.setdefault("YSB_PADDLEOCR_MODEL_DIR", str(model_dir))

        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_handle = open(self.log_path, "a", encoding="utf-8", errors="replace")
            self.log_handle.write("\n=== YSB External PaddleOCR worker start ===\n")
            self.log_handle.write(f"python={python}\nworker={worker}\napp_root={_app_root()}\n")
            self.log_handle.flush()
            append_log(self.log_path, "PADDLE EXTERNAL WORKER START", python=python, worker=worker, app_root=_app_root(), memory=memory_text())
        except Exception:
            self.log_handle = subprocess.DEVNULL  # type: ignore[assignment]

        popen_kwargs = _hidden_worker_popen_kwargs()
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
            **popen_kwargs,
        )
        if self.proc.stdout is None:
            raise RuntimeError("External PaddleOCR worker stdout pipe was not created.")
        ready_line = self.proc.stdout.readline().strip()
        try:
            ready = json.loads(ready_line)
        except Exception:
            ready = {}
        append_log(self.log_path, "PADDLE EXTERNAL WORKER READY", ready=ready, memory=memory_text())
        if not ready.get("ready"):
            raise RuntimeError(f"External PaddleOCR worker did not become ready: {ready_line}")

    def run_image(self, image_path: str, options: dict[str, Any] | None = None) -> OcrResult:
        self._start()
        assert self.proc is not None and self.proc.stdin is not None and self.proc.stdout is not None
        img_size = image_size(image_path)
        use_layout_detection = (options or {}).get("use_layout_detection", True) if options else True
        append_log(
            self.log_path,
            "PADDLE OCR REQUEST",
            image_path=image_path,
            file_size=format_bytes(file_size(image_path)),
            image_size=(f"{img_size[0]}x{img_size[1]}" if img_size else "unknown"),
            language=self.language,
            device=self.device,
            use_layout_detection=use_layout_detection,
            memory=memory_text(),
        )
        req = {
            "image_path": image_path,
            "language": self.language,
            "device": self.device,
            "use_layout_detection": use_layout_detection,
        }
        try:
            self.proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("External PaddleOCR worker stopped without response.")
            data = json.loads(line)
            device_info = dict(data.get("device_info") or {})
            requested = str(device_info.get("requested_device") or _normalize_device(self.device))
            resolved = _resolved_from_device_info(device_info)
            err_text = str(data.get("error") or "")
            if _is_explicit_cuda_device(self.device) and resolved != "cuda":
                if resolved == "unknown":
                    err_text = err_text or (
                        "PaddleOCR CUDA 실행 장치 확인값이 비어 있습니다 "
                        f"(worker_python={device_info.get('worker_python') or 'unknown'}, "
                        f"paddle_current_device={device_info.get('paddle_current_device') or 'unknown'}). "
                        "Paddle worker가 최신 패치인지 확인하고 프로그램을 완전히 재시작하세요."
                    )
                else:
                    err_text = err_text or (
                        "PaddleOCR CUDA를 요청했지만 실제 실행 장치가 CUDA가 아닙니다 "
                        f"(resolved={resolved}). Paddle GPU 런타임 설치/복구가 필요합니다."
                    )
                data["ok"] = False
                data["error"] = err_text
            append_log(
                self.log_path,
                "PADDLE OCR RESPONSE",
                ok=bool(data.get("ok")),
                line_count=len(data.get("lines") or []),
                error=err_text,
                requested_device=requested,
                resolved_device=resolved,
                actual_device=str(device_info.get("actual_device") or ""),
                paddle_current_device=str(device_info.get("paddle_current_device") or ""),
                worker_python=str(device_info.get("worker_python") or ""),
                fallback_reason=str(device_info.get("fallback_reason") or ""),
                memory=memory_text(),
            )
            return OcrResult(
                ok=bool(data.get("ok")),
                engine="paddleocr_external",
                lines=list(data.get("lines") or []),
                error=err_text,
                raw=data,
            )
        except Exception as e:
            append_log(self.log_path, "PADDLE OCR EXCEPTION", error=repr(e), traceback=exception_text(e), memory=memory_text())
            self.close()
            return OcrResult(ok=False, engine="paddleocr_external", error=str(e), raw=None)


def _get_external_worker_client(language: str, device: str) -> _ExternalPaddleWorkerClient:
    key = (_normalize_lang(language), _normalize_device(device))
    client = _EXTERNAL_WORKER_CLIENTS.get(key)
    if client is None:
        client = _ExternalPaddleWorkerClient(language=language, device=device)
        _EXTERNAL_WORKER_CLIENTS[key] = client
    return client


def _close_external_workers() -> None:
    for client in list(_EXTERNAL_WORKER_CLIENTS.values()):
        try:
            client.close()
        except Exception:
            pass


atexit.register(_close_external_workers)


def _normalize_lang(language: str) -> str:
    """Map YSB language codes to PaddleOCR language names."""
    lang = str(language or "ja").strip().lower()
    aliases = {
        "ja": "japan",
        "jp": "japan",
        "jpn": "japan",
        "japanese": "japan",
        "일본어": "japan",
        "en": "en",
        "eng": "en",
        "english": "en",
        "영어": "en",
        "ko": "korean",
        "kr": "korean",
        "kor": "korean",
        "korean": "korean",
        "한국어": "korean",
        "zh": "ch",
        "cn": "ch",
        "ch": "ch",
        "chi": "ch",
        "zho": "ch",
        "chinese": "ch",
        "zh-cn": "ch",
        "중국어": "ch",
    }
    return aliases.get(lang, lang or "japan")


def _normalize_device(device: str) -> str:
    dev = str(device or "auto").strip().lower()
    if dev in ("cuda", "gpu", "nvidia", "auto"):
        return "gpu"
    if dev in ("cpu",):
        return "cpu"
    return "gpu"


def _is_model_dir(path: Path) -> bool:
    """Return True when the folder looks like a Paddle/PaddleX inference model."""
    try:
        if not path.exists() or not path.is_dir():
            return False
        markers = (
            "inference.yml",
            "inference.json",
            "model.pdmodel",
            "model.pdiparams",
            "inference.pdmodel",
            "inference.pdiparams",
        )
        if any((path / name).exists() for name in markers):
            return True
        # PaddleX official model folders can contain nested inference files.
        for child in path.iterdir():
            if child.is_file() and child.suffix.lower() in (".pdmodel", ".pdiparams", ".json", ".yml", ".yaml"):
                return True
        return any(path.iterdir())
    except Exception:
        return False


def _local_model_roots() -> list[Path]:
    """Candidate folders for user-managed PaddleOCR local model files.

    Supported layouts:
      local_models/PP-OCRv5_server_det/
      local_models/PP-OCRv5_server_rec/
      local_models/PP-LCNet_x1_0_textline_ori/

      local_models/paddleocr/PP-OCRv5_server_det/
      local_models/paddleocr/PP-OCRv5_server_rec/
      local_models/paddleocr/PP-LCNet_x1_0_textline_ori/
    """
    candidates: list[Path] = []
    env_root = os.environ.get("YSB_PADDLEOCR_MODEL_DIR") or os.environ.get("YSB_LOCAL_MODEL_DIR")
    if env_root:
        candidates.append(Path(env_root).expanduser())

    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent)
    try:
        candidates.append(Path(__file__).resolve().parents[3])
    except Exception:
        pass
    candidates.append(Path.cwd())

    roots: list[Path] = []
    seen: set[str] = set()
    for base in candidates:
        for root in (base / "local_models" / "paddleocr_vl", base / "local_models" / "paddleocr", base / "local_models"):
            try:
                key = str(root.resolve()).lower()
            except Exception:
                key = str(root).lower()
            if key not in seen:
                seen.add(key)
                roots.append(root)

    # Last-resort: PaddleX automatic cache.  Prefer project local_models when present.
    cache_root = Path.home() / ".paddlex" / "official_models"
    try:
        key = str(cache_root.resolve()).lower()
    except Exception:
        key = str(cache_root).lower()
    if key not in seen:
        roots.append(cache_root)
    return roots


def _find_named_model(names: tuple[str, ...]) -> Path | None:
    for root in _local_model_roots():
        for name in names:
            for candidate in (root / name, root / f"{name}_infer"):
                if _is_model_dir(candidate):
                    return candidate
    return None


def _discover_paddle_model_dirs() -> dict[str, str]:
    """Find user-managed PaddleOCR model folders and map them to PaddleOCR kwargs.

    The current Local pipeline already uses comic_text_detector for the primary
    text area/mask detection, but PaddleOCR 3.x still initializes its own OCR
    pipeline.  Pointing it to local model folders prevents first-run downloads
    and keeps Local builds reproducible.
    """
    textline = _find_named_model((
        "PP-LCNet_x1_0_textline_ori",
        "PP-LCNet_x1_0_doc_ori",
    ))
    det = _find_named_model((
        "PP-OCRv5_server_det",
        "PP-OCRv5_mobile_det",
        "PP-OCRv4_server_det",
        "PP-OCRv4_mobile_det",
    ))
    rec = _find_named_model((
        "PP-OCRv5_server_rec",
        "PP-OCRv5_mobile_rec",
        "japan_PP-OCRv3_mobile_rec",
        "PP-OCRv4_server_rec",
        "PP-OCRv4_mobile_rec",
    ))

    dirs: dict[str, str] = {}
    if textline:
        dirs["textline_orientation_model_dir"] = str(textline)
        dirs["cls_model_dir"] = str(textline)
    if det:
        dirs["text_detection_model_dir"] = str(det)
        dirs["det_model_dir"] = str(det)
    if rec:
        dirs["text_recognition_model_dir"] = str(rec)
        dirs["rec_model_dir"] = str(rec)
    return dirs


def _log_local_model_dirs(model_dirs: dict[str, str]) -> None:
    if not model_dirs:
        print(">>> [Local OCR] PaddleOCR local_models not found; using PaddleOCR cache/auto-download.")
        return
    shown = []
    for key in ("textline_orientation_model_dir", "text_detection_model_dir", "text_recognition_model_dir"):
        val = model_dirs.get(key)
        if val:
            shown.append(f"{key}={val}")
    if shown:
        print(">>> [Local OCR] PaddleOCR local model dirs: " + " | ".join(shown))


def _as_points(value: Any) -> list[list[int]]:
    """Convert PaddleOCR polygon/box values into [[x,y]...] points."""
    if value is None:
        return []
    if isinstance(value, str):
        s = value.strip()
        try:
            value = ast.literal_eval(s)
        except Exception:
            nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", s)]
            if len(nums) >= 8:
                value = [[nums[i], nums[i + 1]] for i in range(0, min(len(nums), 8), 2)]
            elif len(nums) >= 4:
                x1, y1, x2, y2 = nums[:4]
                value = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
            else:
                return []
    try:
        arr = np.asarray(value, dtype=np.float32)
        if arr.ndim == 1 and arr.size >= 4:
            # rec_boxes: x1,y1,x2,y2
            x1, y1, x2, y2 = arr[:4].tolist()
            arr = np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=np.float32)
        elif arr.ndim >= 3:
            arr = arr.reshape((-1, 2))
        elif arr.ndim == 2 and arr.shape[1] >= 2:
            arr = arr[:, :2]
        else:
            return []
        pts = []
        for x, y in arr[:16]:
            pts.append([int(round(float(x))), int(round(float(y)))])
        return pts if len(pts) >= 3 else []
    except Exception:
        return []


def _result_obj_to_dict(obj: Any) -> dict[str, Any]:
    """Convert PaddleOCR 2.x/3.x result objects into a plain dict.

    Frozen builds can expose PaddleOCR result objects slightly differently from
    source runs.  In particular, some PaddleOCR 3.x result objects return JSON
    as a string from json()/to_json(), while others expose the payload under
    .res/.data/.result.  Keep this parser permissive so the OCR text does not
    disappear just because the wrapper shape changed.
    """
    if isinstance(obj, dict):
        if isinstance(obj.get("res"), dict):
            return obj["res"]
        return obj
    if isinstance(obj, str):
        try:
            val = json.loads(obj)
            if isinstance(val, dict):
                if isinstance(val.get("res"), dict):
                    return val["res"]
                return val
        except Exception:
            return {}
    for attr in ("res", "data", "result"):
        try:
            val = getattr(obj, attr)
            if isinstance(val, dict):
                if isinstance(val.get("res"), dict):
                    return val["res"]
                return val
            if isinstance(val, str):
                parsed = _result_obj_to_dict(val)
                if parsed:
                    return parsed
        except Exception:
            pass
    for meth in ("to_dict", "json", "to_json"):
        try:
            fn = getattr(obj, meth)
            val = fn() if callable(fn) else fn
            if isinstance(val, dict):
                # PaddleOCR 3.x json() sometimes wraps result under "res".
                if isinstance(val.get("res"), dict):
                    return val["res"]
                return val
            if isinstance(val, str):
                parsed = _result_obj_to_dict(val)
                if parsed:
                    return parsed
        except Exception:
            pass
    return {}


def _first_present(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Return the first existing/non-None value without boolean-testing numpy arrays.

    PaddleOCR 3.x result dictionaries often contain numpy arrays.  Using
    ``a or b`` on those arrays raises: "truth value of an array is ambiguous".
    """
    if not isinstance(data, dict):
        return default
    for key in keys:
        if key in data:
            val = data.get(key)
            if val is not None:
                return val
    return default


def _safe_len(value: Any) -> int:
    try:
        return len(value) if value is not None else 0
    except Exception:
        return 0


def _safe_get_seq(value: Any, index: int, default: Any = None) -> Any:
    try:
        if value is None:
            return default
        if index < len(value):
            return value[index]
    except Exception:
        return default
    return default


def _find_paddleocr_paths() -> tuple[str, str]:
    from pathlib import Path
    app_root = _app_root()
    candidates = [
        app_root / "local_models",
        Path.cwd() / "local_models"
    ]
    local_models_dir = None
    for c in candidates:
        if c.exists() and c.is_dir():
            local_models_dir = c
            break
    if local_models_dir is None:
        local_models_dir = Path("local_models")

    paddle_dir = None
    if local_models_dir.exists():
        for item in local_models_dir.iterdir():
            if item.is_dir() and item.name.lower() == "paddleocr-vl":
                paddle_dir = item
                break

    if paddle_dir is None:
        paddle_dir = local_models_dir / "PaddleOCR-VL"

    layout_dir = None
    if paddle_dir.exists():
        doc_layout = paddle_dir / "PP-DocLayoutV2"
        if doc_layout.exists() and doc_layout.is_dir():
            layout_dir = doc_layout
        else:
            for item in paddle_dir.iterdir():
                if item.is_dir():
                    if item.name.lower() == "layout":
                        layout_dir = item
                        break
                    try:
                        if any(f.suffix == ".pdmodel" for f in item.iterdir() if f.is_file()):
                            layout_dir = item
                            break
                    except Exception:
                        pass

    if layout_dir is None:
        layout_dir = paddle_dir / "PP-DocLayoutV2"

    return str(layout_dir.resolve()), str(paddle_dir.resolve())


class PaddleOcrEngine:
    name = "paddleocr"

    def __init__(self, language: str = "ja", device: str = "auto"):
        self.language = language
        self.device = device

    def _build_engine(self):
        # RTX 4080 성능 활용을 위한 전용 가속 옵션 추가
        os.environ["FLAGS_allocator_strategy"] = "auto_growth"
        os.environ.setdefault("FLAGS_use_mkldnn", "0")
        os.environ.setdefault("FLAGS_use_onednn", "0")

        lang = _normalize_lang(self.language)
        device = _normalize_device(self.device)

        cache_key = (lang, device)
        if cache_key in _ENGINE_CACHE:
            return _ENGINE_CACHE[cache_key]

        try:
            import torch
        except ImportError:
            pass

        from paddleocr import PaddleOCRVL

        layout_dir, rec_dir = _find_paddleocr_paths()

        try:
            engine = PaddleOCRVL(
                pipeline_version="v1",
                device=device,
                layout_detection_model_dir=layout_dir,
                vl_rec_model_dir=rec_dir
            )
            _ENGINE_CACHE[cache_key] = engine
            return engine
        except Exception as e:
            raise RuntimeError(f"PaddleOCR-VL 초기화 실패: {e}")

    def _write_temp_image(self, image_bgr: np.ndarray | None, image_path: str | None) -> tuple[str, bool]:
        if image_bgr is None:
            if not image_path:
                raise ValueError("PaddleOCR 입력 이미지가 없습니다.")
            return image_path, False
        img = np.asarray(image_bgr)
        if img.size <= 0:
            raise ValueError("PaddleOCR 입력 crop이 비어 있습니다.")
        fd, temp_path = tempfile.mkstemp(prefix="ysb_paddle_", suffix=".png")
        os.close(fd)
        ok, buf = cv2.imencode(".png", img)
        if not ok:
            raise ValueError("PaddleOCR 임시 이미지 인코딩 실패")
        with open(temp_path, "wb") as f:
            f.write(buf.tobytes())
        return temp_path, True

    def _parse_old_ocr_result(self, result: Any) -> list[dict[str, Any]]:
        lines: list[dict[str, Any]] = []
        if result is None:
            return lines
        # Old API usually returns: [[ [box, (text, score)], ... ]]
        pages = result if isinstance(result, list) else [result]
        if len(pages) == 1 and isinstance(pages[0], list):
            candidate = pages[0]
        else:
            candidate = pages
        # If the first element is a page list, flatten one more level.
        if candidate and isinstance(candidate[0], list) and candidate[0] and isinstance(candidate[0][0], (list, tuple, np.ndarray)) and len(candidate[0]) != 2:
            flat = []
            for page in candidate:
                if isinstance(page, list):
                    flat.extend(page)
            candidate = flat
        for row in candidate or []:
            try:
                if not isinstance(row, (list, tuple)) or len(row) < 2:
                    continue
                pts = _as_points(row[0])
                text = ""
                score = 0.0
                rec = row[1]
                if isinstance(rec, (list, tuple)) and rec:
                    text = str(rec[0] or "").strip()
                    if len(rec) > 1:
                        score = float(rec[1] or 0.0)
                else:
                    text = str(rec or "").strip()
                if text and pts:
                    lines.append({"text": text, "confidence": score, "points": pts})
            except Exception:
                continue
        return lines

    def _parse_predict_result(self, result: Any) -> list[dict[str, Any]]:
        lines: list[dict[str, Any]] = []
        for obj in (result if isinstance(result, list) else [result]):
            data = _result_obj_to_dict(obj)
            if not data:
                continue
            
            # VLM 파싱 결과 지원
            parsing_res_list = data.get("parsing_res_list")
            if isinstance(parsing_res_list, list):
                for block in parsing_res_list:
                    if block is None:
                        continue
                    if not isinstance(block, dict):
                        text = str(getattr(block, "content", "") or "").strip()
                        if not text:
                            text = str(getattr(block, "block_content", "") or "").strip()
                        if not text:
                            continue
                        score = float(getattr(block, "confidence", 1.0) or 1.0)
                        bbox = getattr(block, "bbox", None)
                        if bbox is None:
                            bbox = getattr(block, "block_bbox", None)
                    else:
                        text = str(block.get("block_content") or block.get("content") or "").strip()
                        if not text:
                            continue
                        score = float(block.get("confidence", 1.0) or 1.0)
                        bbox = block.get("block_bbox") or block.get("bbox")
                    
                    pts = _as_points(bbox)
                    if text and pts:
                        lines.append({"text": text, "confidence": score, "points": pts})
                continue

            # Do not use ``a or b`` here. PaddleOCR 3.x stores many values as
            # numpy arrays, and boolean-testing an array raises an ambiguity error.
            texts = _first_present(data, "rec_texts", "texts", default=[])
            scores = _first_present(data, "rec_scores", "scores", default=[])
            polys = _first_present(data, "rec_polys", "dt_polys", "polys", default=[])
            boxes = _first_present(data, "rec_boxes", "boxes", default=[])
            max_len = max(_safe_len(texts), _safe_len(polys), _safe_len(boxes))
            for i in range(max_len):
                try:
                    text = str(_safe_get_seq(texts, i, "") or "").strip()
                    if not text:
                        continue
                    score_raw = _safe_get_seq(scores, i, 0.0)
                    try:
                        score = float(score_raw if score_raw is not None else 0.0)
                    except Exception:
                        score = 0.0
                    pts = _as_points(_safe_get_seq(polys, i, None))
                    if not pts:
                        pts = _as_points(_safe_get_seq(boxes, i, None))
                    if text and pts:
                        lines.append({"text": text, "confidence": score, "points": pts})
                except Exception:
                    continue
        return lines

    def run(self, request: OcrRequest) -> OcrResult:
        image_bgr = request.options.get("image_bgr") if isinstance(request.options, dict) else None
        image_path = request.image_path
        lang = request.language or self.language
        device = (request.options or {}).get("device", self.device)
        scale = float((request.options or {}).get("scale", 1.0) or 1.0)

        try:
            img_for_ocr = image_bgr
            if img_for_ocr is not None and scale > 1.01:
                h, w = img_for_ocr.shape[:2]
                img_for_ocr = cv2.resize(img_for_ocr, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_CUBIC)

            temp_path, should_delete = self._write_temp_image(img_for_ocr, image_path)
            try:
                if _should_use_external_worker(device):
                    res = _get_external_worker_client(lang, device).run_image(temp_path, options=request.options)
                    if scale > 1.01 and res.lines:
                        inv = 1.0 / scale
                        for line in res.lines:
                            line["points"] = [[int(round(x * inv)), int(round(y * inv))] for x, y in line.get("points", [])]
                    return res

                if _is_explicit_cuda_device(device):
                    raise RuntimeError("PaddleOCR CUDA 런타임을 찾을 수 없습니다. 설정 -> 로컬 CUDA 진단에서 Paddle GPU 런타임 설치/복구를 실행해 주세요.")

                engine = PaddleOcrEngine(language=lang, device=device)._build_engine()
                lines: list[dict[str, Any]] = []
                # PaddleOCR 3.x
                if hasattr(engine, "predict"):
                    try:
                        result = engine.predict(input=temp_path, use_layout_detection=use_layout_detection)
                    except TypeError:
                        result = engine.predict(temp_path, use_layout_detection=use_layout_detection)
                    lines = self._parse_predict_result(result)
                # PaddleOCR 2.x fallback
                if not lines and hasattr(engine, "ocr"):
                    try:
                        result = engine.ocr(temp_path, cls=True)
                    except TypeError:
                        result = engine.ocr(temp_path)
                    lines = self._parse_old_ocr_result(result)

                if scale > 1.01 and lines:
                    inv = 1.0 / scale
                    for line in lines:
                        line["points"] = [[int(round(x * inv)), int(round(y * inv))] for x, y in line.get("points", [])]
                return OcrResult(ok=True, engine=self.name, lines=lines, raw=None)
            finally:
                if should_delete:
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
        except Exception as e:
            return OcrResult(ok=False, engine=self.name, error=str(e), raw=None)
