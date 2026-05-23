# -*- coding: utf-8 -*-
"""Debug preview helpers for text-detection masks.

These helpers are intentionally small and dependency-light. They are used by
Local test scripts to visually inspect whether a detector mask is suitable for
YSB's removal/inpainting flow.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _require_cv2_np():
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
        return cv2, np
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "OpenCV/numpy is required for mask preview generation. "
            "Install requirements/common.txt first."
        ) from exc


def imread_unicode(path: str | Path):
    """Read an image from paths that may contain non-ASCII characters."""
    cv2, np = _require_cv2_np()
    p = Path(path)
    data = np.fromfile(str(p), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_UNCHANGED)


def imwrite_unicode(path: str | Path, image: Any) -> None:
    """Write an image to paths that may contain non-ASCII characters."""
    cv2, _np = _require_cv2_np()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    ext = p.suffix or ".png"
    ok, encoded = cv2.imencode(ext, image)
    if not ok:
        raise RuntimeError(f"Failed to encode image: {p}")
    encoded.tofile(str(p))


def ensure_uint8_mask(mask: Any, *, threshold: int = 1, dilate_px: int = 0):
    """Convert detector masks to a clean 0/255 uint8 mask.

    Args:
        mask: numpy-like mask returned by comic_text_detector.
        threshold: Any pixel value >= threshold is treated as text/mask.
        dilate_px: Optional expansion in pixels. This is useful for checking
            whether outlines/strokes would also be removed.
    """
    cv2, np = _require_cv2_np()
    arr = np.asarray(mask)
    if arr.ndim == 3:
        arr = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    arr = arr.astype(np.uint8, copy=False)
    clean = np.where(arr >= threshold, 255, 0).astype(np.uint8)
    if dilate_px and dilate_px > 0:
        kernel_size = max(1, int(dilate_px) * 2 + 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        clean = cv2.dilate(clean, kernel, iterations=1)
    return clean


def make_mask_overlay(image: Any, mask: Any, *, alpha: float = 0.45):
    """Create an overlay image where masked pixels are tinted red."""
    cv2, np = _require_cv2_np()
    img = image.copy()
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    clean = ensure_uint8_mask(mask)
    red = np.zeros_like(img)
    red[:, :, 2] = 255
    blended = cv2.addWeighted(img, 1.0, red, float(alpha), 0)
    out = img.copy()
    out[clean > 0] = blended[clean > 0]
    return out


def make_mask_whiteout_preview(image: Any, mask: Any):
    """Paint masked pixels white to show the rough removal area."""
    cv2, _np = _require_cv2_np()
    img = image.copy()
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    clean = ensure_uint8_mask(mask)
    out = img.copy()
    out[clean > 0] = (255, 255, 255)
    return out


def make_cv2_inpaint_preview(image: Any, mask: Any, *, radius: int = 3):
    """Create a quick local inpaint preview using OpenCV Telea.

    This is only a cheap preview. It is not meant to match LaMa/API inpainting.
    It is useful for checking whether the mask covers the right pixels.
    """
    cv2, _np = _require_cv2_np()
    img = image.copy()
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    clean = ensure_uint8_mask(mask)
    return cv2.inpaint(img, clean, int(radius), cv2.INPAINT_TELEA)


def write_mask_preview_set(
    *,
    image_path: str | Path,
    mask: Any,
    output_dir: str | Path,
    stem: str | None = None,
    dilate_px: int = 0,
    inpaint_radius: int = 3,
) -> dict[str, str]:
    """Write mask/overlay/whiteout/inpaint preview images and return paths."""
    cv2, _np = _require_cv2_np()
    src = imread_unicode(image_path)
    if src is None:
        raise RuntimeError(f"Failed to read image: {image_path}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = stem or Path(image_path).stem

    clean_mask = ensure_uint8_mask(mask, dilate_px=dilate_px)
    overlay = make_mask_overlay(src, clean_mask)
    whiteout = make_mask_whiteout_preview(src, clean_mask)
    inpaint = make_cv2_inpaint_preview(src, clean_mask, radius=inpaint_radius)

    mask_path = out_dir / f"{base}.mask_used.png"
    overlay_path = out_dir / f"{base}.mask_overlay.png"
    whiteout_path = out_dir / f"{base}.mask_whiteout_preview.png"
    inpaint_path = out_dir / f"{base}.mask_cv2_inpaint_preview.png"

    imwrite_unicode(mask_path, clean_mask)
    imwrite_unicode(overlay_path, overlay)
    imwrite_unicode(whiteout_path, whiteout)
    imwrite_unicode(inpaint_path, inpaint)

    return {
        "mask_used": str(mask_path),
        "mask_overlay": str(overlay_path),
        "mask_whiteout_preview": str(whiteout_path),
        "mask_cv2_inpaint_preview": str(inpaint_path),
    }
