import os
import re
import copy
import cv2
import numpy as np
import requests
import time
import threading
import gc
import sys
import contextlib
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
from ysb.core.inpaint_grouping import build_inpaint_mask_groups


def _log_output_event_enabled(event_name, default=True):
    """Return whether a standalone worker log event should be written.

    UI audit logs go through MainWindow.audit_boundary_event, but AnalysisWorker
    writes to its own single_analyze_*.log file and therefore has to read the
    same log_output_settings.json directly.  Best-effort only: logging must not
    break analysis.
    """
    try:
        from ysb.core.log_options import (
            is_log_event_enabled,
            load_log_output_settings,
            log_output_enabled_map_from_settings,
            log_output_unregistered_from_settings,
        )
        settings = load_log_output_settings()
        enabled_map = log_output_enabled_map_from_settings(settings)
        unregistered = log_output_unregistered_from_settings(settings)
        return bool(is_log_event_enabled(str(event_name or ''), enabled_map, unregistered_enabled=unregistered))
    except Exception:
        return bool(default)


def _append_worker_log_if_enabled(path, event_name, **fields):
    try:
        if _log_output_event_enabled(event_name, default=True):
            append_log(path, event_name, **fields)
    except Exception:
        pass


def _safe_short_text(value, limit=120):
    try:
        text = str(value or '')
    except Exception:
        text = ''
    text = text.replace('\n', '\\n').replace('\r', '\\r')
    if len(text) > int(limit):
        return text[:max(0, int(limit) - 3)] + '...'
    return text


def _rect_ratio_text(rect):
    try:
        _x, _y, w, h = [float(v) for v in (rect or [0, 0, 0, 0])[:4]]
        if w <= 0 or h <= 0:
            return '0.00'
        return f"{h / max(1.0, w):.3f}"
    except Exception:
        return 'unknown'


def _list_count(value):
    try:
        return len(value or [])
    except Exception:
        return 0

def _analysis_status_from_console_line(line):
    """Convert noisy engine console output into one compact progress-panel status.

    The full stdout is still written to the normal log/console.  The progress
    overlay should show only the current meaningful state, because the panel is
    small and users need to know what is happening now, not read a full console.
    Returns (percent_or_None, detail_or_None).
    """
    text = str(line or "").strip()
    if not text:
        return None, None
    text = re.sub(r"^>+\s*", "", text).strip()
    if "[Local OCR]" in text:
        body = text.split("[Local OCR]", 1)[1].strip()
        if "comic_text_detector 마스크 분석" in body:
            target = body.split(":", 1)[1].strip() if ":" in body else "현재 이미지"
            return 28, f"현재 작업: 텍스트 디텍터 마스크 분석 중\n대상: {target}"
        if "text-mask component based" in body:
            m = re.search(r"groups=(\d+).*components=(\d+).*matched_groups=(\d+)", body)
            if m:
                return 42, f"현재 작업: 텍스트 영역 후보 정리 중\n검출 그룹 {m.group(1)}개 / 컴포넌트 {m.group(2)}개 / 매칭 {m.group(3)}개"
            return 42, "현재 작업: 텍스트 영역 후보 정리 중"
        if "PaddleOCR full-page fallback applied" in body:
            m = re.search(r"ok=(\d+)", body)
            return 64, f"현재 작업: PaddleOCR 전체 페이지 인식 결과 적용 중\n성공 영역: {m.group(1)}개" if m else "현재 작업: PaddleOCR 전체 페이지 인식 결과 적용 중"
        if "PaddleOCR full-page fallback failed" in body:
            err = body.split(":", 1)[1].strip() if ":" in body else body
            return 64, f"현재 작업: PaddleOCR 전체 페이지 fallback 실패\n원인: {_safe_short_text(err, 120)}"
        if "PaddleOCR text recognition" in body:
            m = re.search(r"ok=(\d+),\s*errors=(\d+),\s*groups=(\d+)", body)
            if m:
                return 78, f"현재 작업: PaddleOCR 영역별 인식 정리 중\nOCR 성공 {m.group(1)}개 / 오류 {m.group(2)}개 / 그룹 {m.group(3)}개"
            return 78, "현재 작업: PaddleOCR 영역별 인식 정리 중"
        if "Manga OCR text recognition" in body:
            m = re.search(r"ok=(\d+),\s*errors=(\d+),\s*groups=(\d+)", body)
            if m:
                return 78, f"현재 작업: Manga OCR 영역별 인식 정리 중\nOCR 성공 {m.group(1)}개 / 오류 {m.group(2)}개 / 그룹 {m.group(3)}개"
            return 78, "현재 작업: Manga OCR 영역별 인식 정리 중"
        if "comic_text_detector blocks=" in body:
            m = re.search(r"blocks=(\d+),\s*safe_blocks=(\d+),\s*safe_lines=(\d+).*paint_mask_pixels=(\d+)", body)
            if m:
                return 55, f"현재 작업: 감지 마스크/인페인팅 마스크 생성 중\n블록 {m.group(1)}개 / 안전 블록 {m.group(2)}개 / 페인트 마스크 {m.group(4)}px"
            return 55, "현재 작업: 감지 마스크/인페인팅 마스크 생성 중"
        if "sample errors" in body:
            err = body.split(":", 1)[1].strip() if ":" in body else body
            return None, f"참고 오류: {_safe_short_text(err, 140)}"
        return None, f"현재 작업: {_safe_short_text(body, 180)}"
    if "[Local Inpaint]" in text:
        body = text.split("[Local Inpaint]", 1)[1].strip()
        if "LOCAL LaMa device" in body:
            requested = re.search(r"requested=([^,]+)", body)
            resolved = re.search(r"resolved=([^,]+)", body)
            model = re.search(r"model=([^,]+)", body)
            gpu = re.search(r"gpu=(.*)$", body)
            req = requested.group(1).strip() if requested else "auto"
            res = resolved.group(1).strip() if resolved else "unknown"
            mdl = model.group(1).strip() if model else "unknown"
            gpu_name = (gpu.group(1).strip() if gpu else "") or "-"
            return 48, f"현재 작업: LOCAL LaMa 실행 장치 확인\n요청 {req} / 실제 {res} / 모델 {mdl} / GPU {gpu_name}"
        if "Loading" in body:
            return 35, "현재 작업: LOCAL LaMa 모델 로딩 중"
        if "Running" in body:
            return 65, "현재 작업: LOCAL LaMa 인페인팅 실행 중"
        if "model" in body.lower():
            return 25, f"현재 작업: LOCAL LaMa 모델 확인 중\n{_safe_short_text(body, 150)}"
        return None, f"현재 작업: {_safe_short_text(body, 180)}"
    return None, None


class _ProgressTeeStream:
    """Tee stdout/stderr to the real console and emit concise progress updates."""

    def __init__(self, original, emit_func):
        self._original = original
        self._emit = emit_func
        self._buffer = ""

    def write(self, data):
        try:
            if self._original is not None:
                self._original.write(data)
                self._original.flush()
        except Exception:
            pass
        if not data:
            return 0
        self._buffer += str(data)
        pieces = re.split(r"[\r\n]+", self._buffer)
        self._buffer = pieces[-1] if pieces else ""
        for piece in pieces[:-1]:
            piece = piece.strip()
            if not piece:
                continue
            pct, detail = _analysis_status_from_console_line(piece)
            if detail:
                try:
                    if pct is None:
                        self._emit(detail)
                    else:
                        self._emit(f"YSB_PROGRESS|{int(pct)}|{detail}")
                except Exception:
                    pass
        return len(data)

    def flush(self):
        try:
            if self._original is not None:
                self._original.flush()
        except Exception:
            pass


def _summarize_ocr_item_payload(item):
    try:
        it = dict(item or {})
    except Exception:
        it = {}
    out = {}
    for key in ('text', 'rect', 'vertices', 'cx', 'cy', 'stroke_size', 'char_count', 'source_provider', 'locale', 'detected_break', 'order_index', 'confidence'):
        if key in it:
            out[key] = it.get(key)
    return out




def _safe_rect4(value):
    try:
        vals = list(value or [])
        if len(vals) < 4:
            return None
        x, y, w, h = [float(v) for v in vals[:4]]
        if w <= 0 or h <= 0:
            return None
        return [x, y, w, h]
    except Exception:
        return None


def _effective_layout_char_count(text):
    """OCR layout scoring count.

    세로쓰기 한 줄 판정은 rect_h_over_w가 글자 수와 비슷한지를 본다.
    문장부호/공백은 실제 글자칸을 덜 차지하므로 낮은 가중치로 계산한다.
    """
    try:
        raw = str(text or '')
    except Exception:
        raw = ''
    if not raw:
        return 0.0
    punct_light = set('。、，,.．・:：;；!！?？"\'“”‘’「」『』（）()[]【】〈〉《》…ー~〜-')
    total = 0.0
    for ch in raw:
        if ch.isspace():
            total += 0.25
        elif ch in punct_light:
            total += 0.55
        elif ord(ch) < 128:
            total += 0.72
        else:
            total += 1.0
    return max(0.0, total)


def _ocr_item_signature(item):
    if not isinstance(item, dict):
        return None
    return (str(item.get('text') or ''), tuple(int(round(float(v))) for v in (item.get('rect') or [])[:4]))


