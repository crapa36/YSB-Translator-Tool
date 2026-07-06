"""Japanese vertical typesetting engine for YSB rendering.

Imported from the sample generator vertical-layout logic and used by the
main typesetting renderer when writing_direction is vertical.  It handles
attached Japanese quote marks, punctuation spacing, sideways latin/code runs,
vertical ellipsis, and short-number tate-chu-yoko-like rendering without
mutating the source text.
"""

import random

from PyQt6.QtGui import QFont, QFontMetrics, QPainterPath, QTransform
from PyQt6.QtCore import QRectF

try:
    from ysb.engines.text_layout.vertical_layout_engine import (
        build_vertical_text_path as _ysb_refactored_vertical_text_path,
        tokenize_vertical_text as _ysb_refactored_tokenize_vertical_text,
    )
except Exception:
    _ysb_refactored_vertical_text_path = None
    _ysb_refactored_tokenize_vertical_text = None

FAUX_ITALIC_SHEAR = -0.13

# Japanese/Korean vertical-layout punctuation policy:
# - Latin/digit orientation options must NEVER rotate decorative punctuation.
# - Punctuation glyphs must keep the same font-size feel as horizontal writing.
#   Only their advance/position may be compacted for vertical layout.
# - Ellipsis may flow downward in vertical writing, but its dots must not be scaled
#   down compared with the source font size.
# - Hearts/stars/music marks stay upright as decorative marks.
# - Long vowel/dash-like marks may use a fixed Japanese vertical form, but are not
#   controlled by latin/digit sideways settings.
VERTICAL_ELLIPSIS_TOKENS = {"...", "．．．", "…", "‥", "……"}
HORIZONTAL_LONG_MARK_CHARS = set("ㅡー─━—―－-–﹘﹣")
VERTICAL_LONG_MARK_CHARS = set("│｜丨ㅣ┃┆┇")
LONG_MARK_RUN_CHARS = HORIZONTAL_LONG_MARK_CHARS | VERTICAL_LONG_MARK_CHARS
JAPANESE_FIXED_SIDEWAYS_PUNCT = set("ー―-〜～／＼:;：；")
JP_PUNCT_OFFSETS = {
    # 세로쓰기 점/쉼표는 같은 중앙 칸에 박히면 튄다.
    # 단, 이전 값은 너무 오른쪽/위쪽으로 치우쳐 편집기와 확정 렌더에서
    # 쉼표가 글자 사이에 끼어 보였다.  마침표는 살짝 우상단, 쉼표는
    # 살짝 우하단으로 분리해 읽히게 한다.
    "。": (0.22, -0.06), "、": (0.22, 0.08),
    "．": (0.16, -0.08), "，": (0.18, 0.08),
    ".": (0.16, -0.08), ",": (0.18, 0.08),
}
# Render-only substitution. Source text is preserved.
# Keep ASCII dots/commas as ASCII glyphs; converting them to Japanese 。/、 made Korean
# vertical previews look too different from the source. Position/advance is handled below;
# the glyph size itself is not reduced.
VERTICAL_ASCII_PUNCT_DISPLAY = {}
ASCII_DOT_COMMA_PUNCT = {".", ",", "．", "，"}
CENTER_PUNCT = set("！？!?‼⁉♡♥♪☆★※〇○●◎□■△▲▽▼")
QUOTE_OPEN = set("「『【〔［｛〈《〝“‘（([｛＜")
QUOTE_CLOSE = set("」』】〕］｝〉》〟”’）)]｝＞")
BRACKET_CHARS = QUOTE_OPEN | QUOTE_CLOSE

ASCII_PUNCT_AS_PUNCT = set("!?！？…‥、。．，,，♡♥♪☆★※")
PROTECTED_VERTICAL_PUNCT = VERTICAL_ELLIPSIS_TOKENS | JP_PUNCT_OFFSETS.keys() | CENTER_PUNCT | set("、。．，,，")

