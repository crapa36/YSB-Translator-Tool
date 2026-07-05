from __future__ import annotations

import copy
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

from ysb.core.project_store import ProjectStore
from ysb.core.workspace_save_lock import PROJECT_JSON_SAVE_LOCK


@dataclass
class WorkCacheImageDeltaSaveJob:
    """Background payload for workspace image-heavy page delta saves.

    This job must receive only plain Python data, bytes, numpy arrays, paths and
    serializable metadata.  It must never receive QWidget/QPixmap/QGraphicsItem or
    other UI-thread objects.  ProjectStore.save_pages_delta() mutates paths/data, so
    the caller passes snapshots and the worker returns the path/key updates that the
    UI thread may copy back into the live project state.
    """

    project_dir: str
    paths_snapshot: List[str]
    data_snapshot: Dict[int, dict]
    page_indices: List[int]
    current_index: int = 0
    ui_state: Dict[str, Any] = field(default_factory=dict)
    clean_image_format: str = "png"
    clean_image_quality: int = 95
    reason: str = "image_heavy"
    release_non_current: bool = True
    token: str = field(default_factory=lambda: uuid.uuid4().hex)

    @property
    def key(self) -> str:
        idx_key = ",".join(str(int(i)) for i in sorted(set(self.page_indices or [])))
        return f"{os.path.abspath(str(self.project_dir or ''))}|{idx_key}"


class WorkCacheImageDeltaSaveSignals(QObject):
    started = pyqtSignal(dict)
    done = pyqtSignal(dict)
    failed = pyqtSignal(dict)


class WorkCacheImageDeltaSaveRunnable(QRunnable):
    def __init__(self, job: WorkCacheImageDeltaSaveJob):
        super().__init__()
        self.job = job
        self.signals = WorkCacheImageDeltaSaveSignals()

    def run(self):
        try:
            start_payload = {
                "key": getattr(self.job, "key", ""),
                "token": getattr(self.job, "token", ""),
                "project_dir": str(getattr(self.job, "project_dir", "") or ""),
                "page_indices": list(getattr(self.job, "page_indices", []) or []),
                "reason": str(getattr(self.job, "reason", "") or ""),
            }
            self.signals.started.emit(start_payload)
            result = save_work_cache_image_delta_job(self.job)
            self.signals.done.emit(result)
        except Exception as exc:  # pragma: no cover - reported through UI audit log
            self.signals.failed.emit({
                "key": getattr(self.job, "key", ""),
                "token": getattr(self.job, "token", ""),
                "project_dir": str(getattr(self.job, "project_dir", "") or ""),
                "page_indices": list(getattr(self.job, "page_indices", []) or []),
                "reason": str(getattr(self.job, "reason", "") or ""),
                "error": repr(exc),
            })


def _copy_page_update(curr: dict) -> dict:
    out: dict[str, Any] = {}
    if not isinstance(curr, dict):
        return out
    # Only return lightweight state/path fields.  Heavy payload values remain in
    # the worker snapshot and are not copied back into the UI data object.
    for key in (
        "original_name",
        "clean_path",
        "working_source_path",
        "final_paint_path",
        "final_paint_above_path",
        "mask_merge_path",
        "mask_inpaint_path",
        "mask_merge_off_path",
        "mask_inpaint_off_path",
        "mask_merge_dirty",
        "mask_inpaint_dirty",
        "mask_merge_off_dirty",
        "mask_inpaint_off_dirty",
        "mask_toggle_enabled",
        "use_inpainted_as_source",
    ):
        if key in curr:
            try:
                out[key] = copy.deepcopy(curr.get(key))
            except Exception:
                out[key] = curr.get(key)
    return out


def save_work_cache_image_delta_job(job: WorkCacheImageDeltaSaveJob) -> dict:
    project_dir = os.path.abspath(str(job.project_dir or ""))
    if not project_dir:
        raise ValueError("project_dir is empty")
    job.project_dir = project_dir
    indices = sorted({int(i) for i in list(job.page_indices or []) if int(i) >= 0})
    if not indices:
        raise ValueError("page_indices is empty")

    store = ProjectStore(project_dir)
    store.ui_state = dict(job.ui_state or {}) if isinstance(job.ui_state, dict) else {}
    store.clean_image_format = str(job.clean_image_format or "png")
    try:
        store.clean_image_quality = int(job.clean_image_quality or 95)
    except Exception:
        store.clean_image_quality = 95
    try:
        store._cleanup_duplicate_masks_on_save = False
    except Exception:
        pass

    paths = list(job.paths_snapshot or [])
    data = {int(k): v for k, v in dict(job.data_snapshot or {}).items() if isinstance(v, dict)}

    with PROJECT_JSON_SAVE_LOCK:
        ok = bool(store.save_pages_delta(paths, data, set(indices), current_index=int(job.current_index or 0)))

    page_updates: dict[int, dict] = {}
    for i in indices:
        page_updates[int(i)] = _copy_page_update(data.get(int(i), {}))

    return {
        "key": job.key,
        "token": job.token,
        "project_dir": project_dir,
        "page_indices": indices,
        "updated_paths": {int(i): paths[int(i)] for i in indices if 0 <= int(i) < len(paths)},
        "page_updates": page_updates,
        "reason": str(job.reason or "image_heavy"),
        "release_non_current": bool(job.release_non_current),
        "ok": bool(ok),
    }
