from __future__ import annotations

from typing import Any, Callable, Dict, List, Tuple

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QFont, QFontMetrics, QPainterPath, QTransform

from .common_glyph_engine import (
    ASCII_QUOTE,
    CENTER_PUNCT,
    COMMA_PUNCT,
    DOT_PUNCT,
    ELLIPSIS_TOKENS,
    FIXED_SIDEWAYS_PUNCT,
    flip_path_vertically_around_center,
    LONG_MARK_CHARS,
    QUOTE_CLOSE,
    QUOTE_OPEN,
    glyph_path,
    horizontal_ellipsis_sequence_path,
    INLINE_HORIZONTAL_SYMBOL_CHARS,
    is_corner_quote,
    is_normal_quote,
    place_path_in_vertical_cell,
    qfont_for_style,
    rotate_path_around_center,
    tight_vertical_cell_metrics,
    vertical_comma_mark_path,
    vertical_dot_mark_path,
    vertical_ellipsis_path,
    vertical_effective_char_gap,
    vertical_long_mark_path,
    vertical_normal_quote_display_char,
    vertical_normal_quote_path,
    vertical_space_advance,
    vertical_quote_display_char,
)


def _is_latin(ch: str) -> bool:
    return ('A' <= ch <= 'Z') or ('a' <= ch <= 'z') or ('Ａ' <= ch <= 'Ｚ') or ('ａ' <= ch <= 'ｚ')


def _is_digit(ch: str) -> bool:
    return ('0' <= ch <= '9') or ('０' <= ch <= '９')


def _is_code_connector(ch: str) -> bool:
    return ch in "-_/.:#＋－＿／．：＃"


def tokenize_vertical_text_spans(line: str, partial_horizontal_enabled: bool = True) -> List[Tuple[str, str, int, int]]:
    """Tokenize one vertical line while preserving source offsets.

    Zero-width spaces are used as invisible boundaries for partial horizontal
    writing.  They must not be painted, but their positions must remain in the
    logical text index space so caret movement after Space exits the horizontal
    run correctly.
    """
    line = str(line or '')
    out: List[Tuple[str, str, int, int]] = []
    i = 0
    n = len(line)
    while i < n:
        start = i
        ch = line[i]
        if ch in '\t\r\n':
            i += 1
            continue
        if ch == '\u200b':  # zero-width space: 가로쓰기 토큰 경계 마커, 렌더링 안 함
            i += 1
            continue
        if ch in ' 　':
            j = i + 1
            while j < n and line[j] in ' 　':
                j += 1
            out.append(('space', line[i:j], start, j)); i = j; continue
        # dot ellipsis: any adjacent run of . or ． becomes one visual token.
        if ch in '.．':
            j = i + 1
            while j < n and line[j] == ch:
                j += 1
            if j - i >= 2:
                out.append(('ellipsis', line[i:j], start, j)); i = j; continue
        if line.startswith('……', i):
            out.append(('ellipsis', '……', start, i + 2)); i += 2; continue
        if ch in {'…', '‥'}:
            out.append(('ellipsis', ch, start, i + 1)); i += 1; continue
        if ch in LONG_MARK_CHARS:
            j = i + 1
            while j < n and line[j] in LONG_MARK_CHARS:
                j += 1
            tok = line[i:j]
            out.append(('long_run' if len(tok) >= 2 else 'long_mark', tok, start, j)); i = j; continue
        if ch in ASCII_QUOTE:
            try:
                prev_same = sum(1 for c in line[:i] if c == ch)
            except Exception:
                prev_same = 0
            out.append(('quote_open' if prev_same % 2 == 0 else 'quote_close', ch, start, i + 1)); i += 1; continue
        if ch in QUOTE_OPEN:
            out.append(('quote_open', ch, start, i + 1)); i += 1; continue
        if ch in QUOTE_CLOSE:
            out.append(('quote_close', ch, start, i + 1)); i += 1; continue
        if bool(partial_horizontal_enabled) and (_is_latin(ch) or _is_digit(ch)):
            j = i + 1
            while j < n:
                c = line[j]
                if c == '\u200b' or c in '\t\r\n 　':
                    break
                if not (_is_latin(c) or _is_digit(c) or _is_code_connector(c)):
                    break
                # Do not absorb trailing punctuation into code/latin runs.
                if c in DOT_PUNCT or c in COMMA_PUNCT or c in CENTER_PUNCT:
                    break
                j += 1
            tok = line[i:j]
            kind = 'latin' if any(_is_latin(c) for c in tok) else 'digit'
            if any(_is_code_connector(c) for c in tok):
                kind = 'code'
            out.append((kind, tok, start, j)); i = j; continue
        if bool(partial_horizontal_enabled) and ch in INLINE_HORIZONTAL_SYMBOL_CHARS:
            j = i + 1
            while j < n and line[j] in INLINE_HORIZONTAL_SYMBOL_CHARS:
                j += 1
            out.append(('symbol_run', line[i:j], start, j)); i = j; continue
        if ch in DOT_PUNCT or ch in COMMA_PUNCT or ch in CENTER_PUNCT or ch in FIXED_SIDEWAYS_PUNCT:
            out.append(('punct', ch, start, i + 1)); i += 1; continue
        out.append(('jp', ch, start, i + 1)); i += 1
    return out


