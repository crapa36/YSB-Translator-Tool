from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QBrush, QTransform

from ysb.core.text_style_limits import (
    clamp_text_line_spacing,
    positive_scale_factor,
    qt_font_stretch_value,
    text_line_height_from_percent,
)
from ysb.engine.graphics_items import _normalize_partial_style_runs, _style_for_char_index, _line_char_path_for_style, _same_long_mark_pair, _style_run_signature, _same_mergeable_special_pair


def _apply_readable_bold(font: QFont, enabled: bool) -> QFont:
    try:
        font.setWeight(QFont.Weight.DemiBold if enabled else QFont.Weight.Normal)
    except Exception:
        try:
            font.setBold(bool(enabled))
        except Exception:
            pass
    return font


def _style_int(value: Any, default: int = 0, min_value: int | None = None, max_value: int | None = None) -> int:
    try:
        out = int(value if value is not None else default)
    except Exception:
        out = int(default)
    if min_value is not None:
        out = max(int(min_value), out)
    if max_value is not None:
        out = min(int(max_value), out)
    return out


def _color_name(value: Any, fallback: str) -> str:
    """Return a stable #rrggbb string without turning QColor objects into black.

    The live editor receives colors from two places: the saved TextData dict and
    the in-editor cached attributes.  The cached attributes are QColor objects.
    Calling str(QColor(...)) produces a PyQt object repr, not '#ffffff', so the
    previous helper treated valid white text as invalid and fell back to black.
    Keep text color, stroke color and partial-run colors as data colors; contrast
    colors for the workbench background must never overwrite them.
    """
    try:
        if isinstance(value, QColor):
            c = QColor(value)
        else:
            c = QColor(str(value if value is not None and value != '' else fallback))
    except Exception:
        c = QColor(fallback)
    if not c.isValid():
        c = QColor(fallback)
    return c.name()


def _style_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'on', 'y')
    return bool(value)


