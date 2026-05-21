from ysb.ui.main_window_support import *
from ysb.ui.main_window_interaction_mixin import MainWindowInteractionMixin
from ysb.ui.main_window_cloud_mixin import MainWindowCloudMixin
from ysb.ui.main_window_settings_theme_mixin import MainWindowSettingsThemeMixin
from ysb.ui.main_window_text_layout_mixin import MainWindowTextLayoutMixin
from ysb.ui.main_window_project_pages_mixin import MainWindowProjectPagesMixin
from ysb.ui.main_window_history_mixin import MainWindowHistoryMixin
from ysb.ui.main_window_operations_mixin import MainWindowOperationsMixin


class MainWindow(MainWindowInteractionMixin, MainWindowCloudMixin, MainWindowSettingsThemeMixin, MainWindowTextLayoutMixin, MainWindowProjectPagesMixin, MainWindowHistoryMixin, MainWindowOperationsMixin, QMainWindow):

    def __init__(self):
        super().__init__()
        # setup_ui() 도중 일부 도구 초기화가 log()를 호출할 수 있다.
        # 이 시점에는 아직 로그 위젯이 만들어지지 않았으므로 임시 버퍼에 보관한다.
        self._pending_log_messages = []
        self.update_window_title()
        self.setWindowIcon(QIcon(resource_path("ysb_icon.ico")))
        self.resize(1600, 950)
        self.setAcceptDrops(True)

        self.api_settings = ApiSettingsStore.load()
        apply_settings_to_config(self.api_settings)
        self.engine = None
        self.restart_engine(show_error=False)

        self.paths = []
        self.idx = 0
        self.data = {}

        self.project_store = ProjectStore()
        self.project_dir = None
        self.workspace_root = str(get_workspace_root())
        self.ysbt_package_path = None
        self.suggested_project_name = None
        self.is_temp_project = False
        self.is_loading_project = False
        self.is_autosaving = False
        self._busy_counter = 0
        self._busy_reason_stack = []
        self._busy_widgets = []

        self.app_options = load_app_options()
        self.sync_translation_option_cache_to_config()
        self.sync_analysis_mask_options_to_config()

        # 저장본/작업 캐시 분리
        # auto_save_enabled=True  : 변경 즉시 실제 project.json에 저장
        # auto_save_enabled=False : 변경은 작업 캐시에만 저장하고, 프로젝트 저장 버튼으로만 확정
        self.auto_save_enabled = bool(self.app_options.get("auto_save_enabled", False))
        self.ui_theme = str(self.app_options.get(UI_THEME_KEY, THEME_DARK) or THEME_DARK).lower()
        if self.ui_theme not in (THEME_DARK, THEME_LIGHT):
            self.ui_theme = THEME_DARK
        self.ui_language = normalize_ui_language(self.app_options.get(UI_LANGUAGE_KEY, LANG_KO))
        self.analysis_number_box_width = int(self.app_options.get("analysis_number_box_width", 40) or 40)
        self.page_tab_display_name_mode = normalize_page_display_mode(self.app_options.get(PAGE_TAB_DISPLAY_MODE_KEY, DEFAULT_PAGE_DISPLAY_MODE))
        self.output_display_name_mode = normalize_page_display_mode(self.app_options.get(OUTPUT_DISPLAY_MODE_KEY, DEFAULT_PAGE_DISPLAY_MODE))
        self.show_paths_in_log = bool(self.app_options.get(SHOW_PATHS_IN_LOG_KEY, False))
        self.show_cache_paths_in_settings = bool(self.app_options.get(SHOW_CACHE_PATHS_IN_SETTINGS_KEY, False))
        self.work_project_store = None
        self.work_project_dir = None
        self.has_unsaved_changes = False
        self._closing_confirmed = False
        # 종료 처리 중에는 focusOut/QTimer가 삭제된 QGraphicsScene에 접근하지 못하게 막는다.
        self._app_is_closing = False

        # 일괄 작업/페이지 로딩 중에는 화면에 남아 있는 마스크를
        # 현재 페이지 데이터에 자동 저장하면 안 된다.
        self.is_batch_running = False
        self.is_page_loading = False
        self.current_batch_mode = None

        self.inline_text_editor = None
        self.inline_text_target = None

        self.text_clipboard = []
        self.text_paste_pending = False
        self.last_canvas_context_pos = None

        self.last_mode = 0
        self._current_work_mode = 0
        self._global_event_filter_installed = False

        # 번역 묶음 수: 한 번의 API 요청에 몇 줄을 묶어 보낼지
        # 번역 API별로 따로 기억한다.
        self.trans_chunk_sizes = {
            "openai": 20,
            "deepseek": 8,
            "google": 50,
            "gemini": 10,
            "custom": 20,
        }

        self.default_text_color = "#000000"
        self.default_stroke_color = "#FFFFFF"
        self.default_line_spacing = 100
        self.default_letter_spacing = 0
        self.default_char_width = 100
        self.default_char_height = 100
        self.default_bold = False
        self.default_italic = False
        self.default_strike = False
        self.final_paint_color = "#FFFFFF"
        self.final_paint_above_text = False
        self.final_paint_opacity = 100
        self.default_align = "center"
        self.mask_toggle_enabled = False
        self.magic_wand_mask = None
        self.magic_wand_seed = None
        self.magic_wand_seeds = []
        self.magic_wand_history = []
        self._style_signal_lock = False
        self._preset_loading = False
        self._syncing_selection = False
        self._table_check_lock = False
        self.text_presets = {}

        self.shortcut_settings = ShortcutSettingsStore.load()
        self.actions = {}
        self.macro_actions = []
        self.item_preset_actions = []
        self.item_text_presets = {}
        self._item_preset_loading = False
        self._item_preset_signal_lock = False
        self.shortcut_label_map = shortcut_label_map()

        # 매크로 실행 큐
        # 비동기 작업(분석/인페인팅/일괄 작업)은 완료 콜백을 받아야 다음 단계로 넘어간다.
        self.macro_running = False
        self.macro_queue = []
        self.macro_current = None
        self.macro_waiting_key = None
        self.macro_waiting_kind = None
        self.macro_current_name = ""
        self._suppress_project_undo = False
        self._tooltip_timer = QTimer(self)
        self._tooltip_timer.setSingleShot(True)
        self._tooltip_timer.timeout.connect(self._show_delayed_tooltip)
        self._tooltip_target = None
        self._tooltip_html = ""

        # 최종화면 텍스트 작업용 실행 취소 스택
        self.page_text_undo_stacks = {}
        # 표/화면 동기화 중에는 텍스트 undo 스냅샷을 만들지 않는다.
        self._text_undo_restore_lock = False
        # 자동저장 직전 화면의 텍스트 아이템 좌표를 data에 반영할 때 재진입을 막는다.
        self._text_scene_sync_lock = False

        # 전역 작업 되돌리기 스택.
        # 페이지/탭/줌/화면 이동/텍스트 편집처럼 여러 페이지를 오가며 생기는 작업을
        # 현재 페이지 전용 스택이 아니라 하나의 시간순 스택으로 관리한다.
        self.project_undo_stack = []
        self.project_redo_stack = []
        self._project_undo_restore_lock = False
        self._deferred_undo_records = {}
        # 매크로/글꼴 프리셋처럼 Undo 기록을 남기지 않는 작업은
        # 과거 Undo로 되돌아가면 상태가 꼬일 수 있으므로 Undo 경계를 세운다.
        self.undo_boundary = None
        self.macro_executed_any = False
        self.macro_has_undo_boundary = False
        self.macro_undo_record = None
        self._macro_allow_undo_append = False
        self.project_ui_view_states = {}
        self.suggested_package_dir = None

        self.setup_actions()
        self.setup_ui()
        self._last_show_final_text_checked = bool(self.cb_show_final_text.isChecked()) if hasattr(self, "cb_show_final_text") else True
        self._last_final_paint_above_text = bool(getattr(self, "final_paint_above_text", False))
        self.load_text_preset_cache()
        self.load_item_text_preset_cache()
        self.setup_menu()
        self.apply_theme(self.ui_theme)
        self.apply_shortcuts()
        self.apply_language(self.ui_language)
        self.install_global_input_filter()
        # 오래된 임시 작업 폴더는 한 달에 한 번 자동 정리한다.
        QTimer.singleShot(1500, self.auto_cleanup_temp_files_if_needed)

        # .ysbt 더블클릭 전용 경량 런처가 남긴 열기 요청을 감시한다.
        # 이미 켜진 앱에 파일 경로만 전달해 드래그앤드롭과 같은 빠른 열기를 구현한다.
        self.setup_external_open_queue_monitor()

    def showEvent(self, event):
        try:
            super().showEvent(event)
        finally:
            self.schedule_native_title_bar_theme(self, dark=not self.is_light_theme())

    def changeEvent(self, event):
        try:
            super().changeEvent(event)
        finally:
            try:
                if event.type() in (
                    QEvent.Type.WindowStateChange,
                    QEvent.Type.PaletteChange,
                    QEvent.Type.StyleChange,
                ):
                    self.schedule_native_title_bar_theme(self, dark=not self.is_light_theme())
            except Exception:
                pass


