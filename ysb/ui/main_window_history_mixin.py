from ysb.ui.main_window_support import *


class MainWindowHistoryMixin:

    def on_final_paint_opacity_changed(self, value):
        self.final_paint_opacity = max(1, min(100, int(value)))
        self.log(f"🖌️ 최종 브러시 불투명도: {self.final_paint_opacity}%")

    def update_final_paint_option_bar_visibility(self):
        # 최종 브러시 옵션도 상단 공유 옵션바에 편입한다.
        if hasattr(self, "final_paint_option_bar"):
            self.final_paint_option_bar.hide()
        if hasattr(self, "sb_final_paint_opacity"):
            self.sb_final_paint_opacity.blockSignals(True)
            try:
                self.sb_final_paint_opacity.setValue(int(self.final_paint_opacity))
            finally:
                self.sb_final_paint_opacity.blockSignals(False)
        try:
            if hasattr(self, "refresh_shared_option_bar"):
                self.refresh_shared_option_bar()
        except Exception:
            pass

    def update_final_paint_z_order(self):
        """최종 페인팅 레이어는 항상 아래/위 두 장으로 고정한다."""
        below = getattr(self.view, "final_paint_item", None)
        above = getattr(self.view, "final_paint_above_item", None)
        if below is not None:
            below.setZValue(8)
        if above is not None:
            above.setZValue(80)

    def on_final_paint_above_text_toggled(self, checked):
        # 기존에 그린 레이어의 위치는 바꾸지 않는다.
        # 이 토글은 이후 새로 그리는 브러시가 들어갈 레이어만 선택한다.
        old_state = bool(getattr(self, "_last_final_paint_above_text", getattr(self, "final_paint_above_text", False)))
        new_state = bool(checked)
        if (
            old_state != new_state
            and not getattr(self, "_project_undo_restore_lock", False)
            and not getattr(self, "is_loading_project", False)
            and not getattr(self, "is_page_loading", False)
            and not getattr(self, "is_batch_running", False)
        ):
            try:
                rec = self.make_project_undo_record("텍스트 위 페인팅 ON/OFF")
                rec.setdefault("ui_state", self.current_project_ui_state())
                rec["ui_state"]["final_paint_above_text"] = old_state
                self.append_project_undo_record(rec)
            except Exception:
                pass
        self.final_paint_above_text = new_state
        self._last_final_paint_above_text = new_state
        if hasattr(self, "act_final_paint_above_text"):
            self.act_final_paint_above_text.setText("T↑" if self.final_paint_above_text else "T↓")
        state = "ON" if checked else "OFF"
        self.log(f"🎚️ 새 브러시를 텍스트 위에 그리기: {state}")
        self.auto_save_project()

    def toggle_final_paint_above_text(self):
        if hasattr(self, "act_final_paint_above_text"):
            self.act_final_paint_above_text.toggle()
        else:
            self.on_final_paint_above_text_toggled(not self.final_paint_above_text)

    def adjust_final_paint_opacity(self, delta):
        value = max(1, min(100, int(self.final_paint_opacity) + int(delta)))
        self.final_paint_opacity = value
        if hasattr(self, "sb_final_paint_opacity"):
            self.sb_final_paint_opacity.blockSignals(True)
            try:
                self.sb_final_paint_opacity.setValue(value)
            finally:
                self.sb_final_paint_opacity.blockSignals(False)
        self.log(f"🖌️ 최종 브러시 불투명도: {value}%")

    def final_paint_rgba_from_value(self, value):
        if value is None:
            return None
        try:
            if isinstance(value, (bytes, bytearray)):
                arr = np.frombuffer(value, np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
            elif isinstance(value, np.ndarray):
                img = value.copy()
            else:
                return None

            if img is None:
                return None
            if img.ndim == 2:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGBA)
            elif img.ndim == 3 and img.shape[2] == 3:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA)
            elif img.ndim == 3 and img.shape[2] == 4:
                # cv2 imdecode는 BGRA이므로 RGBA로 변환
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
            return img
        except Exception:
            return None

    def compose_final_paint_on_bgr(self, base_bgr, paint_value):
        if base_bgr is None:
            return None
        base = base_bgr.copy()
        paint = self.final_paint_rgba_from_value(paint_value)
        if paint is None:
            return base
        h, w = base.shape[:2]
        if paint.shape[0] != h or paint.shape[1] != w:
            paint = cv2.resize(paint, (w, h), interpolation=cv2.INTER_LINEAR)
        alpha = paint[:, :, 3:4].astype(np.float32) / 255.0
        rgb = paint[:, :, :3].astype(np.float32)
        bgr = rgb[:, :, ::-1]
        out = base.astype(np.float32) * (1.0 - alpha) + bgr * alpha
        return np.clip(out, 0, 255).astype(np.uint8)

    def final_base_image_for_page(self, page_idx):
        curr = self.data.get(page_idx)
        if not curr:
            return None
        base = self.bg_clean_to_np_image(curr.get('bg_clean'))
        if base is not None:
            return base
        return self.get_source_display_image(page_idx)

    def on_final_paint_edited(self):
        if self.is_page_loading or self.is_batch_running:
            return
        curr = self.data.get(self.idx)
        if not curr:
            return
        curr['final_paint'] = self.view.get_final_paint_png_bytes()
        if hasattr(self.view, "get_final_paint_above_png_bytes"):
            curr['final_paint_above'] = self.view.get_final_paint_above_png_bytes()
        self.log("💾 최종 페인팅 자동 저장")
        self.auto_save_project()

    def _hide_eyedropper_color_feedback(self):
        try:
            popup = getattr(self, '_eyedropper_color_popup', None)
            if popup is not None:
                popup.hide()
        except Exception:
            pass

    def _show_eyedropper_color_feedback(self, hex_color):
        try:
            QApplication.clipboard().setText(str(hex_color))
        except Exception:
            pass
        try:
            html = (
                f'<div style="white-space:nowrap; font-weight:bold;">'
                f'<span style="display:inline-block; width:14px; height:14px; border-radius:7px; '
                f'background:{hex_color}; border:1px solid #222;">&nbsp;&nbsp;&nbsp;</span> '
                f'{hex_color}</div>'
            )
            popup = getattr(self, '_eyedropper_color_popup', None)
            if popup is None:
                popup = QLabel()
                popup.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
                popup.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                popup.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
                popup.setTextFormat(Qt.TextFormat.RichText)
                self._eyedropper_color_popup = popup
            popup.setText(html)
            if self.is_light_theme():
                popup.setStyleSheet('QLabel { background:#ffffff; color:#111827; border:1px solid #cfd7e5; border-radius:4px; padding:4px; }')
            else:
                popup.setStyleSheet('QLabel { background:#1f2430; color:#ffffff; border:1px solid #4b5563; border-radius:4px; padding:4px; }')
            popup.adjustSize()
            # 좌클릭을 누르고 있는 동안만 보이는 색상 팝업이다.
            # QToolTip을 새로 띄우지 않고 같은 QLabel을 갱신해서 깜빡임을 줄인다.
            popup.move(QCursor.pos() + QPoint(4, 4))
            if not popup.isVisible():
                popup.show()
            else:
                popup.update()
        except Exception:
            pass

    def _apply_eyedropper_color_from_bgr(self, b, g, r, source_label="스포이드"):
        self.final_paint_color = QColor(int(r), int(g), int(b)).name(QColor.NameFormat.HexRgb).upper()
        self.update_color_button_styles()
        self._show_eyedropper_color_feedback(self.final_paint_color)
        self.log(f"🧪 {source_label}: {self.final_paint_color} 클립보드 복사")

    def pick_final_paint_color_from_scene(self, x, y):
        if self.cb_mode.currentIndex() != 4:
            return
        curr = self.data.get(self.idx)
        if not curr:
            return
        base = self.final_base_image_for_page(self.idx)
        if base is None:
            return
        img = self.compose_final_paint_on_bgr(base, curr.get('final_paint'))
        img = self.compose_final_paint_on_bgr(img, curr.get('final_paint_above'))
        h, w = img.shape[:2]
        if x < 0 or y < 0 or x >= w or y >= h:
            return
        b, g, r = [int(v) for v in img[y, x]]
        self._apply_eyedropper_color_from_bgr(b, g, r, "스포이드")

    def pick_final_paint_color_from_source_scene(self, x, y):
        if self.cb_mode.currentIndex() != 4:
            return
        img = self.get_source_display_image(self.idx)
        if img is None:
            return
        h, w = img.shape[:2]
        if x < 0 or y < 0 or x >= w or y >= h:
            return
        b, g, r = [int(v) for v in img[y, x]]
        self._apply_eyedropper_color_from_bgr(b, g, r, "원본 비교창 스포이드")

    def apply_final_paint_to_background(self):
        if self.cb_mode.currentIndex() != 4:
            self.log("⚠️ 최종화면에서만 사용할 수 있습니다.")
            return
        curr = self.data.get(self.idx)
        if not curr:
            return
        paint_bytes = self.view.get_final_paint_png_bytes()
        paint_above_bytes = self.view.get_final_paint_above_png_bytes() if hasattr(self.view, "get_final_paint_above_png_bytes") else None
        if paint_bytes is None and paint_above_bytes is None:
            self.log("⚠️ 반영할 최종 페인팅이 없습니다.")
            return

        base = self.final_base_image_for_page(self.idx)
        if base is None:
            self.log("⚠️ 반영할 배경 이미지가 없습니다.")
            return

        merged = self.compose_final_paint_on_bgr(base, paint_bytes)
        merged = self.compose_final_paint_on_bgr(merged, paint_above_bytes)
        encoded = self.encode_np_image_to_png_bytes(merged)
        if encoded is not None:
            curr['bg_clean'] = encoded
        else:
            curr['bg_clean'] = merged

        # "원본으로 반영"은 실제 파일을 덮어쓰지 않고,
        # 프로젝트 내부 작업중 원본(working_source)을 최신 기준으로 교체한다.
        self.set_working_source_image(curr, merged)

        curr['final_paint'] = None
        curr['final_paint_above'] = None
        self.auto_save_project()
        self.mode_chg(self.cb_mode.currentIndex())
        self.log("📌 최종 페인팅을 원본 탭 기준 이미지로 반영했습니다.")

    def create_final_text_at(self, x, y, centered=True):
        if self.cb_mode.currentIndex() != 4:
            return
        curr = self.data.get(self.idx)
        if not curr:
            return

        data_list = curr.setdefault('data', [])
        max_id = 0
        for item in data_list:
            try:
                max_id = max(max_id, int(item.get('id', 0)))
            except Exception:
                pass
        new_id = max_id + 1

        w, h = 260, 80
        temp_data = {
            'id': new_id,
            'text': '',
            'translated_text': '',
            'rect': [int(x - w / 2), int(y - h / 2), w, h] if centered else [int(x), int(y), w, h],
            'use_inpaint': True,
            'font_family': self.cb_font.currentFont().family(),
            'font_size': int(self.sb_font_size.value()),
            'stroke_width': int(self.sb_strk.value()),
            'text_color': str(self.default_text_color or "#000000"),
            'stroke_color': str(self.default_stroke_color or "#FFFFFF"),
            'align': self.default_align,
            'x_off': 0,
            'y_off': 0,
            'manual_text_rect': True,
            'text_anchor_mode': 'text',
            'force_show': True,
            'pending_new_text': True,
        }

        # 아직 우측 텍스트 행에는 넣지 않는다.
        # 실제 텍스트 입력이 완료될 때 finish_inline_text_edit()에서 data_list에 추가한다.
        item = TypesettingItem(
            temp_data,
            self.cb_font.currentFont().family(),
            self.sb_font_size.value(),
            self.sb_strk.value(),
            self.on_text_item_moved,
            text_color=self.default_text_color,
            stroke_color=self.default_stroke_color,
            align=self.default_align,
        )
        item.main_window = self
        self.view.scene.addItem(item)
        item.setZValue(30)
        item.setSelected(True)
        self.start_inline_text_edit(item)
        self.log(f"➕ 새 텍스트 영역 생성 대기 (ID: {new_id})")

    def on_view_mask_edited(self):
        # 붓질이 끝났을 때 현재 페이지의 마스크만 자동 저장한다.
        if self.is_page_loading or self.is_batch_running:
            return

        curr = self.data.get(self.idx)
        if not curr:
            return

        m = self.view.get_mask_np()
        if m is None:
            return

        mode = self.cb_mode.currentIndex()
        if mode == 2:
            self.set_active_mask(curr, m, mode)
            curr['mask_toggle_enabled'] = self.mask_toggle_enabled
            self.log("💾 텍스트 마스크 자동 저장")
        elif mode == 3:
            self.set_active_mask(curr, m, mode)
            curr['mask_toggle_enabled'] = self.mask_toggle_enabled
            self.log("💾 페인팅 마스크 자동 저장")
        else:
            return

        self.auto_save_project()

    def flush_pending_log_messages(self):
        pending = list(getattr(self, "_pending_log_messages", []) or [])
        if not pending or not hasattr(self, "log_w") or self.log_w is None:
            return
        self._pending_log_messages = []
        for msg in pending:
            try:
                self.log_w.append(str(msg))
            except Exception:
                pass
        try:
            self.log_w.verticalScrollBar().setValue(self.log_w.verticalScrollBar().maximum())
        except Exception:
            pass

    def log(self, m):
        try:
            m = self.tr_msg(m)
        except Exception:
            pass
        try:
            if not bool(getattr(self, "show_paths_in_log", False)):
                m = hide_paths_in_log_text(m, self.tr_ui("경로 숨김"))
        except Exception:
            pass
        if not hasattr(self, "log_w") or self.log_w is None:
            try:
                self._pending_log_messages.append(str(m))
            except Exception:
                self._pending_log_messages = [str(m)]
            try:
                print(str(m))
            except Exception:
                pass
            return
        try:
            self.log_w.append(str(m))
            self.log_w.verticalScrollBar().setValue(self.log_w.verticalScrollBar().maximum())
        except Exception:
            try:
                print(str(m))
            except Exception:
                pass

    def get_special_shortcuts(self):
        symbol_map = {}
        for key, (_label, symbol) in TEXT_SYMBOLS.items():
            symbol_map[symbol] = self.shortcut_settings.seq("text_" + key)
        return symbol_map

    def get_linebreak_shortcut(self):
        return self.shortcut_settings.seq("text_linebreak")


    def _ocr_language_options_for_provider(self, provider=None):
        provider = str(provider or getattr(getattr(self, "api_settings", None), "selected_ocr_provider", "clova") or "clova")
        if provider == "google_vision":
            return [("영어", "en"), ("일본어", "ja"), ("중국어", "zh"), ("한국어", "ko")]
        if provider == "local_paddle_ocr":
            return [("일본어", "ja"), ("영어", "en"), ("한국어", "ko"), ("중국어", "zh")]
        if provider == "local_manga_ocr":
            return [("일본어", "ja")]
        # CLOVA 기본
        return [("일본어", "ja"), ("중국어", "zh"), ("한국어", "ko")]

    def _current_ocr_language_value(self):
        settings = getattr(self, "api_settings", None)
        provider = str(getattr(settings, "selected_ocr_provider", "clova") or "clova")
        if provider == "google_vision":
            return str(getattr(settings, "google_vision_ocr_language", "en") or "en")
        if provider == "local_paddle_ocr":
            return str(getattr(settings, "local_paddle_ocr_language", "ja") or "ja")
        if provider == "local_manga_ocr":
            return "ja"
        return str(getattr(settings, "clova_ocr_language", "ja") or "ja")

    def refresh_ocr_language_combo(self, save=False):
        combo = getattr(self, "cb_ocr_language", None)
        if combo is None:
            return
        provider = str(getattr(getattr(self, "api_settings", None), "selected_ocr_provider", "clova") or "clova")
        current = self._current_ocr_language_value()
        combo.blockSignals(True)
        try:
            combo.clear()
            for label, value in self._ocr_language_options_for_provider(provider):
                combo.addItem(self.tr_ui(label) if hasattr(self, "tr_ui") else label, value)
            if not self.set_combo_current_data(combo, current):
                combo.setCurrentIndex(0 if combo.count() else -1)
        finally:
            combo.blockSignals(False)

    def on_ocr_language_toolbar_changed(self, *_args):
        combo = getattr(self, "cb_ocr_language", None)
        if combo is None or not hasattr(self, "api_settings"):
            return
        value = str(combo.currentData() or combo.currentText() or "").strip()
        if not value:
            return
        provider = str(getattr(self.api_settings, "selected_ocr_provider", "clova") or "clova")
        if provider == "google_vision":
            self.api_settings.google_vision_ocr_language = value
        elif provider == "local_paddle_ocr":
            self.api_settings.local_paddle_ocr_language = value
        elif provider == "local_manga_ocr":
            value = "ja"
        else:
            self.api_settings.clova_ocr_language = value
        try:
            ApiSettingsStore.save(self.api_settings)
            apply_settings_to_config(self.api_settings)
        except Exception:
            pass

    def _chunk_attr_for_provider(self, provider):
        return {
            "openai": "openai_chunk_size",
            "deepseek": "deepseek_chunk_size",
            "google": "google_translate_chunk_size",
            "gemini": "gemini_chunk_size",
            "custom": "custom_translation_chunk_size",
        }.get(str(provider or "openai"), "openai_chunk_size")

    def on_translation_provider_changed(self, save=True):
        provider = self.cb_trans_provider.currentData() or "openai"
        if save and hasattr(self, "api_settings"):
            try:
                self.api_settings.selected_translation_provider = str(provider)
                ApiSettingsStore.save(self.api_settings)
                apply_settings_to_config(self.api_settings)
            except Exception:
                pass

    def on_translation_chunk_changed(self, value):
        # v2.1.0 이후 상단 툴바 묶음 입력은 제거되었다.
        # 구버전/호환 위젯이 남아 있을 경우만 캐시에 반영한다.
        provider = self.cb_trans_provider.currentData() or "openai"
        self.trans_chunk_sizes[provider] = int(value)

    def get_current_translation_chunk_size(self):
        provider = self.cb_trans_provider.currentData() or "openai"
        attr = self._chunk_attr_for_provider(provider)
        try:
            value = int(getattr(self.api_settings, attr, 0) or 0)
        except Exception:
            value = 0
        if value <= 0:
            value = int(self.trans_chunk_sizes.get(provider, 8 if provider == "deepseek" else (50 if provider == "google" else (10 if provider == "gemini" else 20))))
        return max(1, min(value, 100))

    def open_text_number_width_dialog(self):
        """분석도 노란 텍스트 번호 박스 너비를 즉시 조정한다."""
        dlg = QDialog(self)
        dlg.setWindowTitle("텍스트 넘버 크기 변경")
        dlg.resize(360, 120)

        layout = QVBoxLayout(dlg)
        info = QLabel("분석도에 표시되는 노란 텍스트 번호 박스의 너비값을 조정합니다.")
        info.setWordWrap(True)
        layout.addWidget(info)

        line = QHBoxLayout()
        line.addWidget(QLabel("너비값"))
        spin = QSpinBox()
        spin.setRange(20, 300)
        spin.setValue(int(getattr(self, "analysis_number_box_width", 40)))
        spin.setSuffix(" px")
        spin.setKeyboardTracking(True)
        spin.selectAll()
        line.addWidget(spin, 1)
        layout.addLayout(line)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)

        old_value = int(getattr(self, "analysis_number_box_width", 40))

        def apply_value(value):
            self.analysis_number_box_width = int(value)
            self.save_app_options_cache()
            if self.cb_mode.currentIndex() == 1:
                self.mode_chg(1)

        spin.valueChanged.connect(apply_value)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)

        spin.setFocus()
        spin.selectAll()

        result = dlg.exec()
        if result != QDialog.DialogCode.Accepted:
            self.analysis_number_box_width = old_value
            self.save_app_options_cache()
            if self.cb_mode.currentIndex() == 1:
                self.mode_chg(1)
        else:
            apply_value(spin.value())
            self.log(f"🔢 텍스트 넘버 박스 너비 변경: {spin.value()}px")

    def open_shortcut_settings_dialog(self):
        dlg = ShortcutSettingsDialog(self.shortcut_settings, self, show_cache_path=bool(getattr(self, "show_cache_paths_in_settings", False)))
        if not dlg.exec():
            return
        new_settings = dlg.get_settings()
        # 단축키 창에서 비활성화된 기존 단축키 상태를 유지하면서 매크로도 보존한다.
        if not hasattr(new_settings, "macros"):
            new_settings.macros = getattr(self.shortcut_settings, "macros", [])
        self.apply_pending_item_preset_disables_for_shortcut_settings(getattr(dlg, "_pending_disabled_item_presets", set()), new_settings)
        if not self.resolve_item_preset_conflicts_for_new_shortcut_settings(new_settings, parent=self, source_label="단축키"):
            self.log("↩️ 단축키 설정 저장 취소: 개별 글꼴 프리셋 단축키 충돌")
            return
        self.shortcut_settings = new_settings
        ShortcutSettingsStore.save(self.shortcut_settings)
        self.apply_shortcuts()
        self.log("⌨️ 단축키 설정 캐시 저장 완료")

    def open_macro_settings_dialog(self):
        dlg = MacroSettingsDialog(self.shortcut_settings, self)
        if not dlg.exec():
            return
        new_settings = dlg.get_settings()
        self.apply_pending_item_preset_disables_for_shortcut_settings(getattr(dlg, "_pending_disabled_item_presets", set()), new_settings)
        if not self.resolve_item_preset_conflicts_for_new_shortcut_settings(new_settings, parent=self, source_label="매크로"):
            self.log("↩️ 매크로 설정 저장 취소: 개별 글꼴 프리셋 단축키 충돌")
            return
        self.shortcut_settings = new_settings
        ShortcutSettingsStore.save(self.shortcut_settings)
        self.apply_shortcuts()
        self.log("🧩 매크로 설정 캐시 저장 완료")

    def macro_action_requires_undo_boundary(self, key):
        """Undo로 복원하면 상태가 꼬일 수 있는 매크로 단계인지 판단한다.

        분석/번역/인페인팅 계열은 외부/API 결과 또는 큰 처리 결과를 반영하므로
        매크로 전체를 Undo 경계로 처리한다. 그 외 일반 편집 매크로는 1개의
        Undo 스냅샷으로 되돌릴 수 있게 둔다.
        """
        key = str(key or "")
        return key in {
            "work_analyze",
            "paint_reanalyze",
            "work_translate",
            "work_inpaint",
            "batch_analyze",
            "batch_translate",
            "batch_inpaint",
        }

    def macro_actions_require_undo_boundary(self, actions):
        return any(self.macro_action_requires_undo_boundary(k) for k in (actions or []))

    def macro_wait_kind_for_key(self, key):
        """매크로에서 다음 단계로 넘어가기 전에 완료 신호를 기다려야 하는 기능."""
        if key in ("work_analyze", "paint_reanalyze"):
            return "analysis"
        if key == "work_inpaint":
            return "inpaint"
        if key.startswith("batch_"):
            return "batch"
        return ""

    def macro_batch_key_for_mode(self, mode):
        return {
            "analyze": "batch_analyze",
            "translate": "batch_translate",
            "inpaint": "batch_inpaint",
            "export": "batch_export",
        }.get(str(mode or ""), "")

    def run_macro(self, macro):
        name = str(macro.get("name", "매크로"))
        actions = list(macro.get("actions", []) or [])
        if not actions:
            self.log(f"⚠️ 매크로 '{name}'에 등록된 기능이 없습니다.")
            return

        if self.macro_running:
            QMessageBox.information(self, self.tr_ui("매크로 실행 중"), self.tr_msg("이미 실행 중인 매크로가 있습니다. 현재 매크로가 끝난 뒤 다시 실행해주세요."))
            return

        has_batch = any(str(k).startswith("batch_") for k in actions)
        if has_batch:
            ans = QMessageBox.question(
                self,
                "매크로 실행 확인",
                f"'{name}' 매크로에 일괄 작업이 포함되어 있습니다.\n실행할까요?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                self.log(f"↩️ 매크로 취소: {name}")
                return

        has_undo_boundary = self.macro_actions_require_undo_boundary(actions)
        macro_undo_record = None
        if not has_undo_boundary:
            # 일반 편집 매크로는 내부 단계별 Undo를 쌓지 않고,
            # 매크로 실행 직전 상태 1개만 저장해서 Ctrl+Z 한 번으로 되돌린다.
            full_project = any(str(k).startswith("batch_") or str(k).endswith("_batch") for k in actions)
            macro_undo_record = self.make_project_undo_record(f"매크로 실행: {name}", full_project=full_project)

        self.macro_running = True
        self.macro_queue = list(actions)
        self.macro_current = None
        self.macro_waiting_key = None
        self.macro_waiting_kind = None
        self.macro_current_name = name
        self.macro_executed_any = False
        self.macro_has_undo_boundary = has_undo_boundary
        self.macro_undo_record = macro_undo_record

        self.log(f"🧩 매크로 실행: {name} / {len(self.macro_queue)}단계")
        QTimer.singleShot(0, self.run_next_macro_step)

    def run_next_macro_step(self):
        if not self.macro_running:
            return

        if not self.macro_queue:
            name = self.macro_current_name or "매크로"
            executed_any = bool(getattr(self, "macro_executed_any", False))
            has_boundary = bool(getattr(self, "macro_has_undo_boundary", False))
            macro_undo_record = getattr(self, "macro_undo_record", None)
            self.log(f"✅ 매크로 완료: {name}")
            self.macro_running = False
            self.macro_current = None
            self.macro_waiting_key = None
            self.macro_waiting_kind = None
            self.macro_current_name = ""
            self.macro_executed_any = False
            self.macro_has_undo_boundary = False
            self.macro_undo_record = None
            if executed_any:
                if has_boundary:
                    self.break_undo_chain("macro", name)
                elif macro_undo_record:
                    old_allow = getattr(self, "_macro_allow_undo_append", False)
                    self._macro_allow_undo_append = True
                    try:
                        self.append_project_undo_record(macro_undo_record)
                    finally:
                        self._macro_allow_undo_append = old_allow
                    self.update_undo_redo_buttons()
                    self.log(
                        f"↶ Macro undo snapshot saved: {name}"
                        if getattr(self, "ui_language", LANG_KO) == LANG_EN else
                        f"↶ 매크로 Undo 기록 생성: {name}"
                    )
            return

        key = self.macro_queue.pop(0)
        self.macro_current = key
        action = self.actions.get(key)

        if action is None:
            self.log(f"⚠️ [{self.macro_current_name}] 매크로 기능 없음: {key}")
            QTimer.singleShot(0, self.run_next_macro_step)
            return

        if not action.isEnabled():
            self.log(f"⚠️ [{self.macro_current_name}] 비활성 기능 건너뜀: {action.text()}")
            QTimer.singleShot(0, self.run_next_macro_step)
            return

        wait_kind = self.macro_wait_kind_for_key(key)
        self.macro_waiting_key = key if wait_kind else None
        self.macro_waiting_kind = wait_kind or None

        self.log(f"🧩 [{self.macro_current_name}] 단계 실행: {action.text()}")

        try:
            self.macro_executed_any = True
            action.trigger()
            QApplication.processEvents()
        except Exception as e:
            self.log(f"❌ [{self.macro_current_name}] 매크로 중단: {key} / {e}")
            self.stop_macro_queue()
            return

        if wait_kind:
            # 비동기 작업은 워커가 실제로 시작됐는지 잠깐 뒤 확인한다.
            # 시작되지 않은 경우(취소/데이터 없음/키 없음 등)는 매크로가 무한 대기하지 않도록 다음 단계로 넘긴다.
            QTimer.singleShot(250, lambda k=key, wk=wait_kind: self.verify_macro_wait_started(k, wk))
        else:
            # 동기 작업은 함수가 끝난 뒤 바로 다음 단계.
            QTimer.singleShot(0, self.run_next_macro_step)

    def verify_macro_wait_started(self, key, wait_kind):
        if not self.macro_running or self.macro_waiting_key != key:
            return

        running = False
        try:
            if wait_kind == "analysis":
                running = hasattr(self, "w") and self.w is not None and self.w.isRunning()
            elif wait_kind == "inpaint":
                running = hasattr(self, "iw") and self.iw is not None and self.iw.isRunning()
            elif wait_kind == "batch":
                running = hasattr(self, "bw") and self.bw is not None and self.bw.isRunning()
        except Exception:
            running = False

        if not running:
            self.log(f"↪️ [{self.macro_current_name}] 단계 대기 생략: 작업이 시작되지 않음 ({key})")
            self.macro_mark_current_step_done(key)

    def macro_mark_current_step_done(self, key=None):
        if not self.macro_running:
            return

        if key and self.macro_waiting_key and key != self.macro_waiting_key:
            return

        if self.macro_waiting_key:
            self.log(f"✅ [{self.macro_current_name}] 단계 완료: {self.macro_waiting_key}")

        self.macro_waiting_key = None
        self.macro_waiting_kind = None
        self.macro_current = None
        QTimer.singleShot(0, self.run_next_macro_step)

    def stop_macro_queue(self):
        self.macro_running = False
        self.macro_queue = []
        self.macro_current = None
        self.macro_waiting_key = None
        self.macro_waiting_kind = None
        self.macro_current_name = ""
        self.macro_has_undo_boundary = False
        self.macro_undo_record = None

    def current_transform_data_item(self):
        curr = self.data.get(self.idx)
        if not curr:
            return None
        for d in curr.get('data', []) or []:
            if d.get('_transform_mode', False) or d.get('_skew_mode', False) or d.get('_trapezoid_mode', False) or d.get('_arc_mode', False):
                return d
        return None

    def is_text_transform_active(self):
        return self.current_transform_data_item() is not None

    def view_state_key(self, page_idx=None, mode=None):
        if page_idx is None:
            page_idx = getattr(self, "idx", 0)
        if mode is None:
            try:
                mode = self.cb_mode.currentIndex()
            except Exception:
                mode = getattr(self, "last_mode", 0)
        return f"{int(page_idx)}:{int(mode)}"

    def capture_view_state(self):
        """현재 뷰의 확대율/이동 위치를 JSON 저장 가능한 값으로 캡처한다."""
        try:
            tr = self.view.transform()
            return {
                "transform": [
                    float(tr.m11()), float(tr.m12()), float(tr.m13()),
                    float(tr.m21()), float(tr.m22()), float(tr.m23()),
                    float(tr.m31()), float(tr.m32()), float(tr.m33()),
                ],
                "h_scroll": int(self.view.horizontalScrollBar().value()),
                "v_scroll": int(self.view.verticalScrollBar().value()),
            }
        except Exception:
            return {}

    def apply_view_state(self, state):
        if getattr(self, "_app_is_closing", False):
            return False
        if not isinstance(state, dict) or not state:
            return False
        vals = state.get("transform") or []
        try:
            if len(vals) == 9:
                self.view.setTransform(QTransform(*[float(x) for x in vals]))
            if "h_scroll" in state:
                self.view.horizontalScrollBar().setValue(int(state.get("h_scroll") or 0))
            if "v_scroll" in state:
                self.view.verticalScrollBar().setValue(int(state.get("v_scroll") or 0))
            return True
        except Exception:
            return False

    def restore_current_view_state_later(self, page_idx=None, mode=None):
        try:
            key = self.view_state_key(self.idx if page_idx is None else page_idx, self.cb_mode.currentIndex() if mode is None else mode)
            state = copy.deepcopy((getattr(self, "project_ui_view_states", {}) or {}).get(key) or {})
            if not state:
                return False
            self.apply_view_state(state)
            QTimer.singleShot(0, lambda st=copy.deepcopy(state): self.apply_view_state(st))
            QTimer.singleShot(30, lambda st=copy.deepcopy(state): self.apply_view_state(st))
            QTimer.singleShot(80, lambda st=copy.deepcopy(state): self.apply_view_state(st))
            return True
        except Exception:
            return False

    def remember_current_view_state(self):
        if not hasattr(self, "view") or not hasattr(self, "cb_mode"):
            return
        try:
            key = self.view_state_key(self.idx, self.cb_mode.currentIndex())
            self.project_ui_view_states[key] = self.capture_view_state()
        except Exception:
            pass

    def restore_project_ui_state(self, ui_state, refresh=False):
        if not isinstance(ui_state, dict):
            return False
        old_restore = getattr(self, "_project_undo_restore_lock", False)
        self._project_undo_restore_lock = True
        try:
            if hasattr(self, "cb_show_final_text") and "show_final_text" in ui_state:
                self.cb_show_final_text.blockSignals(True)
                try:
                    self.cb_show_final_text.setChecked(bool(ui_state.get("show_final_text")))
                    self._last_show_final_text_checked = bool(ui_state.get("show_final_text"))
                finally:
                    self.cb_show_final_text.blockSignals(False)
            if hasattr(self, "act_final_paint_above_text") and "final_paint_above_text" in ui_state:
                val = bool(ui_state.get("final_paint_above_text"))
                self.final_paint_above_text = val
                self.act_final_paint_above_text.blockSignals(True)
                try:
                    self.act_final_paint_above_text.setChecked(val)
                    self.act_final_paint_above_text.setText("T↑" if val else "T↓")
                    self._last_final_paint_above_text = val
                finally:
                    self.act_final_paint_above_text.blockSignals(False)
            if isinstance(ui_state.get("view_states"), dict):
                self.project_ui_view_states = copy.deepcopy(ui_state.get("view_states") or {})
            if refresh and hasattr(self, "cb_mode") and self.cb_mode.currentIndex() == 4:
                old_suppress = getattr(self, "_suppress_mode_undo", False)
                self._suppress_mode_undo = True
                try:
                    self.mode_chg(4)
                finally:
                    self._suppress_mode_undo = old_suppress
            return True
        finally:
            self._project_undo_restore_lock = old_restore

    def current_project_ui_state(self):
        self.remember_current_view_state()
        try:
            mode = int(self.cb_mode.currentIndex())
        except Exception:
            mode = int(getattr(self, "last_mode", 0) or 0)
        return {
            "current_mode": mode,
            "view_states": copy.deepcopy(getattr(self, "project_ui_view_states", {}) or {}),
            "show_final_text": bool(self.cb_show_final_text.isChecked()) if hasattr(self, "cb_show_final_text") else True,
            "final_paint_above_text": bool(getattr(self, "final_paint_above_text", False)),
        }

    def save_project_store(self, store, paths=None, data=None, idx=None):
        """ProjectStore.save() 호출 전에 UI 상태를 같이 넣는 공통 저장 함수."""
        if store is None:
            return False
        try:
            store.ui_state = self.current_project_ui_state()
        except Exception:
            store.ui_state = getattr(store, "ui_state", {}) or {}
        store.save(paths if paths is not None else self.paths, data if data is not None else self.data, self.idx if idx is None else idx)
        return True

    def undo_boundary_log_text(self, event, kind, name=""):
        """Undo 경계 생성/차단 로그 문구를 현재 UI 언어에 맞춰 돌려준다."""
        kind = str(kind or "action")
        name = str(name or "").strip()
        is_en = getattr(self, "ui_language", LANG_KO) == LANG_EN

        boundary_labels = {
            "macro": ("매크로", "macro"),
            "font_preset": ("글꼴 프리셋", "font preset"),
            "analysis": ("분석 결과", "analysis results"),
            "reanalyze": ("텍스트 마스크 재분석 결과", "text mask re-analysis results"),
            "translation": ("번역 결과", "translation results"),
            "inpaint": ("인페인팅 결과", "inpainting results"),
            "batch_analysis": ("일괄 분석 결과", "batch analysis results"),
            "batch_translation": ("일괄 번역 결과", "batch translation results"),
            "batch_inpaint": ("일괄 인페인팅 결과", "batch inpainting results"),
        }
        ko_label, en_label = boundary_labels.get(kind, ("작업", "action"))
        ko_name = name or ko_label
        en_name = name or en_label

        if kind == "macro":
            if event == "set":
                return (
                    f"🧱 Undo boundary set: macro '{en_name}' was executed, so previous undo history was cleared."
                    if is_en else
                    f"🧱 Undo 경계 생성: 매크로 '{ko_name}' 실행으로 이전 되돌리기 내역을 끊었습니다."
                )
            return (
                f"⛔ Cannot undo: macro '{en_name}' created an undo boundary. To prevent state conflicts, actions before that point cannot be restored."
                if is_en else
                f"⛔ 되돌릴 수 없습니다: 매크로 '{ko_name}' 실행 이후 Undo 경계가 생겼습니다. 상태 꼬임 방지를 위해 그 이전으로는 돌아가지 않습니다."
            )

        api_boundary_kinds = {
            "analysis", "reanalyze", "translation", "inpaint",
            "batch_analysis", "batch_translation", "batch_inpaint",
        }
        if kind in api_boundary_kinds:
            if event == "set":
                return (
                    f"🧱 Undo boundary set: {en_label} were applied, so previous undo history was cleared."
                    if is_en else
                    f"🧱 Undo 경계 생성: {ko_label} 반영으로 이전 되돌리기 내역을 끊었습니다."
                )
            return (
                f"⛔ Cannot undo: {en_label} created an undo boundary. To prevent state conflicts, actions before that point cannot be restored."
                if is_en else
                f"⛔ 되돌릴 수 없습니다: {ko_label} 반영 이후 Undo 경계가 생겼습니다. 상태 꼬임 방지를 위해 그 이전으로는 돌아가지 않습니다."
            )

        if event == "set":
            return (
                "🧱 Undo boundary set: previous undo history was cleared to prevent state conflicts."
                if is_en else
                "🧱 Undo 경계 생성: 상태 꼬임 방지를 위해 이전 되돌리기 내역을 끊었습니다."
            )
        return (
            "⛔ Cannot undo: an undo boundary was created. To prevent state conflicts, actions before that point cannot be restored."
            if is_en else
            "⛔ 되돌릴 수 없습니다: Undo 경계가 생겼습니다. 상태 꼬임 방지를 위해 그 이전으로는 돌아가지 않습니다."
        )

    def break_undo_chain(self, kind="action", name=""):
        """매크로/글꼴 프리셋처럼 Undo 기록을 남기지 않는 작업 뒤에 과거 Undo를 차단한다."""
        self.undo_boundary = {"kind": str(kind or "action"), "name": str(name or "")}
        self.project_undo_stack = []
        self.project_redo_stack = []
        self.page_text_undo_stacks = {}
        self._deferred_undo_records = {}
        try:
            self.view.history.clear()
        except Exception:
            pass
        self.log(self.undo_boundary_log_text("set", kind, name))
        self.update_undo_redo_buttons()
        return True

    def log_undo_boundary_blocked(self):
        boundary = getattr(self, "undo_boundary", None)
        if not boundary:
            return False
        self.log(self.undo_boundary_log_text("blocked", boundary.get("kind"), boundary.get("name")))
        return True

    def set_work_mode_without_undo(self, mode):
        try:
            mode = int(mode)
        except Exception:
            mode = 0
        if not hasattr(self, "cb_mode") or self.cb_mode.count() <= 0:
            self.last_mode = mode
            self._current_work_mode = mode
            return
        mode = max(0, min(mode, self.cb_mode.count() - 1))
        self.cb_mode.blockSignals(True)
        try:
            self.cb_mode.setCurrentIndex(mode)
        finally:
            self.cb_mode.blockSignals(False)
        self.last_mode = mode
        self._current_work_mode = mode

    def copy_page_data_for_undo(self, page_idx=None):
        if page_idx is None:
            page_idx = self.idx
        curr = self.data.get(page_idx)
        if not isinstance(curr, dict):
            return None
        out = {}
        for k, v in curr.items():
            if k == 'ori':
                out[k] = v
            elif isinstance(v, np.ndarray):
                out[k] = v.copy()
            else:
                out[k] = copy.deepcopy(v)
        return out

    def copy_project_data_for_undo(self):
        """일괄 텍스트 작업용 전체 프로젝트 스냅샷.

        번역문 일괄 불러오기/일괄 지우기/텍스트 정리처럼 여러 페이지를 한 번에
        바꾸는 작업은 현재 페이지만 저장하면 Ctrl+Z 복원이 깨진다.
        이 경우 변경 전 self.data 전체를 저장해 하나의 Undo 단계로 되돌린다.
        """
        out = {}
        try:
            keys = list((self.data or {}).keys())
        except Exception:
            keys = []
        for page_idx in keys:
            page_data = self.copy_page_data_for_undo(page_idx)
            if page_data is not None:
                out[page_idx] = page_data
        return out

    def append_project_undo_record(self, rec, clear_redo=True):
        if not rec:
            return False
        if getattr(self, "_project_undo_restore_lock", False):
            return False
        # 매크로 실행 중에는 단계별 Undo를 쌓지 않는다.
        # 일반 매크로는 완료 시점에 매크로 1개짜리 Undo만 저장하고,
        # 분석/번역/인페인팅 포함 매크로는 Undo 경계로 끊는다.
        if getattr(self, "macro_running", False) and not getattr(self, "_macro_allow_undo_append", False):
            return False
        if not hasattr(self, "project_undo_stack") or self.project_undo_stack is None:
            self.project_undo_stack = []
        self.project_undo_stack.append(rec)
        # Undo 스택은 가볍게 20단계만 유지한다.
        # 텍스트 라인/탭 이동까지 모두 스택에 넣기 때문에 오래된 기록은 FIFO로 버린다.
        if len(self.project_undo_stack) > 20:
            self.project_undo_stack.pop(0)
        if clear_redo:
            # 새 작업이 들어오면 기존 Redo 흐름은 더 이상 유효하지 않다.
            self.project_redo_stack = []
        self.update_undo_redo_buttons()
        return True

    def append_project_redo_record(self, rec):
        if not rec:
            return False
        if not hasattr(self, "project_redo_stack") or self.project_redo_stack is None:
            self.project_redo_stack = []
        self.project_redo_stack.append(rec)
        if len(self.project_redo_stack) > 20:
            self.project_redo_stack.pop(0)
        self.update_undo_redo_buttons()
        return True

    def make_project_undo_record(self, reason="작업", page_idx=None, full_project=False):
        if page_idx is None:
            page_idx = self.idx
        try:
            mode = int(self.cb_mode.currentIndex())
        except Exception:
            mode = int(getattr(self, "last_mode", 0) or 0)
        rec = {
            "reason": str(reason or "작업"),
            "page_idx": int(page_idx),
            "mode": mode,
            "view_state": self.capture_view_state(),
            "magic_wand_state": self.capture_magic_wand_state(),
            "ui_state": self.current_project_ui_state(),
        }
        if full_project:
            rec["project_paths"] = list(getattr(self, "paths", []) or [])
            rec["project_data"] = self.copy_project_data_for_undo()
        else:
            rec["page_data"] = self.copy_page_data_for_undo(page_idx)
        return rec

    def make_ui_undo_record(self, reason="화면 작업", page_idx=None, mode=None):
        """탭/페이지/줌/화면 이동용 경량 Undo 기록.

        이 작업들은 data 자체를 바꾸지 않으므로 이미지/마스크/텍스트 전체를
        복사하지 않는다. 이전 구현처럼 page_data를 매번 복사하면 탭 이동이나
        최종화면 전환이 무거워지고, Ctrl+Z 연속 동작도 끊기는 원인이 된다.
        """
        if page_idx is None:
            page_idx = self.idx
        try:
            current_mode = int(self.cb_mode.currentIndex())
        except Exception:
            current_mode = int(getattr(self, "last_mode", 0) or 0)
        if mode is None:
            mode = current_mode
        return {
            "reason": str(reason or "화면 작업"),
            "page_idx": int(page_idx),
            "mode": int(mode),
            "view_state": self.capture_view_state(),
            "magic_wand_state": self.capture_magic_wand_state(),
            "ui_state": self.current_project_ui_state(),
            "ui_only": True,
        }

    def is_ui_only_undo_reason(self, reason):
        text = str(reason or "")
        return text in ("작업 탭 변경", "페이지 이동", "화면 이동", "화면 확대/축소")

    def push_project_undo(self, reason="작업", page_idx=None, full_project=False):
        if getattr(self, "_project_undo_restore_lock", False):
            return False
        # 매크로 실행 중 발생한 단계별 작업은 Ctrl+Z 스택에 쌓지 않는다.
        # 매크로는 여러 기능을 연쇄 실행하므로 Undo 기록에 섞이면 복구 순서가 꼬일 수 있다.
        if getattr(self, "macro_running", False) or getattr(self, "_suppress_project_undo", False):
            return False
        if getattr(self, "is_loading_project", False) or getattr(self, "is_page_loading", False) or getattr(self, "is_batch_running", False):
            return False
        if not self.paths or page_idx is None and self.idx not in self.data:
            return False
        target_page = self.idx if page_idx is None else page_idx
        if (not full_project) and self.is_ui_only_undo_reason(reason):
            rec = self.make_ui_undo_record(reason, target_page)
        else:
            rec = self.make_project_undo_record(reason, target_page, full_project=full_project)
        return self.append_project_undo_record(rec)

    def begin_deferred_project_undo(self, key, reason="작업"):
        if not key:
            return None
        if getattr(self, "macro_running", False) or getattr(self, "_suppress_project_undo", False):
            return None
        if getattr(self, "_project_undo_restore_lock", False) or getattr(self, "is_page_loading", False) or getattr(self, "is_batch_running", False):
            return None
        if self.is_ui_only_undo_reason(reason):
            rec = self.make_ui_undo_record(reason)
        else:
            rec = self.make_project_undo_record(reason)
        self._deferred_undo_records[str(key)] = rec
        return rec

    def finish_deferred_project_undo(self, key, force=False, changed=None, autosave=True):
        rec = self._deferred_undo_records.pop(str(key), None)
        if getattr(self, "macro_running", False) or getattr(self, "_suppress_project_undo", False):
            if autosave:
                self.auto_save_project()
            return False
        if not rec:
            return False
        if changed is None:
            changed = True
        if not force and not changed:
            return False
        self.append_project_undo_record(rec)
        if autosave:
            self.auto_save_project()
        return True

    def copy_text_line_state_for_undo(self, page_idx=None, include_masks=False):
        """원문/번역문/텍스트행 삭제/재정렬용 경량 스냅샷.

        일반 텍스트 라인 수정은 이미지/전체 마스크를 복사할 필요가 없다.
        현재 페이지의 data 리스트만 복사해서 Ctrl+Z 복원을 가볍게 만든다.
        삭제처럼 마스크 슬롯을 같이 건드리는 작업만 include_masks=True로 필요한
        마스크 슬롯을 추가 보존한다.
        """
        if page_idx is None:
            page_idx = self.idx
        curr = self.data.get(page_idx)
        if not isinstance(curr, dict):
            return None
        state = {
            "data": copy.deepcopy(curr.get("data", []) or []),
        }
        if include_masks:
            for key in ("mask_merge", "mask_inpaint", "mask_merge_off", "mask_inpaint_off"):
                value = curr.get(key)
                state[key] = value.copy() if isinstance(value, np.ndarray) else copy.deepcopy(value)
            state["mask_toggle_enabled"] = bool(curr.get("mask_toggle_enabled", False))
        return state

    def make_text_line_undo_record(self, reason="텍스트 라인 변경", page_idx=None, include_masks=False):
        if page_idx is None:
            page_idx = self.idx
        try:
            mode = int(self.cb_mode.currentIndex())
        except Exception:
            mode = int(getattr(self, "last_mode", 0) or 0)
        return {
            "reason": str(reason or "텍스트 라인 변경"),
            "page_idx": int(page_idx),
            "mode": mode,
            "view_state": self.capture_view_state(),
            "magic_wand_state": self.capture_magic_wand_state(),
            "ui_state": self.current_project_ui_state(),
            "text_line_state": self.copy_text_line_state_for_undo(page_idx, include_masks=include_masks),
        }

    def push_text_line_undo(self, reason="텍스트 라인 변경", page_idx=None, include_masks=False):
        if getattr(self, "_project_undo_restore_lock", False):
            return False
        if getattr(self, "macro_running", False) or getattr(self, "_suppress_project_undo", False):
            return False
        if getattr(self, "is_loading_project", False) or getattr(self, "is_page_loading", False) or getattr(self, "is_batch_running", False):
            return False
        if not self.paths or (page_idx is None and self.idx not in self.data):
            return False
        rec = self.make_text_line_undo_record(reason, self.idx if page_idx is None else page_idx, include_masks=include_masks)
        return self.append_project_undo_record(rec)

    def unique_history_rename_target(self, target_path):
        """Undo/Redo 중 목표 파일명이 이미 있을 때 자동 대체 이름을 만든다."""
        try:
            target = Path(str(target_path))
            folder = target.parent
            ext = target.suffix or ".png"
            base = safe_page_file_stem(target.stem, fallback="image")
            for n in range(1, 10000):
                cand = folder / f"{base}({n}){ext}"
                if not cand.exists():
                    return str(cand)
            return str(folder / f"{base}({uuid.uuid4().hex[:8]}){ext}")
        except Exception:
            return str(target_path)

    def confirm_history_rename_conflict(self, target_path, auto_path, reason="원본 파일명 변경"):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle(self.tr_ui("파일명 중복"))
        msg.setText(self.tr_ui("되돌리려는 원본 이미지 파일명이 이미 있습니다."))
        msg.setInformativeText(
            f"{self.tr_ui('기존 이름')} : {os.path.basename(str(target_path))}\n"
            f"{self.tr_ui('자동 이름')} : {os.path.basename(str(auto_path))}"
        )
        btn_auto = msg.addButton(self.tr_ui("이름 바꾸고 계속"), QMessageBox.ButtonRole.AcceptRole)
        btn_cancel = msg.addButton(self.tr_ui("되돌리지 않기"), QMessageBox.ButtonRole.RejectRole)
        for _btn in (btn_auto, btn_cancel):
            try:
                _btn.setMinimumWidth(148)
            except Exception:
                pass
        msg.setDefaultButton(btn_auto)
        msg.setEscapeButton(btn_cancel)
        try:
            msg.setStyleSheet(
                self.message_box_style()
                + "\nQMessageBox QPushButton { min-width:148px; padding:6px 14px; }"
            )
        except Exception:
            pass
        force_message_box_front(msg)
        msg.exec()
        return msg.clickedButton() is btn_auto

    def update_history_record_paths_after_rename(self, rec, page_idx, expected_to, actual_to):
        """충돌 때문에 Undo/Redo 목표명이 바뀐 경우 스냅샷도 실제 파일명에 맞춘다."""
        try:
            page_idx = int(page_idx)
        except Exception:
            page_idx = None
        expected_to = str(expected_to)
        actual_to = str(actual_to)
        if expected_to == actual_to:
            return
        try:
            paths = rec.get("project_paths")
            if isinstance(paths, list):
                for i, p in enumerate(paths):
                    try:
                        if str(Path(str(p)).resolve()).lower() == str(Path(expected_to).resolve()).lower():
                            paths[i] = actual_to
                    except Exception:
                        if str(p) == expected_to:
                            paths[i] = actual_to
                if page_idx is not None and 0 <= page_idx < len(paths):
                    paths[page_idx] = actual_to
        except Exception:
            pass
        try:
            pdata = rec.get("project_data")
            if isinstance(pdata, dict) and page_idx is not None:
                curr = pdata.get(page_idx)
                if curr is None:
                    curr = pdata.get(str(page_idx))
                if isinstance(curr, dict):
                    curr["original_name"] = os.path.basename(actual_to)
        except Exception:
            pass
        try:
            page_data = rec.get("page_data")
            if isinstance(page_data, dict):
                page_data["original_name"] = os.path.basename(actual_to)
        except Exception:
            pass

    def apply_file_rename_ops_for_history(self, rec):
        """Undo/Redo 기록에 포함된 실제 파일명 변경을 먼저 적용한다."""
        ops = (rec or {}).get("file_rename_ops")
        if not isinstance(ops, list) or not ops:
            return True

        for op in ops:
            if not isinstance(op, dict):
                continue
            src = str(op.get("from_path") or "")
            dst = str(op.get("to_path") or "")
            if not src or not dst:
                continue
            try:
                src_path = Path(src)
                dst_path = Path(dst)
                page_idx = op.get("page_idx")

                if not src_path.exists():
                    # 이미 목표 상태에 가깝거나 파일이 정리된 경우는 데이터 복원으로 이어간다.
                    continue

                actual_dst = dst_path
                try:
                    same_path = str(src_path.resolve()).lower() == str(dst_path.resolve()).lower()
                except Exception:
                    same_path = str(src_path).lower() == str(dst_path).lower()

                if dst_path.exists() and not same_path:
                    auto_path = Path(self.unique_history_rename_target(dst_path))
                    if not self.confirm_history_rename_conflict(dst_path, auto_path, op.get("reason", "원본 파일명 변경")):
                        return False
                    actual_dst = auto_path

                actual_dst.parent.mkdir(parents=True, exist_ok=True)

                if same_path and str(src_path) != str(actual_dst):
                    tmp = src_path.with_name(f".__ysb_history_rename_{uuid.uuid4().hex}{src_path.suffix}")
                    os.rename(str(src_path), str(tmp))
                    os.rename(str(tmp), str(actual_dst))
                elif str(src_path) != str(actual_dst):
                    os.rename(str(src_path), str(actual_dst))

                self.update_history_record_paths_after_rename(rec, page_idx, dst_path, actual_dst)
            except Exception as e:
                QMessageBox.critical(
                    self,
                    self.tr_ui("파일명 변경 Undo 실패"),
                    f"{self.tr_ui('원본 이미지 파일명을 되돌리지 못했습니다.')}\n{e}",
                )
                return False
        return True

    def invert_file_rename_ops(self, ops):
        out = []
        for op in ops or []:
            if not isinstance(op, dict):
                continue
            out.append({
                "page_idx": op.get("page_idx"),
                "from_path": op.get("to_path"),
                "to_path": op.get("from_path"),
                "reason": op.get("reason", "원본 파일명 변경"),
            })
        return out

    def make_current_undo_record_like(self, rec):
        """Undo/Redo 왕복용 현재 상태 스냅샷을 기존 기록과 같은 가벼운 단위로 만든다."""
        reason = str((rec or {}).get("reason") or "작업")
        try:
            page_idx = int(getattr(self, "idx", 0) or 0)
        except Exception:
            page_idx = 0

        def _attach_inverse_file_ops(out_rec):
            ops = (rec or {}).get("file_rename_ops")
            if isinstance(ops, list) and ops:
                out_rec["file_rename_ops"] = self.invert_file_rename_ops(ops)
            return out_rec

        text_line_state = (rec or {}).get("text_line_state")
        if isinstance(text_line_state, dict):
            include_masks = any(k in text_line_state for k in ("mask_merge", "mask_inpaint", "mask_merge_off", "mask_inpaint_off", "mask_toggle_enabled"))
            return _attach_inverse_file_ops(self.make_text_line_undo_record(reason, page_idx=page_idx, include_masks=include_masks))
        if (rec or {}).get("ui_only"):
            try:
                mode = int(self.cb_mode.currentIndex())
            except Exception:
                mode = int(getattr(self, "last_mode", 0) or 0)
            return _attach_inverse_file_ops(self.make_ui_undo_record(reason, page_idx=page_idx, mode=mode))
        if isinstance((rec or {}).get("project_data"), dict):
            return _attach_inverse_file_ops(self.make_project_undo_record(reason, page_idx=page_idx, full_project=True))
        return _attach_inverse_file_ops(self.make_project_undo_record(reason, page_idx=page_idx, full_project=False))

    def restore_project_history_record(self, rec):
        """Undo/Redo 기록 1개를 실제 작업 상태로 복원한다."""
        page_idx = int(rec.get("page_idx", self.idx) or 0)
        rec_paths = rec.get("project_paths")
        path_count = len(rec_paths) if isinstance(rec_paths, list) else len(self.paths)
        if path_count <= 0:
            page_idx = 0
        elif page_idx < 0 or page_idx >= path_count:
            page_idx = max(0, min(page_idx, path_count - 1))

        if not self.apply_file_rename_ops_for_history(rec):
            return False

        self._project_undo_restore_lock = True
        self._text_undo_restore_lock = True
        try:
            text_line_state = rec.get("text_line_state")
            if isinstance(text_line_state, dict):
                curr = self.data.get(page_idx)
                if isinstance(curr, dict):
                    curr["data"] = copy.deepcopy(text_line_state.get("data", []) or [])
                    for key in ("mask_merge", "mask_inpaint", "mask_merge_off", "mask_inpaint_off"):
                        if key in text_line_state:
                            value = text_line_state.get(key)
                            curr[key] = value.copy() if isinstance(value, np.ndarray) else copy.deepcopy(value)
                    if "mask_toggle_enabled" in text_line_state:
                        curr["mask_toggle_enabled"] = bool(text_line_state.get("mask_toggle_enabled"))
            elif not rec.get("ui_only"):
                rec_paths = rec.get("project_paths")
                if isinstance(rec_paths, list):
                    self.paths = list(rec_paths)
                project_data = rec.get("project_data")
                if isinstance(project_data, dict):
                    restored = {}
                    for k, v in project_data.items():
                        try:
                            kk = int(k)
                        except Exception:
                            kk = k
                        restored[kk] = self.copy_undo_page_data(v) if isinstance(v, dict) else copy.deepcopy(v)
                    self.data = restored
                else:
                    page_data = rec.get("page_data")
                    if isinstance(page_data, dict):
                        self.data[page_idx] = self.copy_undo_page_data(page_data)

            if self.paths:
                page_idx = max(0, min(page_idx, len(self.paths) - 1))
            else:
                page_idx = 0
            self.idx = page_idx
            mode = int(rec.get("mode", 0) or 0)
            self.set_work_mode_without_undo(mode)
            self.restore_project_ui_state(rec.get("ui_state"), refresh=False)

            prev_loading = self.is_page_loading
            self.is_page_loading = True
            try:
                self.load()
            finally:
                self.is_page_loading = prev_loading

            self.restore_project_ui_state(rec.get("ui_state"), refresh=(mode == 4))

            state = copy.deepcopy(rec.get("view_state") or {})
            if state:
                self.apply_view_state(state)
                QTimer.singleShot(0, lambda st=state: self.apply_view_state(st))
                QTimer.singleShot(30, lambda st=state: self.apply_view_state(st))
                QTimer.singleShot(80, lambda st=state: self.apply_view_state(st))

            try:
                self.view.history.clear()
            except Exception:
                pass
            try:
                self.restore_magic_wand_state(rec.get("magic_wand_state"))
            except Exception:
                pass
            self.page_text_undo_stacks = {}
            self.auto_save_project()
        finally:
            self._text_undo_restore_lock = False
            self._project_undo_restore_lock = False
        return True

    def undo_project_action(self):
        stack = getattr(self, "project_undo_stack", None) or []
        if not stack:
            self.update_undo_redo_buttons()
            return False
        rec = stack.pop()
        redo_rec = self.make_current_undo_record_like(rec)
        if not self.restore_project_history_record(rec):
            self.update_undo_redo_buttons()
            return False
        self.append_project_redo_record(redo_rec)
        self.log(f"↩️ {rec.get('reason', '작업')} 되돌림")
        self.update_undo_redo_buttons()
        return True

    def redo_project_action(self):
        stack = getattr(self, "project_redo_stack", None) or []
        if not stack:
            self.update_undo_redo_buttons()
            return False
        rec = stack.pop()
        undo_rec = self.make_current_undo_record_like(rec)
        if not self.restore_project_history_record(rec):
            self.update_undo_redo_buttons()
            return False
        self.append_project_undo_record(undo_rec, clear_redo=False)
        self.log(f"↷ {rec.get('reason', '작업')} 재실행")
        self.update_undo_redo_buttons()
        return True

    def copy_undo_page_data(self, page_data):
        out = {}
        for k, v in (page_data or {}).items():
            if k == 'ori':
                out[k] = v
            elif isinstance(v, np.ndarray):
                out[k] = v.copy()
            else:
                out[k] = copy.deepcopy(v)
        return out

    def push_page_text_undo(self, reason="텍스트 작업"):
        # v1.6.3: 페이지를 넘긴 뒤에도 이전 페이지 텍스트 작업을 되돌릴 수 있도록
        # 페이지 전용 스택 대신 전역 작업 스택에 현재 페이지 상태를 저장한다.
        return self.push_project_undo(reason)

    def undo_page_text(self):
        # 구버전 호출 호환용. 실제 Ctrl+Z는 handle_general_undo()에서
        # undo_project_action()을 먼저 사용한다.
        return self.undo_project_action()

    def end_active_text_transform(self, refresh=True):
        active = self.current_transform_data_item()
        if active is None:
            return False
        was_skew = bool(active.get('_skew_mode', False))
        was_trapezoid = bool(active.get('_trapezoid_mode', False))
        was_arc = bool(active.get('_arc_mode', False))
        active.pop('_transform_mode', None)
        active.pop('_skew_mode', None)
        active.pop('_trapezoid_mode', None)
        active.pop('_arc_mode', None)
        if refresh and self.cb_mode.currentIndex() == 4:
            selected_id = active.get('id')
            self.mode_chg(4)
            if selected_id is not None:
                self.reselect_text_items([selected_id])
        self.auto_save_project()
        if was_arc:
            self.log("🔷 부채꼴 변형 종료")
        elif was_trapezoid:
            self.log("🔷 사다리꼴 변형 종료")
        elif was_skew:
            self.log("🔷 평행사변형 변형 종료")
        else:
            self.log("🔷 텍스트 변형 모드 종료")
        return True

    def undo_last_arc_transform_point(self):
        active = self.current_transform_data_item() if hasattr(self, 'current_transform_data_item') else None
        if not isinstance(active, dict) or not active.get('_arc_mode'):
            return False
        handles = active.get('arc_handles')
        if not isinstance(handles, list) or not handles:
            return False
        handles.pop()
        active['arc_handles'] = handles
        try:
            active['arc_active_index'] = len(handles) - 1 if handles else -1
        except Exception:
            pass
        selected_id = active.get('id')
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
            if selected_id is not None:
                self.reselect_text_items([selected_id])
        self.auto_save_project()
        self.log(f"↩️ 부채꼴 제어점 제거: 남은 점 {len(handles)}개")
        self.update_undo_redo_buttons()
        return True

    def can_general_undo(self):
        try:
            active = self.current_transform_data_item() if hasattr(self, 'current_transform_data_item') else None
            if isinstance(active, dict) and active.get('_arc_mode') and isinstance(active.get('arc_handles'), list) and active.get('arc_handles'):
                return True
            if getattr(getattr(self, "view", None), "draw_mode", None) == 'ocr_region_select' and getattr(self, 'ocr_region_temp_history', None):
                return True
            if getattr(self, "project_undo_stack", None):
                return True
            if getattr(getattr(self, "view", None), "history", None):
                return True
            if getattr(getattr(self, "view", None), "draw_mode", None) == 'magic_wand' and getattr(self, 'magic_wand_history', None):
                return True
        except Exception:
            pass
        return False

    def can_general_redo(self):
        return bool(getattr(self, "project_redo_stack", None))

    def set_history_button_tooltips(self):
        """Keep quick undo/redo on the unified delayed tooltip system only."""
        def shortcut_text(key, fallback=""):
            try:
                seq = self.shortcut_settings.seq(key)
                txt = seq.toString(QKeySequence.SequenceFormat.NativeText)
                return txt or fallback
            except Exception:
                return fallback

        def set_delayed(widget, title, shortcut, desc):
            if widget is None:
                return
            try:
                widget.setToolTip("")
                action = widget.defaultAction() if hasattr(widget, "defaultAction") else None
                if action is not None:
                    action.setToolTip("")
                    action.setStatusTip("")
                    action.setWhatsThis("")
            except Exception:
                pass
            try:
                if hasattr(self, "register_delayed_tooltip"):
                    self.register_delayed_tooltip(widget, title, shortcut, desc)
                    return
            except Exception:
                pass
            try:
                widget.setProperty("delayed_tooltip_title", title)
                widget.setProperty("delayed_tooltip_shortcut", shortcut)
                widget.setProperty("delayed_tooltip_description", desc)
                if hasattr(self, "_tooltip_rich_text"):
                    widget.setProperty("delayed_tooltip_html", self._tooltip_rich_text(title, shortcut, desc))
                widget.installEventFilter(self)
            except Exception:
                pass

        if hasattr(self, "btn_quick_undo"):
            set_delayed(
                self.btn_quick_undo,
                self.tr_ui("뒤로가기"),
                shortcut_text("paint_undo", "Ctrl+Z"),
                self.tr_msg("최근 작업을 되돌립니다."),
            )
        if hasattr(self, "btn_quick_redo"):
            set_delayed(
                self.btn_quick_redo,
                self.tr_ui("앞으로 가기"),
                shortcut_text("paint_redo", "Ctrl+Y"),
                self.tr_msg("되돌린 작업을 다시 실행합니다."),
            )
    def history_button_style(self, enabled):
        if enabled:
            return "background:#3b465a;color:#ffffff;border:1px solid #7f8ba3;font-weight:bold;"
        return "background:#2a2d34;color:#777b84;border:1px solid #444852;font-weight:bold;"

    def update_undo_redo_buttons(self):
        try:
            can_undo = self.can_general_undo()
            can_redo = self.can_general_redo()
            if hasattr(self, "btn_quick_undo"):
                self.btn_quick_undo.setEnabled(can_undo)
            if hasattr(self, "btn_quick_redo"):
                self.btn_quick_redo.setEnabled(can_redo)
            self.set_history_button_tooltips()
        except Exception:
            pass

    def handle_general_undo(self):
        if self.undo_last_arc_transform_point():
            return
        if getattr(self.view, 'draw_mode', None) == 'ocr_region_select' and getattr(self, 'ocr_region_temp_history', None):
            if self.undo_last_ocr_analysis_region_temp():
                return
        if self.undo_project_action():
            return
        if self.log_undo_boundary_blocked():
            self.update_undo_redo_buttons()
            return
        if getattr(self.view, 'draw_mode', None) == 'magic_wand' and getattr(self, 'magic_wand_history', None):
            self.undo_magic_wand_selection()
            self.update_undo_redo_buttons()
            return
        self.view.undo()
        self.update_undo_redo_buttons()

    def handle_general_redo(self):
        if self.redo_project_action():
            return
        self.log("⚠️ 다시 실행할 내역이 없습니다." if self.ui_language == LANG_KO else "⚠️ There is no action to redo.")
        self.update_undo_redo_buttons()