# 세로쓰기 공백은 글자 1칸을 통째로 비우는 것이 아니라,
# 가로쓰기의 단어 사이 공백처럼 작은 세로 간격으로 처리한다.
# ASCII 공백은 약 0.32em, 전각 공백은 의도적인 넓은 공백으로 보고 약 0.50em을 쓴다.
VERTICAL_ASCII_SPACE_ADVANCE_RATIO = 0.32
VERTICAL_IDEOGRAPHIC_SPACE_ADVANCE_RATIO = 0.50
# 세로쓰기에서는 같은 UI 자간 값도 위아래 충돌 체감이 더 강하다.
# UI 값은 그대로 보이게 두고, 렌더/편집 내부에서만 최소 안전 자간을 더한다.
VERTICAL_DEFAULT_CHAR_GAP_RATIO = 0.12


def vertical_effective_char_gap(base_cell_h, raw_gap=0.0):
    """Map UI letter spacing to vertical visual gap.

    Horizontal -1px can still look safe because glyphs advance sideways, but
    vertical Korean stacks tall glyphs directly on top of each other.  Add a
    small em-based safety gap in vertical writing only, without changing the UI
    spinbox value.
    """
    try:
        base = max(1.0, float(base_cell_h or 1.0))
    except Exception:
        base = 1.0
    try:
        raw = float(raw_gap or 0.0)
    except Exception:
        raw = 0.0
    safe = max(0.0, base * VERTICAL_DEFAULT_CHAR_GAP_RATIO)
    # Positive user spacing already means "open it up". Keep it mostly direct,
    # but still add a tiny vertical safety pad so the preview/editor match.
    if raw > 0:
        return raw + safe * 0.35
    return raw + safe


def vertical_space_advance(token, base_cell_h, char_gap=0.0):
    """Return render advance for space characters in vertical writing.

    In vertical Korean/Japanese layout, an ordinary word space should behave like
    horizontal word spacing, not like a full blank glyph cell.  The source text is
    preserved; only the visual advance is compacted.
    """
    try:
        base = max(1.0, float(base_cell_h or 1.0))
    except Exception:
        base = 1.0
    try:
        gap = max(0.0, float(char_gap or 0.0))
    except Exception:
        gap = 0.0
    total = 0.0
    for ch in str(token or ' '):
        if ch == '　':
            ratio = VERTICAL_IDEOGRAPHIC_SPACE_ADVANCE_RATIO
        else:
            ratio = VERTICAL_ASCII_SPACE_ADVANCE_RATIO
        total += max(1.0, base * ratio) + gap * 0.25
    return max(1.0, total)


def _tight_vertical_cell_metrics(path_font, fm):
    """Return tight vertical glyph cell metrics for percentage-consistent spacing.

    Horizontal 50% line spacing visually brings rows close because the row pitch is
    based on the font's real line box.  The old vertical renderer used
    fm.lineSpacing() for every glyph advance and then added a separate column gap,
    so vertical 50% still looked like a full blank cell.  Use actual glyph path
    bounds as the base cell, then apply the same percentage directly to the
    column pitch.
    """
    try:
        sample = "가漢あ"
        widths = []
        heights = []
        for ch in sample:
            path = QPainterPath()
            path.addText(0, 0, path_font, ch)
            rect = path.boundingRect()
            if not rect.isNull() and rect.width() > 0 and rect.height() > 0:
                widths.append(float(rect.width()))
                heights.append(float(rect.height()))
        fw = max(1.0, float(fm.height()))
        fl = max(1.0, float(fm.lineSpacing()))
        if widths:
            cell_w = max(max(widths), fw * 0.62)
        else:
            cell_w = max(1.0, fw * 0.72)
        if heights:
            cell_h = max(max(heights), fl * 0.62)
        else:
            cell_h = max(1.0, fl * 0.72)
        # Do not exceed the full font line box; otherwise 50% can never look tight.
        cell_w = min(max(1.0, cell_w), fw)
        cell_h = min(max(1.0, cell_h), fl)
        return cell_w, cell_h
    except Exception:
        return max(1.0, float(fm.height())), max(1.0, float(fm.lineSpacing()))


