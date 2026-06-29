# -*- coding: utf-8 -*-
"""세로쓰기 전용 텍스트 자동조정 엔진.

가로쓰기 자동조정은 줄 수 후보/한국어 줄내림 점수/박스 채움률을 함께 판단한다.
세로쓰기 자동조정은 성격이 다르다. 한국어식 세로쓰기는 기본적으로 "한 세로 열"로
취급해야 하므로, 이 모듈은 줄내림 후보를 만들지 않고 현재 텍스트를 한 줄로 정리한 뒤
OCR 영역 안에 들어가는 최대 글자 크기만 찾는다.
"""
from __future__ import annotations

_QRECTF_IMPORT_ERRORS = []
QRectF = None
for _qrectf_module in ('PyQt6.QtCore', 'PyQt5.QtCore', 'PySide6.QtCore', 'PySide2.QtCore'):
    try:
        QRectF = __import__(_qrectf_module, fromlist=['QRectF']).QRectF
        break
    except Exception as _exc:
        _QRECTF_IMPORT_ERRORS.append(f'{_qrectf_module}: {_exc!r}')
if QRectF is None:
    raise ImportError('QRectF를 가져올 수 없습니다. 시도 결과: ' + '; '.join(_QRECTF_IMPORT_ERRORS))


def _audit(owner, event, **payload):
    try:
        if hasattr(owner, 'audit_boundary_event'):
            owner.audit_boundary_event(event, **payload)
    except Exception:
        pass


def _safe_int(value, default=0):
    try:
        return int(round(float(value)))
    except Exception:
        return int(default)


def _one_vertical_line(text):
    """세로쓰기 자동조정용 단일 열 텍스트.

    기존 번역문에 우발적으로 들어간 줄바꿈은 세로 열 분리가 아니라 한 열 안의 문장으로
    합친다. 일반 띄어쓰기는 남겨서 단어 호흡은 보존한다.
    """
    raw = str(text or '').replace('\r\n', '\n').replace('\r', '\n')
    parts = [p.strip() for p in raw.split('\n') if p.strip()]
    if parts:
        return ' '.join(parts).strip()
    return raw.strip()


def _normalize_direction(owner, item):
    try:
        return owner.text_item_writing_direction(item)
    except Exception:
        return str((item or {}).get('writing_direction') or 'horizontal').strip().lower()


def vertical_auto_apply_enabled(owner):
    """자동 텍스트 조정 시 OCR 세로쓰기 hint를 세로쓰기 모드로 자동 적용할지."""
    try:
        return bool((getattr(owner, 'app_options', {}) or {}).get('auto_text_apply_vertical_writing', True))
    except Exception:
        return True


def item_has_vertical_single_column_hint(item, *, min_confidence=0.68):
    if not isinstance(item, dict):
        return False
    hint = str(item.get('ocr_layout_hint') or item.get('layout_hint') or '').strip().lower()
    axis = str(item.get('ocr_layout_axis') or '').strip().lower()
    try:
        confidence = float(item.get('ocr_layout_confidence', 0.0) or 0.0)
    except Exception:
        confidence = 0.0
    # 자동 세로쓰기 적용은 반드시 '한 세로 열' 확정 후보에만 허용한다.
    # vertical_multi_column/axis=vertical 같은 정보는 일본어 원문이 세로계열이라는 뜻일 수는
    # 있어도, 한국어 번역문을 한 줄 세로쓰기 처리해도 된다는 뜻은 아니다.
    if hint == 'vertical_single_column' and confidence >= float(min_confidence):
        return True
    return False


def item_should_use_vertical_auto_adjust(owner, item, *, allow_auto_detect=True):
    if not isinstance(item, dict):
        return False
    if bool(item.get('rasterized_text')):
        return False
    if _normalize_direction(owner, item) == 'vertical':
        return True
    if not bool(allow_auto_detect):
        return False
    return item_has_vertical_single_column_hint(item)