def _main_ocr_layout_item(row):
    """Backward-compatible largest non-ruby OCR piece selector.

    Earlier builds used this single piece for orientation scoring.  Keep the
    helper for diagnostics/fallbacks, but the actual layout tagger below must
    score the whole non-ruby OCR group, not just this representative piece.
    """
    items = _non_ruby_ocr_layout_items(row)
    if items:
        def _area(it):
            rect = _safe_rect4((it or {}).get('rect')) or [0, 0, 0, 0]
            return float(rect[2]) * float(rect[3])
        return sorted(items, key=_area, reverse=True)[0]
    if isinstance(row, dict):
        rect = _safe_rect4(row.get('rect'))
        text = str(row.get('text') or '')
        if rect and text.strip():
            return {'text': text, 'rect': rect, 'vertices': (row.get('vertices_list') or [None])[0] if row.get('vertices_list') else None, 'char_count': len(text)}
    return None


def _non_ruby_ocr_layout_items(row):
    """Return OCR pieces that should participate in main-text layout scoring."""
    if not isinstance(row, dict):
        return []
    raw_items = list(row.get('ocr_items_all') or row.get('ocr_items') or [])
    ruby_sigs = set()
    for rb in list(row.get('ruby_ocr_items') or []):
        sig = _ocr_item_signature(rb)
        if sig is not None:
            ruby_sigs.add(sig)
    items = []
    for it in raw_items:
        if not isinstance(it, dict):
            continue
        sig = _ocr_item_signature(it)
        if sig is not None and sig in ruby_sigs:
            continue
        rect = _safe_rect4(it.get('rect'))
        if not rect:
            continue
        txt = str(it.get('text') or '')
        if not txt.strip():
            continue
        items.append(it)
    return items


def _union_rect4_from_rects(rects):
    good = []
    for rect in rects or []:
        r = _safe_rect4(rect)
        if r:
            good.append(r)
    if not good:
        return None
    x1 = min(r[0] for r in good)
    y1 = min(r[1] for r in good)
    x2 = max(r[0] + r[2] for r in good)
    y2 = max(r[1] + r[3] for r in good)
    return [x1, y1, max(1.0, x2 - x1), max(1.0, y2 - y1)]


def _median_float(values, default=0.0):
    vals = sorted(float(v) for v in (values or []) if v is not None)
    if not vals:
        return float(default)
    mid = len(vals) // 2
    if len(vals) % 2:
        return float(vals[mid])
    return (float(vals[mid - 1]) + float(vals[mid])) / 2.0


def _combined_non_ruby_text(row, items):
    """Text count for a full OCR group.

    OCR providers may return a whole long string as one item, or split a single
    OCR region into several vertical columns/pieces.  The vertical one-column
    decision must count every visible main-text character in the whole group.
    """
    parts = []
    for it in list(items or []):
        if isinstance(it, dict):
            t = str(it.get('text') or '')
            if t.strip():
                parts.append(t)
    text = ''.join(parts).strip()
    if text:
        return text
    try:
        return str((row or {}).get('text') or '').strip()
    except Exception:
        return ''


def _score_ocr_layout_orientation(text, rect):
    rect = _safe_rect4(rect)
    if not rect:
        return {'hint': 'unknown', 'axis': 'unknown', 'confidence': 0.0, 'reason': 'no_rect'}
    x, y, w, h = rect
    raw_text = str(text or '')
    effective_count = _effective_layout_char_count(raw_text)
    visible_count = len([ch for ch in raw_text if not ch.isspace()])
    if effective_count < 2.0 or visible_count < 2:
        return {'hint': 'unknown', 'axis': 'unknown', 'confidence': 0.0, 'reason': 'too_short', 'effective_char_count': round(effective_count, 3), 'visible_char_count': visible_count}
    h_over_w = h / max(1.0, w)
    w_over_h = w / max(1.0, h)
    vertical_score = h_over_w / max(1.0, effective_count)
    horizontal_score = w_over_h / max(1.0, effective_count)

    # 세로쓰기 한 줄: 글자칸이 위아래로 쌓이므로 h/w가 전체 글자 수와 대략 비슷하다.
    vertical = bool(visible_count >= 3 and h_over_w >= 2.75 and 0.42 <= vertical_score <= 1.75)
    horizontal = bool(visible_count >= 2 and w_over_h >= 1.35 and 0.32 <= horizontal_score <= 1.95)

    if vertical:
        closeness = max(0.0, 1.0 - min(1.0, abs(vertical_score - 1.0) / 0.85))
        ratio_bonus = min(0.22, max(0.0, (h_over_w - 2.75) / 18.0))
        confidence = min(0.99, max(0.70, 0.72 + closeness * 0.20 + ratio_bonus))
        return {
            'hint': 'vertical_single_column',
            'axis': 'vertical',
            'confidence': round(confidence, 4),
            'reason': 'char_count_rect_ratio_vertical_single_column',
            'rect_h_over_w': round(h_over_w, 4),
            'rect_w_over_h': round(w_over_h, 4),
            'effective_char_count': round(effective_count, 3),
            'visible_char_count': int(visible_count),
            'vertical_score': round(vertical_score, 4),
            'horizontal_score': round(horizontal_score, 4),
        }
    if horizontal:
        closeness = max(0.0, 1.0 - min(1.0, abs(horizontal_score - 1.0) / 0.95))
        confidence = min(0.98, max(0.62, 0.65 + closeness * 0.20))
        return {
            'hint': 'horizontal_single_line',
            'axis': 'horizontal',
            'confidence': round(confidence, 4),
            'reason': 'char_count_rect_ratio_horizontal_single_line',
            'rect_h_over_w': round(h_over_w, 4),
            'rect_w_over_h': round(w_over_h, 4),
            'effective_char_count': round(effective_count, 3),
            'visible_char_count': int(visible_count),
            'vertical_score': round(vertical_score, 4),
            'horizontal_score': round(horizontal_score, 4),
        }
    return {
        'hint': 'unknown',
        'axis': 'unknown',
        'confidence': 0.0,
        'reason': 'ratio_not_decisive',
        'rect_h_over_w': round(h_over_w, 4),
        'rect_w_over_h': round(w_over_h, 4),
        'effective_char_count': round(effective_count, 3),
        'visible_char_count': int(visible_count),
        'vertical_score': round(vertical_score, 4),
        'horizontal_score': round(horizontal_score, 4),
    }


