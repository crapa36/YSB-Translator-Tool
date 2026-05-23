# -*- coding: utf-8 -*-
"""comic_text_detector adapter for YSB Tool Local.

The vendored detector is intentionally loaded lazily so Lite builds can import
YSB common modules without requiring torch/comic_text_detector dependencies.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
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


class ComicTextDetectorEngine:
    name = "comic_text_detector"

    def __init__(self, *, model_path: str | None = None, vendor_dir: str | None = None) -> None:
        self.model_path = Path(model_path) if model_path else default_comic_detector_model_path()
        self.vendor_dir = Path(vendor_dir) if vendor_dir else default_comic_detector_vendor_dir()
        self._detector: Any = None
        self._device: str | None = None
        self._input_size: int | None = None

    def available(self) -> tuple[bool, str]:
        if not is_local_edition():
            return False, "comic_text_detector is Local edition only."
        if not self.vendor_dir.exists():
            return False, f"comic_text_detector vendor folder not found: {self.vendor_dir}"
        if not self.model_path.exists():
            return False, f"comic_text_detector model not found: {self.model_path}"
        try:
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

    def _load_detector(self, *, input_size: int = 1024, device: str = "auto"):
        if self._detector is not None and self._device == device and self._input_size == input_size:
            return self._detector

        ok, reason = self.available()
        if not ok:
            raise RuntimeError(reason)

        with self._vendor_import_path():
            _install_numpy_compat_aliases()
            import torch
            from inference import TextDetector

            if device == "auto":
                device = "cuda" if torch.cuda.is_available() else "cpu"
            self._detector = TextDetector(
                model_path=str(self.model_path),
                input_size=input_size,
                device=device,
                act="leaky",
            )
            self._device = device
            self._input_size = input_size
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
            device = str(options.get("device", "auto"))
            save_masks = bool(options.get("save_masks", False))
            output_dir = Path(options.get("output_dir") or image_path.parent)
            keep_undetected_mask = bool(options.get("keep_undetected_mask", True))

            detector = self._load_detector(input_size=input_size, device=device)

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
                    raw={"mask": mask, "mask_refined": mask_refined, "blocks": block_list},
                )
        except Exception as exc:
            return TextDetectionResult(ok=False, engine=self.name, error=str(exc))