def tokenize_vertical_text(line: str, partial_horizontal_enabled: bool = True) -> List[Tuple[str, str]]:
    return [(kind, tok) for kind, tok, _start, _end in tokenize_vertical_text_spans(line, partial_horizontal_enabled=partial_horizontal_enabled)]


def _default_style_provider(_display_index: int) -> Dict[str, Any]:
    return {}


def _token_base_metrics(font: QFont, style: Dict[str, Any] | None) -> Tuple[QFont, QFontMetrics, float, float]:
    f = qfont_for_style(style, font)
    fm = QFontMetrics(f)
    cell_w, cell_h = tight_vertical_cell_metrics(f, fm)
    return f, fm, cell_w, cell_h


def _horizontal_advance_for_text(text: str, font: QFont, style: Dict[str, Any] | None) -> float:
    f = qfont_for_style(style, font)
    fm = QFontMetrics(f)
    total = 0.0
    for ch in str(text or ''):
        try:
            total += max(1.0, float(fm.horizontalAdvance(ch)))
        except Exception:
            total += max(1.0, float(fm.height()) * 0.45)
    return max(1.0, total)


def build_token_visual(kind: str, token: str, font: QFont, style: Dict[str, Any] | None, base_cell_w: float | None = None, base_cell_h: float | None = None) -> Dict[str, Any]:
    kind = str(kind or 'jp')
    token = str(token or '')
    st = dict(style or {})
    f, fm, local_w, local_h = _token_base_metrics(font, st)
    cell_w = max(1.0, float(base_cell_w or local_w or 1.0), float(local_w or 1.0))
    base_h = max(1.0, float(base_cell_h or local_h or 1.0), float(local_h or 1.0))

    path = QPainterPath()
    adv = base_h
    rotated = False
    compact_gap = False

    if kind == 'space':
        adv = vertical_space_advance(token, base_h, 0.0)
        return {'path': path, 'advance': adv, 'cell_w': cell_w, 'style': st, 'rotated': False, 'compact_gap': True}

    if kind in {'long_mark', 'long_run'}:
        adv = _horizontal_advance_for_text(token, f, st)
        cell_w = max(cell_w, float(fm.height()))
        slot = QRectF(-cell_w / 2.0, 0.0, cell_w, adv)
        path = vertical_long_mark_path(token, slot, f, st, overshoot=(kind == 'long_mark'))
        return {'path': path, 'advance': max(1.0, adv), 'cell_w': cell_w, 'style': st, 'rotated': True, 'compact_gap': False}

    if kind == 'ellipsis':
        # 폰트 원본 글리프를 90도 회전해서 세로 방향으로 표시.
        # 가로쓰기 말줄임표(…)와 동일한 폰트 글리프를 사용하되 세로로 세움.
        path = glyph_path(token[0] if token else '…', f, st)
        if path.isEmpty():
            path = glyph_path('…', f, st)
        if not path.isEmpty():
            path = rotate_path_around_center(path, 90.0)
        br = path.boundingRect()
        if br.isNull() or br.width() <= 0 or br.height() <= 0:
            adv = max(base_h * 0.78, 1.0)
            cell_w = max(cell_w, base_h * 0.24)
        else:
            adv = max(base_h * 0.58, float(br.height()) + base_h * 0.10)
            cell_w = max(cell_w, float(br.width()))
        path = place_path_in_vertical_cell(path, cell_w, adv, 0.0, 0.0)
        return {'path': path, 'advance': adv, 'cell_w': cell_w, 'style': st, 'rotated': False, 'compact_gap': True}

    raw = glyph_path(token, f, st)
    raw_rect = raw.boundingRect()

    if kind in {'quote_open', 'quote_close'}:
        # Hanging punctuation is a 2-pass layout concern.  Corner brackets and
        # quotation marks are different families and must not share the same
        # visual glyph or the same attach strength.
        corner_quote = bool(is_corner_quote(token))
        normal_quote = bool(is_normal_quote(token))
        if corner_quote:
            display_quote = vertical_quote_display_char(token, kind)
            path = glyph_path(display_quote, f, st)
            quote_family = 'corner'
            adv = max(base_h * 0.34, 1.0)
        elif normal_quote:
            # Normal quotes are NOT corner brackets and must remain in the text
            # flow.  Spaces before/after them should move the quote, so do not
            # attach them to neighboring glyphs.  Open quotes sit in the
            # upper-right of their own cell; close quotes in the lower-left.
            path = vertical_normal_quote_path(token, kind, f, st)
            quote_family = 'normal'
            adv = max(base_h * 0.42, 1.0)
            br = path.boundingRect()
            if not br.isNull() and br.width() > 0 and br.height() > 0:
                if kind == 'quote_open':
                    # 세로쓰기 open quote: 다음 글자 위쪽, 컬럼 오른쪽에 배치.
                    # 정답 이미지 기준 - 오른쪽 위
                    target_x = cell_w * 0.42
                    target_y = adv * 0.05
                    dx = target_x - br.center().x()
                    dy = target_y - br.top()
                else:
                    # 세로쓰기 close quote: 이전 글자 아래쪽, 컬럼 왼쪽에 배치.
                    # 정답 이미지 기준 - 왼쪽 아래
                    target_x = -cell_w * 0.42
                    target_y = adv * 0.95
                    dx = target_x - br.center().x()
                    dy = target_y - br.bottom()
                tr = QTransform(); tr.translate(dx, dy)
                path = tr.map(path)
            return {
                'path': path,
                'advance': adv,
                'cell_w': cell_w,
                'style': st,
                'rotated': bool(kind == 'quote_close'),
                'compact_gap': True,
                'hanging': False,
                'bleed': True,
                'raw_hanging_path': False,
                'corner_quote': False,
                'quote_family': 'normal',
            }
        else:
            display_quote = vertical_quote_display_char(token, kind)
            path = glyph_path(display_quote, f, st)
            quote_family = 'other'
            adv = max(base_h * 0.22, 1.0)
        if path.isEmpty():
            path = raw
        # Quote/bracket marks may visually sit near the column edge, but they
        # must not change the core text column width.  Widening cell_w here makes
        # the same text have a different width just because a corner bracket was
        # typed.  Keep width stable; placement is handled in the 2-pass attach.
        return {
            'path': path,
            'advance': adv,
            'cell_w': cell_w,
            'style': st,
            'rotated': bool(normal_quote and kind == 'quote_close'),
            'compact_gap': True,
            'hanging': True,
            'bleed': True,
            'raw_hanging_path': True,
            'corner_quote': corner_quote,
            'quote_family': quote_family,
        }

    if kind == 'symbol_run':
        # Consecutive special punctuation such as !? stays horizontal inside a
        # vertical line until the user inserts a space.  Treat it as one visual
        # word but keep the source as individual characters.
        path = glyph_path(token, f, st)
        br = path.boundingRect()
        adv = max(base_h * 0.72, float(br.height()) if not br.isNull() else base_h * 0.72, 1.0)
        cell_w = max(cell_w, float(br.width()) if not br.isNull() else cell_w)
        path = place_path_in_vertical_cell(path, cell_w, adv, 0.0, 0.0)
        return {'path': path, 'advance': adv, 'cell_w': cell_w, 'style': st, 'rotated': False, 'compact_gap': False, 'symbol_run': True}

    if kind == 'punct':
        path = raw
        tok = token
        if tok in DOT_PUNCT or tok in COMMA_PUNCT:
            adv = max(base_h * 0.42, 1.0)
            if tok in COMMA_PUNCT:
                # 세로쓰기 쉼표: 폰트 원본 글리프(,) + 반시계 90도 + 상하대칭.
                # ① glyph_path로 원본 , 가져옴
                # ② rotate_path_around_center(path, -90) : 반시계 90도
                # ③ flip_path_vertically_around_center(path) : 상하대칭
                path = glyph_path(tok, f, st)
                if not path.isEmpty():
                    path = rotate_path_around_center(path, -90.0)
                    path = flip_path_vertically_around_center(path)
                br_c = path.boundingRect() if not path.isEmpty() else None
                if br_c is not None and not br_c.isNull() and br_c.height() > 0:
                    adv = max(float(br_c.height()) * 1.2, base_h * 0.42)
                else:
                    adv = max(base_h * 0.42, 1.0)
                ox, oy = cell_w * 0.24, base_h * 0.02
                rotated_punct = False
            else:
                # Dot punctuation remains a compact dot.  Do not use a font
                # period glyph because some fonts make it tall after scaling.
                path = vertical_dot_mark_path(f, st)
                ox, oy = cell_w * 0.24, base_h * 0.02
                rotated_punct = False
            br = path.boundingRect()
            if not br.isNull():
                cell_w = max(cell_w, float(br.width()))
            path = place_path_in_vertical_cell(path, cell_w, adv, ox, oy)
            return {'path': path, 'advance': adv, 'cell_w': cell_w, 'style': st, 'rotated': rotated_punct, 'compact_gap': True}
        if tok in CENTER_PUNCT:
            adv = max(base_h * 0.78, 1.0)
            path = place_path_in_vertical_cell(path, cell_w, adv, 0.0, 0.0)
            return {'path': path, 'advance': adv, 'cell_w': cell_w, 'style': st, 'rotated': False, 'compact_gap': False}
        if tok in FIXED_SIDEWAYS_PUNCT:
            path = rotate_path_around_center(path, 90.0)
            adv = max(base_h * 0.80, 1.0)
            path = place_path_in_vertical_cell(path, cell_w, adv, 0.0, 0.0)
            return {'path': path, 'advance': adv, 'cell_w': cell_w, 'style': st, 'rotated': True, 'compact_gap': False}
        adv = max(base_h * 0.70, 1.0)
        path = place_path_in_vertical_cell(path, cell_w, adv, 0.0, 0.0)
        return {'path': path, 'advance': adv, 'cell_w': cell_w, 'style': st, 'rotated': False, 'compact_gap': False}

    if kind in {'latin', 'code', 'digit'}:
        # 영어/숫자/코드: 회전 없이 그대로 세로 배치.
        # 각 토큰이 하나의 행을 차지하며 가로쓰기 방향 그대로 표시.
        br = raw.boundingRect()
        adv = max(base_h, float(br.height()) if not br.isNull() else base_h)
        cell_w = max(cell_w, float(br.width()) if not br.isNull() else cell_w)
        path = place_path_in_vertical_cell(raw, cell_w, adv, 0.0, 0.0)
        return {'path': path, 'advance': adv, 'cell_w': cell_w, 'style': st, 'rotated': False, 'compact_gap': False}

    # Ordinary glyph.  Use actual ink bounds for cell width, but keep a stable
    # vertical pitch for Hangul/CJK.
    br = raw_rect
    adv = max(base_h, float(br.height()) if not br.isNull() else base_h)
    cell_w = max(cell_w, float(br.width()) if not br.isNull() else cell_w)
    path = place_path_in_vertical_cell(raw, cell_w, adv, 0.0, 0.0)
    return {'path': path, 'advance': adv, 'cell_w': cell_w, 'style': st, 'rotated': False, 'compact_gap': False}