def exception_hook(exctype, value, traceback):
    global _handling_fatal_exception
    import traceback as tb
    error_msg = "".join(tb.format_exception(exctype, value, traceback))
    print(error_msg)

    # 예외 표시 중 Qt 이벤트가 다시 들어와 같은 예외를 반복 발생시키면
    # CMD에 무한히 쌓이고 프로그램 종료가 늦어진다. 한 번만 다이얼로그를 띄운다.
    if _handling_fatal_exception:
        try:
            sys.__stderr__.write(error_msg + "\n")
        except Exception:
            pass
        sys.exit(1)

    _handling_fatal_exception = True
    try:
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle("python")
        msg_box.setText("치명적인 오류 발생!")
        msg_box.setInformativeText(str(value))
        msg_box.setDetailedText(error_msg)
        apply_message_box_dark_palette(msg_box)
        force_message_box_front(msg_box)
        msg_box.exec()
    except Exception:
        pass
    sys.exit(1)


def run_app() -> None:
    sys.excepthook = exception_hook

    # Windows 작업표시줄이 PyQt 기본 아이콘 대신 앱 아이콘을 잡도록 지정한다.
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("YSB.YeoksikBoongi.Tool")
    except Exception:
        pass

    app = QApplication(sys.argv)

    close_pyinstaller_boot_splash()

    # 두 번째 실행이면 기존 프로세스에 열기 요청만 전달하고 종료한다.
    # 이 경로에서는 어떤 스플래시도 만들지 않는다.
    if notify_running_instance(sys.argv[1:]):
        sys.exit(0)

    single_instance_server = SingleInstanceServer()
    if not single_instance_server.start():
        QMessageBox.warning(None, "단일 실행 경고", "단일 실행 서버를 시작하지 못했습니다.\n프로그램은 계속 실행되지만 중복 실행 차단이 정상 동작하지 않을 수 있습니다.")

    app.setWindowIcon(QIcon(resource_path("ysb_icon.ico")))

    launcher_owned = is_launcher_splash_owner()
    write_launcher_mode_debug("after_launcher_owned_check")
    if launcher_owned:
        # 런처가 55%에서 멈추지 않도록, 런처 모드 판정 직후 즉시 진행률을 남긴다.
        report_launcher_progress(56, translate_ui_text("메인 초기화 시작 중..."))

    # 런처가 시작한 경우:
    # - 메인 스플래시는 절대 만들지 않는다.
    # - 메인은 런처의 단일 스플래시에 진행률만 보고한다.
    if launcher_owned:
        write_main_startup_signal()
        write_launcher_mode_debug("after_startup_signal")
        report_launcher_progress(58, translate_ui_text("환경 준비 중..."))

        # 작업 폴더 설정창 같은 실제 입력창이 필요하면, 런처를 먼저 닫게 한다.
        try:
            needs_setup, _reason, _kind = workspace_root_needs_setup()
        except Exception:
            needs_setup = False
        if needs_setup:
            report_launcher_progress(100, translate_ui_text("설정 화면으로 전환 중..."), done=True)
            wait_for_launcher_closed_if_needed()
            if not run_initial_workspace_setup_if_needed():
                sys.exit(0)
        else:
            if not run_initial_workspace_setup_if_needed():
                sys.exit(0)

        # 런처가 확장자 사전 확인을 처리한 경우 메인은 중복 알림을 띄우지 않는다.
        report_launcher_progress(65, translate_ui_text("환경 준비 중..."))
        prompt_update_ysbt_file_association_if_needed(None)

        report_launcher_progress(78, translate_ui_text("인터페이스 로딩 중..."))
        w = MainWindow()
        single_instance_server.set_main_window(w)

        report_launcher_progress(92, translate_ui_text("화면 구성 마무리 중..."))
        w.setWindowIcon(QIcon(resource_path("ysb_icon.ico")))

        try:
            if len(sys.argv) > 1:
                open_arg = sys.argv[1]
                w.open_project_path(open_arg, external_request=True)
        except Exception:
            pass

        report_launcher_progress(100, translate_ui_text("시작 완료"), done=True)
        wait_for_launcher_closed_if_needed()
        w.show()
        sys.exit(app.exec())

    # 메인 EXE 직접 실행:
    # - 런처가 폴더에 있더라도 호출하지 않는다.
    # - 메인 스플래시만 표시한다.
    if not run_initial_workspace_setup_if_needed():
        sys.exit(0)

    prompt_update_ysbt_file_association_if_needed(None)

    splash = make_splash_screen()
    if splash is not None:
        splash.set_progress(45, translate_ui_text("환경 준비 중..."))

    if splash is not None:
        splash.set_progress(62, translate_ui_text("인터페이스 로딩 중..."))

    w = MainWindow()
    single_instance_server.set_main_window(w)

    if splash is not None:
        splash.set_progress(88, translate_ui_text("화면 구성 마무리 중..."))

    w.setWindowIcon(QIcon(resource_path("ysb_icon.ico")))
    w.show()

    try:
        if len(sys.argv) > 1:
            open_arg = sys.argv[1]
            w.open_project_path(open_arg, external_request=True)
    except Exception:
        pass

    if splash is not None:
        splash.set_progress(100, translate_ui_text("시작 완료"))
        splash.stop()
        QApplication.processEvents()
        QTimer.singleShot(120, lambda: splash.finish(w))

    sys.exit(app.exec())


if __name__ == "__main__":
    run_app()
