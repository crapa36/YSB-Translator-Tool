from ysb.ui.main_window_support import *


class MainWindowInteractionMixin:

    def _is_local_edition_for_ui(self):
        """Return True only for the Local edition UI.

        LOCAL CUDA diagnosis installs/checks the program-managed GPU runtime.
        Lite/API builds must not expose this action through menus, shortcuts,
        macros, or stale cached commands.  Fail closed when the edition cannot
        be resolved.
        """
        try:
            from ysb.editions.current import is_local_edition
            return bool(is_local_edition())
        except Exception:
            return False

    def setup_actions(self):
        def make_action(key, text, slot):
            action = QAction(text, self)
            def _guarded_slot(*args, _slot=slot, _key=key):
                if self._block_global_action_during_inline_text_edit(_key):
                    return
                _slot()
            action.triggered.connect(_guarded_slot)
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
        make_action("work_source_compare", "원본 비교창 열기/끄기", self.open_source_compare_view)
        make_action("work_page_prev", "이전 페이지", self.prev)
        make_action("work_page_next", "다음 페이지", self.next)
        make_action("work_page_list", "페이지 목록", self.show_page_tab_menu)
        make_action("work_page_full_name", "현재 페이지 이름 보기", self.show_current_page_full_name)
        make_action("work_page_rename_source", "페이지 탭 파일명 변경", self.rename_current_page_source_file)
        make_action("work_page_delete_current", "현재 페이지 탭 삭제", self.delete_current_page_shortcut)
        make_action("work_page_delete_all", "일괄 페이지탭 삭제", self.delete_all_pages_shortcut)
        make_action("work_open_current_project_folder", "현재 프로젝트의 작업 폴더로 이동하기", self.open_current_project_work_folder)
        make_action("work_analyze", "분석", self.anal)
        make_action("paint_auto_clean_detection_mask", "감지 마스크 자동 정리", self.auto_clean_detection_mask_current)
        try:
            _auto_clean_tip = "현재 OCR 병합 영역 안의 OCR 조각을 군체 단위로 묶고, 군체별 보호 영역을 만든 뒤 우선순위가 낮은 겹침 마스크를 커팅합니다. 정리 후 재분석을 실행하세요."
            self.actions["paint_auto_clean_detection_mask"].setToolTip(self.tr_msg(_auto_clean_tip))
            self.actions["paint_auto_clean_detection_mask"].setStatusTip(self.tr_msg(_auto_clean_tip))
            self.actions["paint_auto_clean_detection_mask"].setWhatsThis(self.tr_msg(_auto_clean_tip))
        except Exception:
            pass
        make_action("paint_reanalyze", "재분석", self.reanalyze_mask)
        try:
            _reanalyze_tip = "현재 텍스트 마스크를 기준으로 OCR 분석 영역을 다시 만들고, 기존 마스크는 재사용합니다."
            self.actions["paint_reanalyze"].setToolTip(self.tr_msg(_reanalyze_tip))
            self.actions["paint_reanalyze"].setStatusTip(self.tr_msg(_reanalyze_tip))
            self.actions["paint_reanalyze"].setWhatsThis(self.tr_msg(_reanalyze_tip))
        except Exception:
            pass
        make_action("work_quick_ocr", "빠른 OCR 설정", self.request_open_quick_ocr_dialog)
        make_action("quick_ocr_execute", "빠른 OCR 실행", self.start_quick_ocr_selection)
        # 빠른 OCR 설정은 프로그램 바탕/포커스 외부에 툴팁이 뜨면 거슬리므로
        # 단축키만 유지하고 일반 툴팁은 비워 둔다.
        try:
            self.actions["work_quick_ocr"].setToolTip("")
            self.actions["work_quick_ocr"].setStatusTip("")
            self.actions["work_quick_ocr"].setWhatsThis("")
            for prop in (
                "delayed_tooltip_title",
                "delayed_tooltip_shortcut",
                "delayed_tooltip_description",
                "delayed_tooltip_force_white_in_light",
                "delayed_tooltip_force_outline",
                "delayed_tooltip_html",
            ):
                self.setProperty(prop, None)
        except Exception:
            pass
        make_action("work_text_number_width", "텍스트 넘버 크기 변경", self.open_text_number_width_dialog)
        make_action("work_translate", "번역", self.trans)
        make_action("work_inpaint", "인페인팅", self.run_inpainting)
        make_action("work_import_clean_background", "클린본 불러오기", self.import_clean_background)
        make_action("work_inpaint_source", "배경을 원본으로 쓰기", self.use_inpainted_as_source)
        make_action("work_restore_original_source", "원본으로 돌아가기", self.restore_original_source)
        make_action("work_extract_text", "지문 추출", self.extract_text_current)
        make_action("work_import_translation", "번역문 불러오기", self.import_translation_current)
        make_action("work_clear_translation", "번역문 내용 지우기", self.clear_translation_current)
        make_action("work_clean_text", "텍스트 정리", self.clean_text_current)
        try:
            _text_clean_tip = "체크 해제한 OCR/텍스트 항목을 삭제하고 번호를 재정렬합니다. 활성 OCR 영역 밖의 자동 마스크도 함께 정리하며, 사용자 수정 마스크는 유지합니다."
            self.actions["work_clean_text"].setToolTip(self.tr_msg(_text_clean_tip))
            self.actions["work_clean_text"].setStatusTip(self.tr_msg(_text_clean_tip))
            self.actions["work_clean_text"].setWhatsThis(self.tr_msg(_text_clean_tip))
        except Exception:
            pass
        make_action("work_clean_mask", "마스크 정리", self.clean_mask_current)
        try:
            _mask_clean_tip = "현재 페이지에서 활성 OCR 영역 밖의 자동 마스크만 제거합니다. 사용자 수정 마스크는 유지합니다."
            self.actions["work_clean_mask"].setToolTip(self.tr_msg(_mask_clean_tip))
            self.actions["work_clean_mask"].setStatusTip(self.tr_msg(_mask_clean_tip))
            self.actions["work_clean_mask"].setWhatsThis(self.tr_msg(_mask_clean_tip))
        except Exception:
            pass
        make_action("work_reset_text_rects", "현재 텍스트 기준으로 영역 재설정", self.reset_text_rects_current)
        make_action("work_export", "출력", self.export_result)
        make_action("work_output_preview", "출력 미리보기", self.show_output_preview)

        # 자동화 작업
        make_action("auto_text_size_current", "텍스트 자동 조정", self.auto_text_size_current)
        make_action("auto_text_size_batch", "일괄 텍스트 자동 조정", self.auto_text_size_batch)
        make_action("auto_text_adjust_options", "자동 텍스트 조정 옵션", self.open_auto_text_adjust_options_dialog)
        make_action("auto_linebreak_current", "텍스트 자동 조정(줄내림 호환)", self.auto_linebreak_current)
        make_action("auto_linebreak_batch", "일괄 텍스트 자동 조정(줄내림 호환)", self.auto_linebreak_batch)
        try:
            _auto_adjust_tip = "번역문을 OCR 영역 안에 자동 배치하고, 한국어 줄내림과 텍스트 크기를 점수 기반으로 함께 조정합니다."
            _auto_adjust_batch_tip = "선택한 페이지의 번역문을 OCR 영역 안에 자동 배치하고, 한국어 줄내림과 텍스트 크기를 점수 기반으로 함께 조정합니다."
            _auto_adjust_options_tip = "자동 텍스트 조정에서 세로쓰기 자동 적용과 비정상적으로 작은 글자 보정 기준을 조정합니다."
            for _key, _tip in (("auto_text_size_current", _auto_adjust_tip), ("auto_linebreak_current", _auto_adjust_tip), ("auto_text_size_batch", _auto_adjust_batch_tip), ("auto_linebreak_batch", _auto_adjust_batch_tip), ("auto_text_adjust_options", _auto_adjust_options_tip)):
                self.actions[_key].setToolTip(self.tr_msg(_tip))
                self.actions[_key].setStatusTip(self.tr_msg(_tip))
                self.actions[_key].setWhatsThis(self.tr_msg(_tip))
        except Exception:
            pass

        # 일괄 작업
        make_action("batch_analyze", "일괄 분석", lambda: self.run_batch('analyze'))
        make_action("batch_reanalyze", "일괄 재분석", lambda: self.run_batch('reanalyze'))
        try:
            _batch_reanalyze_tip = "선택한 페이지마다 현재 텍스트 마스크를 기준으로 OCR 분석 영역을 다시 만들고, 기존 마스크는 재사용합니다."
            self.actions["batch_reanalyze"].setToolTip(self.tr_msg(_batch_reanalyze_tip))
            self.actions["batch_reanalyze"].setStatusTip(self.tr_msg(_batch_reanalyze_tip))
            self.actions["batch_reanalyze"].setWhatsThis(self.tr_msg(_batch_reanalyze_tip))
        except Exception:
            pass
        make_action("batch_translate", "일괄 번역", lambda: self.run_batch('translate'))
        make_action("batch_inpaint", "일괄 인페인팅", lambda: self.run_batch('inpaint'))
        make_action("batch_extract_text", "일괄 지문 추출", self.extract_text_batch)
        make_action("batch_clear_translation", "일괄 번역문 내용 지우기", self.clear_translation_batch)
        make_action("batch_clean_text", "일괄 텍스트 정리", self.clean_text_batch)
        make_action("batch_clean_mask", "일괄 마스크 정리", self.clean_mask_batch)
        try:
            _batch_mask_clean_tip = "선택한 페이지들에서 활성 OCR 영역 밖의 자동 마스크만 일괄 제거합니다. 사용자 수정 마스크는 유지합니다."
            self.actions["batch_clean_mask"].setToolTip(self.tr_msg(_batch_mask_clean_tip))
            self.actions["batch_clean_mask"].setStatusTip(self.tr_msg(_batch_mask_clean_tip))
            self.actions["batch_clean_mask"].setWhatsThis(self.tr_msg(_batch_mask_clean_tip))
        except Exception:
            pass
        make_action("batch_reset_text_rects", "일괄 현재 텍스트 기준으로 영역 재설정", self.reset_text_rects_batch)
        make_action("batch_export", "일괄 출력", lambda: self.run_batch('export'))

        # 설정 / 옵션
        make_action("option_settings_overview", "설정 / 옵션", self.request_open_settings_overview_dialog)
        # v2.4 QA6: 자동저장 모드는 폐지.
        # 예전 단축키/매크로 캐시가 참조해도 오류가 나지 않도록 비활성 액션만 보존한다.
        self.act_auto_save_mode = make_action("option_auto_save_mode", "자동저장 모드(폐지됨)", self.toggle_auto_save_mode)
        self.act_auto_save_mode.setEnabled(False)
        self.act_auto_save_mode.setVisible(False)
        make_action("option_theme_settings", "테마 설정", self.open_theme_settings_dialog)
        make_action("option_language_settings", "언어 설정", self.open_language_settings_dialog)
        make_action("setting_operation_mode", "조작 방식", self.open_operation_mode_dialog)
        make_action("setting_page_tab_display_name", "페이지 탭 표시명 설정", self.open_page_tab_display_name_dialog)
        make_action("setting_output_display_name", "출력 표시명 설정", self.open_output_display_name_dialog)
        make_action("setting_output_options", "출력 옵션", self.open_output_options_dialog)
        make_action("setting_log_options", "로그 출력 설정", self.open_log_options_dialog)
        try:
            _log_options_tip = "엔진/자동 조정/렌더링 진단 로그 중 어떤 이벤트를 파일에 출력할지 선택합니다. 설정은 별도 캐시 JSON에 저장됩니다."
            self.actions["setting_log_options"].setToolTip(self.tr_msg(_log_options_tip))
            self.actions["setting_log_options"].setStatusTip(self.tr_msg(_log_options_tip))
            self.actions["setting_log_options"].setWhatsThis(self.tr_msg(_log_options_tip))
        except Exception:
            pass
        act_hide_bg = make_action("option_hide_background", "배경 가리기", self.toggle_hide_background_enabled)
        try:
            act_hide_bg.setCheckable(True)
            act_hide_bg.setChecked(self.is_hide_background_enabled())
            _hide_bg_tip = "작업 화면의 이미지 배경을 짙은 회색으로 가리고, 이미지 바깥쪽에 밝은 페이드 테두리를 표시합니다. 텍스트, 박스, 마스크는 보이고 원본 비교창에는 적용되지 않습니다."
            act_hide_bg.setToolTip(self.tr_msg(_hide_bg_tip))
            act_hide_bg.setStatusTip(self.tr_msg(_hide_bg_tip))
            act_hide_bg.setWhatsThis(self.tr_msg(_hide_bg_tip))
            self.sync_hide_background_action_state()
        except Exception:
            pass
        # 텍스트 넘침 검사 토글은 새 자동조정 엔진 본선에서 사용하지 않으므로
        # 옵션 메뉴/단축키 항목으로 만들지 않는다.
        # 관련 getter/setter는 구버전 프로젝트 옵션 호환용으로만 남긴다.
        act_tooltips = make_action("setting_interface_tooltips", "인터페이스 툴팁 표시", self.toggle_interface_tooltips_enabled)
        try:
            act_tooltips.setCheckable(True)
            act_tooltips.setChecked(self.is_interface_tooltips_enabled())
        except Exception:
            pass
        make_action("setting_file_path_visibility", "파일 경로 표시", self.open_file_path_visibility_dialog)
        make_action("option_api_settings", "API 관리", self.open_api_settings_dialog)
        make_action("option_translation_prompt", "번역 프롬프트 입력", self.open_translation_prompt_dialog)
        make_action("option_glossary", "단어장", self.open_glossary_dialog)
        make_action("option_analysis_mask_settings", "분석 마스크 확장 비율", self.open_analysis_mask_settings_dialog)
        make_action("option_mask_color_settings", "마스크 색상 지정", self.open_mask_color_settings_dialog)
        make_action("option_ocr_analysis_regions", "OCR 분석 범위 지정", self.open_ocr_analysis_region_dialog)
        if self._is_local_edition_for_ui():
            make_action("option_cuda_runtime_diagnosis", "로컬 CUDA 진단", self.open_cuda_runtime_diagnosis_dialog)
        make_action("option_cleanup_outputs", "출력물 삭제", self.open_output_cleanup_dialog)
        make_action("option_workspace_location", "작업 폴더 위치 변경", self.change_workspace_location)
        make_action("option_workspace_reset_default", "작업 폴더 위치 기본값으로 변경", self.reset_workspace_location_to_default)
        make_action("option_cleanup_temp_files", "사용자 데이터 및 임시파일 정리", self.cleanup_temp_files_dialog)
        make_action("option_workspace_size_manager", "작업 폴더 용량 관리", self.open_workspace_folder_size_manager_dialog)
        make_action("option_register_ysb", ".ysbt 확장자 연결 등록", self.register_ysb_file_association)
        make_action("option_unregister_ysbt", ".ysbt 확장자 연결 해제", self.unregister_ysbt_file_association)
        make_action("option_shortcut_settings", "단축키 통합 관리", self.open_shortcut_settings_dialog)
        make_action("option_macro_settings", "매크로 관리", self.open_macro_settings_dialog)
        make_action("option_text_preset_settings", "페이지 글꼴 프리셋 관리", self.open_text_preset_dialog)
        make_action("option_item_text_preset_settings", "개별 글꼴 프리셋 관리", self.open_item_text_preset_dialog)

        # 도움말
        make_action("help_program_manual", "프로그램 메뉴얼", self.open_program_manual_url)
        make_action("help_open_website", "YSB Tool 사이트로 가기", self.open_ysb_tool_site_url)
        make_action("help_report_bug", "버그제보 / 문의하기", self.open_bug_report_url)
        make_action("help_about", "프로그램 정보", self.open_about_dialog)

        # 클라우드
        make_action("cloud_register", "클라우드 등록", self.cloud_register)
        make_action("cloud_unregister", "클라우드 등록 해제", self.cloud_unregister)
        make_action("cloud_cache_backup", "클라우드로 캐시 백업", self.cloud_backup_cache)
        make_action("cloud_cache_restore", "클라우드에서 캐시 불러오기", self.cloud_restore_cache)
        make_action("cloud_delete_backups", "클라우드 백업 삭제", self.cloud_delete_cache_backups)

        # 토글/보조 작업
        make_action("paint_undo", "작업 취소", self.handle_global_undo_shortcut)
        make_action("paint_redo", "작업 재실행", self.handle_general_redo)
        make_action("paint_magic_fill", "마스킹 칠하기", self.fill_magic_wand_mask)
        make_action("paint_area_fill", "영역 페인팅", lambda *args: self.set_tool("area_paint"))
        make_action("paint_mask_cut", "마스크 커팅", lambda *args: self.set_tool("mask_cut"))
        make_action("paint_color_outline_mask", "색상/테두리 마스크", lambda *args: self.set_tool("color_outline_mask"))
        make_action("paint_original_restore", "영역 원본 복구", lambda *args: self.set_tool("original_restore"))
        make_action("paint_mask_toggle", "마스크 ON/OFF", self.toggle_mask_toggle)
        make_action("view_text_toggle", "텍스트 표시 ON/OFF", self.toggle_show_final_text)
        make_action("final_paint_color", "최종 페인팅 색상", lambda *args: self.pick_color("final_paint"))
        make_action("final_paint_to_background", "배경을 원본으로 쓰기", self.use_final_background_as_source)
        make_action("final_text_tool", "최종 텍스트 도구", lambda *args: self.set_tool("final_text"))
        make_action("final_style_clone", "스타일 복제", lambda *args: self.set_tool("text_style_clone"))
        make_action("final_paint_above_toggle", "텍스트 위 페인팅 ON/OFF", self.toggle_final_paint_above_text)
        make_action("final_paint_opacity_inc", "브러시 불투명도 증가", lambda *args: self.adjust_final_paint_opacity(+5))
        make_action("final_paint_opacity_dec", "브러시 불투명도 감소", lambda *args: self.adjust_final_paint_opacity(-5))

    def open_cuda_runtime_diagnosis_dialog(self):
        """Open the Local CUDA/runtime diagnosis dialog."""
        if not self._is_local_edition_for_ui():
            try:
                self.log("ℹ️ 로컬 CUDA 진단은 Local판 전용이라 현재 에디션에서는 열지 않습니다.")
            except Exception:
                pass
            return
        try:
            from ysb.ui.cuda_runtime_dialog import CudaRuntimeDiagnosisDialog
            dlg = CudaRuntimeDiagnosisDialog(self)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, self.tr_ui("로컬 CUDA 진단 실패"), str(e))
            try:
                self.log(f"❌ 로컬 CUDA 진단 실패: {e}")
            except Exception:
                pass

    def open_external_url(self, url):
        """도움말 메뉴에서 외부 웹페이지를 기본 브라우저로 연다."""
        try:
            ok = QDesktopServices.openUrl(QUrl(str(url)))
            if not ok:
                raise RuntimeError(self.tr_ui("웹 브라우저로 링크를 열 수 없습니다."))
        except Exception as e:
            try:
                webbrowser.open(str(url))
                return
            except Exception:
                pass
            QMessageBox.warning(self, self.tr_ui("링크 열기 실패"), str(e))

    def open_program_manual_url(self):
        self.open_external_url(YSB_TOOL_MANUAL_URL)

    def open_ysb_tool_site_url(self):
        self.open_external_url(YSB_TOOL_SITE_URL)

    def open_bug_report_url(self):
        # 프로그램에서는 공식 지원 페이지를 경유하고,
        # 사이트 안의 문의/버그제보 버튼이 GitHub Issues 작성 화면으로 이동한다.
        self.open_external_url(YSB_TOOL_SUPPORT_URL)

    def start_auto_version_check(self):
        """Check latest version in the background after startup.

        The app must stay usable without internet, so failures are intentionally
        silent. Only a newer version shows a small dialog.
        """
        try:
            if getattr(self, "_auto_version_check_started", False):
                return
            self._auto_version_check_started = True
            worker = VersionCheckThread(APP_VERSION, timeout=5, parent=self)
            self._auto_version_check_thread = worker
            worker.version_info_ready.connect(self._on_auto_version_info_ready)
            worker.version_check_failed.connect(self._on_auto_version_check_failed)
            worker.finished.connect(worker.deleteLater)
            worker.finished.connect(lambda: setattr(self, "_auto_version_check_thread", None))
            worker.start()
        except Exception:
            pass

    def _on_auto_version_check_failed(self, message):
        # 인터넷이 없거나 사이트가 잠시 안 열려도 프로그램 사용은 막지 않는다.
        try:
            self._auto_version_check_error = str(message)
        except Exception:
            pass

    def _on_auto_version_info_ready(self, info):
        try:
            if getattr(self, "_app_is_closing", False):
                return
            latest_version = str((info or {}).get("latest_version") or "").strip()
            if not latest_version:
                return
            if _ysb_version_tuple(APP_VERSION) >= _ysb_version_tuple(latest_version):
                return

            options = load_app_options()
            ignored = str(options.get(UPDATE_IGNORED_VERSION_KEY, "") or "").strip()
            if ignored == latest_version:
                return

            dialog = UpdateAvailableDialog(self, current_version=APP_VERSION, version_info=info)
            dialog.exec()

            if dialog.ignore_this_version():
                options[UPDATE_IGNORED_VERSION_KEY] = latest_version
                save_app_options(options)
                try:
                    self.app_options = dict(options)
                except Exception:
                    pass

            if getattr(dialog, "open_download_requested", False):
                self.open_external_url(str(info.get("download_page_url") or YSB_TOOL_DOWNLOAD_PAGE_URL))
        except Exception:
            pass

    def apply_shortcuts(self):
        for key, action in self.actions.items():
            # Alt+V 현재 페이지 이름은 keyPress/keyRelease에서 직접 처리한다.
            # QAction 단축키와 동시에 살아 있으면 팝업이 두 번 떠서 깜빡인다.
            if key == "work_page_full_name":
                action.setShortcut(QKeySequence())
                action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
                continue
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
            action.triggered.connect(lambda checked=False, m=dict(macro): None if self._block_global_action_during_inline_text_edit('macro') else self.run_macro(m))
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
            action.triggered.connect(lambda checked=False, n=name: None if self._block_global_action_during_inline_text_edit('item_text_preset') else self.apply_item_text_preset_by_name(n, record_undo=True))
            self.addAction(action)
            self.item_preset_actions.append(action)

        if hasattr(self, "cb_show_final_text"):
            self.configure_ui_tooltips()

        try:
            self.install_final_text_clipboard_canvas_shortcuts()
        except Exception:
            pass

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

        # 브러시/지우개는 마스크 탭 + 최종화면에서 사용.
        for attr in ("act_brush", "act_erase"):
            if hasattr(self, attr):
                getattr(self, attr).setVisible(drawing_tabs)

        # 요술봉은 마스크 탭 + 최종결과 탭에서 사용한다.
        # 랩핑/커팅은 마스크 탭 전용이다.
        if hasattr(self, "act_magic"):
            self.act_magic.setVisible(mask_tabs or final_tab)
        if hasattr(self, "act_mask_wrap"):
            self.act_mask_wrap.setVisible(mask_tabs)
        if hasattr(self, "act_mask_cut"):
            self.act_mask_cut.setVisible(mask_tabs)
        if hasattr(self, "act_color_outline_mask"):
            self.act_color_outline_mask.setVisible(mask_tabs)
        if hasattr(self, "act_original_restore"):
            self.act_original_restore.setVisible(final_tab)
        # 마스크 ON/OFF는 페인팅 마스크 탭 전용.
        if hasattr(self, "act_mask_toggle"):
            self.act_mask_toggle.setVisible(paint_only)
        if hasattr(self, "mask_toggle_wrap") and self.mask_toggle_wrap:
            self.mask_toggle_wrap.setVisible(paint_only)

        # 영역 페인팅 버튼은 마스크 탭에서는 영역 마스킹, 최종결과 탭에서는 영역 칠하기로 쓴다.
        if hasattr(self, "act_final_area_paint"):
            self.act_final_area_paint.setVisible(mask_tabs or final_tab)

        # 나머지 최종화면 전용 도구.
        for attr in ("act_final_paint_color", "act_final_text_tool", "act_text_style_clone", "act_final_paint_to_bg", "act_final_paint_above_text"):
            if hasattr(self, attr):
                getattr(self, attr).setVisible(final_tab)

        # 텍스트 마스크 자동 정리는 옵션 체크박스 기반 자동 처리로 이동했다.
        # 수동 자동 정리 버튼은 더 이상 노출하지 않고, 텍스트 마스크 탭에는 재분석만 표시한다.
        btn_auto_clean = getattr(self, "btn_auto_clean_detection_mask", None)
        if btn_auto_clean is not None:
            btn_auto_clean.setVisible(False)
        btn_reanalyze = getattr(self, "btn_reanalyze", None)
        if btn_reanalyze is not None:
            btn_reanalyze.setVisible(mode == 2)

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
            sub = "#374151" if is_light else "#E7E2E5"
            line = "#D1C9CE" if is_light else "#555056"
        elif is_light and force_white_in_light:
            fg = "#ffffff"
            sub = "#ffffff"
            line = "#ffffff"
        elif is_light:
            fg = "#111827"
            sub = "#374151"
            line = "#D1C9CE"
        else:
            fg = "#ffffff"
            sub = "#E7E2E5"
            line = "#555056"

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
        """Return True for events that belong to this main window/canvas.

        App-level key events for QGraphicsView may arrive with the viewport or
        QGraphicsScene as ``obj`` instead of a QWidget.  The final-text clipboard
        shortcut filter must still treat those as our canvas events; otherwise
        Ctrl+C/Ctrl+V can be accepted or eaten elsewhere without running the YSB
        text-object copy/paste command.
        """
        try:
            if obj is self:
                return True
            view = getattr(self, 'view', None)
            if view is not None:
                try:
                    if obj is view:
                        return True
                except Exception:
                    pass
                try:
                    if obj is view.viewport():
                        return True
                except Exception:
                    pass
                try:
                    scene = view.scene() if callable(getattr(view, 'scene', None)) else getattr(view, 'scene', None)
                    if obj is scene:
                        return True
                except Exception:
                    pass
            if isinstance(obj, QWidget):
                return obj.window() is self
            # Some Qt objects report only a QObject parent chain.  Walk it back
            # toward the owning widget/view so scene-level shortcut events are not
            # rejected just because the first object is not a QWidget.
            p = obj
            for _ in range(12):
                if p is None:
                    break
                if p is self:
                    return True
                if view is not None and p is view:
                    return True
                if isinstance(p, QWidget):
                    return p.window() is self
                try:
                    p = p.parent()
                except Exception:
                    break
            return False
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
                if isinstance(target, (QLineEdit, QAbstractSpinBox, QKeySequenceEdit)):
                    return target
                # QSpinBox/QComboBox 내부 lineEdit이나 popup child에서 올라가기
                p = target
                for _ in range(8):
                    if p is None or not hasattr(p, "parent"):
                        break
                    p = p.parent()
                    if isinstance(p, (QAbstractSpinBox, QKeySequenceEdit)):
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

    def handle_inline_text_editor_local_undo_redo(self, redo=False):
        """인라인 텍스트 편집 중 Ctrl+Z/Y가 전역 Undo로 새지 않게 로컬 Undo/Redo를 우선 처리한다.

        QGraphicsTextItem의 QTextDocument 기본 undo는 자동 alignment/resize 보정과 섞이면
        커서 이동처럼 보일 수 있어, InlineTextEditItem의 스냅샷 undo를 사용한다.
        """
        editor = getattr(self, "inline_text_editor", None)
        if editor is None:
            return False
        try:
            if redo:
                ok = bool(editor.perform_inline_local_redo())
            else:
                ok = bool(editor.perform_inline_local_undo())
            if hasattr(self, 'audit_boundary_event'):
                self.audit_boundary_event(
                    'INLINE_TEXT_EDITOR_GLOBAL_SHORTCUT_ROUTED_LOCAL',
                    page_idx=getattr(self, 'idx', None),
                    redo=bool(redo),
                    ok=ok,
                    throttle_ms=80,
                )
        except Exception:
            pass
        return True

    def handle_global_undo_shortcut(self):
        if self.handle_inline_text_editor_local_undo_redo(redo=False):
            return True
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
        # QComboBox/QFontComboBox는 클릭 자체가 팝업 열기 동작이라 일반 입력 안정화 필터를 붙이지 않는다.
        # 마우스 press/release 경로가 중복으로 지나가면 팝업이 두 번 열리는 것처럼 번쩍일 수 있다.
        if isinstance(widget, (QComboBox, QFontComboBox)):
            return
        try:
            if isinstance(widget, QAbstractSpinBox):
                # 숫자 입력 중 매 키마다 valueChanged가 발생하면 화면/우측 UI가 갱신되며
                # 포커스가 OCR 언어 콤보박스 등으로 튈 수 있다. 입력 확정 시점에만 반영한다.
                widget.setKeyboardTracking(False)
        except Exception:
            pass
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

    def configure_stable_numeric_inputs(self):
        """메인 UI의 숫자 입력칸은 입력 중 포커스를 잃지 않도록 안정화한다."""
        try:
            widgets = list(self.findChildren(QAbstractSpinBox))
        except Exception:
            widgets = []
        for spin in widgets:
            try:
                spin.setKeyboardTracking(False)
            except Exception:
                pass
            try:
                self.install_enter_escape_for_input(spin)
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
            getattr(self, "final_item_size", None),
            getattr(self, "final_item_stroke", None),
            getattr(self, "sb_text_opacity", None),
            getattr(self, "sb_trans_chunk", None),
            getattr(self, "sb_final_paint_opacity", None),
            getattr(self, "sb_magic_tolerance", None),
            getattr(self, "sb_magic_expand", None),
            getattr(self, "sb_mask_cut_px", None),
        ):
            self.install_enter_escape_for_input(widget)
        try:
            self.configure_stable_numeric_inputs()
        except Exception:
            pass

    def is_hide_background_enabled(self):
        return bool(getattr(self, "hide_background_enabled", False))

    def sync_hide_background_action_state(self):
        try:
            action = getattr(self, "actions", {}).get("option_hide_background")
            if action is None:
                return
            enabled = self.is_hide_background_enabled()
            action.setCheckable(True)
            action.setChecked(enabled)
            base_text = self.tr_ui("배경 가리기") if hasattr(self, "tr_ui") else "배경 가리기"
            action.setText(f"{base_text} ✓" if enabled else base_text)
            action.setStatusTip("ON" if enabled else "OFF")
        except Exception:
            pass

    def apply_hide_background_to_work_view(self):
        try:
            view = getattr(self, "view", None)
            if view is not None and hasattr(view, "apply_background_visibility"):
                view.apply_background_visibility()
        except Exception:
            pass
        try:
            # 원본 비교/클론창은 예외다. 여기서는 갱신하지 않는다.
            if hasattr(self, "audit_boundary_event"):
                self.audit_boundary_event("HIDE_BACKGROUND_APPLIED", enabled=self.is_hide_background_enabled())
        except Exception:
            pass

    def set_hide_background_enabled(self, enabled, *, persist=True, announce=True):
        enabled = bool(enabled)
        self.hide_background_enabled = enabled
        try:
            self.app_options["hide_background_enabled"] = enabled
        except Exception:
            pass
        try:
            self.sync_hide_background_action_state()
        except Exception:
            pass
        try:
            self.apply_hide_background_to_work_view()
        except Exception:
            pass
        if persist:
            try:
                self.save_app_options_cache()
            except Exception:
                try:
                    from ysb.core.cache_utils import save_app_options
                    save_app_options(self.app_options)
                except Exception:
                    pass
        if announce:
            try:
                self.log("🕶️ 배경 가리기: ON" if enabled else "🕶️ 배경 가리기: OFF")
            except Exception:
                pass
        return enabled

    def toggle_hide_background_enabled(self):
        return self.set_hide_background_enabled(not self.is_hide_background_enabled(), persist=True, announce=True)

    def is_text_image_overflow_check_enabled(self):
        return bool(getattr(self, "text_image_overflow_check_enabled", True))

    def sync_text_image_overflow_check_action_state(self):
        try:
            action = getattr(self, "actions", {}).get("option_text_image_overflow_check")
            if action is None:
                return
            enabled = self.is_text_image_overflow_check_enabled()
            action.setCheckable(True)
            action.setChecked(enabled)
            base_text = self.tr_ui("텍스트 넘침 검사") if hasattr(self, "tr_ui") else "텍스트 넘침 검사"
            action.setText(f"{base_text} ✓" if enabled else base_text)
            action.setStatusTip("ON" if enabled else "OFF")
        except Exception:
            pass

    def set_text_image_overflow_check_enabled(self, enabled, *, persist=True, announce=True):
        enabled = bool(enabled)
        self.text_image_overflow_check_enabled = enabled
        try:
            self.app_options["text_image_overflow_check_enabled"] = enabled
        except Exception:
            pass
        try:
            self.sync_text_image_overflow_check_action_state()
        except Exception:
            pass
        if persist:
            try:
                self.save_app_options_cache()
            except Exception:
                try:
                    from ysb.core.cache_utils import save_app_options
                    save_app_options(self.app_options)
                except Exception:
                    pass
        try:
            if hasattr(self, 'audit_boundary_event'):
                self.audit_boundary_event(
                    'TEXT_AUTO_ADJUST_IMAGE_OVERFLOW_CHECK_TOGGLE',
                    enabled=bool(enabled),
                    policy='text_image_overflow_check_blocks_growth_and_final_boundary_when_enabled',
                )
        except Exception:
            pass
        if announce:
            try:
                self.log(self.tr_msg("📐 텍스트 넘침 검사: ON") if enabled else self.tr_msg("📐 텍스트 넘침 검사: OFF"))
            except Exception:
                pass
        return enabled

    def toggle_text_image_overflow_check_enabled(self):
        return self.set_text_image_overflow_check_enabled(not self.is_text_image_overflow_check_enabled(), persist=True, announce=True)

    def is_interface_tooltips_enabled(self):
        return bool(getattr(self, "interface_tooltips_enabled", True))

    def sync_interface_tooltips_action_state(self):
        try:
            action = getattr(self, "actions", {}).get("setting_interface_tooltips")
            if action is None:
                return
            enabled = self.is_interface_tooltips_enabled()
            action.setCheckable(True)
            action.setChecked(enabled)
            base_text = self.tr_ui("인터페이스 툴팁 표시") if hasattr(self, "tr_ui") else "인터페이스 툴팁 표시"
            # 메뉴에서 현재 상태를 바로 볼 수 있게 켜져 있을 때만 체크 표시를 텍스트 뒤에 붙인다.
            action.setText(f"{base_text} ✓" if enabled else base_text)
            action.setStatusTip("ON" if enabled else "OFF")
        except Exception:
            pass

    def set_interface_tooltips_enabled(self, enabled, *, persist=True, announce=True):
        enabled = bool(enabled)
        self.interface_tooltips_enabled = enabled
        try:
            self.app_options["interface_tooltips_enabled"] = enabled
        except Exception:
            pass
        if not enabled:
            try:
                self._tooltip_target = None
                self._tooltip_html = ""
                timer = getattr(self, "_tooltip_timer", None)
                if timer is not None:
                    timer.stop()
            except Exception:
                pass
            try:
                self._hide_delayed_tooltip_popup()
            except Exception:
                pass
        try:
            self.sync_interface_tooltips_action_state()
        except Exception:
            pass
        if persist:
            try:
                self.save_app_options_cache()
            except Exception:
                try:
                    from ysb.core.cache_utils import save_app_options
                    save_app_options(self.app_options)
                except Exception:
                    pass
        if announce:
            try:
                self.log("💬 인터페이스 툴팁: ON" if enabled else "💬 인터페이스 툴팁: OFF")
            except Exception:
                pass
        return enabled

    def toggle_interface_tooltips_enabled(self):
        return self.set_interface_tooltips_enabled(not self.is_interface_tooltips_enabled(), persist=True, announce=True)

    def register_delayed_tooltip(self, widget, title, shortcut_text="", description=""):
        if widget is None:
            return

        # 메인 윈도우 전체에 지연 툴팁이 붙으면 창 전체가 하나의 툴팁 영역처럼 동작한다.
        # 빠른 OCR 설정 툴팁이 바탕 어디서나 뜨던 원인이 이 케이스였으므로 방어한다.
        if widget is self:
            try:
                for prop in (
                    "delayed_tooltip_title",
                    "delayed_tooltip_shortcut",
                    "delayed_tooltip_description",
                    "delayed_tooltip_force_white_in_light",
                    "delayed_tooltip_force_outline",
                    "delayed_tooltip_html",
                ):
                    self.setProperty(prop, None)
            except Exception:
                pass
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

        # QComboBox 계열은 팝업 클릭 경로가 예민하므로 기본적으로 지연 툴팁용 eventFilter를 붙이지 않는다.
        # 단, 글꼴 선택 콤보처럼 "처음 쓰는 사람이 반드시 봐야 하는" 핵심 컨트롤은
        # allow_delayed_tooltip_on_combo 속성을 켜서 내부 overlay 툴팁을 허용한다.
        allow_combo_delayed = False
        try:
            allow_combo_delayed = bool(widget.property("allow_delayed_tooltip_on_combo"))
        except Exception:
            allow_combo_delayed = False
        if isinstance(widget, (QComboBox, QFontComboBox)) and not allow_combo_delayed:
            try:
                widget.setToolTip(self.tr_msg(title))
            except Exception:
                pass
            return

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
        # QFontComboBox 같은 복합 위젯은 실제 hover가 내부 child로 들어갈 수 있다.
        # 허용된 combo에 한해서 child에도 같은 tooltip property/filter를 복사한다.
        try:
            if allow_combo_delayed and isinstance(widget, (QComboBox, QFontComboBox)):
                for child in widget.findChildren(QWidget):
                    try:
                        child.setToolTip("")
                        child.setProperty("delayed_tooltip_title", title)
                        child.setProperty("delayed_tooltip_shortcut", shortcut_text)
                        child.setProperty("delayed_tooltip_description", description)
                        child.setProperty("delayed_tooltip_force_white_in_light", force_white_in_light)
                        child.setProperty("delayed_tooltip_force_outline", force_outline)
                        child.setProperty("delayed_tooltip_html", self._tooltip_rich_text(title, shortcut_text, description, force_white_in_light=force_white_in_light, force_outline=force_outline))
                        child.installEventFilter(self)
                    except Exception:
                        pass
        except Exception:
            pass

    def _hide_delayed_tooltip_popup(self):
        try:
            QToolTip.hideText()
        except Exception:
            pass
        try:
            popup = getattr(self, "_tooltip_popup", None)
            if popup is not None:
                popup.hide()
        except Exception:
            pass
        try:
            self._tooltip_visible_target = None
        except Exception:
            pass

    def _cursor_inside_tooltip_target(self, widget, margin=3):
        try:
            if widget is None or not widget.isVisible():
                return False
            pos = QCursor.pos()
            top_left = widget.mapToGlobal(QPoint(0, 0))
            rect = QRect(top_left, widget.size()).adjusted(-margin, -margin, margin, margin)
            return rect.contains(pos)
        except Exception:
            return False

    def _validate_delayed_tooltip_hover(self):
        widget = getattr(self, "_tooltip_visible_target", None) or getattr(self, "_tooltip_target", None)
        popup = getattr(self, "_tooltip_popup", None)
        try:
            has_native = bool(QToolTip.isVisible())
        except Exception:
            has_native = False
        visible = bool((popup is not None and popup.isVisible()) or has_native)
        if not visible:
            return
        if not self._cursor_inside_tooltip_target(widget, margin=6):
            try:
                self._tooltip_timer.stop()
            except Exception:
                pass
            self._tooltip_target = None
            self._tooltip_html = ""
            self._hide_delayed_tooltip_popup()
            return
        try:
            QTimer.singleShot(250, self._validate_delayed_tooltip_hover)
        except Exception:
            pass

    def _tooltip_popup_position(self, widget, popup):
        """위젯 위치에 맞춰 툴팁을 버튼과 겹치지 않게 배치한다."""
        gap = 10
        try:
            top_left = widget.mapToGlobal(QPoint(0, 0))
            rect = QRect(top_left, widget.size())
        except Exception:
            return QCursor.pos() + QPoint(12, 12)

        try:
            main_tl = self.mapToGlobal(QPoint(0, 0))
            main_rect = QRect(main_tl, self.size())
        except Exception:
            main_rect = QRect()

        try:
            hint = str(widget.property("delayed_tooltip_position") or "")
        except Exception:
            hint = ""

        try:
            ox = int(widget.property("delayed_tooltip_offset_x") or 0)
            oy = int(widget.property("delayed_tooltip_offset_y") or 0)
        except Exception:
            ox, oy = 0, 0

        pw = max(1, popup.width())
        ph = max(1, popup.height())

        def pos_above():
            return QPoint(rect.center().x() - pw // 2, rect.top() - ph - gap)

        def pos_below(extra_y=0):
            return QPoint(rect.center().x() - pw // 2, rect.bottom() + gap + extra_y)

        def pos_right():
            return QPoint(rect.right() + gap, rect.center().y() - ph // 2)

        def pos_left():
            return QPoint(rect.left() - pw - gap, rect.center().y() - ph // 2)

        if hint == "right":
            pos = pos_right()
        elif hint == "left":
            pos = pos_left()
        elif hint == "above":
            pos = pos_above()
        elif hint == "below":
            pos = pos_below()
        elif hint == "below_low":
            pos = pos_below(34)
        else:
            # 기본 자동 배치:
            # - 왼쪽 도구바 버튼은 오른쪽
            # - 하단 버튼은 위
            # - 오른쪽 인터페이스 버튼은 조금 아래
            # - 나머지는 아래
            try:
                if main_rect.isValid():
                    if rect.center().x() <= main_rect.left() + 90:
                        pos = pos_right()
                    elif rect.center().y() >= main_rect.bottom() - 130:
                        pos = pos_above()
                    elif rect.center().x() >= main_rect.right() - 210:
                        pos = pos_below(12)
                    else:
                        pos = pos_below()
                else:
                    pos = pos_below()
            except Exception:
                pos = pos_below()

        pos += QPoint(ox, oy)

        # 화면 밖으로 너무 튀어나가지 않게 최소 보정한다.
        try:
            screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
            if screen is not None:
                avail = screen.availableGeometry()
                x = max(avail.left() + 4, min(pos.x(), avail.right() - pw - 4))
                y = max(avail.top() + 4, min(pos.y(), avail.bottom() - ph - 4))
                pos = QPoint(x, y)
        except Exception:
            pass
        return pos

    def _show_delayed_tooltip(self):
        if not self.is_interface_tooltips_enabled():
            try:
                self._hide_delayed_tooltip_popup()
            except Exception:
                pass
            return
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
            self._tooltip_visible_target = widget
        except Exception:
            pass

        # v2.3.1 tooltip isolation:
        # 기본 QToolTip은 버튼을 가리고, parent 없는 ToolTip 창은 작업표시줄에 python 창으로 잡힐 수 있다.
        # 그래서 메인윈도우 내부 QLabel overlay만 사용한다.
        try:
            QToolTip.hideText()
        except Exception:
            pass
        try:
            popup = getattr(self, "_tooltip_popup", None)
            if popup is None:
                popup = QLabel(self)
                popup.setObjectName("ysbDelayedTooltipOverlay")
                popup.setTextFormat(Qt.TextFormat.RichText)
                popup.setWordWrap(True)
                popup.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                popup.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
                popup.hide()
                self._tooltip_popup = popup
            popup.setText(html)
            if self.is_light_theme():
                popup.setStyleSheet("QLabel#ysbDelayedTooltipOverlay { background:#ffffff; color:#111827; border:1px solid #D1C9CE; border-radius:0px; padding:7px 9px; }")
            else:
                popup.setStyleSheet("QLabel#ysbDelayedTooltipOverlay { background:#242329; color:#ffffff; border:1px solid #555056; border-radius:0px; padding:7px 9px; }")
            popup.setMaximumWidth(420)
            popup.adjustSize()
            global_pos = self._tooltip_popup_position(widget, popup)
            local_pos = self.mapFromGlobal(global_pos)
            x = max(4, min(local_pos.x(), max(4, self.width() - popup.width() - 4)))
            y = max(4, min(local_pos.y(), max(4, self.height() - popup.height() - 4)))
            popup.move(x, y)
            popup.show()
            popup.raise_()
            try:
                self.audit_top_level_widgets("delayed_tooltip_overlay", throttle_ms=1000)
            except Exception:
                pass
            self._tooltip_visible_target = widget
            QTimer.singleShot(250, self._validate_delayed_tooltip_hover)
        except Exception:
            pass


    def _inline_text_editor_is_active(self):
        try:
            editor = getattr(self, "inline_text_editor", None)
            return editor is not None and not bool(getattr(editor, "_closing", False))
        except Exception:
            return False

    def _block_global_action_during_inline_text_edit(self, key=None):
        """Block application/toolbox shortcuts while the inline text editor is active.

        The inline editor owns text-input shortcuts (symbols, copy/paste, undo/redo,
        Ctrl+Enter, Esc, IME, etc.).  QAction shortcuts such as tools, style changes,
        page movement, macro actions, and item presets must not fire while the user is
        typing inside a text object.
        """
        if not self._inline_text_editor_is_active():
            return False
        try:
            self.audit_boundary_event(
                "INLINE_EDITOR_GLOBAL_ACTION_BLOCKED",
                action_key=str(key or ""),
                throttle_ms=80,
            )
        except Exception:
            pass
        return True

    def _inline_text_edit_event_filter(self, obj, event):
        if not self._inline_text_editor_is_active():
            return False
        et = event.type()
        if et not in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress):
            return False
        editor = getattr(self, "inline_text_editor", None)
        if editor is None:
            return False

        # Consume ShortcutOverride so WindowShortcut QAction/global tool shortcuts do
        # not activate.  Return False for widget-based fallback editors so their own
        # normal key handling still receives the subsequent KeyPress.
        if et == QEvent.Type.ShortcutOverride:
            try:
                event.accept()
            except Exception:
                pass
            try:
                self.audit_boundary_event("INLINE_EDITOR_SHORTCUT_OVERRIDE_BLOCKED", key=int(event.key()), mods=int(event.modifiers().value), throttle_ms=80)
            except Exception:
                pass
            return False

        # If the legacy QWidget fallback editor is active, let that QTextEdit handle
        # actual KeyPress events.  The ShortcutOverride above already blocked global
        # actions.
        try:
            edit_widget = getattr(editor, "_edit", None)
            if edit_widget is not None:
                w = obj
                while w is not None:
                    if w is edit_widget:
                        return False
                    try:
                        w = w.parent()
                    except Exception:
                        break
        except Exception:
            pass

        # Direct YSB editor lives as a QGraphicsObject, so key events can reach the
        # QGraphicsView/viewport instead of the item.  Forward the KeyPress to the
        # editor and stop the event here so no toolbox shortcut or view key handler
        # can also run.
        try:
            editor.keyPressEvent(event)
        except Exception:
            pass
        try:
            event.accept()
        except Exception:
            pass
        return True

    def _is_focus_text_input_for_plain_editing(self, obj=None):
        """Do not steal Ctrl+C/V from real text inputs, spinboxes, or shortcut editors."""
        try:
            target = self.current_single_line_input_widget(obj)
            if target is not None:
                return True
        except Exception:
            pass
        try:
            fw = QApplication.focusWidget()
        except Exception:
            fw = None
        for target in (obj, fw):
            try:
                if target is not None and self.is_text_input_widget(target):
                    return True
            except Exception:
                pass
        return False

    def _focused_plain_input_has_user_selection(self, obj=None):
        """Return True only when a focused text-like editor is actively selecting text.

        A stale focus on a spinbox/line-edit can remain after the user clicks a
        final text object.  In that stale-focus case Ctrl+C/V must belong to the
        selected YSB text object, not to the abandoned editor.  We preserve the
        editor only when it has an actual text selection, which is the clearest
        signal that the user is editing/copying that field right now.
        """
        try:
            if self._inline_text_editor_is_active():
                return True
        except Exception:
            pass
        candidates = []
        try:
            fw = QApplication.focusWidget()
        except Exception:
            fw = None
        for target in (obj, fw):
            if target is None:
                continue
            try:
                line = self.current_single_line_input_widget(target)
                if line is not None:
                    candidates.append(line)
            except Exception:
                pass
            candidates.append(target)
        seen = set()
        for target in candidates:
            try:
                ident = id(target)
                if ident in seen:
                    continue
                seen.add(ident)
            except Exception:
                pass
            try:
                if isinstance(target, QLineEdit):
                    if target.hasSelectedText():
                        return True
                    continue
            except Exception:
                pass
            try:
                if isinstance(target, (QTextEdit, QPlainTextEdit)):
                    cur = target.textCursor()
                    if cur is not None and cur.hasSelection():
                        return True
                    continue
            except Exception:
                pass
            try:
                if isinstance(target, QAbstractSpinBox):
                    line = target.lineEdit()
                    if line is not None and line.hasSelectedText():
                        return True
                    continue
            except Exception:
                pass
            try:
                if isinstance(target, QComboBox):
                    line = target.lineEdit()
                    if line is not None and line.hasSelectedText():
                        return True
                    continue
            except Exception:
                pass
            try:
                if isinstance(target, QKeySequenceEdit):
                    return True
            except Exception:
                pass
        return False

    def _final_text_clipboard_should_ignore_stale_input_focus(self, action, obj=None):
        """Decide whether final-text Ctrl+C/V should override stale widget focus."""
        try:
            if self._inline_text_editor_is_active():
                return False
        except Exception:
            pass
        try:
            selected_count = len(self.selected_text_data_items())
        except Exception:
            selected_count = 0
        try:
            paste_source = bool(self.has_available_text_paste_source()) if hasattr(self, 'has_available_text_paste_source') else bool(getattr(self, 'text_clipboard', None))
        except Exception:
            paste_source = False
        if action == 'copy':
            return selected_count > 0
        if action in ('paste_mode', 'paste_same_position'):
            # If a text object is selected, the user's visible context is the final canvas.
            # If nothing is selected, only override when the focus does not have an
            # explicit user text selection; this lets normal line-edit paste keep working.
            return paste_source and (selected_count > 0 or not self._focused_plain_input_has_user_selection(obj))
        return False

    def focus_final_text_canvas_for_shortcut(self, reason=''):
        """Return keyboard ownership to the final canvas after object selection.

        Selecting a QGraphicsItem does not always move QWidget focus away from the
        last option editor/spinbox.  Then Ctrl+C/V is handled as normal widget
        copy/paste and never reaches the YSB text-object clipboard route.
        """
        try:
            if getattr(self, 'cb_mode', None) is None or self.cb_mode.currentIndex() != 4:
                return False
            view = getattr(self, 'view', None)
            if view is None:
                return False
            try:
                view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            except Exception:
                pass
            try:
                vp = view.viewport()
                if vp is not None:
                    vp.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            except Exception:
                vp = None
            try:
                view.setFocus(Qt.FocusReason.MouseFocusReason)
            except Exception:
                try:
                    view.setFocus()
                except Exception:
                    pass
            try:
                if vp is not None:
                    vp.setFocus(Qt.FocusReason.MouseFocusReason)
            except Exception:
                pass
            try:
                self._final_text_canvas_focus_token = time.time()
            except Exception:
                pass
            try:
                if not getattr(self, '_final_text_clipboard_canvas_shortcuts', None):
                    self.install_final_text_clipboard_canvas_shortcuts()
            except Exception:
                pass
            try:
                self.audit_boundary_event('FINAL_TEXT_CANVAS_FOCUS_RESTORED', reason=str(reason or ''), throttle_ms=100)
            except Exception:
                pass
            return True
        except Exception:
            return False

    def _final_text_clipboard_shortcut_guard_active(self, action, window_ms=220):
        try:
            guard = getattr(self, '_final_text_clipboard_shortcut_guard', {}) or {}
            last = float(guard.get(str(action), 0.0) or 0.0)
            return (time.time() - last) * 1000.0 <= float(window_ms)
        except Exception:
            return False

    def _mark_final_text_clipboard_shortcut_guard(self, action):
        try:
            guard = getattr(self, '_final_text_clipboard_shortcut_guard', None)
            if not isinstance(guard, dict):
                guard = {}
                self._final_text_clipboard_shortcut_guard = guard
            guard[str(action)] = time.time()
        except Exception:
            pass

    def _handle_final_text_clipboard_shortcut_event(self, obj, event):
        """Route final-text copy/paste shortcuts before QGraphicsView eats them.

        Qt first emits ShortcutOverride and then may deliver KeyPress to the canvas
        view/scene/item.  The previous guard accepted ShortcutOverride but executed
        the command only on KeyPress, so the command was lost when QGraphicsView ate
        that KeyPress.  Execute the text-object clipboard command on whichever event
        reaches this filter first, then suppress the immediately following duplicate.
        """
        try:
            et = event.type()
            if et not in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress):
                return False
            if not self._is_own_window_object(obj):
                return False
            if getattr(self, 'cb_mode', None) is None or self.cb_mode.currentIndex() != 4:
                return False
        except Exception:
            return False

        def _accept_only():
            try:
                event.accept()
            except Exception:
                pass
            return True

        def _event_phase():
            try:
                return 'ShortcutOverride' if et == QEvent.Type.ShortcutOverride else 'KeyPress'
            except Exception:
                return str(et)

        def _matched_action():
            try:
                # More specific shortcut first: Ctrl+Shift+V must not be consumed
                # by the plain Ctrl+V paste mode check.
                if self._event_matches_final_text_clipboard_action(event, "paste_same_position"):
                    return 'paste_same_position'
            except Exception:
                pass
            try:
                if self._event_matches_final_text_clipboard_action(event, "copy"):
                    return 'copy'
            except Exception:
                pass
            try:
                if self._event_matches_final_text_clipboard_action(event, "paste_mode"):
                    return 'paste_mode'
            except Exception:
                pass
            return None

        action = _matched_action()
        if not action:
            return False

        try:
            if self._is_focus_text_input_for_plain_editing(obj):
                if not self._final_text_clipboard_should_ignore_stale_input_focus(action, obj):
                    try:
                        self.audit_boundary_event(
                            'TEXT_CLIPBOARD_SHORTCUT_REJECTED',
                            action=action,
                            reason='active_plain_input_focus',
                            phase=_event_phase(),
                            focus_widget=type(QApplication.focusWidget()).__name__ if QApplication.focusWidget() is not None else '',
                            obj_type=type(obj).__name__ if obj is not None else '',
                            throttle_ms=80,
                        )
                    except Exception:
                        pass
                    return False
                try:
                    self.audit_boundary_event(
                        'TEXT_CLIPBOARD_SHORTCUT_STALE_INPUT_FOCUS_OVERRIDDEN',
                        action=action,
                        phase=_event_phase(),
                        focus_widget=type(QApplication.focusWidget()).__name__ if QApplication.focusWidget() is not None else '',
                        obj_type=type(obj).__name__ if obj is not None else '',
                        throttle_ms=80,
                    )
                except Exception:
                    pass
                try:
                    self.focus_final_text_canvas_for_shortcut(reason='clipboard_shortcut_override_stale_focus')
                except Exception:
                    pass
        except Exception:
            pass

        if et == QEvent.Type.KeyPress and self._final_text_clipboard_shortcut_guard_active(action):
            try:
                self.audit_boundary_event('TEXT_CLIPBOARD_SHORTCUT_DUPLICATE_SUPPRESSED', action=action, phase=_event_phase(), throttle_ms=80)
            except Exception:
                pass
            return _accept_only()

        try:
            ok = bool(self.handle_final_text_clipboard_shortcut_command(action, phase=_event_phase()))
        except Exception as e:
            try:
                self.audit_boundary_event('TEXT_CLIPBOARD_SHORTCUT_ERROR', action=str(action), phase=_event_phase(), error=repr(e), throttle_ms=80)
            except Exception:
                pass
            return False

        if ok:
            if et == QEvent.Type.ShortcutOverride:
                self._mark_final_text_clipboard_shortcut_guard(action)
            try:
                self.audit_boundary_event('TEXT_CLIPBOARD_SHORTCUT_HANDLED', action=action, phase=_event_phase(), throttle_ms=80)
            except Exception:
                pass
            return _accept_only()

        try:
            self.audit_boundary_event('TEXT_CLIPBOARD_SHORTCUT_REJECTED', action=action, reason='command_returned_false', phase=_event_phase(), throttle_ms=80)
        except Exception:
            pass
        return False

    def eventFilter(self, obj, event):
        """Delayed tooltip + source compare sync event filter."""
        et = event.type()

        try:
            if self._inline_text_edit_event_filter(obj, event):
                return True
        except Exception:
            pass

        try:
            if self._handle_final_text_clipboard_shortcut_event(obj, event):
                return True
        except Exception:
            pass

        try:
            if et in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress) and self._event_matches_text_delete_shortcut(event):
                # ShortcutOverride와 KeyPress가 연달아 들어오는데 ShortcutOverride에서
                # 삭제 확인창을 띄우면 모달 종료 뒤 KeyPress가 다시 처리되어 확인창이 두 번 뜬다.
                # ShortcutOverride는 "이 키는 우리가 쓴다"는 표시만 하고, 실제 삭제는 KeyPress/QShortcut에서 한 번만 실행한다.
                if et == QEvent.Type.ShortcutOverride:
                    event.accept()
                    return True
                if self.handle_final_text_delete_shortcut_command(phase='EventFilter'):
                    event.accept()
                    return True
        except Exception:
            pass

        try:
            if et == QEvent.Type.Wheel and hasattr(self, "handle_text_font_size_wheel_event"):
                if self.handle_text_font_size_wheel_event(obj, event):
                    return True
        except Exception:
            pass

        # 설정/프리셋 다이얼로그 흰색 깜빡임 분석용 로그.
        try:
            if isinstance(obj, QDialog):
                dialog_key = ""
                try:
                    dialog_key = str(obj.property("dialog_timing_log_key") or "")
                except Exception:
                    dialog_key = ""
                if dialog_key:
                    now = time.time()
                    try:
                        created_at = float(obj.property("dialog_timing_created_at") or 0.0)
                    except Exception:
                        created_at = 0.0
                    try:
                        exec_at = float(obj.property("dialog_timing_exec_enter_at") or 0.0)
                    except Exception:
                        exec_at = 0.0
                    if et == QEvent.Type.Show:
                        self.audit_boundary_event(
                            "DIALOG_SHOW_EVENT",
                            dialog_key=dialog_key,
                            title=obj.windowTitle(),
                            since_create_ms=int((now - created_at) * 1000) if created_at else None,
                            since_exec_enter_ms=int((now - exec_at) * 1000) if exec_at else None,
                            size=f"{obj.width()}x{obj.height()}",
                            memory=memory_text(),
                            throttle_ms=20,
                        )
                    elif et == QEvent.Type.Paint:
                        if not bool(obj.property("dialog_first_paint_logged")):
                            obj.setProperty("dialog_first_paint_logged", True)
                            self.audit_boundary_event(
                                "DIALOG_FIRST_PAINT",
                                dialog_key=dialog_key,
                                title=obj.windowTitle(),
                                since_create_ms=int((now - created_at) * 1000) if created_at else None,
                                since_exec_enter_ms=int((now - exec_at) * 1000) if exec_at else None,
                                size=f"{obj.width()}x{obj.height()}",
                                memory=memory_text(),
                                throttle_ms=20,
                            )
                    elif et == QEvent.Type.Hide:
                        self.audit_boundary_event(
                            "DIALOG_HIDE_EVENT",
                            dialog_key=dialog_key,
                            title=obj.windowTitle(),
                            since_create_ms=int((now - created_at) * 1000) if created_at else None,
                            memory=memory_text(),
                            throttle_ms=20,
                        )
        except Exception:
            pass

        # 상단 메뉴바 반응 지연 분석용 로그.
        # 클릭 이벤트가 들어온 시점, aboutToShow 시점, QMenu Show 시점을 분리해서 본다.
        try:
            if isinstance(obj, QMenuBar):
                if et in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
                    try:
                        pos = event.position().toPoint()
                    except Exception:
                        try:
                            pos = event.pos()
                        except Exception:
                            pos = QPoint()
                    action_title = ""
                    action_text = ""
                    try:
                        act = obj.actionAt(pos)
                        if act is not None:
                            action_text = act.text()
                            action_title = action_text.replace("&", "")
                    except Exception:
                        pass
                    now = time.time()
                    if et == QEvent.Type.MouseButtonPress:
                        self._last_menu_bar_press_time = now
                        self._last_menu_bar_press_title = action_title
                        self.audit_boundary_event(
                            "MENU_BAR_MOUSE_PRESS",
                            action_title=action_title,
                            raw_text=action_text,
                            x=int(pos.x()),
                            y=int(pos.y()),
                            button=int(event.button().value) if hasattr(event.button(), "value") else str(event.button()),
                            memory=memory_text(),
                            throttle_ms=50,
                        )
                    else:
                        press_t = float(getattr(self, "_last_menu_bar_press_time", 0.0) or 0.0)
                        self.audit_boundary_event(
                            "MENU_BAR_MOUSE_RELEASE",
                            action_title=action_title,
                            raw_text=action_text,
                            elapsed_since_press_ms=int((now - press_t) * 1000) if press_t else None,
                            x=int(pos.x()),
                            y=int(pos.y()),
                            button=int(event.button().value) if hasattr(event.button(), "value") else str(event.button()),
                            memory=memory_text(),
                            throttle_ms=50,
                        )
                elif et == QEvent.Type.MouseMove:
                    # Hover 로그는 체감 조작감을 둔탁하게 만들 수 있어 기본적으로 끈다.
                    # 필요할 때만 self.menu_timing_verbose = True로 켠다.
                    if bool(getattr(self, "menu_timing_verbose", False)):
                        try:
                            pos = event.position().toPoint()
                        except Exception:
                            try:
                                pos = event.pos()
                            except Exception:
                                pos = QPoint()
                        try:
                            act = obj.actionAt(pos)
                            title = act.text().replace("&", "") if act is not None else ""
                        except Exception:
                            title = ""
                        self.audit_boundary_event("MENU_BAR_MOUSE_MOVE", action_title=title, x=int(pos.x()), y=int(pos.y()), throttle_ms=1500)
            elif isinstance(obj, QMenu):
                if et == QEvent.Type.Show:
                    try:
                        press_t = float(getattr(self, "_last_menu_bar_press_time", 0.0) or 0.0)
                    except Exception:
                        press_t = 0.0
                    self.audit_boundary_event(
                        "MENU_SHOW_EVENT",
                        menu_title=obj.title(),
                        obj_name=obj.objectName(),
                        action_count=len(obj.actions()),
                        since_press_ms=int((time.time() - press_t) * 1000) if press_t else None,
                        memory=memory_text(),
                        throttle_ms=50,
                    )
                elif et == QEvent.Type.Hide:
                    self.audit_boundary_event(
                        "MENU_HIDE_EVENT",
                        menu_title=obj.title(),
                        obj_name=obj.objectName(),
                        memory=memory_text(),
                        throttle_ms=50,
                    )
        except Exception:
            pass

        # registered delayed-tooltip widgets use our internal overlay only.
        # Block Qt native tooltips so they do not cover buttons or create odd colored popups.
        if et == QEvent.Type.ToolTip:
            # QMenu/QMenuBar native tooltip events are fragile on Windows when the
            # menu is being closed and a modal dialog is opened immediately after
            # an action click.  Do not call QToolTip.hideText() for menus; simply
            # consume the tooltip event.  This prevents access-violation crashes
            # observed when opening the Quick OCR settings from the Work menu.
            try:
                if isinstance(obj, (QMenu, QMenuBar)):
                    try:
                        if hasattr(event, "accept"):
                            event.accept()
                    except Exception:
                        pass
                    return True
            except Exception:
                pass
            try:
                if bool(obj.property("allow_native_tooltip")):
                    if self.is_interface_tooltips_enabled():
                        return False
                    try:
                        self.audit_boundary_event("NATIVE_TOOLTIP_BLOCKED_BY_SETTING", obj_type=type(obj).__name__, obj_name=getattr(obj, "objectName", lambda: "")(), throttle_ms=1000)
                    except Exception:
                        pass
                    try:
                        QToolTip.hideText()
                    except Exception:
                        pass
                    return True
            except Exception:
                pass
            try:
                self.audit_boundary_event("NATIVE_TOOLTIP_BLOCKED", obj_type=type(obj).__name__, obj_name=getattr(obj, "objectName", lambda: "")(), throttle_ms=1000)
            except Exception:
                pass
            try:
                QToolTip.hideText()
            except Exception:
                pass
            return True

        # 스타일 복제 도구는 ESC로 기준 선택/도구 상태를 해제한다.
        try:
            if et in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress) and event.key() == Qt.Key.Key_Escape:
                if getattr(getattr(self, "view", None), "draw_mode", None) == "text_style_clone":
                    if et == QEvent.Type.KeyPress:
                        if hasattr(self, "clear_text_style_clone_source"):
                            self.clear_text_style_clone_source(keep_tool=False)
                        else:
                            self.set_tool(None)
                    event.accept()
                    return True
        except Exception:
            pass

        # Enter/Esc from right-side numeric/single-line inputs must commit/cancel the
        # edit and return focus to the image workspace.  Do this before global
        # shortcut handling or Qt focus traversal can move focus to the OCR language
        # combo box.
        try:
            if et in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress):
                key = event.key()
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
                    target = self.current_single_line_input_widget(obj)
                    if target is not None:
                        # Do not steal Enter from multiline text editors.
                        if not isinstance(target, (QTextEdit, QPlainTextEdit)):
                            if key == Qt.Key.Key_Escape:
                                if self.escape_single_line_input_focus_first(target):
                                    event.accept()
                                    return True
                            else:
                                if not (event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.AltModifier)):
                                    if self.finish_single_line_input_by_enter(target):
                                        event.accept()
                                        return True
        except Exception:
            pass

        # Source compare clone sync must be driven only by real view movement.
        # Resize/Paint/MouseMove are layout/UI events and can drag the image toward
        # the top-left when the compare splitter is moved, so they are intentionally ignored.
        try:
            view = getattr(self, "view", None)
            if view is not None and obj is view.viewport():
                if et in (QEvent.Type.Wheel, QEvent.Type.MouseButtonRelease):
                    try:
                        if hasattr(self, "_begin_source_compare_clone_fast_path"):
                            self._begin_source_compare_clone_fast_path("main_view_event", delay_ms=120)
                    except Exception:
                        pass
                    if hasattr(self, "schedule_source_compare_sync"):
                        self.schedule_source_compare_sync(16 if et == QEvent.Type.Wheel else 0)
        except Exception:
            pass

        # Source compare clone can now be controlled directly.
        # If scroll sync is ON, wheel/drag operations on the clone drive the main work view too.
        try:
            sc_view = getattr(self, "source_compare_view", None)
            if sc_view is not None and obj is sc_view.viewport():
                if et == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                    try:
                        if hasattr(self, '_hide_eyedropper_color_feedback'):
                            self._hide_eyedropper_color_feedback()
                    except Exception:
                        pass

                if (
                    et == QEvent.Type.MouseButtonPress
                    and event.button() == Qt.MouseButton.LeftButton
                    and (event.modifiers() & Qt.KeyboardModifier.AltModifier)
                    and getattr(self, "cb_mode", None) is not None
                    and self.cb_mode.currentIndex() == 4
                ):
                    try:
                        pt = sc_view.mapToScene(event.pos())
                        if hasattr(self, "pick_final_paint_color_from_source_scene"):
                            self.pick_final_paint_color_from_source_scene(int(pt.x()), int(pt.y()), global_pos=event.globalPosition().toPoint())
                            return True
                    except Exception:
                        pass

                if (
                    et == QEvent.Type.MouseMove
                    and event.buttons() & Qt.MouseButton.LeftButton
                    and (event.modifiers() & Qt.KeyboardModifier.AltModifier)
                    and getattr(self, "cb_mode", None) is not None
                    and self.cb_mode.currentIndex() == 4
                ):
                    try:
                        pt = sc_view.mapToScene(event.pos())
                        if hasattr(self, "pick_final_paint_color_from_source_scene"):
                            self.pick_final_paint_color_from_source_scene(int(pt.x()), int(pt.y()), global_pos=event.globalPosition().toPoint())
                            return True
                    except Exception:
                        pass

                if et == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                    try:
                        if hasattr(self, "_begin_source_compare_clone_fast_path"):
                            self._begin_source_compare_clone_fast_path("clone_mouse_press", delay_ms=120)
                    except Exception:
                        pass
                    try:
                        self._source_compare_user_driving = True
                    except Exception:
                        pass
                elif et == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                    try:
                        if hasattr(self, "_begin_source_compare_clone_fast_path"):
                            self._begin_source_compare_clone_fast_path("clone_mouse_release", delay_ms=120)
                    except Exception:
                        pass
                    try:
                        self._source_compare_user_driving = False
                    except Exception:
                        pass
                    if hasattr(self, "schedule_main_sync_from_source_compare"):
                        self.schedule_main_sync_from_source_compare(16)
                elif et == QEvent.Type.Wheel:
                    try:
                        if hasattr(self, "_begin_source_compare_clone_fast_path"):
                            self._begin_source_compare_clone_fast_path("clone_wheel", delay_ms=120)
                    except Exception:
                        pass
                    try:
                        self._source_compare_user_driving = True
                    except Exception:
                        pass
                    if hasattr(self, "schedule_main_sync_from_source_compare"):
                        self.schedule_main_sync_from_source_compare(16)
                    try:
                        QTimer.singleShot(140, lambda: setattr(self, '_source_compare_user_driving', False))
                    except Exception:
                        pass

                if et == QEvent.Type.MouseMove and getattr(self, "_source_compare_user_driving", False):
                    try:
                        if hasattr(self, "_begin_source_compare_clone_fast_path"):
                            self._begin_source_compare_clone_fast_path("clone_mouse_move", delay_ms=120)
                    except Exception:
                        pass

                if hasattr(self, "handle_source_compare_quick_ocr_event") and self.handle_source_compare_quick_ocr_event(event):
                    return True
        except Exception:
            pass

        try:
            view = getattr(self, "view", None)
            if view is not None and obj is view.viewport() and et == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                if hasattr(self, '_hide_eyedropper_color_feedback'):
                    self._hide_eyedropper_color_feedback()
        except Exception:
            pass


        try:
            if obj is getattr(self, '_source_compare_splitter_handle', None):
                if et == QEvent.Type.MouseButtonPress:
                    self._source_compare_splitter_adjusting = True
                    if hasattr(self, '_block_source_compare_sync_temporarily'):
                        self._block_source_compare_sync_temporarily(320)
                    if hasattr(self, '_capture_source_compare_splitter_states'):
                        self._source_compare_splitter_view_states = self._capture_source_compare_splitter_states()
                elif et == QEvent.Type.MouseMove:
                    # splitter 이동은 레이아웃 변경만 해야 한다. 이미지 좌표/확대/스크롤은 저장값으로 유지한다.
                    if hasattr(self, '_block_source_compare_sync_temporarily'):
                        self._block_source_compare_sync_temporarily(220)
                    if hasattr(self, '_restore_source_compare_splitter_states'):
                        self._restore_source_compare_splitter_states()
                elif et == QEvent.Type.MouseButtonRelease:
                    states = getattr(self, '_source_compare_splitter_view_states', None)
                    if hasattr(self, '_block_source_compare_sync_temporarily'):
                        self._block_source_compare_sync_temporarily(320)
                    if hasattr(self, '_restore_source_compare_splitter_states'):
                        self._restore_source_compare_splitter_states(states)
                        QTimer.singleShot(0, lambda s=states: self._restore_source_compare_splitter_states(s))
                        QTimer.singleShot(80, lambda s=states: self._restore_source_compare_splitter_states(s))
                    self._source_compare_splitter_view_states = None
                    QTimer.singleShot(180, lambda: setattr(self, '_source_compare_splitter_adjusting', False))
                elif et == QEvent.Type.MouseButtonDblClick:
                    if hasattr(self, 'reset_source_compare_splitter_half'):
                        self.reset_source_compare_splitter_half()
                        event.accept()
                        return True
        except Exception:
            pass

        try:
            html = obj.property("delayed_tooltip_html") if obj is not None and hasattr(obj, "property") else None
        except Exception:
            html = None

        if html:
            if not self.is_interface_tooltips_enabled():
                try:
                    if getattr(self, "_tooltip_target", None) is obj or getattr(self, "_tooltip_visible_target", None) is obj:
                        self._tooltip_target = None
                        self._tooltip_html = ""
                        timer = getattr(self, "_tooltip_timer", None)
                        if timer is not None:
                            timer.stop()
                        self._hide_delayed_tooltip_popup()
                except Exception:
                    pass
                return False
            try:
                if et == QEvent.Type.Enter:
                    # New target: always clear any previous popup first.
                    if getattr(self, "_tooltip_visible_target", None) is not obj:
                        self._hide_delayed_tooltip_popup()
                    self._tooltip_target = obj
                    self._tooltip_html = str(html)
                    popup = getattr(self, "_tooltip_popup", None)
                    try:
                        self._tooltip_timer.stop()
                    except Exception:
                        pass
                    if popup is not None and popup.isVisible() and getattr(self, "_tooltip_visible_target", None) is obj:
                        return False
                    self._tooltip_timer.start(420)

                elif et == QEvent.Type.MouseMove:
                    if getattr(self, "_tooltip_target", None) is obj:
                        self._tooltip_html = str(html)

                elif et in (
                    QEvent.Type.Leave,
                    QEvent.Type.Hide,
                    QEvent.Type.Close,
                    QEvent.Type.Destroy,
                    QEvent.Type.FocusOut,
                    QEvent.Type.WindowDeactivate,
                    QEvent.Type.MouseButtonPress,
                    QEvent.Type.MouseButtonRelease,
                    QEvent.Type.Wheel,
                    QEvent.Type.KeyPress,
                ):
                    if getattr(self, "_tooltip_target", None) is obj or getattr(self, "_tooltip_visible_target", None) is obj:
                        try:
                            self._tooltip_timer.stop()
                        except Exception:
                            pass
                        self._tooltip_target = None
                        self._tooltip_html = ""
                        self._hide_delayed_tooltip_popup()
            except Exception:
                pass

        return super().eventFilter(obj, event)


    def configure_ui_tooltips(self):
        def seq_text(key):
            if key.startswith("RAW:"):
                return key[4:]
            try:
                return self.shortcut_settings.seq(key).toString(QKeySequence.SequenceFormat.NativeText)
            except Exception:
                return ""

        def tooltip_pos(widget, pos="", x=0, y=0):
            try:
                if widget is not None:
                    if pos:
                        widget.setProperty("delayed_tooltip_position", pos)
                    if x:
                        widget.setProperty("delayed_tooltip_offset_x", int(x))
                    if y:
                        widget.setProperty("delayed_tooltip_offset_y", int(y))
            except Exception:
                pass

        # 좌측 그림판/마스크 도구
        if hasattr(self, "tb") and self.tb is not None:
            action_info = []
            if hasattr(self, "act_brush"): action_info.append((self.act_brush, "브러시", seq_text("paint_brush")))
            if hasattr(self, "act_erase"): action_info.append((self.act_erase, "지우개", seq_text("paint_erase")))
            if hasattr(self, "act_redo"): action_info.append((self.act_redo, "작업 재실행", seq_text("paint_redo")))
            if hasattr(self, "act_magic"): action_info.append((self.act_magic, "요술봉", seq_text("paint_magic_select"), "마스크 탭에서는 마스크 선택/채우기, 최종결과 탭에서는 팔레트 색상으로 영역 칠하기에 사용합니다."))
            if hasattr(self, "act_mask_wrap"): action_info.append((self.act_mask_wrap, "마스크 랩핑", seq_text("paint_mask_wrap"), "영역 안의 떨어진 마스크들을 하나의 채움 영역으로 감싸줍니다."))
            if hasattr(self, "act_mask_cut"): action_info.append((self.act_mask_cut, "마스크 커팅", seq_text("paint_mask_cut"), "선택 영역 밖 경계를 지정 픽셀만큼 잘라 붙어 있는 마스크를 분리합니다."))
            if hasattr(self, "act_color_outline_mask"): action_info.append((self.act_color_outline_mask, "색상/테두리 마스크", seq_text("paint_color_outline_mask"), "드래그한 영역 안에서 텍스트 색상 또는 닫힌 획 내부를 현재 마스크에 추가합니다. Alt+클릭으로 기준 색상을 찍습니다."))
            if hasattr(self, "act_original_restore"): action_info.append((self.act_original_restore, "영역 원본 복구", seq_text("paint_original_restore"), "최종결과 탭에서 지정한 영역에 원본 이미지 조각을 다시 덧씌워 수선합니다."))
            if hasattr(self, "act_final_area_paint"): action_info.append((self.act_final_area_paint, "영역 페인팅/마스킹", seq_text("paint_area_fill"), "마스크 탭에서는 영역 마스킹, 최종결과 탭에서는 현재 페인팅 색상으로 영역을 칠합니다."))
            if hasattr(self, "act_final_text_tool"): action_info.append((self.act_final_text_tool, "최종 텍스트 도구", seq_text("final_text_tool"), "최종화면을 클릭하면 텍스트 영역을 만듭니다. 내용 작성 후 Ctrl+Return을 누르거나 다른 곳을 클릭하면 작성이 완료됩니다."))
            if hasattr(self, "act_text_style_clone"): action_info.append((self.act_text_style_clone, "스타일 복제", seq_text("final_style_clone"), "기준 텍스트를 먼저 클릭하면 초록 점선으로 표시됩니다. 이후 다른 텍스트를 클릭하면 텍스트 스타일과 고급 옵션을 복제합니다. ESC로 해제합니다."))
            if hasattr(self, "act_final_paint_to_bg"): action_info.append((self.act_final_paint_to_bg, "배경을 원본으로 쓰기", seq_text("final_paint_to_background"), "최종결과 배경을 이후 분석/인페인팅 기준이 되는 작업용 원본으로 반영합니다."))
            if hasattr(self, "act_final_paint_above_text"): action_info.append((self.act_final_paint_above_text, "텍스트 위에 페인팅", seq_text("final_paint_above_toggle"), "ON이면 이후 새로 칠하는 브러시가 텍스트보다 위 레이어에 그려집니다."))
            for info in action_info:
                try:
                    if len(info) >= 4:
                        act, title, sk, desc = info
                    else:
                        act, title, sk = info
                        desc = ""
                    _w = self.tb.widgetForAction(act)
                    if _w is not None:
                        _w.setToolTip("")
                        tooltip_pos(_w, "right")
                    self.register_delayed_tooltip(_w, title, sk, desc)
                except Exception:
                    pass

        if hasattr(self, "act_final_paint_color") and hasattr(self, "tb"):
            try:
                w = self.tb.widgetForAction(self.act_final_paint_color)
                if w is not None:
                    w.setProperty("force_outlined_tooltip_text", True)
                    w.setProperty("force_color_tooltip_text", True)
                    tooltip_pos(w, "right")
                self.register_delayed_tooltip(w, "최종 페인팅 색상", seq_text("final_paint_color"), "스포이드: Alt+마우스 좌클릭")
            except Exception:
                self.register_delayed_tooltip(self.tb.widgetForAction(self.act_final_paint_color), "최종 페인팅 색상", seq_text("final_paint_color"), "스포이드: Alt+마우스 좌클릭")
        if hasattr(self, "mask_toggle_wrap"):
            tooltip_pos(self.mask_toggle_wrap, "right")
            self.register_delayed_tooltip(
                self.mask_toggle_wrap,
                "페인팅 마스크 ON/OFF",
                seq_text("paint_mask_toggle"),
                "ON은 분석 기반, OFF는 직접 칠한 마스크를 사용합니다."
            )
        if hasattr(self, "sb_brush_size"):
            self.register_delayed_tooltip(self.sb_brush_size, "브러시 크기", f"{seq_text('paint_zoom_out')} / {seq_text('paint_zoom_in')}", "브러시와 지우개의 두께를 1px 단위로 조절합니다.")
        if hasattr(self, "final_paint_option_bar"):
            self.register_delayed_tooltip(self.sb_final_paint_opacity, "최종 브러시 불투명도", f"{seq_text('final_paint_opacity_dec')} / {seq_text('final_paint_opacity_inc')}", "최종화면 브러시 색상의 알파값을 조절합니다.")
        if hasattr(self, "magic_wand_bar"):
            self.register_delayed_tooltip(self.btn_magic_expand, "선택 영역 확장", seq_text("paint_magic_expand"))
            self.register_delayed_tooltip(self.btn_magic_fill, "마스킹/영역 칠하기", seq_text("paint_magic_fill"), "마스크 탭에서는 마스크를 채우고, 최종결과 탭에서는 현재 팔레트 색상으로 영역을 칠합니다.")
            self.register_delayed_tooltip(self.sb_magic_tolerance, "RGB 허용범위", f"{seq_text('paint_magic_tolerance_inc')} / {seq_text('paint_magic_tolerance_dec')}")
            self.register_delayed_tooltip(self.sb_magic_expand, "영역 확장 범위", f"{seq_text('paint_magic_expand_inc')} / {seq_text('paint_magic_expand_dec')}")
        if hasattr(self, "area_paint_bar"):
            self.register_delayed_tooltip(self.btn_area_paint_rect, "사각형 영역", seq_text("paint_mask_wrap_rect"), "마스크 탭에서는 영역 마스킹, 최종결과 탭에서는 현재 페인팅 색상으로 영역 칠하기를 수행합니다.")
            self.register_delayed_tooltip(self.btn_area_paint_free, "자유형 영역", seq_text("paint_mask_wrap_free"), "마스크 탭에서는 영역 마스킹, 최종결과 탭에서는 현재 페인팅 색상으로 영역 칠하기를 수행합니다.")
            self.register_delayed_tooltip(self.btn_area_paint_polygon, "폴리곤 영역", seq_text("paint_mask_wrap_polygon"), "점을 하나씩 찍어 직선으로 닫힌 영역을 만든 뒤 영역 마스킹/페인팅을 수행합니다. 작성 중 Ctrl+Z/Backspace는 마지막 점만 취소합니다.")
        if hasattr(self, "mask_wrap_bar"):
            self.register_delayed_tooltip(self.btn_mask_wrap_rect, "사각형으로 영역 그리기", seq_text("paint_mask_wrap_rect"), "윈도우 캡처처럼 사각형 범위를 잡고 그 안의 마스크들을 하나로 감싸 채웁니다.")
            self.register_delayed_tooltip(self.btn_mask_wrap_free, "자유형으로 영역 그리기", seq_text("paint_mask_wrap_free"), "드래그한 자유형 범위 안에서만 마스크들을 하나로 감싸 채웁니다.")
            self.register_delayed_tooltip(self.btn_mask_wrap_polygon, "폴리곤으로 영역 그리기", seq_text("paint_mask_wrap_polygon"), "점을 하나씩 찍어 만든 닫힌 다각형 안에서만 마스크들을 하나로 감싸 채웁니다.")
        if hasattr(self, "mask_cut_bar"):
            self.register_delayed_tooltip(self.btn_mask_cut_rect, "사각형으로 영역 그리기", seq_text("paint_mask_wrap_rect"), "사각형 보존 영역의 바깥 경계를 지정 픽셀만큼 잘라냅니다.")
            self.register_delayed_tooltip(self.btn_mask_cut_free, "자유형으로 영역 그리기", seq_text("paint_mask_wrap_free"), "자유형 보존 영역의 바깥 경계를 지정 픽셀만큼 잘라냅니다.")
            self.register_delayed_tooltip(self.btn_mask_cut_polygon, "폴리곤으로 영역 그리기", seq_text("paint_mask_wrap_polygon"), "점을 하나씩 찍어 만든 닫힌 다각형 보존 영역의 바깥 경계를 지정 픽셀만큼 잘라냅니다.")
            self.register_delayed_tooltip(self.sb_mask_cut_px, "커팅 폭", "", "선택 영역 밖으로 잘라낼 마스크 폭입니다.")
        if hasattr(self, "color_outline_mask_bar"):
            self.register_delayed_tooltip(self.btn_color_outline_mask_rect, "사각형 영역 지정", "", "사각형으로 영역을 잡고, 그 안에서 조건에 맞는 부분만 마스크합니다.")
            self.register_delayed_tooltip(self.btn_color_outline_mask_free, "자유형 영역 지정", "", "자유형으로 영역을 잡고, 그 안에서 조건에 맞는 부분만 마스크합니다.")
            self.register_delayed_tooltip(self.btn_color_outline_mask_polygon, "폴리곤 영역 지정", seq_text("paint_mask_wrap_polygon"), "점을 하나씩 찍어 만든 닫힌 다각형 안에서 조건에 맞는 부분만 마스크합니다.")
            self.register_delayed_tooltip(self.btn_color_outline_text_color, "텍스트", "Alt+클릭", "획 감지 OFF일 때 이 색상과 가까운 픽셀을 마스크합니다.")
            self.register_delayed_tooltip(self.sb_color_outline_tolerance, "허용치", "", "텍스트 또는 획 색상을 얼마나 넓게 허용할지 정합니다.")
            self.register_delayed_tooltip(self.cb_color_outline_detect_outline, "획 감지", "", "켜면 텍스트 색상은 무시하고, 옆 색상칩의 획 색으로 닫힌 윤곽 내부를 마스크합니다. 획이 그림이나 배경선과 이어진 경우에는 의도하지 않은 영역이 잡힐 수 있습니다.")
            self.register_delayed_tooltip(self.btn_color_outline_outline_color, "획 감지", "Alt+클릭", "획 감지 ON일 때 닫힌 윤곽을 찾을 기준 색상입니다.")
            self.register_delayed_tooltip(self.sb_color_outline_expand, "영역 확장", "", "최종 마스크를 지정 픽셀만큼 확장합니다.")
        if hasattr(self, "ocr_region_bar"):
            self.register_delayed_tooltip(self.btn_ocr_region_rect, "사각형 OCR 분석 영역", seq_text("paint_mask_wrap_rect"), "사각형으로 OCR이 읽을 영역을 지정합니다.")
            self.register_delayed_tooltip(self.btn_ocr_region_free, "자유형 OCR 분석 영역", seq_text("paint_mask_wrap_free"), "자유형으로 OCR이 읽을 영역을 지정합니다.")
            self.register_delayed_tooltip(self.btn_ocr_region_polygon, "폴리곤 OCR 분석 영역", seq_text("paint_mask_wrap_polygon"), "점을 하나씩 찍어 만든 닫힌 다각형을 OCR 분석 영역으로 지정합니다.")
            self.register_delayed_tooltip(self.btn_ocr_region_finish, "OCR 분석 영역 지정 종료", "", "지정한 영역을 저장하거나 폐기하고 영역 지정 모드를 종료합니다.")

        # 툴팁 글자색은 테마 기본값을 따른다.
        # 색상 버튼처럼 특수한 경우만 개별 QToolTip 스타일에서 처리한다.

        # 우측 상단 작업 버튼/옵션
        if hasattr(self, "sb_trans_chunk"):
            self.register_delayed_tooltip(self.sb_trans_chunk, "묶음 수", "", "한 번의 API 요청에 묶어서 보낼 텍스트 줄 수")
        if hasattr(self, "btn_reanalyze"):
            tooltip_pos(self.btn_reanalyze, "above")
            self.register_delayed_tooltip(self.btn_reanalyze, "재분석", seq_text("paint_reanalyze"), "텍스트 마스크를 유지한 채 현재 페이지를 다시 분석합니다.")
        if hasattr(self, "btn_analyze"):
            tooltip_pos(self.btn_analyze, "above")
            self.register_delayed_tooltip(self.btn_analyze, "분석", seq_text("work_analyze"), "현재 페이지를 분석합니다.")
            # 빠른 OCR 설정은 버튼이 아니라 단축키/메뉴로 여는 기능이다.
            # 메인 윈도우(self)에 지연 툴팁을 등록하면 창 전체가 툴팁 영역이 되어
            # 포커스가 없어도 마우스 진입 시 계속 툴팁이 뜬다.
            # 따라서 여기서는 별도 지연 툴팁을 등록하지 않는다.
        if hasattr(self, "btn_translate"):
            tooltip_pos(self.btn_translate, "above")
            self.register_delayed_tooltip(self.btn_translate, "번역", seq_text("work_translate"))
        if hasattr(self, "btn_inpaint"):
            tooltip_pos(self.btn_inpaint, "above")
            self.register_delayed_tooltip(self.btn_inpaint, "인페인팅", seq_text("work_inpaint"))
        if hasattr(self, "btn_text_cleanup"):
            tooltip_pos(self.btn_text_cleanup, "above")
            self.register_delayed_tooltip(
                self.btn_text_cleanup,
                "텍스트 정리",
                seq_text("work_clean_text"),
                self.tr_msg("체크 해제한 OCR/텍스트 항목을 삭제하고 번호를 재정렬합니다. 활성 OCR 영역 밖의 자동 마스크도 함께 정리하며, 사용자 수정 마스크는 유지합니다.")
            )
        if hasattr(self, "btn_mask_cleanup"):
            tooltip_pos(self.btn_mask_cleanup, "above")
            self.register_delayed_tooltip(self.btn_mask_cleanup, "마스크 정리", seq_text("work_clean_mask"), "현재 페이지에서 활성 OCR 영역 밖의 자동 마스크만 제거합니다. 사용자 수정 마스크는 유지합니다.")
        if hasattr(self, "cb_show_final_text"):
            tooltip_pos(self.cb_show_final_text, "left", x=-6)
            self.register_delayed_tooltip(self.cb_show_final_text, "텍스트 표시 ON/OFF", seq_text("view_text_toggle"))
        if hasattr(self, "cb_font"):
            try:
                self.cb_font.setProperty("allow_delayed_tooltip_on_combo", True)
                tooltip_pos(self.cb_font, "below", y=4)
            except Exception:
                pass
            self.register_delayed_tooltip(
                self.cb_font,
                "글꼴 선택",
                seq_text("item_font_select"),
                "폰트 설정창을 엽니다.",
            )
        if hasattr(self, "sb_font_size"):
            self.register_delayed_tooltip(
                self.sb_font_size,
                "글꼴 크기",
                seq_text("text_font_size"),
                "숫자 입력은 선택 텍스트 크기를 입력값으로 통일합니다. 마우스 휠, =/+ 확대, - 축소는 각 텍스트의 현재 크기를 기준으로 상대 조정합니다.",
            )
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
            tooltip_pos(self.btn_prev_page, "above")
            self.register_delayed_tooltip(self.btn_prev_page, "이전 페이지", seq_text("work_page_prev"))
        if hasattr(self, "btn_next_page"):
            tooltip_pos(self.btn_next_page, "above")
            self.register_delayed_tooltip(self.btn_next_page, "다음 페이지", seq_text("work_page_next"))
        if hasattr(self, "btn_page_tab_menu"):
            tooltip_pos(self.btn_page_tab_menu, "above")
            self.register_delayed_tooltip(self.btn_page_tab_menu, "페이지 목록", seq_text("work_page_list"))
        if hasattr(self, "btn_page_scroll_left"):
            tooltip_pos(self.btn_page_scroll_left, "above")
            self.register_delayed_tooltip(self.btn_page_scroll_left, "페이지 탭 왼쪽 이동", "")
        if hasattr(self, "btn_page_scroll_right"):
            tooltip_pos(self.btn_page_scroll_right, "above")
            self.register_delayed_tooltip(self.btn_page_scroll_right, "페이지 탭 오른쪽 이동", "")
        if hasattr(self, "btn_page_add"):
            tooltip_pos(self.btn_page_add, "above")
            self.register_delayed_tooltip(self.btn_page_add, "이미지 불러오기", seq_text("project_import_images"), "현재 프로젝트에서는 현재 페이지 뒤에 이미지를 추가합니다.")
        if hasattr(self, "btn_project_exit"):
            tooltip_pos(self.btn_project_exit, "below_low", y=10)
            self.register_delayed_tooltip(self.btn_project_exit, "프로젝트 나가기", seq_text("project_exit"), "현재 프로젝트를 닫고 시작 화면으로 돌아갑니다.")
        if hasattr(self, "btn_page"):
            # 페이지 번호/이름 영역은 메뉴 조작 동선과 겹쳐 툴팁이 방해되므로 끈다.
            try:
                self.btn_page.setToolTip("")
                for _name in ("delayed_tooltip_title", "delayed_tooltip_shortcut", "delayed_tooltip_description", "delayed_tooltip_html"):
                    self.btn_page.setProperty(_name, "")
            except Exception:
                pass
        if hasattr(self, "cb_mode"):
            tooltip_pos(self.cb_mode, "above")
            self.register_delayed_tooltip(self.cb_mode, "작업 탭", seq_text("work_tab_cycle"), "원본, 분석도, 마스크, 최종결과 탭을 전환합니다.")
        if hasattr(self, "btn_quick_undo"):
            tooltip_pos(self.btn_quick_undo, "above")
            self.register_delayed_tooltip(self.btn_quick_undo, "뒤로가기", seq_text("paint_undo"), "최근 작업을 되돌립니다.")
        if hasattr(self, "btn_quick_redo"):
            tooltip_pos(self.btn_quick_redo, "above")
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
            try:
                self.cb_item_text_preset.setProperty("allow_delayed_tooltip_on_combo", True)
            except Exception:
                pass
            self.register_delayed_tooltip(self.cb_item_text_preset, "개별 글꼴 프리셋", "", "선택한 텍스트 객체에 적용할 개별 글꼴 프리셋을 선택합니다.")
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
        if hasattr(self, "final_item_size"):
            self.register_delayed_tooltip(
                self.final_item_size,
                "선택 텍스트 크기",
                "= 확대 / - 축소",
                "숫자 입력은 선택 텍스트 크기를 입력값으로 통일합니다. 마우스 휠, =/+ 확대, - 축소는 각 텍스트의 현재 크기를 기준으로 상대 조정합니다.",
            )
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
        if hasattr(self, "sb_text_opacity"):
            self.register_delayed_tooltip(self.sb_text_opacity, "텍스트 불투명도", "", "선택한 텍스트의 불투명도를 조절합니다.")
        if hasattr(self, "btn_text_effect_gradient"):
            self.register_delayed_tooltip(self.btn_text_effect_gradient, "고급 텍스트/획 옵션", seq_text("text_effect_gradient"), "선택한 텍스트에 고급 텍스트/획 옵션 창을 엽니다.")
        if hasattr(self, "btn_text_effect_transform"):
            self.register_delayed_tooltip(self.btn_text_effect_transform, "텍스트 변형", seq_text("text_transform_toggle"), "선택한 텍스트의 기준 변형 모드를 켜거나 끕니다.")
        if hasattr(self, "btn_text_effect_skew"):
            self.register_delayed_tooltip(self.btn_text_effect_skew, "평행사변형 변형", seq_text("text_skew_toggle"), "선택한 텍스트를 평행사변형 형태로 기울입니다.")
        if hasattr(self, "btn_text_effect_trapezoid"):
            self.register_delayed_tooltip(self.btn_text_effect_trapezoid, "사다리꼴 변형", seq_text("text_trapezoid_toggle"), "선택한 텍스트에 좌우/상하 원근감을 적용합니다.")
        if hasattr(self, "btn_text_effect_arc"):
            self.register_delayed_tooltip(self.btn_text_effect_arc, "부채꼴 변형", seq_text("text_arc_toggle"), "선택한 텍스트를 부채꼴로 휘게 변형합니다.")
        if hasattr(self, "btn_align_left"):
            self.register_delayed_tooltip(self.btn_align_left, "왼쪽 정렬", seq_text("item_align_left"))
            self.register_delayed_tooltip(self.btn_align_center, "가운데 정렬", seq_text("item_align_center"))
            self.register_delayed_tooltip(self.btn_align_right, "오른쪽 정렬", seq_text("item_align_right"))

    def message_box_style(self):
        """확인/경고/질문창 공통 스타일. 홈/클라우드 쪽의 부드러운 카드 톤에 맞춘다."""
        if self.is_light_theme():
            return """
                QMessageBox, QMessageBox QWidget { background:#F5EFF3; color:#111827; }
                QMessageBox QLabel { background:#F5EFF3; color:#111827; line-height:1.35em; }
                QMessageBox QLabel, QMessageBox QFrame {
                    border:0px;
                }
                QMessageBox QTextEdit, QMessageBox QPlainTextEdit, QMessageBox QScrollArea {
                    background:#ffffff;
                    color:#111827;
                    border:1px solid #D1C9CE;
                    selection-background-color:#F5E8EA;
                    selection-color:#111827;
                }
                QMessageBox QPushButton {
                    background:#ffffff;
                    color:#111827;
                    border:1px solid #D1C9CE;
                    border-radius:0px;
                    padding:7px 18px;
                    min-width:72px;
                }
                QMessageBox QPushButton:hover { background:#FBF5F6; border-color:#D7A3A9; }
                QMessageBox QPushButton:pressed { background:#F5E8EA; }
                QMessageBox QToolTip { background-color:#ffffff; color:#111827; border:1px solid #D1C9CE; border-radius:0px; padding:5px; }
            """
        return """
            QMessageBox, QMessageBox QWidget { background:#252328; color:#F4EEF2; }
            QMessageBox QLabel { background:#252328; color:#F4EEF2; line-height:1.35em; }
            QMessageBox QLabel, QMessageBox QFrame {
                border:0px;
            }
            QMessageBox QTextEdit, QMessageBox QPlainTextEdit, QMessageBox QScrollArea {
                background:#211F23;
                color:#F4EEF2;
                border:1px solid #3A363B;
                selection-background-color:#5B3136;
                selection-color:#ffffff;
            }
            QMessageBox QPushButton {
                background:#373136;
                color:#F4EEF2;
                border:1px solid #615A60;
                border-radius:0px;
                padding:7px 18px;
                min-width:72px;
            }
            QMessageBox QPushButton:hover { background:#443A40; border-color:#7B7078; }
            QMessageBox QPushButton:pressed { background:#302C31; }
            QMessageBox QToolTip { background-color:#242329; color:#ffffff; border:1px solid #555056; border-radius:0px; padding:5px; }
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
            if hasattr(self, "clear_pending_work_cache_save_state"):
                self.clear_pending_work_cache_save_state("clear_current_project_runtime_state")
        except Exception:
            pass
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
        self.undo_clear_all_pages("project close")
        self.undo_clear_project("project close")
        self.undo_boundary = None
        self.project_ui_view_states = {}
        self.magic_wand_mask = None
        self.magic_wand_seed = None
        self.magic_wand_seeds = []
        self.magic_wand_history = []
        self.text_clipboard = []
        self.text_clipboard_is_plain = False
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
                workspace_dir=getattr(self, "project_dir", "") or "",
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

    def _find_recent_project_workspace_folder(self, package_path):
        """최근 프로젝트 카드의 .ysbt 경로에서 실제 작업 폴더를 찾는다.

        최근 프로젝트의 "폴더 위치 열기"는 .ysbt가 저장된 문서 폴더가 아니라
        workspaces 아래의 해당 프로젝트 작업 폴더를 우선 열어야 한다.
        """
        raw = str(package_path or "").strip().strip('"')
        if not raw:
            return None
        try:
            package_abs = os.path.abspath(os.path.expandvars(os.path.expanduser(raw)))
        except Exception:
            package_abs = raw

        # 현재 열려 있는 프로젝트라면 이미 알고 있는 project_dir이 가장 정확하다.
        try:
            current_package = getattr(self, "ysbt_package_path", None)
            current_dir = getattr(self, "project_dir", None)
            if current_package and current_dir:
                if os.path.abspath(str(current_package)).lower() == os.path.abspath(str(package_abs)).lower():
                    if os.path.isdir(str(current_dir)):
                        return os.path.abspath(str(current_dir))
        except Exception:
            pass

        manifest = {}
        project_uuid = ""
        try:
            if os.path.isfile(package_abs):
                manifest = read_ysb_manifest(package_abs) or {}
                project_uuid = str(manifest.get("project_uuid") or "")
        except Exception:
            manifest = {}
            project_uuid = ""

        try:
            root = Path(str(workspaces_dir()))
            if not root.exists():
                return None

            package_key = os.path.abspath(str(package_abs)).lower()
            uuid_match = None
            for child in root.iterdir():
                try:
                    if not child.is_dir():
                        continue
                    if not (child / PROJECT_FILENAME).exists():
                        continue
                    manifest_path = child / "manifest.json"
                    if not manifest_path.exists():
                        continue
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        m = json.load(f)
                    if not isinstance(m, dict):
                        continue
                    src = str(m.get("package_source") or "")
                    src_key = os.path.abspath(src).lower() if src else ""
                    child_uuid = str(m.get("project_uuid") or "")

                    # 같은 .ysbt 경로가 기록된 폴더를 최우선으로 연다.
                    if src_key and src_key == package_key:
                        if (not project_uuid) or (child_uuid == project_uuid):
                            return str(child)
                    # 예전 기록처럼 package_source가 없거나 경로가 바뀐 경우 UUID로 보조 매칭한다.
                    if project_uuid and child_uuid == project_uuid and uuid_match is None:
                        uuid_match = str(child)
                except Exception:
                    continue
            if uuid_match:
                return uuid_match

            # 예상 폴더명도 한 번 더 확인한다.
            if project_uuid:
                expected = root / f"{clean_workspace_name(Path(package_abs).stem)}_{project_uuid[:8]}"
                if expected.exists() and expected.is_dir():
                    return str(expected)
        except Exception:
            pass
        return None

    def _open_path_location_in_file_manager(self, path, select_file=True):
        """파일/폴더 위치를 OS 파일 관리자에서 연다.

        Windows에서 QDesktopServices.openUrl(QUrl.fromLocalFile(folder))만 쓰면
        상대경로/현재 작업 디렉터리 상태에 따라 바탕화면이나 문서 폴더 같은
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
        """최근 프로젝트 카드의 [폴더 위치 열기].

        이 메뉴에서 말하는 위치는 내부 작업 폴더(workspaces)가 아니라
        사용자가 저장한 .ysbt 파일이 있는 폴더다.
        이전 패치에서 작업 폴더를 우선 열도록 바꾸면서 여러 최근 항목이
        모두 문서/YSB_Translator/workspaces 쪽으로 열리는 혼동이 생겼으므로
        여기서는 항상 recent_projects.json에 기록된 .ysbt_path 기준으로 연다.
        """
        try:
            self._open_path_location_in_file_manager(path, select_file=False)
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

