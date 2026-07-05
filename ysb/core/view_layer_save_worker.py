from __future__ import annotations

import copy
import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import numpy as np
from PyQt6.QtCore import QObject, QRunnable, pyqtSignal
from PyQt6.QtGui import QImage

from ysb.core.workspace_save_lock import PROJECT_JSON_SAVE_LOCK
from ysb.core.project_store import (
    PROJECT_FILENAME,
    PROJECT_VERSION,
    ProjectStore,
    _atomic_save_mask_array,
    _mask_canonical_path,
    ensure_dir,
    json_safe,
    relpath,
)



@dataclass
class ViewLayerSaveJob:
    """Background-save payload for current view layer changes.

    The UI thread may capture QImage copies or numpy masks, but this job never
    receives QPixmap/QGraphicsItem/QWidget/scene objects.  PNG encoding, mask file
    writes, and project.json updates happen in the worker thread.
    """

    project_dir: str
    page_idx: int
    page_count: int
    current_index: int = 0
    image_path: str = ""
    original_name: str = ""
    ui_state: Dict[str, Any] = field(default_factory=dict)
    process_final_paint: bool = False
    final_paint_qimage: Optional[QImage] = None
    final_paint_above_qimage: Optional[QImage] = None
    process_mask: bool = False
    mask_key: str = ""
    mask_array: Any = None
    mask_toggle_enabled: bool = False
    use_inpainted_as_source: bool = False
    token: str = field(default_factory=lambda: uuid.uuid4().hex)

    @property
    def key(self) -> str:
        return f"{os.path.abspath(str(self.project_dir or ''))}|{int(self.page_idx)}"


class ViewLayerSaveSignals(QObject):
    started = pyqtSignal(dict)
    done = pyqtSignal(dict)
    failed = pyqtSignal(dict)


class ViewLayerSaveRunnable(QRunnable):
    def __init__(self, job: ViewLayerSaveJob):
        super().__init__()
        self.job = job
        self.signals = ViewLayerSaveSignals()

    def run(self):
        try:
            self.signals.started.emit(
                {
                    "key": getattr(self.job, "key", ""),
                    "token": getattr(self.job, "token", ""),
                    "page_idx": int(getattr(self.job, "page_idx", -1) or -1),
                    "project_dir": str(getattr(self.job, "project_dir", "") or ""),
                    "process_final_paint": bool(getattr(self.job, "process_final_paint", False)),
                    "process_mask": bool(getattr(self.job, "process_mask", False)),
                    "mask_key": str(getattr(self.job, "mask_key", "") or ""),
                }
            )
            result = save_view_layer_job(self.job)
            self.signals.done.emit(result)
        except Exception as exc:  # pragma: no cover - surfaced through UI audit log
            self.signals.failed.emit(
                {
                    "key": getattr(self.job, "key", ""),
                    "token": getattr(self.job, "token", ""),
                    "page_idx": int(getattr(self.job, "page_idx", -1) or -1),
                    "project_dir": str(getattr(self.job, "project_dir", "") or ""),
                    "error": repr(exc),
                }
            )


