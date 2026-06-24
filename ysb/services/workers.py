import os
import re
import copy
import cv2
import numpy as np
import requests
import time
import threading
import gc
from PyQt6.QtCore import QThread, pyqtSignal

from ysb.utils.runtime_logger import (
    append_block,
    append_log,
    estimated_bgr_mb,
    exception_text,
    file_size,
    format_bytes,
    image_size,
    make_log_path,
    memory_text,
    numpy_shape_text,
)


def _imwrite_unicode(path, image):
    try:
        ext = os.path.splitext(str(path))[1] or ".png"
        ok, buf = cv2.imencode(ext, image)
        if not ok:
            return False
        buf.tofile(str(path))
        return True
    except Exception:
        return False


def _download_replicate_output(output):
    """Replicate output can be URL strings, lists, FileOutput objects, file-like objects, bytes, or local paths."""
    if output is None:
        return b""
    if isinstance(output, (list, tuple)):
        if not output:
            return b""
        output = output[0]
    if isinstance(output, (bytes, bytearray)):
        return bytes(output)
    # replicate FileOutput often supports read()
    try:
        if hasattr(output, "read") and callable(output.read):
            data = output.read()
            if isinstance(data, str):
                return data.encode("utf-8")
            return bytes(data or b"")
    except Exception:
        pass
    # some objects expose url
    try:
        if hasattr(output, "url"):
            output = output.url
    except Exception:
        pass
    text = str(output)
    if text.startswith("http://") or text.startswith("https://"):
        r = requests.get(text, timeout=180)
        r.raise_for_status()
        return r.content
    if os.path.exists(text):
        with open(text, "rb") as f:
            return f.read()
    # Last fallback: requests may know how to handle object string repr for older clients.
    r = requests.get(text, timeout=180)
    r.raise_for_status()
    return r.content


def _inpaint_resize_limits(provider):
    provider = str(provider or "replicate_lama").strip().lower()
    if provider in ("local_lama", "local_sdxl_lightning"):
        return {
            "warn_max_side": 3000,
            "warn_max_pixels": 9_000_000,
            "target_max_side": 2800,
            "target_max_pixels": 7_500_000,
        }
    if provider == "replicate_lama":
        return {
            "warn_max_side": 2800,
            "warn_max_pixels": 6_000_000,
            "target_max_side": 2200,
            "target_max_pixels": 4_000_000,
        }
    return None


def _build_inpaint_resize_plan_from_size(width, height, limits):
    if not limits:
        return None
    w = int(width or 0)
    h = int(height or 0)
    if w <= 0 or h <= 0:
        return None
    max_side = max(w, h)
    total_pixels = w * h
    warn_max_side = int(limits.get("warn_max_side", 0) or 0)
    warn_max_pixels = int(limits.get("warn_max_pixels", 0) or 0)
    if (warn_max_side <= 0 or max_side <= warn_max_side) and (warn_max_pixels <= 0 or total_pixels <= warn_max_pixels):
        return None
    scale = 1.0
    target_max_side = int(limits.get("target_max_side", warn_max_side) or warn_max_side or 0)
    target_max_pixels = int(limits.get("target_max_pixels", warn_max_pixels) or warn_max_pixels or 0)
    if target_max_side > 0 and max_side > target_max_side:
        scale = min(scale, float(target_max_side) / float(max_side))
    if target_max_pixels > 0 and total_pixels > target_max_pixels:
        scale = min(scale, float(target_max_pixels / float(total_pixels)) ** 0.5)
    if scale >= 0.9999:
        return None
    return {
        "target_width": max(1, int(round(w * scale))),
        "target_height": max(1, int(round(h * scale))),
        "orig_width": w,
        "orig_height": h,
    }