def _gap_between(prev_kind: str | None, next_kind: str | None, base_gap: float, base_h: float) -> float:
    if not next_kind:
        return 0.0
    # If an ellipsis follows a bracket/quote, give it a little breathing room.
    # The previous zero-gap rule made 「... or 」... look glued together.
    if prev_kind in {'quote_open', 'quote_close'} and next_kind == 'ellipsis':
        return max(1.0, float(base_h) * 0.08)
    if prev_kind in {'quote_open', 'quote_close'} or next_kind in {'quote_open', 'quote_close'}:
        # quote/bracket glyphs are attached marks; do not add generic tracking
        # around them, otherwise they drift away from the wrapped glyph.
        return 0.0
    if prev_kind in {'punct', 'ellipsis'} or next_kind in {'punct', 'ellipsis'}:
        return min(max(0.0, base_gap), max(0.0, base_h * 0.05))
    return max(0.0, base_gap)



def _is_hanging_quote_entry(entry: Dict[str, Any] | None) -> bool:
    try:
        return str((entry or {}).get('kind') or '') in {'quote_open', 'quote_close'}
    except Exception:
        return False


def _is_flow_anchor_entry(entry: Dict[str, Any] | None) -> bool:
    try:
        k = str((entry or {}).get('kind') or '')
    except Exception:
        k = ''
    return bool(k and k not in {'quote_open', 'quote_close', 'space'})