def _score_ocr_layout_group(row):
    """Score OCR layout using the whole main-text group.

    세로쓰기 자동 적용은 한국어식 '한 세로 열'만 대상으로 한다.  따라서 OCR 조각
    하나가 세로로 길다는 이유만으로 전체 영역을 vertical_single_column으로 태깅하지
    않는다.  여러 OCR 조각이 있으면 전체 non-ruby 글자 수, 전체 union rect, 그리고
    X축이 한 열로 정렬됐는지를 함께 본다.
    """
    if not isinstance(row, dict):
        return {'hint': 'unknown', 'axis': 'unknown', 'confidence': 0.0, 'reason': 'invalid_row'}
    items = _non_ruby_ocr_layout_items(row)
    if items:
        rect = _union_rect4_from_rects([(it or {}).get('rect') for it in items])
        text = _combined_non_ruby_text(row, items)
    else:
        rect = _safe_rect4(row.get('rect'))
        text = str(row.get('text') or '').strip()
    if not rect or not text:
        return {'hint': 'unknown', 'axis': 'unknown', 'confidence': 0.0, 'reason': 'no_group_rect_or_text'}

    item_count = len(items)
    score = _score_ocr_layout_orientation(text, rect)
    score['group_item_count'] = int(item_count)
    score['group_text'] = text
    score['group_rect'] = [int(round(float(v))) for v in rect[:4]]

    if item_count >= 2:
        centers_x = []
        centers_y = []
        widths = []
        heights = []
        verticalish_count = 0
        for it in items:
            r = _safe_rect4((it or {}).get('rect'))
            if not r:
                continue
            x, y, w, h = r
            centers_x.append(x + w / 2.0)
            centers_y.append(y + h / 2.0)
            widths.append(w)
            heights.append(h)
            if h / max(1.0, w) >= 1.55:
                verticalish_count += 1
        x_span = (max(centers_x) - min(centers_x)) if centers_x else 0.0
        y_span = (max(centers_y) - min(centers_y)) if centers_y else 0.0
        median_w = _median_float(widths, default=rect[2])
        median_h = _median_float(heights, default=rect[3])
        # 같은 세로열 안에서 OCR이 여러 조각으로 잘린 경우만 허용한다.
        # 여러 세로열이면 center_x가 글자폭 이상으로 벌어진다.
        same_column_limit = max(18.0, median_w * 0.90)
        same_column = bool(x_span <= same_column_limit)
        score['group_center_x_span'] = round(float(x_span), 3)
        score['group_center_y_span'] = round(float(y_span), 3)
        score['group_median_item_w'] = round(float(median_w), 3)
        score['group_median_item_h'] = round(float(median_h), 3)
        score['group_same_column'] = bool(same_column)
        score['group_verticalish_item_count'] = int(verticalish_count)

        if score.get('hint') == 'vertical_single_column' and not same_column:
            # 일본어 세로 원문이 여러 열로 묶인 말풍선이다.  세로 계열 후보라는 정보는
            # 남기되, 한국어 자동 세로쓰기 한 줄 적용 대상은 아니다.
            score['hint'] = 'vertical_multi_column'
            score['axis'] = 'vertical'
            score['confidence'] = 0.0
            score['reason'] = 'multi_ocr_items_not_same_column'
        elif score.get('hint') == 'vertical_single_column':
            score['reason'] = 'group_char_count_rect_ratio_vertical_single_column'
        elif verticalish_count >= max(2, item_count // 2 + 1) and not same_column:
            score['hint'] = 'vertical_multi_column'
            score['axis'] = 'vertical'
            score['confidence'] = 0.0
            score['reason'] = 'multi_column_vertical_text_not_single_column'
        elif score.get('hint') == 'horizontal_single_line':
            score['reason'] = 'group_char_count_rect_ratio_horizontal_single_line'
    else:
        score['group_center_x_span'] = 0.0
        score['group_center_y_span'] = 0.0
        score['group_same_column'] = True if item_count == 1 else None
        if score.get('hint') == 'vertical_single_column':
            score['reason'] = 'single_ocr_item_char_count_rect_ratio_vertical_single_column'
        elif score.get('hint') == 'horizontal_single_line':
            score['reason'] = 'single_ocr_item_char_count_rect_ratio_horizontal_single_line'
    return score

def tag_ocr_layout_candidates(data):
    """Tag analysis rows with OCR layout orientation candidates.

    This does not change user-facing writing_direction. It only stores evidence that
    later auto text adjustment can use when its vertical auto-apply option is on.
    """
    try:
        rows = list(data or [])
    except Exception:
        return data
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            score = _score_ocr_layout_group(row)
            row['ocr_layout_hint'] = score.get('hint', 'unknown')
            row['ocr_layout_axis'] = score.get('axis', 'unknown')
            row['ocr_layout_confidence'] = float(score.get('confidence', 0.0) or 0.0)
            row['ocr_layout_policy'] = 'group_char_count_rect_ratio'
            row['ocr_layout_reason'] = score.get('reason')
            row['ocr_layout_main_text'] = score.get('group_text') or str(row.get('text') or '')
            row['ocr_layout_main_rect'] = score.get('group_rect') or []
            row['ocr_layout_effective_char_count'] = score.get('effective_char_count')
            row['ocr_layout_visible_char_count'] = score.get('visible_char_count')
            row['ocr_layout_rect_h_over_w'] = score.get('rect_h_over_w')
            row['ocr_layout_rect_w_over_h'] = score.get('rect_w_over_h')
            row['ocr_layout_vertical_score'] = score.get('vertical_score')
            row['ocr_layout_horizontal_score'] = score.get('horizontal_score')
            row['ocr_layout_group_item_count'] = score.get('group_item_count')
            row['ocr_layout_group_center_x_span'] = score.get('group_center_x_span')
            row['ocr_layout_group_center_y_span'] = score.get('group_center_y_span')
            row['ocr_layout_group_median_item_w'] = score.get('group_median_item_w')
            row['ocr_layout_group_median_item_h'] = score.get('group_median_item_h')
            row['ocr_layout_group_same_column'] = score.get('group_same_column')
            row['ocr_layout_group_verticalish_item_count'] = score.get('group_verticalish_item_count')
        except Exception:
            try:
                row['ocr_layout_hint'] = 'unknown'
                row['ocr_layout_axis'] = 'unknown'
                row['ocr_layout_confidence'] = 0.0
                row['ocr_layout_reason'] = 'exception'
            except Exception:
                pass
    return data

def _append_single_analyze_data_detail_logs(log_path, data):
    """Write togglable per-box/per-OCR-item logs for single analysis results.

    This is the quickest way to verify whether an OCR provider preserves token
    coordinates that can later be used for vertical-writing detection.
    """
    try:
        rows = list(data or [])
    except Exception:
        rows = []
    try:
        total_ocr_all = sum(_list_count((row or {}).get('ocr_items_all')) for row in rows if isinstance(row, dict))
        total_ocr_main = sum(_list_count((row or {}).get('ocr_items')) for row in rows if isinstance(row, dict))
        total_ruby = sum(_list_count((row or {}).get('ruby_ocr_items')) for row in rows if isinstance(row, dict))
        all_keys = []
        for row in rows[:12]:
            if isinstance(row, dict):
                for key in row.keys():
                    if key not in all_keys:
                        all_keys.append(str(key))
        _append_worker_log_if_enabled(
            log_path,
            'SINGLE_ANALYZE_DATA_SUMMARY',
            boxes=len(rows),
            ocr_items=total_ocr_main,
            ocr_items_all=total_ocr_all,
            ruby_ocr_items=total_ruby,
            sample_keys=all_keys[:80],
            memory=memory_text(),
        )
        detector_row = None
        for row in rows:
            if isinstance(row, dict) and (row.get('detector_device_requested') or row.get('detector_device_resolved') or row.get('detector_device_actual')):
                detector_row = row
                break
        if detector_row:
            _append_worker_log_if_enabled(
                log_path,
                'SINGLE_ANALYZE_DETECTOR_DEVICE',
                requested=detector_row.get('detector_device_requested'),
                resolved=detector_row.get('detector_device_resolved'),
                actual=detector_row.get('detector_device_actual'),
                model_device=detector_row.get('detector_model_device'),
                cuda_available=detector_row.get('detector_cuda_available'),
                cuda_count=detector_row.get('detector_cuda_count'),
                cuda_gpu=detector_row.get('detector_cuda_gpu'),
                worker_python=detector_row.get('detector_worker_python'),
                memory=memory_text(),
            )
    except Exception:
        pass

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            _append_worker_log_if_enabled(log_path, 'SINGLE_ANALYZE_BOX_DETAIL', index=idx, row_type=type(row).__name__, memory=memory_text())
            continue
        try:
            rect = row.get('rect') or row.get('text_mask_rect') or row.get('mask_rect') or []
            keys = sorted([str(k) for k in row.keys()])
            flags = []
            for key in ('local_detector_only', 'local_mask_aligned_rect', 'protected_fallback', 'use_inpaint'):
                if key in row:
                    flags.append(f"{key}={row.get(key)}")
            _append_worker_log_if_enabled(
                log_path,
                'SINGLE_ANALYZE_BOX_DETAIL',
                index=idx,
                id=row.get('id'),
                text=_safe_short_text(row.get('text'), 160),
                translated_text=_safe_short_text(row.get('translated_text'), 80),
                rect=rect,
                rect_h_over_w=_rect_ratio_text(rect),
                vertices_list_count=_list_count(row.get('vertices_list')),
                ocr_items_count=_list_count(row.get('ocr_items')),
                ocr_items_all_count=_list_count(row.get('ocr_items_all')),
                ruby_ocr_items_count=_list_count(row.get('ruby_ocr_items')),
                ocr_lang=row.get('ocr_lang'),
                ocr_engine=row.get('ocr_engine'),
                detector_engine=row.get('detector_engine'),
                detector_device_requested=row.get('detector_device_requested'),
                detector_device_resolved=row.get('detector_device_resolved'),
                detector_device_actual=row.get('detector_device_actual'),
                detector_model_device=row.get('detector_model_device'),
                detector_cuda_available=row.get('detector_cuda_available'),
                detector_cuda_count=row.get('detector_cuda_count'),
                detector_cuda_gpu=row.get('detector_cuda_gpu'),
                avg_stroke=row.get('avg_stroke'),
                ocr_layout_hint=row.get('ocr_layout_hint'),
                ocr_layout_axis=row.get('ocr_layout_axis'),
                ocr_layout_confidence=row.get('ocr_layout_confidence'),
                ocr_layout_reason=row.get('ocr_layout_reason'),
                ocr_layout_effective_char_count=row.get('ocr_layout_effective_char_count'),
                ocr_layout_visible_char_count=row.get('ocr_layout_visible_char_count'),
                ocr_layout_rect_h_over_w=row.get('ocr_layout_rect_h_over_w'),
                ocr_layout_vertical_score=row.get('ocr_layout_vertical_score'),
                ocr_layout_group_item_count=row.get('ocr_layout_group_item_count'),
                ocr_layout_group_same_column=row.get('ocr_layout_group_same_column'),
                ocr_layout_group_center_x_span=row.get('ocr_layout_group_center_x_span'),
                ocr_layout_group_median_item_w=row.get('ocr_layout_group_median_item_w'),
                flags=';'.join(flags),
                keys=keys,
                memory=memory_text(),
            )
        except Exception:
            pass

        try:
            # ocr_items_all preserves every OCR piece in the group when available.
            # If it is absent, fall back to ocr_items so the log still tells us what
            # the provider returned/preserved.
            items = row.get('ocr_items_all') or row.get('ocr_items') or []
            source_name = 'ocr_items_all' if row.get('ocr_items_all') else 'ocr_items'
            for item_idx, item in enumerate(list(items or [])):
                if not isinstance(item, dict):
                    _append_worker_log_if_enabled(
                        log_path,
                        'SINGLE_ANALYZE_OCR_ITEM_DETAIL',
                        group_index=idx,
                        item_index=item_idx,
                        source=source_name,
                        item_type=type(item).__name__,
                        memory=memory_text(),
                    )
                    continue
                summary = _summarize_ocr_item_payload(item)
                _append_worker_log_if_enabled(
                    log_path,
                    'SINGLE_ANALYZE_OCR_ITEM_DETAIL',
                    group_index=idx,
                    item_index=item_idx,
                    source=source_name,
                    text=_safe_short_text(summary.get('text'), 100),
                    rect=summary.get('rect'),
                    rect_h_over_w=_rect_ratio_text(summary.get('rect')),
                    cx=summary.get('cx'),
                    cy=summary.get('cy'),
                    vertices=summary.get('vertices'),
                    char_count=summary.get('char_count'),
                    stroke_size=summary.get('stroke_size'),
                    provider=summary.get('source_provider'),
                    locale=summary.get('locale'),
                    detected_break=summary.get('detected_break'),
                    order_index=summary.get('order_index'),
                    confidence=summary.get('confidence'),
                    memory=memory_text(),
                )
        except Exception:
            pass


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
    if provider == "local_lama":
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





def _local_ocr_runtime_status(provider: str) -> tuple[bool, str]:
    """Check local OCR runtime inside the worker thread.

    The UI should already have opened the progress dialog before this runs.
    Return a user-readable message instead of showing modal popups here.
    """
    provider = str(provider or "").lower()
    try:
        from ysb.editions.local.local_dependency_check import (
            comic_text_detector_runtime_status,
            external_paddleocr_worker_status,
            manga_ocr_ready,
        )
        det_ok, det_missing = comic_text_detector_runtime_status()
        if not det_ok:
            return False, "Torch 텍스트 디텍터 의존성이 부족합니다: " + ", ".join(det_missing)
        if provider == "local_paddle_ocr":
            ok, detail = external_paddleocr_worker_status()
            if not ok:
                return False, "PaddleOCR 런타임 준비 실패: " + str(detail)
            return True, "Torch 텍스트 디텍터 + PaddleOCR 런타임 확인 완료"
        if provider == "local_manga_ocr":
            ok, detail = manga_ocr_ready()
            if not ok:
                return False, "Manga OCR 런타임 준비 실패: " + str(detail)
            return True, "Torch 텍스트 디텍터 + Manga OCR 런타임 확인 완료"
        return True, "Local OCR 런타임 확인 대상 아님"
    except Exception as e:
        return False, f"Local OCR 런타임 확인 중 오류: {type(e).__name__}: {e}"

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



class WorkerResultValidationError(ValueError):
    """Raised when a worker technically finished but the output is not usable."""


def _first_nonempty_text(values, limit=3):
    out = []
    for value in values or []:
        text = str(value or '').strip()
        if not text:
            continue
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _analysis_error_keys_for_provider(provider):
    provider = str(provider or '').strip().lower()
    if provider == 'local_paddle_ocr':
        return ('local_paddle_ocr_error',)
    if provider == 'local_manga_ocr':
        return ('local_manga_ocr_error',)
    return ('local_paddle_ocr_error', 'local_manga_ocr_error')


def _summarize_analysis_result(provider, data):
    rows = list(data or [])
    total_ocr_main = 0
    total_ocr_all = 0
    total_text_rows = 0
    detector_only_rows = 0
    none_engine_rows = 0
    error_rows = []
    samples = []
    error_keys = _analysis_error_keys_for_provider(provider)
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        ocr_main = _list_count(row.get('ocr_items'))
        ocr_all = _list_count(row.get('ocr_items_all'))
        total_ocr_main += ocr_main
        total_ocr_all += ocr_all
        if str(row.get('text') or '').strip() or ocr_main > 0 or ocr_all > 0:
            total_text_rows += 1
        if bool(row.get('local_detector_only')):
            detector_only_rows += 1
        if not str(row.get('ocr_engine') or '').strip():
            none_engine_rows += 1
        for key in error_keys:
            err = row.get(key)
            if err:
                error_rows.append((idx, key, str(err)))
                if len(samples) < 3:
                    samples.append(f"{idx + 1}번 {key}: {str(err)[:160]}")
                break
    return {
        'boxes': len(rows),
        'ocr_items': total_ocr_main,
        'ocr_items_all': total_ocr_all,
        'text_rows': total_text_rows,
        'detector_only_rows': detector_only_rows,
        'none_engine_rows': none_engine_rows,
        'error_rows': error_rows,
        'error_samples': samples,
    }


def validate_analysis_result_or_raise(provider, provider_name, ori, data, mask_merge, mask_inpaint, *, preserve_text_mask=False):
    """Fail when an OCR/analysis worker ended but produced an abnormal result.

    Detector-only rows are valid only for a detector-only workflow. For OCR providers,
    finishing with boxes but without OCR text/items is a failed OCR, not a success.
    """
    provider = str(provider or '').strip().lower()
    provider_name = str(provider_name or 'OCR')
    if ori is None:
        raise WorkerResultValidationError(f"{provider_name} 분석 결과가 비정상입니다: 원본 이미지 결과가 없습니다.")
    if mask_merge is None or mask_inpaint is None:
        raise WorkerResultValidationError(f"{provider_name} 분석 결과가 비정상입니다: 텍스트/페인팅 마스크 결과가 없습니다.")

    local_ocr = provider in {'local_paddle_ocr', 'local_manga_ocr'}
    summary = _summarize_analysis_result(provider, data)
    boxes = int(summary.get('boxes') or 0)
    if boxes <= 0:
        # 텍스트가 없는 페이지일 수 있으므로 에러로 보지 않는다.
        return summary

    errors = []
    if summary.get('error_rows'):
        sample = ' / '.join(summary.get('error_samples') or [])
        errors.append(f"OCR 내부 오류가 {len(summary.get('error_rows') or [])}개 있습니다" + (f" ({sample})" if sample else ""))

    if local_ocr:
        if int(summary.get('ocr_items_all') or 0) <= 0 and int(summary.get('text_rows') or 0) <= 0:
            errors.append(f"텍스트 영역은 {boxes}개 감지됐지만 OCR 인식 결과가 0개입니다")
        if int(summary.get('detector_only_rows') or 0) >= boxes:
            errors.append("모든 영역이 detector-only 상태입니다. 선택한 로컬 OCR이 실제로 결과를 채우지 못했습니다")
        if int(summary.get('none_engine_rows') or 0) >= boxes:
            errors.append("모든 영역의 ocr_engine이 비어 있습니다. OCR 엔진 실행 결과로 볼 수 없습니다")

    if errors:
        hint = ""
        if provider == 'local_paddle_ocr':
            hint = "\n조치: 설정 -> 로컬 CUDA 진단에서 Paddle GPU 런타임 설치/복구를 확인하세요. CPU 모드라면 PaddleOCR CPU 실행 가능 여부를 확인하세요."
        elif provider == 'local_manga_ocr':
            hint = "\n조치: 설정 -> 로컬 CUDA 진단에서 Torch CUDA 런타임 설치/복구를 확인하세요. CPU 모드라면 Manga OCR CPU 실행 가능 여부를 확인하세요."
        raise WorkerResultValidationError(
            f"{provider_name} 분석 결과가 비정상입니다.\n"
            f"감지 영역: {boxes}개 / OCR 항목: {summary.get('ocr_items_all', 0)}개 / 텍스트 행: {summary.get('text_rows', 0)}개\n"
            + "\n".join(f"- {e}" for e in errors)
            + hint
        )
    return summary


def _decode_image_bytes_for_validation(img_data):
    try:
        if not img_data:
            return None
        arr = np.frombuffer(bytes(img_data), dtype=np.uint8)
        if arr.size <= 0:
            return None
        return cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
    except Exception:
        return None


def format_inpaint_failure_message(error, provider="", provider_name=""):
    raw = str(error or "").strip()
    provider = str(provider or "").strip().lower()
    provider_name = str(provider_name or "인페인팅")
    if provider == "local_lama" or "LOCAL LaMa" in raw or "simple_lama" in raw or "SimpleLaMa" in raw:
        if "Attempting to deserialize object on CUDA device" in raw or "map_location" in raw:
            return (
                "LOCAL LaMa 모델 로딩 실패입니다.\n"
                "원인: CUDA 저장 모델을 현재 실행 장치에 맞게 불러오지 못했습니다.\n"
                "- CPU 모드라면 모델을 CPU로 map_location 처리해야 합니다.\n"
                "- CUDA 모드라면 Torch CUDA 런타임에서 CUDA 장치가 보여야 합니다.\n"
                f"원문 오류: {raw}\n"
                "조치: 패치 적용 후 프로그램을 완전히 재시작하세요. 계속 실패하면 설정 -> 로컬 CUDA 진단에서 Torch CUDA 런타임 설치/복구를 실행하세요."
            )
        if "CUDA device requested" in raw or "CUDA를 요청" in raw or "forced_cuda_unavailable" in raw:
            return (
                "LOCAL LaMa CUDA 실행 실패입니다.\n"
                "원인: CUDA 모드를 요청했지만 worker에서 CUDA 장치를 사용할 수 없습니다.\n"
                f"원문 오류: {raw}\n"
                "조치: 설정 -> 로컬 CUDA 진단에서 Torch CUDA 런타임 설치/복구를 확인하세요. CPU로 실행하려면 Device를 CPU 또는 자동으로 바꾸세요."
            )
        if "simple_lama_inpainting" in raw:
            return (
                "LOCAL LaMa 필수 패키지가 없습니다.\n"
                f"원문 오류: {raw}\n"
                "조치: 설정 -> 로컬 CUDA 진단에서 Torch CUDA 런타임 설치/복구를 실행하세요."
            )
        if "mask" in raw.lower() and ("empty" in raw.lower() or "비어" in raw):
            return (
                "LOCAL LaMa 인페인팅 마스크가 비어 있습니다.\n"
                f"원문 오류: {raw}"
            )
        return (
            "LOCAL LaMa 인페인팅 실행 실패입니다.\n"
            f"원문 오류: {raw}\n"
            "조치: 설정 -> 로컬 CUDA 진단에서 Torch CUDA 런타임 상태를 확인하세요."
        )
    return f"{provider_name} 실행 실패입니다.\n원문 오류: {raw}"


def validate_inpaint_result_or_raise(provider, img_data, engine=None):
    provider = str(provider or '').strip().lower()
    if not img_data:
        raise WorkerResultValidationError("인페인팅 결과가 비어 있습니다.")
    img = _decode_image_bytes_for_validation(img_data)
    if img is None or getattr(img, 'size', 0) <= 0:
        raise WorkerResultValidationError("인페인팅 결과 이미지를 디코딩할 수 없습니다. 결과 파일이 깨졌거나 비어 있습니다.")
    try:
        h, w = img.shape[:2]
        if h <= 0 or w <= 0:
            raise WorkerResultValidationError("인페인팅 결과 이미지 크기가 비정상입니다.")
    except WorkerResultValidationError:
        raise
    except Exception:
        raise WorkerResultValidationError("인페인팅 결과 이미지 형태가 비정상입니다.")

    if provider == 'local_lama':
        info = getattr(engine, '_last_local_lama_device_info', None) if engine is not None else None
        if isinstance(info, dict) and info:
            req = str(info.get('requested_device') or 'auto').strip().lower()
            resolved = str(info.get('resolved_device') or '').strip().lower()
            model_device = str(info.get('model_device') or '').strip().lower()
            cuda_ok = bool(info.get('cuda_available'))
            if req == 'cuda':
                actual_cuda = resolved.startswith('cuda') or model_device.startswith('cuda')
                if not actual_cuda or not cuda_ok:
                    raise WorkerResultValidationError(
                        "LOCAL LaMa CUDA 실행 결과가 비정상입니다.\n"
                        f"요청 장치: cuda / 실제 장치: {resolved or 'unknown'} / 모델 장치: {model_device or 'unknown'} / CUDA 사용 가능: {cuda_ok}\n"
                        "조치: 설정 -> 로컬 CUDA 진단에서 Torch CUDA 런타임 설치/복구를 실행하세요."
                    )
            elif req == 'cpu':
                try:
                    cuda_count = int(info.get('cuda_device_count') or 0)
                except Exception:
                    cuda_count = 0
                reason = str(info.get('reason') or '').strip().lower()
                # CPU mode may run in the Torch CUDA runtime while CUDA is hidden
                # (cuda_count=0).  Some SimpleLaMa wrappers keep stale metadata such
                # as model_device='cuda' even after map_location/to('cpu').  Do not
                # discard a valid image result on that metadata alone.
                actual_cuda = resolved.startswith('cuda') or (
                    model_device.startswith('cuda') and cuda_count > 0 and reason != 'forced_cpu'
                )
                if actual_cuda:
                    raise WorkerResultValidationError(
                        "LOCAL LaMa CPU 실행 결과가 비정상입니다. CPU를 요청했지만 CUDA 장치에서 실행된 것으로 감지되었습니다."
                    )
    return True

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


def _current_inpaint_provider_info():
    try:
        from ysb.engine.manga_engine import Config
        provider = str(getattr(Config, "INPAINT_PROVIDER", "replicate_lama") or "replicate_lama").strip().lower()
    except Exception:
        provider = "replicate_lama"
    if provider == "replicate_stable":
        return provider, "Stable Diffusion"
    if provider == "gemini_inpaint":
        return provider, "Gemini"
    if provider == "local_lama":
        return provider, "LOCAL LaMa"
    return provider, "LaMa"


def _normalize_inpaint_mask_array(mask, width, height):
    if mask is None:
        return None
    try:
        arr = np.asarray(mask)
        if arr.size <= 0:
            return None
        if arr.ndim == 3:
            if arr.shape[2] >= 4:
                alpha = arr[:, :, 3]
                rgb_gray = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2GRAY)
                gray = np.maximum(rgb_gray, alpha)
            else:
                gray = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2GRAY)
        else:
            gray = arr.astype(np.uint8, copy=False)
        if gray.shape[1] != int(width) or gray.shape[0] != int(height):
            gray = cv2.resize(gray, (int(width), int(height)), interpolation=cv2.INTER_NEAREST)
        _thr, bin_mask = cv2.threshold(gray.astype(np.uint8, copy=False), 0, 255, cv2.THRESH_BINARY)
        if int(np.count_nonzero(bin_mask)) <= 0:
            return None
        return bin_mask
    except Exception:
        return None


