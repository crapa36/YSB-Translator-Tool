from ysb.ui.main_window_support import *


class MainWindowSettingsThemeMixin:

    def settings_dialog_style(self):
        """통합 설정/옵션 계열 창 전용 몽글 카드 스타일."""
        if self.is_light_theme():
            return """
                QDialog { background:#f4f6fa; color:#22252b; }
                QScrollArea { background:transparent; border:0; }
                QLabel { color:#22252b; }
                QFrame#SettingsBlock {
                    background:#ffffff;
                    border:1px solid #dfe5ef;
                    border-radius:16px;
                }
                QFrame#SettingsItem {
                    background:#f9fbfe;
                    border:1px solid #e4eaf3;
                    border-radius:14px;
                }
                QLabel#SettingsItemTitle { font-size:13px; font-weight:700; color:#1f232b; }
                QLabel#SettingsTitle, QLabel#SettingsDialogTitle { font-size:22px; font-weight:800; color:#1f232b; }
                QLabel#SettingsSectionTitle { font-size:16px; font-weight:750; color:#1f232b; }
                QLabel#SettingsDescription { color:#667085; line-height:140%; }
                QLabel#SettingsPath {
                    color:#667085;
                    background:#f1f4f9;
                    border:1px solid #e0e6f0;
                    border-radius:0px;
                    padding:3px 6px;
                }
                QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QFontComboBox, QSpinBox, QDoubleSpinBox, QKeySequenceEdit {
                    background:#ffffff;
                    color:#22252b;
                    border:1px solid #cfd7e5;
                    border-radius:0px;
                    padding:3px 6px;
                    selection-background-color:#dbeafe;
                    selection-color:#111827;
                }
                QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QFontComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QKeySequenceEdit:focus {
                    border:1px solid #8fb4e8;
                    background:#ffffff;
                }
QCheckBox, QRadioButton { color:#22252b; spacing:9px; }
                QCheckBox::indicator, QRadioButton::indicator {
                    width:15px; height:15px;
                    border:1px solid #aab4c3;
                    background:#ffffff;
                    border-radius:0px;
                }
                QRadioButton::indicator { border-radius:0px; }
                QCheckBox::indicator:checked, QRadioButton::indicator:checked {
                    background:#7aa8e8;
                    border:1px solid #7aa8e8;
                }
                QPushButton {
                    background:#f8fafc;
                    color:#22252b;
                    border:1px solid #cfd7e5;
                    border-radius:0px;
                    padding:4px 10px;
                }
                QPushButton:hover { background:#edf4ff; border-color:#aac4e8; }
                QPushButton:pressed { background:#e3edf9; }
                QPushButton:disabled { background:#edf0f5; color:#9aa4b2; border-color:#dde3ec; }
                QTabWidget::pane { border:1px solid #dfe5ef; border-radius:0px; background:#ffffff; }
                QTabBar::tab {
                    background:#edf1f7;
                    color:#4b5563;
                    border:1px solid #d9e0ea;
                    border-bottom:none;
                    border-top-left-radius:10px;
                    border-top-right-radius:3px;
                    padding:4px 10px;
                }
                QTabBar::tab:selected { background:#ffffff; color:#1f232b; font-weight:700; }
                QListWidget, QTableWidget, QTreeWidget {
                    background:#ffffff;
                    color:#22252b;
                    border:1px solid #dfe5ef;
                    border-radius:0px;
                    alternate-background-color:#f7f9fd;
                    selection-background-color:#dbeafe;
                    selection-color:#111827;
                }
                QHeaderView::section {
                    background:#f1f4f9;
                    color:#374151;
                    border:0;
                    border-right:1px solid #dfe5ef;
                    padding:7px;
                }
                QScrollBar:vertical { background:#eef2f8; width:12px; margin:0; border:0; border-radius:0px; }
                QScrollBar::handle:vertical { background:#cbd5e1; min-height:30px; border-radius:0px; }
                QScrollBar::handle:vertical:hover { background:#b7c3d4; }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
                QScrollBar:horizontal { background:#eef2f8; height:12px; margin:0; border:0; border-radius:0px; }
                QScrollBar::handle:horizontal { background:#cbd5e1; min-width:30px; border-radius:0px; }
                QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }
            """
        return """
            QDialog { background:#202226; color:#f2f4f8; }
            QScrollArea { background:transparent; border:0; }
            QLabel { color:#f2f4f8; }
            QFrame#SettingsBlock {
                background:#282c33;
                border:1px solid #3b414c;
                border-radius:16px;
            }
            QFrame#SettingsItem {
                background:#24282f;
                border:1px solid #363c47;
                border-radius:14px;
            }
            QLabel#SettingsItemTitle { font-size:13px; font-weight:700; color:#ffffff; }
            QLabel#SettingsTitle, QLabel#SettingsDialogTitle { font-size:22px; font-weight:800; color:#ffffff; }
            QLabel#SettingsSectionTitle { font-size:16px; font-weight:750; color:#ffffff; }
            QLabel#SettingsDescription { color:#b5bfce; line-height:140%; }
            QLabel#SettingsPath {
                color:#c6ceda;
                background:#1f2228;
                border:1px solid #3b414c;
                border-radius:0px;
                padding:3px 6px;
            }
            QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QFontComboBox, QSpinBox, QDoubleSpinBox, QKeySequenceEdit {
                background:#1f2228;
                color:#f5f7fb;
                border:1px solid #434a56;
                border-radius:0px;
                padding:3px 6px;
                selection-background-color:#4c6f9f;
                selection-color:#ffffff;
            }
            QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QFontComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QKeySequenceEdit:focus {
                border:1px solid #7ea2d6;
                background:#222630;
            }
QCheckBox, QRadioButton { color:#f2f4f8; spacing:9px; }
            QCheckBox::indicator, QRadioButton::indicator {
                width:15px; height:15px;
                border:1px solid #6f7786;
                background:#1f2228;
                border-radius:0px;
            }
            QRadioButton::indicator { border-radius:0px; }
            QCheckBox::indicator:checked, QRadioButton::indicator:checked {
                background:#78a6e6;
                border:1px solid #78a6e6;
            }
            QPushButton {
                background:#333843;
                color:#f2f4f8;
                border:1px solid #555d6c;
                border-radius:0px;
                padding:4px 10px;
            }
            QPushButton:hover { background:#3d4654; border-color:#718098; }
            QPushButton:pressed { background:#2b303a; }
            QPushButton:disabled { background:#2a2d33; color:#858d9a; border-color:#3f4550; }
            QTabWidget::pane { border:1px solid #3b414c; border-radius:0px; background:#24282f; }
            QTabBar::tab {
                background:#2a2e36;
                color:#b5bfce;
                border:1px solid #3b414c;
                border-bottom:none;
                border-top-left-radius:10px;
                border-top-right-radius:3px;
                padding:4px 10px;
            }
            QTabBar::tab:selected { background:#333842; color:#ffffff; font-weight:700; }
            QListWidget, QTableWidget, QTreeWidget {
                background:#24282f;
                color:#f2f4f8;
                border:1px solid #3b414c;
                border-radius:0px;
                alternate-background-color:#282d35;
                selection-background-color:#3d587d;
                selection-color:#ffffff;
            }
            QHeaderView::section {
                background:#2d323b;
                color:#d7deea;
                border:0;
                border-right:1px solid #3b414c;
                padding:7px;
            }
            QScrollBar:vertical { background:#20242b; width:12px; margin:0; border:0; border-radius:0px; }
            QScrollBar::handle:vertical { background:#424a57; min-height:30px; border-radius:0px; }
            QScrollBar::handle:vertical:hover { background:#566173; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
            QScrollBar:horizontal { background:#20242b; height:12px; margin:0; border:0; border-radius:0px; }
            QScrollBar::handle:horizontal { background:#424a57; min-width:30px; border-radius:0px; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }
        """

    def _settings_block(self, title, description=None):
        block = QFrame()
        block.setObjectName("SettingsBlock")
        layout = QVBoxLayout(block)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        title_label = QLabel(self.tr_ui(title))
        title_label.setObjectName("SettingsSectionTitle")
        layout.addWidget(title_label)
        if description:
            desc = QLabel(self.tr_ui(description))
            desc.setObjectName("SettingsDescription")
            desc.setWordWrap(True)
            layout.addWidget(desc)
        return block, layout

    def _settings_row(self, label_text, widget, description=None):
        row_wrap = QWidget()
        row = QHBoxLayout(row_wrap)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        label = QLabel(self.tr_ui(label_text))
        label.setMinimumWidth(180)
        left.addWidget(label)
        if description:
            desc = QLabel(self.tr_ui(description))
            desc.setObjectName("SettingsDescription")
            desc.setWordWrap(True)
            left.addWidget(desc)
        row.addLayout(left, 1)
        row.addWidget(widget, 0)
        return row_wrap

    def _settings_button(self, text, slot):
        btn = QPushButton(self.tr_ui(text))
        btn.clicked.connect(slot)
        return btn

    def open_file_path_visibility_dialog(self):
        """로그/설정창의 실제 경로 표시 여부를 따로 조정하는 전용 설정창."""
        old_show_paths_in_log = bool(getattr(self, "show_paths_in_log", False))
        old_show_cache_paths_in_settings = bool(getattr(self, "show_cache_paths_in_settings", False))

        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr_ui("파일 경로 표시"))
        dlg.setModal(True)
        dlg.resize(680, 360)
        dlg.setStyleSheet(self.settings_dialog_style())

        root = QVBoxLayout(dlg)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel(self.tr_ui("파일 경로 표시"), dlg)
        title.setObjectName("SettingsDialogTitle")
        root.addWidget(title)

        intro = QLabel(self.tr_ui("로그와 설정창에 실제 파일 경로를 표시할지 정합니다. 기본값은 꺼짐이며, 필요한 경우에만 켜는 고급 정보입니다."), dlg)
        intro.setObjectName("SettingsDescription")
        intro.setWordWrap(True)
        root.addWidget(intro)

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)
        root.addLayout(body, 1)

        def add_toggle(title_text, description_text, checked=False):
            item = QFrame(dlg)
            item.setObjectName("SettingsItem")
            item_layout = QHBoxLayout(item)
            item_layout.setContentsMargins(12, 10, 12, 10)
            item_layout.setSpacing(12)
            text_box = QVBoxLayout()
            text_box.setContentsMargins(0, 0, 0, 0)
            text_box.setSpacing(4)
            t = QLabel(self.tr_ui(title_text), item)
            t.setObjectName("SettingsItemTitle")
            text_box.addWidget(t)
            d = QLabel(self.tr_ui(description_text), item)
            d.setObjectName("SettingsDescription")
            d.setWordWrap(True)
            text_box.addWidget(d)
            item_layout.addLayout(text_box, 1)
            cb = QCheckBox(self.tr_ui("표시"), item)
            cb.setChecked(bool(checked))
            item_layout.addWidget(cb, 0)
            body.addWidget(item)
            return cb

        cb_show_paths_log = add_toggle(
            "로그창에 파일 위치 및 경로 표시",
            "로그에 저장 위치, 출력 위치, 작업 폴더 같은 실제 파일 경로를 함께 표시합니다. 끄면 완료/실패 같은 결과 문구만 표시합니다.",
            old_show_paths_in_log,
        )
        cb_show_cache_paths = add_toggle(
            "옵션 및 설정창에 캐시 위치 경로 표시",
            "API, 단축키 같은 옵션/설정 관리창에서 실제 캐시 파일 위치를 표시합니다. 끄면 캐시 경로는 숨깁니다.",
            old_show_cache_paths_in_settings,
        )
        body.addStretch(1)

        buttons = QDialogButtonBox(dlg)
        ok_btn = buttons.addButton(self.tr_ui("확인"), QDialogButtonBox.ButtonRole.AcceptRole)
        close_btn = buttons.addButton(self.tr_ui("닫기"), QDialogButtonBox.ButtonRole.RejectRole)
        root.addWidget(buttons)

        def apply_path_visibility_changes():
            new_show_paths_in_log = bool(cb_show_paths_log.isChecked())
            new_show_cache_paths_in_settings = bool(cb_show_cache_paths.isChecked())
            self.show_paths_in_log = new_show_paths_in_log
            self.show_cache_paths_in_settings = new_show_cache_paths_in_settings
            if new_show_paths_in_log != old_show_paths_in_log:
                self.log("🧾 로그 경로 표시: ON" if new_show_paths_in_log else "🧾 로그 경로 표시: OFF")
            if new_show_cache_paths_in_settings != old_show_cache_paths_in_settings:
                self.log("🧾 설정창 캐시 경로 표시: ON" if new_show_cache_paths_in_settings else "🧾 설정창 캐시 경로 표시: OFF")
            self.save_app_options_cache()
            self.log("⚙️ " + self.tr_ui("파일 경로 표시 설정 저장 완료"))
            dlg.accept()

        ok_btn.clicked.connect(apply_path_visibility_changes)
        close_btn.clicked.connect(dlg.reject)
        dlg.exec()

    def open_settings_overview_dialog(self):
        """설정과 옵션을 한 번에 보는 통합 창.
        - 확인: 이 창에서 직접 바꾼 설정을 저장하고 닫는다.
        - 닫기/X: 이 창에서 직접 바꾼 설정을 저장하지 않고 닫는다.
        - 복잡한 옵션은 각 전용 관리창의 확인/닫기 규칙을 따른다.
        """
        old_auto_save = bool(getattr(self, "auto_save_enabled", False))
        old_theme = str(getattr(self, "ui_theme", THEME_DARK) or THEME_DARK)
        old_language = normalize_ui_language(getattr(self, "ui_language", LANG_KO))
        old_temp_enabled = self.is_temp_auto_cleanup_enabled()
        old_temp_days = self.get_temp_auto_cleanup_days()
        old_page_tab_display = normalize_page_display_mode(getattr(self, "page_tab_display_name_mode", DEFAULT_PAGE_DISPLAY_MODE))
        old_output_display = normalize_page_display_mode(getattr(self, "output_display_name_mode", DEFAULT_PAGE_DISPLAY_MODE))
        old_show_paths_in_log = bool(getattr(self, "show_paths_in_log", False))
        old_show_cache_paths_in_settings = bool(getattr(self, "show_cache_paths_in_settings", False))

        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr_ui("설정 / 옵션"))
        dlg.setModal(True)
        dlg.resize(820, 760)
        dlg.setStyleSheet(self.settings_dialog_style())

        root = QVBoxLayout(dlg)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel(self.tr_ui("설정 / 옵션"))
        title.setObjectName("SettingsDialogTitle")
        root.addWidget(title)

        intro = QLabel(self.tr_ui("확인을 누르면 이 창에서 바꾼 설정이 저장됩니다. 닫기나 X를 누르면 이 창에서 바꾼 설정은 저장하지 않습니다. 복잡한 항목은 오른쪽 버튼으로 전용 관리창을 엽니다."))
        intro.setObjectName("SettingsDescription")
        intro.setWordWrap(True)
        root.addWidget(intro)

        scroll = QScrollArea(dlg)
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(12)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        def make_action_button(text, slot):
            btn = QPushButton(self.tr_ui(text), dlg)
            btn.setMinimumWidth(150)
            btn.clicked.connect(slot)
            return btn

        def add_item(layout, title_text, description_text, control_widget=None, button_text=None, button_slot=None):
            item = QFrame(dlg)
            item.setObjectName("SettingsItem")
            item_layout = QHBoxLayout(item)
            item_layout.setContentsMargins(12, 10, 12, 10)
            item_layout.setSpacing(12)
            text_box = QVBoxLayout()
            text_box.setContentsMargins(0, 0, 0, 0)
            text_box.setSpacing(4)
            t = QLabel(self.tr_ui(title_text), item)
            t.setObjectName("SettingsItemTitle")
            text_box.addWidget(t)
            d = QLabel(self.tr_ui(description_text), item)
            d.setObjectName("SettingsDescription")
            d.setWordWrap(True)
            text_box.addWidget(d)
            item_layout.addLayout(text_box, 1)
            if control_widget is not None:
                item_layout.addWidget(control_widget, 0)
            if button_text and button_slot:
                item_layout.addWidget(make_action_button(button_text, button_slot), 0)
            layout.addWidget(item)
            return item

        # 설정 섹션
        settings_block, settings_layout = self._settings_block(
            "설정",
            "프로그램의 기본 동작과 작업 환경을 정하는 항목입니다. 여기서 직접 바꾼 값은 확인을 눌러야 저장됩니다.",
        )

        cb_auto = QCheckBox(self.tr_ui("자동저장 모드"), dlg)
        cb_auto.setChecked(old_auto_save)
        add_item(
            settings_layout,
            "자동저장 모드",
            "ON이면 변경 사항을 실제 프로젝트에 바로 저장합니다. OFF이면 임시 작업 캐시에 먼저 저장하고, 프로젝트 저장 시 확정합니다.",
            cb_auto,
        )

        combo_theme = QComboBox(dlg)
        combo_theme.addItem(self.tr_ui("다크 테마"), THEME_DARK)
        combo_theme.addItem(self.tr_ui("화이트 테마"), THEME_LIGHT)
        combo_theme.setCurrentIndex(1 if old_theme == THEME_LIGHT else 0)
        add_item(
            settings_layout,
            "테마 설정",
            "프로그램 전체의 밝기 테마를 정합니다. 확인을 누르면 선택한 테마가 적용됩니다.",
            combo_theme,
        )

        combo_lang = QComboBox(dlg)
        combo_lang.addItem(self.tr_ui("한국어"), LANG_KO)
        combo_lang.addItem("English", LANG_EN)
        combo_lang.setCurrentIndex(1 if old_language == LANG_EN else 0)
        add_item(
            settings_layout,
            "언어 설정",
            "메뉴와 안내 문구의 표시 언어를 정합니다. 확인을 누르면 선택한 언어가 적용됩니다.",
            combo_lang,
        )

        cb_show_paths_log = QCheckBox(self.tr_ui("표시"), dlg)
        cb_show_paths_log.setChecked(old_show_paths_in_log)
        add_item(
            settings_layout,
            "로그창에 파일 위치 및 경로 표시",
            "로그에 저장 위치, 출력 위치, 작업 폴더 같은 실제 파일 경로를 함께 표시합니다. 끄면 완료/실패 같은 결과 문구만 표시합니다.",
            cb_show_paths_log,
        )

        cb_show_cache_paths = QCheckBox(self.tr_ui("표시"), dlg)
        cb_show_cache_paths.setChecked(old_show_cache_paths_in_settings)
        add_item(
            settings_layout,
            "옵션 및 설정창에 캐시 위치 경로 표시",
            "API, 단축키 같은 옵션/설정 관리창에서 실제 캐시 파일 위치를 표시합니다. 끄면 캐시 경로는 숨깁니다.",
            cb_show_cache_paths,
        )

        def fill_page_name_combo(combo, current_value):
            choices = [
                ("원본 파일명", PAGE_DISPLAY_MODE_ORIGINAL),
                ("1p_원본 파일명", PAGE_DISPLAY_MODE_PAGE_ORIGINAL),
                ("page001", PAGE_DISPLAY_MODE_PAGE_NUMBER),
            ]
            current_value = normalize_page_display_mode(current_value)
            for label, value in choices:
                combo.addItem(self.tr_ui(label), value)
                if value == current_value:
                    combo.setCurrentIndex(combo.count() - 1)

        combo_page_tab_name = QComboBox(dlg)
        fill_page_name_combo(combo_page_tab_name, old_page_tab_display)
        add_item(
            settings_layout,
            "페이지 탭 표시명",
            "좌측 이미지 작업창 상단의 페이지 탭에 표시할 이름 형식을 정합니다. 기본값은 1p_원본 파일명입니다.",
            combo_page_tab_name,
        )

        combo_output_name = QComboBox(dlg)
        fill_page_name_combo(combo_output_name, old_output_display)
        add_item(
            settings_layout,
            "출력 표시명",
            "결과물, 클린 이미지, 포토샵 스크립트 파일명에 사용할 페이지 이름 형식을 정합니다. 기본값은 1p_원본 파일명입니다.",
            combo_output_name,
        )

        workspace_widget = QWidget(dlg)
        workspace_row = QHBoxLayout(workspace_widget)
        workspace_row.setContentsMargins(0, 0, 0, 0)
        workspace_row.setSpacing(8)
        try:
            old_workspace_root = Path(load_workspace_config().get("workspace_root") or get_workspace_root())
        except Exception:
            old_workspace_root = Path(str(get_workspace_root()))
        workspace_target = {"path": old_workspace_root}
        workspace_label = QLabel(str(old_workspace_root), workspace_widget)
        workspace_label.setObjectName("SettingsPath")
        workspace_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        workspace_row.addWidget(workspace_label, 1)
        def change_workspace_from_dialog():
            # 통합 설정창에서는 개별 작업 폴더 설정창을 다시 띄우지 않는다.
            # 여기서는 경로값만 바꾸고, 실제 저장/재기동 확인은 통합 설정창의 [확인]에서 처리한다.
            current = str(workspace_target.get("path") or old_workspace_root)
            selected = QFileDialog.getExistingDirectory(dlg, self.tr_ui("작업 폴더 위치 선택"), current)
            if selected:
                try:
                    target = normalize_workspace_root_from_user(selected)
                except Exception:
                    QMessageBox.warning(dlg, self.tr_ui("경로 오류"), self.tr_ui("작업 폴더 경로가 올바르지 않습니다."))
                    return
                workspace_target["path"] = target
                workspace_label.setText(str(target))
        btn_change_workspace = QPushButton(self.tr_ui("위치 변경"), workspace_widget)
        btn_change_workspace.clicked.connect(change_workspace_from_dialog)
        workspace_row.addWidget(btn_change_workspace)
        def reset_workspace_from_dialog():
            # 즉시 저장하지 않고 표시값만 기본값으로 되돌린다.
            # [확인]에서 재기동을 승인해야 실제 적용된다.
            target = default_workspace_root()
            workspace_target["path"] = target
            workspace_label.setText(str(target))
        btn_reset_workspace = QPushButton(self.tr_ui("기본값으로\n변경"), workspace_widget)
        btn_reset_workspace.setToolTip(self.tr_ui("Windows 실제 문서 폴더 아래 YSB_Translator로 되돌립니다."))
        btn_reset_workspace.clicked.connect(reset_workspace_from_dialog)
        workspace_row.addWidget(btn_reset_workspace)
        add_item(
            settings_layout,
            "작업 폴더 위치",
            "프로젝트 작업 폴더와 캐시가 저장되는 기준 위치입니다. 위치를 바꾸면 프로그램을 재기동해야 적용됩니다. 취소하면 이전 작업 폴더 위치값으로 원복됩니다. 기본값은 Windows 실제 문서 폴더 아래 YSB_Translator입니다.",
            workspace_widget,
        )

        temp_widget = QWidget(dlg)
        temp_row = QHBoxLayout(temp_widget)
        temp_row.setContentsMargins(0, 0, 0, 0)
        temp_row.setSpacing(8)
        cb_temp_auto = QCheckBox(self.tr_ui("자동삭제"), temp_widget)
        cb_temp_auto.setChecked(old_temp_enabled)
        combo_days = QComboBox(temp_widget)
        for days, label in self.temp_cleanup_period_options():
            combo_days.addItem(self.tr_ui(label), days)
            if days == old_temp_days:
                combo_days.setCurrentIndex(combo_days.count() - 1)
        combo_days.setEnabled(cb_temp_auto.isChecked())
        cb_temp_auto.toggled.connect(lambda checked: combo_days.setEnabled(bool(checked)))
        temp_row.addWidget(cb_temp_auto)
        temp_row.addWidget(combo_days)
        add_item(
            settings_layout,
            "임시 파일 관리",
            "오래된 임시 작업 폴더를 자동으로 정리할지 정합니다. 즉시 삭제는 별도 확인 후 바로 실행됩니다.",
            temp_widget,
            "지금 정리",
            lambda: self.delete_temp_files_now(dlg),
        )

        add_item(
            settings_layout,
            "YSBT 파일 연결 등록",
            ".ysbt 파일을 더블클릭했을 때 현재 역식붕이 툴로 바로 열리게 Windows 연결을 등록합니다.",
            None,
            "등록",
            self.register_ysb_file_association,
        )
        add_item(
            settings_layout,
            "YSBT 파일 연결 해제",
            "현재 사용자 계정의 .ysbt 연결을 해제합니다. 이전 테스트용 .ysb 연결도 함께 정리합니다.",
            None,
            "해제",
            self.unregister_ysbt_file_association,
        )

        body_layout.addWidget(settings_block)

        # 옵션 섹션
        options_block, options_layout = self._settings_block(
            "옵션",
            "작업 기능을 관리하는 항목입니다. 이 창 안에 전부 펼치면 복잡해지므로, 각 항목의 버튼으로 기존 전용 관리창을 엽니다.",
        )
        option_items = [
            (
                "API 관리",
                "OpenAI, DeepSeek, OpenAI 호환 서버, 인페인팅 API 같은 외부 API 주소와 키, 모델명을 관리합니다. 유료 API 정보가 들어갈 수 있으니 저장 전 확인이 필요합니다.",
                "관리",
                self.open_api_settings_dialog,
            ),
            (
                "번역 프롬프트 입력",
                "AI 번역에 사용할 기본 지침을 편집합니다. 작품 말투, 번역 규칙, 금지 표현 같은 지시문을 이곳에서 관리합니다.",
                "편집",
                self.open_translation_prompt_dialog,
            ),
            (
                "단어장",
                "반복해서 나오는 이름, 고유명사, 말투 규칙, 번역 고정어를 관리합니다. 번역 품질을 일정하게 유지하는 데 쓰입니다.",
                "관리",
                self.open_glossary_dialog,
            ),
            (
                "분석 마스크 확장 비율",
                "OCR/분석 결과로 만들어지는 마스크의 여유 범위와 최소 확장 크기를 조절합니다. 최소 확장 크기를 0px로 두면 강제 최소 확장을 사용하지 않습니다.",
                "설정",
                self.open_analysis_mask_settings_dialog,
            ),
            (
                "단축키 통합 관리",
                "작업, 일괄 처리, 텍스트 입력, 옵션 기능에 연결된 단축키를 한곳에서 바꿉니다. 충돌 확인과 비활성화도 여기서 처리합니다.",
                "관리",
                self.open_shortcut_settings_dialog,
            ),
            (
                "매크로 관리",
                "여러 작업을 하나의 사용자 단축키로 묶어 실행하는 매크로를 관리합니다. 반복 작업을 줄이는 자동화용 기능입니다.",
                "관리",
                self.open_macro_settings_dialog,
            ),
            (
                "페이지 글꼴 프리셋 관리",
                "현재 페이지 또는 전체 페이지에 적용할 글꼴 스타일 묶음을 관리합니다. 페이지 단위 식질 스타일을 빠르게 맞출 때 사용합니다.",
                "관리",
                self.open_text_preset_dialog,
            ),
            (
                "개별 글꼴 프리셋 관리",
                "선택한 텍스트 박스 하나에 적용할 글꼴, 크기, 테두리, 색상 같은 개별 스타일 프리셋을 관리합니다.",
                "관리",
                self.open_item_text_preset_dialog,
            ),
        ]
        for title_text, desc_text, btn_text, slot in option_items:
            add_item(options_layout, title_text, desc_text, None, btn_text, slot)

        body_layout.addWidget(options_block)
        body_layout.addStretch(1)

        save_applied = {"ok": False, "restart": False}

        def apply_settings_overview_changes():
            new_auto_save = bool(cb_auto.isChecked())
            new_theme = str(combo_theme.currentData() or THEME_DARK)
            if new_theme not in (THEME_DARK, THEME_LIGHT):
                new_theme = THEME_DARK
            new_language = normalize_ui_language(combo_lang.currentData())
            new_temp_enabled = bool(cb_temp_auto.isChecked())
            new_temp_days = int(combo_days.currentData() or old_temp_days or 7)
            new_page_tab_display = normalize_page_display_mode(combo_page_tab_name.currentData())
            new_output_display = normalize_page_display_mode(combo_output_name.currentData())
            new_show_paths_in_log = bool(cb_show_paths_log.isChecked())
            new_show_cache_paths_in_settings = bool(cb_show_cache_paths.isChecked())

            # 확인 → 저장 확인에서 예를 누른 뒤에만 실제 저장/적용한다.
            if new_theme != old_theme:
                self.ui_theme = new_theme
                self.apply_theme(new_theme)
            if new_language != old_language:
                self.ui_language = new_language
                self.apply_language(new_language)
            if new_temp_enabled != old_temp_enabled or new_temp_days != old_temp_days:
                self.set_temp_cleanup_options(new_temp_enabled, new_temp_days)
                self.log(f"🧹 임시 파일 자동삭제 설정: {'ON' if new_temp_enabled else 'OFF'} / {new_temp_days}일")
            display_changed = (new_page_tab_display != old_page_tab_display) or (new_output_display != old_output_display)
            self.page_tab_display_name_mode = new_page_tab_display
            self.output_display_name_mode = new_output_display
            if new_page_tab_display != old_page_tab_display:
                self.refresh_page_tabs()
                self.log(f"📑 페이지 탭 표시명 설정: {new_page_tab_display}")
            if new_output_display != old_output_display:
                self.log(f"📤 출력 표시명 설정: {new_output_display}")
            path_visibility_changed = (new_show_paths_in_log != old_show_paths_in_log) or (new_show_cache_paths_in_settings != old_show_cache_paths_in_settings)
            self.show_paths_in_log = new_show_paths_in_log
            self.show_cache_paths_in_settings = new_show_cache_paths_in_settings
            if new_show_paths_in_log != old_show_paths_in_log:
                self.log("🧾 로그 경로 표시: ON" if new_show_paths_in_log else "🧾 로그 경로 표시: OFF")
            if new_show_cache_paths_in_settings != old_show_cache_paths_in_settings:
                self.log("🧾 설정창 캐시 경로 표시: ON" if new_show_cache_paths_in_settings else "🧾 설정창 캐시 경로 표시: OFF")
            if new_auto_save != old_auto_save:
                try:
                    self.act_auto_save_mode.blockSignals(True)
                    self.act_auto_save_mode.setChecked(new_auto_save)
                    self.act_auto_save_mode.blockSignals(False)
                except Exception:
                    pass
                self.toggle_auto_save_mode(new_auto_save)
            else:
                self.save_app_options_cache()
            if (display_changed or path_visibility_changed) and new_auto_save == old_auto_save:
                self.save_app_options_cache()
            self.log("⚙️ 설정 / 옵션 저장 완료")
            save_applied["ok"] = True

        def on_settings_overview_ok():
            # 설정창은 닫지 않은 상태에서 먼저 저장 여부를 묻는다.
            # 아니오(N)를 누르면 설정창으로 돌아가 다시 조작할 수 있다.
            if not self.ask_yes_no_shortcut(
                "설정 저장",
                "이 창에서 바꾼 설정을 저장할까요?",
                yes_text="저장",
                no_text="취소",
                default_yes=True,
                icon=QMessageBox.Icon.Question,
                parent=dlg,
            ):
                self.log("⚙️ 설정 / 옵션 저장 취소")
                return

            try:
                current_workspace = Path(old_workspace_root).resolve()
                target_workspace = Path(workspace_target.get("path") or old_workspace_root).resolve()
            except Exception:
                current_workspace = Path(str(old_workspace_root))
                target_workspace = Path(str(workspace_target.get("path") or old_workspace_root))

            workspace_changed = current_workspace != target_workspace
            if workspace_changed:
                if not workspace_restart_confirmation(dlg, current_workspace, target_workspace, self.ui_language):
                    # 재기동을 취소하면 설정창은 그대로 두고 작업 폴더 표시값만 이전값으로 원복한다.
                    workspace_target["path"] = old_workspace_root
                    workspace_label.setText(str(old_workspace_root))
                    self.log("📁 작업 폴더 위치 변경 취소")
                    return
                try:
                    apply_settings_overview_changes()
                    schedule_workspace_root_change(target_workspace)
                    save_applied["restart"] = True
                    self.log(f"📁 작업 폴더 위치 변경 예약 및 재기동: {target_workspace}")
                    dlg.accept()
                    restart_application_detached()
                    return
                except Exception as e:
                    QMessageBox.critical(dlg, self.tr_ui("저장 실패"), f"{self.tr_ui('작업 폴더 위치를 변경하지 못했습니다.')}\n{e}")
                    workspace_target["path"] = old_workspace_root
                    workspace_label.setText(str(old_workspace_root))
                    return

            apply_settings_overview_changes()
            dlg.accept()

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dlg)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr_ui("확인"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(self.tr_ui("닫기"))
        btns.accepted.connect(on_settings_overview_ok)
        btns.rejected.connect(dlg.reject)
        root.addWidget(btns)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            self.log("⚙️ 설정 / 옵션 변경 취소")
            return

        if save_applied.get("ok") and not save_applied.get("restart"):
            self.show_ok_notice("설정 저장 완료", "설정이 저장되었습니다.")

    def open_analysis_mask_settings_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr_ui("분석 마스크 확장 비율"))
        dlg.resize(660, 500)
        dlg.setStyleSheet(self.settings_dialog_style())
        root = QVBoxLayout(dlg)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        title = QLabel(self.tr_ui("분석 마스크 확장 비율"), dlg)
        title.setObjectName("SettingsTitle")
        root.addWidget(title)

        desc = QLabel(self.tr_ui("OCR/분석 결과로 만들어지는 마스크의 여유 범위와 최소 확장 크기를 조절합니다. 최소 확장 크기를 0px로 두면 강제 최소 확장을 사용하지 않습니다."), dlg)
        desc.setObjectName("SettingsDescription")
        desc.setWordWrap(True)
        root.addWidget(desc)

        form_box = QFrame(dlg)
        form_box.setObjectName("SettingsItem")
        form_layout = QVBoxLayout(form_box)
        form_layout.setContentsMargins(12, 12, 12, 12)
        form_layout.setSpacing(12)

        old_text_ratio = clamp_analysis_mask_ratio(
            self.app_options.get(ANALYSIS_TEXT_MASK_EXPAND_RATIO_KEY, DEFAULT_ANALYSIS_TEXT_MASK_EXPAND_RATIO),
            DEFAULT_ANALYSIS_TEXT_MASK_EXPAND_RATIO,
        )
        old_paint_ratio = clamp_analysis_mask_ratio(
            self.app_options.get(ANALYSIS_PAINT_MASK_EXPAND_RATIO_KEY, DEFAULT_ANALYSIS_PAINT_MASK_EXPAND_RATIO),
            DEFAULT_ANALYSIS_PAINT_MASK_EXPAND_RATIO,
        )
        old_text_min_px = clamp_analysis_mask_min_px(
            self.app_options.get(ANALYSIS_TEXT_MASK_MIN_EXPAND_PX_KEY, DEFAULT_ANALYSIS_TEXT_MASK_MIN_EXPAND_PX),
            DEFAULT_ANALYSIS_TEXT_MASK_MIN_EXPAND_PX,
        )
        old_paint_min_px = clamp_analysis_mask_min_px(
            self.app_options.get(ANALYSIS_PAINT_MASK_MIN_EXPAND_PX_KEY, DEFAULT_ANALYSIS_PAINT_MASK_MIN_EXPAND_PX),
            DEFAULT_ANALYSIS_PAINT_MASK_MIN_EXPAND_PX,
        )

        def make_ratio_spin(value):
            spin = QDoubleSpinBox(dlg)
            spin.setRange(0.00, 2.00)
            spin.setDecimals(2)
            spin.setSingleStep(0.05)
            spin.setValue(float(value))
            spin.setSuffix(" x")
            spin.setMinimumWidth(120)
            return spin

        def make_px_spin(value):
            spin = QSpinBox(dlg)
            spin.setRange(0, 100)
            spin.setSingleStep(1)
            spin.setValue(int(value))
            spin.setSuffix(" px")
            spin.setMinimumWidth(120)
            return spin

        def add_setting_row(title_text, description_text, editor):
            row = QHBoxLayout()
            text_box = QVBoxLayout()
            text_box.setContentsMargins(0, 0, 0, 0)
            item_title = QLabel(self.tr_ui(title_text), dlg)
            item_title.setObjectName("SettingsItemTitle")
            item_desc = QLabel(self.tr_ui(description_text), dlg)
            item_desc.setObjectName("SettingsDescription")
            item_desc.setWordWrap(True)
            text_box.addWidget(item_title)
            text_box.addWidget(item_desc)
            row.addLayout(text_box, 1)
            row.addWidget(editor, 0)
            form_layout.addLayout(row)

        spin_text = make_ratio_spin(old_text_ratio)
        add_setting_row(
            "텍스트 마스크 확장 비율",
            "분석 결과의 텍스트 마스크를 묶고 확장하는 비율입니다. 말풍선 글자 테두리가 덜 잡히면 이 값을 올리세요.",
            spin_text,
        )

        spin_text_min = make_px_spin(old_text_min_px)
        add_setting_row(
            "텍스트 마스크 최소 확장 크기",
            "텍스트 마스크를 만들 때 비율 계산값이 작아도 최소로 확장할 픽셀 크기입니다. 0px이면 최소 확장 강제를 사용하지 않습니다.",
            spin_text_min,
        )

        line = QFrame(dlg)
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        form_layout.addWidget(line)

        spin_paint = make_ratio_spin(old_paint_ratio)
        add_setting_row(
            "페인트 마스크 확장 비율",
            "인페인팅/페인트 마스크를 만들 때 글자 주변을 얼마나 여유 있게 지울지 정합니다. 배경까지 너무 많이 잡히면 이 값을 낮추세요.",
            spin_paint,
        )

        spin_paint_min = make_px_spin(old_paint_min_px)
        add_setting_row(
            "페인트 마스크 최소 확장 크기",
            "페인트 마스크를 만들 때 비율 계산값이 작아도 최소로 확장할 픽셀 크기입니다. 0px이면 최소 확장 강제를 사용하지 않습니다.",
            spin_paint_min,
        )

        reset_row = QHBoxLayout()
        reset_row.addStretch(1)
        btn_reset = QPushButton(self.tr_ui("기본값으로 돌아가기"), dlg)
        reset_row.addWidget(btn_reset)
        form_layout.addLayout(reset_row)

        def reset_defaults():
            spin_text.setValue(DEFAULT_ANALYSIS_TEXT_MASK_EXPAND_RATIO)
            spin_text_min.setValue(DEFAULT_ANALYSIS_TEXT_MASK_MIN_EXPAND_PX)
            spin_paint.setValue(DEFAULT_ANALYSIS_PAINT_MASK_EXPAND_RATIO)
            spin_paint_min.setValue(DEFAULT_ANALYSIS_PAINT_MASK_MIN_EXPAND_PX)

        btn_reset.clicked.connect(reset_defaults)
        root.addWidget(form_box)
        root.addStretch(1)

        save_applied = {"ok": False, "restart": False}

        def apply_changes():
            text_ratio = clamp_analysis_mask_ratio(spin_text.value(), DEFAULT_ANALYSIS_TEXT_MASK_EXPAND_RATIO)
            paint_ratio = clamp_analysis_mask_ratio(spin_paint.value(), DEFAULT_ANALYSIS_PAINT_MASK_EXPAND_RATIO)
            text_min_px = clamp_analysis_mask_min_px(spin_text_min.value(), DEFAULT_ANALYSIS_TEXT_MASK_MIN_EXPAND_PX)
            paint_min_px = clamp_analysis_mask_min_px(spin_paint_min.value(), DEFAULT_ANALYSIS_PAINT_MASK_MIN_EXPAND_PX)
            self.app_options[ANALYSIS_TEXT_MASK_EXPAND_RATIO_KEY] = text_ratio
            self.app_options[ANALYSIS_PAINT_MASK_EXPAND_RATIO_KEY] = paint_ratio
            self.app_options[ANALYSIS_TEXT_MASK_MIN_EXPAND_PX_KEY] = text_min_px
            self.app_options[ANALYSIS_PAINT_MASK_MIN_EXPAND_PX_KEY] = paint_min_px
            self.sync_analysis_mask_options_to_config()
            self.save_app_options_cache()
            self.log(f"🎭 분석 마스크 확장 설정 저장: 텍스트 {text_ratio:.2f}/{text_min_px}px, 페인트 {paint_ratio:.2f}/{paint_min_px}px")
            save_applied["ok"] = True

        def on_ok():
            if not self.ask_yes_no_shortcut(
                "분석 마스크 설정 저장",
                "분석 마스크 확장 설정을 저장할까요?",
                yes_text="저장",
                no_text="취소",
                default_yes=True,
                icon=QMessageBox.Icon.Question,
                parent=dlg,
            ):
                self.log("🎭 분석 마스크 확장 설정 저장 취소")
                return
            apply_changes()
            dlg.accept()

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dlg)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr_ui("확인"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(self.tr_ui("닫기"))
        btns.accepted.connect(on_ok)
        btns.rejected.connect(dlg.reject)
        root.addWidget(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted and save_applied.get("ok"):
            self.show_ok_notice("분석 마스크 설정 저장 완료", "분석 마스크 확장 설정이 저장되었습니다.")

    def open_launcher_options_menu(self):
        menu = QMenu(self)
        menu.addAction(self.actions["option_theme_settings"])
        menu.addAction(self.actions["option_language_settings"])
        menu.addSeparator()
        menu.addAction(self.actions["option_api_settings"])
        menu.addAction(self.actions["option_translation_prompt"])
        menu.addAction(self.actions["option_glossary"])
        menu.addAction(self.actions["option_analysis_mask_settings"])
        menu.addAction(self.actions["option_ocr_analysis_regions"])
        menu.addSeparator()
        menu.addAction(self.actions["option_shortcut_settings"])
        menu.addAction(self.actions["option_macro_settings"])
        menu.exec(QCursor.pos())

    def open_launcher_help(self):
        QMessageBox.information(
            self,
            self.tr_ui("도움말 / 매뉴얼"),
            self.tr_ui("런처 화면에서는 새 프로젝트, 프로젝트 열기, 마지막 작업 복구, 최근 프로젝트 열기를 바로 사용할 수 있습니다."),
        )

    def open_about_dialog(self):
        """도움말 > 프로그램 정보."""
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr_ui("프로그램 정보"))
        dialog.resize(500, 280)

        layout = QVBoxLayout(dialog)

        title = QLabel(self.tr_ui("YSB Translator Tool / 역식붕이 툴"))
        title.setStyleSheet("font-size:18px;font-weight:bold;")
        layout.addWidget(title)

        try:
            version = str(APP_VERSION)
        except Exception:
            version = "unknown"

        info = QLabel(
            self.tr_ui("버전") + f" {version}\n"
            "© 2026 amule949\n"
            "Support Email: ysbtool.support@gmail.com\n\n"
            "GNU General Public License v3.0\n"
            + self.tr_ui("자세한 내용은 LICENSE 및 TRADEMARKS.md를 참고하세요.")
        )
        info.setWordWrap(True)
        info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(info)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, dialog)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr_ui("확인"))
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)

        try:
            dialog.setStyleSheet(self.settings_dialog_style())
        except Exception:
            try:
                dialog.setStyleSheet(self.message_box_style())
            except Exception:
                pass

        dialog.exec()

    def setup_project_exit_button(self, menubar):
        """작업 화면 우측 상단에 프로젝트를 닫고 홈으로 나가는 버튼을 둔다."""
        try:
            btn = QToolButton(self)
            self.btn_project_exit = btn
            btn.setText(self.tr_ui("프로젝트 나가기"))
            btn.setToolTip(self.tr_ui("프로젝트 나가기"))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setAutoRaise(False)
            btn.setFixedHeight(26)
            btn.setMinimumWidth(118)
            btn.clicked.connect(lambda: self.actions["project_exit"].trigger() if hasattr(self, "actions") and "project_exit" in self.actions else self.show_launcher())
            self.apply_project_exit_button_theme()
            menubar.setCornerWidget(btn, Qt.Corner.TopRightCorner)
            self.update_project_exit_button_visibility()
        except Exception:
            pass

    def apply_project_exit_button_theme(self):
        """프로젝트 나가기 버튼도 현재 테마 팔레트를 따라가게 한다."""
        try:
            btn = getattr(self, "btn_project_exit", None)
            if btn is None:
                return
            if self.is_light_theme():
                btn.setStyleSheet(
                    "QToolButton { "
                    "background:#f8fafc; color:#22252b; border:1px solid #cfd7e5; "
                    "border-radius:0px; padding:3px 10px; font-weight:700; "
                    "}"
                    "QToolButton:hover { background:#edf4ff; border-color:#aac4e8; color:#111827; }"
                    "QToolButton:pressed { background:#dbeafe; border-color:#8fb4e8; }"
                    "QToolButton:disabled { background:#edf1f7; color:#9aa4b2; border-color:#dfe5ef; }"
                )
            else:
                btn.setStyleSheet(
                    "QToolButton { "
                    "background:#333843; color:#f2f4f8; border:1px solid #555d6c; "
                    "border-radius:0px; padding:3px 10px; font-weight:700; "
                    "}"
                    "QToolButton:hover { background:#3d587d; border-color:#7ea2d6; color:#ffffff; }"
                    "QToolButton:pressed { background:#26384f; border-color:#5f83b5; }"
                    "QToolButton:disabled { background:#2a2f38; color:#7d8594; border-color:#3b414c; }"
                )
            btn.update()
        except Exception:
            pass

    def update_project_exit_button_visibility(self):
        try:
            btn = getattr(self, "btn_project_exit", None)
            if btn is None:
                return
            in_editor = False
            try:
                in_editor = bool(
                    hasattr(self, "main_stack")
                    and hasattr(self, "editor_widget")
                    and self.main_stack.currentWidget() is self.editor_widget
                )
            except Exception:
                in_editor = False
            btn.setVisible(bool(in_editor and self.has_open_project()))
            btn.setEnabled(bool(in_editor and self.has_open_project()))
        except Exception:
            pass

    def setup_menu(self):
        menubar = self.menuBar()

        project_menu = menubar.addMenu(self.tr_ui("프로젝트")); self.project_menu = project_menu
        # 1. 새로 만들기 및 열기
        project_menu.addAction(self.actions["project_new"])
        project_menu.addAction(self.actions["project_import_images"])
        project_menu.addAction(self.actions["project_open"])
        project_menu.addAction(self.actions["project_open_json"])
        project_menu.addSeparator()
        # 2. 저장하기
        project_menu.addAction(self.actions["project_save"])
        project_menu.addAction(self.actions["project_save_as"])
        project_menu.addSeparator()
        # 3. 복구하기
        project_menu.addAction(self.actions["project_recover_last_work"])
        project_menu.addSeparator()
        # 4. 기타 옵션
        project_menu.addAction(self.actions["project_show_launcher"])
        project_menu.addAction(self.actions["project_exit"])
        project_menu.addAction(self.actions["option_settings_overview"])

        work_menu = menubar.addMenu(self.tr_ui("작업")); self.work_menu = work_menu
        work_menu.addSection(self.tr_ui("기본동작"))
        work_menu.addAction(self.actions["work_source_compare"])
        work_menu.addAction(self.actions["work_open_current_project_folder"])
        work_menu.addAction(self.actions["work_export"])
        work_menu.addSeparator()

        work_menu.addSection(self.tr_ui("페이지탭"))
        work_menu.addAction(self.actions["work_page_rename_source"])
        work_menu.addAction(self.actions["work_page_delete_current"])
        work_menu.addSeparator()

        work_menu.addSection(self.tr_ui("작업류"))
        work_menu.addAction(self.actions["work_analyze"])
        work_menu.addAction(self.actions["work_translate"])
        work_menu.addAction(self.actions["work_inpaint"])
        work_menu.addSeparator()

        work_menu.addSection(self.tr_ui("텍스트 수정류"))
        work_menu.addAction(self.actions["work_extract_text"])
        work_menu.addAction(self.actions["work_import_translation"])
        work_menu.addAction(self.actions["work_clear_translation"])
        work_menu.addAction(self.actions["work_clean_text"])
        work_menu.addSeparator()

        work_menu.addSection(self.tr_ui("이미지 교체류"))
        work_menu.addAction(self.actions["work_inpaint_source"])
        if "final_paint_to_background" in self.actions:
            work_menu.addAction(self.actions["final_paint_to_background"])
        work_menu.addAction(self.actions["work_restore_original_source"])
        work_menu.addSeparator()

        work_menu.addSection(self.tr_ui("기타 동작"))
        work_menu.addAction(self.actions["work_quick_ocr"])
        work_menu.addAction(self.actions["work_text_number_width"])
        work_menu.addAction(self.actions["work_reset_text_rects"])

        batch_menu = menubar.addMenu(self.tr_ui("일괄 작업")); self.batch_menu = batch_menu
        batch_menu.addSection(self.tr_ui("기본 동작"))
        batch_menu.addAction(self.actions["batch_export"])
        batch_menu.addSeparator()

        batch_menu.addSection(self.tr_ui("일괄 작업류"))
        batch_menu.addAction(self.actions["batch_analyze"])
        batch_menu.addAction(self.actions["batch_translate"])
        batch_menu.addAction(self.actions["batch_inpaint"])
        batch_menu.addSeparator()

        batch_menu.addSection(self.tr_ui("텍스트 수정류"))
        batch_menu.addAction(self.actions["batch_extract_text"])
        batch_menu.addAction(self.actions["batch_import_translation"])
        batch_menu.addAction(self.actions["batch_clear_translation"])
        batch_menu.addAction(self.actions["batch_clean_text"])
        batch_menu.addSeparator()

        batch_menu.addSection(self.tr_ui("기타 동작"))
        batch_menu.addAction(self.actions["batch_reset_text_rects"])
        if "work_page_delete_all" in self.actions:
            batch_menu.addAction(self.actions["work_page_delete_all"])

        auto_menu = menubar.addMenu(self.tr_ui("자동화 작업")); self.auto_menu = auto_menu
        auto_menu.addAction(self.actions["auto_text_size_current"])
        auto_menu.addAction(self.actions["auto_text_size_batch"])
        auto_menu.addSeparator()
        auto_menu.addAction(self.actions["auto_linebreak_current"])
        auto_menu.addAction(self.actions["auto_linebreak_batch"])

        cloud_menu = menubar.addMenu(self.tr_ui("클라우드")); self.cloud_menu = cloud_menu
        cloud_menu.addAction(self.actions["cloud_register"])
        cloud_menu.addAction(self.actions["cloud_unregister"])
        cloud_menu.addSeparator()
        cloud_menu.addAction(self.actions["cloud_cache_backup"])
        cloud_menu.addAction(self.actions["cloud_cache_restore"])
        cloud_menu.addSeparator()
        cloud_menu.addAction(self.actions["cloud_delete_backups"])

        option_menu = menubar.addMenu(self.tr_ui("옵션")); self.option_menu = option_menu
        option_menu.addAction(self.actions["option_api_settings"])
        option_menu.addAction(self.actions["option_translation_prompt"])
        option_menu.addAction(self.actions["option_glossary"])
        option_menu.addSeparator()
        option_menu.addAction(self.actions["option_shortcut_settings"])
        option_menu.addAction(self.actions["option_macro_settings"])
        option_menu.addAction(self.actions["option_text_preset_settings"])
        option_menu.addAction(self.actions["option_item_text_preset_settings"])
        option_menu.addSeparator()
        option_menu.addAction(self.actions["option_analysis_mask_settings"])
        option_menu.addAction(self.actions["option_ocr_analysis_regions"])
        option_menu.addAction(self.actions["option_cleanup_outputs"])
        settings_menu = menubar.addMenu(self.tr_ui("설정")); self.settings_menu = settings_menu
        settings_menu.addAction(self.actions["option_auto_save_mode"])
        settings_menu.addAction(self.actions["option_theme_settings"])
        settings_menu.addAction(self.actions["option_language_settings"])
        settings_menu.addAction(self.actions["setting_page_tab_display_name"])
        settings_menu.addAction(self.actions["setting_output_display_name"])
        settings_menu.addSeparator()
        settings_menu.addAction(self.actions["option_workspace_location"])
        settings_menu.addAction(self.actions["option_cleanup_temp_files"])
        settings_menu.addAction(self.actions["option_register_ysb"])
        settings_menu.addAction(self.actions["option_unregister_ysbt"])
        settings_menu.addSeparator()
        settings_menu.addAction(self.actions["setting_file_path_visibility"])

        help_menu = menubar.addMenu(self.tr_ui("도움말")); self.help_menu = help_menu
        help_menu.addAction(self.actions["help_program_manual"])
        help_menu.addAction(self.actions["help_open_website"])
        help_menu.addAction(self.actions["help_report_bug"])
        help_menu.addSeparator()
        help_menu.addAction(self.actions["help_about"])

        self.setup_project_exit_button(menubar)

    def setup_ui(self):
        self.main_stack = QStackedWidget()
        self.setCentralWidget(self.main_stack)

        self.recent_project_store = RecentProjectStore()
        self.launcher_widget = LauncherWidget(
            self.recent_project_store,
            app_version=APP_VERSION,
            lang=getattr(self, "ui_language", LANG_KO),
            theme=getattr(self, "ui_theme", THEME_DARK),
            parent=self,
        )
        self.launcher_widget.newProjectRequested.connect(self.new_empty_project_action)
        self.launcher_widget.openProjectRequested.connect(self.open_project)
        self.launcher_widget.importImagesRequested.connect(self.import_images_action)
        self.launcher_widget.recoverRequested.connect(self.recover_last_work_project)
        self.launcher_widget.cloudRequested.connect(lambda: self.open_cloud_overview_dialog(include_project_backup=False))
        self.launcher_widget.optionsRequested.connect(self.open_settings_overview_dialog)
        self.launcher_widget.helpRequested.connect(self.open_launcher_help)
        self.launcher_widget.recentProjectOpenRequested.connect(self.confirm_open_recent_project)
        self.launcher_widget.recentProjectRemoveRequested.connect(self.remove_recent_project_from_launcher)
        self.launcher_widget.recentProjectRevealRequested.connect(self.reveal_recent_project_in_folder)
        self.main_stack.addWidget(self.launcher_widget)

        w = QWidget()
        self.editor_widget = w
        self.main_stack.addWidget(w)
        self.main_stack.setCurrentWidget(self.launcher_widget)
        lay = QHBoxLayout(w)
        split = EditorSplitter(Qt.Orientation.Horizontal, default_right_width=700)
        self.editor_splitter = split
        split.setHandleWidth(8)
        lay.addWidget(split)

        # Left Panel
        lp = QWidget()
        lp.setMinimumWidth(0)
        lp.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        ll = QHBoxLayout(lp)
        ll.setContentsMargins(0, 0, 0, 0)

        self.view = MuleImageViewer(self)
        self.view.scene.selectionChanged.connect(self.on_scene_selection_changed)
        try:
            self.view.installEventFilter(self)
            self.view.viewport().installEventFilter(self)
            self.view.viewport().setMouseTracking(True)
        except Exception:
            pass

        tb = QToolBar(orientation=Qt.Orientation.Vertical)
        tb.setStyleSheet("background:#24282f; border:1px solid #3b414c; border-radius:0px;")
        self.act_brush = QAction("🖌️", self, triggered=lambda: self.set_tool('draw'))
        tb.addAction(self.act_brush)
        self.act_erase = QAction("🧼", self, triggered=lambda: self.set_tool('erase'))
        tb.addAction(self.act_erase)

        self.act_reanal = QAction("🔄", self)
        self.act_reanal.triggered.connect(self.reanalyze_mask)
        tb.addAction(self.act_reanal)


        self.act_magic = QAction("⭐", self)
        self.act_magic.triggered.connect(lambda *args: self.set_tool('magic_wand'))
        tb.addAction(self.act_magic)
        try:
            _magic_btn = tb.widgetForAction(self.act_magic)
            if _magic_btn is not None:
                _magic_btn.setStyleSheet("font-size:18px; color:#ffd43b;")
        except Exception:
            pass

        self.act_mask_wrap = QAction("🩹", self)
        self.act_mask_wrap.triggered.connect(lambda *args: self.set_tool('mask_wrap'))
        tb.addAction(self.act_mask_wrap)

        self.act_mask_cut = QAction("🔪", self)
        self.act_mask_cut.triggered.connect(lambda *args: self.set_tool('mask_cut'))
        tb.addAction(self.act_mask_cut)

        # QCheckBox를 QToolBar에 직접 넣으면 QToolBar 레이아웃 + QCheckBox indicator가 따로 놀아
        # 다른 도구 버튼들과 여백/정렬이 맞지 않는다.
        # 그래서 다른 그림판 도구와 동일하게 checkable QAction으로 통일한다.
        self.act_mask_toggle = QAction("☐", self)
        self.act_mask_toggle.setCheckable(True)
        # QAction 자체 툴팁은 QToolBar가 즉시 표시할 수 있으므로 비워둔다.
        # 실제 안내는 register_delayed_tooltip()의 지연 툴팁 하나로만 표시한다.
        self.act_mask_toggle.setToolTip("")
        self.act_mask_toggle.setStatusTip("")
        self.act_mask_toggle.setWhatsThis("")

        self.act_mask_toggle.toggled.connect(self.on_mask_toggle_changed)
        tb.addAction(self.act_mask_toggle)

        # 기존 코드 호환용 별칭: setChecked/toggle/blockSignals/setVisible 등을 QAction이 그대로 지원한다.
        self.cb_mask_toggle = self.act_mask_toggle
        self.mask_toggle_wrap = tb.widgetForAction(self.act_mask_toggle)
        if self.mask_toggle_wrap:
            self.mask_toggle_wrap.setToolTip("")
            self.mask_toggle_wrap.setStyleSheet("")

        self.act_final_paint_color = QAction("", self)
        self.act_final_paint_color.triggered.connect(lambda *args: self.pick_color("final_paint"))
        tb.addAction(self.act_final_paint_color)

        self.act_final_area_paint = QAction("▦", self)
        self.act_final_area_paint.setToolTip("")
        self.act_final_area_paint.setStatusTip("")
        self.act_final_area_paint.setWhatsThis("")
        self.act_final_area_paint.triggered.connect(lambda *args: self.set_tool("area_paint"))
        tb.addAction(self.act_final_area_paint)
        try:
            _area_paint_widget = tb.widgetForAction(self.act_final_area_paint)
            if _area_paint_widget is not None:
                _area_paint_widget.setToolTip("")
                try:
                    _area_paint_widget.clicked.connect(lambda checked=False: self.set_tool("area_paint"))
                except Exception:
                    pass
        except Exception:
            pass

        self.act_final_text_tool = QAction("T", self)
        self.act_final_text_tool.triggered.connect(lambda *args: self.set_tool("final_text"))
        tb.addAction(self.act_final_text_tool)

        self.act_final_paint_to_bg = QAction("↧", self)
        self.act_final_paint_to_bg.triggered.connect(self.apply_final_paint_to_background)
        tb.addAction(self.act_final_paint_to_bg)

        self.act_final_paint_above_text = QAction("T↓", self)
        self.act_final_paint_above_text.setCheckable(True)
        self.act_final_paint_above_text.setChecked(False)
        self.act_final_paint_above_text.toggled.connect(self.on_final_paint_above_text_toggled)
        tb.addAction(self.act_final_paint_above_text)

        self.tb = tb
        self.tb.setFixedWidth(42)
        self.tb.setVisible(True)
        self.tb.setEnabled(False)
        ll.addWidget(tb)

        vc = QWidget()
        vl = QVBoxLayout(vc)
        vl.setContentsMargins(0, 0, 0, 0)

        self.page_tab_container = QWidget()
        self.page_tab_container.setFixedHeight(36)
        page_tab_layout = QHBoxLayout(self.page_tab_container)
        page_tab_layout.setContentsMargins(4, 3, 4, 3)
        page_tab_layout.setSpacing(6)
        self.btn_page_tab_menu = QToolButton()
        self.btn_page_tab_menu.setText("☰")
        self.btn_page_tab_menu.setToolTip(self.tr_ui("페이지 목록"))
        self.btn_page_tab_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_page_tab_menu.setFixedSize(32, 28)
        self.btn_page_tab_menu.clicked.connect(self.show_page_tab_menu)
        self.page_tab_bar = ScrollablePageTabBar(self)
        self.page_tab_bar.setExpanding(False)
        self.page_tab_bar.setDrawBase(False)
        self.page_tab_bar.setUsesScrollButtons(True)
        self.page_tab_bar.setElideMode(Qt.TextElideMode.ElideMiddle)
        self.page_tab_bar.setMovable(True)
        self.page_tab_bar.setTabsClosable(True)
        self.page_tab_bar.currentChanged.connect(self.on_page_tab_changed)
        self.page_tab_bar.tabCloseRequested.connect(self.close_page_from_tab)
        try:
            self.page_tab_bar.tabRenameRequested.connect(self.rename_page_source_from_tab)
        except Exception:
            pass
        try:
            self.page_tab_bar.tabMoved.connect(self.on_page_tab_moved)
        except Exception:
            pass

        self.btn_page_scroll_left = QToolButton()
        self.btn_page_scroll_left.setText("◀")
        self.btn_page_scroll_left.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_page_scroll_left.setFixedSize(24, 28)
        self.btn_page_scroll_left.clicked.connect(self.scroll_page_tabs_left)

        self.btn_page_scroll_right = QToolButton()
        self.btn_page_scroll_right.setText("▶")
        self.btn_page_scroll_right.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_page_scroll_right.setFixedSize(24, 28)
        self.btn_page_scroll_right.clicked.connect(self.scroll_page_tabs_right)

        self.btn_page_add = QToolButton()
        self.btn_page_add.setText("+")
        self.btn_page_add.setToolTip(self.native_tooltip_html("이미지 불러오기", self.shortcut_text_for_key("project_import_images", "Alt+O"), "현재 프로젝트에서는 현재 페이지 뒤에 이미지를 추가합니다."))
        self.btn_page_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_page_add.setFixedSize(32, 28)
        self.btn_page_add.clicked.connect(self.import_images_action)
        page_tab_layout.addWidget(self.btn_page_tab_menu, 0)
        page_tab_layout.addWidget(self.page_tab_bar, 1)
        page_tab_layout.addWidget(self.btn_page_scroll_left, 0)
        page_tab_layout.addWidget(self.btn_page_scroll_right, 0)
        page_tab_layout.addWidget(self.btn_page_add, 0)
        vl.addWidget(self.page_tab_container)
        self._refreshing_page_tabs = False
        self.apply_page_tab_style()
        self.refresh_page_tabs()

        # 상단 공유 옵션바: 도구별 옵션은 이 한 줄을 공유한다.
        # 바 자체는 항상 보이고, 선택/도구 상태에 따라 내부 내용만 교체한다.
        self.shared_option_bar = QWidget()
        self.shared_option_bar.setObjectName("SharedOptionBar")
        self.shared_option_bar_layout = QHBoxLayout(self.shared_option_bar)
        self.shared_option_bar_layout.setContentsMargins(6, 1, 6, 1)
        self.shared_option_bar_layout.setSpacing(6)
        self.shared_option_left = QWidget()
        self.shared_option_left_layout = QHBoxLayout(self.shared_option_left)
        self.shared_option_left_layout.setContentsMargins(0, 0, 0, 0)
        self.shared_option_left_layout.setSpacing(6)
        self.shared_option_right = QWidget()
        self.shared_option_right_layout = QHBoxLayout(self.shared_option_right)
        self.shared_option_right_layout.setContentsMargins(0, 0, 0, 0)
        self.shared_option_right_layout.setSpacing(6)
        self.shared_option_bar_layout.addWidget(self.shared_option_left, 0)
        self.shared_option_bar_layout.addStretch(1)
        self.shared_option_bar_layout.addWidget(self.shared_option_right, 0)
        try:
            self.shared_option_bar.setFixedHeight(30)
            self.shared_option_bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        except Exception:
            pass
        self.shared_option_bar.show()
        vl.addWidget(self.shared_option_bar)

        self.final_edit_bar = QWidget()
        final_bar = QHBoxLayout(self.final_edit_bar)
        final_bar.setContentsMargins(6, 1, 6, 1)
        final_bar.setSpacing(6)
        self.final_item_font = QFontComboBox()
        self.final_item_font.setMinimumWidth(180)
        self.final_item_size = QSpinBox()
        self.final_item_size.setRange(5, 500)
        self.final_item_size.setSuffix(" px")
        self.final_item_stroke = QSpinBox()
        self.final_item_stroke.setRange(0, 100)
        self.final_item_stroke.setSuffix(" px")
        self.btn_item_text_color = QPushButton("문자색")
        self.btn_item_stroke_color = QPushButton("획색")
        self.btn_item_align_left = QPushButton("≡◁")
        self.btn_item_align_center = QPushButton("≡◇")
        self.btn_item_align_right = QPushButton("▷≡")
        self.sb_text_opacity = QSpinBox()
        self.sb_text_opacity.setRange(0, 100)
        self.sb_text_opacity.setValue(100)
        self.sb_text_opacity.setSuffix(" %")
        self.sb_text_opacity.setFixedWidth(76)
        self.sb_text_opacity.setToolTip("")
        self.btn_text_effect_gradient = QPushButton("◩")
        self.btn_text_effect_transform = QPushButton("⤢")
        self.btn_text_effect_skew = QPushButton("▱")
        self.btn_text_effect_trapezoid = QPushButton("▰")
        self.btn_text_effect_arc = QPushButton("⌒")
        self.btn_text_effect_rasterize = QPushButton("▣")
        for _btn, _tip in (
            (self.btn_text_effect_gradient, "문자/획 그라데이션"),
            (self.btn_text_effect_transform, "텍스트 변형"),
            (self.btn_text_effect_skew, "평행사변형 변형"),
            (self.btn_text_effect_trapezoid, "사다리꼴 변형"),
            (self.btn_text_effect_arc, "부채꼴 변형"),
            (self.btn_text_effect_rasterize, "텍스트를 객체로 변환"),
        ):
            _btn.setFixedSize(30, 26)
            _btn.setToolTip("")
        # 공유바에는 선택 텍스트용 빠른 옵션만 최소 구성으로 올린다.
        final_bar.addWidget(QLabel("불투명도"))
        final_bar.addWidget(self.sb_text_opacity)
        final_bar.addWidget(self.btn_text_effect_gradient)
        final_bar.addWidget(self.btn_text_effect_transform)
        final_bar.addWidget(self.btn_text_effect_skew)
        final_bar.addWidget(self.btn_text_effect_trapezoid)
        final_bar.addWidget(self.btn_text_effect_arc)
        final_bar.addStretch()
        self.final_edit_bar.hide()
        vl.addWidget(self.final_edit_bar)
        try:
            self.final_edit_bar.setFixedHeight(30)
            self.final_edit_bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        except Exception:
            pass

        self.final_paint_option_bar = QWidget()
        final_paint_bar = QHBoxLayout(self.final_paint_option_bar)
        final_paint_bar.setContentsMargins(6, 1, 6, 1)
        final_paint_bar.setSpacing(6)
        self.sb_final_paint_opacity = QSpinBox()
        self.sb_final_paint_opacity.setRange(1, 100)
        self.sb_final_paint_opacity.setValue(100)
        self.sb_final_paint_opacity.setSuffix(" %")
        self.sb_final_paint_opacity.setFixedWidth(80)
        self.sb_final_paint_opacity.valueChanged.connect(self.on_final_paint_opacity_changed)
        final_paint_bar.addWidget(QLabel("브러시"))
        final_paint_bar.addWidget(QLabel("불투명도"))
        final_paint_bar.addWidget(self.sb_final_paint_opacity)
        final_paint_bar.addStretch()
        self.final_paint_option_bar.hide()
        vl.addWidget(self.final_paint_option_bar)
        try:
            self.final_paint_option_bar.setFixedHeight(30)
            self.final_paint_option_bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        except Exception:
            pass

        self.area_paint_bar = QWidget()
        area_paint_bar_lay = QHBoxLayout(self.area_paint_bar)
        area_paint_bar_lay.setContentsMargins(6, 1, 6, 1)
        area_paint_bar_lay.setSpacing(6)
        self.btn_area_paint_rect = QPushButton(self.tr_ui("▭ 사각형"))
        self.btn_area_paint_rect.setCheckable(True)
        self.btn_area_paint_rect.clicked.connect(lambda checked=False: self.set_area_paint_shape("rect"))
        self.btn_area_paint_free = QPushButton(self.tr_ui("✎ 자유형"))
        self.btn_area_paint_free.setCheckable(True)
        self.btn_area_paint_free.clicked.connect(lambda checked=False: self.set_area_paint_shape("free"))
        area_paint_bar_lay.addWidget(QLabel(self.tr_ui("영역 페인팅")))
        area_paint_bar_lay.addWidget(self.btn_area_paint_rect)
        area_paint_bar_lay.addWidget(self.btn_area_paint_free)
        area_paint_bar_lay.addWidget(QLabel(self.tr_ui("선택한 영역을 현재 최종 페인팅 색상으로 채웁니다.")))
        area_paint_bar_lay.addStretch()
        self.area_paint_bar.hide()
        vl.addWidget(self.area_paint_bar)
        try:
            self.area_paint_bar.setFixedHeight(30)
            self.area_paint_bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        except Exception:
            pass
        self.set_area_paint_shape("rect", silent=True)

        self.magic_wand_bar = QWidget()
        magic_bar = QHBoxLayout(self.magic_wand_bar)
        magic_bar.setContentsMargins(6, 1, 6, 1)
        magic_bar.setSpacing(6)
        self.sb_magic_tolerance = QSpinBox()
        self.sb_magic_tolerance.setRange(0, 255)
        self.sb_magic_tolerance.setValue(20)
        self.sb_magic_tolerance.setFixedWidth(70)
        self.sb_magic_tolerance.setToolTip("요술봉 RGB 허용범위")
        self.btn_magic_expand = QPushButton("영역확장")
        self.btn_magic_expand.clicked.connect(self.expand_magic_wand_selection)
        self.sb_magic_expand = QSpinBox()
        self.sb_magic_expand.setRange(0, 200)
        self.sb_magic_expand.setValue(3)
        self.sb_magic_expand.setSuffix(" px")
        self.sb_magic_expand.setFixedWidth(80)
        self.sb_magic_expand.setToolTip("요술봉 영역확장 범위")
        self.btn_magic_fill = QPushButton("마스킹 칠하기")
        self.btn_magic_fill.clicked.connect(self.fill_magic_wand_mask)
        magic_bar.addWidget(QLabel("요술봉"))
        magic_bar.addWidget(QLabel("RGB 허용범위"))
        magic_bar.addWidget(self.sb_magic_tolerance)
        magic_bar.addWidget(self.btn_magic_expand)
        magic_bar.addWidget(QLabel("확장 범위"))
        magic_bar.addWidget(self.sb_magic_expand)
        magic_bar.addWidget(self.btn_magic_fill)
        magic_bar.addStretch()
        self.magic_wand_bar.hide()
        vl.addWidget(self.magic_wand_bar)
        try:
            self.magic_wand_bar.setFixedHeight(30)
            self.magic_wand_bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        except Exception:
            pass
        self.sb_magic_tolerance.valueChanged.connect(self.on_magic_wand_tolerance_changed)

        self.mask_wrap_bar = QWidget()
        mask_wrap_bar_lay = QHBoxLayout(self.mask_wrap_bar)
        mask_wrap_bar_lay.setContentsMargins(6, 1, 6, 1)
        mask_wrap_bar_lay.setSpacing(6)
        self.btn_mask_wrap_rect = QPushButton(self.tr_ui("▭ 사각형"))
        self.btn_mask_wrap_rect.setCheckable(True)
        self.btn_mask_wrap_rect.clicked.connect(lambda checked=False: self.set_mask_wrap_shape("rect"))
        self.btn_mask_wrap_free = QPushButton(self.tr_ui("✎ 자유형"))
        self.btn_mask_wrap_free.setCheckable(True)
        self.btn_mask_wrap_free.clicked.connect(lambda checked=False: self.set_mask_wrap_shape("free"))
        mask_wrap_bar_lay.addWidget(QLabel(self.tr_ui("마스크 랩핑")))
        mask_wrap_bar_lay.addWidget(self.btn_mask_wrap_rect)
        mask_wrap_bar_lay.addWidget(self.btn_mask_wrap_free)
        mask_wrap_bar_lay.addWidget(QLabel(self.tr_ui("선택한 영역 안의 떨어진 마스크들을 하나의 채움 영역으로 감싸줍니다.")))
        mask_wrap_bar_lay.addStretch()
        self.mask_wrap_bar.hide()
        vl.addWidget(self.mask_wrap_bar)
        try:
            self.mask_wrap_bar.setFixedHeight(30)
            self.mask_wrap_bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        except Exception:
            pass
        self.set_mask_wrap_shape("rect", silent=True)

        self.mask_cut_bar = QWidget()
        mask_cut_bar_lay = QHBoxLayout(self.mask_cut_bar)
        mask_cut_bar_lay.setContentsMargins(6, 1, 6, 1)
        mask_cut_bar_lay.setSpacing(6)
        self.btn_mask_cut_rect = QPushButton(self.tr_ui("▭ 사각형"))
        self.btn_mask_cut_rect.setCheckable(True)
        self.btn_mask_cut_rect.clicked.connect(lambda checked=False: self.set_mask_cut_shape("rect"))
        self.btn_mask_cut_free = QPushButton(self.tr_ui("✎ 자유형"))
        self.btn_mask_cut_free.setCheckable(True)
        self.btn_mask_cut_free.clicked.connect(lambda checked=False: self.set_mask_cut_shape("free"))
        self.sb_mask_cut_px = QSpinBox()
        self.sb_mask_cut_px.setRange(1, 200)
        self.sb_mask_cut_px.setValue(8)
        self.sb_mask_cut_px.setSuffix(" px")
        mask_cut_bar_lay.addWidget(QLabel(self.tr_ui("마스크 커팅")))
        mask_cut_bar_lay.addWidget(self.btn_mask_cut_rect)
        mask_cut_bar_lay.addWidget(self.btn_mask_cut_free)
        mask_cut_bar_lay.addWidget(QLabel(self.tr_ui("커팅 폭")))
        mask_cut_bar_lay.addWidget(self.sb_mask_cut_px)
        mask_cut_bar_lay.addWidget(QLabel(self.tr_ui("선택 영역 밖 경계를 지정 픽셀만큼 잘라 붙어 있는 마스크를 분리합니다.")))
        mask_cut_bar_lay.addStretch()
        self.mask_cut_bar.hide()
        vl.addWidget(self.mask_cut_bar)
        try:
            self.mask_cut_bar.setFixedHeight(30)
            self.mask_cut_bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        except Exception:
            pass
        self.set_mask_cut_shape("rect", silent=True)

        self.ocr_region_bar = QWidget()
        ocr_region_bar_lay = QHBoxLayout(self.ocr_region_bar)
        ocr_region_bar_lay.setContentsMargins(6, 1, 6, 1)
        ocr_region_bar_lay.setSpacing(6)
        self.btn_ocr_region_rect = QPushButton(self.tr_ui("▭ 사각형"))
        self.btn_ocr_region_rect.setCheckable(True)
        self.btn_ocr_region_rect.clicked.connect(lambda checked=False: self.set_ocr_region_shape("rect"))
        self.btn_ocr_region_free = QPushButton(self.tr_ui("✎ 자유형"))
        self.btn_ocr_region_free.setCheckable(True)
        self.btn_ocr_region_free.clicked.connect(lambda checked=False: self.set_ocr_region_shape("free"))
        self.btn_ocr_region_finish = QPushButton(self.tr_ui("분석 영역 지정 종료"))
        self.btn_ocr_region_finish.clicked.connect(self.finish_ocr_analysis_region_selection)
        ocr_region_bar_lay.addWidget(QLabel(self.tr_ui("OCR 분석 영역")))
        ocr_region_bar_lay.addWidget(self.btn_ocr_region_rect)
        ocr_region_bar_lay.addWidget(self.btn_ocr_region_free)
        ocr_region_bar_lay.addWidget(QLabel(self.tr_ui("OCR이 읽을 범위를 드래그로 지정합니다.")))
        ocr_region_bar_lay.addStretch()
        ocr_region_bar_lay.addWidget(self.btn_ocr_region_finish)
        self.ocr_region_bar.hide()
        vl.addWidget(self.ocr_region_bar)
        try:
            self.ocr_region_bar.setFixedHeight(30)
            self.ocr_region_bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        except Exception:
            pass
        self.set_ocr_region_shape("rect", silent=True)

        self.source_compare_bar = QWidget()
        source_compare_bar_lay = QHBoxLayout(self.source_compare_bar)
        source_compare_bar_lay.setContentsMargins(6, 1, 6, 1)
        source_compare_bar_lay.setSpacing(6)
        source_compare_bar_lay.addStretch()

        self.source_compare_controls = QWidget()
        source_compare_controls_lay = QHBoxLayout(self.source_compare_controls)
        source_compare_controls_lay.setContentsMargins(0, 0, 0, 0)
        source_compare_controls_lay.setSpacing(6)
        self.cb_source_compare_sync = QCheckBox(self.tr_ui("스크롤 동기화"))
        self.cb_source_compare_sync.setChecked(True)
        self.cb_source_compare_sync.toggled.connect(self.on_source_compare_sync_toggled)
        self.btn_source_compare_close = QPushButton(self.tr_ui("원본 비교창 끄기"))
        self.btn_source_compare_close.clicked.connect(self.close_source_compare_view)
        source_compare_controls_lay.addWidget(self.cb_source_compare_sync)
        source_compare_controls_lay.addWidget(self.btn_source_compare_close)
        try:
            if hasattr(self, "shared_option_right_layout"):
                self.shared_option_right_layout.addWidget(self.source_compare_controls)
        except Exception:
            pass
        self.source_compare_controls.hide()
        self.source_compare_bar.hide()
        vl.addWidget(self.source_compare_bar)
        try:
            self.source_compare_bar.setFixedHeight(30)
            self.source_compare_bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        except Exception:
            pass

        self.source_compare_view = QGraphicsView()
        self.source_compare_scene = QGraphicsScene(self.source_compare_view)
        self.source_compare_view.setScene(self.source_compare_scene)
        self.source_compare_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.source_compare_view.setBackgroundBrush(QBrush(QColor(30, 30, 30)))
        self.source_compare_view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.source_compare_view.setMinimumWidth(0)
        try:
            self.source_compare_view.viewport().installEventFilter(self)
        except Exception:
            pass
        self.source_compare_view.hide()

        self.source_compare_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.source_compare_splitter.setHandleWidth(6)
        self.source_compare_splitter.addWidget(self.source_compare_view)
        self.source_compare_splitter.addWidget(self.view)
        self.source_compare_splitter.setChildrenCollapsible(True)
        self.source_compare_splitter.setCollapsible(0, True)
        self.source_compare_splitter.setCollapsible(1, False)
        self.source_compare_splitter.setStretchFactor(0, 1)
        self.source_compare_splitter.setStretchFactor(1, 2)
        self.source_compare_splitter.setSizes([0, 1200])
        vl.addWidget(self.source_compare_splitter)
        try:
            self.source_compare_splitter.handle(1).installEventFilter(self)
            self._source_compare_splitter_handle = self.source_compare_splitter.handle(1)
        except Exception:
            pass

        try:
            self.source_compare_splitter.splitterMoved.connect(lambda pos, index: None)
            self.view.horizontalScrollBar().valueChanged.connect(self._on_main_view_scroll_changed_for_source_compare)
            self.view.verticalScrollBar().valueChanged.connect(self._on_main_view_scroll_changed_for_source_compare)
            self.source_compare_view.horizontalScrollBar().valueChanged.connect(self._on_source_compare_scroll_changed_for_main)
            self.source_compare_view.verticalScrollBar().valueChanged.connect(self._on_source_compare_scroll_changed_for_main)
        except Exception:
            pass

        ll.addWidget(vc)

        cl = QHBoxLayout()
        self.btn_prev_page = QPushButton("◀")
        self.btn_prev_page.clicked.connect(self.prev)
        cl.addWidget(self.btn_prev_page)
        self.btn_page = QPushButton("0 / 0")
        self.btn_page.setStyleSheet("border:none; font-weight:bold; color:#f2f2f2;")
        self.btn_page.clicked.connect(self.jump_page)
        cl.addWidget(self.btn_page)
        self.btn_next_page = QPushButton("▶")
        self.btn_next_page.clicked.connect(self.next)
        cl.addWidget(self.btn_next_page)

        self.cb_mode = QComboBox()
        self.cb_mode.addItems(["1. 원본", "2. 분석도", "3. 텍스트 마스크", "4. 페인팅 마스크", "5. 최종결과"])
        self.cb_mode.currentIndexChanged.connect(self.mode_chg)
        cl.addWidget(self.cb_mode)

        # Undo / Redo quick buttons.
        # 작업 탭 콤보 바로 오른쪽에 두어 탭/페이지/텍스트 작업을 마우스로도 되돌릴 수 있게 한다.
        self.btn_quick_undo = QPushButton("↺")
        self.btn_quick_undo.setFixedWidth(36)
        self.btn_quick_undo.setMinimumHeight(26)
        self.btn_quick_undo.clicked.connect(self.handle_global_undo_shortcut)
        cl.addWidget(self.btn_quick_undo)
        self.btn_quick_redo = QPushButton("↻")
        self.btn_quick_redo.setFixedWidth(36)
        self.btn_quick_redo.setMinimumHeight(26)
        self.btn_quick_redo.clicked.connect(self.handle_general_redo)
        cl.addWidget(self.btn_quick_redo)
        self.update_paint_toolbar_visibility()
        self.update_undo_redo_buttons()

        cl.addStretch()
        self.btn_text_mask_reanalyze = QPushButton(self.tr_ui("🔄 재분석"))
        self.btn_text_mask_reanalyze.setStyleSheet("background:#3d587d;color:#ffffff;font-weight:700;border:1px solid #7ea2d6;border-radius:0px;padding:6px 10px")
        self.btn_text_mask_reanalyze.clicked.connect(self.reanalyze_mask)
        self.btn_text_mask_reanalyze.hide()
        cl.addWidget(self.btn_text_mask_reanalyze)
        self.btn_analyze = QPushButton(self.tr_ui("⚡ 분석"), clicked=self.anal)
        self.btn_analyze.setStyleSheet("background:#7d4a4a;color:#ffffff;font-weight:700;border:1px solid #a86b6b;border-radius:0px;padding:6px 10px")
        cl.addWidget(self.btn_analyze)
        vl.addLayout(cl)
        split.addWidget(lp)

        # Right Panel
        rp = QWidget()
        # 오른쪽 작업 패널은 기본 상태에서는 사용자지정 콤보박스까지 보이도록 충분한 폭을 잡는다.
        # 단, splitter를 끌면 왼쪽/오른쪽 모두 거의 끝까지 접을 수 있게 최소 폭은 낮게 둔다.
        rp.setMinimumWidth(0)
        rp.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        rl = QVBoxLayout(rp)
        rl.setContentsMargins(6, 6, 6, 6)
        rl.setSpacing(4)

        self.right_panel = rp
        self.right_scroll = QScrollArea()
        self.right_scroll.setWidgetResizable(True)
        self.right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.right_scroll.setMinimumWidth(0)
        self.right_scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.right_scroll.setWidget(rp)
        split.addWidget(self.right_scroll)
        split.setChildrenCollapsible(True)
        split.setCollapsible(0, True)
        split.setCollapsible(1, True)
        # 왼쪽 이미지 뷰어를 주 작업 공간으로 두되,
        # 우측 기본 폭은 주요 컨트롤이 보이는 선에서 너무 넓지 않게 맞춘다.
        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 0)
        split.setSizes([1200, 700])

        # 글꼴 프리셋은 옵션 메뉴의 "글꼴 프리셋 관리"에서 다룬다.
        # 캐시/자동저장 로직 호환을 위해 컨트롤 객체는 숨겨 둔다.
        self.cb_text_preset = QComboBox(self)
        self.cb_text_preset.hide()
        self.btn_preset_save = QPushButton("프리셋 저장", self)
        self.btn_preset_save.hide()
        self.btn_preset_import = QPushButton("JSON 가져오기", self)
        self.btn_preset_import.hide()
        self.btn_preset_apply_page = QPushButton("페이지 적용", self)
        self.btn_preset_apply_page.hide()
        self.btn_preset_apply_all = QPushButton("전체 적용", self)
        self.btn_preset_apply_all.hide()

        # 우측 인터페이스 1줄: 선택 텍스트 스타일
        style_line = QHBoxLayout()
        style_line.setContentsMargins(0, 0, 0, 0)
        style_line.setSpacing(6)
        self.cb_font = QFontComboBox()
        self.cb_font.setFixedWidth(150)
        self.cb_font.setFixedHeight(26)
        self.cb_font.setToolTip("글꼴")
        self.sb_font_size = QSpinBox()
        self.sb_font_size.setRange(10, 300)
        self.sb_font_size.setValue(35)
        self.sb_font_size.setSuffix(" px")
        self.sb_font_size.setFixedWidth(100)
        self.sb_font_size.setToolTip("글꼴 크기")
        self.sb_strk = QSpinBox()
        self.sb_strk.setRange(0, 100)
        self.sb_strk.setValue(3)
        self.sb_strk.setSuffix(" px")
        self.sb_strk.setFixedWidth(90)
        self.sb_strk.setToolTip("획 크기")

        self.btn_text_color = QPushButton("")
        self.btn_text_color.setToolTip("문자 색상")
        self.btn_text_color.setFixedSize(26, 26)
        self.btn_stroke_color = QPushButton("")
        self.btn_stroke_color.setToolTip("획 색상")
        self.btn_stroke_color.setFixedSize(26, 26)

        self.btn_align_left = QPushButton("≡◁")
        self.btn_align_center = QPushButton("≡◇")
        self.btn_align_right = QPushButton("▷≡")
        for b in (self.btn_align_left, self.btn_align_center, self.btn_align_right):
            b.setCheckable(True)
            b.setFixedWidth(42)
            b.setFixedHeight(26)
            b.setToolTip("글자 정렬")

        self.sb_line_spacing = QSpinBox()
        self.sb_line_spacing.setRange(50, 300)
        self.sb_line_spacing.setValue(100)
        self.sb_line_spacing.setSuffix(" %")
        self.sb_line_spacing.setFixedWidth(78)
        self.sb_line_spacing.setToolTip("행간")

        self.sb_letter_spacing = QSpinBox()
        self.sb_letter_spacing.setRange(-100, 200)
        self.sb_letter_spacing.setValue(0)
        self.sb_letter_spacing.setSuffix(" px")
        self.sb_letter_spacing.setFixedWidth(78)
        self.sb_letter_spacing.setToolTip("자간")

        self.sb_char_width = QSpinBox()
        self.sb_char_width.setRange(10, 300)
        self.sb_char_width.setValue(100)
        self.sb_char_width.setSuffix(" %")
        self.sb_char_width.setFixedWidth(78)
        self.sb_char_width.setToolTip("문자 너비")

        self.sb_char_height = QSpinBox()
        self.sb_char_height.setRange(10, 300)
        self.sb_char_height.setValue(100)
        self.sb_char_height.setSuffix(" %")
        self.sb_char_height.setFixedWidth(78)
        self.sb_char_height.setToolTip("문자 높이")

        self.btn_bold = QPushButton("B")
        self.btn_italic = QPushButton("I")
        self.btn_strike = QPushButton("S")
        for b, tip in (
            (self.btn_bold, "굵게"),
            (self.btn_italic, "기울이기"),
            (self.btn_strike, "취소선"),
        ):
            b.setCheckable(True)
            b.setFixedWidth(32)
            b.setFixedHeight(26)
            b.setToolTip(tip)

        self.apply_text_style_button_styles()

        style_line.addWidget(QLabel("폰트"))
        style_line.addWidget(self.cb_font)
        style_line.addWidget(QLabel("크기"))
        style_line.addWidget(self.sb_font_size)
        style_line.addWidget(self.btn_text_color)
        style_line.addWidget(QLabel("획"))
        style_line.addWidget(self.sb_strk)
        style_line.addWidget(self.btn_stroke_color)
        style_line.addWidget(self.btn_align_left)
        style_line.addWidget(self.btn_align_center)
        style_line.addWidget(self.btn_align_right)
        style_line.addStretch()
        rl.addLayout(style_line)

        # 우측 인터페이스 2줄: 글꼴 상세 옵션
        detail_line = QHBoxLayout()
        detail_line.setContentsMargins(0, 0, 0, 0)
        detail_line.setSpacing(6)
        detail_line.addWidget(QLabel("행간"))
        detail_line.addWidget(self.sb_line_spacing)
        detail_line.addWidget(QLabel("자간"))
        detail_line.addWidget(self.sb_letter_spacing)
        detail_line.addWidget(QLabel("너비"))
        detail_line.addWidget(self.sb_char_width)
        detail_line.addWidget(QLabel("높이"))
        detail_line.addWidget(self.sb_char_height)
        detail_line.addWidget(self.btn_bold)
        detail_line.addWidget(self.btn_italic)
        detail_line.addWidget(self.btn_strike)

        self.cb_item_text_preset = QComboBox()
        self.cb_item_text_preset.setMinimumWidth(100)
        self.cb_item_text_preset.setMaximumWidth(110)
        self.cb_item_text_preset.setFixedHeight(26)
        self.cb_item_text_preset.setToolTip("개별 글꼴 프리셋")
        detail_line.addWidget(self.cb_item_text_preset)

        detail_line.addStretch()
        rl.addLayout(detail_line)

        self.text_style_control_widgets = [
            self.cb_font, self.sb_font_size, self.btn_text_color,
            self.sb_strk, self.btn_stroke_color,
            self.btn_align_left, self.btn_align_center, self.btn_align_right,
            self.sb_line_spacing, self.sb_letter_spacing,
            self.sb_char_width, self.sb_char_height,
            self.btn_bold, self.btn_italic, self.btn_strike,
            self.cb_item_text_preset, getattr(self, 'sb_text_opacity', None),
            getattr(self, 'btn_text_effect_gradient', None), getattr(self, 'btn_text_effect_transform', None),
            getattr(self, 'btn_text_effect_skew', None), getattr(self, 'btn_text_effect_trapezoid', None),
            getattr(self, 'btn_text_effect_arc', None), getattr(self, 'btn_text_effect_rasterize', None),
        ]

        # 우측 인터페이스 3줄: 자주 쓰는 작업만 남긴 압축 배치
        # 지문 추출 / 번역문 불러오기 / 인페인팅 원본 전환은 메뉴와 단축키로만 사용한다.
        al = QHBoxLayout()
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(6)
        self.cb_ocr_language = QComboBox()
        self.cb_ocr_language.setFixedHeight(26)
        self.cb_ocr_language.setMinimumWidth(92)
        self.cb_ocr_language.setMaximumWidth(120)
        self.refresh_ocr_language_combo(save=False)
        self.cb_ocr_language.currentIndexChanged.connect(self.on_ocr_language_toolbar_changed)

        self.cb_trans_provider = QComboBox()
        self.cb_trans_provider.setFixedHeight(26)
        self.cb_trans_provider.addItem("OpenAI", "openai")
        self.cb_trans_provider.addItem("DeepSeek", "deepseek")
        self.cb_trans_provider.addItem("Google", "google")
        self.cb_trans_provider.addItem("Gemini", "gemini")
        self.cb_trans_provider.addItem("Custom", "custom")
        self.set_combo_current_data(self.cb_trans_provider, getattr(self.api_settings, "selected_translation_provider", "openai"))
        self.cb_trans_provider.currentIndexChanged.connect(self.on_translation_provider_changed)

        self.sb_trans_chunk = QSpinBox()
        self.sb_trans_chunk.setRange(1, 100)
        self.sb_trans_chunk.setValue(self.trans_chunk_sizes.get("openai", 20))
        self.sb_trans_chunk.setSuffix(" items" if getattr(self, "ui_language", LANG_KO) == LANG_EN else "개")
        self.sb_trans_chunk.setFixedHeight(26)
        self.sb_trans_chunk.setStatusTip(self.tr_msg("한 번의 API 요청에 묶어서 보낼 텍스트 줄 수"))
        self.sb_trans_chunk.valueChanged.connect(self.on_translation_chunk_changed)

        self.cb_show_final_text = QCheckBox("텍스트 표시")
        self.cb_show_final_text.setChecked(True)
        self.cb_show_final_text.setFixedHeight(26)
        self.cb_show_final_text.toggled.connect(self.on_show_final_text_toggled)

        self.btn_translate = QPushButton("🌐 번역", clicked=self.trans)
        self.btn_translate.setFixedHeight(26)
        self.btn_inpaint = QPushButton("🎨 인페인팅", clicked=self.run_inpainting, styleSheet="background:#456f56;color:#ffffff;border:1px solid #6f9b7b;border-radius:0px;padding:4px 10px")
        self.btn_inpaint.setFixedHeight(26)
        self.btn_text_cleanup = QPushButton("🧹 텍스트 정리", clicked=self.clean_text_current)
        self.btn_text_cleanup.setFixedHeight(26)

        al.addWidget(QLabel("OCR언어"))
        al.addWidget(self.cb_ocr_language)
        al.addWidget(QLabel("번역AI"))
        al.addWidget(self.cb_trans_provider)
        al.addWidget(self.btn_translate)
        al.addWidget(self.btn_inpaint)
        al.addWidget(self.btn_text_cleanup)
        al.addWidget(self.cb_show_final_text)
        al.addStretch()
        rl.addLayout(al)

        self.tab = TextTableWidget(0, 4)
        self.tab.setHorizontalHeaderLabels(["ID", "X", "원문", "번역"])
        self.tab.setItemDelegateForColumn(
            3,
            MultilineDelegate(
                self.tab,
                shortcut_getter=self.get_special_shortcuts,
                linebreak_getter=self.get_linebreak_shortcut,
            )
        )
        self.tab.itemChanged.connect(self.on_table_item_changed)
        self.tab.itemSelectionChanged.connect(self.on_table_selection_changed)
        self.tab.rowsReordered.connect(self.on_text_table_rows_reordered)
        self.tab.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.tab.setDragDropOverwriteMode(False)
        self.tab.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.tab.setDragEnabled(True)
        self.tab.setAcceptDrops(True)
        self.tab.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tab.customContextMenuRequested.connect(self.on_table_context_menu)
        self.tab.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tab.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tab.setStyleSheet(
            "QTableWidget { background:#26282d; color:#f2f2f2; gridline-color:#4a4d55; border:1px solid #3b414c; border-radius:0px; }"
            "QTableWidget::item:selected { background:#3d587d; color:#ffffff; }"
        )
        rl.addWidget(self.tab)

        self.tab.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tab.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tab.setColumnWidth(0, 46)
        self.tab.setColumnWidth(1, 28)
        self.tab.setWordWrap(True)
        self.tab.verticalHeader().setVisible(False)
        self.tab.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        self.btn_export_result = QPushButton(self.tr_ui("📤 결과물 출력"), clicked=self.export_result, styleSheet="background:#3d587d;color:#ffffff;font-weight:700;border:1px solid #7ea2d6;border-radius:0px;height:40px")
        rl.addWidget(self.btn_export_result)

        # 작업 로그는 하단에 작은 조작 막대를 두고, 막대의 버튼으로 접고 펼친다.
        # 버튼을 큰 빈 로그 영역 안에 띄우지 않도록 로그 본문과 조작 막대를 분리한다.
        self.log_panel = QWidget()
        self.log_panel.setObjectName("LogPanel")
        self.log_panel_layout = QVBoxLayout(self.log_panel)
        self.log_panel_layout.setContentsMargins(0, 0, 0, 0)
        self.log_panel_layout.setSpacing(0)

        self.log_w = QTextEdit(self.log_panel)
        self.log_w.setFixedHeight(96)
        self.log_w.setReadOnly(True)
        self.log_w.setStyleSheet("background:#222;color:#0f0;")
        self.log_panel_layout.addWidget(self.log_w)

        self.log_footer = QWidget(self.log_panel)
        self.log_footer.setObjectName("LogPanelFooter")
        self.log_footer.setFixedHeight(30)
        log_footer_layout = QHBoxLayout(self.log_footer)
        log_footer_layout.setContentsMargins(8, 2, 4, 2)
        log_footer_layout.setSpacing(6)
        self.lbl_log_title = QLabel(self.tr_ui("작업 로그"), self.log_footer)
        self.lbl_log_title.setObjectName("LogPanelTitle")
        self.btn_log_toggle = QPushButton(self.log_footer)
        self.btn_log_toggle.setObjectName("LogPanelToggleButton")
        self.btn_log_toggle.setFixedHeight(24)
        self.btn_log_toggle.setMinimumWidth(96)
        self.btn_log_toggle.clicked.connect(self.toggle_log_panel_collapsed)
        log_footer_layout.addWidget(self.lbl_log_title)
        # 로그 접기/열기 버튼은 로그 제목 바로 옆에 둔다.
        # 오른쪽 끝으로 밀면 실제 로그 조작 위치가 너무 멀어져 시선 이동이 커진다.
        log_footer_layout.addWidget(self.btn_log_toggle)
        log_footer_layout.addStretch(1)
        self.log_panel_layout.addWidget(self.log_footer)
        self.log_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        rl.addWidget(self.log_panel)
        self.refresh_log_panel_state(save=False)
        self.flush_pending_log_messages()
        split.setSizes([1200, 700])

        self.cb_text_preset.currentIndexChanged.connect(self.on_text_preset_selected)
        self.btn_preset_save.clicked.connect(self.save_text_preset_named)
        self.btn_preset_import.clicked.connect(self.import_text_preset_json)
        self.btn_preset_apply_page.clicked.connect(self.apply_current_preset_to_current_page_safe)
        self.btn_preset_apply_all.clicked.connect(self.apply_current_preset_to_all_pages)

        self.cb_font.currentFontChanged.connect(self.on_global_text_style_changed)
        self.sb_font_size.valueChanged.connect(self.on_global_text_style_changed)
        self.sb_strk.valueChanged.connect(self.on_global_text_style_changed)
        self.sb_line_spacing.valueChanged.connect(self.on_global_text_style_changed)
        self.sb_letter_spacing.valueChanged.connect(self.on_global_text_style_changed)
        self.sb_char_width.valueChanged.connect(self.on_global_text_style_changed)
        self.sb_char_height.valueChanged.connect(self.on_global_text_style_changed)
        self.btn_bold.toggled.connect(self.on_global_text_style_changed)
        self.btn_italic.toggled.connect(self.on_global_text_style_changed)
        self.btn_strike.toggled.connect(self.on_global_text_style_changed)
        self.cb_item_text_preset.currentIndexChanged.connect(self.on_item_text_preset_selected)
        self.btn_text_color.clicked.connect(self.make_safe_slot(self.pick_color, "global_text"))
        self.btn_stroke_color.clicked.connect(self.make_safe_slot(self.pick_color, "global_stroke"))
        self.btn_align_left.clicked.connect(self.make_safe_slot(self.set_global_align, "left"))
        self.btn_align_center.clicked.connect(self.make_safe_slot(self.set_global_align, "center"))
        self.btn_align_right.clicked.connect(self.make_safe_slot(self.set_global_align, "right"))

        self.final_item_font.currentFontChanged.connect(self.on_final_item_style_changed)
        self.final_item_size.valueChanged.connect(self.on_final_item_style_changed)
        self.final_item_stroke.valueChanged.connect(self.on_final_item_style_changed)
        self.btn_item_text_color.clicked.connect(self.make_safe_slot(self.pick_color, "item_text"))
        self.btn_item_stroke_color.clicked.connect(self.make_safe_slot(self.pick_color, "item_stroke"))
        self.btn_item_align_left.clicked.connect(self.make_safe_slot(self.apply_style_to_selected, align="left"))
        self.btn_item_align_center.clicked.connect(self.make_safe_slot(self.apply_style_to_selected, align="center"))
        self.btn_item_align_right.clicked.connect(self.make_safe_slot(self.apply_style_to_selected, align="right"))
        self.sb_text_opacity.valueChanged.connect(self.on_text_opacity_changed)
        self.btn_text_effect_gradient.clicked.connect(self.open_selected_text_gradient_dialog)
        self.btn_text_effect_transform.clicked.connect(self.toggle_selected_text_transform_quick)
        self.btn_text_effect_skew.clicked.connect(self.toggle_selected_text_skew_quick)
        self.btn_text_effect_trapezoid.clicked.connect(self.toggle_selected_text_trapezoid_quick)
        self.btn_text_effect_arc.clicked.connect(self.toggle_selected_text_arc_quick)
        self.btn_text_effect_rasterize.clicked.connect(self.rasterize_selected_text_quick)
        self.page_required_widgets = [
            getattr(self, 'tb', None), getattr(self, 'view', None), getattr(self, 'btn_prev_page', None), getattr(self, 'btn_next_page', None),
            getattr(self, 'cb_mode', None), getattr(self, 'btn_page', None), getattr(self, 'btn_text_mask_reanalyze', None), getattr(self, 'btn_analyze', None),
            getattr(self, 'cb_ocr_language', None), getattr(self, 'cb_trans_provider', None), getattr(self, 'btn_translate', None), getattr(self, 'btn_inpaint', None), getattr(self, 'btn_text_cleanup', None),
            getattr(self, 'cb_show_final_text', None), getattr(self, 'tab', None), getattr(self, 'btn_export_result', None),
            getattr(self, 'page_tab_bar', None), getattr(self, 'btn_page_tab_menu', None),
        ]
        self.page_required_action_keys = [
            'work_analyze', 'work_quick_ocr', 'paint_reanalyze', 'work_translate', 'work_inpaint', 'work_inpaint_source',
            'batch_analyze', 'batch_translate', 'batch_inpaint', 'work_page_prev', 'work_page_next', 'work_page_list', 'work_page_full_name',
        ]
        self.update_color_button_styles()
        self.apply_text_style_button_styles()
        self.update_text_style_control_state([])
        self.update_page_presence_interlocks()
        self.install_main_input_enter_escape_filters()
        try:
            self.configure_stable_numeric_inputs()
        except Exception:
            pass

    def toggle_log_panel_collapsed(self):
        self.set_log_panel_collapsed(not bool(getattr(self, "log_panel_collapsed", False)), save=True)

    def set_log_panel_collapsed(self, collapsed, save=True):
        self.log_panel_collapsed = bool(collapsed)
        self.refresh_log_panel_state(save=save)

    def refresh_log_panel_state(self, save=False):
        collapsed = bool(getattr(self, "log_panel_collapsed", False))
        try:
            if hasattr(self, "log_w") and self.log_w is not None:
                self.log_w.setVisible(not collapsed)
            if hasattr(self, "log_panel") and self.log_panel is not None:
                self.log_panel.setFixedHeight(30 if collapsed else 126)
        except Exception:
            pass
        try:
            if hasattr(self, "lbl_log_title") and self.lbl_log_title is not None:
                self.lbl_log_title.setText(self.tr_ui("작업 로그"))
            if hasattr(self, "btn_log_toggle") and self.btn_log_toggle is not None:
                if collapsed:
                    self.btn_log_toggle.setText("▲ " + self.tr_ui("로그 열기"))
                    self.btn_log_toggle.setToolTip(self.tr_ui("숨긴 작업 로그를 다시 엽니다."))
                else:
                    self.btn_log_toggle.setText("— " + self.tr_ui("로그 숨기기"))
                    self.btn_log_toggle.setToolTip(self.tr_ui("작업 로그를 아래 막대로 접습니다."))
        except Exception:
            pass
        try:
            self.apply_log_panel_theme()
        except Exception:
            pass
        if save:
            try:
                self.app_options[LOG_PANEL_COLLAPSED_KEY] = collapsed
                self.save_app_options_cache()
            except Exception:
                pass

    def apply_log_panel_theme(self):
        light = self.is_light_theme() if hasattr(self, "is_light_theme") else False
        if light:
            panel_style = "QWidget#LogPanel { background:#ffffff; border:1px solid #dfe5ef; border-radius:0px; }"
            header_style = "QWidget#LogPanelFooter { background:#eef2f8; border:0; border-top:1px solid #dfe5ef; }"
            title_style = "color:#374151; font-weight:700;"
            button_style = (
                "QPushButton#LogPanelToggleButton { background:#f8fafc; color:#374151; border:1px solid #cfd7e5; "
                "border-radius:0px; padding:2px 8px; font-weight:700; }"
                "QPushButton#LogPanelToggleButton:hover { background:#edf4ff; border-color:#aac4e8; }"
            )
            log_style = "background:#ffffff;color:#25704a;border:0;border-radius:0px;"
        else:
            panel_style = "QWidget#LogPanel { background:#1f2228; border:1px solid #3b414c; border-radius:0px; }"
            header_style = "QWidget#LogPanelFooter { background:#24282f; border:0; border-top:1px solid #3b414c; }"
            title_style = "color:#d7deea; font-weight:700;"
            button_style = (
                "QPushButton#LogPanelToggleButton { background:#333843; color:#f2f4f8; border:1px solid #555d6c; "
                "border-radius:0px; padding:2px 8px; font-weight:700; }"
                "QPushButton#LogPanelToggleButton:hover { background:#3d4654; border-color:#718098; }"
            )
            log_style = "background:#1f2228;color:#8ee0a1;border:0;border-radius:0px;"
        try:
            if hasattr(self, "log_panel") and self.log_panel is not None:
                self.log_panel.setStyleSheet(panel_style)
            if hasattr(self, "log_footer") and self.log_footer is not None:
                self.log_footer.setStyleSheet(header_style)
            if hasattr(self, "log_header") and self.log_header is not None:
                self.log_header.setStyleSheet(header_style)
            if hasattr(self, "lbl_log_title") and self.lbl_log_title is not None:
                self.lbl_log_title.setStyleSheet(title_style)
            if hasattr(self, "btn_log_toggle") and self.btn_log_toggle is not None:
                self.btn_log_toggle.setStyleSheet(button_style)
            if hasattr(self, "log_w") and self.log_w is not None:
                self.log_w.setStyleSheet(log_style)
        except Exception:
            pass

    def shortcut_text_for_key(self, key, fallback=""):
        try:
            seq = self.shortcut_settings.seq(key)
            if seq and not seq.isEmpty():
                txt = seq.toString(QKeySequence.SequenceFormat.NativeText)
                return txt or fallback
        except Exception:
            pass
        return fallback

    def set_dialog_control_tooltip(self, widget, title, key="", desc=""):
        if widget is None:
            return
        shortcut = self.shortcut_text_for_key(key, "") if key else ""
        parts = [self.tr_ui(title)]
        if shortcut:
            parts.append(shortcut)
        if desc:
            parts.append(self.tr_msg(desc))
        try:
            widget.setToolTip("\n".join(parts))
        except Exception:
            pass

    def focus_dialog_control(self, widget):
        if widget is None:
            return
        try:
            widget.setFocus()
            if hasattr(widget, "selectAll"):
                widget.selectAll()
            elif hasattr(widget, "lineEdit") and widget.lineEdit() is not None:
                widget.lineEdit().selectAll()
        except Exception:
            pass

    def add_dialog_shortcut(self, dialog, key, callback):
        try:
            seq = self.shortcut_settings.seq(key)
        except Exception:
            seq = QKeySequence()
        if not seq or seq.isEmpty():
            return None
        sc = QShortcut(seq, dialog)
        sc.setContext(Qt.ShortcutContext.WindowShortcut)
        sc.activated.connect(callback)
        if not hasattr(dialog, "_ysb_style_shortcuts"):
            dialog._ysb_style_shortcuts = []
        dialog._ysb_style_shortcuts.append(sc)
        return sc

    def apply_current_preset_to_current_page_safe(self, *signal_args):
        return self.apply_current_preset_to_page(self.idx, refresh=True)

    def install_style_editor_shortcuts(self, dialog, controls):
        """메인 인터페이스와 같은 글꼴 상세 단축키/툴팁을 프리셋 창에도 적용한다."""
        if not dialog or not controls:
            return

        if not hasattr(dialog, "_ysb_enter_commit_filter"):
            dialog._ysb_enter_commit_filter = EnterCommitFilter(parent_dialog=dialog, fallback_widget=dialog, parent=dialog)
        for _name, _widget in list(controls.items()):
            if _widget is None:
                continue
            try:
                _widget.installEventFilter(dialog._ysb_enter_commit_filter)
            except Exception:
                pass
            try:
                line = _widget.lineEdit()
                if line is not None:
                    line.installEventFilter(dialog._ysb_enter_commit_filter)
            except Exception:
                pass

        def open_font_selector():
            font_widget = controls.get("font")
            size_widget = controls.get("size")
            bold_widget = controls.get("bold")
            italic_widget = controls.get("italic")
            try:
                current_family = font_widget.currentFont().family()
            except Exception:
                current_family = ""
            try:
                current_size = int(size_widget.value())
            except Exception:
                current_size = 24
            dlg = FontSelectDialog(
                current_family=current_family,
                current_size=current_size,
                current_bold=bool(bold_widget.isChecked()) if bold_widget else False,
                current_italic=bool(italic_widget.isChecked()) if italic_widget else False,
                parent=self,
            )
            if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_font_family():
                if font_widget is not None:
                    font_widget.setCurrentFont(QFont(dlg.selected_font_family()))
                if bold_widget is not None:
                    bold_widget.setChecked(dlg.selected_is_bold())
                if italic_widget is not None:
                    italic_widget.setChecked(dlg.selected_is_italic())

        focus_map = {
            "text_font_size": ("size", "글꼴 크기", "현재 편집 중인 글자 크기 값을 선택합니다."),
            "text_stroke_size": ("stroke", "획 크기", "현재 편집 중인 외곽선 두께 값을 선택합니다."),
            "text_line_spacing": ("line_spacing", "행간", "줄과 줄 사이 간격 값을 선택합니다."),
            "text_letter_spacing": ("letter_spacing", "자간", "글자와 글자 사이 간격 값을 선택합니다."),
            "text_char_width": ("char_width", "너비", "문자의 가로 비율 값을 선택합니다."),
            "text_char_height": ("char_height", "높이", "문자의 세로 비율 값을 선택합니다."),
        }
        for key, (control_name, title, desc) in focus_map.items():
            widget = controls.get(control_name)
            self.set_dialog_control_tooltip(widget, title, key, desc)
            self.add_dialog_shortcut(dialog, key, self.make_safe_slot(self.focus_dialog_control, widget))

        toggle_map = {
            "text_bold_toggle": ("bold", "굵게"),
            "text_italic_toggle": ("italic", "기울이기"),
            "text_strike_toggle": ("strike", "취소선"),
        }
        for key, (control_name, title) in toggle_map.items():
            widget = controls.get(control_name)
            self.set_dialog_control_tooltip(widget, title, key, "")
            self.add_dialog_shortcut(dialog, key, self.make_safe_click_slot(widget))

        color_map = {
            "item_text_color": ("text_color", "문자 색상", "현재 편집 중인 문자 색상을 선택합니다."),
            "item_stroke_color": ("stroke_color", "획 색상", "현재 편집 중인 외곽선 색상을 선택합니다."),
        }
        for key, (control_name, title, desc) in color_map.items():
            widget = controls.get(control_name)
            self.set_dialog_control_tooltip(widget, title, key, desc)

        align_map = {
            "item_align_left": ("align_left", "왼쪽 정렬"),
            "item_align_center": ("align_center", "가운데 정렬"),
            "item_align_right": ("align_right", "오른쪽 정렬"),
        }
        for key, (control_name, title) in align_map.items():
            widget = controls.get(control_name)
            self.set_dialog_control_tooltip(widget, title, key, "")

        font_widget = controls.get("font")
        self.set_dialog_control_tooltip(font_widget, "글꼴 선택", "item_font_select", "전용 글꼴 선택창을 엽니다.")
        self.add_dialog_shortcut(dialog, "item_font_select", open_font_selector)

    def open_font_select_dialog(self):
        """전용 글꼴 선택 창을 열어 선택 텍스트 또는 기본 글꼴에 적용한다."""
        try:
            current_family = self.cb_font.currentFont().family()
        except Exception:
            current_family = ""
        try:
            current_size = int(self.sb_font_size.value())
        except Exception:
            current_size = 24
        try:
            current_bold = bool(self.btn_bold.isChecked())
            current_italic = bool(self.btn_italic.isChecked())
        except Exception:
            current_bold = False
            current_italic = False

        dlg = FontSelectDialog(
            current_family=current_family,
            current_size=current_size,
            current_bold=current_bold,
            current_italic=current_italic,
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return False

        family = dlg.selected_font_family()
        if not family:
            return False

        style_updates = {
            "font_family": family,
            "bold": dlg.selected_is_bold(),
            "italic": dlg.selected_is_italic(),
        }

        if self.cb_mode.currentIndex() == 4 and self.selected_text_items():
            self.apply_style_to_selected(**style_updates)
        else:
            self.cb_font.setCurrentFont(QFont(family))
            try:
                self.btn_bold.setChecked(bool(style_updates["bold"]))
                self.btn_italic.setChecked(bool(style_updates["italic"]))
            except Exception:
                pass
            self.on_global_text_style_changed()

        self.log((f"🔤 Font selected: {family} / {dlg.selected_font_style()}" if self.ui_language == LANG_EN else f"🔤 글꼴 선택: {family} / {dlg.selected_font_style()}"))
        return True

    def set_combo_current_data(self, combo, data):
        """QComboBox의 userData 값으로 현재 항목을 선택한다."""
        try:
            for i in range(combo.count()):
                if str(combo.itemData(i)) == str(data):
                    combo.setCurrentIndex(i)
                    return True
        except Exception:
            pass
        return False

    def tr_ui(self, text):
        return translate_ui_text(text, getattr(self, "ui_language", LANG_KO))

    def tr_msg(self, text):
        return translate_ui_dynamic_text(text, getattr(self, "ui_language", LANG_KO))

    def display_project_name(self):
        """창 제목에 표시할 현재 파일명.
        .ysbt 파일명은 사람이 보는 이름 그대로 두고, UUID는 내부 manifest/작업 폴더에서만 관리한다.
        구버전 이름_고유번호.ysbt 파일을 열었을 때만 표시용으로 뒤쪽 코드를 숨긴다.
        """
        name = ""
        try:
            if getattr(self, "ysbt_package_path", None):
                name = Path(self.ysbt_package_path).stem
            elif getattr(self, "suggested_project_name", None):
                name = str(self.suggested_project_name)
        except Exception:
            name = ""
        if not name:
            return ""
        name = re.sub(r"_[0-9a-fA-F]{8,12}$", "", name)
        return name

    def update_window_title(self):
        is_en = normalize_ui_language(getattr(self, "ui_language", current_ui_language())) == LANG_EN
        base_name = APP_NAME_EN if is_en else APP_NAME_KO
        base = f"{base_name} {APP_VERSION}"
        project_name = self.display_project_name()
        try:
            self.setWindowTitle(f"{base} - {project_name}" if project_name else base)
        except Exception:
            pass

    def split_uuid_suffix_from_name(self, name: str):
        stem = clean_workspace_name(name or "ysb_project")
        m = re.match(r"^(.*)_([0-9a-fA-F]{8,12})$", stem)
        if m:
            return clean_workspace_name(m.group(1) or stem), m.group(2).lower()
        return stem, None

    def make_ysbt_path_with_uuid_suffix(self, path: str, project_uuid: str | None = None):
        """사용자가 고른 .ysbt 경로를 확정한다.

        v1.6 정책:
        - .ysbt 파일명에는 UUID를 붙이지 않는다.
        - UUID는 패키지 내부 manifest.json에 저장한다.
        - 작업 폴더를 만들 때만 파일명 뒤에 uuid 짧은값을 붙인다.

        함수명은 기존 호출부 호환을 위해 유지한다.
        반환: (ysbt_path, display_project_name, project_uuid)
        """
        path = self.normalize_ysb_path(path)
        path_obj = Path(path)
        display_name, existing_code = self.split_uuid_suffix_from_name(path_obj.stem)
        if project_uuid:
            final_uuid = str(project_uuid)
        elif existing_code:
            # 구버전 이름_고유번호.ysbt를 저장할 때도 파일명은 정리하되,
            # 기존 코드 앞자리는 내부 UUID에 이어받는다.
            random_tail = uuid.uuid4().hex[len(existing_code):]
            final_uuid = (existing_code + random_tail)[:32]
        else:
            final_uuid = uuid.uuid4().hex
        clean_path = path_obj.with_name(safe_project_name(display_name) + YSB_EXTENSION)
        return str(clean_path), display_name, final_uuid

    def translate_child_widgets(self, root_widget):
        """설정창/프리셋창처럼 나중에 생성되는 창의 고정 문구를 현재 언어로 바꾼다."""
        if root_widget is None:
            return
        try:
            for widget in root_widget.findChildren((QLabel, QPushButton, QCheckBox, QGroupBox, QRadioButton)):
                try:
                    txt = widget.text()
                except Exception:
                    continue
                if txt:
                    widget.setText(self.tr_msg(txt))
        except Exception:
            pass
        try:
            for combo in root_widget.findChildren(QComboBox):
                for i in range(combo.count()):
                    txt = combo.itemText(i)
                    if txt:
                        combo.setItemText(i, self.tr_msg(txt))
        except Exception:
            pass
        try:
            for spin in root_widget.findChildren(QSpinBox):
                if spin.specialValueText():
                    spin.setSpecialValueText(self.tr_ui(spin.specialValueText()))
        except Exception:
            pass
        try:
            for widget in root_widget.findChildren(QWidget):
                tip = widget.toolTip()
                if tip:
                    widget.setToolTip(self.tr_msg(tip))
        except Exception:
            pass

    def apply_language(self, language=None):
        """저장된 표시 언어를 메인 UI에 적용한다.
        사용자 원문/번역문 데이터는 건드리지 않고, 고정 UI 문구만 교체한다.
        """
        lang = normalize_ui_language(language or getattr(self, "ui_language", LANG_KO))
        self.ui_language = lang
        try:
            self.update_window_title()
        except Exception:
            pass

        # 메뉴 제목
        for attr, ko in (
            ("project_menu", "프로젝트"),
            ("work_menu", "작업"),
            ("batch_menu", "일괄 작업"),
            ("auto_menu", "자동화 작업"),
            ("settings_menu", "설정"),
            ("cloud_menu", "클라우드"),
            ("option_menu", "옵션"),
            ("help_menu", "도움말"),
        ):
            menu = getattr(self, attr, None)
            if menu is not None:
                try:
                    menu.setTitle(self.tr_ui(ko))
                except Exception:
                    pass

        action_ko = {
            "project_new": "새로 만들기",
            "project_import_images": "이미지 불러오기",
            "project_open": "열기",
            "project_open_json": "JSON으로 열기",
            "project_show_launcher": "홈화면으로 가기",
            "project_exit": "프로젝트 나가기",
            "project_save": "저장하기",
            "project_save_as": "다른 이름으로 저장하기",
            "project_recover_last_work": "복구하기",
            "option_settings_overview": "설정 / 옵션",
            "work_tab_cycle": "작업탭 변경",
            "paint_undo": "작업 취소",
            "paint_redo": "작업 재실행",
            "work_page_prev": "이전 페이지",
            "work_page_next": "다음 페이지",
            "work_page_list": "페이지 목록",
            "work_page_full_name": "현재 페이지 이름 보기",
            "work_page_rename_source": "페이지 탭 파일명 변경",
            "work_page_delete_current": "현재 페이지 탭 삭제",
            "work_page_delete_all": "전체 페이지 탭 삭제",
            "work_open_current_project_folder": "현재 프로젝트의 작업 폴더로 이동하기",
            "work_analyze": "분석",
            "work_quick_ocr": "빠른 OCR 설정",
            "quick_ocr_execute": "빠른 OCR 실행",
            "work_text_number_width": "텍스트 넘버 크기 변경",
            "work_translate": "번역",
            "work_inpaint": "인페인팅",
            "work_inpaint_source": "인페인팅을 원본으로",
            "work_restore_original_source": "원본으로 돌아가기",
            "work_extract_text": "지문 추출",
            "work_import_translation": "번역문 불러오기",
            "work_clear_translation": "번역문 내용 지우기",
            "work_clean_text": "텍스트 정리",
            "work_reset_text_rects": "현재 텍스트 기준으로 영역 재설정",
            "work_export": "출력",
            "batch_analyze": "일괄 분석",
            "batch_translate": "일괄 번역",
            "batch_inpaint": "일괄 인페인팅",
            "batch_extract_text": "일괄 지문 추출",
            "batch_import_translation": "일괄 번역문 불러오기",
            "batch_clear_translation": "일괄 번역문 내용 지우기",
            "batch_clean_text": "일괄 텍스트 정리",
            "batch_reset_text_rects": "일괄 현재 텍스트 기준으로 영역 재설정",
            "batch_export": "일괄 출력",
            "auto_text_size_current": "자동 텍스트 크기 조정",
            "auto_text_size_batch": "일괄 자동 텍스트 크기 조정",
            "auto_linebreak_current": "자동 줄 내림",
            "auto_linebreak_batch": "일괄 자동 줄 내림",
            "option_auto_save_mode": "자동저장 모드",
            "option_theme_settings": "테마 설정",
            "option_language_settings": "언어 설정",
            "setting_page_tab_display_name": "페이지 탭 표시명 설정",
            "setting_output_display_name": "출력 표시명 설정",
            "setting_file_path_visibility": "파일 경로 표시",
            "option_api_settings": "API 관리",
            "option_translation_prompt": "번역 프롬프트 입력",
            "option_glossary": "단어장",
            "option_analysis_mask_settings": "분석 마스크 확장 비율",
            "option_ocr_analysis_regions": "OCR 분석 범위 지정",
            "option_cleanup_outputs": "출력물 삭제",
            "option_workspace_location": "작업 폴더 위치 변경",
            "option_workspace_reset_default": "작업 폴더 위치 기본값으로 변경",
            "option_cleanup_temp_files": "임시 파일 관리",
            "option_register_ysb": ".ysbt 확장자 연결 등록",
            "option_unregister_ysbt": ".ysbt 확장자 연결 해제",
            "option_shortcut_settings": "단축키 통합 관리",
            "option_macro_settings": "매크로 관리",
            "option_text_preset_settings": "페이지 글꼴 프리셋 관리",
            "option_item_text_preset_settings": "개별 글꼴 프리셋 관리",
            "cloud_register": "클라우드 등록",
            "cloud_unregister": "클라우드 등록 해제",
            "cloud_cache_backup": "클라우드로 캐시 백업",
            "cloud_cache_restore": "클라우드에서 캐시 불러오기",
            "cloud_delete_backups": "클라우드 백업 삭제",
            "help_program_manual": "프로그램 메뉴얼",
            "help_open_website": "YSB Tool 사이트로 가기",
            "help_report_bug": "버그제보 / 문의하기",
            "help_about": "프로그램 정보",
            "paint_magic_fill": "마스킹 칠하기",
            "paint_mask_wrap": "마스크 랩핑",
            "paint_mask_cut": "마스크 커팅",
            "paint_mask_wrap_rect": "마스크 선택 사각형",
            "paint_mask_wrap_free": "마스크 선택 자유형",
            "paint_mask_toggle": "마스크 ON/OFF",
            "view_text_toggle": "텍스트 표시 ON/OFF",
            "final_paint_color": "최종 페인팅 색상",
            "final_paint_to_background": "최종 페인팅을 배경에 반영",
            "final_text_tool": "최종 텍스트 도구",
            "final_paint_above_toggle": "텍스트 위 페인팅 ON/OFF",
            "final_paint_opacity_inc": "브러시 불투명도 증가",
            "final_paint_opacity_dec": "브러시 불투명도 감소",
        }
        for key, ko in action_ko.items():
            action = self.actions.get(key)
            if action is not None:
                try:
                    action.setText(self.tr_ui(ko))
                except Exception:
                    pass

        try:
            if hasattr(self, "launcher_widget"):
                self.launcher_widget.set_language(lang)
        except Exception:
            pass

        # 현재 생성된 고정 UI 위젯의 텍스트를 교체한다.
        widget_types = (QLabel, QPushButton, QCheckBox, QGroupBox, QRadioButton)
        for widget in self.findChildren(widget_types):
            try:
                txt = widget.text()
            except Exception:
                continue
            if txt:
                new_txt = self.tr_ui(txt)
                if new_txt != txt:
                    try:
                        widget.setText(new_txt)
                    except Exception:
                        pass

        # 우측 텍스트 표 헤더
        try:
            if hasattr(self, "tab"):
                headers = ["ID", "X", self.tr_ui("원문"), self.tr_ui("번역")]
                self.tab.setHorizontalHeaderLabels(headers)
                for row in (0,):
                    item = self.tab.item(row, 2)
                    if item and item.text() in ("전체 선택", "Select All"):
                        item.setText(self.tr_ui("전체 선택"))
        except Exception:
            pass

        # 콤보박스 기본 항목
        try:
            if hasattr(self, "cb_text_preset"):
                for i in range(self.cb_text_preset.count()):
                    if self.cb_text_preset.itemData(i) == "__last__":
                        self.cb_text_preset.setItemText(i, self.tr_ui("마지막 설정"))
            if hasattr(self, "cb_item_text_preset"):
                for i in range(self.cb_item_text_preset.count()):
                    if self.cb_item_text_preset.itemData(i) == "__custom__":
                        self.cb_item_text_preset.setItemText(i, self.tr_ui("사용자지정"))
        except Exception:
            pass

        # 작업 탭/모드 콤보박스 항목
        try:
            if hasattr(self, "cb_mode"):
                mode_labels = ["1. 원본", "2. 분석도", "3. 텍스트 마스크", "4. 페인팅 마스크", "5. 최종결과"]
                cur = self.cb_mode.currentIndex()
                self.cb_mode.blockSignals(True)
                for i, ko in enumerate(mode_labels):
                    if i < self.cb_mode.count():
                        self.cb_mode.setItemText(i, self.tr_ui(ko))
                self.cb_mode.setCurrentIndex(cur)
                self.cb_mode.blockSignals(False)
        except Exception:
            try:
                self.cb_mode.blockSignals(False)
            except Exception:
                pass

        # 콤보박스 안의 기본 한국어 항목
        try:
            for combo in self.findChildren(QComboBox):
                for i in range(combo.count()):
                    txt = combo.itemText(i)
                    if txt:
                        new_txt = self.tr_ui(txt)
                        if new_txt != txt:
                            combo.setItemText(i, new_txt)
        except Exception:
            pass

        # 일부 위젯은 이모지/특수값 때문에 일반 순회 번역만으로는 바뀌지 않으므로 직접 보정한다.
        try:
            # 행간/자간은 수치 기반으로 표시한다. 행간 기본값은 100%, 자간 기본값은 0px.
            # QSpinBox specialValueText("자동")는 최솟값 전용이라 음수/기본값 UX와 충돌한다.
            if hasattr(self, "btn_analyze"):
                self.btn_analyze.setText(self.tr_ui("⚡ 분석"))
            if hasattr(self, "btn_text_mask_reanalyze"):
                self.btn_text_mask_reanalyze.setText(self.tr_ui("🔄 재분석"))
            if hasattr(self, "btn_mask_wrap_rect"):
                self.btn_mask_wrap_rect.setText(self.tr_ui("▭ 사각형"))
            if hasattr(self, "btn_mask_wrap_free"):
                self.btn_mask_wrap_free.setText(self.tr_ui("✎ 자유형"))
            if hasattr(self, "btn_mask_cut_rect"):
                self.btn_mask_cut_rect.setText(self.tr_ui("▭ 사각형"))
            if hasattr(self, "btn_mask_cut_free"):
                self.btn_mask_cut_free.setText(self.tr_ui("✎ 자유형"))
            if hasattr(self, "btn_area_paint_rect"):
                self.btn_area_paint_rect.setText(self.tr_ui("▭ 사각형"))
            if hasattr(self, "btn_area_paint_free"):
                self.btn_area_paint_free.setText(self.tr_ui("✎ 자유형"))
            if hasattr(self, "btn_translate"):
                self.btn_translate.setText(self.tr_ui("🌐 번역"))
            if hasattr(self, "btn_inpaint"):
                self.btn_inpaint.setText(self.tr_ui("🎨 인페인팅"))
            if hasattr(self, "btn_text_cleanup"):
                self.btn_text_cleanup.setText(self.tr_ui("🧹 텍스트 정리"))
            if hasattr(self, "btn_export_result"):
                self.btn_export_result.setText(self.tr_ui("📤 결과물 출력"))
            if hasattr(self, "sb_trans_chunk"):
                self.sb_trans_chunk.setSuffix(" items" if lang == LANG_EN else "개")
                self.sb_trans_chunk.setStatusTip(self.tr_msg("한 번의 API 요청에 묶어서 보낼 텍스트 줄 수"))
            if hasattr(self, "btn_project_exit"):
                self.btn_project_exit.setText(self.tr_ui("프로젝트 나가기"))
                seq = self.shortcut_settings.seq("project_exit").toString(QKeySequence.SequenceFormat.NativeText)
                self.btn_project_exit.setToolTip(self.native_tooltip_html("프로젝트 나가기", seq))
            if hasattr(self, "btn_page_tab_menu"):
                self.btn_page_tab_menu.setText("☰")
                seq = self.shortcut_settings.seq("work_page_list").toString(QKeySequence.SequenceFormat.NativeText)
                self.btn_page_tab_menu.setToolTip(self.native_tooltip_html("페이지 목록", seq))
        except Exception:
            pass

        # 기본 툴팁 문구도 언어 설정에 맞춘다.
        try:
            for widget in self.findChildren(QWidget):
                tip = widget.toolTip()
                if tip:
                    new_tip = self.tr_ui(tip)
                    if new_tip != tip:
                        widget.setToolTip(new_tip)
        except Exception:
            pass

        try:
            self.refresh_log_panel_state(save=False)
        except Exception:
            pass

        try:
            self.configure_ui_tooltips()
        except Exception:
            pass

    def open_language_settings_dialog(self):
        """옵션 > 언어 설정."""
        old_language = normalize_ui_language(getattr(self, "ui_language", LANG_KO))

        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr_ui("언어 설정"))
        dialog.resize(360, 160)
        layout = QVBoxLayout(dialog)

        label = QLabel(self.tr_ui("표시 언어를 선택하세요.\n확인을 누르면 즉시 적용되고, 닫기를 누르면 변경하지 않습니다."))
        label.setWordWrap(True)
        layout.addWidget(label)

        combo = QComboBox(dialog)
        combo.addItem(self.tr_ui("한국어"), LANG_KO)
        combo.addItem("English", LANG_EN)
        combo.setCurrentIndex(1 if old_language == LANG_EN else 0)
        layout.addWidget(combo)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dialog)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr_ui("확인"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(self.tr_ui("닫기"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        dialog.setStyleSheet(self.settings_dialog_style())

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected = normalize_ui_language(combo.currentData())
        self.ui_language = selected
        self.save_app_options_cache()
        self.apply_language(selected)
        self.log("🌐 Language changed: English" if selected == LANG_EN else "🌐 언어 변경: 한국어")

    def apply_theme(self, theme=None):
        """저장된 테마값에 따라 전체 UI 테마를 적용한다."""
        theme = str(theme or getattr(self, "ui_theme", THEME_DARK) or THEME_DARK).lower()
        if theme not in (THEME_DARK, THEME_LIGHT):
            theme = THEME_DARK
        self.ui_theme = theme
        if theme == THEME_LIGHT:
            self.apply_light_theme()
        else:
            self.apply_dark_theme()
        try:
            if hasattr(self, "launcher_widget"):
                self.launcher_widget.set_theme(theme)
        except Exception:
            pass
        self.force_theme_repaint_after_apply()

    def refresh_top_bars_for_theme(self):
        """Qt 내부 상단 영역만 현재 테마에 맞춘다.
        Windows 네이티브 제목 표시줄은 건드리지 않는다. 네이티브 프레임을 강제로
        다시 그리면 최소화/복원/전체화면 전환 뒤 포커스와 입력 상태가 꼬일 수 있다.
        """
        light = self.is_light_theme()
        try:
            mb = self.menuBar()
            if mb is not None:
                if light:
                    mb.setStyleSheet(
                        "QMenuBar { background-color:#ffffff; color:#22252b; border-bottom:1px solid #e0e6f0; padding:2px 4px; }"
                        "QMenuBar::item { background:transparent; padding:6px 10px; border-radius:0px; }"
                        "QMenuBar::item:selected { background:#edf4ff; color:#111827; }"
                    )
                else:
                    mb.setStyleSheet(
                        "QMenuBar { background-color:#1d1f23; color:#f2f4f8; border-bottom:1px solid #303640; padding:2px 4px; }"
                        "QMenuBar::item { background:transparent; padding:6px 10px; border-radius:0px; }"
                        "QMenuBar::item:selected { background:#303640; color:#ffffff; }"
                    )
                mb.update()
        except Exception:
            pass

        try:
            self.apply_project_exit_button_theme()
        except Exception:
            pass

        try:
            self.apply_log_panel_theme()
        except Exception:
            pass

    def force_theme_repaint_after_apply(self):
        # 안전 원칙: 테마 적용은 1회만 수행한다.
        # 지연 타이머, processEvents, activateWindow/raise_, 네이티브 프레임 Redraw는 사용하지 않는다.
        self.refresh_top_bars_for_theme()
        try:
            self.update()
        except Exception:
            pass

    def open_theme_settings_dialog(self):
        """옵션 > 테마 설정."""
        old_theme = str(getattr(self, "ui_theme", THEME_DARK) or THEME_DARK).lower()
        if old_theme not in (THEME_DARK, THEME_LIGHT):
            old_theme = THEME_DARK

        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr_ui("테마 설정"))
        dialog.resize(360, 170)
        layout = QVBoxLayout(dialog)

        label = QLabel(self.tr_ui("화면에 적용할 테마를 선택하세요.\n확인을 누르면 즉시 적용되고, 닫기를 누르면 변경하지 않습니다."))
        label.setWordWrap(True)
        layout.addWidget(label)

        combo = QComboBox(dialog)
        combo.addItem(self.tr_ui("다크 테마"), THEME_DARK)
        combo.addItem(self.tr_ui("화이트 테마"), THEME_LIGHT)
        combo.setCurrentIndex(0 if old_theme == THEME_DARK else 1)
        layout.addWidget(combo)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dialog)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr_ui("확인"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(self.tr_ui("닫기"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        # 현재 테마에 맞춰 설정창도 어색하지 않게 표시한다.
        if old_theme == THEME_LIGHT:
            dialog.setStyleSheet("""
                QDialog { background:#f6f7f9; color:#202124; }
                QLabel { color:#202124; }
                QComboBox { background:#ffffff; color:#202124; border:1px solid #b9bec7; padding:4px; }
                QPushButton { background:#ffffff; color:#202124; border:1px solid #aeb4bf; padding:5px 14px; }
                QPushButton:hover { background:#e9eef7; }
            """)
        else:
            dialog.setStyleSheet("""
                QDialog { background:#1f1f22; color:#f2f2f2; }
                QLabel { color:#f2f2f2; }
                QComboBox { background:#2d2f34; color:#f5f5f5; border:1px solid #53565f; padding:4px; }
                QPushButton { background:#353841; color:#f2f2f2; border:1px solid #5a5d66; padding:5px 14px; }
                QPushButton:hover { background:#424652; }
            """)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected = str(combo.currentData() or THEME_DARK)
        if selected not in (THEME_DARK, THEME_LIGHT):
            selected = THEME_DARK
        self.ui_theme = selected
        self.save_app_options_cache()
        self.apply_theme(selected)
        self.log(f"🎨 테마 변경: {'화이트 테마' if selected == THEME_LIGHT else '다크 테마'}")

    def apply_native_title_bar_theme(self, widget=None, dark=None):
        """Windows 네이티브 제목 표시줄 테마 적용은 공개판에서 비활성화한다.

        DwmSetWindowAttribute/SetWindowPos/RedrawWindow 같은 비클라이언트 영역 갱신은
        Windows와 Qt의 포커스 이벤트를 계속 흔들 수 있다. 색상 일치보다 입력 안정성을
        우선하므로 제목 표시줄은 OS 기본 동작에 맡긴다.
        """
        return

    def schedule_native_title_bar_theme(self, widget=None, dark=None):
        """네이티브 제목 표시줄 지연 갱신 비활성화.
        최소화/복원/전체화면 전환 뒤 버벅임과 먹통을 막기 위해 아무 작업도 하지 않는다.
        """
        return

    def apply_tooltip_theme(self, light=None):
        """QToolTip은 OS/Qt 기본 팔레트 영향을 많이 받아 글자색이 흐려질 수 있다.
        테마 적용 시마다 팔레트와 앱 스타일시트를 같이 고정해 대비를 보장한다.
        """
        if light is None:
            light = self.is_light_theme() if hasattr(self, "is_light_theme") else False

        app = QApplication.instance()
        if light:
            bg = QColor("#ffffff")
            fg = QColor("#111827")
            border = "#cfd7e5"
        else:
            bg = QColor("#1f2430")
            fg = QColor("#ffffff")
            border = "#4b5563"

        pal = QPalette()
        pal.setColor(QPalette.ColorRole.ToolTipBase, bg)
        pal.setColor(QPalette.ColorRole.ToolTipText, fg)
        try:
            QToolTip.setPalette(pal)
        except Exception:
            pass

        if app:
            try:
                app.setStyleSheet(
                    "QToolTip { "
                    f"background-color:{bg.name()}; "
                    f"color:{fg.name()}; "
                    f"border:1px solid {border}; "
                    "border-radius:0px; "
                    "padding:5px; "
                    "}"
                )
            except Exception:
                pass

    def apply_light_theme(self):
        """화이트 테마를 부드러운 카드형 톤으로 적용한다."""
        app = QApplication.instance()
        if app:
            app.setStyleSheet("""
                QToolTip { background-color:#ffffff; color:#111827; border:1px solid #cfd7e5; border-radius:0px; padding:5px; }
            """)
            pal = QPalette()
            pal.setColor(QPalette.ColorRole.Window, QColor("#f4f6fa"))
            pal.setColor(QPalette.ColorRole.WindowText, QColor("#22252b"))
            pal.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
            pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#f7f9fd"))
            pal.setColor(QPalette.ColorRole.Text, QColor("#22252b"))
            pal.setColor(QPalette.ColorRole.Button, QColor("#f8fafc"))
            pal.setColor(QPalette.ColorRole.ButtonText, QColor("#22252b"))
            pal.setColor(QPalette.ColorRole.Highlight, QColor("#dbeafe"))
            pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#111827"))
            pal.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffff"))
            pal.setColor(QPalette.ColorRole.ToolTipText, QColor("#111827"))
            app.setPalette(pal)
            self.apply_tooltip_theme(light=True)

        self.setStyleSheet("""
            QMainWindow, QWidget { background-color:#f4f6fa; color:#22252b; }
            QMenuBar {
                background-color:#ffffff;
                color:#22252b;
                border-bottom:1px solid #e0e6f0;
                padding:2px 4px;
            }
            QMenuBar::item { background:transparent; padding:6px 10px; border-radius:0px; }
            QMenuBar::item:selected { background:#edf4ff; }
            QMenu {
                background-color:#ffffff;
                color:#22252b;
                border:1px solid #dfe5ef;
                border-radius:0px;
                padding:6px;
            }
            QMenu::separator { height:1px; background:#e3e8f1; margin:6px 6px; }
            QMenu::item { padding:7px 28px 7px 12px; border-radius:0px; }
            QMenu::item:selected { background-color:#edf4ff; color:#111827; }
            QMessageBox { background:#f4f6fa; color:#111827; }
            QMessageBox QLabel { color:#111827; }
            QMessageBox QPushButton { background:#ffffff; color:#111827; border:1px solid #cfd7e5; border-radius:0px; padding:4px 10px; min-width:56px; }
            QMessageBox QPushButton:hover { background:#edf4ff; border-color:#aac4e8; }
            QLabel, QCheckBox, QRadioButton, QGroupBox { color:#22252b; }
            QGroupBox {
                border:1px solid #dfe5ef;
                border-radius:0px;
                margin-top:12px;
                padding:10px;
                background:#ffffff;
            }
            QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 5px; color:#374151; }
            QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QFontComboBox, QSpinBox, QDoubleSpinBox, QKeySequenceEdit {
                background-color:#ffffff;
                color:#22252b;
                border:1px solid #cfd7e5;
                border-radius:0px;
                padding:3px 6px;
                selection-background-color:#dbeafe;
                selection-color:#111827;
            }
            QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QFontComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QKeySequenceEdit:focus {
                border:1px solid #8fb4e8;
            }
            QAbstractItemView {
                background-color:#ffffff;
                color:#22252b;
                border:1px solid #dfe5ef;
                border-radius:0px;
                alternate-background-color:#f7f9fd;
                selection-background-color:#dbeafe;
                selection-color:#111827;
                gridline-color:#e4eaf3;
            }
            QHeaderView::section {
                background-color:#f1f4f9;
                color:#374151;
                border:0;
                border-right:1px solid #dfe5ef;
                padding:7px;
            }
            QPushButton {
                background-color:#f8fafc;
                color:#22252b;
                border:1px solid #cfd7e5;
                border-radius:0px;
                padding:4px 10px;
            }
            QPushButton:hover { background-color:#edf4ff; border-color:#aac4e8; }
            QPushButton:pressed { background-color:#e3edf9; }
            QPushButton:disabled { background-color:#edf0f5; color:#9aa4b2; border-color:#dde3ec; }
            QToolBar {
                background-color:#eef2f8;
                border:1px solid #dfe5ef;
                border-radius:0px;
                spacing:5px;
                padding:4px;
            }
            QToolButton {
                background-color:#f8fafc;
                color:#22252b;
                border:1px solid #cfd7e5;
                border-radius:0px;
                padding:5px;
            }
            QToolButton:hover { background-color:#edf4ff; border-color:#aac4e8; }
            QToolButton:checked { background-color:#dbeafe; border-color:#8fb4e8; }
            QCheckBox::indicator, QRadioButton::indicator {
                width:15px; height:15px;
                border:1px solid #aab4c3;
                background:#ffffff;
                border-radius:0px;
            }
            QRadioButton::indicator { border-radius:0px; }
            QCheckBox::indicator:checked, QRadioButton::indicator:checked { background:#7aa8e8; border:1px solid #7aa8e8; }
            QSplitter::handle { background:#dfe5ef; }
            QTabWidget::pane { border:1px solid #dfe5ef; border-radius:0px; background:#ffffff; }
            QTabBar::tab {
                background:#edf1f7;
                color:#4b5563;
                padding:8px 12px;
                border:1px solid #d9e0ea;
                border-bottom:none;
                border-top-left-radius:10px;
                border-top-right-radius:3px;
            }
            QTabBar::tab:selected { background:#ffffff; color:#1f232b; font-weight:bold; }
            QTabBar::tab:hover { background:#edf4ff; }
            QScrollBar:vertical { background:#eef2f8; width:12px; margin:0; border:0; border-radius:0px; }
            QScrollBar::handle:vertical { background:#cbd5e1; min-height:30px; border-radius:0px; }
            QScrollBar::handle:vertical:hover { background:#b7c3d4; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
            QScrollBar:horizontal { background:#eef2f8; height:12px; margin:0; border:0; border-radius:0px; }
            QScrollBar::handle:horizontal { background:#cbd5e1; min-width:30px; border-radius:0px; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }
            QToolTip { background-color:#ffffff; color:#111827; border:1px solid #cfd7e5; border-radius:0px; padding:5px; }
        """)
        if hasattr(self, 'tb') and self.tb:
            self.tb.setStyleSheet("background:#eef2f8; border:1px solid #dfe5ef; border-radius:0px;")
        if hasattr(self, 'mask_toggle_wrap') and self.mask_toggle_wrap:
            self.mask_toggle_wrap.setStyleSheet("")
        if hasattr(self, 'btn_page') and self.btn_page:
            self.btn_page.setStyleSheet("border:none; font-weight:bold; color:#22252b;")
        self.apply_page_tab_style()
        self.apply_text_style_button_styles()
        if hasattr(self, 'tab') and self.tab:
            self.tab.setStyleSheet(
                "QTableWidget { background:#ffffff; color:#22252b; gridline-color:#e4eaf3; border:1px solid #dfe5ef; border-radius:0px; }"
                "QTableWidget::item:selected { background:#dbeafe; color:#111827; }"
                "QTableWidget QTableCornerButton::section { background:#f1f4f9; border:1px solid #dfe5ef; }"
            )
            self.repaint_text_table_theme()
        self.apply_log_panel_theme()
        self.update_color_button_styles()
        self.schedule_native_title_bar_theme(self, dark=False)

    def apply_dark_theme(self):
        """다크 테마를 홈/클라우드와 맞는 부드러운 카드형 톤으로 적용한다."""
        app = QApplication.instance()
        if app:
            app.setStyleSheet("""
                QToolTip { background-color:#1f2430; color:#ffffff; border:1px solid #4b5563; border-radius:0px; padding:5px; }
            """)
            pal = QPalette()
            pal.setColor(QPalette.ColorRole.Window, QColor("#202226"))
            pal.setColor(QPalette.ColorRole.WindowText, QColor("#f2f4f8"))
            pal.setColor(QPalette.ColorRole.Base, QColor("#24282f"))
            pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#282d35"))
            pal.setColor(QPalette.ColorRole.Text, QColor("#f2f4f8"))
            pal.setColor(QPalette.ColorRole.Button, QColor("#333843"))
            pal.setColor(QPalette.ColorRole.ButtonText, QColor("#f2f4f8"))
            pal.setColor(QPalette.ColorRole.Highlight, QColor("#3d587d"))
            pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
            pal.setColor(QPalette.ColorRole.ToolTipBase, QColor("#1f2430"))
            pal.setColor(QPalette.ColorRole.ToolTipText, QColor("#ffffff"))
            app.setPalette(pal)

        self.setStyleSheet("""
            QMainWindow, QWidget { background-color:#202226; color:#f2f4f8; }
            QMenuBar {
                background-color:#1d1f23;
                color:#f2f4f8;
                border-bottom:1px solid #303640;
                padding:2px 4px;
            }
            QMenuBar::item { background:transparent; padding:6px 10px; border-radius:0px; }
            QMenuBar::item:selected { background:#303640; }
            QMenu {
                background-color:#282c33;
                color:#f2f4f8;
                border:1px solid #3b414c;
                border-radius:0px;
                padding:6px;
            }
            QMenu::separator { height:1px; background:#3b414c; margin:6px 6px; }
            QMenu::item { padding:7px 28px 7px 12px; border-radius:0px; }
            QMenu::item:selected { background-color:#38404c; color:#ffffff; }
            QMessageBox { background:#24272d; color:#f2f4f8; }
            QMessageBox QLabel { color:#f2f4f8; }
            QMessageBox QPushButton { background:#333843; color:#f2f4f8; border:1px solid #586173; border-radius:0px; padding:4px 10px; min-width:56px; }
            QMessageBox QPushButton:hover { background:#3d4654; border-color:#74839a; }
            QLabel, QCheckBox, QRadioButton, QGroupBox { color:#f2f4f8; }
            QGroupBox {
                border:1px solid #3b414c;
                border-radius:0px;
                margin-top:12px;
                padding:10px;
                background:#282c33;
            }
            QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 5px; color:#d7deea; }
            QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QFontComboBox, QSpinBox, QDoubleSpinBox, QKeySequenceEdit {
                background-color:#1f2228;
                color:#f5f7fb;
                border:1px solid #434a56;
                border-radius:0px;
                padding:3px 6px;
                selection-background-color:#4c6f9f;
                selection-color:#ffffff;
            }
            QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QFontComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QKeySequenceEdit:focus {
                border:1px solid #7ea2d6;
                background:#222630;
            }
            QAbstractItemView {
                background-color:#24282f;
                color:#f2f4f8;
                border:1px solid #3b414c;
                border-radius:0px;
                alternate-background-color:#282d35;
                selection-background-color:#3d587d;
                selection-color:#ffffff;
                gridline-color:#38404a;
            }
            QHeaderView::section {
                background-color:#2d323b;
                color:#d7deea;
                border:0;
                border-right:1px solid #3b414c;
                padding:7px;
            }
            QPushButton {
                background-color:#333843;
                color:#f2f4f8;
                border:1px solid #555d6c;
                border-radius:0px;
                padding:4px 10px;
            }
            QPushButton:hover { background-color:#3d4654; border-color:#718098; }
            QPushButton:pressed { background-color:#2b303a; }
            QPushButton:disabled { background-color:#2a2d33; color:#858d9a; border-color:#3f4550; }
            QToolBar {
                background-color:#24282f;
                border:1px solid #3b414c;
                border-radius:0px;
                spacing:5px;
                padding:4px;
            }
            QToolButton {
                background-color:#333843;
                color:#f2f4f8;
                border:1px solid #555d6c;
                border-radius:0px;
                padding:5px;
            }
            QToolButton:hover { background-color:#3d4654; border-color:#718098; }
            QToolButton:checked { background-color:#3d587d; border-color:#7ea2d6; }
            QCheckBox::indicator, QRadioButton::indicator {
                width:15px; height:15px;
                border:1px solid #6f7786;
                background:#1f2228;
                border-radius:0px;
            }
            QRadioButton::indicator { border-radius:0px; }
            QCheckBox::indicator:checked, QRadioButton::indicator:checked { background:#78a6e6; border:1px solid #78a6e6; }
            QSplitter::handle { background:#303640; }
            QTabWidget::pane { border:1px solid #3b414c; border-radius:0px; background:#24282f; }
            QTabBar::tab {
                background:#2a2e36;
                color:#b5bfce;
                padding:8px 12px;
                border:1px solid #3b414c;
                border-bottom:none;
                border-top-left-radius:10px;
                border-top-right-radius:3px;
            }
            QTabBar::tab:selected { background:#333842; color:#ffffff; font-weight:bold; }
            QTabBar::tab:hover { background:#38404c; }
            QScrollBar:vertical { background:#20242b; width:12px; margin:0; border:0; border-radius:0px; }
            QScrollBar::handle:vertical { background:#424a57; min-height:30px; border-radius:0px; }
            QScrollBar::handle:vertical:hover { background:#566173; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
            QScrollBar:horizontal { background:#20242b; height:12px; margin:0; border:0; border-radius:0px; }
            QScrollBar::handle:horizontal { background:#424a57; min-width:30px; border-radius:0px; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }
            QToolTip { background-color:#1f2430; color:#ffffff; border:1px solid #4b5563; border-radius:0px; padding:5px; }
        """)
        if hasattr(self, 'tb') and self.tb:
            self.tb.setStyleSheet("background:#24282f; border:1px solid #3b414c; border-radius:0px;")
        if hasattr(self, 'mask_toggle_wrap') and self.mask_toggle_wrap:
            self.mask_toggle_wrap.setStyleSheet("")
        if hasattr(self, 'btn_page') and self.btn_page:
            self.btn_page.setStyleSheet("border:none; font-weight:bold; color:#f2f4f8;")
        self.apply_page_tab_style()
        self.apply_text_style_button_styles()
        if hasattr(self, 'tab') and self.tab:
            self.tab.setStyleSheet(
                "QTableWidget { background:#24282f; color:#f2f4f8; gridline-color:#38404a; border:1px solid #3b414c; border-radius:0px; }"
                "QTableWidget::item:selected { background:#3d587d; color:#ffffff; }"
                "QTableWidget QTableCornerButton::section { background:#2d323b; border:1px solid #3b414c; }"
            )
            self.repaint_text_table_theme()
        self.apply_log_panel_theme()
        self.update_color_button_styles()

    def make_color_icon(self, color_value):
        pix = QPixmap(22, 22)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        c = QColor(str(color_value or "#FFFFFF"))
        if not c.isValid():
            c = QColor("#FFFFFF")
        painter.setPen(QPen(QColor("#777777"), 1))
        painter.setBrush(QBrush(c))
        painter.drawRect(2, 2, 18, 18)
        painter.end()
        return QIcon(pix)

    def update_color_button_styles(self):
        pairs = [
            (getattr(self, "btn_text_color", None), self.default_text_color, "문자 색상"),
            (getattr(self, "btn_stroke_color", None), self.default_stroke_color, "획 색상"),
            (getattr(self, "btn_item_text_color", None), self.default_text_color, "문자 색상"),
            (getattr(self, "btn_item_stroke_color", None), self.default_stroke_color, "획 색상"),
        ]
        for btn, color, tooltip in pairs:
            if btn:
                btn.setText("")
                btn.setStatusTip(f"{tooltip}: {color}")
                try:
                    btn.setProperty("force_outlined_tooltip_text", True)
                    btn.setProperty("force_color_tooltip_text", True)
                except Exception:
                    pass
                btn.setFixedSize(26, 26)
                tip_bg = "#ffffff" if self.is_light_theme() else "#000000"
                tip_fg = "#111827" if self.is_light_theme() else "#ffffff"
                tip_border = "#cfd7e5" if self.is_light_theme() else "#4b5563"
                btn.setStyleSheet(
                    f"QPushButton {{ background:{color}; border:1px solid #555d6c; border-radius:0px; padding:0px; }}"
                    f"QPushButton:hover {{ border:1px solid #9cc2ff; }}"
                    f"QToolTip {{ background-color:{tip_bg}; color:{tip_fg}; border:1px solid {tip_border}; border-radius:0px; padding:5px; }}"
                )

        if hasattr(self, "act_final_paint_color"):
            self.act_final_paint_color.setIcon(self.make_color_icon(self.final_paint_color))
            self.act_final_paint_color.setText("")
            self.act_final_paint_color.setStatusTip(f"최종 페인팅 색상: {self.final_paint_color}")
            try:
                w = self.tb.widgetForAction(self.act_final_paint_color) if hasattr(self, "tb") else None
                if w is not None:
                    w.setProperty("force_outlined_tooltip_text", True)
                    w.setProperty("force_color_tooltip_text", True)
                    tip_bg = "#ffffff" if self.is_light_theme() else "#000000"
                    tip_fg = "#111827" if self.is_light_theme() else "#ffffff"
                    tip_border = "#cfd7e5" if self.is_light_theme() else "#4b5563"
                    w.setStyleSheet(
                        f"QToolButton {{ border:1px solid #3b414c; border-radius:0px; padding:2px; }}"
                        f"QToolTip {{ background-color:{tip_bg}; color:{tip_fg}; border:1px solid {tip_border}; border-radius:0px; padding:5px; }}"
                    )
            except Exception:
                pass