def _rect_from_item(item):
    try:
        vals = list((item or {}).get('rect') or [0, 0, 1, 1])
        x, y, w, h = [float(v) for v in vals[:4]]
        if w <= 0 or h <= 0:
            return None
        return QRectF(x, y, max(1.0, w), max(1.0, h))
    except Exception:
        return None


def _measure_vertical(owner, item, line, family, size, stroke):
    try:
        return owner._measure_typesetting_lines_for_auto_fit(
            item, [str(line or '')], family, int(size), stroke=stroke, writing_direction='vertical'
        )
    except Exception:
        try:
            return owner._measure_wrapped_lines_for_auto_fit(item, [str(line or '')], family, int(size), stroke=stroke)
        except Exception:
            return None


def _font_family(owner, item):
    try:
        return item.get('font_family') or owner.cb_font.currentFont().family()
    except Exception:
        return item.get('font_family') or 'Arial'


def _stroke_width(item):
    try:
        return max(0, int(item.get('stroke_width', 0) or 0))
    except Exception:
        return 0


def _initial_font_size(owner, item, page_idx=None, fallback_size=24):
    try:
        return int(owner._auto_text_adjust_initial_font_size(item, page_idx=page_idx, fallback_size=fallback_size))
    except Exception:
        return _safe_int(item.get('font_size', fallback_size), fallback_size)


def fit_vertical_single_column_item(owner, item, page_idx=None, *, auto_detected=False):
    """Apply one-column vertical fitting to one item.

    변경 대상: writing_direction, translated/text linebreak 정리, font_size, inner offsets,
    x_off/y_off, 자동조정 메타데이터. line_spacing/letter_spacing 등 사용자 서식은 건드리지 않는다.
    """
    if not isinstance(item, dict):
        return False
    try:
        text_key, original = owner._auto_layout_text_key_and_value(item)
    except Exception:
        text_key = 'translated_text' if str(item.get('translated_text') or '').strip() else 'text'
        original = item.get(text_key, '') or ''
    line = _one_vertical_line(original)
    if not line:
        return False
    rect = _rect_from_item(item)
    if rect is None:
        return False
    family = _font_family(owner, item)
    stroke = _stroke_width(item)
    box_w, box_h = float(rect.width()), float(rect.height())
    fallback_size = _safe_int(item.get('font_size', 24), 24)
    start_size = _initial_font_size(owner, item, page_idx=page_idx, fallback_size=fallback_size)
    short_side = min(box_w, box_h)
    long_side = max(box_w, box_h)
    max_size = int(max(float(start_size) * 12.0, short_side * 3.5, long_side * 2.2, 72.0))
    max_size = max(1, min(960, max_size))

    lo, hi = 1, max_size
    best = 1
    best_m = _measure_vertical(owner, item, line, family, 1, stroke) or (1.0, 1.0)
    check_count = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        measured = _measure_vertical(owner, item, line, family, mid, stroke)
        check_count += 1
        if measured is None:
            hi = mid - 1
            continue
        mw, mh = float(measured[0]), float(measured[1])
        if mw <= box_w + 0.5 and mh <= box_h + 0.5:
            best = mid
            best_m = (mw, mh)
            lo = mid + 1
        else:
            hi = mid - 1
    measured_w, measured_h = float(best_m[0]), float(best_m[1])

    changed = False
    old_direction = _normalize_direction(owner, item)
    old_size = _safe_int(item.get('font_size', fallback_size), fallback_size)
    old_text = str(item.get(text_key) or '')

    if old_direction != 'vertical':
        item['writing_direction'] = 'vertical'
        changed = True
    if old_text != line:
        item[text_key] = line
        changed = True
    if old_size != int(best):
        item['font_size'] = int(best)
        changed = True
    for key in ('x_off', 'y_off', 'inner_text_x_off', 'inner_text_y_off'):
        try:
            if _safe_int(item.get(key, 0), 0) != 0:
                item[key] = 0
                changed = True
        except Exception:
            pass

    fill_w = measured_w / max(1.0, box_w)
    fill_h = measured_h / max(1.0, box_h)
    item['auto_layout_mode'] = 'vertical_single_column_auto_adjust'
    item['auto_layout_writing_direction'] = 'vertical'
    item['auto_layout_vertical_auto_applied'] = bool(auto_detected or old_direction != 'vertical')
    item['auto_layout_vertical_single_line_only'] = True
    item['auto_layout_vertical_source_hint'] = str(item.get('ocr_layout_hint') or '')
    item['auto_layout_vertical_source_confidence'] = item.get('ocr_layout_confidence')
    item['auto_layout_line_count'] = 1
    item['auto_layout_line_count_target'] = 1
    item['auto_layout_fill_w'] = round(float(fill_w), 4)
    item['auto_layout_fill_h'] = round(float(fill_h), 4)
    item['auto_layout_touch_ok'] = bool(measured_w <= box_w + 0.5 and measured_h <= box_h + 0.5)
    item['auto_layout_near_touch_ok'] = item['auto_layout_touch_ok']
    item['auto_layout_hard_fail'] = bool(not item['auto_layout_touch_ok'])
    item['auto_layout_vertical_size_check_count'] = int(check_count)
    item['auto_layout_vertical_measured_w'] = round(float(measured_w), 3)
    item['auto_layout_vertical_measured_h'] = round(float(measured_h), 3)

    _audit(
        owner,
        'TEXT_VERTICAL_AUTO_ADJUST_ITEM_DONE',
        page_idx=page_idx,
        item_id=item.get('id'),
        changed=bool(changed),
        auto_detected=bool(auto_detected),
        old_direction=old_direction,
        old_size=old_size,
        new_size=int(best),
        text_key=text_key,
        text_changed=old_text != line,
        measured_w=round(measured_w, 2),
        measured_h=round(measured_h, 2),
        box_w=round(box_w, 2),
        box_h=round(box_h, 2),
        fill_w=round(fill_w, 4),
        fill_h=round(fill_h, 4),
        hint=item.get('ocr_layout_hint'),
        confidence=item.get('ocr_layout_confidence'),
        policy='vertical_single_column_one_line_only',
    )
    return bool(changed)