def _encode_png_bytes(image):
    try:
        ok, buf = cv2.imencode('.png', image, [int(cv2.IMWRITE_PNG_COMPRESSION), 6])
        if not ok:
            return b''
        return bytes(buf.tobytes())
    except Exception:
        return b''


def _decode_inpaint_result_image(img_data):
    try:
        arr = np.frombuffer(bytes(img_data or b''), dtype=np.uint8)
        if arr.size <= 0:
            return None
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None or getattr(img, 'size', 0) <= 0:
            return None
        return img
    except Exception:
        return None


def _compose_group_result(base_img, result_crop, mask_crop):
    """Composite only the mask and a small feather area back into the original crop.

    LaMa sees the padded context crop, but the paste-back area stays mask-led so
    clean background outside the mask is not unexpectedly replaced.
    """
    if base_img is None or result_crop is None or mask_crop is None:
        return base_img
    try:
        h, w = base_img.shape[:2]
        if h <= 0 or w <= 0:
            return base_img
        if result_crop.shape[1] != w or result_crop.shape[0] != h:
            result_crop = cv2.resize(result_crop, (w, h), interpolation=cv2.INTER_CUBIC)
        if mask_crop.ndim == 3:
            gray = cv2.cvtColor(mask_crop, cv2.COLOR_RGB2GRAY)
        else:
            gray = mask_crop.astype(np.uint8, copy=False)
        if gray.shape[1] != w or gray.shape[0] != h:
            gray = cv2.resize(gray, (w, h), interpolation=cv2.INTER_NEAREST)
        _thr, bin_mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY)
        if int(np.count_nonzero(bin_mask)) <= 0:
            return base_img
        # A small feather reduces crop seam artifacts without letting the whole
        # context crop overwrite the original page.
        short_side = max(1, min(w, h))
        dilate_px = max(3, min(21, int(round(short_side * 0.012))))
        if dilate_px % 2 == 0:
            dilate_px += 1
        kernel = np.ones((dilate_px, dilate_px), np.uint8)
        soft = cv2.dilate(bin_mask, kernel, iterations=1)
        blur_px = max(3, min(31, dilate_px * 2 + 1))
        if blur_px % 2 == 0:
            blur_px += 1
        soft = cv2.GaussianBlur(soft, (blur_px, blur_px), 0)
        alpha = (soft.astype(np.float32) / 255.0)[:, :, None]
        out = (result_crop.astype(np.float32) * alpha + base_img.astype(np.float32) * (1.0 - alpha))
        return np.clip(out, 0, 255).astype(np.uint8)
    except Exception:
        return result_crop if result_crop is not None else base_img