def _find_attach_entry(entries: List[Dict[str, Any]], index: int, direction: int) -> Dict[str, Any] | None:
    try:
        i = int(index) + int(direction)
    except Exception:
        return None
    while 0 <= i < len(entries):
        e = entries[i]
        if _is_flow_anchor_entry(e):
            return e
        i += int(direction)
    return None


def _map_hanging_quote_path(entry: Dict[str, Any], entries: List[Dict[str, Any]], entry_index: int, x: float, core_w: float, base_h: float) -> QPainterPath:
    """Place vertical quote/bracket glyphs by attaching to neighboring text.

    Opening marks attach to the next visible glyph.  Closing marks attach to the
    previous visible glyph.  They are allowed to bleed outside the core Hangul
    column so they can visually wrap the text instead of creating a separate row.
    """
    p0 = entry.get('path0') or QPainterPath()
    if p0 is None or p0.isEmpty():
        return QPainterPath()
    br = p0.boundingRect()
    if br.isNull() or br.width() <= 0 or br.height() <= 0:
        return QPainterPath()
    kind = str(entry.get('kind') or '')
    family = str(entry.get('quote_family') or ('corner' if bool(entry.get('corner_quote', False)) else 'normal'))
    corner = family == 'corner'
    normal = family == 'normal'
    if kind == 'quote_open':
        anchor = _find_attach_entry(entries, entry_index, +1) or entry
        anchor_y = float(anchor.get('y', entry.get('y', 0.0)) or 0.0)
        if corner:
            # 홀낫표 open(「→﹁): 컬럼 안쪽으로 당겨서 글자에 밀착.
            # x에서 빼야 안쪽(왼쪽)으로 이동. 상하 여백 유지.
            target_x = float(x) + float(core_w) * 0.25
            target_y = anchor_y - float(base_h) * 0.22
        elif normal:
            # 따옴표 open: 홀낫표와 비슷한 위치 기준.
            target_x = float(x) + float(core_w) * 0.25
            target_y = anchor_y - float(br.height()) * 0.22
        else:
            target_x = float(x) + float(core_w) * 0.12
            target_y = anchor_y - float(base_h) * 0.14
        dx = target_x - br.center().x()
        dy = target_y - br.top()
    else:
        anchor = _find_attach_entry(entries, entry_index, -1) or entry
        anchor_y = float(anchor.get('y', entry.get('y', 0.0)) or 0.0) + float(anchor.get('advance', base_h) or base_h)
        if corner:
            # 홀낫표 close(」→﹂): 컬럼 안쪽으로 당겨서 글자에 밀착.
            # x에서 더해야 안쪽(오른쪽)으로 이동. 상하 여백 유지.
            target_x = float(x) - float(core_w) * 0.25
            target_y = anchor_y + float(base_h) * 0.22
        elif normal:
            # 따옴표 close: 홀낫표와 비슷한 위치 기준.
            target_x = float(x) - float(core_w) * 0.25
            target_y = anchor_y + float(br.height()) * 0.22
        else:
            target_x = float(x) - float(core_w) * 0.12
            target_y = anchor_y + float(base_h) * 0.14
        dx = target_x - br.center().x()
        dy = target_y - br.bottom()
    tr = QTransform()
    tr.translate(dx, dy)
    return tr.map(p0)

