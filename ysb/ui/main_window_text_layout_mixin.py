from ysb.ui.main_window_support import *
from ysb.core import korean_linebreak_rules as ko_linebreak_rules
from ysb.core.text_style_limits import TEXT_FONT_SIZE_MIN, TEXT_FONT_SIZE_MAX, TEXT_LINE_SPACING_MIN, TEXT_LINE_SPACING_MAX, TEXT_LETTER_SPACING_MIN, TEXT_LETTER_SPACING_MAX, TEXT_CHAR_SCALE_MIN, TEXT_CHAR_SCALE_MAX, TEXT_STROKE_WIDTH_MAX, clamp_text_font_size, clamp_text_line_spacing, clamp_text_letter_spacing, clamp_text_char_scale, positive_scale_factor


class MainWindowTextLayoutMixin:

    def strip_object_display_prefix_for_data(self, value):
        """Remove table-only object labels from real OCR/translation text."""
        text = str(value or "")
        prefixes = ("[객체] ", "[객체]", "[Object] ", "[Object]", "[OBJECT] ", "[OBJECT]")
        changed = True
        while changed:
            changed = False
            left = text.lstrip()
            leading = text[:len(text) - len(left)]
            for prefix in prefixes:
                if left.startswith(prefix):
                    left = left[len(prefix):]
                    text = leading + left
                    changed = True
                    break
        return text

    def sanitize_text_data_object_prefixes(self, item):
        if not isinstance(item, dict):
            return False
        changed = False
        for key in ("text", "translated_text", "object_source_text"):
            if key in item:
                clean = self.strip_object_display_prefix_for_data(item.get(key))
                if clean != str(item.get(key, "") or ""):
                    item[key] = clean
                    changed = True
        return changed

    def normalize_writing_direction(self, value=None):
        """Normalize text writing direction without touching OCR/text rectangles."""
        text = str(value or "horizontal").strip().lower()
        if text in ("vertical", "v", "세로", "세로쓰기"):
            return "vertical"
        return "horizontal"

    def writing_direction_label(self, value=None):
        direction = self.normalize_writing_direction(value)
        return self.tr_ui("세로쓰기") if direction == "vertical" else self.tr_ui("가로쓰기")

    def current_default_writing_direction(self):
        return self.normalize_writing_direction(getattr(self, "default_writing_direction", "horizontal"))

    def set_default_writing_direction(self, direction, announce=True):
        direction = self.normalize_writing_direction(direction)
        self.default_writing_direction = direction
        try:
            self.app_options["default_writing_direction"] = direction
            save_app_options(self.app_options)
        except Exception:
            pass
        try:
            if announce:
                self.log(f"↕️ {self.tr_ui('새 텍스트 쓰기 방향')}: {self.writing_direction_label(direction)}")
        except Exception:
            pass
        return direction

    def ensure_text_writing_direction(self, item):
        if isinstance(item, dict):
            item["writing_direction"] = self.normalize_writing_direction(item.get("writing_direction", "horizontal"))
            return item["writing_direction"]
        return "horizontal"

    def text_item_writing_direction(self, item):
        if isinstance(item, dict):
            return self.normalize_writing_direction(item.get("writing_direction", "horizontal"))
        data = getattr(item, "data", None)
        if isinstance(data, dict):
            return self.text_item_writing_direction(data)
        return "horizontal"

    def is_text_writing_direction_change_blocked(self, item):
        data = item if isinstance(item, dict) else getattr(item, "data", None)
        if not isinstance(data, dict):
            return True
        if bool(data.get("rasterized_text")):
            return True
        runtime_keys = ("_transform_mode", "_skew_mode", "_trapezoid_mode", "_arc_mode")
        if any(bool(data.get(k, False)) for k in runtime_keys):
            return True
        numeric_keys = ("rotation", "skew_x", "skew_y", "trap_left", "trap_right", "trap_top", "trap_bottom", "arc_top", "arc_bottom", "arc_left", "arc_right")
        for key in numeric_keys:
            try:
                if abs(float(data.get(key, 0) or 0)) > 1e-6:
                    return True
            except Exception:
                if data.get(key):
                    return True
        handles = data.get("arc_handles")
        if isinstance(handles, list) and handles:
            return True
        return False

    def show_writing_direction_blocked_message(self):
        try:
            QMessageBox.information(self, self.tr_ui("쓰기 방향"), self.tr_ui("텍스트 변형이 적용된 객체는 쓰기 방향을 변경할 수 없습니다."))
        except Exception:
            try:
                self.log("⚠️ " + self.tr_ui("텍스트 변형이 적용된 객체는 쓰기 방향을 변경할 수 없습니다."))
            except Exception:
                pass

    def set_text_items_writing_direction(self, data_items, direction, *, reason="쓰기 방향 변경", announce=True):
        direction = self.normalize_writing_direction(direction)
        items = [d for d in list(data_items or []) if isinstance(d, dict) and not d.get("rasterized_text")]
        if not items:
            return False
        blocked = [d for d in items if self.is_text_writing_direction_change_blocked(d)]
        editable = [d for d in items if d not in blocked]
        if blocked and not editable:
            self.show_writing_direction_blocked_message()
            return False
        if not editable:
            return False
        changed = [d for d in editable if self.text_item_writing_direction(d) != direction]
        if not changed:
            return False
        try:
            self.undo_text_checkpoint(reason)
        except Exception:
            pass
        ids = []
        for d in changed:
            d["writing_direction"] = direction
            if d.get("id") is not None:
                ids.append(d.get("id"))
        try:
            self.finalize_text_change(ids=ids, fields=["writing_direction"], reason=reason, delay_ms=900)
        except Exception:
            try:
                self.mark_active_page_dirty("text")
                self.schedule_deferred_auto_save_project(900)
            except Exception:
                pass
        if ids:
            try:
                self.reselect_text_items(ids)
            except Exception:
                pass
        if blocked:
            self.show_writing_direction_blocked_message()
        try:
            if announce:
                self.log(f"↕️ {self.tr_ui('쓰기 방향 변경')}: {self.writing_direction_label(direction)} ({len(changed)}개)")
        except Exception:
            pass
        return True

    def add_writing_direction_submenu(self, menu, *, current_direction="horizontal", enabled=True, on_horizontal=None, on_vertical=None):
        sub = menu.addMenu(self.tr_ui("쓰기 방향"))
        act_h = sub.addAction(self.tr_ui("가로쓰기"))
        act_v = sub.addAction(self.tr_ui("세로쓰기"))
        for act in (act_h, act_v):
            act.setCheckable(True)
            act.setEnabled(bool(enabled))
        current_direction = self.normalize_writing_direction(current_direction)
        act_h.setChecked(current_direction == "horizontal")
        act_v.setChecked(current_direction == "vertical")
        if not enabled:
            try:
                sub.setToolTipsVisible(True)
                tip = self.tr_ui("텍스트 변형이 적용된 객체는 쓰기 방향을 변경할 수 없습니다.")
                act_h.setToolTip(tip)
                act_v.setToolTip(tip)
            except Exception:
                pass
        if callable(on_horizontal):
            act_h.triggered.connect(lambda checked=False: on_horizontal())
        if callable(on_vertical):
            act_v.triggered.connect(lambda checked=False: on_vertical())
        return sub, act_h, act_v

    def show_final_text_tool_context_menu(self, global_pos):
        menu = QMenu(self)
        _sub, act_h, act_v = self.add_writing_direction_submenu(
            menu,
            current_direction=self.current_default_writing_direction(),
            enabled=True,
        )
        chosen = menu.exec(global_pos)
        if chosen == act_h:
            self.set_default_writing_direction('horizontal')
            self.activate_final_text_tool_after_direction_menu()
        elif chosen == act_v:
            self.set_default_writing_direction('vertical')
            self.activate_final_text_tool_after_direction_menu()

    def activate_final_text_tool_after_direction_menu(self):
        """좌측 텍스트 도구 우클릭에서 방향을 골랐으면 곧바로 텍스트 도구를 사용할 의도다.

        방향만 바꾸고 이전 도구가 그대로 남으면 사용자가 다시 T 도구를 눌러야 하므로,
        새 텍스트 생성 기본값을 바꾸는 동시에 최종 텍스트 도구도 활성화한다.
        """
        try:
            if hasattr(self, 'set_tool'):
                self.set_tool('final_text')
                return True
        except Exception:
            pass
        try:
            if hasattr(self, 'set_final_text_tool_active'):
                if self.set_final_text_tool_active(True):
                    return True
        except Exception:
            pass
        try:
            if hasattr(self, 'select_final_text_tool'):
                self.select_final_text_tool()
                return True
        except Exception:
            pass
        try:
            if hasattr(self, 'set_current_tool'):
                self.set_current_tool('final_text')
                return True
        except Exception:
            pass
        try:
            if hasattr(self, 'current_tool'):
                self.current_tool = 'final_text'
                return True
        except Exception:
            pass
        return False


    def text_preset_dir(self):
        path = get_cache_dir() / "text_preset"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def text_preset_path(self, name):
        safe = str(name or "preset").strip().replace("/", "_").replace("\\", "_")
        return self.text_preset_dir() / f"{safe}.json"

    def last_text_preset_path(self):
        return self.text_preset_dir() / "_last_preset.json"

    def text_preset_state_path(self):
        return self.text_preset_dir() / "_preset_state.json"

    def item_text_preset_dir(self):
        path = get_cache_dir() / "item_text_preset"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def item_text_preset_path(self, name):
        safe = self.safe_preset_name(name)
        return self.item_text_preset_dir() / f"{safe}.json"

    def item_text_preset_state_path(self):
        return self.item_text_preset_dir() / "_item_preset_state.json"

    def load_item_text_preset_state(self):
        try:
            with open(self.item_text_preset_state_path(), "r", encoding="utf-8") as f:
                state = json.load(f)
            if not isinstance(state, dict):
                state = {}
        except Exception:
            state = {}
        state.setdefault("style", self.current_style_snapshot() if hasattr(self, "cb_font") else {})
        state.setdefault("include", {**{k: True for k, _ in self.style_field_specs()}, "advanced_text_options": bool(self.style_has_advanced_text_options(state.get("style") or {}))})
        return state

    def save_item_text_preset_state(self, style=None, include=None, selected=None):
        _style = self.normalize_style_dict(style or self.current_style_snapshot())
        _include_raw = include or {}
        _include = {k: bool(_include_raw.get(k, False)) for k, _ in self.style_field_specs()}
        _include["advanced_text_options"] = bool(_include_raw.get("advanced_text_options", bool(self.style_has_advanced_text_options(_style))))
        state = {
            "style": _style,
            "include": _include,
            "selected": selected or None,
        }
        self.item_text_preset_dir().mkdir(parents=True, exist_ok=True)
        with open(self.item_text_preset_state_path(), "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def safe_preset_name(self, name):
        safe = str(name or "preset").strip().replace("/", "_").replace("\\", "_")
        return safe or "preset"

    def style_field_specs(self):
        return [
            ("font_family", "폰트"),
            ("font_size", "크기"),
            ("text_color", "문자색"),
            ("stroke_width", "획"),
            ("stroke_color", "획색"),
            ("align", "정렬"),
            ("writing_direction", "쓰기 방향"),
            ("line_spacing", "행간"),
            ("letter_spacing", "자간"),
            ("char_width", "너비"),
            ("char_height", "높이"),
            ("bold", "굵게"),
            ("italic", "기울임"),
            ("strike", "취소선"),
        ]

    def advanced_text_effect_fields(self):
        return [
            "text_gradient_enabled", "text_gradient_color1", "text_gradient_color2", "text_gradient_angle", "text_gradient_ratio",
            "stroke_gradient_enabled", "stroke_gradient_color1", "stroke_gradient_color2", "stroke_gradient_angle", "stroke_gradient_ratio",
            "double_stroke_enabled", "double_stroke_color", "double_stroke_width",
            "text_shadow_enabled", "text_shadow_color", "text_shadow_opacity", "text_shadow_offset_x", "text_shadow_offset_y", "text_shadow_blur",
            "text_glow_enabled", "text_glow_color", "text_glow_opacity", "text_glow_offset_x", "text_glow_offset_y", "text_glow_size", "text_glow_blur",
        ]

    def default_advanced_text_options(self):
        return {
            "text_gradient_enabled": False,
            "text_gradient_color1": "#000000",
            "text_gradient_color2": "#FFFFFF",
            "text_gradient_angle": 0,
            "text_gradient_ratio": 50,
            "stroke_gradient_enabled": False,
            "stroke_gradient_color1": "#FFFFFF",
            "stroke_gradient_color2": "#000000",
            "stroke_gradient_angle": 0,
            "stroke_gradient_ratio": 50,
            "double_stroke_enabled": False,
            "double_stroke_color": "#000000",
            "double_stroke_width": 0,
            "text_shadow_enabled": False,
            "text_shadow_color": "#000000",
            "text_shadow_opacity": 45,
            "text_shadow_offset_x": 3,
            "text_shadow_offset_y": 3,
            "text_shadow_blur": 4,
            "text_glow_enabled": False,
            "text_glow_color": "#FFFFFF",
            "text_glow_opacity": 35,
            "text_glow_offset_x": 0,
            "text_glow_offset_y": 0,
            "text_glow_size": 3,
            "text_glow_blur": 8,
        }

    def normalize_advanced_text_options(self, values=None):
        raw = dict(values or {})
        nested = raw.get("advanced_text_options")
        if isinstance(nested, dict):
            raw.update(nested)
        out = self.default_advanced_text_options()

        def _bool(key):
            return bool(raw.get(key, out.get(key, False)))

        def _int(key, default, lo=None, hi=None):
            try:
                value = int(raw.get(key, default))
            except Exception:
                value = int(default)
            if lo is not None:
                value = max(lo, value)
            if hi is not None:
                value = min(hi, value)
            return value

        def _color(key, default):
            text = str(raw.get(key, default) or default)
            try:
                c = QColor(text)
                if c.isValid():
                    return c.name(QColor.NameFormat.HexRgb).upper()
            except Exception:
                pass
            return str(default).upper()

        for key in ("text_gradient_enabled", "stroke_gradient_enabled", "double_stroke_enabled", "text_shadow_enabled", "text_glow_enabled"):
            out[key] = _bool(key)
        for key, default in (
            ("text_gradient_color1", "#000000"), ("text_gradient_color2", "#FFFFFF"),
            ("stroke_gradient_color1", "#FFFFFF"), ("stroke_gradient_color2", "#000000"),
            ("double_stroke_color", "#000000"), ("text_shadow_color", "#000000"), ("text_glow_color", "#FFFFFF"),
        ):
            out[key] = _color(key, default)
        out["text_gradient_angle"] = _int("text_gradient_angle", 0, -360, 360)
        out["text_gradient_ratio"] = _int("text_gradient_ratio", 50, 1, 99)
        out["stroke_gradient_angle"] = _int("stroke_gradient_angle", 0, -360, 360)
        out["stroke_gradient_ratio"] = _int("stroke_gradient_ratio", 50, 1, 99)
        out["double_stroke_width"] = _int("double_stroke_width", 0, 0, 80)
        out["text_shadow_opacity"] = _int("text_shadow_opacity", 45, 0, 100)
        out["text_shadow_offset_x"] = _int("text_shadow_offset_x", 3, -300, 300)
        out["text_shadow_offset_y"] = _int("text_shadow_offset_y", 3, -300, 300)
        out["text_shadow_blur"] = _int("text_shadow_blur", 4, 0, 200)
        out["text_glow_opacity"] = _int("text_glow_opacity", 35, 0, 100)
        out["text_glow_offset_x"] = _int("text_glow_offset_x", 0, -300, 300)
        out["text_glow_offset_y"] = _int("text_glow_offset_y", 0, -300, 300)
        out["text_glow_size"] = _int("text_glow_size", 3, 0, 200)
        out["text_glow_blur"] = _int("text_glow_blur", 8, 0, 200)
        return out

    def style_has_advanced_text_options(self, style):
        adv = self.normalize_advanced_text_options(style or {})
        return any(bool(adv.get(k)) for k in (
            "text_gradient_enabled", "stroke_gradient_enabled", "double_stroke_enabled", "text_shadow_enabled", "text_glow_enabled"
        ))

    def flatten_style_with_advanced_options(self, style):
        style = dict(style or {})
        adv = self.normalize_advanced_text_options(style)
        out = dict(style)
        out["advanced_text_options"] = adv
        for key in self.advanced_text_effect_fields():
            out[key] = adv.get(key)
        return out

    def style_with_advanced_options(self, style, advanced_options=None):
        out = self.normalize_style_dict(style)
        adv_source = advanced_options if advanced_options is not None else (style or {})
        out["advanced_text_options"] = self.normalize_advanced_text_options(adv_source)
        return out

    def open_preset_advanced_text_options_dialog(self, style, parent_dialog=None, preview_callback=None):
        base = self.flatten_style_with_advanced_options(style or {})
        dlg = TextAdvancedEffectDialog(base, parent_dialog or self)
        try:
            dlg.setWindowTitle(self.tr_ui("고급 텍스트/획 옵션"))
        except Exception:
            pass
        if callable(preview_callback):
            try:
                dlg.previewChanged.connect(lambda values: preview_callback(self.style_with_advanced_options(style or {}, values)))
            except Exception:
                pass
        result = dlg.exec()
        if result != QDialog.DialogCode.Accepted:
            return None
        return self.normalize_advanced_text_options(dlg.values())

    def style_summary_text(self, style, include=None):
        style = self.style_with_advanced_options(style or {})
        include = include or {k: True for k, _ in self.style_field_specs()}
        parts = []
        def yes(v): return "ON" if v else "OFF"
        for key, label in self.style_field_specs():
            if not include.get(key, False):
                continue
            value = style.get(key)
            if key == "font_family":
                value = str(value)
            elif key == "font_size":
                value = f"{value}px"
            elif key == "stroke_width":
                value = f"{value}px"
            elif key == "writing_direction":
                value = self.writing_direction_label(value)
            elif key in ("line_spacing",):
                value = f"{value}%"
            elif key in ("letter_spacing",):
                value = "자동" if int(value or 0) == 0 else f"{value}px"
            elif key in ("char_width", "char_height"):
                value = f"{value}%"
            elif key in ("bold", "italic", "strike"):
                value = yes(bool(value))
            parts.append(f"{label}:{value}")
        if include.get("advanced_text_options", True) and self.style_has_advanced_text_options(style):
            parts.append("고급:ON")
        return " / ".join(parts) if parts else "포함 옵션 없음"

    def page_preset_state(self):
        try:
            with open(self.text_preset_state_path(), "r", encoding="utf-8") as f:
                state = json.load(f)
            if not isinstance(state, dict):
                state = {}
        except Exception:
            state = {}
        state.setdefault("active", "__last__")
        state.setdefault("enabled", {})
        return state

    def save_page_preset_state(self, state):
        state = dict(state or {})
        state.setdefault("active", "__last__")
        state.setdefault("enabled", {})
        self.text_preset_dir().mkdir(parents=True, exist_ok=True)
        with open(self.text_preset_state_path(), "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def current_style_snapshot(self):
        style = {
            "font_family": self.cb_font.currentFont().family(),
            "font_size": int(self.sb_font_size.value()),
            "stroke_width": int(self.sb_strk.value()),
            "text_color": self.default_text_color,
            "stroke_color": self.default_stroke_color,
            "align": self.default_align,
            "writing_direction": self.current_default_writing_direction(),
            "line_spacing": int(self.sb_line_spacing.value()) if hasattr(self, "sb_line_spacing") else self.default_line_spacing,
            "letter_spacing": int(self.sb_letter_spacing.value()) if hasattr(self, "sb_letter_spacing") else self.default_letter_spacing,
            "char_width": int(self.sb_char_width.value()) if hasattr(self, "sb_char_width") else self.default_char_width,
            "char_height": int(self.sb_char_height.value()) if hasattr(self, "sb_char_height") else self.default_char_height,
            "bold": bool(self.btn_bold.isChecked()) if hasattr(self, "btn_bold") else self.default_bold,
            "italic": bool(self.btn_italic.isChecked()) if hasattr(self, "btn_italic") else self.default_italic,
            "strike": bool(self.btn_strike.isChecked()) if hasattr(self, "btn_strike") else self.default_strike,
        }
        adv = getattr(self, "_current_text_preset_advanced_options", None)
        if isinstance(adv, dict) and self.style_has_advanced_text_options({"advanced_text_options": adv}):
            style["advanced_text_options"] = self.normalize_advanced_text_options(adv)
        return self.normalize_style_dict(style)

    def normalize_style_dict(self, style):
        style = dict(style or {})
        align = str(style.get("align") or "center").lower()
        if align not in ("left", "center", "right"):
            align = "center"
        writing_direction = self.normalize_writing_direction(style.get("writing_direction", getattr(self, "default_writing_direction", "horizontal")))

        def _int(key, default, lo=None, hi=None):
            try:
                value = int(style.get(key, default))
            except Exception:
                value = default
            if lo is not None:
                value = max(lo, value)
            if hi is not None:
                value = min(hi, value)
            return value

        out = {
            "font_family": str(style.get("font_family") or self.cb_font.currentFont().family()),
            "font_size": clamp_text_font_size(style.get("font_size", self.sb_font_size.value()), self.sb_font_size.value()),
            "stroke_width": _int("stroke_width", self.sb_strk.value(), 0, 300),
            "text_color": str(style.get("text_color") or "#000000"),
            "stroke_color": str(style.get("stroke_color") or "#FFFFFF"),
            "align": align,
            "writing_direction": writing_direction,
            "line_spacing": clamp_text_line_spacing(style.get("line_spacing", 100), 100),
            "letter_spacing": clamp_text_letter_spacing(style.get("letter_spacing", 0), 0),
            "char_width": clamp_text_char_scale(style.get("char_width", 100), 100),
            "char_height": clamp_text_char_scale(style.get("char_height", 100), 100),
            "bold": bool(style.get("bold", False)),
            "italic": bool(style.get("italic", False)),
            "strike": bool(style.get("strike", False)),
        }
        if isinstance(style.get("advanced_text_options"), dict) or any(k in style for k in self.advanced_text_effect_fields()):
            out["advanced_text_options"] = self.normalize_advanced_text_options(style)
        return out

    def apply_style_to_controls(self, style):
        style = self.normalize_style_dict(style)
        self._style_signal_lock = True
        try:
            self.cb_font.setCurrentFont(QFont(style["font_family"]))
            self._set_widget_value_blocked(self.sb_font_size, int(style["font_size"]))
            self._set_widget_value_blocked(self.sb_strk, int(style["stroke_width"]))
            self.default_text_color = style["text_color"]
            self.default_stroke_color = style["stroke_color"]
            self.default_align = style["align"]
            self.default_writing_direction = self.normalize_writing_direction(style.get("writing_direction", "horizontal"))
            if hasattr(self, "sb_line_spacing"):
                self._set_widget_value_blocked(self.sb_line_spacing, int(style["line_spacing"]))
            if hasattr(self, "sb_letter_spacing"):
                self._set_widget_value_blocked(self.sb_letter_spacing, int(style["letter_spacing"]))
            if hasattr(self, "sb_char_width"):
                self._set_widget_value_blocked(self.sb_char_width, int(style["char_width"]))
            if hasattr(self, "sb_char_height"):
                self._set_widget_value_blocked(self.sb_char_height, int(style["char_height"]))
            if hasattr(self, "btn_bold"):
                self._set_widget_checked_blocked(self.btn_bold, bool(style["bold"]))
            if hasattr(self, "btn_italic"):
                self._set_widget_checked_blocked(self.btn_italic, bool(style["italic"]))
            if hasattr(self, "btn_strike"):
                self._set_widget_checked_blocked(self.btn_strike, bool(style["strike"]))
            if isinstance(style.get("advanced_text_options"), dict) or any(k in style for k in self.advanced_text_effect_fields()):
                self._current_text_preset_advanced_options = self.normalize_advanced_text_options(style)
            else:
                self._current_text_preset_advanced_options = self.default_advanced_text_options()
            self.update_color_button_styles()
        finally:
            self._style_signal_lock = False

    def save_last_text_preset(self, active="__last__"):
        if not hasattr(self, "cb_font"):
            return
        try:
            self.text_preset_dir().mkdir(parents=True, exist_ok=True)
            with open(self.last_text_preset_path(), "w", encoding="utf-8") as f:
                json.dump(self.current_style_snapshot(), f, ensure_ascii=False, indent=2)
            state = self.page_preset_state()
            state["active"] = active
            self.save_page_preset_state(state)
        except Exception as e:
            self.log(f"⚠️ 프리셋 자동저장 실패: {e}")

    def schedule_last_text_preset_save(self, active="__last__", delay_ms=800):
        """글꼴/크기/행간 스핀박스 조작 중 프리셋 JSON을 매 틱마다 쓰지 않고 한 번으로 묶는다."""
        try:
            self._pending_last_text_preset_active = active
            timer = getattr(self, "_last_text_preset_save_timer", None)
            if timer is None:
                timer = QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(lambda: self.save_last_text_preset(getattr(self, "_pending_last_text_preset_active", "__last__")))
                self._last_text_preset_save_timer = timer
            timer.stop()
            timer.start(max(100, int(delay_ms or 800)))
        except Exception:
            self.save_last_text_preset(active)

    def load_text_preset_cache(self):
        if not hasattr(self, "cb_text_preset"):
            return
        self._preset_loading = True
        self.text_presets = {}
        self.cb_text_preset.blockSignals(True)
        try:
            self.cb_text_preset.clear()
            self.cb_text_preset.addItem("마지막 설정", "__last__")
            preset_dir = self.text_preset_dir()
            for path in sorted(preset_dir.glob("*.json")):
                if path.name.startswith("_"):
                    continue
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        style = self.normalize_style_dict(json.load(f))
                    name = path.stem
                    self.text_presets[name] = style
                    self.cb_text_preset.addItem(name, name)
                except Exception:
                    continue

            state = self.page_preset_state()
            active = str(state.get("active") or "__last__")

            style = None
            if active != "__last__" and active in self.text_presets:
                style = self.text_presets[active]
                idx = self.cb_text_preset.findData(active)
                if idx >= 0:
                    self.cb_text_preset.setCurrentIndex(idx)
            else:
                try:
                    with open(self.last_text_preset_path(), "r", encoding="utf-8") as f:
                        style = self.normalize_style_dict(json.load(f))
                except Exception:
                    style = self.current_style_snapshot()
                self.cb_text_preset.setCurrentIndex(0)

            if style:
                self.apply_style_to_controls(style)
        finally:
            self.cb_text_preset.blockSignals(False)
            self._preset_loading = False
        self.save_last_text_preset(self.cb_text_preset.currentData() or "__last__")

    def on_text_preset_selected(self, *args):
        if self._preset_loading:
            return
        key = self.cb_text_preset.currentData() or "__last__"
        if key == "__last__":
            try:
                with open(self.last_text_preset_path(), "r", encoding="utf-8") as f:
                    style = self.normalize_style_dict(json.load(f))
            except Exception:
                style = self.current_style_snapshot()
        else:
            style = self.text_presets.get(str(key))
            if not style:
                return
        self.apply_style_to_controls(style)
        applied_to_selection = False
        if self.cb_mode.currentIndex() == 4 and self.selected_text_items():
            self.apply_style_to_selected(**style)
            applied_to_selection = True
        self.save_last_text_preset(str(key))
        preset_label = self.cb_text_preset.currentText()
        self.log(f"🎛️ 글꼴 프리셋 로딩: {preset_label}")

    def save_text_preset_named(self):
        name, ok = QInputDialog.getText(self, "프리셋 저장", "저장할 프리셋 이름:")
        if not ok or not name.strip():
            return
        safe = name.strip().replace("/", "_").replace("\\", "_")
        path = self.text_preset_path(safe)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.current_style_snapshot(), f, ensure_ascii=False, indent=2)
        self.load_text_preset_cache()
        idx = self.cb_text_preset.findData(safe)
        if idx >= 0:
            self.cb_text_preset.setCurrentIndex(idx)
        self.save_last_text_preset(safe)
        self.log(f"💾 글꼴 프리셋 저장: {safe}")

    def import_text_preset_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "글꼴 프리셋 JSON 가져오기", str(self.text_preset_dir()), "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                style = self.normalize_style_dict(json.load(f))
        except Exception as e:
            QMessageBox.warning(self, "가져오기 실패", f"프리셋 JSON을 읽지 못했습니다.\n{e}")
            return
        default_name = Path(path).stem
        name, ok = QInputDialog.getText(self, "프리셋 이름", "저장할 프리셋 이름:", text=default_name)
        if not ok or not name.strip():
            return
        safe = name.strip().replace("/", "_").replace("\\", "_")
        with open(self.text_preset_path(safe), "w", encoding="utf-8") as f:
            json.dump(style, f, ensure_ascii=False, indent=2)
        self.load_text_preset_cache()
        idx = self.cb_text_preset.findData(safe)
        if idx >= 0:
            self.cb_text_preset.setCurrentIndex(idx)
        self.log(f"📥 글꼴 프리셋 가져오기 완료: {safe}")

    def normalize_shortcut_text(self, shortcut):
        """단축키 비교용 PortableText 정규화."""
        try:
            if isinstance(shortcut, QKeySequence):
                seq = shortcut
            else:
                seq = key_sequence_from_text(str(shortcut or ""))
            return seq.toString(QKeySequence.SequenceFormat.PortableText)
        except Exception:
            return str(shortcut or "").strip()

    def standard_shortcut_label(self, key):
        if hasattr(self, "shortcut_label_map") and key in self.shortcut_label_map:
            return self.shortcut_label_map.get(key, key)
        if hasattr(self, "actions") and key in self.actions:
            return self.actions[key].text()
        return str(key)

    def ask_disable_conflict(self, parent, title, message):
        return QMessageBox.question(
            parent or self,
            title,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

    def resolve_conflicts_for_item_preset_shortcut(self, owner_name, seq_text, parent=None):
        """개별 글꼴 프리셋 단축키 지정 시 일반 단축키/매크로/다른 개별 프리셋과 충돌 검사.
        후입 우선: 사용자가 허용하면 기존 상대방을 비활성화한다.
        """
        seq_text = self.normalize_shortcut_text(seq_text)
        if not seq_text:
            return True

        # 1) 일반 단축키와 충돌하면 일반 단축키 OFF
        for key, shortcut in list(self.shortcut_settings.shortcuts.items()):
            if not self.shortcut_settings.enabled.get(key, True):
                continue
            if shortcut and self.normalize_shortcut_text(shortcut) == seq_text:
                label = self.standard_shortcut_label(key)
                ok = self.ask_disable_conflict(
                    parent,
                    "기존 단축키 비활성화 확인",
                    f"'{label}' 기능이 같은 단축키를 사용 중입니다.\n\n"
                    f"기존 단축키를 비활성화하고 '{owner_name}' 개별 글꼴 프리셋에 지정할까요?",
                )
                if not ok:
                    return False
                self.shortcut_settings.enabled[key] = False
                self.shortcut_settings.shortcuts[key] = ""

        # 2) 매크로와 충돌하면 매크로 OFF
        for macro in getattr(self.shortcut_settings, "macros", []) or []:
            if not macro.get("enabled", True):
                continue
            macro_seq = str(macro.get("shortcut", "") or "")
            if macro_seq and self.normalize_shortcut_text(macro_seq) == seq_text:
                macro_name = str(macro.get("name", "매크로"))
                ok = self.ask_disable_conflict(
                    parent,
                    "매크로 단축키 비활성화 확인",
                    f"'{macro_name}' 매크로가 같은 단축키를 사용 중입니다.\n\n"
                    f"매크로를 비활성화하고 '{owner_name}' 개별 글꼴 프리셋에 지정할까요?",
                )
                if not ok:
                    return False
                macro["enabled"] = False
                macro["shortcut"] = ""

        # 3) 다른 개별 글꼴 프리셋과 충돌하면 기존 개별 프리셋 OFF
        for name, preset in list(getattr(self, "item_text_presets", {}).items()):
            if str(name) == str(owner_name):
                continue
            if not preset.get("enabled", True):
                continue
            other_seq = str(preset.get("shortcut", "") or "")
            if other_seq and self.normalize_shortcut_text(other_seq) == seq_text:
                ok = self.ask_disable_conflict(
                    parent,
                    "개별 프리셋 단축키 비활성화 확인",
                    f"'{name}' 개별 글꼴 프리셋이 같은 단축키를 사용 중입니다.\n\n"
                    f"기존 개별 프리셋을 비활성화하고 '{owner_name}'에 지정할까요?",
                )
                if not ok:
                    return False
                preset["enabled"] = False
                self.save_item_text_preset_named(name, preset)

        ShortcutSettingsStore.save(self.shortcut_settings)
        return True

    def set_item_text_preset_shortcut_checked(self, name, seq_text, parent=None):
        preset = self.item_text_presets.get(name)
        if not preset:
            return False
        new_text = self.normalize_shortcut_text(seq_text)
        old_text = self.normalize_shortcut_text(preset.get("shortcut", "") or "")
        if new_text == old_text:
            return True
        if new_text and not self.resolve_conflicts_for_item_preset_shortcut(name, new_text, parent=parent):
            return False
        preset["shortcut"] = new_text
        self.save_item_text_preset_named(name, preset)
        self.refresh_item_text_preset_combo()
        self.apply_shortcuts()
        return True

    def set_item_text_preset_enabled_checked(self, name, enabled, parent=None):
        preset = self.item_text_presets.get(name)
        if not preset:
            return False
        if enabled:
            seq_text = self.normalize_shortcut_text(preset.get("shortcut", "") or "")
            if seq_text and not self.resolve_conflicts_for_item_preset_shortcut(name, seq_text, parent=parent):
                return False
        preset["enabled"] = bool(enabled)
        self.save_item_text_preset_named(name, preset)
        self.refresh_item_text_preset_combo()
        self.apply_shortcuts()
        return True

    def resolve_item_preset_conflicts_for_new_shortcut_settings(self, new_settings, parent=None, source_label="단축키"):
        """일반 단축키/매크로 설정 저장 시, 개별 프리셋과 겹치면 개별 프리셋을 비활성화한다."""
        changed = False
        for name, preset in list(getattr(self, "item_text_presets", {}).items()):
            if not preset.get("enabled", True):
                continue
            item_seq = self.normalize_shortcut_text(preset.get("shortcut", "") or "")
            if not item_seq:
                continue

            # 일반 단축키 충돌
            for key, shortcut in list(new_settings.shortcuts.items()):
                if not new_settings.enabled.get(key, True):
                    continue
                if shortcut and self.normalize_shortcut_text(shortcut) == item_seq:
                    label = self.standard_shortcut_label(key)
                    ok = self.ask_disable_conflict(
                        parent,
                        "개별 프리셋 단축키 비활성화 확인",
                        f"'{name}' 개별 글꼴 프리셋이 '{label}' 기능과 같은 단축키를 사용 중입니다.\n\n"
                        f"개별 글꼴 프리셋을 비활성화하고 {source_label} 설정을 저장할까요?",
                    )
                    if not ok:
                        return False
                    preset["enabled"] = False
                    self.save_item_text_preset_named(name, preset)
                    changed = True
                    break

            if not preset.get("enabled", True):
                continue

            # 매크로 충돌
            for macro in getattr(new_settings, "macros", []) or []:
                if not macro.get("enabled", True):
                    continue
                macro_seq = str(macro.get("shortcut", "") or "")
                if macro_seq and self.normalize_shortcut_text(macro_seq) == item_seq:
                    macro_name = str(macro.get("name", "매크로"))
                    ok = self.ask_disable_conflict(
                        parent,
                        "개별 프리셋 단축키 비활성화 확인",
                        f"'{name}' 개별 글꼴 프리셋이 '{macro_name}' 매크로와 같은 단축키를 사용 중입니다.\n\n"
                        f"개별 글꼴 프리셋을 비활성화하고 {source_label} 설정을 저장할까요?",
                    )
                    if not ok:
                        return False
                    preset["enabled"] = False
                    self.save_item_text_preset_named(name, preset)
                    changed = True
                    break

        if changed:
            self.refresh_item_text_preset_combo()
        return True

    def apply_pending_item_preset_disables_for_shortcut_settings(self, pending_names, new_settings):
        """단축키/매크로 설정창에서 입력 중 허용한 개별 프리셋 충돌을 OK 저장 시점에 적용한다.

        사용자가 중간에 단축키를 다시 바꿨을 수 있으므로, 최종 new_settings와 실제로
        아직 충돌하는 경우에만 해당 개별 프리셋을 비활성화한다.
        """
        changed = False
        for name in sorted({str(x) for x in (pending_names or []) if str(x)}):
            preset = self.item_text_presets.get(name)
            if not preset or not preset.get("enabled", True):
                continue
            item_seq = self.normalize_shortcut_text(preset.get("shortcut", "") or "")
            if not item_seq:
                continue

            conflict = False
            for key, shortcut in list(getattr(new_settings, "shortcuts", {}) .items()):
                if not getattr(new_settings, "enabled", {}).get(key, True):
                    continue
                if shortcut and self.normalize_shortcut_text(shortcut) == item_seq:
                    conflict = True
                    break
            if not conflict:
                for macro in getattr(new_settings, "macros", []) or []:
                    if not macro.get("enabled", True):
                        continue
                    macro_seq = self.normalize_shortcut_text(macro.get("shortcut", "") or "")
                    if macro_seq and macro_seq == item_seq:
                        conflict = True
                        break

            if conflict:
                preset["enabled"] = False
                self.save_item_text_preset_named(name, preset)
                changed = True
                self.log(f"🔕 개별 글꼴 프리셋 단축키 비활성화: {name}")

        if changed:
            self.refresh_item_text_preset_combo()
            self.apply_shortcuts()
        return changed

    def load_item_text_preset_cache(self):
        self.item_text_presets = {}
        preset_dir = self.item_text_preset_dir()
        for path in sorted(preset_dir.glob("*.json")):
            if path.name.startswith("_"):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict) and "style" in raw:
                    style = self.normalize_style_dict(raw.get("style"))
                    include = raw.get("include") or {}
                    include = {k: bool(include.get(k, False)) for k, _ in self.style_field_specs()}
                    include["advanced_text_options"] = bool((raw.get("include") or {}).get("advanced_text_options", bool(self.style_has_advanced_text_options(style))))
                    # 예전 파일/비어있는 파일은 전부 포함으로 보정
                    if not any(include.values()):
                        include = {k: True for k, _ in self.style_field_specs()}
                        include["advanced_text_options"] = bool(self.style_has_advanced_text_options(style))
                    preset = {
                        "style": style,
                        "include": include,
                        "enabled": bool(raw.get("enabled", True)),
                        "shortcut": str(raw.get("shortcut", "") or ""),
                    }
                else:
                    preset = {
                        "style": self.normalize_style_dict(raw),
                        "include": {**{k: True for k, _ in self.style_field_specs()}, "advanced_text_options": bool(self.style_has_advanced_text_options(self.normalize_style_dict(raw)))},
                        "enabled": True,
                        "shortcut": "",
                    }
                self.item_text_presets[path.stem] = preset
            except Exception:
                continue

        self.refresh_item_text_preset_combo()
        # 단축키 액션 갱신
        if hasattr(self, "actions"):
            self.apply_shortcuts()

    def save_item_text_preset_named(self, name, preset):
        safe = self.safe_preset_name(name)
        path = self.item_text_preset_path(safe)
        style = self.normalize_style_dict(preset.get("style"))
        include_raw = preset.get("include") or {}
        include = {k: bool(include_raw.get(k, False)) for k, _ in self.style_field_specs()}
        include["advanced_text_options"] = bool(include_raw.get("advanced_text_options", bool(self.style_has_advanced_text_options(style))))
        payload = {
            "style": style,
            "include": include,
            "enabled": bool(preset.get("enabled", True)),
            "shortcut": str(preset.get("shortcut", "") or ""),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        self.item_text_presets[safe] = payload
        return safe

    def refresh_item_text_preset_combo(self, select_key="__custom__"):
        if not hasattr(self, "cb_item_text_preset"):
            return
        self._item_preset_loading = True
        self.cb_item_text_preset.blockSignals(True)
        try:
            self.cb_item_text_preset.clear()
            self.cb_item_text_preset.addItem("사용자지정", "__custom__")
            for name, preset in sorted(self.item_text_presets.items()):
                if preset.get("enabled", True):
                    self.cb_item_text_preset.addItem(name, name)
            idx = self.cb_item_text_preset.findData(select_key)
            self.cb_item_text_preset.setCurrentIndex(idx if idx >= 0 else 0)
        finally:
            self.cb_item_text_preset.blockSignals(False)
            self._item_preset_loading = False

    def set_item_preset_combo_custom(self):
        if not hasattr(self, "cb_item_text_preset") or self._item_preset_loading:
            return
        self.cb_item_text_preset.blockSignals(True)
        try:
            self.cb_item_text_preset.setCurrentIndex(0)
        finally:
            self.cb_item_text_preset.blockSignals(False)

    def set_item_preset_combo_mixed(self):
        if not hasattr(self, "cb_item_text_preset") or self._item_preset_loading:
            return
        self.cb_item_text_preset.blockSignals(True)
        try:
            idx = self.cb_item_text_preset.findData("__mixed__")
            if idx < 0:
                self.cb_item_text_preset.insertItem(1, "다수의 프리셋", "__mixed__")
                idx = 1
            self.cb_item_text_preset.setCurrentIndex(idx)
        finally:
            self.cb_item_text_preset.blockSignals(False)

    def update_item_preset_combo_for_selected_texts(self):
        """최종화면 텍스트 선택 상태에 따라 개별 프리셋 콤보 표시를 맞춘다."""
        if not hasattr(self, "cb_item_text_preset") or self._item_preset_loading:
            return

        items = self.selected_text_items()
        if not items:
            self.set_item_preset_combo_custom()
            return

        names = []
        for item in items:
            name = str(item.data.get("item_text_preset_name") or "").strip()
            if not name or name not in getattr(self, "item_text_presets", {}):
                name = "__custom__"
            names.append(name)

        uniq = sorted(set(names))
        if len(uniq) > 1:
            self.set_item_preset_combo_mixed()
            return

        key = uniq[0] if uniq else "__custom__"
        self.cb_item_text_preset.blockSignals(True)
        try:
            mix_idx = self.cb_item_text_preset.findData("__mixed__")
            if mix_idx >= 0:
                self.cb_item_text_preset.removeItem(mix_idx)

            idx = self.cb_item_text_preset.findData(key)
            self.cb_item_text_preset.setCurrentIndex(idx if idx >= 0 else 0)
        finally:
            self.cb_item_text_preset.blockSignals(False)

    def on_item_text_preset_selected(self, *args):
        if self._item_preset_loading or self._item_preset_signal_lock:
            return
        key = self.cb_item_text_preset.currentData() if hasattr(self, "cb_item_text_preset") else "__custom__"
        if not key or key in ("__custom__", "__mixed__"):
            return
        self.apply_item_text_preset_by_name(str(key), from_combo=True)

    def item_preset_style_subset(self, preset):
        style = self.normalize_style_dict(preset.get("style"))
        include = preset.get("include") or {}
        subset = {}
        for key, _label in self.style_field_specs():
            if include.get(key, False):
                subset[key] = style.get(key)
        if include.get("advanced_text_options", False):
            adv = self.normalize_advanced_text_options(style)
            for key in self.advanced_text_effect_fields():
                subset[key] = adv.get(key)
        return subset

    def apply_item_text_preset_by_name(self, name, from_combo=False, record_undo=True):
        name = str(name or "")
        preset = self.item_text_presets.get(name)
        if not preset:
            self.log(f"⚠️ 개별 글꼴 프리셋을 찾지 못했습니다: {name}")
            return False
        if not preset.get("enabled", True):
            self.log(f"⚠️ 비활성화된 개별 글꼴 프리셋입니다: {name}")
            return False
        subset = self.item_preset_style_subset(preset)
        if not subset:
            self.log(f"⚠️ 적용할 옵션이 없는 개별 글꼴 프리셋입니다: {name}")
            return False

        selected = self.selected_text_items()
        if selected and self.cb_mode.currentIndex() == 4:
            self.apply_style_to_selected(preset_name=name, record_undo=record_undo, **subset)
            if from_combo and hasattr(self, "cb_item_text_preset"):
                self._item_preset_signal_lock = True
                try:
                    idx = self.cb_item_text_preset.findData(name)
                    if idx >= 0:
                        self.cb_item_text_preset.setCurrentIndex(idx)
                finally:
                    self._item_preset_signal_lock = False
            self.log(f"🎛️ 개별 글꼴 프리셋 적용: {name}")
            # 글꼴 프리셋은 Undo 경계가 아니라 일반 Undo 스택에 포함한다.
            return True

        self.log("⚠️ 개별 글꼴 프리셋을 적용할 텍스트를 최종화면에서 선택하세요.")
        self.set_item_preset_combo_custom()
        return False

    def selected_scene_text_ids(self):
        ids = [item.data.get('id') for item in self.selected_text_items() if item.data.get('id') is not None]
        for tid in self.selected_table_text_ids():
            if tid is not None and tid not in ids:
                ids.append(tid)
        return ids

    def restore_text_items_by_snapshot(self, page_idx, snapshot_by_id):
        curr = self.data.get(page_idx)
        if not curr or not snapshot_by_id:
            return
        for i, d in enumerate(curr.get('data', [])):
            key = str(d.get('id'))
            if key in snapshot_by_id:
                curr['data'][i] = copy.deepcopy(snapshot_by_id[key])

    def open_text_preset_dialog(self):
        """페이지 글꼴 프리셋 관리.

        확인은 페이지 적용이 아니라 '마지막 설정' 저장 전용이다.
        실제 반영은 현재 페이지에 적용 / 전체 페이지에 적용 버튼에서만 수행한다.
        """
        _dlg_t0 = time.time()
        try:
            self.audit_boundary_event("PRESET_DIALOG_BUILD_ENTER", dialog_key="page_text_preset", memory=memory_text())
        except Exception:
            pass
        dialog = QDialog(self)
        dialog.setProperty("dialog_timing_log_key", "page_text_preset")
        dialog.setProperty("dialog_timing_created_at", _dlg_t0)
        dialog.installEventFilter(self)
        # 구성 중에는 그리지 않아서 흰색 빈 창이 먼저 보이는 느낌을 줄인다.
        dialog.setUpdatesEnabled(False)
        dialog.setWindowTitle(self.tr_ui("페이지 글꼴 프리셋 관리"))
        dialog.resize(1040, 620)
        dialog.setStyleSheet(self.settings_dialog_style())

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        save_location_label = self.tr_ui("저장 위치")
        try:
            preset_dir_display = str(self.text_preset_dir()) if bool(getattr(self, "show_cache_paths_in_settings", False)) else self.tr_ui("경로 숨김")
        except Exception:
            preset_dir_display = self.tr_ui("경로 숨김")
        info = QLabel(f"{save_location_label}: {preset_dir_display}")
        info.setWordWrap(True)
        layout.addWidget(info)

        original_idx = self.idx
        original_page_snapshot = copy.deepcopy(self.data.get(self.idx)) if self.idx in self.data else None
        original_style_snapshot = self.current_style_snapshot()
        original_active_key = self.cb_text_preset.currentData() if hasattr(self, "cb_text_preset") else "__last__"
        dialog_state = {"applied": False, "restored": False}
        dialog_lock = {"value": False}
        selected_name = {"value": None}

        dialog_text_color = {"value": original_style_snapshot.get("text_color", "#000000")}
        dialog_stroke_color = {"value": original_style_snapshot.get("stroke_color", "#FFFFFF")}
        dialog_align = {"value": original_style_snapshot.get("align", "center")}
        dialog_advanced_options = {"value": self.normalize_advanced_text_options(original_style_snapshot)}

        # ---------- style editor ----------
        editor = QWidget(dialog)
        editor_l = QVBoxLayout(editor)
        editor_l.setContentsMargins(0, 0, 0, 0)
        editor_l.setSpacing(6)

        row1 = QHBoxLayout()
        row1.setSpacing(6)
        dlg_font = QFontComboBox(dialog); dlg_font.setFixedWidth(160); dlg_font.setFixedHeight(26)
        dlg_size = QSpinBox(dialog); dlg_size.setRange(TEXT_FONT_SIZE_MIN, TEXT_FONT_SIZE_MAX); dlg_size.setSuffix(" px"); dlg_size.setFixedWidth(96); dlg_size.setFixedHeight(26)
        dlg_stroke = QSpinBox(dialog); dlg_stroke.setRange(0, TEXT_STROKE_WIDTH_MAX); dlg_stroke.setSuffix(" px"); dlg_stroke.setFixedWidth(96); dlg_stroke.setFixedHeight(26)
        dlg_text_color_btn = QPushButton("", dialog); dlg_text_color_btn.setFixedSize(26, 26)
        dlg_stroke_color_btn = QPushButton("", dialog); dlg_stroke_color_btn.setFixedSize(26, 26)
        dlg_align_left = QPushButton("▶", dialog); dlg_align_center = QPushButton("◆", dialog); dlg_align_right = QPushButton("◀", dialog)
        for b in (dlg_align_left, dlg_align_center, dlg_align_right):
            b.setFixedWidth(42); b.setFixedHeight(26)
        row1.addWidget(QLabel(self.tr_ui("폰트"))); row1.addWidget(dlg_font)
        row1.addWidget(QLabel(self.tr_ui("크기"))); row1.addWidget(dlg_size)
        row1.addWidget(dlg_text_color_btn)
        row1.addWidget(QLabel(self.tr_ui("획"))); row1.addWidget(dlg_stroke); row1.addWidget(dlg_stroke_color_btn)
        row1.addWidget(dlg_align_left); row1.addWidget(dlg_align_center); row1.addWidget(dlg_align_right)
        row1.addStretch()
        editor_l.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(6)
        dlg_line_spacing = QSpinBox(dialog); dlg_line_spacing.setRange(TEXT_LINE_SPACING_MIN, TEXT_LINE_SPACING_MAX); dlg_line_spacing.setValue(100); dlg_line_spacing.setSuffix(" %"); dlg_line_spacing.setFixedWidth(96); dlg_line_spacing.setFixedHeight(26)
        dlg_letter_spacing = QSpinBox(dialog); dlg_letter_spacing.setRange(TEXT_LETTER_SPACING_MIN, TEXT_LETTER_SPACING_MAX); dlg_letter_spacing.setSuffix(" px"); dlg_letter_spacing.setFixedWidth(96); dlg_letter_spacing.setFixedHeight(26)
        dlg_char_width = QSpinBox(dialog); dlg_char_width.setRange(TEXT_CHAR_SCALE_MIN, TEXT_CHAR_SCALE_MAX); dlg_char_width.setValue(100); dlg_char_width.setSuffix(" %"); dlg_char_width.setFixedWidth(96); dlg_char_width.setFixedHeight(26)
        dlg_char_height = QSpinBox(dialog); dlg_char_height.setRange(TEXT_CHAR_SCALE_MIN, TEXT_CHAR_SCALE_MAX); dlg_char_height.setValue(100); dlg_char_height.setSuffix(" %"); dlg_char_height.setFixedWidth(96); dlg_char_height.setFixedHeight(26)
        dlg_bold = QPushButton("B", dialog); dlg_italic = QPushButton("I", dialog); dlg_strike = QPushButton("S", dialog)
        dlg_advanced = QPushButton(self.tr_ui("고급..."), dialog)
        dlg_writing_direction = QComboBox(dialog)
        dlg_writing_direction.addItem(self.tr_ui("가로쓰기"), "horizontal")
        dlg_writing_direction.addItem(self.tr_ui("세로쓰기"), "vertical")
        dlg_writing_direction.setFixedHeight(26)
        dlg_writing_direction.setMinimumWidth(92)
        for b, tip in ((dlg_bold, "굵게"), (dlg_italic, "기울이기"), (dlg_strike, "취소선")):
            b.setCheckable(True); b.setFixedWidth(32); b.setFixedHeight(26); b.setToolTip(tip)
        dlg_advanced.setFixedHeight(26); dlg_advanced.setMinimumWidth(68)
        dlg_bold.setStyleSheet("font-weight:bold;"); dlg_italic.setStyleSheet("font-style:italic;"); dlg_strike.setStyleSheet("text-decoration: line-through;")
        self.install_style_editor_shortcuts(dialog, {
            "font": dlg_font,
            "size": dlg_size,
            "stroke": dlg_stroke,
            "line_spacing": dlg_line_spacing,
            "letter_spacing": dlg_letter_spacing,
            "char_width": dlg_char_width,
            "char_height": dlg_char_height,
            "bold": dlg_bold,
            "italic": dlg_italic,
            "strike": dlg_strike,
            "text_color": dlg_text_color_btn,
            "stroke_color": dlg_stroke_color_btn,
            "align_left": dlg_align_left,
            "align_center": dlg_align_center,
            "align_right": dlg_align_right,
        })
        row2.addWidget(QLabel(self.tr_ui("행간"))); row2.addWidget(dlg_line_spacing)
        row2.addWidget(QLabel(self.tr_ui("자간"))); row2.addWidget(dlg_letter_spacing)
        row2.addWidget(QLabel(self.tr_ui("너비"))); row2.addWidget(dlg_char_width)
        row2.addWidget(QLabel(self.tr_ui("높이"))); row2.addWidget(dlg_char_height)
        row2.addWidget(QLabel(self.tr_ui("쓰기 방향"))); row2.addWidget(dlg_writing_direction)
        row2.addWidget(dlg_bold); row2.addWidget(dlg_italic); row2.addWidget(dlg_strike); row2.addWidget(dlg_advanced)
        row2.addStretch()
        editor_l.addLayout(row2)
        layout.addWidget(editor)

        def refresh_color_buttons():
            tip_bg = "#ffffff" if self.is_light_theme() else "#000000"
            tip_fg = "#111827" if self.is_light_theme() else "#ffffff"
            tip_border = "#D1C9CE" if self.is_light_theme() else "#555056"
            dlg_text_color_btn.setStyleSheet(
                f"QPushButton {{ background:{dialog_text_color['value']}; border:1px solid #444; padding:0px; }}"
                f"QToolTip {{ background-color:{tip_bg}; color:{tip_fg}; border:1px solid {tip_border}; border-radius:0px; padding:5px; }}"
            )
            dlg_stroke_color_btn.setStyleSheet(
                f"QPushButton {{ background:{dialog_stroke_color['value']}; border:1px solid #444; padding:0px; }}"
                f"QToolTip {{ background-color:{tip_bg}; color:{tip_fg}; border:1px solid {tip_border}; border-radius:0px; padding:5px; }}"
            )
            checked_style = "background:#F5E8EA; color:#111827; border:1px solid #C78A90; border-radius:0px;" if self.is_light_theme() else "background:#5B3136; color:#ffffff; border:1px solid #C78A90; border-radius:0px;"
            for align, btn in (("left", dlg_align_left), ("center", dlg_align_center), ("right", dlg_align_right)):
                btn.setStyleSheet(checked_style if dialog_align["value"] == align else "")

        def dialog_style_snapshot():
            return self.style_with_advanced_options({
                "font_family": dlg_font.currentFont().family(),
                "font_size": int(dlg_size.value()),
                "stroke_width": int(dlg_stroke.value()),
                "text_color": dialog_text_color["value"],
                "stroke_color": dialog_stroke_color["value"],
                "align": dialog_align["value"],
                "writing_direction": self.normalize_writing_direction(dlg_writing_direction.currentData()),
                "line_spacing": int(dlg_line_spacing.value()),
                "letter_spacing": int(dlg_letter_spacing.value()),
                "char_width": int(dlg_char_width.value()),
                "char_height": int(dlg_char_height.value()),
                "bold": bool(dlg_bold.isChecked()),
                "italic": bool(dlg_italic.isChecked()),
                "strike": bool(dlg_strike.isChecked()),
            }, dialog_advanced_options["value"])

        def apply_style_to_dialog(style):
            style = self.normalize_style_dict(style)
            dialog_lock["value"] = True
            try:
                dlg_font.setCurrentFont(QFont(style["font_family"]))
                dlg_size.setValue(int(style["font_size"]))
                dlg_stroke.setValue(int(style["stroke_width"]))
                dialog_text_color["value"] = style["text_color"]
                dialog_stroke_color["value"] = style["stroke_color"]
                dialog_align["value"] = style["align"]
                idx = dlg_writing_direction.findData(self.normalize_writing_direction(style.get("writing_direction", "horizontal")))
                dlg_writing_direction.setCurrentIndex(idx if idx >= 0 else 0)
                dlg_line_spacing.setValue(100 if int(style["line_spacing"] or 0) == 0 else int(style["line_spacing"]))
                dlg_letter_spacing.setValue(int(style["letter_spacing"]))
                dlg_char_width.setValue(int(style["char_width"]))
                dlg_char_height.setValue(int(style["char_height"]))
                dlg_bold.setChecked(bool(style["bold"]))
                dlg_italic.setChecked(bool(style["italic"]))
                dlg_strike.setChecked(bool(style["strike"]))
                dialog_advanced_options["value"] = self.normalize_advanced_text_options(style)
                refresh_color_buttons()
            finally:
                dialog_lock["value"] = False

        # ---------- preset list ----------
        rows_widget = QWidget(dialog)
        rows_layout = QVBoxLayout(rows_widget)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        rows_layout.setSpacing(4)
        scroll = QScrollArea(dialog); scroll.setWidgetResizable(True); scroll.setWidget(rows_widget); scroll.setMinimumHeight(300)
        layout.addWidget(scroll, 1)

        def preset_tip(widget, title, desc="", key=""):
            try:
                self.set_dialog_control_tooltip(widget, title, key, desc)
            except Exception:
                try:
                    widget.setToolTip("\n".join([self.tr_ui(title), self.tr_msg(desc) if desc else ""]))
                    widget.setProperty("allow_native_tooltip", True)
                except Exception:
                    pass

        # 프리셋 편집창 상단 설정 컨트롤도 메인 인터페이스와 같은 툴팁을 가진다.
        preset_tip(dlg_font, "글꼴 선택", "폰트 설정창을 엽니다.", "item_font_select")
        preset_tip(dlg_size, "글꼴 크기", "현재 페이지 글꼴 프리셋의 글자 크기를 조절합니다.", "text_font_size")
        preset_tip(dlg_stroke, "획 크기", "현재 페이지 글꼴 프리셋의 외곽선 두께를 조절합니다.", "text_stroke_size")
        preset_tip(dlg_text_color_btn, "문자 색상", "현재 페이지 글꼴 프리셋의 문자 색상을 선택합니다.", "item_text_color")
        preset_tip(dlg_stroke_color_btn, "획 색상", "현재 페이지 글꼴 프리셋의 외곽선 색상을 선택합니다.", "item_stroke_color")
        preset_tip(dlg_line_spacing, "행간", "줄과 줄 사이 간격을 조절합니다.", "text_line_spacing")
        preset_tip(dlg_letter_spacing, "자간", "글자와 글자 사이 간격을 조절합니다.", "text_letter_spacing")
        preset_tip(dlg_char_width, "너비", "문자의 가로 비율을 조절합니다.", "text_char_width")
        preset_tip(dlg_char_height, "높이", "문자의 세로 비율을 조절합니다.", "text_char_height")
        preset_tip(dlg_writing_direction, "쓰기 방향", "현재 페이지 글꼴 프리셋의 기본 쓰기 방향을 선택합니다.")
        preset_tip(dlg_bold, "굵게", "굵게 설정을 켜거나 끕니다.", "text_bold_toggle")
        preset_tip(dlg_italic, "기울이기", "기울이기 설정을 켜거나 끕니다.", "text_italic_toggle")
        preset_tip(dlg_strike, "취소선", "취소선 설정을 켜거나 끕니다.", "text_strike_toggle")
        preset_tip(dlg_advanced, "고급 텍스트/획 옵션", "현재 페이지 글꼴 프리셋에 문자/획 그라데이션, 2중 획, 그림자, 후광을 저장합니다.", "text_effect_gradient")
        preset_tip(dlg_align_left, "왼쪽 정렬", "텍스트를 왼쪽으로 정렬합니다.", "item_align_left")
        preset_tip(dlg_align_center, "가운데 정렬", "텍스트를 가운데로 정렬합니다.", "item_align_center")
        preset_tip(dlg_align_right, "오른쪽 정렬", "텍스트를 오른쪽으로 정렬합니다.", "item_align_right")

        def load_page_presets():
            presets = {}
            for path in sorted(self.text_preset_dir().glob("*.json")):
                if path.name.startswith("_"):
                    continue
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        presets[path.stem] = self.normalize_style_dict(json.load(f))
                except Exception:
                    continue
            return presets

        def preview_style_on_current_page(style):
            if original_page_snapshot is None or original_idx not in self.data:
                self.apply_style_to_controls(style)
                return
            self.data[original_idx] = copy.deepcopy(original_page_snapshot)
            style = self.normalize_style_dict(style)
            self.apply_style_to_controls(style)
            curr = self.data.get(original_idx)
            targets = [x for x in curr.get('data', []) if x.get('use_inpaint', True)]
            self.apply_style_dict_to_data_items(targets, style)
            if self.idx == original_idx:
                self.ref_tab()
                if self.cb_mode.currentIndex() == 4:
                    self.mode_chg(4)

        def refresh_rows(select_name=None):
            while rows_layout.count():
                item = rows_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            header = QWidget(rows_widget)
            h = QHBoxLayout(header); h.setContentsMargins(6, 2, 6, 2)
            h.addWidget(QLabel("사용"), 0)
            h.addWidget(QLabel("선택"), 0)
            h.addWidget(QLabel("이름"), 1)
            h.addWidget(QLabel("내용"), 3)
            h.addWidget(QLabel("관리"), 1)
            rows_layout.addWidget(header)

            presets = load_page_presets()
            state = self.page_preset_state()
            enabled_map = state.get("enabled", {})
            for name, style in presets.items():
                row = QWidget(rows_widget)
                row_l = QHBoxLayout(row); row_l.setContentsMargins(6, 2, 6, 2); row_l.setSpacing(6)
                chk = QCheckBox(); chk.setChecked(bool(enabled_map.get(name, True)))
                btn_select = QPushButton("선택")
                name_edit = QLineEdit(name)
                try:
                    if not hasattr(dialog, "_ysb_enter_commit_filter"):
                        dialog._ysb_enter_commit_filter = EnterCommitFilter(parent_dialog=dialog, fallback_widget=dialog, parent=dialog)
                    name_edit.installEventFilter(dialog._ysb_enter_commit_filter)
                except Exception:
                    pass
                summary = QLabel(self.style_summary_text(style)); summary.setWordWrap(True)
                btn_update = QPushButton("수정 저장")
                btn_delete = QPushButton("삭제")
                preset_tip(chk, "프리셋 사용", "체크하면 이 페이지 글꼴 프리셋을 사용할 수 있습니다.")
                preset_tip(btn_select, "페이지 프리셋 선택", "이 프리셋을 현재 프리셋 편집창에 불러오고, 현재 페이지에 미리보기로 적용합니다.")
                preset_tip(name_edit, "프리셋 이름", "이름을 바꾸고 Enter를 누르거나 포커스를 빼면 프리셋 이름이 변경됩니다.")
                preset_tip(summary, "프리셋 내용", "이 프리셋에 저장된 글꼴, 크기, 색상, 행간, 자간 등 스타일 요약입니다.")
                preset_tip(btn_update, "프리셋 수정 저장", "현재 위쪽 편집값으로 이 페이지 글꼴 프리셋을 덮어씁니다.")
                preset_tip(btn_delete, "프리셋 삭제", "이 페이지 글꼴 프리셋을 삭제합니다.")

                if not chk.isChecked():
                    if self.is_light_theme():
                        row.setStyleSheet("background:#F2EDEF; color:#91888F;")
                        summary.setStyleSheet("color:#91888F;")
                        name_edit.setStyleSheet("background:#F8F3F5; color:#91888F; border:1px solid #D2CBD0;")
                    else:
                        row.setStyleSheet("background:#242424; color:#888888;")
                        summary.setStyleSheet("color:#888888;")
                        name_edit.setStyleSheet("color:#888888;")
                is_selected = (selected_name["value"] == name or select_name == name)
                if is_selected:
                    if self.is_light_theme():
                        row_style = "background:#e8f1ff; border:1px solid #A85D66;"
                        child_style = "background:#ffffff; color:#202124; border:1px solid #A85D66;"
                    else:
                        row_style = "background:#31415c; border:1px solid #5b8def;"
                        child_style = "background:#2f5fa7; color:white; border:1px solid #80b4ff;"
                    row.setStyleSheet(row_style)
                    btn_select.setText("선택됨")
                    btn_select.setStyleSheet("background:#4b79c7; color:white; font-weight:bold; border:1px solid #9cc3ff;")
                    name_edit.setStyleSheet(child_style)
                    summary.setStyleSheet(child_style)
                    btn_update.setStyleSheet("background:#8A4A52; color:white;")
                    btn_delete.setStyleSheet("background:#8A4A52; color:white;")
                    selected_name["value"] = name

                row_l.addWidget(chk)
                row_l.addWidget(btn_select)
                row_l.addWidget(name_edit, 1)
                row_l.addWidget(summary, 3)
                row_l.addWidget(btn_update)
                row_l.addWidget(btn_delete)
                rows_layout.addWidget(row)

                def on_enabled(v, n=name):
                    st = self.page_preset_state()
                    st.setdefault("enabled", {})[n] = bool(v)
                    self.save_page_preset_state(st)
                    self.load_text_preset_cache()
                    self.log(f"🔘 페이지 글꼴 프리셋 {'사용' if v else '미사용'}: {n}")
                    refresh_rows(selected_name["value"])

                def on_select(_checked=False, n=name):
                    # 이미 선택된 프리셋을 다시 누르면 선택 해제한다.
                    if selected_name["value"] == n:
                        selected_name["value"] = None
                        if original_page_snapshot is not None and original_idx in self.data:
                            self.data[original_idx] = copy.deepcopy(original_page_snapshot)
                            if self.idx == original_idx:
                                self.ref_tab()
                                if self.cb_mode.currentIndex() == 4:
                                    self.mode_chg(4)
                        refresh_rows(None)
                        self.log(f"↩️ 페이지 글꼴 프리셋 선택 해제: {n}")
                        return

                    presets_now = load_page_presets()
                    style_now = presets_now.get(n)
                    if not style_now:
                        return
                    selected_name["value"] = n
                    apply_style_to_dialog(style_now)
                    preview_style_on_current_page(style_now)
                    refresh_rows(n)
                    self.log(f"🎛️ 페이지 글꼴 프리셋 선택: {n}")

                def on_name_finished(edit=name_edit, old_name=name):
                    new_name = self.safe_preset_name(edit.text())
                    if not new_name or new_name == old_name:
                        edit.setText(old_name); return
                    old_path = self.text_preset_path(old_name)
                    new_path = self.text_preset_path(new_name)
                    if new_path.exists():
                        QMessageBox.warning(dialog, self.tr_ui("이름 변경 실패"), self.tr_ui("같은 이름의 프리셋이 이미 있습니다."))
                        edit.setText(old_name); return
                    if old_path.exists():
                        old_path.rename(new_path)
                    st = self.page_preset_state()
                    enabled = st.setdefault("enabled", {})
                    if old_name in enabled:
                        enabled[new_name] = enabled.pop(old_name)
                    if st.get("active") == old_name:
                        st["active"] = new_name
                    self.save_page_preset_state(st)
                    if selected_name["value"] == old_name:
                        selected_name["value"] = new_name
                    refresh_rows(new_name)

                def on_update(_checked=False, n=name, label=summary):
                    style_now = dialog_style_snapshot()
                    with open(self.text_preset_path(n), "w", encoding="utf-8") as f:
                        json.dump(style_now, f, ensure_ascii=False, indent=2)
                    selected_name["value"] = n
                    label.setText(self.style_summary_text(style_now))
                    refresh_rows(n)
                    self.log(f"💾 페이지 글꼴 프리셋 수정 저장: {n}")

                def on_delete(_checked=False, n=name):
                    ans = QMessageBox.question(dialog, self.tr_ui("프리셋 삭제"), self.tr_msg(f"'{n}' 프리셋을 삭제할까요?"), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                    if ans != QMessageBox.StandardButton.Yes:
                        return
                    try:
                        self.text_preset_path(n).unlink(missing_ok=True)
                    except Exception:
                        pass
                    st = self.page_preset_state()
                    st.setdefault("enabled", {}).pop(n, None)
                    if st.get("active") == n:
                        st["active"] = "__last__"
                    self.save_page_preset_state(st)
                    if selected_name["value"] == n:
                        selected_name["value"] = None
                    refresh_rows()
                    self.log(f"🗑️ 페이지 글꼴 프리셋 삭제: {n}")

                chk.toggled.connect(on_enabled)
                btn_select.clicked.connect(on_select)
                name_edit.editingFinished.connect(on_name_finished)
                btn_update.clicked.connect(on_update)
                btn_delete.clicked.connect(on_delete)

            rows_layout.addStretch()

        def restore_full_original_state():
            _restore_t0 = time.time()
            try:
                self.audit_boundary_event("PRESET_DIALOG_RESTORE_ENTER", dialog_key="page_text_preset", reason="restore_full_original_state", memory=memory_text())
            except Exception:
                pass
            if original_page_snapshot is not None and original_idx in self.data:
                self.data[original_idx] = copy.deepcopy(original_page_snapshot)
            self.apply_style_to_controls(original_style_snapshot)
            self.load_text_preset_cache()

            def _refresh_after_dialog_close():
                try:
                    if self.idx == original_idx:
                        self.ref_tab()
                        if self.cb_mode.currentIndex() == 4:
                            self.mode_chg(4)
                finally:
                    try:
                        self.audit_boundary_event("PRESET_DIALOG_RESTORE_REFRESH_DONE", dialog_key="page_text_preset", memory=memory_text(), throttle_ms=50)
                    except Exception:
                        pass

            if self.idx == original_idx:
                # 닫는 순간에 화면을 통째로 재구성하면 창이 깜빡이는 느낌이 난다.
                # 데이터 원복은 즉시 하고, 무거운 화면 재구성은 다음 이벤트 틱으로 미룬다.
                QTimer.singleShot(0, _refresh_after_dialog_close)
            dialog_state["restored"] = True
            try:
                self.audit_boundary_event("PRESET_DIALOG_RESTORE_DONE", dialog_key="page_text_preset", elapsed_ms=int((time.time() - _restore_t0) * 1000), deferred_refresh=True, memory=memory_text())
            except Exception:
                pass

        def on_dialog_style_changed(*args):
            if dialog_lock["value"]:
                return
            refresh_color_buttons()
            preview_style_on_current_page(dialog_style_snapshot())

        def pick_dialog_color(target):
            current = dialog_text_color["value"] if target == "text" else dialog_stroke_color["value"]
            color = ysb_get_color_with_hex_focus(QColor(current), self, "색상 선택")
            if not color.isValid():
                return
            if target == "text":
                dialog_text_color["value"] = color.name(QColor.NameFormat.HexRgb).upper()
            else:
                dialog_stroke_color["value"] = color.name(QColor.NameFormat.HexRgb).upper()
            on_dialog_style_changed()

        def set_dialog_align(align):
            dialog_align["value"] = align
            on_dialog_style_changed()

        def open_dialog_advanced_options():
            before = copy.deepcopy(dialog_advanced_options["value"])
            values = self.open_preset_advanced_text_options_dialog(dialog_style_snapshot(), parent_dialog=dialog, preview_callback=preview_style_on_current_page)
            if values is None:
                dialog_advanced_options["value"] = before
                preview_style_on_current_page(dialog_style_snapshot())
                return
            dialog_advanced_options["value"] = values
            preview_style_on_current_page(dialog_style_snapshot())
            self.log("🎨 페이지 글꼴 프리셋 고급 옵션 편집")

        for widget in (dlg_font, dlg_size, dlg_stroke, dlg_line_spacing, dlg_letter_spacing, dlg_char_width, dlg_char_height):
            if hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(on_dialog_style_changed)
        dlg_writing_direction.currentIndexChanged.connect(on_dialog_style_changed)
        dlg_font.currentFontChanged.connect(on_dialog_style_changed)
        dlg_bold.toggled.connect(on_dialog_style_changed)
        dlg_italic.toggled.connect(on_dialog_style_changed)
        dlg_strike.toggled.connect(on_dialog_style_changed)
        dlg_text_color_btn.clicked.connect(self.make_safe_slot(pick_dialog_color, "text"))
        dlg_stroke_color_btn.clicked.connect(self.make_safe_slot(pick_dialog_color, "stroke"))
        dlg_align_left.clicked.connect(self.make_safe_slot(set_dialog_align, "left"))
        dlg_align_center.clicked.connect(self.make_safe_slot(set_dialog_align, "center"))
        dlg_align_right.clicked.connect(self.make_safe_slot(set_dialog_align, "right"))
        dlg_advanced.clicked.connect(open_dialog_advanced_options)

        btn_line = QHBoxLayout()
        btn_add = QPushButton(self.tr_ui("현재 스타일을 새 프리셋으로 추가"), dialog)
        btn_import = QPushButton(self.tr_ui("불러오기"), dialog)
        btn_apply_page = QPushButton(self.tr_ui("현재 페이지에 적용"), dialog)
        btn_apply_all = QPushButton(self.tr_ui("전체 페이지에 적용"), dialog)
        btn_ok = QPushButton(self.tr_ui("확인"), dialog)
        btn_close = QPushButton(self.tr_ui("닫기"), dialog)
        preset_tip(btn_add, "페이지 프리셋 추가", "현재 위쪽 편집값을 새 페이지 글꼴 프리셋으로 저장합니다.")
        preset_tip(btn_import, "페이지 프리셋 불러오기", "외부 JSON 파일에서 페이지 글꼴 프리셋을 가져옵니다.")
        preset_tip(btn_apply_page, "현재 페이지에 적용", "선택한 페이지 글꼴 프리셋을 현재 페이지의 텍스트들에 적용하고 창을 닫습니다.")
        preset_tip(btn_apply_all, "전체 페이지에 적용", "선택한 페이지 글꼴 프리셋을 전체 페이지에 적용하고 창을 닫습니다.")
        preset_tip(btn_ok, "확인", "페이지에 적용하지 않고 마지막 설정값만 저장한 뒤 닫습니다.")
        preset_tip(btn_close, "닫기", "변경사항을 저장하지 않고 창을 닫습니다.")
        btn_line.addWidget(btn_add)
        btn_line.addWidget(btn_import)
        btn_line.addStretch()
        btn_line.addWidget(btn_apply_page)
        btn_line.addWidget(btn_apply_all)
        btn_line.addWidget(btn_ok)
        btn_line.addWidget(btn_close)
        layout.addLayout(btn_line)

        def add_current_as_preset():
            name, ok = QInputDialog.getText(dialog, self.tr_ui("페이지 프리셋 추가"), self.tr_ui("프리셋 이름:"))
            if not ok or not name.strip():
                return
            safe = self.safe_preset_name(name)
            if self.text_preset_path(safe).exists():
                ans = QMessageBox.question(dialog, self.tr_ui("덮어쓰기"), self.tr_msg(f"'{safe}' 프리셋이 이미 있습니다. 덮어쓸까요?"), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if ans != QMessageBox.StandardButton.Yes:
                    return
            with open(self.text_preset_path(safe), "w", encoding="utf-8") as f:
                json.dump(dialog_style_snapshot(), f, ensure_ascii=False, indent=2)
            st = self.page_preset_state()
            st.setdefault("enabled", {})[safe] = True
            self.save_page_preset_state(st)
            # 새로 추가는 목록에만 추가한다. 파란 선택 강조는 남기지 않는다.
            selected_name["value"] = None
            refresh_rows(None)
            self.log(f"💾 페이지 글꼴 프리셋 추가: {safe}")

        def import_page_preset():
            path, _ = self.get_open_file_name_logged("import_page_preset", dialog, self.tr_ui("페이지 글꼴 프리셋 불러오기"), str(self.text_preset_dir()), "JSON (*.json)")
            if not path:
                return
            try:
                with open(path, "r", encoding="utf-8-sig") as f:
                    raw = json.load(f)
                style = self.normalize_style_dict(raw.get("style") if isinstance(raw, dict) and "style" in raw else raw)
            except Exception as e:
                msg_text = self.tr_ui("프리셋 JSON을 읽지 못했습니다.")
                QMessageBox.warning(dialog, self.tr_ui("불러오기 실패"), f"{msg_text}\n{e}")
                return
            default_name = Path(path).stem
            name, ok = QInputDialog.getText(dialog, self.tr_ui("프리셋 이름"), self.tr_ui("추가할 프리셋 이름:"), text=default_name)
            if not ok or not name.strip():
                return
            safe = self.safe_preset_name(name)
            with open(self.text_preset_path(safe), "w", encoding="utf-8") as f:
                json.dump(style, f, ensure_ascii=False, indent=2)
            # 불러오기는 프리셋 목록에 추가만 한다. 파란 선택 행은 남기지 않는다.
            selected_name["value"] = None
            apply_style_to_dialog(style)
            preview_style_on_current_page(style)
            refresh_rows(None)
            self.log(f"📥 페이지 글꼴 프리셋 불러오기 완료: {safe}")

        def commit_dialog_style(active_key=None):
            active_key = active_key or selected_name["value"] or "__last__"
            self.apply_style_to_controls(dialog_style_snapshot())
            self.save_last_text_preset(active_key)
            self.load_text_preset_cache()
            return dialog_style_snapshot()

        def apply_to_current_page_and_close():
            commit_dialog_style()
            if self.idx in self.data:
                self.apply_current_preset_to_page(self.idx, refresh=True)
                self.auto_save_project()
            else:
                self.log("⚠️ 현재 페이지가 없어 프리셋은 저장만 하고 페이지 적용은 생략합니다.")
            dialog_state["applied"] = True
            dialog.accept()

        def apply_to_all_pages_and_close():
            commit_dialog_style()
            if any(bool(self.data.get(i)) for i in range(len(self.paths))):
                self.apply_current_preset_to_all_pages()
                self.auto_save_project()
            else:
                self.log("⚠️ 전체 페이지 데이터가 없어 프리셋은 저장만 하고 전체 적용은 생략합니다.")
            dialog_state["applied"] = True
            dialog.accept()

        def confirm_save_last_only():
            # 확인은 페이지 적용이 아니다. 미리보기로 바뀐 현재 페이지 데이터를 먼저 원복한 뒤,
            # 상단에서 만진 "마지막 설정값"만 저장한다.
            if original_page_snapshot is not None and original_idx in self.data:
                self.data[original_idx] = copy.deepcopy(original_page_snapshot)
            commit_dialog_style()
            if self.idx == original_idx:
                QTimer.singleShot(0, lambda: (self.ref_tab(), self.mode_chg(4) if self.cb_mode.currentIndex() == 4 else None))
            dialog_state["restored"] = True
            self.log("💾 페이지 글꼴 프리셋 마지막 설정 저장 완료")
            dialog.accept()

        btn_add.clicked.connect(add_current_as_preset)
        btn_import.clicked.connect(import_page_preset)
        btn_apply_page.clicked.connect(apply_to_current_page_and_close)
        btn_apply_all.clicked.connect(apply_to_all_pages_and_close)
        btn_ok.clicked.connect(confirm_save_last_only)
        btn_close.clicked.connect(dialog.reject)

        apply_style_to_dialog(original_style_snapshot)
        refresh_color_buttons()
        refresh_rows(selected_name["value"])

        try:
            self.audit_boundary_event("PRESET_DIALOG_BUILD_DONE", dialog_key="page_text_preset", elapsed_ms=int((time.time() - _dlg_t0) * 1000), memory=memory_text())
        except Exception:
            pass
        try:
            dialog.setUpdatesEnabled(True)
            dialog.update()
        except Exception:
            pass
        try:
            dialog.setProperty("dialog_timing_exec_enter_at", time.time())
            self.audit_boundary_event("PRESET_DIALOG_EXEC_ENTER", dialog_key="page_text_preset", memory=memory_text())
        except Exception:
            pass
        try:
            self.apply_portable_spinbox_style(dialog)
        except Exception:
            pass
        result = dialog.exec()
        try:
            self.audit_boundary_event("PRESET_DIALOG_EXEC_RETURN", dialog_key="page_text_preset", result=int(result), elapsed_ms=int((time.time() - float(dialog.property("dialog_timing_exec_enter_at") or time.time())) * 1000), memory=memory_text())
        except Exception:
            pass
        if not dialog_state["applied"] and not dialog_state["restored"]:
            restore_full_original_state()

    def open_item_text_preset_dialog(self):
        """선택 텍스트에만 적용하는 개별 글꼴 프리셋 관리.

        이 창의 실시간 변경은 선택 텍스트에만 임시 미리보기로 보이고,
        확인/닫기로 나가면 실제 텍스트에는 적용하지 않는다.
        실제 적용은 우측 콤보 선택 또는 프리셋 단축키로만 한다.
        """
        _dlg_t0 = time.time()
        try:
            self.audit_boundary_event("PRESET_DIALOG_BUILD_ENTER", dialog_key="item_text_preset", memory=memory_text())
        except Exception:
            pass
        dialog = QDialog(self)
        dialog.setProperty("dialog_timing_log_key", "item_text_preset")
        dialog.setProperty("dialog_timing_created_at", _dlg_t0)
        dialog.installEventFilter(self)
        dialog.setUpdatesEnabled(False)
        dialog.setWindowTitle(self.tr_ui("개별 글꼴 프리셋 관리"))
        dialog.resize(1120, 680)
        dialog.setStyleSheet(self.settings_dialog_style())

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        save_location_label = self.tr_ui("저장 위치")
        preset_note = self.tr_msg("체크한 옵션만 프리셋에 포함됩니다. 이 창의 미리보기는 닫을 때 원래대로 복구됩니다.")
        try:
            preset_dir_display = str(self.item_text_preset_dir()) if bool(getattr(self, "show_cache_paths_in_settings", False)) else self.tr_ui("경로 숨김")
        except Exception:
            preset_dir_display = self.tr_ui("경로 숨김")
        info = QLabel(f"{save_location_label}: {preset_dir_display}\n{preset_note}")
        info.setWordWrap(True)
        layout.addWidget(info)

        page_idx = self.idx
        original_page_snapshot = copy.deepcopy(self.data.get(page_idx)) if page_idx in self.data else None
        selected_ids = self.selected_scene_text_ids()
        curr = self.data.get(page_idx)
        selected_snapshot = {}
        if curr and selected_ids:
            idset = {str(x) for x in selected_ids}
            for d in curr.get('data', []):
                if str(d.get('id')) in idset:
                    selected_snapshot[str(d.get('id'))] = copy.deepcopy(d)

        state = self.load_item_text_preset_state()
        base_style = self.normalize_style_dict(state.get("style") or self.current_style_snapshot())
        include_default = state.get("include") or {k: True for k, _ in self.style_field_specs()}

        dialog_lock = {"value": False}
        selected_name = {"value": state.get("selected")}
        dialog_text_color = {"value": base_style["text_color"]}
        dialog_stroke_color = {"value": base_style["stroke_color"]}
        dialog_align = {"value": base_style["align"]}
        dialog_advanced_options = {"value": self.normalize_advanced_text_options(base_style)}

        # ---------- editor ----------
        top = QWidget(dialog)
        top_l = QVBoxLayout(top); top_l.setContentsMargins(0, 0, 0, 0); top_l.setSpacing(6)

        row1 = QHBoxLayout(); row1.setSpacing(6)
        dlg_font = QFontComboBox(dialog); dlg_font.setFixedWidth(160); dlg_font.setFixedHeight(26)
        dlg_size = QSpinBox(dialog); dlg_size.setRange(TEXT_FONT_SIZE_MIN, TEXT_FONT_SIZE_MAX); dlg_size.setSuffix(" px"); dlg_size.setFixedWidth(96); dlg_size.setFixedHeight(26)
        dlg_stroke = QSpinBox(dialog); dlg_stroke.setRange(0, TEXT_STROKE_WIDTH_MAX); dlg_stroke.setSuffix(" px"); dlg_stroke.setFixedWidth(96); dlg_stroke.setFixedHeight(26)
        dlg_text_color_btn = QPushButton("", dialog); dlg_text_color_btn.setFixedSize(26, 26)
        dlg_stroke_color_btn = QPushButton("", dialog); dlg_stroke_color_btn.setFixedSize(26, 26)
        dlg_align_left = QPushButton("▶", dialog); dlg_align_center = QPushButton("◆", dialog); dlg_align_right = QPushButton("◀", dialog)
        for b in (dlg_align_left, dlg_align_center, dlg_align_right):
            b.setFixedWidth(42); b.setFixedHeight(26)
        row1.addWidget(QLabel(self.tr_ui("폰트"))); row1.addWidget(dlg_font)
        row1.addWidget(QLabel(self.tr_ui("크기"))); row1.addWidget(dlg_size)
        row1.addWidget(dlg_text_color_btn)
        row1.addWidget(QLabel(self.tr_ui("획"))); row1.addWidget(dlg_stroke); row1.addWidget(dlg_stroke_color_btn)
        row1.addWidget(dlg_align_left); row1.addWidget(dlg_align_center); row1.addWidget(dlg_align_right)
        row1.addStretch()
        top_l.addLayout(row1)

        row2 = QHBoxLayout(); row2.setSpacing(6)
        dlg_line_spacing = QSpinBox(dialog); dlg_line_spacing.setRange(TEXT_LINE_SPACING_MIN, TEXT_LINE_SPACING_MAX); dlg_line_spacing.setValue(100); dlg_line_spacing.setSuffix(" %"); dlg_line_spacing.setFixedWidth(96); dlg_line_spacing.setFixedHeight(26)
        dlg_letter_spacing = QSpinBox(dialog); dlg_letter_spacing.setRange(TEXT_LETTER_SPACING_MIN, TEXT_LETTER_SPACING_MAX); dlg_letter_spacing.setSuffix(" px"); dlg_letter_spacing.setFixedWidth(96); dlg_letter_spacing.setFixedHeight(26)
        dlg_char_width = QSpinBox(dialog); dlg_char_width.setRange(TEXT_CHAR_SCALE_MIN, TEXT_CHAR_SCALE_MAX); dlg_char_width.setValue(100); dlg_char_width.setSuffix(" %"); dlg_char_width.setFixedWidth(96); dlg_char_width.setFixedHeight(26)
        dlg_char_height = QSpinBox(dialog); dlg_char_height.setRange(TEXT_CHAR_SCALE_MIN, TEXT_CHAR_SCALE_MAX); dlg_char_height.setValue(100); dlg_char_height.setSuffix(" %"); dlg_char_height.setFixedWidth(96); dlg_char_height.setFixedHeight(26)
        dlg_bold = QPushButton("B", dialog); dlg_italic = QPushButton("I", dialog); dlg_strike = QPushButton("S", dialog)
        dlg_advanced = QPushButton(self.tr_ui("고급..."), dialog)
        dlg_writing_direction = QComboBox(dialog)
        dlg_writing_direction.addItem(self.tr_ui("가로쓰기"), "horizontal")
        dlg_writing_direction.addItem(self.tr_ui("세로쓰기"), "vertical")
        dlg_writing_direction.setFixedHeight(26)
        dlg_writing_direction.setMinimumWidth(92)
        for b, tip in ((dlg_bold, "굵게"), (dlg_italic, "기울이기"), (dlg_strike, "취소선")):
            b.setCheckable(True); b.setFixedWidth(32); b.setFixedHeight(26); b.setToolTip(tip)
        dlg_advanced.setFixedHeight(26); dlg_advanced.setMinimumWidth(68)
        dlg_bold.setStyleSheet("font-weight:bold;"); dlg_italic.setStyleSheet("font-style:italic;"); dlg_strike.setStyleSheet("text-decoration: line-through;")
        self.install_style_editor_shortcuts(dialog, {
            "font": dlg_font,
            "size": dlg_size,
            "stroke": dlg_stroke,
            "line_spacing": dlg_line_spacing,
            "letter_spacing": dlg_letter_spacing,
            "char_width": dlg_char_width,
            "char_height": dlg_char_height,
            "bold": dlg_bold,
            "italic": dlg_italic,
            "strike": dlg_strike,
            "text_color": dlg_text_color_btn,
            "stroke_color": dlg_stroke_color_btn,
            "align_left": dlg_align_left,
            "align_center": dlg_align_center,
            "align_right": dlg_align_right,
        })
        row2.addWidget(QLabel(self.tr_ui("행간"))); row2.addWidget(dlg_line_spacing)
        row2.addWidget(QLabel(self.tr_ui("자간"))); row2.addWidget(dlg_letter_spacing)
        row2.addWidget(QLabel(self.tr_ui("너비"))); row2.addWidget(dlg_char_width)
        row2.addWidget(QLabel(self.tr_ui("높이"))); row2.addWidget(dlg_char_height)
        row2.addWidget(QLabel(self.tr_ui("쓰기 방향"))); row2.addWidget(dlg_writing_direction)
        row2.addWidget(dlg_bold); row2.addWidget(dlg_italic); row2.addWidget(dlg_strike); row2.addWidget(dlg_advanced)
        row2.addStretch()
        top_l.addLayout(row2)

        include_box = QGroupBox("프리셋에 포함할 옵션", dialog)
        include_l = QGridLayout(include_box)
        include_checks = {}
        for idx, (key, label) in enumerate(self.style_field_specs()):
            chk = QCheckBox(label, include_box)
            chk.setChecked(bool(include_default.get(key, False)))
            include_checks[key] = chk
            include_l.addWidget(chk, idx // 7, idx % 7)
        adv_idx = len(self.style_field_specs())
        chk_adv = QCheckBox(self.tr_ui("고급 옵션"), include_box)
        chk_adv.setChecked(bool(include_default.get("advanced_text_options", self.style_has_advanced_text_options(base_style))))
        include_checks["advanced_text_options"] = chk_adv
        include_l.addWidget(chk_adv, adv_idx // 7, adv_idx % 7)
        top_l.addWidget(include_box)
        layout.addWidget(top)

        def current_dialog_style():
            return self.style_with_advanced_options({
                "font_family": dlg_font.currentFont().family(),
                "font_size": int(dlg_size.value()),
                "stroke_width": int(dlg_stroke.value()),
                "text_color": dialog_text_color["value"],
                "stroke_color": dialog_stroke_color["value"],
                "align": dialog_align["value"],
                "writing_direction": self.normalize_writing_direction(dlg_writing_direction.currentData()),
                "line_spacing": int(dlg_line_spacing.value()),
                "letter_spacing": int(dlg_letter_spacing.value()),
                "char_width": int(dlg_char_width.value()),
                "char_height": int(dlg_char_height.value()),
                "bold": bool(dlg_bold.isChecked()),
                "italic": bool(dlg_italic.isChecked()),
                "strike": bool(dlg_strike.isChecked()),
            }, dialog_advanced_options["value"])

        def current_include():
            return {k: chk.isChecked() for k, chk in include_checks.items()}

        def refresh_color_buttons():
            tip_bg = "#ffffff" if self.is_light_theme() else "#000000"
            tip_fg = "#111827" if self.is_light_theme() else "#ffffff"
            tip_border = "#D1C9CE" if self.is_light_theme() else "#555056"
            dlg_text_color_btn.setStyleSheet(
                f"QPushButton {{ background:{dialog_text_color['value']}; border:1px solid #444; padding:0px; }}"
                f"QToolTip {{ background-color:{tip_bg}; color:{tip_fg}; border:1px solid {tip_border}; border-radius:0px; padding:5px; }}"
            )
            dlg_stroke_color_btn.setStyleSheet(
                f"QPushButton {{ background:{dialog_stroke_color['value']}; border:1px solid #444; padding:0px; }}"
                f"QToolTip {{ background-color:{tip_bg}; color:{tip_fg}; border:1px solid {tip_border}; border-radius:0px; padding:5px; }}"
            )
            checked_style = "background:#F5E8EA; color:#111827; border:1px solid #C78A90; border-radius:0px;" if self.is_light_theme() else "background:#5B3136; color:#ffffff; border:1px solid #C78A90; border-radius:0px;"
            for align, btn in (("left", dlg_align_left), ("center", dlg_align_center), ("right", dlg_align_right)):
                btn.setStyleSheet(checked_style if dialog_align["value"] == align else "")

        def apply_style_to_editor(style, include=None):
            st = self.normalize_style_dict(style)
            inc = include if include is not None else current_include()
            dialog_lock["value"] = True
            try:
                dlg_font.setCurrentFont(QFont(st["font_family"]))
                dlg_size.setValue(int(st["font_size"]))
                dlg_stroke.setValue(int(st["stroke_width"]))
                dialog_text_color["value"] = st["text_color"]
                dialog_stroke_color["value"] = st["stroke_color"]
                dialog_align["value"] = st["align"]
                idx = dlg_writing_direction.findData(self.normalize_writing_direction(st.get("writing_direction", "horizontal")))
                dlg_writing_direction.setCurrentIndex(idx if idx >= 0 else 0)
                dlg_line_spacing.setValue(100 if int(st["line_spacing"] or 0) == 0 else int(st["line_spacing"]))
                dlg_letter_spacing.setValue(int(st["letter_spacing"]))
                dlg_char_width.setValue(int(st["char_width"]))
                dlg_char_height.setValue(int(st["char_height"]))
                dlg_bold.setChecked(bool(st["bold"]))
                dlg_italic.setChecked(bool(st["italic"]))
                dlg_strike.setChecked(bool(st["strike"]))
                dialog_advanced_options["value"] = self.normalize_advanced_text_options(st)
                for k, chk in include_checks.items():
                    chk.setChecked(bool(inc.get(k, False)))
                refresh_color_buttons()
            finally:
                dialog_lock["value"] = False

        def preview_selected_only():
            if dialog_lock["value"]:
                return
            if not selected_snapshot:
                refresh_color_buttons()
                return

            # 누적 미리보기/다른 텍스트 오염 방지:
            # 매번 창을 열었을 때의 전체 페이지 원본 상태에서 다시 시작한다.
            if original_page_snapshot is not None and page_idx in self.data:
                self.data[page_idx] = copy.deepcopy(original_page_snapshot)
            else:
                self.restore_text_items_by_snapshot(page_idx, selected_snapshot)

            preset = {"style": current_dialog_style(), "include": current_include()}
            subset = self.item_preset_style_subset(preset)
            if subset:
                curr_now = self.data.get(page_idx)
                if curr_now:
                    idset = set(selected_snapshot.keys())
                    for d in curr_now.get('data', []):
                        if str(d.get('id')) in idset:
                            for k, v in subset.items():
                                d[k] = v
            if self.idx == page_idx:
                self.ref_tab()
                if self.cb_mode.currentIndex() == 4:
                    self.mode_chg(4)
                    self.reselect_text_items([int(x) for x in selected_snapshot.keys() if str(x).isdigit()])
            refresh_color_buttons()

        def pick_color(target):
            current = dialog_text_color["value"] if target == "text" else dialog_stroke_color["value"]
            color = ysb_get_color_with_hex_focus(QColor(current), self, "색상 선택")
            if not color.isValid():
                return
            if target == "text":
                dialog_text_color["value"] = color.name(QColor.NameFormat.HexRgb).upper()
            else:
                dialog_stroke_color["value"] = color.name(QColor.NameFormat.HexRgb).upper()
            preview_selected_only()

        def set_align(a):
            dialog_align["value"] = a
            preview_selected_only()

        def open_item_dialog_advanced_options():
            before = copy.deepcopy(dialog_advanced_options["value"])
            values = self.open_preset_advanced_text_options_dialog(current_dialog_style(), parent_dialog=dialog, preview_callback=lambda style: (dialog_advanced_options.__setitem__("value", self.normalize_advanced_text_options(style)), preview_selected_only()))
            if values is None:
                dialog_advanced_options["value"] = before
                preview_selected_only()
                return
            dialog_advanced_options["value"] = values
            preview_selected_only()
            self.log("🎨 개별 글꼴 프리셋 고급 옵션 편집")

        for widget in (dlg_font, dlg_size, dlg_stroke, dlg_line_spacing, dlg_letter_spacing, dlg_char_width, dlg_char_height):
            if hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(preview_selected_only)
        dlg_font.currentFontChanged.connect(preview_selected_only)
        dlg_writing_direction.currentIndexChanged.connect(preview_selected_only)
        dlg_bold.toggled.connect(preview_selected_only)
        dlg_italic.toggled.connect(preview_selected_only)
        dlg_strike.toggled.connect(preview_selected_only)
        for chk in include_checks.values():
            chk.toggled.connect(preview_selected_only)
        dlg_text_color_btn.clicked.connect(self.make_safe_slot(pick_color, "text"))
        dlg_stroke_color_btn.clicked.connect(self.make_safe_slot(pick_color, "stroke"))
        dlg_align_left.clicked.connect(self.make_safe_slot(set_align, "left"))
        dlg_align_center.clicked.connect(self.make_safe_slot(set_align, "center"))
        dlg_align_right.clicked.connect(self.make_safe_slot(set_align, "right"))
        dlg_advanced.clicked.connect(open_item_dialog_advanced_options)

        # ---------- rows ----------
        rows_widget = QWidget(dialog)
        rows_layout = QVBoxLayout(rows_widget)
        rows_layout.setContentsMargins(0, 0, 0, 0); rows_layout.setSpacing(4)
        scroll = QScrollArea(dialog); scroll.setWidgetResizable(True); scroll.setWidget(rows_widget); scroll.setMinimumHeight(300)
        layout.addWidget(scroll, 1)

        def preset_tip(widget, title, desc="", key=""):
            try:
                self.set_dialog_control_tooltip(widget, title, key, desc)
            except Exception:
                try:
                    widget.setToolTip("\n".join([self.tr_ui(title), self.tr_msg(desc) if desc else ""]))
                    widget.setProperty("allow_native_tooltip", True)
                except Exception:
                    pass

        # 프리셋 편집창 상단 설정 컨트롤도 메인 인터페이스와 같은 툴팁을 가진다.
        preset_tip(dlg_font, "글꼴 선택", "폰트 설정창을 엽니다.", "item_font_select")
        preset_tip(dlg_size, "글꼴 크기", "개별 글꼴 프리셋의 글자 크기를 조절합니다.", "text_font_size")
        preset_tip(dlg_stroke, "획 크기", "개별 글꼴 프리셋의 외곽선 두께를 조절합니다.", "text_stroke_size")
        preset_tip(dlg_text_color_btn, "문자 색상", "개별 글꼴 프리셋의 문자 색상을 선택합니다.", "item_text_color")
        preset_tip(dlg_stroke_color_btn, "획 색상", "개별 글꼴 프리셋의 외곽선 색상을 선택합니다.", "item_stroke_color")
        preset_tip(dlg_line_spacing, "행간", "줄과 줄 사이 간격을 조절합니다.", "text_line_spacing")
        preset_tip(dlg_letter_spacing, "자간", "글자와 글자 사이 간격을 조절합니다.", "text_letter_spacing")
        preset_tip(dlg_char_width, "너비", "문자의 가로 비율을 조절합니다.", "text_char_width")
        preset_tip(dlg_char_height, "높이", "문자의 세로 비율을 조절합니다.", "text_char_height")
        preset_tip(dlg_writing_direction, "쓰기 방향", "개별 글꼴 프리셋에 포함할 쓰기 방향을 선택합니다.")
        preset_tip(dlg_bold, "굵게", "굵게 설정을 켜거나 끕니다.", "text_bold_toggle")
        preset_tip(dlg_italic, "기울이기", "기울이기 설정을 켜거나 끕니다.", "text_italic_toggle")
        preset_tip(dlg_strike, "취소선", "취소선 설정을 켜거나 끕니다.", "text_strike_toggle")
        preset_tip(dlg_advanced, "고급 텍스트/획 옵션", "개별 글꼴 프리셋에 문자/획 그라데이션, 2중 획, 그림자, 후광을 저장합니다.", "text_effect_gradient")
        preset_tip(dlg_align_left, "왼쪽 정렬", "텍스트를 왼쪽으로 정렬합니다.", "item_align_left")
        preset_tip(dlg_align_center, "가운데 정렬", "텍스트를 가운데로 정렬합니다.", "item_align_center")
        preset_tip(dlg_align_right, "오른쪽 정렬", "텍스트를 오른쪽으로 정렬합니다.", "item_align_right")
        for _key, _chk in include_checks.items():
            preset_tip(_chk, "프리셋 포함 옵션", "체크하면 이 항목을 개별 글꼴 프리셋에 포함합니다.")

        def refresh_rows(select_name=None):
            while rows_layout.count():
                item = rows_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            header = QWidget(rows_widget)
            h = QHBoxLayout(header); h.setContentsMargins(6, 2, 6, 2)
            h.addWidget(QLabel("사용"), 0)
            h.addWidget(QLabel("선택"), 0)
            h.addWidget(QLabel("이름"), 1)
            h.addWidget(QLabel("포함/내용"), 3)
            h.addWidget(QLabel("단축키"), 1)
            h.addWidget(QLabel("관리"), 1)
            rows_layout.addWidget(header)

            for name, preset in sorted(self.item_text_presets.items()):
                row = QWidget(rows_widget)
                row_l = QHBoxLayout(row); row_l.setContentsMargins(6, 2, 6, 2); row_l.setSpacing(6)
                chk_enabled = QCheckBox(); chk_enabled.setChecked(bool(preset.get("enabled", True)))
                btn_select = QPushButton("선택")
                name_edit = QLineEdit(name)
                summary = QLabel(self.style_summary_text(preset.get("style"), preset.get("include"))); summary.setWordWrap(True)
                key_edit = ConfirmingKeySequenceEdit(); key_edit.setKeySequence(key_sequence_from_text(str(preset.get("shortcut", "") or ""))); key_edit.setMaximumWidth(160)
                btn_update = QPushButton("수정 저장")
                btn_delete = QPushButton("삭제")
                preset_tip(chk_enabled, "프리셋 사용", "체크하면 이 개별 글꼴 프리셋을 콤보박스와 단축키에서 사용할 수 있습니다.")
                preset_tip(btn_select, "개별 프리셋 선택", "이 프리셋을 선택한 텍스트 객체에 미리보기로 적용합니다.")
                preset_tip(name_edit, "프리셋 이름", "이름을 바꾸고 Enter를 누르거나 포커스를 빼면 프리셋 이름이 변경됩니다.")
                preset_tip(summary, "프리셋 내용", "이 프리셋에 저장된 글꼴, 크기, 색상, 행간, 자간 등 스타일 요약입니다.")
                preset_tip(key_edit, "프리셋 단축키", "이 개별 글꼴 프리셋을 바로 적용할 단축키를 지정합니다.")
                preset_tip(btn_update, "프리셋 수정 저장", "현재 위쪽 편집값과 포함 옵션으로 이 개별 글꼴 프리셋을 덮어씁니다.")
                preset_tip(btn_delete, "프리셋 삭제", "이 개별 글꼴 프리셋을 삭제합니다.")

                if not chk_enabled.isChecked():
                    if self.is_light_theme():
                        row.setStyleSheet("background:#F2EDEF; color:#91888F;")
                        summary.setStyleSheet("color:#91888F;")
                        name_edit.setStyleSheet("background:#F8F3F5; color:#91888F; border:1px solid #D2CBD0;")
                        key_edit.setStyleSheet("background:#F8F3F5; color:#91888F; border:1px solid #D2CBD0;")
                    else:
                        row.setStyleSheet("background:#242424; color:#888888;")
                        summary.setStyleSheet("color:#888888;")
                        name_edit.setStyleSheet("color:#888888;")
                        key_edit.setStyleSheet("color:#888888;")

                is_selected = (selected_name["value"] == name or select_name == name)
                if is_selected:
                    if self.is_light_theme():
                        row_style = "background:#e8f1ff; border:1px solid #A85D66;"
                        child_style = "background:#ffffff; color:#202124; border:1px solid #A85D66;"
                    else:
                        row_style = "background:#31415c; border:1px solid #5b8def;"
                        child_style = "background:#2f5fa7; color:white; border:1px solid #80b4ff;"
                    row.setStyleSheet(row_style)
                    btn_select.setText("선택됨")
                    btn_select.setStyleSheet("background:#4b79c7; color:white; font-weight:bold; border:1px solid #9cc3ff;")
                    name_edit.setStyleSheet(child_style)
                    summary.setStyleSheet(child_style)
                    key_edit.setStyleSheet(child_style)
                    btn_update.setStyleSheet("background:#8A4A52; color:white;")
                    btn_delete.setStyleSheet("background:#8A4A52; color:white;")
                    selected_name["value"] = name

                row_l.addWidget(chk_enabled)
                row_l.addWidget(btn_select)
                row_l.addWidget(name_edit, 1)
                row_l.addWidget(summary, 3)
                row_l.addWidget(key_edit, 1)
                row_l.addWidget(btn_update)
                row_l.addWidget(btn_delete)
                rows_layout.addWidget(row)

                def on_select(_checked=False, n=name):
                    # 이미 선택된 프리셋을 다시 누르면 선택 해제한다.
                    if selected_name["value"] == n:
                        selected_name["value"] = None
                        if original_page_snapshot is not None and page_idx in self.data:
                            self.data[page_idx] = copy.deepcopy(original_page_snapshot)
                            if self.idx == page_idx:
                                self.ref_tab()
                                if self.cb_mode.currentIndex() == 4:
                                    self.mode_chg(4)
                                    self.reselect_text_items([int(x) for x in selected_snapshot.keys() if str(x).isdigit()])
                        refresh_rows(None)
                        self.log(f"↩️ 개별 글꼴 프리셋 선택 해제: {n}")
                        return

                    p = self.item_text_presets.get(n)
                    if not p:
                        return
                    selected_name["value"] = n
                    apply_style_to_editor(p.get("style") or self.current_style_snapshot(), p.get("include") or {})
                    preview_selected_only()
                    refresh_rows(n)
                    self.log(f"🎛️ 개별 글꼴 프리셋 선택: {n}")

                def on_enabled(v, n=name, checkbox=chk_enabled):
                    if not self.set_item_text_preset_enabled_checked(n, bool(v), parent=dialog):
                        checkbox.blockSignals(True)
                        try:
                            checkbox.setChecked(not bool(v))
                        finally:
                            checkbox.blockSignals(False)
                        return
                    self.log(f"🔘 개별 글꼴 프리셋 {'사용' if v else '미사용'}: {n}")
                    refresh_rows(selected_name["value"])

                def on_shortcut_finished(edit=key_edit, n=name, old_seq=str(preset.get("shortcut", "") or "")):
                    try:
                        clean_seq = sequence_without_confirm_keys(edit.keySequence())
                        clean_text = key_sequence_to_portable(clean_seq)
                        current_text = key_sequence_to_portable(edit.keySequence())
                        if clean_text != current_text:
                            edit.blockSignals(True)
                            try:
                                edit.setKeySequence(clean_seq)
                            finally:
                                edit.blockSignals(False)
                        seq_text = clean_text
                    except Exception:
                        seq_text = key_sequence_to_portable(edit.keySequence())
                    if self.normalize_shortcut_text(seq_text) == self.normalize_shortcut_text(old_seq):
                        return
                    if not self.set_item_text_preset_shortcut_checked(n, seq_text, parent=dialog):
                        edit.blockSignals(True)
                        try:
                            if old_seq:
                                edit.setKeySequence(key_sequence_from_text(old_seq))
                            else:
                                edit.clear()
                        finally:
                            edit.blockSignals(False)
                        return
                    self.log(f"⌨️ 개별 글꼴 프리셋 단축키 변경: {n} = {seq_text or '없음'}")
                    refresh_rows(selected_name["value"])

                def on_name_finished(edit=name_edit, old_name=name):
                    new_name = self.safe_preset_name(edit.text())
                    if new_name == old_name:
                        edit.setText(old_name); return
                    if self.item_text_preset_path(new_name).exists():
                        QMessageBox.warning(dialog, self.tr_ui("이름 변경 실패"), self.tr_ui("같은 이름의 프리셋이 이미 있습니다."))
                        edit.setText(old_name); return
                    old_path = self.item_text_preset_path(old_name)
                    new_path = self.item_text_preset_path(new_name)
                    if old_path.exists():
                        old_path.rename(new_path)
                    if selected_name["value"] == old_name:
                        selected_name["value"] = new_name
                    self.load_item_text_preset_cache()
                    refresh_rows(new_name)

                def on_update(_checked=False, n=name, label=summary):
                    p_old = self.item_text_presets.get(n) or {}
                    p = {
                        "style": current_dialog_style(),
                        "include": current_include(),
                        "enabled": bool(p_old.get("enabled", True)),
                        "shortcut": str(p_old.get("shortcut", "") or ""),
                    }
                    safe = self.save_item_text_preset_named(n, p)
                    selected_name["value"] = safe
                    label.setText(self.style_summary_text(p["style"], p["include"]))
                    self.refresh_item_text_preset_combo()
                    self.apply_shortcuts()
                    refresh_rows(safe)
                    self.log(f"💾 개별 글꼴 프리셋 수정 저장: {safe}")

                def on_delete(_checked=False, n=name):
                    ans = QMessageBox.question(dialog, self.tr_ui("개별 프리셋 삭제"), self.tr_msg(f"'{n}' 프리셋을 삭제할까요?"), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                    if ans != QMessageBox.StandardButton.Yes:
                        return
                    try:
                        self.item_text_preset_path(n).unlink(missing_ok=True)
                    except Exception:
                        pass
                    if selected_name["value"] == n:
                        selected_name["value"] = None
                    self.load_item_text_preset_cache()
                    refresh_rows()
                    self.log(f"🗑️ 개별 글꼴 프리셋 삭제: {n}")

                btn_select.clicked.connect(on_select)
                chk_enabled.toggled.connect(on_enabled)
                key_edit.editingFinished.connect(on_shortcut_finished)
                name_edit.editingFinished.connect(on_name_finished)
                btn_update.clicked.connect(on_update)
                btn_delete.clicked.connect(on_delete)

            rows_layout.addStretch()

        # ---------- bottom buttons ----------
        btn_line = QHBoxLayout()
        btn_add = QPushButton(self.tr_ui("현재 설정을 새 개별 프리셋으로 추가"), dialog)
        btn_import = QPushButton(self.tr_ui("불러오기"), dialog)
        btn_ok = QPushButton(self.tr_ui("확인"), dialog)
        btn_close = QPushButton(self.tr_ui("닫기"), dialog)
        preset_tip(btn_add, "개별 프리셋 추가", "현재 위쪽 편집값과 포함 옵션을 새 개별 글꼴 프리셋으로 저장합니다.")
        preset_tip(btn_import, "개별 프리셋 불러오기", "외부 JSON 파일에서 개별 글꼴 프리셋을 가져옵니다.")
        preset_tip(btn_ok, "확인", "개별 프리셋 관리 상태를 저장하고 창을 닫습니다. 미리보기는 원래 페이지 상태로 복구됩니다.")
        preset_tip(btn_close, "닫기", "변경사항을 저장하지 않고 창을 닫습니다. 미리보기는 원래 페이지 상태로 복구됩니다.")
        btn_line.addWidget(btn_add)
        btn_line.addWidget(btn_import)
        btn_line.addStretch()
        btn_line.addWidget(btn_ok)
        btn_line.addWidget(btn_close)
        layout.addLayout(btn_line)

        def add_current():
            name, ok = QInputDialog.getText(dialog, self.tr_ui("개별 프리셋 추가"), self.tr_ui("프리셋 이름:"))
            if not ok or not name.strip():
                return
            safe = self.safe_preset_name(name)
            if self.item_text_preset_path(safe).exists():
                ans = QMessageBox.question(dialog, self.tr_ui("덮어쓰기"), self.tr_msg(f"'{safe}' 프리셋이 이미 있습니다. 덮어쓸까요?"), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if ans != QMessageBox.StandardButton.Yes:
                    return
            preset = {
                "style": current_dialog_style(),
                "include": current_include(),
                "enabled": True,
                "shortcut": "",
            }
            self.save_item_text_preset_named(safe, preset)
            self.load_item_text_preset_cache()
            # 새로 추가는 목록에만 추가한다. 파란 선택 강조는 남기지 않는다.
            selected_name["value"] = None
            refresh_rows(None)
            self.log(f"💾 개별 글꼴 프리셋 추가: {safe}")

        def import_item_preset():
            path, _ = self.get_open_file_name_logged("import_item_preset", dialog, self.tr_ui("개별 글꼴 프리셋 불러오기"), str(self.item_text_preset_dir()), "JSON (*.json)")
            if not path:
                return
            try:
                with open(path, "r", encoding="utf-8-sig") as f:
                    raw = json.load(f)
                if isinstance(raw, dict) and "style" in raw:
                    style = self.normalize_style_dict(raw.get("style"))
                    inc = raw.get("include") or {k: True for k, _ in self.style_field_specs()}
                    inc = dict(inc or {})
                    inc.setdefault("advanced_text_options", bool(self.style_has_advanced_text_options(style)))
                else:
                    style = self.normalize_style_dict(raw)
                    inc = {**{k: True for k, _ in self.style_field_specs()}, "advanced_text_options": bool(self.style_has_advanced_text_options(style))}
            except Exception as e:
                msg_text = self.tr_ui("프리셋 JSON을 읽지 못했습니다.")
                QMessageBox.warning(dialog, self.tr_ui("불러오기 실패"), f"{msg_text}\n{e}")
                return
            default_name = Path(path).stem
            name, ok = QInputDialog.getText(dialog, self.tr_ui("프리셋 이름"), self.tr_ui("추가할 프리셋 이름:"), text=default_name)
            if not ok or not name.strip():
                return
            safe = self.safe_preset_name(name)
            preset = {"style": style, "include": inc, "enabled": True, "shortcut": ""}
            self.save_item_text_preset_named(safe, preset)
            self.load_item_text_preset_cache()
            # 불러오기는 프리셋 목록에 추가만 한다. 파란 선택 행은 남기지 않는다.
            selected_name["value"] = None
            apply_style_to_editor(style, inc)
            preview_selected_only()
            refresh_rows(None)
            self.log(f"📥 개별 글꼴 프리셋 불러오기 완료: {safe}")

        def restore_selected_preview():
            _restore_t0 = time.time()
            try:
                self.audit_boundary_event("PRESET_DIALOG_RESTORE_ENTER", dialog_key="item_text_preset", reason="restore_selected_preview", selected_count=len(selected_snapshot or {}), memory=memory_text())
            except Exception:
                pass
            # 개별 프리셋 창은 실제 적용 창이 아니므로, 나갈 때는 창을 열기 전 페이지 상태로 통째로 복구한다.
            if original_page_snapshot is not None and page_idx in self.data:
                self.data[page_idx] = copy.deepcopy(original_page_snapshot)
            else:
                self.restore_text_items_by_snapshot(page_idx, selected_snapshot)

            def _refresh_after_dialog_close():
                try:
                    if self.idx == page_idx:
                        self.ref_tab()
                        if self.cb_mode.currentIndex() == 4:
                            self.mode_chg(4)
                            self.reselect_text_items([int(x) for x in selected_snapshot.keys() if str(x).isdigit()])
                            self.update_item_preset_combo_for_selected_texts()
                finally:
                    try:
                        self.audit_boundary_event("PRESET_DIALOG_RESTORE_REFRESH_DONE", dialog_key="item_text_preset", memory=memory_text(), throttle_ms=50)
                    except Exception:
                        pass

            if self.idx == page_idx:
                QTimer.singleShot(0, _refresh_after_dialog_close)
            try:
                self.audit_boundary_event("PRESET_DIALOG_RESTORE_DONE", dialog_key="item_text_preset", elapsed_ms=int((time.time() - _restore_t0) * 1000), deferred_refresh=True, memory=memory_text())
            except Exception:
                pass

        def accept_and_save_state():
            restore_selected_preview()
            self.save_item_text_preset_state(current_dialog_style(), current_include(), selected_name["value"])
            self.load_item_text_preset_cache()
            self.log("💾 개별 글꼴 프리셋 마지막 설정 저장 완료")
            dialog.accept()

        def reject_without_state():
            restore_selected_preview()
            dialog.reject()

        btn_add.clicked.connect(add_current)
        btn_import.clicked.connect(import_item_preset)
        btn_ok.clicked.connect(accept_and_save_state)
        btn_close.clicked.connect(reject_without_state)

        apply_style_to_editor(base_style, include_default)
        refresh_color_buttons()
        refresh_rows(selected_name["value"])
        # 창을 여는 순간 ref_tab()/mode_chg()로 scene을 재조립하면
        # Qt modal exec 진입 직전 네이티브 크래시가 날 수 있다.
        # 실제 미리보기는 사용자가 값을 바꾸거나 프리셋을 선택할 때만 수행한다.
        try:
            self.audit_boundary_event("PRESET_DIALOG_BUILD_DONE", dialog_key="item_text_preset", elapsed_ms=int((time.time() - _dlg_t0) * 1000), memory=memory_text())
        except Exception:
            pass
        try:
            dialog.setUpdatesEnabled(True)
            dialog.update()
        except Exception:
            pass
        try:
            dialog.setProperty("dialog_timing_exec_enter_at", time.time())
            self.audit_boundary_event("PRESET_DIALOG_EXEC_ENTER", dialog_key="item_text_preset", memory=memory_text())
        except Exception:
            pass
        old_modal_dialog_active = bool(getattr(self, "_modal_dialog_active", False))
        old_source_compare_visible = False
        try:
            old_source_compare_visible = bool(self.source_compare_is_visible()) if hasattr(self, "source_compare_is_visible") else False
        except Exception:
            old_source_compare_visible = False
        try:
            self._modal_dialog_active = True
            if hasattr(self, "note_ui_interaction_activity"):
                self.note_ui_interaction_activity(2500)
            if hasattr(self, "_block_source_compare_sync_temporarily"):
                self._block_source_compare_sync_temporarily(2500)
            if hasattr(self, "stop_source_compare_sync_timer"):
                self.stop_source_compare_sync_timer()
        except Exception:
            pass
        try:
            self.apply_portable_spinbox_style(dialog)
        except Exception:
            pass
        try:
            result = dialog.exec()
        finally:
            try:
                self._modal_dialog_active = old_modal_dialog_active
            except Exception:
                pass
            try:
                if old_source_compare_visible and hasattr(self, "start_source_compare_sync_timer"):
                    QTimer.singleShot(220, self.start_source_compare_sync_timer)
            except Exception:
                pass
        try:
            self.audit_boundary_event("PRESET_DIALOG_EXEC_RETURN", dialog_key="item_text_preset", result=int(result), elapsed_ms=int((time.time() - float(dialog.property("dialog_timing_exec_enter_at") or time.time())) * 1000), memory=memory_text())
        except Exception:
            pass
        if result != QDialog.DialogCode.Accepted:
            restore_selected_preview()

    def set_preset_combo_to_last(self):
        if not hasattr(self, "cb_text_preset") or self._preset_loading:
            return
        self.cb_text_preset.blockSignals(True)
        try:
            self.cb_text_preset.setCurrentIndex(0)
        finally:
            self.cb_text_preset.blockSignals(False)

    def ensure_item_style_defaults_for_page(self, page_idx):
        curr = self.data.get(page_idx)
        if not curr:
            return
        style = self.current_style_snapshot()
        for item in curr.get('data', []):
            item.setdefault('font_family', style['font_family'])
            item.setdefault('font_size', style['font_size'])
            item.setdefault('stroke_width', style['stroke_width'])
            item.setdefault('text_color', style['text_color'])
            item.setdefault('stroke_color', style['stroke_color'])
            item.setdefault('align', style['align'])
            item.setdefault('line_spacing', style['line_spacing'])
            item.setdefault('letter_spacing', style['letter_spacing'])
            item.setdefault('char_width', style['char_width'])
            item.setdefault('char_height', style['char_height'])
            item.setdefault('bold', style['bold'])
            item.setdefault('italic', style['italic'])
            item.setdefault('strike', style['strike'])

    def apply_style_dict_to_data_items(self, items, style):
        style = self.normalize_style_dict(style)
        advanced = self.normalize_advanced_text_options(style) if self.style_has_advanced_text_options(style) else None
        for item in items or []:
            item.update({
                'font_family': style['font_family'],
                'font_size': style['font_size'],
                'stroke_width': style['stroke_width'],
                'text_color': style['text_color'],
                'stroke_color': style['stroke_color'],
                'align': style['align'],
                'line_spacing': style['line_spacing'],
                'letter_spacing': style['letter_spacing'],
                'char_width': style['char_width'],
                'char_height': style['char_height'],
                'bold': style['bold'],
                'italic': style['italic'],
                'strike': style['strike'],
            })
            if 'writing_direction' in style and not self.is_text_writing_direction_change_blocked(item):
                item['writing_direction'] = self.normalize_writing_direction(style.get('writing_direction'))
            if advanced is not None:
                for key in self.advanced_text_effect_fields():
                    item[key] = advanced.get(key)

    def apply_current_preset_to_data_items(self, items):
        self.apply_style_dict_to_data_items(items, self.current_style_snapshot())

    def text_style_clone_field_names(self):
        fields = [key for key, _label in self.style_field_specs()]
        fields.extend(["opacity"])
        try:
            fields.extend(list(self.advanced_text_effect_fields()))
        except Exception:
            pass
        # Text deformation/effect fields are style-like, but coordinates/rect/content are not.
        fields.extend([
            "rotation", "_transform_mode",
            "skew_x", "skew_y", "_skew_mode",
            "trap_left", "trap_right", "trap_top", "trap_bottom", "_trapezoid_mode",
            "arc_top", "arc_bottom", "arc_left", "arc_right",
            "arc_top_pos", "arc_bottom_pos", "arc_left_pos", "arc_right_pos",
            "arc_handles", "_arc_mode",
        ])
        out = []
        seen = set()
        for key in fields:
            if key not in seen:
                seen.add(key)
                out.append(key)
        return out

    def text_style_clone_default_values(self):
        defaults = {
            "opacity": 100,
            "rotation": 0,
            "_transform_mode": False,
            "skew_x": 0,
            "skew_y": 0,
            "_skew_mode": False,
            "trap_left": 0,
            "trap_right": 0,
            "trap_top": 0,
            "trap_bottom": 0,
            "_trapezoid_mode": False,
            "arc_top": 0,
            "arc_bottom": 0,
            "arc_left": 0,
            "arc_right": 0,
            "arc_top_pos": 50,
            "arc_bottom_pos": 50,
            "arc_left_pos": 50,
            "arc_right_pos": 50,
            "arc_handles": [],
            "_arc_mode": False,
        }
        try:
            defaults.update(self.default_advanced_text_options())
        except Exception:
            pass
        return defaults

    def text_style_clone_snapshot_from_data(self, data_item):
        if not isinstance(data_item, dict):
            return {}
        style = self.normalize_style_dict(data_item)
        adv = self.normalize_advanced_text_options(data_item)
        style["advanced_text_options"] = adv
        for key in self.advanced_text_effect_fields():
            style[key] = copy.deepcopy(adv.get(key))
        defaults = self.text_style_clone_default_values()
        for key in self.text_style_clone_field_names():
            if key in style:
                continue
            if key in data_item:
                style[key] = copy.deepcopy(data_item.get(key))
            elif key in defaults:
                style[key] = copy.deepcopy(defaults.get(key))
        return style

    def clear_text_style_clone_source(self, keep_tool=False):
        try:
            marker = getattr(self, "_text_style_clone_marker", None)
            if marker is not None:
                scene = marker.scene()
                if scene is not None:
                    scene.removeItem(marker)
        except Exception:
            pass
        self._text_style_clone_marker = None
        self._text_style_clone_source_id = None
        self._text_style_clone_style = None
        if not keep_tool:
            try:
                if getattr(getattr(self, "view", None), "draw_mode", None) == "text_style_clone":
                    self.set_tool(None)
            except Exception:
                pass

    def update_text_style_clone_marker(self, text_item=None):
        try:
            scene = getattr(getattr(self, "view", None), "scene", None)
            if scene is None:
                return
            if text_item is None:
                sid = str(getattr(self, "_text_style_clone_source_id", "") or "")
                for obj in list(scene.items()):
                    if isinstance(obj, TypesettingItem) and str(getattr(obj, "data", {}).get("id")) == sid:
                        text_item = obj
                        break
            if text_item is None:
                return
            try:
                rect = text_item.text_content_scene_rect() if hasattr(text_item, "text_content_scene_rect") else text_item.sceneBoundingRect()
            except Exception:
                rect = text_item.sceneBoundingRect()
            rect = QRectF(rect).adjusted(-4, -4, 4, 4)
            marker = getattr(self, "_text_style_clone_marker", None)
            if marker is None or marker.scene() is None:
                pen = QPen(QColor(0, 220, 120, 240), 2, Qt.PenStyle.DashLine)
                marker = QGraphicsRectItem(rect)
                marker.setPen(pen)
                marker.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                marker.setZValue(100000)
                try:
                    marker.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
                    marker.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
                except Exception:
                    pass
                scene.addItem(marker)
                self._text_style_clone_marker = marker
            else:
                marker.setRect(rect)
                marker.setZValue(100000)
                marker.show()
        except Exception:
            pass

    def apply_text_style_clone_to_item(self, target_data, source_style):
        if not isinstance(target_data, dict) or not isinstance(source_style, dict):
            return []
        changed = []
        defaults = self.text_style_clone_default_values()
        for key in self.text_style_clone_field_names():
            if key in ("id", "text", "translated_text", "rect", "vertices_list", "x_off", "y_off", "inner_text_x_off", "inner_text_y_off"):
                continue
            if key == "writing_direction" and self.is_text_writing_direction_change_blocked(target_data):
                continue
            if key in source_style:
                new_value = copy.deepcopy(source_style.get(key))
            else:
                new_value = copy.deepcopy(defaults.get(key))
            old_value = target_data.get(key)
            if old_value != new_value:
                target_data[key] = new_value
                changed.append(key)
        return changed

    def handle_text_style_clone_click(self, text_item):
        data_item = getattr(text_item, "data", None)
        if not isinstance(data_item, dict):
            return True
        sid = data_item.get("id")
        if not getattr(self, "_text_style_clone_style", None):
            self._text_style_clone_source_id = sid
            self._text_style_clone_style = self.text_style_clone_snapshot_from_data(data_item)
            self.update_text_style_clone_marker(text_item)
            try:
                self.log(f"🧬 스타일 복제 기준 선택: ID {sid} — 적용할 텍스트를 클릭하세요. ESC로 해제.")
            except Exception:
                pass
            return True
        if str(sid) == str(getattr(self, "_text_style_clone_source_id", "")):
            self.update_text_style_clone_marker(text_item)
            return True
        source_style = copy.deepcopy(getattr(self, "_text_style_clone_style", {}) or {})
        changed = []
        try:
            self.append_text_engine_diff_for_items("텍스트 스타일 복제", [data_item], fields=self.text_style_clone_field_names())
        except Exception:
            pass
        changed = self.apply_text_style_clone_to_item(data_item, source_style)
        if changed:
            try:
                if hasattr(self, "refresh_final_text_items_by_ids"):
                    if not self.refresh_final_text_items_by_ids([sid]):
                        self.schedule_final_text_scene_refresh(60)
                else:
                    self.schedule_final_text_scene_refresh(60)
            except Exception:
                pass
            try:
                self.finalize_text_change(ids=[sid], items=[data_item], fields=changed, reason="텍스트 스타일 복제", delay_ms=900)
            except Exception:
                pass
            try:
                self.log(f"🧬 스타일 복제 적용: ID {sid}")
            except Exception:
                pass
        return True

    def _text_engine_mode_index(self):
        try:
            return int(self.cb_mode.currentIndex())
        except Exception:
            return int(getattr(self, "last_mode", 0) or 0)

    def make_text_engine_diff_record_for_items(self, reason, items, fields=None, page_idx=None):
        page_idx = int(self.idx if page_idx is None else page_idx)
        curr = self.data.get(page_idx) or {}
        data_list = curr.get('data', []) if isinstance(curr, dict) else []
        if not hasattr(self, 'text_engine') or self.text_engine is None:
            return None
        try:
            return self.text_engine.make_diff_record_for_items(
                data_list=data_list,
                page_idx=page_idx,
                mode=self._text_engine_mode_index(),
                reason=str(reason or '텍스트 변경'),
                items=list(items or []),
                fields=list(fields or []),
            )
        except Exception:
            return None

    def append_text_engine_diff_for_items(self, reason, items, fields=None, page_idx=None):
        # QA15: 텍스트 계열 Undo는 부분 diff 최적화를 버리고 현재 페이지 text state 전체를
        # 순서대로 쌓는다. 스타일/고급 옵션/프리셋/변형 모두 같은 복원 경로를 탄다.
        try:
            return self.undo_push_text_line(str(reason or '텍스트 변경'), page_idx=page_idx if page_idx is not None else self.idx, include_masks=False)
        except Exception:
            return False

    def mark_text_engine_items_dirty(self, items, fields=None, page_idx=None):
        page_idx = int(self.idx if page_idx is None else page_idx)
        ids = []
        for item in list(items or []):
            if isinstance(item, dict):
                sid = item.get('id')
                if sid is not None:
                    ids.append(sid)
        try:
            if hasattr(self, 'text_engine') and self.text_engine is not None:
                self.text_engine.mark_dirty(page_idx, ids, list(fields or []))
            if page_idx == int(getattr(self, 'idx', 0) or 0):
                self.mark_active_page_dirty('text')
            elif hasattr(self, 'project_engine') and self.project_engine is not None:
                self.project_engine.mark_page_dirty(page_idx, 'text')
        except Exception:
            pass
        # journal/checkpoint dirty는 YSBT 저장용 dirty와 별도로 관리한다.
        try:
            pages = getattr(self, "_checkpoint_dirty_pages", None)
            if pages is None:
                pages = set()
                self._checkpoint_dirty_pages = pages
            pages.add(int(page_idx))
            kinds = getattr(self, "_checkpoint_dirty_kinds", None)
            if kinds is None:
                kinds = {}
                self._checkpoint_dirty_kinds = kinds
            kinds.setdefault(int(page_idx), set()).add("text")
        except Exception:
            pass
        return ids

    def refresh_text_engine_items(self, ids, *, page_idx=None, update_table=True, refresh_scene=True):
        page_idx = int(self.idx if page_idx is None else page_idx)
        ids = [x for x in (ids or []) if x is not None]
        if not ids or page_idx != int(getattr(self, 'idx', 0) or 0):
            return False
        if update_table:
            try:
                self.update_table_rows_for_text_ids(ids)
            except Exception:
                pass
        if refresh_scene and self.cb_mode.currentIndex() == 4:
            try:
                if not self.refresh_final_text_items_by_ids(ids):
                    self.schedule_final_text_scene_refresh(30)
            except Exception:
                self.schedule_final_text_scene_refresh(30)
        return True

    def finalize_text_change(self, ids=None, *, items=None, fields=None, page_idx=None, reason="텍스트 변경", delay_ms=1800, update_table=True, refresh_scene=True):
        """모든 텍스트 변경 루트의 공통 후처리.

        data 수정은 호출부가 이미 끝낸 뒤 들어온다고 보고,
        여기서는 텍스트 엔진 dirty, 현재 화면 부분 갱신, page journal 체크포인트 예약만 처리한다.
        ref_tab()/mode_chg(4)는 직접 호출하지 않는다.
        """
        page_idx = int(self.idx if page_idx is None else page_idx)
        ids = [x for x in (ids or []) if x is not None]
        if items:
            try:
                ids = self.mark_text_engine_items_dirty(items, fields=fields, page_idx=page_idx)
            except Exception:
                ids = ids or []
        else:
            try:
                if hasattr(self, 'text_engine') and self.text_engine is not None:
                    self.text_engine.mark_dirty(page_idx, ids, list(fields or []))
                if page_idx == int(getattr(self, 'idx', 0) or 0):
                    self.mark_active_page_dirty('text')
                elif hasattr(self, 'project_engine') and self.project_engine is not None:
                    self.project_engine.mark_page_dirty(page_idx, 'text')
                pages = getattr(self, "_checkpoint_dirty_pages", None)
                if pages is None:
                    pages = set()
                    self._checkpoint_dirty_pages = pages
                pages.add(int(page_idx))
                kinds = getattr(self, "_checkpoint_dirty_kinds", None)
                if kinds is None:
                    kinds = {}
                    self._checkpoint_dirty_kinds = kinds
                kinds.setdefault(int(page_idx), set()).add("text")
            except Exception:
                pass

        if page_idx == int(getattr(self, 'idx', 0) or 0):
            try:
                if ids:
                    self.refresh_text_engine_items(ids, page_idx=page_idx, update_table=update_table, refresh_scene=refresh_scene)
                elif refresh_scene and self.cb_mode.currentIndex() == 4:
                    self.schedule_final_text_scene_refresh(80)
            except Exception:
                try:
                    if refresh_scene:
                        self.schedule_final_text_scene_refresh(80)
                except Exception:
                    pass
            try:
                self.schedule_deferred_auto_save_project(delay_ms)
            except Exception:
                try:
                    self.auto_save_project()
                except Exception:
                    pass
        else:
            try:
                # 다른 페이지도 복구 대상 journal에 포함해야 하므로 타이머는 현재 페이지에서 한 번 예약한다.
                self.schedule_deferred_auto_save_project(delay_ms)
            except Exception:
                pass
        return ids

    def update_table_rows_for_text_ids(self, ids):
        if not hasattr(self, 'tab'):
            return False
        ids = {str(x) for x in (ids or []) if x is not None}
        if not ids:
            return False
        curr = self.data.get(self.idx) or {}
        data = curr.get('data', []) if isinstance(curr, dict) else []
        by_id = {str(d.get('id')): d for d in data if isinstance(d, dict)}
        changed = False
        old_lock = getattr(self, '_table_check_lock', False)
        self._table_check_lock = True
        try:
            self.tab.blockSignals(True)
            for row in range(1, self.tab.rowCount()):
                id_item = self.tab.item(row, 0)
                if not id_item:
                    continue
                sid = id_item.text().strip()
                if sid not in ids or sid not in by_id:
                    continue
                d = by_id[sid]
                try:
                    self.sanitize_text_data_object_prefixes(d)
                except Exception:
                    pass
                text_value = str(d.get('text', '') or '')
                trans_value = str(d.get('translated_text', '') or '')
                item2 = self.tab.item(row, 2)
                item3 = self.tab.item(row, 3)
                if item2 is None:
                    item2 = QTableWidgetItem()
                    self.tab.setItem(row, 2, item2)
                if item3 is None:
                    item3 = QTableWidgetItem()
                    self.tab.setItem(row, 3, item3)
                display_trans = ("[객체] " + (trans_value or str(d.get('object_source_text', '') or ''))) if d.get('rasterized_text') else trans_value
                if item2.text() != text_value:
                    item2.setText(text_value)
                    changed = True
                if item3.text() != display_trans:
                    item3.setText(display_trans)
                    changed = True
                item2.setData(Qt.ItemDataRole.UserRole, text_value)
                item3.setData(Qt.ItemDataRole.UserRole, trans_value)
                try:
                    self.set_table_row_visual(row, bool(d.get('use_inpaint', True)))
                except Exception:
                    pass
        finally:
            try:
                self.tab.blockSignals(False)
            except Exception:
                pass
            self._table_check_lock = old_lock
        return changed

    def apply_current_preset_to_page(self, page_idx, refresh=False):
        curr = self.data.get(page_idx)
        if not curr:
            self.log("⚠️ 현재 페이지가 없어 프리셋 페이지 적용을 건너뜁니다.")
            return 0
        targets = [x for x in curr.get('data', []) if x.get('use_inpaint', True)]
        if targets:
            self.append_text_engine_diff_for_items("현재 페이지 글꼴 프리셋 적용", targets, fields=list(self.current_style_snapshot().keys()), page_idx=page_idx)
        self.apply_current_preset_to_data_items(targets)
        ids = self.finalize_text_change(
            items=targets,
            fields=list(self.current_style_snapshot().keys()),
            page_idx=page_idx,
            reason="현재 페이지 글꼴 프리셋 적용",
            delay_ms=1800,
            refresh_scene=bool(refresh),
        )
        self.log(f"🎛️ 현재 페이지 프리셋 적용: {len(targets)}개")
        # 현재 페이지 프리셋 적용은 Undo 경계가 아니라 일반 Undo 스택에 포함한다.
        return len(targets)

    def apply_current_preset_to_all_pages(self):
        total = 0
        touched_current = False
        undo_record = self.make_project_undo_record("전체 페이지 글꼴 프리셋 적용", full_project=True)

        for i in range(len(self.paths)):
            curr = self.data.get(i)
            if not curr:
                continue
            targets = [x for x in curr.get('data', []) if x.get('use_inpaint', True)]
            self.apply_current_preset_to_data_items(targets)
            if targets:
                self.mark_text_engine_items_dirty(targets, fields=list(self.current_style_snapshot().keys()), page_idx=i)
            total += len(targets)
            if i == self.idx:
                touched_current = True

        if touched_current and self.idx in self.data:
            try:
                current_targets = [x for x in (self.data.get(self.idx) or {}).get('data', []) if x.get('use_inpaint', True)]
                current_ids = [x.get('id') for x in current_targets if isinstance(x, dict)]
                self.refresh_text_engine_items(current_ids, page_idx=self.idx)
            except Exception:
                self.schedule_final_text_scene_refresh(80)

        try:
            self.schedule_deferred_auto_save_project(1800)
        except Exception:
            self.auto_save_project()
        if total:
            self.undo_push_project(undo_record)
            self.log(f"🎛️ 전체 페이지 프리셋 적용: {total}개")
            # 전체 페이지 프리셋 적용은 Undo 경계가 아니라 일반 Undo 스택에 포함한다.
        else:
            self.log("⚠️ 적용할 페이지/텍스트가 없어 전체 프리셋 적용을 건너뜁니다.")

    def auto_target_items_for_page(self, page_idx):
        curr = self.data.get(page_idx)
        if not curr:
            return []
        return [x for x in curr.get('data', []) if x.get('use_inpaint', True)]

    def item_layout_text(self, item):
        text = str(item.get('translated_text', '') or '')
        if not text.strip():
            text = str(item.get('text', '') or '')
        return text

    def ensure_item_style_for_auto(self, item):
        style = self.current_style_snapshot()
        item.setdefault('font_family', style['font_family'])
        item.setdefault('font_size', style['font_size'])
        item.setdefault('stroke_width', style['stroke_width'])
        item.setdefault('text_color', style['text_color'])
        item.setdefault('stroke_color', style['stroke_color'])
        item.setdefault('align', style['align'])
        item.setdefault('writing_direction', self.current_default_writing_direction())

    def auto_wrap_lines_for_metrics(self, text, fm, max_w, protect_short_tokens=True):
        """
        QFontMetrics 기준으로 줄바꿈 결과를 계산한다.

        현재 규칙:
        - 구형 고정 글자 수 보호 규칙은 쓰지 않는다.
        - 공백 없는 단일 덩어리는 korean_linebreak_rules의 3글자 보존 기준만 따른다.
        - 긴 덩어리는 보호 단위/장식 특문 분리 규칙을 거쳐 폭 기준으로 나눈다.
        """
        text = str(text or '').replace('\r\n', '\n').replace('\r', '\n')
        max_w = max(1, int(max_w))

        try:
            protect_len = max(1, int(getattr(ko_linebreak_rules, 'SHORT_WORD_PRESERVE_LEN_MAX', 3) or 3))
        except Exception:
            protect_len = 3
        try:
            no_split_len = max(1, int(getattr(ko_linebreak_rules, 'NO_SPLIT_COMPACT_LEN_MAX', protect_len) or protect_len))
        except Exception:
            no_split_len = protect_len

        compact_len = ko_linebreak_rules.compact_len(text)
        has_spacing = any(ch.isspace() for ch in text.strip())
        if protect_short_tokens and compact_len <= no_split_len and not has_spacing:
            return [text.replace('\n', '').strip()]

        def split_units(paragraph):
            units = []
            buf = ''
            for ch in paragraph:
                if ch.isspace():
                    if buf:
                        units.append(buf)
                        buf = ''
                    if ch == ' ':
                        units.append(' ')
                else:
                    buf += ch
            if buf:
                units.append(buf)
            return units

        def append_line(lines, current):
            if current or not lines:
                lines.append(current.rstrip())

        def unit_visual_len(value):
            try:
                return int(ko_linebreak_rules.visual_len(value))
            except Exception:
                return len(str(value or ''))

        def unit_width(value):
            try:
                return float(fm.horizontalAdvance(str(value or '')))
            except Exception:
                return 0.0

        def break_long_unit(unit, current, lines):
            # 긴 덩어리는 3글자 보존/보호 단위 규칙을 거쳐 폭 기준으로 나눈다.
            try:
                pieces = ko_linebreak_rules.split_token_by_width(
                    unit,
                    max_w,
                    unit_width,
                    max_visual_part_len=max(protect_len, ko_linebreak_rules.SPLIT_MIN_PART_LEN),
                )
            except Exception:
                pieces = list(str(unit or ''))
            for piece in pieces or [unit]:
                piece = str(piece or '')
                if not piece:
                    continue
                trial = current + piece
                if current and fm.horizontalAdvance(trial) > max_w:
                    append_line(lines, current)
                    current = ''

                # 보호 단위보다 긴 조각이 아직도 폭을 넘는 경우만 최후의 글자 단위 분해를 허용한다.
                if not current and fm.horizontalAdvance(piece) > max_w and unit_visual_len(piece) > protect_len:
                    for ch in piece:
                        trial_ch = current + ch
                        if current and fm.horizontalAdvance(trial_ch) > max_w:
                            append_line(lines, current)
                            current = ch
                        else:
                            current = trial_ch
                else:
                    current = current + piece if current else piece
            return current

        result = []
        for para in text.split('\n'):
            if para == '':
                result.append('')
                continue

            lines = []
            current = ''
            for unit in split_units(para):
                if unit == ' ':
                    # 줄 첫머리 공백은 버린다.
                    if current:
                        trial = current + unit
                        if fm.horizontalAdvance(trial) <= max_w:
                            current = trial
                    continue

                unit_len = unit_visual_len(unit)
                trial = current + unit

                if fm.horizontalAdvance(trial) <= max_w:
                    current = trial
                    continue

                if protect_short_tokens and unit_len <= protect_len:
                    # 3글자 이하 완성 어절은 내부에서 끊지 않는다.
                    if current:
                        append_line(lines, current)
                    current = unit
                else:
                    current = break_long_unit(unit, current, lines)

            append_line(lines, current)
            result.extend(lines)

        return result or ['']

    def auto_measure_text_block(self, text, family, size, max_w, stroke=0):
        font = QFont(family)
        font.setPixelSize(int(size))
        fm = QFontMetrics(font)
        lines = self.auto_wrap_lines_for_metrics(text, fm, max_w)

        max_line_w = 0
        for line in lines:
            max_line_w = max(max_line_w, fm.horizontalAdvance(line))

        # lineSpacing이 실제 줄 간격에 더 가까워서 height()보다 안정적이다.
        total_h = fm.lineSpacing() * max(1, len(lines)) + int(stroke) * 2
        total_w = max_line_w + int(stroke) * 2
        return total_w, total_h, lines

    def _rect_from_vertices_like(self, vertices):
        try:
            pts = []
            for v in vertices or []:
                if isinstance(v, dict):
                    x = int(round(float(v.get('x', 0))))
                    y = int(round(float(v.get('y', 0))))
                else:
                    x = int(round(float(v[0])))
                    y = int(round(float(v[1])))
                pts.append((x, y))
            if not pts:
                return None
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            x1, x2 = min(xs), max(xs)
            y1, y2 = min(ys), max(ys)
            return [x1, y1, max(1, x2 - x1), max(1, y2 - y1)]
        except Exception:
            return None

    def _normalize_ocr_piece(self, piece):
        if not isinstance(piece, dict):
            return None

        text = str(piece.get('text') or piece.get('inferText') or piece.get('label') or '').strip()
        rect = None
        if piece.get('rect') is not None:
            try:
                r = piece.get('rect')
                rect = [int(round(float(r[0]))), int(round(float(r[1]))), int(round(float(r[2]))), int(round(float(r[3])))]
            except Exception:
                rect = None
        if rect is None:
            if isinstance(piece.get('boundingPoly'), dict):
                rect = self._rect_from_vertices_like(piece.get('boundingPoly', {}).get('vertices'))
            elif piece.get('vertices') is not None:
                rect = self._rect_from_vertices_like(piece.get('vertices'))

        if not rect:
            return None

        x, y, w, h = rect
        compact_text = ''.join(ch for ch in text if not ch.isspace())
        try:
            char_count = int(piece.get('char_count') or len(compact_text) or 1)
        except Exception:
            char_count = max(1, len(compact_text))
        return {
            'text': text,
            'char_count': max(1, char_count),
            'rect': [x, y, w, h],
            'cx': x + w / 2.0,
            'cy': y + h / 2.0,
            'w': w,
            'h': h,
            'area': max(1, w * h),
            'source_provider': str(piece.get('source_provider', '') or piece.get('source', '') or ''),
            'locale': str(piece.get('locale', '') or ''),
        }

    def _collect_item_ocr_pieces(self, item):
        """분석 결과에 포함돼 있을 수 있는 OCR 조각들을 최대한 수집한다."""
        pieces = []
        for key in ['ocr_items', 'raw_items', 'source_items', 'children', 'segments', 'parts', 'items', 'fragments']:
            val = item.get(key)
            if isinstance(val, list):
                for p in val:
                    npiece = self._normalize_ocr_piece(p)
                    if npiece:
                        pieces.append(npiece)
        dedup = []
        seen = set()
        for p in pieces:
            sig = (tuple(p['rect']), p['text'])
            if sig in seen:
                continue
            seen.add(sig)
            dedup.append(p)
        return dedup

    def estimate_source_font_size_from_ocr_coords(self, item):
        """CLOVA OCR 조각 좌표를 이용해 원문 글자 크기를 추정한다.

        이전 방식의 문제:
        - 그룹 전체 rect 높이 / 전체 글자 수로 상한을 걸면,
          여러 세로열이 한 말풍선에 들어간 경우 글자 크기가 과하게 작아진다.
        - fallback/mask가 작은 값으로 나오면 OCR 좌표 추정값까지 같이 깎였다.

        새 방식:
        - OCR 조각 자체의 긴 방향/글자수 + 짧은 방향 폭을 우선 사용한다.
        - 글자 단위 OCR 조각이 있을 때만 중심 간격을 보조로 사용한다.
        - 그룹 전체 글자수 기반 전역 cap은 사용하지 않는다.
        """
        pieces = self._collect_item_ocr_pieces(item)
        # Manga OCR은 detector 영역 crop을 읽는 인식 OCR이라, 이 좌표를 글자 크기 추정에 쓰지 않는다.
        pieces = [p for p in pieces if str(p.get('source_provider', '') or '').lower() != 'local_manga_ocr']
        if not pieces:
            return None

        rect = item.get('rect') or [0, 0, 1, 1]
        try:
            box_w = max(1, int(rect[2]))
            box_h = max(1, int(rect[3]))
        except Exception:
            box_w, box_h = 1, 1

        vertical = box_h >= box_w

        size_vals = [p['h'] if vertical else p['w'] for p in pieces]
        area_vals = [p['area'] for p in pieces]
        med_size = float(np.median(size_vals)) if size_vals else 0.0
        med_area = float(np.median(area_vals)) if area_vals else 0.0

        # 후리가나/첨자 후보는 이미 엔진에서 분리하지만,
        # 기존 프로젝트나 예외 케이스를 위해 한 번 더 방어한다.
        main_pieces = [
            p for p in pieces
            if (p['h'] if vertical else p['w']) >= max(3.0, med_size * 0.55)
            and p['area'] >= max(4.0, med_area * 0.30)
        ] or pieces

        piece_sizes = []
        for p in main_pieces:
            axis_len = float(p['h'] if vertical else p['w'])
            cross_len = float(p['w'] if vertical else p['h'])
            char_count = max(1, int(p['char_count']))

            provider = str(p.get('source_provider', '') or '').lower()
            if char_count <= 1:
                # 글자 단위로 잡힌 경우: 짧은 방향 폭이 글자 크기에 가깝다.
                if provider == 'google_vision':
                    score = max(cross_len * 1.00, axis_len * 0.80)
                else:
                    score = max(cross_len * 0.95, axis_len * 0.85)
            else:
                # 단어/문장 덩어리로 잡힌 경우:
                # 긴 방향/글자수는 글자 피치, 짧은 방향은 실제 획 폭에 가깝다.
                pitch = axis_len / char_count
                if provider == 'google_vision':
                    # Google Vision은 단어/행 단위 박스가 CLOVA보다 넓게 잡히는 경우가 있어
                    # 짧은 방향 폭을 조금 더 신뢰해 원문 글자 크기 추정이 과소평가되지 않게 한다.
                    score = max(pitch * 1.05, cross_len * 1.02)
                else:
                    score = max(pitch * 1.08, cross_len * 0.88)

            piece_sizes.append(score)

        if not piece_sizes:
            return None

        piece_est = float(np.median(piece_sizes))

        # 글자 단위 OCR 조각이 여러 개 있을 때만 중심 간격을 보조로 사용한다.
        gap_est = None
        single_pieces = [p for p in main_pieces if int(p.get('char_count', 1)) == 1]
        if len(single_pieces) >= 2:
            if vertical:
                base_axis = float(np.median([p['cx'] for p in single_pieces]))
                aligned = [p for p in single_pieces if abs(p['cx'] - base_axis) <= max(8.0, piece_est * 0.75)]
                aligned = aligned if len(aligned) >= 2 else single_pieces
                ordered = sorted(aligned, key=lambda p: p['cy'])
                gaps = [b['cy'] - a['cy'] for a, b in zip(ordered, ordered[1:]) if (b['cy'] - a['cy']) > 2]
            else:
                base_axis = float(np.median([p['cy'] for p in single_pieces]))
                aligned = [p for p in single_pieces if abs(p['cy'] - base_axis) <= max(8.0, piece_est * 0.75)]
                aligned = aligned if len(aligned) >= 2 else single_pieces
                ordered = sorted(aligned, key=lambda p: p['cx'])
                gaps = [b['cx'] - a['cx'] for a, b in zip(ordered, ordered[1:]) if (b['cx'] - a['cx']) > 2]

            if gaps:
                candidate = float(np.median(gaps)) * 0.96
                # 중심 간격이 조각 추정값과 너무 다르면, 줄/열 간격을 잘못 잡은 것으로 보고 버린다.
                if piece_est * 0.55 <= candidate <= piece_est * 1.80:
                    gap_est = candidate

        if gap_est is not None:
            est = (piece_est + gap_est) / 2.0
        else:
            est = piece_est

        # 아주 극단적인 값만 말풍선 크기로 제한한다.
        est = min(est, max(8.0, box_h * 0.90, box_w * 0.90))
        return max(5, int(round(est)))

    def estimate_source_font_size_from_mask(self, item, page_idx=None):
        """텍스트 마스크 연결요소로 폰트 크기 보정값을 얻는다."""
        if page_idx is None:
            page_idx = self.idx

        curr = self.data.get(page_idx)
        if not curr:
            return None

        mask = curr.get('mask_merge')
        if mask is None or not isinstance(mask, np.ndarray):
            return None

        rect = item.get('rect')
        if not rect or len(rect) < 4:
            return None

        try:
            x, y, w, h = [int(v) for v in rect[:4]]
        except Exception:
            return None

        if mask.ndim == 3:
            gray = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
        else:
            gray = mask.copy()

        mh, mw = gray.shape[:2]
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(mw, x + max(1, w))
        y2 = min(mh, y + max(1, h))
        if x2 <= x1 or y2 <= y1:
            return None

        crop = gray[y1:y2, x1:x2]
        if crop.size == 0:
            return None

        _, bw = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY)
        if int(np.count_nonzero(bw)) <= 0:
            return None

        num, labels, stats, cent = cv2.connectedComponentsWithStats(bw, 8)
        heights = []
        crop_area = max(1, crop.shape[0] * crop.shape[1])
        min_area = max(3, int(crop_area * 0.0003))

        for i in range(1, num):
            ww = int(stats[i, cv2.CC_STAT_WIDTH])
            hh = int(stats[i, cv2.CC_STAT_HEIGHT])
            aa = int(stats[i, cv2.CC_STAT_AREA])
            if aa < min_area or hh < 3 or ww < 1:
                continue
            heights.append(hh)

        if not heights:
            return None

        est = float(np.median(heights)) * 1.04
        try:
            box_h = max(1, int(rect[3]))
            est = min(est, box_h * 0.75)
        except Exception:
            pass
        return max(5, int(round(est)))

    def estimate_source_font_size_fallback(self, item):
        """OCR 박스와 원문 글자 수로 최후 보정값을 추정한다."""
        rect = item.get('rect')
        if not rect or len(rect) < 4:
            return None

        source_text = str(item.get('text', '') or '')
        if not source_text.strip():
            return None

        try:
            box_w = max(1, int(rect[2]))
            box_h = max(1, int(rect[3]))
        except Exception:
            return None

        compact_len = max(1, len(''.join(ch for ch in source_text if not ch.isspace())))
        lines = [line.strip() for line in source_text.replace('\r\n', '\n').replace('\r', '\n').split('\n') if line.strip()]
        line_count = max(1, len(lines))
        vertical = box_h >= box_w

        height_based = (box_h / line_count) * 0.64
        density_based = ((box_w * box_h) / compact_len) ** 0.5 * 0.88

        try:
            short_len_for_density = max(1, int(getattr(ko_linebreak_rules, 'NO_SPLIT_COMPACT_LEN_MAX', 3) or 3))
        except Exception:
            short_len_for_density = 3
        if compact_len <= short_len_for_density:
            density_based *= 0.85

        # 여러 세로열이 한 그룹에 들어간 경우 box_h / 전체 글자 수는 너무 작아진다.
        # fallback에서는 높이/밀도만 사용하고, 전체 글자 수 기반 긴축 cap은 걸지 않는다.
        est = min(height_based, density_based)
        return max(5, int(round(est)))

    def _normalize_ocr_lang_for_layout(self, value):
        """텍스트 자동화에 쓰는 OCR 언어 값을 en/ja/ko/zh 중 하나로 정규화한다."""
        lang = str(value or '').strip().lower()
        aliases = {
            'jp': 'ja', 'jpn': 'ja', 'japanese': 'ja', '일본어': 'ja',
            'en-us': 'en', 'en-gb': 'en', 'eng': 'en', 'english': 'en', '영어': 'en',
            'kr': 'ko', 'kor': 'ko', 'korean': 'ko', '한국어': 'ko',
            'cn': 'zh', 'chi': 'zh', 'zho': 'zh', 'chinese': 'zh', '중국어': 'zh',
            'zh-cn': 'zh', 'zh-tw': 'zh', 'zh-hans': 'zh', 'zh-hant': 'zh',
        }
        return aliases.get(lang, lang if lang in ('en', 'ja', 'ko', 'zh') else '')

    def current_ocr_language_for_layout(self):
        """현재 API 설정의 OCR 언어를 자동 조판 기본값으로 가져온다."""
        try:
            provider = str(getattr(Config, 'OCR_PROVIDER', 'clova') or 'clova').strip().lower()
            if provider == 'google_vision':
                return self._normalize_ocr_lang_for_layout(getattr(Config, 'GOOGLE_VISION_OCR_LANGUAGE', 'en')) or 'en'
            return self._normalize_ocr_lang_for_layout(getattr(Config, 'CLOVA_OCR_LANGUAGE', 'ja')) or 'ja'
        except Exception:
            return 'ja'

    def item_ocr_language_for_layout(self, item):
        """분석 당시 저장된 OCR 언어를 우선 사용하고, 없으면 조각/현재 설정으로 보완한다."""
        if not isinstance(item, dict):
            return self.current_ocr_language_for_layout()

        for key in ('ocr_lang', 'ocr_language', 'source_lang'):
            lang = self._normalize_ocr_lang_for_layout(item.get(key))
            if lang:
                return lang

        # 구버전 프로젝트 호환: OCR 조각의 locale/source_provider로 최대한 추정한다.
        locale_votes = []
        provider_votes = []
        for list_key in ('ocr_items', 'ocr_items_all', 'raw_items', 'source_items', 'children', 'segments', 'parts', 'items'):
            val = item.get(list_key)
            if not isinstance(val, list):
                continue
            for piece in val:
                if not isinstance(piece, dict):
                    continue
                lang = self._normalize_ocr_lang_for_layout(piece.get('locale') or piece.get('language') or piece.get('lang'))
                if lang:
                    locale_votes.append(lang)
                provider = str(piece.get('source_provider', '') or piece.get('source', '') or '').lower()
                if provider:
                    provider_votes.append(provider)
        if locale_votes:
            try:
                return max(set(locale_votes), key=locale_votes.count)
            except Exception:
                return locale_votes[0]

        text_sample = f"{item.get('text', '')}\n{item.get('translated_text', '')}"
        if re.search(r'[A-Za-z]', text_sample) and not re.search(r'[가-힣ぁ-ゖァ-ヺ一-龯]', text_sample):
            return 'en'
        if re.search(r'[가-힣]', text_sample):
            return 'ko'

        return self.current_ocr_language_for_layout()

    def current_translation_target_language_for_layout(self):
        """번역 대상 언어를 자동 조판의 1순위 출력 언어로 사용한다."""
        try:
            lang = getattr(getattr(self, "api_settings", None), "translation_target_language", None)
            if not lang:
                lang = getattr(Config, "TRANSLATION_TARGET_LANGUAGE", "ko")
            return self._normalize_ocr_lang_for_layout(lang) or "ko"
        except Exception:
            return "ko"

    def detect_text_language_for_layout(self, text):
        """번역문 내용이 명백히 다른 문자권이면 출력 언어 판정을 보정한다."""
        sample = str(text or "")
        if not sample.strip():
            return ""
        # 공백/숫자/기호를 제외한 문자권 표본으로 판정한다.
        hangul = len(re.findall(r'[가-힣]', sample))
        kana = len(re.findall(r'[ぁ-ゖァ-ヺ]', sample))
        cjk = len(re.findall(r'[一-龯]', sample))
        alpha = len(re.findall(r'[A-Za-z]', sample))
        letters = max(1, hangul + kana + cjk + alpha)
        if hangul / letters >= 0.25 or hangul >= 2:
            return "ko"
        if (kana + cjk) / letters >= 0.45 and (kana + cjk) >= 2:
            return "ja"
        if alpha / letters >= 0.60 and alpha >= 2:
            return "en"
        return ""

    def item_output_language_for_layout(self, item):
        """OCR 언어가 아니라 최종 출력/번역문 언어를 자동 조정 기준으로 고른다."""
        target = self.current_translation_target_language_for_layout()
        if not isinstance(item, dict):
            return target or "ko"
        text_key, text_value = self._auto_layout_text_key_and_value(item)
        detected = self.detect_text_language_for_layout(text_value)
        # 명백한 문자권은 목표 언어보다 우선한다. 짧은 OK/AI/... 같은 애매한 텍스트는 목표 언어를 유지한다.
        if detected:
            return detected
        return target or self.item_ocr_language_for_layout(item) or "ko"


    def _auto_layout_text_key_and_value(self, item):
        """자동 조판 대상 텍스트 키를 고른다. 번역문이 있으면 번역문, 없으면 원문을 사용한다."""
        translated = str(item.get('translated_text', '') or '')
        if translated.strip():
            return 'translated_text', translated
        source = str(item.get('text', '') or '')
        return 'text', source

    def is_manga_ocr_layout_item(self, item):
        """Manga OCR 결과인지 판정한다.

        Manga OCR은 글자/단어 좌표를 주는 OCR이 아니라, detector 영역 crop을 읽어
        문자열만 돌려주는 인식 전용 OCR에 가깝다. 따라서 일반 일본어 OCR 좌표 기반
        자동 크기 추정으로 보내면 detector 영역 폭/높이를 글자 크기로 오해할 수 있다.
        """
        if not isinstance(item, dict):
            return False
        if str(item.get('ocr_engine', '') or '').lower() == 'manga_ocr':
            return True
        provider_keys = (
            'source_provider', 'provider', 'ocr_provider', 'source', 'engine',
        )
        for key in provider_keys:
            if str(item.get(key, '') or '').lower() == 'local_manga_ocr':
                return True
        for list_key in ('ocr_items', 'ocr_items_all', 'raw_items', 'source_items', 'children', 'segments', 'parts', 'items'):
            val = item.get(list_key)
            if not isinstance(val, list):
                continue
            for piece in val:
                if not isinstance(piece, dict):
                    continue
                provider = str(piece.get('source_provider', '') or piece.get('source', '') or piece.get('provider', '') or '').lower()
                if provider == 'local_manga_ocr':
                    return True
        return False

    def _wrap_manga_translation_lines(self, text, fm, max_w, letter_spacing=0):
        """Manga OCR 전용 번역문 줄내림.

        - 공백 기준으로 재조립한다.
        - 긴 토큰은 억지로 글자 단위 분해하지 않는다.
        - 짧은 조사/단어들은 가능한 만큼 같은 줄에 붙이고, 넘치면 다음 줄로 내린다.
        - Manga OCR 영역은 세로로 긴 경우가 많으므로 폭보다 하단 초과 방지를 우선한다.
        """
        text = re.sub(r'\s+', ' ', str(text or '').replace('\r\n', '\n').replace('\r', '\n').replace('\n', ' ')).strip()
        if not text:
            return ['']
        max_w = max(1, int(max_w))
        tokens = [t for t in text.split(' ') if t]
        if not tokens:
            return [text]

        def compact_len(s):
            return len(''.join(ch for ch in str(s or '') if not ch.isspace()))

        def width(s):
            return self._text_advance_with_letter_spacing(s, fm, letter_spacing)

        try:
            preserve_len = max(1, int(getattr(ko_linebreak_rules, 'SHORT_WORD_PRESERVE_LEN_MAX', 3) or 3))
        except Exception:
            preserve_len = 3

        lines = []
        current = ''
        for token in tokens:
            if not current:
                current = token
                continue

            trial = current + ' ' + token
            # 짧은 묶음은 폭이 조금 넘어도 한 줄로 둔다. 너무 잦은 줄내림 방지.
            if compact_len(trial) <= preserve_len:
                current = trial
                continue

            if width(trial) <= max_w:
                current = trial
                continue

            lines.append(current.rstrip())
            current = token

        if current:
            lines.append(current.rstrip())
        return lines or [text]

    def _fit_manga_ocr_text_for_item(self, item, page_idx=None):
        """Manga OCR 전용 자동 줄내림 + 자동 크기 조정.

        Manga OCR은 일본어 전용 인식 OCR이지만 좌표는 detector 영역 단위에 가깝다.
        따라서 원문 좌표 기반 글자 크기 추정 대신, 실제 출력될 번역문을 기준으로
        위에서 아래로 배치하고 OCR 영역의 하단을 넘지 않을 때까지 font_size를 줄인다.
        """
        rect = item.get('rect')
        if not rect or len(rect) < 4:
            return False

        # 번역문 기준이 원칙. 번역문이 아직 없으면 안전하게 원문을 fallback으로 사용한다.
        text_key = 'translated_text' if str(item.get('translated_text', '') or '').strip() else 'text'
        original = str(item.get(text_key, '') or '')
        if not original.strip():
            return False

        source_text = self.normalize_auto_wrap_source_text_for_lang(original, lang='ko')
        if not source_text.strip():
            return False

        self.ensure_item_style_for_auto(item)

        # OCR rect가 페이지 가장자리에서 지나치게 좁게 잘린 경우,
        # 작은 박스 안에 우겨넣지 말고 안쪽 방향으로 계산 박스를 먼저 넓힌다.
        # 최종 충돌은 뒤의 전역 겹침 보정/최종 재검사가 처리한다.
        try:
            if lang == 'ko' and self.text_item_writing_direction(item) != 'vertical':
                expanded_rect, expand_info = self._auto_layout_expand_narrow_edge_fit_rect_for_item(
                    item, rect, source_text, page_idx=page_idx
                )
                if expanded_rect and list(expanded_rect) != list(self._auto_layout_normalize_rect_candidate(rect, 'rect') or rect):
                    old_rect_for_expand = self._auto_layout_normalize_rect_candidate(item.get('rect'), 'rect') if isinstance(item, dict) else None
                    item.setdefault('auto_layout_narrow_edge_original_rect', list(old_rect_for_expand or rect))
                    # OCR rect는 불변. 좁은 가장자리 보정은 계산용 rect에만 적용한다.
                    item['auto_layout_fit_rect'] = list(expanded_rect)
                    item['auto_layout_fit_box_source'] = 'narrow_edge_expand'
                    item['auto_layout_narrow_edge_expanded'] = True
                    item['auto_layout_narrow_edge_expand_info'] = dict(expand_info or {})
                    rect = list(expanded_rect)
                    try:
                        self._auto_adjust_diag(
                            'TEXT_AUTO_ADJUST_NARROW_EDGE_FIT_RECT_EXPANDED',
                            item,
                            ocr_rect_locked=True,
                            ocr_rect=list(old_rect_for_expand or []),
                            effective_rect=list(expanded_rect),
                            **(expand_info or {}),
                        )
                    except Exception:
                        pass
        except Exception as exc:
            try:
                self._auto_adjust_diag('TEXT_AUTO_ADJUST_NARROW_EDGE_FIT_RECT_EXPAND_ERROR', item, error=repr(exc))
            except Exception:
                pass

        try:
            box_w = max(1, int(rect[2]))
            box_h = max(1, int(rect[3]))
        except Exception as exc:
            self._auto_adjust_diag('TEXT_AUTO_ADJUST_SKIP', item, reason='bad_rect', rect=rect, error=repr(exc))
            return False

        try:
            family = item.get('font_family') or self.cb_font.currentFont().family()
        except Exception:
            family = item.get('font_family') or 'Arial'
        try:
            start_size = int(item.get('font_size', self.sb_font_size.value()) or self.sb_font_size.value())
        except Exception:
            start_size = 24
        try:
            stroke = int(item.get('stroke_width', 0) or 0)
        except Exception:
            stroke = 0

        min_size = 5
        # 처음엔 넉넉하게 잡고 아래로 넘치지 않을 때까지 줄인다.
        max_size_by_box = int(max(box_w * 0.95, box_h * 0.28, start_size * 1.70))
        max_size = max(min_size, min(260, max(start_size, max_size_by_box)))
        # 자동 맞춤은 OCR 박스 외곽선을 기준으로 한다.
        # 글자 외곽선(stroke)은 렌더 측정값에는 포함하지만, 맞춤 가능 영역을 깎는 내부 여백으로 쓰지 않는다.
        wrap_target_w = max(1, int(box_w * 1.12))
        # OCR 박스 높이 전체를 사용한다. 하단/상단 안전 여백은 자동 맞춤에서 두지 않는다.
        max_h = max(1, int(box_h * 1.00))

        chosen_size = None
        chosen_lines = None
        chosen_height = None

        for size in range(max_size, min_size - 1, -1):
            _font, fm, line_spacing_pct, char_width_pct, char_height_pct, letter_spacing = self._auto_layout_item_style_metrics(item, family, size)
            sx = positive_scale_factor(char_width_pct)
            wrap_w = max(1, int(wrap_target_w / sx))
            lines = self._wrap_manga_translation_lines(source_text, fm, wrap_w, letter_spacing=letter_spacing)
            _measured_w, measured_h = self._measure_wrapped_lines_for_auto_fit(item, lines, family, size, stroke=stroke)
            chosen_size = size
            chosen_lines = lines
            chosen_height = measured_h
            if measured_h <= max_h:
                break

        if chosen_lines is None or chosen_size is None:
            return False

        wrapped = '\n'.join([line.rstrip() for line in chosen_lines]).strip()
        changed = bool(fit_rect_changed)

        if wrapped and wrapped != str(original or ''):
            item[text_key] = wrapped
            changed = True

        old_size = int(item.get('font_size', start_size) or start_size)
        if old_size != int(chosen_size):
            item['font_size'] = int(chosen_size)
            changed = True

        if item.get('ocr_engine') != 'manga_ocr':
            item['ocr_engine'] = 'manga_ocr'
            changed = True
        if item.get('ocr_lang') != 'ja':
            item['ocr_lang'] = 'ja'
            changed = True
        item['auto_layout_mode'] = 'manga_ocr_translation_fit'

        if chosen_height is not None and chosen_height > max_h:
            item['auto_wrap_height_overflow'] = True
        else:
            item.pop('auto_wrap_height_overflow', None)

        return changed

    def normalize_auto_wrap_source_text_for_lang(self, text, lang=None):
        """언어별 자동 줄내림용 원문 정리. 기존 줄바꿈은 다시 감기 위해 해제한다."""
        lang = self._normalize_ocr_lang_for_layout(lang) or 'ja'
        text = str(text or '').replace('\r\n', '\n').replace('\r', '\n')
        parts = [p.strip() for p in text.split('\n')]
        parts = [p for p in parts if p]
        if not parts:
            return ""

        if lang in ('en', 'ko'):
            joined = ' '.join(parts)
            joined = re.sub(r'\s+', ' ', joined).strip()
            # 문장부호 앞에 생긴 불필요한 공백 제거.
            joined = re.sub(r'\s+([,.;:!?…])', r'\1', joined)
            joined = re.sub(r'\s+([)\]\}])', r'\1', joined)
            joined = re.sub(r'([([{])\s+', r'\1', joined)
            return joined

        # 일본어/중국어는 기존 줄내림을 공백 없이 합친다.
        return ''.join(parts)

    def _auto_layout_item_style_metrics(self, item, family, size):
        font = QFont(str(family))
        font.setPixelSize(int(size))
        try:
            ysb_apply_readable_bold_to_font(font, bool(item.get('bold', False)))
            font.setItalic(bool(item.get('italic', False)))
        except Exception:
            pass
        fm = QFontMetrics(font)
        try:
            line_spacing_pct = clamp_text_line_spacing(item.get('line_spacing', 100), 100)
        except Exception:
            line_spacing_pct = 100
        try:
            char_width_pct = clamp_text_char_scale(item.get('char_width', 100), 100)
        except Exception:
            char_width_pct = 100
        try:
            char_height_pct = clamp_text_char_scale(item.get('char_height', 100), 100)
        except Exception:
            char_height_pct = 100
        try:
            letter_spacing = int(item.get('letter_spacing', 0) or 0)
        except Exception:
            letter_spacing = 0
        return font, fm, line_spacing_pct, char_width_pct, char_height_pct, letter_spacing

    def _text_advance_with_letter_spacing(self, text, fm, letter_spacing=0):
        text = str(text or '')
        if not text:
            return 0
        base = fm.horizontalAdvance(text)
        if len(text) >= 2 and int(letter_spacing or 0) != 0:
            base += int(letter_spacing or 0) * (len(text) - 1)
        return max(0, int(base))

    def _ko_compact_len(self, text):
        return ko_linebreak_rules.compact_len(text)

    def _ko_line_is_bad_particle_only(self, line):
        """한국어 줄 끝/시작에서 soft 조사 또는 hard 짧은 어미가 외톨이로 떨어지는지 판단한다."""
        return ko_linebreak_rules.line_is_bad_particle_only(line)

    def _ko_line_is_hard_attach_only(self, line):
        """hard 짧은 어미/꼬리만 한 줄에 떨어졌는지 판단한다."""
        return ko_linebreak_rules.line_is_hard_attach_only(line)

    def _ko_line_is_soft_attach_only(self, line):
        """soft 조사만 한 줄에 떨어졌는지 판단한다."""
        return ko_linebreak_rules.line_is_soft_attach_only(line)

    def _ko_bound_morphemes(self):
        """한국어 줄내림 보호 단위 묶음.

        실제 목록은 ysb/core/korean_linebreak_rules.py에서 관리한다.
        """
        return ko_linebreak_rules.bound_morphemes()

    def _ko_leading_bound_morpheme(self, line):
        """줄 맨 앞에 떨어진 조사/짧은 말끝을 찾는다."""
        return ko_linebreak_rules.leading_bound_morpheme(line)

    def _ko_repair_bound_particle_lines(self, lines, fm, max_w, letter_spacing=0, allow_w_ratio=ko_linebreak_rules.BOUND_REPAIR_WIDTH_ALLOW_RATIO):
        """줄 앞에 떨어진 soft 조사/hard 짧은 어미를 직전 줄로 되붙인다.

        비율 우선 줄내림을 하더라도 hard 짧은 어미는 반드시 앞말에 붙이는 쪽을 우선한다.
        soft 조사는 떨어지면 아쉽지만, 폭이 지나치게 넘으면 감점 후보로 남길 수 있다.
        단, '까지/부터/하고/어요/니까' 같은 2글자 이상 보호 단위는 독립 줄을 허용하고 내부 절단만 막는다.
        폭이 OCR 영역보다 약간 넓어져도 10%까지는 허용한다.
        """
        src = [str(x or '').strip() for x in (lines or []) if str(x or '').strip()]
        if not src:
            return ['']
        max_w = max(1, int(max_w or 1))

        def width(s):
            return self._text_advance_with_letter_spacing(s, fm, letter_spacing)

        out = []
        for raw in src:
            line = str(raw or '').strip()
            if not out:
                out.append(line)
                continue
            guard = 0
            while line and guard < 4:
                guard += 1
                m = self._ko_leading_bound_morpheme(line)
                if not m:
                    break
                rest = line.lstrip()[len(m):].lstrip()
                trial = (out[-1] + m).strip()
                # hard 짧은 어미/꼬리는 폭보다 의미 보존을 우선해 강제로 붙인다.
                # soft 조사는 허용 폭 안에 들어올 때만 붙이고, 너무 넘치면 감점 후보로 남긴다.
                if self._ko_line_is_hard_attach_only(m) or width(trial) <= max_w * float(allow_w_ratio or 1.0):
                    out[-1] = trial
                    line = rest
                    continue
                break
            if line:
                out.append(line.strip())

        # 조사/짧은 말끝만 남은 줄은 마지막으로 한 번 더 앞줄에 붙인다.
        changed = True
        guard = 0
        while changed and guard < 12:
            guard += 1
            changed = False
            fixed = []
            i = 0
            while i < len(out):
                line = out[i]
                if i > 0 and self._ko_line_is_bad_particle_only(line):
                    trial = (fixed[-1] + line).strip() if fixed else line
                    if fixed and (self._ko_line_is_hard_attach_only(line) or width(trial) <= max_w * float(allow_w_ratio or 1.0)):
                        fixed[-1] = trial
                        changed = True
                    else:
                        fixed.append(line)
                    i += 1
                    continue
                fixed.append(line)
                i += 1
            out = fixed
        return [x for x in out if x] or ['']

    def _ko_linebreak_badness(self, lines):
        """한국어 조사/짧은 말끝/보호 단위/특문 줄내림 불량도.

        실제 조건은 ysb/core/korean_linebreak_rules.py에서 관리한다.
        - 조사/짧은 종결어미 단독 줄은 금지급 감점
        - '까지/부터/하고/에서/어요/니까' 같은 2글자 이상 보호 단위 내부 절단은 금지급 감점
        - 가벼운 닫는 문장부호가 줄 앞에 오면 감점
        """
        return ko_linebreak_rules.linebreak_badness(lines)

    def _ko_split_long_token(self, token, fm, target_w, letter_spacing=0):
        """공백 없는 긴 한국어 덩어리를 식질용으로 자른다.

        실제 분할 규칙은 ysb/core/korean_linebreak_rules.py에서 관리한다.
        이 경로도 '지금까 / 지의', '너하 / 고나'처럼 기능 단위가 내부 절단되지 않도록
        폭 기준 분할을 모듈 함수에 위임한다.
        """
        token = str(token or '').strip()
        if not token:
            return []

        def width(s):
            return self._text_advance_with_letter_spacing(s, fm, letter_spacing)

        try:
            return ko_linebreak_rules.split_token_by_width(
                token,
                target_w,
                width,
                max_visual_part_len=max(ko_linebreak_rules.SPLIT_MIN_PART_LEN, int(max(3, self._ko_compact_len(token) // 2))),
            )
        except Exception:
            return ko_linebreak_rules.split_token_by_count(
                token,
                max(ko_linebreak_rules.SPLIT_MIN_PART_LEN, int(max(3, self._ko_compact_len(token) // 2))),
            )

    def _wrap_korean_greedy_lines(self, text, fm, target_w, letter_spacing=0):
        """한국어 후보 줄내림 1개를 만든다. 공백 우선 + 긴 덩어리 내부 분할."""
        text = re.sub(r'\s+', ' ', str(text or '').strip())
        if not text:
            return ['']
        target_w = max(1, int(target_w))

        def width(s):
            return self._text_advance_with_letter_spacing(s, fm, letter_spacing)

        tokens = [t for t in text.split(' ') if t]
        lines = []
        current = ''

        def push_current():
            nonlocal current
            if current or not lines:
                lines.append(current.strip())
            current = ''

        for token in tokens:
            token_parts = [token]
            if width(token) > target_w and self._ko_compact_len(token) > 4:
                token_parts = self._ko_split_long_token(token, fm, target_w, letter_spacing=letter_spacing)
            for part in token_parts:
                if not current:
                    current = part
                    continue
                trial = current + ' ' + part
                if width(trial) <= target_w:
                    current = trial
                else:
                    push_current()
                    current = part
        push_current()
        return self._ko_repair_bound_particle_lines(
            [x for x in lines if x is not None] or [''], fm, target_w, letter_spacing=letter_spacing, allow_w_ratio=ko_linebreak_rules.BOUND_REPAIR_WIDTH_ALLOW_RATIO
        )

    def _ko_merge_loose_lines(self, lines, fm, max_w, letter_spacing=0):
        """폭 여백이 많이 남거나 짧은 줄이 생겼을 때 인접 줄을 다시 병합한다."""
        lines = [str(x or '').strip() for x in (lines or []) if str(x or '').strip()]
        if not lines:
            return ['']
        max_w = max(1, int(max_w))

        def width(s):
            return self._text_advance_with_letter_spacing(s, fm, letter_spacing)

        changed = True
        guard = 0
        while changed and guard < 24:
            guard += 1
            changed = False
            i = 0
            merged = []
            while i < len(lines):
                if i + 1 < len(lines):
                    a, b = lines[i], lines[i + 1]
                    trial = (a + ' ' + b).strip()
                    a_short = self._ko_compact_len(a) < 3 or self._ko_line_is_bad_particle_only(a)
                    b_short = self._ko_compact_len(b) < 3 or self._ko_line_is_bad_particle_only(b)
                    loose = width(a) < max_w * 0.45 and width(b) < max_w * 0.55
                    if width(trial) <= max_w * 1.10 and (a_short or b_short or loose):
                        merged.append(trial)
                        i += 2
                        changed = True
                        continue
                merged.append(lines[i])
                i += 1
            lines = merged
        return self._ko_repair_bound_particle_lines(
            lines or [''], fm, max_w, letter_spacing=letter_spacing, allow_w_ratio=ko_linebreak_rules.BOUND_REPAIR_WIDTH_ALLOW_RATIO
        )

    def _ko_wrap_candidates(self, text, fm, max_w, letter_spacing=0, max_h=None, box_w=None, box_h=None, item=None, family=None, size=None, stroke=0):
        """한국어 자동 조정용 줄 후보를 여러 개 만든다.

        핵심 원칙:
        1) OCR 박스의 폭/높이 비율을 먼저 본다.
        2) 그 비율에 가까운 텍스트 덩어리 모양이 되도록 줄 구조 후보를 만든다.
        3) 선택된 줄 구조를 폰트 크기 탐색 단계에서 최대한 키운다.
        """
        text = re.sub(r'\s+', ' ', str(text or '').strip())
        if not text:
            return [['']]
        max_w = max(1, int(max_w))
        candidates = []
        seen = set()

        def add_candidate(lines):
            # 한국어 1글자 조사 결합/기능 단위 내부 보존이 OCR 형상 점수보다 우선한다.
            # 후보를 등록하기 전에 줄 앞에 떨어진 1글자 조사를 먼저 복구한다.
            repaired = self._ko_repair_bound_particle_lines(
                lines, fm, max_w, letter_spacing=letter_spacing, allow_w_ratio=ko_linebreak_rules.BOUND_REPAIR_WIDTH_ALLOW_RATIO
            )
            cleaned = tuple(str(x or '').strip() for x in (repaired or []) if str(x or '').strip()) or ('',)
            if cleaned not in seen:
                seen.add(cleaned)
                candidates.append(list(cleaned))

        # 1차: OCR 박스 비율 기반 후보.
        # 같은 텍스트라도 세로로 긴 말풍선이면 짧은 줄 여러 개, 가로로 긴 영역이면 긴 줄 적은 개수를 우선 만든다.
        try:
            bw = max(1.0, float(box_w if box_w is not None else max_w))
            bh = max(1.0, float(box_h if box_h is not None else (max_h or max_w)))
            box_ratio = max(0.12, min(8.0, bw / bh))
        except Exception:
            box_ratio = 1.0

        try:
            if item is not None and family is not None and size is not None:
                _mw, one_line_h = self._measure_wrapped_lines_for_auto_fit(item, ['가'], family, size, stroke=stroke)
            else:
                one_line_h = max(1.0, float(fm.lineSpacing()))
        except Exception:
            one_line_h = max(1.0, float(fm.lineSpacing()))

        compact_len = max(1, self._ko_compact_len(text))
        # 짧은 대사는 한 줄 후보도 살리고, 긴 대사는 박스 세로비에 따라 여러 줄 후보를 넓게 본다.
        max_lines_by_height = 8
        if max_h is not None:
            try:
                max_lines_by_height = max(1, min(12, int(float(max_h) / max(1.0, one_line_h * 0.72))))
            except Exception:
                max_lines_by_height = 8
        max_lines_by_text = max(1, min(12, int(math.ceil(compact_len / 2.0))))
        max_lines = max(1, min(12, max(max_lines_by_height, min(8, max_lines_by_text))))

        preferred_lines = []
        if box_ratio < 0.55:       # 세로로 긴 영역
            preferred_lines = [4, 5, 3, 6, 2, 7, 8, 1]
        elif box_ratio < 0.90:     # 약간 세로형
            preferred_lines = [3, 4, 2, 5, 6, 1]
        elif box_ratio > 2.20:     # 가로로 긴 영역
            preferred_lines = [1, 2, 3, 4]
        elif box_ratio > 1.35:     # 약간 가로형
            preferred_lines = [2, 1, 3, 4, 5]
        else:                      # 정사각형 근처
            preferred_lines = [2, 3, 1, 4, 5, 6]
        # 텍스트 길이에 비해 말이 안 되는 줄 수는 뒤로 밀린다.
        ordered_lines = []
        for n in preferred_lines + list(range(1, max_lines + 1)):
            if n < 1 or n > max_lines:
                continue
            if n not in ordered_lines:
                ordered_lines.append(n)

        for line_count in ordered_lines:
            block_h = max(1.0, one_line_h * line_count)
            target_w = block_h * box_ratio
            # line_count 기반 목표 폭이 너무 좁거나 넓으면 OCR 영역 안에서 현실적인 값으로 조정한다.
            target_w = max(max_w * 0.28, min(max_w * 1.06, target_w))
            # 줄 수가 적어야 하는 가로형 영역은 조금 더 넓게, 세로형은 조금 더 좁게도 같이 시험한다.
            shape_ratios = (1.00, 0.90, 1.10, 0.78, 1.22)
            for sr in shape_ratios:
                tw = max(1, int(target_w * sr))
                lines = self._wrap_korean_greedy_lines(text, fm, tw, letter_spacing=letter_spacing)
                add_candidate(lines)
                add_candidate(self._ko_merge_loose_lines(lines, fm, max_w, letter_spacing=letter_spacing))

        # 2차: 기존 폭 비율 후보. 비율 기반 후보가 놓치는 안정 후보를 보존한다.
        ratios = (1.08, 1.00, 0.94, 0.88, 0.80, 0.72, 0.64, 0.56, 0.48, 0.40)
        for ratio in ratios:
            target_w = max(1, int(max_w * ratio))
            lines = self._wrap_korean_greedy_lines(text, fm, target_w, letter_spacing=letter_spacing)
            add_candidate(lines)
            add_candidate(self._ko_merge_loose_lines(lines, fm, max_w, letter_spacing=letter_spacing))

        # 원문 줄내림이 이미 있는 경우도 후보로 둔다.
        raw_lines = tuple(x.strip() for x in str(text or '').replace('\r\n', '\n').replace('\r', '\n').split('\n') if x.strip())
        if raw_lines:
            add_candidate(raw_lines)
        return candidates or [[text]]

    def _score_korean_layout_candidate(self, item, lines, family, size, max_w, max_h, box_w, box_h, stroke=0, left_neighbor_rects=None):
        """점수 기반 한국어 조판 후보 평가. 높을수록 좋다.

        기존 로직은 초과 방지에 강하고 빈 공간 감점이 약했다.
        이 점수식은 OCR 영역 비율에 맞는 텍스트 덩어리를 먼저 선호하고,
        그 덩어리가 영역을 충분히 채우도록 보상/감점을 더 강하게 둔다.
        """
        measured_w, measured_h = self._measure_wrapped_lines_for_auto_fit(item, lines, family, size, stroke=stroke)
        max_w = max(1.0, float(max_w))
        max_h = max(1.0, float(max_h))
        raw_box_ratio = float(box_w) / max(1.0, float(box_h))
        box_ratio = max(0.12, min(8.0, raw_box_ratio))
        text_ratio = max(0.08, float(measured_w) / max(1.0, float(measured_h)))

        # 큰 글씨를 더 강하게 선호한다. 단, 초과 후보는 아래에서 크게 깎인다.
        # 주변 텍스트/OCR 영역과 실제로 겹치지 않으면 가로폭은 OCR 영역 대비 110%까지 허용한다.
        score = float(size) * 7.5
        neighbor_overlap = False
        try:
            candidate_rect_for_overlap = self._candidate_text_scene_rect(item, lines, family, size, stroke=stroke)
            if candidate_rect_for_overlap is not None:
                for nr in left_neighbor_rects or []:
                    if candidate_rect_for_overlap.intersects(nr):
                        neighbor_overlap = True
                        break
        except Exception:
            neighbor_overlap = False
        allowed_w = max_w * (1.0 if neighbor_overlap else 1.10)
        allowed_h = max_h
        over_w = max(0.0, measured_w - allowed_w)
        over_h = max(0.0, measured_h - allowed_h)
        if over_w > 0:
            score -= 6000.0 + over_w * 24.0
        if over_h > 0:
            score -= 7600.0 + over_h * 30.0
        if neighbor_overlap:
            score -= 9000.0

        widths = []
        try:
            _font, fm, _lsp, char_width_pct, _chp, letter_spacing = self._auto_layout_item_style_metrics(item, family, size)
            sx = char_width_pct / 100.0
            for line in lines or ['']:
                widths.append(self._text_advance_with_letter_spacing(line, fm, letter_spacing) * sx)
        except Exception:
            widths = [measured_w]

        non_empty = [w for w in widths if w > 0]
        if non_empty:
            avg_w = sum(non_empty) / len(non_empty)
            variance = sum(abs(w - avg_w) for w in non_empty) / max(1, len(non_empty))
            # 줄 길이 균형은 보되, 영역 채우기보다 우선하지 않게 기존보다 약간 낮춘다.
            score -= variance * 0.58

        # OCR 박스 비율에 가까운 덩어리를 강하게 선호한다.
        # 단순 차이보다 로그 비율이 세로형/가로형 모두 더 안정적이다.
        try:
            ratio_cost = abs(math.log(max(0.08, text_ratio) / max(0.08, box_ratio)))
        except Exception:
            ratio_cost = abs(text_ratio - box_ratio)
        score -= ratio_cost * 360.0

        fill_w = measured_w / max_w
        fill_h = measured_h / max_h
        # 식질 기본값은 안전 여백을 조금 남기되, 영역이 크게 비는 것은 강하게 피한다.
        if box_ratio < 0.75:
            target_w, target_h = 0.84, 0.86
            min_good_w, min_good_h = 0.50, 0.58
        elif box_ratio > 1.70:
            target_w, target_h = 0.90, 0.78
            min_good_w, min_good_h = 0.60, 0.45
        else:
            target_w, target_h = 0.88, 0.82
            min_good_w, min_good_h = 0.55, 0.52

        score -= abs(target_w - min(1.35, fill_w)) * 260.0
        score -= abs(target_h - min(1.35, fill_h)) * 250.0
        if fill_w < min_good_w:
            score -= (min_good_w - fill_w) * 1500.0
        if fill_h < min_good_h:
            score -= (min_good_h - fill_h) * 1450.0
        allowed_fill_w = 1.0 if neighbor_overlap else 1.10
        if fill_w > allowed_fill_w:
            score -= (fill_w - allowed_fill_w) * 1200.0
        if fill_h > 1.0:
            score -= (fill_h - 1.0) * 1400.0

        line_count = max(1, len(lines or []))
        compact_len = self._ko_compact_len(''.join(lines or []))
        # 박스 모양과 줄 수가 심하게 어긋나면 감점한다.
        if box_ratio < 0.70 and line_count <= 1 and compact_len >= 5:
            score -= 520.0
        if box_ratio > 1.85 and line_count >= 5:
            score -= 380.0 + (line_count - 4) * 80.0
        score -= max(0, line_count - 8) * 38.0

        for line in lines or []:
            clen = self._ko_compact_len(line)
            if clen <= 0:
                score -= 400.0
            elif clen < 2:
                score -= 340.0
            elif clen < 3:
                score -= 180.0
            if self._ko_line_is_bad_particle_only(line):
                score -= 650.0

        # 한국어 조사/짧은 말끝 결합과 보호 단위 내부 보존은 형상 점수보다 우선한다.
        # 줄 앞에 보호 부착 단위가 떨어진 후보와 보호 단위가 내부 절단된 후보는 낮은 우선순위로 밀어낸다.
        linebreak_badness = self._ko_linebreak_badness(lines)
        if linebreak_badness > 0:
            score -= linebreak_badness * 12000.0

        return score, measured_w, measured_h

    def _candidate_text_scene_rect(self, item, lines, family, size, stroke=0):
        """자동 조정 후보가 실제 화면에서 차지할 대략적인 scene rect를 계산한다."""
        measured_w, measured_h = self._measure_wrapped_lines_for_auto_fit(item, lines, family, size, stroke=stroke)
        rect = list(item.get('rect') or [0, 0, 1, 1])
        while len(rect) < 4:
            rect.append(1)
        rect_x = float(rect[0])
        rect_y = float(rect[1])
        rect_w = max(1.0, float(rect[2]))
        rect_h = max(1.0, float(rect[3]))
        x_off = float(item.get('x_off', 0) or 0)
        y_off = float(item.get('y_off', 0) or 0)
        # inner_text_*_off는 OCR/작업 박스 자체를 움직이지 않고
        # 실제 글자 path만 박스 안에서 미세 이동시키는 자동 겹침 보정 전용 값이다.
        try:
            inner_x_off = float(item.get('inner_text_x_off', 0) or 0)
        except Exception:
            inner_x_off = 0.0
        try:
            inner_y_off = float(item.get('inner_text_y_off', 0) or 0)
        except Exception:
            inner_y_off = 0.0
        align = str(item.get('align') or getattr(self, 'default_align', 'center') or 'center').lower()
        if align == 'left':
            left = rect_x + x_off
        elif align == 'right':
            left = rect_x + x_off + rect_w - measured_w
        else:
            left = rect_x + x_off + rect_w / 2.0 - measured_w / 2.0
        top = rect_y + y_off + rect_h / 2.0 - measured_h / 2.0
        left += inner_x_off
        top += inner_y_off
        # measured_w/measured_h already include the visible stroke width from
        # _measure_wrapped_lines_for_auto_fit(). Do NOT add another safety pad here.
        # Auto-fit collision uses exact visible text bounds, not an inflated margin box.
        return QRectF(left, top, measured_w, measured_h)

    def _candidate_text_line_scene_rects(self, item, lines, family, size, stroke=0):
        """충돌 검사 전용: 전체 블록 사각형이 아니라 줄별 실제 텍스트 bounds를 만든다.

        OCR rect끼리의 충돌은 보지 않는다. 같은 텍스트 블록 안에서도 빈 공간은 충돌로
        취급하지 않기 위해, 각 줄의 실제 폭을 따로 계산한다.
        """
        try:
            if self.text_item_writing_direction(item) == 'vertical':
                rr = self._candidate_text_scene_rect(item, lines, family, size, stroke=stroke)
                return [rr] if rr is not None else []
        except Exception:
            pass
        try:
            safe_lines = [str(x or '') for x in (lines or [''])]
            if not safe_lines:
                safe_lines = ['']
            block = self._candidate_text_scene_rect(item, safe_lines, family, size, stroke=stroke)
            if block is None:
                return []
            _font, fm, line_spacing_pct, char_width_pct, char_height_pct, letter_spacing = self._auto_layout_item_style_metrics(item, family, size)
            sx = positive_scale_factor(char_width_pct)
            sy = positive_scale_factor(char_height_pct)
            line_height = max(1.0, float(fm.lineSpacing()) * (float(line_spacing_pct) / 100.0) * sy)
            pad_each = max(0.0, float(int(stroke or 0)))
            pad_total = pad_each * 2.0
            align = str(item.get('align') or getattr(self, 'default_align', 'center') or 'center').lower()
            rects = []
            for idx, line in enumerate(safe_lines):
                line_text = str(line or '')
                raw_w = float(self._text_advance_with_letter_spacing(line_text, fm, letter_spacing)) * sx
                line_w = max(1.0, raw_w + pad_total)
                line_h = max(1.0, line_height + pad_total)
                if align == 'left':
                    lx = float(block.left())
                elif align == 'right':
                    lx = float(block.right()) - line_w
                else:
                    lx = float(block.left()) + (float(block.width()) - line_w) / 2.0
                ly = float(block.top()) + idx * line_height
                rects.append(QRectF(lx, ly, line_w, line_h))
            return [r for r in rects if r is not None]
        except Exception:
            rr = None
            try:
                rr = self._candidate_text_scene_rect(item, lines, family, size, stroke=stroke)
            except Exception:
                rr = None
            return [rr] if rr is not None else []

    def _left_neighbor_rects_for_auto_adjust(self, item, page_idx=None):
        """현재 항목 왼쪽의 실제 렌더 텍스트 줄 bounds만 충돌 후보로 고른다.

        OCR rect는 가까운 후보를 1차 필터링하는 용도로만 사용한다.
        result에는 다른 OCR/말풍선 박스가 아니라 실제 텍스트 line QRectF만 넣는다.
        """
        if page_idx is None:
            page_idx = self.idx
        curr = self.data.get(page_idx) or {}
        rect = item.get('rect') or [0, 0, 0, 0]
        try:
            x, y, w, h = [float(v) for v in rect[:4]]
        except Exception:
            return []
        cx = x + w / 2.0
        y1, y2 = y, y + h
        result = []
        for other in curr.get('data', []) or []:
            if other is item or not isinstance(other, dict) or not other.get('use_inpaint', True):
                continue
            try:
                _k, other_text = self._auto_layout_text_key_and_value(other)
            except Exception:
                other_text = other.get('translated_text') or other.get('text') or ''
            if not str(other_text or '').strip():
                continue

            # OCR rect는 "왼쪽/근처 후보인지" 확인하는 1차 필터로만 사용한다.
            orect = other.get('rect') or [0, 0, 0, 0]
            try:
                ox, oy, ow, oh = [float(v) for v in orect[:4]]
            except Exception:
                continue
            ocx = ox + ow / 2.0
            if ocx >= cx:
                continue
            oy1, oy2 = oy, oy + oh
            overlap_y = min(y2, oy2) - max(y1, oy1)
            if overlap_y <= 0:
                continue

            # 실제 충돌 후보는 OCR 박스가 아니라 렌더된 텍스트 줄 bbox다.
            try:
                other_line_rects = self._auto_adjust_visual_line_rects_for_item(other)
            except Exception:
                other_line_rects = []
            if other_line_rects:
                result.extend([r for r in other_line_rects if r is not None])
        return result

    def _neighbor_rects_for_auto_adjust(self, item, page_idx=None):
        """현재 항목 주변의 실제 렌더 텍스트 줄 bounds만 충돌 검사 대상으로 고른다.

        OCR rect는 근처 후보를 빠르게 거르는 guard 필터에만 사용한다.
        최종 result에는 OCR 박스가 아니라 other의 실제 line QRectF만 들어간다.
        """
        if page_idx is None:
            page_idx = self.idx
        curr = self.data.get(page_idx) or {}
        rect = item.get('rect') or [0, 0, 0, 0]
        try:
            x, y, w, h = [float(v) for v in rect[:4]]
        except Exception:
            return []
        result = []
        # 아주 먼 영역은 검사할 필요가 없으니 OCR rect로 1차 후보 필터만 한다.
        guard = QRectF(x - w * 0.75, y - h * 0.75, max(1.0, w * 2.5), max(1.0, h * 2.5))
        for other in curr.get('data', []) or []:
            if other is item or not isinstance(other, dict) or not other.get('use_inpaint', True):
                continue
            try:
                _k, other_text = self._auto_layout_text_key_and_value(other)
            except Exception:
                other_text = other.get('translated_text') or other.get('text') or ''
            if not str(other_text or '').strip():
                continue

            orect = other.get('rect') or [0, 0, 0, 0]
            try:
                ox, oy, ow, oh = [float(v) for v in orect[:4]]
            except Exception:
                continue
            # OCR rect는 guard 필터용으로만 쓴다.
            nr = QRectF(ox, oy, max(1.0, ow), max(1.0, oh))
            if not guard.intersects(nr):
                continue

            # 실제 충돌 후보는 OCR 박스가 아니라 렌더된 텍스트 줄 bbox다.
            try:
                other_line_rects = self._auto_adjust_visual_line_rects_for_item(other)
            except Exception:
                other_line_rects = []
            if other_line_rects:
                result.extend([r for r in other_line_rects if r is not None])
        return result

    def _auto_text_adjust_initial_font_size(self, item, page_idx=None, fallback_size=24):
        """CLOVA/Paddle 등 OCR 좌표 기반 기존 추정식을 우선 사용해 최초 폰트 크기를 정한다."""
        candidates = []
        try:
            ocr_est = self.estimate_source_font_size_from_ocr_coords(item)
            if ocr_est is not None:
                candidates.append(float(ocr_est))
        except Exception:
            pass
        if not candidates:
            try:
                mask_est = self.estimate_source_font_size_from_mask(item, page_idx)
                if mask_est is not None:
                    candidates.append(float(mask_est))
            except Exception:
                pass
        if not candidates:
            try:
                fallback_est = self.estimate_source_font_size_fallback(item)
                if fallback_est is not None:
                    candidates.append(float(fallback_est))
            except Exception:
                pass
        if candidates:
            return max(1, min(260, int(round(candidates[0]))))
        try:
            return max(1, min(260, int(item.get('font_size', fallback_size) or fallback_size)))
        except Exception:
            return max(1, min(260, int(fallback_size or 24)))

    def _wrap_space_language_lines(self, text, fm, max_w, lang='en', letter_spacing=0):
        """영어/한국어용 공백 보존 줄내림. 단어 우선, 불가피할 때만 글자 단위로 끊는다."""
        text = re.sub(r'\s+', ' ', str(text or '').strip())
        if not text:
            return ['']
        max_w = max(1, int(max_w))
        words = text.split(' ')
        lines = []
        current = ''

        def width(s):
            return self._text_advance_with_letter_spacing(s, fm, letter_spacing)

        def push_current():
            nonlocal current
            if current or not lines:
                lines.append(current.rstrip())
            current = ''

        def break_long_word(word):
            nonlocal current
            for ch in str(word):
                trial = current + ch
                if current and width(trial) > max_w:
                    push_current()
                    current = ch
                else:
                    current = trial

        for word in words:
            if word == '':
                continue
            trial = word if not current else current + ' ' + word
            if width(trial) <= max_w:
                current = trial
                continue
            if current:
                push_current()
            if width(word) <= max_w:
                current = word
            else:
                break_long_word(word)

        push_current()
        return lines or ['']

    def _auto_compact_wrapped_lines_fill_empty_space(self, item, lines, family, size, stroke=0, max_w=1, max_h=1, overlap_checker=None):
        """1차 자동 줄내림 뒤에 남은 빈공간을 어절 단위로 채운다.

        1차 배치는 OCR 영역을 넘기지 않는 쪽으로 보수적으로 동작한다. 그 결과
        `진짜/내가/할/수/있을까`처럼 각 줄 오른쪽이 비는 경우가 생기므로,
        이 후처리는 아래 줄의 첫 어절을 위 줄에 올려도 OCR 영역 안에 들어갈 때만
        줄 수를 줄인다. 글자 크기, 행간, 자간, 박스 크기는 절대 건드리지 않는다.

        단, 한국어 자동조정 본체가 이미 1.10배 폭까지 허용하므로 이 메우기 단계도
        같은 폭 허용치를 사용한다. 그래야 `할 / 수`처럼 빈 줄 느낌이 나는 배치를
        `할 수`로 합치는 후보가 초반 strict fit에서 부당하게 탈락하지 않는다.
        """
        try:
            safe_lines = [str(x or '').strip() for x in (lines or []) if str(x or '').strip()]
            if len(safe_lines) <= 1:
                return safe_lines or [''], False, {'moved': 0}
            max_w = max(1.0, float(max_w or 1))
            max_h = max(1.0, float(max_h or 1))
            size = max(1, int(size or 1))
        except Exception:
            return list(lines or ['']), False, {'moved': 0, 'error': 'init_failed'}

        def _tokens(line):
            # 어절 단위가 기본이다. 공백이 없는 긴 한 덩어리는 억지로 글자 단위 분해하지 않는다.
            parts = re.findall(r'\S+', str(line or '').strip())
            return parts or []

        try:
            allow_w_ratio = max(1.0, float(getattr(ko_linebreak_rules, 'HARD_WIDTH_LIMIT_RATIO', 1.10) or 1.10))
        except Exception:
            allow_w_ratio = 1.10

        def _fits(candidate_lines):
            try:
                mw, mh = self._measure_wrapped_lines_for_auto_fit(item, candidate_lines, family, size, stroke=stroke)
                if float(mw) > max_w * allow_w_ratio + 0.5 or float(mh) > max_h + 0.5:
                    return False, float(mw), float(mh), {'reason': 'ocr_fit_limit', 'allow_w_ratio': round(float(allow_w_ratio), 4)}
                if callable(overlap_checker):
                    ov, ovinfo = overlap_checker(candidate_lines, size)
                    if ov:
                        return False, float(mw), float(mh), ovinfo
                return True, float(mw), float(mh), None
            except Exception as exc:
                return False, 0.0, 0.0, {'error': repr(exc)}

        current = list(safe_lines)
        moved = 0
        passes = 0
        last_mw = None
        last_mh = None
        last_block = None
        while passes < 64:
            passes += 1
            changed_in_pass = False
            i = 0
            while i < len(current) - 1:
                # 같은 줄에 더 들어갈 수 있으면 다음 줄의 첫 어절을 계속 끌어올린다.
                while i < len(current) - 1:
                    nxt = _tokens(current[i + 1])
                    if not nxt:
                        break
                    token = nxt[0]
                    trial_line = (str(current[i] or '').rstrip() + ' ' + token).strip() if str(current[i] or '').strip() else token
                    rest = ' '.join(nxt[1:]).strip()
                    candidate = list(current)
                    candidate[i] = trial_line
                    if rest:
                        candidate[i + 1] = rest
                    else:
                        del candidate[i + 1]
                    ok, mw, mh, block = _fits(candidate)
                    last_mw, last_mh, last_block = mw, mh, block
                    if not ok:
                        break
                    current = candidate
                    moved += 1
                    changed_in_pass = True
                i += 1
            if not changed_in_pass:
                break

        changed = bool(moved > 0 and current != safe_lines)
        return current or [''], changed, {
            'moved': int(moved),
            'passes': int(passes),
            'measured_w': round(float(last_mw or 0.0), 2),
            'measured_h': round(float(last_mh or 0.0), 2),
            'last_block': str(last_block)[:180] if last_block is not None else '',
        }

    def _auto_text_size_empty_space_compact_pass(self, page_idx, targets, *, phase='final_empty_space_compact'):
        """현재 글자 크기에서 빈 줄 느낌이 남은 텍스트를 마지막으로 한 번 더 메운다.

        폰트 크기/행간/자간/OCR rect는 바꾸지 않고 줄내림만 다시 압축한다.
        후보는 OCR 폭 1.10배 안쪽, 페이지 경계 안쪽, 다른 텍스트와 실제 bounds 비겹침일 때만 적용한다.
        """
        try:
            size = self._auto_layout_page_image_size_for_auto(page_idx=page_idx)
        except Exception:
            size = None
        if not size:
            return []
        try:
            page_rect = QRectF(0.0, 0.0, float(size[0]), float(size[1]))
        except Exception:
            return []

        active = []
        for item in targets or []:
            if not isinstance(item, dict) or not item.get('use_inpaint', True):
                continue
            try:
                _key, text = self._auto_layout_text_key_and_value(item)
            except Exception:
                text = item.get('translated_text') or item.get('text') or ''
            if str(text or '').strip():
                active.append(item)
        if not active:
            return []

        changed_ids = []
        for item in active:
            try:
                if self.text_item_writing_direction(item) == 'vertical':
                    continue
            except Exception:
                pass
            try:
                text_key, text_value = self._auto_layout_text_key_and_value(item)
            except Exception:
                text_key = 'translated_text' if str(item.get('translated_text', '') or '').strip() else 'text'
                text_value = item.get(text_key, '') or ''
            raw_text = str(text_value or '').replace('\r\n', '\n').replace('\r', '\n')
            lines = [ln.rstrip() for ln in raw_text.split('\n') if ln.strip()]
            if len(lines) <= 1:
                continue
            try:
                family = item.get('font_family') or self.cb_font.currentFont().family()
            except Exception:
                family = item.get('font_family') or 'Arial'
            try:
                font_size = max(1, int(round(float(item.get('font_size', 0) or 0))))
            except Exception:
                font_size = 1
            try:
                stroke = max(0, int(item.get('stroke_width', 0) or 0))
            except Exception:
                stroke = 0
            try:
                rect = item.get('rect') or [0, 0, 1, 1]
                max_w = max(1.0, float(rect[2]))
                max_h = max(1.0, float(rect[3]))
            except Exception:
                continue

            old_text = str(item.get(text_key, '') or '')
            old_font = item.get('font_size')
            old_ix = item.get('inner_text_x_off')
            old_iy = item.get('inner_text_y_off')

            def _restore():
                try:
                    item[text_key] = old_text
                    item['font_size'] = old_font
                    if old_ix is None:
                        item.pop('inner_text_x_off', None)
                    else:
                        item['inner_text_x_off'] = old_ix
                    if old_iy is None:
                        item.pop('inner_text_y_off', None)
                    else:
                        item['inner_text_y_off'] = old_iy
                except Exception:
                    pass

            def _overlap_or_boundary(candidate_lines, test_size):
                try:
                    item[text_key] = '\n'.join([str(x or '').rstrip() for x in candidate_lines if str(x or '').strip()]).strip()
                    item['font_size'] = int(test_size)
                    rr = self._auto_adjust_visual_rect_for_item(item)
                    boundary_info = self._auto_text_size_page_boundary_overflow_info(rr, page_rect)
                    if bool(boundary_info.get('overflow')):
                        return True, {'reason': 'page_boundary', 'boundary_info': boundary_info}
                    ov, ov_info = self._auto_text_item_overlaps_any(item, active, strict=True)
                    if ov:
                        return True, {'reason': 'text_overlap', 'overlap_info': ov_info}
                    return False, None
                except Exception as exc:
                    return True, {'reason': 'exception', 'error': repr(exc)}
                finally:
                    _restore()

            try:
                compacted, changed, diag = self._auto_compact_wrapped_lines_fill_empty_space(
                    item,
                    lines,
                    family,
                    font_size,
                    stroke=stroke,
                    max_w=max_w,
                    max_h=max_h,
                    overlap_checker=_overlap_or_boundary,
                )
            except Exception as exc:
                compacted, changed, diag = lines, False, {'error': repr(exc)}

            if not changed:
                continue

            new_lines = [str(x or '').rstrip() for x in compacted or [] if str(x or '').strip()]
            if not new_lines or new_lines == lines:
                continue
            try:
                item[text_key] = '\n'.join(new_lines).strip()
                item['font_size'] = int(font_size)
                rr = self._auto_adjust_visual_rect_for_item(item)
                boundary_info = self._auto_text_size_page_boundary_overflow_info(rr, page_rect)
                ov, ov_info = self._auto_text_item_overlaps_any(item, active, strict=True)
                if bool(boundary_info.get('overflow')) or ov:
                    _restore()
                    try:
                        if hasattr(self, 'audit_boundary_event'):
                            self.audit_boundary_event(
                                'TEXT_AUTO_ADJUST_EMPTY_SPACE_COMPACT_BLOCKED',
                                page_idx=page_idx,
                                item_id=item.get('id'),
                                phase=str(phase or ''),
                                old_line_count=len(lines),
                                new_line_count=len(new_lines),
                                boundary_info=boundary_info if bool(boundary_info.get('overflow')) else {},
                                overlap_info=ov_info if ov else {},
                            )
                    except Exception:
                        pass
                    continue
                item['auto_layout_empty_space_compact_applied'] = True
                item['auto_layout_empty_space_compact_phase'] = str(phase or '')
                item['auto_layout_empty_space_compact_old_line_count'] = int(len(lines))
                item['auto_layout_empty_space_compact_new_line_count'] = int(len(new_lines))
                item['auto_layout_empty_space_compact_diag'] = diag or {}
                cid = item.get('id')
                if cid is not None and cid not in changed_ids:
                    changed_ids.append(cid)
                try:
                    if hasattr(self, 'audit_boundary_event'):
                        self.audit_boundary_event(
                            'TEXT_AUTO_ADJUST_EMPTY_SPACE_COMPACT_APPLIED',
                            page_idx=page_idx,
                            item_id=item.get('id'),
                            phase=str(phase or ''),
                            old_line_count=len(lines),
                            new_line_count=len(new_lines),
                            moved=int((diag or {}).get('moved') or 0),
                            old_preview='\\n'.join(lines)[:160],
                            new_preview='\\n'.join(new_lines)[:160],
                            policy='font_size_rect_spacing_locked_repack_words_with_ocr_width_allowance',
                        )
                except Exception:
                    pass
            except Exception:
                _restore()
                continue

        try:
            if hasattr(self, 'audit_boundary_event'):
                self.audit_boundary_event(
                    'TEXT_AUTO_ADJUST_EMPTY_SPACE_COMPACT_PASS_DONE',
                    page_idx=page_idx,
                    phase=str(phase or ''),
                    changed_ids=[x for x in changed_ids if x is not None],
                    changed_count=len([x for x in changed_ids if x is not None]),
                )
        except Exception:
            pass
        return [x for x in changed_ids if x is not None]

    def _measure_wrapped_lines_for_auto_fit(self, item, lines, family, size, stroke=0):
        if self.text_item_writing_direction(item) == 'vertical':
            return self._measure_typesetting_lines_for_auto_fit(item, lines, family, size, stroke=stroke, writing_direction='vertical')
        _font, fm, line_spacing_pct, char_width_pct, char_height_pct, letter_spacing = self._auto_layout_item_style_metrics(item, family, size)
        sx = char_width_pct / 100.0
        sy = char_height_pct / 100.0
        max_line_w = 0.0
        for line in lines or ['']:
            max_line_w = max(max_line_w, self._text_advance_with_letter_spacing(line, fm, letter_spacing) * sx)
        line_height = max(1.0, fm.lineSpacing() * (line_spacing_pct / 100.0) * sy)
        total_h = line_height * max(1, len(lines or ['']))
        total_w = max_line_w
        pad = max(0, int(stroke or 0)) * 2
        return total_w + pad, total_h + pad

    def _measure_typesetting_lines_for_auto_fit(self, item, lines, family, size, stroke=0, writing_direction='horizontal'):
        """Measure the same path style used by the final typesetting item.

        세로쓰기 자동조정은 가로 줄내림 폭 계산을 쓰면 안 된다. 최종 렌더링과
        같은 build_typesetting_text_path() 경로로 bounds를 계산하되, OCR rect와
        원문 텍스트는 절대 변경하지 않는다.
        """
        font, fm, line_spacing_pct, char_width_pct, char_height_pct, letter_spacing = self._auto_layout_item_style_metrics(item, family, size)
        sx = positive_scale_factor(char_width_pct)
        sy = positive_scale_factor(char_height_pct)
        try:
            line_height = max(1, int(fm.lineSpacing() * (float(line_spacing_pct) / 100.0)))
        except Exception:
            line_height = max(1, int(fm.lineSpacing()))
        align = str(item.get('align') or getattr(self, 'default_align', 'center') or 'center').lower()
        if align not in ('left', 'center', 'right'):
            align = 'center'
        safe_lines = [str(x or '') for x in (lines or [''])]
        if not safe_lines:
            safe_lines = ['']
        try:
            path, _line_rects = build_typesetting_text_path(safe_lines, font, align, line_height, letter_spacing, writing_direction)
            if sx != 1.0 or sy != 1.0:
                tr = QTransform()
                tr.scale(sx, sy)
                path = tr.map(path)
            rect = path.boundingRect()
            if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
                width = max(1.0, float(fm.height()) * sx)
                height = max(1.0, float(fm.height()) * sy)
            else:
                width = max(1.0, float(rect.width()))
                height = max(1.0, float(rect.height()))
        except Exception:
            # 최종 렌더링 path 측정에 실패하면 안전하게 기존 근사값으로 후퇴한다.
            max_len = max(1, max(len(str(x or '')) for x in safe_lines))
            width = max(1.0, float(fm.height()) * max(1, len(safe_lines)) * sx)
            height = max(1.0, float(fm.height()) * max_len * sy)
        pad = max(0, int(stroke or 0)) * 2
        return width + pad, height + pad

    def _vertical_auto_adjust_lines(self, text):
        """Return source-preserving vertical columns for auto-adjust.

        자동조정 3단계에서는 세로쓰기 원문을 가로쓰기용으로 재줄내림하지 않는다.
        기존 줄바꿈은 세로 열 경계로 보존하고, 내용 자체는 저장 변경하지 않는다.
        """
        raw = str(text or '').replace('\r\n', '\n').replace('\r', '\n')
        lines = [ln.rstrip() for ln in raw.split('\n') if ln.strip()]
        if not lines and raw.strip():
            lines = [raw.strip()]
        return lines or ['']

    def _fit_vertical_text_for_item(self, item, *, text_key, original, fit_rect_changed, lang, family, fallback_size, stroke, box_w, box_h, page_idx=None):
        """Fit vertical-writing text by changing font size only.

        세로쓰기 객체에는 한국어/영어 가로 줄내림 알고리즘을 적용하지 않는다.
        OCR 영역과 원문 텍스트는 그대로 두고, 현재 줄바꿈을 세로 열로 해석해
        최종 렌더링 path가 OCR 박스 안에 들어가는 최대 글자 크기만 찾는다.
        """
        lines = self._vertical_auto_adjust_lines(original)
        max_w = max(1, int(box_w))
        max_h = max(1, int(box_h))
        start_size = self._auto_text_adjust_initial_font_size(item, page_idx=page_idx if page_idx is not None else getattr(self, 'idx', None), fallback_size=fallback_size)
        short_side = min(float(box_w), float(box_h))
        long_side = max(float(box_w), float(box_h))
        max_size = int(max(float(start_size) * 12.0, short_side * 3.5, long_side * 2.2, 72.0))
        max_size = max(1, min(960, max_size))
        lo, hi = 1, max_size
        best = 1
        best_m = self._measure_typesetting_lines_for_auto_fit(item, lines, family, 1, stroke=stroke, writing_direction='vertical')
        check_count = 0
        while lo <= hi:
            mid = (lo + hi) // 2
            mw, mh = self._measure_typesetting_lines_for_auto_fit(item, lines, family, mid, stroke=stroke, writing_direction='vertical')
            check_count += 1
            if mw <= max_w and mh <= max_h:
                best = mid
                best_m = (mw, mh)
                lo = mid + 1
            else:
                hi = mid - 1
        measured_w, measured_h = best_m
        changed = bool(fit_rect_changed)
        old_size = int(item.get('font_size', fallback_size) or fallback_size)
        if old_size != int(best):
            item['font_size'] = int(best)
            changed = True
        if item.get('ocr_lang') != lang:
            item['ocr_lang'] = lang
            changed = True
        if self.text_item_writing_direction(item) != 'vertical':
            item['writing_direction'] = 'vertical'
            changed = True
        if int(round(float(item.get('x_off', 0) or 0))) != 0:
            item['x_off'] = 0
            changed = True
        if int(round(float(item.get('y_off', 0) or 0))) != 0:
            item['y_off'] = 0
            changed = True
        fill_w = float(measured_w) / max(1.0, float(max_w))
        fill_h = float(measured_h) / max(1.0, float(max_h))
        item['auto_layout_mode'] = 'vertical_text_auto_adjust'
        item['auto_layout_writing_direction'] = 'vertical'
        item['auto_layout_line_count'] = int(len(lines))
        item['auto_layout_line_count_target'] = int(len(lines))
        item['auto_layout_fill_w'] = float(round(fill_w, 4))
        item['auto_layout_fill_h'] = float(round(fill_h, 4))
        item['auto_layout_req_w'] = 0.0
        item['auto_layout_req_h'] = 0.0
        item['auto_layout_edge_deficit'] = 0.0
        item['auto_layout_touch_ok'] = bool(measured_w <= max_w and measured_h <= max_h)
        item['auto_layout_near_touch_ok'] = item['auto_layout_touch_ok']
        item['auto_layout_hard_fail'] = bool(not item['auto_layout_touch_ok'])
        item['auto_layout_centered_to_ocr_box'] = True
        item['auto_layout_vertical_preserved_source_text'] = True
        item['auto_layout_vertical_size_check_count'] = int(check_count)
        if measured_w > max_w or measured_h > max_h:
            item['auto_wrap_height_overflow'] = True
        else:
            item.pop('auto_wrap_height_overflow', None)
        self._auto_adjust_diag(
            'TEXT_AUTO_ADJUST_VERTICAL_APPLIED',
            item,
            lang=lang,
            changed=bool(changed),
            old_size=old_size,
            final_size=int(best),
            size_delta=int(best) - int(old_size),
            final_text_changed=False,
            measured_w=round(float(measured_w), 2),
            measured_h=round(float(measured_h), 2),
            box_w=int(max_w),
            box_h=int(max_h),
            fill_w=item.get('auto_layout_fill_w'),
            fill_h=item.get('auto_layout_fill_h'),
            line_count=len(lines),
            size_check_count=int(check_count),
            policy='preserve_source_lines_fit_vertical_path_only',
        )
        return changed


    def _auto_layout_normalize_rect_candidate(self, value, key_name='rect'):
        """자동 조정용 rect 후보를 [x, y, w, h] 형태로 정규화한다."""
        try:
            if value is None:
                return None
            if hasattr(value, 'x') and hasattr(value, 'y') and hasattr(value, 'width') and hasattr(value, 'height'):
                x = float(value.x())
                y = float(value.y())
                w = float(value.width())
                h = float(value.height())
            else:
                vals = list(value)
                if len(vals) < 4:
                    return None
                x, y, a, b = [float(v) for v in vals[:4]]
                name = str(key_name or '').lower()
                if ('bbox' in name or name.endswith('_xyxy')) and a > x and b > y:
                    w = a - x
                    h = b - y
                else:
                    w = a
                    h = b
            if w <= 0 or h <= 0:
                return None
            return [int(round(x)), int(round(y)), max(1, int(round(w))), max(1, int(round(h)))]
        except Exception:
            return None

    def _auto_layout_rect_area(self, rect):
        try:
            return max(0.0, float(rect[2])) * max(0.0, float(rect[3]))
        except Exception:
            return 0.0

    def _auto_layout_resolve_fit_rect_for_item(self, item):
        """텍스트 자동 조정의 기준 박스를 고른다.

        핵심 규칙:
        - 자동 조정은 현재 글자 bounds/수동 축소 박스를 신뢰하지 않는다.
        - OCR/마스크 계열 원래 감지 박스가 남아 있으면 그 박스를 우선한다.
        - 수동 텍스트 박스가 작아져 있어도, 더 큰 OCR 계열 박스가 있으면 그쪽으로 복구한다.
        """
        if not isinstance(item, dict):
            return None, 'none'
        current = self._auto_layout_normalize_rect_candidate(item.get('rect'), 'rect')
        candidates = []
        # 우선순위가 높은 OCR/마스크 계열. red dashed OCR box가 보통 이쪽에 남는다.
        preferred_keys = (
            'auto_layout_ocr_rect', 'ocr_rect', 'ocr_crop_rect',
            'text_mask_rect', 'mask_rect', 'detector_rect', 'source_rect',
            'original_rect', 'initial_rect', 'raw_rect', 'bbox', 'box',
        )
        for key in preferred_keys:
            if key in item:
                rect = self._auto_layout_normalize_rect_candidate(item.get(key), key)
                if rect:
                    candidates.append((key, rect, True))
        if current:
            candidates.append(('rect', current, False))
        if not candidates:
            return None, 'none'
        # 중복 제거
        dedup = []
        seen = set()
        for src, rect, preferred in candidates:
            tup = tuple(int(v) for v in rect[:4])
            if tup in seen:
                continue
            seen.add(tup)
            dedup.append((src, rect, preferred))
        candidates = dedup
        current_area = self._auto_layout_rect_area(current) if current else 0.0
        preferred = [(src, rect, pref) for src, rect, pref in candidates if pref]
        # OCR/마스크 계열 중 현재 rect보다 충분히 큰 후보가 있으면 무조건 그쪽으로 간다.
        larger_preferred = []
        for src, rect, pref in preferred:
            area = self._auto_layout_rect_area(rect)
            if current_area <= 0 or area >= current_area * 1.08 or rect[2] >= (current or rect)[2] * 1.08 or rect[3] >= (current or rect)[3] * 1.08:
                larger_preferred.append((src, rect, area))
        if larger_preferred:
            src, rect, _area = max(larger_preferred, key=lambda x: x[2])
            return list(rect), src
        # 그렇지 않으면 전체 후보 중 가장 큰 박스를 고른다. 단, 같은 크기면 현재 rect를 유지한다.
        src, rect, _pref = max(candidates, key=lambda x: self._auto_layout_rect_area(x[1]))
        return list(rect), src

    def _auto_layout_apply_fit_rect_if_needed(self, item, fit_rect, fit_source):
        """자동 조정 계산용 fit rect를 기록하되 OCR rect는 절대 바꾸지 않는다.

        item['rect']는 빨간 OCR 영역/분석 영역의 원본 좌표다.
        자동 조정은 별도의 계산용 fit_rect를 사용할 수 있지만, 이 값을 rect에
        써버리면 OCR 영역이 이동/확장된 것처럼 보이고 이후 조정 기준도 꼬인다.
        """
        if not isinstance(item, dict) or not fit_rect:
            return False
        old_rect = self._auto_layout_normalize_rect_candidate(item.get('rect'), 'rect') or [0, 0, 1, 1]
        new_rect = [int(v) for v in fit_rect[:4]]
        changed = False

        # OCR rect와 텍스트 위치 오프셋은 자동 조정에서 손대지 않는다.
        # 필요한 계산 박스만 auto_layout_fit_rect에 별도로 남긴다.
        item['auto_layout_ocr_rect_locked'] = True
        item['auto_layout_fit_box_source'] = str(fit_source or 'rect')
        item['auto_layout_fit_rect'] = list(new_rect)
        if old_rect != new_rect:
            item['auto_layout_effective_fit_rect_differs_from_ocr_rect'] = True
            try:
                self._auto_adjust_diag(
                    'TEXT_AUTO_ADJUST_FIT_RECT_USED_WITHOUT_RECT_MUTATION',
                    item,
                    ocr_rect=list(old_rect),
                    effective_rect=list(new_rect),
                    fit_box_source=str(fit_source or 'rect'),
                    policy='ocr_rect_is_immutable',
                )
            except Exception:
                pass
        else:
            item.pop('auto_layout_effective_fit_rect_differs_from_ocr_rect', None)

        # 수동 텍스트 rect 모드는 실제 글자 bounds를 작업 박스로 쓰게 만들어 자동 확대를 막는다.
        # 자동 조정에서는 계산 기준만 OCR/fit rect로 보되, rect 자체는 바꾸지 않는다.
        if bool(item.get('manual_text_rect')):
            item['manual_text_rect'] = False
            changed = True
        if str(item.get('text_anchor_mode') or '').lower() == 'text':
            item['text_anchor_mode'] = 'ocr'
            changed = True
        return changed

    def _auto_layout_page_image_size_for_auto(self, page_idx=None):
        """자동 텍스트 조정용 페이지 이미지 크기를 최대한 안전하게 얻는다."""
        idx = page_idx
        try:
            if idx is None:
                idx = int(getattr(self, 'idx', 0) or 0)
        except Exception:
            idx = 0

        # 1) 프로젝트 데이터에 저장된 크기 후보
        try:
            page = (self.data.get(int(idx)) if isinstance(getattr(self, 'data', None), dict) else None) or {}
            for w_key, h_key in (
                ('width', 'height'), ('image_width', 'image_height'), ('page_width', 'page_height'),
                ('original_width', 'original_height'), ('w', 'h'),
            ):
                if w_key in page and h_key in page:
                    w = int(float(page.get(w_key) or 0))
                    h = int(float(page.get(h_key) or 0))
                    if w > 0 and h > 0:
                        return w, h
            size = page.get('image_size') or page.get('size')
            if isinstance(size, (list, tuple)) and len(size) >= 2:
                w = int(float(size[0] or 0))
                h = int(float(size[1] or 0))
                if w > 0 and h > 0:
                    return w, h
        except Exception:
            pass

        # 2) 현재 paths 이미지 파일에서 직접 읽기
        try:
            paths = getattr(self, 'paths', None) or []
            if idx is not None and 0 <= int(idx) < len(paths):
                path = str(paths[int(idx)] or '')
                if path:
                    qimg = QImage(path)
                    if not qimg.isNull() and qimg.width() > 0 and qimg.height() > 0:
                        return int(qimg.width()), int(qimg.height())
        except Exception:
            pass

        # 3) 뷰어 배경 pixmap 후보
        try:
            v = getattr(self, 'viewer', None)
            for attr in ('bg_pixmap', 'pixmap', 'base_pixmap'):
                pix = getattr(v, attr, None) if v is not None else None
                if pix is not None and hasattr(pix, 'width') and pix.width() > 0 and pix.height() > 0:
                    return int(pix.width()), int(pix.height())
        except Exception:
            pass
        return None

    def _auto_layout_expand_narrow_edge_fit_rect_for_item(self, item, rect, source_text, page_idx=None):
        """
        OCR rect가 지나치게 좁게 잡힌 경우 자동 조정 계산 박스만 확장한다.

        원칙:
        - item['rect']는 OCR 원본 영역이므로 절대 수정하지 않는다.
        - 페이지 가장자리 클리핑형 좁은 박스만 안쪽 방향으로 확장한다.
        - 내부 세로형 박스는 대부분 정상적인 세로 말풍선 배치이므로 자동 확장하지 않는다.
        - 확장 후 실제 텍스트 충돌은 후처리에서 보되, 줄내림/띄어쓰기는 1차 조정 이후 건드리지 않는다.
        """
        try:
            if not isinstance(item, dict):
                return None, {}
            base = self._auto_layout_normalize_rect_candidate(rect, 'rect')
            if not base:
                return None, {}
            x, y, w, h = [float(v) for v in base[:4]]
            if w <= 0 or h <= 0:
                return None, {}
            compact_len = max(1, int(self._ko_compact_len(str(source_text or ''))))
            if compact_len < 8:
                return None, {'reason': 'short_text', 'compact_len': compact_len}

            page_size = self._auto_layout_page_image_size_for_auto(page_idx=page_idx)
            page_w = float(page_size[0]) if page_size else 0.0
            page_h = float(page_size[1]) if page_size else 0.0
            edge_tol = max(2.0, min(10.0, max(1.0, w) * 0.08))
            near_left = x <= edge_tol
            near_right = bool(page_w > 0 and (x + w) >= page_w - edge_tol)

            ratio = float(w) / max(1.0, float(h))
            narrow_limit = max(112.0, min(220.0, float(h) * 0.72))
            too_narrow = bool(w < narrow_limit or ratio < 0.58)

            # x=0 / 우측 끝에 붙어 있어도 세로로 긴 OCR 박스는 정상 배치일 가능성이 높다.
            # 이런 박스를 계산용으로 넓히면 '뭐, 생으로 / 해도 괜찮 / 겠지.'처럼
            # 원래 세로로 쌓여야 할 대사가 가로형으로 풀리며 비율이 망가진다.
            # 따라서 가장자리 보정은 "가로/정사각형에 가까운 박스가 가장자리에서 잘린 경우"만 허용한다.
            tall_vertical_edge = bool((near_left or near_right) and ratio < 0.72 and h >= 120.0 and compact_len >= 4)
            if tall_vertical_edge:
                return None, {
                    'reason': 'preserve_tall_edge_ratio_no_expand',
                    'compact_len': compact_len,
                    'ratio': round(ratio, 4),
                    'narrow_limit': round(narrow_limit, 2),
                    'near_left': near_left,
                    'near_right': near_right,
                    'policy': 'keep_original_ocr_ratio_for_tall_edge_text',
                }

            # 내부 세로형 OCR 박스를 자동 확장하면 원래 세로로 쌓여야 하는 대사까지
            # 가로로 풀리며 줄비율이 망가진다. 현재 계산폭 확장은 페이지 가장자리의
            # 비세로형 절단 박스에만 허용한다.
            generic_tall_narrow = False

            if not (too_narrow and (near_left or near_right)) and not generic_tall_narrow:
                return None, {
                    'reason': 'not_narrow_edge_or_tall_narrow',
                    'compact_len': compact_len,
                    'ratio': round(ratio, 4),
                    'narrow_limit': round(narrow_limit, 2),
                    'near_left': near_left,
                    'near_right': near_right,
                    'generic_tall_narrow': generic_tall_narrow,
                }

            if generic_tall_narrow:
                # 현재 비활성화 상태. 내부 좁은 OCR 박스 확장은 별도 안전 조건을 다시 설계하기 전까지 금지한다.
                return None, {'reason': 'generic_tall_narrow_disabled'}
            else:
                # 페이지 가장자리 절단형 중에서도 세로형은 위에서 차단한다.
                # 남은 후보는 가로/정사각형 박스가 가장자리에서 잘린 경우로 보고 안쪽 방향으로만 복구한다.
                target_w = max(float(w), max(float(w) * 1.55, float(h) * 0.82, 128.0))
                target_w = min(target_w, 320.0)
                target_w = min(target_w, max(140.0, float(h) * 1.05))
                expand_policy = 'narrow_edge_ocr_rect_expand_inside_page_before_fit_non_vertical_only'

            if page_w > 0:
                target_w = min(target_w, page_w)
            if target_w <= float(w) * 1.12:
                return None, {'reason': 'expansion_too_small', 'target_w': round(target_w, 2), 'old_w': round(w, 2), 'generic_tall_narrow': generic_tall_narrow}

            if near_left:
                nx = max(0.0, x)
                nw = target_w
                if page_w > 0:
                    nw = min(nw, max(1.0, page_w - nx))
            elif near_right:
                right = x + w
                nw = target_w
                nx = right - nw
                if page_w > 0:
                    nx = max(0.0, min(nx, page_w - nw))
            else:
                nw = target_w
                nx = x - (nw - w) / 2.0
                if page_w > 0:
                    nx = max(0.0, min(nx, page_w - nw))

            new_rect = [int(round(nx)), int(round(y)), max(1, int(round(nw))), max(1, int(round(h)))]
            if new_rect[2] <= int(round(w)):
                return None, {'reason': 'not_wider_after_clamp', 'new_rect': new_rect}
            info = {
                'old_rect': [int(round(x)), int(round(y)), int(round(w)), int(round(h))],
                'new_rect': list(new_rect),
                'compact_len': compact_len,
                'ratio': round(ratio, 4),
                'narrow_limit': round(narrow_limit, 2),
                'target_w': round(float(target_w), 2),
                'page_size': f"{int(page_w)}x{int(page_h)}" if page_w and page_h else '',
                'near_left': near_left,
                'near_right': near_right,
                'generic_tall_narrow': bool(generic_tall_narrow),
                'policy': expand_policy,
            }
            return new_rect, info
        except Exception as exc:
            return None, {'reason': 'error', 'error': repr(exc)}

    def _auto_adjust_diag(self, event, item=None, **fields):
        """텍스트 자동 조정 진단 로그. 데이터 변경 없이 스킵/루프/결과만 남긴다."""
        try:
            if not hasattr(self, 'audit_boundary_event'):
                return
            payload = dict(fields or {})
            if isinstance(item, dict):
                payload.setdefault('item_id', item.get('id'))
                try:
                    text_key, text_value = self._auto_layout_text_key_and_value(item)
                except Exception:
                    text_key = ''
                    text_value = item.get('translated_text') or item.get('text') or ''
                payload.setdefault('text_key', text_key)
                try:
                    raw_text = str(text_value or '')
                    payload.setdefault('text_len', len(raw_text))
                    payload.setdefault('text_preview', raw_text.replace('\r', '\\r').replace('\n', '\\n')[:80])
                except Exception:
                    pass
                try:
                    payload.setdefault('rect', item.get('rect'))
                    payload.setdefault('ocr_crop_rect', item.get('ocr_crop_rect'))
                    payload.setdefault('text_mask_rect', item.get('text_mask_rect'))
                    payload.setdefault('mask_rect', item.get('mask_rect'))
                    payload.setdefault('ocr_rect', item.get('ocr_rect'))
                except Exception:
                    pass
                try:
                    payload.setdefault('old_font_size', item.get('font_size'))
                    payload.setdefault('font_family', item.get('font_family'))
                    payload.setdefault('manual_text_rect', bool(item.get('manual_text_rect')))
                    payload.setdefault('text_anchor_mode', item.get('text_anchor_mode'))
                    payload.setdefault('auto_layout_mode_prev', item.get('auto_layout_mode'))
                except Exception:
                    pass
            self.audit_boundary_event(str(event), **payload)
        except Exception:
            pass

    def _auto_adjust_item_text_state_for_diag(self, item):
        """자동 조정 전 대상/비대상/빈 박스 진단용 스냅샷."""
        info = {}
        try:
            if not isinstance(item, dict):
                info['item_type'] = type(item).__name__
                info['diag_reason'] = 'non_dict_item'
                return info
            text_raw = str(item.get('text') or '')
            translated_raw = str(item.get('translated_text') or '')
            display_raw = str(item.get('display_text') or '')
            try:
                text_key, effective_raw = self._auto_layout_text_key_and_value(item)
            except Exception:
                text_key = 'translated_text' if translated_raw.strip() else 'text'
                effective_raw = translated_raw if translated_raw.strip() else text_raw
            layout_raw = str(effective_raw or '')
            compact = ''.join(ch for ch in layout_raw if not ch.isspace())
            use_inpaint = bool(item.get('use_inpaint', True))
            rect = self._auto_layout_normalize_rect_candidate(item.get('rect'), 'rect')
            reason = ''
            if not use_inpaint:
                reason = 'use_inpaint_false'
            elif not rect:
                reason = 'missing_or_bad_rect'
            elif not (text_raw.strip() or translated_raw.strip() or display_raw.strip() or layout_raw.strip()):
                reason = 'empty_text_and_translation'
            else:
                reason = 'eligible_or_targetable'
            info.update({
                'item_id': item.get('id'),
                'rect': item.get('rect'),
                'normalized_rect': rect,
                'use_inpaint': use_inpaint,
                'use_translate': item.get('use_translate'),
                'use_output': item.get('use_output'),
                'use_ocr': item.get('use_ocr'),
                'rasterized_text': bool(item.get('rasterized_text')),
                'hidden': bool(item.get('hidden') or item.get('is_hidden')),
                'text_key': text_key,
                'text_len_raw': len(text_raw),
                'translated_len_raw': len(translated_raw),
                'display_len_raw': len(display_raw),
                'effective_len_raw': len(layout_raw),
                'effective_compact_len': len(compact),
                'text_preview_raw': text_raw.replace('\r', '\\r').replace('\n', '\\n')[:80],
                'translated_preview_raw': translated_raw.replace('\r', '\\r').replace('\n', '\\n')[:80],
                'effective_preview_raw': layout_raw.replace('\r', '\\r').replace('\n', '\\n')[:80],
                'font_size': item.get('font_size'),
                'font_family': item.get('font_family'),
                'stroke_width': item.get('stroke_width'),
                'line_spacing': item.get('line_spacing'),
                'auto_layout_mode': item.get('auto_layout_mode'),
                'diag_reason': reason,
            })
            # OCR/마스크/원본 박스 후보가 있는지 한 번에 보이게 남긴다.
            for key in ('ocr_rect', 'ocr_crop_rect', 'text_mask_rect', 'mask_rect', 'detector_rect', 'source_rect', 'original_rect', 'initial_rect', 'raw_rect', 'bbox', 'box'):
                if key in item:
                    info[key] = item.get(key)
        except Exception as exc:
            info.setdefault('diag_reason', 'diag_error')
            info['diag_error'] = repr(exc)
        return info

    def _log_auto_adjust_page_linkage_scan(self, page_idx, targets):
        """자동 조정 전에 페이지 데이터/화면 텍스트 박스 연결 상태를 전부 로깅한다.

        목적:
        - 빨간 박스는 보이는데 자동 조정 대상에 안 들어가는 항목 탐지
        - translated_text/text가 비어 있는 빈 박스 탐지
        - use_inpaint=False 등으로 target에서 빠진 항목 탐지
        - 실제 final scene에 떠 있는 텍스트 아이템과 data item의 불일치 탐지
        """
        try:
            if not hasattr(self, 'audit_boundary_event'):
                return
            curr = (self.data.get(page_idx) or {}) if hasattr(self, 'data') else {}
            data_items = list(curr.get('data', []) or [])
            targets = list(targets or [])
            target_obj_ids = {id(x) for x in targets if isinstance(x, dict)}
            target_ids = {str(x.get('id')) for x in targets if isinstance(x, dict) and x.get('id') is not None}
            self.audit_boundary_event(
                'TEXT_AUTO_ADJUST_PAGE_SCAN_START',
                page_idx=page_idx,
                data_count=len(data_items),
                target_count=len(targets),
                target_ids=list(target_ids)[:80],
            )
            missing_target_count = 0
            empty_box_count = 0
            use_inpaint_false_count = 0
            for idx, item in enumerate(data_items):
                info = self._auto_adjust_item_text_state_for_diag(item)
                will_target = bool(id(item) in target_obj_ids or (isinstance(item, dict) and str(item.get('id')) in target_ids))
                info.update({
                    'page_idx': page_idx,
                    'data_index': idx,
                    'will_auto_adjust': will_target,
                })
                reason = str(info.get('diag_reason') or '')
                if not will_target:
                    missing_target_count += 1
                if reason == 'empty_text_and_translation':
                    empty_box_count += 1
                if reason == 'use_inpaint_false':
                    use_inpaint_false_count += 1
                self.audit_boundary_event('TEXT_AUTO_ADJUST_PAGE_ITEM_SCAN', **info)
            self.audit_boundary_event(
                'TEXT_AUTO_ADJUST_PAGE_SCAN_DONE',
                page_idx=page_idx,
                data_count=len(data_items),
                target_count=len(targets),
                non_target_count=missing_target_count,
                empty_box_count=empty_box_count,
                use_inpaint_false_count=use_inpaint_false_count,
            )
            self._log_auto_adjust_scene_linkage_scan(page_idx=page_idx, target_ids=target_ids)
        except Exception as exc:
            try:
                self.audit_boundary_event('TEXT_AUTO_ADJUST_PAGE_SCAN_ERROR', page_idx=page_idx, error=repr(exc))
            except Exception:
                pass

    def _log_auto_adjust_scene_linkage_scan(self, page_idx=None, target_ids=None):
        """현재 final scene에 실제로 떠 있는 텍스트 박스도 함께 진단한다."""
        try:
            if not hasattr(self, 'audit_boundary_event'):
                return
            view = getattr(self, 'view', None)
            scene = None
            if view is not None:
                try:
                    scene = view.scene() if callable(getattr(view, 'scene', None)) else getattr(view, 'scene', None)
                except Exception:
                    scene = getattr(view, 'scene', None)
            if scene is None:
                self.audit_boundary_event('TEXT_AUTO_ADJUST_SCENE_SCAN_SKIP', page_idx=page_idx, reason='no_scene')
                return
            scene_items = []
            try:
                scene_items = list(scene.items() or [])
            except Exception:
                scene_items = []
            target_ids = set(str(x) for x in (target_ids or set()))
            scanned = 0
            text_like = 0
            for sidx, obj in enumerate(scene_items[:300]):
                data = getattr(obj, 'data', None)
                if not isinstance(data, dict):
                    continue
                # TypesettingItem/TextItem 계열만 잡는다. data에 rect/id/text 계열이 있으면 충분히 유효하다.
                if not any(k in data for k in ('rect', 'translated_text', 'text', 'font_size')):
                    continue
                text_like += 1
                info = self._auto_adjust_item_text_state_for_diag(data)
                try:
                    br = obj.sceneBoundingRect() if callable(getattr(obj, 'sceneBoundingRect', None)) else None
                    if br is not None:
                        info['scene_bounding_rect'] = [round(float(br.x()), 2), round(float(br.y()), 2), round(float(br.width()), 2), round(float(br.height()), 2)]
                except Exception:
                    pass
                try:
                    ar = obj.text_area_rect() if callable(getattr(obj, 'text_area_rect', None)) else None
                    if ar is not None:
                        # text_area_rect는 item local 좌표일 수 있으므로 원 data rect와 함께 보조로만 기록한다.
                        info['scene_text_area_rect_local'] = [round(float(ar.x()), 2), round(float(ar.y()), 2), round(float(ar.width()), 2), round(float(ar.height()), 2)]
                except Exception:
                    pass
                try:
                    info['is_selected_scene_item'] = bool(obj.isSelected()) if callable(getattr(obj, 'isSelected', None)) else False
                except Exception:
                    pass
                info.update({
                    'page_idx': page_idx,
                    'scene_index': sidx,
                    'scene_item_type': type(obj).__name__,
                    'target_id_match': str(info.get('item_id')) in target_ids if info.get('item_id') is not None else False,
                })
                self.audit_boundary_event('TEXT_AUTO_ADJUST_SCENE_TEXT_ITEM_SCAN', **info)
                scanned += 1
                if scanned >= 120:
                    break
            self.audit_boundary_event('TEXT_AUTO_ADJUST_SCENE_SCAN_DONE', page_idx=page_idx, scene_item_count=len(scene_items), text_like_count=text_like, logged_count=scanned)
        except Exception as exc:
            try:
                self.audit_boundary_event('TEXT_AUTO_ADJUST_SCENE_SCAN_ERROR', page_idx=page_idx, error=repr(exc))
            except Exception:
                pass

    def _fit_space_language_text_for_item(self, item, lang='en', page_idx=None):
        """영어/한국어: 텍스트 자동 조정.

        한국어는 후보 줄내림을 여러 개 만들고 점수를 매겨 가장 사각형에 가까운 배치를 자동 적용한다.
        폰트 크기는 기존 OCR 좌표 기반 추정식을 최초값으로 쓰고, 박스 초과/이웃 OCR 겹침이 있으면 줄인다.
        """
        self._auto_adjust_diag('TEXT_AUTO_ADJUST_FORCE_ENTER', item, lang_requested=lang, page_idx=page_idx)
        fit_rect, fit_source = self._auto_layout_resolve_fit_rect_for_item(item)
        if not fit_rect or len(fit_rect) < 4:
            self._auto_adjust_diag('TEXT_AUTO_ADJUST_SKIP', item, reason='no_fit_rect', fit_rect=fit_rect, fit_box_source=fit_source, lang_requested=lang)
            return False
        try:
            if hasattr(self, 'audit_boundary_event'):
                old_rect = self._auto_layout_normalize_rect_candidate(item.get('rect'), 'rect') if isinstance(item, dict) else None
                self.audit_boundary_event(
                    'TEXT_AUTO_ADJUST_BOX_RESOLVED',
                    item_id=item.get('id') if isinstance(item, dict) else None,
                    old_rect=old_rect,
                    fit_rect=fit_rect,
                    fit_box_source=fit_source,
                    manual_text_rect=bool(item.get('manual_text_rect')) if isinstance(item, dict) else False,
                    text_anchor_mode=item.get('text_anchor_mode') if isinstance(item, dict) else '',
                )
        except Exception:
            pass
        fit_rect_changed = self._auto_layout_apply_fit_rect_if_needed(item, fit_rect, fit_source)
        # 계산은 fit_rect로 하되, item['rect'](OCR 영역)는 절대 변경하지 않는다.
        rect = list(fit_rect or (item.get('rect') or [0, 0, 1, 1]))
        self._auto_adjust_diag(
            'TEXT_AUTO_ADJUST_TARGET_RECT',
            item,
            fit_rect=fit_rect,
            fit_box_source=fit_source,
            fit_rect_changed=bool(fit_rect_changed),
            effective_rect=rect,
            ocr_rect=item.get('rect') if isinstance(item, dict) else None,
            policy='effective_fit_rect_only_ocr_rect_immutable',
        )

        text_key, original = self._auto_layout_text_key_and_value(item)
        if not str(original or '').strip():
            self._auto_adjust_diag('TEXT_AUTO_ADJUST_SKIP', item, reason='empty_original', text_key=text_key, fit_rect=fit_rect, fit_box_source=fit_source)
            return False

        lang = self._normalize_ocr_lang_for_layout(lang) or 'en'
        source_text = self.normalize_auto_wrap_source_text_for_lang(original, lang)
        if not source_text.strip():
            self._auto_adjust_diag('TEXT_AUTO_ADJUST_SKIP', item, reason='empty_normalized_source', text_key=text_key, original_len=len(str(original or '')), lang=lang)
            return False
        self._auto_adjust_diag('TEXT_AUTO_ADJUST_SOURCE_READY', item, lang=lang, text_key=text_key, original_len=len(str(original or '')), normalized_len=len(str(source_text or '')), source_preview=str(source_text or '').replace('\n', '\\n')[:80])

        self.ensure_item_style_for_auto(item)

        # OCR rect가 페이지 가장자리에서 지나치게 좁게 잘린 경우,
        # 작은 박스 안에 우겨넣지 말고 안쪽 방향으로 계산 박스를 먼저 넓힌다.
        # 최종 충돌은 뒤의 전역 겹침 보정/최종 재검사가 처리한다.
        try:
            if lang == 'ko' and self.text_item_writing_direction(item) != 'vertical':
                expanded_rect, expand_info = self._auto_layout_expand_narrow_edge_fit_rect_for_item(
                    item, rect, source_text, page_idx=page_idx
                )
                if expanded_rect and list(expanded_rect) != list(self._auto_layout_normalize_rect_candidate(rect, 'rect') or rect):
                    old_rect_for_expand = self._auto_layout_normalize_rect_candidate(item.get('rect'), 'rect') if isinstance(item, dict) else None
                    item.setdefault('auto_layout_narrow_edge_original_rect', list(old_rect_for_expand or rect))
                    # OCR rect는 불변. 좁은 가장자리 보정은 계산용 rect에만 적용한다.
                    item['auto_layout_fit_rect'] = list(expanded_rect)
                    item['auto_layout_fit_box_source'] = 'narrow_edge_expand'
                    item['auto_layout_narrow_edge_expanded'] = True
                    item['auto_layout_narrow_edge_expand_info'] = dict(expand_info or {})
                    rect = list(expanded_rect)
                    try:
                        self._auto_adjust_diag(
                            'TEXT_AUTO_ADJUST_NARROW_EDGE_FIT_RECT_EXPANDED',
                            item,
                            ocr_rect_locked=True,
                            ocr_rect=list(old_rect_for_expand or []),
                            effective_rect=list(expanded_rect),
                            **(expand_info or {}),
                        )
                    except Exception:
                        pass
        except Exception as exc:
            try:
                self._auto_adjust_diag('TEXT_AUTO_ADJUST_NARROW_EDGE_FIT_RECT_EXPAND_ERROR', item, error=repr(exc))
            except Exception:
                pass

        try:
            box_w = max(1, int(rect[2]))
            box_h = max(1, int(rect[3]))
        except Exception as exc:
            self._auto_adjust_diag('TEXT_AUTO_ADJUST_SKIP', item, reason='bad_rect', rect=rect, error=repr(exc))
            return False

        try:
            family = item.get('font_family') or self.cb_font.currentFont().family()
        except Exception:
            family = item.get('font_family') or 'Arial'
        try:
            fallback_size = int(item.get('font_size', self.sb_font_size.value()) or self.sb_font_size.value())
        except Exception:
            fallback_size = 24
        try:
            stroke = int(item.get('stroke_width', 0) or 0)
        except Exception:
            stroke = 0

        if self.text_item_writing_direction(item) == 'vertical':
            self._auto_adjust_diag(
                'TEXT_AUTO_ADJUST_VERTICAL_ROUTE',
                item,
                lang=lang,
                policy='preserve_ocr_rect_and_source_text_fit_font_size_only',
                text_key=text_key,
            )
            return self._fit_vertical_text_for_item(
                item,
                text_key=text_key,
                original=original,
                fit_rect_changed=fit_rect_changed,
                lang=lang,
                family=family,
                fallback_size=fallback_size,
                stroke=stroke,
                box_w=box_w,
                box_h=box_h,
                page_idx=page_idx,
            )

        if lang == 'ko':
            # 한국어 자동 조정은 이제 점수 후보 난립 방식이 아니라 고정 4단계로만 간다.
            # 1) OCR 영역 비율 확인
            # 2) 비율대로 줄내림 형상 먼저 확정
            # 3) 확정된 줄 형상을 OCR 영역에 최대 크기로 맞춤
            # 4) 다른 텍스트/OCR 영역과 겹치면 줄 구조는 유지한 채 크기만 줄임
            # 자동 조정은 OCR 박스의 외곽선까지 쓰는 것이 기준이다.
            # stroke_width는 렌더링 측정에는 포함하지만, fit 영역에서 좌우/상하 여백으로 빼지 않는다.
            max_w = max(1, int(box_w * 1.00))
            max_h = max(1, int(box_h * 1.00))
            box_ratio = max(0.12, min(8.0, float(box_w) / max(1.0, float(box_h))))
            compact_len = max(1, self._ko_compact_len(source_text))
            left_neighbors = self._neighbor_rects_for_auto_adjust(item, page_idx=page_idx)

            # 행간은 사용자가 직접 맞춘 스타일 값이다.
            # 자동 조정은 줄내림/글자 크기만 바꾸고, line_spacing 값은 절대 변경하지 않는다.
            try:
                old_line_spacing_for_auto = int(item.get('line_spacing', 100) or 100)
            except Exception:
                old_line_spacing_for_auto = 100

            # 줄내림 형상 판단용 기준 폰트. 실제 크기는 뒤의 binary search에서 따로 정한다.
            shape_size = 96
            _shape_font, shape_fm, _shape_lsp, shape_char_w, _shape_ch, shape_letter_spacing = self._auto_layout_item_style_metrics(item, family, shape_size)

            def _line_count_candidates():
                return ko_linebreak_rules.line_count_candidates(compact_len, box_ratio)

            def _split_ko_to_line_count(text, target_lines):
                # OCR 박스 비율을 넘겨 줄내림 후보 자체가 박스 형상에 가까워지게 한다.
                # 글자 크기는 뒤의 binary search에서 줄 구조를 유지한 채 조정한다.
                lines = ko_linebreak_rules.split_to_line_count(text, target_lines, box_ratio=box_ratio)
                return self._ko_repair_bound_particle_lines(lines, shape_fm, max_w, letter_spacing=shape_letter_spacing, allow_w_ratio=ko_linebreak_rules.BOUND_REPAIR_WIDTH_ALLOW_RATIO)

            def _measure_shape_ratio(lines):
                mw, mh = self._measure_wrapped_lines_for_auto_fit(item, lines, family, shape_size, stroke=stroke)
                return max(0.08, float(mw) / max(1.0, float(mh))), mw, mh

            def _neighbor_text_rects_for_auto_adjust_force():
                """다른 OCR 박스가 아니라, 실제 화면에 올라온 다른 텍스트 덩어리만 충돌 대상으로 본다."""
                # 2-pass 자동 조정의 1차 패스에서는 겹침을 절대 보지 않는다.
                # 먼저 모든 텍스트를 자기 OCR 박스 기준으로 최대화한 뒤,
                # 2차 패스에서 오른쪽부터 인접 텍스트끼리만 신뢰 가능한 final rect로 비교한다.
                if bool(getattr(self, '_auto_text_adjust_ignore_neighbors', False)):
                    try:
                        self._auto_adjust_diag(
                            'TEXT_AUTO_ADJUST_NEIGHBOR_SCAN_SKIPPED',
                            item,
                            reason='first_pass_ignore_neighbors',
                            policy='two_pass_resize_first_overlap_second',
                        )
                    except Exception:
                        pass
                    return []
                try:
                    curr = self.data.get(page_idx if page_idx is not None else self.idx) or {}
                except Exception:
                    curr = {}
                out = []
                try:
                    rect0 = item.get('rect') or [0, 0, 1, 1]
                    x0, y0, w0, h0 = [float(v) for v in rect0[:4]]
                    guard = QRectF(x0 - w0 * 1.25, y0 - h0 * 1.25, max(1.0, w0 * 3.5), max(1.0, h0 * 3.5))
                except Exception:
                    guard = None
                for other in curr.get('data', []) or []:
                    if other is item or not isinstance(other, dict):
                        continue
                    try:
                        _k, other_text = self._auto_layout_text_key_and_value(other)
                    except Exception:
                        other_text = other.get('translated_text') or other.get('text') or ''
                    if not str(other_text or '').strip():
                        continue
                    try:
                        other_rect = other.get('rect') or [0, 0, 1, 1]
                        if guard is not None:
                            ox, oy, ow, oh = [float(v) for v in other_rect[:4]]
                            if not guard.intersects(QRectF(ox, oy, max(1.0, ow), max(1.0, oh))):
                                continue
                    except Exception:
                        pass
                    try:
                        other_lines = [ln.strip() for ln in str(other_text).replace('\r\n', '\n').replace('\r', '\n').split('\n') if ln.strip()]
                        if not other_lines:
                            other_lines = [str(other_text).strip()]
                        ofamily = other.get('font_family') or family
                        osize = max(1, int(other.get('font_size', fallback_size) or fallback_size))
                        ostroke = max(0, int(other.get('stroke_width', 0) or 0))
                        rrs = self._candidate_text_line_scene_rects(other, other_lines, ofamily, osize, stroke=ostroke)
                        if rrs:
                            # Text-to-text collision uses line-level visible text bounds only.
                            # No OCR-box collision, no safety padding.
                            out.extend(rrs)
                    except Exception:
                        continue
                return out

            text_neighbors = _neighbor_text_rects_for_auto_adjust_force()

            def candidate_text_overlap_info(lines, size):
                # OCR/말풍선 영역끼리 겹치는 건 자동 조정 제한 사유가 아니다.
                # 실제 화면에 렌더되는 다른 텍스트 덩어리의 보이는 bounds와만 비교한다.
                # 추가 여백/패딩 없음: visible text vs visible text only.
                try:
                    if not text_neighbors:
                        return False, None
                    crects = self._candidate_text_line_scene_rects(item, lines, family, int(size), stroke=stroke)
                    if not crects:
                        return False, None
                    for idx_cr, crect in enumerate(crects):
                        for idx_nr, nr in enumerate(text_neighbors):
                            if not crect.intersects(nr):
                                continue
                            inter = crect.intersected(nr)
                            ow = max(0.0, float(inter.width()))
                            oh = max(0.0, float(inter.height()))
                            area = ow * oh
                            cand_area = max(1.0, float(crect.width()) * float(crect.height()))
                            neigh_area = max(1.0, float(nr.width()) * float(nr.height()))
                            min_area = max(1.0, min(cand_area, neigh_area))
                            # 자동 텍스트 조정에서는 텍스트끼리 겹침을 허용하지 않는다.
                            # OCR 박스끼리의 겹침은 무시하지만, 실제 줄 bounds가 1px이라도
                            # 겹치면 후보에서 제외하고 최종 보정에서 다시 줄인다.
                            if ow <= 0.0 or oh <= 0.0 or area <= 0.0:
                                continue
                            return True, {
                                'candidate_rect': [round(crect.x(), 2), round(crect.y(), 2), round(crect.width(), 2), round(crect.height(), 2)],
                                'candidate_line_index': int(idx_cr),
                                'neighbor_index': int(idx_nr),
                                'neighbor_rect': [round(nr.x(), 2), round(nr.y(), 2), round(nr.width(), 2), round(nr.height(), 2)],
                                'overlap_w': round(ow, 2),
                                'overlap_h': round(oh, 2),
                                'overlap_area': round(area, 2),
                                'min_area': round(min_area, 2),
                                'area_ratio': round(area / min_area, 4),
                                'policy': 'no_text_overlap_allowed_ignore_ocr_boxes',
                            }
                except Exception as exc:
                    return False, {'error': repr(exc)}
                return False, None

            if text_neighbors:
                try:
                    self._auto_adjust_diag(
                        'TEXT_AUTO_ADJUST_NEIGHBOR_TEXT_RECTS',
                        item,
                        overlap_mode='no_text_overlap_allowed_ignore_ocr_boxes',
                        neighbor_text_count=len(text_neighbors),
                        neighbor_rects=str([[round(r.x(), 2), round(r.y(), 2), round(r.width(), 2), round(r.height(), 2)] for r in text_neighbors[:8]]),
                    )
                except Exception:
                    pass

            def _required_fill_for_box():
                # 최소 합격선은 ysb/core/korean_linebreak_rules.py에서 관리한다.
                return ko_linebreak_rules.required_fill_for_box(box_ratio)

            req_w, req_h = _required_fill_for_box()
            if compact_len <= 4:
                # 짧은 말도 작은 상태로 통과시키지 않는다.
                # 합격선을 낮추지 않고, 필요하면 emergency split에서 더 찢어서 키운다.
                pass

            start_size = self._auto_text_adjust_initial_font_size(item, page_idx=page_idx, fallback_size=fallback_size)
            short_side = min(float(box_w), float(box_h))
            long_side = max(float(box_w), float(box_h))
            max_size = int(max(float(start_size) * 12.0, short_side * 3.5, long_side * 2.2, 72.0))
            max_size = max(1, min(960, max_size))
            hard_width_limit = max_w * ko_linebreak_rules.HARD_WIDTH_LIMIT_RATIO
            try:
                line_candidates_diag = _line_count_candidates()
            except Exception:
                line_candidates_diag = []
            self._auto_adjust_diag(
                'TEXT_AUTO_ADJUST_FONT_LOOP_ENTER',
                item,
                lang=lang,
                box_w=box_w,
                box_h=box_h,
                box_ratio=round(float(box_ratio), 4),
                compact_len=compact_len,
                max_w=max_w,
                max_h=max_h,
                hard_width_limit=round(float(hard_width_limit), 2),
                start_size=start_size,
                max_size=max_size,
                fallback_size=fallback_size,
                stroke=stroke,
                line_count_candidates=line_candidates_diag,
                neighbor_text_count=len(text_neighbors),
                fit_space_policy='ocr_box_full_no_inner_margin',
                overlap_policy='candidate_stage_no_text_overlap_page_postpass_final_gap',
                measurement_policy='stroke_counted_as_visible_text_not_margin',
                final_margin_policy='final_page_postpass_requires_1px_gap',
                line_spacing_policy='preserve_user_setting',
                old_line_spacing=old_line_spacing_for_auto,
            )

            def _measure_lines_at(lines, size):
                return self._measure_wrapped_lines_for_auto_fit(item, lines, family, int(size), stroke=stroke)

            def _fit_max_size_for_lines(lines, allow_overlap=False):
                # 무조건 크게 키운 뒤, 폭/높이/다른 텍스트 겹침에 걸릴 때만 줄인다.
                # 겹침 판정은 visible text bounds only. 추가 여백/패딩은 쓰지 않는다.
                lo, hi = 1, max_size
                best = 1
                best_m = _measure_lines_at(lines, 1)
                overlap_cache = {}
                diag = {
                    'overlap_block_count': 0,
                    'overlap_check_count': 0,
                    'last_overlap_block_size': None,
                    'last_overlap_info': None,
                    'final_overlap': False,
                    'final_overlap_info': None,
                    'final_overlap_check_size': None,
                    'width_block_count': 0,
                    'height_block_count': 0,
                    'last_width_block_size': None,
                    'last_height_block_size': None,
                }

                def _cached_overlap(size):
                    key = int(size)
                    if key not in overlap_cache:
                        diag['overlap_check_count'] += 1
                        overlap_cache[key] = candidate_text_overlap_info(lines, key)
                    return overlap_cache[key]

                while lo <= hi:
                    mid = (lo + hi) // 2
                    mw, mh = _measure_lines_at(lines, mid)
                    ok = True
                    if mw > hard_width_limit:
                        ok = False
                        diag['width_block_count'] += 1
                        diag['last_width_block_size'] = int(mid)
                    if mh > max_h:
                        ok = False
                        diag['height_block_count'] += 1
                        diag['last_height_block_size'] = int(mid)
                    if ok and (not allow_overlap):
                        ov, ovinfo = _cached_overlap(mid)
                        if ov:
                            ok = False
                            diag['overlap_block_count'] += 1
                            diag['last_overlap_block_size'] = int(mid)
                            diag['last_overlap_info'] = ovinfo
                    if ok:
                        best = mid
                        best_m = (mw, mh)
                        lo = mid + 1
                    else:
                        hi = mid - 1

                if not allow_overlap:
                    final_ov, final_info = _cached_overlap(best)
                    diag['final_overlap'] = bool(final_ov)
                    diag['final_overlap_info'] = final_info
                    diag['final_overlap_check_size'] = int(best)
                return int(best), best_m[0], best_m[1], diag

            def _touch_ok_for_lines(lines, fill_w, fill_h):
                return ko_linebreak_rules.touch_ok_for_lines(
                    lines, fill_w, fill_h,
                    compact_length=compact_len,
                    box_ratio=box_ratio,
                    req_w=req_w,
                    req_h=req_h,
                )

            def _near_touch_ok(fill_w, fill_h):
                return ko_linebreak_rules.near_touch_ok(fill_w, fill_h, req_w, req_h)

            hard_candidates = []
            seen_lines = set()
            emergency_pool = []
            # 강제 재루프: 줄 수 후보를 전부 돌리고, 각 줄 구조를 최대 크기까지 키운 뒤 합격선 검사.
            for line_count in _line_count_candidates():
                lines = _split_ko_to_line_count(source_text, line_count)
                cleaned_key = tuple(str(x or '').strip() for x in (lines or []) if str(x or '').strip())
                if not cleaned_key or cleaned_key in seen_lines:
                    continue
                seen_lines.add(cleaned_key)
                lines = list(cleaned_key)
                size, mw, mh, fit_diag = _fit_max_size_for_lines(lines, allow_overlap=False)
                fill_w = float(mw) / max(1.0, float(max_w))
                fill_h = float(mh) / max(1.0, float(max_h))
                try:
                    shape_ratio = max(0.08, float(mw) / max(1.0, float(mh)))
                    ratio_cost = abs(math.log(max(0.08, shape_ratio) / max(0.08, box_ratio)))
                except Exception:
                    shape_ratio = 1.0
                    ratio_cost = 9.0
                badness = self._ko_linebreak_badness(lines)
                touch = _touch_ok_for_lines(lines, fill_w, fill_h)
                deficit = max(0.0, req_w - fill_w) + max(0.0, req_h - fill_h)
                # 합격 후보 최우선. 불합격 후보는 작은 fallback이 아니라 최대치 후보 중 deficit이 가장 작은 것만 보관한다.
                score = ko_linebreak_rules.candidate_score(
                    touch=bool(touch),
                    badness=float(badness),
                    deficit=float(deficit),
                    ratio_cost=float(ratio_cost),
                    size=int(size),
                    fill_w=float(fill_w),
                    fill_h=float(fill_h),
                )
                cand = {
                    'score': score,
                    'lines': lines,
                    'size': int(size),
                    'mw': float(mw),
                    'mh': float(mh),
                    'fill_w': float(fill_w),
                    'fill_h': float(fill_h),
                    'touch': bool(touch),
                    'near_touch': bool(_near_touch_ok(fill_w, fill_h)),
                    'deficit': float(deficit),
                    'shape_ratio': float(shape_ratio),
                    'badness': float(badness),
                    'overlap': bool((fit_diag or {}).get('final_overlap')),
                    'fit_diag': fit_diag,
                    'line_count_target': int(line_count),
                    'emergency': False,
                }
                hard_candidates.append(cand)
                self._auto_adjust_diag(
                    'TEXT_AUTO_ADJUST_CANDIDATE',
                    item,
                    phase='normal',
                    line_count_target=int(line_count),
                    size=int(size),
                    measured_w=round(float(mw), 2),
                    measured_h=round(float(mh), 2),
                    fill_w=round(float(fill_w), 4),
                    fill_h=round(float(fill_h), 4),
                    req_w=round(float(req_w), 4),
                    req_h=round(float(req_h), 4),
                    touch_ok=bool(touch),
                    near_touch_ok=bool(_near_touch_ok(fill_w, fill_h)),
                    deficit=round(float(deficit), 4),
                    badness=round(float(badness), 4),
                    overlap=bool(cand.get('overlap')),
                    overlap_block_count=int((fit_diag or {}).get('overlap_block_count') or 0),
                    overlap_check_count=int((fit_diag or {}).get('overlap_check_count') or 0),
                    final_overlap=bool((fit_diag or {}).get('final_overlap')),
                    final_overlap_check_size=(fit_diag or {}).get('final_overlap_check_size'),
                    width_block_count=int((fit_diag or {}).get('width_block_count') or 0),
                    height_block_count=int((fit_diag or {}).get('height_block_count') or 0),
                    last_overlap_block_size=(fit_diag or {}).get('last_overlap_block_size'),
                    last_width_block_size=(fit_diag or {}).get('last_width_block_size'),
                    last_height_block_size=(fit_diag or {}).get('last_height_block_size'),
                    overlap_info=str((fit_diag or {}).get('last_overlap_info'))[:240],
                    final_overlap_info=str((fit_diag or {}).get('final_overlap_info'))[:240],
                    lines=' / '.join(lines)[:160],
                )

            self._auto_adjust_diag(
                'TEXT_AUTO_ADJUST_CANDIDATE_SUMMARY',
                item,
                phase='normal_done',
                candidate_count=len(hard_candidates),
                passing_count=len([c for c in hard_candidates if c.get('touch')]),
                seen_line_shapes=len(seen_lines),
            )

            # 그래도 합격선에 못 닿으면 마지막 강제 재루프.
            # 단, 번역문 띄어쓰기는 절대 삭제하지 않는다. 이전 emergency split은
            # 공백을 제거한 chars 기준으로 조각을 만들면서 '야~슬 / 슬수업'처럼
            # 원래 있던 띄어쓰기를 없앨 수 있었다. 여기서는 같은 줄 수를 다시
            # 시도하더라도 _split_ko_to_line_count()를 통해 기존 공백 토큰을 보존한다.
            if not any(c.get('touch') for c in hard_candidates):
                raw = re.sub(r'\s+', ' ', str(source_text or '').strip())
                max_emergency_lines = max(1, min(ko_linebreak_rules.MAX_LINE_COUNT, self._ko_compact_len(raw)))
                for line_count in _line_count_candidates() + list(range(1, max_emergency_lines + 1)):
                    n = max(1, min(max_emergency_lines, int(line_count or 1)))
                    if n <= 1:
                        lines = [raw]
                    else:
                        lines = _split_ko_to_line_count(raw, n)
                    # 안전망: 줄 후보가 원문에 있던 공백을 모두 잃어버렸다면 후보를 폐기한다.
                    # 자동조정은 줄바꿈만 추가할 수 있고, 기존 띄어쓰기를 삭제하면 안 된다.
                    try:
                        if ko_linebreak_rules.would_remove_inner_spaces(raw, lines):
                            self._auto_adjust_diag(
                                'TEXT_AUTO_ADJUST_CANDIDATE_REJECTED',
                                item,
                                reason='would_remove_spaces',
                                phase='emergency',
                                line_count_target=int(line_count),
                                raw_preview=raw[:120],
                                lines=' / '.join(lines)[:160],
                            )
                            continue
                    except Exception:
                        pass
                    cleaned_key = tuple(x for x in lines if x)
                    if not cleaned_key or cleaned_key in seen_lines:
                        continue
                    seen_lines.add(cleaned_key)
                    lines = list(cleaned_key)
                    size, mw, mh, fit_diag = _fit_max_size_for_lines(lines, allow_overlap=False)
                    fill_w = float(mw) / max(1.0, float(max_w))
                    fill_h = float(mh) / max(1.0, float(max_h))
                    try:
                        shape_ratio = max(0.08, float(mw) / max(1.0, float(mh)))
                        ratio_cost = abs(math.log(max(0.08, shape_ratio) / max(0.08, box_ratio)))
                    except Exception:
                        shape_ratio = 1.0
                        ratio_cost = 9.0
                    badness = self._ko_linebreak_badness(lines) + ko_linebreak_rules.EMERGENCY_BADNESS_PENALTY
                    touch = _touch_ok_for_lines(lines, fill_w, fill_h)
                    deficit = max(0.0, req_w - fill_w) + max(0.0, req_h - fill_h)
                    score = ko_linebreak_rules.candidate_score(
                        touch=bool(touch),
                        badness=float(badness),
                        deficit=float(deficit),
                        ratio_cost=float(ratio_cost),
                        size=int(size),
                        fill_w=float(fill_w),
                        fill_h=float(fill_h),
                    )
                    ecand = {
                        'score': score,
                        'lines': lines,
                        'size': int(size),
                        'mw': float(mw),
                        'mh': float(mh),
                        'fill_w': float(fill_w),
                        'fill_h': float(fill_h),
                        'touch': bool(touch),
                        'near_touch': bool(_near_touch_ok(fill_w, fill_h)),
                        'deficit': float(deficit),
                        'shape_ratio': float(shape_ratio),
                        'badness': float(badness),
                        'overlap': bool((fit_diag or {}).get('final_overlap')),
                        'fit_diag': fit_diag,
                        'line_count_target': int(line_count),
                        'emergency': True,
                    }
                    hard_candidates.append(ecand)
                    self._auto_adjust_diag(
                        'TEXT_AUTO_ADJUST_CANDIDATE',
                        item,
                        phase='emergency',
                        line_count_target=int(line_count),
                        size=int(size),
                        measured_w=round(float(mw), 2),
                        measured_h=round(float(mh), 2),
                        fill_w=round(float(fill_w), 4),
                        fill_h=round(float(fill_h), 4),
                        req_w=round(float(req_w), 4),
                        req_h=round(float(req_h), 4),
                        touch_ok=bool(touch),
                        near_touch_ok=bool(_near_touch_ok(fill_w, fill_h)),
                        deficit=round(float(deficit), 4),
                        badness=round(float(badness), 4),
                        overlap=bool(ecand.get('overlap')),
                        overlap_block_count=int((fit_diag or {}).get('overlap_block_count') or 0),
                        overlap_check_count=int((fit_diag or {}).get('overlap_check_count') or 0),
                        final_overlap=bool((fit_diag or {}).get('final_overlap')),
                        final_overlap_check_size=(fit_diag or {}).get('final_overlap_check_size'),
                        width_block_count=int((fit_diag or {}).get('width_block_count') or 0),
                        height_block_count=int((fit_diag or {}).get('height_block_count') or 0),
                        last_overlap_block_size=(fit_diag or {}).get('last_overlap_block_size'),
                        last_width_block_size=(fit_diag or {}).get('last_width_block_size'),
                        last_height_block_size=(fit_diag or {}).get('last_height_block_size'),
                        overlap_info=str((fit_diag or {}).get('last_overlap_info'))[:240],
                        final_overlap_info=str((fit_diag or {}).get('final_overlap_info'))[:240],
                        lines=' / '.join(lines)[:160],
                    )

            self._auto_adjust_diag(
                'TEXT_AUTO_ADJUST_CANDIDATE_SUMMARY',
                item,
                phase='final',
                candidate_count=len(hard_candidates),
                passing_count=len([c for c in hard_candidates if c.get('touch')]),
                seen_line_shapes=len(seen_lines),
            )

            if not hard_candidates:
                self._auto_adjust_diag('TEXT_AUTO_ADJUST_SKIP', item, reason='no_hard_candidates_after_loop', max_size=max_size, line_candidates=line_candidates_diag)
                return False

            # 선택 우선순위:
            # 1) 명백한 합격 후보 + 근접 합격 후보를 함께 본다.
            # 2) 근접 합격이더라도 글자가 더 크고 OCR 박스를 거의 채우면 통과 후보보다 우선할 수 있다.
            # 3) 단, 세로로 긴 OCR 박스에서 합격 후보가 하나도 없으면 1줄 초소형 후보보다
            #    여러 줄 후보를 우선한다. 이때 OCR 박스/행간/기존 스타일은 건드리지 않는다.
            passing = [c for c in hard_candidates if c.get('touch')]
            near_passing = [c for c in hard_candidates if (not c.get('touch')) and c.get('near_touch')]
            pool = (passing + near_passing) if (passing or near_passing) else hard_candidates

            def _candidate_select_key(c):
                return ko_linebreak_rules.candidate_select_key(c, compact_length=compact_len, box_ratio=box_ratio)

            selection_policy = 'prefer_larger_font_with_near_pass_and_reject_weak_one_line'
            vertical_fallback_multiline = False

            if not (passing or near_passing) and float(box_ratio) < 0.55 and int(compact_len) >= 4:
                multiline_pool = [
                    c for c in hard_candidates
                    if len([ln for ln in (c.get('lines') or []) if str(ln or '').strip()]) >= 2
                ]

                def _vertical_fallback_select_key(c):
                    try:
                        lines_v = [ln for ln in (c.get('lines') or []) if str(ln or '').strip()]
                        line_count_v = max(1, len(lines_v))
                    except Exception:
                        line_count_v = 1
                    try:
                        size_v = int(c.get('size') or 0)
                    except Exception:
                        size_v = 0
                    try:
                        deficit_v = float(c.get('deficit') or 0.0)
                    except Exception:
                        deficit_v = 9.0
                    try:
                        badness_v = float(c.get('badness') or 0.0)
                    except Exception:
                        badness_v = 0.0
                    try:
                        fill_w_v = min(ko_linebreak_rules.HARD_WIDTH_LIMIT_RATIO, float(c.get('fill_w') or 0.0))
                        fill_h_v = min(1.00, float(c.get('fill_h') or 0.0))
                    except Exception:
                        fill_w_v = fill_h_v = 0.0
                    try:
                        shape_ratio_v = max(0.08, float(c.get('shape_ratio') or 0.0))
                        ratio_cost_v = abs(math.log(max(0.08, shape_ratio_v) / max(0.08, float(box_ratio))))
                    except Exception:
                        ratio_cost_v = 9.0

                    # 합격 후보가 하나도 없는 세로형 박스에서는 "큰 글씨"보다 "OCR 박스 비율 유지"가 우선이다.
                    # 글자가 조금 작아져도 원래 세로 말풍선의 줄 수/비율을 지키는 쪽을 선택해야
                    # '뭐, 생으로 / 해도 괜찮 / 겠지.' 같은 가로 풀림을 막을 수 있다.
                    severe_badness = max(0.0, badness_v - 1.0)
                    light_badness = min(1.0, badness_v)
                    target_lines = max(3, min(8, int(math.ceil(float(compact_len) / 2.4))))
                    return (
                        -severe_badness,
                        -ratio_cost_v,
                        -deficit_v,
                        fill_h_v + fill_w_v * 0.20,
                        -abs(line_count_v - target_lines),
                        size_v,
                        -light_badness,
                    )

                if multiline_pool:
                    chosen = max(multiline_pool, key=_vertical_fallback_select_key)
                    vertical_fallback_multiline = True
                    selection_policy = 'vertical_fallback_preserve_ocr_ratio_when_no_passing'
                    try:
                        self._auto_adjust_diag(
                            'TEXT_AUTO_ADJUST_VERTICAL_FALLBACK_MULTILINE',
                            item,
                            box_ratio=round(float(box_ratio), 4),
                            compact_len=int(compact_len),
                            candidate_count=len(hard_candidates),
                            multiline_count=len(multiline_pool),
                            chosen_size=int(chosen.get('size') or 0),
                            chosen_deficit=round(float(chosen.get('deficit') or 0.0), 4),
                            chosen_badness=round(float(chosen.get('badness') or 0.0), 4),
                            lines=' / '.join(list(chosen.get('lines') or []))[:160],
                        )
                    except Exception:
                        pass
                else:
                    chosen = max(pool, key=_candidate_select_key)
            else:
                chosen = max(pool, key=_candidate_select_key)

            chosen_lines = list(chosen.get('lines') or [source_text])
            chosen_size = int(chosen.get('size') or 1)
            measured_w = float(chosen.get('mw') or 0.0)
            measured_h = float(chosen.get('mh') or 0.0)

            # 1차 줄내림이 OCR 영역을 넘기지 않으려고 지나치게 잘게 쪼갠 경우,
            # 아래 줄의 첫 어절을 위 줄 빈공간으로 올리는 후처리를 한 번 더 수행한다.
            # 행간/글자크기/박스는 그대로 두고 줄 구조만 줄인다.
            # 다만 세로형 fallback으로 여러 줄을 고른 경우는 한 줄로 되돌리지 않는다.
            line_compacted = False
            compact_diag = {'moved': 0, 'skipped': bool(vertical_fallback_multiline)}
            if vertical_fallback_multiline:
                try:
                    self._auto_adjust_diag(
                        'TEXT_AUTO_ADJUST_LINE_COMPACT_SKIPPED',
                        item,
                        reason='vertical_fallback_preserve_multiline',
                        box_ratio=round(float(box_ratio), 4),
                        compact_len=int(compact_len),
                        line_count=len(chosen_lines),
                        lines=' / '.join(chosen_lines)[:160],
                    )
                except Exception:
                    pass
            else:
                compacted_lines, line_compacted, compact_diag = self._auto_compact_wrapped_lines_fill_empty_space(
                    item,
                    chosen_lines,
                    family,
                    chosen_size,
                    stroke=stroke,
                    max_w=max_w,
                    max_h=max_h,
                    overlap_checker=candidate_text_overlap_info,
                )
            if line_compacted:
                chosen_lines = list(compacted_lines or chosen_lines)
                measured_w, measured_h = _measure_lines_at(chosen_lines, chosen_size)
                fill_w_after = float(measured_w) / max(1.0, float(max_w))
                fill_h_after = float(measured_h) / max(1.0, float(max_h))
                chosen['lines'] = list(chosen_lines)
                chosen['mw'] = float(measured_w)
                chosen['mh'] = float(measured_h)
                chosen['fill_w'] = float(fill_w_after)
                chosen['fill_h'] = float(fill_h_after)
                chosen['touch'] = bool(_touch_ok_for_lines(chosen_lines, fill_w_after, fill_h_after))
                chosen['near_touch'] = bool(_near_touch_ok(fill_w_after, fill_h_after))
                chosen['deficit'] = float(max(0.0, req_w - fill_w_after) + max(0.0, req_h - fill_h_after))
                chosen['badness'] = float(self._ko_linebreak_badness(chosen_lines)) + (ko_linebreak_rules.EMERGENCY_BADNESS_PENALTY if chosen.get('emergency') else 0.0)
                chosen['line_count_target'] = int(len(chosen_lines))
                chosen['line_compacted'] = True
                chosen['line_compact_diag'] = compact_diag
                try:
                    self._auto_adjust_diag(
                        'TEXT_AUTO_ADJUST_LINE_COMPACTED',
                        item,
                        moved=int((compact_diag or {}).get('moved') or 0),
                        line_count=len(chosen_lines),
                        measured_w=round(float(measured_w), 2),
                        measured_h=round(float(measured_h), 2),
                        fill_w=round(float(fill_w_after), 4),
                        fill_h=round(float(fill_h_after), 4),
                        lines=' / '.join(chosen_lines)[:160],
                    )
                except Exception:
                    pass

            self._auto_adjust_diag(
                'TEXT_AUTO_ADJUST_CHOSEN',
                item,
                chosen_from=('passing' if chosen.get('touch') else ('near_passing' if chosen.get('near_touch') else 'fallback_no_passing')),
                selection_policy=selection_policy,
                size=int(chosen_size),
                measured_w=round(float(measured_w), 2),
                measured_h=round(float(measured_h), 2),
                fill_w=round(float(float(measured_w) / max(1.0, float(max_w))), 4),
                fill_h=round(float(float(measured_h) / max(1.0, float(max_h))), 4),
                req_w=round(float(req_w), 4),
                req_h=round(float(req_h), 4),
                touch_ok=bool(chosen.get('touch')),
                near_touch_ok=bool(chosen.get('near_touch')),
                deficit=round(float(chosen.get('deficit') or 0.0), 4),
                old_size=int(item.get('font_size', fallback_size) or fallback_size),
                line_count=len(chosen_lines),
                line_count_target=int(chosen.get('line_count_target') or len(chosen_lines)),
                emergency_split=bool(chosen.get('emergency')),
                overlap_block_count=int(((chosen.get('fit_diag') or {}).get('overlap_block_count') or 0)),
                overlap_check_count=int(((chosen.get('fit_diag') or {}).get('overlap_check_count') or 0)),
                final_overlap=bool(((chosen.get('fit_diag') or {}).get('final_overlap'))),
                final_overlap_check_size=(chosen.get('fit_diag') or {}).get('final_overlap_check_size'),
                width_block_count=int(((chosen.get('fit_diag') or {}).get('width_block_count') or 0)),
                height_block_count=int(((chosen.get('fit_diag') or {}).get('height_block_count') or 0)),
                overlap_info=str(((chosen.get('fit_diag') or {}).get('last_overlap_info')))[:240],
                final_overlap_info=str(((chosen.get('fit_diag') or {}).get('final_overlap_info'))[:240] if ((chosen.get('fit_diag') or {}).get('final_overlap_info')) is not None else ''),
                lines=' / '.join(chosen_lines)[:160],
            )

            wrapped = '\n'.join([line.rstrip() for line in chosen_lines]).strip()
            changed = bool(fit_rect_changed)
            if wrapped and wrapped != str(original or ''):
                item[text_key] = wrapped
                changed = True
            old_size = int(item.get('font_size', fallback_size) or fallback_size)
            if old_size != int(chosen_size):
                item['font_size'] = int(chosen_size)
                changed = True
            if item.get('ocr_lang') != lang:
                item['ocr_lang'] = lang
                changed = True

            fill_w = float(measured_w) / max(1.0, float(max_w))
            fill_h = float(measured_h) / max(1.0, float(max_h))
            overlap_now = bool(chosen.get('overlap') or ((chosen.get('fit_diag') or {}).get('final_overlap')))
            touch_ok = bool(chosen.get('touch'))
            item['auto_layout_mode'] = 'ko_force_resize_retry_loop'
            item['auto_layout_shape_ratio'] = float(round(float(chosen.get('shape_ratio') or 0.0), 4))
            item['auto_layout_box_ratio'] = float(round(box_ratio, 4))
            item['auto_layout_line_count'] = int(len(chosen_lines))
            item['auto_layout_line_count_target'] = int(chosen.get('line_count_target') or len(chosen_lines))
            item['auto_layout_fill_w'] = float(round(fill_w, 4))
            item['auto_layout_fill_h'] = float(round(fill_h, 4))
            item['auto_layout_req_w'] = float(round(req_w, 4))
            item['auto_layout_req_h'] = float(round(req_h, 4))
            item['auto_layout_edge_deficit'] = float(round(max(0.0, req_w - fill_w) + max(0.0, req_h - fill_h), 4))
            item['auto_layout_touch_ok'] = bool(touch_ok)
            item['auto_layout_near_touch_ok'] = bool(chosen.get('near_touch'))
            item['auto_layout_hard_fail'] = bool(not (touch_ok or chosen.get('near_touch')))
            item['auto_layout_selection_policy'] = selection_policy
            # 자동 조정 후에는 OCR 박스 기준 중앙 배치를 강제한다.
            # 사용자 행간/서식은 건드리지 않고 위치 오프셋만 OCR 중심 기준으로 되돌린다.
            if int(round(float(item.get('x_off', 0) or 0))) != 0:
                item['x_off'] = 0
                changed = True
            if int(round(float(item.get('y_off', 0) or 0))) != 0:
                item['y_off'] = 0
                changed = True
            item['auto_layout_centered_to_ocr_box'] = True
            item['auto_layout_force_retry_count'] = int(len(hard_candidates))
            item['auto_layout_emergency_split'] = bool(chosen.get('emergency'))
            item['auto_layout_width_overflow_allowed'] = bool((measured_w > max_w) and (measured_w <= hard_width_limit) and not overlap_now)
            item['auto_layout_overlap_shrink'] = bool(overlap_now)
            item['auto_layout_pairwise_overlap_shrink'] = bool(overlap_now)
            item['auto_layout_pairwise_overlap_policy'] = 'no_text_overlap_allowed'
            item['auto_layout_pairwise_fixed_neighbor_id'] = None
            item['auto_layout_overlap_policy'] = 'no_text_overlap_allowed'
            item['auto_layout_line_spacing_preserved'] = int(item.get('line_spacing', old_line_spacing_for_auto) or old_line_spacing_for_auto)
            item['auto_layout_ko_bound_badness'] = float(round(float(chosen.get('badness') or 0.0), 4))
            try:
                item['auto_layout_score'] = float(round(float(chosen.get('score') or 0.0), 4))
            except Exception:
                pass
            if measured_w > hard_width_limit or measured_h > max_h or not (touch_ok or chosen.get('near_touch')):
                item['auto_wrap_height_overflow'] = True
            else:
                item.pop('auto_wrap_height_overflow', None)
            self._auto_adjust_diag(
                'TEXT_AUTO_ADJUST_APPLIED',
                item,
                lang=lang,
                mode=item.get('auto_layout_mode'),
                changed=bool(changed),
                old_size=old_size,
                final_size=int(chosen_size),
                size_delta=int(chosen_size) - int(old_size),
                final_text_changed=bool(wrapped and wrapped != str(original or '')),
                fill_w=item.get('auto_layout_fill_w'),
                fill_h=item.get('auto_layout_fill_h'),
                req_w=item.get('auto_layout_req_w'),
                req_h=item.get('auto_layout_req_h'),
                touch_ok=item.get('auto_layout_touch_ok'),
                hard_fail=item.get('auto_layout_hard_fail'),
                retry_count=item.get('auto_layout_force_retry_count'),
                line_count=item.get('auto_layout_line_count'),
                overlap_policy=item.get('auto_layout_overlap_policy'),
                line_spacing=item.get('line_spacing'),
                warning='final_size_not_greater_than_old' if int(chosen_size) <= int(old_size) else '',
            )
            return changed

        # 영어는 기존 단어 기준 맞춤을 유지하되, 이름상 텍스트 자동 조정에 합류한다.
        # 자동 조정은 OCR 박스 외곽까지 채우는 것을 기본값으로 한다.
        width_ratio = 1.00
        height_ratio = 1.00
        start_size = self._auto_text_adjust_initial_font_size(item, page_idx=page_idx, fallback_size=fallback_size)
        # stroke_width는 텍스트 렌더 측정에만 반영하고, OCR fit 박스를 줄이는 내부 여백으로 쓰지 않는다.
        max_w = max(1, int(box_w * width_ratio))
        max_h = max(1, int(box_h * height_ratio))

        chosen_size = None
        chosen_lines = None
        chosen_score = None
        self._auto_adjust_diag(
            'TEXT_AUTO_ADJUST_FONT_LOOP_ENTER',
            item,
            lang=lang,
            box_w=box_w,
            box_h=box_h,
            max_w=max_w,
            max_h=max_h,
            start_size=start_size,
            max_size=start_size,
            fallback_size=fallback_size,
            stroke=stroke,
        )

        for size in range(max(1, int(start_size)), 0, -1):
            _font, fm, _line_spacing_pct, char_width_pct, _char_height_pct, letter_spacing = self._auto_layout_item_style_metrics(item, family, size)
            wrap_w = max(1, int(max_w / positive_scale_factor(char_width_pct)))
            lines = self._wrap_space_language_lines(source_text, fm, wrap_w, lang=lang, letter_spacing=letter_spacing)
            measured_w, measured_h = self._measure_wrapped_lines_for_auto_fit(item, lines, family, size, stroke=stroke)
            if measured_w <= max_w and measured_h <= max_h:
                fill_h = measured_h / max(1, max_h)
                score = (size, -abs(0.68 - fill_h))
                chosen_size = size
                chosen_lines = lines
                chosen_score = score
                break

        if chosen_lines is None:
            size = 1
            _font, fm, _line_spacing_pct, char_width_pct, _char_height_pct, letter_spacing = self._auto_layout_item_style_metrics(item, family, size)
            wrap_w = max(1, int(max_w / positive_scale_factor(char_width_pct)))
            chosen_lines = self._wrap_space_language_lines(source_text, fm, wrap_w, lang=lang, letter_spacing=letter_spacing)
            chosen_size = size

        wrapped = '\n'.join([line.rstrip() for line in chosen_lines]).strip()
        changed = False

        if wrapped and wrapped != str(original or ''):
            item[text_key] = wrapped
            changed = True

        old_size = int(item.get('font_size', fallback_size) or fallback_size)
        if old_size != int(chosen_size):
            item['font_size'] = int(chosen_size)
            changed = True

        if item.get('ocr_lang') != lang:
            item['ocr_lang'] = lang
            changed = True
        item['auto_layout_mode'] = 'text_auto_adjust'

        return changed

    def auto_text_size_item(self, item, page_idx=None):
        """텍스트 자동 조정.

        OCR 언어가 아니라 최종 출력/번역 대상 언어를 기준으로 줄내림+크기 조정을 함께 수행한다.
        한국어는 사각 조판 점수식을 쓰고, 다른 언어도 공통 fit 루틴으로 반드시 줄내림을 적용한다.

        자동 조정의 변경 대상은 번역문 줄바꿈과 font_size뿐이다.
        line_spacing/letter_spacing/char_width/char_height는 사용자 서식 값이므로
        내부 루틴이나 이전 패치 경로에서 값이 바뀌어도 즉시 원복한다.
        """
        protected_style = {}
        if isinstance(item, dict):
            for key in ('line_spacing', 'letter_spacing', 'char_width', 'char_height'):
                if key in item:
                    protected_style[key] = item.get(key)
        self._auto_adjust_diag('TEXT_AUTO_ADJUST_ITEM_ENTER', item, page_idx=page_idx, protected_style=protected_style)

        def _restore_protected_style(result):
            if not isinstance(item, dict) or not protected_style:
                return bool(result)
            restored = []
            for key, value in protected_style.items():
                try:
                    if item.get(key) != value:
                        item[key] = value
                        restored.append(key)
                except Exception:
                    pass
            if restored:
                try:
                    if hasattr(self, 'audit_boundary_event'):
                        self.audit_boundary_event(
                            'TEXT_AUTO_ADJUST_PROTECTED_STYLE_RESTORED',
                            page_idx=page_idx,
                            item_id=item.get('id'),
                            restored_keys=restored,
                            policy='auto_adjust_never_changes_spacing_or_scale_style',
                        )
                except Exception:
                    pass
            return bool(result)

        if self.is_manga_ocr_layout_item(item):
            self._auto_adjust_diag('TEXT_AUTO_ADJUST_ROUTE', item, route='manga_ocr_layout')
            result = self._fit_manga_ocr_text_for_item(item, page_idx=page_idx)
            result = _restore_protected_style(result)
            self._auto_adjust_diag('TEXT_AUTO_ADJUST_MANGA_RESULT', item, changed=bool(result), font_size=item.get('font_size') if isinstance(item, dict) else None)
            return result

        lang = self.item_output_language_for_layout(item)
        self._auto_adjust_diag('TEXT_AUTO_ADJUST_ROUTE', item, route='space_language_fit', output_lang=lang)
        try:
            if hasattr(self, 'audit_boundary_event'):
                self.audit_boundary_event(
                    'TEXT_AUTO_ADJUST_LANG',
                    item_id=item.get('id') if isinstance(item, dict) else None,
                    ocr_lang=self.item_ocr_language_for_layout(item) if isinstance(item, dict) else '',
                    output_lang=lang,
                    target_lang=self.current_translation_target_language_for_layout(),
                    detected_lang=self.detect_text_language_for_layout((item or {}).get('translated_text') or (item or {}).get('text') or '') if isinstance(item, dict) else '',
                )
        except Exception:
            pass
        result = self._fit_space_language_text_for_item(item, lang=lang, page_idx=page_idx)
        result = _restore_protected_style(result)
        try:
            if hasattr(self, 'audit_boundary_event') and isinstance(item, dict):
                self.audit_boundary_event(
                    'TEXT_AUTO_ADJUST_RESULT',
                    item_id=item.get('id'),
                    mode=item.get('auto_layout_mode'),
                    font_size=item.get('font_size'),
                    line_spacing=item.get('line_spacing'),
                    letter_spacing=item.get('letter_spacing'),
                    char_width=item.get('char_width'),
                    char_height=item.get('char_height'),
                    fill_w=item.get('auto_layout_fill_w'),
                    fill_h=item.get('auto_layout_fill_h'),
                    req_w=item.get('auto_layout_req_w'),
                    req_h=item.get('auto_layout_req_h'),
                    edge_deficit=item.get('auto_layout_edge_deficit'),
                    touch_ok=item.get('auto_layout_touch_ok'),
                    ko_bound_badness=item.get('auto_layout_ko_bound_badness'),
                    width_overflow_allowed=item.get('auto_layout_width_overflow_allowed'),
                    hard_fail=item.get('auto_layout_hard_fail'),
                    retry_count=item.get('auto_layout_force_retry_count'),
                    emergency_split=item.get('auto_layout_emergency_split'),
                    line_count=item.get('auto_layout_line_count'),
                    line_count_target=item.get('auto_layout_line_count_target'),
                    changed=bool(result),
                    final_text_preview=str(((item.get('translated_text') if isinstance(item, dict) else '') or (item.get('text') if isinstance(item, dict) else '') or '')).replace('\n', '\\n')[:120] if isinstance(item, dict) else '',
                    final_rect=item.get('rect') if isinstance(item, dict) else None,
                )
        except Exception:
            pass
        try:
            if bool(result):
                # 일부 실행 경로(번역 후 자동 조정/개별 자동 조정)는 auto_text_size_for_page()를
                # 거치지 않고 item 단위 함수만 반복 호출한다. 이 경우 1차에서는
                # _auto_text_adjust_ignore_neighbors=True로 이웃 검사를 건너뛰지만, 마지막
                # 페이지 단위 최다 빈도 크기/겹침 후처리가 호출되지 않아 텍스트가 겹치거나
                # 비정상적으로 작게 남을 수 있다. 페이지 루틴 안이 아닐 때는 짧게 묶어서
                # 후처리를 반드시 예약한다.
                if not bool(getattr(self, '_auto_text_adjust_in_page_run', False)):
                    self._schedule_auto_text_size_page_postpass(page_idx=page_idx, reason='auto_text_size_item')
        except Exception:
            pass
        return result

    def normalize_auto_wrap_source_text(self, text):
        """구버전 호환용 기본 자동 줄내림 원문 정리."""
        return self.normalize_auto_wrap_source_text_for_lang(text, lang='ja')

    def auto_wrap_text_for_item(self, item):
        """구버전 자동 줄내림 호환. 이제 모든 언어에서 텍스트 자동 조정 공통 루틴을 탄다."""
        lang = self.item_output_language_for_layout(item)
        return self._fit_space_language_text_for_item(item, lang=lang, page_idx=getattr(self, 'idx', None))

    def refresh_final_text_items_by_ids(self, ids):
        """최종결과 scene 전체 재구성 없이 지정 텍스트 아이템만 제자리 갱신한다."""
        try:
            if self.cb_mode.currentIndex() != 4:
                return False
            if hasattr(self, 'rebuild_current_page_text_layer_from_data'):
                return bool(self.rebuild_current_page_text_layer_from_data([x for x in (ids or []) if x is not None]))
            return False
        except Exception:
            return False

    def _auto_adjust_current_text_lines_for_item(self, item):
        """현재 item에 실제 적용된 텍스트 줄을 신뢰 가능한 겹침 검사 단위로 반환한다."""
        try:
            _key, text = self._auto_layout_text_key_and_value(item)
        except Exception:
            text = (item or {}).get('translated_text') or (item or {}).get('text') or ''
        lines = [ln.strip() for ln in str(text or '').replace('\r\n', '\n').replace('\r', '\n').split('\n') if ln.strip()]
        if not lines and str(text or '').strip():
            lines = [str(text or '').strip()]
        return lines or ['']

    def _auto_adjust_visual_rect_for_item(self, item):
        """sceneBoundingRect 대신, 현재 데이터에서 직접 계산한 최종 텍스트 bounds를 반환한다.

        이 함수는 페이지 경계/전체 배치용 블록 bounds다. 텍스트끼리의 겹침 검사는
        _auto_adjust_visual_line_rects_for_item()의 줄별 bounds를 우선 사용한다.
        """
        if not isinstance(item, dict):
            return None
        try:
            family = item.get('font_family') or self.cb_font.currentFont().family()
        except Exception:
            family = item.get('font_family') or 'Arial'
        try:
            size = max(1, int(item.get('font_size', 24) or 24))
        except Exception:
            size = 24
        try:
            stroke = max(0, int(item.get('stroke_width', 0) or 0))
        except Exception:
            stroke = 0
        try:
            lines = self._auto_adjust_current_text_lines_for_item(item)
            return self._candidate_text_scene_rect(item, lines, family, size, stroke=stroke)
        except Exception:
            return None

    def _auto_adjust_visual_line_rects_for_item(self, item):
        """현재 item의 실제 줄별 텍스트 bounds를 반환한다. 다른 OCR rect는 보지 않는다."""
        if not isinstance(item, dict):
            return []
        try:
            family = item.get('font_family') or self.cb_font.currentFont().family()
        except Exception:
            family = item.get('font_family') or 'Arial'
        try:
            size = max(1, int(item.get('font_size', 24) or 24))
        except Exception:
            size = 24
        try:
            stroke = max(0, int(item.get('stroke_width', 0) or 0))
        except Exception:
            stroke = 0
        try:
            lines = self._auto_adjust_current_text_lines_for_item(item)
            return self._candidate_text_line_scene_rects(item, lines, family, size, stroke=stroke)
        except Exception:
            rr = self._auto_adjust_visual_rect_for_item(item)
            return [rr] if rr is not None else []

    def _auto_adjust_pair_overlap_info(self, current_rect, fixed_rect, *, strict=False):
        """두 텍스트의 실제 표시 bounds가 겹치거나 1px 여백을 침범하는지 본다.

        current_rect/fixed_rect는 QRectF 하나일 수도 있고, 줄별 QRectF 리스트일 수도 있다.
        리스트가 들어오면 "전체 블록 사각형"이 아니라 실제 줄 rect끼리만 비교한다.
        다른 OCR 영역/말풍선 rect는 이 검사에 절대 쓰지 않는다.
        """
        def _as_rects(value):
            if value is None:
                return []
            if isinstance(value, (list, tuple)):
                out = []
                for v in value:
                    try:
                        if v is not None and hasattr(v, 'width') and float(v.width()) > 0 and float(v.height()) > 0:
                            out.append(v)
                    except Exception:
                        continue
                return out
            try:
                if hasattr(value, 'width') and float(value.width()) > 0 and float(value.height()) > 0:
                    return [value]
            except Exception:
                pass
            return []

        def _pair_info(cur, fixed, cur_idx=0, fixed_idx=0):
            try:
                required_gap = 0.0
                try:
                    if strict:
                        required_gap = float(getattr(ko_linebreak_rules, 'TEXT_OVERLAP_REQUIRED_GAP_PX', 1.0) or 1.0)
                except Exception:
                    required_gap = 1.0 if strict else 0.0

                try:
                    actual_intersects = bool(cur.intersects(fixed))
                except Exception:
                    actual_intersects = False

                gap_violation = False
                gap_x = gap_y = 0.0
                if not actual_intersects:
                    if strict and required_gap > 0.0:
                        try:
                            cx1 = float(cur.x())
                            cy1 = float(cur.y())
                            cx2 = cx1 + float(cur.width())
                            cy2 = cy1 + float(cur.height())
                            fx1 = float(fixed.x())
                            fy1 = float(fixed.y())
                            fx2 = fx1 + float(fixed.width())
                            fy2 = fy1 + float(fixed.height())
                            gap_x = max(0.0, max(fx1 - cx2, cx1 - fx2))
                            gap_y = max(0.0, max(fy1 - cy2, cy1 - fy2))
                            axis_overlap_x = (min(cx2, fx2) - max(cx1, fx1)) > 0.0
                            axis_overlap_y = (min(cy2, fy2) - max(cy1, fy1)) > 0.0
                            gap_violation = bool(
                                (axis_overlap_y and gap_x < required_gap)
                                or (axis_overlap_x and gap_y < required_gap)
                            )
                        except Exception:
                            gap_violation = False
                    if not gap_violation:
                        return False, None

                if actual_intersects:
                    inter = cur.intersected(fixed)
                    ow = max(0.0, float(inter.width()))
                    oh = max(0.0, float(inter.height()))
                    area = ow * oh
                    if ow <= 0.0 or oh <= 0.0 or area <= 0.0:
                        if not strict:
                            return False, None
                        gap_violation = True
                else:
                    ow = oh = area = 0.0

                cur_area = max(1.0, float(cur.width()) * float(cur.height()))
                fix_area = max(1.0, float(fixed.width()) * float(fixed.height()))
                min_area = max(1.0, min(cur_area, fix_area))
                area_ratio = area / min_area if area > 0.0 else 0.0

                if gap_violation and area <= 0.0:
                    try:
                        gap_deficit = max(0.0, required_gap - min(gap_x if gap_x > 0.0 else required_gap, gap_y if gap_y > 0.0 else required_gap))
                    except Exception:
                        gap_deficit = required_gap
                    area = max(1.0, float(gap_deficit or required_gap or 1.0))
                    area_ratio = max(0.0001, area / min_area)

                return True, {
                    'current_rect': [round(cur.x(), 2), round(cur.y(), 2), round(cur.width(), 2), round(cur.height(), 2)],
                    'fixed_rect': [round(fixed.x(), 2), round(fixed.y(), 2), round(fixed.width(), 2), round(fixed.height(), 2)],
                    'current_line_index': int(cur_idx),
                    'fixed_line_index': int(fixed_idx),
                    'overlap_w': round(ow, 2),
                    'overlap_h': round(oh, 2),
                    'overlap_area': round(area, 2),
                    'area_ratio': round(area_ratio, 4),
                    'strict': bool(strict),
                    'required_gap_px': float(required_gap),
                    'gap_violation': bool(gap_violation),
                    'gap_x': round(float(gap_x), 2),
                    'gap_y': round(float(gap_y), 2),
                    'policy': 'line_rects_actual_text_only_no_other_ocr_rects_with_1px_gap' if strict else 'line_rects_actual_text_only_no_other_ocr_rects',
                }
            except Exception as exc:
                return False, {'error': repr(exc)}

        try:
            cur_rects = _as_rects(current_rect)
            fix_rects = _as_rects(fixed_rect)
            if not cur_rects or not fix_rects:
                return False, None
            worst = None
            for ci, cur in enumerate(cur_rects):
                for fi, fixed in enumerate(fix_rects):
                    hit, info = _pair_info(cur, fixed, ci, fi)
                    if not hit:
                        continue
                    if worst is None:
                        worst = info
                    else:
                        try:
                            score = float((info or {}).get('area_ratio') or 0.0) * 100000.0 + float((info or {}).get('overlap_area') or 0.0)
                            old_score = float((worst or {}).get('area_ratio') or 0.0) * 100000.0 + float((worst or {}).get('overlap_area') or 0.0)
                            if score > old_score:
                                worst = info
                        except Exception:
                            pass
            if worst is not None:
                try:
                    worst['line_rect_count_current'] = int(len(cur_rects))
                    worst['line_rect_count_fixed'] = int(len(fix_rects))
                except Exception:
                    pass
                return True, worst
            return False, None
        except Exception as exc:
            return False, {'error': repr(exc)}

    def _auto_text_size_page_median_font_size(self, targets):
        """페이지 자동 조정 결과의 최다 빈도 글자 크기(사용자 기준 중위값)를 구한다.

        여기서 말하는 중위값은 수학적 median(가운데값)이 아니라, 페이지에서
        가장 많이 분포한 글자 크기 체급이다. 자동 조정을 모두 끝낸 뒤의
        가로쓰기/활성 텍스트 크기를 보고, 비슷한 크기끼리 묶은 다음 가장 많이
        모인 구간의 대표값을 사용한다.
        """
        sizes = []
        for item in targets or []:
            if not isinstance(item, dict) or not item.get('use_inpaint', True):
                continue
            try:
                if self.text_item_writing_direction(item) == 'vertical':
                    continue
            except Exception:
                pass
            try:
                _key, text = self._auto_layout_text_key_and_value(item)
            except Exception:
                text = item.get('translated_text') or item.get('text') or ''
            if not str(text or '').strip():
                continue
            try:
                size = int(round(float(item.get('font_size', 0) or 0)))
            except Exception:
                size = 0
            if 6 <= size <= 260:
                sizes.append(size)
        if not sizes:
            return None
        sizes.sort()
        if len(sizes) == 1:
            return int(sizes[0])

        # 정확히 같은 값만 세면 39/40/41처럼 같은 체급이 흩어진 페이지를 놓친다.
        # 각 글자 크기 주변의 좁은 창을 훑어 가장 조밀한 구간을 찾는다.
        best = None
        for center in sorted(set(sizes)):
            try:
                tol = max(2, int(round(float(center) * 0.08)))
            except Exception:
                tol = 2
            members = [s for s in sizes if abs(int(s) - int(center)) <= tol]
            if not members:
                continue
            spread = int(max(members) - min(members)) if members else 0
            exact_count = sum(1 for s in sizes if int(s) == int(center))
            # 우선순위: 많이 모인 구간 > 같은 값이 많이 찍힌 중심 > 좁은 구간 > 더 큰 체급
            score = (len(members), exact_count, -spread, int(center))
            if best is None or score > best[0]:
                best = (score, center, members)
        if best is None:
            return int(sizes[len(sizes) // 2])
        _score, _center, members = best
        freq = {}
        for s in members:
            freq[int(s)] = freq.get(int(s), 0) + 1
        max_freq = max(freq.values()) if freq else 0
        mode_values = sorted([v for v, c in freq.items() if c == max_freq])
        if max_freq > 1 and mode_values:
            # 같은 빈도로 여러 값이 있으면 구간 중앙에 가까운 값을 쓰고, 동률이면 큰 쪽을 쓴다.
            avg = float(sum(members)) / max(1, len(members))
            return int(sorted(mode_values, key=lambda v: (abs(float(v) - avg), -int(v)))[0])
        avg = float(sum(members)) / max(1, len(members))
        return int(math.floor(avg + 0.5))

    def _auto_text_rewrap_item_for_font_size(self, item, target_size, page_idx=None):
        """지정 폰트 크기에서 현재 줄 구조를 그대로 둔 채 측정한다.

        중요 원칙:
        - 이 함수는 더 이상 줄내림을 다시 만들지 않는다.
        - 안전 재성장/최다 빈도 글자 크기 하한 보정은 font_size만 바꾼다.
        - translated_text/text 안의 기존 줄바꿈과 띄어쓰기는 그대로 보존한다.

        이전 구현은 target_size마다 한국어 줄내림 후보를 다시 만들어서
        "성욕 강한 / 성인의 몸이라 / ..."처럼 이미 잘 잡힌 비율을 다시 바꿨다.
        후처리 단계에서 줄 구조가 바뀌면 작업자가 검수한 줄비율과 띄어쓰기가 깨지므로,
        여기서는 현재 텍스트 라인 그대로 렌더 bounds만 재측정한다.
        """
        if not isinstance(item, dict):
            return None
        if self.text_item_writing_direction(item) == 'vertical':
            return None
        try:
            text_key, text_value = self._auto_layout_text_key_and_value(item)
        except Exception:
            text_key = 'translated_text' if str(item.get('translated_text', '') or '').strip() else 'text'
            text_value = item.get(text_key, '') or ''
        raw_text = str(text_value or '').replace('\r\n', '\n').replace('\r', '\n')
        if not raw_text.strip():
            return None
        try:
            family = item.get('font_family') or self.cb_font.currentFont().family()
        except Exception:
            family = item.get('font_family') or 'Arial'
        try:
            stroke = int(item.get('stroke_width', 0) or 0)
        except Exception:
            stroke = 0
        size = max(1, min(260, int(round(float(target_size or 1)))))

        # 빈 줄은 렌더러에서 실질 표시가 거의 없으므로 기존 자동 조정 계열과 맞춰 제외한다.
        # 단, 각 줄 내부 띄어쓰기와 줄 순서는 절대 재작성하지 않는다.
        raw_lines = raw_text.split('\n')
        lines = [str(line).rstrip() for line in raw_lines if str(line).strip()]
        if not lines:
            lines = [raw_text.strip()]
        preserved_text = '\n'.join(lines).strip()
        try:
            mw, mh = self._measure_wrapped_lines_for_auto_fit(item, lines, family, size, stroke=stroke)
        except Exception:
            return None
        try:
            if hasattr(self, 'audit_boundary_event'):
                self.audit_boundary_event(
                    'TEXT_AUTO_ADJUST_REWRAP_PRESERVE_LINES',
                    page_idx=page_idx,
                    item_id=item.get('id'),
                    target_size=int(size),
                    line_count=int(len(lines)),
                    text_key=str(text_key),
                    policy='postpass_font_size_only_keep_existing_linebreaks',
                )
        except Exception:
            pass
        return {
            'text_key': text_key,
            'text': preserved_text,
            'lines': list(lines),
            'size': int(size),
            'measured_w': float(mw),
            'measured_h': float(mh),
            'line_policy': 'preserve_existing_lines',
        }

    def auto_text_median_floor_threshold_percent(self):
        """자동 텍스트 조정에서 비정상적으로 작은 글자만 감지하는 최다 빈도값 대비 기준.

        33이면 페이지 최다 빈도 글자 크기의 33% 이하만 작은 텍스트로 본다.
        0이면 최다 빈도 하한 보정을 끈다.
        """
        try:
            value = int((getattr(self, 'app_options', {}) or {}).get('auto_text_median_floor_threshold_percent', 33) or 0)
        except Exception:
            value = 33
        return max(0, min(100, int(value)))

    def set_auto_text_median_floor_threshold_percent(self, value, save=True):
        try:
            value = int(value)
        except Exception:
            value = 33
        value = max(0, min(100, int(value)))
        try:
            if not isinstance(getattr(self, 'app_options', None), dict):
                self.app_options = {}
            self.app_options['auto_text_median_floor_threshold_percent'] = int(value)
            if save:
                self.save_app_options_cache()
        except Exception:
            try:
                if save:
                    save_app_options(getattr(self, 'app_options', {}) or {})
            except Exception:
                pass
        return int(value)

    def auto_text_apply_vertical_writing_enabled(self):
        """자동 텍스트 조정 시 OCR 세로쓰기 후보를 세로쓰기 모드로 자동 전환할지."""
        try:
            return bool((getattr(self, 'app_options', {}) or {}).get('auto_text_apply_vertical_writing', True))
        except Exception:
            return True

    def set_auto_text_apply_vertical_writing_enabled(self, enabled, save=True):
        value = bool(enabled)
        try:
            if not isinstance(getattr(self, 'app_options', None), dict):
                self.app_options = {}
            self.app_options['auto_text_apply_vertical_writing'] = value
            if save:
                self.save_app_options_cache()
        except Exception:
            try:
                if save:
                    save_app_options(getattr(self, 'app_options', {}) or {})
            except Exception:
                pass
        return value

    def open_auto_text_adjust_options_dialog(self):
        """자동화 작업 > 자동 텍스트 조정 옵션.

        자동 텍스트 조정에서 사용하는 세로쓰기 자동 적용과 최소 텍스트 크기 보정을 함께 관리한다.
        """
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr_ui('자동 텍스트 조정 옵션'))
        dlg.setModal(True)
        dlg.resize(620, 390)
        try:
            dlg.setStyleSheet(self.settings_dialog_style())
        except Exception:
            pass

        root = QVBoxLayout(dlg)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        title = QLabel(self.tr_ui('자동 텍스트 조정 옵션'), dlg)
        title.setObjectName('SettingsTitle')
        root.addWidget(title)

        desc = QLabel(self.tr_ui('텍스트 자동 조정에서 OCR 세로쓰기 후보 자동 적용과 최소 텍스트 크기 보정을 설정합니다.'), dlg)
        desc.setObjectName('SettingsDescription')
        desc.setWordWrap(True)
        root.addWidget(desc)

        vertical_box = QFrame(dlg)
        vertical_box.setObjectName('SettingsItem')
        v_layout = QVBoxLayout(vertical_box)
        v_layout.setContentsMargins(12, 12, 12, 12)
        v_layout.setSpacing(8)

        chk_vertical = QCheckBox(self.tr_ui('텍스트 조정 시 세로쓰기 자동 적용'), vertical_box)
        chk_vertical.setChecked(self.auto_text_apply_vertical_writing_enabled())
        chk_vertical.setToolTip(self.tr_ui('분석 단계에서 세로쓰기 한 줄 후보로 태깅된 OCR 영역을 자동 텍스트 조정 시 세로쓰기 모드로 전환합니다. 세로쓰기는 줄내림 없이 한 세로 열만 사용합니다.'))
        v_layout.addWidget(chk_vertical)

        vertical_help = QLabel(self.tr_ui('OCR 박스의 세로/가로 비율과 글자 수를 비교해 세로쓰기 한 줄 후보로 태깅된 항목만 자동 전환합니다. 체크를 끄면 이미 세로쓰기로 지정된 텍스트만 세로쓰기 전용 조정을 탑니다.'), vertical_box)
        vertical_help.setObjectName('SettingsDescription')
        vertical_help.setWordWrap(True)
        v_layout.addWidget(vertical_help)
        root.addWidget(vertical_box)

        floor_box = QFrame(dlg)
        floor_box.setObjectName('SettingsItem')
        grid = QGridLayout(floor_box)
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        label = QLabel(self.tr_ui('최소 텍스트 크기 보정'), floor_box)
        label.setObjectName('SettingsItemTitle')
        spin = QSpinBox(floor_box)
        spin.setRange(0, 100)
        spin.setSuffix('%')
        spin.setValue(self.auto_text_median_floor_threshold_percent())
        spin.setToolTip(self.tr_ui('페이지에서 가장 많이 나온 글자 크기(최다 빈도 크기)를 기준으로, 사용자가 설정한 비율 이하의 텍스트만 비정상적으로 작다고 보고 그 최다 빈도 크기로 키웁니다. 기본값은 33%이며, 0%는 사용하지 않습니다.'))

        def _threshold_help_text(value):
            template = self.tr_ui('현재 설정값이 {value}%이면 페이지 최다 빈도 글자 크기의 {value}% 이하인 텍스트만 보정합니다. 기준보다 큰 텍스트는 그대로 둡니다.')
            try:
                return str(template).format(value=int(value))
            except Exception:
                return f"현재 설정값이 {int(value)}%이면 페이지 최다 빈도 글자 크기의 {int(value)}% 이하인 텍스트만 보정합니다. 기준보다 큰 텍스트는 그대로 둡니다."

        help_label = QLabel(_threshold_help_text(spin.value()), floor_box)
        help_label.setObjectName('SettingsDescription')
        help_label.setWordWrap(True)
        try:
            spin.valueChanged.connect(lambda value: help_label.setText(_threshold_help_text(value)))
        except Exception:
            pass

        grid.addWidget(label, 0, 0)
        grid.addWidget(spin, 0, 1)
        grid.addWidget(help_label, 1, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        root.addWidget(floor_box)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dlg)
        root.addStretch(1)
        root.addWidget(buttons)

        def _accept():
            vertical_enabled = self.set_auto_text_apply_vertical_writing_enabled(chk_vertical.isChecked(), save=False)
            value = self.set_auto_text_median_floor_threshold_percent(spin.value(), save=False)
            try:
                self.save_app_options_cache()
            except Exception:
                try:
                    save_app_options(getattr(self, 'app_options', {}) or {})
                except Exception:
                    pass
            try:
                state = 'ON' if vertical_enabled else 'OFF'
                self.log(f"🔤 자동 텍스트 조정 옵션 저장: 세로쓰기 자동 적용 {state}, 작은 텍스트 기준 {value}%")
            except Exception:
                pass
            dlg.accept()

        buttons.accepted.connect(_accept)
        buttons.rejected.connect(dlg.reject)
        dlg.exec()

    def _auto_text_item_overlaps_any(self, item, active, *, strict=True):
        """현재 item의 실제 렌더 bounds가 다른 텍스트와 겹치는지 검사한다."""
        try:
            rr = self._auto_adjust_visual_line_rects_for_item(item)
        except Exception:
            rr = None
        if not rr:
            return True, {'error': 'no_line_rect'}
        worst = None
        for other in active or []:
            if other is item:
                continue
            if not isinstance(other, dict) or not other.get('use_inpaint', True):
                continue
            try:
                _k, other_text = self._auto_layout_text_key_and_value(other)
            except Exception:
                other_text = other.get('translated_text') or other.get('text') or ''
            if not str(other_text or '').strip():
                continue
            try:
                orr = self._auto_adjust_visual_line_rects_for_item(other)
            except Exception:
                orr = None
            ov, info = self._auto_adjust_pair_overlap_info(rr, orr, strict=bool(strict))
            if ov:
                worst = info
                return True, worst
        return False, None

    def _auto_text_size_try_grow_item_to_safe_size(self, page_idx, item, active, target_size, *, reason='safe_grow'):
        """겹치지 않는 범위에서 item의 글자 크기를 최대한 키운다.

        기존 median floor는 대상이 되면 곧장 페이지 최다 빈도 크기까지 키웠다. 그러면 큰 텍스트가
        겹침을 만들고, 다음 겹침 패스가 다시 8px 같은 읽기 어려운 크기까지 줄이는 진동이 생긴다.
        이 함수는 target_size까지 후보를 시험하되, 실제 렌더 bounds 기준으로 겹치지 않는 최대값만 적용한다.
        """
        if not isinstance(item, dict) or not item.get('use_inpaint', True):
            return None
        if self.text_item_writing_direction(item) == 'vertical':
            return None
        try:
            text_key, text_value = self._auto_layout_text_key_and_value(item)
        except Exception:
            text_key = 'translated_text' if str(item.get('translated_text', '') or '').strip() else 'text'
            text_value = item.get(text_key, '') or ''
        raw_text = str(text_value or '').strip()
        if not raw_text:
            return None
        try:
            old_size = max(1, int(round(float(item.get('font_size', 0) or 0))))
        except Exception:
            old_size = 1
        try:
            target_size = max(old_size, min(260, int(round(float(target_size or old_size)))))
        except Exception:
            target_size = old_size
        if target_size <= old_size:
            return None
        old_text = str(item.get(text_key, '') or '')
        old_font = item.get('font_size')
        best = None
        # 큰 폭으로 한 번에 튀지 않고 모든 크기를 검사한다.
        # 단, 후처리 재성장에서는 줄내림을 다시 만들지 않고 현재 줄 구조 그대로 측정한다.
        # target은 대개 페이지 최다 빈도 글자 크기라 범위가 작다.
        for test_size in range(old_size + 1, target_size + 1):
            try:
                item[text_key] = raw_text
                item['font_size'] = int(test_size)
                result = self._auto_text_rewrap_item_for_font_size(item, test_size, page_idx=page_idx)
                if not result:
                    continue
                new_text = str(result.get('text') or '').strip()
                if not new_text:
                    continue
                # 안전 재성장/하한 보정은 줄비율을 바꾸지 않는다.
                # _auto_text_rewrap_item_for_font_size()가 현재 라인을 그대로 반환하므로
                # 여기서도 기존 줄 구조를 보존한 텍스트만 임시 적용한다.
                item[text_key] = new_text
                item['font_size'] = int(test_size)
                ov, info = self._auto_text_item_overlaps_any(item, active, strict=True)
                if not ov:
                    best = {
                        'size': int(test_size),
                        'text_key': text_key,
                        'text': new_text,
                        'lines': list(result.get('lines') or []),
                        'measured_w': float(result.get('measured_w') or 0.0),
                        'measured_h': float(result.get('measured_h') or 0.0),
                    }
            except Exception:
                continue
        # 원상복구 후 최선 후보만 적용한다.
        item[text_key] = old_text
        item['font_size'] = old_font
        if not best:
            try:
                if hasattr(self, 'audit_boundary_event'):
                    self.audit_boundary_event(
                        'TEXT_AUTO_ADJUST_SAFE_GROW_NO_FIT',
                        page_idx=page_idx,
                        item_id=item.get('id'),
                        old_size=int(old_size),
                        target_size=int(target_size),
                        reason=str(reason or ''),
                    )
            except Exception:
                pass
            return None
        if int(best.get('size') or old_size) <= int(old_size):
            return None
        item[best['text_key']] = best['text']
        item['font_size'] = int(best['size'])
        item['auto_layout_safe_grow_applied'] = True
        item['auto_layout_safe_grow_reason'] = str(reason or '')
        item['auto_layout_safe_grow_old_size'] = int(old_size)
        item['auto_layout_safe_grow_new_size'] = int(best['size'])
        item['auto_layout_safe_grow_target_size'] = int(target_size)
        item['auto_layout_safe_grow_line_count'] = int(len(best.get('lines') or []))
        item['auto_layout_safe_grow_line_policy'] = 'preserve_existing_linebreaks_font_size_only'
        item['auto_layout_safe_grow_measured_w'] = float(round(float(best.get('measured_w') or 0.0), 2))
        item['auto_layout_safe_grow_measured_h'] = float(round(float(best.get('measured_h') or 0.0), 2))
        try:
            if hasattr(self, 'audit_boundary_event'):
                self.audit_boundary_event(
                    'TEXT_AUTO_ADJUST_SAFE_GROW_APPLIED',
                    page_idx=page_idx,
                    item_id=item.get('id'),
                    old_size=int(old_size),
                    new_size=int(best['size']),
                    target_size=int(target_size),
                    reason=str(reason or ''),
                    line_count=int(len(best.get('lines') or [])),
                    measured_w=round(float(best.get('measured_w') or 0.0), 2),
                    measured_h=round(float(best.get('measured_h') or 0.0), 2),
                    line_policy='preserve_existing_linebreaks_font_size_only',
                )
        except Exception:
            pass
        return item.get('id')

    def _auto_text_size_safe_regrow_pass(self, page_idx, targets, *, reason='after_overlap'):
        """겹침 보정으로 과하게 작아진 텍스트를 다시 키워본다."""
        active = [x for x in (targets or []) if isinstance(x, dict) and x.get('use_inpaint', True)]
        if not active:
            return []
        median_size = self._auto_text_size_page_median_font_size(active)
        if not median_size or median_size <= 0:
            return []
        threshold_percent = self.auto_text_median_floor_threshold_percent()
        threshold = max(1, int(round(float(median_size) * (float(threshold_percent) / 100.0)))) if threshold_percent > 0 else 0
        # 33% 기준에 걸린 텍스트 + 겹침 보정으로 줄어든 텍스트 중 대표 체급의 65% 미만인 것만 재성장 대상.
        soft_limit = max(threshold, int(round(float(median_size) * 0.65)))
        changed_ids = []
        try:
            if hasattr(self, 'audit_boundary_event'):
                self.audit_boundary_event(
                    'TEXT_AUTO_ADJUST_SAFE_REGROW_PASS_START',
                    page_idx=page_idx,
                    reason=str(reason or ''),
                    median_size=int(median_size),
                    threshold=int(threshold),
                    soft_limit=int(soft_limit),
                    target_count=len(active),
                )
        except Exception:
            pass
        for item in active:
            if self.text_item_writing_direction(item) == 'vertical':
                continue
            try:
                old_size = max(1, int(round(float(item.get('font_size', 0) or 0))))
            except Exception:
                old_size = 1
            was_shrunk = bool(item.get('auto_layout_global_overlap_shrink'))
            was_floor = bool(item.get('auto_layout_median_floor_applied'))
            if old_size >= int(median_size):
                continue
            if not (old_size <= threshold or (was_shrunk and old_size <= soft_limit) or (was_floor and old_size <= soft_limit)):
                continue
            cid = self._auto_text_size_try_grow_item_to_safe_size(page_idx, item, active, int(median_size), reason=reason)
            if cid is not None and cid not in changed_ids:
                changed_ids.append(cid)
        try:
            if hasattr(self, 'audit_boundary_event'):
                self.audit_boundary_event(
                    'TEXT_AUTO_ADJUST_SAFE_REGROW_PASS_DONE',
                    page_idx=page_idx,
                    reason=str(reason or ''),
                    changed_ids=[x for x in changed_ids if x is not None],
                    changed_count=len([x for x in changed_ids if x is not None]),
                )
        except Exception:
            pass
        return [x for x in changed_ids if x is not None]


    def _auto_text_size_force_grow_debug_log(self, event, **fields):
        """available-space grow 전용 강제 디버그 로그.

        audit_boundary_event는 log_output_settings.json의 이벤트별 ON/OFF를 탄다.
        SIZE_FAIL처럼 다음 원인 추적에 필요한 이벤트는 이 헬퍼로 별도 JSONL에도 남겨서
        이벤트 레지스트리/설정/필드 길이 제한과 무관하게 확인할 수 있게 한다.
        """
        try:
            from ysb.utils.runtime_logger import log_dir, memory_text
            import datetime as _dt
            import json as _json
            import os as _os

            payload = {
                'ts': _dt.datetime.now().isoformat(timespec='milliseconds'),
                'event': str(event or ''),
            }
            try:
                payload['memory'] = memory_text()
            except Exception:
                pass
            try:
                payload['pid'] = _os.getpid()
            except Exception:
                pass
            try:
                payload.update(dict(fields or {}))
            except Exception:
                pass

            # 1) 별도 JSONL: audit 설정 필터와 engine log 필드 축약을 모두 피한다.
            try:
                path = log_dir() / 'auto_text_grow_debug.jsonl'
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('a', encoding='utf-8', errors='replace') as f:
                    f.write(_json.dumps(payload, ensure_ascii=False, default=str) + '\n')
            except Exception:
                pass

            # 2) 기존 engine_boundary 로그에도 필터를 우회한 FORCE 이벤트를 남긴다.
            try:
                audit = getattr(self, 'engine_boundary_audit', None)
                if audit is not None:
                    compact = dict(payload)
                    for _k in list(compact.keys()):
                        try:
                            if _k in {'fail_first', 'fail_last', 'fail_trace_tail', 'blocked_info'}:
                                compact[_k] = str(compact.get(_k))[:900]
                        except Exception:
                            pass
                    audit.note(str(event or ''), **compact)
                    return
            except Exception:
                pass

            try:
                self.log(f"[{str(event or '')}] {payload}")
            except Exception:
                try:
                    print(f"[{str(event or '')}] {payload}")
                except Exception:
                    pass
        except Exception:
            pass


    def _auto_text_size_try_grow_item_to_available_space(self, page_idx, item, active, page_rect, target_size, *, reason='available_space_safe_grow'):
        """작은 텍스트만 실제 여유 공간 기준으로 글자 크기를 다시 키운다.

        이 함수 자체는 OCR 박스를 성장 한계로 쓰지 않으므로 호출부에서 작은 글자/복구 대상만
        넘겨야 한다. 현재 줄내림은 그대로 유지하고, 실제 렌더 bounds가 다른 텍스트와
        겹치지 않으며 이미지 캔버스 밖으로 나가지 않는 최대 font_size 후보만 적용한다.
        필요하면 inner_text_*_off로 페이지 경계 안쪽에만 살짝 밀어 넣는다.
        x_off/y_off, OCR rect, 줄내림은 변경하지 않는다.
        """
        if not isinstance(item, dict) or not item.get('use_inpaint', True):
            return None
        try:
            if self.text_item_writing_direction(item) == 'vertical':
                return None
        except Exception:
            pass
        try:
            text_key, text_value = self._auto_layout_text_key_and_value(item)
        except Exception:
            text_key = 'translated_text' if str(item.get('translated_text', '') or '').strip() else 'text'
            text_value = item.get(text_key, '') or ''
        raw_text = str(text_value or '').replace('\r\n', '\n').replace('\r', '\n').strip()
        if not raw_text:
            return None
        try:
            old_size = max(1, int(round(float(item.get('font_size', 0) or 0))))
        except Exception:
            old_size = 1
        try:
            target_size = max(old_size, min(260, int(round(float(target_size or old_size)))))
        except Exception:
            target_size = old_size
        if target_size <= old_size:
            return None
        old_text = str(item.get(text_key, '') or '')
        old_font = item.get('font_size')
        try:
            locked_ocr_rect_value = list(item.get('rect') or [])
        except Exception:
            locked_ocr_rect_value = []
        try:
            old_ix = int(round(float(item.get('inner_text_x_off', 0) or 0)))
        except Exception:
            old_ix = 0
        try:
            old_iy = int(round(float(item.get('inner_text_y_off', 0) or 0)))
        except Exception:
            old_iy = 0

        best = None
        blocked = None
        grow_fail_trace = []
        grow_fail_reason_totals = {
            'boundary': 0,
            'outside_ocr_rect_plus_10_percent': 0,
            'overlap': 0,
            'exception': 0,
            'measure_failed': 0,
            'empty_text_after_measure': 0,
        }

        def _locked_ocr_qrect():
            try:
                vals = locked_ocr_rect_value if locked_ocr_rect_value else (item.get('rect') or [0, 0, 1, 1])
                x0, y0, w0, h0 = [float(v) for v in list(vals)[:4]]
                return QRectF(x0, y0, max(1.0, w0), max(1.0, h0))
            except Exception:
                return None

        def _locked_ocr_allowed_qrect():
            """OCR rect는 절대 고정하되, 텍스트 visual bounds는 총 10%까지만 넘을 수 있다."""
            try:
                box = _locked_ocr_qrect()
                if box is None:
                    return None
                w = max(1.0, float(box.width()))
                h = max(1.0, float(box.height()))
                mx = w * 0.05
                my = h * 0.05
                return QRectF(float(box.x()) - mx, float(box.y()) - my, w + mx * 2.0, h + my * 2.0)
            except Exception:
                return _locked_ocr_qrect()

        def _rect_inside_locked_ocr(rect, *, tolerance=0.5):
            try:
                box = _locked_ocr_allowed_qrect()
                if box is None or rect is None:
                    return False
                return (
                    float(rect.left()) >= float(box.left()) - float(tolerance)
                    and float(rect.top()) >= float(box.top()) - float(tolerance)
                    and float(rect.right()) <= float(box.right()) + float(tolerance)
                    and float(rect.bottom()) <= float(box.bottom()) + float(tolerance)
                )
            except Exception:
                return False

        def _restore():
            try:
                item[text_key] = old_text
                item['font_size'] = old_font
                item['inner_text_x_off'] = int(old_ix)
                item['inner_text_y_off'] = int(old_iy)
                # OCR rect는 절대 불변. 텍스트 위치 탐색 중 어떤 경로가 rect를 건드려도 즉시 원복한다.
                if locked_ocr_rect_value:
                    item['rect'] = list(locked_ocr_rect_value)
            except Exception:
                pass

        def _record_grow_failure(reason, *, size=None, inner_offset=None, info=None, sample=None, fail_reasons=None):
            nonlocal blocked
            try:
                reason = str(reason or 'unknown')
                if reason not in grow_fail_reason_totals:
                    grow_fail_reason_totals[reason] = 0
                grow_fail_reason_totals[reason] += 1
            except Exception:
                pass
            entry = {
                'size': int(size) if size is not None else None,
                'reason': str(reason or 'unknown'),
            }
            try:
                if inner_offset is not None:
                    entry['inner_offset'] = [int(inner_offset[0]), int(inner_offset[1])]
            except Exception:
                pass
            if info is not None:
                try:
                    entry['info'] = info
                except Exception:
                    pass
            if sample is not None:
                try:
                    entry['sample'] = sample
                except Exception:
                    pass
            if fail_reasons is not None:
                try:
                    entry['fail_reasons'] = dict(fail_reasons)
                except Exception:
                    pass
            blocked = dict(entry)
            try:
                grow_fail_trace.append(dict(entry))
                if len(grow_fail_trace) > 16:
                    del grow_fail_trace[:-16]
            except Exception:
                pass
            return entry

        def _rect_debug_list(rect):
            try:
                if rect is None:
                    return None
                return [round(float(rect.x()), 2), round(float(rect.y()), 2), round(float(rect.width()), 2), round(float(rect.height()), 2)]
            except Exception:
                return None

        def _rect_area(rect):
            try:
                if rect is None:
                    return 0.0
                return max(0.0, float(rect.width())) * max(0.0, float(rect.height()))
            except Exception:
                return 0.0

        def _valid_safe_rect(rect, *, min_side=3.0):
            try:
                return (
                    rect is not None
                    and float(rect.width()) >= float(min_side)
                    and float(rect.height()) >= float(min_side)
                )
            except Exception:
                return False

        def _rect_intersection(a, b, *, min_side=1.0):
            try:
                if a is None or b is None or not a.intersects(b):
                    return None
                inter = a.intersected(b)
                if float(inter.width()) < float(min_side) or float(inter.height()) < float(min_side):
                    return None
                return QRectF(inter)
            except Exception:
                return None

        def _dedupe_rects(rects, *, limit=64):
            out = []
            seen = set()
            try:
                rects = sorted(list(rects or []), key=lambda r: _rect_area(r), reverse=True)
            except Exception:
                rects = list(rects or [])
            for r in rects:
                if not _valid_safe_rect(r):
                    continue
                try:
                    key = (
                        int(round(float(r.x()))),
                        int(round(float(r.y()))),
                        int(round(float(r.width()))),
                        int(round(float(r.height()))),
                    )
                except Exception:
                    continue
                if key in seen:
                    continue
                seen.add(key)
                out.append(QRectF(r))
                if len(out) >= int(limit):
                    break
            return out

        def _split_rect_around_intrusion(rect, intr):
            # rect 안에 intr이 침범한 경우, intr을 피해 쓸 수 있는 위/아래/좌/우 사각형 후보를 만든다.
            # OCR rect 자체는 바꾸지 않고, 후처리 grow에서만 쓰는 임시 안전영역이다.
            try:
                inter = _rect_intersection(rect, intr, min_side=1.0)
                if inter is None:
                    return [QRectF(rect)] if _valid_safe_rect(rect) else []
                parts = []
                left = float(rect.left())
                right = float(rect.right())
                top = float(rect.top())
                bottom = float(rect.bottom())
                ix1 = float(inter.left())
                ix2 = float(inter.right())
                iy1 = float(inter.top())
                iy2 = float(inter.bottom())
                # 침범 위쪽 전체 폭
                parts.append(QRectF(left, top, max(0.0, right - left), max(0.0, iy1 - top)))
                # 침범 아래쪽 전체 폭
                parts.append(QRectF(left, iy2, max(0.0, right - left), max(0.0, bottom - iy2)))
                # 침범 왼쪽 전체 높이
                parts.append(QRectF(left, top, max(0.0, ix1 - left), max(0.0, bottom - top)))
                # 침범 오른쪽 전체 높이
                parts.append(QRectF(ix2, top, max(0.0, right - ix2), max(0.0, bottom - top)))
                return [QRectF(p) for p in parts if _valid_safe_rect(p)]
            except Exception:
                return [QRectF(rect)] if _valid_safe_rect(rect) else []

        def _safe_rect_candidates_excluding_neighbors():
            """현재 item의 OCR 영역에서 이웃의 실제 렌더 텍스트 침범분을 뺀 안전 사각형 후보를 계산한다.

            핵심 정책:
            - 이웃 OCR 박스가 아니라 실제 렌더 line bbox만 침범 영역으로 본다.
            - item['rect']는 절대 수정하지 않는다.
            - 줄 수/줄바꿈/line_spacing은 건드리지 않고, grow 후보 위치 계산에만 사용한다.
            """
            try:
                base = _locked_ocr_qrect()
                if base is None:
                    return []
                try:
                    if page_rect is not None and base.intersects(page_rect):
                        base = base.intersected(page_rect)
                except Exception:
                    pass
                if not _valid_safe_rect(base):
                    return []

                intrusions = []
                current_id = item.get('id')
                for other in active or []:
                    try:
                        if other is item:
                            continue
                        if isinstance(other, dict) and other.get('id') == current_id:
                            continue
                        other_text = other.get('translated_text') or other.get('text') or ''
                        if not str(other_text or '').strip():
                            continue
                        for lr in self._auto_adjust_visual_line_rects_for_item(other) or []:
                            inter = _rect_intersection(base, lr, min_side=1.0)
                            if inter is not None:
                                intrusions.append(inter)
                    except Exception:
                        continue

                intrusions = _dedupe_rects(intrusions, limit=24)
                if not intrusions:
                    return [QRectF(base)]

                candidates = [QRectF(base)]
                for intr in intrusions:
                    next_candidates = []
                    for cand in candidates:
                        try:
                            if cand.intersects(intr):
                                next_candidates.extend(_split_rect_around_intrusion(cand, intr))
                            else:
                                next_candidates.append(QRectF(cand))
                        except Exception:
                            continue
                    candidates = _dedupe_rects(next_candidates, limit=64)
                    if not candidates:
                        break

                # 면적만 최선 기준으로 쓰면 길쭉한 사각형이 과대평가될 수 있으니,
                # 후보는 여러 개 유지하고 실제 텍스트 측정/겹침 검사 단계에서 최종 선택한다.
                return _dedupe_rects(candidates, limit=32)
            except Exception:
                return []

        def _add_offsets_for_safe_rect(offset_add, base_rr, safe_rects):
            # 14차에서 쓰던 레거시 헬퍼. 15차 이후 안전 사각형은 위치 후보가 아니라
            # 폭/높이 기준 font_size 이분탐색에 사용하므로 현재 경로에서는 호출하지 않는다.
            try:
                if base_rr is None:
                    return 0
                added = 0
                bw = max(1.0, float(base_rr.width()))
                bh = max(1.0, float(base_rr.height()))
                base_left = float(base_rr.left())
                base_top = float(base_rr.top())
                for sr in list(safe_rects or [])[:16]:
                    if not _valid_safe_rect(sr):
                        continue
                    sx1 = float(sr.left())
                    sx2 = float(sr.right())
                    sy1 = float(sr.top())
                    sy2 = float(sr.bottom())
                    # safe rect에 들어갈 수 있으면 중앙/모서리/클램프 위치를 모두 후보화한다.
                    if bw <= max(1.0, float(sr.width())):
                        x_positions = [sx1 + (float(sr.width()) - bw) * 0.5, sx1, sx2 - bw]
                    else:
                        x_positions = [sx1 + (float(sr.width()) - bw) * 0.5, sx1, sx2 - bw]
                    if bh <= max(1.0, float(sr.height())):
                        y_positions = [sy1 + (float(sr.height()) - bh) * 0.5, sy1, sy2 - bh]
                    else:
                        y_positions = [sy1 + (float(sr.height()) - bh) * 0.5, sy1, sy2 - bh]
                    # 현재 위치를 safe rect 안으로 최소 이동시키는 후보도 추가한다.
                    try:
                        clamped_x = min(max(base_left, sx1), sx2 - bw)
                        clamped_y = min(max(base_top, sy1), sy2 - bh)
                        x_positions.append(clamped_x)
                        y_positions.append(clamped_y)
                    except Exception:
                        pass
                    for px in x_positions:
                        for py in y_positions:
                            try:
                                ox = float(old_ix) + (float(px) - base_left)
                                oy = float(old_iy) + (float(py) - base_top)
                                offset_add(ox, oy)
                                added += 1
                            except Exception:
                                pass
                return int(added)
            except Exception:
                return 0

        def _safe_rect_based_best_candidate():
            """15차: 안전 사각형의 폭/높이를 기준으로 최대 font_size를 먼저 계산한다.

            14차 구현은 이미 test_size로 만들어진 렌더 블록을 안전 사각형 안으로
            옮기는 후보만 추가했다. 그러면 블록이 안전 사각형보다 큰 경우 어떤 위치로도
            통과할 수 없다. 여기서는 각 안전 사각형별로 현재 줄 구성 그대로 들어가는
            최대 font_size를 이분탐색하고, 그 결과를 실제 위치/경계/겹침 검증까지 통과한
            후보로 만든다.
            """
            safe_rects = []
            try:
                safe_rects = _safe_rect_candidates_excluding_neighbors()
            except Exception:
                safe_rects = []
            safe_rects = list(safe_rects or [])[:16]
            if not safe_rects:
                return None

            local_best = None
            checked = 0
            fit_debug = []

            def _is_better_candidate(cand, cur):
                try:
                    if cand is None:
                        return False
                    if cur is None:
                        return True
                    cand_size = int(cand.get('size') or 0)
                    cur_size = int(cur.get('size') or 0)
                    if cand_size != cur_size:
                        return cand_size > cur_size
                    cand_move = abs(int(cand.get('inner_text_x_off', old_ix)) - int(old_ix)) + abs(int(cand.get('inner_text_y_off', old_iy)) - int(old_iy))
                    cur_move = abs(int(cur.get('inner_text_x_off', old_ix)) - int(old_ix)) + abs(int(cur.get('inner_text_y_off', old_iy)) - int(old_iy))
                    if cand_move != cur_move:
                        return cand_move < cur_move
                    cand_area = float(cand.get('safe_rect_area') or 0.0)
                    cur_area = float(cur.get('safe_rect_area') or 0.0)
                    return cand_area > cur_area
                except Exception:
                    return cur is None

            def _measure_for_size(size):
                try:
                    item[text_key] = old_text
                    item['font_size'] = int(size)
                    item['inner_text_x_off'] = int(old_ix)
                    item['inner_text_y_off'] = int(old_iy)
                    if locked_ocr_rect_value:
                        item['rect'] = list(locked_ocr_rect_value)
                    return self._auto_text_rewrap_item_for_font_size(item, int(size), page_idx=page_idx)
                except Exception:
                    return None

            def _offset_candidates_for_safe_rect(render_rect, safe_rect):
                offsets = []
                seen = set()

                def _add_from_left_top(px, py):
                    try:
                        ox = int(round(float(old_ix) + (float(px) - float(render_rect.left()))))
                        oy = int(round(float(old_iy) + (float(py) - float(render_rect.top()))))
                        key = (ox, oy)
                        if key not in seen:
                            seen.add(key)
                            offsets.append(key)
                    except Exception:
                        pass

                try:
                    bw = max(1.0, float(render_rect.width()))
                    bh = max(1.0, float(render_rect.height()))
                    sx1 = float(safe_rect.left())
                    sy1 = float(safe_rect.top())
                    sx2 = float(safe_rect.right())
                    sy2 = float(safe_rect.bottom())
                    sw = max(1.0, float(safe_rect.width()))
                    sh = max(1.0, float(safe_rect.height()))

                    # 1순위: 안전 사각형 중앙. 14/15차 의도에 가장 가까운 배치.
                    _add_from_left_top(sx1 + (sw - bw) * 0.5, sy1 + (sh - bh) * 0.5)
                    # 현재 위치에서 최소 이동으로 안전 사각형 안에 넣는 후보.
                    _add_from_left_top(min(max(float(render_rect.left()), sx1), sx2 - bw), min(max(float(render_rect.top()), sy1), sy2 - bh))
                    # 정렬/말풍선 모양에 따라 중앙보다 모서리가 더 나은 경우가 있어 함께 검증.
                    _add_from_left_top(sx1, sy1)
                    _add_from_left_top(sx2 - bw, sy1)
                    _add_from_left_top(sx1, sy2 - bh)
                    _add_from_left_top(sx2 - bw, sy2 - bh)
                    _add_from_left_top(sx1 + (sw - bw) * 0.5, sy1)
                    _add_from_left_top(sx1 + (sw - bw) * 0.5, sy2 - bh)
                    _add_from_left_top(sx1, sy1 + (sh - bh) * 0.5)
                    _add_from_left_top(sx2 - bw, sy1 + (sh - bh) * 0.5)
                except Exception:
                    pass
                return offsets

            try:
                upper_limit = 260
                for sr in safe_rects:
                    if not _valid_safe_rect(sr):
                        continue
                    checked += 1
                    sw = max(1.0, float(sr.width()))
                    sh = max(1.0, float(sr.height()))
                    lo = int(old_size) + 1
                    hi = int(upper_limit)
                    fit_result = None
                    fit_size = int(old_size)
                    while lo <= hi:
                        mid = (int(lo) + int(hi)) // 2
                        result = _measure_for_size(mid)
                        if not result:
                            hi = int(mid) - 1
                            continue
                        try:
                            mw = float(result.get('measured_w') or 0.0)
                            mh = float(result.get('measured_h') or 0.0)
                        except Exception:
                            mw = mh = 999999.0
                        if mw <= sw + 0.5 and mh <= sh + 0.5:
                            fit_result = result
                            fit_size = int(mid)
                            lo = int(mid) + 1
                        else:
                            hi = int(mid) - 1

                    if fit_result is None or int(fit_size) <= int(old_size):
                        try:
                            fit_debug.append({'safe_rect': _rect_debug_list(sr), 'fit_size': int(fit_size), 'accepted': False, 'reason': 'no_larger_size_fits_safe_rect'})
                        except Exception:
                            pass
                        continue

                    # 측정값으로 들어간다고 나와도 실제 렌더 bbox/경계/겹침은 반드시 다시 검증한다.
                    # 최댓값이 실패하면 한 칸씩 낮춰서 같은 안전 사각형에서 실제 통과값을 찾는다.
                    accepted_for_rect = None
                    for try_size in range(int(fit_size), int(old_size), -1):
                        result = _measure_for_size(try_size)
                        if not result:
                            continue
                        new_text_for_safe = str(result.get('text') or '').strip()
                        if not new_text_for_safe:
                            continue
                        try:
                            item[text_key] = new_text_for_safe
                            item['font_size'] = int(try_size)
                            item['inner_text_x_off'] = int(old_ix)
                            item['inner_text_y_off'] = int(old_iy)
                            if locked_ocr_rect_value:
                                item['rect'] = list(locked_ocr_rect_value)
                            base_rr = self._auto_adjust_visual_rect_for_item(item)
                        except Exception:
                            base_rr = None
                        if base_rr is None:
                            continue

                        for cand_ix, cand_iy in _offset_candidates_for_safe_rect(base_rr, sr):
                            try:
                                item[text_key] = new_text_for_safe
                                item['font_size'] = int(try_size)
                                item['inner_text_x_off'] = int(cand_ix)
                                item['inner_text_y_off'] = int(cand_iy)
                                if locked_ocr_rect_value:
                                    item['rect'] = list(locked_ocr_rect_value)
                                rr = self._auto_adjust_visual_rect_for_item(item)
                                boundary_info = self._auto_text_size_page_boundary_overflow_info(rr, page_rect)
                                if bool(boundary_info.get('overflow')):
                                    continue
                                if not _rect_inside_locked_ocr(rr, tolerance=0.5):
                                    continue
                                ov, ov_info = self._auto_text_item_overlaps_any(item, active, strict=True)
                                if ov:
                                    continue
                                accepted_for_rect = {
                                    'size': int(try_size),
                                    'text_key': text_key,
                                    'text': new_text_for_safe,
                                    'lines': list(result.get('lines') or []),
                                    'measured_w': float(result.get('measured_w') or 0.0),
                                    'measured_h': float(result.get('measured_h') or 0.0),
                                    'inner_text_x_off': int(cand_ix),
                                    'inner_text_y_off': int(cand_iy),
                                    'visual_rect': _rect_debug_list(rr),
                                    'safe_rect': _rect_debug_list(sr),
                                    'safe_rect_area': float(_rect_area(sr)),
                                    'source': 'safe_rect_binary_fit',
                                }
                                break
                            except Exception:
                                continue
                        if accepted_for_rect is not None:
                            break

                    try:
                        fit_debug.append({
                            'safe_rect': _rect_debug_list(sr),
                            'fit_size': int(fit_size),
                            'accepted': bool(accepted_for_rect is not None),
                            'accepted_size': int(accepted_for_rect.get('size')) if accepted_for_rect else None,
                        })
                    except Exception:
                        pass
                    if _is_better_candidate(accepted_for_rect, local_best):
                        local_best = dict(accepted_for_rect)
            finally:
                _restore()

            try:
                if hasattr(self, 'audit_boundary_event'):
                    self.audit_boundary_event(
                        'TEXT_AUTO_ADJUST_AVAILABLE_SPACE_GROW_SAFE_RECT_FIT_DONE',
                        page_idx=page_idx,
                        item_id=item.get('id'),
                        old_size=int(old_size),
                        target_size=int(target_size),
                        safe_rect_count=int(len(safe_rects)),
                        checked_safe_rect_count=int(checked),
                        selected_size=int(local_best.get('size')) if local_best else None,
                        selected_safe_rect=local_best.get('safe_rect') if local_best else None,
                        fit_debug_tail=list(fit_debug[-8:]),
                        reason=str(reason or ''),
                        policy='fit_font_size_by_safe_rect_width_height_before_offset_grid_search',
                    )
            except Exception:
                pass
            try:
                self._auto_text_size_force_grow_debug_log(
                    'TEXT_AUTO_ADJUST_AVAILABLE_SPACE_GROW_SAFE_RECT_FIT_DONE_FORCE',
                    page_idx=page_idx,
                    item_id=item.get('id'),
                    old_size=int(old_size),
                    target_size=int(target_size),
                    safe_rect_count=int(len(safe_rects)),
                    checked_safe_rect_count=int(checked),
                    selected_size=int(local_best.get('size')) if local_best else None,
                    selected_safe_rect=local_best.get('safe_rect') if local_best else None,
                    fit_debug_tail=list(fit_debug[-12:]),
                    reason=str(reason or ''),
                    policy='forced_safe_rect_binary_fit_debug_log',
                )
            except Exception:
                pass
            return local_best

        def _candidate_offsets_for_size(size, new_text):
            # 재성장 단계는 글자 크기만 키우는 것이 아니라, OCR 영역 안쪽/주변에서
            # inner offset도 함께 탐색해야 한다. 이전 구현은 old offset과 page clamp만
            # 시험해서, 위쪽 텍스트와 겹치는 작은 박스가 있으면 곧장 성장 실패로 끝났다.
            # 여기서는 OCR 내부 중앙/페이지 경계 보정/주변 그리드를 모두 후보로 넣되,
            # OCR 안에 들어가는 후보를 먼저 시도한다.
            offsets = []

            def _add(ox, oy):
                try:
                    ox = int(round(float(ox)))
                    oy = int(round(float(oy)))
                except Exception:
                    return
                pair = (ox, oy)
                if pair not in offsets:
                    offsets.append(pair)

            def _rect_inside(container, rect):
                try:
                    if container is None or rect is None:
                        return False
                    return (
                        float(rect.left()) >= float(container.left()) - 0.5
                        and float(rect.top()) >= float(container.top()) - 0.5
                        and float(rect.right()) <= float(container.right()) + 0.5
                        and float(rect.bottom()) <= float(container.bottom()) + 0.5
                    )
                except Exception:
                    return False

            _add(old_ix, old_iy)
            try:
                item[text_key] = new_text
                item['font_size'] = int(size)
                item['inner_text_x_off'] = int(old_ix)
                item['inner_text_y_off'] = int(old_iy)
                base_rr = self._auto_adjust_visual_rect_for_item(item)
                info = self._auto_text_size_page_boundary_overflow_info(base_rr, page_rect)
                if bool(info.get('overflow')):
                    dx, dy = self._auto_text_size_page_boundary_clamp_delta(base_rr, page_rect)
                    _add(float(old_ix) + float(dx), float(old_iy) + float(dy))

                ocr_rect = _locked_ocr_qrect()
                allowed_ocr_rect = _locked_ocr_allowed_qrect()

                if base_rr is not None and ocr_rect is not None and allowed_ocr_rect is not None:
                    # 15차: 안전 사각형은 이제 여기서 "이미 렌더된 블록의 위치 후보"로 쓰지 않는다.
                    # 사이즈 루프 시작 전에 안전 사각형 폭/높이 기준 이분탐색으로 먼저 평가한다.
                    # 여기서는 기존 grid fallback 후보만 유지한다.

                    # OCR 중심에 맞추는 후보.
                    try:
                        center_dx = float(ocr_rect.center().x()) - float(base_rr.center().x())
                        center_dy = float(ocr_rect.center().y()) - float(base_rr.center().y())
                        _add(float(old_ix) + center_dx, float(old_iy) + center_dy)
                    except Exception:
                        pass

                    # OCR 허용 박스(원본 OCR 총 10% 확장) 안으로 밀어 넣는 후보.
                    # OCR rect 자체는 절대 움직이지 않는다.
                    try:
                        fit_dx = 0.0
                        fit_dy = 0.0
                        if float(base_rr.left()) < float(allowed_ocr_rect.left()):
                            fit_dx += float(allowed_ocr_rect.left()) - float(base_rr.left())
                        if float(base_rr.right()) > float(allowed_ocr_rect.right()):
                            fit_dx -= float(base_rr.right()) - float(allowed_ocr_rect.right())
                        if float(base_rr.top()) < float(allowed_ocr_rect.top()):
                            fit_dy += float(allowed_ocr_rect.top()) - float(base_rr.top())
                        if float(base_rr.bottom()) > float(allowed_ocr_rect.bottom()):
                            fit_dy -= float(base_rr.bottom()) - float(allowed_ocr_rect.bottom())
                        _add(float(old_ix) + fit_dx, float(old_iy) + fit_dy)
                    except Exception:
                        pass

                    # 겹침 회피용 주변 그리드.
                    # 기존 구현은 OCR 박스 크기의 35% 단일 스텝만 사용해서, 10~20px 단위의 좁은 틈을
                    # 통째로 건너뛸 수 있었다. 먼저 큰 격자로 방향을 잡고, 그중 페이지/OCR 제약 비용이
                    # 낮은 후보 주변만 작은 격자로 다시 훑는 coarse-to-fine 탐색으로 바꾼다.
                    try:
                        bw = max(1.0, float(base_rr.width()))
                        bh = max(1.0, float(base_rr.height()))
                        coarse_sx = max(6.0, min(max(24.0, float(ocr_rect.width()) * 0.35), bw * 0.65))
                        coarse_sy = max(6.0, min(max(24.0, float(ocr_rect.height()) * 0.35), bh * 0.90))

                        coarse_anchors = list(offsets)
                        for ax, ay in coarse_anchors[:6]:
                            for dx in (-coarse_sx, -coarse_sx * 0.5, 0.0, coarse_sx * 0.5, coarse_sx):
                                for dy in (-coarse_sy, -coarse_sy * 0.5, 0.0, coarse_sy * 0.5, coarse_sy):
                                    _add(float(ax) + dx, float(ay) + dy)

                        def _outside_amount(container, rect):
                            try:
                                if container is None or rect is None:
                                    return 999999.0
                                amount = 0.0
                                if float(rect.left()) < float(container.left()):
                                    amount += float(container.left()) - float(rect.left())
                                if float(rect.right()) > float(container.right()):
                                    amount += float(rect.right()) - float(container.right())
                                if float(rect.top()) < float(container.top()):
                                    amount += float(container.top()) - float(rect.top())
                                if float(rect.bottom()) > float(container.bottom()):
                                    amount += float(rect.bottom()) - float(container.bottom())
                                return max(0.0, float(amount))
                            except Exception:
                                return 999999.0

                        def _probe_offset_cost(ox, oy):
                            try:
                                item[text_key] = new_text
                                item['font_size'] = int(size)
                                item['inner_text_x_off'] = int(round(float(ox)))
                                item['inner_text_y_off'] = int(round(float(oy)))
                                rr = self._auto_adjust_visual_rect_for_item(item)
                                boundary_info = self._auto_text_size_page_boundary_overflow_info(rr, page_rect)
                                page_cost = float((boundary_info or {}).get('cost') or 0.0)
                                ocr_cost = _outside_amount(allowed_ocr_rect, rr)
                                move = abs(int(round(float(ox))) - int(old_ix)) + abs(int(round(float(oy))) - int(old_iy))
                                return (page_cost, ocr_cost, move, int(round(float(ox))), int(round(float(oy))))
                            except Exception:
                                try:
                                    move = abs(int(round(float(ox))) - int(old_ix)) + abs(int(round(float(oy))) - int(old_iy))
                                except Exception:
                                    move = 999999
                                return (999999.0, 999999.0, move, int(round(float(ox))), int(round(float(oy))))

                        probe_scored = [_probe_offset_cost(ox, oy) for ox, oy in list(offsets)]
                        probe_scored.sort()

                        # 2단계: 유망 후보 주변을 8~16px 단위로 촘촘히 다시 탐색한다.
                        fine_sx = max(4.0, min(12.0, coarse_sx * 0.15))
                        fine_sy = max(4.0, min(16.0, coarse_sy * 0.15))
                        for _page_cost, _ocr_cost, _move, ax, ay in probe_scored[:8]:
                            for dx in (-fine_sx * 2.0, -fine_sx, 0.0, fine_sx, fine_sx * 2.0):
                                for dy in (-fine_sy * 2.0, -fine_sy, 0.0, fine_sy, fine_sy * 2.0):
                                    _add(float(ax) + dx, float(ay) + dy)

                        # 3단계: 최상위 후보는 4px 단위로 한 번 더 훑어 좁은 틈을 놓치지 않는다.
                        micro_step = 4.0
                        for _page_cost, _ocr_cost, _move, ax, ay in probe_scored[:4]:
                            for dx in (-micro_step * 2.0, -micro_step, 0.0, micro_step, micro_step * 2.0):
                                for dy in (-micro_step * 2.0, -micro_step, 0.0, micro_step, micro_step * 2.0):
                                    _add(float(ax) + dx, float(ay) + dy)
                    except Exception:
                        pass

                # 후보 정렬: 페이지 안, OCR 안, 이동량 작은 순서.
                scored = []
                for ox, oy in offsets:
                    try:
                        item[text_key] = new_text
                        item['font_size'] = int(size)
                        item['inner_text_x_off'] = int(ox)
                        item['inner_text_y_off'] = int(oy)
                        rr = self._auto_adjust_visual_rect_for_item(item)
                        boundary_info = self._auto_text_size_page_boundary_overflow_info(rr, page_rect)
                        page_cost = float((boundary_info or {}).get('cost') or 0.0)
                        inside_ocr = _rect_inside(allowed_ocr_rect, rr) if 'allowed_ocr_rect' in locals() else False
                        move = abs(int(ox) - int(old_ix)) + abs(int(oy) - int(old_iy))
                        scored.append((page_cost, 0 if inside_ocr else 1, move, int(ox), int(oy)))
                    except Exception:
                        scored.append((999999.0, 2, abs(int(ox) - int(old_ix)) + abs(int(oy) - int(old_iy)), int(ox), int(oy)))
                scored.sort()
                offsets = [(x[3], x[4]) for x in scored]
            except Exception:
                pass
            return offsets

        safe_rect_best = None
        try:
            safe_rect_best = _safe_rect_based_best_candidate()
        except Exception:
            safe_rect_best = None
            _restore()

        consecutive_fail_count = 0
        max_consecutive_fail_count = 8
        best_success_size = int(old_size)

        for test_size in range(old_size + 1, target_size + 1):
            ok_at_this_size = False
            result = None
            try:
                item[text_key] = old_text
                item['font_size'] = int(test_size)
                item['inner_text_x_off'] = int(old_ix)
                item['inner_text_y_off'] = int(old_iy)
                result = self._auto_text_rewrap_item_for_font_size(item, test_size, page_idx=page_idx)
            except Exception:
                result = None
            if not result:
                _record_grow_failure('measure_failed', size=int(test_size))
                break
            new_text = str(result.get('text') or '').strip()
            if not new_text:
                _record_grow_failure('empty_text_after_measure', size=int(test_size))
                break

            size_fail_reasons = {
                'boundary': 0,
                'outside_ocr_rect_plus_10_percent': 0,
                'overlap': 0,
                'exception': 0,
            }
            size_fail_first = None
            size_fail_last = None
            size_candidate_count = 0
            for cand_ix, cand_iy in _candidate_offsets_for_size(test_size, new_text):
                size_candidate_count += 1
                try:
                    item[text_key] = new_text
                    item['font_size'] = int(test_size)
                    item['inner_text_x_off'] = int(cand_ix)
                    item['inner_text_y_off'] = int(cand_iy)
                    rr = self._auto_adjust_visual_rect_for_item(item)
                    boundary_info = self._auto_text_size_page_boundary_overflow_info(rr, page_rect)
                    if bool(boundary_info.get('overflow')):
                        size_fail_reasons['boundary'] = int(size_fail_reasons.get('boundary', 0)) + 1
                        entry = _record_grow_failure(
                            'boundary',
                            size=int(test_size),
                            inner_offset=[int(cand_ix), int(cand_iy)],
                            info={'overflow_info': boundary_info},
                        )
                        if size_fail_first is None:
                            size_fail_first = dict(entry)
                        size_fail_last = dict(entry)
                        continue
                    if not _rect_inside_locked_ocr(rr, tolerance=0.5):
                        try:
                            ocr_box = _locked_ocr_qrect()
                            ocr_info = [round(float(ocr_box.x()), 2), round(float(ocr_box.y()), 2), round(float(ocr_box.width()), 2), round(float(ocr_box.height()), 2)] if ocr_box is not None else None
                        except Exception:
                            ocr_info = None
                        try:
                            allowed_box = _locked_ocr_allowed_qrect()
                            allowed_info = [round(float(allowed_box.x()), 2), round(float(allowed_box.y()), 2), round(float(allowed_box.width()), 2), round(float(allowed_box.height()), 2)] if allowed_box is not None else None
                        except Exception:
                            allowed_info = None
                        size_fail_reasons['outside_ocr_rect_plus_10_percent'] = int(size_fail_reasons.get('outside_ocr_rect_plus_10_percent', 0)) + 1
                        entry = _record_grow_failure(
                            'outside_ocr_rect_plus_10_percent',
                            size=int(test_size),
                            inner_offset=[int(cand_ix), int(cand_iy)],
                            info={
                                'ocr_rect': ocr_info,
                                'allowed_overflow_ratio': 0.10,
                                'allowed_rect': allowed_info,
                                'visual_rect': [round(float(rr.x()), 2), round(float(rr.y()), 2), round(float(rr.width()), 2), round(float(rr.height()), 2)] if rr is not None else None,
                                'policy': 'available_space_grow_must_keep_visual_text_inside_ocr_rect_plus_10_percent',
                            },
                        )
                        if size_fail_first is None:
                            size_fail_first = dict(entry)
                        size_fail_last = dict(entry)
                        continue
                    ov, ov_info = self._auto_text_item_overlaps_any(item, active, strict=True)
                    if ov:
                        blocker_id = None
                        try:
                            # 현재 상세 overlap info에는 id가 없으므로, rect만 보조로 남긴다.
                            blocker_id = ov_info.get('fixed_item_id') if isinstance(ov_info, dict) else None
                        except Exception:
                            blocker_id = None
                        size_fail_reasons['overlap'] = int(size_fail_reasons.get('overlap', 0)) + 1
                        entry = _record_grow_failure(
                            'overlap',
                            size=int(test_size),
                            inner_offset=[int(cand_ix), int(cand_iy)],
                            info={'overlap_info': ov_info, 'blocker_item_id': blocker_id},
                        )
                        if size_fail_first is None:
                            size_fail_first = dict(entry)
                        size_fail_last = dict(entry)
                        continue
                    best = {
                        'size': int(test_size),
                        'text_key': text_key,
                        'text': new_text,
                        'lines': list(result.get('lines') or []),
                        'measured_w': float(result.get('measured_w') or 0.0),
                        'measured_h': float(result.get('measured_h') or 0.0),
                        'inner_text_x_off': int(cand_ix),
                        'inner_text_y_off': int(cand_iy),
                        'visual_rect': [round(float(rr.x()), 2), round(float(rr.y()), 2), round(float(rr.width()), 2), round(float(rr.height()), 2)] if rr is not None else None,
                    }
                    ok_at_this_size = True
                    break
                except Exception as exc:
                    size_fail_reasons['exception'] = int(size_fail_reasons.get('exception', 0)) + 1
                    entry = _record_grow_failure(
                        'exception',
                        size=int(test_size),
                        inner_offset=[int(cand_ix), int(cand_iy)],
                        info={'error': repr(exc)},
                    )
                    if size_fail_first is None:
                        size_fail_first = dict(entry)
                    size_fail_last = dict(entry)
                    continue
            if not ok_at_this_size:
                try:
                    _grow_size_fail_payload = {
                        'page_idx': page_idx,
                        'item_id': item.get('id'),
                        'test_size': int(test_size),
                        'old_size': int(old_size),
                        'target_size': int(target_size),
                        'candidate_count': int(size_candidate_count),
                        'fail_reasons': dict(size_fail_reasons),
                        'fail_first': size_fail_first or {},
                        'fail_last': size_fail_last or {},
                        'fail_trace_tail': list(grow_fail_trace[-12:]),
                        'reason': str(reason or ''),
                        'text_preview': str(new_text or '')[:160],
                        'old_text_preview': str(old_text or '')[:160],
                        'old_inner_offset': [int(old_ix), int(old_iy)],
                        'safe_rect_policy': 'compute_largest_free_rects_inside_ocr_excluding_rendered_neighbor_lines',
                        'overflow_check_enabled': bool(self.is_text_image_overflow_check_enabled()) if hasattr(self, 'is_text_image_overflow_check_enabled') else True,
                        'policy': 'record_each_size_failure_distribution_before_consecutive_fail_stop',
                    }
                except Exception:
                    _grow_size_fail_payload = {}
                try:
                    if hasattr(self, 'audit_boundary_event'):
                        self.audit_boundary_event(
                            'TEXT_AUTO_ADJUST_AVAILABLE_SPACE_GROW_SIZE_FAIL',
                            **dict(_grow_size_fail_payload),
                        )
                except Exception:
                    pass
                try:
                    self._auto_text_size_force_grow_debug_log(
                        'TEXT_AUTO_ADJUST_AVAILABLE_SPACE_GROW_SIZE_FAIL_FORCE',
                        **dict(_grow_size_fail_payload),
                    )
                except Exception:
                    pass
            if ok_at_this_size:
                consecutive_fail_count = 0
                best_success_size = int(test_size)
            else:
                # 한국어 줄바꿈은 크기 변화에 따라 줄 구성이 비선형으로 바뀔 수 있다.
                # 한 크기에서 실패했다고 더 큰 크기가 반드시 더 나쁘다고 볼 수 없으므로
                # 즉시 중단하지 않고 다음 크기도 계속 탐색한다.
                consecutive_fail_count += 1
                if consecutive_fail_count >= max_consecutive_fail_count and int(test_size) > int(best_success_size):
                    try:
                        if hasattr(self, 'audit_boundary_event'):
                            self.audit_boundary_event(
                                'TEXT_AUTO_ADJUST_AVAILABLE_SPACE_GROW_CONTINUOUS_FAIL_STOP',
                                page_idx=page_idx,
                                item_id=item.get('id'),
                                old_size=int(old_size),
                                last_test_size=int(test_size),
                                target_size=int(target_size),
                                best_success_size=int(best_success_size),
                                consecutive_fail_count=int(consecutive_fail_count),
                                blocked_info=blocked or {},
                                fail_reason_totals=dict(grow_fail_reason_totals),
                                fail_trace_tail=list(grow_fail_trace[-8:]),
                                reason=str(reason or ''),
                                policy='continue_after_single_size_failure_stop_only_after_consecutive_failures',
                            )
                    except Exception:
                        pass
                    try:
                        self._auto_text_size_force_grow_debug_log(
                            'TEXT_AUTO_ADJUST_AVAILABLE_SPACE_GROW_CONTINUOUS_FAIL_STOP_FORCE',
                            page_idx=page_idx,
                            item_id=item.get('id'),
                            old_size=int(old_size),
                            last_test_size=int(test_size),
                            target_size=int(target_size),
                            best_success_size=int(best_success_size),
                            consecutive_fail_count=int(consecutive_fail_count),
                            blocked_info=blocked or {},
                            fail_reason_totals=dict(grow_fail_reason_totals),
                            fail_trace_tail=list(grow_fail_trace[-20:]),
                            reason=str(reason or ''),
                            overflow_check_enabled=bool(self.is_text_image_overflow_check_enabled()) if hasattr(self, 'is_text_image_overflow_check_enabled') else True,
                            policy='forced_unfiltered_continuous_fail_debug_log',
                        )
                    except Exception:
                        pass
                    break
                continue

        try:
            if safe_rect_best is not None:
                safe_size = int(safe_rect_best.get('size') or 0)
                cur_size = int(best.get('size') or 0) if best is not None else 0
                if safe_size > cur_size:
                    best = dict(safe_rect_best)
                    target_size = max(int(target_size), int(safe_size))
        except Exception:
            pass

        _restore()

        if best is None or int(best.get('size') or old_size) <= int(old_size):
            try:
                if hasattr(self, 'audit_boundary_event'):
                    self.audit_boundary_event(
                        'TEXT_AUTO_ADJUST_AVAILABLE_SPACE_GROW_BLOCKED',
                        page_idx=page_idx,
                        item_id=item.get('id'),
                        old_size=int(old_size),
                        target_size=int(target_size),
                        blocked_info=blocked or {},
                        fail_reason_totals=dict(grow_fail_reason_totals),
                        fail_trace_tail=list(grow_fail_trace[-8:]),
                        reason=str(reason or ''),
                        policy='grow_continue_after_single_size_failure_preserve_ocr_rect_and_lines',
                    )
            except Exception:
                pass
            return None

        try:
            item[best['text_key']] = best['text']
            item['font_size'] = int(best['size'])
            item['inner_text_x_off'] = int(best.get('inner_text_x_off', old_ix))
            item['inner_text_y_off'] = int(best.get('inner_text_y_off', old_iy))
            if locked_ocr_rect_value:
                item['rect'] = list(locked_ocr_rect_value)
            item['auto_layout_available_space_grow_applied'] = True
            item['auto_layout_available_space_grow_reason'] = str(reason or '')
            item['auto_layout_available_space_grow_old_size'] = int(old_size)
            item['auto_layout_available_space_grow_new_size'] = int(best['size'])
            item['auto_layout_available_space_grow_target_size'] = int(target_size)
            item['auto_layout_available_space_grow_old_inner_text_x_off'] = int(old_ix)
            item['auto_layout_available_space_grow_old_inner_text_y_off'] = int(old_iy)
            item['auto_layout_available_space_grow_new_inner_text_x_off'] = int(best.get('inner_text_x_off', old_ix))
            item['auto_layout_available_space_grow_new_inner_text_y_off'] = int(best.get('inner_text_y_off', old_iy))
            item['auto_layout_available_space_grow_line_count'] = int(len(best.get('lines') or []))
            item['auto_layout_available_space_grow_visual_rect'] = best.get('visual_rect')
            item['auto_layout_available_space_grow_source'] = str(best.get('source') or 'grid_offset_search')
            if best.get('safe_rect') is not None:
                item['auto_layout_available_space_grow_safe_rect'] = best.get('safe_rect')
        except Exception:
            pass
        try:
            if hasattr(self, 'audit_boundary_event'):
                self.audit_boundary_event(
                    'TEXT_AUTO_ADJUST_AVAILABLE_SPACE_GROW_APPLIED',
                    page_idx=page_idx,
                    item_id=item.get('id'),
                    old_size=int(old_size),
                    new_size=int(best['size']),
                    target_size=int(target_size),
                    inner_offset_before=[int(old_ix), int(old_iy)],
                    inner_offset_after=[int(best.get('inner_text_x_off', old_ix)), int(best.get('inner_text_y_off', old_iy))],
                    line_count=int(len(best.get('lines') or [])),
                    visual_rect=best.get('visual_rect'),
                    source=str(best.get('source') or 'grid_offset_search'),
                    safe_rect=best.get('safe_rect'),
                    reason=str(reason or ''),
                    policy='safe_rect_binary_fit_competes_with_grid_offset_search_preserve_ocr_rect_and_lines',
                )
        except Exception:
            pass
        try:
            self._auto_text_size_force_grow_debug_log(
                'TEXT_AUTO_ADJUST_AVAILABLE_SPACE_GROW_APPLIED_FORCE',
                page_idx=page_idx,
                item_id=item.get('id'),
                old_size=int(old_size),
                new_size=int(best['size']),
                target_size=int(target_size),
                inner_offset_before=[int(old_ix), int(old_iy)],
                inner_offset_after=[int(best.get('inner_text_x_off', old_ix)), int(best.get('inner_text_y_off', old_iy))],
                line_count=int(len(best.get('lines') or [])),
                visual_rect=best.get('visual_rect'),
                source=str(best.get('source') or 'grid_offset_search'),
                safe_rect=best.get('safe_rect'),
                reason=str(reason or ''),
                policy='forced_unfiltered_applied_debug_log_safe_rect_binary_fit_enabled',
            )
        except Exception:
            pass
        return item.get('id')

    def _auto_text_size_available_space_grow_pass(self, page_idx, targets, *, phase='after_boundary'):
        """작은 텍스트를 OCR 10% 한계 안에서 위치/줄구성까지 보며 다시 키운다.

        1차 자동 조정은 OCR rect 기준으로 텍스트를 맞춘다. 이 패스는 충분히 큰 텍스트에는
        적용하지 않고, 페이지 대표 체급 대비 작은 텍스트나 앞선 보정으로 작아진 텍스트만
        실제 렌더 bounds 기준으로 안전하게 키운다.
        """
        try:
            size = self._auto_layout_page_image_size_for_auto(page_idx=page_idx)
        except Exception:
            size = None
        if not size:
            return []
        try:
            page_rect = QRectF(0.0, 0.0, float(size[0]), float(size[1]))
        except Exception:
            return []
        active = []
        for item in targets or []:
            if not isinstance(item, dict) or not item.get('use_inpaint', True):
                continue
            try:
                _key, text = self._auto_layout_text_key_and_value(item)
            except Exception:
                text = item.get('translated_text') or item.get('text') or ''
            if str(text or '').strip():
                active.append(item)
        if not active:
            return []
        changed_ids = []
        # 작은 글씨부터 기회를 준다. 이미 충분히 큰 글씨가 먼저 자리를 차지해서
        # 작은 글씨의 성장 가능성을 막는 일을 줄이기 위한 순서다.
        def _sort_key(x):
            try:
                fs = int(round(float(x.get('font_size', 0) or 0)))
            except Exception:
                fs = 0
            try:
                iid = int(x.get('id', 0) or 0)
            except Exception:
                iid = 0
            return (fs, iid)
        ordered = sorted(active, key=_sort_key)
        try:
            median_size = int(self._auto_text_size_page_median_font_size(active) or 0)
        except Exception:
            median_size = 0
        try:
            small_threshold = int(round(float(median_size) * 0.85)) if median_size > 0 else 72
        except Exception:
            small_threshold = 72
        # available-space grow는 OCR rect를 넘길 수 있는 강한 후처리이므로
        # 충분히 큰 글자에는 적용하지 않는다. 페이지 대표 체급 대비 작은 글자이거나
        # 앞선 겹침/하한 보정으로 작아진 텍스트만 보정 대상으로 본다.
        small_threshold = max(1, min(72, int(small_threshold or 72)))
        try:
            if hasattr(self, 'audit_boundary_event'):
                self.audit_boundary_event(
                    'TEXT_AUTO_ADJUST_AVAILABLE_SPACE_GROW_PASS_START',
                    page_idx=page_idx,
                    phase=str(phase or ''),
                    target_count=len(ordered),
                    page_size=f'{int(size[0])}x{int(size[1])}',
                    median_size=int(median_size),
                    small_threshold=int(small_threshold),
                    policy='grow_recovery_or_all_ko_first_pass_fit_text_using_position_search_actual_text_bounds_not_ocr_box',
                )
        except Exception:
            pass
        for item in ordered:
            try:
                old_size = max(1, int(round(float(item.get('font_size', 0) or 0))))
            except Exception:
                old_size = 1
            was_shrunk = bool(item.get('auto_layout_global_overlap_shrink'))
            was_floor = bool(item.get('auto_layout_median_floor_applied'))
            was_pairwise = bool(
                item.get('auto_layout_pairwise_overlap_shrink')
                or item.get('auto_layout_pairwise_inner_offset')
                or item.get('auto_layout_pairwise_overlap_unresolved')
            )
            # 그냥 작은 글자라는 이유만으로 전체를 다시 키우면, 이미 정상 배치된 OCR까지
            # inner offset이 튀어 OCR 영역이 이동한 것처럼 보인다. 다만 1차 ko_force_resize_retry_loop는
            # 위치 탐색 없이 크기/줄구성만으로 touch_ok를 판단하므로, OCR을 거의 채운 tight-fit 항목은
            # available-space grow에서 한 번 더 위치 탐색 기회를 줘야 한다.
            was_hard_fail = bool(item.get('auto_layout_hard_fail'))
            extreme_small = bool(old_size <= max(12, int(round(float(small_threshold) * 0.50))))
            try:
                fill_w_value = float(item.get('auto_layout_fill_w', 0) or 0.0)
            except Exception:
                fill_w_value = 0.0
            try:
                fill_h_value = float(item.get('auto_layout_fill_h', 0) or 0.0)
            except Exception:
                fill_h_value = 0.0
            mode_value = str(item.get('auto_layout_mode') or '')
            was_tight_fit = bool(
                mode_value == 'ko_force_resize_retry_loop'
                and fill_w_value >= 0.85
                and fill_h_value >= 0.85
            )
            # 6차 재진단 기준:
            # tight-fit 임계값에 기대면 로그/저장 타이밍 차이로 item_id=2 같은 1차 확정 항목이
            # available_space_grow 입구에서 다시 빠질 수 있다. 1차 ko_force_resize_retry_loop 자체가
            # 위치 이동을 고려하지 않는 패스이므로, 해당 모드의 가로쓰기 항목은 모두 위치 탐색 재성장
            # 검토 대상에 포함한다. 실제 채택 여부는 grow 내부의 OCR+10%/페이지 경계/실제 텍스트 겹침 검사가 결정한다.
            was_first_pass_fit = bool(mode_value == 'ko_force_resize_retry_loop')
            should_try_grow = bool(
                was_pairwise
                or was_shrunk
                or was_floor
                or (was_hard_fail and extreme_small)
                or was_tight_fit
                or was_first_pass_fit
            )
            if not should_try_grow:
                try:
                    if hasattr(self, 'audit_boundary_event'):
                        self.audit_boundary_event(
                            'TEXT_AUTO_ADJUST_AVAILABLE_SPACE_GROW_BLOCKED',
                            page_idx=page_idx,
                            item_id=item.get('id'),
                            old_size=int(old_size),
                            target_size=int(old_size),
                            reason=str(phase or ''),
                            blocked_info={
                                'reason': 'not_recovery_or_tight_fit_target',
                                'median_size': int(median_size),
                                'small_threshold': int(small_threshold),
                                'was_pairwise': bool(was_pairwise),
                                'was_hard_fail': bool(was_hard_fail),
                                'extreme_small': bool(extreme_small),
                                'was_tight_fit': bool(was_tight_fit),
                                'was_first_pass_fit': bool(was_first_pass_fit),
                                'auto_layout_mode': mode_value,
                                'fill_w': round(float(fill_w_value), 4),
                                'fill_h': round(float(fill_h_value), 4),
                            },
                            policy='skip_only_non_recovery_and_non_first_pass_fit_text_preserve_ocr_rect',
                        )
                except Exception:
                    pass
                continue
            try:
                if was_first_pass_fit and hasattr(self, 'audit_boundary_event'):
                    self.audit_boundary_event(
                        'TEXT_AUTO_ADJUST_AVAILABLE_SPACE_GROW_FIRST_PASS_TARGET',
                        page_idx=page_idx,
                        item_id=item.get('id'),
                        old_size=int(old_size),
                        fill_w=round(float(fill_w_value), 4),
                        fill_h=round(float(fill_h_value), 4),
                        was_tight_fit=bool(was_tight_fit),
                        auto_layout_mode=mode_value,
                        phase=str(phase or ''),
                        policy='all_ko_force_resize_retry_loop_items_get_position_search_regrow_chance',
                    )
            except Exception:
                pass

            # 작은 글자 보정용 재성장이므로 상승폭을 제한한다. 단, pairwise 겹침 보정으로 줄어든 텍스트는
            # 직전 크기까지 다시 올려보며, 위치 탐색으로 해결 가능한지 확인한다.
            target_size = min(260, max(old_size + 1, int(round(float(old_size) * 1.35))))
            try:
                target_size = min(260, max(target_size, old_size + 12))
            except Exception:
                pass
            if was_pairwise:
                try:
                    prev_size = int(round(float(item.get('auto_layout_pairwise_old_size', 0) or 0)))
                except Exception:
                    prev_size = 0
                try:
                    if prev_size > 0:
                        target_size = min(260, max(int(target_size), int(prev_size)))
                except Exception:
                    pass
            cid = self._auto_text_size_try_grow_item_to_available_space(
                page_idx,
                item,
                active,
                page_rect,
                int(target_size),
                reason=str(phase or 'after_boundary'),
            )
            if cid is not None and cid not in changed_ids:
                changed_ids.append(cid)
        try:
            if hasattr(self, 'audit_boundary_event'):
                self.audit_boundary_event(
                    'TEXT_AUTO_ADJUST_AVAILABLE_SPACE_GROW_PASS_DONE',
                    page_idx=page_idx,
                    phase=str(phase or ''),
                    changed_ids=[x for x in changed_ids if x is not None],
                    changed_count=len([x for x in changed_ids if x is not None]),
                )
        except Exception:
            pass
        return [x for x in changed_ids if x is not None]

    def _auto_text_size_median_floor_pass(self, page_idx, targets):
        """비정상적으로 작은 텍스트만 페이지 최다 빈도 글자 크기까지 끌어올린다.

        이 패스는 1차 겹침 정리 뒤, 최종 겹침 검사 전에 실행한다. OCR 박스가 너무 좁아서 번역문이
        콩알만 해진 경우만 잡기 위해, 기본 기준은 페이지 최다 빈도 글자 크기의 33% 이하로 둔다.
        """
        median_size = self._auto_text_size_page_median_font_size(targets)
        if not median_size or median_size <= 0:
            return []
        threshold_percent = self.auto_text_median_floor_threshold_percent()
        if threshold_percent <= 0:
            return []
        changed_ids = []
        threshold = max(1, int(round(float(median_size) * (float(threshold_percent) / 100.0))))
        try:
            if hasattr(self, 'audit_boundary_event'):
                self.audit_boundary_event(
                    'TEXT_AUTO_ADJUST_MEDIAN_FLOOR_PASS_START',
                    page_idx=page_idx,
                    median_size=int(median_size),
                    threshold=int(threshold),
                    threshold_percent=int(threshold_percent),
                    target_count=len(targets or []),
                    policy='final_pass_only_extremely_small_text',
                )
        except Exception:
            pass
        for item in targets or []:
            if not isinstance(item, dict) or not item.get('use_inpaint', True):
                continue
            if self.text_item_writing_direction(item) == 'vertical':
                continue
            try:
                _key, text = self._auto_layout_text_key_and_value(item)
            except Exception:
                text = item.get('translated_text') or item.get('text') or ''
            if not str(text or '').strip():
                continue
            try:
                old_size = int(round(float(item.get('font_size', 0) or 0)))
            except Exception:
                old_size = 0
            # 중위값의 지정 비율 이하만 비정상적으로 작다고 본다.
            if old_size <= 0 or old_size > threshold:
                continue
            # 곧장 median_size로 키우면 다음 겹침 패스가 다시 8px까지 줄이는 진동이 생긴다.
            # 실제 렌더 bounds 기준으로 겹치지 않는 최대 크기만 적용한다.
            before_size = int(old_size)
            cid = self._auto_text_size_try_grow_item_to_safe_size(
                page_idx,
                item,
                targets or [],
                int(median_size),
                reason='median_floor_safe_grow',
            )
            if cid is None:
                continue
            try:
                after_size = int(round(float(item.get('font_size', before_size) or before_size)))
            except Exception:
                after_size = before_size
            item['auto_layout_median_floor_applied'] = True
            item['auto_layout_median_floor_size'] = int(after_size)
            item['auto_layout_median_floor_target_size'] = int(median_size)
            item['auto_layout_median_floor_old_size'] = int(before_size)
            item['auto_layout_median_floor_threshold'] = int(threshold)
            item['auto_layout_median_floor_threshold_percent'] = int(threshold_percent)
            changed_ids.append(item.get('id'))
            try:
                if hasattr(self, 'audit_boundary_event'):
                    self.audit_boundary_event(
                        'TEXT_AUTO_ADJUST_MEDIAN_FLOOR_APPLIED',
                        page_idx=page_idx,
                        item_id=item.get('id'),
                        old_size=int(before_size),
                        new_size=int(after_size),
                        target_size=int(median_size),
                        threshold=int(threshold),
                        threshold_percent=int(threshold_percent),
                        policy='safe_grow_until_no_render_overlap_font_size_only_preserve_lines',
                    )
            except Exception:
                pass
        try:
            if hasattr(self, 'audit_boundary_event'):
                self.audit_boundary_event(
                    'TEXT_AUTO_ADJUST_MEDIAN_FLOOR_PASS_DONE',
                    page_idx=page_idx,
                    changed_ids=[x for x in changed_ids if x is not None],
                    changed_count=len([x for x in changed_ids if x is not None]),
                )
        except Exception:
            pass
        return [x for x in changed_ids if x is not None]

    def _auto_text_size_global_overlap_pass(self, page_idx, targets, max_passes=10, phase='post_fit'):
        """전체 텍스트 쌍을 대상으로 겹침을 반복 보정한다.

        기존 인접쌍 패스는 오른쪽부터 3-2, 2-1만 봐서 3-1, 위아래, 대각선 겹침을
        놓칠 수 있었다. 이 패스는 모든 visible bounds 쌍을 검사하고, 겹치는 쌍의
        한쪽을 조금씩 줄여 안정될 때까지 반복한다.
        """
        active = []
        for item in targets or []:
            if not isinstance(item, dict) or not item.get('use_inpaint', True):
                continue
            try:
                _key, text = self._auto_layout_text_key_and_value(item)
            except Exception:
                text = item.get('translated_text') or item.get('text') or ''
            if str(text or '').strip():
                active.append(item)
        if len(active) < 2:
            return []

        def _rect(item):
            try:
                return self._auto_adjust_visual_line_rects_for_item(item)
            except Exception:
                return []

        def _rect_area_from_item(item):
            try:
                r = item.get('rect') or [0, 0, 1, 1]
                return max(1.0, float(r[2])) * max(1.0, float(r[3]))
            except Exception:
                return 1.0

        def _choose_shrink_item(a, b):
            # 중위값 보정으로 방금 키운 항목이 있으면 그쪽을 먼저 되돌린다.
            af = bool(a.get('auto_layout_median_floor_applied'))
            bf = bool(b.get('auto_layout_median_floor_applied'))
            if af != bf:
                return a if af else b
            # 그 외에는 원래 OCR/텍스트 박스가 더 작은 쪽을 낮은 우선순위로 본다.
            aa = _rect_area_from_item(a)
            ba = _rect_area_from_item(b)
            if abs(aa - ba) > max(aa, ba) * 0.08:
                return a if aa < ba else b
            # 같으면 글자 크기가 더 큰 쪽을 줄여 체감 변화량을 줄인다.
            try:
                asz = int(a.get('font_size', 24) or 24)
                bsz = int(b.get('font_size', 24) or 24)
                if asz != bsz:
                    return a if asz > bsz else b
            except Exception:
                pass
            return b

        def _overlap_cost_with_all(item):
            rr = _rect(item)
            if rr is None:
                return 0.0, None
            total_cost = 0.0
            worst_info = None
            for other in active:
                if other is item:
                    continue
                ov, info = self._auto_adjust_pair_overlap_info(
                    rr,
                    _rect(other),
                    strict=(str(phase or '') in ('after_median_floor', 'final_render_margin', 'final_after_boundary', 'final_after_available_space_grow', 'final_after_available_space_grow_boundary')),
                )
                if ov:
                    try:
                        cost = float((info or {}).get('area_ratio') or 0.0) * 100000.0 + float((info or {}).get('overlap_area') or 0.0)
                    except Exception:
                        cost = 999999999.0
                    total_cost += cost
                    worst_info = info
            return total_cost, worst_info

        changed_ids = []
        try:
            _page_rep_size = int(self._auto_text_size_page_median_font_size(active) or 0)
        except Exception:
            _page_rep_size = 0
        readable_floor = max(18, int(round(float(_page_rep_size) * 0.25))) if _page_rep_size > 0 else 18
        try:
            if hasattr(self, 'audit_boundary_event'):
                self.audit_boundary_event('TEXT_AUTO_ADJUST_GLOBAL_OVERLAP_PASS_START', page_idx=page_idx, target_count=len(active), max_passes=int(max_passes), phase=str(phase or 'post_fit'), readable_floor=int(readable_floor), representative_size=int(_page_rep_size or 0))
        except Exception:
            pass
        for pass_no in range(1, int(max_passes or 10) + 1):
            pair_to_fix = None
            rects = {id(item): _rect(item) for item in active}
            for i in range(len(active)):
                for j in range(i + 1, len(active)):
                    a = active[i]
                    b = active[j]
                    ov, info = self._auto_adjust_pair_overlap_info(
                        rects.get(id(a)),
                        rects.get(id(b)),
                        strict=(str(phase or '') in ('after_median_floor', 'final_render_margin', 'final_after_boundary', 'final_after_available_space_grow', 'final_after_available_space_grow_boundary')),
                    )
                    if ov:
                        try:
                            if hasattr(self, 'audit_boundary_event') and str(phase or '') in ('after_median_floor', 'final_render_margin', 'final_after_boundary', 'final_after_available_space_grow', 'final_after_available_space_grow_boundary'):
                                self.audit_boundary_event(
                                    'TEXT_AUTO_ADJUST_FINAL_RENDER_OVERLAP_PAIR',
                                    page_idx=page_idx,
                                    phase=str(phase or 'post_fit'),
                                    pass_no=int(pass_no),
                                    item_a=a.get('id'),
                                    item_b=b.get('id'),
                                    overlap_info=info,
                                )
                        except Exception:
                            pass
                        pair_to_fix = (a, b, info)
                        break
                if pair_to_fix:
                    break
            if not pair_to_fix:
                break
            a, b, info = pair_to_fix
            target = _choose_shrink_item(a, b)
            old_size = max(1, int(target.get('font_size', 24) or 24))
            # 예전에는 겹침이 끝까지 안 풀리면 8px까지 내려가서 글자가 사라지는 문제가 있었다.
            # 이제는 대표 체급의 약 1/4 또는 18px 중 큰 값을 절대 가독 하한으로 둔다.
            # 선택된 쪽이 이미 하한이면 반대쪽을 줄여본다.
            if old_size <= int(readable_floor):
                other = b if target is a else a
                try:
                    other_size = max(1, int(other.get('font_size', 24) or 24))
                except Exception:
                    other_size = 1
                if other_size > int(readable_floor):
                    target = other
                    old_size = other_size
                else:
                    try:
                        if hasattr(self, 'audit_boundary_event'):
                            self.audit_boundary_event(
                                'TEXT_AUTO_ADJUST_GLOBAL_OVERLAP_SHRINK_BLOCKED_BY_READABLE_FLOOR',
                                page_idx=page_idx,
                                phase=str(phase or 'post_fit'),
                                pass_no=int(pass_no),
                                item_a=a.get('id'),
                                item_b=b.get('id'),
                                readable_floor=int(readable_floor),
                                pair_info=info,
                            )
                    except Exception:
                        pass
                    break
            min_size = max(int(readable_floor), int(round(old_size * 0.55)))
            if min_size >= old_size:
                min_size = max(int(readable_floor), old_size - 1)
            if min_size >= old_size:
                break
            best = None
            best_resolved = False
            original_size = old_size
            for test_size in range(old_size - 1, min_size - 1, -1):
                try:
                    target['font_size'] = int(test_size)
                    cost, worst = _overlap_cost_with_all(target)
                    if best is None or cost < best[0]:
                        best = (float(cost), int(test_size), worst)
                    if cost <= 0.0:
                        best_resolved = True
                        break
                except Exception:
                    continue
            if best is None:
                target['font_size'] = int(original_size)
                break
            _cost, best_size, worst = best
            if not best_resolved and float(_cost or 0.0) > 0.0:
                # 겹침이 완전히 풀리지 않는다면 글자를 계속 깎아 없애지 않는다.
                # 최소 가독 하한까지만 줄이고, 다음 패스에서 반대쪽/원인 텍스트도 줄일 기회를 준다.
                best_size = max(int(best_size), int(min_size))
            if int(best_size) == int(original_size):
                target['font_size'] = int(original_size)
                break
            target['font_size'] = int(best_size)
            target['auto_layout_global_overlap_shrink'] = True
            target['auto_layout_global_overlap_policy'] = 'all_pairs_iterative_shrink_final_recheck' if str(phase or '') == 'after_median_floor' else 'all_pairs_iterative_shrink'
            target['auto_layout_global_overlap_pass'] = int(pass_no)
            target['auto_layout_global_overlap_old_size'] = int(original_size)
            target['auto_layout_global_overlap_new_size'] = int(best_size)
            target['auto_layout_global_overlap_unresolved_cost', 'auto_layout_page_boundary_fixed', 'auto_layout_page_boundary_phase', 'auto_layout_page_boundary_old_size', 'auto_layout_page_boundary_new_size', 'auto_layout_page_boundary_old_inner_text_x_off', 'auto_layout_page_boundary_old_inner_text_y_off', 'auto_layout_page_boundary_new_inner_text_x_off', 'auto_layout_page_boundary_new_inner_text_y_off', 'auto_layout_page_boundary_overflow_before', 'auto_layout_page_boundary_overflow_after'] = float(round(float(_cost or 0.0), 4))
            changed_ids.append(target.get('id'))
            try:
                if hasattr(self, 'audit_boundary_event'):
                    self.audit_boundary_event(
                        'TEXT_AUTO_ADJUST_GLOBAL_OVERLAP_SHRINK',
                        page_idx=page_idx,
                        phase=str(phase or 'post_fit'),
                        pass_no=int(pass_no),
                        item_id=target.get('id'),
                        old_size=int(original_size),
                        new_size=int(best_size),
                        min_size=int(min_size),
                        pair_info=info,
                        remaining_cost=float(round(float(_cost or 0.0), 4)),
                        remaining_info=worst,
                    )
            except Exception:
                pass
        try:
            if hasattr(self, 'audit_boundary_event'):
                self.audit_boundary_event(
                    'TEXT_AUTO_ADJUST_GLOBAL_OVERLAP_PASS_DONE',
                    page_idx=page_idx,
                    phase=str(phase or 'post_fit'),
                    changed_ids=[x for x in changed_ids if x is not None],
                    changed_count=len([x for x in changed_ids if x is not None]),
                )
        except Exception:
            pass
        return list(dict.fromkeys([x for x in changed_ids if x is not None]))

    def _auto_text_size_pairwise_overlap_pass(self, page_idx, targets, phase='post_fit'):
        """오른쪽에서 왼쪽으로 인접 텍스트를 고정/보정하는 2차 겹침 보정 패스.

        1차 자동 조정은 모든 텍스트를 OCR 영역 기준으로 먼저 맞춘다.
        그 다음 이 패스에서 오른쪽 텍스트를 먼저 확정하고, 왼쪽/현재 텍스트가
        오른쪽 텍스트를 침범할 때만 현재 텍스트를 보정한다.

        핵심 규칙:
        - OCR rect는 절대 수정하지 않는다.
        - 이미 결정된 줄내림(translated_text의 \n)은 절대 다시 만들지 않는다.
        - 후처리에서는 font_size와 inner_text_x_off/inner_text_y_off만 사용한다.
        - 먼저 OCR rect 내부에서 텍스트만 이동해 보고, 부족할 때만 글자 크기를 줄인다.
        - 완전히 해결되지 않아도 원복하지 않고, 겹침 비용이 가장 낮은 후보를 적용한다.
        """
        if not targets:
            return []

        def _text_for_item(it):
            try:
                _k, text = self._auto_layout_text_key_and_value(it)
            except Exception:
                text = (it or {}).get('translated_text') or (it or {}).get('text') or ''
            return str(text or '')

        def _record_for_item(it):
            if not isinstance(it, dict) or not it.get('use_inpaint', True):
                return None
            if not _text_for_item(it).strip():
                return None
            try:
                rr = self._auto_adjust_visual_rect_for_item(it)
            except Exception:
                rr = None
            if rr is None:
                return None
            try:
                line_rects = self._auto_adjust_visual_line_rects_for_item(it)
            except Exception:
                line_rects = []
            if not line_rects:
                line_rects = [rr]
            try:
                cx = float(rr.x()) + float(rr.width()) / 2.0
                cy = float(rr.y()) + float(rr.height()) / 2.0
            except Exception:
                cx = cy = 0.0
            return {'item': it, 'rect': rr, 'line_rects': line_rects, 'cx': cx, 'cy': cy}

        def _refresh_record(rec):
            if not rec:
                return rec
            new_rec = _record_for_item(rec.get('item'))
            return new_rec or rec

        def _vertical_related(a_rect, b_rect):
            try:
                ay1 = float(a_rect.y())
                ay2 = ay1 + float(a_rect.height())
                by1 = float(b_rect.y())
                by2 = by1 + float(b_rect.height())
                overlap = min(ay2, by2) - max(ay1, by1)
                if overlap > 0.0:
                    return True, overlap
                acy = ay1 + float(a_rect.height()) / 2.0
                bcy = by1 + float(b_rect.height()) / 2.0
                center_gap = abs(acy - bcy)
                near_limit = max(float(a_rect.height()), float(b_rect.height())) * 0.45
                return bool(center_gap <= near_limit), -center_gap
            except Exception:
                return False, 0.0

        def _right_neighbor_candidates(current_rec, fixed_records):
            out = []
            if not current_rec:
                return out
            cur = current_rec.get('rect')
            ccx = float(current_rec.get('cx') or 0.0)
            try:
                cur_right = float(cur.x()) + float(cur.width())
            except Exception:
                cur_right = ccx
            for fixed_rec in fixed_records or []:
                fixed = fixed_rec.get('rect')
                fcx = float(fixed_rec.get('cx') or 0.0)
                if fcx <= ccx + 0.5:
                    continue
                related, v_score = _vertical_related(cur, fixed)
                if not related:
                    continue
                try:
                    fixed_left = float(fixed.x())
                    edge_gap = fixed_left - cur_right
                except Exception:
                    edge_gap = fcx - ccx
                # 이미 겹친 후보(edge_gap < 0)를 최우선, 아니면 가장 가까운 오른쪽 이웃.
                out.append((0 if edge_gap <= 0 else 1, abs(edge_gap), abs(fcx - ccx), -float(v_score or 0.0), fixed_rec))
            out.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
            return [x[-1] for x in out]

        def _overlap_cost(overlap_info):
            if not isinstance(overlap_info, dict):
                return 0.0
            try:
                return float(overlap_info.get('area_ratio') or 0.0) * 100000.0 + float(overlap_info.get('overlap_area') or 0.0)
            except Exception:
                return 999999999.0

        def _offset_value(item, key):
            try:
                return int(round(float(item.get(key, 0) or 0)))
            except Exception:
                return 0

        def _inner_offset_value(item, axis):
            key = 'inner_text_x_off' if str(axis).lower().startswith('x') else 'inner_text_y_off'
            try:
                return int(round(float(item.get(key, 0) or 0)))
            except Exception:
                return 0

        def _set_inner_offsets(item, x_off, y_off):
            # x_off/y_off는 사용자/아이템 전체 위치 이동용 값이다.
            # 자동 겹침 보정에서는 절대 건드리지 않고, 글자 path 전용 내부 오프셋만 기록한다.
            item['inner_text_x_off'] = int(round(float(x_off or 0)))
            item['inner_text_y_off'] = int(round(float(y_off or 0)))

        def _ocr_safe_rect(item, strict_gap=False):
            try:
                rect = list(item.get('rect') or [0, 0, 1, 1])
                while len(rect) < 4:
                    rect.append(1)
                x, y, w, h = [float(v) for v in rect[:4]]
                w = max(1.0, float(w))
                h = max(1.0, float(h))
                # OCR rect는 절대 이동/확장 저장하지 않는다.
                # 텍스트 visual bounds 판정만 OCR 대비 총 10%까지 허용한다.
                # 다른 OCR 영역은 겹침 검사 대상이 아니다.
                mx = w * 0.05
                my = h * 0.05
                pad = 1.0 if strict_gap else 0.0
                return QRectF(
                    x - mx + pad,
                    y - my + pad,
                    max(1.0, w + mx * 2.0 - pad * 2.0),
                    max(1.0, h + my * 2.0 - pad * 2.0),
                )
            except Exception:
                return None

        def _rect_inside(inner, rr, tolerance=0.75):
            try:
                if inner is None or rr is None:
                    return False
                return bool(
                    float(rr.left()) >= float(inner.left()) - float(tolerance)
                    and float(rr.top()) >= float(inner.top()) - float(tolerance)
                    and float(rr.right()) <= float(inner.right()) + float(tolerance)
                    and float(rr.bottom()) <= float(inner.bottom()) + float(tolerance)
                )
            except Exception:
                return False

        def _overlap_cost_with_fixed_records(item, fixed_records, *, strict=False):
            rr = None
            try:
                rr = self._auto_adjust_visual_rect_for_item(item)
            except Exception:
                rr = None
            if rr is None:
                return 999999999.0, None, None, True
            total = 0.0
            worst = None
            any_overlap = False
            try:
                current_lines = self._auto_adjust_visual_line_rects_for_item(item)
            except Exception:
                current_lines = [rr] if rr is not None else []
            for frec in fixed_records or []:
                fixed_rect = frec.get('line_rects') if isinstance(frec, dict) else None
                if not fixed_rect and isinstance(frec, dict):
                    fixed_rect = [frec.get('rect')]
                still, info = self._auto_adjust_pair_overlap_info(current_lines, fixed_rect, strict=bool(strict))
                if still:
                    any_overlap = True
                    cost = _overlap_cost(info)
                    total += float(cost or 0.0)
                    worst = info
            return float(total), worst, rr, bool(any_overlap)

        def _dedup_numbers(values):
            out = []
            seen = set()
            for v in values:
                try:
                    iv = int(round(float(v)))
                except Exception:
                    continue
                if iv not in seen:
                    seen.add(iv)
                    out.append(iv)
            return out

        def _offset_candidates_for_current(item, fixed_rect, *, strict=False, base_x=None, base_y=None):
            """현재 줄내림/글자 크기를 유지한 채 OCR rect 내부 이동 후보를 만든다.

            반환 후보는 (inner_text_x_off, inner_text_y_off, rect, inside) 튜플이다.
            inside=True 후보만 채택한다. OCR rect 밖으로 나가는 내부 이동 후보는 절대 fallback으로 쓰지 않는다.
            """
            if not isinstance(item, dict):
                return []
            bx = _inner_offset_value(item, 'x') if base_x is None else int(round(float(base_x or 0)))
            by = _inner_offset_value(item, 'y') if base_y is None else int(round(float(base_y or 0)))
            _set_inner_offsets(item, bx, by)
            try:
                base_rect = self._auto_adjust_visual_rect_for_item(item)
            except Exception:
                base_rect = None
            if base_rect is None:
                return []
            safe = _ocr_safe_rect(item, strict_gap=bool(strict))
            try:
                low_dx = float(safe.left()) - float(base_rect.left())
                high_dx = float(safe.right()) - float(base_rect.right())
                low_dy = float(safe.top()) - float(base_rect.top())
                high_dy = float(safe.bottom()) - float(base_rect.bottom())
            except Exception:
                low_dx = high_dx = low_dy = high_dy = 0.0

            try:
                cur_cx = float(base_rect.center().x())
                cur_cy = float(base_rect.center().y())
                fix_cx = float(fixed_rect.center().x()) if fixed_rect is not None else cur_cx
                fix_cy = float(fixed_rect.center().y()) if fixed_rect is not None else cur_cy
            except Exception:
                cur_cx = cur_cy = fix_cx = fix_cy = 0.0
            away_x = 1.0 if cur_cx >= fix_cx else -1.0
            away_y = 1.0 if cur_cy >= fix_cy else -1.0

            # 중심/끝/절반/방향성 이동을 모두 본다. 많은 후보가 아니므로 충분히 가볍다.
            dx_values = [0, low_dx, high_dx, low_dx / 2.0, high_dx / 2.0]
            dy_values = [0, low_dy, high_dy, low_dy / 2.0, high_dy / 2.0]
            for step in (6, 10, 16, 24, 32, 48, 64):
                dx_values.append(away_x * step)
                dy_values.append(away_y * step)
                dx_values.append(-away_x * step)
                dy_values.append(-away_y * step)
            # 위아래로 붙은 말풍선은 y 이동이 가장 중요하므로 y 단독 후보를 더 촘촘히 둔다.
            try:
                if fixed_rect is not None:
                    if float(base_rect.center().y()) >= float(fixed_rect.center().y()):
                        dy_values.extend([high_dy, high_dy * 0.75, high_dy * 0.5])
                    else:
                        dy_values.extend([low_dy, low_dy * 0.75, low_dy * 0.5])
            except Exception:
                pass

            candidates = []
            for dx in _dedup_numbers(dx_values):
                for dy in _dedup_numbers(dy_values):
                    nx = bx + dx
                    ny = by + dy
                    _set_inner_offsets(item, nx, ny)
                    try:
                        rr = self._auto_adjust_visual_rect_for_item(item)
                    except Exception:
                        rr = None
                    if rr is None:
                        continue
                    inside = _rect_inside(safe, rr)
                    candidates.append((int(nx), int(ny), rr, bool(inside)))
            # 원위치 후보는 반드시 포함한다.
            _set_inner_offsets(item, bx, by)
            try:
                rr = self._auto_adjust_visual_rect_for_item(item)
                candidates.append((int(bx), int(by), rr, _rect_inside(safe, rr)))
            except Exception:
                pass
            # 후보 중복 제거
            out = []
            seen = set()
            for nx, ny, rr, inside in candidates:
                key = (int(nx), int(ny))
                if key in seen:
                    continue
                seen.add(key)
                out.append((int(nx), int(ny), rr, bool(inside)))
            return out

        def _best_offset_for_current(item, fixed_records, fixed_rect, *, strict=False, base_x=None, base_y=None):
            """font_size/줄내림은 유지하고 inner_text_x_off/inner_text_y_off 후보 중 최저 겹침 비용을 고른다."""
            original_x = _inner_offset_value(item, 'x') if base_x is None else int(round(float(base_x or 0)))
            original_y = _inner_offset_value(item, 'y') if base_y is None else int(round(float(base_y or 0)))
            _set_inner_offsets(item, original_x, original_y)
            baseline_cost, baseline_info, baseline_rect, baseline_overlap = _overlap_cost_with_fixed_records(item, fixed_records, strict=bool(strict))
            candidates = _offset_candidates_for_current(item, fixed_rect, strict=bool(strict), base_x=original_x, base_y=original_y)
            if not candidates:
                _set_inner_offsets(item, original_x, original_y)
                return {
                    'resolved': bool((not bool(baseline_overlap)) and _rect_inside(_ocr_safe_rect(item, strict_gap=bool(strict)), baseline_rect)),
                    'improved': False,
                    'cost': float(baseline_cost),
                    'inner_x_off': int(original_x),
                    'inner_y_off': int(original_y),
                    'rect': baseline_rect,
                    'info': baseline_info,
                    'inside': _rect_inside(_ocr_safe_rect(item, strict_gap=bool(strict)), baseline_rect),
                    'baseline_cost': float(baseline_cost),
                    'candidate_count': 0,
                }

            best = None
            # OCR rect 밖으로 빠지는 후보는 절대 채택하지 않는다.
            # 내부 후보가 없다면 글자 크기 축소 단계에서 다시 시도한다.
            inside_candidates = [c for c in candidates if c[3]]
            eval_candidates = inside_candidates
            if not eval_candidates:
                _set_inner_offsets(item, original_x, original_y)
                return {
                    'resolved': bool((not bool(baseline_overlap)) and _rect_inside(_ocr_safe_rect(item, strict_gap=bool(strict)), baseline_rect)),
                    'improved': False,
                    'cost': float(baseline_cost),
                    'inner_x_off': int(original_x),
                    'inner_y_off': int(original_y),
                    'rect': baseline_rect,
                    'info': baseline_info,
                    'inside': _rect_inside(_ocr_safe_rect(item, strict_gap=bool(strict)), baseline_rect),
                    'baseline_cost': float(baseline_cost),
                    'baseline_info': baseline_info,
                    'baseline_rect': baseline_rect,
                    'candidate_count': 0,
                }
            for nx, ny, _rr, inside in eval_candidates:
                _set_inner_offsets(item, nx, ny)
                cost, info, rr, overlap = _overlap_cost_with_fixed_records(item, fixed_records, strict=bool(strict))
                moved = abs(int(nx) - int(original_x)) + abs(int(ny) - int(original_y))
                # 비용이 같다면 덜 움직이는 후보를 선택한다.
                key = (float(cost), int(moved), 0 if inside else 1)
                if best is None or key < best[0]:
                    best = (key, int(nx), int(ny), rr, info, bool(overlap), bool(inside), float(cost))
                if not overlap and inside:
                    # 내부에서 완전 해결된 가장 작은 이동 후보면 충분하다.
                    break
            if best is None:
                _set_inner_offsets(item, original_x, original_y)
                return None
            _key, nx, ny, rr, info, overlap, inside, cost = best
            _set_inner_offsets(item, original_x, original_y)
            return {
                'resolved': bool((not bool(overlap)) and bool(inside)),
                'improved': bool(bool(inside) and (float(cost) < float(baseline_cost) - 0.001 or nx != original_x or ny != original_y)),
                'cost': float(cost),
                'inner_x_off': int(nx),
                'inner_y_off': int(ny),
                'rect': rr,
                'info': info,
                'inside': bool(inside),
                'baseline_cost': float(baseline_cost),
                'baseline_info': baseline_info,
                'baseline_rect': baseline_rect,
                'candidate_count': len(eval_candidates),
            }

        records = []
        for item in targets:
            rec = _record_for_item(item)
            if rec is not None:
                records.append(rec)
        if len(records) < 2:
            return []

        # 오른쪽부터 확정한다. 같은 x권에서는 위쪽부터 안정적으로 본다.
        ordered = sorted(records, key=lambda r: (-float(r.get('cx') or 0.0), float(r.get('cy') or 0.0)))
        try:
            if hasattr(self, 'audit_boundary_event'):
                self.audit_boundary_event(
                    'TEXT_AUTO_ADJUST_PAIRWISE_PASS_START',
                    page_idx=page_idx,
                    phase=str(phase or 'post_fit'),
                    policy='right_to_left_actual_text_bounds_only_ignore_other_ocr_rects_preserve_rect_and_linebreaks',
                    order=[{'id': r['item'].get('id'), 'font_size': r['item'].get('font_size'), 'rect': r['item'].get('rect'), 'x_off': r['item'].get('x_off', 0), 'y_off': r['item'].get('y_off', 0), 'inner_text_x_off': r['item'].get('inner_text_x_off', 0), 'inner_text_y_off': r['item'].get('inner_text_y_off', 0), 'cx': round(float(r.get('cx') or 0.0), 2), 'cy': round(float(r.get('cy') or 0.0), 2)} for r in ordered],
                )
        except Exception:
            pass

        changed_ids = []
        fixed_records = []
        # post_fit 단계에서부터 1px strict를 강제하면 렌더 bounds의 과대 측정 때문에
        # 실제 글자는 멀쩡한데도 너무 일찍 축소/이동이 시작된다.
        # 최종 확인 단계에서만 1px 여백을 본다.
        strict = bool(str(phase or '') in ('final_render_margin', 'final_after_boundary'))
        for idx_order, rec in enumerate(ordered):
            current = rec.get('item')
            current_rec = _refresh_record(rec)
            candidates = _right_neighbor_candidates(current_rec, fixed_records)
            if not candidates:
                fixed_records.append(current_rec)
                continue

            # 한 current가 여러 오른쪽 이웃과 닿을 수 있으므로, 최대 몇 번 반복해서 현재 텍스트만 보정한다.
            for local_pass in range(1, 6):
                current_rec = _refresh_record(current_rec)
                candidates = _right_neighbor_candidates(current_rec, fixed_records)
                if not candidates:
                    break
                fixed_rec = candidates[0]
                fixed_item = fixed_rec.get('item')
                current_rect = current_rec.get('rect')
                fixed_rect = fixed_rec.get('rect')
                current_line_rects = current_rec.get('line_rects') or ([current_rect] if current_rect is not None else [])
                fixed_line_rects = fixed_rec.get('line_rects') or ([fixed_rect] if fixed_rect is not None else [])
                should_fix, info = self._auto_adjust_pair_overlap_info(current_line_rects, fixed_line_rects, strict=strict)
                try:
                    if hasattr(self, 'audit_boundary_event'):
                        self.audit_boundary_event(
                            'TEXT_AUTO_ADJUST_PAIRWISE_CHECK',
                            page_idx=page_idx,
                            phase=str(phase or 'post_fit'),
                            pair_index=int(idx_order),
                            local_pass=int(local_pass),
                            fixed_item_id=fixed_item.get('id') if isinstance(fixed_item, dict) else None,
                            current_item_id=current.get('id') if isinstance(current, dict) else None,
                            fixed_rect=[round(fixed_rect.x(), 2), round(fixed_rect.y(), 2), round(fixed_rect.width(), 2), round(fixed_rect.height(), 2)] if fixed_rect is not None else None,
                            current_rect=[round(current_rect.x(), 2), round(current_rect.y(), 2), round(current_rect.width(), 2), round(current_rect.height(), 2)] if current_rect is not None else None,
                            overlap=bool(should_fix),
                            overlap_info=info,
                        )
                except Exception:
                    pass
                if not should_fix:
                    break

                old_size = max(1, int(current.get('font_size', 24) or 24))
                old_x = _inner_offset_value(current, 'x')
                old_y = _inner_offset_value(current, 'y')

                # 1) 줄내림/글자 크기는 유지하고, OCR rect 안에서 텍스트만 먼저 움직인다.
                offset_best = _best_offset_for_current(current, fixed_records, fixed_rect, strict=strict, base_x=old_x, base_y=old_y)
                if offset_best and bool(offset_best.get('inside')) and (offset_best.get('resolved') or float(offset_best.get('cost') or 0.0) < _overlap_cost(info) - 0.001):
                    _set_inner_offsets(current, offset_best.get('inner_x_off'), offset_best.get('inner_y_off'))
                    current['auto_layout_pairwise_overlap_shrink'] = False
                    current['auto_layout_pairwise_inner_offset'] = True
                    current['auto_layout_pairwise_overlap_policy'] = 'preserve_ocr_rect_and_linebreaks_inner_offset_first'
                    current['auto_layout_pairwise_phase'] = str(phase or 'post_fit')
                    current['auto_layout_pairwise_fixed_neighbor_id'] = fixed_item.get('id') if isinstance(fixed_item, dict) else None
                    current['auto_layout_pairwise_overlap_unresolved'] = not bool(offset_best.get('resolved'))
                    current['auto_layout_pairwise_old_inner_text_x_off'] = int(old_x)
                    current['auto_layout_pairwise_old_inner_text_y_off'] = int(old_y)
                    current['auto_layout_pairwise_new_inner_text_x_off'] = int(offset_best.get('inner_x_off') or 0)
                    current['auto_layout_pairwise_new_inner_text_y_off'] = int(offset_best.get('inner_y_off') or 0)
                    current['auto_layout_pairwise_overlap_unresolved_cost'] = float(round(float(offset_best.get('cost') or 0.0), 4))
                    if current.get('id') not in changed_ids:
                        changed_ids.append(current.get('id'))
                    try:
                        if hasattr(self, 'audit_boundary_event'):
                            self.audit_boundary_event(
                                'TEXT_AUTO_ADJUST_PAIRWISE_INNER_OFFSET',
                                page_idx=page_idx,
                                phase=str(phase or 'post_fit'),
                                current_item_id=current.get('id'),
                                fixed_item_id=fixed_item.get('id') if isinstance(fixed_item, dict) else None,
                                font_size=int(old_size),
                                old_inner_text_x_off=int(old_x),
                                old_inner_text_y_off=int(old_y),
                                new_inner_text_x_off=int(offset_best.get('inner_x_off') or 0),
                                new_inner_text_y_off=int(offset_best.get('inner_y_off') or 0),
                                resolved=bool(offset_best.get('resolved')),
                                inside_ocr_rect=bool(offset_best.get('inside')),
                                candidate_count=int(offset_best.get('candidate_count') or 0),
                                before_cost=float(round(float(offset_best.get('baseline_cost') or 0.0), 4)),
                                after_cost=float(round(float(offset_best.get('cost') or 0.0), 4)),
                                remaining_overlap_info=offset_best.get('info'),
                                policy='ocr_rect_locked_linebreak_locked_move_text_inside_rect_first',
                            )
                    except Exception:
                        pass
                    # 완전 해결이면 다음 local pass에서 더 이상 겹침이 없어서 빠진다.
                    if bool(offset_best.get('resolved')):
                        continue

                # 2) 이동만으로 해결이 안 되면, 줄내림/rect는 그대로 두고 글자 크기와 내부 offset을 함께 탐색한다.
                original_size = int(current.get('font_size', old_size) or old_size)
                original_x = _inner_offset_value(current, 'x')
                original_y = _inner_offset_value(current, 'y')
                # 너무 작아지는 것을 막되, 기존 70%보다 조금 더 유연하게 허용한다.
                min_size = max(18, int(round(old_size * 0.60)))
                if min_size >= old_size:
                    min_size = max(1, old_size - 1)

                best_resolved = None
                best_any = None
                # 원상태도 후보에 넣어 비용 기준을 명확히 한다.
                current['font_size'] = int(original_size)
                _set_inner_offsets(current, original_x, original_y)
                base_cost, base_info, base_rect, base_overlap = _overlap_cost_with_fixed_records(current, fixed_records, strict=strict)
                base_inside = _rect_inside(_ocr_safe_rect(current, strict_gap=bool(strict)), base_rect)
                best_any = (float(base_cost), int(original_size), int(original_x), int(original_y), base_rect, base_info, bool(base_overlap), True, int(0)) if base_inside else None

                for test_size in range(old_size - 1, min_size - 1, -1):
                    try:
                        current['font_size'] = int(test_size)
                        _set_inner_offsets(current, original_x, original_y)
                        moved_best = _best_offset_for_current(current, fixed_records, fixed_rect, strict=strict, base_x=original_x, base_y=original_y)
                        if not moved_best:
                            continue
                        if not bool(moved_best.get('inside')):
                            continue
                        cost = float(moved_best.get('cost') or 0.0)
                        nx = int(moved_best.get('inner_x_off') or 0)
                        ny = int(moved_best.get('inner_y_off') or 0)
                        rr = moved_best.get('rect')
                        inf = moved_best.get('info')
                        resolved = bool(moved_best.get('resolved'))
                        moved = abs(nx - original_x) + abs(ny - original_y)
                        cand = (cost, int(test_size), nx, ny, rr, inf, not resolved, bool(moved_best.get('inside')), int(moved))
                        if best_any is None or (cost, 0 if resolved else 1, int(moved), -int(test_size)) < (best_any[0], 0 if not best_any[6] else 1, best_any[8], -best_any[1]):
                            best_any = cand
                        if resolved:
                            best_resolved = cand
                            break
                    except Exception:
                        continue

                chosen = best_resolved or best_any
                if chosen is None:
                    current['font_size'] = int(original_size)
                    _set_inner_offsets(current, original_x, original_y)
                    break
                chosen_cost, best_size, best_x, best_y, best_rect, remaining_info, unresolved_flag, inside_flag, moved_amount = chosen
                current['font_size'] = int(best_size)
                _set_inner_offsets(current, best_x, best_y)
                changed = bool(int(best_size) != int(original_size) or int(best_x) != int(original_x) or int(best_y) != int(original_y))
                current['auto_layout_pairwise_overlap_shrink'] = bool(int(best_size) != int(original_size))
                current['auto_layout_pairwise_inner_offset'] = bool(int(best_x) != int(original_x) or int(best_y) != int(original_y))
                current['auto_layout_pairwise_overlap_policy'] = 'actual_text_bounds_only_ignore_other_ocr_rects_preserve_ocr_rect_and_linebreaks_best_font_size_and_inner_offset'
                current['auto_layout_pairwise_phase'] = str(phase or 'post_fit')
                current['auto_layout_pairwise_fixed_neighbor_id'] = fixed_item.get('id') if isinstance(fixed_item, dict) else None
                current['auto_layout_pairwise_overlap_unresolved'] = bool(unresolved_flag)
                current['auto_layout_pairwise_old_size'] = int(original_size)
                current['auto_layout_pairwise_new_size'] = int(best_size)
                current['auto_layout_pairwise_old_inner_text_x_off'] = int(original_x)
                current['auto_layout_pairwise_old_inner_text_y_off'] = int(original_y)
                current['auto_layout_pairwise_new_inner_text_x_off'] = int(best_x)
                current['auto_layout_pairwise_new_inner_text_y_off'] = int(best_y)
                current['auto_layout_pairwise_overlap_unresolved_cost'] = float(round(float(chosen_cost or 0.0), 4))
                if changed and current.get('id') not in changed_ids:
                    changed_ids.append(current.get('id'))
                try:
                    if hasattr(self, 'audit_boundary_event'):
                        try:
                            best_line_rects = self._auto_adjust_visual_line_rects_for_item(current)
                        except Exception:
                            best_line_rects = [best_rect] if best_rect is not None else []
                        fixed_line_rects_for_audit = fixed_rec.get('line_rects') or ([fixed_rect] if fixed_rect is not None else [])
                        resolved, resolved_info = self._auto_adjust_pair_overlap_info(best_line_rects, fixed_line_rects_for_audit, strict=strict)
                        self.audit_boundary_event(
                            'TEXT_AUTO_ADJUST_PAIRWISE_FONT_OFFSET',
                            page_idx=page_idx,
                            phase=str(phase or 'post_fit'),
                            current_item_id=current.get('id'),
                            fixed_item_id=fixed_item.get('id') if isinstance(fixed_item, dict) else None,
                            old_size=int(original_size),
                            new_size=int(best_size),
                            min_size=int(min_size),
                            old_inner_text_x_off=int(original_x),
                            old_inner_text_y_off=int(original_y),
                            new_inner_text_x_off=int(best_x),
                            new_inner_text_y_off=int(best_y),
                            resolved=not bool(resolved),
                            unresolved=bool(unresolved_flag),
                            inside_ocr_rect=bool(inside_flag),
                            before_cost=float(round(float(base_cost or 0.0), 4)),
                            after_cost=float(round(float(chosen_cost or 0.0), 4)),
                            remaining_overlap_info=(resolved_info if resolved_info is not None else remaining_info),
                            policy='ocr_rect_locked_linebreak_locked_font_size_and_inner_offset_best_effort_no_rewrap',
                        )
                except Exception:
                    pass
                if not changed:
                    break

            fixed_records.append(_refresh_record(current_rec))

        try:
            if hasattr(self, 'audit_boundary_event'):
                self.audit_boundary_event(
                    'TEXT_AUTO_ADJUST_PAIRWISE_PASS_DONE',
                    page_idx=page_idx,
                    phase=str(phase or 'post_fit'),
                    changed_ids=[x for x in changed_ids if x is not None],
                    changed_count=len([x for x in changed_ids if x is not None]),
                )
        except Exception:
            pass
        return [x for x in changed_ids if x is not None]


    def _auto_text_size_page_boundary_overflow_info(self, visual_rect, page_rect):
        """Return overflow info for a rendered text rect against the image canvas."""
        try:
            try:
                if hasattr(self, 'is_text_image_overflow_check_enabled') and not self.is_text_image_overflow_check_enabled():
                    return {'overflow': False, 'cost': 0.0, 'disabled': True, 'policy': 'text_image_overflow_check_disabled'}
            except Exception:
                pass
            if visual_rect is None or page_rect is None or visual_rect.isNull() or page_rect.isNull():
                return {'overflow': False, 'cost': 0.0}
            left = max(0.0, float(page_rect.left()) - float(visual_rect.left()))
            top = max(0.0, float(page_rect.top()) - float(visual_rect.top()))
            right = max(0.0, float(visual_rect.right()) - float(page_rect.right()))
            bottom = max(0.0, float(visual_rect.bottom()) - float(page_rect.bottom()))
            cost = float(left + top + right + bottom)
            return {
                'overflow': bool(cost > 0.01),
                'cost': round(cost, 4),
                'left': round(left, 2),
                'top': round(top, 2),
                'right': round(right, 2),
                'bottom': round(bottom, 2),
                'visual_rect': [round(float(visual_rect.x()), 2), round(float(visual_rect.y()), 2), round(float(visual_rect.width()), 2), round(float(visual_rect.height()), 2)],
                'page_rect': [round(float(page_rect.x()), 2), round(float(page_rect.y()), 2), round(float(page_rect.width()), 2), round(float(page_rect.height()), 2)],
            }
        except Exception:
            return {'overflow': False, 'cost': 0.0}

    def _auto_text_size_page_boundary_clamp_delta(self, visual_rect, page_rect):
        """Return dx/dy needed to move a visual rect inside the page when possible."""
        dx = dy = 0.0
        try:
            try:
                if hasattr(self, 'is_text_image_overflow_check_enabled') and not self.is_text_image_overflow_check_enabled():
                    return 0.0, 0.0
            except Exception:
                pass
            if visual_rect.left() < page_rect.left():
                dx += float(page_rect.left() - visual_rect.left())
            if visual_rect.right() > page_rect.right():
                # If both sides overflow because the rect is wider than the page,
                # this will leave a remaining overflow and the shrink loop will handle it.
                dx += float(page_rect.right() - visual_rect.right())
            if visual_rect.top() < page_rect.top():
                dy += float(page_rect.top() - visual_rect.top())
            if visual_rect.bottom() > page_rect.bottom():
                dy += float(page_rect.bottom() - visual_rect.bottom())
        except Exception:
            dx = dy = 0.0
        return dx, dy

    def _auto_text_size_try_fit_item_to_page_boundary(self, item, page_rect, page_idx=None, phase='final_boundary'):
        """Keep actual rendered text bounds inside the image canvas.

        This is the final guard for edge OCR boxes.  OCR rect/x_off/y_off and
        existing line breaks stay fixed.  The pass first tries an inner text
        offset toward the inside of the image; if the rendered text is still
        outside the canvas, it shrinks font_size while preserving lines.
        """
        try:
            if hasattr(self, 'is_text_image_overflow_check_enabled') and not self.is_text_image_overflow_check_enabled():
                return False
        except Exception:
            pass
        if not isinstance(item, dict):
            return False
        try:
            _key, text = self._auto_layout_text_key_and_value(item)
        except Exception:
            text = item.get('translated_text') or item.get('text') or ''
        if not str(text or '').strip():
            return False
        try:
            old_size = max(1, int(round(float(item.get('font_size', 24) or 24))))
        except Exception:
            old_size = 24
        try:
            old_ix = int(round(float(item.get('inner_text_x_off', 0) or 0)))
        except Exception:
            old_ix = 0
        try:
            old_iy = int(round(float(item.get('inner_text_y_off', 0) or 0)))
        except Exception:
            old_iy = 0

        original_rect = self._auto_adjust_visual_rect_for_item(item)
        original_info = self._auto_text_size_page_boundary_overflow_info(original_rect, page_rect)
        if not bool(original_info.get('overflow')):
            return False

        try:
            if hasattr(self, 'audit_boundary_event'):
                self.audit_boundary_event(
                    'TEXT_AUTO_ADJUST_PAGE_BOUNDARY_VIOLATION',
                    page_idx=page_idx,
                    item_id=item.get('id'),
                    phase=str(phase or 'final_boundary'),
                    overflow_info=original_info,
                    font_size_before=int(old_size),
                    inner_offset_before=[int(old_ix), int(old_iy)],
                    policy='visual_text_bounds_must_stay_inside_image_canvas',
                )
        except Exception:
            pass

        def _eval_candidate(size, ix, iy):
            try:
                item['font_size'] = int(size)
                item['inner_text_x_off'] = int(round(ix))
                item['inner_text_y_off'] = int(round(iy))
                rr = self._auto_adjust_visual_rect_for_item(item)
                info = self._auto_text_size_page_boundary_overflow_info(rr, page_rect)
                cost = float(info.get('cost') or 0.0)
                move = abs(float(ix) - float(old_ix)) + abs(float(iy) - float(old_iy))
                shrink = max(0, int(old_size) - int(size))
                return {'size': int(size), 'ix': int(round(ix)), 'iy': int(round(iy)), 'rect': rr, 'info': info, 'cost': cost, 'score': (cost, shrink, move)}
            except Exception:
                return None

        best = None
        # Try simple inner offset first at the current font size.
        try:
            dx, dy = self._auto_text_size_page_boundary_clamp_delta(original_rect, page_rect)
            cand = _eval_candidate(old_size, old_ix + dx, old_iy + dy)
            if cand is not None:
                best = cand
        except Exception:
            pass

        # If needed, shrink while preserving current line breaks.  At each size,
        # also clamp the inner offset toward the page interior.
        try:
            representative = int(self._auto_text_size_page_median_font_size([item]) or 0)
        except Exception:
            representative = 0
        min_size = max(10, int(round(float(old_size) * 0.45)))
        if representative > 0:
            min_size = max(min_size, int(round(float(representative) * 0.25)))
        if min_size >= old_size:
            min_size = max(1, old_size - 1)
        for size in range(old_size - 1, min_size - 1, -1):
            try:
                item['font_size'] = int(size)
                item['inner_text_x_off'] = int(old_ix)
                item['inner_text_y_off'] = int(old_iy)
                rr = self._auto_adjust_visual_rect_for_item(item)
                if rr is None:
                    continue
                dx, dy = self._auto_text_size_page_boundary_clamp_delta(rr, page_rect)
                cand = _eval_candidate(size, old_ix + dx, old_iy + dy)
                if cand is None:
                    continue
                if best is None or tuple(cand.get('score')) < tuple(best.get('score')):
                    best = cand
                if float(cand.get('cost') or 0.0) <= 0.01:
                    break
            except Exception:
                continue

        # Restore before deciding, then apply only if there is real improvement.
        try:
            item['font_size'] = int(old_size)
            item['inner_text_x_off'] = int(old_ix)
            item['inner_text_y_off'] = int(old_iy)
        except Exception:
            pass

        if best is None:
            return False
        old_cost = float(original_info.get('cost') or 0.0)
        new_cost = float(best.get('cost') or 0.0)
        if new_cost >= old_cost - 0.01:
            try:
                if hasattr(self, 'audit_boundary_event'):
                    self.audit_boundary_event(
                        'TEXT_AUTO_ADJUST_PAGE_BOUNDARY_UNRESOLVED',
                        page_idx=page_idx,
                        item_id=item.get('id'),
                        phase=str(phase or 'final_boundary'),
                        min_size=int(min_size),
                        overflow_before=original_info,
                        overflow_after=(best.get('info') or {}),
                        policy='no_candidate_improved_page_boundary_overflow',
                    )
            except Exception:
                pass
            return False

        try:
            item['font_size'] = int(best.get('size'))
            item['inner_text_x_off'] = int(best.get('ix'))
            item['inner_text_y_off'] = int(best.get('iy'))
            item['auto_layout_page_boundary_fixed'] = True
            item['auto_layout_page_boundary_phase'] = str(phase or 'final_boundary')
            item['auto_layout_page_boundary_old_size'] = int(old_size)
            item['auto_layout_page_boundary_new_size'] = int(best.get('size'))
            item['auto_layout_page_boundary_old_inner_text_x_off'] = int(old_ix)
            item['auto_layout_page_boundary_old_inner_text_y_off'] = int(old_iy)
            item['auto_layout_page_boundary_new_inner_text_x_off'] = int(best.get('ix'))
            item['auto_layout_page_boundary_new_inner_text_y_off'] = int(best.get('iy'))
            item['auto_layout_page_boundary_overflow_before'] = original_info
            item['auto_layout_page_boundary_overflow_after'] = best.get('info') or {}
        except Exception:
            pass
        try:
            if hasattr(self, 'audit_boundary_event'):
                method = 'inner_offset'
                if int(best.get('size')) < int(old_size):
                    method = 'shrink_and_inner_offset' if (int(best.get('ix')) != old_ix or int(best.get('iy')) != old_iy) else 'shrink'
                self.audit_boundary_event(
                    'TEXT_AUTO_ADJUST_PAGE_BOUNDARY_FIXED',
                    page_idx=page_idx,
                    item_id=item.get('id'),
                    phase=str(phase or 'final_boundary'),
                    method=method,
                    font_size_before=int(old_size),
                    font_size_after=int(best.get('size')),
                    inner_offset_before=[int(old_ix), int(old_iy)],
                    inner_offset_after=[int(best.get('ix')), int(best.get('iy'))],
                    overflow_before=original_info,
                    overflow_after=(best.get('info') or {}),
                    policy='preserve_ocr_rect_xoff_yoff_and_linebreaks_fit_visual_text_inside_canvas',
                )
        except Exception:
            pass
        if new_cost > 0.01:
            try:
                if hasattr(self, 'audit_boundary_event'):
                    self.audit_boundary_event(
                        'TEXT_AUTO_ADJUST_PAGE_BOUNDARY_UNRESOLVED',
                        page_idx=page_idx,
                        item_id=item.get('id'),
                        phase=str(phase or 'final_boundary'),
                        min_size=int(min_size),
                        overflow_before=original_info,
                        overflow_after=(best.get('info') or {}),
                        policy='best_candidate_applied_but_remaining_overflow_exists',
                    )
            except Exception:
                pass
        return True

    def _auto_text_size_page_boundary_pass(self, page_idx, targets, phase='after_final_overlap'):
        """Final pass: rendered text must not exceed the image canvas."""
        try:
            if hasattr(self, 'is_text_image_overflow_check_enabled') and not self.is_text_image_overflow_check_enabled():
                try:
                    if hasattr(self, 'audit_boundary_event'):
                        self.audit_boundary_event(
                            'TEXT_AUTO_ADJUST_PAGE_BOUNDARY_PASS_SKIPPED',
                            page_idx=page_idx,
                            phase=str(phase or ''),
                            policy='text_image_overflow_check_disabled_by_option',
                        )
                except Exception:
                    pass
                return []
        except Exception:
            pass
        try:
            size = self._auto_layout_page_image_size_for_auto(page_idx=page_idx)
        except Exception:
            size = None
        if not size:
            return []
        try:
            page_rect = QRectF(0.0, 0.0, float(size[0]), float(size[1]))
        except Exception:
            return []
        changed_ids = []
        active = []
        for item in targets or []:
            if not isinstance(item, dict) or not item.get('use_inpaint', True):
                continue
            try:
                _key, text = self._auto_layout_text_key_and_value(item)
            except Exception:
                text = item.get('translated_text') or item.get('text') or ''
            if str(text or '').strip():
                active.append(item)
        try:
            if hasattr(self, 'audit_boundary_event'):
                self.audit_boundary_event('TEXT_AUTO_ADJUST_PAGE_BOUNDARY_PASS_START', page_idx=page_idx, phase=str(phase or ''), target_count=len(active), page_size=f'{int(size[0])}x{int(size[1])}')
        except Exception:
            pass
        for item in active:
            try:
                if self._auto_text_size_try_fit_item_to_page_boundary(item, page_rect, page_idx=page_idx, phase=phase):
                    cid = item.get('id')
                    if cid not in changed_ids:
                        changed_ids.append(cid)
            except Exception as exc:
                try:
                    if hasattr(self, 'audit_boundary_event'):
                        self.audit_boundary_event('TEXT_AUTO_ADJUST_PAGE_BOUNDARY_UNRESOLVED', page_idx=page_idx, item_id=item.get('id'), phase=str(phase or ''), error=repr(exc), policy='exception_during_page_boundary_pass')
                except Exception:
                    pass
        try:
            if hasattr(self, 'audit_boundary_event'):
                self.audit_boundary_event('TEXT_AUTO_ADJUST_PAGE_BOUNDARY_PASS_DONE', page_idx=page_idx, phase=str(phase or ''), changed_ids=[x for x in changed_ids if x is not None], changed_count=len([x for x in changed_ids if x is not None]))
        except Exception:
            pass
        return [x for x in changed_ids if x is not None]

    def _auto_text_adjust_dirty_fields(self):
        return ['font_size', 'x_off', 'y_off', 'inner_text_x_off', 'inner_text_y_off', 'translated_text', 'text', 'writing_direction', 'ocr_lang', 'auto_layout_mode', 'auto_wrap_height_overflow', 'auto_layout_score', 'auto_layout_fill_w', 'auto_layout_fill_h', 'auto_layout_touch_ok', 'auto_layout_ko_bound_badness', 'auto_layout_width_overflow_allowed', 'auto_layout_shape_ratio', 'auto_layout_box_ratio', 'auto_layout_line_count', 'auto_layout_overlap_shrink', 'auto_layout_pairwise_overlap_shrink', 'auto_layout_pairwise_inner_offset', 'auto_layout_pairwise_overlap_policy', 'auto_layout_pairwise_fixed_neighbor_id', 'auto_layout_pairwise_phase', 'auto_layout_pairwise_overlap_unresolved', 'auto_layout_pairwise_overlap_unresolved_cost', 'auto_layout_pairwise_old_size', 'auto_layout_pairwise_new_size', 'auto_layout_pairwise_old_x_off', 'auto_layout_pairwise_old_y_off', 'auto_layout_pairwise_new_x_off', 'auto_layout_pairwise_new_y_off', 'auto_layout_pairwise_old_inner_text_x_off', 'auto_layout_pairwise_old_inner_text_y_off', 'auto_layout_pairwise_new_inner_text_x_off', 'auto_layout_pairwise_new_inner_text_y_off', 'auto_layout_fit_rect', 'auto_layout_fit_box_source', 'auto_layout_ocr_rect_locked', 'auto_layout_effective_fit_rect_differs_from_ocr_rect', 'auto_layout_narrow_edge_original_rect', 'auto_layout_narrow_edge_expanded', 'auto_layout_narrow_edge_expand_info', 'auto_layout_median_floor_applied', 'auto_layout_median_floor_size', 'auto_layout_median_floor_old_size', 'auto_layout_median_floor_threshold', 'auto_layout_median_floor_threshold_percent', 'auto_layout_median_floor_line_count', 'auto_layout_median_floor_measured_w', 'auto_layout_median_floor_measured_h', 'auto_layout_global_overlap_shrink', 'auto_layout_global_overlap_policy', 'auto_layout_global_overlap_pass', 'auto_layout_global_overlap_old_size', 'auto_layout_global_overlap_new_size', 'auto_layout_global_overlap_unresolved_cost', 'auto_layout_safe_grow_applied', 'auto_layout_safe_grow_reason', 'auto_layout_safe_grow_old_size', 'auto_layout_safe_grow_new_size', 'auto_layout_safe_grow_target_size', 'auto_layout_available_space_grow_applied', 'auto_layout_available_space_grow_reason', 'auto_layout_available_space_grow_old_size', 'auto_layout_available_space_grow_new_size', 'auto_layout_available_space_grow_target_size', 'auto_layout_available_space_grow_old_inner_text_x_off', 'auto_layout_available_space_grow_old_inner_text_y_off', 'auto_layout_available_space_grow_new_inner_text_x_off', 'auto_layout_available_space_grow_new_inner_text_y_off', 'auto_layout_available_space_grow_line_count', 'auto_layout_available_space_grow_visual_rect']

    def _run_auto_text_size_page_postpass(self, page_idx=None, targets=None, refresh=False, reason='manual'):
        """텍스트 자동조정 호환 진입점.

        LEGACY text_auto_adjust_sequence.py는 더 이상 사용하지 않는다.
        새 본선은 ysb.ui.text_auto_adjust_engine.run_text_auto_adjust_engine_for_page 하나만 탄다.
        """
        from ysb.ui.text_auto_adjust_engine import run_text_auto_adjust_engine_for_page
        return run_text_auto_adjust_engine_for_page(
            self,
            page_idx=page_idx,
            targets=targets,
            refresh=refresh,
            reason=reason,
        )

    def _schedule_auto_text_size_page_postpass(self, page_idx=None, reason='auto_text_size_item'):
        """item 단위 호출 뒤 새 엔진을 페이지 단위로 한 번 예약한다.

        과거의 text_auto_adjust_sequence.py 예약 경로는 제거했다.
        """
        try:
            page_idx = self.idx if page_idx is None else int(page_idx)
        except Exception:
            page_idx = getattr(self, 'idx', 0)
        try:
            pending = getattr(self, '_auto_text_page_postpass_pending', None)
            if not isinstance(pending, dict):
                pending = {}
                self._auto_text_page_postpass_pending = pending
            pending[int(page_idx)] = str(reason or '')
            seq = int(getattr(self, '_auto_text_page_postpass_seq', 0) or 0) + 1
            self._auto_text_page_postpass_seq = seq
        except Exception:
            seq = 0

        def _run_deferred_engine(expected_seq=seq, pidx=page_idx):
            try:
                if expected_seq and int(getattr(self, '_auto_text_page_postpass_seq', 0) or 0) != int(expected_seq):
                    return
            except Exception:
                pass
            try:
                pending = getattr(self, '_auto_text_page_postpass_pending', {}) or {}
                pending.pop(int(pidx), None)
            except Exception:
                pass
            try:
                self._run_auto_text_size_page_postpass(
                    page_idx=pidx,
                    refresh=(pidx == getattr(self, 'idx', None)),
                    reason='deferred_item_auto_adjust_engine',
                )
            except Exception as exc:
                try:
                    if hasattr(self, 'audit_boundary_event'):
                        self.audit_boundary_event('TEXT_AUTO_ADJUST_ENGINE_DEFERRED_ERROR', page_idx=pidx, error=repr(exc))
                except Exception:
                    pass

        try:
            QTimer.singleShot(220, _run_deferred_engine)
        except Exception:
            _run_deferred_engine()

    def auto_text_size_for_page(self, page_idx, refresh=False, progress_cb=None):
        """페이지 단위 텍스트 자동조정 진입점. 새 엔진만 사용한다."""
        from ysb.ui.text_auto_adjust_engine import run_text_auto_adjust_engine_for_page
        changed_ids = run_text_auto_adjust_engine_for_page(
            self,
            page_idx=page_idx,
            refresh=refresh,
            progress_cb=progress_cb,
            reason='auto_text_size_for_page_engine',
        )
        return len(changed_ids or [])

    def _auto_text_size_for_page_impl(self, page_idx, refresh=False, progress_cb=None):
        """구버전 내부 호출 호환 wrapper. 새 엔진만 사용한다."""
        return self.auto_text_size_for_page(page_idx, refresh=refresh, progress_cb=progress_cb)

    def auto_linebreak_for_page(self, page_idx, refresh=False):
        """구버전 자동 줄내림 호환 경로. 이제 텍스트 자동 조정과 같은 루틴을 탄다."""
        return self.auto_text_size_for_page(page_idx, refresh=refresh)

    def _auto_text_adjust_progress_detail(self, current, total, page_idx=None, item=None, extra=""):
        """텍스트 자동 조정 진행창은 진행률만 짧게 보여준다."""
        try:
            return f"진행: {int(current)}/{max(1, int(total or 0))}"
        except Exception:
            return "진행 중..."

    def _auto_text_adjust_batch_progress_detail(self, page_current, page_total, page_idx=None, text_current=0, text_total=0, item=None, extra="", overall_current=None, overall_total=None):
        """일괄 텍스트 자동 조정 진행창도 긴 설명 없이 통합 진행률만 보여준다."""
        try:
            if overall_total is not None and int(overall_total) > 0:
                return f"진행: {int(overall_current or 0)}/{int(overall_total)}"
        except Exception:
            pass
        try:
            return f"진행: {int(page_current)}/{max(1, int(page_total or 0))} · 텍스트 {int(text_current)}/{max(1, int(text_total or 0))}"
        except Exception:
            return "진행 중..."

    def auto_text_size_current(self):
        if not self.paths:
            return
        self.commit_current_page_ui_to_data()
        targets = list(self.auto_target_items_for_page(self.idx) or [])
        total = len(targets)
        if targets:
            self.append_text_engine_diff_for_items(
                "텍스트 자동 조정",
                targets,
                fields=self._auto_text_adjust_dirty_fields(),
                page_idx=self.idx,
            )
        self._long_task_cancel_requested = False
        try:
            self.show_task_progress_overlay(
                "텍스트 자동 조정",
                self._auto_text_adjust_progress_detail(0, total, self.idx),
                total=total,
                cancellable=True,
            )
            QApplication.processEvents()
        except Exception:
            pass

        def _progress(current, total_count, item, phase):
            try:
                self.update_task_progress_overlay(
                    current=current,
                    total=total_count,
                    detail=self._auto_text_adjust_progress_detail(current, total_count, self.idx, item),
                )
                QApplication.processEvents()
            except Exception:
                pass

        try:
            changed = self.auto_text_size_for_page(self.idx, refresh=True, progress_cb=_progress)
        finally:
            try:
                QTimer.singleShot(350, self.hide_task_progress_overlay)
            except Exception:
                try:
                    self.hide_task_progress_overlay()
                except Exception:
                    pass
        if changed:
            self.finalize_text_change(
                items=targets,
                fields=self._auto_text_adjust_dirty_fields(),
                page_idx=self.idx,
                reason='텍스트 자동 조정',
                delay_ms=1800,
            )
        else:
            try:
                self.schedule_deferred_auto_save_project(1800)
            except Exception:
                self.auto_save_project()
        try:
            self.ensure_final_text_layer_bound('after_auto_text_size_current', delay_ms=120)
        except Exception:
            pass
        if bool(getattr(self, "_long_task_cancel_requested", False)):
            self.log(f"↩️ 텍스트 자동 조정 취소: 현재 페이지 {changed}개 적용")
        else:
            self.log(f"🤖 텍스트 자동 조정 완료: 현재 페이지 {changed}개")

    def auto_text_size_batch(self):
        if not self.paths:
            return
        title = "일괄 텍스트 자동 조정"
        selected_indices, selected_label = self.choose_batch_page_indices_for_context(title, "auto_text_size")
        if selected_indices is None:
            self.log("↩️ 일괄 텍스트 자동 조정 취소")
            return
        self.commit_current_page_ui_to_data()

        # 일괄 자동조정은 페이지 안에서 텍스트별 진행 신호가 많이 발생한다.
        # 진행창 게이지는 페이지 내부 0~N으로 리셋하지 않고, 선택 페이지 전체의
        # 통합 텍스트 단위로 계산한다. 현재 페이지 내부 진행률은 detail 텍스트로만 표시한다.
        page_target_counts = {}
        page_unit_bases = {}
        page_unit_units = {}
        page_orders = {}
        total_units = 0
        try:
            for order, page_idx in enumerate(selected_indices, 1):
                try:
                    count = len(list(self.auto_target_items_for_page(page_idx) or []))
                except Exception:
                    count = 0
                page_target_counts[int(page_idx)] = int(count)
                page_unit_bases[int(page_idx)] = int(total_units)
                page_unit_units[int(page_idx)] = max(1, int(count))
                page_orders[int(page_idx)] = int(order)
                total_units += max(1, int(count))
            self._batch_progress_units_total = max(1, int(total_units))
            self._batch_progress_units_done = 0
            self._batch_progress_unit_page_bases = dict(page_unit_bases)
            self._batch_progress_unit_page_units = dict(page_unit_units)
            self._batch_progress_unit_page_orders = dict(page_orders)
        except Exception:
            # 실패해도 기존 페이지 단위 게이지로 동작하게 둔다.
            pass

        def process_page(i):
            targets = list(self.auto_target_items_for_page(i) or [])
            total = len(targets)
            page_order = int(page_orders.get(int(i), 0) or 0)
            page_total = len(selected_indices)
            page_base = int(page_unit_bases.get(int(i), 0) or 0)
            overall_total = int(getattr(self, '_batch_progress_units_total', 0) or 0)
            def _progress(current, total_count, item, phase):
                try:
                    text_current = max(0, min(int(current or 0), int(total_count or 0)))
                    overall_current = page_base + text_current
                    if overall_total > 0:
                        self._batch_progress_units_done = max(0, min(int(overall_current), int(overall_total)))
                    self.update_task_progress_overlay(
                        current=(self._batch_progress_units_done if overall_total > 0 else None),
                        total=(overall_total if overall_total > 0 else None),
                        detail=self._auto_text_adjust_batch_progress_detail(
                            page_order, page_total, i, text_current, int(total_count or 0), item,
                            overall_current=(self._batch_progress_units_done if overall_total > 0 else None),
                            overall_total=(overall_total if overall_total > 0 else None),
                        ),
                    )
                    QApplication.processEvents()
                except Exception:
                    pass
            changed = self.auto_text_size_for_page(i, refresh=False, progress_cb=_progress)
            try:
                if overall_total > 0:
                    self._batch_progress_units_done = min(overall_total, page_base + max(1, int(total)))
            except Exception:
                pass
            if changed <= 0:
                return "skipped", "변경된 텍스트 없음"
            return "done", f"{changed}개 조정"

        result = self.run_page_queue_batch(title, "auto_text_size", selected_indices, selected_label, process_page, visual=True, cancellable=True)
        try:
            if self.cb_mode.currentIndex() == 4:
                self.schedule_final_text_scene_refresh(80)
            self.schedule_deferred_auto_save_project(1800)
        except Exception:
            pass



    def auto_linebreak_current(self):
        """구버전 자동 줄내림 단축키 호환. 텍스트 자동 조정을 실행한다."""
        return self.auto_text_size_current()

    def auto_linebreak_batch(self):
        """구버전 일괄 자동 줄내림 단축키 호환. 일괄 텍스트 자동 조정을 실행한다."""
        return self.auto_text_size_batch()



    def current_scene_cursor_pos(self):
        try:
            return self.view.mapToScene(self.view.mapFromGlobal(QCursor.pos()))
        except Exception:
            rect = self.view.scene.sceneRect()
            return rect.center()

    def item_id_value(self, item_or_data):
        data = item_or_data.data if isinstance(item_or_data, TypesettingItem) else item_or_data
        try:
            return int(data.get('id'))
        except Exception:
            return data.get('id') if isinstance(data, dict) else None

    def find_data_item_by_id(self, item_id):
        curr = self.data.get(self.idx)
        if not curr:
            return None
        for d in curr.get('data', []):
            if str(d.get('id')) == str(item_id):
                return d
        return None

    def select_text_item_and_row(self, text_item):
        if text_item is None:
            return
        if getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
            return
        scene = self._safe_graphics_scene()
        if scene is None:
            return
        self._syncing_selection = True
        try:
            try:
                for item in scene.items():
                    if isinstance(item, TypesettingItem):
                        item.setSelected(item is text_item)
            except RuntimeError:
                return
            self.select_table_rows_by_ids([text_item.data.get('id')])
            try:
                self.focus_final_text_canvas_for_shortcut(reason='select_text_item_and_row')
            except Exception:
                pass
        finally:
            self._syncing_selection = False
        self.on_scene_selection_changed()

    def row_to_text_data(self, row):
        curr = self.data.get(self.idx)
        if not curr or row <= 0:
            return None
        data_index = row - 1
        d = curr.get('data', [])
        if 0 <= data_index < len(d):
            return d[data_index]
        return None

    def selected_text_data_items(self):
        curr = self.data.get(self.idx)
        if not curr:
            return []
        ids = {str(x.data.get('id')) for x in self.selected_text_items()}
        ids.update(str(x) for x in self.selected_table_text_ids())
        if not ids:
            return []
        return [d for d in curr.get('data', []) if str(d.get('id')) in ids]

    def clear_masks_for_text_data(self, data_item):
        curr = self.data.get(self.idx)
        if not curr or not data_item:
            return

        # 텍스트 하나를 삭제할 때도 분석 자동 생성 마스크만 정리한다.
        # 삭제 영역이 다른 활성 OCR 영역과 겹치면 겹친 부분은 살아 있는 OCR 마스크로 보고 보존한다.
        # 페인팅 마스크의 사용자 수정용 OFF 레이어는 절대 지우지 않는다.
        for key in ('mask_merge', 'mask_inpaint'):
            mask = curr.get(key)
            if not isinstance(mask, np.ndarray):
                continue
            try:
                base_gray = cv2.cvtColor(mask, cv2.COLOR_RGB2GRAY) if getattr(mask, 'ndim', 2) == 3 else mask
                shape = base_gray.shape[:2]
                if hasattr(self, '_ocr_item_region_mask_for_shape'):
                    remove_region = self._ocr_item_region_mask_for_shape(data_item, shape)
                else:
                    remove_region = None
                if not isinstance(remove_region, np.ndarray) or not np.any(remove_region):
                    # helper가 없거나 실패하면 기존 rect fallback을 사용한다.
                    rect = data_item.get('rect') or [0, 0, 0, 0]
                    try:
                        x = int(round(float(rect[0]) + float(data_item.get('x_off', 0) or 0)))
                        y = int(round(float(rect[1]) + float(data_item.get('y_off', 0) or 0)))
                        w = int(round(float(rect[2])))
                        h = int(round(float(rect[3])))
                    except Exception:
                        continue
                    mh, mw = shape[:2]
                    x1 = max(0, x)
                    y1 = max(0, y)
                    x2 = min(mw, x + w)
                    y2 = min(mh, y + h)
                    if x2 <= x1 or y2 <= y1:
                        continue
                    remove_region = np.zeros(shape, dtype=np.uint8)
                    remove_region[y1:y2, x1:x2] = 255
                if hasattr(self, '_active_ocr_region_mask_for_shape'):
                    active_region = self._active_ocr_region_mask_for_shape(curr, shape, exclude_items=[data_item])
                else:
                    active_region = np.zeros(shape, dtype=np.uint8)
                if not isinstance(active_region, np.ndarray):
                    active_region = np.zeros(shape, dtype=np.uint8)
                remove_only = cv2.bitwise_and(remove_region, cv2.bitwise_not(active_region))
                if not np.any(remove_only):
                    try:
                        self.audit_boundary_event(
                            'MASK_CLEAR_TEXT_ITEM_PRESERVE_ALL',
                            page_idx=getattr(self, 'idx', None),
                            key=str(key),
                            item_id=data_item.get('id'),
                            remove_region_nonzero=int(np.count_nonzero(remove_region)),
                            active_region_nonzero=int(np.count_nonzero(active_region)),
                        )
                    except Exception:
                        pass
                    continue
                before_nz = int(np.count_nonzero(base_gray))
                if mask.ndim == 2:
                    out = mask.copy()
                    out[remove_only > 0] = 0
                else:
                    out = mask.copy()
                    out[remove_only > 0] = 0
                after_gray = cv2.cvtColor(out, cv2.COLOR_RGB2GRAY) if getattr(out, 'ndim', 2) == 3 else out
                after_nz = int(np.count_nonzero(after_gray))
                if np.array_equal(mask, out):
                    continue
                curr[key] = out
                curr[f'{key}_dirty'] = True
                try:
                    self.mark_page_data_dirty_explicit(self.idx, f'mask:{key}')
                except Exception:
                    try:
                        self.mark_active_page_dirty('mask')
                    except Exception:
                        pass
                try:
                    self.audit_boundary_event(
                        'MASK_CLEAR_TEXT_ITEM',
                        page_idx=getattr(self, 'idx', None),
                        key=str(key),
                        item_id=data_item.get('id'),
                        before_nonzero=before_nz,
                        after_nonzero=after_nz,
                        removed_nonzero=max(0, before_nz - after_nz),
                        remove_region_nonzero=int(np.count_nonzero(remove_region)),
                        remove_only_nonzero=int(np.count_nonzero(remove_only)),
                        preserved_overlap_nonzero=int(np.count_nonzero(cv2.bitwise_and(remove_region, active_region))),
                        active_region_nonzero=int(np.count_nonzero(active_region)),
                    )
                except Exception:
                    pass
            except Exception as e:
                try:
                    self.log(f"⚠️ 텍스트 삭제 마스크 정리 실패({key}): {e}")
                except Exception:
                    pass

    def delete_text_data_items(self, data_items=None, ask=True):
        curr = self.data.get(self.idx)
        if not curr:
            return False

        if data_items is None:
            data_items = self.selected_text_data_items()
        data_items = [d for d in (data_items or []) if d in curr.get('data', [])]
        if not data_items:
            self.log("⚠️ There is no text to delete." if self.ui_language == LANG_EN else "⚠️ 삭제할 텍스트가 없습니다.")
            return False

        try:
            mode = int(self.cb_mode.currentIndex())
        except Exception:
            mode = 0

        # Delete can be triggered while a QGraphicsItem/key event is still on the Qt stack.
        # Running ref_tab()/mode_chg()/scene purge synchronously in that stack has caused
        # native Abort/access-violation crashes.  Confirm now, then apply the deletion after
        # the current event has unwound while keeping object references to the selected rows.
        if mode == 4 and not bool(getattr(self, '_text_delete_deferred_apply_active', False)):
            if ask:
                if self.ui_language == LANG_EN:
                    msg = f"Delete {len(data_items)} selected text item(s)?\nThe mask for those areas will also be cleared."
                else:
                    msg = f"선택한 텍스트 {len(data_items)}개를 삭제할까요?\n해당 영역의 마스크도 함께 지워집니다."
                ans = QMessageBox.question(
                    self,
                    self.tr_ui("텍스트 삭제"),
                    msg,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if ans != QMessageBox.StandardButton.Yes:
                    return False
            snapshot_items = list(data_items)
            try:
                self.audit_boundary_event(
                    "TEXT_DELETE_APPLY_DEFERRED",
                    count=len(snapshot_items),
                    delay_ms=0,
                    throttle_ms=100,
                )
            except Exception:
                pass

            def _apply_deferred_delete():
                if getattr(self, '_app_is_closing', False) or getattr(self, '_closing_confirmed', False):
                    return
                self._text_delete_deferred_apply_active = True
                try:
                    self.delete_text_data_items(snapshot_items, ask=False)
                finally:
                    self._text_delete_deferred_apply_active = False

            try:
                QTimer.singleShot(0, _apply_deferred_delete)
            except Exception:
                _apply_deferred_delete()
            return True

        if ask:
            if self.ui_language == LANG_EN:
                msg = f"Delete {len(data_items)} selected text item(s)?\nThe mask for those areas will also be cleared."
            else:
                msg = f"선택한 텍스트 {len(data_items)}개를 삭제할까요?\n해당 영역의 마스크도 함께 지워집니다."
            ans = QMessageBox.question(
                self,
                self.tr_ui("텍스트 삭제"),
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return False

        # 058에서 텍스트 라인 삭제를 프로젝트 스냅샷 Undo로 잡았더니
        # 표/탭 갱신 시 렉이 커져서, 가벼운 기존 page undo 방식으로 되돌린다.
        undo_ok = self.undo_push_text_line('텍스트 삭제', include_masks=True)
        try:
            self.audit_boundary_event("TEXT_DELETE_UNDO_RECORD", count=len(data_items), undo_ok=bool(undo_ok), throttle_ms=100)
        except Exception:
            pass

        old_text_ids = []
        old_data_ref_ids = set()
        for d in list(data_items):
            if isinstance(d, dict):
                old_data_ref_ids.add(id(d))
                try:
                    if d.get('id') is not None:
                        old_text_ids.append(d.get('id'))
                except Exception:
                    pass

        entered_guard = False
        removed_scene_items = 0
        if mode == 4:
            try:
                if hasattr(self, '_enter_text_scene_mutation_timer_guard'):
                    self._enter_text_scene_mutation_timer_guard(reason='text_delete_live_remove')
                    entered_guard = True
            except Exception:
                entered_guard = False
            try:
                timer = getattr(self, '_final_text_light_refresh_timer', None)
                if timer is not None and timer.isActive():
                    timer.stop()
            except Exception:
                pass
            try:
                if hasattr(self, '_remove_inline_text_editor_from_scene'):
                    self._remove_inline_text_editor_from_scene()
            except Exception:
                pass
            try:
                if hasattr(self, '_remove_live_text_scene_items_by_identity_or_id'):
                    removed_scene_items = self._remove_live_text_scene_items_by_identity_or_id(
                        data_ref_ids=old_data_ref_ids,
                        text_ids=old_text_ids,
                        reason='text_delete_live_remove',
                    )
            except Exception:
                removed_scene_items = 0

        deleted_count = 0
        for d in list(data_items):
            self.clear_masks_for_text_data(d)
            try:
                curr['data'].remove(d)
                deleted_count += 1
            except ValueError:
                pass

        if deleted_count <= 0:
            if entered_guard:
                try:
                    self._release_text_scene_mutation_timer_guard(reason='text_delete_live_remove_empty')
                except Exception:
                    pass
            return False

        # 삭제 후 우측 텍스트 행 라인넘버(ID)를 1부터 다시 정렬한다.
        # 분석도/마스크 탭의 왼쪽 번호 박스도 같은 data id를 보므로 즉시 다시 그린다.
        self.renumber_text_items_for_current_page(curr)
        try:
            if hasattr(self, 'clip_page_masks_to_active_ocr_regions'):
                self.clip_page_masks_to_active_ocr_regions(self.idx, reason='delete_text_data_items')
        except Exception:
            pass

        try:
            self.audit_boundary_event(
                "TEXT_DELETE_LIVE_APPLY",
                deleted_count=deleted_count,
                removed_scene_items=removed_scene_items,
                mode=mode,
                throttle_ms=100,
            )
        except Exception:
            pass

        if mode == 4:
            # Final tab deletion is now handled as a small live scene mutation.
            # Do not call refresh_after_text_line_change(), because that schedules
            # safe_text_scene_resync -> purge all TypesettingItems -> mode_chg(4),
            # which can invalidate Qt item references immediately after Delete.
            try:
                if hasattr(self, '_purge_orphan_text_scene_items'):
                    self._purge_orphan_text_scene_items(reason='text_delete_live_apply')
            except Exception:
                pass
            try:
                self.schedule_text_table_refresh_after_structure_change([], delay_ms=0, reason='text_delete_live_apply')
            except Exception:
                try:
                    self.ref_tab()
                except Exception:
                    pass
            try:
                self.log_text_layer_lifecycle_snapshot(reason=reason, stage='add_live_items_done_before_update', max_items=20, stack=False)
            except Exception:
                pass
            try:
                self.force_update_final_scene_region()
            except Exception:
                try:
                    scene = self._safe_graphics_scene() if hasattr(self, '_safe_graphics_scene') else getattr(getattr(self, 'view', None), 'scene', None)
                    if scene is not None:
                        scene.update()
                except Exception:
                    pass
            try:
                self.mark_current_page_for_recovery_checkpoint('text')
            except Exception:
                pass
            try:
                self.mark_active_page_dirty('text')
            except Exception:
                pass
            try:
                self.schedule_deferred_auto_save_project()
            except Exception:
                try:
                    self.auto_save_project()
                except Exception:
                    pass
            finally:
                if entered_guard:
                    try:
                        self._release_text_scene_mutation_timer_guard(reason='text_delete_live_remove')
                    except Exception:
                        pass
        else:
            if entered_guard:
                try:
                    self._release_text_scene_mutation_timer_guard(reason='text_delete_live_remove_non_final')
                except Exception:
                    pass
            old_skip_mode_mask_commit = getattr(self, "_skip_mode_mask_commit", False)
            old_skip_view_mask_commit = getattr(self, "_skip_view_mask_commit", False)
            old_skip_reason = getattr(self, "_skip_view_mask_commit_reason", "")
            self._skip_mode_mask_commit = True
            self._skip_view_mask_commit = True
            self._skip_view_mask_commit_reason = 'delete_text_refresh_data_to_view'
            try:
                self.ref_tab()
                if mode in (2, 3):
                    self.mode_chg(mode)
                else:
                    self.refresh_after_text_line_change(autosave=False)
            finally:
                self._skip_mode_mask_commit = old_skip_mode_mask_commit
                self._skip_view_mask_commit = old_skip_view_mask_commit
                self._skip_view_mask_commit_reason = old_skip_reason
            try:
                self.schedule_deferred_auto_save_project()
            except Exception:
                try:
                    self.auto_save_project()
                except Exception:
                    pass

        self.log((f"🗑️ Text deletion complete: {deleted_count} items / IDs reordered" if self.ui_language == LANG_EN else f"🗑️ 텍스트 삭제 완료: {deleted_count}개 / 번호 재정렬"))
        return True

    def _text_object_clipboard_mime_type(self):
        return "application/x-ysb-translator-text-items"

    def _clipboard_plain_text_for_text_items(self, data_items):
        texts = []
        for d in data_items or []:
            if not isinstance(d, dict):
                continue
            text = d.get('translated_text')
            if text in (None, ''):
                text = d.get('text', '')
            text = str(text or '')
            if text:
                texts.append(text)
        return "\n".join(texts)

    def _strip_text_clipboard_runtime_keys(self, item):
        """Remove live Qt/runtime-only state before copy/paste serialization."""
        if not isinstance(item, dict):
            return item
        for key in (
            'pending_new_text', 'force_show', '_qt_item', '_scene_item',
            '_transform_mode', '_skew_mode', '_trapezoid_mode', '_arc_mode',
            'arc_active_index', '_drag_state', '_resize_state', '_edit_widget',
        ):
            try:
                item.pop(key, None)
            except Exception:
                pass
        return item

    def _json_safe_text_clipboard_item(self, item):
        """Return a JSON-serializable text-item copy for the OS clipboard."""
        def _safe_value(value):
            if value is None or isinstance(value, (str, int, float, bool)):
                return value
            if isinstance(value, dict):
                out = {}
                for k, v in value.items():
                    sk = str(k)
                    # Runtime/private Qt references are not project data.
                    if sk in ('_qt_item', '_scene_item', '_edit_widget'):
                        continue
                    sv = _safe_value(v)
                    if sv is not _DROP:
                        out[sk] = sv
                return out
            if isinstance(value, (list, tuple)):
                out = []
                for v in value:
                    sv = _safe_value(v)
                    if sv is not _DROP:
                        out.append(sv)
                return out
            # QPointF/QRectF/QImage/QGraphicsItem and other runtime objects must not
            # enter the clipboard payload.  Dropping them is safer than converting to
            # an arbitrary string that could later be mistaken for real project data.
            return _DROP

        class _DropSentinel:
            pass

        _DROP = _DropSentinel()
        try:
            copied = copy.deepcopy(item) if isinstance(item, dict) else dict(item or {})
        except Exception:
            copied = dict(item or {}) if isinstance(item, dict) else {}
        copied = self._strip_text_clipboard_runtime_keys(copied)
        safe = _safe_value(copied)
        if not isinstance(safe, dict):
            safe = {}
        return safe

    def _safe_text_object_clipboard_items(self, data_items):
        items = []
        for d in data_items or []:
            if not isinstance(d, dict):
                continue
            item = self._json_safe_text_clipboard_item(d)
            if item:
                items.append(item)
        return items

    def publish_text_object_clipboard_to_os(self, data_items):
        """Copy YSB text-object clipboard to the OS clipboard as a custom MIME payload.

        The internal Python clipboard can be lost or bypassed when Ctrl+C/V is eaten by
        QGraphicsView/QAction focus routing.  Keeping an object payload in QClipboard
        makes right-click copy -> shortcut paste and shortcut copy -> right-click paste
        share the same source without converting YSB text boxes to plain text.
        """
        items = self._safe_text_object_clipboard_items(data_items)
        if not items:
            return False
        try:
            payload = json.dumps(items, ensure_ascii=False).encode('utf-8')
            mime = QMimeData()
            mime.setData(self._text_object_clipboard_mime_type(), QByteArray(payload))
            plain = self._clipboard_plain_text_for_text_items(items)
            if plain:
                mime.setText(plain)
            QApplication.clipboard().setMimeData(mime)
            try:
                self.audit_boundary_event('TEXT_OBJECT_CLIPBOARD_OS_PUBLISHED', count=len(items), text_len=len(plain), throttle_ms=80)
            except Exception:
                pass
            return True
        except Exception as e:
            try:
                self.audit_boundary_event('TEXT_OBJECT_CLIPBOARD_OS_PUBLISH_ERROR', error=str(e), throttle_ms=80)
            except Exception:
                pass
            return False

    def load_text_object_clipboard_from_os(self):
        """Restore YSB text-object clipboard from the OS custom MIME payload if present."""
        try:
            mime = QApplication.clipboard().mimeData()
        except Exception:
            mime = None
        if mime is None:
            return False
        try:
            fmt = self._text_object_clipboard_mime_type()
            if not mime.hasFormat(fmt):
                return False
            raw = bytes(mime.data(fmt)).decode('utf-8')
            items = json.loads(raw)
            if isinstance(items, dict):
                items = [items]
            items = self._safe_text_object_clipboard_items(items)
            if not items:
                return False
            self.text_clipboard = items
            self.text_clipboard_is_plain = False
            self.text_paste_pending = False
            try:
                self.audit_boundary_event('TEXT_OBJECT_CLIPBOARD_OS_LOADED', count=len(items), throttle_ms=80)
            except Exception:
                pass
            return True
        except Exception as e:
            try:
                self.audit_boundary_event('TEXT_OBJECT_CLIPBOARD_OS_LOAD_ERROR', error=str(e), throttle_ms=80)
            except Exception:
                pass
            return False

    def copy_text_data_items(self, data_items=None):
        if data_items is None:
            data_items = self.selected_text_data_items()
        data_items = [d for d in (data_items or []) if isinstance(d, dict)]
        if not data_items:
            self.log("⚠️ 복사할 텍스트가 없습니다.")
            return False

        self.text_clipboard = self._safe_text_object_clipboard_items(data_items)
        if not self.text_clipboard:
            self.log("⚠️ 복사할 수 있는 텍스트 데이터가 없습니다.")
            return False
        self.text_clipboard_is_plain = False
        self.text_paste_pending = False
        self.publish_text_object_clipboard_to_os(self.text_clipboard)
        self.log(f"📋 텍스트 복사 완료: {len(self.text_clipboard)}개")
        return True

    def next_text_id(self):
        curr = self.data.get(self.idx)
        max_id = 0
        if curr:
            for d in curr.get('data', []):
                try:
                    max_id = max(max_id, int(d.get('id', 0)))
                except Exception:
                    pass
        return max_id + 1

    def text_clipboard_visible_anchor(self, data_items=None):
        """붙여넣기 기준점을 실제 보이는 텍스트의 좌상단에 가깝게 잡는다."""
        src_items = [copy.deepcopy(d) for d in (data_items or self.text_clipboard or []) if isinstance(d, dict)]
        if not src_items:
            return 0.0, 0.0
        first = src_items[0]
        if first.get('rasterized_text'):
            rect = list(first.get('rect') or [0, 0, 1, 1])
            while len(rect) < 4:
                rect.append(1)
            try:
                return float(rect[0]) + float(first.get('x_off', 0) or 0), float(rect[1]) + float(first.get('y_off', 0) or 0)
            except Exception:
                return 0.0, 0.0
        try:
            item = TypesettingItem(
                first,
                self.cb_font.currentFont().family() if hasattr(self, 'cb_font') else 'Arial',
                self.sb_font_size.value() if hasattr(self, 'sb_font_size') else int(first.get('font_size', 24) or 24),
                self.sb_strk.value() if hasattr(self, 'sb_strk') else int(first.get('stroke_width', 0) or 0),
                None,
                text_color=getattr(self, "default_text_color", "#000000"),
                stroke_color=getattr(self, "default_stroke_color", "#FFFFFF"),
                align=getattr(self, "default_align", "center"),
            )
            r = item.text_content_scene_rect()
            if not r.isNull() and r.width() > 0 and r.height() > 0:
                return float(r.left()), float(r.top())
        except Exception:
            pass
        rect = list(first.get('rect') or [0, 0, 1, 1])
        while len(rect) < 4:
            rect.append(1)
        try:
            return float(rect[0]) + float(first.get('x_off', 0) or 0), float(rect[1]) + float(first.get('y_off', 0) or 0)
        except Exception:
            return 0.0, 0.0

    def text_clipboard_visible_bounds(self, data_items=None):
        """붙여넣기 미리보기/확정 배치용 대략 bounds를 구한다."""
        src_items = [copy.deepcopy(d) for d in (data_items or self.text_clipboard or []) if isinstance(d, dict)]
        if not src_items:
            return 0.0, 0.0, 1.0, 1.0
        xs = []
        ys = []
        for d in src_items:
            rect = list(d.get('rect') or [0, 0, 1, 1])
            while len(rect) < 4:
                rect.append(1)
            try:
                x = float(rect[0]) + float(d.get('x_off', 0) or 0)
                y = float(rect[1]) + float(d.get('y_off', 0) or 0)
                w = max(1.0, float(rect[2]))
                h = max(1.0, float(rect[3]))
            except Exception:
                x, y, w, h = 0.0, 0.0, 1.0, 1.0
            xs.extend([x, x + w])
            ys.extend([y, y + h])
        return min(xs), min(ys), max(xs), max(ys)

    def text_clipboard_paste_origin_from_cursor(self, data_items, scene_pos):
        """커서의 끝이 텍스트 묶음의 상단 중앙에 오도록 배치한다."""
        try:
            cx, cy = float(scene_pos.x()), float(scene_pos.y())
        except Exception:
            cx, cy = 0.0, 0.0
        base_x, base_y = self.text_clipboard_visible_anchor(data_items)
        try:
            _l, _t, right, bottom = self.text_clipboard_visible_bounds(data_items)
            group_w = max(1.0, float(right) - float(base_x))
            group_h = max(1.0, float(bottom) - float(base_y))
        except Exception:
            group_w, group_h = 260.0, 80.0
        gap = 3.0
        return cx - (group_w / 2.0), cy - group_h - gap

    def schedule_text_table_refresh_after_structure_change(self, selected_ids=None, delay_ms=0, reason='text structure change'):
        """텍스트 data 개수 변경 뒤 우측 텍스트 라인 표만 안전하게 갱신한다.

        붙여넣기/삭제/복원 직후에는 scene item 개수와 data 개수가 잠깐 다를 수 있다.
        이때 ref_tab()을 mousePressEvent/keyPressEvent 안에서 즉시 호출하거나
        mode_chg(4)를 강제로 태우면 Qt scene 생명주기가 꼬일 수 있으므로,
        표 갱신만 다음 이벤트 루프로 넘겨 분리한다.
        """
        ids = [x for x in (selected_ids or []) if x is not None]

        def _refresh_table_only():
            try:
                if getattr(self, '_app_is_closing', False) or getattr(self, '_closing_confirmed', False):
                    return
            except Exception:
                pass
            try:
                self.ref_tab()
            except Exception:
                return
            if ids:
                try:
                    self.select_table_rows_by_ids(ids)
                except Exception:
                    pass
            try:
                self.audit_boundary_event(
                    'TEXT_TABLE_REFRESH_AFTER_STRUCTURE_CHANGE',
                    reason=str(reason or ''),
                    ids=','.join(str(x) for x in ids),
                    throttle_ms=100,
                )
            except Exception:
                pass

        try:
            QTimer.singleShot(max(0, int(delay_ms or 0)), _refresh_table_only)
        except Exception:
            _refresh_table_only()


    def ensure_final_text_layer_bound(self, reason='final_text_layer_bound_check', *, delay_ms=0):
        """최종결과 탭의 텍스트 data와 live TypesettingItem 상태를 진단만 한다.

        이전 패치에서는 data에는 translated_text가 있는데 scene에 TypesettingItem이 없으면
        누락된 item을 즉시 다시 붙이는 안전망을 두었다. 하지만 그 방식은 show_text=False로
        정상 draw 루트가 막힌 원인을 가릴 수 있으므로 제거한다. 이제 이 함수는 불일치를
        로그로만 남긴다. 실제 표시 여부는 mode_chg/draw_movable_texts의 정상 경로가 책임진다.
        """
        def _run():
            try:
                if getattr(self, '_app_is_closing', False) or getattr(self, '_closing_confirmed', False):
                    return False
            except Exception:
                pass
            try:
                if int(self.cb_mode.currentIndex()) != 4:
                    return False
            except Exception:
                return False
            try:
                scene_ids, data_ids, selected_ids = self._safe_text_scene_current_ids()
            except Exception as exc:
                try:
                    self.audit_boundary_event('TEXT_LAYER_BIND_CHECK_ERROR', reason=str(reason or ''), error=repr(exc))
                except Exception:
                    pass
                return False
            missing = sorted(list(set(data_ids) - set(scene_ids)), key=lambda x: str(x))
            extra = sorted(list(set(scene_ids) - set(data_ids)), key=lambda x: str(x))
            try:
                self.audit_boundary_event(
                    'TEXT_LAYER_BIND_CHECK',
                    reason=str(reason or ''),
                    scene_count=len(scene_ids),
                    data_count=len(data_ids),
                    missing_count=len(missing),
                    extra_count=len(extra),
                    missing=','.join(str(x) for x in missing[:30]),
                    extra=','.join(str(x) for x in extra[:30]),
                    repair_enabled=False,
                )
            except Exception:
                pass
            if missing or extra:
                try:
                    self.audit_boundary_event(
                        'TEXT_LAYER_BIND_MISMATCH_NO_REPAIR',
                        reason=str(reason or ''),
                        missing_count=len(missing),
                        extra_count=len(extra),
                        missing=','.join(str(x) for x in missing[:30]),
                        extra=','.join(str(x) for x in extra[:30]),
                        policy='diagnostic_only_normal_draw_must_handle_text_layer',
                        stack=True,
                    )
                except Exception:
                    pass
            return False

        try:
            delay_ms = max(0, int(delay_ms or 0))
        except Exception:
            delay_ms = 0
        if delay_ms > 0:
            try:
                QTimer.singleShot(delay_ms, _run)
                return True
            except Exception:
                return bool(_run())
        return bool(_run())

    def _add_live_text_items_for_ids(self, text_ids, *, selected=True, reason='text_add_live_items'):
        """Add newly-created text data rows to the current final-result scene without a full mode rebuild.

        Paste/delete/undo can temporarily make curr['data'] and live TypesettingItem count differ.
        For the common paste case the safe fix is to add only the missing items.  Calling
        mode_chg(4) during the same click/key event can invalidate QGraphicsItem references
        still held by Qt and crash the process, especially with the source compare clone view on.
        """
        try:
            if int(self.cb_mode.currentIndex()) != 4:
                return False
        except Exception:
            return False
        try:
            self.log_text_layer_lifecycle_snapshot(reason=reason, stage='add_live_items_enter', max_items=20, stack=True)
        except Exception:
            pass
        try:
            ids = [x for x in (text_ids or []) if x is not None]
        except Exception:
            ids = []
        if not ids:
            return False
        curr = self.data.get(self.idx)
        if not isinstance(curr, dict):
            return False
        data_list = curr.get('data', []) or []
        data_by_id = {}
        try:
            for d in data_list:
                if isinstance(d, dict) and d.get('id') is not None:
                    data_by_id[str(d.get('id'))] = d
        except Exception:
            data_by_id = {}
        scene = self._safe_graphics_scene() if hasattr(self, '_safe_graphics_scene') else getattr(getattr(self, 'view', None), 'scene', None)
        if scene is None:
            return False
        try:
            existing_ids = {
                str(getattr(obj, 'data', {}).get('id'))
                for obj in list(scene.items())
                if isinstance(obj, TypesettingItem) and getattr(obj, 'data', {}).get('id') is not None
            }
        except Exception:
            existing_ids = set()
        try:
            if selected:
                scene.clearSelection()
        except Exception:
            pass
        created = []
        rebound = 0
        old_rebuild = getattr(self, '_is_rebuilding_text_layer', False)
        self._is_rebuilding_text_layer = True
        entered_guard = False
        try:
            try:
                if hasattr(self, '_enter_text_scene_mutation_timer_guard'):
                    self._enter_text_scene_mutation_timer_guard(reason=str(reason or 'text_add_live_items'))
                    entered_guard = True
            except Exception:
                entered_guard = False
            try:
                top_z = max([float(getattr(x, 'zValue', lambda: 30)()) for x in scene.items()] or [30.0])
            except Exception:
                top_z = 90.0
            for i, tid in enumerate(ids):
                sid = str(tid)
                d = data_by_id.get(sid)
                if not isinstance(d, dict):
                    continue
                try:
                    if hasattr(self, '_is_renderable_text_data_item') and not self._is_renderable_text_data_item(d):
                        continue
                except Exception:
                    pass
                if sid in existing_ids:
                    try:
                        for obj in list(scene.items()):
                            if isinstance(obj, TypesettingItem) and str(getattr(obj, 'data', {}).get('id')) == sid:
                                if getattr(obj, 'data', None) is not d:
                                    obj.data = d
                                    rebound += 1
                                obj.setSelected(bool(selected))
                                obj.update()
                    except Exception:
                        pass
                    continue
                item = None
                try:
                    item = self._make_live_typesetting_item_for_current_scene(d, z_value=top_z + 1 + i, selected=bool(selected))
                except Exception:
                    item = None
                if item is not None:
                    created.append(sid)
                    existing_ids.add(sid)
                    try:
                        self.audit_boundary_event(
                            'TEXT_LIVE_ITEM_CREATE_DONE',
                            reason=str(reason or ''),
                            item_id=sid,
                            selected=bool(selected),
                            z_value=float(item.zValue()),
                            scene_rect=[round(item.sceneBoundingRect().x(), 2), round(item.sceneBoundingRect().y(), 2), round(item.sceneBoundingRect().width(), 2), round(item.sceneBoundingRect().height(), 2)],
                            preview=self._text_layer_diag_preview(d.get('translated_text'), 50),
                        )
                    except Exception:
                        pass
            try:
                self.audit_boundary_event(
                    'TEXT_LIVE_ITEMS_ADDED_AFTER_STRUCTURE_CHANGE',
                    reason=str(reason or ''),
                    created=','.join(str(x) for x in created),
                    requested=','.join(str(x) for x in ids),
                    rebound=rebound,
                    throttle_ms=100,
                )
            except Exception:
                pass
            try:
                self.force_update_final_scene_region()
            except Exception:
                try:
                    scene.update()
                except Exception:
                    pass
            return bool(created or rebound)
        finally:
            self._is_rebuilding_text_layer = old_rebuild
            if entered_guard:
                try:
                    if hasattr(self, '_release_text_scene_mutation_timer_guard'):
                        self._release_text_scene_mutation_timer_guard(reason=str(reason or 'text_add_live_items'))
                except Exception:
                    pass

    def _make_live_typesetting_item_for_current_scene(self, data_item, *, z_value=None, selected=False):
        """Create one live TypesettingItem in the current final-result scene without rebuilding the whole page."""
        if not isinstance(data_item, dict):
            return None
        scene = self._safe_graphics_scene() if hasattr(self, '_safe_graphics_scene') else getattr(getattr(self, 'view', None), 'scene', None)
        if scene is None:
            return None
        item = TypesettingItem(
            data_item,
            self.cb_font.currentFont().family() if hasattr(self, 'cb_font') else str(data_item.get('font_family') or 'Arial'),
            self.sb_font_size.value() if hasattr(self, 'sb_font_size') else int(data_item.get('font_size', 24) or 24),
            self.sb_strk.value() if hasattr(self, 'sb_strk') else int(data_item.get('stroke_width', 0) or 0),
            self.on_text_item_moved if hasattr(self, 'on_text_item_moved') else None,
            text_color=getattr(self, 'default_text_color', '#000000'),
            stroke_color=getattr(self, 'default_stroke_color', '#FFFFFF'),
            align=getattr(self, 'default_align', 'center'),
        )
        item.main_window = self
        try:
            if z_value is not None:
                item.setZValue(float(z_value))
            else:
                item.setZValue(90)
        except Exception:
            pass
        try:
            if hasattr(getattr(self, 'view', None), '_set_layer_tag'):
                self.view._set_layer_tag(item, 'movable_text')
        except Exception:
            pass
        try:
            scene.addItem(item)
            item.setSelected(bool(selected))
        except Exception:
            return None
        return item

    def _selected_or_source_text_data_for_drag_duplicate(self, source_item):
        src_data = getattr(source_item, 'data', None)
        if not isinstance(src_data, dict):
            return []
        try:
            selected = [d for d in self.selected_text_data_items() if isinstance(d, dict)]
        except Exception:
            selected = []
        src_id = str(src_data.get('id'))
        if not selected or all(str(d.get('id')) != src_id for d in selected):
            selected = [src_data]
        # Preserve page order and remove duplicates.
        seen = set()
        ordered = []
        curr = self.data.get(self.idx) or {}
        selected_ids = {str(d.get('id')) for d in selected}
        for d in curr.get('data', []) or []:
            sid = str(d.get('id'))
            if sid in selected_ids and sid not in seen:
                ordered.append(d)
                seen.add(sid)
        return ordered or [src_data]

    def begin_text_ctrl_drag_duplicate(self, source_item, scene_press_pos):
        """Ctrl+drag: duplicate selected text items and attach the copies to the mouse."""
        if getattr(self, '_app_is_closing', False) or getattr(self, '_closing_confirmed', False):
            return False
        try:
            if self.cb_mode.currentIndex() != 4:
                return False
        except Exception:
            return False
        curr = self.data.get(self.idx)
        if not curr:
            return False
        scene = self._safe_graphics_scene() if hasattr(self, '_safe_graphics_scene') else getattr(getattr(self, 'view', None), 'scene', None)
        if scene is None:
            return False
        sources = self._selected_or_source_text_data_for_drag_duplicate(source_item)
        sources = [d for d in sources if isinstance(d, dict)]
        if not sources:
            return False

        try:
            self.push_page_text_undo('텍스트 Ctrl 드래그 복제')
        except Exception:
            try:
                self.undo_text_checkpoint('텍스트 Ctrl 드래그 복제')
            except Exception:
                pass

        try:
            scene.clearSelection()
        except Exception:
            pass

        new_items = []
        new_ids = []
        next_id = self.next_text_id()
        try:
            top_z = max([float(getattr(x, 'zValue', lambda: 30)()) for x in scene.items()] or [30.0])
        except Exception:
            top_z = 90.0
        for i, src in enumerate(sources):
            try:
                d = copy.deepcopy(src)
            except Exception:
                d = dict(src)
            d['id'] = next_id
            next_id += 1
            for _runtime_key in (
                'pending_new_text', 'force_show', '_qt_item', '_scene_item',
                '_transform_mode', '_skew_mode', '_trapezoid_mode', '_arc_mode', 'arc_active_index',
            ):
                d.pop(_runtime_key, None)
            if 'manual_text_rect' not in d:
                d['manual_text_rect'] = True
            if 'text_anchor_mode' not in d:
                d['text_anchor_mode'] = 'text'
            curr.setdefault('data', []).append(d)
            item = self._make_live_typesetting_item_for_current_scene(d, z_value=top_z + 1 + i, selected=True)
            if item is None:
                try:
                    curr.setdefault('data', []).remove(d)
                except Exception:
                    pass
                continue
            new_items.append(item)
            new_ids.append(d.get('id'))

        if not new_items:
            return False

        press = QPointF(scene_press_pos)
        state = {
            'items': new_items,
            'ids': list(new_ids),
            'press_scene': press,
            'press_positions': [QPointF(item.pos()) for item in new_items],
        }
        self._text_ctrl_drag_duplicate_state = state
        try:
            self._text_item_drag_active = True
            self._text_item_drag_active_count = max(1, int(getattr(self, '_text_item_drag_active_count', 0) or 0) + 1)
            self._text_item_drag_active_id = ','.join(str(x) for x in new_ids)
        except Exception:
            pass
        try:
            self.audit_boundary_event('TEXT_CTRL_DRAG_DUPLICATE_BEGIN', ids=','.join(str(x) for x in new_ids), count=len(new_ids), throttle_ms=80)
        except Exception:
            pass
        return True

    def update_text_ctrl_drag_duplicate(self, scene_pos, *, axis_lock=False, vertical_only=False):
        state = getattr(self, '_text_ctrl_drag_duplicate_state', None)
        if not isinstance(state, dict):
            return False
        try:
            delta = QPointF(scene_pos) - QPointF(state.get('press_scene'))
            if axis_lock or vertical_only:
                # Shift+Ctrl drag uses axis lock: horizontal if X movement dominates, vertical if Y movement dominates.
                if abs(float(delta.x())) >= abs(float(delta.y())):
                    delta.setY(0.0)
                else:
                    delta.setX(0.0)
        except Exception:
            delta = QPointF(0, 0)
        for item, press_pos in zip(list(state.get('items') or []), list(state.get('press_positions') or [])):
            try:
                item.setPos(QPointF(press_pos) + delta)
                item.update()
            except RuntimeError:
                pass
            except Exception:
                pass
        return True

    def finish_text_ctrl_drag_duplicate(self, *, commit=True):
        state = getattr(self, '_text_ctrl_drag_duplicate_state', None)
        self._text_ctrl_drag_duplicate_state = None
        if not isinstance(state, dict):
            return False
        items = [x for x in (state.get('items') or []) if isinstance(x, TypesettingItem)]
        ids = [x for x in (state.get('ids') or []) if x is not None]
        if not commit:
            curr = self.data.get(self.idx) or {}
            for item in items:
                try:
                    if item.scene() is not None:
                        item.scene().removeItem(item)
                except Exception:
                    pass
                try:
                    curr.get('data', []).remove(item.data)
                except Exception:
                    pass
            return True
        for item in items:
            try:
                x_off, y_off = item.current_text_offsets_from_item_pos(item.pos())
                item.data['x_off'] = int(x_off)
                item.data['y_off'] = int(y_off)
                item.setSelected(True)
            except Exception:
                pass
        try:
            self._text_item_drag_active_count = max(0, int(getattr(self, '_text_item_drag_active_count', 0) or 0) - 1)
            if int(getattr(self, '_text_item_drag_active_count', 0) or 0) <= 0:
                self._text_item_drag_active = False
                self._text_item_drag_active_id = None
        except Exception:
            pass
        try:
            self.schedule_text_table_refresh_after_structure_change(ids, delay_ms=0, reason='텍스트 Ctrl 드래그 복제')
        except Exception:
            pass
        try:
            self.finalize_text_change(ids=ids, fields=['data', 'x_off', 'y_off'], reason='텍스트 Ctrl 드래그 복제', delay_ms=1500, update_table=False, refresh_scene=False)
        except Exception:
            try:
                self.schedule_deferred_auto_save_project(1500)
            except Exception:
                pass
        try:
            QTimer.singleShot(30, lambda ids=list(ids): self.reselect_text_items(ids))
        except Exception:
            pass
        try:
            self.audit_boundary_event('TEXT_CTRL_DRAG_DUPLICATE_DONE', ids=','.join(str(x) for x in ids), count=len(ids), throttle_ms=80)
        except Exception:
            pass
        self.log(f"📋 Ctrl 드래그 복제 완료: {len(ids)}개")
        return True

    def nudge_selected_text_items(self, dx=0, dy=0):
        """Move selected text items by keyboard arrows in page coordinates."""
        try:
            if self.cb_mode.currentIndex() != 4:
                return False
        except Exception:
            return False
        data_items = [d for d in self.selected_text_data_items() if isinstance(d, dict)]
        if not data_items:
            return False
        try:
            dx = int(dx)
            dy = int(dy)
        except Exception:
            return False
        if dx == 0 and dy == 0:
            return False
        ids = [d.get('id') for d in data_items if d.get('id') is not None]
        if not ids:
            return False

        # 방향키 이동이 시작된 순간, CAD 선택 사각형/자유형 미리보기나
        # 우측 표의 '전체 선택' 행 같은 임시 선택 영역은 더 이상 유효하지 않다.
        # 실제 이동 대상인 텍스트 선택은 유지하되, 선택 과정에서 남은 영역 표시만 끊는다.
        try:
            view = getattr(self, 'view', None)
            if view is not None:
                if hasattr(view, 'cancel_cad_text_selection_interaction'):
                    view.cancel_cad_text_selection_interaction(clear_preview=True)
                if hasattr(view, 'clear_cad_text_selection_undo_stack'):
                    view.clear_cad_text_selection_undo_stack()
        except Exception:
            pass
        try:
            tab = getattr(self, 'tab', None)
            if tab is not None:
                sm = tab.selectionModel()
                if sm is not None:
                    # row 0은 실제 텍스트가 아니라 '전체 선택' 헤더/가상 행이다.
                    # 방향키로 실제 텍스트를 이동하는 순간에는 이 행 선택을 제거하고
                    # 아래에서 이동 대상 텍스트 행만 다시 선택한다.
                    try:
                        model = tab.model()
                        if tab.rowCount() > 0 and tab.columnCount() > 0:
                            top = model.index(0, 0)
                            bottom = model.index(0, tab.columnCount() - 1)
                            sm.select(QItemSelection(top, bottom),
                                      QItemSelectionModel.SelectionFlag.Deselect | QItemSelectionModel.SelectionFlag.Rows)
                    except Exception:
                        pass
        except Exception:
            pass

        try:
            self.push_page_text_undo('텍스트 방향키 이동')
        except Exception:
            try:
                self.undo_text_checkpoint('텍스트 방향키 이동')
            except Exception:
                pass
        for d in data_items:
            try:
                d['x_off'] = int(round(float(d.get('x_off', 0) or 0))) + dx
                d['y_off'] = int(round(float(d.get('y_off', 0) or 0))) + dy
            except Exception:
                d['x_off'] = int(dx)
                d['y_off'] = int(dy)
        # Move live selected scene items immediately.  No full scene rebuild is needed.
        idset = {str(x) for x in ids}
        try:
            for item in self.selected_text_items():
                if str(getattr(item, 'data', {}).get('id')) in idset:
                    item.setPos(QPointF(item.pos().x() + dx, item.pos().y() + dy))
                    item.update()
        except Exception:
            pass
        try:
            if hasattr(self, 'select_table_rows_by_ids'):
                self.select_table_rows_by_ids(ids)
        except Exception:
            pass
        try:
            self.finalize_text_change(ids=ids, fields=['x_off', 'y_off'], reason='텍스트 방향키 이동', delay_ms=900, update_table=True, refresh_scene=False)
        except Exception:
            try:
                self.schedule_deferred_auto_save_project(900)
            except Exception:
                pass
        try:
            self.audit_boundary_event('TEXT_KEYBOARD_NUDGE', ids=','.join(str(x) for x in ids), dx=dx, dy=dy, count=len(ids), throttle_ms=80)
        except Exception:
            pass
        return True

    def paste_text_clipboard_at(self, scene_pos=None):
        curr = self.data.get(self.idx)
        if not curr:
            return False
        if not self.text_clipboard:
            self.log("⚠️ 붙여넣을 텍스트가 없습니다.")
            return False

        if scene_pos is None:
            scene_pos = self.current_scene_cursor_pos()
        try:
            px, py = float(scene_pos.x()), float(scene_pos.y())
        except Exception:
            px, py = 0.0, 0.0

        src_items = [copy.deepcopy(d) for d in self.text_clipboard]
        base_x, base_y = self.text_clipboard_visible_anchor(src_items)
        # 커서가 텍스트를 가리지 않도록 커서의 위쪽 끝단을 텍스트 묶음의 우측 하단에 맞춘다.
        px, py = self.text_clipboard_paste_origin_from_cursor(src_items, scene_pos)

        # 2.4.1 안정 경로 복원: 붙여넣기는 item 개수가 바뀌는 구조 변경이므로
        # Command/Checkpoint 경로가 아니라 page text snapshot Undo로 잡는다.
        self.push_page_text_undo('텍스트 붙여넣기')

        new_ids = []
        next_id = self.next_text_id()
        for i, d in enumerate(src_items):
            rect = list(d.get('rect') or [0, 0, 260, 80])
            while len(rect) < 4:
                rect.append(1)
            try:
                old_x = float(rect[0]) + float(d.get('x_off', 0) or 0)
                old_y = float(rect[1]) + float(d.get('y_off', 0) or 0)
                dx = old_x - base_x
                dy = old_y - base_y
                rect[0] = int(round(px + dx))
                rect[1] = int(round(py + dy))
            except Exception:
                rect[0] = int(round(px))
                rect[1] = int(round(py))

            d['id'] = next_id
            next_id += 1
            d['rect'] = [int(rect[0]), int(rect[1]), max(1, int(rect[2])), max(1, int(rect[3]))]
            d['x_off'] = 0
            d['y_off'] = 0
            d['manual_text_rect'] = True
            d['text_anchor_mode'] = 'text'
            d['use_inpaint'] = True
            # Windows/일반 클립보드 텍스트는 복사 원본 스타일이 없으므로
            # 붙여넣기 확정 시점의 현재 UI 텍스트 설정을 다시 입힌다.
            # 미리보기 생성 후 사용자가 폰트/행간/자간을 바꾼 경우까지 따라가기 위함이다.
            if bool(getattr(self, 'text_clipboard_is_plain', False)):
                try:
                    if hasattr(self, 'apply_style_dict_to_data_items'):
                        self.apply_style_dict_to_data_items([d], self.current_style_snapshot())
                except Exception:
                    pass
            self._strip_text_clipboard_runtime_keys(d)
            new_ids.append(d['id'])
            curr.setdefault('data', []).append(d)

        # 붙여넣기 직후에는 data와 scene 개수가 달라진다.
        # 이때 전체 mode_chg(4)로 scene을 갈아엎으면 Qt가 아직 잡고 있는 마우스/선택 item 참조와
        # 충돌해 access violation이 날 수 있다. 새로 추가된 텍스트 item만 live scene에 붙인다.
        try:
            live_added = False
            if self.cb_mode.currentIndex() == 4:
                live_added = bool(self._add_live_text_items_for_ids(new_ids, selected=True, reason='텍스트 붙여넣기'))
                if not live_added:
                    self.schedule_final_text_scene_refresh(120)
                    try:
                        QTimer.singleShot(180, lambda ids=list(new_ids): self.reselect_text_items(ids))
                    except Exception:
                        pass
            self.schedule_text_table_refresh_after_structure_change(new_ids, delay_ms=30, reason='텍스트 붙여넣기')
            self.finalize_text_change(ids=new_ids, fields=['data'], reason='텍스트 붙여넣기', delay_ms=1800)
        except Exception:
            self.auto_save_project()
        self.log(f"📋 텍스트 붙여넣기 완료: {len(new_ids)}개")
        return True

    def paste_text_clipboard_same_position(self):
        """Ctrl+Shift+V: 복사한 텍스트를 현재 페이지의 같은 이미지 좌표에 붙여넣는다."""
        if self.cb_mode.currentIndex() != 4:
            return False
        curr = self.data.get(self.idx)
        if not curr:
            return False
        if not self.text_clipboard or bool(getattr(self, "text_clipboard_is_plain", False)):
            self.log("⚠️ 원위치 붙여넣기는 최종결과 탭에서 복사한 텍스트만 사용할 수 있습니다.")
            return False

        src_items = [copy.deepcopy(d) for d in self.text_clipboard if isinstance(d, dict)]
        if not src_items:
            self.log("⚠️ 붙여넣을 텍스트가 없습니다.")
            return False

        # 2.4.1 안정 경로 복원: 원위치 붙여넣기도 구조 변경이므로 page text snapshot Undo로 잡는다.
        self.push_page_text_undo('텍스트 원위치 붙여넣기')

        new_ids = []
        next_id = self.next_text_id()
        for d in src_items:
            rect = list(d.get('rect') or [0, 0, 260, 80])
            while len(rect) < 4:
                rect.append(1)
            try:
                rect = [int(round(float(rect[0]))), int(round(float(rect[1]))), max(1, int(round(float(rect[2])))), max(1, int(round(float(rect[3]))))]
            except Exception:
                rect = [0, 0, 260, 80]

            d['id'] = next_id
            next_id += 1
            d['rect'] = rect
            # 원위치 붙여넣기는 복사 당시의 페이지 내부 좌표/오프셋/변형값을 그대로 보존한다.
            # 단, 임시 선택/생성 플래그와 기존 item 참조성 상태는 새 텍스트에 가져가지 않는다.
            self._strip_text_clipboard_runtime_keys(d)
            if 'manual_text_rect' not in d:
                d['manual_text_rect'] = True
            if 'text_anchor_mode' not in d:
                d['text_anchor_mode'] = 'text'
            new_ids.append(d['id'])
            curr.setdefault('data', []).append(d)

        # 원위치 붙여넣기도 전체 scene 재구성 대신 새 텍스트 item만 추가한다.
        try:
            live_added = False
            if self.cb_mode.currentIndex() == 4:
                live_added = bool(self._add_live_text_items_for_ids(new_ids, selected=True, reason='텍스트 원위치 붙여넣기'))
                if not live_added:
                    self.schedule_final_text_scene_refresh(120)
                    try:
                        QTimer.singleShot(180, lambda ids=list(new_ids): self.reselect_text_items(ids))
                    except Exception:
                        pass
            self.schedule_text_table_refresh_after_structure_change(new_ids, delay_ms=30, reason='텍스트 원위치 붙여넣기')
            self.finalize_text_change(ids=new_ids, fields=['data'], reason='텍스트 원위치 붙여넣기', delay_ms=1800)
        except Exception:
            try:
                self.schedule_deferred_auto_save_project(1800)
            except Exception:
                self.auto_save_project()
        self.log(f"📋 원위치 붙여넣기 완료: {len(new_ids)}개")
        return True

    def windows_clipboard_text(self):
        try:
            text = QApplication.clipboard().text()
        except Exception:
            text = ""
        return str(text or "")

    def make_text_clipboard_item_from_plain_text(self, text):
        text = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            return None
        line_count = max(1, text.count("\n") + 1)
        try:
            style = self.current_style_snapshot() if hasattr(self, 'current_style_snapshot') else {}
        except Exception:
            style = {}
        try:
            style = self.normalize_style_dict(style) if hasattr(self, 'normalize_style_dict') else dict(style or {})
        except Exception:
            style = dict(style or {})
        try:
            font_size = int(style.get('font_size') or self.sb_font_size.value())
        except Exception:
            font_size = 24
        w = 320
        h = max(70, int(font_size * (line_count + 1.4)))
        item = {
            'id': 0,
            'text': text,
            'translated_text': text,
            'rect': [0, 0, w, h],
            'use_inpaint': True,
            'x_off': 0,
            'y_off': 0,
            'manual_text_rect': True,
            'text_anchor_mode': 'text',
            'force_show': True,
        }
        try:
            if hasattr(self, 'apply_style_dict_to_data_items'):
                self.apply_style_dict_to_data_items([item], style)
            else:
                item.update({
                    'font_family': style.get('font_family') or (self.cb_font.currentFont().family() if hasattr(self, 'cb_font') else 'Arial'),
                    'font_size': font_size,
                    'stroke_width': int(style.get('stroke_width', self.sb_strk.value() if hasattr(self, 'sb_strk') else 0) or 0),
                    'text_color': str(style.get('text_color') or getattr(self, 'default_text_color', '#000000') or '#000000'),
                    'stroke_color': str(style.get('stroke_color') or getattr(self, 'default_stroke_color', '#FFFFFF') or '#FFFFFF'),
                    'align': style.get('align') or getattr(self, 'default_align', 'center'),
                })
        except Exception:
            item.update({
                'font_family': self.cb_font.currentFont().family() if hasattr(self, 'cb_font') else 'Arial',
                'font_size': font_size,
                'stroke_width': int(self.sb_strk.value()) if hasattr(self, 'sb_strk') else 0,
                'text_color': str(getattr(self, 'default_text_color', '#000000') or '#000000'),
                'stroke_color': str(getattr(self, 'default_stroke_color', '#FFFFFF') or '#FFFFFF'),
                'align': getattr(self, 'default_align', 'center'),
            })
        try:
            self.audit_boundary_event(
                'TEXT_PLAIN_CLIPBOARD_STYLE_APPLIED',
                font_family=str(item.get('font_family', '')),
                font_size=item.get('font_size'),
                stroke_width=item.get('stroke_width'),
                writing_direction=item.get('writing_direction'),
                line_spacing=item.get('line_spacing'),
                letter_spacing=item.get('letter_spacing'),
                char_width=item.get('char_width'),
                char_height=item.get('char_height'),
                text_len=len(text),
                throttle_ms=80,
            )
        except Exception:
            pass
        return item

    def load_plain_text_clipboard_for_paste(self):
        text = self.windows_clipboard_text()
        item = self.make_text_clipboard_item_from_plain_text(text)
        if not item:
            return False
        self.text_clipboard = [item]
        self.text_clipboard_is_plain = True
        self.text_paste_pending = False
        try:
            if getattr(self, 'view', None) is not None and hasattr(self.view, 'clear_paste_preview'):
                self.view.clear_paste_preview()
        except Exception:
            pass
        return True

    def has_available_text_paste_source(self):
        """Return True when either a YSB text-object clipboard or OS text clipboard can be pasted."""
        try:
            if self.text_clipboard:
                return True
        except Exception:
            pass
        try:
            mime = QApplication.clipboard().mimeData()
            if mime is not None and mime.hasFormat(self._text_object_clipboard_mime_type()):
                return True
        except Exception:
            pass
        try:
            return bool(str(QApplication.clipboard().text() or '').strip())
        except Exception:
            return False

    def ensure_text_clipboard_for_paste(self, refresh_plain=False):
        """Prepare internal paste buffer without forcing callers to know clipboard kind.

        Priority is important:
        1) an internal YSB text-object copy must never be overwritten by the plain
           text mirror that we also put on the OS clipboard;
        2) a YSB custom MIME object on the OS clipboard is restored before plain text;
        3) only then do we convert ordinary OS text into a new YSB text box.
        """
        try:
            if self.text_clipboard and not bool(getattr(self, 'text_clipboard_is_plain', False)):
                return True
        except Exception:
            pass
        try:
            if self.load_text_object_clipboard_from_os():
                return True
        except Exception:
            pass
        try:
            if refresh_plain or not self.text_clipboard or bool(getattr(self, 'text_clipboard_is_plain', False)):
                if self.load_plain_text_clipboard_for_paste():
                    return True
        except Exception:
            pass
        return bool(getattr(self, 'text_clipboard', None))

    def paste_text_clipboard_at_or_load_plain(self, scene_pos=None, refresh_plain=False):
        if not self.ensure_text_clipboard_for_paste(refresh_plain=refresh_plain):
            self.log("⚠️ 붙여넣을 텍스트가 없습니다.")
            return False
        return self.paste_text_clipboard_at(scene_pos)

    def enter_text_paste_mode(self):
        """Ctrl+V는 즉시 붙여넣지 않고, 커서에 미리보기만 붙인 뒤 클릭 위치에 확정한다."""
        if self.cb_mode.currentIndex() != 4:
            return False
        # Ctrl+V는 일반 클립보드 텍스트를 쓸 때마다 최신 내용으로 갱신한다.
        # YSB 텍스트박스 복사본이 있을 때는 그 복사본을 유지한다.
        if not self.ensure_text_clipboard_for_paste(refresh_plain=bool(getattr(self, "text_clipboard_is_plain", False))):
            self.log("⚠️ 붙여넣을 텍스트가 없습니다.")
            return False

        self.text_paste_pending = True
        self.set_tool("paste_text")
        try:
            self.view.show_paste_preview(self.text_clipboard, self.current_scene_cursor_pos())
        except Exception:
            pass
        self.log("📋 붙여넣기 위치 지정: 마우스를 움직인 뒤 클릭하면 붙여넣습니다. ESC로 취소.")
        return True

    def finish_text_paste_at(self, scene_pos):
        if not self.text_paste_pending:
            return False

        self.text_paste_pending = False
        try:
            self.view.clear_paste_preview()
        except Exception:
            pass

        ok = self.paste_text_clipboard_at(scene_pos)
        self.set_tool(None)
        return ok

    def _selected_or_context_text_data_items(self, context_data_item=None):
        items = self.selected_text_data_items() if hasattr(self, "selected_text_data_items") else []
        if context_data_item is not None and not items:
            items = [context_data_item]
        if context_data_item is not None and str(context_data_item.get('id')) not in {str(d.get('id')) for d in items}:
            # 캔버스 우클릭은 해당 항목 하나만 다루는 것이 안전하다.
            items = [context_data_item]
        return [d for d in items if isinstance(d, dict)]

    def open_text_advanced_effect_dialog(self, data_items=None):
        data_items = [d for d in (data_items or self.selected_text_data_items()) if isinstance(d, dict)]
        data_items = [d for d in data_items if not d.get('rasterized_text')]
        if not data_items:
            self.log("⚠️ " + self.tr_ui("효과를 적용할 편집 가능한 텍스트가 없습니다."))
            return False
        try:
            if hasattr(self, "flush_text_scene_geometry_to_data"):
                self.flush_text_scene_geometry_to_data(data_items, mark_dirty=False, reason="before advanced text options")
        except Exception:
            pass

        effect_fields = [
            "text_gradient_enabled", "text_gradient_color1", "text_gradient_color2", "text_gradient_angle", "text_gradient_ratio",
            "stroke_gradient_enabled", "stroke_gradient_color1", "stroke_gradient_color2", "stroke_gradient_angle", "stroke_gradient_ratio",
            "double_stroke_enabled", "double_stroke_color", "double_stroke_width",
            "text_shadow_enabled", "text_shadow_color", "text_shadow_opacity", "text_shadow_offset_x", "text_shadow_offset_y", "text_shadow_blur",
            "text_glow_enabled", "text_glow_color", "text_glow_opacity", "text_glow_offset_x", "text_glow_offset_y", "text_glow_size", "text_glow_blur",
        ]
        selected_ids = [d.get('id') for d in data_items]
        original_values = []
        for d in data_items:
            original_values.append({k: copy.deepcopy(d.get(k)) for k in effect_fields})

        def apply_values_to_items(values, *, refresh_scene=True):
            if not isinstance(values, dict):
                return
            for d in data_items:
                for k in effect_fields:
                    if k in values:
                        d[k] = values[k]
            if refresh_scene and self.cb_mode.currentIndex() == 4:
                try:
                    live_ok = False
                    try:
                        if hasattr(self, "refresh_text_items_live_in_place"):
                            live_ok = bool(self.refresh_text_items_live_in_place(self.selected_text_items(), keep_selection=True))
                    except Exception:
                        live_ok = False
                    if not live_ok and not self.refresh_final_text_items_by_ids(selected_ids):
                        self.schedule_final_text_scene_refresh(80)
                    self.reselect_text_items(selected_ids)
                except Exception:
                    self.schedule_final_text_scene_refresh(80)

        def restore_originals(*, refresh_scene=True):
            for d, orig in zip(data_items, original_values):
                for k in effect_fields:
                    if orig.get(k) is None:
                        d.pop(k, None)
                    else:
                        d[k] = copy.deepcopy(orig.get(k))
            if refresh_scene and self.cb_mode.currentIndex() == 4:
                try:
                    live_ok = False
                    try:
                        if hasattr(self, "refresh_text_items_live_in_place"):
                            live_ok = bool(self.refresh_text_items_live_in_place(self.selected_text_items(), keep_selection=True))
                    except Exception:
                        live_ok = False
                    if not live_ok and not self.refresh_final_text_items_by_ids(selected_ids):
                        self.schedule_final_text_scene_refresh(80)
                    self.reselect_text_items(selected_ids)
                except Exception:
                    self.schedule_final_text_scene_refresh(80)

        dlg = TextAdvancedEffectDialog(data_items[0], self)
        try:
            dlg.previewChanged.connect(lambda values: apply_values_to_items(values, refresh_scene=True))
        except Exception:
            pass

        result = dlg.exec()
        final_values = dlg.values()
        if result != QDialog.DialogCode.Accepted:
            restore_originals(refresh_scene=True)
            return False

        # 미리보기 중 data가 이미 바뀌었으므로, Undo 기준점은 원본 상태로 잠깐 돌린 뒤 잡는다.
        restore_originals(refresh_scene=False)
        self.append_text_engine_diff_for_items('고급 텍스트/획 옵션 변경', data_items, fields=list(final_values.keys()))
        apply_values_to_items(final_values, refresh_scene=False)
        for d in data_items:
            try:
                if bool(d.get('manual_text_rect')) or str(d.get('text_anchor_mode') or '').lower() == 'text':
                    self.shrink_text_rect_to_content(d)
            except Exception:
                pass
        try:
            self.finalize_text_change(
                ids=selected_ids,
                items=data_items,
                fields=list(final_values.keys()),
                reason='고급 텍스트/획 옵션 변경',
                delay_ms=1800,
            )
            self.reselect_text_items(selected_ids)
        except Exception:
            try:
                self.schedule_final_text_scene_refresh(80)
                self.schedule_deferred_auto_save_project(1800)
            except Exception:
                pass
        self.log(f"🎨 고급 텍스트/획 옵션 적용: {len(data_items)}개")
        return True

    def _qimage_to_png_base64(self, image):
        if image is None or image.isNull():
            return ""
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buf, "PNG")
        buf.close()
        return bytes(ba.toBase64()).decode("ascii")

    def _qimage_from_png_base64(self, value):
        if not value:
            return QImage()
        try:
            raw = base64.b64decode(str(value).encode("ascii"), validate=False)
            img = QImage()
            img.loadFromData(raw, "PNG")
            return img.convertToFormat(QImage.Format.Format_ARGB32)
        except Exception:
            return QImage()

    def render_text_data_item_to_raster_png(self, data_item):
        if not data_item or data_item.get('rasterized_text'):
            return None
        temp_data = copy.deepcopy(data_item)
        temp_data.pop('_transform_mode', None)
        temp_data.pop('_skew_mode', None)
        scene = QGraphicsScene()
        item = TypesettingItem(
            temp_data,
            self.cb_font.currentFont().family(),
            self.sb_font_size.value(),
            self.sb_strk.value(),
            None,
            text_color=self.default_text_color,
            stroke_color=self.default_stroke_color,
            align=self.default_align,
        )
        item.suppress_guides = True
        item.setSelected(False)
        scene.addItem(item)
        scene_rect = item.sceneBoundingRect().adjusted(-4, -4, 4, 4)
        if scene_rect.isNull() or scene_rect.width() <= 0 or scene_rect.height() <= 0:
            return None
        w = max(1, int(math.ceil(scene_rect.width())))
        h = max(1, int(math.ceil(scene_rect.height())))
        if w > 12000 or h > 12000:
            self.log("⚠️ 객체화할 텍스트가 너무 큽니다.")
            return None
        scene.setSceneRect(scene_rect)
        image = QImage(w, h, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            scene.render(painter, QRectF(0, 0, w, h), scene_rect)
        finally:
            painter.end()
            scene.clear()
        return {
            "png": self._qimage_to_png_base64(image),
            "rect": [int(round(scene_rect.left())), int(round(scene_rect.top())), w, h],
            "width": w,
            "height": h,
        }

    def convert_text_data_items_to_raster_objects(self, data_items=None):
        try:
            self.sync_final_text_scene_to_data()
        except Exception:
            pass
        data_items = [d for d in (data_items or self.selected_text_data_items()) if isinstance(d, dict)]
        data_items = [d for d in data_items if not d.get('rasterized_text')]
        if not data_items:
            self.log("⚠️ " + self.tr_ui("객체로 변환할 일반 텍스트가 없습니다."))
            return False
        if QMessageBox.question(
            self,
            "텍스트를 객체로 변환",
            "선택한 텍스트를 이미지 객체로 변환합니다.\n변환 후에는 텍스트 내용을 직접 수정할 수 없습니다.\n계속할까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return False
        selected_ids = [d.get('id') for d in data_items]
        self.undo_text_checkpoint('텍스트 객체 변환')
        converted = 0
        for d in data_items:
            payload = self.render_text_data_item_to_raster_png(d)
            if not payload or not payload.get('png'):
                continue
            d['rasterized_text'] = True
            d['raster_png'] = payload['png']
            d['raster_w'] = payload['width']
            d['raster_h'] = payload['height']
            d['rect'] = payload['rect']
            d['x_off'] = 0
            d['y_off'] = 0
            d['rotation'] = 0
            d['manual_text_rect'] = True
            d['text_anchor_mode'] = 'raster'
            d.pop('_transform_mode', None)
            d.pop('_skew_mode', None)
            d.pop('_trapezoid_mode', None)
            d.pop('_arc_mode', None)
            d['object_source_text'] = self.strip_object_display_prefix_for_data(d.get('translated_text') or '')
            converted += 1
        if not converted:
            self.log("⚠️ 객체 변환에 실패했습니다.")
            return False
        try:
            if self.cb_mode.currentIndex() == 4:
                self.schedule_final_text_scene_refresh(80)
                self.reselect_text_items(selected_ids)
            self.finalize_text_change(ids=selected_ids, fields=['rasterized_text', 'raster_png'], reason='텍스트 객체 변환', delay_ms=1800)
        except Exception:
            self.auto_save_project()
        self.log(f"🧱 텍스트 객체 변환 완료: {converted}개")
        return True

    def begin_raster_text_erase_mode(self, data_items=None):
        data_items = [d for d in (data_items or self.selected_text_data_items()) if isinstance(d, dict) and d.get('rasterized_text')]
        if not data_items:
            self.log("⚠️ " + self.tr_ui("일부 지우기는 객체로 변환된 텍스트에서만 사용할 수 있습니다."))
            return False
        self.raster_erase_target_ids = [d.get('id') for d in data_items]
        self.set_tool('raster_erase')
        self.log(f"🧽 객체 일부 지우기: 지울 영역을 사각형으로 드래그하세요. 대상 {len(data_items)}개")
        return True

    def apply_raster_text_erase_rect(self, scene_rect):
        scene_rect = QRectF(scene_rect).normalized()
        if scene_rect.width() < 1 or scene_rect.height() < 1:
            self.log("↩️ 객체 지우기 취소: 영역이 너무 작습니다.")
            return False
        target_ids = {str(x) for x in getattr(self, 'raster_erase_target_ids', []) or []}
        curr = self.data.get(self.idx)
        if not curr:
            return False
        targets = []
        for d in curr.get('data', []) or []:
            if not d.get('rasterized_text'):
                continue
            if target_ids and str(d.get('id')) not in target_ids:
                continue
            targets.append(d)
        if not targets:
            self.log("⚠️ 지울 수 있는 텍스트 객체가 없습니다.")
            return False

        self.undo_text_checkpoint('텍스트 객체 일부 지우기')
        changed_ids = []
        for d in targets:
            img = self._qimage_from_png_base64(d.get('raster_png'))
            if img.isNull():
                continue
            rect = list(d.get('rect') or [0, 0, img.width(), img.height()])
            while len(rect) < 4:
                rect.append(1)
            obj_rect = QRectF(
                float(rect[0]) + float(d.get('x_off', 0) or 0),
                float(rect[1]) + float(d.get('y_off', 0) or 0),
                max(1.0, float(rect[2])),
                max(1.0, float(rect[3])),
            )
            inter = scene_rect.intersected(obj_rect)
            if inter.isNull() or inter.width() <= 0 or inter.height() <= 0:
                continue
            local = QRectF(inter.left() - obj_rect.left(), inter.top() - obj_rect.top(), inter.width(), inter.height())
            p = QPainter(img)
            try:
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
                p.fillRect(local, Qt.GlobalColor.transparent)
            finally:
                p.end()
            d['raster_png'] = self._qimage_to_png_base64(img)
            d['raster_w'] = img.width()
            d['raster_h'] = img.height()
            changed_ids.append(d.get('id'))
        if not changed_ids:
            self.log("↩️ 객체 지우기 취소: 선택한 영역이 객체와 겹치지 않습니다.")
            return False
        try:
            if self.cb_mode.currentIndex() == 4:
                self.schedule_final_text_scene_refresh(80)
                self.reselect_text_items(changed_ids)
            self.finalize_text_change(ids=changed_ids, fields=['raster_png'], reason='텍스트 객체 일부 지우기', delay_ms=1800)
        except Exception:
            self.auto_save_project()
        self.log(f"🧽 텍스트 객체 일부 지우기 완료: {len(changed_ids)}개")
        return True


    def _final_text_enable_toggle_label(self, data_items):
        data_items = [d for d in (data_items or []) if isinstance(d, dict)]
        if not data_items:
            base = self.tr_ui("텍스트 비활성화")
        else:
            states = [bool(d.get('use_inpaint', True)) for d in data_items]
            if states and all(states):
                base = self.tr_ui("텍스트 비활성화")
            elif states and not any(states):
                base = self.tr_ui("텍스트 활성화")
            else:
                base = self.tr_ui("텍스트 활성/비활성 전환")
        return base

    def configure_text_context_shortcut_action(self, action, shortcut_key, tooltip=None):
        """Attach the currently configured shortcut to a text context-menu action.

        The context menu must show the same shortcut the actual command uses.
        Do not append hard-coded shortcut text to labels; let QAction render the
        current ShortcutSettings sequence so user changes/disabled shortcuts are
        reflected automatically.
        """
        if action is None or not shortcut_key:
            return
        try:
            seq = None
            if hasattr(self, 'shortcut_settings'):
                seq = self.shortcut_settings.seq(str(shortcut_key))
            if seq is not None and not seq.isEmpty():
                action.setShortcut(seq)
                try:
                    action.setShortcutVisibleInContextMenu(True)
                except Exception:
                    pass
            else:
                try:
                    action.setShortcut(QKeySequence())
                except Exception:
                    pass
        except Exception:
            pass
        if tooltip:
            try:
                action.setToolTip(self.tr_ui(str(tooltip)))
            except Exception:
                pass

    def configure_final_text_enable_toggle_action(self, action):
        if action is None:
            return
        self.configure_text_context_shortcut_action(
            action,
            "text_disable_toggle",
            "선택한 텍스트를 최종 화면과 출력 대상에서 제외하거나 다시 포함합니다.",
        )

    def toggle_selected_final_text_enabled(self, data_items=None, force_state=None, announce=True):
        """최종화면에서 선택 텍스트의 use_inpaint를 토글한다.

        분석도 박스 클릭/우측 체크박스와 같은 use_inpaint 값을 사용한다.
        Ctrl+U는 캔버스 선택 텍스트뿐 아니라 우측 텍스트 행 선택도 대상으로 삼는다.
        """
        try:
            if self.cb_mode.currentIndex() != 4:
                return False
        except Exception:
            return False

        curr = self.data.get(self.idx) if isinstance(getattr(self, 'data', None), dict) else None
        if not curr or 'data' not in curr:
            return False

        if data_items is None:
            try:
                data_items = self.selected_text_data_items()
            except Exception:
                data_items = []
        data_items = [d for d in (data_items or []) if isinstance(d, dict)]
        if not data_items:
            try:
                self.log("⚠️ " + self.tr_ui("토글할 텍스트가 선택되어 있지 않습니다."))
            except Exception:
                pass
            return False

        # 현재 페이지 data에 실제로 들어 있는 항목만 대상으로 삼는다.
        curr_items = list(curr.get('data', []) or [])
        wanted_ids = {str(d.get('id')) for d in data_items if d.get('id') is not None}
        targets = [d for d in curr_items if str(d.get('id')) in wanted_ids]
        if not targets:
            return False

        if force_state is None:
            # 모두 켜져 있으면 끄고, 하나라도 꺼져 있으면 다시 켠다.
            new_state = not all(bool(d.get('use_inpaint', True)) for d in targets)
        else:
            new_state = bool(force_state)

        changed = [d for d in targets if bool(d.get('use_inpaint', True)) != bool(new_state)]
        if not changed:
            return True

        ids = [d.get('id') for d in changed if d.get('id') is not None]
        try:
            self.undo_push_text_line('텍스트 활성/비활성 변경')
        except Exception:
            pass

        old_lock = bool(getattr(self, '_table_check_lock', False))
        try:
            self._table_check_lock = True
            if hasattr(self, 'tab') and self.tab is not None:
                try:
                    self.tab.blockSignals(True)
                except Exception:
                    pass
            for d in changed:
                d['use_inpaint'] = bool(new_state)
                try:
                    row = curr_items.index(d) + 1
                except Exception:
                    row = -1
                if row > 0 and hasattr(self, 'set_table_check_state'):
                    try:
                        self.set_table_check_state(row, bool(new_state))
                        self.set_table_row_visual(row, bool(new_state))
                    except Exception:
                        pass
            try:
                all_checked = len(curr_items) > 0 and all(x.get('use_inpaint', True) for x in curr_items)
                self.set_table_check_state(0, all_checked)
                self.paint_all_row_header()
            except Exception:
                pass
        finally:
            if hasattr(self, 'tab') and self.tab is not None:
                try:
                    self.tab.blockSignals(False)
                except Exception:
                    pass
            self._table_check_lock = old_lock

        try:
            if bool(new_state):
                # 다시 켤 때는 hidden item이 남아 있지 않을 수 있으므로 필요한 ID만 재생성한다.
                refreshed = False
                try:
                    refreshed = bool(self.refresh_final_text_items_by_ids(ids))
                except Exception:
                    refreshed = False
                if not refreshed:
                    try:
                        self.schedule_final_text_scene_refresh(60)
                    except Exception:
                        pass
                try:
                    self.reselect_text_items(ids)
                except Exception:
                    pass
            else:
                # 끌 때는 전체 재구성 없이 기존 최종 텍스트 item을 즉시 숨긴다.
                self.sync_final_text_visibility_only()
                try:
                    self.select_table_rows_by_ids(ids)
                except Exception:
                    pass
        except Exception:
            pass

        try:
            self.mark_active_page_dirty('text')
        except Exception:
            pass
        try:
            self.schedule_deferred_auto_save_project()
        except Exception:
            try:
                self.auto_save_project()
            except Exception:
                pass

        if announce:
            try:
                if bool(new_state):
                    self.log(f"🔄 {self.tr_ui('텍스트 활성화')}: {len(changed)}개")
                else:
                    self.log(f"🔄 {self.tr_ui('텍스트 비활성화')}: {len(changed)}개")
            except Exception:
                pass
        return True

    def show_final_text_context_menu(self, text_item, global_pos, scene_pos=None):
        if self.cb_mode.currentIndex() != 4 or text_item is None:
            return
        self.last_canvas_context_pos = scene_pos
        # 이미 여러 텍스트가 선택된 상태에서 그중 하나를 우클릭하면
        # 다중 선택을 유지한다. 선택 밖 항목을 우클릭할 때만 해당 항목 하나로 전환한다.
        try:
            selected_scene_items = [x for x in self._safe_graphics_scene().selectedItems() if isinstance(x, TypesettingItem)]
        except Exception:
            selected_scene_items = []
        if text_item not in selected_scene_items:
            self.select_text_item_and_row(text_item)
        else:
            self.on_scene_selection_changed()

        data_items = self._selected_or_context_text_data_items(text_item.data)
        raster_items = [d for d in data_items if d.get('rasterized_text')]
        editable_text_items = [d for d in data_items if not d.get('rasterized_text')]

        menu = QMenu(self)
        act_copy = menu.addAction(self.tr_ui("텍스트 복사"))
        self.configure_text_context_shortcut_action(act_copy, "text_copy")
        act_paste = menu.addAction(self.tr_ui("텍스트 붙여넣기"))
        self.configure_text_context_shortcut_action(act_paste, "text_paste")
        act_paste.setEnabled(self.has_available_text_paste_source())
        act_toggle_enabled = menu.addAction(self._final_text_enable_toggle_label(data_items))
        act_toggle_enabled.setEnabled(bool(data_items))
        self.configure_final_text_enable_toggle_action(act_toggle_enabled)
        menu.addSeparator()
        act_effect = menu.addAction(self.tr_ui("고급 텍스트/획 옵션..."))
        self.configure_text_context_shortcut_action(act_effect, "text_effect_gradient")
        act_effect.setEnabled(bool(editable_text_items))
        writing_menu_enabled = bool(editable_text_items) and not any(self.is_text_writing_direction_change_blocked(d) for d in editable_text_items)
        _wd_sub, act_wd_h, act_wd_v = self.add_writing_direction_submenu(
            menu,
            current_direction=self.text_item_writing_direction(editable_text_items[0] if editable_text_items else None),
            enabled=writing_menu_enabled,
        )
        transform_menu = menu.addMenu(self.tr_ui("텍스트 변형"))
        transform_menu.setEnabled(bool(editable_text_items))
        act_skew = transform_menu.addAction(self.tr_ui("평행사변형 변형"))
        self.configure_text_context_shortcut_action(act_skew, "text_skew_toggle")
        act_skew.setCheckable(True)
        act_skew.setChecked(bool(text_item.data.get('_skew_mode', False)))
        act_skew.setEnabled(len(editable_text_items) == 1 and not bool(text_item.data.get('rasterized_text')))
        act_trapezoid = transform_menu.addAction(self.tr_ui("사다리꼴 변형"))
        self.configure_text_context_shortcut_action(act_trapezoid, "text_trapezoid_toggle")
        act_trapezoid.setCheckable(True)
        act_trapezoid.setChecked(bool(text_item.data.get('_trapezoid_mode', False)))
        act_trapezoid.setEnabled(len(editable_text_items) == 1 and not bool(text_item.data.get('rasterized_text')))
        act_arc = transform_menu.addAction(self.tr_ui("부채꼴 변형"))
        self.configure_text_context_shortcut_action(act_arc, "text_arc_toggle")
        act_arc.setCheckable(True)
        act_arc.setChecked(bool(text_item.data.get('_arc_mode', False)))
        act_arc.setEnabled(len(editable_text_items) == 1 and not bool(text_item.data.get('rasterized_text')))
        transform_menu.addSeparator()
        act_transform = transform_menu.addAction(self.tr_ui("텍스트 비율/회전"))
        self.configure_text_context_shortcut_action(act_transform, "text_transform_toggle")
        act_transform.setCheckable(True)
        act_transform.setChecked(bool(text_item.data.get('_transform_mode', False)))
        act_transform.setEnabled(len(editable_text_items) == 1 and not bool(text_item.data.get('rasterized_text')))
        menu.addSeparator()
        act_rasterize = menu.addAction(self.tr_ui("텍스트를 객체로 변환"))
        self.configure_text_context_shortcut_action(act_rasterize, "text_rasterize")
        act_rasterize.setEnabled(bool(editable_text_items))
        menu.addSeparator()
        act_delete = menu.addAction(self.tr_ui("텍스트 삭제"))
        self.configure_text_context_shortcut_action(act_delete, "text_delete")

        chosen = menu.exec(global_pos)
        if chosen == act_copy:
            self.copy_text_data_items(data_items or [text_item.data])
        elif chosen == act_paste:
            self.paste_text_clipboard_at_or_load_plain(scene_pos)
        elif chosen == act_toggle_enabled:
            self.toggle_selected_final_text_enabled(data_items)
        elif chosen == act_effect:
            self.open_text_advanced_effect_dialog(editable_text_items)
        elif chosen == act_wd_h:
            self.set_text_items_writing_direction(editable_text_items, 'horizontal')
        elif chosen == act_wd_v:
            self.set_text_items_writing_direction(editable_text_items, 'vertical')
        elif chosen == act_skew:
            self.toggle_text_skew_mode(text_item.data)
        elif chosen == act_trapezoid:
            self.toggle_text_trapezoid_mode(text_item.data)
        elif chosen == act_arc:
            self.toggle_text_arc_mode(text_item.data)
        elif chosen == act_transform:
            self.toggle_text_transform_mode(text_item.data)
        elif chosen == act_rasterize:
            self.convert_text_data_items_to_raster_objects(editable_text_items)
        elif chosen == act_delete:
            self.delete_text_data_items(data_items or [text_item.data], ask=True)

    def clear_text_transform_modes(self, except_data=None):
        curr = self.data.get(self.idx)
        if not curr:
            return
        for d in curr.get('data', []):
            if except_data is not None and d is except_data:
                continue
            d.pop('_transform_mode', None)
            d.pop('_skew_mode', None)
            d.pop('_trapezoid_mode', None)
            d.pop('_arc_mode', None)

    def toggle_text_transform_mode(self, data_item):
        """최종화면 텍스트 변형 모드 토글."""
        if self.cb_mode.currentIndex() != 4 or not data_item:
            return

        enabled = not bool(data_item.get('_transform_mode', False))
        self.clear_text_transform_modes(except_data=data_item)
        selected_id = data_item.get('id')

        if enabled:
            # 변형 모드는 영역 자체를 만지는 작업이다.
            # 따라서 OCR 초기 박스가 남아 있더라도 변형 진입 순간 현재 보이는
            # 실제 텍스트 bounds로 rect를 재생성하고 그 영역을 바로 띄운다.
            rect_changed = self.ensure_text_anchor_rect(
                data_item,
                record_undo=True,
                reason="텍스트 변형 영역 자동 재생성",
            )
            data_item['_transform_mode'] = True
            data_item.pop('_skew_mode', None)
            data_item.pop('_trapezoid_mode', None)
            data_item.pop('_arc_mode', None)
            if rect_changed:
                self.log("🔷 텍스트 변형 영역 자동 재생성: OCR 영역 대신 현재 텍스트 bounds를 사용합니다.")
            self.log("🔷 텍스트 변형 모드 ON: 파란 테두리/핸들을 조작하세요. Alt+드래그로 이동, Ctrl+Enter 또는 배경 클릭으로 종료")
        else:
            data_item.pop('_transform_mode', None)
            self.log("🔷 텍스트 변형 모드 OFF")

        if self.cb_mode.currentIndex() == 4:
            try:
                if selected_id is not None:
                    if not self.refresh_final_text_items_by_ids([selected_id]):
                        self.schedule_final_text_scene_refresh(80)
                    self.reselect_text_items([selected_id])
                else:
                    self.schedule_final_text_scene_refresh(80)
            except Exception:
                try:
                    self.schedule_final_text_scene_refresh(80)
                except Exception:
                    pass
        try:
            self.finalize_text_change(ids=[selected_id] if selected_id is not None else [], fields=['transform_mode'], reason='텍스트 변형 모드 변경', delay_ms=1800)
        except Exception:
            try:
                self.mark_active_page_dirty('text')
                self.schedule_deferred_auto_save_project(1800)
            except Exception:
                pass

    def toggle_text_skew_mode(self, data_item):
        """최종화면 텍스트 기울이기 직접 조정 모드 토글."""
        if self.cb_mode.currentIndex() != 4 or not data_item or data_item.get('rasterized_text'):
            return

        enabled = not bool(data_item.get('_skew_mode', False))
        self.clear_text_transform_modes(except_data=data_item)
        selected_id = data_item.get('id')
        try:
            if hasattr(self, "flush_text_scene_geometry_to_data"):
                self.flush_text_scene_geometry_to_data([data_item], mark_dirty=False, reason="before text transform mode")
        except Exception:
            pass

        if enabled:
            rect_changed = self.ensure_text_anchor_rect(
                data_item,
                record_undo=True,
                reason="텍스트 기울이기 영역 자동 재생성",
            )
            data_item['_skew_mode'] = True
            data_item.pop('_transform_mode', None)
            data_item.pop('_trapezoid_mode', None)
            data_item.pop('_arc_mode', None)
            if rect_changed:
                self.log("🔷 텍스트 기울이기 영역 자동 재생성: 현재 텍스트 bounds를 사용합니다.")
            self.log("🔷 평행사변형 변형 ON: 파란 테두리의 상/하 핸들은 가로 기울임, 좌/우 핸들은 세로 기울임입니다. 핸들 더블클릭으로 각도 입력.")
        else:
            data_item.pop('_skew_mode', None)
            self.log("🔷 평행사변형 변형 OFF")

        if self.cb_mode.currentIndex() == 4:
            try:
                if selected_id is not None:
                    if not self.refresh_final_text_items_by_ids([selected_id]):
                        self.schedule_final_text_scene_refresh(80)
                    self.reselect_text_items([selected_id])
                else:
                    self.schedule_final_text_scene_refresh(80)
            except Exception:
                try:
                    self.schedule_final_text_scene_refresh(80)
                except Exception:
                    pass
        try:
            self.finalize_text_change(ids=[selected_id] if selected_id is not None else [], fields=['transform_mode'], reason='텍스트 변형 모드 변경', delay_ms=1800)
        except Exception:
            try:
                self.mark_active_page_dirty('text')
                self.schedule_deferred_auto_save_project(1800)
            except Exception:
                pass

    def toggle_text_trapezoid_mode(self, data_item):
        """최종화면 텍스트 사다리꼴 변형 직접 조정 모드 토글."""
        if self.cb_mode.currentIndex() != 4 or not data_item or data_item.get('rasterized_text'):
            return

        enabled = not bool(data_item.get('_trapezoid_mode', False))
        self.clear_text_transform_modes(except_data=data_item)
        selected_id = data_item.get('id')
        try:
            if hasattr(self, "flush_text_scene_geometry_to_data"):
                self.flush_text_scene_geometry_to_data([data_item], mark_dirty=False, reason="before text transform mode")
        except Exception:
            pass

        if enabled:
            rect_changed = self.ensure_text_anchor_rect(
                data_item,
                record_undo=True,
                reason="사다리꼴 변형 영역 자동 재생성",
            )
            data_item['_trapezoid_mode'] = True
            data_item.pop('_transform_mode', None)
            data_item.pop('_skew_mode', None)
            data_item.pop('_arc_mode', None)
            if rect_changed:
                self.log("🔷 사다리꼴 변형 영역 자동 재생성: 현재 텍스트 bounds를 사용합니다.")
            self.log("🔷 사다리꼴 변형 ON: 네 꼭짓점과 상/하/좌/우 핸들을 드래그하세요. 좌우 핸들은 세로 원근, 상하 핸들은 가로 원근을 조정합니다. 핸들 더블클릭으로 수치 입력.")
        else:
            data_item.pop('_trapezoid_mode', None)
            self.log("🔷 사다리꼴 변형 OFF")

        if self.cb_mode.currentIndex() == 4:
            try:
                if selected_id is not None:
                    if not self.refresh_final_text_items_by_ids([selected_id]):
                        self.schedule_final_text_scene_refresh(80)
                    self.reselect_text_items([selected_id])
                else:
                    self.schedule_final_text_scene_refresh(80)
            except Exception:
                try:
                    self.schedule_final_text_scene_refresh(80)
                except Exception:
                    pass
        try:
            self.finalize_text_change(ids=[selected_id] if selected_id is not None else [], fields=['transform_mode'], reason='텍스트 변형 모드 변경', delay_ms=1800)
        except Exception:
            try:
                self.mark_active_page_dirty('text')
                self.schedule_deferred_auto_save_project(1800)
            except Exception:
                pass

    def toggle_text_arc_mode(self, data_item):
        """최종화면 텍스트 부채꼴 변형 직접 조정 모드 토글."""
        if self.cb_mode.currentIndex() != 4 or not data_item or data_item.get('rasterized_text'):
            return

        enabled = not bool(data_item.get('_arc_mode', False))
        self.clear_text_transform_modes(except_data=data_item)
        selected_id = data_item.get('id')
        try:
            if hasattr(self, "flush_text_scene_geometry_to_data"):
                self.flush_text_scene_geometry_to_data([data_item], mark_dirty=False, reason="before text transform mode")
        except Exception:
            pass

        if enabled:
            rect_changed = self.ensure_text_anchor_rect(
                data_item,
                record_undo=True,
                reason="부채꼴 변형 영역 자동 재생성",
            )
            data_item['_arc_mode'] = True
            data_item.pop('_transform_mode', None)
            data_item.pop('_skew_mode', None)
            data_item.pop('_trapezoid_mode', None)
            if rect_changed:
                self.log("🔷 부채꼴 변형 영역 자동 재생성: 현재 텍스트 bounds를 사용합니다.")
            self.log("🔷 부채꼴 변형 ON: 상/하/좌/우 중앙 핸들을 드래그해 휘어짐을 조정하세요. 핸들 더블클릭으로 각 면의 휘어짐 수치를 직접 입력합니다.")
        else:
            data_item.pop('_arc_mode', None)
            self.log("🔷 부채꼴 변형 OFF")

        if self.cb_mode.currentIndex() == 4:
            try:
                if selected_id is not None:
                    if not self.refresh_final_text_items_by_ids([selected_id]):
                        self.schedule_final_text_scene_refresh(80)
                    self.reselect_text_items([selected_id])
                else:
                    self.schedule_final_text_scene_refresh(80)
            except Exception:
                try:
                    self.schedule_final_text_scene_refresh(80)
                except Exception:
                    pass
        try:
            self.finalize_text_change(ids=[selected_id] if selected_id is not None else [], fields=['transform_mode'], reason='텍스트 변형 모드 변경', delay_ms=1800)
        except Exception:
            try:
                self.mark_active_page_dirty('text')
                self.schedule_deferred_auto_save_project(1800)
            except Exception:
                pass

    def show_final_background_context_menu(self, global_pos, scene_pos):
        if self.cb_mode.currentIndex() != 4:
            return
        self.last_canvas_context_pos = scene_pos

        menu = QMenu(self)
        act_paste = menu.addAction(self.tr_ui("텍스트 붙여넣기"))
        self.configure_text_context_shortcut_action(act_paste, "text_paste")
        act_paste.setEnabled(self.has_available_text_paste_source())
        act_add = menu.addAction(self.tr_ui("텍스트 추가"))

        chosen = menu.exec(global_pos)
        if chosen == act_paste:
            self.paste_text_clipboard_at_or_load_plain(scene_pos)
        elif chosen == act_add:
            # QMenu가 닫히는 포커스 전환과 inline editor 생성이 같은 이벤트 루프에 섞이면
            # 빈 편집기가 곧바로 focusOut 되어 우클릭 텍스트 추가가 실패한 것처럼 보일 수 있다.
            # 메뉴가 완전히 닫힌 다음 현재 UI 스타일을 반영한 텍스트 편집기를 연다.
            self.set_tool("final_text")
            try:
                sx, sy = int(scene_pos.x()), int(scene_pos.y())
            except Exception:
                sx, sy = 0, 0
            def _deferred_add_text():
                try:
                    self.create_final_text_at(sx, sy, centered=False)
                    try:
                        if getattr(self, 'inline_text_editor', None) is not None:
                            self.inline_text_editor.setFocus(Qt.FocusReason.OtherFocusReason)
                    except Exception:
                        pass
                    try:
                        self.audit_boundary_event('TEXT_CONTEXT_ADD_DONE', x=sx, y=sy, throttle_ms=80)
                    except Exception:
                        pass
                except Exception as exc:
                    try:
                        self.audit_boundary_event('TEXT_CONTEXT_ADD_ERROR', error=str(exc), x=sx, y=sy, throttle_ms=80)
                    except Exception:
                        pass
                    try:
                        self.log(f"⚠️ 우클릭 텍스트 추가 실패: {exc}")
                    except Exception:
                        pass
            try:
                self.audit_boundary_event('TEXT_CONTEXT_ADD_REQUEST', x=sx, y=sy, throttle_ms=80)
            except Exception:
                pass
            try:
                QTimer.singleShot(0, _deferred_add_text)
            except Exception:
                _deferred_add_text()

    def on_table_context_menu(self, pos):
        row = self.tab.rowAt(pos.y())
        if row <= 0:
            return

        if not self.tab.selectionModel().isRowSelected(row, QModelIndex()):
            self.tab.selectRow(row)

        data_item = self.row_to_text_data(row)
        if data_item is None:
            return

        data_items = self.selected_text_data_items() or [data_item]
        raster_items = [d for d in data_items if isinstance(d, dict) and d.get('rasterized_text')]
        editable_text_items = [d for d in data_items if isinstance(d, dict) and not d.get('rasterized_text')]

        menu = QMenu(self)
        act_toggle_enabled = menu.addAction(self._final_text_enable_toggle_label(data_items))
        act_toggle_enabled.setEnabled(bool(data_items))
        self.configure_final_text_enable_toggle_action(act_toggle_enabled)
        menu.addSeparator()
        act_effect = menu.addAction(self.tr_ui("고급 텍스트/획 옵션..."))
        self.configure_text_context_shortcut_action(act_effect, "text_effect_gradient")
        act_effect.setEnabled(bool(editable_text_items))
        writing_menu_enabled = bool(editable_text_items) and not any(self.is_text_writing_direction_change_blocked(d) for d in editable_text_items)
        _wd_sub, act_wd_h, act_wd_v = self.add_writing_direction_submenu(
            menu,
            current_direction=self.text_item_writing_direction(editable_text_items[0] if editable_text_items else None),
            enabled=writing_menu_enabled,
        )
        act_skew = menu.addAction(self.tr_ui("평행사변형 변형"))
        self.configure_text_context_shortcut_action(act_skew, "text_skew_toggle")
        act_skew.setEnabled(len(editable_text_items) == 1)
        act_trapezoid = menu.addAction(self.tr_ui("사다리꼴 변형"))
        self.configure_text_context_shortcut_action(act_trapezoid, "text_trapezoid_toggle")
        act_trapezoid.setEnabled(len(editable_text_items) == 1)
        act_arc = menu.addAction(self.tr_ui("부채꼴 변형"))
        self.configure_text_context_shortcut_action(act_arc, "text_arc_toggle")
        act_arc.setEnabled(len(editable_text_items) == 1)
        act_rasterize = menu.addAction(self.tr_ui("텍스트를 객체로 변환"))
        self.configure_text_context_shortcut_action(act_rasterize, "text_rasterize")
        act_rasterize.setEnabled(bool(editable_text_items))
        menu.addSeparator()
        act_delete = menu.addAction(self.tr_ui("텍스트 삭제"))
        self.configure_text_context_shortcut_action(act_delete, "text_delete")
        chosen = menu.exec(self.tab.viewport().mapToGlobal(pos))
        if chosen == act_toggle_enabled:
            self.toggle_selected_final_text_enabled(data_items)
        elif chosen == act_effect:
            self.open_text_advanced_effect_dialog(editable_text_items)
        elif chosen == act_wd_h:
            self.set_text_items_writing_direction(editable_text_items, 'horizontal')
        elif chosen == act_wd_v:
            self.set_text_items_writing_direction(editable_text_items, 'vertical')
        elif chosen == act_skew:
            self.toggle_text_skew_mode(editable_text_items[0] if editable_text_items else None)
        elif chosen == act_trapezoid:
            self.toggle_text_trapezoid_mode(editable_text_items[0] if editable_text_items else None)
        elif chosen == act_arc:
            self.toggle_text_arc_mode(editable_text_items[0] if editable_text_items else None)
        elif chosen == act_rasterize:
            self.convert_text_data_items_to_raster_objects(editable_text_items)
        elif chosen == act_delete:
            self.delete_text_data_items(data_items, ask=True)

    def erase_raster_text_brush_line(self, scene_start, scene_end, brush_size=25):
        if self.cb_mode.currentIndex() != 4:
            return False
        scene = self._safe_graphics_scene() if hasattr(self, '_safe_graphics_scene') else getattr(getattr(self, 'view', None), 'scene', None)
        if scene is None:
            return False
        changed_ids = []
        try:
            line_rect = QRectF(QPointF(scene_start), QPointF(scene_end)).normalized().adjusted(-brush_size, -brush_size, brush_size, brush_size)
        except Exception:
            line_rect = QRectF()
        for item in list(scene.items()):
            if not isinstance(item, TypesettingItem):
                continue
            if not item.data.get('rasterized_text'):
                continue
            try:
                if not line_rect.isNull() and not item.sceneBoundingRect().adjusted(-brush_size, -brush_size, brush_size, brush_size).intersects(line_rect):
                    continue
                # 첫 실제 후보를 만난 순간에만 텍스트 Undo를 연다.
                # 지우개가 객체 바깥에서 시작해도 스트로크가 객체를 통과하면 여기서 정상 기록된다.
                if not getattr(self, '_raster_text_erase_undo_started', False):
                    try:
                        self.undo_text_checkpoint('텍스트 객체 지우개')
                    except Exception:
                        pass
                    self._raster_text_erase_undo_started = True
                if item.erase_raster_line_scene(scene_start, scene_end, brush_size):
                    changed_ids.append(item.data.get('id'))
            except Exception:
                continue
        if changed_ids:
            self._raster_text_erase_changed_ids = list(set((getattr(self, '_raster_text_erase_changed_ids', []) or []) + changed_ids))
            return True
        return False

    def finish_raster_text_brush_erase(self):
        changed_ids = getattr(self, '_raster_text_erase_changed_ids', []) or []
        self._raster_text_erase_changed_ids = []
        self._raster_text_erase_undo_started = False
        if not changed_ids:
            return False
        self.auto_save_project()
        try:
            self.reselect_text_items(changed_ids)
        except Exception:
            pass
        self.log(f"🧽 텍스트 객체 지우개 적용: {len(changed_ids)}개")
        return True

    def renumber_text_items_for_current_page(self, curr=None):
        """우측 텍스트 행의 라인넘버(ID)를 현재 순서 기준 1부터 다시 정렬한다."""
        if curr is None:
            curr = self.data.get(self.idx)
        if not curr:
            return
        for n, d in enumerate(curr.get('data', []) or [], start=1):
            d['id'] = n

    def select_all_current_text_editor_later(self):
        """QTableWidget 편집기/QLineEdit/QTextEdit가 열린 직후 전체 선택한다."""
        def _select():
            fw = QApplication.focusWidget()
            try:
                if isinstance(fw, QLineEdit):
                    fw.selectAll()
                    return
                if isinstance(fw, (QTextEdit, QPlainTextEdit)):
                    cur = fw.textCursor()
                    cur.select(QTextCursor.SelectionType.Document)
                    fw.setTextCursor(cur)
                    return
            except Exception:
                pass

        QTimer.singleShot(0, _select)
        QTimer.singleShot(30, _select)
        QTimer.singleShot(80, _select)

    def edit_table_translation_row(self, row):
        """우측 텍스트 표의 해당 행 번역문 칸을 편집 모드로 열고 전체 선택한다."""
        if not hasattr(self, "tab"):
            return False
        if row <= 0 or row >= self.tab.rowCount():
            return False

        item = self.tab.item(row, 3)
        if item is None:
            item = QTableWidgetItem("")
            self.tab.setItem(row, 3, item)

        self.tab.setFocus()
        self.tab.setCurrentCell(row, 3)
        self.tab.editItem(item)
        self.select_all_current_text_editor_later()
        return True

    def edit_selected_translation_text_f2(self):
        """F2: 선택된 텍스트 영역/텍스트 행의 번역문을 바로 수정한다."""
        # 최종화면에서 텍스트 객체가 선택되어 있으면 그 자리 편집으로 들어간다.
        if self.cb_mode.currentIndex() == 4:
            items = self.selected_text_items()
            if items:
                self.start_inline_text_edit(items[0], select_all=True)
                return True

        # 우측 표에서 선택된 행이 있으면 번역문 칸을 편집한다.
        if hasattr(self, "tab"):
            rows = sorted({idx.row() for idx in self.tab.selectedIndexes() if idx.row() > 0})
            row = rows[0] if rows else self.tab.currentRow()
            if row > 0:
                return self.edit_table_translation_row(row)

        return False

    def apply_text_layer_z_order_from_data(self, curr=None):
        """현재 data 순서와 최종화면 텍스트 z-order를 맞춘다.

        YSB의 텍스트 표는 레이어 스택이다. 표 위쪽에 있는 행이 더 위에
        보여야 하므로 data[0]이 가장 높은 z값을 갖는다.
        """
        try:
            if curr is None:
                curr = self.data.get(self.idx)
        except Exception:
            curr = None
        if not isinstance(curr, dict):
            return False
        data_list = curr.get('data', []) or []
        try:
            renderable = [
                d for d in data_list
                if isinstance(d, dict)
                and bool(d.get('use_inpaint', True))
                and (str(d.get('translated_text', '') or '').strip() or d.get('force_show'))
            ]
            total = len(renderable)
            z_by_id = {str(d.get('id')): 30 + (total - i) for i, d in enumerate(renderable) if d.get('id') is not None}
        except Exception:
            z_by_id = {}
        if not z_by_id:
            return False
        scene = self._safe_graphics_scene() if hasattr(self, '_safe_graphics_scene') else getattr(getattr(self, 'view', None), 'scene', None)
        if scene is None:
            return False
        changed = False
        try:
            for obj in list(scene.items()):
                if not isinstance(obj, TypesettingItem):
                    continue
                sid = str((getattr(obj, 'data', {}) or {}).get('id'))
                if sid not in z_by_id:
                    continue
                new_z = float(z_by_id[sid])
                try:
                    if abs(float(obj.zValue()) - new_z) > 0.001:
                        obj.setZValue(new_z)
                        changed = True
                except Exception:
                    pass
            if changed:
                try:
                    scene.update()
                except Exception:
                    pass
        except Exception:
            return False
        return changed

    def on_text_table_rows_reordered(self):
        """우측 텍스트 행 드래그 후 data 순서를 표/드롭 순서에 맞춘다.

        표의 행은 텍스트 레이어 한 덩어리이며, 표 위쪽 행일수록 화면/출력에서
        더 위에 그려진다. 셀 문자열 드래그 이동은 TextTableWidget에서 차단하고,
        여기서는 행 ID 순서만 받아 data 리스트를 재배열한다.
        """
        if self._syncing_selection or self._table_check_lock:
            return
        curr = self.data.get(self.idx)
        if not curr:
            return

        pending_order = None
        try:
            pending_order = getattr(self.tab, '_pending_row_id_order', None)
            if pending_order:
                pending_order = [str(x).strip() for x in pending_order if str(x).strip() and str(x).strip() != 'ALL']
                self.tab._pending_row_id_order = None
        except Exception:
            pending_order = None

        id_order = []
        if pending_order:
            id_order = pending_order
        else:
            for row in range(1, self.tab.rowCount()):
                item = self.tab.item(row, 0)
                if item:
                    txt = item.text().strip()
                    if txt and txt != "ALL":
                        id_order.append(txt)

        if not id_order:
            return

        old_data = curr.get('data', [])
        old_id_order = [str(d.get('id')) for d in old_data]
        if id_order == old_id_order:
            return

        self.undo_push_text_line('텍스트 행 순서 변경')

        by_id = {str(d.get('id')): d for d in old_data}
        new_data = [by_id[i] for i in id_order if i in by_id]
        for d in old_data:
            if d not in new_data:
                new_data.append(d)

        curr['data'] = new_data
        self.renumber_text_items_for_current_page(curr)
        try:
            self.apply_text_layer_z_order_from_data(curr)
        except Exception:
            pass
        self.ref_tab()
        self.refresh_after_text_line_change(autosave=True)
        self.log("↕️ Text layer order changed: top rows render above lower rows" if self.ui_language == LANG_EN else "↕️ 텍스트 레이어 순서 변경 완료: 표 위쪽 행이 더 위에 표시됩니다")

    def set_text_detail_focus(self, attr):
        widget = getattr(self, attr, None)
        if widget is None:
            return
        widget.setFocus()
        try:
            widget.selectAll()
        except Exception:
            pass

    def toggle_bold(self):
        if hasattr(self, "btn_bold"):
            self.btn_bold.toggle()

    def toggle_italic(self):
        if hasattr(self, "btn_italic"):
            self.btn_italic.toggle()

    def toggle_strike(self):
        if hasattr(self, "btn_strike"):
            self.btn_strike.toggle()

    def _safe_graphics_scene(self):
        """현재 QGraphicsScene이 살아 있으면 반환한다.

        Qt 종료/모드 전환/씬 재생성 타이밍에는 Python 래퍼는 남아 있는데
        내부 C++ QGraphicsScene이 이미 삭제된 상태가 될 수 있다. 이때 selectedItems(),
        items(), blockSignals() 같은 호출이 RuntimeError를 내므로 모든 scene 접근 전
        이 헬퍼를 통과시킨다.
        """
        view = getattr(self, "view", None)
        scene = getattr(view, "scene", None) if view is not None else None
        if scene is None:
            return None
        try:
            # C++ 객체 생존 여부를 확인하는 가장 가벼운 호출.
            scene.sceneRect()
        except RuntimeError:
            return None
        except Exception:
            return None
        return scene