def _execute_grouped_inpainting(
    engine,
    source_path,
    data,
    inpaint_mask,
    *,
    page_idx=-1,
    groups=None,
    max_work_side=2800,
    log_path=None,
    progress_emit=None,
    prefix='',
    cancel_check=None,
):
    """Run LaMa by mask-beacon groups and return one full-page PNG byte payload.

    This is the real execution counterpart of the preview overlay: the exact
    group list is built from the mask, each padded group rect is cropped, LaMa is
    called per crop, and only the mask/feather area is composed back.
    """
    provider, provider_name = _current_inpaint_provider_info()
    src_img = _imread_unicode(str(source_path))
    if src_img is None:
        raise ValueError(f"이미지를 읽을 수 없습니다: {source_path}")
    h, w = src_img.shape[:2]
    bin_mask = _normalize_inpaint_mask_array(inpaint_mask, w, h)
    if bin_mask is None:
        raise ValueError("인페인팅 마스크가 비어 있습니다.")

    if groups is None:
        groups = build_inpaint_mask_groups(bin_mask, max_work_side=int(max_work_side or 2800))
    groups = list(groups or [])
    if not groups:
        raise ValueError("인페인팅 마스크 그룹이 없습니다.")

    total = len(groups)
    if progress_emit:
        progress_emit(0, f"현재 작업: 인페인팅 그룹 준비 완료\n전체 그룹: {total}개")
    if log_path:
        append_log(log_path, "GROUPED INPAINT START", page_idx=page_idx, groups=total, source_size=f"{w}x{h}", mask=numpy_shape_text(bin_mask), mask_nonzero=int(np.count_nonzero(bin_mask)), memory=memory_text())

    import tempfile
    import shutil
    temp_dir = tempfile.mkdtemp(prefix="ysb_group_inpaint_")
    composed = src_img.copy()
    try:
        for order, group in enumerate(groups, 1):
            if cancel_check and cancel_check():
                raise RuntimeError("인페인팅 작업이 취소되었습니다.")
            rect = group.get('rect') or group.get('bbox') or []
            if len(rect) < 4:
                continue
            x1, y1, x2, y2 = [int(round(float(v))) for v in rect[:4]]
            x1 = max(0, min(w - 1, x1))
            y1 = max(0, min(h - 1, y1))
            x2 = max(x1 + 1, min(w, x2))
            y2 = max(y1 + 1, min(h, y2))
            crop = composed[y1:y2, x1:x2].copy()
            mask_crop = bin_mask[y1:y2, x1:x2].copy()
            mask_nonzero = int(np.count_nonzero(mask_crop))
            if mask_nonzero <= 0:
                if log_path:
                    append_log(log_path, "GROUPED INPAINT SKIP EMPTY", page_idx=page_idx, group=order, total=total, rect=f"{x1},{y1},{x2},{y2}", memory=memory_text())
                continue

            pct_start = int(round(((order - 1) / max(1, total)) * 100))
            if progress_emit:
                progress_emit(pct_start, f"현재 작업: {provider_name} 인페인팅 실행 중\n그룹 {order}/{total} · {x2-x1}x{y2-y1}")
            if log_path:
                append_log(log_path, "GROUPED INPAINT GROUP ENTER", page_idx=page_idx, group=order, total=total, rect=f"{x1},{y1},{x2},{y2}", size=f"{x2-x1}x{y2-y1}", mask_nonzero=mask_nonzero, memory=memory_text())

            crop_path = os.path.join(temp_dir, f"page_{int(page_idx)+1:04d}_group_{order:03d}.png")
            if not _imwrite_unicode(crop_path, crop):
                raise ValueError(f"그룹 crop 이미지를 저장하지 못했습니다: {crop_path}")

            def _tee_group_progress(msg):
                if not progress_emit:
                    return
                text = str(msg or '').strip()
                if not text:
                    return
                try:
                    if text.startswith('YSB_PROGRESS|'):
                        _tag, sub_pct, sub_detail = text.split('|', 2)
                        sub_pct = max(0, min(100, int(float(sub_pct))))
                        mapped = int(round(((order - 1) + (sub_pct / 100.0)) / max(1, total) * 100))
                        progress_emit(mapped, sub_detail)
                    else:
                        progress_emit(pct_start, text)
                except Exception:
                    try:
                        progress_emit(pct_start, text)
                    except Exception:
                        pass

            stream = _ProgressTeeStream(sys.__stdout__, _tee_group_progress)
            err_stream = _ProgressTeeStream(sys.__stderr__, _tee_group_progress)
            with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(err_stream):
                result = engine.execute_inpainting(crop_path, [], mask_crop)
            if not result:
                raise WorkerResultValidationError(f"{provider_name} 그룹 {order}/{total} 인페인팅 결과가 비어 있습니다.")
            img_data = _download_replicate_output(result)
            validate_inpaint_result_or_raise(provider, img_data, engine)
            result_crop = _decode_inpaint_result_image(img_data)
            if result_crop is None:
                raise WorkerResultValidationError(f"그룹 {order}/{total} 인페인팅 결과 이미지를 디코딩할 수 없습니다.")
            composed_crop = _compose_group_result(composed[y1:y2, x1:x2], result_crop, mask_crop)
            composed[y1:y2, x1:x2] = composed_crop

            pct_done = int(round((order / max(1, total)) * 100))
            if progress_emit:
                progress_emit(pct_done, f"현재 작업: 인페인팅 그룹 완료\n그룹 {order}/{total} 완료 ({pct_done}%)")
            if log_path:
                append_log(log_path, "GROUPED INPAINT GROUP DONE", page_idx=page_idx, group=order, total=total, percent=pct_done, bytes=len(img_data or b''), memory=memory_text())

        encoded = _encode_png_bytes(composed)
        if not encoded:
            raise WorkerResultValidationError("그룹 인페인팅 결과 PNG 인코딩에 실패했습니다.")
        if log_path:
            append_log(log_path, "GROUPED INPAINT DONE", page_idx=page_idx, groups=total, bytes=len(encoded or b''), memory=memory_text())
        return encoded, groups
    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass


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
        self.translation_chunk_size_setting = self._resolve_translation_chunk_setting(main_window, self.provider)
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

    def _resolve_translation_chunk_setting(self, main_window, provider):
        """Return 0 for Auto, or a fixed line count for one translation request."""
        attr = {
            "openai": "openai_chunk_size",
            "deepseek": "deepseek_chunk_size",
            "google": "google_translate_chunk_size",
            "gemini": "gemini_chunk_size",
            "gemini_deferred": "gemini_delayed_chunk_size",
            "custom": "custom_translation_chunk_size",
            "lm_studio": "lm_studio_chunk_size",
        }.get(str(provider or "openai"), "openai_chunk_size")
        settings = getattr(main_window, "api_settings", None)
        try:
            return max(0, min(int(getattr(settings, attr, 0) or 0), 100))
        except Exception:
            return 0
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
        # Clean file names are canonical page-order names: Clean_1p, Clean_2p, ...
        # The engine canonicalizes this stem to the final Clean_Np filename.
        try:
            return f"{int(page_idx) + 1}p"
        except Exception:
            return "1p"


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
                    self.progress.emit(f"{prefix} 1/4 OCR 분석 준비: {base_name}")
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
                    self.progress.emit(f"{prefix} 3/4 OCR 실행")
                    o, d, mm, mi = self.engine.analyze_image(
                        path,
                        analysis_regions=regions,
                    )
                    d = tag_ocr_layout_candidates(d)
                    validate_analysis_result_or_raise(self.ocr_provider, self.ocr_provider_name, o, d, mm, mi)
                    self.progress.emit(f"{prefix} 4/4 OCR 결과 정리")
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
                        d = tag_ocr_layout_candidates(d)
                        validate_analysis_result_or_raise(self.ocr_provider, self.ocr_provider_name, o, d, mm, mi, preserve_text_mask=True)
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
                    source_chars = sum(len(str(t or "")) for t in texts)
                    nonempty_count = sum(1 for t in texts if str(t or "").strip())
                    translate_t0 = time.perf_counter()
                    effective_chunk_size = self.translation_chunk_size_setting
                    if effective_chunk_size <= 0:
                        # 자동: 이 페이지의 체크된 번역 대상 줄 전체를 한 청크로 묶는다.
                        effective_chunk_size = max(1, len(texts))
                    append_log(
                        self.batch_log_path,
                        "TRANSLATE REQUEST BEGIN",
                        index=i,
                        provider=self.provider,
                        chunk_size=effective_chunk_size,
                        chunk_mode="auto_page" if self.translation_chunk_size_setting <= 0 else "fixed",
                        target_count=len(target_items),
                        nonempty_count=nonempty_count,
                        source_chars=source_chars,
                        memory=memory_text(),
                    )
                    trans = self.engine.translate_text_batch(texts, provider=self.provider, chunk_size=effective_chunk_size)
                    translate_elapsed_ms = int((time.perf_counter() - translate_t0) * 1000)
                    result_chars = sum(len(str(t or "")) for t in (trans or []))
                    append_log(
                        self.batch_log_path,
                        "TRANSLATE RESPONSE DONE",
                        index=i,
                        provider=self.provider,
                        response_count=len(trans or []),
                        source_chars=source_chars,
                        result_chars=result_chars,
                        elapsed_ms=translate_elapsed_ms,
                        memory=memory_text(),
                    )

                    if len(trans) != len(target_items):
                        raise ValueError(f"번역 개수 불일치: 요청 {len(target_items)}개 / 응답 {len(trans)}개")

                    apply_t0 = time.perf_counter()
                    for item, t in zip(target_items, trans):
                        item['translated_text'] = str(t) if t is not None else ''

                    payload = {
                        'data': new_data,
                        '_batch_timing': {
                            'mode': self.mode,
                            'provider': self.provider,
                            'target_count': len(target_items),
                            'nonempty_count': nonempty_count,
                            'source_chars': source_chars,
                            'result_chars': result_chars,
                            'translate_elapsed_ms': translate_elapsed_ms,
                            'apply_to_payload_elapsed_ms': int((time.perf_counter() - apply_t0) * 1000),
                        },
                    }
                    append_log(
                        self.batch_log_path,
                        "TRANSLATE PAYLOAD READY",
                        index=i,
                        data_count=len(new_data or []),
                        translate_elapsed_ms=translate_elapsed_ms,
                        memory=memory_text(),
                    )

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

                    self.progress.emit(f"{prefix} 현재 작업: 인페인팅 이미지/마스크 준비 중 - {base_name}")
                    append_log(self.batch_log_path, "INPAINT ENTER", index=i, data_count=len(inpaint_data or []), mask=numpy_shape_text(inpaint_mask), memory=memory_text())

                    temp_cleanup_path = None
                    source_path = self._write_bg_clean_as_source(i, curr_data, path)
                    self.progress.emit(f"{prefix} 2/5 입력 이미지/마스크 준비")
                    append_log(self.batch_log_path, "INPAINT SOURCE READY", index=i, source_path=source_path, memory=memory_text())

                    # 인페인팅은 항상 미리보기와 같은 마스크-비콘 그룹 방식으로 실행한다.
                    # 전체 페이지 리사이즈/타일 분할이 아니라, 2800px 작업 캔버스 안에 패킹된 그룹 crop만 LaMa에 보낸다.
                    append_log(self.batch_log_path, "GROUPED INPAINT REQUEST", index=i, source_path=source_path, resized=False, memory=memory_text())
                    self.progress.emit(f"{prefix} 현재 작업: 인페인팅 그룹 계산 중")

                    def _batch_group_progress(percent, detail):
                        try:
                            detail_text = str(detail or '').replace('현재 작업: ', '', 1)
                            self.progress.emit(f"{prefix} {detail_text}")
                        except Exception:
                            pass

                    bg_bytes, used_groups = _execute_grouped_inpainting(
                        self.engine,
                        source_path,
                        inpaint_data,
                        inpaint_mask,
                        page_idx=i,
                        max_work_side=2800,
                        log_path=self.batch_log_path,
                        progress_emit=_batch_group_progress,
                        prefix=prefix,
                        cancel_check=lambda: not bool(getattr(self, 'is_running', True)),
                    )

                    append_log(self.batch_log_path, "GROUPED INPAINT RESPONSE", index=i, groups=len(used_groups or []), bytes=format_bytes(len(bg_bytes or b'')), memory=memory_text())
                    if bg_bytes:
                        curr_data['bg_clean'] = bg_bytes
                        payload = {'bg_clean': bg_bytes}
                        self.progress.emit(f"{prefix} 현재 작업: 인페인팅 결과 반영 대기")
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
    failed = pyqtSignal(str)
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

            detector_note = ""
            if provider == "local_paddle_ocr":
                detector_note = "Torch 텍스트 감지 + PaddleOCR"
            elif provider == "local_manga_ocr":
                detector_note = "Torch 텍스트 감지 + Manga OCR"

            status_name = provider_name if not detector_note else f"{provider_name} ({detector_note})"
            self.log.emit(f"YSB_PROGRESS|5|현재 작업: OCR 런타임 확인 중\n엔진: {status_name}")
            if provider in {"local_paddle_ocr", "local_manga_ocr"}:
                ok, runtime_msg = _local_ocr_runtime_status(provider)
                self.log.emit((f"YSB_PROGRESS|12|현재 작업: 로컬 런타임 확인 완료\n{runtime_msg}") if ok else f"❌ {runtime_msg}")
                if not ok:
                    raise ValueError(runtime_msg)
            else:
                self.log.emit(f"YSB_PROGRESS|12|현재 작업: OCR API/엔진 준비 중\n엔진: {provider_name}")
            self.log.emit("YSB_PROGRESS|18|현재 작업: 이미지 파일과 마스크 준비 중")
            if provider in {"local_paddle_ocr", "local_manga_ocr"}:
                self.log.emit("YSB_PROGRESS|25|현재 작업: Torch 텍스트 디텍터 준비 중")
            if provider == "local_manga_ocr":
                self.log.emit("YSB_PROGRESS|30|현재 작업: Manga OCR 모델 장치 확인 중")
            if self.mask is not None:
                self.log.emit(f"YSB_PROGRESS|32|현재 작업: {provider_name} OCR 재분석 시작")
                stream = _ProgressTeeStream(sys.__stdout__, self.log.emit)
                err_stream = _ProgressTeeStream(sys.__stderr__, self.log.emit)
                with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(err_stream):
                    o, d, mm, mi = self.engine.reanalyze_from_manual_mask(self.path, self.mask, self.data)
                d = tag_ocr_layout_candidates(d)
            else:
                if self.analysis_regions:
                    self.log.emit(f"YSB_PROGRESS|32|현재 작업: {provider_name} 지정 범위 분석 시작\n대상 영역: {len(self.analysis_regions)}개")
                else:
                    self.log.emit(f"YSB_PROGRESS|32|현재 작업: {provider_name} 전체 분석 시작")
                stream = _ProgressTeeStream(sys.__stdout__, self.log.emit)
                err_stream = _ProgressTeeStream(sys.__stderr__, self.log.emit)
                with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(err_stream):
                    o, d, mm, mi = self.engine.analyze_image(self.path, analysis_regions=self.analysis_regions)
                d = tag_ocr_layout_candidates(d)
            self.log.emit("YSB_PROGRESS|88|현재 작업: OCR 영역과 레이아웃 후보 정리 중")
            validation_summary = validate_analysis_result_or_raise(provider, provider_name, o, d, mm, mi, preserve_text_mask=bool(self.mask is not None))
            self.log.emit("YSB_PROGRESS|96|현재 작업: OCR 결과를 화면에 반영할 준비 중")
            append_log(self.analysis_log_path, "SINGLE ANALYZE DONE", boxes=len(d or []), ori=numpy_shape_text(o), mask_merge=numpy_shape_text(mm), mask_inpaint=numpy_shape_text(mi), validation=validation_summary, memory=memory_text())
            _append_single_analyze_data_detail_logs(self.analysis_log_path, d)
            self.log.emit(f"✅ 완료 ({len(d)}개)")
            self.finished.emit(o, d, _copy_mask(mm), _copy_mask(mi))
        except Exception as e:
            import traceback
            append_log(self.analysis_log_path, "SINGLE ANALYZE EXCEPTION", error=repr(e), memory=memory_text())
            append_block(self.analysis_log_path, "TRACEBACK", exception_text(e))
            traceback.print_exc()
            msg = str(e)
            self.log.emit(f"YSB_PROGRESS|100|오류: {msg}")
            self.log.emit(f"❌ 오류: {msg}")
            try:
                self.failed.emit(msg)
            except Exception:
                pass



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
    failed = pyqtSignal(int, str)
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
                else:
                    provider_name = "LaMa"
            except Exception:
                provider = "unknown"
                provider_name = "인페인팅"
            append_log(self.inpaint_log_path, "SINGLE INPAINT PROVIDER", page_idx=self.page_idx, provider=provider, provider_name=provider_name, memory=memory_text())
            try:
                temp_dir = os.environ.get("TMP") or os.environ.get("TEMP") or ""
                py_temp_dir = ""
                try:
                    import tempfile
                    py_temp_dir = tempfile.gettempdir()
                except Exception:
                    py_temp_dir = ""
                append_log(
                    self.inpaint_log_path,
                    "SINGLE INPAINT TEMP_ENV",
                    page_idx=self.page_idx,
                    temp_env=temp_dir,
                    tempfile_gettempdir=py_temp_dir,
                    temp_dir_exists=os.path.isdir(py_temp_dir) if py_temp_dir else False,
                    temp_dir_writable=os.access(py_temp_dir, os.W_OK) if py_temp_dir else False,
                    memory=memory_text(),
                )
            except Exception:
                pass
            self.log.emit(f"YSB_PROGRESS|8|현재 작업: 인페인팅 런타임 확인 중\n엔진: {provider_name}")
            self.log.emit("YSB_PROGRESS|20|현재 작업: 이미지와 마스크 준비 완료")
            self.log.emit(f"YSB_PROGRESS|35|현재 작업: {provider_name} 인페인팅 실행 중")
            stream = _ProgressTeeStream(sys.__stdout__, self.log.emit)
            err_stream = _ProgressTeeStream(sys.__stderr__, self.log.emit)
            with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(err_stream):
                res = self.engine.execute_inpainting(self.path, self.data, self.mask)
            if res:
                try:
                    info = getattr(self.engine, "_last_local_lama_device_info", None)
                    if isinstance(info, dict) and info:
                        append_log(
                            self.inpaint_log_path,
                            "SINGLE INPAINT LOCAL_LAMA_DEVICE",
                            page_idx=self.page_idx,
                            requested=info.get("requested_device"),
                            resolved=info.get("resolved_device"),
                            model_device=info.get("model_device"),
                            cuda_available=info.get("cuda_available"),
                            cuda_device_count=info.get("cuda_device_count"),
                            cuda_device_name=info.get("cuda_device_name"),
                            torch_version=info.get("torch_version"),
                            torch_cuda_build=info.get("torch_cuda_build"),
                            worker_python=info.get("worker_python"),
                            reason=info.get("reason"),
                            memory=memory_text(),
                        )
                except Exception:
                    pass
                self.log.emit("YSB_PROGRESS|82|현재 작업: 인페인팅 결과 수신/디코딩 중")
                img_data = _download_replicate_output(res)
                validate_inpaint_result_or_raise(provider, img_data, self.engine)
                append_log(self.inpaint_log_path, "SINGLE INPAINT DONE", page_idx=self.page_idx, bytes=len(img_data or b""), memory=memory_text())
                self.log.emit("YSB_PROGRESS|96|현재 작업: 인페인팅 결과를 화면에 반영할 준비 중")
                self.finished.emit(self.page_idx, img_data)
            else:
                append_log(self.inpaint_log_path, "SINGLE INPAINT EMPTY_RESULT", page_idx=self.page_idx, memory=memory_text())
                msg = f"{provider_name} 인페인팅 결과가 비어 있습니다. 작업은 완료로 처리하지 않습니다."
                self.log.emit(f"YSB_PROGRESS|100|오류: {msg}")
                self.failed.emit(self.page_idx, msg)
        except Exception as e:
            append_log(self.inpaint_log_path, "SINGLE INPAINT EXCEPTION", page_idx=self.page_idx, error=repr(e), memory=memory_text())
            try:
                lama_debug = getattr(self.engine, "_last_lama_temp_mask_debug", None)
                if isinstance(lama_debug, dict) and lama_debug:
                    append_log(self.inpaint_log_path, "SINGLE INPAINT LAMA_TEMP_MASK_DEBUG", page_idx=self.page_idx, **lama_debug, memory=memory_text())
            except Exception:
                pass
            append_block(self.inpaint_log_path, "TRACEBACK", exception_text(e))
            err_msg = format_inpaint_failure_message(e, provider, provider_name)
            self.log.emit(f"YSB_PROGRESS|100|오류: {err_msg}")
            self.failed.emit(self.page_idx, err_msg)
        finally:
            if _cleanup_temp_inpaint_request(self.cleanup_path):
                append_log(self.inpaint_log_path, "SINGLE INPAINT TEMP CLEANUP", page_idx=self.page_idx, path=self.cleanup_path, memory=memory_text())
                self.log.emit(f"🧹 임시 인페인팅 입력 정리: {os.path.basename(self.cleanup_path)}")


