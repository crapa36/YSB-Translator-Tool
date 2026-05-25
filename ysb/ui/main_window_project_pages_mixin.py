from ysb.ui.main_window_support import *


class MainWindowProjectPagesMixin:

    def selected_text_items(self):
        if getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
            return []
        scene = self._safe_graphics_scene()
        if scene is None:
            return []
        try:
            return [item for item in scene.selectedItems() if isinstance(item, TypesettingItem)]
        except RuntimeError:
            return []
        except Exception:
            return []

    def _set_widget_value_blocked(self, widget, value):
        """프로그램이 UI 값을 채울 때 valueChanged 재발동/포커스 튐을 막는다."""
        if widget is None:
            return
        blocker = None
        try:
            blocker = QSignalBlocker(widget)
        except Exception:
            blocker = None
        try:
            widget.setValue(value)
        except Exception:
            pass
        finally:
            try:
                del blocker
            except Exception:
                pass

    def _set_widget_checked_blocked(self, widget, checked):
        if widget is None:
            return
        blocker = None
        try:
            blocker = QSignalBlocker(widget)
        except Exception:
            blocker = None
        try:
            widget.setChecked(bool(checked))
        except Exception:
            pass
        finally:
            try:
                del blocker
            except Exception:
                pass

    def calculate_tight_text_scene_rect(self, data_item):
        """data_item의 현재 번역문/스타일이 실제로 차지하는 scene rect를 계산한다.

        OCR 원본 박스는 처음 배치용으로 유지하되, 사용자가 텍스트를 한 번 수정하면
        그 이후의 선택/변형 박스는 실제 텍스트 크기에 맞게 축소되어야 한다.
        Qt 문서 boundingRect 대신 TypesettingItem과 같은 QPainterPath 기준을 사용한다.
        """
        if not isinstance(data_item, dict):
            return None
        text = str(data_item.get('translated_text', '') or '')
        lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        if not lines:
            lines = ['']

        try:
            fallback_family = self.cb_font.currentFont().family() if hasattr(self, 'cb_font') else 'Arial'
        except Exception:
            fallback_family = 'Arial'
        try:
            fallback_size = int(self.sb_font_size.value()) if hasattr(self, 'sb_font_size') else 24
        except Exception:
            fallback_size = 24

        font = QFont(str(data_item.get('font_family') or fallback_family))
        try:
            font.setPixelSize(int(data_item.get('font_size', fallback_size) or fallback_size))
        except Exception:
            font.setPixelSize(fallback_size)
        try:
            font.setBold(bool(data_item.get('bold', False)))
            font.setItalic(bool(data_item.get('italic', False)))
            letter_spacing = int(data_item.get('letter_spacing', 0) or 0)
        except Exception:
            pass

        try:
            line_spacing_pct = max(50, min(300, int(data_item.get('line_spacing', 100) or 100)))
        except Exception:
            line_spacing_pct = 100
        try:
            char_width_pct = max(10, min(300, int(data_item.get('char_width', 100) or 100)))
        except Exception:
            char_width_pct = 100
        try:
            char_height_pct = max(10, min(300, int(data_item.get('char_height', 100) or 100)))
        except Exception:
            char_height_pct = 100

        align = (data_item.get('align') or getattr(self, 'default_align', 'center') or 'center').lower()
        if align not in ('left', 'center', 'right'):
            align = 'center'

        fm = QFontMetrics(font)
        line_height = max(1, int(fm.lineSpacing() * (line_spacing_pct / 100.0)))
        path, _line_rects = build_typesetting_text_path(lines, font, align, line_height, letter_spacing)

        if char_width_pct != 100 or char_height_pct != 100:
            tr = QTransform()
            tr.scale(char_width_pct / 100.0, char_height_pct / 100.0)
            path = tr.map(path)

        path_rect = path.boundingRect()
        if path_rect.isNull() or path_rect.width() <= 0 or path_rect.height() <= 0:
            path_rect = QRectF(0, 0, 1, max(1, fm.height()))

        rect = list(data_item.get('rect') or [0, 0, 1, 1])
        while len(rect) < 4:
            rect.append(1)
        x_off = float(data_item.get('x_off', 0) or 0)
        y_off = float(data_item.get('y_off', 0) or 0)
        rect_x = float(rect[0])
        rect_y = float(rect[1])
        rect_w = max(1.0, float(rect[2]))
        rect_h = max(1.0, float(rect[3]))
        text_w = max(1.0, float(path_rect.width()))
        text_h = max(1.0, float(path_rect.height()))

        if align == 'left':
            anchor_x = rect_x + x_off
            left = anchor_x
        elif align == 'right':
            anchor_x = rect_x + x_off + rect_w
            left = anchor_x - text_w
        else:
            anchor_x = rect_x + x_off + rect_w / 2.0
            left = anchor_x - text_w / 2.0

        # v1.6.3+: 텍스트는 영역의 세로 중심에 배치된다.
        anchor_y = rect_y + y_off + rect_h / 2.0
        top = anchor_y - text_h / 2.0

        return QRectF(left, top, text_w, text_h)

    def shrink_text_rect_to_content(self, data_item):
        """텍스트 수정 후 작업/변형 박스를 실제 텍스트 크기로 줄인다."""
        return self.ensure_text_anchor_rect(data_item, record_undo=False)

    def ensure_text_anchor_rect(self, data_item, record_undo=False, reason="텍스트 영역 자동 재생성"):
        """현재 보이는 실제 텍스트 bounds를 새 텍스트 영역으로 확정한다.

        초기 OCR 영역은 최초 배치용 기준일 뿐이다. 텍스트 직접 수정 또는
        텍스트 변형 모드 진입 시점에는 현재 화면에 보이는 실제 글자 영역을
        기준으로 rect를 다시 만들고, 이후 선택/변형 박스가 이 영역을 보게 한다.
        """
        if not isinstance(data_item, dict):
            return False
        rect = self.calculate_tight_text_scene_rect(data_item)
        if rect is None:
            return False

        new_rect = [
            int(round(rect.x())),
            int(round(rect.y())),
            max(1, int(round(rect.width()))),
            max(1, int(round(rect.height()))),
        ]
        old_rect = list(data_item.get('rect') or [])
        while len(old_rect) < 4:
            old_rect.append(0)
        try:
            old_rect4 = [int(round(float(v))) for v in old_rect[:4]]
        except Exception:
            old_rect4 = old_rect[:4]
        old_x = int(round(float(data_item.get('x_off', 0) or 0)))
        old_y = int(round(float(data_item.get('y_off', 0) or 0)))
        already_text_anchor = bool(data_item.get('manual_text_rect')) or str(data_item.get('text_anchor_mode') or '').lower() == 'text'
        changed = (
            old_rect4 != new_rect
            or old_x != 0
            or old_y != 0
            or not already_text_anchor
        )
        if not changed:
            return False

        if record_undo:
            try:
                self.push_page_text_undo(reason)
            except Exception:
                pass

        data_item['rect'] = new_rect
        data_item['x_off'] = 0
        data_item['y_off'] = 0
        data_item['manual_text_rect'] = True
        data_item['text_anchor_mode'] = 'text'
        return True

    def reset_text_rects_current(self):
        """현재 페이지의 모든 텍스트 영역을 현재 보이는 텍스트 bounds 기준으로 재생성한다."""
        if not self.paths or self.idx not in self.data:
            self.log("⚠️ 영역을 재설정할 현재 페이지가 없습니다.")
            return

        # 최종화면에서 드래그 이동한 좌표가 아직 data에 완전히 박히기 전일 수 있으므로
        # 먼저 현재 UI 상태를 data에 동기화한 뒤, 그 상태를 Undo 기준으로 저장한다.
        try:
            self.commit_current_page_ui_to_data(include_mask=False)
        except Exception:
            pass

        curr = self.data.get(self.idx) or {}
        items = [d for d in (curr.get('data', []) or []) if isinstance(d, dict)]
        if not items:
            self.log("⚠️ 영역을 재설정할 텍스트가 없습니다.")
            return

        undo_rec = self.make_project_undo_record("현재 텍스트 기준 영역 재설정")
        changed = 0
        for d in items:
            try:
                if self.ensure_text_anchor_rect(d, record_undo=False, reason="현재 텍스트 기준 영역 재설정"):
                    changed += 1
            except Exception:
                continue

        if changed <= 0:
            self.log("↩️ 현재 텍스트 기준 영역 재설정: 변경된 영역이 없습니다.")
            return

        self.append_project_undo_record(undo_rec)
        self.auto_save_project()
        self.ref_tab()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
        self.log(f"📐 현재 텍스트 기준 영역 재설정 완료: {changed}개")

    def reset_text_rects_batch(self):
        """전체 페이지의 모든 텍스트 영역을 현재 텍스트 bounds 기준으로 일괄 재생성한다."""
        if not self.paths or not self.data:
            self.log("⚠️ 영역을 재설정할 프로젝트가 없습니다.")
            return

        try:
            self.commit_current_page_ui_to_data(include_mask=False)
        except Exception:
            pass

        total_candidates = 0
        try:
            for page_data in (self.data or {}).values():
                if isinstance(page_data, dict):
                    total_candidates += sum(1 for d in (page_data.get('data', []) or []) if isinstance(d, dict))
        except Exception:
            total_candidates = 0
        if total_candidates <= 0:
            self.log("⚠️ 영역을 재설정할 텍스트가 없습니다.")
            return

        msg = f"전체 {len(self.paths)}페이지의 텍스트 영역을 현재 텍스트 기준으로 다시 만들까요?\n총 {total_candidates}개 텍스트가 대상입니다."
        if not self.confirm_batch_operation("일괄 텍스트 기준 영역 재설정", msg):
            self.log("↩️ 일괄 텍스트 기준 영역 재설정 취소")
            return

        undo_rec = self.make_project_undo_record("일괄 텍스트 기준 영역 재설정", full_project=True)
        changed_pages = 0
        changed_total = 0
        old_batch = getattr(self, "is_batch_running", False)
        self.is_batch_running = True
        try:
            for page_idx in sorted((self.data or {}).keys()):
                page_data = self.data.get(page_idx)
                if not isinstance(page_data, dict):
                    continue
                page_changed = 0
                for d in (page_data.get('data', []) or []):
                    if not isinstance(d, dict):
                        continue
                    try:
                        if self.ensure_text_anchor_rect(d, record_undo=False, reason="일괄 텍스트 기준 영역 재설정"):
                            page_changed += 1
                    except Exception:
                        continue
                if page_changed:
                    changed_pages += 1
                    changed_total += page_changed
        finally:
            self.is_batch_running = old_batch

        if changed_total <= 0:
            self.log("↩️ 일괄 텍스트 기준 영역 재설정: 변경된 영역이 없습니다.")
            return

        self.append_project_undo_record(undo_rec)
        self.auto_save_project()
        self.ref_tab()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
        self.log(f"📐 일괄 텍스트 기준 영역 재설정 완료: {changed_pages}페이지 / {changed_total}개")

    def start_inline_text_edit(self, text_item, select_all=False):
        """최종 화면 텍스트를 더블클릭/F2 했을 때 그 자리에서 직접 편집한다."""
        if self.cb_mode.currentIndex() != 4:
            return

        if self.inline_text_editor is not None:
            self.finish_inline_text_edit(commit=True, refresh=False)

        if text_item is None:
            return
        if bool(getattr(text_item, 'data', {}).get('rasterized_text')):
            self.log("⚠️ " + self.tr_ui("객체로 변환된 텍스트는 내용을 직접 수정할 수 없습니다."))
            return

        self.inline_text_target = text_item
        text_item.setSelected(True)

        # 마지막 식자 단계의 직접 수정이므로, 기존 OCR 박스가 아니라 현재 실제 텍스트를 기준으로 편집을 시작한다.
        if hasattr(text_item, 'text_content_scene_rect'):
            scene_rect = text_item.text_content_scene_rect()
        else:
            local_rect = text_item.text_area_rect()
            scene_rect = text_item.mapToScene(local_rect).boundingRect()

        editor = InlineTextEditItem(self, text_item, scene_rect)
        self.inline_text_editor = editor

        text_item.setVisible(False)
        self.view.scene.addItem(editor)
        editor.setFocus(Qt.FocusReason.MouseFocusReason)

        cursor = editor.textCursor()
        cursor.clearSelection()
        if select_all:
            cursor.select(QTextCursor.SelectionType.Document)
        else:
            cursor.movePosition(QTextCursor.MoveOperation.End)
        editor.setTextCursor(cursor)

        self.log(f"✏️ 텍스트 직접 편집 시작 (ID: {text_item.data.get('id')})")

    def finish_inline_text_edit(self, commit=True, refresh=True):
        editor = self.inline_text_editor
        target = self.inline_text_target
        if editor is None:
            return

        is_closing = bool(getattr(self, "_app_is_closing", False))
        try:
            editor._closing = True
        except Exception:
            pass

        # Qt 종료/탭 재구성 타이밍에 QGraphicsTextItem의 C++ 객체가 먼저 삭제될 수 있다.
        # 이 상태에서 toPlainText()/scene()/removeItem() 등을 호출하면
        # "wrapped C/C++ object ... has been deleted"가 나므로 조용히 포인터만 정리한다.
        try:
            _ = editor.toPlainText()
        except RuntimeError:
            self.inline_text_editor = None
            self.inline_text_target = None
            return
        except Exception:
            pass

        selected_id = target.data.get('id') if target is not None else None
        pending_new = bool(target is not None and target.data.get('pending_new_text'))

        changed = False
        added_new = False
        canceled_new = False

        if commit and target is not None:
            try:
                new_text = editor.toPlainText()
            except RuntimeError:
                self.inline_text_editor = None
                self.inline_text_target = None
                return
            changed = (new_text != getattr(editor, 'original_text', ''))

            if pending_new and not str(new_text or '').strip():
                canceled_new = True
                changed = False
                self.log(f"↩️ 새 텍스트 입력 취소 (ID: {target.data.get('id')})")
            elif changed or pending_new:
                self.push_page_text_undo('텍스트 직접 수정' if not pending_new else '새 텍스트 추가')
                target.data['translated_text'] = new_text
                target.data.pop('force_show', None)
                target.data.pop('pending_new_text', None)

                # 직접 수정한 경우에는 기존 OCR 박스가 아니라 현재 편집 텍스트 자체를 기준으로
                # 텍스트 영역을 다시 잡는다. QGraphicsTextItem의 boundingRect()가 아래쪽에
                # 여분 한 줄을 남기는 경우를 피하기 위해 adjusted_scene_rect()의 타이트 계산을 쓴다.
                try:
                    edit_rect = editor.adjusted_scene_rect()
                    if edit_rect.width() > 1 and edit_rect.height() > 1:
                        target.data['rect'] = [
                            int(round(edit_rect.x())),
                            int(round(edit_rect.y())),
                            max(1, int(round(edit_rect.width()))),
                            max(1, int(round(edit_rect.height()))),
                        ]
                        target.data['x_off'] = 0
                        target.data['y_off'] = 0
                        target.data['manual_text_rect'] = True
                        target.data['text_anchor_mode'] = 'text'
                    else:
                        self.shrink_text_rect_to_content(target.data)
                except Exception:
                    try:
                        self.shrink_text_rect_to_content(target.data)
                    except Exception:
                        pass

                if pending_new:
                    curr = self.data.get(self.idx)
                    if curr is not None and target.data not in curr.setdefault('data', []):
                        curr['data'].append(target.data)
                        added_new = True
                    changed = True
                else:
                    target_id = str(target.data.get('id'))
                    self.tab.blockSignals(True)
                    try:
                        for row in range(1, self.tab.rowCount()):
                            id_item = self.tab.item(row, 0)
                            if id_item and id_item.text().strip() == target_id:
                                self.tab.setItem(row, 3, QTableWidgetItem(new_text))
                                break
                    finally:
                        self.tab.blockSignals(False)

            if changed:
                self.tab.resizeRowsToContents()
                self.auto_save_project()
                if added_new:
                    self.log(f"✅ 새 텍스트 추가 완료 (ID: {target.data.get('id')})")
                else:
                    self.log(f"✅ 텍스트 직접 수정 완료 (ID: {target.data.get('id')})")
            elif not canceled_new:
                self.log(f"↩️ 텍스트 직접 수정 변화 없음 (ID: {target.data.get('id')})")
        elif target is not None:
            if pending_new:
                canceled_new = True
                self.log(f"↩️ 새 텍스트 입력 취소 (ID: {target.data.get('id')})")
            else:
                self.log(f"↩️ 텍스트 직접 수정 취소 (ID: {target.data.get('id')})")

        try:
            if editor.scene() is not None:
                editor.scene().removeItem(editor)
        except Exception:
            pass

        if target is not None:
            try:
                if canceled_new and target.scene() is not None:
                    target.scene().removeItem(target)
                else:
                    target.setVisible(True)
            except Exception:
                pass

        self.inline_text_editor = None
        self.inline_text_target = None

        if (not is_closing) and commit and (changed or added_new) and refresh and self.cb_mode.currentIndex() == 4:
            self.ref_tab()
            self.mode_chg(4)
            if selected_id is not None and not canceled_new:
                self.reselect_text_items([selected_id])
        elif (not is_closing) and selected_id is not None and not canceled_new:
            self.reselect_text_items([selected_id])

    def on_scene_selection_changed(self):
        # 프로그램 종료/씬 재생성 중 selectionChanged가 뒤늦게 들어오면
        # 삭제된 QGraphicsScene에 접근하지 않고 조용히 무시한다.
        if getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
            return
        if self._safe_graphics_scene() is None:
            return

        active_transform = self.current_transform_data_item()
        if active_transform is not None:
            active_id = active_transform.get('id')
            items = self.selected_text_items()
            if not any(item.data.get('id') == active_id for item in items):
                self.reselect_text_items([active_id])
                items = self.selected_text_items()
        else:
            items = self.selected_text_items()
        ids = [item.data.get('id') for item in items]
        self.select_table_rows_by_ids(ids)
        if hasattr(self, 'final_edit_bar'):
            self.final_edit_bar.hide()
        self.update_text_style_control_state(items)
        try:
            if hasattr(self, "refresh_shared_option_bar"):
                self.refresh_shared_option_bar()
        except Exception:
            pass

        if not items or self._style_signal_lock:
            return

        d = items[0].data
        self._style_signal_lock = True
        try:
            self.cb_font.setCurrentFont(QFont(d.get('font_family') or self.cb_font.currentFont().family()))
            self._set_widget_value_blocked(self.sb_font_size, int(d.get('font_size', self.sb_font_size.value()) or self.sb_font_size.value()))
            self._set_widget_value_blocked(self.sb_strk, int(d.get('stroke_width', self.sb_strk.value()) or 0))
            if hasattr(self, 'final_item_font'):
                self.final_item_font.setCurrentFont(QFont(d.get('font_family') or self.final_item_font.currentFont().family()))
            if hasattr(self, 'final_item_size'):
                self._set_widget_value_blocked(self.final_item_size, int(d.get('font_size', self.sb_font_size.value()) or self.sb_font_size.value()))
            if hasattr(self, 'final_item_stroke'):
                self._set_widget_value_blocked(self.final_item_stroke, int(d.get('stroke_width', self.sb_strk.value()) or 0))
            self.default_text_color = d.get('text_color') or self.default_text_color
            self.default_stroke_color = d.get('stroke_color') or self.default_stroke_color
            self.default_align = d.get('align') or self.default_align
            if hasattr(self, "sb_line_spacing"):
                self._set_widget_value_blocked(self.sb_line_spacing, int(d.get('line_spacing', self.default_line_spacing) or self.default_line_spacing))
            if hasattr(self, "sb_letter_spacing"):
                self._set_widget_value_blocked(self.sb_letter_spacing, int(d.get('letter_spacing', self.default_letter_spacing) or self.default_letter_spacing))
            if hasattr(self, "sb_char_width"):
                self._set_widget_value_blocked(self.sb_char_width, int(d.get('char_width', self.default_char_width) or self.default_char_width))
            if hasattr(self, "sb_char_height"):
                self._set_widget_value_blocked(self.sb_char_height, int(d.get('char_height', self.default_char_height) or self.default_char_height))
            if hasattr(self, "btn_bold"):
                self._set_widget_checked_blocked(self.btn_bold, bool(d.get('bold', False)))
            if hasattr(self, "btn_italic"):
                self._set_widget_checked_blocked(self.btn_italic, bool(d.get('italic', False)))
            if hasattr(self, "btn_strike"):
                self._set_widget_checked_blocked(self.btn_strike, bool(d.get('strike', False)))
            if hasattr(self, "sb_text_opacity"):
                self._set_widget_value_blocked(self.sb_text_opacity, int(d.get('opacity', 100) or 100))
            self.update_color_button_styles()
            self.update_item_preset_combo_for_selected_texts()
            self.update_text_style_control_state(items)
        finally:
            self._style_signal_lock = False

    def apply_text_style_button_styles(self):
        if self.is_light_theme():
            base = (
                "QPushButton { background:#ffffff; color:#111827; border:1px solid #cfd7e5; border-radius:0px; }"
                "QPushButton:hover { background:#edf4ff; border-color:#9bbce8; }"
                "QPushButton:checked { background:#dbeafe; color:#0f172a; border:1px solid #6fa8ff; font-weight:700; }"
                "QPushButton:disabled { background:#f1f3f6; color:#9ca3af; border:1px solid #d9dee8; }"
            )
        else:
            base = (
                "QPushButton { background:#2f3540; color:#f2f4f8; border:1px solid #5b6472; border-radius:0px; }"
                "QPushButton:hover { background:#374151; }"
                "QPushButton:checked { background:#4b6f9f; color:#ffffff; border:1px solid #9cc2ff; font-weight:700; }"
                "QPushButton:disabled { background:#1f232a; color:#6b7280; border:1px solid #333946; }"
            )
        for btn in (getattr(self, 'btn_align_left', None), getattr(self, 'btn_align_center', None), getattr(self, 'btn_align_right', None)):
            if btn is not None:
                btn.setStyleSheet(base)
        bold = base.replace("QPushButton {", "QPushButton { font-weight:bold;")
        italic = base.replace("QPushButton {", "QPushButton { font-style:italic;")
        strike = base.replace("QPushButton {", "QPushButton { text-decoration: line-through;")
        if hasattr(self, 'btn_bold'):
            self.btn_bold.setStyleSheet(bold)
        if hasattr(self, 'btn_italic'):
            self.btn_italic.setStyleSheet(italic)
        if hasattr(self, 'btn_strike'):
            self.btn_strike.setStyleSheet(strike)

    def set_widget_interlock_visual(self, widget, enabled, disabled_opacity=0.42):
        if widget is None:
            return
        try:
            widget.setEnabled(bool(enabled))
        except Exception:
            pass
        try:
            eff = widget.graphicsEffect()
            if not isinstance(eff, QGraphicsOpacityEffect):
                eff = QGraphicsOpacityEffect(widget)
                widget.setGraphicsEffect(eff)
            eff.setOpacity(1.0 if enabled else float(disabled_opacity))
        except Exception:
            pass

    def update_page_presence_interlocks(self):
        has_pages = bool(getattr(self, 'paths', []))
        for widget in getattr(self, 'page_required_widgets', []):
            self.set_widget_interlock_visual(widget, has_pages)
        for key in getattr(self, 'page_required_action_keys', []):
            action = self.actions.get(key) if hasattr(self, 'actions') else None
            if action is not None:
                try:
                    action.setEnabled(has_pages)
                except Exception:
                    pass
        # 로컬 라벨 변수까지 일일이 저장하지 않아도, 페이지 의존 문구는 같이 흐리게 만든다.
        label_texts = {
            "폰트", "크기", "획", "행간", "자간", "너비", "높이", "번역AI", "묶음",
            "Font", "Size", "Stroke", "Line", "Letter", "Width", "Height", "Translation AI", "Chunk",
        }
        try:
            for label in self.findChildren(QLabel):
                try:
                    if label.text().strip() in label_texts:
                        self.set_widget_interlock_visual(label, has_pages, disabled_opacity=0.35)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if hasattr(self, 'page_tab_bar'):
                self.page_tab_bar.setEnabled(has_pages)
            if hasattr(self, 'btn_page_tab_menu'):
                self.set_widget_interlock_visual(self.btn_page_tab_menu, has_pages)
            for _btn in (getattr(self, 'btn_page_scroll_left', None), getattr(self, 'btn_page_scroll_right', None)):
                if _btn is not None:
                    self.set_widget_interlock_visual(_btn, has_pages)
            if hasattr(self, 'btn_page_add'):
                self.set_widget_interlock_visual(self.btn_page_add, bool(self.has_open_project()))
        except Exception:
            pass
        if not has_pages:
            self.update_text_style_control_state([])

    def update_text_style_control_state(self, selected_items=None):
        if getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
            return
        try:
            items = list(selected_items) if selected_items is not None else self.selected_text_items()
        except Exception:
            items = []
        enabled = bool(items) and hasattr(self, 'cb_mode') and self.cb_mode.currentIndex() == 4
        for widget in getattr(self, 'text_style_control_widgets', []):
            self.set_widget_interlock_visual(widget, enabled, disabled_opacity=0.35)
        self._style_signal_lock = True
        try:
            if not enabled:
                for btn in (getattr(self, 'btn_align_left', None), getattr(self, 'btn_align_center', None), getattr(self, 'btn_align_right', None), getattr(self, 'btn_bold', None), getattr(self, 'btn_italic', None), getattr(self, 'btn_strike', None)):
                    if btn is not None:
                        self._set_widget_checked_blocked(btn, False)
                if hasattr(self, 'sb_text_opacity'):
                    self._set_widget_value_blocked(self.sb_text_opacity, 100)
                return
            d = getattr(items[0], 'data', {}) or {}
            align = str(d.get('align') or getattr(self, 'default_align', 'center') or 'center').lower()
            if align not in ('left', 'center', 'right'):
                align = 'center'
            if hasattr(self, 'btn_align_left'):
                self._set_widget_checked_blocked(self.btn_align_left, align == 'left')
                self._set_widget_checked_blocked(self.btn_align_center, align == 'center')
                self._set_widget_checked_blocked(self.btn_align_right, align == 'right')
            if hasattr(self, 'btn_bold'):
                self._set_widget_checked_blocked(self.btn_bold, bool(d.get('bold', False)))
            if hasattr(self, 'btn_italic'):
                self._set_widget_checked_blocked(self.btn_italic, bool(d.get('italic', False)))
            if hasattr(self, 'btn_strike'):
                self._set_widget_checked_blocked(self.btn_strike, bool(d.get('strike', False)))
            if hasattr(self, 'sb_text_opacity'):
                self._set_widget_value_blocked(self.sb_text_opacity, int(d.get('opacity', 100) or 100))
        finally:
            self._style_signal_lock = False

    def on_final_item_style_changed(self, *args):
        if self._style_signal_lock:
            return
        if not self.selected_text_items():
            return
        self.apply_style_to_selected(
            font_family=self.final_item_font.currentFont().family(),
            font_size=self.final_item_size.value(),
            stroke_width=self.final_item_stroke.value(),
        )


    def on_text_opacity_changed(self, value):
        if getattr(self, '_style_signal_lock', False):
            return
        if not self.selected_text_items() or self.cb_mode.currentIndex() != 4:
            return
        self.apply_style_to_selected(opacity=max(0, min(100, int(value))))

    def selected_first_text_data_item(self):
        try:
            items = self.selected_text_items()
            if items:
                return items[0].data
        except Exception:
            pass
        try:
            rows = self.selected_text_data_items()
            if rows:
                return rows[0]
        except Exception:
            pass
        return None

    def open_selected_text_gradient_dialog(self):
        try:
            self.open_text_advanced_effect_dialog(self.selected_text_data_items())
        except Exception:
            pass

    def toggle_selected_text_transform_quick(self):
        d = self.selected_first_text_data_item()
        if d is not None:
            self.toggle_text_transform_mode(d)

    def toggle_selected_text_skew_quick(self):
        d = self.selected_first_text_data_item()
        if d is not None:
            self.toggle_text_skew_mode(d)

    def toggle_selected_text_trapezoid_quick(self):
        d = self.selected_first_text_data_item()
        if d is not None:
            self.toggle_text_trapezoid_mode(d)

    def toggle_selected_text_arc_quick(self):
        d = self.selected_first_text_data_item()
        if d is not None:
            self.toggle_text_arc_mode(d)

    def rasterize_selected_text_quick(self):
        try:
            self.convert_text_data_items_to_raster_objects(self.selected_text_data_items())
        except Exception:
            pass

    def apply_style_to_selected(self, keep_selection=True, preset_name=None, record_undo=True, **style):
        if getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
            return
        items = self.selected_text_items()
        if not items:
            return
        selected_ids = [item.data.get('id') for item in items]
        if record_undo:
            self.push_page_text_undo('텍스트 스타일 변경')
        for item in items:
            for key, value in style.items():
                item.data[key] = value
            if preset_name:
                item.data['item_text_preset_name'] = str(preset_name)
            else:
                item.data.pop('item_text_preset_name', None)
            # 이미 직접 수정된 텍스트는 OCR 박스를 버린 상태이므로,
            # 스타일 변경 후에도 실제 글자 bounds를 기준으로 텍스트 영역을 다시 만든다.
            try:
                if bool(item.data.get('manual_text_rect')) or str(item.data.get('text_anchor_mode') or '').lower() == 'text':
                    self.shrink_text_rect_to_content(item.data)
            except Exception:
                pass
        self.auto_save_project()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
            if keep_selection:
                self.reselect_text_items(selected_ids)
            self.update_item_preset_combo_for_selected_texts()

    def reselect_text_items(self, selected_ids):
        ids = set(selected_ids or [])
        if not ids or getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
            return
        scene = self._safe_graphics_scene()
        if scene is None:
            return
        try:
            for item in scene.items():
                if isinstance(item, TypesettingItem) and item.data.get('id') in ids:
                    item.setSelected(True)
        except RuntimeError:
            return
        except Exception:
            return

    def select_table_rows_by_ids(self, selected_ids):
        if not hasattr(self, 'tab') or self._syncing_selection:
            return
        ids = {str(x) for x in (selected_ids or []) if x is not None}
        self._syncing_selection = True
        try:
            model = self.tab.model()
            sm = self.tab.selectionModel()
            if not sm:
                return
            sm.clearSelection()
            first_row = None
            for row in range(1, self.tab.rowCount()):
                id_item = self.tab.item(row, 0)
                if id_item and id_item.text().strip() in ids:
                    top = model.index(row, 0)
                    bottom = model.index(row, self.tab.columnCount() - 1)
                    sel = QItemSelection(top, bottom)
                    sm.select(sel, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
                    if first_row is None:
                        first_row = row
            if first_row is not None:
                # setCurrentCell()은 환경에 따라 선택을 마지막 한 줄로 줄일 수 있어서 사용하지 않는다.
                # 현재 인덱스만 조용히 옮기고 다중 선택 상태는 유지한다.
                sm.setCurrentIndex(model.index(first_row, 0), QItemSelectionModel.SelectionFlag.NoUpdate)
        finally:
            self._syncing_selection = False

    def selected_table_text_ids(self):
        if not hasattr(self, 'tab'):
            return []
        rows = sorted({idx.row() for idx in self.tab.selectedIndexes() if idx.row() > 0})
        ids = []
        for row in rows:
            item = self.tab.item(row, 0)
            if item:
                ids.append(item.text().strip())
        return ids

    def on_table_selection_changed(self):
        if self._syncing_selection:
            return
        if getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
            return
        if self.cb_mode.currentIndex() != 4:
            return
        scene = self._safe_graphics_scene()
        if scene is None:
            return
        active_transform = self.current_transform_data_item()
        if active_transform is not None:
            self.reselect_text_items([active_transform.get('id')])
            return
        ids = set(self.selected_table_text_ids())
        self._syncing_selection = True
        try:
            scene.blockSignals(True)
            try:
                for item in scene.items():
                    if isinstance(item, TypesettingItem):
                        item.setSelected(str(item.data.get('id')) in ids)
            finally:
                scene.blockSignals(False)
        except RuntimeError:
            pass
        except Exception:
            pass
        finally:
            self._syncing_selection = False
        # 우측 스타일 칸은 첫 선택 항목 기준으로 맞춘다.
        self.on_scene_selection_changed()

    def on_global_text_style_changed(self, *args):
        if self._style_signal_lock:
            return
        if getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
            return
        selected = self.selected_text_items()
        if not selected or self.cb_mode.currentIndex() != 4:
            self.update_text_style_control_state([])
            return
        self.set_preset_combo_to_last()
        self.set_item_preset_combo_custom()
        self.save_last_text_preset("__last__")
        self.apply_style_to_selected(
                font_family=self.cb_font.currentFont().family(),
                font_size=self.sb_font_size.value(),
                stroke_width=self.sb_strk.value(),
                text_color=self.default_text_color,
                stroke_color=self.default_stroke_color,
                align=self.default_align,
                line_spacing=self.sb_line_spacing.value(),
                letter_spacing=self.sb_letter_spacing.value(),
                char_width=self.sb_char_width.value(),
                char_height=self.sb_char_height.value(),
                bold=self.btn_bold.isChecked(),
                italic=self.btn_italic.isChecked(),
                strike=self.btn_strike.isChecked(),
            )

    def set_global_align(self, align):
        if getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
            return
        selected = self.selected_text_items()
        if not selected or self.cb_mode.currentIndex() != 4:
            self.update_text_style_control_state([])
            return
        self.default_align = align
        self.set_preset_combo_to_last()
        self.set_item_preset_combo_custom()
        self.save_last_text_preset("__last__")
        self.apply_style_to_selected(align=align)
        self.update_text_style_control_state(selected)

    def pick_color(self, target):
        if target in ("global_text", "global_stroke") and (not self.selected_text_items() or self.cb_mode.currentIndex() != 4):
            self.update_text_style_control_state([])
            return
        if target == "final_paint":
            current = self.final_paint_color
        else:
            current = self.default_text_color if "text" in target else self.default_stroke_color
        color = QColorDialog.getColor(QColor(current), self, "색상 선택")
        if not color.isValid():
            return
        hex_color = color.name(QColor.NameFormat.HexRgb).upper()
        if target == "global_text":
            self.default_text_color = hex_color
            self.update_color_button_styles()
            self.on_global_text_style_changed()
        elif target == "global_stroke":
            self.default_stroke_color = hex_color
            self.update_color_button_styles()
            self.on_global_text_style_changed()
        elif target == "item_text":
            self.apply_style_to_selected(text_color=hex_color)
        elif target == "item_stroke":
            self.apply_style_to_selected(stroke_color=hex_color)
        elif target == "final_paint":
            self.final_paint_color = hex_color
            self.update_color_button_styles()
            self.log(f"🎨 최종 페인팅 색상: {hex_color}")

    def on_show_final_text_toggled(self, checked):
        old_state = bool(getattr(self, "_last_show_final_text_checked", not bool(checked)))
        new_state = bool(checked)
        if (
            old_state != new_state
            and not getattr(self, "_project_undo_restore_lock", False)
            and not getattr(self, "is_loading_project", False)
            and not getattr(self, "is_page_loading", False)
            and not getattr(self, "is_batch_running", False)
        ):
            try:
                rec = self.make_project_undo_record("텍스트 표시 ON/OFF")
                rec.setdefault("ui_state", self.current_project_ui_state())
                rec["ui_state"]["show_final_text"] = old_state
                self.append_project_undo_record(rec)
            except Exception:
                pass
        self._last_show_final_text_checked = new_state
        if self.cb_mode.currentIndex() == 4:
            old_suppress = getattr(self, "_suppress_mode_undo", False)
            self._suppress_mode_undo = True
            try:
                self.mode_chg(4)
            finally:
                self._suppress_mode_undo = old_suppress
        self.auto_save_project()

    def active_mask_key(self, mode_idx=None):
        mode_idx = self.cb_mode.currentIndex() if mode_idx is None else mode_idx
        # 텍스트 마스크는 분석/재분석용이라 토글을 쓰지 않는다.
        # 토글은 페인팅 마스크에서만 ON(분석 기반) / OFF(수동 마스크)로 분리한다.
        if mode_idx == 2:
            return 'mask_merge'
        if mode_idx == 3:
            return 'mask_inpaint' if self.mask_toggle_enabled else 'mask_inpaint_off'
        return None

    def get_active_mask(self, curr, mode_idx=None):
        key = self.active_mask_key(mode_idx)
        if not key or not curr:
            return None
        return curr.get(key)

    def set_active_mask(self, curr, mask, mode_idx=None):
        key = self.active_mask_key(mode_idx)
        if key and curr is not None:
            curr[key] = mask.copy() if isinstance(mask, np.ndarray) else mask

    def on_mask_toggle_changed(self, checked):
        curr = self.data.get(self.idx)
        old_state = self.mask_toggle_enabled
        mode = self.cb_mode.currentIndex()
        if (
            mode == 3
            and not getattr(self, "_project_undo_restore_lock", False)
            and not getattr(self, "is_page_loading", False)
            and not getattr(self, "is_batch_running", False)
        ):
            try:
                self.commit_current_page_ui_to_data(include_mask=True)
                self.push_project_undo("마스크 ON/OFF")
            except Exception:
                pass

        # 토글은 페인팅 마스크 전용이다.
        # 텍스트 마스크에서는 분석 마스크(mask_merge)만 쓰므로 ON/OFF 분리 저장을 하지 않는다.
        if curr is not None and mode == 3:
            # 토글을 바꾸기 직전, 화면에 떠 있는 현재 페인팅 마스크를 이전 토글 슬롯에 먼저 저장한다.
            m = self.view.get_mask_np()
            if m is not None:
                curr['mask_inpaint' if old_state else 'mask_inpaint_off'] = m.copy()

        self.mask_toggle_enabled = bool(checked)
        if hasattr(self, "act_mask_toggle"):
            self.act_mask_toggle.setText("☑" if checked else "☐")
        if curr is not None:
            curr['mask_toggle_enabled'] = self.mask_toggle_enabled
        state = "ON" if checked else "OFF"
        self.log(f"🎚️ 페인팅 마스크 토글: {state}")

        if mode == 3:
            # 토글은 탭 이동이 아니라 같은 페인팅 마스크 탭 안에서
            # mask_inpaint / mask_inpaint_off 슬롯만 바꾸는 작업이다.
            # 따라서 mode_chg(3)로 화면을 다시 그릴 때:
            # 1) 탭 변경 Undo를 만들지 않고
            # 2) 이전 화면 마스크를 새 토글 슬롯에 덮어쓰지 않도록 막는다.
            old_suppress_mode_undo = getattr(self, "_suppress_mode_undo", False)
            old_skip_mode_mask_commit = getattr(self, "_skip_mode_mask_commit", False)
            old_mask_toggle_refreshing = getattr(self, "_mask_toggle_refreshing", False)
            self._suppress_mode_undo = True
            self._skip_mode_mask_commit = True
            self._mask_toggle_refreshing = True
            try:
                self.mode_chg(3)
            finally:
                self._suppress_mode_undo = old_suppress_mode_undo
                self._skip_mode_mask_commit = old_skip_mode_mask_commit
                self._mask_toggle_refreshing = old_mask_toggle_refreshing
        self.auto_save_project()

    def set_mask_toggle_safely(self, checked):
        self.mask_toggle_enabled = bool(checked)
        if hasattr(self, 'cb_mask_toggle'):
            self.cb_mask_toggle.blockSignals(True)
            try:
                self.cb_mask_toggle.setChecked(bool(checked))
                if hasattr(self, "act_mask_toggle"):
                    self.act_mask_toggle.setText("☑" if checked else "☐")
            finally:
                self.cb_mask_toggle.blockSignals(False)

    def get_page_stem(self, page_idx):
        """
        TXT 추출/일괄 번역문 불러오기용 파일명 기준.

        이제 기준은 실제 프로젝트의 뿌리 이름인 original_name이다.
        원본 파일명 변경 기능이 original_name과 images 경로를 함께 갱신하므로,
        TXT 출력/일괄 불러오기도 같은 이름을 따라가야 한다.
        """
        try:
            curr = self.data.get(page_idx, {}) if isinstance(self.data, dict) else {}
            name = curr.get('original_name') if isinstance(curr, dict) else ""
            if name:
                return safe_page_file_stem(Path(str(name)).stem, fallback=f"page{int(page_idx) + 1:03d}")
        except Exception:
            pass
        try:
            return safe_page_file_stem(Path(os.path.basename(self.paths[page_idx])).stem, fallback=f"page{int(page_idx) + 1:03d}")
        except Exception:
            return f"page{int(page_idx) + 1:03d}"

    def get_output_root(self):
        if self.project_dir:
            return self.project_dir
        if self.paths:
            return os.path.dirname(os.path.abspath(self.paths[self.idx]))
        return os.getcwd()

    def ensure_subdir(self, name):
        root = self.get_output_root()
        path = os.path.join(root, name)
        os.makedirs(path, exist_ok=True)
        return path

    def output_cleanup_targets(self):
        """현재 프로젝트에서 삭제 가능한 출력물 목록을 모은다."""
        root = Path(self.get_output_root())
        targets = {
            "result": [],
            "script": [],
            "txt": [],
        }

        for result_dir in (root / "result", root / "Result"):
            if result_dir.exists():
                try:
                    targets["result"].extend([p for p in result_dir.iterdir() if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp")])
                except Exception:
                    pass

        scripts_dir = root / "scripts"
        if scripts_dir.exists():
            try:
                targets["script"].extend([p for p in scripts_dir.iterdir() if p.is_file() and p.suffix.lower() in (".jsx", ".js", ".txt")])
            except Exception:
                pass

        for txt_dir in (root / "txt", root / "Txt"):
            if txt_dir.exists():
                try:
                    targets["txt"].extend([p for p in txt_dir.iterdir() if p.is_file() and p.suffix.lower() == ".txt"])
                except Exception:
                    pass

        return targets

    def open_output_cleanup_dialog(self):
        """옵션: 현재 프로젝트 산출물 삭제."""
        if not self.project_dir:
            QMessageBox.information(self, self.tr_ui("출력물 삭제"), self.tr_ui("먼저 프로젝트를 열어주세요."))
            return False

        targets = self.output_cleanup_targets()
        counts = {k: len(v) for k, v in targets.items()}
        if not any(counts.values()):
            QMessageBox.information(self, self.tr_ui("출력물 삭제"), self.tr_ui("삭제할 출력물이 없습니다."))
            return False

        dlg = OutputCleanupDialog(counts, self)
        try:
            dlg.setStyleSheet(self.message_box_style())
        except Exception:
            pass
        if not dlg.exec():
            return False

        selected = dlg.selected()
        files = []
        labels = []
        if selected.get("result"):
            files.extend(targets.get("result", []))
            labels.append(f"{self.tr_ui('최종결과 이미지')} {len(targets.get('result', []))}개")
        if selected.get("script"):
            files.extend(targets.get("script", []))
            labels.append(f"{self.tr_ui('포토샵 스크립트')} {len(targets.get('script', []))}개")
        if selected.get("txt"):
            files.extend(targets.get("txt", []))
            labels.append(f"{self.tr_ui('TXT 지문')} {len(targets.get('txt', []))}개")

        if not files:
            return False

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle(self.tr_ui("출력물 삭제 확인"))
        msg.setText(self.tr_ui("선택한 출력물을 삭제할까요?"))
        msg.setInformativeText("\n".join(labels))
        btn_delete = msg.addButton(self.tr_ui("삭제"), QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = msg.addButton(self.tr_ui("취소"), QMessageBox.ButtonRole.RejectRole)
        for _btn in (btn_delete, btn_cancel):
            try:
                _btn.setMinimumWidth(96)
            except Exception:
                pass
        msg.setDefaultButton(btn_cancel)
        msg.setEscapeButton(btn_cancel)
        try:
            msg.setStyleSheet(self.message_box_style())
        except Exception:
            pass
        force_message_box_front(msg)
        msg.exec()
        if msg.clickedButton() is not btn_delete:
            self.log("↩️ 출력물 삭제 취소")
            return False

        deleted = 0
        failed = 0
        for p in files:
            try:
                p = Path(p)
                if p.exists() and p.is_file():
                    p.unlink()
                    deleted += 1
            except Exception:
                failed += 1

        self.log(f"🧹 출력물 삭제 완료: {deleted}개 삭제 / 실패 {failed}개")
        if failed:
            QMessageBox.warning(self, self.tr_ui("출력물 삭제"), f"{self.tr_ui('일부 파일을 삭제하지 못했습니다.')} 실패: {failed}개")
        return True

    def choose_text_extract_mode(self):
        ko_items = ["원문만", "번역문만", "원문+번역문"]
        display_items = [self.tr_ui(x) for x in ko_items]
        value, ok = QInputDialog.getItem(
            self,
            self.tr_ui("지문 추출"),
            self.tr_ui("추출할 내용:"),
            display_items,
            0,
            False
        )
        if not ok:
            return None
        try:
            idx = display_items.index(value)
            return ko_items[idx]
        except ValueError:
            return value

    def build_text_export_content(self, page_idx, mode):
        curr = self.data.get(page_idx, {})
        blocks = []
        for i, item in enumerate(curr.get('data', []), 1):
            text_id = str(item.get('id', i))
            original = str(item.get('text', '') or '')
            translated = str(item.get('translated_text', '') or '')
            marker = f"[{text_id}]"
            if mode == "원문만":
                blocks.append(f"{marker}\n\n{original}")
            elif mode == "번역문만":
                blocks.append(f"{marker}\n\n{translated}")
            else:
                blocks.append(f"{marker}\n\n{original}\n\n{translated}")
        return "\n\n".join(blocks).rstrip() + "\n"

    def extract_text_current(self):
        if not self.paths:
            return
        self.commit_current_page_ui_to_data()
        mode = self.choose_text_extract_mode()
        if not mode:
            return
        txt_dir = self.ensure_subdir("txt")
        out_path = os.path.join(txt_dir, f"{self.get_page_stem(self.idx)}.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(self.build_text_export_content(self.idx, mode))
        self.log((f"📄 Extract text complete: {out_path}" if self.ui_language == LANG_EN else f"📄 지문 추출 완료: {out_path}"))
        self.auto_save_project()

    def extract_text_batch(self):
        if not self.paths:
            return
        if getattr(self, "ui_language", LANG_KO) == LANG_EN:
            msg = f"Create text extraction TXT files for total {len(self.paths)} page(s)?"
        else:
            msg = f"지문 추출 TXT를 총 {len(self.paths)}페이지 기준으로 생성합니다."
        if not self.confirm_batch_operation("일괄 지문 추출", msg):
            self.log("↩️ Batch extract text canceled" if self.ui_language == LANG_EN else "↩️ 일괄 지문 추출 취소")
            return
        self.commit_current_page_ui_to_data()
        mode = self.choose_text_extract_mode()
        if not mode:
            return
        txt_dir = self.ensure_subdir("txt")
        count = 0
        for i in range(len(self.paths)):
            if i not in self.data or not self.data[i].get('data'):
                continue
            out_path = os.path.join(txt_dir, f"{self.get_page_stem(i)}.txt")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(self.build_text_export_content(i, mode))
            count += 1
        self.log((f"📄 Batch text extraction complete: {count} items / {txt_dir}" if self.ui_language == LANG_EN else f"📄 일괄 지문 추출 완료: {count}개 / {txt_dir}"))
        self.auto_save_project()

    def parse_translation_txt(self, path, valid_ids):
        valid = {str(x) for x in valid_ids}

        def marker_to_id(token):
            token = str(token or "").strip()
            if len(token) >= 3 and token.startswith("[") and token.endswith("]"):
                inner = token[1:-1].strip()
                if inner.isdigit() and inner in valid:
                    return inner
            return None

        with open(path, "r", encoding="utf-8-sig") as f:
            lines = f.read().splitlines()

        result = {}
        i = 0
        while i < len(lines):
            text_id = marker_to_id(lines[i])
            if text_id:
                i += 1
                buf = []
                while i < len(lines):
                    # 다음 번호는 [1]처럼 대괄호 안의 숫자이고,
                    # 현재 페이지에 실제 존재하는 텍스트 번호일 때만 인정한다.
                    # 그래서 1131313, 421 같은 숫자 번역문은 안전하게 본문으로 들어간다.
                    if marker_to_id(lines[i]):
                        break
                    if lines[i].strip():
                        buf.append(lines[i].rstrip())
                    i += 1

                if buf:
                    result[text_id] = "\n".join(buf).strip()
                continue

            i += 1

        return result

    def apply_translation_map_to_page(self, page_idx, trans_map):
        curr = self.data.get(page_idx)
        if not curr:
            return 0
        count = 0
        for i, item in enumerate(curr.get('data', []), 1):
            text_id = str(item.get('id', i))
            if text_id in trans_map:
                new_text = str(trans_map[text_id] or '')
                old_text = str(item.get('translated_text', '') or '')
                if new_text != old_text:
                    item['translated_text'] = new_text
                    try:
                        self.shrink_text_rect_to_content(item)
                    except Exception:
                        pass
                    count += 1
        return count

    def translation_txt_name_candidates(self, page_idx):
        """일괄 번역문 불러오기에서 허용할 TXT 파일명 후보.

        기본은 원본 이미지 stem이지만, 사용자가 출력/지문 추출을 다른 표시명으로 해둔 경우를 위해
        1p_원본명, page001, 현재 출력 표시명도 같이 허용한다.
        """
        candidates = []
        def add(value):
            try:
                stem = safe_page_file_stem(Path(str(value)).stem, fallback="")
                if stem and stem not in candidates:
                    candidates.append(stem)
            except Exception:
                pass

        add(self.get_page_stem(page_idx))
        try:
            add(self.page_display_name(page_idx, mode=PAGE_DISPLAY_MODE_ORIGINAL, include_ext=False))
            add(self.page_display_name(page_idx, mode=PAGE_DISPLAY_MODE_PAGE_ORIGINAL, include_ext=False))
            add(self.page_display_name(page_idx, mode=PAGE_DISPLAY_MODE_PAGE_NUMBER, include_ext=False))
            add(self.output_display_stem(page_idx))
        except Exception:
            pass
        return candidates

    def find_translation_txt_in_folder(self, folder, page_stem=None, page_idx=None):
        """일괄 번역문 불러오기용 TXT 탐색.

        원본명.txt를 기본으로 찾고, 1p_원본명.txt / page001.txt / 출력 표시명.txt도 후보로 인정한다.
        선택한 폴더 바로 아래를 먼저 찾은 뒤 없으면 하위 폴더까지 한 번 더 찾는다.
        """
        if not folder:
            return None
        root = Path(folder)
        if not root.exists() or not root.is_dir():
            return None

        candidates = []
        if page_idx is not None:
            candidates.extend(self.translation_txt_name_candidates(page_idx))
        if page_stem:
            stem = safe_page_file_stem(Path(str(page_stem)).stem, fallback="")
            if stem and stem not in candidates:
                candidates.append(stem)
        if not candidates:
            return None

        targets = {f"{stem}.txt".casefold() for stem in candidates}

        try:
            for child in root.iterdir():
                if child.is_file() and child.name.casefold() in targets:
                    return str(child)
        except Exception:
            pass

        try:
            for child in root.rglob("*.txt"):
                if child.is_file() and child.name.casefold() in targets:
                    return str(child)
        except Exception:
            pass
        return None

    def import_translation_current(self):
        if not self.paths or self.idx not in self.data:
            return
        curr = self.data[self.idx]
        valid_ids = [str(x.get('id', i + 1)) for i, x in enumerate(curr.get('data', []))]
        if not valid_ids:
            self.log("⚠️ 불러올 텍스트 번호가 없습니다.")
            return
        default_txt = os.path.join(self.ensure_subdir("txt"), f"{self.get_page_stem(self.idx)}.txt")
        legacy_txt = os.path.join(self.get_output_root(), "Txt", f"{self.get_page_stem(self.idx)}.txt")
        if (not os.path.exists(default_txt)) and os.path.exists(legacy_txt):
            default_txt = legacy_txt
        path, _ = QFileDialog.getOpenFileName(self, self.tr_ui("번역문 TXT 불러오기"), default_txt, "Text (*.txt)")
        if not path:
            return
        trans_map = self.parse_translation_txt(path, valid_ids)
        if not trans_map:
            QMessageBox.warning(self, self.tr_ui("불러오기 실패"), self.tr_ui("현재 페이지 텍스트 번호와 맞는 번역문을 찾지 못했습니다."))
            return
        undo_rec = self.make_project_undo_record("번역문 불러오기")
        count = self.apply_translation_map_to_page(self.idx, trans_map)
        if count:
            self.append_project_undo_record(undo_rec)
        self.ref_tab()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
        self.log(f"📥 번역문 불러오기 완료: {count}개")
        self.auto_save_project()

    def import_translation_batch(self):
        if not self.paths:
            return
        start_dir = self.ensure_subdir("txt")
        legacy_txt_dir = os.path.join(self.get_output_root(), "Txt")
        try:
            if not any(Path(start_dir).glob("*.txt")) and os.path.isdir(legacy_txt_dir) and any(Path(legacy_txt_dir).glob("*.txt")):
                start_dir = legacy_txt_dir
        except Exception:
            pass
        folder = QFileDialog.getExistingDirectory(self, self.tr_ui("일괄 번역문 TXT 폴더 선택"), start_dir)
        if not folder:
            return
        if not self.confirm_batch_operation("일괄 번역문 불러오기", f"선택한 폴더의 TXT 번역문을 {len(self.paths)}페이지에 적용합니다."):
            self.log("↩️ 일괄 번역문 불러오기 취소")
            return
        self.commit_current_page_ui_to_data()
        undo_rec = self.make_project_undo_record("일괄 번역문 불러오기", full_project=True)
        total_pages = 0
        total_items = 0
        missing = 0
        for i in range(len(self.paths)):
            curr = self.data.get(i)
            if not curr or not curr.get('data'):
                continue
            txt_path = self.find_translation_txt_in_folder(folder, self.get_page_stem(i), page_idx=i)
            if not txt_path:
                missing += 1
                continue
            valid_ids = [str(x.get('id', n + 1)) for n, x in enumerate(curr.get('data', []))]
            trans_map = self.parse_translation_txt(txt_path, valid_ids)
            if not trans_map:
                continue
            count = self.apply_translation_map_to_page(i, trans_map)
            if count:
                total_pages += 1
                total_items += count
        if total_items:
            self.append_project_undo_record(undo_rec)
        self.ref_tab()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
        if total_pages == 0:
            QMessageBox.warning(
                self,
                self.tr_ui("일괄 불러오기 실패"),
                self.tr_msg("선택한 폴더에서 현재 페이지와 맞는 TXT 파일을 찾지 못했거나, 맞는 텍스트 번호를 찾지 못했습니다.\n"
                "허용 예: sample.txt, 1p_sample.txt, page001.txt"),
            )
        self.log(f"📥 일괄 번역문 불러오기 완료: {total_pages}페이지 / {total_items}개 / TXT 없음 {missing}개")
        self.auto_save_project()

    def clear_translation_current(self):
        """현재 페이지의 번역문 칸을 모두 비운다."""
        if not self.paths or self.idx not in self.data:
            return

        self.commit_current_page_ui_to_data()
        curr = self.data.get(self.idx)
        if not curr or not curr.get('data'):
            self.log("⚠️ 지울 번역문이 없습니다.")
            return

        undo_rec = self.make_project_undo_record("번역문 내용 지우기")
        count = 0
        for item in curr.get('data', []):
            if str(item.get('translated_text', '') or ''):
                item['translated_text'] = ''
                try:
                    self.shrink_text_rect_to_content(item)
                except Exception:
                    pass
                count += 1

        if count:
            self.append_project_undo_record(undo_rec)
        self.ref_tab()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
        self.auto_save_project()
        self.log(f"🧹 번역문 내용 지우기 완료: {count}개")

    def clear_translation_batch(self):
        """전체 페이지의 번역문 칸을 모두 비운다."""
        if not self.paths:
            return

        if not self.confirm_batch_operation("일괄 번역문 내용 지우기", f"전체 {len(self.paths)}페이지의 번역문 내용을 지웁니다."):
            self.log("↩️ 일괄 번역문 내용 지우기 취소")
            return

        self.commit_current_page_ui_to_data()
        undo_rec = self.make_project_undo_record("일괄 번역문 내용 지우기", full_project=True)

        total_pages = 0
        total_items = 0

        for page_idx in range(len(self.paths)):
            curr = self.data.get(page_idx)
            if not curr or not curr.get('data'):
                continue

            page_count = 0
            for item in curr.get('data', []):
                if str(item.get('translated_text', '') or ''):
                    item['translated_text'] = ''
                    try:
                        self.shrink_text_rect_to_content(item)
                    except Exception:
                        pass
                    page_count += 1

            if page_count:
                total_pages += 1
                total_items += page_count

        if total_items:
            self.append_project_undo_record(undo_rec)
        self.ref_tab()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
        self.auto_save_project()
        self.log(f"🧹 일괄 번역문 내용 지우기 완료: {total_pages}페이지 / {total_items}개")

    def clear_masks_for_removed_items(self, curr, removed_items):
        if not curr or not removed_items:
            return
        mask_keys = ['mask_merge', 'mask_inpaint', 'mask_merge_off', 'mask_inpaint_off']
        for item in removed_items:
            try:
                x, y, w, h = [int(v) for v in item.get('rect', [0, 0, 0, 0])]
            except Exception:
                continue
            for key in mask_keys:
                m = curr.get(key)
                if not isinstance(m, np.ndarray):
                    continue
                yy1 = max(0, y)
                yy2 = min(m.shape[0], y + h)
                xx1 = max(0, x)
                xx2 = min(m.shape[1], x + w)
                if yy2 > yy1 and xx2 > xx1:
                    m[yy1:yy2, xx1:xx2] = 0

    def clean_text_for_page(self, page_idx):
        curr = self.data.get(page_idx)
        if not curr or 'data' not in curr:
            return 0
        old_items = list(curr.get('data', []))
        removed = [x for x in old_items if not x.get('use_inpaint', True)]
        kept = [x for x in old_items if x.get('use_inpaint', True)]
        if not removed:
            return 0

        self.clear_masks_for_removed_items(curr, removed)
        for n, item in enumerate(kept, 1):
            item['id'] = n
        curr['data'] = kept
        return len(removed)

    def clean_text_current(self):
        if not self.paths or self.idx not in self.data:
            return
        self.commit_current_page_ui_to_data()
        removed_count = sum(1 for x in self.data[self.idx].get('data', []) if not x.get('use_inpaint', True))
        if removed_count <= 0:
            self.log("🧹 There are no unchecked items to delete." if self.ui_language == LANG_EN else "🧹 삭제할 체크 해제 항목이 없습니다.")
            return
        if self.ui_language == LANG_EN:
            msg = f"Delete {removed_count} unchecked text item(s) and reorder IDs?\nThe masks for those text areas will also be cleared."
        else:
            msg = f"체크 해제된 텍스트 {removed_count}개를 삭제하고 번호를 재정렬할까요?\n해당 텍스트 영역의 마스크도 함께 지워집니다."
        ans = QMessageBox.question(
            self,
            self.tr_ui("텍스트 정리"),
            msg,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        undo_rec = self.make_project_undo_record("텍스트 정리")
        removed = self.clean_text_for_page(self.idx)
        if removed:
            self.append_project_undo_record(undo_rec)
        self.ref_tab()
        self.mode_chg(self.cb_mode.currentIndex())
        self.log((f"🧹 Clean text complete: {removed} items deleted / IDs reordered" if self.ui_language == LANG_EN else f"🧹 텍스트 정리 완료: {removed}개 삭제 / 번호 재정렬"))
        self.auto_save_project()

    def clean_text_batch(self):
        if not self.paths:
            return
        self.commit_current_page_ui_to_data()
        total_candidates = 0
        for i in range(len(self.paths)):
            curr = self.data.get(i)
            if curr:
                total_candidates += sum(1 for x in curr.get('data', []) if not x.get('use_inpaint', True))
        if total_candidates <= 0:
            self.log("🧹 There are no unchecked items to clean in batch." if self.ui_language == LANG_EN else "🧹 일괄 정리할 체크 해제 항목이 없습니다.")
            return
        if self.ui_language == LANG_EN:
            msg = f"Delete {total_candidates} unchecked text item(s) across all pages and reorder IDs?\nThe masks for those text areas will also be cleared."
        else:
            msg = f"전체 페이지에서 체크 해제된 텍스트 {total_candidates}개를 삭제하고 번호를 재정렬할까요?\n해당 텍스트 영역의 마스크도 함께 지워집니다."
        ans = QMessageBox.question(
            self,
            self.tr_ui("일괄 텍스트 정리"),
            msg,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        undo_rec = self.make_project_undo_record("일괄 텍스트 정리", full_project=True)
        total_removed = 0
        pages = 0
        for i in range(len(self.paths)):
            removed = self.clean_text_for_page(i)
            if removed:
                total_removed += removed
                pages += 1
        if total_removed:
            self.append_project_undo_record(undo_rec)
        self.ref_tab()
        self.mode_chg(self.cb_mode.currentIndex())
        self.log((f"🧹 Batch clean text complete: {pages} page(s) / {total_removed} items deleted" if self.ui_language == LANG_EN else f"🧹 일괄 텍스트 정리 완료: {pages}페이지 / {total_removed}개 삭제"))
        self.auto_save_project()

    def bg_clean_to_np_image(self, bg):
        """bg_clean 값을 화면/마스크 작업용 OpenCV 이미지(BGR np.ndarray)로 변환한다."""
        if bg is None:
            return None

        try:
            if isinstance(bg, np.ndarray):
                return bg.copy()

            if isinstance(bg, (bytes, bytearray)):
                arr = np.frombuffer(bg, np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                return img.copy() if img is not None else None

            if isinstance(bg, str) and os.path.exists(bg):
                arr = np.fromfile(bg, np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                return img.copy() if img is not None else None
        except Exception:
            return None

        return None

    def get_real_original_image(self, page_idx):
        """프로젝트 images 폴더에 있는 실제 원본 파일을 다시 읽는다."""
        if page_idx < 0 or page_idx >= len(self.paths):
            return None
        try:
            return cv2.imdecode(np.fromfile(self.paths[page_idx], np.uint8), 1)
        except Exception:
            return None

    def normalize_image_to_original_size(self, page_idx, img):
        """
        인페인팅 결과 이미지를 프로젝트 원본 해상도에 맞춘다.

        일부 인페인팅 API는 결과 해상도를 바꿔서 반환할 수 있다.
        이 상태로 다시 인페인팅하면 기존 마스크/텍스트 좌표와 크기가 어긋날 수 있으므로
        툴 내부 기준 이미지는 항상 원본 해상도에 맞춘다.
        """
        if img is None:
            return None

        ref = self.get_real_original_image(page_idx)
        if ref is None:
            return img

        rh, rw = ref.shape[:2]
        h, w = img.shape[:2]
        if (h, w) == (rh, rw):
            return img

        try:
            resized = cv2.resize(img, (rw, rh), interpolation=cv2.INTER_CUBIC)
            self.log(f"↔️ 인페인팅 결과 해상도 보정: {w}x{h} → {rw}x{rh}")
            return resized
        except Exception:
            return img

    def encode_np_image_to_png_bytes(self, img):
        if img is None:
            return None
        try:
            ok, buf = cv2.imencode(".png", img)
            if ok:
                return buf.tobytes()
        except Exception:
            pass
        return None

    def set_working_source_image(self, curr, img):
        """인페인팅/최종 브러시 반영 후 '원본 탭 기준 이미지'로 쓸 작업중 소스를 저장한다."""
        if curr is None or img is None:
            return
        encoded = self.encode_np_image_to_png_bytes(img)
        curr['working_source'] = encoded if encoded is not None else img
        curr['use_inpainted_as_source'] = True
        curr['ori'] = img.copy() if isinstance(img, np.ndarray) else img

    def write_np_image_as_inpaint_source(self, page_idx, img):
        """현재 기준 이미지를 인페인팅 입력 파일로 저장한다. Windows 한글 경로 안전 처리."""
        if img is None:
            return None

        clean_dir = self.ensure_subdir("clean")
        out_path = os.path.join(clean_dir, f"inpaint_source_{page_idx + 1:04d}.png")

        try:
            ok, buf = cv2.imencode(".png", img)
            if not ok:
                self.log("⚠️ 인페인팅 기준 이미지 인코딩 실패")
                return None

            # cv2.imwrite는 Windows 한글 경로에서 실패할 수 있어 np.tofile로 저장한다.
            buf.tofile(out_path)

            if not os.path.exists(out_path) or os.path.getsize(out_path) <= 0:
                self.log("⚠️ 인페인팅 기준 이미지 파일 저장 실패")
                return None

            return out_path
        except Exception as e:
            self.log(f"⚠️ 인페인팅 기준 이미지 저장 오류: {e}")
            return None

    def normalize_inpaint_mask_to_input_image(self, input_path, mask):
        """인페인팅 입력 이미지와 마스크 크기가 다르면 마스크를 입력 이미지 크기에 맞춘다."""
        if mask is None:
            return None

        try:
            img = cv2.imdecode(np.fromfile(input_path, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                return mask

            ih, iw = img.shape[:2]
            mh, mw = mask.shape[:2]
            if (mh, mw) == (ih, iw):
                return mask

            fixed = cv2.resize(mask, (iw, ih), interpolation=cv2.INTER_NEAREST)
            self.log((f"↔️ Inpaint mask size normalized: {mw}x{mh} → {iw}x{ih}" if self.ui_language == LANG_EN else f"↔️ 인페인팅 마스크 해상도 보정: {mw}x{mh} → {iw}x{ih}"))
            return fixed
        except Exception:
            return mask

    def get_source_display_image(self, page_idx):
        """
        원본/분석/마스크 탭에서 실제로 보여줄 기준 이미지.

        use_inpainted_as_source=True면 프로젝트 내부의 작업중 원본(working_source)을 우선 사용한다.
        working_source는 "인페인팅을 원본으로"와 "최종 브러시를 원본으로"가 공유하는 최신 기준 파일이다.
        """
        curr = self.data.get(page_idx, {})

        if curr.get('use_inpainted_as_source'):
            img = self.bg_clean_to_np_image(curr.get('working_source'))
            if img is not None:
                img = self.normalize_image_to_original_size(page_idx, img)
                curr['ori'] = img.copy()
                return curr['ori']

            img = self.bg_clean_to_np_image(curr.get('bg_clean'))
            if img is not None:
                img = self.normalize_image_to_original_size(page_idx, img)
                self.set_working_source_image(curr, img)
                return curr['ori']

        img = curr.get('ori')
        if img is None:
            img = self.get_real_original_image(page_idx)
            if img is not None:
                curr['ori'] = img
        return img

    def get_inpainting_input_path(self, page_idx):
        curr = self.data.get(page_idx, {})
        if curr.get('use_inpainted_as_source'):
            # 덧칠 모드에서는 현재 원본 탭에 표시되는 이미지(curr['ori'])를 그대로 입력으로 쓴다.
            # bg_clean을 다시 직접 쓰면, 최신 결과와 표시 기준이 엇갈릴 수 있다.
            img = self.get_source_display_image(page_idx)
            src = self.write_np_image_as_inpaint_source(page_idx, img)
            if src:
                return src
            self.log("⚠️ Failed to save the inpaint source image. Using the real original image instead." if self.ui_language == LANG_EN else "⚠️ 인페인팅 기준 이미지 저장 실패. 실제 원본 이미지로 진행합니다.")
        return self.paths[page_idx]

    def use_inpainted_as_source(self):
        curr = self.data.get(self.idx)
        if not curr:
            return
        if not curr.get('bg_clean'):
            QMessageBox.warning(self, self.tr_ui("인페인팅 결과 없음"), self.tr_ui("먼저 인페인팅된 이미지가 있어야 원본으로 가져올 수 있습니다."))
            return

        img = self.bg_clean_to_np_image(curr.get('bg_clean'))
        if img is None:
            QMessageBox.warning(self, self.tr_ui("이미지 변환 실패"), self.tr_ui("인페인팅 결과 이미지를 원본 탭에 표시할 수 없습니다."))
            return

        # 실제 원본 파일은 건드리지 않고, 프로젝트 내부 작업중 원본(working_source)에 저장한다.
        img = self.normalize_image_to_original_size(self.idx, img)
        self.set_working_source_image(curr, img)
        self.log("🔁 Inpaint result has been imported as the working source image for the Original tab." if self.ui_language == LANG_EN else "🔁 인페인팅 결과를 원본 탭의 작업중 기준 이미지로 가져왔습니다.")
        self.auto_save_project()
        self.mode_chg(self.cb_mode.currentIndex())

    def restore_original_source(self):
        curr = self.data.get(self.idx)
        if not curr:
            return
        curr['use_inpainted_as_source'] = False
        curr['working_source'] = None
        real_ori = self.get_real_original_image(self.idx)
        if real_ori is not None:
            curr['ori'] = real_ori
        self.log("↩️ The Original tab base image has been restored to the real original image." if self.ui_language == LANG_EN else "↩️ 원본 탭의 기준 이미지를 실제 원본으로 되돌렸습니다.")
        self.auto_save_project()
        self.mode_chg(self.cb_mode.currentIndex())

    def restart_engine(self, show_error=True):
        apply_settings_to_config(self.api_settings)

        try:
            self.engine = MangaProcessEngine()
            if show_error and hasattr(self, "log_w"):
                self.log("🔧 Engine restarted" if self.ui_language == LANG_EN else "🔧 엔진 재시동 완료")
            return True
        except Exception as e:
            self.engine = None
            print(f"Engine Init Error: {e}")
            if show_error:
                QMessageBox.warning(
                    self,
                    self.tr_ui("엔진 초기화 실패"),
                    self.tr_msg("API 설정이 비어 있거나 잘못되어 엔진을 시작하지 못했습니다.\n"
                    "[옵션 > API 관리]에서 키를 저장한 뒤 다시 시도해주세요.\n\n") + f"{self.tr_ui('오류')}: {e}"
                )
            return False

    def ensure_engine_ready(self):
        if self.engine is not None:
            return True

        QMessageBox.warning(
            self,
            self.tr_ui("API 설정 필요"),
            self.tr_msg("엔진이 아직 준비되지 않았습니다.\n[옵션 > API 관리]에서 키를 저장해주세요.")
        )
        return False

    def bring_to_front(self):
        """두 번째 실행 요청이 들어왔을 때 현재 창을 앞으로 가져온다."""
        self.force_app_focus(reason="single-instance")

    def force_app_focus(self, reason="external-open", log_once=False):
        """
        .ysbt 더블클릭 / 드래그 앤 드롭 / 외부 열기 후 창 포커스를 YSB로 되돌린다.
        Windows는 다른 프로세스가 만든 포커스 변경을 막는 경우가 있어 Qt 포커스와 Win32 포커스를 여러 번 같이 시도한다.
        """
        delays = (0, 80, 220, 450)
        for delay in delays:
            QTimer.singleShot(delay, lambda r=reason: self._force_app_focus_once(r))
        if log_once:
            try:
                if self.ui_language == LANG_EN:
                    self.log(f"🪟 Focus requested: {reason}")
                else:
                    self.log(f"🪟 창 포커스 요청: {reason}")
            except Exception:
                pass

    def _force_app_focus_once(self, reason="external-open"):
        try:
            if self.isMinimized():
                self.showNormal()
            else:
                self.show()

            try:
                self.setWindowState((self.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
            except Exception:
                pass

            # Qt 기본 포커스 요청
            self.raise_()
            self.activateWindow()
            self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

            # Windows에서는 파일 더블클릭/두 번째 프로세스 전달 뒤 포커스가 탐색기나 cmd에 남는 경우가 있다.
            if sys.platform.startswith("win"):
                try:
                    import ctypes
                    user32 = ctypes.windll.user32
                    hwnd = int(self.winId())
                    SW_RESTORE = 9
                    HWND_TOPMOST = -1
                    HWND_NOTOPMOST = -2
                    SWP_NOMOVE = 0x0002
                    SWP_NOSIZE = 0x0001
                    SWP_SHOWWINDOW = 0x0040
                    ASFW_ANY = -1
                    try:
                        user32.AllowSetForegroundWindow(ASFW_ANY)
                    except Exception:
                        pass
                    try:
                        user32.ShowWindow(hwnd, SW_RESTORE)
                    except Exception:
                        pass
                    # 포커스 제한이 걸린 환경에서도 앞으로 나오도록 topmost를 아주 짧게 토글한다.
                    try:
                        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
                        user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
                    except Exception:
                        pass
                    try:
                        user32.BringWindowToTop(hwnd)
                    except Exception:
                        pass
                    try:
                        user32.SetForegroundWindow(hwnd)
                    except Exception:
                        pass
                    try:
                        user32.SetFocus(hwnd)
                    except Exception:
                        pass
                except Exception:
                    pass
        except Exception:
            pass

    def has_open_project(self):
        return bool(self.project_dir or self.paths)


    def ensure_task_progress_overlay(self):
        try:
            overlay = getattr(self, "_task_progress_overlay", None)
            if overlay is None:
                overlay = CenterTaskProgressOverlay(self)
                overlay.cancelRequested.connect(self.request_current_long_task_cancel)
                self._task_progress_overlay = overlay
            return overlay
        except Exception:
            return None

    def ensure_task_alert_overlay(self):
        try:
            overlay = getattr(self, "_task_alert_overlay", None)
            if overlay is None:
                overlay = CenterTaskAlertOverlay(self)
                self._task_alert_overlay = overlay
            return overlay
        except Exception:
            return None

    def pause_task_progress_overlay_for_alert(self, detail=None):
        try:
            overlay = getattr(self, "_task_progress_overlay", None)
            if overlay is not None and overlay.isVisible():
                overlay.set_paused(True, detail=detail)
        except Exception:
            pass

    def show_task_alert_overlay(self, title="작업 알림", detail=""):
        try:
            self.pause_task_progress_overlay_for_alert(detail=detail)
            overlay = self.ensure_task_alert_overlay()
            if overlay is not None:
                overlay.show_alert(title, detail)
        except Exception:
            pass

    def _is_long_task_alert_message(self, message):
        text = str(message or "")
        if not text.strip():
            return False
        markers = ("❌", "⚠️", "오류", "에러", "실패", "Error", "ERROR", "Exception", "Traceback")
        return any(m in text for m in markers)

    def handle_long_task_message(self, message, *, current=None, total=None):
        text = str(message or "")
        try:
            self.log(text)
        except Exception:
            pass
        if self._is_long_task_alert_message(text):
            self.update_task_progress_overlay(current=current, total=total, detail=text)
            self.show_task_alert_overlay("작업 알림", text)
            return
        self.update_task_progress_overlay(current=current, total=total, detail=text)

    def prepare_task_progress_overlay(self, title, detail="", total=0, cancellable=True):
        """Prepare the center progress overlay without showing it yet.

        The overlay should not appear while pre-flight validation dialogs are still
        possible.  It is displayed lazily on the first worker progress/log signal,
        which means a missing key / confirmation / early alert does not leave a
        fake progress panel on screen.
        """
        try:
            self._pending_task_progress_overlay = {
                "title": str(title or "작업 중"),
                "detail": str(detail or ""),
                "total": int(total or 0) if str(total or "").strip() else 0,
                "cancellable": bool(cancellable),
            }
            self.ensure_task_progress_overlay()
        except Exception:
            self._pending_task_progress_overlay = None

    def show_task_progress_overlay(self, title, detail="", total=0, cancellable=True):
        try:
            self._pending_task_progress_overlay = None
            overlay = self.ensure_task_progress_overlay()
            if overlay is None:
                return
            overlay.show_task(title, detail, total=total, cancellable=cancellable)
        except Exception:
            pass

    def update_task_progress_overlay(self, current=None, total=None, detail=None):
        try:
            overlay = getattr(self, "_task_progress_overlay", None)
            pending = getattr(self, "_pending_task_progress_overlay", None)
            if (overlay is None or not overlay.isVisible()) and pending:
                overlay = self.ensure_task_progress_overlay()
                if overlay is not None:
                    show_detail = str(detail if detail is not None else pending.get("detail", ""))
                    show_total = total if total is not None else pending.get("total", 0)
                    overlay.show_task(
                        pending.get("title", "작업 중"),
                        show_detail,
                        total=show_total,
                        cancellable=pending.get("cancellable", True),
                    )
                    self._pending_task_progress_overlay = None
            if overlay is not None and overlay.isVisible():
                overlay.update_task(current=current, total=total, detail=detail)
        except Exception:
            pass

    def hide_task_progress_overlay(self):
        try:
            self._pending_task_progress_overlay = None
            overlay = getattr(self, "_task_progress_overlay", None)
            if overlay is not None:
                overlay.hide()
            alert = getattr(self, "_task_alert_overlay", None)
            if alert is not None:
                alert.hide()
        except Exception:
            pass

    def request_current_long_task_cancel(self):
        """Cancel button handler for the center progress overlay.

        Long OCR/API/local-model calls cannot always be interrupted in the middle of
        the current request.  Workers stop before the next page/chunk/step.
        """
        self._long_task_cancel_requested = True
        worker = None
        for name in ("translation_worker", "bw", "iw", "w"):
            try:
                candidate = getattr(self, name, None)
            except Exception:
                candidate = None
            if candidate is not None and hasattr(candidate, "stop"):
                worker = candidate
                try:
                    candidate.stop()
                except Exception:
                    pass
        self.update_task_progress_overlay(
            detail="취소 요청됨. 현재 진행중인 과정이 완료 된 후 종료됩니다."
        )
        try:
            self.log("⏹️ 취소 요청됨: 현재 진행중인 과정이 완료된 후 종료됩니다.")
        except Exception:
            pass

    def busy_reason_text(self, reason=""):
        reason = str(reason or "").strip()
        if reason:
            return reason
        return "Working..." if getattr(self, "ui_language", LANG_KO) == LANG_EN else "작업 중"

    def begin_busy_state(self, reason="작업 중"):
        """긴 내부 작업 중에는 Wait Cursor와 UI 잠금을 걸어 중복 클릭을 막는다."""
        try:
            if not hasattr(self, "_busy_counter"):
                self._busy_counter = 0
            if not hasattr(self, "_busy_reason_stack"):
                self._busy_reason_stack = []
            self._busy_counter += 1
            self._busy_reason_stack.append(self.busy_reason_text(reason))
            if self._busy_counter > 1:
                QApplication.processEvents()
                return

            try:
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            except Exception:
                pass

            widgets = []
            try:
                cw = self.centralWidget()
                if cw is not None:
                    widgets.append(cw)
            except Exception:
                pass
            try:
                mb = self.menuBar()
                if mb is not None:
                    widgets.append(mb)
            except Exception:
                pass
            try:
                for tb in self.findChildren(QToolBar):
                    widgets.append(tb)
            except Exception:
                pass

            self._busy_widgets = []
            for w in widgets:
                try:
                    self._busy_widgets.append((w, bool(w.isEnabled())))
                    w.setEnabled(False)
                except Exception:
                    pass

            try:
                self.setCursor(Qt.CursorShape.WaitCursor)
            except Exception:
                pass

            text = self._busy_reason_stack[-1] if self._busy_reason_stack else self.busy_reason_text(reason)
            self.log(
                f"⏳ Busy: {text} / UI locked"
                if getattr(self, "ui_language", LANG_KO) == LANG_EN else
                f"⏳ 작업 중: {text} / UI 잠금"
            )
            QApplication.processEvents()
        except Exception:
            pass

    def end_busy_state(self, reason=""):
        """begin_busy_state()로 잠근 UI와 커서를 복구한다."""
        try:
            if not hasattr(self, "_busy_counter"):
                self._busy_counter = 0
            if self._busy_counter <= 0:
                self._busy_counter = 0
                return

            self._busy_counter -= 1
            try:
                if getattr(self, "_busy_reason_stack", None):
                    self._busy_reason_stack.pop()
            except Exception:
                pass

            if self._busy_counter > 0:
                QApplication.processEvents()
                return

            for w, enabled in reversed(getattr(self, "_busy_widgets", []) or []):
                try:
                    w.setEnabled(enabled)
                except Exception:
                    pass
            self._busy_widgets = []

            try:
                self.unsetCursor()
            except Exception:
                pass
            try:
                while QApplication.overrideCursor() is not None:
                    QApplication.restoreOverrideCursor()
            except Exception:
                pass

            text = self.busy_reason_text(reason)
            self.hide_task_progress_overlay()
            self.log(
                f"✅ Busy finished: {text} / UI unlocked"
                if getattr(self, "ui_language", LANG_KO) == LANG_EN else
                f"✅ 작업 완료: {text} / UI 잠금 해제"
            )
            QApplication.processEvents()
        except Exception:
            try:
                QApplication.restoreOverrideCursor()
            except Exception:
                pass

    def guard_project_action(self, action_name="프로젝트 작업"):
        """일괄 작업 중에는 프로젝트 열기/저장/위치 변경 같은 구조 변경 동작을 막는다."""
        if getattr(self, "is_batch_running", False):
            QMessageBox.information(
                self,
                self.tr_ui("일괄 작업 중"),
                self.tr_msg(f"현재 일괄 작업이 진행 중입니다.\n{action_name}은(는) 일괄 작업이 끝난 뒤 다시 시도해 주세요."),
            )
            self.log(f"⛔ 일괄 작업 중 차단됨: {action_name}")
            return False
        return True

    def set_project_action_interlock(self, locked):
        """일괄 작업 중 사용하면 위험한 프로젝트 관련 메뉴를 비활성화한다."""
        for key in (
            "project_new",
            "project_open",
            "project_open_json",
            "project_save",
            "project_save_as",
            "option_workspace_location",
            "option_workspace_reset_default",
        ):
            action = self.actions.get(key) if hasattr(self, "actions") else None
            if action is not None:
                action.setEnabled(not locked)

    def close_current_project_state_for_switch(self):
        """새 프로젝트를 열기 전 현재 프로젝트의 임시 상태를 정리한다."""
        try:
            self.cleanup_work_cache()
        except Exception:
            pass
        try:
            self.delete_temp_project_if_needed()
        except Exception:
            pass
        self.has_unsaved_changes = False

    def confirm_close_current_project_for_open(self, source_text=""):
        """외부 .ysbt 열기 요청이 들어왔을 때 현재 프로젝트를 닫을지 확인한다."""
        if not self.has_open_project():
            return True
        title = self.tr_ui("프로젝트 열기")
        message = self.tr_msg(
            "현재 열려있는 프로젝트를 닫고 새 프로젝트를 열까요?\n\n"
            "[예] 기존 프로젝트를 닫고 새 프로젝트를 엽니다.\n"
            "[아니오] 열기를 취소합니다."
        )
        if source_text:
            message += f"\n\n{self.tr_ui('열려고 하는 파일:')}\n{source_text}"
        ans = styled_question(
            self,
            title,
            message,
            default_yes=False,
        )
        if ans != QMessageBox.StandardButton.Yes:
            self.log("↩️ 외부 프로젝트 열기 취소")
            return False

        # 저장하지 않은 작업이 있으면 기존 저장 확인 루틴을 한 번 더 거친다.
        # 사용자가 저장/저장 안 함/취소 중 선택할 수 있게 해서 데이터 손실을 막는다.
        if self.has_unsaved_changes:
            return self.confirm_unsaved_before_switch()

        self.close_current_project_state_for_switch()
        return True

    def setup_external_open_queue_monitor(self):
        """YSB Launcher가 기록한 .ysbt 열기 요청 큐를 감시한다."""
        try:
            self.write_external_open_runtime_info()
        except Exception:
            pass

        self._external_open_queue_timer = QTimer(self)
        self._external_open_queue_timer.setInterval(350)
        self._external_open_queue_timer.timeout.connect(self.process_external_open_queue)
        self._external_open_queue_timer.start()

        self._external_runtime_timer = QTimer(self)
        self._external_runtime_timer.setInterval(5000)
        self._external_runtime_timer.timeout.connect(self.write_external_open_runtime_info)
        self._external_runtime_timer.start()

        QTimer.singleShot(700, self.process_external_open_queue)

    def write_external_open_runtime_info(self):
        """경량 런처가 메인 앱 실행 여부를 빠르게 판단할 수 있게 pid 정보를 남긴다."""
        try:
            path = ysb_main_runtime_info_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "pid": os.getpid(),
                "exe": str(Path(sys.executable).resolve()),
                "time": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                "queue": str(ysb_open_queue_path()),
            }
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
        except Exception:
            pass

    def cleanup_external_open_runtime_info(self):
        """정상 종료 시 런처용 pid 정보를 정리한다. 실패해도 종료는 막지 않는다."""
        try:
            path = ysb_main_runtime_info_path()
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if int(data.get("pid") or -1) != os.getpid():
                        return
                except Exception:
                    pass
                path.unlink()
        except Exception:
            pass

    def is_fresh_external_open_payload(self, payload, max_age_sec=600):
        """오래 전에 남은 열기 큐가 재실행 때 이전 프로젝트를 다시 여는 일을 막는다."""
        try:
            t = payload.get("time_epoch")
            if t is None:
                return False
            age = time.time() - float(t)
            return 0 <= age <= float(max_age_sec)
        except Exception:
            return False

    def process_external_open_queue(self):
        """open_queue.jsonl에 쌓인 .ysbt 열기 요청을 기존 창에서 처리한다."""
        queue_path = ysb_open_queue_path()
        if not queue_path.exists():
            return
        try:
            processing_path = queue_path.with_suffix(f".processing.{os.getpid()}.{int(time.time() * 1000)}")
            try:
                queue_path.replace(processing_path)
            except FileNotFoundError:
                return
            except Exception:
                # 다른 프로세스가 쓰는 순간이면 다음 타이머에서 다시 처리한다.
                return

            try:
                raw = processing_path.read_text(encoding="utf-8", errors="replace")
            finally:
                try:
                    processing_path.unlink()
                except Exception:
                    pass

            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    continue
                if not isinstance(payload, dict):
                    continue
                if not self.is_fresh_external_open_payload(payload):
                    try:
                        self.log("🧹 오래된 외부 열기 큐 무시")
                    except Exception:
                        pass
                    continue
                command = str(payload.get("command") or "activate")
                if command == "activate":
                    self.handle_single_instance_payload({"command": "activate", "source": "launcher-queue"})
                    continue
                if command != "open":
                    continue
                path = str(payload.get("path") or "")
                if not path:
                    continue
                if not (path.lower().endswith(YSB_EXTENSION) or os.path.basename(path).lower() == PROJECT_FILENAME):
                    continue
                self.handle_single_instance_payload({"command": "open", "path": path, "source": "launcher-queue"})
        except Exception as e:
            try:
                self.log(f"⚠️ 외부 열기 큐 처리 실패: {e}")
            except Exception:
                pass

    def handle_single_instance_payload(self, payload):
        """두 번째 실행 프로세스에서 넘어온 메시지를 현재 창에서 처리한다."""
        self.force_app_focus(reason="external request")
        payload = payload or {}
        command = str(payload.get("command", "activate") or "activate")
        if command != "open":
            return
        path = str(payload.get("path", "") or "")
        if not path:
            return
        if not self.guard_project_action("외부 YSBT 파일 열기"):
            return
        if not self.confirm_close_current_project_for_open(path):
            return
        self.open_project_path(path, external_request=True)
        self.force_app_focus(reason="external file open")

    def is_supported_image_path(self, path):
        try:
            return bool(path) and Path(str(path)).suffix.lower() in IMAGE_DROP_EXTS and os.path.isfile(str(path))
        except Exception:
            return False

    def normalize_image_drop_paths(self, paths):
        out = []
        seen = set()
        for path in paths or []:
            try:
                p = os.path.abspath(str(path))
            except Exception:
                continue
            if p.lower() in seen:
                continue
            if self.is_supported_image_path(p):
                out.append(p)
                seen.add(p.lower())
        return out

    def page_original_name(self, page_idx):
        try:
            curr = self.data.get(int(page_idx), {}) if isinstance(self.data, dict) else {}
            name = curr.get("original_name") if isinstance(curr, dict) else ""
            if name:
                return str(name)
            return os.path.basename(str(self.paths[int(page_idx)]))
        except Exception:
            return f"page{int(page_idx) + 1:03d}"

    def page_display_name(self, page_idx, mode=None, include_ext=False):
        mode = normalize_page_display_mode(mode or getattr(self, "page_tab_display_name_mode", DEFAULT_PAGE_DISPLAY_MODE))
        original = self.page_original_name(page_idx)
        stem = safe_page_file_stem(original, fallback=f"page{int(page_idx) + 1:03d}")
        ext = Path(str(original)).suffix if include_ext else ""
        if mode == PAGE_DISPLAY_MODE_ORIGINAL:
            return f"{stem}{ext}"
        if mode == PAGE_DISPLAY_MODE_PAGE_NUMBER:
            return f"page{int(page_idx) + 1:03d}{ext}"
        return f"{int(page_idx) + 1}p_{stem}{ext}"

    def output_display_stem(self, page_idx):
        return self.page_display_name(page_idx, mode=getattr(self, "output_display_name_mode", DEFAULT_PAGE_DISPLAY_MODE), include_ext=False)

    def path_for_output_display(self, page_idx):
        """구버전 호환용 표시명 경로. 실제 출력은 output_display_stem을 별도로 넘긴다."""
        try:
            src = str(self.paths[int(page_idx)])
            ext = Path(src).suffix or ".png"
            return os.path.join(os.path.dirname(os.path.abspath(src)), self.output_display_stem(page_idx) + ext)
        except Exception:
            return os.path.join(self.get_output_root(), self.output_display_stem(page_idx) + ".png")

    def ensure_page_source_path(self, page_idx):
        """원본 파일명 변경/저장 후 self.paths가 낡았을 때 images/original_name 기준으로 복구한다."""
        try:
            page_idx = int(page_idx)
        except Exception:
            return False
        if page_idx < 0 or page_idx >= len(getattr(self, "paths", []) or []):
            return False

        try:
            current = Path(str(self.paths[page_idx]))
            if current.exists():
                return True
        except Exception:
            current = None

        curr = self.data.get(page_idx, {}) if isinstance(self.data, dict) else {}
        original = curr.get("original_name") if isinstance(curr, dict) else ""
        images_dirs = []
        try:
            if self.project_dir:
                images_dirs.append(Path(str(self.project_dir)) / "images")
        except Exception:
            pass
        try:
            active = self.active_page_storage_dir()
            if active:
                images_dirs.append(Path(str(active)) / "images")
        except Exception:
            pass

        candidates = []
        if original:
            for d in images_dirs:
                candidates.append(d / str(original))

        original_stem = Path(str(original)).stem.lower() if original else ""
        for d in images_dirs:
            try:
                if not d.exists():
                    continue
                if original_stem:
                    for p in d.iterdir():
                        if p.is_file() and p.stem.lower() == original_stem:
                            candidates.append(p)
                if current is not None:
                    old_stem = current.stem.lower()
                    for p in d.iterdir():
                        if p.is_file() and p.stem.lower() == old_stem:
                            candidates.append(p)
            except Exception:
                pass

        for cand in candidates:
            try:
                if cand.exists() and cand.is_file():
                    self.paths[page_idx] = str(cand)
                    if isinstance(curr, dict):
                        curr["original_name"] = cand.name
                        self.data[page_idx] = curr
                    try:
                        self.save_project_store(self.project_store)
                    except Exception:
                        pass
                    return True
            except Exception:
                pass

        return False

    def collect_used_source_stems_for_rename(self, except_index=None):
        used = set()
        try:
            except_index = None if except_index is None else int(except_index)
        except Exception:
            except_index = None
        for i, p in enumerate(getattr(self, "paths", []) or []):
            if except_index is not None and i == except_index:
                continue
            try:
                used.add(Path(str(p)).stem.lower())
            except Exception:
                pass
            try:
                curr = self.data.get(i, {}) if isinstance(self.data, dict) else {}
                original = curr.get("original_name") if isinstance(curr, dict) else ""
                if original:
                    used.add(Path(str(original)).stem.lower())
            except Exception:
                pass
        return used

    def unique_source_rename_target(self, current_path, requested_stem, page_index):
        current = Path(str(current_path))
        folder = current.parent
        ext = current.suffix or ".png"
        base = safe_page_file_stem(requested_stem, fallback=current.stem or "image")
        used = self.collect_used_source_stems_for_rename(except_index=page_index)

        def candidate(n=None):
            stem = base if n is None else f"{base}({n})"
            return stem, folder / f"{stem}{ext}"

        stem, path = candidate(None)
        if stem.lower() not in used and (not path.exists() or str(path.resolve()).lower() == str(current.resolve()).lower()):
            return str(path), False

        for n in range(1, 10000):
            stem, path = candidate(n)
            if stem.lower() not in used and not path.exists():
                return str(path), True

        stem = f"{base}({uuid.uuid4().hex[:8]})"
        return str(folder / f"{stem}{ext}"), True

    def rename_page_source_from_tab(self, page_idx):
        return self.rename_page_source_file(page_idx)

    def rename_current_page_source_file(self):
        return self.rename_page_source_file(getattr(self, "idx", 0))

    def rename_page_source_file(self, page_idx):
        """프로젝트 내부 images 원본 파일명을 변경하고 관련 기준 이름을 갱신한다."""
        if not getattr(self, "paths", None):
            return False
        try:
            page_idx = int(page_idx)
        except Exception:
            page_idx = int(getattr(self, "idx", 0) or 0)
        if page_idx < 0 or page_idx >= len(self.paths):
            return False
        if not self.guard_project_action("페이지 탭 파일명 변경"):
            return False

        current_path = Path(str(self.paths[page_idx]))
        if not current_path.exists():
            QMessageBox.warning(
                self,
                self.tr_ui("파일 없음"),
                f"{self.tr_ui('현재 페이지의 원본 이미지 파일을 찾을 수 없습니다.')}\n{current_path}",
            )
            return False

        current_stem = current_path.stem
        while True:
            new_stem, ok = QInputDialog.getText(
                self,
                self.tr_ui("페이지 탭 파일명 변경"),
                self.tr_msg("새 원본 파일명을 입력하세요.\n확장자는 현재 파일의 확장자를 유지합니다."),
                QLineEdit.EchoMode.Normal,
                current_stem,
            )
            if not ok:
                return False
            new_stem = safe_page_file_stem(Path(str(new_stem or "")).stem, fallback=current_stem)
            if not new_stem:
                continue
            if new_stem == current_stem:
                return False

            target_path, has_conflict = self.unique_source_rename_target(current_path, new_stem, page_idx)
            if has_conflict:
                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Icon.Warning)
                msg.setWindowTitle(self.tr_ui("파일명 중복"))
                msg.setText(self.tr_ui("같은 이름의 원본 이미지 파일명이 이미 있습니다."))
                msg.setInformativeText(
                    f"{self.tr_ui('입력한 이름')} : {new_stem}{current_path.suffix}\n"
                    f"{self.tr_ui('자동 이름')} : {os.path.basename(target_path)}"
                )
                btn_auto = msg.addButton(self.tr_ui("자동 이름 사용"), QMessageBox.ButtonRole.AcceptRole)
                btn_retry = msg.addButton(self.tr_ui("다시 입력"), QMessageBox.ButtonRole.ActionRole)
                btn_cancel = msg.addButton(self.tr_ui("취소"), QMessageBox.ButtonRole.RejectRole)
                for _btn in (btn_auto, btn_retry, btn_cancel):
                    try:
                        _btn.setMinimumWidth(128)
                    except Exception:
                        pass
                msg.setDefaultButton(btn_retry)
                msg.setEscapeButton(btn_cancel)
                try:
                    msg.setStyleSheet(
                        self.message_box_style()
                        + "\nQMessageBox QPushButton { min-width:128px; padding:6px 14px; }"
                    )
                except Exception:
                    pass
                force_message_box_front(msg)
                msg.exec()
                clicked = msg.clickedButton()
                if clicked is btn_cancel:
                    return False
                if clicked is btn_retry:
                    current_stem = new_stem
                    continue
                # 자동 이름 사용은 target_path 그대로 진행
            break

        try:
            self.commit_current_page_ui_to_data()
            self.remember_current_view_state()
        except Exception:
            pass

        undo_rec = None
        if not getattr(self, "_project_undo_restore_lock", False):
            try:
                undo_rec = self.make_project_undo_record("원본 파일명 변경", page_idx=page_idx, full_project=True)
            except Exception:
                undo_rec = None

        new_path = Path(target_path)
        try:
            if str(current_path.resolve()).lower() == str(new_path.resolve()).lower() and str(current_path) != str(new_path):
                temp_path = current_path.with_name(f".__ysb_rename_tmp_{uuid.uuid4().hex}{current_path.suffix}")
                os.rename(str(current_path), str(temp_path))
                os.rename(str(temp_path), str(new_path))
            else:
                os.rename(str(current_path), str(new_path))
        except Exception as e:
            QMessageBox.critical(
                self,
                self.tr_ui("파일명 변경 실패"),
                f"{self.tr_ui('원본 이미지 파일명을 변경하지 못했습니다.')}\n{e}",
            )
            return False

        self.paths[page_idx] = str(new_path)
        if not isinstance(self.data, dict):
            self.data = {}
        curr = self.data.get(page_idx) or {}
        curr["original_name"] = os.path.basename(str(new_path))
        self.data[page_idx] = curr

        if undo_rec is not None:
            try:
                undo_rec["file_rename_ops"] = [{
                    "page_idx": int(page_idx),
                    "from_path": str(new_path),
                    "to_path": str(current_path),
                    "reason": "원본 파일명 변경",
                }]
                self.append_project_undo_record(undo_rec)
            except Exception:
                pass

        try:
            if hasattr(self, "page_tab_bar"):
                self.page_tab_bar.setTabText(page_idx, self.page_display_name(page_idx))
                self.page_tab_bar.setTabToolTip(page_idx, self.page_display_name(page_idx, include_ext=True))
        except Exception:
            pass
        try:
            if page_idx == self.idx:
                self.load()
                self.restore_current_view_state_later()
        except Exception:
            pass
        try:
            self.save_project_store(self.project_store)
        except Exception:
            pass
        self.auto_save_project()
        self.log(f"✏️ 원본 파일명 변경: {current_path.name} → {new_path.name}")
        return True

    def apply_page_tab_style(self):
        if not hasattr(self, "page_tab_container") or not hasattr(self, "page_tab_bar"):
            return
        if self.is_light_theme():
            self.page_tab_container.setStyleSheet("background:#eef2f8; border:1px solid #dfe5ef; border-radius:0px;")
            self.page_tab_bar.setStyleSheet(
                "QTabBar::tab { background:#ffffff; color:#4b5563; padding:6px 28px 6px 10px; border:1px solid #cfd7e5; border-bottom:1px solid #cfd7e5; border-radius:0px; min-width:82px; }"
                "QTabBar::tab:selected { background:#dbeafe; color:#111827; font-weight:700; border-color:#8fb4e8; }"
                "QTabBar::tab:hover { background:#edf4ff; color:#111827; }"
                "QTabBar::scroller { width:0px; }"
                "QTabBar QToolButton { width:0px; height:0px; max-width:0px; max-height:0px; border:0px; padding:0px; margin:0px; background:transparent; color:transparent; }"
            )
            if hasattr(self, "btn_page_tab_menu"):
                self.btn_page_tab_menu.setStyleSheet(
                    "QToolButton { background:#ffffff; color:#1f2937; border:1px solid #cfd7e5; border-radius:0px; font-size:16px; font-weight:700; }"
                    "QToolButton:hover { background:#edf4ff; border-color:#8fb4e8; }"
                    "QToolButton:disabled { background:#eef2f8; color:#9ca3af; border:1px solid #d1d5db; }"
                )
            for _btn in (getattr(self, "btn_page_scroll_left", None), getattr(self, "btn_page_scroll_right", None)):
                if _btn is not None:
                    _btn.setStyleSheet(
                        "QToolButton { background:#ffffff; color:#111827; border:1px solid #cfd7e5; border-radius:0px; font-size:14px; font-weight:900; padding:0px; }"
                        "QToolButton:hover { background:#edf4ff; border-color:#8fb4e8; }"
                        "QToolButton:disabled { background:#eef2f8; color:#9ca3af; border:1px solid #d1d5db; }"
                    )
            if hasattr(self, "btn_page_add"):
                self.btn_page_add.setStyleSheet(
                    "QToolButton { background:#ffffff; color:#1f2937; border:1px solid #cfd7e5; border-radius:0px; font-size:17px; font-weight:700; }"
                    "QToolButton:hover { background:#edf4ff; border-color:#8fb4e8; }"
                    "QToolButton:disabled { background:#eef2f8; color:#9ca3af; border:1px solid #d1d5db; }"
                )
            try:
                self.page_tab_bar.apply_theme(True)
            except Exception:
                pass
            self.update_page_tab_scroll_buttons()
        else:
            self.page_tab_container.setStyleSheet("background:#20242b; border:1px solid #3b414c; border-radius:0px;")
            self.page_tab_bar.setStyleSheet(
                "QTabBar::tab { background:#2a2e36; color:#b5bfce; padding:6px 28px 6px 10px; border:1px solid #3b414c; border-bottom:1px solid #3b414c; border-radius:0px; min-width:82px; }"
                "QTabBar::tab:selected { background:#3d587d; color:#ffffff; font-weight:700; border-color:#7ea2d6; }"
                "QTabBar::tab:hover { background:#38404c; color:#ffffff; }"
                "QTabBar::scroller { width:0px; }"
                "QTabBar QToolButton { width:0px; height:0px; max-width:0px; max-height:0px; border:0px; padding:0px; margin:0px; background:transparent; color:transparent; }"
            )
            if hasattr(self, "btn_page_tab_menu"):
                self.btn_page_tab_menu.setStyleSheet(
                    "QToolButton { background:#2a2e36; color:#ffffff; border:1px solid #3b414c; border-radius:0px; font-size:16px; font-weight:700; }"
                    "QToolButton:hover { background:#38404c; border-color:#7ea2d6; }"
                    "QToolButton:disabled { background:#1f232a; color:#6b7280; border:1px solid #333946; }"
                )
            for _btn in (getattr(self, "btn_page_scroll_left", None), getattr(self, "btn_page_scroll_right", None)):
                if _btn is not None:
                    _btn.setStyleSheet(
                        "QToolButton { background:#2a2e36; color:#ffffff; border:1px solid #3b414c; border-radius:0px; font-size:14px; font-weight:900; padding:0px; }"
                        "QToolButton:hover { background:#38404c; border-color:#7ea2d6; }"
                        "QToolButton:disabled { background:#1f232a; color:#6b7280; border:1px solid #333946; }"
                    )
            if hasattr(self, "btn_page_add"):
                self.btn_page_add.setStyleSheet(
                    "QToolButton { background:#2a2e36; color:#ffffff; border:1px solid #3b414c; border-radius:0px; font-size:17px; font-weight:700; }"
                    "QToolButton:hover { background:#38404c; border-color:#7ea2d6; }"
                    "QToolButton:disabled { background:#1f232a; color:#6b7280; border:1px solid #333946; }"
                )
            try:
                self.page_tab_bar.apply_theme(False)
            except Exception:
                pass
            self.update_page_tab_scroll_buttons()

    def scroll_page_tabs_left(self):
        self.page_tab_scroll_generation = int(getattr(self, "page_tab_scroll_generation", 0) or 0) + 1
        bar = getattr(self, "page_tab_bar", None)
        if bar is not None and hasattr(bar, "scroll_step"):
            return bar.scroll_step(-1)
        return False

    def scroll_page_tabs_right(self):
        self.page_tab_scroll_generation = int(getattr(self, "page_tab_scroll_generation", 0) or 0) + 1
        bar = getattr(self, "page_tab_bar", None)
        if bar is not None and hasattr(bar, "scroll_step"):
            return bar.scroll_step(+1)
        return False

    def update_page_tab_scroll_buttons(self):
        """커스텀 탭바에서는 내부 스크롤 버튼 보정이 필요 없다."""
        try:
            bar = getattr(self, "page_tab_bar", None)
            if bar is not None and hasattr(bar, "apply_theme"):
                bar.apply_theme(self.is_light_theme())
        except Exception:
            pass

    def schedule_current_page_tab_visible(self, center=False):
        scheduled_generation = int(getattr(self, "page_tab_scroll_generation", 0) or 0)
        def _run():
            if scheduled_generation != int(getattr(self, "page_tab_scroll_generation", 0) or 0):
                return
            self.ensure_current_page_tab_visible(center=center)
        QTimer.singleShot(0, _run)

    def ensure_current_page_tab_visible(self, center=False):
        """현재 페이지 탭이 페이지탭 박스 안에 완전히 보이도록 스크롤한다."""
        try:
            bar = getattr(self, "page_tab_bar", None)
            if bar is None or not hasattr(bar, "scroll") or not hasattr(bar, "_tabs"):
                return False
            idx = int(getattr(self, "idx", 0) or 0)
            if idx < 0 or idx >= len(bar._tabs):
                return False

            sb = bar.scroll.horizontalScrollBar()
            viewport_w = bar.scroll.viewport().width()
            tab = bar._tabs[idx]
            left = int(tab.x())
            right = int(tab.x() + tab.width())
            cur = int(sb.value())
            view_left = cur
            view_right = cur + max(1, viewport_w)

            if center:
                target = left - max(0, (viewport_w - tab.width()) // 2)
            elif left < view_left:
                target = left
            elif right > view_right:
                target = right - viewport_w
            else:
                return True

            target = max(sb.minimum(), min(sb.maximum(), int(target)))
            sb.setValue(target)
            return True
        except Exception:
            return False

    def show_current_page_full_name(self):
        """Alt+V: 현재 페이지 탭 전체 이름을 누르고 있는 동안만 보여준다."""
        if not getattr(self, "paths", None):
            self.log("⚠️ 표시할 페이지가 없습니다.")
            return False
        try:
            page_idx = max(0, min(int(self.idx), len(self.paths) - 1))
        except Exception:
            page_idx = 0
        text = self.page_display_name(page_idx, include_ext=True)
        try:
            bar = getattr(self, "page_tab_bar", None)
            if bar is not None and 0 <= page_idx < bar.count():
                rect = bar.tabRect(page_idx)
                anchor = bar.mapToGlobal(rect.bottomLeft()) + QPoint(0, 8)
            else:
                anchor = QCursor.pos() + QPoint(12, 12)

            html = self.native_tooltip_html("현재 페이지 이름", "Alt+V", text)
            popup = getattr(self, "_page_full_name_popup", None)
            if popup is None:
                popup = QLabel()
                popup.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
                popup.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                popup.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
                popup.setTextFormat(Qt.TextFormat.RichText)
                self._page_full_name_popup = popup
            popup.setText(html)
            if self.is_light_theme():
                popup.setStyleSheet("QLabel { background:#ffffff; color:#111827; border:1px solid #cfd7e5; border-radius:0px; padding:5px; }")
            else:
                popup.setStyleSheet("QLabel { background:#1f2430; color:#ffffff; border:1px solid #4b5563; border-radius:0px; padding:5px; }")
            popup.adjustSize()
            popup.move(anchor)
            popup.show()
            self._page_full_name_popup_hold_by_shortcut = True
        except Exception:
            try:
                QMessageBox.information(self, self.tr_ui("현재 페이지 이름"), text)
            except Exception:
                pass
        self.log(f"📄 현재 페이지 이름: {text}")
        return True

    def hide_current_page_full_name(self):
        try:
            QToolTip.hideText()
        except Exception:
            pass
        try:
            popup = getattr(self, "_page_full_name_popup", None)
            if popup is not None:
                popup.hide()
        except Exception:
            pass
        self._page_full_name_popup_hold_by_shortcut = False

    def hide_page_tab_menu(self):
        try:
            old_popup = getattr(self, "_page_list_popup", None)
            if old_popup is not None and old_popup.isVisible():
                old_popup.close()
        except Exception:
            pass
        self._page_list_popup = None
        self._page_list_popup_hold_by_shortcut = False

    def show_page_tab_menu(self, hold_by_shortcut=False):
        """좌측 3선 버튼/단축키에서 현재 프로젝트의 페이지 목록을 포커스 가능한 세로 목록으로 보여준다."""
        try:
            old_popup = getattr(self, "_page_list_popup", None)
            if old_popup is not None and old_popup.isVisible():
                if hold_by_shortcut:
                    self._page_list_popup_hold_by_shortcut = True
                    return
                old_popup.close()
                return
        except Exception:
            pass
        self._page_list_popup_hold_by_shortcut = bool(hold_by_shortcut)

        btn = getattr(self, "btn_page_tab_menu", None)
        anchor = btn if btn is not None else self

        popup = QFrame(self, Qt.WindowType.Popup)
        self._page_list_popup = popup
        popup.setObjectName("PageListPopup")
        popup.setMinimumWidth(260)
        try:
            if self.is_light_theme():
                popup.setStyleSheet(
                    "QFrame#PageListPopup { background:#ffffff; color:#111827; border:1px solid #cfd7e5; }"
                    "QLabel { color:#111827; font-weight:700; padding:6px 8px 2px 8px; }"
                    "QListWidget { background:#ffffff; color:#111827; border:0px; outline:0px; }"
                    "QListWidget::item { padding:6px 10px; min-height:22px; }"
                    "QListWidget::item:selected { background:#dbeafe; color:#111827; }"
                    "QListWidget::item:hover { background:#edf4ff; }"
                )
            else:
                popup.setStyleSheet(
                    "QFrame#PageListPopup { background:#24282f; color:#ffffff; border:1px solid #3b414c; }"
                    "QLabel { color:#ffffff; font-weight:700; padding:6px 8px 2px 8px; }"
                    "QListWidget { background:#24282f; color:#ffffff; border:0px; outline:0px; }"
                    "QListWidget::item { padding:6px 10px; min-height:22px; }"
                    "QListWidget::item:selected { background:#3d587d; color:#ffffff; }"
                    "QListWidget::item:hover { background:#38404c; }"
                )
        except Exception:
            pass

        layout = QVBoxLayout(popup)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        title = QLabel(self.tr_ui("페이지 목록"), popup)
        layout.addWidget(title)

        page_list = QListWidget(popup)
        page_list.setUniformItemSizes(True)
        page_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        page_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        page_list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        popup.page_list_widget = page_list
        layout.addWidget(page_list)

        current_page_item = None
        if not self.paths:
            item = QListWidgetItem(self.tr_ui("페이지 없음"))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            page_list.addItem(item)
        else:
            for i in range(len(self.paths)):
                label = self.page_display_name(i, include_ext=False)
                is_current = (i == self.idx)
                prefix = "▶ " if is_current else "   "
                item = QListWidgetItem(prefix + label)
                item.setData(Qt.ItemDataRole.UserRole, i)
                item.setData(Qt.ItemDataRole.UserRole + 1, is_current)
                try:
                    item.setToolTip(self.page_display_name(i, include_ext=True))
                except Exception:
                    pass
                if is_current:
                    current_page_item = item
                    try:
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)
                        if self.is_light_theme():
                            item.setBackground(QBrush(QColor("#fff7ed")))
                            item.setForeground(QBrush(QColor("#111827")))
                        else:
                            item.setBackground(QBrush(QColor("#303846")))
                            item.setForeground(QBrush(QColor("#ffffff")))
                    except Exception:
                        pass
                page_list.addItem(item)
            if 0 <= self.idx < page_list.count():
                page_list.setCurrentRow(self.idx)
                try:
                    page_list.setCurrentItem(page_list.item(self.idx), QItemSelectionModel.SelectionFlag.ClearAndSelect)
                except Exception:
                    pass
            elif page_list.count() > 0:
                page_list.setCurrentRow(0)

        def _activate_item(item=None):
            try:
                item = item or page_list.currentItem()
                if item is None:
                    return
                page = item.data(Qt.ItemDataRole.UserRole)
                if page is None:
                    return
                popup.close()
                self.jump_to_page_from_menu(int(page))
            except Exception:
                pass

        page_list.itemActivated.connect(_activate_item)
        page_list.itemClicked.connect(_activate_item)

        row_height = 30
        try:
            max_popup_height = max(180, self.height() // 2)
        except Exception:
            max_popup_height = 300
        visible_rows = max(1, min(page_list.count() or 1, max(1, (max_popup_height - 34) // row_height)))
        popup_height = min(max_popup_height, 34 + max(1, page_list.count()) * row_height)
        try:
            popup_width = max(360, min(760, self.width() // 2))
        except Exception:
            popup_width = 520
        popup.resize(popup_width, popup_height)
        page_list.setMinimumHeight(min(visible_rows * row_height, max_popup_height - 34))
        page_list.setMaximumHeight(max_popup_height - 34)

        try:
            pos = anchor.mapToGlobal(QPoint(0, anchor.height()))
        except Exception:
            pos = self.mapToGlobal(QPoint(40, 80))
        popup.move(pos)
        popup.show()
        popup.raise_()
        popup.activateWindow()
        try:
            if current_page_item is not None:
                page_list.scrollToItem(current_page_item, QAbstractItemView.ScrollHint.PositionAtCenter)
                page_list.setCurrentItem(current_page_item, QItemSelectionModel.SelectionFlag.ClearAndSelect)
            elif page_list.currentItem() is not None:
                page_list.scrollToItem(page_list.currentItem(), QAbstractItemView.ScrollHint.PositionAtCenter)
        except Exception:
            pass
        page_list.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def jump_to_page_from_menu(self, page_idx):
        try:
            page_idx = int(page_idx)
        except Exception:
            return
        if page_idx < 0 or page_idx >= len(self.paths):
            return
        if hasattr(self, "page_tab_bar"):
            try:
                self.page_tab_bar.setCurrentIndex(page_idx)
                return
            except Exception:
                pass
        self.on_page_tab_changed(page_idx)

    def refresh_page_tabs(self):
        if not hasattr(self, "page_tab_bar"):
            return
        bar = self.page_tab_bar
        has_pages = bool(self.paths)
        try:
            if hasattr(self, "btn_page_tab_menu"):
                self.btn_page_tab_menu.setEnabled(has_pages)
        except Exception:
            pass
        try:
            bar.setEnabled(has_pages)
        except Exception:
            pass
        self._refreshing_page_tabs = True
        try:
            bar.blockSignals(True)
            # QTabBar에는 QTabWidget처럼 clear() 메서드가 없으므로
            # 기존 탭은 removeTab() 루프로 제거한다.
            while bar.count() > 0:
                bar.removeTab(0)
            if not self.paths:
                bar.setTabsClosable(False)
                bar.setMovable(False)
                return
            bar.setTabsClosable(True)
            bar.setMovable(True)
            for i, _path in enumerate(self.paths):
                bar.addTab(self.page_display_name(i))
                try:
                    bar.setTabToolTip(i, self.page_display_name(i, include_ext=True))
                except Exception:
                    pass
            if self.idx < 0:
                self.idx = 0
            if self.idx >= len(self.paths):
                self.idx = len(self.paths) - 1
            bar.setCurrentIndex(self.idx)
        finally:
            try:
                bar.blockSignals(False)
            except Exception:
                pass
            self._refreshing_page_tabs = False
            try:
                self.update_page_tab_scroll_buttons()
            except Exception:
                pass

    def remap_indexed_dict_by_order(self, src, order):
        out = {}
        src = src or {}
        for new_idx, old_idx in enumerate(order or []):
            if old_idx in src:
                out[new_idx] = src.get(old_idx)
        return out

    def remap_view_states_by_order(self, order):
        states = getattr(self, "project_ui_view_states", {}) or {}
        if not isinstance(states, dict) or not order:
            self.project_ui_view_states = {} if not order else states
            return
        old_to_new = {int(old): int(new) for new, old in enumerate(order)}
        new_states = {}
        for key, state in states.items():
            try:
                page_s, mode_s = str(key).split(":", 1)
                old_page = int(page_s)
                if old_page in old_to_new:
                    new_states[f"{old_to_new[old_page]}:{int(mode_s)}"] = copy.deepcopy(state)
            except Exception:
                pass
        self.project_ui_view_states = new_states

    def on_page_tab_changed(self, index):
        if getattr(self, "_refreshing_page_tabs", False):
            return
        if index < 0 or index >= len(self.paths):
            return
        if index == self.idx:
            return

        preserve_scroll = None
        target_was_visible = False
        try:
            bar = getattr(self, "page_tab_bar", None)
            if bar is not None and hasattr(bar, "scroll") and hasattr(bar, "_tabs"):
                sb = bar.scroll.horizontalScrollBar()
                preserve_scroll = int(sb.value())
                if 0 <= int(index) < len(bar._tabs):
                    tab = bar._tabs[int(index)]
                    left = int(tab.x())
                    right = int(tab.x() + tab.width())
                    view_left = preserve_scroll
                    view_right = preserve_scroll + max(1, int(bar.scroll.viewport().width()))
                    target_was_visible = (left >= view_left and right <= view_right)
        except Exception:
            preserve_scroll = None
            target_was_visible = False

        # 페이지 전환은 구조 변경이 아니라 탐색 동작이다.
        # 이미 보이는 탭을 클릭했다면 탭바 시점은 보존하고,
        # 보이지 않거나 절반만 보일 때만 현재 순간 기준으로 한 번 보정한다.
        self.commit_current_page_ui_to_data()
        self.remember_current_view_state()
        self.idx = int(index)
        self.load()
        self.restore_current_view_state_later()

        scheduled_generation = int(getattr(self, "page_tab_scroll_generation", 0) or 0)

        def _restore_or_ensure_tab_position():
            # 예약 후 사용자가 좌우 화살표로 탭바를 수동 이동했다면,
            # 오래된 자동 보정은 실행하지 않는다.
            if scheduled_generation != int(getattr(self, "page_tab_scroll_generation", 0) or 0):
                return
            try:
                bar = getattr(self, "page_tab_bar", None)
                if target_was_visible and preserve_scroll is not None and bar is not None and hasattr(bar, "scroll"):
                    sb = bar.scroll.horizontalScrollBar()
                    sb.setValue(max(sb.minimum(), min(sb.maximum(), int(preserve_scroll))))
                    return
            except Exception:
                pass
            self.ensure_current_page_tab_visible()

        QTimer.singleShot(0, _restore_or_ensure_tab_position)

    def close_page_from_tab(self, index):
        if index < 0 or index >= len(self.paths):
            return
        name = self.page_display_name(index, include_ext=True)
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle(self.tr_ui("페이지 삭제"))
        msg.setText(self.tr_ui("이 페이지를 프로젝트에서 삭제할까요?"))
        msg.setInformativeText(str(name))
        btn_delete = msg.addButton(self.tr_ui("삭제"), QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = msg.addButton(self.tr_ui("취소"), QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_cancel)
        msg.setStyleSheet(self.message_box_style())
        force_message_box_front(msg)
        msg.exec()
        if msg.clickedButton() is not btn_delete:
            self.log("↩️ 페이지 삭제 취소")
            return
        self.delete_page_at(index)

    def delete_page_at(self, index):
        if index < 0 or index >= len(self.paths):
            return False
        self.commit_current_page_ui_to_data()
        self.remember_current_view_state()
        undo_rec = self.make_project_undo_record("페이지 삭제", full_project=True)
        old_count = len(self.paths)
        old_idx = self.idx
        order = [i for i in range(old_count) if i != index]
        removed_name = self.page_display_name(index, include_ext=True)
        self.paths.pop(index)
        self.data = self.remap_indexed_dict_by_order(self.data, order)
        self.remap_view_states_by_order(order)
        if self.paths:
            if old_idx > index:
                self.idx = old_idx - 1
            elif old_idx == index:
                self.idx = min(index, len(self.paths) - 1)
            else:
                self.idx = old_idx
        else:
            self.idx = 0
        self.page_text_undo_stacks = {}
        self.append_project_undo_record(undo_rec)
        self.load()
        self.auto_save_project()
        self.log(f"🗑️ 페이지 삭제: {removed_name}")
        return True

    def delete_current_page_shortcut(self):
        """Ctrl+Q: 현재 열려 있는 이미지 탭을 삭제한다."""
        if not getattr(self, "paths", None):
            self.log("⚠️ 삭제할 이미지탭이 없습니다.")
            return False
        try:
            index = max(0, min(int(self.idx), len(self.paths) - 1))
        except Exception:
            index = 0
        self.close_page_from_tab(index)
        return True

    def delete_all_pages_shortcut(self):
        """Ctrl+Shift+Q: 현재 프로젝트의 모든 이미지 탭을 삭제한다."""
        if not getattr(self, "paths", None):
            self.log("⚠️ 삭제할 이미지탭이 없습니다.")
            return False

        count = len(self.paths)
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle(self.tr_ui("전체 페이지 삭제"))
        msg.setText(self.tr_ui("현재 프로젝트의 모든 이미지탭을 삭제할까요?"))
        msg.setInformativeText(self.tr_ui(f"총 {count}개의 페이지가 삭제됩니다."))
        btn_delete = msg.addButton(self.tr_ui("전체 삭제"), QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = msg.addButton(self.tr_ui("취소"), QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_cancel)
        try:
            msg.setStyleSheet(self.message_box_style())
        except Exception:
            pass
        force_message_box_front(msg)
        msg.exec()
        if msg.clickedButton() is not btn_delete:
            self.log("↩️ 전체 페이지 삭제 취소")
            return False

        self.commit_current_page_ui_to_data()
        self.remember_current_view_state()
        undo_rec = self.make_project_undo_record("전체 페이지 삭제", full_project=True)
        self.paths = []
        self.data = {}
        self.idx = 0
        self.project_ui_view_states = {}
        self.page_text_undo_stacks = {}
        self.append_project_undo_record(undo_rec)
        self.load()
        self.auto_save_project()
        self.log(f"🗑️ 전체 이미지탭 삭제: {count}개")
        return True

    def on_page_tab_moved(self, from_index, to_index):
        if getattr(self, "_refreshing_page_tabs", False):
            return
        if from_index == to_index:
            return
        if from_index < 0 or to_index < 0 or from_index >= len(self.paths) or to_index >= len(self.paths):
            self.refresh_page_tabs()
            return

        bar = getattr(self, "page_tab_bar", None)
        try:
            visible_index = int(bar.currentIndex()) if bar is not None else int(self.idx)
        except Exception:
            visible_index = int(self.idx) if self.paths else 0
        try:
            tab_scroll_value = int(bar.scroll.horizontalScrollBar().value()) if bar is not None and hasattr(bar, "scroll") else None
        except Exception:
            tab_scroll_value = None

        self.commit_current_page_ui_to_data()
        self.remember_current_view_state()
        undo_rec = self.make_project_undo_record("페이지 순서 변경", full_project=True)

        n = len(self.paths)
        order = list(range(n))
        moved_old = order.pop(from_index)
        order.insert(to_index, moved_old)

        old_paths = list(self.paths)
        self.paths = [old_paths[old_i] for old_i in order]
        self.data = self.remap_indexed_dict_by_order(self.data, order)
        self.remap_view_states_by_order(order)

        # QTabBar가 이미 화면상으로 탭을 이동시켰으므로, 여기서 전체 탭을 다시 만들지 않는다.
        # 다시 만들면 드래그 직후 잡고 있던 탭/선택 위치가 한 번 더 튀어 보일 수 있다.
        self.idx = max(0, min(visible_index, len(self.paths) - 1)) if self.paths else 0
        self.page_text_undo_stacks = {}
        self.append_project_undo_record(undo_rec)

        try:
            if bar is not None:
                bar.blockSignals(True)
                try:
                    for i in range(min(bar.count(), len(self.paths))):
                        bar.setTabText(i, self.page_display_name(i))
                        bar.setTabToolTip(i, self.page_display_name(i, include_ext=True))
                    # 커스텀 탭바는 드래그 시 이미 시각적 이동을 끝낸 상태다.
                    # 여기서 currentIndex를 다시 강제로 바꾸면 탭 위치가 또 확인되는 느낌이 생기므로,
                    # 내부 idx와 표시 상태만 조용히 맞춘다.
                    try:
                        bar._current = self.idx
                        bar.apply_theme(self.is_light_theme())
                    except Exception:
                        pass
                finally:
                    bar.blockSignals(False)
        except Exception:
            pass

        self.load()
        self.restore_current_view_state_later()
        try:
            if tab_scroll_value is not None and bar is not None and hasattr(bar, "scroll"):
                QTimer.singleShot(0, lambda v=tab_scroll_value, b=bar: b.scroll.horizontalScrollBar().setValue(
                    max(b.scroll.horizontalScrollBar().minimum(), min(b.scroll.horizontalScrollBar().maximum(), int(v)))
                ))
        except Exception:
            pass
        self.update_page_tab_scroll_buttons()
        self.auto_save_project()
        self.log(f"↔️ 페이지 순서 변경: {from_index + 1} → {to_index + 1}")

    def active_page_storage_dir(self):
        """새로 삽입하는 이미지가 들어갈 현재 작업 기준 폴더.
        자동저장 OFF에서는 실제 프로젝트가 아니라 작업 캐시에 먼저 넣어야 한다.
        """
        root = str(self.project_dir or "")
        if not getattr(self, "auto_save_enabled", False):
            if not getattr(self, "work_project_dir", None):
                try:
                    self.start_work_cache_from_current(mark_dirty=True)
                except Exception:
                    pass
            root = str(getattr(self, "work_project_dir", None) or root)
        return root

    def unique_insert_image_path(self, src_path):
        storage_root = self.active_page_storage_dir() or str(self.project_dir)
        images_dir = os.path.join(storage_root, "images")
        os.makedirs(images_dir, exist_ok=True)
        src = Path(src_path)
        ext = src.suffix.lower() if src.suffix.lower() in IMAGE_DROP_EXTS else ".png"
        base = safe_page_file_stem(src.stem, fallback="inserted")

        # 원본 파일명을 최대한 보존하되, 확장자가 달라도 표시 stem이 겹치면 회피한다.
        # 예: 0007.jpg가 있으면 0007.png는 0007(1).png로 저장.
        existing_stems = set()
        try:
            for p in Path(images_dir).iterdir():
                if p.is_file():
                    existing_stems.add(p.stem.lower())
        except Exception:
            pass

        candidate_stem = base
        candidate = os.path.join(images_dir, f"{candidate_stem}{ext}")
        if candidate_stem.lower() not in existing_stems and not os.path.exists(candidate):
            return candidate

        for n in range(1, 10000):
            candidate_stem = f"{base}({n})"
            candidate = os.path.join(images_dir, f"{candidate_stem}{ext}")
            if candidate_stem.lower() not in existing_stems and not os.path.exists(candidate):
                return candidate

        return os.path.join(images_dir, f"{base}({uuid.uuid4().hex[:8]}){ext}")

    def unique_initial_image_target_path(self, src_path, images_dir, used_stems=None, current_path=None):
        """새 프로젝트 생성 직후 원본 파일명 보존용 대상 경로를 만든다.

        ProjectStore 경로가 0001/0002 같은 번호명을 만들었더라도 여기서 최종적으로
        원본명 기반 파일명으로 다시 정리한다.
        """
        used_stems = used_stems if used_stems is not None else set()
        src = Path(str(src_path))
        ext = src.suffix.lower() if src.suffix.lower() in IMAGE_DROP_EXTS else ".png"
        base = safe_page_file_stem(src.stem, fallback="image")
        current_resolved = ""
        try:
            current_resolved = str(Path(str(current_path)).resolve()).lower() if current_path else ""
        except Exception:
            current_resolved = ""

        existing_stems = set(used_stems)
        try:
            for p in Path(images_dir).iterdir():
                if not p.is_file():
                    continue
                try:
                    if current_resolved and str(p.resolve()).lower() == current_resolved:
                        continue
                except Exception:
                    pass
                existing_stems.add(p.stem.lower())
        except Exception:
            pass

        def make_candidate(n=None):
            stem = base if n is None else f"{base}({n})"
            return stem, Path(images_dir) / f"{stem}{ext}"

        stem, target = make_candidate(None)
        if stem.lower() not in existing_stems and (not target.exists() or str(target.resolve()).lower() == current_resolved):
            used_stems.add(stem.lower())
            return str(target)

        for n in range(1, 10000):
            stem, target = make_candidate(n)
            if stem.lower() not in existing_stems and not target.exists():
                used_stems.add(stem.lower())
                return str(target)

        stem = f"{base}({uuid.uuid4().hex[:8]})"
        used_stems.add(stem.lower())
        return str(Path(images_dir) / f"{stem}{ext}")

    def enforce_initial_project_image_names(self, source_paths):
        """새 프로젝트 생성 후 images 폴더의 실제 파일명을 원본명 기반으로 정리한다."""
        if not getattr(self, "project_dir", None) or not getattr(self, "paths", None):
            return False
        images_dir = os.path.join(str(self.project_dir), "images")
        os.makedirs(images_dir, exist_ok=True)
        changed = False
        used_stems = set()
        limit = min(len(self.paths), len(source_paths or []))
        for i in range(limit):
            try:
                src = source_paths[i]
                old_path = Path(str(self.paths[i]))
                if not old_path.exists():
                    continue
                target_path = Path(self.unique_initial_image_target_path(src, images_dir, used_stems, current_path=old_path))
                if str(old_path.resolve()).lower() != str(target_path.resolve()).lower():
                    if str(old_path.resolve()).lower() == str(target_path.resolve()).lower() and str(old_path) != str(target_path):
                        tmp = old_path.with_name(f".__ysb_init_rename_{uuid.uuid4().hex}{old_path.suffix}")
                        os.rename(str(old_path), str(tmp))
                        os.rename(str(tmp), str(target_path))
                    else:
                        os.rename(str(old_path), str(target_path))
                    self.paths[i] = str(target_path)
                    changed = True
                else:
                    self.paths[i] = str(target_path)
                if not isinstance(self.data, dict):
                    self.data = {}
                curr = self.data.get(i) or {}
                curr["original_name"] = os.path.basename(str(target_path))
                self.data[i] = curr
            except Exception as e:
                try:
                    self.log(f"⚠️ 원본 파일명 보존 실패({i + 1}p): {e}")
                except Exception:
                    pass
        if changed:
            try:
                self.save_project_store(self.project_store)
            except Exception:
                try:
                    self.project_store.save(self.paths, self.data, current_index=getattr(self, "idx", 0))
                except Exception:
                    pass
        return changed

    def make_page_data_for_image(self, image_path, original_name=None):
        img = cv2.imdecode(np.fromfile(image_path, np.uint8), 1)
        return {
            'ori': img,
            'data': [],
            'mask_merge': None,
            'mask_inpaint': None,
            'mask_merge_off': None,
            'mask_inpaint_off': None,
            'mask_toggle_enabled': False,
            'use_inpainted_as_source': False,
            'bg_clean': None,
            'working_source': None,
            'final_paint': None,
            'final_paint_above': None,
            'ocr_analysis_regions': [],
            'original_name': original_name or os.path.basename(image_path),
        }

    def insert_images_at_position(self, source_paths, insert_at=0, source_label="이미지 삽입"):
        source_paths = self.normalize_image_drop_paths(source_paths)
        if not source_paths:
            return False
        if not self.project_dir:
            return self.create_new_project_from_image_paths(source_paths, source_label=source_label)
        if not self.guard_project_action("이미지 삽입"):
            return False
        self.commit_current_page_ui_to_data()
        self.remember_current_view_state()
        undo_rec = self.make_project_undo_record("이미지 삽입", full_project=True)
        insert_at = max(0, min(int(insert_at), len(self.paths)))
        copied_paths = []
        copied_data = []
        for src in source_paths:
            dst = self.unique_insert_image_path(src)
            shutil.copy2(src, dst)
            copied_paths.append(dst)
            copied_data.append(self.make_page_data_for_image(dst, original_name=os.path.basename(dst)))

        old_paths = list(self.paths)
        old_data = dict(self.data or {})
        self.paths = old_paths[:insert_at] + copied_paths + old_paths[insert_at:]
        new_data = {}
        for new_i in range(len(self.paths)):
            if new_i < insert_at:
                if new_i in old_data:
                    new_data[new_i] = old_data[new_i]
            elif new_i < insert_at + len(copied_data):
                new_data[new_i] = copied_data[new_i - insert_at]
            else:
                old_i = new_i - len(copied_data)
                if old_i in old_data:
                    new_data[new_i] = old_data[old_i]
        self.data = new_data

        states = getattr(self, "project_ui_view_states", {}) or {}
        shifted_states = {}
        for key, state in states.items():
            try:
                page_s, mode_s = str(key).split(":", 1)
                old_page = int(page_s)
                new_page = old_page + len(copied_data) if old_page >= insert_at else old_page
                shifted_states[f"{new_page}:{int(mode_s)}"] = copy.deepcopy(state)
            except Exception:
                pass
        self.project_ui_view_states = shifted_states
        self.idx = insert_at
        self.page_text_undo_stacks = {}
        self.append_project_undo_record(undo_rec)
        self.load()
        self.auto_save_project()
        self.log(f"🖼️ 이미지 {len(copied_paths)}장 삽입: {insert_at + 1}페이지부터")
        return True

    def insert_images_after_current(self, source_paths):
        insert_at = (self.idx + 1) if self.paths else 0
        return self.insert_images_at_position(source_paths, insert_at=insert_at, source_label="드래그 앤 드롭")

    def import_images_at_end_action(self):
        # 이전 버전 호환용: + 탭도 일반 이미지 불러오기와 같은 동작을 사용한다.
        return self.import_images_action()

    def _dragged_local_files(self, event):
        try:
            mime = event.mimeData()
            if not mime or not mime.hasUrls():
                return []
            out = []
            for url in mime.urls():
                path = url.toLocalFile()
                if path:
                    out.append(os.path.abspath(path))
            return out
        except Exception:
            return []

    def _dragged_image_paths(self, event):
        return self.normalize_image_drop_paths(self._dragged_local_files(event))

    def _dragged_supported_files(self, event):
        files = self._dragged_local_files(event)
        images = self.normalize_image_drop_paths(files)
        ysb = ""
        for path in files:
            if path and str(path).lower().endswith(YSB_EXTENSION):
                ysb = os.path.abspath(path)
                break
        return images, ysb

    def handle_supported_file_drop(self, event):
        images, ysb_path = self._dragged_supported_files(event)
        if images:
            if self.project_dir:
                return self.insert_images_after_current(images)
            return self.create_new_project_from_image_paths(images, source_label="드래그 앤 드롭")
        if ysb_path:
            if not self.guard_project_action("YSBT 파일 드래그 열기"):
                return False
            if not self.confirm_close_current_project_for_open(ysb_path):
                return False
            self.open_project_path(ysb_path, external_request=True)
            self.force_app_focus(reason="drag and drop open")
            return True
        return False

    def _dragged_ysbt_path(self, event):
        _images, ysb = self._dragged_supported_files(event)
        return ysb

    def dragEnterEvent(self, event):
        images, ysb = self._dragged_supported_files(event)
        if images or ysb:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        images, ysb = self._dragged_supported_files(event)
        if images or ysb:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        images, ysb = self._dragged_supported_files(event)
        if not images and not ysb:
            event.ignore()
            return
        event.acceptProposedAction()
        self.handle_supported_file_drop(event)

    def change_workspace_location(self):
        """옵션 메뉴에서 작업 폴더 설정 창을 다시 연다.

        첫 실행 설정창과 같은 UI를 쓰되, 닫기를 눌러도 프로그램은 종료하지 않는다.
        위치가 바뀐 경우에는 다음 실행 시 이동되도록 예약한다.
        """
        if not self.guard_project_action("작업 폴더 위치 변경"):
            return
        dlg = WorkspaceSetupDialog(self, first_run=False)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.workspace_root = str(get_workspace_root())
            self.log("📁 작업 폴더 설정 확인")
        else:
            self.log("📁 작업 폴더 설정 변경 취소")

    def reset_workspace_location_to_default(self, parent=None):
        """작업 폴더 위치를 Windows 실제 문서 폴더 기준 기본값으로 되돌린 뒤 재기동한다."""
        if not self.guard_project_action("작업 폴더 위치 기본값으로 변경"):
            return
        parent = parent or self
        target = default_workspace_root()
        try:
            current = Path(load_workspace_config().get("workspace_root") or get_workspace_root()).resolve()
            target_resolved = target.resolve()
        except Exception:
            current = Path(str(get_workspace_root()))
            target_resolved = target

        if current == target_resolved:
            set_workspace_root(target)
            QMessageBox.information(
                parent,
                self.tr_ui("설정 완료"),
                f"{self.tr_ui('작업 폴더 위치가 이미 기본값입니다.')}\n\n{target}",
            )
            self.log(f"📁 작업 폴더 기본값 확인: {target}")
            return

        if not workspace_restart_confirmation(parent, current, target, self.ui_language):
            self.log("📁 작업 폴더 기본값 변경 취소")
            return

        try:
            schedule_workspace_root_change(target)
            self.log(f"📁 작업 폴더 기본값 변경 예약 및 재기동: {target}")
            restart_application_detached()
        except Exception as e:
            QMessageBox.critical(
                parent,
                self.tr_ui("저장 실패"),
                f"{self.tr_ui('작업 폴더 위치를 기본값으로 변경하지 못했습니다.')}\n{e}",
            )

    def register_ysb_file_association(self):
        if not is_windows():
            QMessageBox.information(self, self.tr_ui("지원 안내"), self.tr_msg(".ysbt 확장자 연결 등록은 Windows에서만 지원합니다."))
            return
        if is_ysbt_file_association_registered():
            QMessageBox.information(self, self.tr_ui("이미 등록됨"), self.tr_msg(".ysbt 확장자가 현재 실행 중인 역식붕이 툴에 이미 연결되어 있습니다."))
            return

        if is_ysbt_file_association_registered_to_other_ysb():
            registered = get_registered_ysbt_file_association_command() or "알 수 없음"
            message = (
                ".ysbt 확장자가 다른 위치의 역식붕이 툴에 연결되어 있습니다.\n"
                "현재 실행 중인 프로그램으로 연결을 갱신할까요?\n\n"
                f"현재 등록된 실행 명령:\n{registered}\n\n"
                "이 작업은 Windows의 확장자 연결 정보만 현재 프로그램으로 덮어씁니다. 기존 .ysbt 프로젝트 파일은 변경되지 않습니다."
            )
        else:
            message = (
                "현재 사용자 계정에 .ysbt 확장자 연결을 등록합니다.\n"
                "등록 후 .ysbt 파일을 더블클릭하면 역식붕이 툴로 열립니다. 계속할까요?"
            )

        ans = QMessageBox.question(
            self,
            self.tr_ui(".ysbt 확장자 연결 등록"),
            self.tr_msg(message),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        try:
            register_ysbt_file_association_raw()
            QMessageBox.information(self, self.tr_ui("등록 완료"), self.tr_ui(".ysbt 확장자 연결을 현재 실행 중인 역식붕이 툴로 등록했습니다.\n아이콘 표시는 Windows 아이콘 캐시 때문에 조금 늦게 갱신될 수 있습니다."))
            self.log("🔗 .ysbt 확장자 연결 등록/갱신 완료")
        except Exception as e:
            QMessageBox.critical(self, self.tr_ui("등록 실패"), f"{self.tr_ui('.ysbt 확장자 연결 등록에 실패했습니다.')}\n{e}")

    def unregister_ysbt_file_association(self):
        """현재 사용자 계정에 등록된 .ysbt 연결을 제거한다.

        이전 테스트 버전에서 이 프로그램이 등록한 .ysb 연결도 함께 정리한다.
        단, 다른 프로그램에 연결된 .ysb는 변경하지 않는다.
        """
        if not is_windows():
            QMessageBox.information(self, self.tr_ui("지원 안내"), self.tr_ui("확장자 연결 해제는 Windows에서만 지원합니다."))
            return
        ans = QMessageBox.question(
            self,
            self.tr_ui("확장자 연결 해제"),
            self.tr_ui("현재 사용자 계정의 .ysbt 연결을 해제합니다.\n이전 테스트 버전에서 이 프로그램이 등록한 .ysb 연결도 함께 정리합니다.\n다른 프로그램에 연결된 .ysb는 변경하지 않습니다.\n\n계속할까요?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        try:
            removed = unregister_ysbt_file_association_raw(include_legacy=True)
            msg = self.tr_ui("확장자 연결 해제를 완료했습니다.")
            if removed:
                msg += "\n\n" + self.tr_ui("제거 항목") + ":\n- " + "\n- ".join(removed)
            else:
                msg += "\n\n" + self.tr_ui("제거할 연결 항목이 없었습니다.")
            QMessageBox.information(self, self.tr_ui("해제 완료"), msg)
            self.log("🔗 확장자 연결 해제 완료: " + (", ".join(removed) if removed else "제거 항목 없음"))
        except Exception as e:
            QMessageBox.critical(self, self.tr_ui("해제 실패"), f"{self.tr_ui('확장자 연결 해제에 실패했습니다.')}\n{e}")

    def workspace_temp_project_dir(self, project_name="unsaved_project"):
        """새 프로젝트용 임시 작업 폴더를 만든다.

        v1.8 런처 이후에는 사용자가 작업 폴더를 문서/YSB_Translator로 잡아두었는지
        바로 확인할 수 있어야 하므로, 새 프로젝트의 임시 작업도 workspaces 아래에 만든다.
        아직 .ysbt로 저장되지 않은 상태라는 의미는 is_temp_project 플래그로 관리한다.
        """
        safe = safe_project_name(project_name)
        return unique_dir(workspaces_dir(), f"unsaved_{safe}_{uuid.uuid4().hex[:8]}")

    def workspace_project_dir(self, project_name="ysb_project", code=None, *, append_code=True):
        safe = clean_workspace_name(project_name)
        return unique_dir_with_code_suffix(workspaces_dir(), safe, code, append_code=append_code)

    def normalize_ysb_path(self, path):
        if not path:
            return path
        return path if path.lower().endswith(YSB_EXTENSION) else path + YSB_EXTENSION

    def current_package_default_path(self):
        base = getattr(self, "suggested_project_name", None) or (Path(self.project_dir).name if self.project_dir else "ysb_project")
        base = clean_workspace_name(base)
        try:
            package_dir = Path(getattr(self, "suggested_package_dir", None) or default_package_dir())
        except Exception:
            package_dir = default_package_dir()
        return str(package_dir / f"{safe_project_name(base)}{YSB_EXTENSION}")

    def delete_temp_project_if_needed(self):
        """저장되지 않은 임시 프로젝트 폴더를 안전하게 삭제한다.

        예전에는 임시 프로젝트가 temp 아래에만 있었지만, v1.8 런처 이후 새 프로젝트는
        사용자가 지정한 작업 폴더의 workspaces 아래에 unsaved_* 형태로 보이게 만든다.
        따라서 is_temp_project=True이고 아직 .ysbt 패키지에 연결되지 않은 경우에는
        temp/workspaces 내부의 unsaved_* 폴더를 정리한다.
        """
        if self.is_temp_project and self.project_dir and os.path.exists(self.project_dir):
            try:
                proj = os.path.abspath(self.project_dir)
                roots = [os.path.abspath(str(temp_dir())), os.path.abspath(str(workspaces_dir()))]
                name = os.path.basename(proj)
                can_delete = (not getattr(self, "ysbt_package_path", None)) and name.startswith("unsaved_")
                if can_delete and any(proj.startswith(root) for root in roots):
                    shutil.rmtree(self.project_dir, ignore_errors=True)
                    self.log(f"🧹 임시 프로젝트 삭제: {self.project_dir}")
            except Exception:
                pass
        self.is_temp_project = False

    def promote_temp_project_to_workspace(self, project_name=None):
        if not self.is_temp_project:
            return True
        if not self.project_dir or not os.path.exists(self.project_dir):
            return False

        name = clean_workspace_name(project_name or Path(self.project_dir).name)
        dst = self.workspace_project_dir(name)
        old_dir = self.project_dir
        try:
            # 현재 temp 프로젝트 저장 후, 새 폴더를 만들지 않고 temp 폴더 자체를 정식 작업 폴더로 승격한다.
            self.save_project_store(self.project_store)
            if os.path.abspath(old_dir) != os.path.abspath(dst):
                shutil.move(old_dir, dst)
            self.project_dir = dst
            self.project_store = ProjectStore(dst)
            # UUID는 manifest 내부에 유지하고, 폴더명/프로젝트명은 깔끔한 이름으로 갱신한다.
            self.project_store.write_manifest(project_name=name)
            self.is_temp_project = False

            # 혹시 이전 버전에서 workspaces 안에 unsaved_* 찌꺼기가 생겼다면,
            # 현재 승격한 폴더와 다른 빈/동일 임시 폴더만 안전하게 제거한다.
            try:
                ws_root = os.path.abspath(str(workspaces_dir()))
                old_abs = os.path.abspath(old_dir)
                dst_abs = os.path.abspath(dst)
                if old_abs.startswith(ws_root) and os.path.basename(old_abs).startswith("unsaved_") and old_abs != dst_abs and os.path.exists(old_abs):
                    shutil.rmtree(old_abs, ignore_errors=True)
            except Exception:
                pass

            self.reload_saved_project_from_disk(refresh_view=False)
            self.log(f"📦 임시 프로젝트를 작업 폴더로 승격: {dst}")
            return True
        except Exception as e:
            msg_text = self.tr_ui("임시 프로젝트를 작업 폴더로 옮기지 못했습니다.")
            QMessageBox.critical(self, self.tr_ui("프로젝트 이동 실패"), f"{msg_text}\n{e}")
            return False

    def record_recovery_project_dir(self, project_dir):
        """비정상 종료 후 복구 후보로 쓸 마지막 작업 폴더를 옵션 캐시에 기록한다."""
        try:
            if not project_dir:
                return
            project_dir = os.path.abspath(str(project_dir))
            if not os.path.exists(os.path.join(project_dir, PROJECT_FILENAME)):
                return
            self.app_options["last_recovery_project_dir"] = project_dir
            save_app_options(self.app_options)
        except Exception:
            pass

    def recovery_candidate_roots(self):
        return [self.project_cache_root(), temp_dir()]

    def find_recovery_candidates(self):
        """work_sessions/temp 안에서 project.json이 있는 복구 후보를 최신순으로 찾는다."""
        candidates = []
        seen = set()

        def add_candidate(path):
            try:
                p = Path(path)
                project_file = p / PROJECT_FILENAME
                if not project_file.exists():
                    return
                resolved = str(p.resolve())
                if resolved in seen:
                    return
                seen.add(resolved)
                try:
                    mtime = max(project_file.stat().st_mtime, p.stat().st_mtime)
                except Exception:
                    mtime = p.stat().st_mtime if p.exists() else 0
                candidates.append((mtime, str(p), str(project_file)))
            except Exception:
                pass

        # 1순위: 마지막 작업 캐시로 명시 기록한 폴더
        last_dir = str((self.app_options or {}).get("last_recovery_project_dir") or "").strip()
        if last_dir:
            add_candidate(last_dir)

        # 2순위: work cache / temp 폴더 전체 검색
        for root in self.recovery_candidate_roots():
            try:
                root = Path(root)
                if not root.exists():
                    continue
                for child in root.iterdir():
                    if child.is_dir():
                        add_candidate(child)
            except Exception:
                pass

        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates

    def recover_last_work_project(self):
        """마지막 작업 캐시/임시 프로젝트를 열어 복구한다."""
        if not self.guard_project_action("마지막 작업 복구"):
            return
        candidates = self.find_recovery_candidates()
        if not candidates:
            QMessageBox.information(
                self,
                self.tr_ui("복구할 작업 없음"),
                self.tr_ui("복구할 수 있는 임시 작업 파일을 찾지 못했습니다."),
            )
            self.log("⚠️ 복구할 임시 작업 파일 없음")
            return

        _mtime, project_dir, project_file = candidates[0]
        msg = (
            f"{self.tr_ui('마지막 작업 폴더를 복구할까요?')}\n\n"
            f"{project_dir}\n\n"
            f"{self.tr_ui('복구한 작업은 아직 정식 YSBT 파일이 아닐 수 있습니다. 필요한 경우 [프로젝트 저장]으로 다시 저장해 주세요.')}"
        )
        ans = QMessageBox.question(
            self,
            self.tr_ui("마지막 작업 복구"),
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if ans != QMessageBox.StandardButton.Yes:
            self.log("↩️ 마지막 작업 복구 취소")
            return

        if not self.confirm_unsaved_before_switch():
            return

        try:
            # 복구 폴더 자체를 임시 프로젝트로 연다. 원본 .ysbt와 연결하지 않고,
            # 사용자가 저장할 때 새 YSBT로 확정하게 한다.
            self.load_project_json(project_file, package_path=None, temp_project=False)
            self.ysbt_package_path = None
            self.is_temp_project = True
            self.has_unsaved_changes = True
            self.record_recovery_project_dir(project_dir)
            self.update_window_title()
            self.log(f"🧯 마지막 작업 복구 완료: {project_dir}")
            self.log("💾 복구한 작업은 [프로젝트 저장] 또는 [다른 이름으로 저장]으로 YSBT 파일에 확정하세요.")
        except Exception as e:
            QMessageBox.critical(
                self,
                self.tr_ui("복구 실패"),
                f"{self.tr_ui('마지막 작업을 복구하지 못했습니다.')}\n{project_dir}\n\n{e}",
            )
            self.log(f"❌ 마지막 작업 복구 실패: {e}")

    def temp_path_created_timestamp(self, path):
        """폴더 생성 시각을 우선 사용하고, 불가능하면 수정 시각을 사용한다."""
        try:
            return Path(path).stat().st_ctime
        except Exception:
            try:
                return Path(path).stat().st_mtime
            except Exception:
                return 0

    def temp_cleanup_category_roots(self):
        return [
            ("temp", self.tr_ui("임시 프로젝트"), temp_dir()),
            ("work_sessions", self.tr_ui("작업 캐시"), self.project_cache_root()),
        ]

    def empty_temp_cleanup_summary(self):
        return {
            "temp": {"label": self.tr_ui("임시 프로젝트"), "count": 0, "size": 0},
            "work_sessions": {"label": self.tr_ui("작업 캐시"), "count": 0, "size": 0},
        }

    def format_size_mb(self, size_bytes):
        try:
            return f"{float(size_bytes or 0) / (1024 * 1024):.1f} MB"
        except Exception:
            return "0.0 MB"

    def collect_temp_cleanup_targets(self, *, older_than_days=None, skip_current=True, exclude_recovery=False):
        """temp/work_sessions에서 삭제 가능한 임시 작업 폴더를 분류별로 모은다."""
        skip_dirs = set()
        if skip_current:
            for p in (getattr(self, "project_dir", None), getattr(self, "work_project_dir", None)):
                if p:
                    try:
                        skip_dirs.add(str(Path(p).resolve()))
                    except Exception:
                        pass

        if exclude_recovery:
            try:
                last_dir = str((self.app_options or {}).get("last_recovery_project_dir") or "").strip()
                if last_dir:
                    skip_dirs.add(str(Path(last_dir).resolve()))
            except Exception:
                pass

        now_ts = time.time()
        max_age_seconds = None
        if older_than_days is not None:
            try:
                max_age_seconds = max(0, int(older_than_days)) * 24 * 60 * 60
            except Exception:
                max_age_seconds = None

        targets = []
        total_size = 0
        summary = self.empty_temp_cleanup_summary()

        for key, label, root in self.temp_cleanup_category_roots():
            try:
                root = Path(root)
                if not root.exists():
                    continue
                for child in root.iterdir():
                    if not child.is_dir():
                        continue
                    try:
                        resolved = str(child.resolve())
                    except Exception:
                        resolved = str(child)
                    if resolved in skip_dirs:
                        continue

                    if max_age_seconds is not None:
                        created_ts = self.temp_path_created_timestamp(child)
                        if created_ts and (now_ts - created_ts) < max_age_seconds:
                            continue

                    folder_size = 0
                    try:
                        for file in child.rglob("*"):
                            if file.is_file():
                                folder_size += file.stat().st_size
                    except Exception:
                        pass

                    targets.append(child)
                    total_size += folder_size
                    summary.setdefault(key, {"label": label, "count": 0, "size": 0})
                    summary[key]["label"] = label
                    summary[key]["count"] += 1
                    summary[key]["size"] += folder_size
            except Exception:
                pass

        return targets, total_size, summary

    def temp_cleanup_summary_text(self, summary, total_count=None, total_size=None):
        summary = summary or self.empty_temp_cleanup_summary()
        temp_info = summary.get("temp", {})
        work_info = summary.get("work_sessions", {})
        if total_count is None:
            total_count = int(temp_info.get("count", 0) or 0) + int(work_info.get("count", 0) or 0)
        if total_size is None:
            total_size = int(temp_info.get("size", 0) or 0) + int(work_info.get("size", 0) or 0)
        return (
            f"{self.tr_ui('임시 프로젝트')}: {int(temp_info.get('count', 0) or 0)} / {self.format_size_mb(temp_info.get('size', 0))}\n"
            f"{self.tr_ui('작업 캐시')}: {int(work_info.get('count', 0) or 0)} / {self.format_size_mb(work_info.get('size', 0))}\n"
            f"{self.tr_ui('총합')}: {int(total_count or 0)} / {self.format_size_mb(total_size)}"
        )

    def temp_cleanup_period_options(self):
        return [
            (7, "일주일"),
            (30, "한달"),
            (90, "3개월"),
            (180, "6개월"),
            (365, "12개월"),
        ]

    def get_temp_auto_cleanup_days(self):
        try:
            days = int((self.app_options or {}).get("temp_auto_cleanup_days", 7) or 7)
        except Exception:
            days = 7
        if days not in (7, 30, 90, 180, 365):
            days = 7
        return days

    def is_temp_auto_cleanup_enabled(self):
        return bool((self.app_options or {}).get("temp_auto_cleanup_enabled", True))

    def set_temp_cleanup_options(self, enabled=None, days=None):
        try:
            if enabled is not None:
                self.app_options["temp_auto_cleanup_enabled"] = bool(enabled)
            if days is not None:
                days = int(days)
                if days not in (7, 30, 90, 180, 365):
                    days = 7
                self.app_options["temp_auto_cleanup_days"] = days
            save_app_options(self.app_options)
        except Exception:
            pass

    def auto_cleanup_temp_files_if_needed(self):
        """설정된 주기마다, 설정된 기간 이상 지난 임시 작업 폴더를 자동 삭제한다."""
        try:
            if not self.is_temp_auto_cleanup_enabled():
                self.log(
                    "🧹 Auto temp cleanup is disabled."
                    if getattr(self, "ui_language", LANG_KO) == LANG_EN else
                    "🧹 자동 임시 파일 정리: 꺼짐"
                )
                return

            period_days = self.get_temp_auto_cleanup_days()
            max_age_days = period_days
            now_ts = time.time()
            last_ts = float((self.app_options or {}).get("last_temp_auto_cleanup_at", 0) or 0)
            if last_ts and (now_ts - last_ts) < period_days * 24 * 60 * 60:
                return

            targets, total_size, summary = self.collect_temp_cleanup_targets(older_than_days=max_age_days, skip_current=True, exclude_recovery=True)

            deleted = 0
            failed = 0
            for path in targets:
                try:
                    shutil.rmtree(path, ignore_errors=False)
                    deleted += 1
                except Exception:
                    failed += 1

            try:
                last_dir = str((self.app_options or {}).get("last_recovery_project_dir") or "")
                if last_dir and not os.path.exists(last_dir):
                    self.app_options.pop("last_recovery_project_dir", None)
            except Exception:
                pass

            self.app_options["last_temp_auto_cleanup_at"] = now_ts
            self.app_options["temp_auto_cleanup_enabled"] = True
            self.app_options["temp_auto_cleanup_days"] = period_days
            save_app_options(self.app_options)

            if deleted or failed:
                size_mb = total_size / (1024 * 1024)
                self.log(
                    f"🧹 Auto temp cleanup: deleted {deleted}, failed {failed}, approx. {size_mb:.1f} MB / period {period_days} days"
                    if getattr(self, "ui_language", LANG_KO) == LANG_EN else
                    f"🧹 자동 임시 파일 정리: 삭제 {deleted}개 / 실패 {failed}개 / 약 {size_mb:.1f} MB / 주기 {period_days}일"
                )
            else:
                self.log(
                    "🧹 Auto temp cleanup: no old temporary files."
                    if getattr(self, "ui_language", LANG_KO) == LANG_EN else
                    "🧹 자동 임시 파일 정리: 오래된 임시 파일 없음"
                )
        except Exception as e:
            try:
                self.log(
                    f"⚠️ Auto temp cleanup failed: {e}"
                    if getattr(self, "ui_language", LANG_KO) == LANG_EN else
                    f"⚠️ 자동 임시 파일 정리 실패: {e}"
                )
            except Exception:
                pass

    def delete_temp_files_now(self, parent=None):
        """현재 작업과 연결되지 않은 temp/work_sessions 임시 파일을 즉시 삭제한다."""
        targets, total_size, summary = self.collect_temp_cleanup_targets(
            older_than_days=None,
            skip_current=True,
            exclude_recovery=False,
        )

        if not targets:
            QMessageBox.information(
                parent or self,
                self.tr_ui("삭제할 임시 파일 없음"),
                self.tr_ui("삭제할 수 있는 임시 작업 파일이 없습니다."),
            )
            self.log("🧹 삭제할 임시 작업 파일 없음")
            return False

        msg = (
            f"{self.tr_ui('현재 열려 있는 작업을 제외한 임시 작업 폴더를 삭제합니다.')}\n\n"
            f"{self.temp_cleanup_summary_text(summary, len(targets), total_size)}\n\n"
            f"{self.tr_ui('삭제 후에는 해당 임시 작업을 복구할 수 없습니다. 계속할까요?')}"
        )
        ans = QMessageBox.question(
            parent or self,
            self.tr_ui("임시 파일 삭제"),
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            self.log("↩️ 임시 파일 삭제 취소")
            return False

        deleted = 0
        failed = 0
        for path in targets:
            try:
                shutil.rmtree(path, ignore_errors=False)
                deleted += 1
            except Exception:
                failed += 1

        # 삭제한 폴더가 마지막 복구 기록이면 기록도 비운다.
        try:
            last_dir = str((self.app_options or {}).get("last_recovery_project_dir") or "")
            if last_dir and not os.path.exists(last_dir):
                self.app_options.pop("last_recovery_project_dir", None)
                save_app_options(self.app_options)
        except Exception:
            pass

        self.log(f"🧹 임시 파일 삭제 완료: {deleted}개 삭제 / {failed}개 실패")
        QMessageBox.information(
            parent or self,
            self.tr_ui("임시 파일 삭제 완료"),
            self.tr_ui(f"임시 파일 삭제가 완료되었습니다.\n삭제: {deleted}개\n실패: {failed}개"),
        )
        return True

    def cleanup_temp_files_dialog(self):
        """임시 파일 수동 삭제 + 자동 삭제 옵션 설정 창."""
        if not self.guard_project_action("임시 파일 관리"):
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr_ui("임시 파일 관리"))
        dlg.setModal(True)
        layout = QVBoxLayout(dlg)

        desc = QLabel(self.tr_ui("임시 파일 삭제와 자동 삭제 주기를 설정합니다."))
        desc.setWordWrap(True)
        layout.addWidget(desc)

        stats_label = QLabel("")
        stats_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        stats_label.setWordWrap(True)
        layout.addWidget(stats_label)

        row = QHBoxLayout()
        btn_delete = QPushButton(self.tr_ui("임시파일 삭제"))
        cb_auto = QCheckBox(self.tr_ui("임시파일 자동삭제"))
        combo_days = QComboBox()

        current_days = self.get_temp_auto_cleanup_days()
        for days, label in self.temp_cleanup_period_options():
            combo_days.addItem(self.tr_ui(label), days)
            if days == current_days:
                combo_days.setCurrentIndex(combo_days.count() - 1)

        cb_auto.setChecked(self.is_temp_auto_cleanup_enabled())
        combo_days.setEnabled(cb_auto.isChecked())

        row.addWidget(btn_delete)
        row.addStretch(1)
        row.addWidget(cb_auto)
        row.addWidget(combo_days)
        layout.addLayout(row)

        note = QLabel(self.tr_ui("자동 삭제는 선택한 기간마다 실행되며, 선택한 기간 이상 지난 임시 작업 폴더만 삭제합니다."))
        note.setWordWrap(True)
        layout.addWidget(note)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        layout.addWidget(btns)

        def refresh_stats():
            try:
                targets, total_size, summary = self.collect_temp_cleanup_targets(
                    older_than_days=None,
                    skip_current=True,
                    exclude_recovery=False,
                )
                stats_label.setText(self.temp_cleanup_summary_text(summary, len(targets), total_size))
            except Exception as e:
                stats_label.setText(f"{self.tr_ui('임시 파일 상태를 읽지 못했습니다.')}: {e}")

        def save_options():
            days = combo_days.currentData()
            self.set_temp_cleanup_options(cb_auto.isChecked(), days)
            combo_days.setEnabled(cb_auto.isChecked())
            self.log(
                f"🧹 임시 파일 자동삭제 설정: {'ON' if cb_auto.isChecked() else 'OFF'} / {int(days)}일"
            )

        def delete_and_refresh():
            changed = self.delete_temp_files_now(dlg)
            if changed:
                refresh_stats()

        cb_auto.toggled.connect(lambda _checked: save_options())
        combo_days.currentIndexChanged.connect(lambda _idx: save_options())
        btn_delete.clicked.connect(delete_and_refresh)
        btns.rejected.connect(dlg.reject)

        refresh_stats()
        dlg.resize(560, 220)
        dlg.exec()

    def open_project_path(self, path, external_request=False):
        """파일 연결/명령행 인자로 받은 .ysbt 또는 project.json을 연다."""
        if not path:
            return
        if not self.guard_project_action("프로젝트 열기"):
            return
        path = os.path.abspath(path)
        if not external_request:
            if not self.confirm_unsaved_before_switch():
                return
        if path.lower().endswith(YSB_EXTENSION):
            self.open_ysb_package(path)
            if external_request:
                self.force_app_focus(reason="external project open")
            return
        if os.path.isdir(path):
            project_file = os.path.join(path, PROJECT_FILENAME)
        else:
            project_file = path
        if os.path.basename(project_file) != PROJECT_FILENAME or not os.path.exists(project_file):
            msg_text = self.tr_ui("열 수 있는 프로젝트 파일이 아닙니다.")
            QMessageBox.warning(self, self.tr_ui("프로젝트 없음"), f"{msg_text}\n{path}")
            return
        self.load_project_json(project_file)
        if external_request:
            self.force_app_focus(reason="external project open")

    def load_project_json(self, project_file, package_path=None, temp_project=False):
        self.is_loading_project = True
        try:
            self.commit_current_page_ui_to_data()
            self.project_store = ProjectStore()
            self.paths, self.data, self.idx = self.project_store.load(project_file)
            self.page_text_undo_stacks = {}
            self.project_undo_stack = []
            self.project_redo_stack = []
            self.undo_boundary = None
            self.update_undo_redo_buttons()
            ui_state = getattr(self.project_store, "ui_state", {}) or {}
            self.project_ui_view_states = copy.deepcopy(ui_state.get("view_states") or {})
            self.restore_project_ui_state(ui_state, refresh=False)
            self.project_dir = self.project_store.project_dir
            self.ysbt_package_path = package_path
            self.suggested_project_name = self.split_uuid_suffix_from_name(Path(package_path).stem)[0] if package_path else None
            self.is_temp_project = bool(temp_project)
            self.update_window_title()
            self.mark_saved_state()
            self.log(f"📂 프로젝트 열림: {self.project_dir}")
            if package_path:
                self.log(f"📦 연결된 YSBT 파일: {package_path}")

            # 새 프로젝트 생성은 원본 탭으로 시작하지만, 기존 프로젝트 열기는 마지막 작업 탭/화면 상태로 복원한다.
            mode_to_load = 0 if temp_project else int(ui_state.get("current_mode", 0) or 0)
            self.set_work_mode_without_undo(mode_to_load)
            self.show_editor()
            self.load()
            self.record_current_project_recent()
            state = self.project_ui_view_states.get(self.view_state_key(self.idx, mode_to_load))
            if state:
                self.apply_view_state(state)
                QTimer.singleShot(0, lambda st=copy.deepcopy(state): self.apply_view_state(st))
                QTimer.singleShot(30, lambda st=copy.deepcopy(state): self.apply_view_state(st))
                QTimer.singleShot(80, lambda st=copy.deepcopy(state): self.apply_view_state(st))

            if not self.auto_save_enabled:
                self.start_work_cache_from_current(mark_dirty=False)
        finally:
            self.is_loading_project = False

    def open_ysb_package(self, package_path):
        try:
            # 기준은 항상 .ysbt 파일이다. 같은 UUID/같은 .ysbt이면 기존 작업 폴더를 조용히 재사용하고,
            # 다른 파일이면 extract_ysb_package가 충돌 없는 새 작업 폴더를 만든다.
            target_dir, manifest, reused = extract_ysb_package(package_path, workspaces_dir(), reuse_existing=True)
            self.load_project_json(os.path.join(target_dir, PROJECT_FILENAME), package_path=package_path, temp_project=False)
        except Exception as e:
            QMessageBox.critical(self, self.tr_ui("YSBT 열기 실패"), f"{self.tr_ui('YSBT 프로젝트를 열지 못했습니다.')}\n{package_path}\n\n{e}")

    def project_cache_root(self):
        root = get_cache_dir() / "work_sessions"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def cleanup_work_cache(self):
        if self.work_project_dir and os.path.exists(self.work_project_dir):
            try:
                shutil.rmtree(self.work_project_dir, ignore_errors=True)
            except Exception:
                pass
        self.work_project_dir = None
        self.work_project_store = None
        self.page_tab_scroll_generation = 0

    def make_work_cache_dir(self):
        if self.project_dir:
            base = Path(self.project_dir).name
        else:
            base = "unsaved_project"
        safe_base = "".join(c if c.isalnum() or c in ("_", "-", ".") else "_" for c in base)
        return str(self.project_cache_root() / f"{safe_base}_{uuid.uuid4().hex[:10]}")

    def start_work_cache_from_current(self, mark_dirty=False):
        """현재 메모리 상태를 기준으로 새 작업 캐시를 만든다."""
        if not self.project_dir:
            return
        old_cache = self.work_project_dir
        cache_dir = self.make_work_cache_dir()

        store = ProjectStore(cache_dir)
        self.save_project_store(store)

        # store.save()가 paths를 cache 내부 이미지 경로로 고정할 수 있으므로 이후 작업은 캐시 기준으로 돌아간다.
        self.work_project_store = store
        self.work_project_dir = cache_dir
        self.record_recovery_project_dir(cache_dir)
        self.has_unsaved_changes = bool(mark_dirty)

        if old_cache and old_cache != cache_dir and os.path.exists(old_cache):
            try:
                shutil.rmtree(old_cache, ignore_errors=True)
            except Exception:
                pass

        self.log(f"🧪 작업 캐시 시작: {cache_dir}")

    def save_to_work_cache(self):
        if not self.project_dir:
            return
        if self.work_project_store is None or not self.work_project_dir:
            self.start_work_cache_from_current(mark_dirty=False)
        if self.work_project_store is None:
            return
        self.save_project_store(self.work_project_store)
        self.record_recovery_project_dir(self.work_project_dir)
        self.has_unsaved_changes = True

    def mark_saved_state(self):
        self.has_unsaved_changes = False

    def save_app_options_cache(self):
        self.app_options["auto_save_enabled"] = bool(self.auto_save_enabled)
        self.app_options[UI_THEME_KEY] = str(getattr(self, "ui_theme", THEME_DARK) or THEME_DARK)
        self.app_options[UI_LANGUAGE_KEY] = normalize_ui_language(getattr(self, "ui_language", LANG_KO))
        self.app_options["analysis_number_box_width"] = int(getattr(self, "analysis_number_box_width", 40))
        self.app_options[PAGE_TAB_DISPLAY_MODE_KEY] = normalize_page_display_mode(getattr(self, "page_tab_display_name_mode", DEFAULT_PAGE_DISPLAY_MODE))
        self.app_options[OUTPUT_DISPLAY_MODE_KEY] = normalize_page_display_mode(getattr(self, "output_display_name_mode", DEFAULT_PAGE_DISPLAY_MODE))
        self.app_options[LOG_PANEL_COLLAPSED_KEY] = bool(getattr(self, "log_panel_collapsed", DEFAULT_LOG_PANEL_COLLAPSED))
        self.app_options[SHOW_PATHS_IN_LOG_KEY] = bool(getattr(self, "show_paths_in_log", False))
        self.app_options[SHOW_CACHE_PATHS_IN_SETTINGS_KEY] = bool(getattr(self, "show_cache_paths_in_settings", False))
        self.app_options["temp_auto_cleanup_enabled"] = bool(self.app_options.get("temp_auto_cleanup_enabled", True))
        cleanup_days = int(self.app_options.get("temp_auto_cleanup_days", 7) or 7)
        if cleanup_days not in (7, 30, 90, 180, 365):
            cleanup_days = 7
        self.app_options["temp_auto_cleanup_days"] = cleanup_days
        self.app_options[ANALYSIS_TEXT_MASK_EXPAND_RATIO_KEY] = clamp_analysis_mask_ratio(
            self.app_options.get(ANALYSIS_TEXT_MASK_EXPAND_RATIO_KEY, getattr(Config, "MERGE_RATIO", DEFAULT_ANALYSIS_TEXT_MASK_EXPAND_RATIO)),
            DEFAULT_ANALYSIS_TEXT_MASK_EXPAND_RATIO,
        )
        self.app_options[ANALYSIS_PAINT_MASK_EXPAND_RATIO_KEY] = clamp_analysis_mask_ratio(
            self.app_options.get(ANALYSIS_PAINT_MASK_EXPAND_RATIO_KEY, getattr(Config, "INPAINT_RATIO", DEFAULT_ANALYSIS_PAINT_MASK_EXPAND_RATIO)),
            DEFAULT_ANALYSIS_PAINT_MASK_EXPAND_RATIO,
        )
        self.app_options[ANALYSIS_TEXT_MASK_MIN_EXPAND_PX_KEY] = clamp_analysis_mask_min_px(
            self.app_options.get(ANALYSIS_TEXT_MASK_MIN_EXPAND_PX_KEY, getattr(Config, "MERGE_MIN_STROKE_PX", DEFAULT_ANALYSIS_TEXT_MASK_MIN_EXPAND_PX)),
            DEFAULT_ANALYSIS_TEXT_MASK_MIN_EXPAND_PX,
        )
        self.app_options[ANALYSIS_PAINT_MASK_MIN_EXPAND_PX_KEY] = clamp_analysis_mask_min_px(
            self.app_options.get(ANALYSIS_PAINT_MASK_MIN_EXPAND_PX_KEY, getattr(Config, "MIN_STROKE_PX", DEFAULT_ANALYSIS_PAINT_MASK_MIN_EXPAND_PX)),
            DEFAULT_ANALYSIS_PAINT_MASK_MIN_EXPAND_PX,
        )
        self.sync_analysis_mask_options_to_config()
        self.app_options.setdefault(TRANSLATION_PROMPT_KEY, "")
        self.app_options.setdefault(TRANSLATION_GLOSSARY_TEXT_KEY, "")
        self.app_options.setdefault(TRANSLATION_GLOSSARY_PATH_KEY, "")
        save_app_options(self.app_options)

    def page_name_mode_label_pairs(self):
        return [
            (PAGE_DISPLAY_MODE_ORIGINAL, "원본 파일명"),
            (PAGE_DISPLAY_MODE_PAGE_ORIGINAL, "1p_원본 파일명"),
            (PAGE_DISPLAY_MODE_PAGE_NUMBER, "page001"),
        ]

    def ask_page_name_mode(self, title, current_mode):
        pairs = self.page_name_mode_label_pairs()
        current_mode = normalize_page_display_mode(current_mode)
        labels = [label for _mode, label in pairs]
        current_index = 0
        for i, (mode, _label) in enumerate(pairs):
            if mode == current_mode:
                current_index = i
                break
        value, ok = QInputDialog.getItem(
            self,
            self.tr_ui(title),
            self.tr_ui("표시명 형식:"),
            [self.tr_ui(label) for label in labels],
            current_index,
            False,
        )
        if not ok:
            return None
        try:
            selected_index = [self.tr_ui(label) for label in labels].index(value)
        except ValueError:
            selected_index = current_index
        return pairs[selected_index][0]

    def open_page_tab_display_name_dialog(self):
        old_mode = normalize_page_display_mode(getattr(self, "page_tab_display_name_mode", DEFAULT_PAGE_DISPLAY_MODE))
        new_mode = self.ask_page_name_mode("페이지 탭 표시명 설정", old_mode)
        if not new_mode or new_mode == old_mode:
            return False
        self.page_tab_display_name_mode = normalize_page_display_mode(new_mode)
        self.save_app_options_cache()
        self.refresh_page_tabs()
        self.log(f"📑 페이지 탭 표시명 설정: {self.page_tab_display_name_mode}")
        return True

    def open_output_display_name_dialog(self):
        old_mode = normalize_page_display_mode(getattr(self, "output_display_name_mode", DEFAULT_PAGE_DISPLAY_MODE))
        new_mode = self.ask_page_name_mode("출력 표시명 설정", old_mode)
        if not new_mode or new_mode == old_mode:
            return False
        self.output_display_name_mode = normalize_page_display_mode(new_mode)
        self.save_app_options_cache()
        self.log(f"📤 출력 표시명 설정: {self.output_display_name_mode}")
        return True

    def sync_translation_option_cache_to_config(self):
        """옵션 캐시에 저장된 번역 프롬프트/단어장을 번역 엔진 Config에 반영한다."""
        try:
            Config.TRANSLATION_PROMPT = str(self.app_options.get(TRANSLATION_PROMPT_KEY, "") or "")
            Config.TRANSLATION_GLOSSARY_TEXT = str(self.app_options.get(TRANSLATION_GLOSSARY_TEXT_KEY, "") or "")
        except Exception:
            pass

    def sync_analysis_mask_options_to_config(self):
        """옵션 캐시의 분석 마스크 확장 설정을 엔진 Config에 반영한다."""
        try:
            text_ratio = clamp_analysis_mask_ratio(
                self.app_options.get(ANALYSIS_TEXT_MASK_EXPAND_RATIO_KEY, DEFAULT_ANALYSIS_TEXT_MASK_EXPAND_RATIO),
                DEFAULT_ANALYSIS_TEXT_MASK_EXPAND_RATIO,
            )
            paint_ratio = clamp_analysis_mask_ratio(
                self.app_options.get(ANALYSIS_PAINT_MASK_EXPAND_RATIO_KEY, DEFAULT_ANALYSIS_PAINT_MASK_EXPAND_RATIO),
                DEFAULT_ANALYSIS_PAINT_MASK_EXPAND_RATIO,
            )
            text_min_px = clamp_analysis_mask_min_px(
                self.app_options.get(ANALYSIS_TEXT_MASK_MIN_EXPAND_PX_KEY, DEFAULT_ANALYSIS_TEXT_MASK_MIN_EXPAND_PX),
                DEFAULT_ANALYSIS_TEXT_MASK_MIN_EXPAND_PX,
            )
            paint_min_px = clamp_analysis_mask_min_px(
                self.app_options.get(ANALYSIS_PAINT_MASK_MIN_EXPAND_PX_KEY, DEFAULT_ANALYSIS_PAINT_MASK_MIN_EXPAND_PX),
                DEFAULT_ANALYSIS_PAINT_MASK_MIN_EXPAND_PX,
            )
            self.app_options[ANALYSIS_TEXT_MASK_EXPAND_RATIO_KEY] = text_ratio
            self.app_options[ANALYSIS_PAINT_MASK_EXPAND_RATIO_KEY] = paint_ratio
            self.app_options[ANALYSIS_TEXT_MASK_MIN_EXPAND_PX_KEY] = text_min_px
            self.app_options[ANALYSIS_PAINT_MASK_MIN_EXPAND_PX_KEY] = paint_min_px
            Config.MERGE_RATIO = text_ratio
            Config.INPAINT_RATIO = paint_ratio
            Config.MERGE_MIN_STROKE_PX = text_min_px
            Config.MIN_STROKE_PX = paint_min_px
        except Exception:
            pass

    def reload_saved_project_from_disk(self, refresh_view=True):
        """실제 프로젝트 저장본을 다시 로드해서 paths를 프로젝트 폴더 기준으로 되돌린다."""
        if not self.project_dir:
            return False
        project_file = os.path.join(self.project_dir, PROJECT_FILENAME)
        if not os.path.exists(project_file):
            return False

        self.is_loading_project = True
        try:
            store = ProjectStore()
            self.paths, self.data, self.idx = store.load(project_file)
            self.project_store = store
            self.project_dir = store.project_dir
            ui_state = getattr(store, "ui_state", {}) or {}
            self.project_ui_view_states = copy.deepcopy(ui_state.get("view_states") or getattr(self, "project_ui_view_states", {}) or {})
            self.restore_project_ui_state(ui_state, refresh=False)
            if refresh_view:
                mode_to_load = int(ui_state.get("current_mode", self.cb_mode.currentIndex() if hasattr(self, "cb_mode") else 0) or 0)
                self.set_work_mode_without_undo(mode_to_load)
                self.load()
                state = self.project_ui_view_states.get(self.view_state_key(self.idx, mode_to_load))
                if state:
                    self.apply_view_state(state)
                    QTimer.singleShot(0, lambda st=copy.deepcopy(state): self.apply_view_state(st))
                    QTimer.singleShot(30, lambda st=copy.deepcopy(state): self.apply_view_state(st))
                    QTimer.singleShot(80, lambda st=copy.deepcopy(state): self.apply_view_state(st))
            return True
        finally:
            self.is_loading_project = False

    def commit_to_real_project_only(self):
        """작업 캐시 상태를 실제 프로젝트에 저장하되, 새 작업 캐시는 만들지 않는다."""
        if not self.project_dir:
            return False
        self.commit_current_page_ui_to_data()
        self.save_project_store(self.project_store)
        self.mark_saved_state()
        return True

    def toggle_auto_save_mode(self, checked):
        checked = bool(checked)

        if checked:
            if self.has_unsaved_changes:
                ans = QMessageBox.question(
                    self,
                    "자동저장 전환",
                    "저장하지 않은 작업이 있습니다.\n현재 작업 캐시를 프로젝트에 저장하고 자동저장 모드로 전환할까요?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if ans != QMessageBox.StandardButton.Yes:
                    self.act_auto_save_mode.blockSignals(True)
                    self.act_auto_save_mode.setChecked(False)
                    self.act_auto_save_mode.blockSignals(False)
                    return
                if not self.commit_to_real_project_only():
                    self.act_auto_save_mode.blockSignals(True)
                    self.act_auto_save_mode.setChecked(False)
                    self.act_auto_save_mode.blockSignals(False)
                    return

            # 핵심: 자동저장 ON에서는 paths가 실제 프로젝트 폴더를 가리켜야 한다.
            # OFF 캐시를 삭제하기 전에 저장본을 다시 로드해서 캐시 경로 의존을 끊는다.
            self.auto_save_enabled = True
            self.save_app_options_cache()
            self.reload_saved_project_from_disk(refresh_view=True)
            self.cleanup_work_cache()
            self.mark_saved_state()
            self.log("💾 자동저장 모드 ON: 변경 사항이 실제 프로젝트에 바로 저장됩니다.")
        else:
            self.auto_save_enabled = False
            self.save_app_options_cache()
            # 이후 변경은 작업 캐시에만 저장한다.
            if self.project_dir:
                self.start_work_cache_from_current(mark_dirty=False)
            self.log("🧪 자동저장 모드 OFF: 변경 사항은 작업 캐시에만 저장됩니다.")

    def confirm_unsaved_before_switch(self):
        if not self.has_unsaved_changes:
            return True

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle(self.tr_ui("저장하지 않은 작업"))
        msg.setText(self.tr_ui("저장하지 않은 작업이 있습니다."))
        msg.setInformativeText(self.tr_ui("현재 프로젝트를 닫기 전에 저장할까요?"))
        btn_save = msg.addButton(self.tr_ui("저장"), QMessageBox.ButtonRole.AcceptRole)
        btn_discard = msg.addButton(self.tr_ui("저장 안 함"), QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = msg.addButton(self.tr_ui("취소"), QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_save)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == btn_save:
            self.save_project()
            return not self.has_unsaved_changes
        if clicked == btn_discard:
            self.cleanup_work_cache()
            self.delete_temp_project_if_needed()
            self.has_unsaved_changes = False
            return True
        return False

    def closeEvent(self, event):
        """프로그램 종료 처리.

        최종화면의 인라인 텍스트 편집/QGraphics 상태가 열린 채로 종료 확인창이 뜨면
        focusOutEvent와 closeEvent가 겹쳐 예외가 날 수 있다. 종료 전에 현재 편집 상태를
        먼저 안전하게 확정하고, 종료 처리 중 예외가 나도 프로그램이 바로 튕기지 않게 막는다.
        """
        try:
            if getattr(self, "is_batch_running", False):
                QMessageBox.information(
                    self,
                    self.tr_ui("일괄 작업 중"),
                    self.tr_ui("일괄 작업 중에는 프로그램을 종료할 수 없습니다.\n작업이 끝난 뒤 다시 종료해 주세요."),
                )
                event.ignore()
                return

            if getattr(self, "_closing_confirmed", False):
                self.cleanup_external_open_runtime_info()
                event.accept()
                return

            self._app_is_closing = True

            # 핵심 보정: 최종화면 인라인 텍스트 편집 중 종료하면 QMessageBox 포커스 이동으로
            # finish_inline_text_edit()가 closeEvent 도중 재진입할 수 있다. 먼저 확정해서 안정화한다.
            if getattr(self, "inline_text_editor", None) is not None:
                try:
                    self.finish_inline_text_edit(commit=True, refresh=False)
                except Exception as e:
                    self.log(f"⚠️ 종료 전 텍스트 편집 확정 실패: {e}")

            # 최종화면/표의 현재 UI 상태를 가능한 한 data에 반영한다. 실패해도 종료 확인창은 유지한다.
            try:
                if getattr(self, "project_dir", None) and getattr(self, "paths", None):
                    self.commit_current_page_ui_to_data()
                    if getattr(self, "auto_save_enabled", False):
                        self.auto_save_project()
            except Exception as e:
                self.log(f"⚠️ 종료 전 현재 화면 상태 반영 실패: {e}")

            if self.has_unsaved_changes:
                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Icon.Warning)
                msg.setWindowTitle(self.tr_ui("저장하지 않은 작업"))
                msg.setText(self.tr_ui("저장하지 않은 작업이 있습니다."))
                msg.setInformativeText(self.tr_ui("종료하기 전에 프로젝트를 저장할까요?"))
                btn_save = msg.addButton(self.tr_ui("저장"), QMessageBox.ButtonRole.AcceptRole)
                btn_discard = msg.addButton(self.tr_ui("저장 안 함"), QMessageBox.ButtonRole.DestructiveRole)
                btn_cancel = msg.addButton(self.tr_ui("취소"), QMessageBox.ButtonRole.RejectRole)
                msg.setDefaultButton(btn_save)
                msg.exec()

                clicked = msg.clickedButton()
                if clicked == btn_cancel:
                    self._app_is_closing = False
                    event.ignore()
                    return
                if clicked == btn_save:
                    self.save_project()
                    if self.has_unsaved_changes:
                        self._app_is_closing = False
                        event.ignore()
                        return
                elif clicked == btn_discard:
                    try:
                        self.cleanup_work_cache()
                    except Exception as e:
                        self.log(f"⚠️ 작업 캐시 정리 실패: {e}")
                    try:
                        self.delete_temp_project_if_needed()
                    except Exception as e:
                        self.log(f"⚠️ 임시 프로젝트 삭제 실패: {e}")
                    self.has_unsaved_changes = False
            else:
                # 정상 종료 시 남은 작업 캐시는 삭제한다. 실패해도 종료 자체를 튕기게 만들지 않는다.
                try:
                    self.cleanup_work_cache()
                except Exception as e:
                    self.log(f"⚠️ 작업 캐시 정리 실패: {e}")

            self.cleanup_external_open_runtime_info()
            self._closing_confirmed = True
            event.accept()
        except Exception as e:
            self._app_is_closing = False
            try:
                import traceback
                detail = traceback.format_exc()
                self.log(f"❌ 종료 처리 중 오류: {e}")
                QMessageBox.critical(
                    self,
                    self.tr_ui("종료 오류"),
                    self.tr_ui("프로그램 종료 처리 중 오류가 발생했습니다.\n작업 보호를 위해 종료를 취소합니다.") + f"\n\n{detail}",
                )
            except Exception:
                pass
            event.ignore()

    def default_empty_project_name(self):
        """빈 프로젝트 생성 기본 이름을 만든다."""
        try:
            return self.tr_ui("새 프로젝트")
        except Exception:
            return "새 프로젝트"

    def project_creation_preview_path(self, parent_dir, project_name):
        """새 빈 프로젝트가 생성될 YSBT 경로를 미리 보여준다."""
        try:
            parent = Path(str(parent_dir or workspaces_dir())).expanduser()
        except Exception:
            parent = workspaces_dir()
        name = clean_workspace_name(project_name or self.default_empty_project_name())
        return str(parent / f"{safe_project_name(name)}{YSB_EXTENSION}")

    def remember_last_project_create_dir(self, directory):
        try:
            directory = str(directory or "").strip()
            if not directory:
                return
            self.app_options[LAST_PROJECT_CREATE_DIR_KEY] = directory
            save_app_options(self.app_options)
        except Exception:
            pass

    def resolve_initial_project_create_dir(self):
        fallback = str(workspaces_dir())
        saved = str((self.app_options or {}).get(LAST_PROJECT_CREATE_DIR_KEY, "") or "").strip()
        if saved and os.path.isdir(saved):
            return saved
        if saved and not os.path.isdir(saved):
            QMessageBox.warning(
                self,
                self.tr_ui("프로젝트 생성 위치 확인"),
                self.tr_ui("마지막 프로젝트 생성 위치를 찾지 못했습니다.\n새 위치를 선택해 주세요."),
            )
            chosen = QFileDialog.getExistingDirectory(self, self.tr_ui("프로젝트 생성 위치 선택"), fallback)
            if chosen:
                self.remember_last_project_create_dir(chosen)
                return chosen
        return fallback

    def build_create_project_ysbt_path(self, parent_dir, project_name):
        """새 프로젝트 만들기에서 사용자가 입력한 이름 그대로의 YSBT 경로를 만든다.

        중복 이름은 자동 suffix를 붙이지 않고, 생성창에서 사용자에게
        이름 변경/덮어쓰기/취소를 물어본다.
        """
        parent = Path(str(parent_dir or workspaces_dir())).expanduser()
        parent.mkdir(parents=True, exist_ok=True)
        safe_name = safe_project_name(clean_workspace_name(project_name or self.default_empty_project_name()))
        return str(parent / f"{safe_name}{YSB_EXTENSION}")

    def build_unique_create_project_ysbt_path(self, parent_dir, project_name):
        return self.build_create_project_ysbt_path(parent_dir, project_name)

    def new_empty_project_action(self):
        """이미지 없이 빈 프로젝트를 먼저 생성한다."""
        if not self.guard_project_action("새 프로젝트 만들기"):
            return False

        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr_ui("새 프로젝트 만들기"))
        dlg.setModal(True)
        dlg.resize(560, 220)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        name_label = QLabel(self.tr_ui("프로젝트 이름"), dlg)
        name_edit = QLineEdit(dlg)
        name_edit.setText(self.default_empty_project_name())
        name_edit.selectAll()
        layout.addWidget(name_label)
        layout.addWidget(name_edit)

        location_label = QLabel(self.tr_ui("생성 위치"), dlg)
        location_row = QHBoxLayout()
        location_edit = QLineEdit(dlg)
        try:
            location_edit.setText(self.resolve_initial_project_create_dir())
        except Exception:
            location_edit.setText(str(workspaces_dir()))
        browse_btn = QToolButton(dlg)
        browse_btn.setText("⋯")
        browse_btn.setFixedWidth(34)
        location_row.addWidget(location_edit, 1)
        location_row.addWidget(browse_btn, 0)
        layout.addWidget(location_label)
        layout.addLayout(location_row)

        preview_label = QLabel(dlg)
        preview_label.setWordWrap(True)
        preview_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        preview_label.setObjectName("ProjectCreatePathPreview")
        try:
            preview_label.setStyleSheet("QLabel#ProjectCreatePathPreview { color:#9fb7d8; padding:6px 0px; }")
        except Exception:
            pass
        layout.addWidget(preview_label)

        info_label = QLabel(self.tr_ui("프로젝트 이름과 생성 위치를 먼저 확정하고, 빈 프로젝트(.ysbt)를 만든 뒤 나중에 이미지 불러오기로 페이지를 추가합니다."), dlg)
        info_label.setWordWrap(True)
        try:
            info_label.setStyleSheet("color:#9ca3af;")
        except Exception:
            pass
        layout.addWidget(info_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dlg)
        try:
            buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr_ui("만들기"))
            buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(self.tr_ui("취소"))
        except Exception:
            pass
        layout.addWidget(buttons)

        def update_preview():
            try:
                preview = self.project_creation_preview_path(location_edit.text(), name_edit.text())
                preview_label.setText(f"{self.tr_ui('생성 경로')}: {preview}")
            except Exception:
                pass

        def browse_location():
            start = location_edit.text().strip() or str(workspaces_dir())
            folder = QFileDialog.getExistingDirectory(dlg, self.tr_ui("프로젝트 생성 위치 선택"), start)
            if folder:
                location_edit.setText(folder)
                update_preview()

        overwrite_choice = {"value": False}

        def accept_with_duplicate_check():
            project_name_now = clean_workspace_name(name_edit.text() or self.default_empty_project_name())
            parent_dir_now = location_edit.text().strip() or str(workspaces_dir())
            try:
                candidate_path = self.build_create_project_ysbt_path(parent_dir_now, project_name_now)
            except Exception:
                candidate_path = self.project_creation_preview_path(parent_dir_now, project_name_now)

            if candidate_path and os.path.exists(candidate_path):
                msg = QMessageBox(dlg)
                msg.setIcon(QMessageBox.Icon.Warning)
                msg.setWindowTitle(self.tr_ui("이름 중복"))
                msg.setText(self.tr_ui("같은 이름의 YSBT 프로젝트가 이미 있습니다."))
                msg.setInformativeText(str(candidate_path))
                btn_rename = msg.addButton(self.tr_ui("이름 바꾸기"), QMessageBox.ButtonRole.AcceptRole)
                btn_overwrite = msg.addButton(self.tr_ui("덮어쓰기"), QMessageBox.ButtonRole.DestructiveRole)
                btn_cancel = msg.addButton(self.tr_ui("취소"), QMessageBox.ButtonRole.RejectRole)
                msg.setDefaultButton(btn_rename)
                msg.setEscapeButton(btn_cancel)
                try:
                    msg.setStyleSheet(self.message_box_style())
                except Exception:
                    pass
                force_message_box_front(msg)
                msg.exec()
                clicked = msg.clickedButton()

                if clicked is btn_rename:
                    overwrite_choice["value"] = False
                    name_edit.setFocus(Qt.FocusReason.OtherFocusReason)
                    name_edit.selectAll()
                    return
                if clicked is btn_overwrite:
                    overwrite_choice["value"] = True
                    dlg.accept()
                    return
                return

            overwrite_choice["value"] = False
            dlg.accept()

        browse_btn.clicked.connect(browse_location)
        name_edit.textChanged.connect(update_preview)
        location_edit.textChanged.connect(update_preview)
        buttons.accepted.connect(accept_with_duplicate_check)
        buttons.rejected.connect(dlg.reject)
        update_preview()

        name_edit.setFocus(Qt.FocusReason.OtherFocusReason)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return False

        project_name = clean_workspace_name(name_edit.text() or self.default_empty_project_name())
        parent_dir = location_edit.text().strip() or str(workspaces_dir())
        return self.create_empty_project(project_name=project_name, parent_dir=parent_dir, overwrite_existing=bool(overwrite_choice.get("value")))

    def create_empty_project(self, project_name="새 프로젝트", parent_dir=None, overwrite_existing=False):
        """이미지 없는 빈 프로젝트를 만들고, 즉시 YSBT까지 생성한 뒤 에디터로 진입한다."""
        if not self.guard_project_action("새 프로젝트 만들기"):
            return False
        if not self.confirm_unsaved_before_switch():
            return False

        project_name = clean_workspace_name(project_name or self.default_empty_project_name())
        try:
            parent = Path(str(parent_dir or workspaces_dir())).expanduser()
            parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(
                self,
                self.tr_ui("프로젝트 생성 실패"),
                f"{self.tr_ui('프로젝트 생성 위치를 만들 수 없습니다.')}\n{parent_dir}\n\n{e}",
            )
            return False

        try:
            self.commit_current_page_ui_to_data()
        except Exception:
            pass

        package_seed = self.build_create_project_ysbt_path(parent, project_name)
        package_path, display_project_name, project_uuid = self.make_ysbt_path_with_uuid_suffix(package_seed)
        if os.path.exists(package_path) and not overwrite_existing:
            QMessageBox.warning(
                self,
                self.tr_ui("이름 중복"),
                f"{self.tr_ui('같은 이름의 YSBT 프로젝트가 이미 있습니다.')}\n{package_path}",
            )
            return False
        project_dir = self.workspace_project_dir(display_project_name, code=project_uuid[:8], append_code=True)
        try:
            store = ProjectStore(project_dir)
            store.init_dirs()
            store.ui_state = {"current_mode": 0, "view_states": {}, "show_final_text": True}
            store.save([], {}, current_index=0)
            store.write_manifest(package_source=package_path, project_name=display_project_name, project_uuid=project_uuid)
            if overwrite_existing and os.path.exists(package_path):
                try:
                    os.remove(package_path)
                except Exception:
                    pass
            package_project(project_dir, package_path, project_name=display_project_name, project_uuid=project_uuid)
        except Exception as e:
            QMessageBox.critical(
                self,
                self.tr_ui("프로젝트 생성 실패"),
                f"{self.tr_ui('빈 프로젝트를 만들지 못했습니다.')}\n{package_path}\n\n{e}",
            )
            return False

        self.close_current_project_state_for_switch()
        self.project_store = store
        self.project_dir = project_dir
        self.paths = []
        self.data = {}
        self.idx = 0
        self.page_text_undo_stacks = {}
        self.project_undo_stack = []
        self.project_redo_stack = []
        self.undo_boundary = None
        self.project_ui_view_states = {}
        self.ysbt_package_path = package_path
        self.is_temp_project = False
        self.suggested_project_name = display_project_name
        self.suggested_package_dir = str(parent)
        self.work_project_dir = None
        self.work_project_store = None
        self.is_loading_project = False
        self.record_recovery_project_dir(project_dir)
        self.remember_last_project_create_dir(parent)
        self.mark_saved_state()
        self.update_window_title()
        self.update_undo_redo_buttons()
        self.reset_mode_to_original()
        self.show_editor()
        self.load()
        self.record_current_project_recent()
        self.log(f"📁 빈 프로젝트 생성: {project_dir}")
        self.log(f"💾 YSBT가 저장되었습니다: {package_path}")
        self.log("🖼️ 아직 이미지가 없습니다. [이미지 불러오기] 또는 페이지 탭의 [+]로 페이지를 추가하세요.")
        if not self.auto_save_enabled:
            self.start_work_cache_from_current(mark_dirty=False)
        return True

    def create_new_project_from_image_paths(self, source_paths, source_label="이미지 드롭"):
        source_paths = self.normalize_image_drop_paths(source_paths)
        if not source_paths:
            self.log("⚠️ 불러올 이미지 파일이 없습니다.")
            return False
        if not self.guard_project_action("새 프로젝트 만들기"):
            return False
        if not self.confirm_unsaved_before_switch():
            return False

        # 프로젝트 이름은 첫 생성 때 묻지 않는다.
        # 실제 이름은 .ysbt로 저장할 때 파일명 기준으로 확정된다.
        self.suggested_project_name = safe_project_name(Path(source_paths[0]).stem + "_project")
        self.suggested_package_dir = None
        project_dir = self.workspace_temp_project_dir(self.suggested_project_name)

        self.commit_current_page_ui_to_data()

        self.project_store = ProjectStore(project_dir)
        self.paths, self.data = self.project_store.create_from_images(project_dir, source_paths)
        self.page_text_undo_stacks = {}
        self.project_undo_stack = []
        self.project_redo_stack = []
        self.undo_boundary = None
        self.update_undo_redo_buttons()
        self.project_ui_view_states = {}
        self.project_store.write_manifest(project_name="unsaved_project")
        self.project_dir = project_dir
        self.enforce_initial_project_image_names(source_paths)
        self.record_recovery_project_dir(project_dir)
        self.ysbt_package_path = None
        self.is_temp_project = True
        self.update_window_title()
        self.idx = 0
        self.is_loading_project = False
        self.log(f"📁 새 임시 프로젝트 작업 폴더 생성: {project_dir}")
        self.log("💾 아직 YSBT 파일로 저장되지 않았습니다. [프로젝트 저장] 또는 [다른 이름으로 저장]을 눌러 .ysbt로 저장하세요.")
        self.log(f"🖼️ 이미지 {len(source_paths)}장으로 새 프로젝트 생성: {source_label}")
        self.has_unsaved_changes = True
        if not self.auto_save_enabled:
            self.start_work_cache_from_current(mark_dirty=True)
            self.enforce_initial_project_image_names(source_paths)
        self.reset_mode_to_original()
        self.show_editor()
        self.load()
        return True

    def import_images_action(self):
        """이미지를 불러온다. 작업 중이면 현재 페이지 뒤에 삽입하고, 홈에서는 새 프로젝트로 시작한다."""
        source_paths, _ = QFileDialog.getOpenFileNames(
            self,
            self.tr_ui("불러올 이미지 선택"),
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)"
        )
        if not source_paths:
            return
        try:
            in_editor = (
                hasattr(self, "main_stack")
                and hasattr(self, "editor_widget")
                and self.main_stack.currentWidget() is self.editor_widget
            )
        except Exception:
            in_editor = False
        if in_editor and self.has_open_project():
            return self.insert_images_after_current(source_paths)
        return self.create_new_project_from_image_paths(source_paths, source_label="이미지 불러오기")

    def new_project_from_images(self):
        source_paths, _ = QFileDialog.getOpenFileNames(
            self,
            self.tr_ui("프로젝트에 넣을 이미지 선택"),
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)"
        )
        if not source_paths:
            return
        self.create_new_project_from_image_paths(source_paths, source_label="파일 선택")

    def open_project(self):
        """YSBT 전용 프로젝트 열기.

        v1.6부터 기본 프로젝트 열기는 .ysbt 패키지만 지원한다.
        구버전 폴더/project.json 열기 흐름은 아래에 주석으로 남겨두고,
        별도 메뉴인 [JSON으로 열기]에서만 project.json을 열 수 있게 분리한다.
        """
        if not self.guard_project_action("프로젝트 열기"):
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr_ui("YSBT 프로젝트 열기"),
            str(default_package_dir()),
            "YSBT Project (*.ysbt);;All Files (*.*)"
        )
        if not path:
            return

        self.open_project_path(path)

    def open_project_json(self):
        """구버전/디버그용 project.json 직접 열기. 기본 열기와 분리한다."""
        if not self.guard_project_action("JSON으로 열기"):
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr_ui("프로젝트 JSON 열기"),
            str(workspaces_dir()),
            "Project JSON (project.json);;JSON (*.json);;All Files (*.*)"
        )
        if not path:
            return

        self.open_project_path(path)

    def save_project(self):
        if not self.guard_project_action("프로젝트 저장"):
            return
        if not self.project_dir:
            self.log("⚠️ 프로젝트가 없습니다. 새 프로젝트를 먼저 만들어주세요.")
            return
        if not self.ysbt_package_path:
            # 새 프로젝트/구버전 폴더 프로젝트는 첫 저장 때 .ysbt 위치를 정한다.
            self.save_project_as()
            return

        self.begin_busy_state("프로젝트 저장")
        try:
            self.commit_current_page_ui_to_data()
            self.save_project_store(self.project_store)
            try:
                package_project(self.project_dir, self.ysbt_package_path)
            except Exception as e:
                msg_text = self.tr_ui("프로젝트는 작업 폴더에 저장했지만, YSBT 파일 저장에 실패했습니다.")
                QMessageBox.critical(self, self.tr_ui("YSBT 저장 실패"), f"{msg_text}\n\n{e}")
                self.has_unsaved_changes = True
                return
            self.mark_saved_state()
            self.update_window_title()
            self.log(f"💾 프로젝트 저장 완료: {self.ysbt_package_path}")
            self.record_current_project_recent()

            # 자동저장 OFF에서는 저장본을 다시 로드한 뒤, 새 작업 캐시를 기준으로 이어간다.
            if not self.auto_save_enabled:
                self.reload_saved_project_from_disk(refresh_view=False)
                self.start_work_cache_from_current(mark_dirty=False)
                if self.cb_mode.currentIndex() >= 0:
                    self.load()
        finally:
            self.end_busy_state("프로젝트 저장")

    def ensure_save_as_output_parent(self, path_abs: str):
        """다른 이름으로 저장 대상 폴더가 없을 때 먼저 만든다."""
        parent = os.path.dirname(os.path.abspath(str(path_abs or "")))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)

    def _write_image_for_save_as_fallback(self, img, dst_path: str) -> bool:
        """원본 이미지 경로가 사라진 경우 메모리 이미지/작업 이미지를 새 저장용 파일로 복구한다."""
        if img is None:
            return False
        try:
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            ext = Path(dst_path).suffix.lower()
            if ext not in (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"):
                ext = ".png"
                dst_path = str(Path(dst_path).with_suffix(ext))

            if isinstance(img, (bytes, bytearray)):
                with open(dst_path, "wb") as f:
                    f.write(img)
                return os.path.exists(dst_path) and os.path.getsize(dst_path) > 0

            if isinstance(img, np.ndarray):
                encode_ext = ".jpg" if ext == ".jpeg" else ext
                ok, buf = cv2.imencode(encode_ext, img)
                if ok:
                    buf.tofile(dst_path)
                    return os.path.exists(dst_path) and os.path.getsize(dst_path) > 0
        except Exception:
            return False
        return False

    def prepare_save_as_paths_for_store(self, target_project_dir: str):
        """Save As용 이미지 경로 목록을 만든다.

        ProjectStore.save()는 원본 이미지 파일이 실제 디스크에 있어야 새 프로젝트 폴더로 복사할 수 있다.
        그런데 작업 폴더 이동/임시 캐시 정리/구버전 경로 문제로 self.paths의 일부가 사라진 경우
        다른 이름으로 저장이 [WinError 3]로 실패할 수 있다.

        이 함수는 저장 전에 각 이미지 경로를 확인하고,
        경로가 없으면 현재 프로젝트 images 폴더나 메모리의 ori/working_source로 복구한다.
        """
        prepared = list(self.paths or [])
        image_dir = os.path.join(str(target_project_dir), "images")
        os.makedirs(image_dir, exist_ok=True)

        project_images_dir = os.path.join(str(self.project_dir or ""), "images")
        known_exts = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")

        for i, src in enumerate(prepared):
            src_text = str(src or "")
            if src_text and os.path.exists(src_text):
                continue

            candidates = []
            if src_text:
                candidates.append(src_text)
                if self.project_dir and not os.path.isabs(src_text):
                    candidates.append(os.path.join(str(self.project_dir), src_text))
                if self.project_dir:
                    candidates.append(os.path.join(str(self.project_dir), "images", os.path.basename(src_text)))

            if os.path.isdir(project_images_dir):
                try:
                    for ext in known_exts:
                        candidates.append(os.path.join(project_images_dir, f"{i + 1:04d}{ext}"))
                except Exception:
                    pass

            found = None
            for cand in candidates:
                try:
                    if cand and os.path.exists(cand):
                        found = os.path.abspath(cand)
                        break
                except Exception:
                    pass

            if found:
                prepared[i] = found
                continue

            curr = self.data.get(i, {}) if isinstance(self.data, dict) else {}
            ext = Path(src_text).suffix.lower() if src_text else ".png"
            if ext not in known_exts:
                ext = ".png"
            original_hint = curr.get("original_name") if isinstance(curr, dict) else ""
            base = safe_page_file_stem(Path(str(original_hint or src_text or f"page{i + 1:03d}")).stem, fallback=f"page{i + 1:03d}")
            candidate = os.path.join(image_dir, f"{base}{ext}")
            if os.path.exists(candidate):
                for n in range(1, 10000):
                    candidate = os.path.join(image_dir, f"{base}({n}){ext}")
                    if not os.path.exists(candidate):
                        break
            dst = candidate

            recovered = False
            img = curr.get("ori") if isinstance(curr, dict) else None
            if img is not None:
                recovered = self._write_image_for_save_as_fallback(img, dst)

            if not recovered and isinstance(curr, dict):
                working_source = curr.get("working_source")
                if working_source is not None:
                    recovered = self._write_image_for_save_as_fallback(working_source, dst)

            if not recovered:
                raise FileNotFoundError(
                    "다른 이름으로 저장할 원본 이미지 경로를 찾지 못했습니다.\n"
                    f"페이지: {i + 1}\n"
                    f"기존 경로: {src_text or '(비어 있음)'}"
                )

            prepared[i] = dst

        return prepared

    def save_project_as(self):
        if not self.guard_project_action("다른 이름으로 저장"):
            return
        if not self.project_dir and not self.paths:
            self.log("⚠️ 저장할 이미지/프로젝트가 없습니다.")
            return

        default_path = self.ysbt_package_path or self.current_package_default_path()
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr_ui("다른 이름으로 YSBT 저장"),
            default_path,
            "YSBT Project (*.ysbt)"
        )
        if not path:
            return
        old_package_path = os.path.abspath(self.ysbt_package_path) if self.ysbt_package_path else None
        old_is_temp_project = bool(getattr(self, "is_temp_project", False))
        path_abs, display_project_name, new_uuid = self.make_ysbt_path_with_uuid_suffix(path)
        path_abs = os.path.abspath(path_abs)

        # 같은 .ysbt 파일을 고른 경우에는 일반 저장과 동일하게 처리한다.
        if old_package_path and os.path.abspath(path_abs).lower() == old_package_path.lower():
            self.save_project()
            return

        self.begin_busy_state("다른 이름으로 저장")
        try:
            self.commit_current_page_ui_to_data()

            # Save As는 새 .ysbt 패키지와 새 작업 폴더로 분기한다.
            # 기존 .ysbt 파일에는 현재까지의 미저장 변경분을 쓰지 않고,
            # 새 파일/새 작업 폴더가 현재 상태를 이어받는다.
            project_name = clean_workspace_name(display_project_name or Path(path_abs).stem)
            old_project_dir = self.project_dir
            old_work_cache = self.work_project_dir
            # .ysbt 파일명은 깔끔하게 유지하고, 실제 작업 폴더에만 uuid 짧은값을 붙인다.
            new_project_dir = self.workspace_project_dir(project_name, code=new_uuid[:8], append_code=True)

            try:
                self.ensure_save_as_output_parent(path_abs)
                new_store = ProjectStore(new_project_dir)
                # ProjectStore.save()는 전달받은 paths를 새 작업 폴더 내부 이미지 경로로 고정한다.
                # 실패 시 기존 self.paths가 오염되지 않도록 복사본을 사용하고, 성공 후에만 반영한다.
                save_as_paths = self.prepare_save_as_paths_for_store(new_project_dir)
                self.save_project_store(new_store, paths=save_as_paths)
                new_store.write_manifest(package_source=path_abs, project_name=project_name, project_uuid=new_uuid)
                package_project(new_project_dir, path_abs, project_name=project_name, project_uuid=new_uuid)
            except Exception as e:
                QMessageBox.critical(self, self.tr_ui("YSBT 저장 실패"), f"{self.tr_ui('YSBT 파일을 저장하지 못했습니다.')}\n{path_abs}\n\n{e}")
                self.has_unsaved_changes = True
                return

            # 현재 작업은 새 파일/새 작업 폴더로 전환한다.
            self.paths = save_as_paths
            self.project_dir = new_project_dir
            self.project_store = ProjectStore(new_project_dir)
            self.ysbt_package_path = path_abs
            self.suggested_project_name = display_project_name
            self.suggested_package_dir = os.path.dirname(path_abs)
            self.is_temp_project = False
            self.update_window_title()

            # 기존 임시 캐시/임시 프로젝트 정리.
            if old_work_cache and old_work_cache != self.work_project_dir and os.path.exists(old_work_cache):
                try:
                    shutil.rmtree(old_work_cache, ignore_errors=True)
                except Exception:
                    pass
            if old_is_temp_project and old_project_dir and os.path.abspath(old_project_dir) != os.path.abspath(new_project_dir):
                try:
                    old_abs = os.path.abspath(old_project_dir)
                    roots = [os.path.abspath(str(temp_dir())), os.path.abspath(str(workspaces_dir()))]
                    if os.path.basename(old_abs).startswith("unsaved_") and any(old_abs.startswith(root) for root in roots) and os.path.exists(old_abs):
                        shutil.rmtree(old_abs, ignore_errors=True)
                except Exception:
                    pass
            self.work_project_dir = None
            self.work_project_store = None

            # Save As는 "현재 상태를 새 파일 B로 분기"하는 동작이다.
            # 따라서 기존 파일 A의 작업 폴더는 B로 갱신/삭제하지 않고, A.ysbt에 저장된 상태로 되돌려 둔다.
            # A와 B의 작업 폴더가 동시에 남아 있어야 사용자가 기대하는 Save As 동작과 맞다.
            try:
                if old_package_path and old_project_dir and os.path.abspath(old_project_dir) != os.path.abspath(new_project_dir):
                    old_abs = os.path.abspath(old_project_dir)
                    roots = [os.path.abspath(str(workspaces_dir())), os.path.abspath(str(temp_dir()))]
                    if any(old_abs.startswith(root) for root in roots) and os.path.exists(old_package_path):
                        # 자동저장 ON 등으로 A의 작업 폴더에 미저장 변경분이 들어갔을 수 있으므로,
                        # A.ysbt 패키지 기준으로 A 작업 폴더를 조용히 복구한다.
                        if os.path.exists(old_abs):
                            shutil.rmtree(old_abs, ignore_errors=True)
                        extract_ysb_package(old_package_path, workspaces_dir(), reuse_existing=False)
            except Exception as e:
                try:
                    self.log(f"⚠️ Save As 이후 기존 작업 폴더 복구 실패: {e}")
                except Exception:
                    pass

            self.reload_saved_project_from_disk(refresh_view=False)
            self.mark_saved_state()
            self.log(f"💾 다른 이름으로 저장 완료: {self.ysbt_package_path}")
            self.record_current_project_recent()
            if not self.auto_save_enabled:
                self.start_work_cache_from_current(mark_dirty=False)
            self.load()
        finally:
            self.end_busy_state("다른 이름으로 저장")

    def auto_save_project(self):
        if self.is_loading_project or self.is_autosaving:
            return
        if not self.project_dir:
            return
        self.is_autosaving = True
        try:
            # 자동저장 진입 시점에 우측 표 텍스트와 최종화면 텍스트 좌표를 먼저 data에 고정한다.
            # 이전 버전은 마스크/브러시는 화면에서 바로 읽어왔지만, 텍스트 이동/수정은
            # 일부 경로에서 data 반영이 늦어져 자동저장 결과가 빠질 수 있었다.
            self.commit_current_page_ui_to_data(include_mask=False)
            if self.auto_save_enabled:
                self.save_project_store(self.project_store)
                # 자동저장 ON은 실제 프로젝트 파일까지 확정한다.
                # .ysbt가 있는 프로젝트는 작업 폴더 project.json만이 아니라 패키지 파일도 즉시 갱신한다.
                # 자동저장 OFF일 때는 아래 save_to_work_cache()만 사용하므로 실제 파일은 건드리지 않는다.
                if self.ysbt_package_path and not self.is_temp_project:
                    try:
                        package_project(self.project_dir, self.ysbt_package_path)
                    except Exception as e:
                        self.has_unsaved_changes = True
                        self.log(f"⚠️ 자동저장 패키지 갱신 실패: {e}")
                        return
                # 새 임시 프로젝트는 폴더에는 저장되어도 아직 .ysbt 패키지가 없으므로 저장 필요 상태를 유지한다.
                self.has_unsaved_changes = bool(self.is_temp_project or not self.ysbt_package_path)
            else:
                self.save_to_work_cache()
        finally:
            self.is_autosaving = False

    def sync_final_text_scene_to_data(self):
        """최종화면의 실제 텍스트 아이템 위치를 현재 페이지 data에 동기화한다.

        일반 드래그/변형 드래그는 대부분 해당 이벤트에서 data를 갱신하지만,
        자동저장/페이지 이동/닫기처럼 이벤트 타이밍이 섞이는 경우를 위해
        저장 직전 화면에 남아 있는 TypesettingItem의 좌표를 한 번 더 확정한다.
        """
        if getattr(self, "_text_scene_sync_lock", False) or getattr(self, "_text_undo_restore_lock", False):
            return False
        scene = self._safe_graphics_scene()
        if scene is None:
            return False
        curr = self.data.get(self.idx)
        if not curr:
            return False

        self._text_scene_sync_lock = True
        changed = False
        try:
            data_list = curr.get('data', []) or []
            by_id = {str(d.get('id')): d for d in data_list if isinstance(d, dict)}
            try:
                scene_items = list(scene.items())
            except RuntimeError:
                return False
            except Exception:
                return False
            for item in scene_items:
                if not isinstance(item, TypesettingItem):
                    continue
                d = getattr(item, 'data', None)
                if not isinstance(d, dict):
                    continue
                if d.get('pending_new_text'):
                    continue
                item_id = str(d.get('id'))
                target = by_id.get(item_id)
                if target is None:
                    continue

                rect = list(target.get('rect') or [0, 0, 1, 1])
                while len(rect) < 4:
                    rect.append(1)
                try:
                    align = (target.get('align') or 'center').lower()
                    if align == 'left':
                        anchor_x = float(rect[0])
                    elif align == 'right':
                        anchor_x = float(rect[0]) + float(rect[2])
                    else:
                        anchor_x = float(rect[0]) + float(rect[2]) / 2.0

                    path_rect = getattr(item, '_text_path_rect', item.boundingRect())
                    item_pos = item.pos()
                    rect_x = float(rect[0])
                    rect_y = float(rect[1])
                    rect_w = max(1.0, float(rect[2]))
                    rect_h = max(1.0, float(rect[3]))
                    if bool(target.get('rasterized_text')) or bool(getattr(item, '_is_rasterized_text', False)):
                        # 객체화된 텍스트는 rect가 래스터 이미지의 좌상단 기준이다.
                        # 일반 텍스트처럼 center/align 보정을 넣으면 이동 후 저장 시 위치가 다시 밀린다.
                        new_x_off = int(round(float(item_pos.x()) - rect_x))
                        new_y_off = int(round(float(item_pos.y()) - rect_y))
                    elif align == 'left':
                        new_x_off = int(round(float(item_pos.x()) + float(path_rect.left()) - rect_x))
                        new_y_off = int(round(float(item_pos.y()) + float(path_rect.center().y()) - (rect_y + rect_h / 2.0)))
                    elif align == 'right':
                        new_x_off = int(round(float(item_pos.x()) + float(path_rect.right()) - (rect_x + rect_w)))
                        new_y_off = int(round(float(item_pos.y()) + float(path_rect.center().y()) - (rect_y + rect_h / 2.0)))
                    else:
                        new_x_off = int(round(float(item_pos.x()) + float(path_rect.center().x()) - (rect_x + rect_w / 2.0)))
                        new_y_off = int(round(float(item_pos.y()) + float(path_rect.center().y()) - (rect_y + rect_h / 2.0)))
                except Exception:
                    continue

                old_x_off = int(target.get('x_off', 0) or 0)
                old_y_off = int(target.get('y_off', 0) or 0)
                if new_x_off != old_x_off or new_y_off != old_y_off:
                    target['x_off'] = new_x_off
                    target['y_off'] = new_y_off
                    changed = True
            return changed
        finally:
            self._text_scene_sync_lock = False

    def commit_current_page_ui_to_data(self, include_mask=True):
        curr = self.data.get(self.idx)
        if not curr:
            return

        # 최종화면 탭에서는 화면 위 텍스트 아이템의 현재 위치를 저장 데이터에 먼저 고정한다.
        self.sync_final_text_scene_to_data()

        # 표 상태 반영
        for row in range(1, self.tab.rowCount()):
            data_index = row - 1
            if data_index < 0 or data_index >= len(curr.get('data', [])):
                continue

            data_item = curr['data'][data_index]
            data_item['use_inpaint'] = self.get_table_check_state(row)

            # 객체화된 텍스트는 우측 표에 [객체] 표시용 문자열을 보여주지만,
            # 그 문자열이 원본 translated_text에 다시 저장되면 [객체] 접두사가 누적된다.
            # 래스터 텍스트 객체는 이동/삭제/부분 지우기만 허용하고 내용 편집 값은 유지한다.
            if data_item.get('rasterized_text'):
                continue

            orig_item = self.tab.item(row, 2)
            if orig_item is not None:
                data_item['text'] = orig_item.text()

            trans_item = self.tab.item(row, 3)
            data_item['translated_text'] = trans_item.text() if trans_item else ""

        # 화면 마스크 자동 저장은 평상시 현재 페이지에서만 허용.
        # 페이지 로딩/일괄 작업 중에는 이전 화면의 마스크가 다른 페이지에 섞일 수 있으므로 차단한다.
        if (not include_mask) or self.is_page_loading or self.is_batch_running:
            return

        if self.cb_mode.currentIndex() in [2, 3]:
            m = self.view.get_mask_np()
            if m is not None:
                self.set_active_mask(curr, m, self.cb_mode.currentIndex())
                curr['mask_toggle_enabled'] = self.mask_toggle_enabled