class YSBInlineEditRenderer:
    """Fast editor-only text renderer used while an inline editor is open.

    This is deliberately *not* the final/canvas/export renderer.  It supports the
    text properties that must be editable live (font, size, fill, stroke, bold,
    italic, strike, spacing, char scale and partial runs), while ignoring advanced
    display effects such as arc/trapezoid/skew/shadow/glow.  The same TextData is
    still used by the canvas/export renderers after the editor is closed.
    """

    def __init__(self, owner: Any):
        self.owner = owner

    def _base_style(self) -> Dict[str, Any]:
        o = self.owner
        target = getattr(o, 'target_item', None)
        data = getattr(target, 'data', {}) if target is not None else {}
        if not isinstance(data, dict):
            data = {}
        try:
            cached_font = getattr(o, '_inline_font', None) or getattr(o, '_base_font', None) or QFont()
        except Exception:
            cached_font = QFont()
        try:
            family = str(data.get('font_family') or cached_font.family() or 'Arial')
        except Exception:
            family = 'Arial'
        try:
            cached_size = int(cached_font.pixelSize()) if cached_font.pixelSize() and cached_font.pixelSize() > 0 else 20
        except Exception:
            cached_size = 20
        try:
            size = int(data.get('font_size') or cached_size or 20)
        except Exception:
            size = 20
        size = max(1, size)
        data_text_color = data.get('text_color', data.get('color', '#000000'))
        data_stroke_color = data.get('stroke_color', '#FFFFFF')
        style = {
            'font_family': family,
            'font_size': size,
            # Keep original text/stroke colors.  The workbench contrast background is
            # separate and must not leak into these values.
            'text_color': _color_name(getattr(o, '_inline_text_color', data_text_color), _color_name(data_text_color, '#000000')),
            'stroke_color': _color_name(getattr(o, '_inline_stroke_color', data_stroke_color), _color_name(data_stroke_color, '#FFFFFF')),
            'stroke_width': _style_int(getattr(o, '_inline_stroke_width', data.get('stroke_width', 0)), 0, 0, 200),
            'bold': _style_bool(data.get('bold'), bool(cached_font.bold())),
            'italic': _style_bool(data.get('italic'), bool(cached_font.italic())),
            'strike': _style_bool(data.get('strike', data.get('strikeout', False)), False),
            'line_spacing': _style_int(getattr(o, 'line_spacing_pct', data.get('line_spacing', 100)), 100, 10, 1000),
            'letter_spacing': _style_int(getattr(o, 'letter_spacing', data.get('letter_spacing', 0)), 0, -500, 500),
            'char_width': _style_int(getattr(o, 'char_width_pct', data.get('char_width', 100)), 100, 10, 1000),
            'char_height': _style_int(getattr(o, 'char_height_pct', data.get('char_height', 100)), 100, 10, 1000),
        }
        try:
            if hasattr(o, '_inline_trace') and not bool(getattr(o, '_ysb_live_style_snapshot_logged', False)):
                o._ysb_live_style_snapshot_logged = True
                o._inline_trace(
                    'INLINE_EDITOR_LIVE_STYLE_SNAPSHOT',
                    font_family=style.get('font_family'),
                    font_size=style.get('font_size'),
                    text_color=style.get('text_color'),
                    stroke_color=style.get('stroke_color'),
                    stroke_width=style.get('stroke_width'),
                    align=str(getattr(o, 'align', data.get('align', 'center'))),
                    letter_spacing=getattr(o, 'letter_spacing', data.get('letter_spacing', 0)),
                    line_spacing=getattr(o, 'line_spacing_pct', data.get('line_spacing', 100)),
                    char_width=getattr(o, 'char_width_pct', data.get('char_width', 100)),
                    char_height=getattr(o, 'char_height_pct', data.get('char_height', 100)),
                )
        except Exception:
            pass
        return style

    def _clean_style(self, style: Dict[str, Any], base_style: Dict[str, Any] | None = None) -> Dict[str, Any]:
        base = dict(base_style or {})
        if isinstance(style, dict):
            base.update(style)
        base['font_family'] = str(base.get('font_family') or (base_style or {}).get('font_family') or 'Arial')
        base['font_size'] = _style_int(base.get('font_size', (base_style or {}).get('font_size', 20)), 20, 1, 9999)
        base['text_color'] = _color_name(base.get('text_color'), _color_name((base_style or {}).get('text_color'), '#000000'))
        base['stroke_color'] = _color_name(base.get('stroke_color'), _color_name((base_style or {}).get('stroke_color'), '#FFFFFF'))
        base['stroke_width'] = _style_int(base.get('stroke_width', (base_style or {}).get('stroke_width', 0)), 0, 0, 200)
        base['bold'] = _style_bool(base.get('bold'), _style_bool((base_style or {}).get('bold'), False))
        base['italic'] = _style_bool(base.get('italic'), _style_bool((base_style or {}).get('italic'), False))
        base['strike'] = _style_bool(base.get('strike', base.get('strikeout', False)), _style_bool((base_style or {}).get('strike'), False))
        base['line_spacing'] = _style_int(base.get('line_spacing', (base_style or {}).get('line_spacing', 100)), 100, 10, 1000)
        base['letter_spacing'] = _style_int(base.get('letter_spacing', (base_style or {}).get('letter_spacing', 0)), 0, -500, 500)
        base['char_width'] = _style_int(base.get('char_width', (base_style or {}).get('char_width', 100)), 100, 10, 1000)
        base['char_height'] = _style_int(base.get('char_height', (base_style or {}).get('char_height', 100)), 100, 10, 1000)
        return base

    def _font_for_style(self, style: Dict[str, Any]) -> QFont:
        st = self._clean_style(style)
        family = str(st.get('font_family') or 'Arial')
        size = _style_int(st.get('font_size', 20), 20, 1, 9999)
        f = QFont(family)
        f.setPixelSize(size)
        _apply_readable_bold(f, bool(st.get('bold', False)))
        f.setItalic(bool(st.get('italic', False)))
        # Do not set QFont stretch here.  The canvas/display renderer creates the
        # normal glyph path first and then applies char_width/char_height scaling.
        # Applying font stretch here and then scaling the path/advance again makes
        # the editor diverge from the stored text options.
        return f

    def _style_char_width_scale(self, style: Dict[str, Any]) -> float:
        try:
            return max(0.01, float(_style_int((style or {}).get('char_width', 100), 100, 10, 1000)) / 100.0)
        except Exception:
            return 1.0

    def _style_char_height_scale(self, style: Dict[str, Any]) -> float:
        try:
            return max(0.01, float(_style_int((style or {}).get('char_height', 100), 100, 10, 1000)) / 100.0)
        except Exception:
            return 1.0

    def _style_letter_spacing(self, style: Dict[str, Any], default_spacing: float = 0.0) -> float:
        try:
            return float(_style_int((style or {}).get('letter_spacing', default_spacing), int(default_spacing or 0), -500, 500))
        except Exception:
            return float(default_spacing or 0.0)

    def _cursor_step_after_char(self, ch: str, next_ch: str, advance: float, style: Dict[str, Any], default_spacing: float = 0.0) -> float:
        try:
            adv = max(1.0, float(advance))
        except Exception:
            adv = 1.0
        if _same_long_mark_pair(ch, next_ch):
            return max(1.0, adv * 0.18)
        return adv + self._style_letter_spacing(style, default_spacing)

    def _style_for_logical_index(self, logical_index: int, runs: List[Dict[str, Any]], base_style: Dict[str, Any]) -> Dict[str, Any]:
        if logical_index < 0:
            return self._clean_style(base_style, base_style)
        try:
            return self._clean_style(_style_for_char_index(runs, int(logical_index), base_style), base_style)
        except Exception:
            return self._clean_style(base_style, base_style)

    def _advance_for_char(self, ch: str, style: Dict[str, Any]) -> float:
        font = self._font_for_style(style)
        try:
            adv = float(QFontMetrics(font).horizontalAdvance(str(ch) if ch else ' '))
        except Exception:
            adv = float(_style_int(style.get('font_size', 20), 20))
        try:
            adv *= self._style_char_width_scale(style)
        except Exception:
            pass
        return max(1.0, adv)

    def _line_width(self, line: str, start_index: int, runs: List[Dict[str, Any]], base_style: Dict[str, Any], letter_spacing: float) -> float:
        cursor = 0.0
        max_right = 0.0
        chars = list(str(line or ''))
        for j, ch in enumerate(chars):
            st = self._style_for_logical_index(int(start_index) + j, runs, base_style)
            adv = self._advance_for_char(ch, st)
            max_right = max(max_right, cursor + adv)
            next_ch = chars[j + 1] if j + 1 < len(chars) else ''
            cursor += self._cursor_step_after_char(ch, next_ch, adv, st, letter_spacing)
        return max(0.0, max_right)


    def layout_horizontal(self) -> Dict[str, Any]:
        o = self.owner
        try:
            display_text, logical_text, preedit, preedit_caret, preedit_len = o._inline_display_text_with_preedit()
        except Exception:
            display_text = str(o.toPlainText() or '')
            logical_text = display_text
            preedit = ''
            preedit_caret = 0
            preedit_len = 0
        logical_len = len(str(logical_text or ''))
        base_style = self._base_style()
        target = getattr(o, 'target_item', None)
        data = getattr(target, 'data', {}) if target is not None else {}
        if not isinstance(data, dict):
            data = {}
        runs = _normalize_partial_style_runs(data.get('partial_style_runs') or data.get('style_runs') or [], logical_len)
        base_font = self._font_for_style(base_style)
        try:
            base_fm = QFontMetrics(base_font)
            base_line = float(base_fm.lineSpacing())
        except Exception:
            base_line = float(base_style.get('font_size', 20)) + 4.0
        try:
            line_spacing_pct = clamp_text_line_spacing(getattr(o, 'line_spacing_pct', data.get('line_spacing', 100)), 100)
        except Exception:
            line_spacing_pct = 100
        try:
            base_sy = positive_scale_factor(getattr(o, 'char_height_pct', data.get('char_height', 100)))
        except Exception:
            base_sy = 1.0
        line_h = max(4.0, abs(float(text_line_height_from_percent(base_line * base_sy, line_spacing_pct))))

        def _styled_line_height(style: Dict[str, Any]) -> float:
            try:
                font_st = self._font_for_style(style)
                fm_st = QFontMetrics(font_st)
                raw = float(fm_st.lineSpacing()) * float(self._style_char_height_scale(style))
            except Exception:
                raw = float(base_line) * float(self._style_char_height_scale(style))
            try:
                pct = clamp_text_line_spacing((style or {}).get('line_spacing', line_spacing_pct), line_spacing_pct)
                return max(4.0, abs(float(text_line_height_from_percent(raw, pct))))
            except Exception:
                return max(4.0, raw)

        try:
            letter_spacing = float(getattr(o, 'letter_spacing', data.get('letter_spacing', 0)) or 0)
        except Exception:
            letter_spacing = 0.0
        rect = QRectF(o.boundingRect())
        # During the very first sizing pass QGraphicsItem may still report the
        # placeholder 1x1 bounds.  Do not freeze the edit-text origin from that
        # dummy rect; use the original inline edit scene rect/local bounds as the
        # starting work area so the live editor opens on top of the existing text.
        try:
            if rect.width() <= 2.0 or rect.height() <= 2.0:
                fixed = QRectF(getattr(o, '_inline_fixed_edit_bounds', QRectF()))
                if fixed.width() > 2.0 and fixed.height() > 2.0:
                    rect = QRectF(0, 0, fixed.width(), fixed.height())
                else:
                    scene_rect = QRectF(getattr(o, '_inline_edit_scene_rect', QRectF()))
                    if scene_rect.width() > 2.0 and scene_rect.height() > 2.0:
                        rect = QRectF(0, 0, scene_rect.width(), scene_rect.height())
        except Exception:
            pass
        pad_x = 5.0
        pad_y = 5.0
        lines = str(display_text or '').split('\n')
        if not lines:
            lines = ['']
        starts: List[int] = []
        p = 0
        for i, line in enumerate(lines):
            starts.append(p)
            p += len(line)
            if i < len(lines) - 1:
                p += 1

        line_heights: List[float] = []
        for row, line in enumerate(lines):
            start = int(starts[row]) if row < len(starts) else 0
            row_h = float(line_h)
            for j, _ch in enumerate(str(line or '')):
                try:
                    logical_idx = o._logical_index_for_display_char(start + j, preedit_caret, preedit_len)
                except Exception:
                    logical_idx = start + j
                st = self._style_for_logical_index(logical_idx, runs, base_style)
                row_h = max(row_h, _styled_line_height(st))
            line_heights.append(max(4.0, row_h))
        if not line_heights:
            line_heights = [float(line_h)]
        row_offsets: List[float] = []
        _row_y = 0.0
        for _h in line_heights:
            row_offsets.append(_row_y)
            _row_y += float(_h)
        total_text_h = max(float(line_h), _row_y)

        # Keep the editor workbench frame stable, but do not freeze each line's X
        # coordinate.  The first live-renderer pass used to calculate line origins from
        # the original text and then keep them forever.  That made left editing natural,
        # but center/right aligned text lost its alignment as soon as the line width
        # changed.  Store only the frame and top Y; recompute the line X from the
        # current display-line width on every layout pass.
        align = str(getattr(o, 'align', data.get('align', 'center')) or 'center').lower()
        if align not in ('left', 'center', 'right'):
            align = 'center'
        frame_rect = getattr(o, '_ysb_edit_render_frame_rect', None)
        if not isinstance(frame_rect, QRectF) or frame_rect.width() <= 2.0 or frame_rect.height() <= 2.0:
            frame_rect = QRectF(rect)
            try:
                # When the current boundingRect is still a placeholder, prefer the
                # original inline edit bounds captured from the display item.
                fixed = QRectF(getattr(o, '_inline_fixed_edit_bounds', QRectF()))
                if fixed.width() > 2.0 and fixed.height() > 2.0:
                    frame_rect = QRectF(0.0, 0.0, fixed.width(), fixed.height())
            except Exception:
                pass
            try:
                o._ysb_edit_render_frame_rect = QRectF(frame_rect)
            except Exception:
                pass
        else:
            frame_rect = QRectF(frame_rect)

        total_h = max(float(line_h), float(total_text_h))
        line_y0_signature = tuple(round(float(h), 3) for h in (line_heights or []))
        prev_signature = getattr(o, '_ysb_edit_render_line_height_signature', None)
        line_y0 = getattr(o, '_ysb_edit_render_line_y0', None)
        # Recenter when line-height distribution changes.  The old cache kept the
        # initial top forever, so increasing the font size of a middle line made it
        # grow upward into the previous line while only pushing the next line down.
        recalc_line_y0 = line_y0 is None or prev_signature != line_y0_signature
        if recalc_line_y0:
            line_y0 = pad_y + (max(1.0, float(frame_rect.height()) - pad_y * 2.0) - total_h) / 2.0
            try:
                o._ysb_edit_render_line_y0 = float(line_y0)
                o._ysb_edit_render_line_height_signature = line_y0_signature
                if hasattr(o, '_inline_trace'):
                    o._inline_trace(
                        'INLINE_EDITOR_EDIT_RENDER_FRAME_INIT' if prev_signature is None else 'INLINE_EDITOR_LINE_BAND_RECENTER',
                        x=round(float(frame_rect.x()), 2),
                        y=round(float(frame_rect.y()), 2),
                        w=round(float(frame_rect.width()), 2),
                        h=round(float(frame_rect.height()), 2),
                        line_y0=round(float(line_y0), 2),
                        total_h=round(float(total_h), 2),
                        align=align,
                    )
            except Exception:
                pass
        else:
            line_y0 = float(line_y0)

        available_w = max(1.0, float(frame_rect.width()) - pad_x * 2.0)

        def _display_line_width(line_text: str, display_start: int) -> float:
            cursor = 0.0
            max_right = 0.0
            chars = list(str(line_text or ''))
            for j, ch in enumerate(chars):
                try:
                    logical_idx = o._logical_index_for_display_char(int(display_start) + j, preedit_caret, preedit_len)
                except Exception:
                    logical_idx = int(display_start) + j
                st = self._style_for_logical_index(logical_idx, runs, base_style)
                adv = self._advance_for_char(ch, st)
                max_right = max(max_right, cursor + adv)
                next_ch = chars[j + 1] if j + 1 < len(chars) else ''
                cursor += self._cursor_step_after_char(ch, next_ch, adv, st, letter_spacing)
            return max(0.0, max_right)

        def _aligned_line_x(line_text: str, display_start: int) -> float:
            lw = _display_line_width(line_text, display_start)
            if align == 'right':
                return float(frame_rect.left()) + float(frame_rect.width()) - pad_x - lw
            if align == 'center':
                return float(frame_rect.left()) + pad_x + (available_w - lw) / 2.0
            return float(frame_rect.left()) + pad_x

        origin = QPointF(_aligned_line_x(lines[0] if lines else '', starts[0] if starts else 0), float(line_y0))

        columns = []
        char_rects: List[Tuple[int, str, QRectF]] = []
        char_paths: List[Dict[str, Any]] = []
        caret_map_display: Dict[int, QPointF] = {}
        content_rect = QRectF()
        line_rects: List[QRectF] = []
        max_right = float(origin.x())
        for row, line in enumerate(lines):
            start = int(starts[row]) if row < len(starts) else 0
            row_line_h = float(line_heights[row]) if row < len(line_heights) else float(line_h)
            row_offset = float(row_offsets[row]) if row < len(row_offsets) else float(row) * float(line_h)
            try:
                row_origin = QPointF(_aligned_line_x(line, start), float(line_y0) + row_offset)
            except Exception:
                row_origin = QPointF(origin.x(), float(origin.y()) + row_offset)
            x = float(row_origin.x())
            y = float(row_origin.y())
            caret_map_display[start] = QPointF(x, y + row_line_h / 2.0)
            line_rect = QRectF(x, y, 1.0, row_line_h)
            for j, ch in enumerate(str(line or '')):
                d_index = start + j
                try:
                    logical_idx = o._logical_index_for_display_char(d_index, preedit_caret, preedit_len)
                except Exception:
                    logical_idx = d_index
                st = self._style_for_logical_index(logical_idx, runs, base_style)
                adv = self._advance_for_char(ch, st)
                slot = QRectF(x, y, adv, row_line_h)
                char_rects.append((int(logical_idx), ch, QRectF(slot)))
                # Build the actual visible glyph path once.  Selection/caret can use slots;
                # paint uses this path so fill/stroke/size match the editor's text options.
                glyph_path = QPainterPath()
                try:
                    font = self._font_for_style(st)
                    raw = QPainterPath()
                    raw.addText(QPointF(0.0, 0.0), font, str(ch))
                    br = raw.boundingRect()
                    if not br.isNull() and br.width() > 0 and br.height() > 0 and not str(ch).isspace():
                        # Horizontal editor glyphs must keep their font-native bearing and
                        # baseline position.  The previous live renderer centered every
                        # glyph bounding box inside its advance slot; narrow punctuation
                        # such as '.', quotes, and corner brackets was therefore dragged
                        # into the middle of the slot.  Build the glyph path at the real
                        # pen x/baseline instead, then apply the saved width/height scale.
                        try:
                            fm_ch = QFontMetrics(font)
                            sx_ch = self._style_char_width_scale(st)
                            sy_ch = self._style_char_height_scale(st)
                            metric_h = max(1.0, float(fm_ch.height()) * sy_ch)
                            baseline_y = float(slot.top()) + (float(slot.height()) - metric_h) / 2.0 + float(fm_ch.ascent()) * sy_ch
                        except Exception:
                            sx_ch = 1.0
                            sy_ch = 1.0
                            baseline_y = float(slot.center().y())
                        tr = QTransform()
                        tr.translate(float(slot.left()), float(baseline_y))
                        tr.scale(float(sx_ch), float(sy_ch))
                        glyph_path = tr.map(raw)
                except Exception:
                    glyph_path = QPainterPath()
                if not glyph_path.isEmpty():
                    ink_rect = glyph_path.boundingRect()
                    try:
                        sw = max(0.0, float(st.get('stroke_width', 0) or 0.0)) / 2.0 + 1.0
                        ink_rect = ink_rect.adjusted(-sw, -sw, sw, sw)
                    except Exception:
                        pass
                    line_rect = line_rect.united(ink_rect)
                    content_rect = ink_rect if content_rect.isNull() else content_rect.united(ink_rect)
                else:
                    content_rect = slot if content_rect.isNull() else content_rect.united(slot)
                    line_rect = line_rect.united(slot)
                char_paths.append({'logical_index': int(logical_idx), 'display_index': d_index, 'char': ch, 'slot': QRectF(slot), 'path': glyph_path, 'style': st})
                next_ch = str(line or '')[j + 1] if j + 1 < len(str(line or '')) else ''
                x += self._cursor_step_after_char(ch, next_ch, adv, st, letter_spacing)
                caret_map_display[d_index + 1] = QPointF(x, y + row_line_h / 2.0)
            if not line:
                content_rect = line_rect if content_rect.isNull() else content_rect.united(line_rect)
            line_rects.append(QRectF(line_rect).adjusted(-2, -2, 2, 2))
            columns.append({'line': str(line or ''), 'start': max(0, min(logical_len, o._logical_index_for_display_char(start, preedit_caret, preedit_len) if hasattr(o, '_logical_index_for_display_char') else start)), 'display_start': start, 'length': len(str(line or '')), 'display_length': len(str(line or '')), 'x': float(row_origin.x()), 'y0': y, 'pitch': row_line_h, 'cell_w': max(1.0, base_line), 'line_h': row_line_h, 'col': row})
            max_right = max(max_right, x)
            if row < len(lines) - 1:
                caret_map_display[start + len(line)] = QPointF(x, y + row_line_h / 2.0)
                try:
                    next_x = _aligned_line_x(lines[row + 1] if row + 1 < len(lines) else '', starts[row + 1] if row + 1 < len(starts) else start + len(line) + 1)
                except Exception:
                    next_x = float(origin.x())
                next_h = float(line_heights[row + 1]) if row + 1 < len(line_heights) else float(line_h)
                caret_map_display[start + len(line) + 1] = QPointF(float(next_x), y + row_line_h + next_h / 2.0)

        caret_map: Dict[int, QPointF] = {}
        for logical_pos in range(0, logical_len + 1):
            try:
                if preedit_len and logical_pos == preedit_caret:
                    display_pos = preedit_caret + preedit_len
                else:
                    display_pos = o._display_index_for_logical_caret(logical_pos, preedit_caret, preedit_len)
            except Exception:
                display_pos = logical_pos
            pnt = caret_map_display.get(display_pos)
            if pnt is not None:
                caret_map[logical_pos] = pnt
        caret_map[logical_len] = caret_map.get(logical_len, caret_map_display.get(len(display_text), QPointF(float(origin.x()), float(origin.y()) + (float(line_heights[0]) if line_heights else float(line_h)) / 2.0)))
        if content_rect.isNull() or content_rect.width() <= 0 or content_rect.height() <= 0:
            content_rect = QRectF(float(origin.x()), float(origin.y()), 1.0, (float(line_heights[0]) if line_heights else float(line_h)))
        left_overflow = max(0.0, -float(content_rect.left()) + 8.0)
        desired_w = max(float(rect.width()), float(content_rect.right()) + left_overflow + 8.0, float(frame_rect.width()))
        desired_h = max(float(rect.height()), float(content_rect.bottom()) + 8.0, float(line_y0) + float(total_text_h) + 8.0, float(frame_rect.height()))
        return {
            'font': base_font,
            'fm': QFontMetrics(base_font),
            'columns': columns,
            'caret_map': caret_map,
            'char_rects': char_rects,
            'char_paths': char_paths,
            'content_rect': QRectF(content_rect).adjusted(-2, -2, 2, 2),
            'line_rects': line_rects,
            'base_cell_w': max(1.0, base_line),
            'pitch': (float(line_heights[0]) if line_heights else float(line_h)),
            'horizontal_direct': True,
            'editor_live_renderer': True,
            'desired_size': (max(30.0, desired_w), max(20.0, desired_h)),
        }

    def paint_horizontal(self, painter: QPainter, layout: Dict[str, Any]) -> bool:
        paths = layout.get('char_paths') or []
        if not paths:
            return False
        painter.save()
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        except Exception:
            pass
        def _flush_group(group_entries):
            if not group_entries:
                return
            try:
                group_path = QPainterPath()
                st = dict(group_entries[0].get('style') or {})
                for ge in group_entries:
                    path = ge.get('path')
                    if path is None or path.isEmpty():
                        continue
                    group_path = path if group_path.isEmpty() else group_path.united(path)
                if group_path.isEmpty():
                    return
                # Inline editing should show clean fill-only glyphs.  The final
                # renderer still applies stroke; showing it during editing makes
                # narrow vertical punctuation and caret alignment look misleading.
                sw = 0.0
                fc = QColor(str(st.get('text_color') or '#000000'))
                if not fc.isValid():
                    fc = QColor('#000000')
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(fc))
                painter.drawPath(group_path)
                if bool(st.get('strike', False)):
                    rr = group_path.boundingRect()
                    if rr.width() > 0 and rr.height() > 0:
                        painter.setPen(QPen(fc, max(1.0, float(st.get('font_size', 20) or 20) * 0.075), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                        painter.setBrush(Qt.BrushStyle.NoBrush)
                        painter.drawLine(QPointF(rr.left(), rr.center().y()), QPointF(rr.right(), rr.center().y()))
            except Exception:
                pass

        group = []
        prev_entry = None
        for entry in paths:
            try:
                path = entry.get('path')
                ch = entry.get('char')
                if path is None or path.isEmpty() or str(ch).isspace():
                    continue
                merge = False
                if prev_entry is not None:
                    merge = (
                        _same_mergeable_special_pair(prev_entry.get('char'), entry.get('char'))
                        and _style_run_signature(prev_entry.get('style') or {}) == _style_run_signature(entry.get('style') or {})
                    )
                if merge:
                    group.append(entry)
                else:
                    _flush_group(group)
                    group = [entry]
                prev_entry = entry
            except Exception:
                _flush_group(group)
                group = []
                prev_entry = None
                continue
        _flush_group(group)
        painter.restore()
        return True