def _prepare_resized_inpaint_request(project_dir, page_idx, source_path, inpaint_mask, provider, policy):
    if not source_path or not os.path.exists(str(source_path)):
        return source_path, inpaint_mask, None
    if not isinstance(policy, dict) or not bool(policy.get("enabled", False)):
        return source_path, inpaint_mask, None
    allowed_pages = policy.get("page_indices") or []
    try:
        allowed_pages = {int(x) for x in allowed_pages}
    except Exception:
        allowed_pages = set()
    if allowed_pages and int(page_idx) not in allowed_pages:
        return source_path, inpaint_mask, None

    limits = {
        "warn_max_side": int(policy.get("warn_max_side", 0) or 0),
        "warn_max_pixels": int(policy.get("warn_max_pixels", 0) or 0),
        "target_max_side": int(policy.get("target_max_side", 0) or 0),
        "target_max_pixels": int(policy.get("target_max_pixels", 0) or 0),
    }
    if not limits.get("target_max_side") and not limits.get("target_max_pixels"):
        limits = _inpaint_resize_limits(provider)
    try:
        img = cv2.imdecode(np.fromfile(str(source_path), np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        img = None
    if img is None:
        return source_path, inpaint_mask, None
    h, w = img.shape[:2]
    plan = _build_inpaint_resize_plan_from_size(w, h, limits)
    if not plan:
        return source_path, inpaint_mask, None
    tw = int(plan.get("target_width", 0) or 0)
    th = int(plan.get("target_height", 0) or 0)
    if tw <= 0 or th <= 0:
        return source_path, inpaint_mask, None
    interp = cv2.INTER_AREA if tw < w or th < h else cv2.INTER_CUBIC
    resized = cv2.resize(img, (tw, th), interpolation=interp)
    base_dir = project_dir or os.path.dirname(str(source_path)) or os.getcwd()
    out_dir = os.path.join(base_dir, "_inpaint_resize_cache")
    os.makedirs(out_dir, exist_ok=True)
    provider_key = str((policy or {}).get("provider") or provider or "").strip().lower()
    # Replicate 업로드는 픽셀 수뿐 아니라 파일 용량도 실패 요인이 될 수 있다.
    # 축소본을 PNG로 저장하면 원본 JPG보다 커질 수 있으므로 Replicate LaMa에는 JPG 임시 입력을 쓴다.
    ext = ".jpg" if provider_key == "replicate_lama" else ".png"
    out_path = os.path.join(out_dir, f"batch_page_{int(page_idx)+1:04d}_{tw}x{th}{ext}")
    if ext == ".jpg":
        ok, buf = cv2.imencode(ext, resized, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        if not ok:
            return source_path, inpaint_mask, None
        try:
            buf.tofile(out_path)
        except Exception:
            return source_path, inpaint_mask, None
    else:
        if not _imwrite_unicode(out_path, resized):
            return source_path, inpaint_mask, None
    resized_mask = inpaint_mask
    if inpaint_mask is not None:
        try:
            resized_mask = cv2.resize(inpaint_mask, (tw, th), interpolation=cv2.INTER_NEAREST)
        except Exception:
            resized_mask = inpaint_mask
    note = f"↘️ 인페인팅 입력 축소: {w}x{h} → {tw}x{th}"
    return out_path, resized_mask, note




def _detect_ocr_provider_name():
    try:
        from ysb.engine.manga_engine import Config
        provider = str(getattr(Config, "OCR_PROVIDER", "clova") or "clova")
        if provider == "google_vision":
            return provider, "Google Vision"
        if provider == "local_paddle_ocr":
            return provider, "LOCAL Paddle OCR"
        if provider == "local_manga_ocr":
            return provider, "LOCAL Manga OCR"
        return provider, "CLOVA"
    except Exception:
        return "unknown", "OCR"


def _log_path_image_summary(log_path, label, path):
    size = image_size(path)
    est = estimated_bgr_mb(size)
    append_log(
        log_path,
        label,
        file_path=path,
        file_size=format_bytes(file_size(path)),
        image_size=(f"{size[0]}x{size[1]}" if size else "unknown"),
        estimated_bgr=(f"{est:.1f}MB" if est is not None else "unknown"),
        memory=memory_text(),
    )


def _imread_unicode(path: str):
    arr = np.fromfile(path, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


PAGE_DISPLAY_MODE_ORIGINAL = "original_name"
PAGE_DISPLAY_MODE_PAGE_ORIGINAL = "1p_original_name"
PAGE_DISPLAY_MODE_PAGE_NUMBER = "page001"
DEFAULT_PAGE_DISPLAY_MODE = PAGE_DISPLAY_MODE_PAGE_ORIGINAL


def _normalize_page_display_mode(value):
    value = str(value or DEFAULT_PAGE_DISPLAY_MODE).strip()
    if value in (PAGE_DISPLAY_MODE_ORIGINAL, PAGE_DISPLAY_MODE_PAGE_ORIGINAL, PAGE_DISPLAY_MODE_PAGE_NUMBER):
        return value
    return DEFAULT_PAGE_DISPLAY_MODE


def _safe_page_file_stem(value, fallback="page"):
    stem = os.path.splitext(os.path.basename(str(value or fallback)))[0].strip() or fallback
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", stem).strip(" .")
    return stem or fallback


def _copy_mask(mask):
    if mask is None:
        return None
    return np.array(mask, dtype=np.uint8).copy()


def _load_mask_from_project_path(project_dir, path_value):
    if not path_value:
        return None
    try:
        p = str(path_value)
        if not os.path.isabs(p) and project_dir:
            p = os.path.join(str(project_dir), p.replace("/", os.sep))
        if os.path.exists(p):
            return np.load(p).copy()
    except Exception:
        return None
    return None

def _is_temp_inpaint_request_path(path):
    try:
        norm = os.path.normpath(str(path or ""))
        if not norm:
            return False
        base = os.path.basename(norm).lower()
        return (
            "_inpaint_resize_cache" in norm
            or base.startswith("ysb_lama_oom_retry_")
            or base.startswith("batch_page_")
            or base.startswith("page_") and "_inpaint_resize_cache" in norm
        )
    except Exception:
        return False


def _cleanup_temp_inpaint_request(path):
    try:
        if path and _is_temp_inpaint_request_path(path) and os.path.exists(str(path)):
            os.remove(str(path))
            return True
    except Exception:
        return False
    return False


def _get_batch_inpaint_wait_seconds(provider):
    try:
        from ysb.engine.manga_engine import Config
        provider = str(provider or getattr(Config, "INPAINT_PROVIDER", "replicate_lama") or "replicate_lama").lower()
        if provider == "replicate_stable":
            return max(0.0, float(getattr(Config, "STABLE_INPAINT_WAIT_SECONDS", 5) or 0))
        if provider == "local_lama":
            return max(0.0, float(getattr(Config, "LOCAL_LAMA_WAIT_SECONDS", 0) or 0))
        if provider == "replicate_lama":
            return max(0.0, float(getattr(Config, "REPLICATE_LAMA_WAIT_SECONDS", 5) or 0))
    except Exception:
        pass
    return 0.0




def _sleep_interruptible(owner, seconds, step=0.1):
    try:
        remain = max(0.0, float(seconds or 0.0))
    except Exception:
        remain = 0.0
    while remain > 0:
        if owner is not None and not bool(getattr(owner, "is_running", True)):
            return False
        interval = min(float(step), remain)
        time.sleep(interval)
        remain -= interval
    return True




def _copy_data_list(data_list):
    return copy.deepcopy(data_list or [])


def _clip_mask_to_checked_text_boxes(mask, data):
    """
    일괄 인페인팅용 ON 마스크 제한:
    분석 기반 페인팅 마스크는 체크된 텍스트 박스 내부만 남긴다.
    """
    if mask is None:
        return None

    if mask.ndim == 3:
        gray = cv2.cvtColor(mask, cv2.COLOR_RGB2GRAY)
    else:
        gray = mask.copy()

    h, w = gray.shape[:2]
    allowed = np.zeros((h, w), dtype=np.uint8)

    for item in data or []:
        if not item.get('use_inpaint', True):
            continue
        rect = item.get('rect')
        if not rect or len(rect) < 4:
            continue
        try:
            rx, ry, rw, rh = [int(v) for v in rect[:4]]
        except Exception:
            continue

        x1 = max(0, rx)
        y1 = max(0, ry)
        x2 = min(w, rx + max(0, rw))
        y2 = min(h, ry + max(0, rh))
        if x2 > x1 and y2 > y1:
            allowed[y1:y2, x1:x2] = 255

    return cv2.bitwise_and(gray, allowed)


def _build_inpainting_payload(mask_toggle_enabled, curr_data):
    """
    - ON: 분석 기반 페인팅 마스크를 체크된 텍스트 박스 영역 안으로 제한.
    - OFF: 수동 OFF 페인팅 마스크를 그대로 사용하고, 텍스트 박스/체크 상태는 무시.
    """
    data = _copy_data_list(curr_data.get('data', []))
    if mask_toggle_enabled:
        mask = _copy_mask(curr_data.get('mask_inpaint'))
        if mask is not None:
            mask = _clip_mask_to_checked_text_boxes(mask, data)
        return data, mask

    return [], _copy_mask(curr_data.get('mask_inpaint_off'))


class UniversalBatchWorker(QThread):
    progress = pyqtSignal(str)
    # page index, mode
    # 메인 UI가 현재 처리 중인 페이지로 따라가게 한다.
    active_item = pyqtSignal(int, str)
    # page index, payload dict
    # payload는 메인 스레드에서 self.data[i]에 반영된다.
    finished_item = pyqtSignal(int, object)
    finished_all = pyqtSignal()

    def __init__(self, main_window, mode, page_indices=None):
        super().__init__()
        self.main = main_window
        self.mode = mode
        self.engine = main_window.engine
        self.is_running = True
        self._item_applied_event = threading.Event()
        self._waiting_item_index = None

        # 스레드 안에서 UI 위젯을 직접 읽지 않도록 시작 시점 값만 복사
        self.paths = list(main_window.paths)
        if page_indices is None:
            self.page_indices = list(range(len(self.paths)))
        else:
            clean_indices = []
            seen_indices = set()
            for raw_idx in page_indices:
                try:
                    page_idx = int(raw_idx)
                except Exception:
                    continue
                if 0 <= page_idx < len(self.paths) and page_idx not in seen_indices:
                    clean_indices.append(page_idx)
                    seen_indices.add(page_idx)
            self.page_indices = clean_indices or list(range(len(self.paths)))
        self.provider = main_window.cb_trans_provider.currentData()
        try:
            from ysb.engine.manga_engine import Config
            self.inpaint_provider = str(getattr(Config, "INPAINT_PROVIDER", "replicate_lama") or "replicate_lama").lower()
        except Exception:
            self.inpaint_provider = "replicate_lama"
        self.font_family = main_window.cb_font.currentFont().family()
        self.stroke_size = main_window.sb_strk.value()
        self.font_size = main_window.sb_font_size.value()
        self.mask_toggle_enabled = bool(getattr(main_window, "mask_toggle_enabled", False))
        self.project_dir = getattr(main_window, "project_dir", None)
        self.output_display_name_mode = _normalize_page_display_mode(getattr(main_window, "output_display_name_mode", DEFAULT_PAGE_DISPLAY_MODE))
        self.output_image_format = str(getattr(main_window, "output_image_format", "png") or "png")
        self.clean_image_format = str(getattr(main_window, "clean_image_format", "png") or "png")
        self.output_image_quality = int(getattr(main_window, "output_image_quality", 95) or 95)
        self.clean_image_quality = int(getattr(main_window, "clean_image_quality", 95) or 95)
        self.batch_inpaint_resize_policy = copy.deepcopy(getattr(main_window, "_batch_inpaint_resize_policy", None))

        self.batch_log_path = make_log_path(f"batch_{self.mode}")
        self.ocr_provider, self.ocr_provider_name = _detect_ocr_provider_name()
        append_log(
            self.batch_log_path,
            "BATCH WORKER INIT",
            mode=self.mode,
            total_paths=len(self.paths),
            selected_pages=len(self.page_indices),
            selected_indices=self.page_indices[:50],
            project_dir=self.project_dir or "",
            translate_provider=self.provider,
            inpaint_provider=self.inpaint_provider,
            ocr_provider=self.ocr_provider,
            memory=memory_text(),
        )

        # 일괄 분석/재분석은 프로젝트 전체 작업이 아니라 페이지 작업을 이어 붙인 매크로다.
        # 시작 시점에 모든 페이지 mask 배열을 복사하면 메모리가 폭증하므로,
        # 전체 스냅샷을 만들지 않고 각 페이지 처리 직전에 필요한 데이터만 읽는다.
        self.data_snapshot = {}
        append_log(
            self.batch_log_path,
            "BATCH SNAPSHOT DEFERRED",
            mode=self.mode,
            selected_pages=len(self.page_indices),
            memory=memory_text(),
        )

    def _snapshot_page_for_mode(self, page_idx, path):
        src = {}
        try:
            src = (getattr(self.main, "data", {}) or {}).get(page_idx) or {}
        except Exception:
            src = {}
        snap = {
            'data': [],
            'mask_merge': None,
            'mask_inpaint': None,
            'mask_merge_off': None,
            'mask_inpaint_off': None,
            'use_inpainted_as_source': False,
            'bg_clean': None,
            'clean_path': None,
            'original_name': src.get('original_name') or os.path.basename(path),
            'ocr_analysis_regions': [],
        }
        append_log(
            self.batch_log_path,
            "SNAPSHOT PAGE BEGIN",
            index=page_idx,
            selected=True,
            source=("disk" if not src else "main.data"),
            file_path=path,
            file_size=format_bytes(file_size(path)),
            image_size=(lambda _s: f"{_s[0]}x{_s[1]}" if _s else "unknown")(image_size(path)),
            memory=memory_text(),
        )
        try:
            if self.mode == 'analyze':
                snap['ocr_analysis_regions'] = copy.deepcopy(src.get('ocr_analysis_regions', []) or [])
            elif self.mode == 'reanalyze':
                snap['data'] = _copy_data_list(src.get('data', []))
                mask_merge = _copy_mask(src.get('mask_merge'))
                if mask_merge is None:
                    mask_merge = _load_mask_from_project_path(self.project_dir, src.get('mask_merge_path'))
                snap['mask_merge'] = mask_merge
                snap['mask_inpaint'] = _copy_mask(src.get('mask_inpaint'))
                if snap['mask_inpaint'] is None:
                    snap['mask_inpaint'] = _load_mask_from_project_path(self.project_dir, src.get('mask_inpaint_path'))
                snap['mask_merge_off'] = _copy_mask(src.get('mask_merge_off'))
                if snap['mask_merge_off'] is None:
                    snap['mask_merge_off'] = _load_mask_from_project_path(self.project_dir, src.get('mask_merge_off_path'))
                snap['mask_inpaint_off'] = _copy_mask(src.get('mask_inpaint_off'))
                if snap['mask_inpaint_off'] is None:
                    snap['mask_inpaint_off'] = _load_mask_from_project_path(self.project_dir, src.get('mask_inpaint_off_path'))
                snap['use_inpainted_as_source'] = bool(src.get('use_inpainted_as_source', False))
                snap['clean_path'] = src.get('clean_path')
                snap['bg_clean'] = src.get('bg_clean')
            elif self.mode == 'translate':
                snap['data'] = _copy_data_list(src.get('data', []))
            elif self.mode == 'inpaint':
                snap['data'] = _copy_data_list(src.get('data', []))
                snap['mask_inpaint'] = _copy_mask(src.get('mask_inpaint'))
                if snap['mask_inpaint'] is None:
                    snap['mask_inpaint'] = _load_mask_from_project_path(self.project_dir, src.get('mask_inpaint_path'))
                snap['mask_inpaint_off'] = _copy_mask(src.get('mask_inpaint_off'))
                if snap['mask_inpaint_off'] is None:
                    snap['mask_inpaint_off'] = _load_mask_from_project_path(self.project_dir, src.get('mask_inpaint_off_path'))
                snap['use_inpainted_as_source'] = bool(src.get('use_inpainted_as_source', False))
                snap['clean_path'] = src.get('clean_path')
                snap['bg_clean'] = src.get('bg_clean')
            elif self.mode == 'export':
                snap['data'] = _copy_data_list(src.get('data', []))
                snap['clean_path'] = src.get('clean_path')
                snap['bg_clean'] = src.get('bg_clean')
        finally:
            append_log(
                self.batch_log_path,
                "SNAPSHOT PAGE DONE",
                index=page_idx,
                selected=True,
                data_count=len(snap.get('data') or []),
                mask_merge=numpy_shape_text(snap.get('mask_merge')),
                mask_inpaint=numpy_shape_text(snap.get('mask_inpaint')),
                regions=len(snap.get('ocr_analysis_regions') or []),
                memory=memory_text(),
            )
        return snap

    def mark_item_applied(self, page_idx=None):
        try:
            if page_idx is None or self._waiting_item_index is None or int(page_idx) == int(self._waiting_item_index):
                self._item_applied_event.set()
        except Exception:
            self._item_applied_event.set()

    def _wait_until_item_applied(self, page_idx):
        self._waiting_item_index = page_idx
        try:
            while self.is_running and not self._item_applied_event.wait(0.05):
                pass
        finally:
            self._waiting_item_index = None

    def _emit_finished_item_and_wait(self, page_idx, payload):
        self._item_applied_event.clear()
        append_log(
            self.batch_log_path,
            "FINISHED ITEM EMIT BEGIN",
            index=page_idx,
            payload_keys=list((payload or {}).keys()) if isinstance(payload, dict) else type(payload).__name__,
            memory=memory_text(),
        )
        self.finished_item.emit(page_idx, payload)
        append_log(self.batch_log_path, "FINISHED ITEM EMIT DONE", index=page_idx, memory=memory_text())
        self._wait_until_item_applied(page_idx)
        try:
            payload = None
            gc.collect()
        except Exception:
            pass

    def _write_bg_clean_as_source(self, page_idx, curr_data, fallback_path):
        if not curr_data.get('use_inpainted_as_source'):
            return fallback_path
        if curr_data.get('clean_path') and os.path.exists(str(curr_data.get('clean_path'))):
            return str(curr_data.get('clean_path'))
        if not curr_data.get('bg_clean'):
            return fallback_path
        root = self.project_dir or os.path.dirname(os.path.abspath(fallback_path))
        clean_dir = os.path.join(root, "clean")
        os.makedirs(clean_dir, exist_ok=True)
        out_path = os.path.join(clean_dir, f"batch_inpaint_source_{page_idx + 1:04d}.png")
        bg = curr_data.get('bg_clean')
        try:
            if isinstance(bg, (bytes, bytearray)):
                with open(out_path, "wb") as f:
                    f.write(bg)
                return out_path
            if isinstance(bg, np.ndarray):
                _imwrite_unicode(out_path, bg)
                return out_path
            if isinstance(bg, str) and os.path.exists(bg):
                return bg
        except Exception:
            return fallback_path
        return fallback_path

    def _output_display_stem(self, page_idx, path, curr_data):
        original = ""
        if isinstance(curr_data, dict):
            original = curr_data.get("original_name") or ""
        if not original:
            original = os.path.basename(str(path or f"page{page_idx + 1:03d}.png"))
        stem = _safe_page_file_stem(original, fallback=f"page{page_idx + 1:03d}")
        mode = _normalize_page_display_mode(getattr(self, "output_display_name_mode", DEFAULT_PAGE_DISPLAY_MODE))
        if mode == PAGE_DISPLAY_MODE_ORIGINAL:
            return stem
        if mode == PAGE_DISPLAY_MODE_PAGE_NUMBER:
            return f"page{page_idx + 1:03d}"
        return f"{page_idx + 1}p_{stem}"

    def _clean_original_stem(self, page_idx, path, curr_data):
        original = ""
        if isinstance(curr_data, dict):
            original = curr_data.get("original_name") or ""
        if not original:
            original = os.path.basename(str(path or f"page{page_idx + 1:03d}.png"))
        return _safe_page_file_stem(original, fallback=f"page{page_idx + 1:03d}")


    def _path_for_output_display(self, page_idx, path, curr_data):
        ext = os.path.splitext(str(path or ""))[1] or ".png"
        return os.path.join(os.path.dirname(os.path.abspath(str(path or os.getcwd()))), self._output_display_stem(page_idx, path, curr_data) + ext)

    def run(self):
        selected_indices = list(getattr(self, "page_indices", None) or range(len(self.paths)))
        total = len(selected_indices)

        visual_modes = {"analyze", "reanalyze", "translate", "inpaint"}
        append_log(
            self.batch_log_path,
            "BATCH RUN START",
            mode=self.mode,
            total=total,
            selected_indices=selected_indices[:50],
            memory=memory_text(),
        )

        for order_idx, i in enumerate(selected_indices):
            if not self.is_running:
                break
            if i < 0 or i >= len(self.paths):
                continue

            path = self.paths[i]
            curr_data = self._snapshot_page_for_mode(i, path)
            base_name = os.path.basename(path)
            prefix = f"[{order_idx + 1}/{total}]"
            _log_path_image_summary(self.batch_log_path, "PAGE START", path)
            append_log(
                self.batch_log_path,
                "PAGE CONTEXT",
                order=order_idx + 1,
                total=total,
                index=i,
                mode=self.mode,
                base_name=base_name,
                data_count=len(curr_data.get('data') or []),
                regions=len(curr_data.get('ocr_analysis_regions') or []),
                mask_merge=numpy_shape_text(curr_data.get('mask_merge')),
                mask_inpaint=numpy_shape_text(curr_data.get('mask_inpaint')),
                memory=memory_text(),
            )

            item_result_emitted = False
            try:
                payload = {}
                if self.mode in visual_modes:
                    append_log(self.batch_log_path, "ACTIVE ITEM EMIT BEGIN", index=i, mode=self.mode, memory=memory_text())
                    self.active_item.emit(i, self.mode)
                    append_log(self.batch_log_path, "ACTIVE ITEM EMIT DONE", index=i, mode=self.mode, memory=memory_text())

                if self.mode == 'analyze':
                    self.progress.emit(f"{prefix} 분석: {base_name}")
                    regions = copy.deepcopy(curr_data.get('ocr_analysis_regions', []) or [])
                    append_log(
                        self.batch_log_path,
                        "ANALYZE ENTER",
                        index=i,
                        provider=self.ocr_provider,
                        provider_name=self.ocr_provider_name,
                        regions=len(regions),
                        file_path=path,
                        memory=memory_text(),
                    )
                    o, d, mm, mi = self.engine.analyze_image(
                        path,
                        analysis_regions=regions,
                    )
                    append_log(
                        self.batch_log_path,
                        "ANALYZE DONE",
                        index=i,
                        boxes=len(d or []),
                        ori=numpy_shape_text(o),
                        mask_merge=numpy_shape_text(mm),
                        mask_inpaint=numpy_shape_text(mi),
                        memory=memory_text(),
                    )
                    payload = {
                        'ori': o,
                        'data': _copy_data_list(d),
                        'mask_merge': _copy_mask(mm),
                        'mask_inpaint': _copy_mask(mi),
                    }
                    append_log(
                        self.batch_log_path,
                        "ANALYZE PAYLOAD READY",
                        index=i,
                        data_count=len(payload.get('data') or []),
                        ori=numpy_shape_text(payload.get('ori')),
                        mask_merge=numpy_shape_text(payload.get('mask_merge')),
                        mask_inpaint=numpy_shape_text(payload.get('mask_inpaint')),
                        memory=memory_text(),
                    )

                elif self.mode == 'reanalyze':
                    self.progress.emit(f"{prefix} 재분석: {base_name}")
                    user_mask = _copy_mask(curr_data.get('mask_merge'))
                    if user_mask is None:
                        payload = {'_batch_status': 'skipped', '_batch_message': '텍스트 마스크 없음'}
                        self.progress.emit(f"{prefix} ⚠️ 재분석 건너뜀: 텍스트 마스크 없음")
                    else:
                        input_path = self._write_bg_clean_as_source(i, curr_data, path)
                        append_log(
                            self.batch_log_path,
                            "REANALYZE ENTER",
                            index=i,
                            provider=self.ocr_provider,
                            provider_name=self.ocr_provider_name,
                            file_path=input_path,
                            data_count=len(curr_data.get('data') or []),
                            mask_merge=numpy_shape_text(user_mask),
                            memory=memory_text(),
                        )
                        o, d, mm, mi = self.engine.reanalyze_from_manual_mask(
                            input_path,
                            user_mask,
                            _copy_data_list(curr_data.get('data', [])),
                        )
                        append_log(
                            self.batch_log_path,
                            "REANALYZE DONE",
                            index=i,
                            boxes=len(d or []),
                            ori=numpy_shape_text(o),
                            mask_merge=numpy_shape_text(mm),
                            mask_inpaint=numpy_shape_text(mi),
                            memory=memory_text(),
                        )
                        payload = {
                            'ori': o,
                            'data': d,
                            'mask_merge': mm,
                            'mask_inpaint': mi,
                            'mask_merge_off': curr_data.get('mask_merge_off'),
                            'mask_inpaint_off': curr_data.get('mask_inpaint_off'),
                            'mask_toggle_enabled': True,
                        }
                        self.progress.emit(f"{prefix} 재분석 완료")

                elif self.mode == 'translate':
                    if not curr_data.get('data'):
                        self.progress.emit(f"{prefix} 번역 건너뜀: 분석 데이터 없음")
                        self._emit_finished_item_and_wait(i, {'_batch_status': 'skipped', '_batch_message': '분석 데이터 없음'})
                        continue

                    self.progress.emit(f"{prefix} 번역: {base_name}")
                    append_log(self.batch_log_path, "TRANSLATE ENTER", index=i, provider=self.provider, data_count=len(curr_data.get('data') or []), memory=memory_text())
                    new_data = _copy_data_list(curr_data.get('data', []))
                    target_items = [item for item in new_data if item.get('use_inpaint', True)]

                    if not target_items:
                        self.progress.emit(f"{prefix} 번역 건너뜀: 체크된 항목 없음")
                        self._emit_finished_item_and_wait(i, {'_batch_status': 'skipped', '_batch_message': '체크된 항목 없음'})
                        continue

                    texts = [item.get('text', '') for item in target_items]
                    append_log(self.batch_log_path, "TRANSLATE REQUEST", index=i, target_count=len(target_items), memory=memory_text())
                    trans = self.engine.translate_text_batch(texts, provider=self.provider)
                    append_log(self.batch_log_path, "TRANSLATE RESPONSE", index=i, response_count=len(trans or []), memory=memory_text())

                    if len(trans) != len(target_items):
                        raise ValueError(f"번역 개수 불일치: 요청 {len(target_items)}개 / 응답 {len(trans)}개")

                    for item, t in zip(target_items, trans):
                        item['translated_text'] = str(t) if t is not None else ''

                    payload = {'data': new_data}
                    append_log(self.batch_log_path, "TRANSLATE PAYLOAD READY", index=i, data_count=len(new_data or []), memory=memory_text())

                elif self.mode == 'inpaint':
                    inpaint_data, inpaint_mask = _build_inpainting_payload(self.mask_toggle_enabled, curr_data)

                    if self.mask_toggle_enabled and not inpaint_data and inpaint_mask is None:
                        self.progress.emit(f"{prefix} 인페인팅 건너뜀: ON 분석/선택 마스크 없음")
                        self._emit_finished_item_and_wait(i, {'_batch_status': 'skipped', '_batch_message': 'ON 분석/선택 마스크 없음'})
                        continue
                    if (not self.mask_toggle_enabled) and inpaint_mask is None:
                        self.progress.emit(f"{prefix} 인페인팅 건너뜀: OFF 페인팅 마스크 없음")
                        self._emit_finished_item_and_wait(i, {'_batch_status': 'skipped', '_batch_message': 'OFF 페인팅 마스크 없음'})
                        continue

                    self.progress.emit(f"{prefix} 인페인팅 준비: {base_name}")
                    append_log(self.batch_log_path, "INPAINT ENTER", index=i, data_count=len(inpaint_data or []), mask=numpy_shape_text(inpaint_mask), memory=memory_text())

                    temp_cleanup_path = None
                    source_path = self._write_bg_clean_as_source(i, curr_data, path)
                    append_log(self.batch_log_path, "INPAINT SOURCE READY", index=i, source_path=source_path, memory=memory_text())
                    source_path, inpaint_mask, resize_note = _prepare_resized_inpaint_request(
                        self.project_dir,
                        i,
                        source_path,
                        inpaint_mask,
                        (self.batch_inpaint_resize_policy or {}).get('provider'),
                        self.batch_inpaint_resize_policy,
                    )
                    if resize_note:
                        temp_cleanup_path = source_path
                        self.progress.emit(f"{prefix} {resize_note}")
                        append_log(self.batch_log_path, "INPAINT RESIZE READY", index=i, source_path=source_path, mask=numpy_shape_text(inpaint_mask), memory=memory_text())
                    append_log(self.batch_log_path, "INPAINT REQUEST", index=i, source_path=source_path, resized=bool(resize_note), memory=memory_text())
                    self.progress.emit(f"{prefix} 인페인팅 실행")
                    res_url = self.engine.execute_inpainting(
                        source_path,
                        inpaint_data,
                        inpaint_mask
                    )

                    append_log(self.batch_log_path, "INPAINT RESPONSE", index=i, has_result=bool(res_url), memory=memory_text())
                    if res_url:
                        append_log(self.batch_log_path, "INPAINT DOWNLOAD ENTER", index=i, result_type=type(res_url).__name__, memory=memory_text())
                        bg_bytes = _download_replicate_output(res_url)
                        append_log(self.batch_log_path, "INPAINT DOWNLOAD DONE", index=i, bytes=format_bytes(len(bg_bytes or b'')), memory=memory_text())

                        curr_data['bg_clean'] = bg_bytes
                        payload = {'bg_clean': bg_bytes}

                        self.progress.emit(f"{prefix} 인페인팅 반영 대기")
                    else:
                        payload = {'_batch_status': 'failed', '_batch_message': '인페인팅 결과 없음'}
                        self.progress.emit(f"{prefix} ⚠️ 인페인팅 결과 없음")

                elif self.mode == 'refresh':
                    self.progress.emit(f"{prefix} 텍스트 갱신: {base_name}")
                    payload = {}

                elif self.mode == 'export':
                    self.progress.emit(f"{prefix} 출력: {base_name}")
                    append_log(self.batch_log_path, "EXPORT ENTER", index=i, data_count=len(curr_data.get('data') or []), memory=memory_text())
                    export_bg = curr_data.get('bg_clean')
                    if export_bg is None:
                        export_bg = path
                    self.engine.export_project_result(
                        curr_data.get('data', []),
                        path,
                        export_bg,
                        self.font_family,
                        self.stroke_size,
                        self.font_size,
                        output_root=self.project_dir,
                        output_name_stem=self._output_display_stem(i, path, curr_data),
                        clean_name_stem=self._clean_original_stem(i, path, curr_data),
                        output_image_format=self.output_image_format,
                        clean_image_format=self.clean_image_format,
                        output_image_quality=self.output_image_quality,
                        clean_image_quality=self.clean_image_quality,
                    )
                    payload = {}
                    append_log(self.batch_log_path, "EXPORT DONE", index=i, memory=memory_text())

                if isinstance(payload, dict) and '_batch_status' not in payload:
                    payload['_batch_status'] = 'done'
                    payload.setdefault('_batch_message', '')
                self._emit_finished_item_and_wait(i, payload)
                item_result_emitted = True
                if self.mode == 'inpaint':
                    append_log(self.batch_log_path, "INPAINT APPLY DONE", index=i, status=(payload or {}).get('_batch_status', 'done'), payload_message=(payload or {}).get('_batch_message', ''), memory=memory_text())
                    self.progress.emit(f"{prefix} 인페인팅 반영 완료")
                    try:
                        if _cleanup_temp_inpaint_request(locals().get('temp_cleanup_path')):
                            append_log(self.batch_log_path, "INPAINT TEMP CLEANUP", index=i, path=locals().get('temp_cleanup_path'), memory=memory_text())
                            self.progress.emit(f"{prefix} 임시 리사이즈 파일 정리")
                    except Exception:
                        pass
                    provider_wait = _get_batch_inpaint_wait_seconds(getattr(self, 'inpaint_provider', None))
                    if order_idx < total - 1 and provider_wait > 0:
                        append_log(self.batch_log_path, "INPAINT WAIT", index=i, seconds=provider_wait, memory=memory_text())
                        self.progress.emit(f"{prefix} 다음 페이지 전 {provider_wait:.1f}초 대기")
                        _sleep_interruptible(self, provider_wait)
                try:
                    curr_data = None
                    payload = None
                    gc.collect()
                except Exception:
                    pass
                if self.mode in visual_modes and order_idx < total - 1 and self.is_running:
                    # 페이지 단위 매크로이므로 다음 페이지 전환은 짧게만 쉰다.
                    time.sleep(0.15)

            except Exception as e:
                # If the page result has already been emitted/applied, a later diagnostic
                # log/cleanup/wait failure must not turn a successful page into a failed
                # page or increment progress twice.
                if item_result_emitted:
                    append_log(self.batch_log_path, "PAGE POST_APPLY EXCEPTION", index=i, error=repr(e), memory=memory_text())
                    append_block(self.batch_log_path, "POST_APPLY_TRACEBACK", exception_text(e))
                    try:
                        self.progress.emit(f"{prefix} ⚠️ 완료 후 정리 경고: {e}")
                    except Exception:
                        pass
                    continue
                append_log(self.batch_log_path, "PAGE EXCEPTION", index=i, error=repr(e), memory=memory_text())
                append_block(self.batch_log_path, "TRACEBACK", exception_text(e))
                self.progress.emit(f"{prefix} ❌ 에러: {e}")
                try:
                    if self.mode == 'inpaint' and _cleanup_temp_inpaint_request(locals().get('temp_cleanup_path')):
                        append_log(self.batch_log_path, "INPAINT TEMP CLEANUP", index=i, path=locals().get('temp_cleanup_path'), reason='exception', memory=memory_text())
                        self.progress.emit(f"{prefix} 임시 리사이즈 파일 정리")
                except Exception:
                    pass
                try:
                    self._emit_finished_item_and_wait(i, {'_batch_status': 'failed', '_batch_message': str(e)})
                except Exception:
                    pass

        append_log(self.batch_log_path, "BATCH LOOP END", mode=self.mode, running=self.is_running, memory=memory_text())
        if self.is_running:
            self.progress.emit(f"✅ 일괄 {self.mode} 완료!")
        else:
            self.progress.emit(f"⏹️ 일괄 {self.mode} 취소 요청 반영: 현재 항목 완료 후 중단")
        append_log(self.batch_log_path, "BATCH FINISHED_ALL EMIT", mode=self.mode, memory=memory_text())
        self.finished_all.emit()

    def stop(self):
        self.is_running = False


class AnalysisWorker(QThread):
    finished = pyqtSignal(object, object, object, object)
    log = pyqtSignal(str)

    def __init__(self, engine, path, mask=None, data=None, analysis_regions=None):
        super().__init__()
        self.engine = engine
        self.path = path
        self.mask = _copy_mask(mask)
        self.data = _copy_data_list(data)
        self.analysis_regions = copy.deepcopy(analysis_regions or [])
        self.analysis_log_path = make_log_path("single_analyze")
        self.cancel_requested = False

    def stop(self):
        self.cancel_requested = True

    def run(self):
        try:
            _log_path_image_summary(self.analysis_log_path, "SINGLE ANALYZE START", self.path)
            append_log(self.analysis_log_path, "SINGLE ANALYZE CONTEXT", mask=numpy_shape_text(self.mask), data_count=len(self.data or []), regions=len(self.analysis_regions or []), memory=memory_text())
            try:
                from ysb.engine.manga_engine import Config
                provider = str(getattr(Config, "OCR_PROVIDER", "clova") or "clova")
                if provider == "google_vision":
                    provider_name = "Google Vision"
                elif provider == "local_paddle_ocr":
                    provider_name = "LOCAL Paddle OCR"
                elif provider == "local_manga_ocr":
                    provider_name = "LOCAL Manga OCR"
                else:
                    provider_name = "CLOVA"
            except Exception:
                provider_name = "OCR"

            if self.mask is not None:
                self.log.emit(f"🔄 {provider_name} OCR로 영역 재분석 중...")
                o, d, mm, mi = self.engine.reanalyze_from_manual_mask(self.path, self.mask, self.data)
            else:
                if self.analysis_regions:
                    self.log.emit(f"🚀 {provider_name} 지정 범위 분석 시작... ({len(self.analysis_regions)}개 영역)")
                else:
                    self.log.emit(f"🚀 {provider_name} 전체 분석 시작...")
                o, d, mm, mi = self.engine.analyze_image(self.path, analysis_regions=self.analysis_regions)
            append_log(self.analysis_log_path, "SINGLE ANALYZE DONE", boxes=len(d or []), ori=numpy_shape_text(o), mask_merge=numpy_shape_text(mm), mask_inpaint=numpy_shape_text(mi), memory=memory_text())
            self.log.emit(f"✅ 완료 ({len(d)}개)")
            self.finished.emit(o, d, _copy_mask(mm), _copy_mask(mi))
        except Exception as e:
            import traceback
            append_log(self.analysis_log_path, "SINGLE ANALYZE EXCEPTION", error=repr(e), memory=memory_text())
            append_block(self.analysis_log_path, "TRACEBACK", exception_text(e))
            traceback.print_exc()
            self.log.emit(f"❌ 오류: {e}")



class QuickOCRWorker(QThread):
    finished = pyqtSignal(str, object)
    log = pyqtSignal(str)

    def __init__(self, engine, path, rect_norm, provider=None, language=None):
        super().__init__()
        self.engine = engine
        self.path = path
        self.rect_norm = copy.deepcopy(rect_norm or [])
        self.provider = provider
        self.language = language

    def run(self):
        try:
            text = self.engine.quick_ocr_image_region(
                self.path,
                self.rect_norm,
                provider=self.provider,
                language=self.language,
            )
            self.finished.emit(text or "", None)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.log.emit(f"❌ 빠른 OCR 오류: {e}")
            self.finished.emit("", str(e))


class InpaintWorker(QThread):
    finished = pyqtSignal(int, object)
    log = pyqtSignal(str)

    def __init__(self, engine, path, data, mask, page_idx=-1, cleanup_path=None):
        super().__init__()
        self.engine = engine
        self.path = path
        self.data = _copy_data_list(data)
        self.mask = _copy_mask(mask)
        try:
            self.page_idx = int(page_idx)
        except Exception:
            self.page_idx = -1
        self.inpaint_log_path = make_log_path("single_inpaint")
        self.cancel_requested = False
        self.cleanup_path = str(cleanup_path) if cleanup_path else None

    def stop(self):
        self.cancel_requested = True

    def run(self):
        try:
            _log_path_image_summary(self.inpaint_log_path, "SINGLE INPAINT START", self.path)
            try:
                mask_nonzero = int(np.count_nonzero(self.mask)) if self.mask is not None else 0
            except Exception:
                mask_nonzero = -1
            append_log(self.inpaint_log_path, "SINGLE INPAINT CONTEXT", page_idx=self.page_idx, mask=numpy_shape_text(self.mask), mask_nonzero=mask_nonzero, data_count=len(self.data or []), memory=memory_text())
            try:
                from ysb.engine.manga_engine import Config
                provider = str(getattr(Config, "INPAINT_PROVIDER", "replicate_lama") or "replicate_lama")
                if provider == "replicate_stable":
                    provider_name = "Stable Diffusion"
                elif provider == "gemini_inpaint":
                    provider_name = "Gemini"
                elif provider == "local_lama":
                    provider_name = "LOCAL LaMa"
                elif provider == "local_sdxl_lightning":
                    provider_name = "LOCAL SDXL Lightning"
                else:
                    provider_name = "LaMa"
            except Exception:
                provider = "unknown"
                provider_name = "인페인팅"
            append_log(self.inpaint_log_path, "SINGLE INPAINT PROVIDER", page_idx=self.page_idx, provider=provider, provider_name=provider_name, memory=memory_text())
            self.log.emit(f"🎨 {provider_name} 인페인팅 시작...")
            res = self.engine.execute_inpainting(self.path, self.data, self.mask)
            if res:
                img_data = _download_replicate_output(res)
                append_log(self.inpaint_log_path, "SINGLE INPAINT DONE", page_idx=self.page_idx, bytes=len(img_data or b""), memory=memory_text())
                self.finished.emit(self.page_idx, img_data)
            else:
                append_log(self.inpaint_log_path, "SINGLE INPAINT EMPTY_RESULT", page_idx=self.page_idx, memory=memory_text())
                self.log.emit("❌ 실패: 인페인팅 결과가 비어 있습니다. 자세한 원인은 single_inpaint 로그의 EXCEPTION/PROVIDER 항목을 확인해 주세요.")
                self.finished.emit(self.page_idx, b"")
        except Exception as e:
            append_log(self.inpaint_log_path, "SINGLE INPAINT EXCEPTION", page_idx=self.page_idx, error=repr(e), memory=memory_text())
            append_block(self.inpaint_log_path, "TRACEBACK", exception_text(e))
            self.log.emit(f"❌ 오류 발생: {e}")
            self.finished.emit(self.page_idx, b"")
        finally:
            if _cleanup_temp_inpaint_request(self.cleanup_path):
                append_log(self.inpaint_log_path, "SINGLE INPAINT TEMP CLEANUP", page_idx=self.page_idx, path=self.cleanup_path, memory=memory_text())
                self.log.emit(f"🧹 임시 인페인팅 입력 정리: {os.path.basename(self.cleanup_path)}")


class TranslationWorker(QThread):
    progress = pyqtSignal(str, int, int)  # detail, current, total
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    canceled = pyqtSignal(object)

    def __init__(self, engine, texts, provider="openai", chunk_size=20):
        super().__init__()
        self.engine = engine
        self.texts = [str(t or "") for t in (texts or [])]
        self.provider = provider or "openai"
        try:
            self.chunk_size = max(1, min(int(chunk_size or 20), 100))
        except Exception:
            self.chunk_size = 20
        self.cancel_requested = False

    def stop(self):
        self.cancel_requested = True

    def run(self):
        total = len(self.texts)
        results = []
        try:
            if total <= 0:
                self.finished.emit([])
                return
            for start in range(0, total, self.chunk_size):
                if self.cancel_requested:
                    self.canceled.emit(results)
                    return
                end = min(total, start + self.chunk_size)
                self.progress.emit(f"번역 중: {start + 1}-{end} / {total}", start, total)
                chunk = self.texts[start:end]
                translated = self.engine.translate_text_batch(
                    chunk,
                    provider=self.provider,
                    chunk_size=len(chunk),
                )
                if translated is None:
                    translated = []
                translated = list(translated)
                if len(translated) < len(chunk):
                    translated.extend(chunk[len(translated):])
                elif len(translated) > len(chunk):
                    translated = translated[:len(chunk)]
                results.extend(translated)
                self.progress.emit(f"번역 완료: {end} / {total}", end, total)
                if self.cancel_requested:
                    self.canceled.emit(results)
                    return
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))