def _load_project_payload(project_dir: str) -> dict:
    project_file = os.path.join(project_dir, PROJECT_FILENAME)
    if not os.path.exists(project_file):
        return {"version": PROJECT_VERSION, "current_index": 0, "pages": [], "ui_state": {}}
    try:
        with open(project_file, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            return loaded
    except Exception:
        pass
    return {"version": PROJECT_VERSION, "current_index": 0, "pages": [], "ui_state": {}}


def _atomic_write_project_payload(project_dir: str, payload: dict) -> None:
    project_file = os.path.join(project_dir, PROJECT_FILENAME)
    tmp_path = project_file + ".view_layer_tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, project_file)


def _qimage_has_visible_alpha(qimg: Optional[QImage]) -> bool:
    if qimg is None or qimg.isNull():
        return False
    img = qimg.convertToFormat(QImage.Format.Format_ARGB32)
    w, h = int(img.width()), int(img.height())
    if w <= 0 or h <= 0:
        return False
    ptr = img.bits()
    ptr.setsize(img.sizeInBytes())
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, img.bytesPerLine() // 4, 4))
    alpha = arr[:, :w, 3]
    return bool(np.any(alpha > 0))


def _atomic_save_qimage_png(qimg: QImage, path: str) -> bool:
    ensure_dir(os.path.dirname(path))
    tmp_path = path + ".tmp.png"
    try:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    except Exception:
        pass
    img = qimg.convertToFormat(QImage.Format.Format_ARGB32)
    if not img.save(tmp_path, "PNG"):
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        return False
    os.replace(tmp_path, path)
    return True


def _write_or_clear_final_paint(job: ViewLayerSaveJob, page: dict, *, above: bool) -> dict:
    key = "final_paint_above" if above else "final_paint"
    folder = "final_paint_above" if above else "final_paint"
    prefix = "final_paint_above" if above else "final_paint"
    qimg = job.final_paint_above_qimage if above else job.final_paint_qimage
    out_path = os.path.join(job.project_dir, folder, f"{prefix}_{int(job.page_idx) + 1:04d}.png")
    result = {f"{key}_processed": True, f"{key}_path": None, f"{key}_cleared": False}
    if qimg is not None and _qimage_has_visible_alpha(qimg):
        if not _atomic_save_qimage_png(qimg, out_path):
            raise IOError(f"failed to save {key} png: {out_path}")
        page[key] = relpath(out_path, job.project_dir)
        result[f"{key}_path"] = out_path
        return result
    page.pop(key, None)
    result[f"{key}_cleared"] = True
    try:
        if os.path.exists(out_path):
            os.remove(out_path)
    except Exception:
        pass
    return result


def save_view_layer_job(job: ViewLayerSaveJob) -> dict:
    project_dir = os.path.abspath(str(job.project_dir or ""))
    if not project_dir:
        raise ValueError("project_dir is empty")
    job.project_dir = project_dir
    ensure_dir(project_dir)
    store = ProjectStore(project_dir)
    store.init_dirs()

    with PROJECT_JSON_SAVE_LOCK:
        payload = _load_project_payload(project_dir)
        pages = payload.get("pages", []) if isinstance(payload.get("pages"), list) else []
        pages = [copy.deepcopy(p) if isinstance(p, dict) else {} for p in pages]
        page_count = max(int(job.page_count or 0), int(job.page_idx) + 1, len(pages))
        while len(pages) < page_count:
            pages.append({})

        page_idx = int(job.page_idx)
        page = pages[page_idx] if isinstance(pages[page_idx], dict) else {}
        page = copy.deepcopy(page)

        if job.image_path:
            try:
                page["image"] = relpath(str(job.image_path), project_dir)
            except Exception:
                page.setdefault("image", str(job.image_path))
        if job.original_name:
            page["original_name"] = str(job.original_name)
        page["mask_toggle_enabled"] = bool(job.mask_toggle_enabled)
        page["use_inpainted_as_source"] = bool(job.use_inpainted_as_source)

        result = {
            "key": job.key,
            "token": job.token,
            "project_dir": project_dir,
            "page_idx": page_idx,
            "processed_final_paint": bool(job.process_final_paint),
            "processed_mask": bool(job.process_mask and job.mask_key),
            "final_paint_path": None,
            "final_paint_above_path": None,
            "mask_key": str(job.mask_key or ""),
            "mask_path": None,
        }

        if job.process_final_paint:
            r1 = _write_or_clear_final_paint(job, page, above=False)
            r2 = _write_or_clear_final_paint(job, page, above=True)
            result.update(r1)
            result.update(r2)
            result["final_paint_path"] = r1.get("final_paint_path")
            result["final_paint_above_path"] = r2.get("final_paint_above_path")

        if job.process_mask and job.mask_key:
            mask = np.array(job.mask_array, dtype=np.uint8).copy()
            mask_path = _mask_canonical_path(project_dir, str(job.mask_key), page_idx)
            if not mask_path:
                raise ValueError(f"invalid mask key: {job.mask_key}")
            _atomic_save_mask_array(mask_path, mask)
            page[str(job.mask_key)] = relpath(mask_path, project_dir)
            result["mask_path"] = mask_path

        pages[page_idx] = page
        payload = {
            "version": payload.get("version") or PROJECT_VERSION,
            "current_index": int(job.current_index),
            "pages": pages[:page_count],
            "ui_state": json_safe(job.ui_state if isinstance(job.ui_state, dict) else payload.get("ui_state", {}) or {}),
        }
        store.ui_state = payload.get("ui_state") if isinstance(payload.get("ui_state"), dict) else {}
        store.write_manifest()
        _atomic_write_project_payload(project_dir, payload)

    return result
