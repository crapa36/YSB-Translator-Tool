from ysb.ui.main_window_support import *


class MainWindowTextLayoutMixin:

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
        state.setdefault("include", {k: True for k, _ in self.style_field_specs()})
        return state

    def save_item_text_preset_state(self, style=None, include=None, selected=None):
        state = {
            "style": self.normalize_style_dict(style or self.current_style_snapshot()),
            "include": {k: bool((include or {}).get(k, False)) for k, _ in self.style_field_specs()},
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
            ("line_spacing", "행간"),
            ("letter_spacing", "자간"),
            ("char_width", "너비"),
            ("char_height", "높이"),
            ("bold", "굵게"),
            ("italic", "기울임"),
            ("strike", "취소선"),
        ]

    def style_summary_text(self, style, include=None):
        style = self.normalize_style_dict(style)
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
            elif key in ("line_spacing",):
                value = f"{100 if int(value or 0) == 0 else value}%"
            elif key in ("letter_spacing",):
                value = "자동" if int(value or 0) == 0 else f"{value}px"
            elif key in ("char_width", "char_height"):
                value = f"{value}%"
            elif key in ("bold", "italic", "strike"):
                value = yes(bool(value))
            parts.append(f"{label}:{value}")
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
        return self.normalize_style_dict({
            "font_family": self.cb_font.currentFont().family(),
            "font_size": int(self.sb_font_size.value()),
            "stroke_width": int(self.sb_strk.value()),
            "text_color": self.default_text_color,
            "stroke_color": self.default_stroke_color,
            "align": self.default_align,
            "line_spacing": int(self.sb_line_spacing.value()) if hasattr(self, "sb_line_spacing") else self.default_line_spacing,
            "letter_spacing": int(self.sb_letter_spacing.value()) if hasattr(self, "sb_letter_spacing") else self.default_letter_spacing,
            "char_width": int(self.sb_char_width.value()) if hasattr(self, "sb_char_width") else self.default_char_width,
            "char_height": int(self.sb_char_height.value()) if hasattr(self, "sb_char_height") else self.default_char_height,
            "bold": bool(self.btn_bold.isChecked()) if hasattr(self, "btn_bold") else self.default_bold,
            "italic": bool(self.btn_italic.isChecked()) if hasattr(self, "btn_italic") else self.default_italic,
            "strike": bool(self.btn_strike.isChecked()) if hasattr(self, "btn_strike") else self.default_strike,
        })

    def normalize_style_dict(self, style):
        style = dict(style or {})
        align = str(style.get("align") or "center").lower()
        if align not in ("left", "center", "right"):
            align = "center"

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

        return {
            "font_family": str(style.get("font_family") or self.cb_font.currentFont().family()),
            "font_size": _int("font_size", self.sb_font_size.value(), 1, 1000),
            "stroke_width": _int("stroke_width", self.sb_strk.value(), 0, 300),
            "text_color": str(style.get("text_color") or "#000000"),
            "stroke_color": str(style.get("stroke_color") or "#FFFFFF"),
            "align": align,
            "line_spacing": _int("line_spacing", 100, 50, 300),
            "letter_spacing": _int("letter_spacing", 0, -500, 500),
            "char_width": _int("char_width", 100, 10, 300),
            "char_height": _int("char_height", 100, 10, 300),
            "bold": bool(style.get("bold", False)),
            "italic": bool(style.get("italic", False)),
            "strike": bool(style.get("strike", False)),
        }

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
            if hasattr(self, "sb_line_spacing"):
                self._set_widget_value_blocked(self.sb_line_spacing, 100 if int(style["line_spacing"] or 0) == 0 else int(style["line_spacing"]))
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
                    # 예전 파일/비어있는 파일은 전부 포함으로 보정
                    if not any(include.values()):
                        include = {k: True for k, _ in self.style_field_specs()}
                    preset = {
                        "style": style,
                        "include": include,
                        "enabled": bool(raw.get("enabled", True)),
                        "shortcut": str(raw.get("shortcut", "") or ""),
                    }
                else:
                    preset = {
                        "style": self.normalize_style_dict(raw),
                        "include": {k: True for k, _ in self.style_field_specs()},
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
        payload = {
            "style": self.normalize_style_dict(preset.get("style")),
            "include": {k: bool((preset.get("include") or {}).get(k, False)) for k, _ in self.style_field_specs()},
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
        dialog = QDialog(self)
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

        # ---------- style editor ----------
        editor = QWidget(dialog)
        editor_l = QVBoxLayout(editor)
        editor_l.setContentsMargins(0, 0, 0, 0)
        editor_l.setSpacing(6)

        row1 = QHBoxLayout()
        row1.setSpacing(6)
        dlg_font = QFontComboBox(dialog); dlg_font.setFixedWidth(160); dlg_font.setFixedHeight(26)
        dlg_size = QSpinBox(dialog); dlg_size.setRange(5, 500); dlg_size.setSuffix(" px"); dlg_size.setFixedWidth(82); dlg_size.setFixedHeight(26)
        dlg_stroke = QSpinBox(dialog); dlg_stroke.setRange(0, 100); dlg_stroke.setSuffix(" px"); dlg_stroke.setFixedWidth(78); dlg_stroke.setFixedHeight(26)
        dlg_text_color_btn = QPushButton("", dialog); dlg_text_color_btn.setFixedSize(26, 26)
        dlg_stroke_color_btn = QPushButton("", dialog); dlg_stroke_color_btn.setFixedSize(26, 26)
        dlg_align_left = QPushButton("≡◁", dialog); dlg_align_center = QPushButton("≡◇", dialog); dlg_align_right = QPushButton("▷≡", dialog)
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
        dlg_line_spacing = QSpinBox(dialog); dlg_line_spacing.setRange(50, 300); dlg_line_spacing.setValue(100); dlg_line_spacing.setSuffix(" %"); dlg_line_spacing.setFixedWidth(86); dlg_line_spacing.setFixedHeight(26)
        dlg_letter_spacing = QSpinBox(dialog); dlg_letter_spacing.setRange(-100, 200); dlg_letter_spacing.setSuffix(" px"); dlg_letter_spacing.setFixedWidth(86); dlg_letter_spacing.setFixedHeight(26)
        dlg_char_width = QSpinBox(dialog); dlg_char_width.setRange(10, 300); dlg_char_width.setValue(100); dlg_char_width.setSuffix(" %"); dlg_char_width.setFixedWidth(86); dlg_char_width.setFixedHeight(26)
        dlg_char_height = QSpinBox(dialog); dlg_char_height.setRange(10, 300); dlg_char_height.setValue(100); dlg_char_height.setSuffix(" %"); dlg_char_height.setFixedWidth(86); dlg_char_height.setFixedHeight(26)
        dlg_bold = QPushButton("B", dialog); dlg_italic = QPushButton("I", dialog); dlg_strike = QPushButton("S", dialog)
        for b, tip in ((dlg_bold, "굵게"), (dlg_italic, "기울이기"), (dlg_strike, "취소선")):
            b.setCheckable(True); b.setFixedWidth(32); b.setFixedHeight(26); b.setToolTip(tip)
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
        row2.addWidget(dlg_bold); row2.addWidget(dlg_italic); row2.addWidget(dlg_strike)
        row2.addStretch()
        editor_l.addLayout(row2)
        layout.addWidget(editor)

        def refresh_color_buttons():
            tip_bg = "#ffffff" if self.is_light_theme() else "#000000"
            tip_fg = "#111827" if self.is_light_theme() else "#ffffff"
            tip_border = "#cfd7e5" if self.is_light_theme() else "#4b5563"
            dlg_text_color_btn.setStyleSheet(
                f"QPushButton {{ background:{dialog_text_color['value']}; border:1px solid #444; padding:0px; }}"
                f"QToolTip {{ background-color:{tip_bg}; color:{tip_fg}; border:1px solid {tip_border}; border-radius:0px; padding:5px; }}"
            )
            dlg_stroke_color_btn.setStyleSheet(
                f"QPushButton {{ background:{dialog_stroke_color['value']}; border:1px solid #444; padding:0px; }}"
                f"QToolTip {{ background-color:{tip_bg}; color:{tip_fg}; border:1px solid {tip_border}; border-radius:0px; padding:5px; }}"
            )
            checked_style = "background:#dbeafe; color:#111827; border:1px solid #8fb4e8; border-radius:0px;" if self.is_light_theme() else "background:#3d587d; color:#ffffff; border:1px solid #7ea2d6; border-radius:0px;"
            for align, btn in (("left", dlg_align_left), ("center", dlg_align_center), ("right", dlg_align_right)):
                btn.setStyleSheet(checked_style if dialog_align["value"] == align else "")

        def dialog_style_snapshot():
            return self.normalize_style_dict({
                "font_family": dlg_font.currentFont().family(),
                "font_size": int(dlg_size.value()),
                "stroke_width": int(dlg_stroke.value()),
                "text_color": dialog_text_color["value"],
                "stroke_color": dialog_stroke_color["value"],
                "align": dialog_align["value"],
                "line_spacing": int(dlg_line_spacing.value()),
                "letter_spacing": int(dlg_letter_spacing.value()),
                "char_width": int(dlg_char_width.value()),
                "char_height": int(dlg_char_height.value()),
                "bold": bool(dlg_bold.isChecked()),
                "italic": bool(dlg_italic.isChecked()),
                "strike": bool(dlg_strike.isChecked()),
            })

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
                dlg_line_spacing.setValue(100 if int(style["line_spacing"] or 0) == 0 else int(style["line_spacing"]))
                dlg_letter_spacing.setValue(int(style["letter_spacing"]))
                dlg_char_width.setValue(int(style["char_width"]))
                dlg_char_height.setValue(int(style["char_height"]))
                dlg_bold.setChecked(bool(style["bold"]))
                dlg_italic.setChecked(bool(style["italic"]))
                dlg_strike.setChecked(bool(style["strike"]))
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

                if not chk.isChecked():
                    if self.is_light_theme():
                        row.setStyleSheet("background:#f1f3f6; color:#8a8f99;")
                        summary.setStyleSheet("color:#8a8f99;")
                        name_edit.setStyleSheet("background:#f7f8fa; color:#8a8f99; border:1px solid #d0d5df;")
                    else:
                        row.setStyleSheet("background:#242424; color:#888888;")
                        summary.setStyleSheet("color:#888888;")
                        name_edit.setStyleSheet("color:#888888;")
                is_selected = (selected_name["value"] == name or select_name == name)
                if is_selected:
                    if self.is_light_theme():
                        row_style = "background:#e8f1ff; border:1px solid #6fa8ff;"
                        child_style = "background:#ffffff; color:#202124; border:1px solid #6fa8ff;"
                    else:
                        row_style = "background:#31415c; border:1px solid #5b8def;"
                        child_style = "background:#2f5fa7; color:white; border:1px solid #80b4ff;"
                    row.setStyleSheet(row_style)
                    btn_select.setText("선택됨")
                    btn_select.setStyleSheet("background:#4b79c7; color:white; font-weight:bold; border:1px solid #9cc3ff;")
                    name_edit.setStyleSheet(child_style)
                    summary.setStyleSheet(child_style)
                    btn_update.setStyleSheet("background:#3d5f92; color:white;")
                    btn_delete.setStyleSheet("background:#3d5f92; color:white;")
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
            if original_page_snapshot is not None and original_idx in self.data:
                self.data[original_idx] = copy.deepcopy(original_page_snapshot)
            self.apply_style_to_controls(original_style_snapshot)
            self.load_text_preset_cache()
            if self.idx == original_idx:
                self.ref_tab()
                if self.cb_mode.currentIndex() == 4:
                    self.mode_chg(4)
            dialog_state["restored"] = True

        def on_dialog_style_changed(*args):
            if dialog_lock["value"]:
                return
            refresh_color_buttons()
            preview_style_on_current_page(dialog_style_snapshot())

        def pick_dialog_color(target):
            current = dialog_text_color["value"] if target == "text" else dialog_stroke_color["value"]
            color = QColorDialog.getColor(QColor(current), self, "색상 선택")
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

        for widget in (dlg_font, dlg_size, dlg_stroke, dlg_line_spacing, dlg_letter_spacing, dlg_char_width, dlg_char_height):
            if hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(on_dialog_style_changed)
        dlg_font.currentFontChanged.connect(on_dialog_style_changed)
        dlg_bold.toggled.connect(on_dialog_style_changed)
        dlg_italic.toggled.connect(on_dialog_style_changed)
        dlg_strike.toggled.connect(on_dialog_style_changed)
        dlg_text_color_btn.clicked.connect(self.make_safe_slot(pick_dialog_color, "text"))
        dlg_stroke_color_btn.clicked.connect(self.make_safe_slot(pick_dialog_color, "stroke"))
        dlg_align_left.clicked.connect(self.make_safe_slot(set_dialog_align, "left"))
        dlg_align_center.clicked.connect(self.make_safe_slot(set_dialog_align, "center"))
        dlg_align_right.clicked.connect(self.make_safe_slot(set_dialog_align, "right"))

        btn_line = QHBoxLayout()
        btn_add = QPushButton(self.tr_ui("현재 스타일을 새 프리셋으로 추가"), dialog)
        btn_import = QPushButton(self.tr_ui("불러오기"), dialog)
        btn_apply_page = QPushButton(self.tr_ui("현재 페이지에 적용"), dialog)
        btn_apply_all = QPushButton(self.tr_ui("전체 페이지에 적용"), dialog)
        btn_ok = QPushButton(self.tr_ui("확인"), dialog)
        btn_close = QPushButton(self.tr_ui("닫기"), dialog)
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
            path, _ = QFileDialog.getOpenFileName(dialog, self.tr_ui("페이지 글꼴 프리셋 불러오기"), str(self.text_preset_dir()), "JSON (*.json)")
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
                self.ref_tab()
                if self.cb_mode.currentIndex() == 4:
                    self.mode_chg(4)
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

        result = dialog.exec()
        if not dialog_state["applied"] and not dialog_state["restored"]:
            restore_full_original_state()

    def open_item_text_preset_dialog(self):
        """선택 텍스트에만 적용하는 개별 글꼴 프리셋 관리.

        이 창의 실시간 변경은 선택 텍스트에만 임시 미리보기로 보이고,
        확인/닫기로 나가면 실제 텍스트에는 적용하지 않는다.
        실제 적용은 우측 콤보 선택 또는 프리셋 단축키로만 한다.
        """
        dialog = QDialog(self)
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

        # ---------- editor ----------
        top = QWidget(dialog)
        top_l = QVBoxLayout(top); top_l.setContentsMargins(0, 0, 0, 0); top_l.setSpacing(6)

        row1 = QHBoxLayout(); row1.setSpacing(6)
        dlg_font = QFontComboBox(dialog); dlg_font.setFixedWidth(160); dlg_font.setFixedHeight(26)
        dlg_size = QSpinBox(dialog); dlg_size.setRange(5, 500); dlg_size.setSuffix(" px"); dlg_size.setFixedWidth(82); dlg_size.setFixedHeight(26)
        dlg_stroke = QSpinBox(dialog); dlg_stroke.setRange(0, 100); dlg_stroke.setSuffix(" px"); dlg_stroke.setFixedWidth(78); dlg_stroke.setFixedHeight(26)
        dlg_text_color_btn = QPushButton("", dialog); dlg_text_color_btn.setFixedSize(26, 26)
        dlg_stroke_color_btn = QPushButton("", dialog); dlg_stroke_color_btn.setFixedSize(26, 26)
        dlg_align_left = QPushButton("≡◁", dialog); dlg_align_center = QPushButton("≡◇", dialog); dlg_align_right = QPushButton("▷≡", dialog)
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
        dlg_line_spacing = QSpinBox(dialog); dlg_line_spacing.setRange(50, 300); dlg_line_spacing.setValue(100); dlg_line_spacing.setSuffix(" %"); dlg_line_spacing.setFixedWidth(86); dlg_line_spacing.setFixedHeight(26)
        dlg_letter_spacing = QSpinBox(dialog); dlg_letter_spacing.setRange(-100, 200); dlg_letter_spacing.setSuffix(" px"); dlg_letter_spacing.setFixedWidth(86); dlg_letter_spacing.setFixedHeight(26)
        dlg_char_width = QSpinBox(dialog); dlg_char_width.setRange(10, 300); dlg_char_width.setValue(100); dlg_char_width.setSuffix(" %"); dlg_char_width.setFixedWidth(86); dlg_char_width.setFixedHeight(26)
        dlg_char_height = QSpinBox(dialog); dlg_char_height.setRange(10, 300); dlg_char_height.setValue(100); dlg_char_height.setSuffix(" %"); dlg_char_height.setFixedWidth(86); dlg_char_height.setFixedHeight(26)
        dlg_bold = QPushButton("B", dialog); dlg_italic = QPushButton("I", dialog); dlg_strike = QPushButton("S", dialog)
        for b, tip in ((dlg_bold, "굵게"), (dlg_italic, "기울이기"), (dlg_strike, "취소선")):
            b.setCheckable(True); b.setFixedWidth(32); b.setFixedHeight(26); b.setToolTip(tip)
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
        row2.addWidget(dlg_bold); row2.addWidget(dlg_italic); row2.addWidget(dlg_strike)
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
        top_l.addWidget(include_box)
        layout.addWidget(top)

        def current_dialog_style():
            return self.normalize_style_dict({
                "font_family": dlg_font.currentFont().family(),
                "font_size": int(dlg_size.value()),
                "stroke_width": int(dlg_stroke.value()),
                "text_color": dialog_text_color["value"],
                "stroke_color": dialog_stroke_color["value"],
                "align": dialog_align["value"],
                "line_spacing": int(dlg_line_spacing.value()),
                "letter_spacing": int(dlg_letter_spacing.value()),
                "char_width": int(dlg_char_width.value()),
                "char_height": int(dlg_char_height.value()),
                "bold": bool(dlg_bold.isChecked()),
                "italic": bool(dlg_italic.isChecked()),
                "strike": bool(dlg_strike.isChecked()),
            })

        def current_include():
            return {k: chk.isChecked() for k, chk in include_checks.items()}

        def refresh_color_buttons():
            tip_bg = "#ffffff" if self.is_light_theme() else "#000000"
            tip_fg = "#111827" if self.is_light_theme() else "#ffffff"
            tip_border = "#cfd7e5" if self.is_light_theme() else "#4b5563"
            dlg_text_color_btn.setStyleSheet(
                f"QPushButton {{ background:{dialog_text_color['value']}; border:1px solid #444; padding:0px; }}"
                f"QToolTip {{ background-color:{tip_bg}; color:{tip_fg}; border:1px solid {tip_border}; border-radius:0px; padding:5px; }}"
            )
            dlg_stroke_color_btn.setStyleSheet(
                f"QPushButton {{ background:{dialog_stroke_color['value']}; border:1px solid #444; padding:0px; }}"
                f"QToolTip {{ background-color:{tip_bg}; color:{tip_fg}; border:1px solid {tip_border}; border-radius:0px; padding:5px; }}"
            )
            checked_style = "background:#dbeafe; color:#111827; border:1px solid #8fb4e8; border-radius:0px;" if self.is_light_theme() else "background:#3d587d; color:#ffffff; border:1px solid #7ea2d6; border-radius:0px;"
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
                dlg_line_spacing.setValue(100 if int(st["line_spacing"] or 0) == 0 else int(st["line_spacing"]))
                dlg_letter_spacing.setValue(int(st["letter_spacing"]))
                dlg_char_width.setValue(int(st["char_width"]))
                dlg_char_height.setValue(int(st["char_height"]))
                dlg_bold.setChecked(bool(st["bold"]))
                dlg_italic.setChecked(bool(st["italic"]))
                dlg_strike.setChecked(bool(st["strike"]))
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
            color = QColorDialog.getColor(QColor(current), self, "색상 선택")
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

        for widget in (dlg_font, dlg_size, dlg_stroke, dlg_line_spacing, dlg_letter_spacing, dlg_char_width, dlg_char_height):
            if hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(preview_selected_only)
        dlg_font.currentFontChanged.connect(preview_selected_only)
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

        # ---------- rows ----------
        rows_widget = QWidget(dialog)
        rows_layout = QVBoxLayout(rows_widget)
        rows_layout.setContentsMargins(0, 0, 0, 0); rows_layout.setSpacing(4)
        scroll = QScrollArea(dialog); scroll.setWidgetResizable(True); scroll.setWidget(rows_widget); scroll.setMinimumHeight(300)
        layout.addWidget(scroll, 1)

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

                if not chk_enabled.isChecked():
                    if self.is_light_theme():
                        row.setStyleSheet("background:#f1f3f6; color:#8a8f99;")
                        summary.setStyleSheet("color:#8a8f99;")
                        name_edit.setStyleSheet("background:#f7f8fa; color:#8a8f99; border:1px solid #d0d5df;")
                        key_edit.setStyleSheet("background:#f7f8fa; color:#8a8f99; border:1px solid #d0d5df;")
                    else:
                        row.setStyleSheet("background:#242424; color:#888888;")
                        summary.setStyleSheet("color:#888888;")
                        name_edit.setStyleSheet("color:#888888;")
                        key_edit.setStyleSheet("color:#888888;")

                is_selected = (selected_name["value"] == name or select_name == name)
                if is_selected:
                    if self.is_light_theme():
                        row_style = "background:#e8f1ff; border:1px solid #6fa8ff;"
                        child_style = "background:#ffffff; color:#202124; border:1px solid #6fa8ff;"
                    else:
                        row_style = "background:#31415c; border:1px solid #5b8def;"
                        child_style = "background:#2f5fa7; color:white; border:1px solid #80b4ff;"
                    row.setStyleSheet(row_style)
                    btn_select.setText("선택됨")
                    btn_select.setStyleSheet("background:#4b79c7; color:white; font-weight:bold; border:1px solid #9cc3ff;")
                    name_edit.setStyleSheet(child_style)
                    summary.setStyleSheet(child_style)
                    key_edit.setStyleSheet(child_style)
                    btn_update.setStyleSheet("background:#3d5f92; color:white;")
                    btn_delete.setStyleSheet("background:#3d5f92; color:white;")
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
            path, _ = QFileDialog.getOpenFileName(dialog, self.tr_ui("개별 글꼴 프리셋 불러오기"), str(self.item_text_preset_dir()), "JSON (*.json)")
            if not path:
                return
            try:
                with open(path, "r", encoding="utf-8-sig") as f:
                    raw = json.load(f)
                if isinstance(raw, dict) and "style" in raw:
                    style = self.normalize_style_dict(raw.get("style"))
                    inc = raw.get("include") or {k: True for k, _ in self.style_field_specs()}
                else:
                    style = self.normalize_style_dict(raw)
                    inc = {k: True for k, _ in self.style_field_specs()}
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
            # 개별 프리셋 창은 실제 적용 창이 아니므로, 나갈 때는 창을 열기 전 페이지 상태로 통째로 복구한다.
            if original_page_snapshot is not None and page_idx in self.data:
                self.data[page_idx] = copy.deepcopy(original_page_snapshot)
            else:
                self.restore_text_items_by_snapshot(page_idx, selected_snapshot)
            if self.idx == page_idx:
                self.ref_tab()
                if self.cb_mode.currentIndex() == 4:
                    self.mode_chg(4)
                    self.reselect_text_items([int(x) for x in selected_snapshot.keys() if str(x).isdigit()])
                    self.update_item_preset_combo_for_selected_texts()

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
        preview_selected_only()
        result = dialog.exec()
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

    def apply_current_preset_to_data_items(self, items):
        self.apply_style_dict_to_data_items(items, self.current_style_snapshot())

    def apply_current_preset_to_page(self, page_idx, refresh=False):
        curr = self.data.get(page_idx)
        if not curr:
            self.log("⚠️ 현재 페이지가 없어 프리셋 페이지 적용을 건너뜁니다.")
            return 0
        targets = [x for x in curr.get('data', []) if x.get('use_inpaint', True)]
        if targets:
            self.push_project_undo("현재 페이지 글꼴 프리셋 적용", page_idx=page_idx)
        self.apply_current_preset_to_data_items(targets)
        if refresh and page_idx == self.idx:
            self.ref_tab()
            if self.cb_mode.currentIndex() == 4:
                self.mode_chg(4)
        self.auto_save_project()
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
            total += len(targets)
            if i == self.idx:
                touched_current = True

        if touched_current and self.idx in self.data:
            self.ref_tab()
            if self.cb_mode.currentIndex() == 4:
                self.mode_chg(4)

        self.auto_save_project()
        if total:
            self.append_project_undo_record(undo_record)
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

    def auto_wrap_lines_for_metrics(self, text, fm, max_w, protect_short_tokens=True):
        """
        QFontMetrics 기준으로 줄바꿈 결과를 계산한다.

        1.2 조건:
        - 전체 텍스트가 5글자 이하라면 영역을 넘어도 줄내림하지 않는다.
        - 단어/덩어리가 5글자 이하라면 그 덩어리 내부는 끊지 않는다.
        - 6글자 이상 덩어리는 영역을 넘으면 글자 단위로 끊어 내린다.
        """
        text = str(text or '').replace('\r\n', '\n').replace('\r', '\n')
        max_w = max(1, int(max_w))

        # 공백 없는 단일 덩어리가 5글자 이하일 때만 한 줄 보호.
        # "저게 뭐야?"처럼 띄어쓰기가 있는 짧은 문장은 단어 사이에서 줄내림할 수 있어야 한다.
        compact_len = len(''.join(ch for ch in text if not ch.isspace()))
        has_spacing = any(ch.isspace() for ch in text.strip())
        if protect_short_tokens and compact_len <= 5 and not has_spacing:
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

        def break_long_unit(unit, current, lines):
            # 6글자 이상 덩어리는 필요하면 글자 단위로 끊는다.
            for ch in unit:
                trial = current + ch
                if current and fm.horizontalAdvance(trial) > max_w:
                    append_line(lines, current)
                    current = ch
                else:
                    current = trial
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

                unit_len = len(unit)
                trial = current + unit

                if fm.horizontalAdvance(trial) <= max_w:
                    current = trial
                    continue

                if unit_len <= 5:
                    # 짧은 단어는 내부에서 끊지 않는다.
                    if current:
                        append_line(lines, current)
                    current = unit
                else:
                    # 긴 덩어리는 현재 줄에 들어갈 만큼 넣고, 넘치면 글자 단위로 끊는다.
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

        if compact_len <= 5:
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
        - 5글자를 넘는 긴 토큰은 억지로 글자 단위 분해하지 않는다.
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

        lines = []
        current = ''
        for token in tokens:
            if not current:
                current = token
                continue

            trial = current + ' ' + token
            # 짧은 묶음은 폭이 조금 넘어도 한 줄로 둔다. 너무 잦은 줄내림 방지.
            if compact_len(trial) <= 5:
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

        try:
            box_w = max(1, int(rect[2]))
            box_h = max(1, int(rect[3]))
        except Exception:
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
        # 폭은 조금 튀어나와도 허용하되, 줄내림 기준 자체는 너무 넓게 잡지 않는다.
        wrap_target_w = max(1, int(box_w * 1.12) - stroke * 2)
        # 핵심 기준: 하단 초과 방지. 약간의 하단 여백만 둔다.
        max_h = max(1, int(box_h * 0.98) - stroke * 2)

        chosen_size = None
        chosen_lines = None
        chosen_height = None

        for size in range(max_size, min_size - 1, -1):
            _font, fm, line_spacing_pct, char_width_pct, char_height_pct, letter_spacing = self._auto_layout_item_style_metrics(item, family, size)
            sx = max(0.1, char_width_pct / 100.0)
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
        changed = False

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
            font.setBold(bool(item.get('bold', False)))
            font.setItalic(bool(item.get('italic', False)))
        except Exception:
            pass
        fm = QFontMetrics(font)
        try:
            line_spacing_pct = max(50, min(300, int(item.get('line_spacing', 100) or 100)))
        except Exception:
            line_spacing_pct = 100
        try:
            char_width_pct = max(10, min(300, int(item.get('char_width', 100) or 100)))
        except Exception:
            char_width_pct = 100
        try:
            char_height_pct = max(10, min(300, int(item.get('char_height', 100) or 100)))
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

    def _measure_wrapped_lines_for_auto_fit(self, item, lines, family, size, stroke=0):
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

    def _fit_space_language_text_for_item(self, item, lang='en'):
        """영어/한국어: 자동 줄내림과 자동 크기조정을 한 번에 수행한다."""
        rect = item.get('rect')
        if not rect or len(rect) < 4:
            return False

        text_key, original = self._auto_layout_text_key_and_value(item)
        if not str(original or '').strip():
            return False

        lang = self._normalize_ocr_lang_for_layout(lang) or 'en'
        source_text = self.normalize_auto_wrap_source_text_for_lang(original, lang)
        if not source_text.strip():
            return False

        self.ensure_item_style_for_auto(item)

        try:
            box_w = max(1, int(rect[2]))
            box_h = max(1, int(rect[3]))
        except Exception:
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

        # 영어/한국어는 말풍선 공간을 적극적으로 쓰되, 좌우/상하 여백은 남긴다.
        if lang == 'en':
            width_ratio = 0.92
            height_ratio = 0.88
            max_size_by_box = int(max(box_h * 0.80, box_w * 0.34, start_size * 1.85))
        else:
            width_ratio = 0.90
            height_ratio = 0.86
            max_size_by_box = int(max(box_h * 0.72, box_w * 0.30, start_size * 1.65))

        max_w = max(1, int(box_w * width_ratio) - stroke * 2)
        max_h = max(1, int(box_h * height_ratio) - stroke * 2)
        min_size = 5
        max_size = max(min_size, min(260, max(start_size, max_size_by_box)))

        chosen_size = None
        chosen_lines = None
        chosen_score = None

        # 가장 큰 크기 우선. 같은 크기에서는 세로 공간을 너무 적게 쓰는 배치를 살짝 덜 선호한다.
        for size in range(max_size, min_size - 1, -1):
            _font, fm, _line_spacing_pct, char_width_pct, _char_height_pct, letter_spacing = self._auto_layout_item_style_metrics(item, family, size)
            wrap_w = max(1, int(max_w / max(0.1, char_width_pct / 100.0)))
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
            # 정말 안 들어가면 최소 크기로라도 감는다.
            size = min_size
            _font, fm, _line_spacing_pct, char_width_pct, _char_height_pct, letter_spacing = self._auto_layout_item_style_metrics(item, family, size)
            wrap_w = max(1, int(max_w / max(0.1, char_width_pct / 100.0)))
            chosen_lines = self._wrap_space_language_lines(source_text, fm, wrap_w, lang=lang, letter_spacing=letter_spacing)
            chosen_size = size

        wrapped = '\n'.join([line.rstrip() for line in chosen_lines]).strip()
        changed = False

        if wrapped and wrapped != str(original or ''):
            item[text_key] = wrapped
            changed = True

        old_size = int(item.get('font_size', start_size) or start_size)
        if old_size != int(chosen_size):
            item['font_size'] = int(chosen_size)
            changed = True

        # 새로 분석한 데이터가 아니거나 구버전 프로젝트여도 이후 버튼 동작이 안정되도록 저장한다.
        if item.get('ocr_lang') != lang:
            item['ocr_lang'] = lang
            changed = True

        return changed

    def auto_text_size_item(self, item, page_idx=None):
        """언어별 자동 크기 조정.

        - 영어/한국어: 번역문 기준으로 자동 줄내림 + 최대 크기 맞춤을 함께 수행한다.
        - 일본어/중국어: 기존 원문 OCR/마스크 기반 크기 추정 로직을 유지한다.
        """
        if self.is_manga_ocr_layout_item(item):
            return self._fit_manga_ocr_text_for_item(item, page_idx=page_idx)

        if self.is_manga_ocr_layout_item(item):
            return self._fit_manga_ocr_text_for_item(item)

        lang = self.item_ocr_language_for_layout(item)
        if lang in ('en', 'ko'):
            return self._fit_space_language_text_for_item(item, lang=lang)

        rect = item.get('rect')
        if not rect or len(rect) < 4:
            return False

        source_text = str(item.get('text', '') or '')
        if not source_text.strip():
            return False

        self.ensure_item_style_for_auto(item)

        ocr_est = self.estimate_source_font_size_from_ocr_coords(item)
        mask_est = self.estimate_source_font_size_from_mask(item, page_idx)
        fallback_est = self.estimate_source_font_size_fallback(item)

        candidates = []
        if ocr_est is not None:
            candidates.append(float(ocr_est))
        if mask_est is not None:
            candidates.append(float(mask_est))
        if fallback_est is not None:
            candidates.append(float(fallback_est))
        if not candidates:
            return False

        if ocr_est is not None:
            # OCR 조각 좌표가 있으면 그 값을 최우선으로 쓴다.
            # fallback/mask는 예전처럼 작은 값으로 OCR 추정치를 깎지 않는다.
            best = float(ocr_est)
        else:
            best = min(candidates)

        best = max(5, min(260, int(round(best))))
        old_value = int(item.get('font_size', self.sb_font_size.value()) or self.sb_font_size.value())
        item['font_size'] = best
        if item.get('ocr_lang') != lang:
            item['ocr_lang'] = lang
            return True
        return old_value != best

    def normalize_auto_wrap_source_text(self, text):
        """구버전 호환용 기본 자동 줄내림 원문 정리."""
        return self.normalize_auto_wrap_source_text_for_lang(text, lang='ja')

    def auto_wrap_text_for_item(self, item):
        """현재 번역문을 텍스트 박스 폭에 맞춰 자동 줄내림한다.

        - 영어/한국어는 자동 줄내림과 자동 크기조정을 같은 fit 로직으로 처리한다.
        - 일본어/중국어는 기존 줄내림 동작을 유지한다.
        """
        lang = self.item_ocr_language_for_layout(item)
        if lang in ('en', 'ko'):
            return self._fit_space_language_text_for_item(item, lang=lang)

        rect = item.get('rect')
        if not rect or len(rect) < 4:
            return False

        original = str(item.get('translated_text', '') or '')
        if not original.strip():
            return False

        source_text = self.normalize_auto_wrap_source_text(original)
        if not source_text.strip():
            return False

        self.ensure_item_style_for_auto(item)

        try:
            box_w = max(1, int(rect[2]))
            box_h = max(1, int(rect[3]))
        except Exception:
            return False

        family = item.get('font_family') or self.cb_font.currentFont().family()
        start_size = int(item.get('font_size', self.sb_font_size.value()) or self.sb_font_size.value())
        stroke = int(item.get('stroke_width', 0) or 0)

        # 기존 줄내림 기준은 유지하되, 하단을 넘으면 크기를 줄이면서 다시 감는다.
        max_w = max(1, int(box_w * 1.00) - stroke * 2)
        max_h = max(1, int(box_h) - stroke * 2)

        min_size = 5
        chosen_size = max(min_size, start_size)
        chosen_lines = None
        chosen_height = None

        for size in range(max(min_size, start_size), min_size - 1, -1):
            font = QFont(family)
            font.setPixelSize(size)
            fm = QFontMetrics(font)
            lines = self.auto_wrap_lines_for_metrics(source_text, fm, max_w, protect_short_tokens=True)
            line_count = max(1, len(lines))
            total_h = fm.lineSpacing() * line_count

            chosen_size = size
            chosen_lines = lines
            chosen_height = total_h

            if total_h <= max_h:
                break

        if chosen_lines is None:
            return False

        wrapped = '\n'.join(chosen_lines).strip()
        changed = False

        if wrapped and wrapped != original:
            item['translated_text'] = wrapped
            changed = True

        if int(item.get('font_size', start_size) or start_size) != chosen_size:
            item['font_size'] = int(chosen_size)
            changed = True

        if changed and chosen_height is not None and chosen_height > max_h:
            item['auto_wrap_height_overflow'] = True
        elif changed:
            item.pop('auto_wrap_height_overflow', None)

        return changed

    def auto_text_size_for_page(self, page_idx, refresh=False):
        changed = 0
        for item in self.auto_target_items_for_page(page_idx):
            if self.auto_text_size_item(item, page_idx=page_idx):
                changed += 1
        if refresh and page_idx == self.idx:
            self.ref_tab()
            if self.cb_mode.currentIndex() == 4:
                self.mode_chg(4)
        return changed

    def auto_linebreak_for_page(self, page_idx, refresh=False):
        changed = 0
        for item in self.auto_target_items_for_page(page_idx):
            if self.auto_wrap_text_for_item(item):
                changed += 1
        if refresh and page_idx == self.idx:
            self.ref_tab()
            if self.cb_mode.currentIndex() == 4:
                self.mode_chg(4)
        return changed

    def auto_text_size_current(self):
        if not self.paths:
            return
        self.commit_current_page_ui_to_data()
        undo_rec = self.make_project_undo_record("자동 텍스트 크기 조정")
        changed = self.auto_text_size_for_page(self.idx, refresh=True)
        if changed:
            self.append_project_undo_record(undo_rec)
        self.auto_save_project()
        self.log(f"🤖 자동 텍스트 크기 조정 완료: 현재 페이지 {changed}개")

    def auto_text_size_batch(self):
        if not self.paths:
            return
        if getattr(self, "ui_language", LANG_KO) == LANG_EN:
            msg = f"Run Batch Auto Text Size on total {len(self.paths)} page(s)?"
        else:
            msg = f"자동 텍스트 크기 조정을 총 {len(self.paths)}페이지에 실행합니다."
        if not self.confirm_batch_operation("일괄 자동 텍스트 크기 조정", msg):
            self.log("↩️ 일괄 자동 텍스트 크기 조정 취소")
            return
        self.commit_current_page_ui_to_data()
        undo_rec = self.make_project_undo_record("일괄 자동 텍스트 크기 조정", full_project=True)
        total = 0
        pages = 0
        for i in range(len(self.paths)):
            changed = self.auto_text_size_for_page(i, refresh=False)
            if changed:
                pages += 1
                total += changed
        if total:
            self.append_project_undo_record(undo_rec)
        self.ref_tab()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
        self.auto_save_project()
        self.log(f"🤖 일괄 자동 텍스트 크기 조정 완료: {pages}페이지 / {total}개")

    def auto_linebreak_current(self):
        if not self.paths:
            return
        self.commit_current_page_ui_to_data()
        undo_rec = self.make_project_undo_record("자동 줄 내림")
        changed = self.auto_linebreak_for_page(self.idx, refresh=True)
        if changed:
            self.append_project_undo_record(undo_rec)
        self.auto_save_project()
        self.log(f"🤖 자동 줄 내림 완료: 현재 페이지 {changed}개")

    def auto_linebreak_batch(self):
        if not self.paths:
            return
        if getattr(self, "ui_language", LANG_KO) == LANG_EN:
            msg = f"Run Batch Auto Line Break on total {len(self.paths)} page(s)?"
        else:
            msg = f"자동 줄 내림을 총 {len(self.paths)}페이지에 실행합니다."
        if not self.confirm_batch_operation("일괄 자동 줄 내림", msg):
            self.log("↩️ 일괄 자동 줄 내림 취소")
            return
        self.commit_current_page_ui_to_data()
        undo_rec = self.make_project_undo_record("일괄 자동 줄 내림", full_project=True)
        total = 0
        pages = 0
        for i in range(len(self.paths)):
            changed = self.auto_linebreak_for_page(i, refresh=False)
            if changed:
                pages += 1
                total += changed
        if total:
            self.append_project_undo_record(undo_rec)
        self.ref_tab()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
        self.auto_save_project()
        self.log(f"🤖 일괄 자동 줄 내림 완료: {pages}페이지 / {total}개")

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

        rect = data_item.get('rect') or [0, 0, 0, 0]
        try:
            x = int(round(float(rect[0]) + float(data_item.get('x_off', 0) or 0)))
            y = int(round(float(rect[1]) + float(data_item.get('y_off', 0) or 0)))
            w = int(round(float(rect[2])))
            h = int(round(float(rect[3])))
        except Exception:
            return

        if w <= 0 or h <= 0:
            return

        for key in ('mask_merge', 'mask_inpaint', 'mask_merge_off', 'mask_inpaint_off'):
            mask = curr.get(key)
            if not isinstance(mask, np.ndarray):
                continue
            mh, mw = mask.shape[:2]
            x1 = max(0, x)
            y1 = max(0, y)
            x2 = min(mw, x + w)
            y2 = min(mh, y + h)
            if x2 <= x1 or y2 <= y1:
                continue
            if mask.ndim == 2:
                mask[y1:y2, x1:x2] = 0
            else:
                mask[y1:y2, x1:x2, :] = 0
            curr[key] = mask

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
        self.push_text_line_undo('텍스트 삭제', include_masks=True)

        deleted_count = 0
        for d in list(data_items):
            self.clear_masks_for_text_data(d)
            try:
                curr['data'].remove(d)
                deleted_count += 1
            except ValueError:
                pass

        if deleted_count <= 0:
            return False

        # 삭제 후 우측 텍스트 행 라인넘버(ID)를 1부터 다시 정렬한다.
        # 분석도/마스크 탭의 왼쪽 번호 박스도 같은 data id를 보므로 즉시 다시 그린다.
        self.renumber_text_items_for_current_page(curr)

        self.ref_tab()
        self.refresh_after_text_line_change(autosave=True)
        self.log((f"🗑️ Text deletion complete: {deleted_count} items / IDs reordered" if self.ui_language == LANG_EN else f"🗑️ 텍스트 삭제 완료: {deleted_count}개 / 번호 재정렬"))
        return True

    def copy_text_data_items(self, data_items=None):
        if data_items is None:
            data_items = self.selected_text_data_items()
        data_items = [d for d in (data_items or []) if isinstance(d, dict)]
        if not data_items:
            self.log("⚠️ 복사할 텍스트가 없습니다.")
            return False

        self.text_clipboard = [copy.deepcopy(d) for d in data_items]
        self.text_clipboard_is_plain = False
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
            d.pop('pending_new_text', None)
            d.pop('force_show', None)
            new_ids.append(d['id'])
            curr.setdefault('data', []).append(d)

        self.ref_tab()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
            self.reselect_text_items(new_ids)
        self.auto_save_project()
        self.log(f"📋 텍스트 붙여넣기 완료: {len(new_ids)}개")
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
            font_size = int(self.sb_font_size.value())
        except Exception:
            font_size = 24
        w = 320
        h = max(70, int(font_size * (line_count + 1.4)))
        return {
            'id': 0,
            'text': text,
            'translated_text': text,
            'rect': [0, 0, w, h],
            'use_inpaint': True,
            'font_family': self.cb_font.currentFont().family() if hasattr(self, 'cb_font') else 'Arial',
            'font_size': font_size,
            'stroke_width': int(self.sb_strk.value()) if hasattr(self, 'sb_strk') else 0,
            'text_color': str(getattr(self, 'default_text_color', '#000000') or '#000000'),
            'stroke_color': str(getattr(self, 'default_stroke_color', '#FFFFFF') or '#FFFFFF'),
            'align': getattr(self, 'default_align', 'center'),
            'x_off': 0,
            'y_off': 0,
            'manual_text_rect': True,
            'text_anchor_mode': 'text',
            'force_show': True,
        }

    def load_plain_text_clipboard_for_paste(self):
        text = self.windows_clipboard_text()
        item = self.make_text_clipboard_item_from_plain_text(text)
        if not item:
            return False
        self.text_clipboard = [item]
        self.text_clipboard_is_plain = True
        return True

    def enter_text_paste_mode(self):
        """Ctrl+V는 즉시 붙여넣지 않고, 커서에 미리보기만 붙인 뒤 클릭 위치에 확정한다."""
        if self.cb_mode.currentIndex() != 4:
            return False
        if not self.text_clipboard or bool(getattr(self, "text_clipboard_is_plain", False)):
            # Windows 클립보드 텍스트로 만든 임시 붙여넣기라면, Ctrl+V 때마다 최신 클립보드 내용으로 갱신한다.
            if not self.load_plain_text_clipboard_for_paste() and not self.text_clipboard:
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
        dlg = TextAdvancedEffectDialog(data_items[0], self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return False
        values = dlg.values()
        selected_ids = [d.get('id') for d in data_items]
        self.push_page_text_undo('텍스트 고급 효과 변경')
        for d in data_items:
            for k, v in values.items():
                d[k] = v
            try:
                if bool(d.get('manual_text_rect')) or str(d.get('text_anchor_mode') or '').lower() == 'text':
                    self.shrink_text_rect_to_content(d)
            except Exception:
                pass
        self.auto_save_project()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
            self.reselect_text_items(selected_ids)
        self.log(f"🎨 텍스트 고급 효과 적용: {len(data_items)}개")
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
        self.push_page_text_undo('텍스트 객체 변환')
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
            d['object_source_text'] = str(d.get('translated_text') or '')
            converted += 1
        if not converted:
            self.log("⚠️ 객체 변환에 실패했습니다.")
            return False
        self.ref_tab()
        self.auto_save_project()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
            self.reselect_text_items(selected_ids)
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

        self.push_page_text_undo('텍스트 객체 일부 지우기')
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
        self.auto_save_project()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
            self.reselect_text_items(changed_ids)
        self.log(f"🧽 텍스트 객체 일부 지우기 완료: {len(changed_ids)}개")
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
        act_copy = menu.addAction("텍스트 복사")
        act_paste = menu.addAction("텍스트 붙여넣기")
        act_paste.setEnabled(bool(self.text_clipboard))
        menu.addSeparator()
        act_effect = menu.addAction(self.tr_ui("문자/획 그라데이션..."))
        act_effect.setEnabled(bool(editable_text_items))
        act_skew = menu.addAction(self.tr_ui("평행사변형 변형"))
        act_skew.setCheckable(True)
        act_skew.setChecked(bool(text_item.data.get('_skew_mode', False)))
        act_skew.setEnabled(len(editable_text_items) == 1 and not bool(text_item.data.get('rasterized_text')))
        act_trapezoid = menu.addAction(self.tr_ui("사다리꼴 변형"))
        act_trapezoid.setCheckable(True)
        act_trapezoid.setChecked(bool(text_item.data.get('_trapezoid_mode', False)))
        act_trapezoid.setEnabled(len(editable_text_items) == 1 and not bool(text_item.data.get('rasterized_text')))
        act_arc = menu.addAction(self.tr_ui("부채꼴 변형"))
        act_arc.setCheckable(True)
        act_arc.setChecked(bool(text_item.data.get('_arc_mode', False)))
        act_arc.setEnabled(len(editable_text_items) == 1 and not bool(text_item.data.get('rasterized_text')))
        act_transform = menu.addAction("텍스트 변형")
        act_transform.setCheckable(True)
        act_transform.setChecked(bool(text_item.data.get('_transform_mode', False)))
        act_transform.setEnabled(not bool(text_item.data.get('rasterized_text')))
        menu.addSeparator()
        act_rasterize = menu.addAction(self.tr_ui("텍스트를 객체로 변환"))
        act_rasterize.setEnabled(bool(editable_text_items))
        menu.addSeparator()
        act_delete = menu.addAction(self.tr_ui("텍스트 삭제"))

        chosen = menu.exec(global_pos)
        if chosen == act_copy:
            self.copy_text_data_items(data_items or [text_item.data])
        elif chosen == act_paste:
            self.paste_text_clipboard_at(scene_pos)
        elif chosen == act_effect:
            self.open_text_advanced_effect_dialog(editable_text_items)
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
            old_suppress = getattr(self, "_suppress_mode_undo", False)
            self._suppress_mode_undo = True
            try:
                self.mode_chg(4)
            finally:
                self._suppress_mode_undo = old_suppress
            if selected_id is not None:
                self.reselect_text_items([selected_id])
        self.auto_save_project()

    def toggle_text_skew_mode(self, data_item):
        """최종화면 텍스트 기울이기 직접 조정 모드 토글."""
        if self.cb_mode.currentIndex() != 4 or not data_item or data_item.get('rasterized_text'):
            return

        enabled = not bool(data_item.get('_skew_mode', False))
        self.clear_text_transform_modes(except_data=data_item)
        selected_id = data_item.get('id')

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
            old_suppress = getattr(self, "_suppress_mode_undo", False)
            self._suppress_mode_undo = True
            try:
                self.mode_chg(4)
            finally:
                self._suppress_mode_undo = old_suppress
            if selected_id is not None:
                self.reselect_text_items([selected_id])
        self.auto_save_project()

    def toggle_text_trapezoid_mode(self, data_item):
        """최종화면 텍스트 사다리꼴 변형 직접 조정 모드 토글."""
        if self.cb_mode.currentIndex() != 4 or not data_item or data_item.get('rasterized_text'):
            return

        enabled = not bool(data_item.get('_trapezoid_mode', False))
        self.clear_text_transform_modes(except_data=data_item)
        selected_id = data_item.get('id')

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
            old_suppress = getattr(self, "_suppress_mode_undo", False)
            self._suppress_mode_undo = True
            try:
                self.mode_chg(4)
            finally:
                self._suppress_mode_undo = old_suppress
            if selected_id is not None:
                self.reselect_text_items([selected_id])
        self.auto_save_project()

    def toggle_text_arc_mode(self, data_item):
        """최종화면 텍스트 부채꼴 변형 직접 조정 모드 토글."""
        if self.cb_mode.currentIndex() != 4 or not data_item or data_item.get('rasterized_text'):
            return

        enabled = not bool(data_item.get('_arc_mode', False))
        self.clear_text_transform_modes(except_data=data_item)
        selected_id = data_item.get('id')

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
            old_suppress = getattr(self, "_suppress_mode_undo", False)
            self._suppress_mode_undo = True
            try:
                self.mode_chg(4)
            finally:
                self._suppress_mode_undo = old_suppress
            if selected_id is not None:
                self.reselect_text_items([selected_id])
        self.auto_save_project()

    def show_final_background_context_menu(self, global_pos, scene_pos):
        if self.cb_mode.currentIndex() != 4:
            return
        self.last_canvas_context_pos = scene_pos

        menu = QMenu(self)
        act_paste = menu.addAction("텍스트 붙여넣기")
        act_paste.setEnabled(bool(self.text_clipboard))
        act_add = menu.addAction("텍스트 추가")

        chosen = menu.exec(global_pos)
        if chosen == act_paste:
            self.paste_text_clipboard_at(scene_pos)
        elif chosen == act_add:
            self.set_tool("final_text")
            try:
                self.create_final_text_at(int(scene_pos.x()), int(scene_pos.y()), centered=False)
            except Exception:
                pass

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
        act_effect = menu.addAction(self.tr_ui("문자/획 그라데이션..."))
        act_effect.setEnabled(bool(editable_text_items))
        act_skew = menu.addAction(self.tr_ui("평행사변형 변형"))
        act_skew.setEnabled(len(editable_text_items) == 1)
        act_trapezoid = menu.addAction(self.tr_ui("사다리꼴 변형"))
        act_trapezoid.setEnabled(len(editable_text_items) == 1)
        act_arc = menu.addAction(self.tr_ui("부채꼴 변형"))
        act_arc.setEnabled(len(editable_text_items) == 1)
        act_rasterize = menu.addAction(self.tr_ui("텍스트를 객체로 변환"))
        act_rasterize.setEnabled(bool(editable_text_items))
        menu.addSeparator()
        act_delete = menu.addAction("텍스트행 삭제")
        chosen = menu.exec(self.tab.viewport().mapToGlobal(pos))
        if chosen == act_effect:
            self.open_text_advanced_effect_dialog(editable_text_items)
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
                        self.push_page_text_undo('텍스트 객체 지우개')
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

    def on_text_table_rows_reordered(self):
        """우측 텍스트 행 드래그 후 data 순서를 표 순서에 맞추고 ID를 재정렬한다."""
        if self._syncing_selection or self._table_check_lock:
            return
        curr = self.data.get(self.idx)
        if not curr:
            return

        id_order = []
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

        # 058에서 프로젝트 스냅샷 Undo로 바꾼 뒤 탭 이동/표 갱신 렉이 커져
        # 행 순서 변경도 기존의 가벼운 page undo 방식으로 되돌린다.
        self.push_text_line_undo('텍스트 행 순서 변경')

        by_id = {str(d.get('id')): d for d in old_data}
        new_data = [by_id[i] for i in id_order if i in by_id]
        for d in old_data:
            if d not in new_data:
                new_data.append(d)

        curr['data'] = new_data
        self.renumber_text_items_for_current_page(curr)
        self.ref_tab()
        self.refresh_after_text_line_change(autosave=True)
        self.log("↕️ Text row order changed / IDs reordered" if self.ui_language == LANG_EN else "↕️ 텍스트 행 순서 변경 완료 / 번호 재정렬")

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

