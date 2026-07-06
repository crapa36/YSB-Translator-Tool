# -*- coding: utf-8 -*-
"""텍스트 자동조정 엔진 (전면 재설계).

기존 main_window_text_layout_mixin.py 안의 자동조정 로직은 OCR rect 직접 사용,
그리드 흔들기, 안전사각형 패치 등이 겹겹이 쌓여 어떤 단계가 무엇을 책임지는지
추적하기 어려운 상태가 되었다. 이 모듈은 5단계로 명확히 끊어서 처음부터 다시 짠다.

5단계 정의 (사용자 정의 그대로):
    1. fit_linebreak     : 박스 비율에 맞춰 줄내림한다. 줄 합치기/3글자 묶기도 여기서 끝낸다.
    2. fit_size_to_ocr   : 1단계 줄내림을 유지한 채, OCR 영역에 맞는 글자 크기를 찾는다.
    3. resolve_overlap   : 다른 렌더 텍스트와의 겹침 + 이미지 캔버스 넘침을 검사/보정한다.
                           (오른쪽 -> 왼쪽 순서로 확정. 확정된 텍스트는 다음 텍스트의
                           "가용 영역"을 깎는 제약이 된다.)
    4. grow_to_mode      : 폰트 크기의 최빈값(mode)을 구하고, 그보다 일정 비율 이상
                           작은 텍스트를 최빈값까지 키운다.
    5. resolve_overlap_2 : 4단계로 커진 텍스트에 대해 겹침/경계 검사를 다시 한다.
                           이번에는 "자기 OCR rect를 넘어가는 것"은 허용한다(예외).
                           이미지 캔버스 경계는 이때도 그대로 지킨다.

설계 원칙:
- 각 단계는 item dict를 직접 변형하지 않고, TextLayoutState를 입출력으로 주고받는
  순수 함수에 가깝게 만든다. 마지막에 apply_state_to_item()으로 한 번만 반영한다.
  -> 이렇게 해야 "단계별 버튼"을 붙였을 때 중간 상태를 그대로 보여줄 수 있다.
- 각 단계 함수는 StepResult(이전 상태, 이후 상태, 보조 정보)를 반환한다.
  UI/디버그 도구는 StepResult만 보면 그 단계에서 무슨 일이 있었는지 알 수 있다.
- OCR rect, x_off/y_off(사용자 위치), translated_text의 줄바꿈 문자는 1단계가
  확정한 뒤로는 절대 다시 바꾸지 않는다. 2~5단계가 만지는 것은 font_size와
  inner_text_x_off/inner_text_y_off뿐이다.
- 한국어 줄내림의 세부 규칙(묶기/3글자 단위/badness 계산)은 새로 만들지 않고
  korean_linebreak_rules.py의 기존 함수를 그대로 재사용한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

_QRECTF_IMPORT_ERRORS = []
QRectF = None
for _qrectf_module in ('PyQt6.QtCore', 'PyQt5.QtCore', 'PySide6.QtCore', 'PySide2.QtCore'):
    try:
        QRectF = __import__(_qrectf_module, fromlist=['QRectF']).QRectF
        break
    except Exception as _exc:  # 다음 바인딩으로 계속 시도
        _QRECTF_IMPORT_ERRORS.append(f'{_qrectf_module}: {_exc!r}')
if QRectF is None:
    # 조용히 None으로 넘어가면 ocr_rect()가 항상 None을 반환해 모든 항목이
    # "텍스트/rect 없음"으로 오인되어 스킵되는 사고가 난다(실제로 PyQt6 환경에서
    # PyQt5만 시도하다 이 문제가 발생했음). 반드시 여기서 크게 실패시킨다.
    raise ImportError(
        'QRectF를 가져올 수 있는 Qt 바인딩(PyQt6/PyQt5/PySide6/PySide2)을 찾지 못했다. '
        '시도한 결과: ' + '; '.join(_QRECTF_IMPORT_ERRORS)
    )

try:
    from ysb.core import korean_linebreak_rules as kbr
except Exception:  # standalone mock/test fallback
    import korean_linebreak_rules as kbr


# ---------------------------------------------------------------------------
# 데이터 모델
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TextLayoutState:
    """한 텍스트 항목의 레이아웃 상태. item dict를 직접 건드리지 않기 위한 스냅샷.

    item['rect']와 x_off/y_off(사용자 위치)는 1단계 이전부터 고정값이므로
    이 상태에는 포함하지 않는다. 여기 담는 것은 단계가 실제로 바꿔도 되는 값뿐이다.
    """
    item_id: object
    lines: tuple              # 줄내림 결과 (line 문자열들). 1단계 이후 절대 안 바뀜.
    font_size: int
    inner_text_x_off: int = 0
    inner_text_y_off: int = 0
    note: str = ''             # 진단/표시용 부가 정보. 알고리즘 판단에는 쓰지 않는다.


@dataclass
class StepResult:
    """단계 하나를 실행한 결과. 버튼 UI가 그대로 표시에 쓸 수 있게 설계."""
    step_name: str
    before: dict              # {item_id: TextLayoutState}
    after: dict                # {item_id: TextLayoutState}
    changed_ids: list = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)  # {item_id: {...자유 형식 진단 정보...}}

    def diff(self):
        """실제로 값이 달라진 항목만 추려서 보여준다(보고된 changed_ids와 별개로 검증 가능)."""
        out = {}
        for iid in set(self.before) | set(self.after):
            b = self.before.get(iid)
            a = self.after.get(iid)
            if b is None or a is None or b != a:
                out[iid] = {'before': b, 'after': a}
        return out


# ---------------------------------------------------------------------------
# owner(메인 윈도우)에 의존하는 저수준 어댑터
#
# 이 영역만 main_window_text_layout_mixin.py의 기존 헬퍼를 그대로 호출한다.
# 텍스트 측정/렌더링 자체를 다시 만들 필요는 없고, "측정"과 "5단계 판단 로직"의
# 책임을 분리하는 것이 이 재설계의 핵심이다.
# ---------------------------------------------------------------------------

class LayoutAdapter:
    """owner(메인 윈도우 mixin 인스턴스)에 대한 얇은 어댑터.

    이 클래스의 메서드 목록이 곧 "새 엔진이 기존 코드에 요구하는 최소 의존성"이다.
    여기 없는 메서드를 5단계 로직이 직접 owner에서 호출하지 않도록 한다.
    """

    def __init__(self, owner, page_idx):
        self.owner = owner
        self.page_idx = page_idx

    def text_key_and_value(self, item):
        try:
            return self.owner._auto_layout_text_key_and_value(item)
        except Exception:
            key = 'translated_text' if str(item.get('translated_text') or '').strip() else 'text'
            return key, item.get(key, '') or ''

    def writing_direction(self, item):
        try:
            return self.owner.text_item_writing_direction(item)
        except Exception:
            return 'horizontal'

    def font_family(self, item):
        try:
            return item.get('font_family') or self.owner.cb_font.currentFont().family()
        except Exception:
            return item.get('font_family') or 'Arial'

    def stroke_width(self, item):
        try:
            return max(0, int(item.get('stroke_width', 0) or 0))
        except Exception:
            return 0

    def ocr_rect(self, item):
        """item['rect']를 QRectF로. 이 값은 1단계 이전부터 고정이며 어떤 단계도 바꾸지 않는다."""
        try:
            x, y, w, h = [float(v) for v in (item.get('rect') or [0, 0, 1, 1])[:4]]
            return QRectF(x, y, max(1.0, w), max(1.0, h))
        except Exception:
            return None

    def page_canvas_rect(self):
        try:
            size = self.owner._auto_layout_page_image_size_for_auto(page_idx=self.page_idx)
        except Exception:
            size = None
        if not size:
            return None
        try:
            return QRectF(0.0, 0.0, float(size[0]), float(size[1]))
        except Exception:
            return None

    def measure(self, item, lines, family, size, stroke=0):
        """주어진 폰트 크기에서 (width, height)를 측정한다. item을 변형하지 않는다.

        실패 시 (0, 0)을 반환하면 이분탐색에서 '아주 잘 들어간다'로 오판될 수 있으므로
        None을 반환하고, 호출부가 그 후보를 실패로 처리하게 한다.
        """
        try:
            return self.owner._measure_wrapped_lines_for_auto_fit(item, list(lines), family, int(size), stroke=stroke)
        except Exception:
            return None

    def render_rect_for_state(self, item, state: 'TextLayoutState'):
        """state(가상의 font_size/inner_offset)를 item에 임시로 적용해 실제 렌더 bbox를 구하고 되돌린다.

        item dict를 일시적으로 건드리지만, 호출 종료 시 원래 값으로 복원하므로
        외부에서 보면 순수 함수처럼 동작한다(단일 UI 스레드 사용을 가정).
        """
        text_key, _old_text = self.text_key_and_value(item)
        backup = {
            text_key: item.get(text_key),
            'font_size': item.get('font_size'),
            'inner_text_x_off': item.get('inner_text_x_off', 0),
            'inner_text_y_off': item.get('inner_text_y_off', 0),
        }
        try:
            item[text_key] = '\n'.join(state.lines)
            item['font_size'] = int(state.font_size)
            item['inner_text_x_off'] = int(state.inner_text_x_off)
            item['inner_text_y_off'] = int(state.inner_text_y_off)
            return self.owner._auto_adjust_visual_rect_for_item(item)
        finally:
            for k, v in backup.items():
                item[k] = v

    def render_line_rects_for_state(self, item, state: 'TextLayoutState'):
        """위와 동일하지만 줄 단위 bbox 리스트를 구한다. 겹침 검사는 항상 이 줄 단위로 한다."""
        text_key, _old_text = self.text_key_and_value(item)
        backup = {
            text_key: item.get(text_key),
            'font_size': item.get('font_size'),
            'inner_text_x_off': item.get('inner_text_x_off', 0),
            'inner_text_y_off': item.get('inner_text_y_off', 0),
        }
        try:
            item[text_key] = '\n'.join(state.lines)
            item['font_size'] = int(state.font_size)
            item['inner_text_x_off'] = int(state.inner_text_x_off)
            item['inner_text_y_off'] = int(state.inner_text_y_off)
            return self.owner._auto_adjust_visual_line_rects_for_item(item) or []
        finally:
            for k, v in backup.items():
                item[k] = v

    def apply_state_to_item(self, item, state: 'TextLayoutState'):
        """단계 실행이 모두 끝난 뒤, 최종 상태를 실제 item dict에 한 번만 반영한다."""
        text_key, _old_text = self.text_key_and_value(item)
        item[text_key] = '\n'.join(state.lines)
        item['font_size'] = int(state.font_size)
        item['inner_text_x_off'] = int(state.inner_text_x_off)
        item['inner_text_y_off'] = int(state.inner_text_y_off)


# ---------------------------------------------------------------------------
# 공용 유틸 (저수준 기하 계산 - owner에 의존하지 않는 순수 함수)
# ---------------------------------------------------------------------------

def _rect_overflow_info(rect, bound_rect):
    """rect가 bound_rect를 얼마나 벗어나는지. 안 벗어나면 overflow=False."""
    if rect is None or bound_rect is None:
        return {'overflow': False, 'left': 0.0, 'top': 0.0, 'right': 0.0, 'bottom': 0.0}
    left = max(0.0, float(bound_rect.left()) - float(rect.left()))
    top = max(0.0, float(bound_rect.top()) - float(rect.top()))
    right = max(0.0, float(rect.right()) - float(bound_rect.right()))
    bottom = max(0.0, float(rect.bottom()) - float(bound_rect.bottom()))
    overflow = (left > 0.5 or top > 0.5 or right > 0.5 or bottom > 0.5)
    return {'overflow': bool(overflow), 'left': left, 'top': top, 'right': right, 'bottom': bottom}


def _rects_overlap(rects_a, rects_b, *, gap_px=0.0):
    """두 줄-rect 리스트 사이에 실제 겹침(또는 gap_px 미만의 여백)이 있는지."""
    for a in rects_a or []:
        ax1, ay1 = float(a.left()), float(a.top())
        ax2, ay2 = float(a.right()), float(a.bottom())
        for b in rects_b or []:
            bx1, by1 = float(b.left()), float(b.top())
            bx2, by2 = float(b.right()), float(b.bottom())
            ox = min(ax2, bx2) - max(ax1, bx1)
            oy = min(ay2, by2) - max(ay1, by1)
            if ox > -gap_px and oy > -gap_px:
                return True
    return False


def _font_size_mode(sizes):
    """폰트 크기 리스트의 최빈값. 동률이면 더 큰 값을 우선한다.

    전부 1회씩만 등장하는 페이지에서는 '가장 큰 값'이 우연히 mode가 되는 문제가 있으므로
    중앙값을 폴백 기준으로 쓴다. 이 값은 3단계 grow_to_mode의 목표 크기이며,
    4단계 resolve_overlap_after_grow는 이 목표를 넘겨 키우지 않는다.
    """
    sizes = [int(s) for s in sizes if s]
    if not sizes:
        return 0
    counts = {}
    for s in sizes:
        counts[s] = counts.get(s, 0) + 1
    best_count = max(counts.values())
    if best_count <= 1:
        ordered = sorted(sizes)
        return int(ordered[len(ordered) // 2])
    candidates = [s for s, c in counts.items() if c == best_count]
    return max(candidates)


def _valid_measure(adapter, item, lines, family, size, stroke=0):
    """측정 실패를 (0, 0) 성공값처럼 해석하지 않기 위한 공용 측정 헬퍼."""
    try:
        measured = adapter.measure(item, lines, family, int(size), stroke=stroke)
        if measured is None:
            return None
        mw, mh = measured
        mw, mh = float(mw), float(mh)
        if mw < 0.0 or mh < 0.0:
            return None
        return mw, mh
    except Exception:
        return None


def _state_from_item(adapter: LayoutAdapter, item) -> TextLayoutState:
    """현재 item dict에서 엔진이 관리하는 최소 상태만 뽑는다."""
    item_id = item.get('id') if isinstance(item, dict) else None
    try:
        text_key, text_value = adapter.text_key_and_value(item)
    except Exception:
        text_key = 'translated_text'
        text_value = (item or {}).get('translated_text') or (item or {}).get('text') or ''
    try:
        font_size = int((item or {}).get('font_size', 24) or 24)
    except Exception:
        font_size = 24
    try:
        ix = int((item or {}).get('inner_text_x_off', 0) or 0)
    except Exception:
        ix = 0
    try:
        iy = int((item or {}).get('inner_text_y_off', 0) or 0)
    except Exception:
        iy = 0
    return TextLayoutState(
        item_id=item_id,
        lines=tuple(str(text_value or '').replace('\r\n', '\n').replace('\r', '\n').split('\n')),
        font_size=font_size,
        inner_text_x_off=ix,
        inner_text_y_off=iy,
    )


def _owner_item_fit_state(adapter: LayoutAdapter, item, before_state: TextLayoutState):
    """기존 단일 item 자동 맞춤을 엔진 1단계의 실측 계산기로 재사용한다.

    새 엔진은 전체 시퀀스를 담당하지만, 1단계의 폰트 측정/언어별 줄내림은 이미
    main_window_text_layout_mixin.py의 auto_text_size_item() 쪽에 많은 예외처리가 있다.
    본선 연결에서 이걸 빼버리면 버튼은 엔진을 타도 실제 1차 맞춤이 거의 안 바뀌는
    문제가 생긴다. 여기서는 실제 item을 직접 바꾸지 않고 사본에만 적용해 결과 상태만
    가져온다. text_auto_adjust_sequence.py는 여전히 사용하지 않는다.
    """
    owner = getattr(adapter, 'owner', None)
    if owner is None or not hasattr(owner, 'auto_text_size_item'):
        return None, {'owner_item_fit_used': False, 'reason': 'no_owner_auto_text_size_item'}
    if not isinstance(item, dict):
        return None, {'owner_item_fit_used': False, 'reason': 'not_dict'}

    probe = dict(item)
    prev_ignore = bool(getattr(owner, '_auto_text_adjust_ignore_neighbors', False))
    prev_in_page_run = bool(getattr(owner, '_auto_text_adjust_in_page_run', False))
    try:
        # 1차 맞춤은 반드시 이웃을 무시하고 OCR/fit rect 기준 최대 크기까지 키운다.
        # 후속 겹침/모드/최종 검사는 이 엔진의 2~4단계가 맡는다.
        owner._auto_text_adjust_ignore_neighbors = True
        owner._auto_text_adjust_in_page_run = True
        try:
            changed = bool(owner.auto_text_size_item(probe, page_idx=adapter.page_idx))
        except TypeError:
            changed = bool(owner.auto_text_size_item(probe))
        after_state = _state_from_item(adapter, probe)
        return after_state, {
            'owner_item_fit_used': True,
            'owner_item_fit_changed': changed,
            'before_size': before_state.font_size,
            'after_size': after_state.font_size,
            'before_line_count': len(before_state.lines),
            'after_line_count': len(after_state.lines),
        }
    except Exception as exc:
        return None, {'owner_item_fit_used': False, 'reason': 'exception', 'error': repr(exc)}
    finally:
        try:
            owner._auto_text_adjust_ignore_neighbors = prev_ignore
            owner._auto_text_adjust_in_page_run = prev_in_page_run
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 1+2단계: 비율에 맞춰 줄내림하고, 그 줄내림에 맞는 글자 크기를 함께 정한다.
#
# korean_linebreak_rules.candidate_select_key()는 size/fill_w/fill_h/touch까지
# 받아야 의미 있는 비교가 가능하다. 즉 "줄 수를 먼저 정하고 그 다음 크기를 정하는"
# 두 단계가 아니라, "줄 수 후보마다 크기까지 같이 계산해서 점수로 비교하는" 한 묶음의
# 판단이다. 사용자가 말한 1/2단계는 이 한 함수 안에서 같이 처리한다.
# ---------------------------------------------------------------------------

def step1and2_fit_linebreak_and_size(adapter: LayoutAdapter, item, *, min_size=1, max_size=260) -> StepResult:
    """OCR 박스 비율에 맞는 줄 수를 고르면서, 동시에 그 줄 구성에 맞는 최대 글자 크기를 정한다.

    각 줄 수 후보에 대해:
      1) korean_linebreak_rules.split_to_line_count()로 그 줄 수에 맞게 텍스트를 나눈다
         (합치기/3글자 묶기 등 세부 규칙은 이 함수 내부에 이미 구현되어 있음 - 재사용).
      2) 그 줄 구성을 유지한 채, OCR rect 안에 들어가는 최대 font_size를 이분탐색한다.
      3) fill_w/fill_h(채움 비율), touch 여부, badness(줄내림 불량도)를 계산해
         candidate_select_key로 점수를 매긴다.
    모든 줄 수 후보 중 점수가 가장 좋은 (줄 수, 크기) 조합을 채택한다.
    """
    item_id = item.get('id')
    text_key, raw_text = adapter.text_key_and_value(item)
    text = str(raw_text or '').strip()
    ocr_rect = adapter.ocr_rect(item)
    family = adapter.font_family(item)
    stroke = adapter.stroke_width(item)

    before_state = _state_from_item(adapter, item)

    if not text or ocr_rect is None:
        return StepResult('1_fit_linebreak_and_size', {item_id: before_state}, {item_id: before_state},
                           diagnostics={item_id: {'skipped': True, 'reason': 'empty_text_or_no_rect'}})

    # 세로쓰기/특수 항목은 기존 단일 맞춤기가 가장 안전하다.
    # 단, 일반 가로쓰기에서 기존 맞춤기가 no-op이면 여기서 바로 끝내지 않고
    # 새 엔진 자체의 1차 줄내림+OCR 최대크기 계산으로 반드시 후퇴한다.
    owner_fit_state, owner_fit_diag = _owner_item_fit_state(adapter, item, before_state)
    if owner_fit_state is not None and before_state != owner_fit_state:
        return StepResult(
            '1_fit_linebreak_and_size',
            {item_id: before_state},
            {item_id: owner_fit_state},
            changed_ids=[item_id],
            diagnostics={item_id: owner_fit_diag},
        )

    if str(adapter.writing_direction(item) or 'horizontal').lower() == 'vertical':
        diag = dict(owner_fit_diag or {})
        diag.update({'skipped': True, 'reason': 'vertical_owner_fit_no_change'})
        return StepResult('1_fit_linebreak_and_size', {item_id: before_state}, {item_id: before_state},
                          diagnostics={item_id: diag})

    # 기존 맞춤기가 변화 없음으로 끝나도 실제로는 현재 줄바꿈/크기 상태가 이미 굳어 있어
    # 재조정이 막힌 것일 수 있다. 새 엔진 1단계는 원문을 다시 정규화해 줄 후보를 만들고,
    # OCR rect에 들어가는 최대 font_size를 직접 계산한다.
    try:
        owner = getattr(adapter, 'owner', None)
        lang = owner.item_output_language_for_layout(item) if owner is not None and hasattr(owner, 'item_output_language_for_layout') else 'ko'
        norm = owner.normalize_auto_wrap_source_text_for_lang(text, lang) if owner is not None and hasattr(owner, 'normalize_auto_wrap_source_text_for_lang') else text
        if str(norm or '').strip():
            text = str(norm or '').strip()
    except Exception:
        pass

    box_w, box_h = float(ocr_rect.width()), float(ocr_rect.height())
    box_ratio = box_w / max(1.0, box_h)
    compact_length = kbr.compact_len(text)
    req_w, req_h = kbr.required_fill_for_box(box_ratio)

    def _fits(lines, size):
        measured = _valid_measure(adapter, item, lines, family, size, stroke=stroke)
        if measured is None:
            return False
        mw, mh = measured
        return mw <= box_w + 0.5 and mh <= box_h + 0.5

    def _max_size_for_lines(lines):
        lo, hi = int(min_size), int(max_size)
        best = 0
        while lo <= hi:
            mid = (lo + hi) // 2
            if _fits(lines, mid):
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        return best

    line_count_candidates = kbr.line_count_candidates(compact_length, box_ratio)
    scored_candidates = []
    tried = []
    for count in line_count_candidates:
        lines = kbr.split_to_line_count(text, count, box_ratio)
        if not lines:
            continue
        size = _max_size_for_lines(lines)
        if size <= 0:
            continue
        measured = _valid_measure(adapter, item, lines, family, size, stroke=stroke)
        if measured is None:
            continue
        mw, mh = measured
        fill_w = mw / box_w if box_w > 0 else 0.0
        fill_h = mh / box_h if box_h > 0 else 0.0
        badness = kbr.linebreak_badness(lines)
        touch = kbr.touch_ok_for_lines(lines, fill_w, fill_h, compact_length=compact_length,
                                        box_ratio=box_ratio, req_w=req_w, req_h=req_h)
        near_touch = kbr.near_touch_ok(fill_w, fill_h, req_w, req_h)
        deficit = max(0.0, req_w - fill_w) + max(0.0, req_h - fill_h)
        candidate = {
            'lines': lines, 'line_count': count, 'size': size,
            'fill_w': fill_w, 'fill_h': fill_h, 'badness': badness,
            'touch': touch, 'near_touch': near_touch, 'deficit': deficit,
        }
        key = kbr.candidate_select_key(candidate, compact_length=compact_length, box_ratio=box_ratio)
        scored_candidates.append((key, candidate))
        tried.append({'line_count': count, 'size': size, 'fill_w': round(fill_w, 3),
                       'fill_h': round(fill_h, 3), 'badness': badness, 'touch': touch})

    if not scored_candidates:
        # 후보가 전혀 안 풀리면 원문 그대로 1줄, 최소 크기로 폴백.
        after_state = replace(before_state, lines=(text,), font_size=max(int(min_size), 1))
        return StepResult('1_fit_linebreak_and_size', {item_id: before_state}, {item_id: after_state},
                           changed_ids=[item_id],
                           diagnostics={item_id: {'fallback': True, 'reason': 'no_candidate_fits'}})

    scored_candidates.sort(key=lambda pair: pair[0], reverse=True)
    best_candidate = scored_candidates[0][1]

    after_state = replace(before_state, lines=tuple(best_candidate['lines']),
                           font_size=int(best_candidate['size']), inner_text_x_off=0, inner_text_y_off=0)
    changed = (before_state != after_state)
    return StepResult(
        '1_fit_linebreak_and_size',
        {item_id: before_state}, {item_id: after_state},
        changed_ids=[item_id] if changed else [],
        diagnostics={item_id: {
            'box_ratio': box_ratio, 'compact_length': compact_length,
            'chosen_line_count': best_candidate['line_count'], 'chosen_size': best_candidate['size'],
            'chosen_fill_w': round(best_candidate['fill_w'], 3), 'chosen_fill_h': round(best_candidate['fill_h'], 3),
            'chosen_touch': best_candidate['touch'],
            'candidates_tried': tried,
        }},
    )






# ---------------------------------------------------------------------------
# 3, 5단계 공용: 오른쪽 -> 왼쪽 순서로 겹침/경계를 해결
# ---------------------------------------------------------------------------

def _available_rect_excluding_fixed(adapter, item, fixed_render_rects, *, allow_exceed_ocr_rect=False,
                                     exceed_margin_ratio=0.6):
    """현재 item이 쓸 수 있는 가용 사각형을 계산한다.

    base = 자기 OCR rect. allow_exceed_ocr_rect=True면 OCR rect를 사방으로
    exceed_margin_ratio만큼 확장한 범위까지 base로 인정한다(절대 이미지 전체가 아니다 -
    "OCR 영역을 약간 넘어가도 된다"는 예외이지 "아무 빈 곳에나 배치해도 된다"는 뜻이 아님).
    그 base에서 이미 확정된 오른쪽 텍스트들의 실제 렌더 영역(fixed_render_rects)을 뺀
    나머지 중 가장 넓은 사각형 후보들을 반환한다.
    """
    ocr_base = adapter.ocr_rect(item)
    if ocr_base is None:
        return []
    if allow_exceed_ocr_rect:
        mx = float(ocr_base.width()) * float(exceed_margin_ratio)
        my = float(ocr_base.height()) * float(exceed_margin_ratio)
        base = QRectF(ocr_base.x() - mx, ocr_base.y() - my,
                       ocr_base.width() + mx * 2.0, ocr_base.height() + my * 2.0)
    else:
        base = QRectF(ocr_base)
    canvas = adapter.page_canvas_rect()
    if base is not None and canvas is not None and base.intersects(canvas):
        base = base.intersected(canvas)
    if base is None or base.width() < 3 or base.height() < 3:
        return []

    candidates = [QRectF(base)]
    for fixed_rect in fixed_render_rects or []:
        next_candidates = []
        for cand in candidates:
            if cand.intersects(fixed_rect):
                inter = cand.intersected(fixed_rect)
                if inter.width() < 1.0 or inter.height() < 1.0:
                    next_candidates.append(QRectF(cand))
                    continue
                left, top = float(cand.left()), float(cand.top())
                right, bottom = float(cand.right()), float(cand.bottom())
                ix1, iy1 = float(inter.left()), float(inter.top())
                ix2, iy2 = float(inter.right()), float(inter.bottom())
                parts = [
                    QRectF(left, top, right - left, max(0.0, iy1 - top)),
                    QRectF(left, iy2, right - left, max(0.0, bottom - iy2)),
                    QRectF(left, top, max(0.0, ix1 - left), bottom - top),
                    QRectF(ix2, top, max(0.0, right - ix2), bottom - top),
                ]
                next_candidates.extend(p for p in parts if p.width() >= 3.0 and p.height() >= 3.0)
            else:
                next_candidates.append(QRectF(cand))
        candidates = next_candidates
        if not candidates:
            break

    # 중복 제거 + 면적 내림차순. 면적이 가장 큰 것이 항상 최선은 아니므로 여러 개를 유지한다.
    seen = set()
    out = []
    for r in sorted(candidates, key=lambda r: r.width() * r.height(), reverse=True):
        key = (round(r.x(), 1), round(r.y(), 1), round(r.width(), 1), round(r.height(), 1))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out[:16]


def _best_size_for_rect(adapter, item, lines, family, stroke, rect, *, min_size, max_size):
    """rect 폭/높이에 맞춰, lines(줄내림 고정)로 이분탐색한 최대 font_size."""
    box_w, box_h = float(rect.width()), float(rect.height())

    def _fits(size):
        measured = _valid_measure(adapter, item, lines, family, size, stroke=stroke)
        if measured is None:
            return False
        mw, mh = measured
        return mw <= box_w + 0.5 and mh <= box_h + 0.5

    lo, hi = int(min_size), int(max_size)
    best = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        if _fits(mid):
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _resolve_right_to_left(adapter: LayoutAdapter, items_with_state, *, allow_exceed_ocr_rect_ids=None,
                            min_size=1, max_size=260, max_size_overrides=None, step_name='resolve_overlap'):
    """오른쪽부터 확정하고, 확정된 텍스트의 실제 렌더 영역을 다음(왼쪽) 텍스트의 제약으로 사용한다.

    items_with_state: [(item, TextLayoutState), ...] - 페이지의 모든 대상.
    allow_exceed_ocr_rect_ids: 이 id 집합에 속한 item은 자기 OCR rect를 넘어가는 배치를 허용한다
        (5단계 예외 규칙). 이미지 캔버스 경계는 이 예외와 무관하게 항상 적용된다.
    max_size_overrides: {item_id: size} - 이 사이즈를 넘는 결과는 채택하지 않는다.
        이 값은 '성장 금지'가 아니라 단계별 목표 상한이다.
        1+2단계는 OCR rect에 맞는 최대 크기까지 먼저 키우고, 2단계 겹침 해소는
        그 목표 크기 안에서 이동/축소한다. 3단계가 mode까지 키웠다면 4단계도
        mode를 넘겨 새로 키우지 않고, 겹치면 그 안에서 이동/축소한다.
    """
    allow_exceed_ocr_rect_ids = set(allow_exceed_ocr_rect_ids or [])
    max_size_overrides = dict(max_size_overrides or {})
    canvas = adapter.page_canvas_rect()

    def _center_x(item, state):
        # 오른쪽->왼쪽 확정 순서는 배치 결과에 따라 흔들리면 안 된다.
        # 렌더 bbox 중심은 inner offset에 따라 바뀌므로, 원래 OCR rect 중심을 기준으로 고정한다.
        try:
            ocr = adapter.ocr_rect(item)
            return float(ocr.center().x()) if ocr is not None else 0.0
        except Exception:
            return 0.0

    ordered = sorted(items_with_state, key=lambda pair: -_center_x(pair[0], pair[1]))

    before = {it.get('id'): st for it, st in items_with_state}
    after = {}
    diagnostics = {}
    changed_ids = []

    fixed_render_rects = []  # 오른쪽부터 차례로 확정된 항목들의 "줄 단위" 렌더 영역이 쌓인다.

    for item, state in ordered:
        item_id = item.get('id')
        allow_exceed = item_id in allow_exceed_ocr_rect_ids
        family = adapter.font_family(item)
        stroke = adapter.stroke_width(item)

        current_lines = adapter.render_line_rects_for_state(item, state)
        overlapped = _rects_overlap(current_lines, fixed_render_rects, gap_px=1.0)

        canvas_rect = adapter.render_rect_for_state(item, state)
        overflow_info = _rect_overflow_info(canvas_rect, canvas) if canvas is not None else {'overflow': False}

        if not overlapped and not overflow_info.get('overflow'):
            # 그대로 둬도 문제 없음 - 가용 영역 계산까지 갈 필요 없다.
            after[item_id] = state
            diagnostics[item_id] = {'resolved_without_change': True}
            fixed_render_rects.extend(current_lines)
            continue

        available_rects = _available_rect_excluding_fixed(
            adapter, item, fixed_render_rects, allow_exceed_ocr_rect=allow_exceed,
        )
        if canvas is not None:
            # 이미지 캔버스 경계는 예외 없이 항상 적용 - 가용 사각형을 캔버스 안으로 한 번 더 클램프.
            available_rects = [r.intersected(canvas) for r in available_rects if r.intersects(canvas)]

        best_choice = None  # (size, rect, candidate_state)
        item_max_size = int(max_size_overrides.get(item_id, max_size))
        for rect in available_rects:
            size = _best_size_for_rect(adapter, item, state.lines, family, stroke, rect,
                                        min_size=min_size, max_size=item_max_size)
            if size <= 0:
                continue
            candidate_state = replace(state, font_size=size, inner_text_x_off=0, inner_text_y_off=0)
            rr = adapter.render_rect_for_state(item, candidate_state)
            if rr is None:
                continue
            # rect 중심에 배치.
            dx = float(rect.center().x() - rr.center().x())
            dy = float(rect.center().y() - rr.center().y())
            candidate_state = replace(candidate_state,
                                       inner_text_x_off=int(round(dx)), inner_text_y_off=int(round(dy)))
            if best_choice is None or size > best_choice[0]:
                best_choice = (size, rect, candidate_state)

        if best_choice is None:
            # 가용 영역에서 풀리지 않으면 원래 크기를 유지하되 위치만 가능한 만큼 보정.
            after[item_id] = state
            diagnostics[item_id] = {'resolved_without_change': False, 'reason': 'no_available_rect_fits',
                                     'available_rect_count': len(available_rects)}
            fixed_render_rects.extend(current_lines)
            continue

        _size, rect, new_state = best_choice
        after[item_id] = new_state
        if new_state != state:
            changed_ids.append(item_id)
        diagnostics[item_id] = {
            'resolved_without_change': False,
            'chosen_rect': [rect.x(), rect.y(), rect.width(), rect.height()],
            'new_size': new_state.font_size,
            'allow_exceed_ocr_rect': allow_exceed,
        }
        fixed_render_rects.extend(adapter.render_line_rects_for_state(item, new_state))

    return StepResult(step_name, before, after, changed_ids=changed_ids, diagnostics=diagnostics)


def step2_resolve_overlap(adapter: LayoutAdapter, items_with_state) -> StepResult:
    """겹침 + 이미지 캔버스 넘침 검사/보정.

    주의: 여기서 '크기 증가를 막는다'는 뜻은 아니다.
    이미 1+2단계에서 OCR 영역 기준 최대 크기까지 키운 상태가 들어오므로,
    이 단계는 그 목표 크기 이하에서만 이동/축소하여 겹침을 푼다.
    즉 OCR 맞춤 성장은 앞 단계에서 보장하고, 겹침 해소 패스가 새로 260px까지
    폭주하는 것만 막는다.
    """
    max_size_overrides = {item.get('id'): int(state.font_size) for item, state in items_with_state}
    return _resolve_right_to_left(adapter, items_with_state, allow_exceed_ocr_rect_ids=None,
                                   max_size_overrides=max_size_overrides,
                                   step_name='2_resolve_overlap')


# ---------------------------------------------------------------------------
# 4단계: 최빈값보다 일정 비율 이상 작은 텍스트를 최빈값까지 키운다.
# ---------------------------------------------------------------------------

def step3_grow_to_mode(adapter: LayoutAdapter, items_with_state, *, threshold_percent=65.0) -> StepResult:
    """font_size의 최빈값(mode)을 구하고, mode * threshold_percent/100 보다 작은 항목을
    mode까지 키운다 (이 단계에서는 OCR rect 안에 들어가는지는 보지 않는다 - 그건 5단계가 검사).
    """
    sizes = [st.font_size for _it, st in items_with_state]
    mode = _font_size_mode(sizes)
    threshold = mode * (float(threshold_percent) / 100.0)

    before = {it.get('id'): st for it, st in items_with_state}
    after = {}
    changed_ids = []
    diagnostics = {'mode': mode, 'threshold': threshold, 'per_item': {}}

    for item, state in items_with_state:
        item_id = item.get('id')
        if mode <= 0 or state.font_size >= threshold:
            after[item_id] = state
            diagnostics['per_item'][item_id] = {'grown': False}
            continue
        new_state = replace(state, font_size=int(mode))
        after[item_id] = new_state
        changed_ids.append(item_id)
        diagnostics['per_item'][item_id] = {'grown': True, 'old_size': state.font_size, 'new_size': mode}

    return StepResult('3_grow_to_mode', before, after, changed_ids=changed_ids, diagnostics=diagnostics)


# ---------------------------------------------------------------------------
# 5단계: 4단계로 커진 텍스트에 대해 다시 겹침/경계 검사. OCR rect 초과는 허용(예외).
# ---------------------------------------------------------------------------

def step4_resolve_overlap_after_grow(adapter: LayoutAdapter, items_with_state, grown_ids, *, size_cap=None) -> StepResult:
    """grown_ids에 속한 항목만 OCR rect를 넘어가는 배치를 허용하고, 나머지는 그대로 엄격 검사.

    size_cap: grown_ids에 속한 항목이 이 값보다 더 커지지 않도록 상한을 둔다.
    4단계가 "최빈값(mode)까지만 키운다"고 정했으므로, 5단계가 그보다 더 키워버리면
    원래 목적(작은 글자를 평균 체급까지 맞춰주는 것)을 벗어난다. None이면 제한하지 않는다
    (디버깅/실험 목적 외에는 항상 mode 값을 넘겨줄 것).
    """
    grown_ids = set(grown_ids or [])
    # 4단계도 '모드까지 키운 뒤 겹치면 줄이는' 단계다.
    # 따라서 모든 항목의 상한은 이 단계에 들어온 현재 font_size로 고정한다.
    # grown 항목은 mode(size_cap)를 넘지 않도록 한 번 더 방어한다.
    max_size_overrides = {}
    for item, state in items_with_state:
        iid = item.get('id')
        cap = int(state.font_size)
        if iid in grown_ids and size_cap is not None:
            cap = min(cap, int(size_cap))
        max_size_overrides[iid] = cap
    return _resolve_right_to_left(adapter, items_with_state, allow_exceed_ocr_rect_ids=grown_ids,
                                   max_size_overrides=max_size_overrides,
                                   step_name='4_resolve_overlap_after_grow')


# ---------------------------------------------------------------------------
# 전체 5단계를 순서대로 실행하는 진입점 + 단계별 수동 실행을 위한 레지스트리
# ---------------------------------------------------------------------------

STEP_NAMES = [
    '1_fit_linebreak_and_size',
    '2_resolve_overlap',
    '3_grow_to_mode',
    '4_resolve_overlap_after_grow',
]
"""사용자가 정의한 5단계 중 1·2번(줄내림 결정 + OCR 크기 맞춤)은 korean_linebreak_rules의
candidate_select_key가 size/fill_w/fill_h까지 같이 봐야 의미 있는 비교가 되므로, 코드 구조상
한 단계로 합쳐서 처리한다. 사용자에게 보여줄 때는 이 1단계를 "1. 줄내림 + 크기"로 표기하면
원래 의도한 5단계와 자연스럽게 대응된다."""


class AutoAdjustSession:
    """페이지 단위로 5단계를 순서대로, 또는 한 단계씩 실행할 수 있게 묶은 세션.

    UI의 "단계별 버튼"은 이 클래스의 run_step()을 호출하도록 연결하면 된다.
    run_step()은 항상 StepResult를 반환하고, 세션 내부 상태(self.states)를 갱신한다.
    각 단계 실행 전에 원본 item dict는 건드리지 않으며, finalize()를 호출해야만
    실제 item에 반영된다 (디버깅 중 실수로 원본이 바뀌는 것을 막기 위함).
    """

    def __init__(self, owner, page_idx, items):
        self.owner = owner
        self.page_idx = page_idx
        self.items = [it for it in (items or []) if isinstance(it, dict)]
        self.adapter = LayoutAdapter(owner, page_idx)
        self.states = {}          # item_id -> TextLayoutState (가장 최근 상태)
        self.history = []          # [StepResult, ...]
        self._grown_ids_from_step4 = set()
        self._mode_from_step3 = None
        try:
            self._mode_grow_threshold_percent = float(owner.auto_text_median_floor_threshold_percent())
        except Exception:
            self._mode_grow_threshold_percent = 65.0

    def _items_with_state(self):
        out = []
        for item in self.items:
            iid = item.get('id')
            state = self.states.get(iid)
            if state is None:
                continue
            out.append((item, state))
        return out

    def run_step(self, step_name: str) -> StepResult:
        if step_name == '1_fit_linebreak_and_size':
            combined_before, combined_after, combined_diag, changed = {}, {}, {}, []
            for item in self.items:
                r = step1and2_fit_linebreak_and_size(self.adapter, item)
                combined_before.update(r.before)
                combined_after.update(r.after)
                combined_diag.update(r.diagnostics)
                changed.extend(r.changed_ids)
            self.states.update(combined_after)
            result = StepResult('1_fit_linebreak_and_size', combined_before, combined_after,
                                 changed_ids=changed, diagnostics=combined_diag)

        elif step_name == '2_resolve_overlap':
            result = step2_resolve_overlap(self.adapter, self._items_with_state())
            self.states.update(result.after)

        elif step_name == '3_grow_to_mode':
            result = step3_grow_to_mode(
                self.adapter,
                self._items_with_state(),
                threshold_percent=self._mode_grow_threshold_percent,
            )
            self.states.update(result.after)
            self._grown_ids_from_step4 = set(result.changed_ids)
            self._mode_from_step3 = result.diagnostics.get('mode')

        elif step_name == '4_resolve_overlap_after_grow':
            result = step4_resolve_overlap_after_grow(
                self.adapter, self._items_with_state(), self._grown_ids_from_step4,
                size_cap=self._mode_from_step3,
            )
            self.states.update(result.after)

        else:
            raise ValueError(f'unknown step: {step_name}')

        self.history.append(result)
        return result

    def run_all(self):
        for name in STEP_NAMES:
            self.run_step(name)
        return list(self.history)

    def finalize(self):
        """세션의 최종 상태를 실제 item dict에 반영한다. 이걸 호출하기 전엔 원본이 안 바뀐다.

        실제 값이 달라진 항목만 changed_ids로 반환한다.
        """
        changed_ids = []
        for item in self.items:
            iid = item.get('id')
            state = self.states.get(iid)
            if state is None:
                continue
            text_key, old_text = self.adapter.text_key_and_value(item)
            old_state = TextLayoutState(
                item_id=iid,
                lines=tuple(str(old_text or '').split('\n')),
                font_size=int(item.get('font_size', 24) or 24),
                inner_text_x_off=int(item.get('inner_text_x_off', 0) or 0),
                inner_text_y_off=int(item.get('inner_text_y_off', 0) or 0),
            )
            if old_state != state:
                changed_ids.append(iid)
            self.adapter.apply_state_to_item(item, state)
        return changed_ids

    def snapshot_table(self):
        """현재 세션 상태를 사람이 보기 좋은 표 형태로 (UI 표시용)."""
        rows = []
        for item in self.items:
            iid = item.get('id')
            state = self.states.get(iid)
            if state is None:
                continue
            rows.append({
                'id': iid,
                'font_size': state.font_size,
                'line_count': len(state.lines),
                'inner_text_x_off': state.inner_text_x_off,
                'inner_text_y_off': state.inner_text_y_off,
            })
        return rows



# ---------------------------------------------------------------------------
# main_window_text_layout_mixin.py에서 직접 호출하는 새 본선 진입점
# ---------------------------------------------------------------------------

def _audit(owner, event, **payload):
    try:
        if hasattr(owner, 'audit_boundary_event'):
            owner.audit_boundary_event(event, **payload)
    except Exception:
        pass


def _progress(progress_cb, current, total, item=None, phase=''):
    if not progress_cb:
        return
    try:
        progress_cb(int(current), int(total), item, str(phase or ''))
    except Exception:
        pass


def _short_diag_preview(diagnostics, *, limit=6):
    """로그용 단계 진단 요약. 전체 diagnostics를 다 찍지 않고 핵심만 짧게 남긴다."""
    try:
        out = []
        for iid, diag in list((diagnostics or {}).items())[:int(limit)]:
            if isinstance(diag, dict):
                out.append({
                    'id': iid,
                    'reason': diag.get('reason'),
                    'owner_fit_used': diag.get('owner_item_fit_used'),
                    'owner_fit_changed': diag.get('owner_item_fit_changed'),
                    'before_size': diag.get('before_size'),
                    'after_size': diag.get('after_size'),
                    'chosen_size': diag.get('chosen_size'),
                    'new_size': diag.get('new_size'),
                    'grown': diag.get('grown'),
                })
            else:
                out.append({'id': iid, 'diag': str(diag)[:120]})
        return out
    except Exception:
        return []


def run_text_auto_adjust_engine_for_page(owner, page_idx=None, targets=None, *, refresh=False, progress_cb=None, reason='manual'):
    """새 텍스트 자동조정 엔진 본선 실행.

    기존 text_auto_adjust_sequence.py를 거치지 않는다. 이 함수가 페이지 단위 자동조정의
    유일한 실행 진입점이다.

    반환값은 실제로 변경된 item id 목록이다. dirty/refresh/autosave 예약까지 이 함수에서
    처리하므로, item 단위 예약 경로와 페이지/일괄 경로가 서로 다른 후처리 시퀀스를 타지 않는다.
    """
    try:
        page_idx = owner.idx if page_idx is None else int(page_idx)
    except Exception:
        page_idx = getattr(owner, 'idx', 0)

    if targets is None:
        try:
            targets = list(owner.auto_target_items_for_page(page_idx) or [])
        except Exception:
            targets = []
    else:
        targets = list(targets or [])

    # 엔진은 실제 텍스트가 있는 inpaint 텍스트 항목만 처리한다.
    active = []
    for item in targets:
        if not isinstance(item, dict) or not item.get('use_inpaint', True):
            continue
        try:
            key, value = owner._auto_layout_text_key_and_value(item)
        except Exception:
            value = item.get('translated_text') or item.get('text') or ''
        if str(value or '').strip():
            active.append(item)

    total = max(1, len(active))
    _audit(
        owner,
        'TEXT_AUTO_ADJUST_ENGINE_START',
        page_idx=page_idx,
        reason=str(reason or ''),
        target_count=len(active),
        policy='new_text_auto_adjust_engine_only_no_legacy_sequence',
    )
    _progress(progress_cb, 0, total, None, 'engine_start')

    if not active:
        _audit(owner, 'TEXT_AUTO_ADJUST_ENGINE_DONE', page_idx=page_idx, reason=str(reason or ''), changed_ids=[], changed_count=0)
        return []

    # 세로쓰기 후보는 가로쓰기 줄내림 후보 계산 전에 별도 모듈에서 한 세로 열로 정리한다.
    # 이후 공통 세션의 겹침/경계 단계는 그대로 타므로, 세로쓰기 전환 항목도 후처리 대상에 포함된다.
    vertical_pre_changed_ids = []
    try:
        from ysb.ui.text_vertical_auto_adjust_engine import apply_vertical_auto_adjust_prepass
        vertical_pre_changed_ids = apply_vertical_auto_adjust_prepass(
            owner,
            page_idx=page_idx,
            items=active,
            allow_auto_detect=True,
        ) or []
    except Exception as exc:
        _audit(owner, 'TEXT_VERTICAL_AUTO_ADJUST_PREPASS_ERROR', page_idx=page_idx, reason=str(reason or ''), error=repr(exc))

    prev_pipeline_active = bool(getattr(owner, '_auto_text_adjust_pipeline_active', False))
    prev_in_page_run = bool(getattr(owner, '_auto_text_adjust_in_page_run', False))
    owner._auto_text_adjust_pipeline_active = True
    owner._auto_text_adjust_in_page_run = True
    changed_ids = []
    try:
        session = AutoAdjustSession(owner, page_idx, active)
        step_names = list(STEP_NAMES)
        for step_index, step_name in enumerate(step_names, 1):
            if bool(getattr(owner, '_long_task_cancel_requested', False)):
                _audit(owner, 'TEXT_AUTO_ADJUST_ENGINE_CANCELLED', page_idx=page_idx, step=step_name, reason=str(reason or ''))
                break
            result = session.run_step(step_name)
            _audit(
                owner,
                'TEXT_AUTO_ADJUST_ENGINE_STEP_DONE',
                page_idx=page_idx,
                reason=str(reason or ''),
                step=step_name,
                changed_ids=[x for x in (result.changed_ids or []) if x is not None],
                changed_count=len([x for x in (result.changed_ids or []) if x is not None]),
                diag_preview=_short_diag_preview(getattr(result, 'diagnostics', {}) or {}),
            )
            # 기존 진행창은 텍스트 개수 기준으로 움직이므로 단계 진행률을 텍스트 개수 범위에 매핑한다.
            mapped_current = int(round(float(total) * float(step_index) / max(1.0, float(len(step_names)))))
            _progress(progress_cb, min(total, max(0, mapped_current)), total, None, step_name)
        if not bool(getattr(owner, '_long_task_cancel_requested', False)):
            changed_ids = list(vertical_pre_changed_ids or []) + list(session.finalize() or [])
    except Exception as exc:
        _audit(owner, 'TEXT_AUTO_ADJUST_ENGINE_ERROR', page_idx=page_idx, reason=str(reason or ''), error=repr(exc))
        raise
    finally:
        owner._auto_text_adjust_pipeline_active = prev_pipeline_active
        owner._auto_text_adjust_in_page_run = prev_in_page_run

    # 순서 보존 + 중복 제거
    changed_ids = list(dict.fromkeys([x for x in changed_ids if x is not None]))

    if changed_ids:
        try:
            owner.mark_text_engine_items_dirty(
                [x for x in active if isinstance(x, dict) and x.get('id') in changed_ids],
                fields=owner._auto_text_adjust_dirty_fields(),
                page_idx=page_idx,
            )
        except Exception:
            pass
        try:
            if refresh and page_idx == owner.idx:
                owner.refresh_text_engine_items(changed_ids, page_idx=page_idx)
        except Exception:
            pass
        try:
            if page_idx == owner.idx and owner.cb_mode.currentIndex() == 4:
                owner.schedule_final_text_scene_refresh(60)
        except Exception:
            pass
        try:
            owner.schedule_deferred_auto_save_project(1800)
        except Exception:
            pass

    _audit(
        owner,
        'TEXT_AUTO_ADJUST_ENGINE_DONE',
        page_idx=page_idx,
        reason=str(reason or ''),
        changed_ids=changed_ids,
        changed_count=len(changed_ids),
        policy='new_text_auto_adjust_engine_only_no_legacy_sequence',
    )
    _progress(progress_cb, total, total, None, 'engine_done')
    return changed_ids
