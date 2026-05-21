from ysb.ui.main_window_support import *


class MainWindowInteractionMixin:

    def setup_actions(self):
        def make_action(key, text, slot):
            action = QAction(text, self)
            action.triggered.connect(lambda *args, _slot=slot: _slot())
            self.actions[key] = action
            self.addAction(action)
            return action

        # 프로젝트
        make_action("project_new", "새로 만들기", self.new_empty_project_action)
        make_action("project_import_images", "이미지 불러오기", self.import_images_action)
        make_action("project_open", "열기", self.open_project)
        make_action("project_open_json", "JSON으로 열기", self.open_project_json)
        make_action("project_show_launcher", "홈화면으로 가기", self.show_launcher)
        make_action("project_exit", "프로젝트 나가기", self.show_launcher)
        make_action("project_save", "저장하기", self.save_project)
        make_action("project_save_as", "다른 이름으로 저장하기", self.save_project_as)
        make_action("project_recover_last_work", "복구하기", self.recover_last_work_project)

        # 개별 작업
        make_action("work_tab_cycle", "작업탭 변경", self.cycle_work_tab)
        make_action("work_page_prev", "이전 페이지", self.prev)
        make_action("work_page_next", "다음 페이지", self.next)
        make_action("work_page_list", "페이지 목록", self.show_page_tab_menu)
        make_action("work_page_full_name", "현재 페이지 이름 보기", self.show_current_page_full_name)
        make_action("work_page_rename_source", "페이지 탭 파일명 변경", self.rename_current_page_source_file)
        make_action("work_page_delete_current", "현재 이미지탭 삭제", self.delete_current_page_shortcut)
        make_action("work_page_delete_all", "전체 이미지탭 삭제", self.delete_all_pages_shortcut)
        make_action("work_open_current_project_folder", "현재 프로젝트의 작업 폴더로 이동하기", self.open_current_project_work_folder)
        make_action("work_analyze", "개별 분석", self.anal)
        make_action("work_text_number_width", "텍스트 넘버 크기 변경", self.open_text_number_width_dialog)
        make_action("work_translate", "개별 번역", self.trans)
        make_action("work_inpaint", "개별 인페인팅", self.run_inpainting)
        make_action("work_inpaint_source", "인페인팅을 원본으로", self.use_inpainted_as_source)
        make_action("work_restore_original_source", "원본으로 돌아가기", self.restore_original_source)
        make_action("work_extract_text", "개별 지문 추출", self.extract_text_current)
        make_action("work_import_translation", "개별 번역문 불러오기", self.import_translation_current)
        make_action("work_clear_translation", "번역문 내용 지우기", self.clear_translation_current)
        make_action("work_clean_text", "개별 텍스트 정리", self.clean_text_current)
        make_action("work_reset_text_rects", "현재 텍스트 기준 영역 재설정", self.reset_text_rects_current)
        make_action("work_export", "개별 출력", self.export_result)

        # 자동화 작업
        make_action("auto_text_size_current", "자동 텍스트 크기 조정", self.auto_text_size_current)
        make_action("auto_text_size_batch", "일괄 자동 텍스트 크기 조정", self.auto_text_size_batch)
        make_action("auto_linebreak_current", "자동 줄 내림", self.auto_linebreak_current)
        make_action("auto_linebreak_batch", "일괄 자동 줄 내림", self.auto_linebreak_batch)

        # 일괄 작업
        make_action("batch_analyze", "일괄 분석", lambda: self.run_batch('analyze'))
        make_action("batch_translate", "일괄 번역", lambda: self.run_batch('translate'))
        make_action("batch_inpaint", "일괄 인페인팅", lambda: self.run_batch('inpaint'))
        make_action("batch_extract_text", "일괄 지문 추출", self.extract_text_batch)
        make_action("batch_import_translation", "일괄 번역문 불러오기", self.import_translation_batch)
        make_action("batch_clear_translation", "일괄 번역문 내용 지우기", self.clear_translation_batch)
        make_action("batch_clean_text", "일괄 텍스트 정리", self.clean_text_batch)
        make_action("batch_reset_text_rects", "일괄 텍스트 기준 영역 재설정", self.reset_text_rects_batch)
        make_action("batch_export", "일괄 출력", lambda: self.run_batch('export'))

        # 설정 / 옵션
        make_action("option_settings_overview", "설정 / 옵션", self.open_settings_overview_dialog)
        self.act_auto_save_mode = make_action("option_auto_save_mode", "자동저장 모드", self.toggle_auto_save_mode)
        self.act_auto_save_mode.setCheckable(True)
        self.act_auto_save_mode.setChecked(self.auto_save_enabled)
        make_action("option_theme_settings", "테마 설정", self.open_theme_settings_dialog)
        make_action("option_language_settings", "언어 설정", self.open_language_settings_dialog)
        make_action("setting_page_tab_display_name", "페이지 탭 표시명 설정", self.open_page_tab_display_name_dialog)
        make_action("setting_output_display_name", "출력 표시명 설정", self.open_output_display_name_dialog)
        make_action("setting_file_path_visibility", "파일 경로 표시", self.open_file_path_visibility_dialog)
        make_action("option_api_settings", "API 관리", self.open_api_settings_dialog)
        make_action("option_translation_prompt", "번역 프롬프트 입력", self.open_translation_prompt_dialog)
        make_action("option_glossary", "단어장", self.open_glossary_dialog)
        make_action("option_analysis_mask_settings", "분석 마스크 확장 비율", self.open_analysis_mask_settings_dialog)
        make_action("option_cleanup_outputs", "출력물 삭제", self.open_output_cleanup_dialog)
        make_action("option_workspace_location", "작업 폴더 위치 변경", self.change_workspace_location)
        make_action("option_workspace_reset_default", "작업 폴더 위치 기본값으로 변경", self.reset_workspace_location_to_default)
        make_action("option_cleanup_temp_files", "임시 파일 관리", self.cleanup_temp_files_dialog)
        make_action("option_register_ysb", ".ysbt 확장자 연결 등록", self.register_ysb_file_association)
        make_action("option_unregister_ysbt", ".ysbt 확장자 연결 해제", self.unregister_ysbt_file_association)
        make_action("option_shortcut_settings", "단축키 통합 관리", self.open_shortcut_settings_dialog)
        make_action("option_macro_settings", "매크로 관리", self.open_macro_settings_dialog)
        make_action("option_text_preset_settings", "페이지 글꼴 프리셋 관리", self.open_text_preset_dialog)
        make_action("option_item_text_preset_settings", "개별 글꼴 프리셋 관리", self.open_item_text_preset_dialog)

        # 도움말
        make_action("help_about", "프로그램 정보", self.open_about_dialog)

        # 클라우드
        make_action("cloud_register", "클라우드 등록", self.cloud_register)
        make_action("cloud_unregister", "클라우드 등록 해제", self.cloud_unregister)
        make_action("cloud_cache_backup", "클라우드로 캐시 백업", self.cloud_backup_cache)
        make_action("cloud_cache_restore", "클라우드에서 캐시 불러오기", self.cloud_restore_cache)
        make_action("cloud_delete_backups", "클라우드 백업 삭제", self.cloud_delete_cache_backups)

        # 토글/보조 작업
        make_action("paint_redo", "작업 재실행", self.handle_general_redo)
        make_action("paint_magic_fill", "마스킹 칠하기", self.fill_magic_wand_mask)
        make_action("paint_mask_cut", "마스크 커팅", lambda *args: self.set_tool("mask_cut"))
        make_action("paint_mask_toggle", "마스크 ON/OFF", self.toggle_mask_toggle)
        make_action("view_text_toggle", "텍스트 표시 ON/OFF", self.toggle_show_final_text)
        make_action("final_paint_color", "최종 페인팅 색상", lambda *args: self.pick_color("final_paint"))
        make_action("final_paint_to_background", "최종 페인팅을 배경으로 반영", self.apply_final_paint_to_background)
        make_action("final_text_tool", "최종 텍스트 도구", lambda *args: self.set_tool("final_text"))
        make_action("final_paint_above_toggle", "텍스트 위 페인팅 ON/OFF", self.toggle_final_paint_above_text)
        make_action("final_paint_opacity_inc", "최종 브러시 불투명도 증가", lambda *args: self.adjust_final_paint_opacity(+5))
        make_action("final_paint_opacity_dec", "최종 브러시 불투명도 감소", lambda *args: self.adjust_final_paint_opacity(-5))

    def apply_shortcuts(self):
        for key, action in self.actions.items():
            seq = self.shortcut_settings.seq(key)
            action.setShortcut(seq)
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)

        # 기존 매크로 액션 제거 후 현재 설정 기준으로 다시 등록한다.
        for action in getattr(self, "macro_actions", []):
            try:
                self.removeAction(action)
            except Exception:
                pass
        self.macro_actions = []

        for macro in getattr(self.shortcut_settings, "macros", []) or []:
            if not macro.get("enabled", True):
                continue
            shortcut = str(macro.get("shortcut", "") or "").strip()
            actions = list(macro.get("actions", []) or [])
            if not shortcut or not actions:
                continue
            action = QAction(str(macro.get("name", "매크로")), self)
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            action.triggered.connect(lambda checked=False, m=dict(macro): self.run_macro(m))
            self.addAction(action)
            self.macro_actions.append(action)

        for action in getattr(self, "item_preset_actions", []):
            try:
                self.removeAction(action)
            except Exception:
                pass
        self.item_preset_actions = []
        for name, preset in sorted(getattr(self, "item_text_presets", {}).items()):
            if not preset.get("enabled", True):
                continue
            shortcut = str(preset.get("shortcut", "") or "").strip()
            if not shortcut:
                continue
            action = QAction(f"개별 글꼴 프리셋: {name}", self)
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            # 개별 글꼴 프리셋 "단축키" 적용은 Ctrl+Z 기록에서 제외한다.
            # 일반 텍스트 조정/콤보 적용은 기존처럼 Undo 대상이다.
            action.triggered.connect(lambda checked=False, n=name: self.apply_item_text_preset_by_name(n, record_undo=True))
            self.addAction(action)
            self.item_preset_actions.append(action)

        if hasattr(self, "cb_show_final_text"):
            self.configure_ui_tooltips()

        try:
            if hasattr(self, "btn_project_exit"):
                seq = self.shortcut_settings.seq("project_exit").toString(QKeySequence.SequenceFormat.NativeText)
                self.btn_project_exit.setToolTip(self.native_tooltip_html("프로젝트 나가기", seq))
            if hasattr(self, "btn_page_tab_menu"):
                seq = self.shortcut_settings.seq("work_page_list").toString(QKeySequence.SequenceFormat.NativeText)
                self.btn_page_tab_menu.setToolTip(self.native_tooltip_html("페이지 목록", seq))
            if hasattr(self, "btn_page_add"):
                seq = self.shortcut_settings.seq("project_import_images").toString(QKeySequence.SequenceFormat.NativeText)
                self.btn_page_add.setToolTip(self.native_tooltip_html("이미지 불러오기", seq, "현재 프로젝트에서는 현재 페이지 뒤에 이미지를 추가합니다."))
        except Exception:
            pass

    def update_paint_toolbar_visibility(self):
        """작업 탭별로 사용할 수 없는 좌측 도구 아이콘은 숨긴다."""
        mode = self.cb_mode.currentIndex() if hasattr(self, "cb_mode") else 0

        mask_tabs = mode in (2, 3)
        final_tab = mode == 4
        drawing_tabs = mask_tabs or final_tab
        paint_only = mode == 3

        # 브러시/지우개/되돌리기는 마스크 탭 + 최종화면에서 사용.
        for attr in ("act_brush", "act_erase", "act_undo"):
            if hasattr(self, attr):
                getattr(self, attr).setVisible(drawing_tabs)

        # 요술봉은 마스크 탭 전용. 재분석은 텍스트 마스크 탭 하단의 파란 버튼으로 이동했다.
        if hasattr(self, "act_magic"):
            self.act_magic.setVisible(mask_tabs)
        if hasattr(self, "act_mask_wrap"):
            self.act_mask_wrap.setVisible(mask_tabs)
        if hasattr(self, "act_mask_cut"):
            self.act_mask_cut.setVisible(mask_tabs)
        if hasattr(self, "act_reanal"):
            self.act_reanal.setVisible(False)
        if hasattr(self, "btn_text_mask_reanalyze"):
            self.btn_text_mask_reanalyze.setVisible(mode == 2)

        # 마스크 ON/OFF는 페인팅 마스크 탭 전용.
        if hasattr(self, "act_mask_toggle"):
            self.act_mask_toggle.setVisible(paint_only)
        if hasattr(self, "mask_toggle_wrap") and self.mask_toggle_wrap:
            self.mask_toggle_wrap.setVisible(paint_only)

        # 최종화면 전용 도구.
        for attr in ("act_final_paint_color", "act_final_text_tool", "act_final_paint_to_bg", "act_final_paint_above_text"):
            if hasattr(self, attr):
                getattr(self, attr).setVisible(final_tab)

        if hasattr(self, "tb"):
            self.tb.setEnabled(drawing_tabs)

    def toggle_mask_toggle(self):
        # 마스크 ON/OFF는 페인팅 마스크 탭 전용이다.
        # 텍스트 마스크 탭에서는 관련 동작을 하지 않는다.
        if self.cb_mode.currentIndex() != 3:
            return
        if hasattr(self, "cb_mask_toggle") and self.cb_mask_toggle is not None:
            self.cb_mask_toggle.toggle()

    def toggle_show_final_text(self):
        if hasattr(self, "cb_show_final_text") and self.cb_show_final_text is not None:
            self.cb_show_final_text.toggle()

    def native_tooltip_html(self, title, shortcut_text="", description=""):
        return self._tooltip_rich_text(title, shortcut_text, description)

    def _tooltip_rich_text(self, title, shortcut_text="", description="", force_white_in_light=False, force_outline=False):
        title = str(title or "")
        shortcut_text = str(shortcut_text or "").strip()
        description = str(description or "").strip()

        color_tooltip = bool(force_outline)
        is_light = self.is_light_theme()
        if color_tooltip:
            fg = "#111827" if is_light else "#ffffff"
            sub = "#374151" if is_light else "#e5e7eb"
            line = "#cfd7e5" if is_light else "#4b5563"
        elif is_light and force_white_in_light:
            fg = "#ffffff"
            sub = "#ffffff"
            line = "#ffffff"
        elif is_light:
            fg = "#111827"
            sub = "#374151"
            line = "#cfd7e5"
        else:
            fg = "#ffffff"
            sub = "#e5e7eb"
            line = "#4b5563"

        base = (
            f'color:{fg};'
            'font-size:12px;'
            'line-height:1.25;'
            'padding:1px 4px;'
            'white-space:normal;'
        )
        rows = [f'<div style="color:{fg}; font-size:12px; line-height:1.25;"><b>{title}</b></div>']
        if shortcut_text:
            rows.append(f'<div style="margin-top:1px;color:{sub}; font-size:11px; line-height:1.22;">{shortcut_text}</div>')
        if description:
            rows.append(f'<div style="margin-top:3px;color:{sub}; border-top:1px solid {line}; padding-top:3px; font-size:11px; line-height:1.25;">{description}</div>')
        return f'<div style="{base}">' + ''.join(rows) + '</div>'

    def is_text_input_widget(self, widget):
        """키 입력을 글자 편집으로 소비해야 하는 입력 위젯인지 확인한다."""
        try:
            if widget is None:
                return False
            if isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit)):
                return True
            # QComboBox 내부의 QLineEdit처럼 직접 타입이 아닌 자식 편집기도 잡는다.
            p = widget
            while p is not None:
                if isinstance(p, (QLineEdit, QTextEdit, QPlainTextEdit)):
                    return True
                p = p.parent()
        except Exception:
            pass
        return False

    def is_editing_table_text_cell(self):
        """우측 텍스트 테이블의 원문/번역 셀을 편집 중인지 확인한다."""
        try:
            fw = QApplication.focusWidget()
            if fw is None or not hasattr(self, "tab") or self.tab is None:
                return False
            if not (fw is self.tab or self.tab.isAncestorOf(fw)):
                return False
            if not self.is_text_input_widget(fw):
                return False
            # 현재 편집기가 열린 셀 좌표를 확인한다. 원문/번역 칸이면 Delete는 행 삭제가 아니라 글자 삭제여야 한다.
            idx = self.tab.currentIndex()
            if idx.isValid() and idx.column() in (2, 3):
                return True
            return True
        except Exception:
            return False

    def install_global_input_filter(self):
        """메인 윈도우 키 입력을 안전하게 정리한다.

        우측 표의 텍스트 셀 편집 중 Delete는 글자 삭제로만 사용하고,
        행 삭제 단축키로 전파하지 않는다.
        """
        if getattr(self, "_global_event_filter_installed", False):
            return
        app = QApplication.instance()
        if app is None:
            return
        try:
            app.installEventFilter(self)
            self._global_event_filter_installed = True
        except Exception:
            pass

    def _is_own_window_object(self, obj):
        try:
            if obj is self:
                return True
            w = obj if isinstance(obj, QWidget) else None
            if w is None:
                return False
            return w.window() is self
        except Exception:
            return False

    def _find_parent_widget_of_type(self, obj, cls):
        try:
            p = obj
            for _ in range(8):
                if p is None or not hasattr(p, "parent"):
                    return None
                p = p.parent()
                if isinstance(p, cls):
                    return p
        except Exception:
            return None
        return None

    def current_font_focus_widget(self, obj=None):
        """메인/프리셋의 글꼴 선택 콤보박스에 포커스가 있는지 확인한다."""
        try:
            fw = QApplication.focusWidget()
        except Exception:
            fw = None
        candidates = [obj, fw]
        for w in candidates:
            if w is None:
                continue
            try:
                if isinstance(w, QFontComboBox):
                    return w
                parent_font_combo = self._find_parent_widget_of_type(w, QFontComboBox)
                if parent_font_combo is not None:
                    return parent_font_combo
            except Exception:
                pass
        return None

    def escape_font_focus_first(self, obj=None):
        """ESC는 글꼴 선택 콤보박스의 포커스를 먼저 빼고, 다른 작업은 하지 않는다."""
        combo = self.current_font_focus_widget(obj)
        if combo is None:
            return False
        try:
            combo.hidePopup()
        except Exception:
            pass
        try:
            combo.clearFocus()
        except Exception:
            pass
        try:
            line = combo.lineEdit()
            if line is not None:
                line.clearFocus()
        except Exception:
            pass
        try:
            if getattr(self, "view", None) is not None:
                self.view.setFocus(Qt.FocusReason.OtherFocusReason)
            else:
                self.setFocus(Qt.FocusReason.OtherFocusReason)
        except Exception:
            pass
        return True

    def current_single_line_input_widget(self, obj=None):
        """ESC/Enter 포커스 탈출 대상이 되는 단일 입력 위젯을 찾는다."""
        try:
            fw = QApplication.focusWidget()
        except Exception:
            fw = None

        for target in (obj, fw):
            if target is None:
                continue
            try:
                if isinstance(target, (QLineEdit, QAbstractSpinBox, QComboBox, QFontComboBox, QKeySequenceEdit)):
                    return target
                # QSpinBox/QComboBox 내부 lineEdit이나 popup child에서 올라가기
                p = target
                for _ in range(8):
                    if p is None or not hasattr(p, "parent"):
                        break
                    p = p.parent()
                    if isinstance(p, (QAbstractSpinBox, QComboBox, QFontComboBox, QKeySequenceEdit)):
                        return p
            except Exception:
                pass
        return None

    def escape_single_line_input_focus_first(self, obj=None):
        """ESC는 단일 입력칸 포커스를 먼저 빼고, 다른 작업은 하지 않는다."""
        target = self.current_single_line_input_widget(obj)
        if target is None:
            return False

        # 멀티라인 텍스트 편집은 ESC 포커스 탈출 대상에서 제외한다.
        if isinstance(target, (QTextEdit, QPlainTextEdit)):
            return False

        try:
            if isinstance(target, QComboBox):
                target.hidePopup()
        except Exception:
            pass

        try:
            if isinstance(target, QAbstractSpinBox):
                target.interpretText()
        except Exception:
            pass

        try:
            if isinstance(target, QKeySequenceEdit):
                target.clear()
        except Exception:
            pass

        # 내부 lineEdit까지 같이 포커스 제거
        try:
            line = target.lineEdit()
            if line is not None:
                try:
                    line.deselect()
                except Exception:
                    pass
                line.clearFocus()
        except Exception:
            pass

        try:
            if hasattr(target, "deselect"):
                target.deselect()
            target.clearFocus()
        except Exception:
            pass

        def move_focus():
            try:
                if getattr(self, "view", None) is not None:
                    self.view.setFocus(Qt.FocusReason.OtherFocusReason)
                else:
                    self.setFocus(Qt.FocusReason.OtherFocusReason)
            except Exception:
                pass

        move_focus()
        # 일부 입력 위젯이 ESC 처리 뒤 포커스를 다시 잡는 경우 대비.
        try:
            QTimer.singleShot(0, move_focus)
            QTimer.singleShot(30, move_focus)
        except Exception:
            pass
        return True

    def finish_single_line_input_by_enter(self, obj=None):
        """단일 입력칸에서 Enter를 누르면 값을 확정하고 포커스를 작업 화면으로 돌린다.
        QSpinBox/QDoubleSpinBox는 내부 QLineEdit이 Enter를 삼키거나 다시 포커스를 잡는 경우가 있어
        즉시 clearFocus + 지연 clearFocus를 같이 수행한다.
        """
        try:
            fw = QApplication.focusWidget()
        except Exception:
            fw = None

        def is_input_like(w):
            if w is None:
                return False
            try:
                if isinstance(w, (QLineEdit, QAbstractSpinBox)):
                    return True
                p = w.parent() if hasattr(w, "parent") else None
                if isinstance(w, QLineEdit) and isinstance(p, QComboBox):
                    return True
                for _ in range(4):
                    p = p.parent() if p is not None and hasattr(p, "parent") else None
                    if isinstance(p, QAbstractSpinBox):
                        return True
            except Exception:
                pass
            return False

        # eventFilter로 들어온 obj가 내부 lineEdit일 수 있으므로 obj를 우선 본다.
        target = obj if is_input_like(obj) else fw
        if target is None or not is_input_like(target):
            return False

        spin = None
        line = None
        try:
            if isinstance(target, QAbstractSpinBox):
                spin = target
                line = target.lineEdit()
            else:
                if isinstance(target, QLineEdit):
                    line = target
                p = target
                for _ in range(5):
                    if p is None or not hasattr(p, "parent"):
                        break
                    p = p.parent()
                    if isinstance(p, QAbstractSpinBox):
                        spin = p
                        try:
                            line = p.lineEdit()
                        except Exception:
                            pass
                        break
        except Exception:
            spin = None

        try:
            if spin is not None:
                spin.interpretText()
        except Exception:
            pass

        # 우측 표 셀 편집기면 표 에디터를 닫아 itemChanged를 확정한다.
        try:
            table = getattr(self, "tab", None)
            if table is not None and (target is table or table.isAncestorOf(target)):
                try:
                    table.commitData(target)
                except Exception:
                    pass
                try:
                    table.closeEditor(target, QAbstractItemDelegate.EndEditHint.NoHint)
                except Exception:
                    pass
                table.setFocus(Qt.FocusReason.OtherFocusReason)
                return True
        except Exception:
            pass

        def ensure_focus_sink():
            sink = getattr(self, "_enter_focus_sink", None)
            try:
                if sink is None:
                    sink = QWidget(self)
                    sink.setObjectName("EnterFocusSink")
                    sink.setFixedSize(1, 1)
                    sink.move(-100, -100)
                    sink.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                    try:
                        sink.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                    except Exception:
                        pass
                    sink.show()
                    self._enter_focus_sink = sink
                return sink
            except Exception:
                return None

        def clear_and_move_focus():
            # QSpinBox 내부 editor가 Enter 처리 뒤 다시 포커스를 잡는 경우가 있어 여러 대상을 같이 정리한다.
            for w in (line, target, spin):
                try:
                    if w is not None:
                        if hasattr(w, "deselect"):
                            w.deselect()
                        w.clearFocus()
                except Exception:
                    pass

            try:
                if getattr(self, "view", None) is not None:
                    try:
                        self.view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                    except Exception:
                        pass
                    self.view.setFocus(Qt.FocusReason.OtherFocusReason)
                    return
            except Exception:
                pass

            sink = ensure_focus_sink()
            try:
                if sink is not None:
                    sink.setFocus(Qt.FocusReason.OtherFocusReason)
                    return
            except Exception:
                pass

            try:
                self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                self.setFocus(Qt.FocusReason.OtherFocusReason)
            except Exception:
                pass

        clear_and_move_focus()
        # Qt가 spinbox keyPressEvent/editingFinished 뒤에 포커스를 다시 잡는 경우 대비.
        QTimer.singleShot(0, clear_and_move_focus)
        QTimer.singleShot(30, clear_and_move_focus)
        return True

    def commit_active_text_editors_before_undo(self):
        """Undo 직전 열린 셀/인라인 텍스트 편집을 data에 먼저 확정한다."""
        try:
            if getattr(self, "inline_text_editor", None) is not None:
                self.finish_inline_text_edit(commit=True, refresh=False)
        except Exception:
            pass

        fw = QApplication.focusWidget()
        if fw is None:
            return

        # 우측 텍스트 표의 임시 편집기라면 닫아서 itemChanged를 먼저 발생시킨다.
        try:
            if getattr(self, "tab", None) is not None and (fw is self.tab or self.tab.isAncestorOf(fw)):
                try:
                    self.tab.commitData(fw)
                except Exception:
                    pass
                try:
                    self.tab.closeEditor(fw, QAbstractItemDelegate.EndEditHint.NoHint)
                except Exception:
                    try:
                        fw.clearFocus()
                        self.tab.setFocus()
                    except Exception:
                        pass
                QApplication.processEvents()
        except Exception:
            pass

    def handle_global_undo_shortcut(self):
        self.commit_active_text_editors_before_undo()
        self.handle_general_undo()
        return True

    def make_safe_slot(self, func, *call_args, **call_kwargs):
        """Qt 시그널 인자와 충돌하지 않게 고정 인자 슬롯을 만든다.

        lambda *args, w=widget 형태는 PyQt 환경/신호 종류에 따라
        keyword-only 인자 오류를 만들 수 있어서 텍스트 UI에서는 이 헬퍼로 통일한다.
        """
        def _slot(*signal_args):
            return func(*call_args, **call_kwargs)
        return _slot

    def make_safe_deferred_input_slot(self, widget, line_edit=None):
        """입력칸 포커스 확정용 지연 슬롯. w 키워드 캡처 람다를 완전히 제거한다."""
        target_widget = widget
        target_line = line_edit
        def _slot(*signal_args):
            try:
                if target_line is not None and QApplication.focusWidget() is not target_line:
                    return
            except Exception:
                pass
            QTimer.singleShot(0, lambda: self.finish_single_line_input_by_enter(target_widget))
        return _slot

    def make_safe_click_slot(self, widget):
        target_widget = widget
        def _slot(*signal_args):
            if target_widget is not None:
                return target_widget.click()
        return _slot

    def install_enter_escape_for_input(self, widget):
        """QSpinBox 내부 editor가 Enter를 삼키는 경우까지 대비해 직접 필터/시그널을 붙인다."""
        if widget is None:
            return
        try:
            widget.installEventFilter(self)
        except Exception:
            pass

        def install_line():
            try:
                line = widget.lineEdit()
            except Exception:
                line = None
            if line is not None:
                try:
                    line.installEventFilter(self)
                except Exception:
                    pass
                try:
                    line.returnPressed.connect(self.make_safe_slot(self.finish_single_line_input_by_enter, widget))
                except Exception:
                    pass
                try:
                    line.editingFinished.connect(self.make_safe_deferred_input_slot(widget, line))
                except Exception:
                    pass

        install_line()
        QTimer.singleShot(0, install_line)

        try:
            if isinstance(widget, QLineEdit):
                widget.returnPressed.connect(self.make_safe_slot(self.finish_single_line_input_by_enter, widget))
        except Exception:
            pass

    def install_main_input_enter_escape_filters(self):
        """메인 상단 조작부 입력칸에서 Enter가 포커스 탈출로 동작하게 한다."""
        for widget in (
            getattr(self, "cb_font", None),
            getattr(self, "sb_font_size", None),
            getattr(self, "sb_strk", None),
            getattr(self, "sb_line_spacing", None),
            getattr(self, "sb_letter_spacing", None),
            getattr(self, "sb_char_width", None),
            getattr(self, "sb_char_height", None),
            getattr(self, "cb_item_text_preset", None),
            getattr(self, "cb_trans_provider", None),
            getattr(self, "sb_trans_chunk", None),
            getattr(self, "sb_final_paint_opacity", None),
            getattr(self, "sb_magic_tolerance", None),
            getattr(self, "sb_magic_expand", None),
        ):
            self.install_enter_escape_for_input(widget)

    def register_delayed_tooltip(self, widget, title, shortcut_text="", description=""):
        if widget is None:
            return

        # QWidget 툴팁과 QAction 툴팁이 동시에 살아 있으면
        # 작은 기본 툴팁 + 지연 툴팁 + 상태 설명이 중복 표시될 수 있다.
        # 그래서 실제 표시는 이 지연 툴팁 하나로 통일한다.
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
            title = self.tr_msg(title)
            description = self.tr_msg(description)
        except Exception:
            pass
        force_white_in_light = False
        try:
            force_white_in_light = bool(widget.property("force_white_tooltip_in_light") or widget.property("force_dark_tooltip"))
        except Exception:
            force_white_in_light = False
        widget.setProperty("delayed_tooltip_title", title)
        widget.setProperty("delayed_tooltip_shortcut", shortcut_text)
        widget.setProperty("delayed_tooltip_description", description)
        force_outline = False
        try:
            force_outline = bool(widget.property("force_outlined_tooltip_text") or widget.property("force_color_tooltip_text"))
        except Exception:
            force_outline = False
        widget.setProperty("delayed_tooltip_force_white_in_light", force_white_in_light)
        widget.setProperty("delayed_tooltip_force_outline", force_outline)
        widget.setProperty("delayed_tooltip_html", self._tooltip_rich_text(title, shortcut_text, description, force_white_in_light=force_white_in_light, force_outline=force_outline))
        widget.installEventFilter(self)

    def _show_delayed_tooltip(self):
        widget = self._tooltip_target
        html = self._tooltip_html
        if widget is None or not html:
            return
        if not widget.isVisible():
            return
        try:
            raw_title = widget.property("delayed_tooltip_title")
            if raw_title:
                raw_shortcut = widget.property("delayed_tooltip_shortcut") or ""
                raw_desc = widget.property("delayed_tooltip_description") or ""
                force_white = bool(widget.property("delayed_tooltip_force_white_in_light"))
                force_outline = bool(widget.property("delayed_tooltip_force_outline"))
                html = self._tooltip_rich_text(raw_title, raw_shortcut, raw_desc, force_white_in_light=force_white, force_outline=force_outline)
                self._tooltip_html = html
        except Exception:
            pass
        try:
            pos = widget.mapToGlobal(QPoint(widget.width() // 2, widget.height()))
        except Exception:
            pos = QCursor.pos()
        QToolTip.showText(pos, html, widget)

    def eventFilter(self, obj, event):
        et = event.type()
        if et in (QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop) and self._is_own_window_object(obj):
            try:
                images, ysb = self._dragged_supported_files(event)
                if images or ysb:
                    event.acceptProposedAction()
                    if et == QEvent.Type.Drop:
                        self.handle_supported_file_drop(event)
                    return True
            except Exception:
                pass
        if et == QEvent.Type.Show and isinstance(obj, QDialog):
            try:
                p = obj.parent()
                while p is not None:
                    if p is self:
                        self.schedule_native_title_bar_theme(obj, dark=not self.is_light_theme())
                        break
                    p = p.parent()
            except Exception:
                pass
        if et in (QEvent.Type.KeyPress, QEvent.Type.ShortcutOverride) and self._is_own_window_object(obj):
            try:
                key = event.key()
                mods = event.modifiers()
                ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)

                if key == Qt.Key.Key_Escape and self.escape_single_line_input_focus_first(obj):
                    event.accept()
                    return True

                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
                    mods & (
                        Qt.KeyboardModifier.ControlModifier
                        | Qt.KeyboardModifier.ShiftModifier
                        | Qt.KeyboardModifier.AltModifier
                    )
                ):
                    # 사용자는 입력을 끝낼 때 습관적으로 Enter를 누른다.
                    # QLineEdit/스핀박스/편집 가능한 콤보박스에서는 Enter가 옆 버튼을 누르거나
                    # 다음 위젯을 건드리지 않고, 편집을 확정한 뒤 포커스만 빠지게 한다.
                    if self.finish_single_line_input_by_enter(obj):
                        event.accept()
                        return True

                if et == QEvent.Type.ShortcutOverride:
                    return False

                if self._event_matches_shortcut(event, "paint_undo") or (ctrl and key == Qt.Key.Key_Z):
                    self.handle_global_undo_shortcut()
                    event.accept()
                    return True
                if self._event_matches_shortcut(event, "paint_redo") or (ctrl and key == Qt.Key.Key_Y):
                    self.handle_general_redo()
                    event.accept()
                    return True
                if key == Qt.Key.Key_Delete:
                    # 텍스트 셀 편집 중 Delete는 글자 삭제로만 동작해야 한다.
                    # 여기서 행 삭제로 처리하면 사용자가 번역문을 수정하다가 라인이 통째로 삭제된다.
                    if self.is_editing_table_text_cell():
                        return False
                    fw = QApplication.focusWidget()
                    in_table = getattr(self, "tab", None) is not None and (fw is self.tab or self.tab.isAncestorOf(fw))
                    if in_table and self.selected_table_text_ids():
                        self.delete_text_data_items(ask=True)
                        event.accept()
                        return True
            except Exception:
                pass
        if hasattr(obj, "property") and (obj.property("delayed_tooltip_title") or obj.property("delayed_tooltip_html")):
            # QAction/QToolButton 기본 툴팁은 action text를 작게 띄우는 경우가 있다.
            # 예: W, ☐ 같은 "아이콘 확대"처럼 보이는 검은 툴팁.
            # 지연 툴팁 하나만 쓰기 위해 기본 ToolTip 이벤트는 완전히 막는다.
            if et == QEvent.Type.ToolTip:
                return True

            if et == QEvent.Type.Enter:
                self._tooltip_target = obj
                try:
                    raw_title = obj.property("delayed_tooltip_title")
                    if raw_title:
                        self._tooltip_html = self._tooltip_rich_text(
                            raw_title,
                            obj.property("delayed_tooltip_shortcut") or "",
                            obj.property("delayed_tooltip_description") or "",
                            force_white_in_light=bool(obj.property("delayed_tooltip_force_white_in_light")),
                        )
                    else:
                        self._tooltip_html = obj.property("delayed_tooltip_html") or ""
                except Exception:
                    self._tooltip_html = obj.property("delayed_tooltip_html") or ""
                self._tooltip_timer.start(500)
            elif et in (QEvent.Type.Leave, QEvent.Type.MouseButtonPress, QEvent.Type.Hide, QEvent.Type.FocusOut):
                if self._tooltip_target is obj:
                    self._tooltip_timer.stop()
                    self._tooltip_target = None
                    self._tooltip_html = ""
                    QToolTip.hideText()
        return super().eventFilter(obj, event)

    def configure_ui_tooltips(self):
        def seq_text(key):
            if key.startswith("RAW:"):
                return key[4:]
            try:
                return self.shortcut_settings.seq(key).toString(QKeySequence.SequenceFormat.NativeText)
            except Exception:
                return ""

        # 좌측 그림판/마스크 도구
        if hasattr(self, "tb") and self.tb is not None:
            action_info = []
            if hasattr(self, "act_brush"): action_info.append((self.act_brush, "브러시", seq_text("paint_brush")))
            if hasattr(self, "act_erase"): action_info.append((self.act_erase, "지우개", seq_text("paint_erase")))
            if hasattr(self, "act_reanal"): action_info.append((self.act_reanal, "재분석", seq_text("paint_reanalyze")))
            if hasattr(self, "act_undo"): action_info.append((self.act_undo, "작업 취소", seq_text("paint_undo")))
            if hasattr(self, "act_redo"): action_info.append((self.act_redo, "작업 재실행", seq_text("paint_redo")))
            if hasattr(self, "act_magic"): action_info.append((self.act_magic, "요술봉 선택", seq_text("paint_magic_select")))
            if hasattr(self, "act_mask_wrap"): action_info.append((self.act_mask_wrap, "마스크 랩핑", seq_text("paint_mask_wrap"), "영역 안의 떨어진 마스크들을 하나의 채움 영역으로 감싸줍니다."))
            if hasattr(self, "act_mask_cut"): action_info.append((self.act_mask_cut, "마스크 커팅", seq_text("paint_mask_cut"), "선택 영역 밖 경계를 지정 픽셀만큼 잘라 붙어 있는 마스크를 분리합니다."))
            if hasattr(self, "act_final_text_tool"): action_info.append((self.act_final_text_tool, "최종 텍스트 도구", seq_text("final_text_tool"), "최종화면을 클릭하면 텍스트 영역을 만듭니다. 내용 작성 후 Ctrl+Return을 누르거나 다른 곳을 클릭하면 작성이 완료됩니다."))
            if hasattr(self, "act_final_paint_to_bg"): action_info.append((self.act_final_paint_to_bg, "최종 페인팅을 배경으로 반영", seq_text("final_paint_to_background")))
            if hasattr(self, "act_final_paint_above_text"): action_info.append((self.act_final_paint_above_text, "텍스트 위에 페인팅", seq_text("final_paint_above_toggle"), "ON이면 이후 새로 칠하는 브러시가 텍스트보다 위 레이어에 그려집니다."))
            for info in action_info:
                try:
                    if len(info) >= 4:
                        act, title, sk, desc = info
                    else:
                        act, title, sk = info
                        desc = ""
                    self.register_delayed_tooltip(self.tb.widgetForAction(act), title, sk, desc)
                except Exception:
                    pass

        if hasattr(self, "act_final_paint_color") and hasattr(self, "tb"):
            try:
                w = self.tb.widgetForAction(self.act_final_paint_color)
                if w is not None:
                    w.setProperty("force_outlined_tooltip_text", True)
                    w.setProperty("force_color_tooltip_text", True)
                self.register_delayed_tooltip(w, "최종 페인팅 색상", seq_text("final_paint_color"), "스포이드: Alt+마우스 좌클릭")
            except Exception:
                self.register_delayed_tooltip(self.tb.widgetForAction(self.act_final_paint_color), "최종 페인팅 색상", seq_text("final_paint_color"), "스포이드: Alt+마우스 좌클릭")
        if hasattr(self, "mask_toggle_wrap"):
            self.register_delayed_tooltip(
                self.mask_toggle_wrap,
                "페인팅 마스크 ON/OFF",
                seq_text("paint_mask_toggle"),
                "ON은 분석 기반, OFF는 직접 칠한 마스크를 사용합니다."
            )
        if hasattr(self, "final_paint_option_bar"):
            self.register_delayed_tooltip(self.sb_final_paint_opacity, "최종 브러시 불투명도", f"{seq_text('final_paint_opacity_dec')} / {seq_text('final_paint_opacity_inc')}", "최종화면 브러시 색상의 알파값을 조절합니다.")
        if hasattr(self, "magic_wand_bar"):
            self.register_delayed_tooltip(self.btn_magic_expand, "선택 영역 확장", seq_text("paint_magic_expand"))
            self.register_delayed_tooltip(self.btn_magic_fill, "마스킹 칠하기", seq_text("paint_magic_fill"))
            self.register_delayed_tooltip(self.sb_magic_tolerance, "RGB 허용범위", f"{seq_text('paint_magic_tolerance_inc')} / {seq_text('paint_magic_tolerance_dec')}")
            self.register_delayed_tooltip(self.sb_magic_expand, "영역 확장 범위", f"{seq_text('paint_magic_expand_inc')} / {seq_text('paint_magic_expand_dec')}")
        if hasattr(self, "mask_wrap_bar"):
            self.register_delayed_tooltip(self.btn_mask_wrap_rect, "사각형으로 영역 그리기", seq_text("paint_mask_wrap_rect"), "윈도우 캡처처럼 사각형 범위를 잡고 그 안의 마스크들을 하나로 감싸 채웁니다.")
            self.register_delayed_tooltip(self.btn_mask_wrap_free, "자유형으로 영역 그리기", seq_text("paint_mask_wrap_free"), "드래그한 자유형 범위 안에서만 마스크들을 하나로 감싸 채웁니다.")
        if hasattr(self, "mask_cut_bar"):
            self.register_delayed_tooltip(self.btn_mask_cut_rect, "사각형으로 영역 그리기", seq_text("paint_mask_wrap_rect"), "사각형 보존 영역의 바깥 경계를 지정 픽셀만큼 잘라냅니다.")
            self.register_delayed_tooltip(self.btn_mask_cut_free, "자유형으로 영역 그리기", seq_text("paint_mask_wrap_free"), "자유형 보존 영역의 바깥 경계를 지정 픽셀만큼 잘라냅니다.")
            self.register_delayed_tooltip(self.sb_mask_cut_px, "커팅 폭", "", "선택 영역 밖으로 잘라낼 마스크 폭입니다.")

        # 툴팁 글자색은 테마 기본값을 따른다.
        # 색상 버튼처럼 특수한 경우만 개별 QToolTip 스타일에서 처리한다.

        # 우측 상단 작업 버튼/옵션
        if hasattr(self, "sb_trans_chunk"):
            self.register_delayed_tooltip(self.sb_trans_chunk, "묶음 수", "", "한 번의 API 요청에 묶어서 보낼 텍스트 줄 수")
        if hasattr(self, "btn_text_mask_reanalyze"):
            self.register_delayed_tooltip(self.btn_text_mask_reanalyze, "텍스트 마스크 재분석", seq_text("paint_reanalyze"), "텍스트 마스크 영역을 기준으로 OCR을 다시 실행합니다.")
        if hasattr(self, "btn_analyze"):
            self.register_delayed_tooltip(self.btn_analyze, "분석", seq_text("work_analyze"), "현재 페이지를 분석합니다.")
        if hasattr(self, "btn_translate"):
            self.register_delayed_tooltip(self.btn_translate, "번역", seq_text("work_translate"))
        if hasattr(self, "btn_inpaint"):
            self.register_delayed_tooltip(self.btn_inpaint, "인페인팅", seq_text("work_inpaint"))
        if hasattr(self, "btn_text_cleanup"):
            self.register_delayed_tooltip(self.btn_text_cleanup, "텍스트 정리", seq_text("work_clean_text"))
        if hasattr(self, "cb_show_final_text"):
            self.register_delayed_tooltip(self.cb_show_final_text, "텍스트 표시 ON/OFF", seq_text("view_text_toggle"))
        if hasattr(self, "cb_font"):
            self.register_delayed_tooltip(self.cb_font, "글꼴", seq_text("item_font_select"), "현재 선택한 텍스트의 글꼴을 바꿉니다.")
        if hasattr(self, "sb_font_size"):
            self.register_delayed_tooltip(self.sb_font_size, "글꼴 크기", seq_text("text_font_size"), "현재 선택한 텍스트의 글자 크기를 조절합니다.")
        if hasattr(self, "sb_strk"):
            self.register_delayed_tooltip(self.sb_strk, "획 크기", seq_text("text_stroke_size"), "현재 선택한 텍스트의 외곽선 두께를 조절합니다.")
        if hasattr(self, "sb_line_spacing"):
            self.register_delayed_tooltip(self.sb_line_spacing, "행간", seq_text("text_line_spacing"), "줄과 줄 사이 간격을 조절합니다.")
        if hasattr(self, "sb_letter_spacing"):
            self.register_delayed_tooltip(self.sb_letter_spacing, "자간", seq_text("text_letter_spacing"), "글자와 글자 사이 간격을 조절합니다.")
        if hasattr(self, "sb_char_width"):
            self.register_delayed_tooltip(self.sb_char_width, "너비", seq_text("text_char_width"), "문자의 가로 비율을 조절합니다.")
        if hasattr(self, "sb_char_height"):
            self.register_delayed_tooltip(self.sb_char_height, "높이", seq_text("text_char_height"), "문자의 세로 비율을 조절합니다.")
        if hasattr(self, "btn_bold"):
            self.register_delayed_tooltip(self.btn_bold, "굵게", seq_text("text_bold_toggle"))
            self.register_delayed_tooltip(self.btn_italic, "기울이기", seq_text("text_italic_toggle"))
            self.register_delayed_tooltip(self.btn_strike, "취소선", seq_text("text_strike_toggle"))
        if hasattr(self, "btn_prev_page"):
            self.register_delayed_tooltip(self.btn_prev_page, "이전 페이지", seq_text("work_page_prev"))
        if hasattr(self, "btn_next_page"):
            self.register_delayed_tooltip(self.btn_next_page, "다음 페이지", seq_text("work_page_next"))
        if hasattr(self, "btn_page_tab_menu"):
            self.register_delayed_tooltip(self.btn_page_tab_menu, "페이지 목록", seq_text("work_page_list"))
        if hasattr(self, "btn_page_scroll_left"):
            self.register_delayed_tooltip(self.btn_page_scroll_left, "페이지 탭 왼쪽 이동", "")
        if hasattr(self, "btn_page_scroll_right"):
            self.register_delayed_tooltip(self.btn_page_scroll_right, "페이지 탭 오른쪽 이동", "")
        if hasattr(self, "btn_page_add"):
            self.register_delayed_tooltip(self.btn_page_add, "이미지 불러오기", seq_text("project_import_images"), "현재 프로젝트에서는 현재 페이지 뒤에 이미지를 추가합니다.")
        if hasattr(self, "btn_project_exit"):
            self.register_delayed_tooltip(self.btn_project_exit, "프로젝트 나가기", seq_text("project_exit"))
        if hasattr(self, "btn_page"):
            self.register_delayed_tooltip(self.btn_page, "페이지 이동", "", "현재 페이지 번호를 눌러 원하는 페이지로 바로 이동합니다.")
        if hasattr(self, "cb_mode"):
            self.register_delayed_tooltip(self.cb_mode, "작업 탭", seq_text("work_tab_cycle"), "원본, 분석도, 마스크, 최종결과 탭을 전환합니다.")
        if hasattr(self, "btn_quick_undo"):
            self.register_delayed_tooltip(self.btn_quick_undo, "뒤로가기", seq_text("paint_undo"), "최근 작업을 되돌립니다.")
        if hasattr(self, "btn_quick_redo"):
            self.register_delayed_tooltip(self.btn_quick_redo, "앞으로 가기", seq_text("paint_redo"), "되돌린 작업을 다시 실행합니다.")
        if hasattr(self, "cb_text_preset"):
            self.register_delayed_tooltip(self.cb_text_preset, "페이지 프리셋", "", "현재 페이지/전체 페이지에 적용할 글꼴 프리셋을 선택합니다.")
        if hasattr(self, "btn_preset_save"):
            self.register_delayed_tooltip(self.btn_preset_save, "페이지 프리셋 저장", "", "현재 글꼴 설정을 페이지 프리셋으로 저장합니다.")
        if hasattr(self, "btn_preset_import"):
            self.register_delayed_tooltip(self.btn_preset_import, "페이지 프리셋 가져오기", "", "외부 프리셋 JSON을 가져옵니다.")
        if hasattr(self, "btn_preset_apply_page"):
            self.register_delayed_tooltip(self.btn_preset_apply_page, "현재 페이지 프리셋 적용", "", "선택한 페이지 프리셋을 현재 페이지에 적용합니다.")
        if hasattr(self, "btn_preset_apply_all"):
            self.register_delayed_tooltip(self.btn_preset_apply_all, "전체 페이지 프리셋 적용", "", "선택한 페이지 프리셋을 전체 페이지에 적용합니다.")
        if hasattr(self, "cb_item_text_preset"):
            self.register_delayed_tooltip(self.cb_item_text_preset, "개별 프리셋", "", "선택한 텍스트 객체에 적용할 개별 글꼴 프리셋을 선택합니다.")
        if hasattr(self, "btn_text_color"):
            try:
                self.btn_text_color.setProperty("force_outlined_tooltip_text", True)
                self.btn_text_color.setProperty("force_color_tooltip_text", True)
            except Exception:
                pass
            self.register_delayed_tooltip(self.btn_text_color, "문자 색상", seq_text("item_text_color"))
        if hasattr(self, "btn_stroke_color"):
            try:
                self.btn_stroke_color.setProperty("force_outlined_tooltip_text", True)
                self.btn_stroke_color.setProperty("force_color_tooltip_text", True)
            except Exception:
                pass
            self.register_delayed_tooltip(self.btn_stroke_color, "획 색상", seq_text("item_stroke_color"))
        if hasattr(self, "btn_item_text_color"):
            try:
                self.btn_item_text_color.setProperty("force_outlined_tooltip_text", True)
                self.btn_item_text_color.setProperty("force_color_tooltip_text", True)
            except Exception:
                pass
            self.register_delayed_tooltip(self.btn_item_text_color, "문자 색상", seq_text("item_text_color"))
        if hasattr(self, "btn_item_stroke_color"):
            try:
                self.btn_item_stroke_color.setProperty("force_outlined_tooltip_text", True)
                self.btn_item_stroke_color.setProperty("force_color_tooltip_text", True)
            except Exception:
                pass
            self.register_delayed_tooltip(self.btn_item_stroke_color, "획 색상", seq_text("item_stroke_color"))
        if hasattr(self, "btn_align_left"):
            self.register_delayed_tooltip(self.btn_align_left, "왼쪽 정렬", seq_text("item_align_left"))
            self.register_delayed_tooltip(self.btn_align_center, "가운데 정렬", seq_text("item_align_center"))
            self.register_delayed_tooltip(self.btn_align_right, "오른쪽 정렬", seq_text("item_align_right"))

    def message_box_style(self):
        """확인/경고/질문창 공통 스타일. 홈/클라우드 쪽의 부드러운 카드 톤에 맞춘다."""
        if self.is_light_theme():
            return """
                QMessageBox, QMessageBox QWidget { background:#f4f6fa; color:#111827; }
                QMessageBox QLabel { background:#f4f6fa; color:#111827; line-height:1.35em; }
                QMessageBox QLabel, QMessageBox QFrame {
                    border:0px;
                }
                QMessageBox QTextEdit, QMessageBox QPlainTextEdit, QMessageBox QScrollArea {
                    background:#ffffff;
                    color:#111827;
                    border:1px solid #cfd7e5;
                    selection-background-color:#dbeafe;
                    selection-color:#111827;
                }
                QMessageBox QPushButton {
                    background:#ffffff;
                    color:#111827;
                    border:1px solid #cfd7e5;
                    border-radius:0px;
                    padding:7px 18px;
                    min-width:72px;
                }
                QMessageBox QPushButton:hover { background:#edf4ff; border-color:#aac4e8; }
                QMessageBox QPushButton:pressed { background:#e3edf9; }
                QMessageBox QToolTip { background-color:#ffffff; color:#111827; border:1px solid #cfd7e5; border-radius:0px; padding:5px; }
            """
        return """
            QMessageBox, QMessageBox QWidget { background:#24272d; color:#f2f4f8; }
            QMessageBox QLabel { background:#24272d; color:#f2f4f8; line-height:1.35em; }
            QMessageBox QLabel, QMessageBox QFrame {
                border:0px;
            }
            QMessageBox QTextEdit, QMessageBox QPlainTextEdit, QMessageBox QScrollArea {
                background:#1f232a;
                color:#f2f4f8;
                border:1px solid #3b414c;
                selection-background-color:#3d587d;
                selection-color:#ffffff;
            }
            QMessageBox QPushButton {
                background:#333843;
                color:#f2f4f8;
                border:1px solid #586173;
                border-radius:0px;
                padding:7px 18px;
                min-width:72px;
            }
            QMessageBox QPushButton:hover { background:#3d4654; border-color:#74839a; }
            QMessageBox QPushButton:pressed { background:#2b3038; }
            QMessageBox QToolTip { background-color:#1f2430; color:#ffffff; border:1px solid #4b5563; border-radius:0px; padding:5px; }
        """

    def _message_button_with_shortcut(self, button, key_text):
        """QMessageBox 버튼에 문자 단축키를 붙인다. 예: Y/N."""
        try:
            button.setShortcut(QKeySequence(str(key_text)))
        except Exception:
            pass
        try:
            button.setAutoDefault(True)
        except Exception:
            pass
        return button

    def ask_yes_no_shortcut(self, title, message, yes_text="예", no_text="아니오", default_yes=True, icon=QMessageBox.Icon.Question, parent=None):
        """Enter/Y/N이 동작하는 단순 확인창. 버튼에는 반드시 (Y)/(N)을 표시한다."""
        msg = QMessageBox(parent or self)
        msg.setIcon(icon)
        msg.setWindowTitle(self.tr_ui(title))
        msg.setText(self.tr_ui(message))
        msg.setStyleSheet(self.message_box_style())
        btn_yes = msg.addButton(f"{self.tr_ui(yes_text)} (Y)", QMessageBox.ButtonRole.AcceptRole)
        btn_no = msg.addButton(f"{self.tr_ui(no_text)} (N)", QMessageBox.ButtonRole.RejectRole)
        self._message_button_with_shortcut(btn_yes, "Y")
        self._message_button_with_shortcut(btn_no, "N")
        try:
            msg.setDefaultButton(btn_yes if default_yes else btn_no)
        except Exception:
            pass
        try:
            msg.setEscapeButton(btn_no)
        except Exception:
            pass
        msg.exec()
        return msg.clickedButton() == btn_yes

    def show_ok_notice(self, title, message, parent=None):
        """확인 버튼 하나만 있는 알림창. Enter로 닫힌다."""
        msg = QMessageBox(parent or self)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle(self.tr_ui(title))
        msg.setText(self.tr_ui(message))
        msg.setStyleSheet(self.message_box_style())
        btn_ok = msg.addButton(self.tr_ui("확인"), QMessageBox.ButtonRole.AcceptRole)
        try:
            msg.setDefaultButton(btn_ok)
        except Exception:
            pass
        force_message_box_front(msg)
        msg.exec()

    def _show_launcher_screen_only(self):
        """프로젝트 상태를 건드리지 않고 런처 화면만 표시한다. 내부 전용."""
        try:
            if hasattr(self, "launcher_widget"):
                self.launcher_widget.refresh()
            if hasattr(self, "main_stack") and hasattr(self, "launcher_widget"):
                self.main_stack.setCurrentWidget(self.launcher_widget)
            self.update_project_exit_button_visibility()
        except Exception:
            pass

    def clear_current_project_runtime_state(self):
        """런처로 돌아가기 위해 현재 프로젝트 세션을 완전히 닫는다."""
        try:
            if getattr(self, "inline_text_editor", None) is not None:
                try:
                    self.finish_inline_text_edit(commit=True, refresh=False)
                except Exception:
                    pass
            if getattr(self, "project_dir", None) and getattr(self, "paths", None):
                try:
                    self.commit_current_page_ui_to_data()
                except Exception:
                    pass
        except Exception:
            pass

        try:
            self.cleanup_work_cache()
        except Exception:
            pass
        try:
            self.delete_temp_project_if_needed()
        except Exception:
            pass

        self.paths = []
        self.data = {}
        self.idx = 0
        self.project_store = ProjectStore()
        self.project_dir = None
        self.ysbt_package_path = None
        self.suggested_project_name = None
        self.is_temp_project = False
        self.work_project_store = None
        self.work_project_dir = None
        self.has_unsaved_changes = False
        self.page_text_undo_stacks = {}
        self.project_undo_stack = []
        self.project_redo_stack = []
        self.undo_boundary = None
        self.project_ui_view_states = {}
        self.magic_wand_mask = None
        self.magic_wand_seed = None
        self.magic_wand_seeds = []
        self.magic_wand_history = []
        self.text_clipboard = []
        self.text_paste_pending = False

        try:
            if hasattr(self, "tab") and self.tab is not None:
                self.tab.blockSignals(True)
                self.tab.setRowCount(0)
                self.tab.blockSignals(False)
        except Exception:
            pass
        try:
            if hasattr(self, "view") and self.view is not None:
                self.view.set_image(None)
        except Exception:
            try:
                self.view.scene.clear()
            except Exception:
                pass
        try:
            self.update_undo_redo_buttons()
        except Exception:
            pass
        try:
            self.update_window_title()
        except Exception:
            pass
        try:
            self.refresh_page_tabs()
        except Exception:
            pass
        try:
            self.update_project_exit_button_visibility()
        except Exception:
            pass

    def show_launcher(self):
        """홈화면으로 이동한다. 홈화면은 열린 프로젝트가 없는 상태여야 한다."""
        if getattr(self, "is_batch_running", False):
            QMessageBox.information(
                self,
                self.tr_ui("일괄 작업 중"),
                self.tr_ui("일괄 작업 중에는 홈화면으로 이동할 수 없습니다.\n작업이 끝난 뒤 다시 시도해 주세요."),
            )
            return

        if self.has_open_project():
            # 홈화면은 휴대폰 홈처럼 빈 상태여야 하므로, 현재 파일/프로젝트 세션을 먼저 닫는다.
            try:
                if getattr(self, "project_dir", None) and getattr(self, "paths", None):
                    self.commit_current_page_ui_to_data()
                    if getattr(self, "auto_save_enabled", False):
                        self.auto_save_project()
            except Exception as e:
                try:
                    self.log(f"⚠️ 홈화면 이동 전 현재 화면 반영 실패: {e}")
                except Exception:
                    pass

            if getattr(self, "has_unsaved_changes", False):
                if not self.confirm_unsaved_before_switch():
                    self.log("↩️ 홈화면 이동 취소")
                    return

            self.clear_current_project_runtime_state()
            self.log("🏠 프로젝트를 닫고 홈화면으로 이동했습니다.")

        self._show_launcher_screen_only()

    def confirm_open_recent_project(self, path):
        """최근 프로젝트 카드는 바로 열지 않고 한 번 확인한다."""
        path = str(path or "")
        if not path or not os.path.exists(path):
            QMessageBox.warning(
                self,
                self.tr_ui("파일을 찾을 수 없음"),
                self.tr_msg("최근 프로젝트 파일을 찾을 수 없습니다.\n최근 목록에서 제거하거나 파일 위치를 확인해 주세요."),
            )
            return
        name = Path(path).name
        message = self.tr_msg("이 최근 프로젝트를 열까요?") + f"\n\n{name}"
        if not self.ask_yes_no_shortcut("최근 프로젝트 열기", message, yes_text="열기", no_text="취소", default_yes=True):
            self.log("↩️ 최근 프로젝트 열기 취소")
            return
        self.open_project_path(path)

    def show_editor(self):
        """런처에서 실제 작업 화면으로 전환한다."""
        try:
            if hasattr(self, "main_stack") and hasattr(self, "editor_widget"):
                self.main_stack.setCurrentWidget(self.editor_widget)
                # 에디터 화면이 실제 배치된 뒤 우측 작업 패널을 기본 폭으로 맞춘다.
                # 기본 폭은 사용자지정 콤보박스까지 잘리지 않는 상태를 기준으로 한다.
                try:
                    QTimer.singleShot(0, self.restore_editor_splitter_default_width)
                except Exception:
                    pass
            self.update_project_exit_button_visibility()
        except Exception:
            pass

    def restore_editor_splitter_default_width(self):
        """좌우 splitter를 우측 작업 패널 기준 기본 폭으로 복원한다."""
        try:
            split = getattr(self, "editor_splitter", None)
            if split is not None and hasattr(split, "reset_to_default_right_panel_width"):
                split.reset_to_default_right_panel_width()
        except Exception:
            pass

    def refresh_launcher(self):
        try:
            if hasattr(self, "launcher_widget"):
                self.launcher_widget.refresh()
        except Exception:
            pass

    def record_current_project_recent(self):
        """현재 열린 YSBT 프로젝트를 최근 목록에 기록하고 첫 페이지 썸네일을 캐시한다."""
        try:
            package_path = getattr(self, "ysbt_package_path", None)
            if not package_path or not os.path.exists(str(package_path)):
                return False
            store = getattr(self, "recent_project_store", None) or RecentProjectStore()
            self.recent_project_store = store
            title = self.display_project_name() or Path(package_path).stem
            thumb = store.make_thumbnail(getattr(self, "paths", []) or [], package_path)
            store.add_project(
                package_path,
                title=title,
                page_count=len(getattr(self, "paths", []) or []),
                thumbnail_path=thumb,
                cloud_backup_status="local_only",
            )
            self.refresh_launcher()
            return True
        except Exception as e:
            try:
                self.log(f"⚠️ 최근 프로젝트 기록 실패: {e}")
            except Exception:
                pass
            return False

    def remove_recent_project_from_launcher(self, path):
        try:
            if hasattr(self, "recent_project_store"):
                self.recent_project_store.remove_project(path)
            self.refresh_launcher()
        except Exception:
            pass

    def _open_path_location_in_file_manager(self, path, select_file=True):
        """파일/폴더 위치를 OS 파일 관리자에서 연다.

        홈화면 최근 프로젝트의 "폴더 위치 열기"는 .ysbt 파일의 부모 폴더를
        열어야 한다. 기존 QDesktopServices.openUrl(QUrl.fromLocalFile(folder))만
        쓰면 Windows 환경/상대경로/현재 작업 디렉터리 상태에 따라 바탕화면 같은
        엉뚱한 위치가 열릴 수 있어, Windows에서는 explorer.exe를 직접 호출한다.
        """
        raw = str(path or "").strip().strip('"')
        if not raw:
            raise FileNotFoundError(self.tr_ui("최근 프로젝트 파일을 찾을 수 없습니다.\n최근 목록에서 제거하거나 파일 위치를 확인해 주세요."))

        raw = os.path.expandvars(os.path.expanduser(raw))
        target = os.path.abspath(raw)

        if os.path.isfile(target):
            folder = os.path.dirname(target)
            if sys.platform.startswith("win") and select_file:
                # 파일 위치를 열면서 해당 .ysbt 파일을 선택한다.
                # 리스트 인자로 넘겨 공백/한글 경로를 안전하게 처리한다.
                subprocess.Popen(["explorer.exe", f"/select,{target}"])
                return target
        elif os.path.isdir(target):
            folder = target
        else:
            folder = os.path.dirname(target)
            if not folder or not os.path.isdir(folder):
                raise FileNotFoundError(target)

        folder = os.path.abspath(folder)
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer.exe", folder])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        return folder

    def reveal_recent_project_in_folder(self, path):
        try:
            self._open_path_location_in_file_manager(path, select_file=True)
        except Exception as e:
            QMessageBox.warning(self, self.tr_ui("폴더 열기 실패"), str(e))

    def open_current_project_work_folder(self):
        """현재 열려 있는 프로젝트의 실제 작업 폴더를 탐색기에서 연다."""
        project_dir = getattr(self, "project_dir", None)
        if not project_dir:
            QMessageBox.information(
                self,
                self.tr_ui("작업 폴더 열기"),
                self.tr_ui("현재 열린 프로젝트가 없습니다."),
            )
            return
        folder = os.path.abspath(str(project_dir))
        if not os.path.isdir(folder):
            QMessageBox.warning(
                self,
                self.tr_ui("작업 폴더 열기 실패"),
                f"{self.tr_ui('현재 프로젝트 작업 폴더를 찾을 수 없습니다.')}\n\n{folder}",
            )
            return
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
            self.log(f"📁 {self.tr_ui('현재 프로젝트 작업 폴더를 열었습니다.')}: {folder}")
        except Exception as e:
            QMessageBox.warning(self, self.tr_ui("작업 폴더 열기 실패"), str(e))