def _is_ascii_latin(ch):
    return ("A" <= ch <= "Z") or ("a" <= ch <= "z")


def _is_fullwidth_latin(ch):
    return ("Ａ" <= ch <= "Ｚ") or ("ａ" <= ch <= "ｚ")


def _is_latin(ch):
    return _is_ascii_latin(ch) or _is_fullwidth_latin(ch)


def _is_digit(ch):
    return ("0" <= ch <= "9") or ("０" <= ch <= "９")


def _is_code_connector(ch):
    return ch in "-_/.:#＋－＿／．：＃"


def _is_run_body_char(ch):
    return _is_latin(ch) or _is_digit(ch) or _is_code_connector(ch)


def _clean_mode(value, allowed, default="auto"):
    value = str(value or default).strip().lower().replace("-", "_")
    return value if value in allowed else default


def _looks_like_trailing_punctuation(text, pos):
    """Return True when dot-like chars should be detached from a latin run."""
    ch = text[pos]
    if ch in "…‥、。，，!?！？♡♥♪☆★※":
        return True
    if ch in ".．":
        # Repeated ... / ．．． is punctuation, not a code connector.
        nxt = text[pos + 1] if pos + 1 < len(text) else ""
        prv = text[pos - 1] if pos > 0 else ""
        if nxt in ".．…‥" or prv in ".．…‥":
            return True
        # A dot followed by latin/digit is likely a code connector: ver.2
        return not (_is_latin(nxt) or _is_digit(nxt))
    return ch in ASCII_PUNCT_AS_PUNCT


def _is_long_mark_run_char(ch):
    return str(ch or "") in LONG_MARK_RUN_CHARS


def tokenize_vertical_text(line, partial_horizontal_enabled=True):
    """Tokenize vertical Japanese text into layout roles.

    Returns list[(kind, token)].  Latin/code/digit runs are grouped so a run can
    rotate as a single visual token.  Decorative punctuation is intentionally
    detached from latin runs so latin angle settings do not rotate quotes/marks.
    """
    if _ysb_refactored_tokenize_vertical_text is not None:
        try:
            return _ysb_refactored_tokenize_vertical_text(line, partial_horizontal_enabled=partial_horizontal_enabled)
        except Exception:
            pass
    line = str(line or "")
    out = []
    i = 0
    n = len(line)

    while i < n:
        ch = line[i]
        if ch in "\t\r\n":
            i += 1
            continue
        if ch in " 　":
            j = i + 1
            while j < n and line[j] in " 　":
                j += 1
            # 세로쓰기에서 띄어쓰기는 보이지 않는 글자가 아니라 실제 단어 간격이다.
            # 다만 글자 1칸을 통째로 비우면 말풍선에서 문단 간격처럼 벌어지므로,
            # 렌더 단계에서 작은 advance로 압축한다.
            out.append(("space", line[i:j]))
            i = j
            continue

        # Dot ellipsis should be one render token, not "..." + leftover dot.
        # This keeps edit/commit preview consistent for "...", "....", "．．．．" etc.
        if ch in ".．":
            j = i + 1
            while j < n and line[j] == ch:
                j += 1
            if j - i >= 2:
                out.append(("punct", line[i:j]))
                i = j
                continue
        if line.startswith("……", i):
            out.append(("punct", "……"))
            i += 2
            continue

        if _is_long_mark_run_char(ch):
            j = i + 1
            while j < n and _is_long_mark_run_char(line[j]):
                j += 1
            token = line[i:j]
            if len(token) >= 2:
                out.append(("long_run", token))
            else:
                out.append(("long_mark", token))
            i = j
            continue

        if ch in "\"'":
            # Straight ASCII quotes have no open/close shape in the code point.
            # Decide by parity inside the current line so editor/final renderer
            # can still use different vertical offsets for opening/closing marks.
            prev_same = 0
            try:
                prev_same = sum(1 for c in line[:i] if c == ch)
            except Exception:
                prev_same = 0
            out.append(("quote_open" if prev_same % 2 == 0 else "quote_close", ch))
            i += 1
            continue

        if ch in QUOTE_OPEN:
            out.append(("quote_open", ch))
            i += 1
            continue
        if ch in QUOTE_CLOSE:
            out.append(("quote_close", ch))
            i += 1
            continue

        if bool(partial_horizontal_enabled) and (_is_latin(ch) or _is_digit(ch)):
            j = i + 1
            while j < n:
                c = line[j]
                if c in "\t\r\n":
                    break
                if c in " 　":
                    k = j + 1
                    while k < n and line[k] in " 　":
                        k += 1
                    if k < n and (_is_latin(line[k]) or _is_digit(line[k])):
                        j = k
                        continue
                    break
                if _looks_like_trailing_punctuation(line, j):
                    break
                if not _is_run_body_char(c):
                    break
                j += 1
            token = line[i:j].strip()
            if token:
                has_latin = any(_is_latin(c) for c in token)
                has_digit = any(_is_digit(c) for c in token)
                has_space = any(c in " 　" for c in token)
                has_connector = any(_is_code_connector(c) for c in token)
                if has_latin and (has_digit or has_connector or has_space):
                    kind = "code" if (has_digit or has_connector) else "latin"
                elif has_latin:
                    kind = "latin"
                elif has_digit:
                    kind = "digit"
                else:
                    kind = "punct"
                out.append((kind, token))
            i = max(j, i + 1)
            continue

        if ch in JAPANESE_FIXED_SIDEWAYS_PUNCT or ch in JP_PUNCT_OFFSETS or ch in CENTER_PUNCT or ch in ASCII_PUNCT_AS_PUNCT:
            out.append(("punct", ch))
        else:
            out.append(("jp", ch))
        i += 1
    return out