class GroupedInpaintWorker(QThread):
    finished = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)
    log = pyqtSignal(str)

    def __init__(self, engine, path, data, mask, page_idx=-1, groups=None, max_work_side=2800):
        super().__init__()
        self.engine = engine
        self.path = path
        self.data = _copy_data_list(data)
        self.mask = _copy_mask(mask)
        self.groups = copy.deepcopy(groups or [])
        try:
            self.page_idx = int(page_idx)
        except Exception:
            self.page_idx = -1
        self.max_work_side = int(max_work_side or 2800)
        self.inpaint_log_path = make_log_path("single_inpaint")
        self.cancel_requested = False

    def stop(self):
        self.cancel_requested = True

    def run(self):
        provider = "unknown"
        provider_name = "인페인팅"
        try:
            _log_path_image_summary(self.inpaint_log_path, "GROUPED SINGLE INPAINT START", self.path)
            provider, provider_name = _current_inpaint_provider_info()
            try:
                mask_nonzero = int(np.count_nonzero(self.mask)) if self.mask is not None else 0
            except Exception:
                mask_nonzero = -1
            append_log(
                self.inpaint_log_path,
                "GROUPED SINGLE INPAINT CONTEXT",
                page_idx=self.page_idx,
                provider=provider,
                provider_name=provider_name,
                groups_hint=len(self.groups or []),
                mask=numpy_shape_text(self.mask),
                mask_nonzero=mask_nonzero,
                data_count=len(self.data or []),
                max_work_side=self.max_work_side,
                memory=memory_text(),
            )
            self.log.emit(f"YSB_PROGRESS|0|현재 작업: 인페인팅 그룹 계산 중")

            def _emit_group_progress(percent, detail):
                try:
                    pct = max(0, min(100, int(percent)))
                except Exception:
                    pct = 0
                self.log.emit(f"YSB_PROGRESS|{pct}|{detail}")

            img_data, used_groups = _execute_grouped_inpainting(
                self.engine,
                self.path,
                self.data,
                self.mask,
                page_idx=self.page_idx,
                groups=(self.groups or None),
                max_work_side=self.max_work_side,
                log_path=self.inpaint_log_path,
                progress_emit=_emit_group_progress,
                cancel_check=lambda: bool(getattr(self, 'cancel_requested', False)),
            )

            if img_data:
                try:
                    info = getattr(self.engine, "_last_local_lama_device_info", None)
                    if isinstance(info, dict) and info:
                        append_log(
                            self.inpaint_log_path,
                            "GROUPED SINGLE INPAINT LOCAL_LAMA_DEVICE",
                            page_idx=self.page_idx,
                            requested=info.get("requested_device"),
                            resolved=info.get("resolved_device"),
                            model_device=info.get("model_device"),
                            cuda_available=info.get("cuda_available"),
                            cuda_device_count=info.get("cuda_device_count"),
                            cuda_device_name=info.get("cuda_device_name"),
                            torch_version=info.get("torch_version"),
                            torch_cuda_build=info.get("torch_cuda_build"),
                            worker_python=info.get("worker_python"),
                            reason=info.get("reason"),
                            memory=memory_text(),
                        )
                except Exception:
                    pass
                self.log.emit(f"YSB_PROGRESS|100|현재 작업: 인페인팅 결과를 화면에 반영할 준비 중\n전체 그룹: {len(used_groups or [])}개")
                self.finished.emit(self.page_idx, img_data)
            else:
                msg = f"{provider_name} 인페인팅 결과가 비어 있습니다. 작업은 완료로 처리하지 않습니다."
                append_log(self.inpaint_log_path, "GROUPED SINGLE INPAINT EMPTY_RESULT", page_idx=self.page_idx, memory=memory_text())
                self.log.emit(f"YSB_PROGRESS|100|오류: {msg}")
                self.failed.emit(self.page_idx, msg)
        except Exception as e:
            append_log(self.inpaint_log_path, "GROUPED SINGLE INPAINT EXCEPTION", page_idx=self.page_idx, error=repr(e), memory=memory_text())
            try:
                lama_debug = getattr(self.engine, "_last_lama_temp_mask_debug", None)
                if isinstance(lama_debug, dict) and lama_debug:
                    append_log(self.inpaint_log_path, "GROUPED SINGLE INPAINT LAMA_TEMP_MASK_DEBUG", page_idx=self.page_idx, **lama_debug, memory=memory_text())
            except Exception:
                pass
            append_block(self.inpaint_log_path, "TRACEBACK", exception_text(e))
            err_msg = format_inpaint_failure_message(e, provider, provider_name)
            self.log.emit(f"YSB_PROGRESS|100|오류: {err_msg}")
            self.failed.emit(self.page_idx, err_msg)