def apply_vertical_auto_adjust_prepass(owner, page_idx=None, items=None, *, allow_auto_detect=True):
    """Route vertical candidates before the horizontal auto-adjust session.

    이미 세로쓰기인 항목은 항상 처리한다. OCR 세로쓰기 후보 자동 적용은 옵션이 켜져 있을 때만
    가로쓰기 항목을 vertical로 전환한다.
    """
    active = [it for it in list(items or []) if isinstance(it, dict)]
    enabled = bool(allow_auto_detect) and vertical_auto_apply_enabled(owner)
    changed_ids = []
    routed = 0
    detected = 0
    _audit(owner, 'TEXT_VERTICAL_AUTO_ADJUST_PREPASS_START', page_idx=page_idx, target_count=len(active), auto_detect_enabled=enabled)
    for item in active:
        old_direction = _normalize_direction(owner, item)
        auto_detected = bool(old_direction != 'vertical' and enabled and item_has_vertical_single_column_hint(item))
        if old_direction != 'vertical' and not auto_detected:
            continue
        routed += 1
        if auto_detected:
            detected += 1
        try:
            if fit_vertical_single_column_item(owner, item, page_idx=page_idx, auto_detected=auto_detected):
                iid = item.get('id')
                if iid is not None:
                    changed_ids.append(iid)
        except Exception as exc:
            _audit(owner, 'TEXT_VERTICAL_AUTO_ADJUST_ITEM_ERROR', page_idx=page_idx, item_id=item.get('id'), error=repr(exc))
    changed_ids = list(dict.fromkeys([x for x in changed_ids if x is not None]))
    _audit(owner, 'TEXT_VERTICAL_AUTO_ADJUST_PREPASS_DONE', page_idx=page_idx, routed_count=routed, auto_detected_count=detected, changed_ids=changed_ids, changed_count=len(changed_ids))
    return changed_ids