def _rotate_path_around_center(path, angle):
    rect = path.boundingRect()
    if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
        return path
    c = rect.center()
    tr = QTransform()
    tr.translate(c.x(), c.y())
    tr.rotate(float(angle or 0))
    tr.translate(-c.x(), -c.y())
    return tr.map(path)


def build_japanese_vertical_text_path(
    lines,
    font,
    align="center",
    line_height=None,
    letter_spacing=0,
    latin_mode="auto",
    digit_mode="auto",
    punctuation_mode="japanese_vertical",
    random_key="",
    vertical_char_spacing=None,
    base_style=None,
    partial_horizontal_enabled=True,
):
    """Build a QPainterPath for Japanese vertical layout.

    This is an experimental, sample-generator-focused layout engine.  It keeps
    quote marks close to adjacent glyphs, separates latin/code runs from trailing
    punctuation, and gives ordinary punctuation more breathing room than quotes.
    """
    if _ysb_refactored_vertical_text_path is not None:
        try:
            return _ysb_refactored_vertical_text_path(
                lines,
                font,
                align=align,
                line_height=line_height,
                letter_spacing=letter_spacing,
                base_style=base_style,
            )
        except Exception:
            pass
    align = (align or "center").lower()
    if align not in ("left", "center", "right"):
        align = "center"
    try:
        letter_spacing = int(letter_spacing or 0)
    except Exception:
        letter_spacing = 0
    base_style = dict(base_style or {})

    latin_mode = _clean_mode(latin_mode, {"auto", "upright", "sideways", "random"}, "auto")
    digit_mode = _clean_mode(digit_mode, {"auto", "upright", "sideways", "tate_chu_yoko", "random"}, "auto")
    punctuation_mode = _clean_mode(punctuation_mode, {"japanese_vertical", "centered", "rotated", "random"}, "japanese_vertical")

    try:
        rng = random.Random(str(random_key or "japanese_vertical_text"))
    except Exception:
        rng = random.Random(0)

    italic_requested = bool(font.italic())
    path_font = QFont(font)
    path_font.setItalic(False)
    fm = QFontMetrics(path_font)
    nominal_line_h = max(1.0, float(fm.lineSpacing()))
    if line_height is None:
        line_height = nominal_line_h
    try:
        requested_line_h = max(1.0, float(line_height))
    except Exception:
        requested_line_h = nominal_line_h

    # 세로쓰기에서는 같은 UI 값을 가로쓰기와 다르게 읽는다.
    # - letter_spacing: 위/아래 글자 사이의 세로 자간
    # - line_spacing: 오른쪽 열과 왼쪽 열 사이의 열 간격
    # 글자 기본 셀 높이까지 line_spacing으로 키우면 세로쓰기 전체가 과하게 늘어나므로
    # 기본 글자 피치는 폰트 기준으로 유지하고, 열 간격만 line_spacing 비율로 조절한다.
    base_cell_w, base_cell_h = _tight_vertical_cell_metrics(path_font, fm)
    try:
        vertical_char_spacing = int(letter_spacing if vertical_char_spacing is None else vertical_char_spacing)
    except Exception:
        vertical_char_spacing = 0
    char_gap = vertical_effective_char_gap(base_cell_h, vertical_char_spacing)
    line_factor = max(0.50, min(3.00, requested_line_h / nominal_line_h))

    def vertical_column_step(cell_w):
        # Same user meaning as horizontal line spacing:
        # 50% = almost touching/overlapping, 100% = normal cell pitch,
        # 150%+ = extra breathing room.
        try:
            return max(1.0, float(cell_w) * float(line_factor))
        except Exception:
            return max(1.0, float(cell_w or 1.0))

    def make_path(token):
        token_path = QPainterPath()
        token_path.addText(0, 0, path_font, str(token or ""))
        if italic_requested and not token_path.isEmpty():
            shear = QTransform()
            shear.shear(FAUX_ITALIC_SHEAR, 0.0)
            token_path = shear.map(token_path)
        return token_path

    def is_vertical_ellipsis_token(token):
        token = str(token or "")
        if token in VERTICAL_ELLIPSIS_TOKENS:
            return True
        if len(token) >= 2 and all(ch == "." for ch in token):
            return True
        if len(token) >= 2 and all(ch == "．" for ch in token):
            return True
        return False

    def horizontal_long_mark_thickness(rect, style=None):
        rr = QRectF(rect)
        if rr.isNull() or rr.width() <= 0 or rr.height() <= 0:
            return 2.0
        st = dict(style or base_style or {})
        try:
            font_size = float(st.get('font_size') or (path_font.pixelSize() if path_font.pixelSize() > 0 else fm.height()))
        except Exception:
            font_size = float(fm.height())
        # Stroke/outline is applied by the painter.  Do not include stroke_width
        # in the fill bar thickness, otherwise vertical long marks become
        # double-thick compared with the horizontal glyph.
        return max(1.2, min(float(rr.height()) * 0.18, max(font_size * 0.075, 1.2)))

    def horizontal_long_mark_path_in_rect(rect, style=None, overshoot=False):
        rr = QRectF(rect)
        path = QPainterPath()
        if rr.isNull() or rr.width() <= 0 or rr.height() <= 0:
            return path
        thickness = horizontal_long_mark_thickness(rr, style)
        extra = min(float(rr.width()) * 0.18, thickness * 0.9) if overshoot else 0.0
        bar = QRectF(
            rr.left() - extra,
            rr.center().y() - thickness / 2.0,
            rr.width() + extra * 2.0,
            thickness,
        )
        radius = max(0.5, thickness / 2.0)
        path.addRoundedRect(bar, radius, radius)
        return path

    def horizontal_special_metrics(token):
        total_adv = 0.0
        for ch in str(token or ""):
            try:
                adv = float(fm.horizontalAdvance(ch))
            except Exception:
                try:
                    adv = float(fm.boundingRect(ch).width())
                except Exception:
                    adv = float(path_font.pixelSize() if path_font.pixelSize() > 0 else fm.height())
            total_adv += max(1.0, adv)
        metric_h = max(1.0, float(fm.height()))
        return max(1.0, total_adv), metric_h

    def horizontal_canonical_rect_for_vertical_slot(slot_rect):
        rr = QRectF(slot_rect)
        return QRectF(0.0, 0.0, max(1.0, rr.height()), max(1.0, rr.width()))

    def rotate_horizontal_path_to_vertical_slot(path, horizontal_rect, target_rect):
        if path is None or path.isEmpty():
            return QPainterPath()
        hr = QRectF(horizontal_rect)
        trr = QRectF(target_rect)
        tr = QTransform()
        tr.translate(trr.center().x(), trr.center().y())
        tr.rotate(90.0)
        tr.translate(-hr.center().x(), -hr.center().y())
        return tr.map(path)

    def make_vertical_long_mark_path(token, slot_rect, style=None, overshoot=False):
        rr = QRectF(slot_rect)
        if rr.isNull() or rr.width() <= 0 or rr.height() <= 0:
            return QPainterPath()
        hrect = horizontal_canonical_rect_for_vertical_slot(rr)
        hpath = horizontal_long_mark_path_in_rect(hrect, style, overshoot=overshoot)
        return rotate_horizontal_path_to_vertical_slot(hpath, hrect, rr)

    def ellipsis_dot_count(token):
        token = str(token or "")
        if token == "‥":
            return 2
        if token in {"…", "...", "．．．"}:
            return 3
        if token == "……":
            return 6
        return max(2, min(6, len(token)))

    def _ellipsis_dot_source_chars(token):
        token = str(token or "")
        if token == "……":
            return ["…", "…"]
        if token == "‥":
            return ["．", "．"]
        if token == "．．．":
            return ["．", "．", "．"]
        if token == "...":
            return [".", ".", "."]
        if token == "…":
            # Use the actual horizontal ellipsis glyph when the source is a single
            # ellipsis character.  Do not replace it with Japanese middle dots.
            return ["…"]
        return list(token) if token else ["."]

    def make_vertical_ellipsis_path(token):
        # Canonical rule for vertical ellipsis: build the same horizontal glyph
        # sequence first, then rotate the whole path into the vertical column.
        # Do not rebuild it from individual dots; otherwise editor/canvas/caret
        # spacing diverges from horizontal punctuation metrics.
        token = str(token or "")
        hpath = make_path(token)
        hrect = hpath.boundingRect()
        if hpath.isEmpty() or hrect.isNull() or hrect.width() <= 0 or hrect.height() <= 0:
            hpath = make_path(".")
            hrect = hpath.boundingRect()
        if hrect.isNull() or hrect.width() <= 0 or hrect.height() <= 0:
            return QPainterPath(), max(base_cell_h * 0.78, 1.0)

        out = _rotate_path_around_center(hpath, 90.0)
        rect = out.boundingRect()
        if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
            return out, max(base_cell_h * 0.78, 1.0)
        tr = QTransform()
        tr.translate(-rect.center().x(), -rect.top())
        out = tr.map(out)
        rect = out.boundingRect()
        return out, max(base_cell_h * 0.78, float(rect.height()))

    def normalize_mode(kind, token):
        if kind in {"latin", "code"}:
            mode = latin_mode
            if mode == "random":
                return rng.choice(["upright", "sideways"])
            if mode == "auto":
                only_fullwidth_latin = all((_is_fullwidth_latin(c) or _is_code_connector(c) or c in " 　") for c in token)
                if only_fullwidth_latin and len(token) <= 3:
                    return "upright"
                return "sideways" if len(token) >= 2 or kind == "code" else "upright"
            return mode
        if kind == "digit":
            mode = digit_mode
            if mode == "random":
                return rng.choice(["upright", "sideways", "tate_chu_yoko"])
            if mode == "auto":
                n = len(str(token or ""))
                if 2 <= n <= 3:
                    return "tate_chu_yoko"
                return "sideways" if n >= 4 else "upright"
            return mode
        if kind in {"punct", "long_mark", "long_run"}:
            mode = punctuation_mode
            if mode == "random":
                return rng.choice(["japanese_vertical", "centered", "rotated"])
            return mode
        return "upright"

    path = QPainterPath()
    line_rects = []
    current_x = 0.0

    for line in lines or []:
        tokens = tokenize_vertical_text(line, partial_horizontal_enabled=partial_horizontal_enabled)
        col_path = QPainterPath()
        current_y = 0.0
        max_cell_w = max(1.0, float(base_cell_w))

        for kind, token in tokens:
            token = str(token or "")
            if not token:
                continue
            if kind == "space":
                # 세로쓰기 공백은 가로쓰기의 단어 사이 공백처럼 작은 간격으로 처리한다.
                # 원문 공백은 그대로 유지하고, 렌더링 진행 위치만 0.32em 수준으로 내린다.
                current_y += vertical_space_advance(token, base_cell_h, char_gap)
                continue

            if kind in {"long_mark", "long_run"}:
                adv_h, metric_h = horizontal_special_metrics(token)
                slot = QRectF(-metric_h / 2.0, current_y, metric_h, max(1.0, adv_h))
                token_path = make_vertical_long_mark_path(token, slot, base_style, overshoot=(kind == "long_mark"))
                if token_path.isEmpty():
                    current_y += max(1.0, adv_h) + char_gap
                    max_cell_w = max(max_cell_w, float(metric_h))
                    continue
                col_path.addPath(token_path)
                token_rect = token_path.boundingRect()
                max_cell_w = max(max_cell_w, float(max(token_rect.width(), metric_h, base_cell_w)))
                current_y += max(1.0, float(slot.height())) + char_gap
                continue

            mode = normalize_mode(kind, token)
            display_token = VERTICAL_ASCII_PUNCT_DISPLAY.get(token, token) if kind == "punct" else token
            token_path = make_path(display_token)
            if token_path.isEmpty():
                current_y += base_cell_h
                continue

            cell_h = base_cell_h
            offset_x = 0.0
            offset_y = 0.0

            if kind in {"quote_open", "quote_close"}:
                # Quote marks are decorative/clinging marks.  They must be much
                # closer to adjacent characters than ordinary punctuation.
                if punctuation_mode in {"rotated", "japanese_vertical"}:
                    token_path = _rotate_path_around_center(token_path, 90.0)
                # Opening marks cling to the upper/right side of the next glyph,
                # closing marks to the lower/left side of the previous glyph.
                # The old close offset used a negative y and made 「」/『』 float
                # into the same vertical slot as the following character.
                cell_h = max(base_cell_h * 0.42, 1.0)
                if kind == "quote_open":
                    offset_y = -base_cell_h * 0.12
                    offset_x = max_cell_w * 0.16
                else:
                    offset_y = base_cell_h * 0.16
                    offset_x = -max_cell_w * 0.16
            elif kind == "punct":
                # Protected Japanese punctuation has fixed vertical behavior.
                # It must not be affected by english/number/punctuation random angle options.
                if is_vertical_ellipsis_token(token):
                    token_path, cell_h = make_vertical_ellipsis_path(token)
                    offset_x = 0.0
                    offset_y = 0.0
                elif token in JP_PUNCT_OFFSETS:
                    ox, oy = JP_PUNCT_OFFSETS.get(token, (0.0, 0.0))
                    offset_x = ox * max_cell_w
                    offset_y = oy * base_cell_h
                    cell_h = max(base_cell_h * 0.72, 1.0)
                    # ASCII . , 는 일본식 。、로 바꾸지 않고 원래 glyph 크기 그대로 쓴다.
                    # 세로쓰기에서 필요한 것은 표시 크기 축소가 아니라 위치 보정이다.
                    if token in ASCII_DOT_COMMA_PUNCT:
                        rect0 = token_path.boundingRect()
                        if not rect0.isNull() and rect0.width() > 0 and rect0.height() > 0:
                            if token in {",", "，"}:
                                offset_x = 0.18 * max_cell_w
                                offset_y = 0.08 * base_cell_h
                            else:
                                offset_x = 0.16 * max_cell_w
                                offset_y = -0.08 * base_cell_h
                elif token in CENTER_PUNCT:
                    # Hearts/stars/music marks are upright decorative symbols in
                    # vertical Japanese samples.  Do not rotate them.
                    cell_h = max(base_cell_h * 0.88, 1.0)
                elif token in JAPANESE_FIXED_SIDEWAYS_PUNCT:
                    # Dash-like marks use a fixed Japanese vertical form.
                    token_path = _rotate_path_around_center(token_path, 90.0)
                    cell_h = max(base_cell_h * 0.86, 1.0)
                elif mode == "rotated":
                    token_path = _rotate_path_around_center(token_path, 90.0)
                    cell_h = max(base_cell_h * 0.86, 1.0)
                else:
                    cell_h = max(base_cell_h * 0.78, 1.0)
            elif mode == "sideways":
                token_path = _rotate_path_around_center(token_path, 90.0)
            elif mode == "tate_chu_yoko":
                rect0 = token_path.boundingRect()
                max_w = max_cell_w * 0.96
                if rect0.width() > max_w and rect0.width() > 0:
                    tr = QTransform()
                    scale = max(0.35, max_w / rect0.width())
                    tr.scale(scale, scale)
                    token_path = tr.map(token_path)
                cell_h = base_cell_h
            else:
                # Upright latin/digit/code mode: split into single vertical cells.
                if len(token) > 1 and kind in {"latin", "digit", "code"}:
                    for ch in token:
                        if ch in " \t　":
                            current_y += vertical_space_advance(ch, base_cell_h, char_gap)
                            continue
                        ch_path = make_path(ch)
                        ch_rect = ch_path.boundingRect()
                        if ch_rect.isNull() or ch_rect.width() <= 0 or ch_rect.height() <= 0:
                            ch_rect = QRectF(0, -fm.ascent(), max(1, fm.averageCharWidth()), max(1, base_cell_h))
                        max_cell_w = max(max_cell_w, float(max(ch_rect.width(), base_cell_w)))
                        tr = QTransform()
                        tr.translate(-ch_rect.center().x(), current_y + base_cell_h * 0.5 - ch_rect.center().y())
                        if not ch_path.isEmpty():
                            col_path.addPath(tr.map(ch_path))
                        current_y += base_cell_h + char_gap
                    continue

            token_rect = token_path.boundingRect()
            if token_rect.isNull() or token_rect.width() <= 0 or token_rect.height() <= 0:
                token_rect = QRectF(0, -fm.ascent(), max(1, fm.averageCharWidth()), max(1, base_cell_h))
            if mode == "sideways" or kind == "code" or (kind == "punct" and token in JAPANESE_FIXED_SIDEWAYS_PUNCT) or (kind == "punct" and mode == "rotated" and token not in PROTECTED_VERTICAL_PUNCT):
                cell_h = max(cell_h, float(token_rect.height()) + max(0.0, char_gap))
            max_cell_w = max(max_cell_w, float(max(token_rect.width(), base_cell_w)))
            tr = QTransform()
            tr.translate(offset_x - token_rect.center().x(), current_y + cell_h * 0.5 - token_rect.center().y() + offset_y)
            if not token_path.isEmpty():
                col_path.addPath(tr.map(token_path))
            current_y += cell_h + char_gap

        col_rect = col_path.boundingRect()
        if col_rect.isNull() or col_rect.width() <= 0 or col_rect.height() <= 0:
            col_rect = QRectF(-max_cell_w * 0.5, 0, max_cell_w, max(1.0, base_cell_h))

        if align == "left":
            dx = current_x - col_rect.left()
        elif align == "right":
            dx = current_x - col_rect.right()
        else:
            dx = current_x - col_rect.center().x()
        tr = QTransform()
        tr.translate(dx, 0)
        if not col_path.isEmpty():
            mapped = tr.map(col_path)
            path.addPath(mapped)
            col_rect = mapped.boundingRect()
        else:
            col_rect = QRectF(col_rect)
            col_rect.translate(dx, 0)

        line_rects.append(QRectF(col_rect))
        current_x -= vertical_column_step(max_cell_w)

    return path, line_rects