class TranslationWorker(QThread):
    progress = pyqtSignal(str, int, int)  # detail, current, total
    trace = pyqtSignal(str, object)  # event_name, fields(dict)
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    canceled = pyqtSignal(object)

    def __init__(self, engine, texts, provider="openai", chunk_size=20, target_language=None):
        super().__init__()
        self.engine = engine
        self.texts = [str(t or "") for t in (texts or [])]
        self.provider = provider or "openai"
        self.target_language = str(target_language or "").strip()
        try:
            self.chunk_size = max(1, min(int(chunk_size or 20), 100))
        except Exception:
            self.chunk_size = 20
        self.cancel_requested = False
        self._trace_id = f"single-{int(time.time() * 1000)}-{id(self) & 0xffff:x}"

    def _emit_trace(self, event, **fields):
        try:
            fields.setdefault("trace_id", self._trace_id)
            fields.setdefault("provider", self.provider)
            fields.setdefault("chunk_size", self.chunk_size)
            fields.setdefault("target_language", self.target_language)
            fields.setdefault("memory", memory_text())
            self.trace.emit(str(event), dict(fields))
        except Exception:
            pass

    def stop(self):
        self.cancel_requested = True
        self._emit_trace("TRANSLATE_SINGLE_CANCEL_REQUESTED")

    def run(self):
        total = len(self.texts)
        results = []
        run_t0 = time.perf_counter()
        total_chars = sum(len(str(t or "")) for t in self.texts)
        nonempty_count = sum(1 for t in self.texts if str(t or "").strip())
        self._emit_trace(
            "TRANSLATE_SINGLE_WORKER_START",
            total=total,
            nonempty_count=nonempty_count,
            total_chars=total_chars,
        )
        try:
            if total <= 0:
                self._emit_trace("TRANSLATE_SINGLE_WORKER_DONE", elapsed_ms=int((time.perf_counter() - run_t0) * 1000), result_count=0)
                self.finished.emit([])
                return
            for start in range(0, total, self.chunk_size):
                if self.cancel_requested:
                    self._emit_trace(
                        "TRANSLATE_SINGLE_WORKER_CANCELED",
                        elapsed_ms=int((time.perf_counter() - run_t0) * 1000),
                        result_count=len(results),
                    )
                    self.canceled.emit(results)
                    return
                end = min(total, start + self.chunk_size)
                self.progress.emit(f"번역 중: {start + 1}-{end} / {total}", start, total)
                chunk = self.texts[start:end]
                chunk_chars = sum(len(str(t or "")) for t in chunk)
                self._emit_trace(
                    "TRANSLATE_SINGLE_CHUNK_BEGIN",
                    start=start,
                    end=end,
                    request_count=len(chunk),
                    chunk_chars=chunk_chars,
                    progress_done=start,
                    progress_total=total,
                )
                if self.target_language:
                    try:
                        from ysb.engine.manga_engine import Config
                        Config.TRANSLATION_TARGET_LANGUAGE = self.target_language
                    except Exception:
                        pass
                chunk_t0 = time.perf_counter()
                try:
                    translated = self.engine.translate_text_batch(
                        chunk,
                        provider=self.provider,
                        chunk_size=len(chunk),
                    )
                except Exception as e:
                    self._emit_trace(
                        "TRANSLATE_SINGLE_CHUNK_EXCEPTION",
                        start=start,
                        end=end,
                        elapsed_ms=int((time.perf_counter() - chunk_t0) * 1000),
                        error=repr(e),
                    )
                    raise
                engine_elapsed_ms = int((time.perf_counter() - chunk_t0) * 1000)
                if translated is None:
                    translated = []
                translated = list(translated)
                raw_result_count = len(translated)
                if len(translated) < len(chunk):
                    translated.extend(chunk[len(translated):])
                elif len(translated) > len(chunk):
                    translated = translated[:len(chunk)]
                result_chars = sum(len(str(t or "")) for t in translated)
                results.extend(translated)
                self._emit_trace(
                    "TRANSLATE_SINGLE_CHUNK_DONE",
                    start=start,
                    end=end,
                    request_count=len(chunk),
                    raw_result_count=raw_result_count,
                    result_count=len(translated),
                    chunk_chars=chunk_chars,
                    result_chars=result_chars,
                    elapsed_ms=engine_elapsed_ms,
                    cumulative_result_count=len(results),
                )
                self.progress.emit(f"번역 완료: {end} / {total}", end, total)
                if self.cancel_requested:
                    self._emit_trace(
                        "TRANSLATE_SINGLE_WORKER_CANCELED",
                        elapsed_ms=int((time.perf_counter() - run_t0) * 1000),
                        result_count=len(results),
                    )
                    self.canceled.emit(results)
                    return
            self._emit_trace(
                "TRANSLATE_SINGLE_WORKER_DONE",
                elapsed_ms=int((time.perf_counter() - run_t0) * 1000),
                result_count=len(results),
                total_chars=total_chars,
            )
            self.finished.emit(results)
        except Exception as e:
            self._emit_trace(
                "TRANSLATE_SINGLE_WORKER_ERROR",
                elapsed_ms=int((time.perf_counter() - run_t0) * 1000),
                result_count=len(results),
                error=repr(e),
            )
            self.error.emit(str(e))
