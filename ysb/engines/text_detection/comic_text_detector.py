# -*- coding: utf-8 -*-
"""comic_text_detector adapter for YSB Tool Local.

The vendored detector is intentionally loaded lazily so Lite builds can import
YSB common modules without requiring torch/comic_text_detector dependencies.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import os
import sys
from typing import Any

from .base import (
    TextDetectionBlock,
    TextDetectionLine,
    TextDetectionRequest,
    TextDetectionResult,
)
from ysb.editions.current import is_local_edition
from ysb.editions.local.comic_model_manager import (
    default_comic_detector_model_path,
    default_comic_detector_vendor_dir,
)


_DLL_DIRECTORY_HANDLES: list[Any] = []


def _activate_managed_torch_runtime_path() -> None:
    """Let the frozen EXE import Torch packages installed by pip --target.

    comic_text_detector runs inside the main process, unlike Paddle/Manga OCR
    workers. In frozen EXE mode the managed Torch runtime lives outside the
    PyInstaller bundle, so it must be added to sys.path before import torch.
    """
    try:
        from ysb.editions.local.cuda_runtime_installer import runtime_env_folder
        target = runtime_env_folder("torch")
    except Exception:
        return
    try:
        if target.exists():
            target_text = str(target)
            if target_text not in sys.path:
                sys.path.insert(0, target_text)
            if os.name == "nt" and hasattr(os, "add_dll_directory"):
                for dll_dir in (target, target / "torch" / "lib"):
                    try:
                        if dll_dir.exists():
                            handle = os.add_dll_directory(str(dll_dir))
                            _DLL_DIRECTORY_HANDLES.append(handle)
                    except Exception:
                        pass
    except Exception:
        pass


def _install_numpy_compat_aliases() -> None:
    """Install tiny compatibility aliases for vendored comic_text_detector.

    Some older detector utilities still refer to NumPy 1.x aliases that were
    removed in NumPy 2.x.  Keeping this shim here prevents Local OCR from
    crashing before the actual mask quality can be tested.
    """
    try:
        import numpy as np
        if not hasattr(np, "bool8"):
            np.bool8 = np.bool_  # type: ignore[attr-defined]
        if not hasattr(np, "float_"):
            np.float_ = np.float64  # type: ignore[attr-defined]
        if not hasattr(np, "int0"):
            np.int0 = np.intp  # type: ignore[attr-defined]
    except Exception:
        pass



def _normalize_torch_device(torch_module: Any, device: str) -> str:
    """Return a safe device string and enforce explicit CUDA strictly.

    Policy:
    - CUDA: CUDA-only.  Fail if the visible Torch runtime cannot use CUDA.
    - CPU: CPU-only.
    - Auto: CPU-safe default, but use CUDA first when the active Torch runtime
      actually recognizes a CUDA device.
    """
    dev = str(device or "auto").strip().lower()
    cuda_api = getattr(torch_module, "cuda", None)
    available = bool(cuda_api is not None and cuda_api.is_available())
    try:
        count = int(cuda_api.device_count() or 0) if cuda_api is not None else 0
    except Exception:
        count = 0
    if dev in ("cuda", "gpu", "nvidia"):
        if available and count > 0:
            return "cuda"
        raise RuntimeError(
            "comic_text_detector CUDA를 사용할 수 없습니다. "
            f"Torch CUDA 상태: cuda_available={available}, device_count={count}. "
            "설정 -> 로컬 CUDA 진단에서 런타임 설치/복구를 진행해 주세요."
        )
    if dev == "cpu":
        return "cpu"
    if available and count > 0:
        return "cuda"
    return "cpu"


def _infer_torch_module_device(obj: Any, *, max_depth: int = 3) -> str:
    """Best-effort model device inference for vendored detector objects."""
    seen: set[int] = set()

    def _walk(value: Any, depth: int) -> str:
        if value is None or depth < 0:
            return ""
        ident = id(value)
        if ident in seen:
            return ""
        seen.add(ident)
        try:
            params = getattr(value, "parameters", None)
            if callable(params):
                for param in params():
                    try:
                        return str(getattr(param, "device", "") or "")
                    except Exception:
                        continue
        except Exception:
            pass
        for attr in ("model", "net", "detector", "module", "text_detector", "textdetector", "unet", "dbnet"):
            try:
                got = getattr(value, attr, None)
            except Exception:
                got = None
            found = _walk(got, depth - 1)
            if found:
                return found
        return ""

    return _walk(obj, max_depth) or "unknown"


def _torch_device_report(torch_module: Any, *, requested: str, resolved: str, detector: Any = None) -> dict[str, Any]:
    cuda_api = getattr(torch_module, "cuda", None)
    try:
        cuda_available = bool(cuda_api is not None and cuda_api.is_available())
    except Exception:
        cuda_available = False
    try:
        cuda_device_count = int(cuda_api.device_count() or 0) if cuda_api is not None else 0
    except Exception:
        cuda_device_count = 0
    cuda_device_name = ""
    if cuda_available and cuda_device_count > 0:
        try:
            cuda_device_name = str(cuda_api.get_device_name(0) or "")
        except Exception:
            cuda_device_name = ""
    try:
        current_device = int(cuda_api.current_device()) if cuda_available and cuda_device_count > 0 else -1
    except Exception:
        current_device = -1
    model_device = _infer_torch_module_device(detector) if detector is not None else "unknown"
    if model_device == "unknown" and str(resolved).startswith("cuda"):
        model_device = "cuda"
    elif model_device == "unknown" and str(resolved) == "cpu":
        model_device = "cpu"
    return {
        "engine": "comic_text_detector",
        "requested_device": str(requested or "auto"),
        "resolved_device": str(resolved or "unknown"),
        "actual_device": "cuda" if str(resolved).startswith("cuda") else ("cpu" if str(resolved) == "cpu" else "unknown"),
        "model_device": model_device,
        "torch_cuda_available": cuda_available,
        "torch_cuda_device_count": cuda_device_count,
        "torch_cuda_device_name": cuda_device_name,
        "torch_cuda_current_device": current_device,
        "torch_version": str(getattr(torch_module, "__version__", "") or ""),
        "torch_cuda_build": str(getattr(getattr(torch_module, "version", None), "cuda", "") or ""),
        "pid": os.getpid(),
        "python_executable": sys.executable,
    }


@contextmanager
def _torch_load_map_location(device: str):
    """Temporarily make vendor torch.load() safe on CPU-only machines."""
    import torch

    original_load = torch.load
    target = "cuda" if str(device).lower().startswith("cuda") and torch.cuda.is_available() else "cpu"
    target_device = torch.device(target)

    def _safe_load(*args, **kwargs):
        # In CPU mode, override any missing/unsafe vendor map_location.
        # This prevents CUDA-saved checkpoints from crashing on CPU-only PCs.
        if target == "cpu":
            kwargs["map_location"] = target_device
        else:
            kwargs.setdefault("map_location", target_device)
        return original_load(*args, **kwargs)

    torch.load = _safe_load  # type: ignore[assignment]
    try:
        yield
    finally:
        torch.load = original_load  # type: ignore[assignment]


class ComicTextDetectorEngine:
    name = "comic_text_detector"

    def __init__(self, *, model_path: str | None = None, vendor_dir: str | None = None) -> None:
        self.model_path = Path(model_path) if model_path else default_comic_detector_model_path()
        self.vendor_dir = Path(vendor_dir) if vendor_dir else default_comic_detector_vendor_dir()
        self._detector: Any = None
        self._device: str | None = None
        self._input_size: int | None = None
        self._last_device_report: dict[str, Any] = {}

    def available(self) -> tuple[bool, str]:
        if not is_local_edition():
            return False, "comic_text_detector is Local edition only."
        if not self.vendor_dir.exists():
            return False, f"comic_text_detector vendor folder not found: {self.vendor_dir}"
        if not self.model_path.exists():
            return False, f"comic_text_detector model not found: {self.model_path}"
        try:
            _activate_managed_torch_runtime_path()
            import importlib.util
            for mod in ("torch", "cv2", "numpy", "pyclipper", "shapely"):
                if importlib.util.find_spec(mod) is None:
                    return False, f"Required Local dependency is not installed: {mod}"
        except Exception as exc:
            return False, str(exc)
        return True, ""

    @contextmanager
    def _vendor_import_path(self):
        path = str(self.vendor_dir)
        added = False
        if path not in sys.path:
            sys.path.insert(0, path)
            added = True
        try:
            yield
        finally:
            if added:
                try:
                    sys.path.remove(path)
                except ValueError:
                    pass

    def _load_detector(self, *, input_size: int = 1024, device: str = "cpu"):
        ok, reason = self.available()
        if not ok:
            raise RuntimeError(reason)

        # Do not hide CUDA globally here.  Older builds used
        # CUDA_VISIBLE_DEVICES="" as a safety switch, but that also made a
        # correctly installed CUDA runtime report device_count()==0.  Device
        # safety is handled below by _normalize_torch_device() and the temporary
        # torch.load(map_location=...) shim instead.

        _activate_managed_torch_runtime_path()
        with self._vendor_import_path():
            _install_numpy_compat_aliases()
            import torch
            from inference import TextDetector

            requested_device = str(device or "auto").strip().lower() or "auto"
            resolved_device = _normalize_torch_device(torch, requested_device)
            if self._detector is not None and self._device == resolved_device and self._input_size == input_size:
                self._last_device_report = _torch_device_report(
                    torch,
                    requested=requested_device,
                    resolved=resolved_device,
                    detector=self._detector,
                )
                return self._detector

            with _torch_load_map_location(resolved_device):
                self._detector = TextDetector(
                    model_path=str(self.model_path),
                    input_size=input_size,
                    device=resolved_device,
                    act="leaky",
                )
            self._device = resolved_device
            self._input_size = input_size
            self._last_device_report = _torch_device_report(
                torch,
                requested=requested_device,
                resolved=resolved_device,
                detector=self._detector,
            )
            return self._detector

    @staticmethod
    def _line_to_result(line: Any) -> TextDetectionLine:
        pts = []
        flat = list(line)
        if len(flat) == 8:
            pts = [(int(flat[i]), int(flat[i + 1])) for i in range(0, 8, 2)]
        return TextDetectionLine(polygon=pts, raw=line)

    @classmethod
    def _block_to_result(cls, block: Any) -> TextDetectionBlock:
        xyxy = getattr(block, "xyxy", [0, 0, 0, 0])
        bbox = tuple(int(v) for v in xyxy[:4])
        lines = [cls._line_to_result(line) for line in list(getattr(block, "lines", []) or [])]
        return TextDetectionBlock(
            bbox=bbox,  # type: ignore[arg-type]
            lines=lines,
            language=str(getattr(block, "language", "unknown") or "unknown"),
            vertical=bool(getattr(block, "vertical", False)),
            font_size=float(getattr(block, "font_size", -1)) if getattr(block, "font_size", -1) is not None else None,
            angle=int(getattr(block, "angle", 0) or 0),
            confidence=float(getattr(block, "prob", 0)) if getattr(block, "prob", None) is not None else None,
            raw=block,
        )

    def detect(self, request: TextDetectionRequest) -> TextDetectionResult:
        try:
            image_path = Path(request.image_path)
            if not image_path.exists():
                return TextDetectionResult(ok=False, engine=self.name, error=f"Image not found: {image_path}")

            options = request.options or {}
            input_size = int(options.get("input_size", 1024))
            device = str(options.get("device", "cpu"))
            save_masks = bool(options.get("save_masks", False))
            output_dir = Path(options.get("output_dir") or image_path.parent)
            keep_undetected_mask = bool(options.get("keep_undetected_mask", True))

            detector = self._load_detector(input_size=input_size, device=device)
            device_report = dict(getattr(self, "_last_device_report", {}) or {})
            try:
                print(
                    ">>> [Local OCR] comic_text_detector device: "
                    f"requested={device_report.get('requested_device', device)}, "
                    f"resolved={device_report.get('resolved_device', 'unknown')}, "
                    f"actual={device_report.get('actual_device', 'unknown')}, "
                    f"model={device_report.get('model_device', 'unknown')}, "
                    f"cuda_available={device_report.get('torch_cuda_available', False)}, "
                    f"cuda_count={device_report.get('torch_cuda_device_count', 0)}, "
                    f"gpu={device_report.get('torch_cuda_device_name', '')}, "
                    f"python={device_report.get('python_executable', sys.executable)}"
                )
            except Exception:
                pass

            with self._vendor_import_path():
                _install_numpy_compat_aliases()
                import cv2
                from utils.io_utils import imread, imwrite
                from utils.textmask import REFINEMASK_INPAINT

                img = imread(str(image_path))
                if img is None:
                    return TextDetectionResult(ok=False, engine=self.name, error=f"Failed to read image: {image_path}")

                mask, mask_refined, block_list = detector(
                    img,
                    refine_mode=REFINEMASK_INPAINT,
                    keep_undetected_mask=keep_undetected_mask,
                )

                blocks = [self._block_to_result(block) for block in block_list]
                mask_path = ""
                refined_mask_path = ""
                if save_masks:
                    output_dir.mkdir(parents=True, exist_ok=True)
                    stem = image_path.stem
                    mask_path = str(output_dir / f"{stem}.comic_text_mask.png")
                    refined_mask_path = str(output_dir / f"{stem}.comic_text_mask_refined.png")
                    imwrite(mask_path, mask)
                    imwrite(refined_mask_path, mask_refined)

                return TextDetectionResult(
                    ok=True,
                    engine=self.name,
                    blocks=blocks,
                    mask_path=mask_path,
                    refined_mask_path=refined_mask_path,
                    raw={
                        "mask": mask,
                        "mask_refined": mask_refined,
                        "blocks": block_list,
                        "device_report": device_report,
                    },
                )
        except Exception as exc:
            msg = str(exc)
            try:
                if "deserialize object on CUDA device" in msg or "cuda.device_count() is 0" in msg:
                    msg += " | YSB hint: comic_text_detector checkpoint is CUDA-saved but current Torch cannot see CUDA. Re-run in CPU/Auto mode or install/connect the Torch CUDA runtime. CPU-safe map_location should prevent this in current builds."
            except Exception:
                pass
            return TextDetectionResult(ok=False, engine=self.name, error=msg)