def build_vertical_text_layout(
    lines: List[str],
    font: QFont,
    *,
    align: str = 'center',
    line_height: float | None = None,
    letter_spacing: float = 0.0,
    style_provider: Callable[[int], Dict[str, Any]] | None = None,
    line_starts: List[int] | None = None,
    base_style: Dict[str, Any] | None = None,
    partial_horizontal_enabled: bool = True,
) -> Dict[str, Any]:
    align = str(align or 'center').lower()
    if align not in {'left', 'center', 'right'}:
        align = 'center'
    lines = [str(x or '') for x in (lines or [''])]
    if not lines:
        lines = ['']
    line_starts = list(line_starts or [0] * len(lines))
    style_provider = style_provider or _default_style_provider
    base_style = dict(base_style or {})
    base_font = qfont_for_style(base_style, font)
    base_fm = QFontMetrics(base_font)
    base_cell_w, base_cell_h = tight_vertical_cell_metrics(base_font, base_fm)
    base_gap = vertical_effective_char_gap(base_cell_h, letter_spacing)
    try:
        nominal_line_h = max(1.0, float(base_fm.lineSpacing()))
    except Exception:
        nominal_line_h = max(1.0, base_cell_w)
    try:
        requested_line_h = float(line_height) if line_height is not None else nominal_line_h
    except Exception:
        requested_line_h = nominal_line_h
    line_factor = max(0.50, min(3.00, requested_line_h / nominal_line_h))

    measured = []
    max_col_w = max(1.0, base_cell_w)
    for col, line in enumerate(lines):
        display_start = int(line_starts[col] if col < len(line_starts) else 0)
        toks = tokenize_vertical_text_spans(line, partial_horizontal_enabled=partial_horizontal_enabled)
        entries = []
        y = 0.0
        for ti, (kind, tok, tok_start, tok_end) in enumerate(toks):
            d = display_start + int(tok_start)
            try:
                st = dict(base_style)
                st.update(style_provider(int(d)) or {})
            except Exception:
                st = dict(base_style)
            visual = build_token_visual(kind, tok, base_font, st, base_cell_w, base_cell_h)
            adv = max(1.0, float(visual.get('advance') or base_cell_h))
            cell_w = max(1.0, float(visual.get('cell_w') or base_cell_w))
            path0 = visual.get('path') or QPainterPath()
            tok_len = max(1, len(str(tok or '')))
            entries.append({
                'kind': kind,
                'token': str(tok or ''),
                'display_index': int(d),
                'path0': path0,
                'advance': adv,
                'cell_w': cell_w,
                'style': dict(visual.get('style') or st),
                'rotated': bool(visual.get('rotated', False)),
                'y': y,
                'token_len': tok_len,
                'hanging': bool(visual.get('hanging', False)),
                'bleed': bool(visual.get('bleed', False)),
                'raw_hanging_path': bool(visual.get('raw_hanging_path', False)),
                'corner_quote': bool(visual.get('corner_quote', False)),
                'quote_family': str(visual.get('quote_family') or ''),
            })
            max_col_w = max(max_col_w, cell_w)
            y += adv
            next_kind = toks[ti + 1][0] if ti + 1 < len(toks) else None
            gap = _gap_between(kind, next_kind, base_gap, base_cell_h)
            if gap:
                y += gap
        measured.append({'line': line, 'display_start': display_start, 'entries': entries, 'height': max(1.0, y if entries else base_cell_h)})

    column_step = max(1.0, max_col_w * line_factor)
    total_width = column_step * max(0, len(measured) - 1) + max_col_w
    current_x = total_width / 2.0 - max_col_w / 2.0

    aggregate = QPainterPath()
    line_rects: List[QRectF] = []
    tokens = []
    char_slots = []
    display_caret_map: Dict[int, QPointF] = {}
    content_rect = QRectF()          # core text rect: excludes hanging quote bleed
    visual_content_rect = QRectF()   # full ink rect: includes quote/ornament bleed
    for col, info in enumerate(measured):
        x = current_x - col * column_step
        col_path = QPainterPath()
        col_rect = QRectF(x - max_col_w / 2.0, 0.0, max_col_w, max(1.0, float(info.get('height') or base_cell_h)))
        line = str(info.get('line') or '')
        display_start = int(info.get('display_start') or 0)
        display_caret_map[display_start] = QPointF(x, 0.0)
        entries_for_column = list(info.get('entries') or [])
        for entry_index, entry in enumerate(entries_for_column):
            d0 = int(entry.get('display_index') or 0)
            tok = str(entry.get('token') or '')
            tok_len = max(1, int(entry.get('token_len') or len(tok) or 1))
            adv = max(1.0, float(entry.get('advance') or base_cell_h))
            cell_w = max(1.0, float(entry.get('cell_w') or max_col_w))
            y0 = float(entry.get('y') or 0.0)
            p0 = entry.get('path0') or QPainterPath()
            mapped = QPainterPath()
            if p0 is not None and not p0.isEmpty():
                if bool(entry.get('raw_hanging_path', False)) and str(entry.get('kind') or '') in {'quote_open', 'quote_close'}:
                    mapped = _map_hanging_quote_path(entry, entries_for_column, int(entry_index), x, max_col_w, base_cell_h)
                else:
                    tr = QTransform()
                    tr.translate(x, y0)
                    mapped = tr.map(p0)
                col_path.addPath(mapped)
                r = mapped.boundingRect()
                if not r.isNull() and r.width() > 0 and r.height() > 0:
                    visual_content_rect = QRectF(r) if visual_content_rect.isNull() else visual_content_rect.united(QRectF(r))
                    if not bool(entry.get('hanging', False)):
                        content_rect = QRectF(r) if content_rect.isNull() else content_rect.united(QRectF(r))
                    col_rect = col_rect.united(QRectF(r))
            token_rect = mapped.boundingRect() if not mapped.isEmpty() else QRectF(x - cell_w/2.0, y0, cell_w, adv)
            if token_rect.isNull() or token_rect.width() <= 0 or token_rect.height() <= 0:
                token_rect = QRectF(x - cell_w/2.0, y0, cell_w, adv)
            tokens.append({**entry, 'path': mapped, 'x': x, 'y0': y0, 'rect': QRectF(token_rect)})

            # Insertion carets are flow boundaries, not abstract cell divisions.
            # Ordinary vertical text divides the token top-to-bottom.  Partial
            # horizontal tokens divide the same row left-to-right so caret movement
            # inside e.g. "456" behaves like a normal horizontal editor.
            visual_top = float(token_rect.top())
            visual_bottom = float(token_rect.bottom())
            if visual_bottom <= visual_top + 0.5:
                visual_top = y0
                visual_bottom = y0 + adv
            slot_left = min(float(token_rect.left()), x - cell_w / 2.0)
            slot_right = max(float(token_rect.right()), x + cell_w / 2.0)
            slot_w = max(1.0, slot_right - slot_left)
            inline_horizontal = str(entry.get('kind') or '') in {'latin', 'code', 'digit', 'symbol_run'}
            if inline_horizontal:
                slot_top = min(visual_top, y0)
                slot_bottom = max(visual_bottom, y0 + adv)
                slot_h = max(1.0, slot_bottom - slot_top)
                y_mid = slot_top + slot_h / 2.0
                # Use proportional advances where possible, but keep a stable
                # fallback for fonts/symbols with unusual metrics.
                advances = []
                total_adv = 0.0
                try:
                    f_for_adv = qfont_for_style(dict(entry.get('style') or {}), base_font)
                    fm_for_adv = QFontMetrics(f_for_adv)
                except Exception:
                    fm_for_adv = base_fm
                for ch2 in tok:
                    try:
                        adv2 = max(1.0, float(fm_for_adv.horizontalAdvance(ch2)))
                    except Exception:
                        adv2 = 1.0
                    advances.append(adv2)
                    total_adv += adv2
                if total_adv <= 0.0:
                    advances = [1.0 for _ in tok]
                    total_adv = float(len(advances) or 1)
                cur_x = slot_left
                for k, ch in enumerate(tok):
                    seg_w = slot_w * (float(advances[k]) / total_adv) if k < len(advances) else slot_w / float(tok_len)
                    if k == tok_len - 1:
                        next_x = slot_right
                    else:
                        next_x = min(slot_right, cur_x + max(1.0, seg_w))
                    slot = QRectF(cur_x, slot_top, max(1.0, next_x - cur_x), slot_h)
                    flow_start = QPointF(cur_x, y_mid)
                    flow_end = QPointF(next_x, y_mid)
                    char_slots.append({
                        'display_index': d0 + k,
                        'char': ch,
                        'slot': slot,
                        'token_index': len(tokens)-1,
                        'path': mapped if k == 0 else QPainterPath(),
                        'style': dict(entry.get('style') or {}),
                        'kind': str(entry.get('kind') or ''),
                        'token': tok,
                        'flow_start': flow_start,
                        'flow_end': flow_end,
                        'inline_horizontal': True,
                        'caret_axis': 'horizontal',
                    })
                    display_caret_map[d0 + k] = flow_start
                    display_caret_map[d0 + k + 1] = flow_end
                    visual_content_rect = QRectF(slot) if visual_content_rect.isNull() else visual_content_rect.united(QRectF(slot))
                    content_rect = QRectF(slot) if content_rect.isNull() else content_rect.united(QRectF(slot))
                    cur_x = next_x
            else:
                seg_h = max(1.0, (visual_bottom - visual_top) / float(tok_len))
                for k, ch in enumerate(tok):
                    top_k = visual_top + seg_h * k
                    bottom_k = visual_top + seg_h * (k + 1)
                    slot = QRectF(slot_left, top_k, slot_w, max(1.0, bottom_k - top_k))
                    char_slots.append({
                        'display_index': d0 + k,
                        'char': ch,
                        'slot': slot,
                        'token_index': len(tokens)-1,
                        'path': mapped if k == 0 else QPainterPath(),
                        'style': dict(entry.get('style') or {}),
                        'kind': str(entry.get('kind') or ''),
                        'token': tok,
                        'flow_start': QPointF(x, top_k),
                        'flow_end': QPointF(x, bottom_k),
                        'inline_horizontal': False,
                        'caret_axis': 'vertical',
                    })
                    display_caret_map[d0 + k] = QPointF(x, top_k)
                    # Do not force position d0+k+1 to the previous glyph bottom if a
                    # next glyph exists; the editor layer will prefer the next glyph's
                    # own flow_start.  Keep this as a fallback/end boundary only.
                    display_caret_map[d0 + k + 1] = QPointF(x, bottom_k)
                    visual_content_rect = QRectF(slot) if visual_content_rect.isNull() else visual_content_rect.united(QRectF(slot))
                    if str(entry.get('kind') or '') not in {'quote_open', 'quote_close'}:
                        content_rect = QRectF(slot) if content_rect.isNull() else content_rect.united(QRectF(slot))
        display_caret_map[display_start + len(line)] = display_caret_map.get(display_start + len(line), QPointF(x, float(info.get('height') or base_cell_h)))
        aggregate.addPath(col_path)
        line_rects.append(QRectF(col_rect).adjusted(-2, -2, 2, 2))
    if content_rect.isNull() or content_rect.width() <= 0 or content_rect.height() <= 0:
        content_rect = QRectF(-max_col_w / 2.0, 0.0, max_col_w, base_cell_h)
    if visual_content_rect.isNull() or visual_content_rect.width() <= 0 or visual_content_rect.height() <= 0:
        visual_content_rect = QRectF(content_rect)
    return {
        'path': aggregate,
        'line_rects': line_rects,
        'tokens': tokens,
        'char_slots': char_slots,
        'display_caret_map': display_caret_map,
        'content_rect': content_rect.adjusted(-2, -2, 2, 2),
        'visual_content_rect': visual_content_rect.adjusted(-2, -2, 2, 2),
        'base_cell_w': max_col_w,
        'base_cell_h': base_cell_h,
        'column_step': column_step,
        'total_width': total_width,
        'base_gap': base_gap,
    }


def build_vertical_text_path(lines, font, align='center', line_height=None, letter_spacing=0, base_style=None):
    partial_horizontal_enabled = bool((base_style or {}).get('partial_horizontal_writing_enabled', True))
    layout = build_vertical_text_layout(lines, font, align=align, line_height=line_height, letter_spacing=letter_spacing, base_style=base_style, partial_horizontal_enabled=partial_horizontal_enabled)
    return layout.get('path') or QPainterPath(), layout.get('line_rects') or []
