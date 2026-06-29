# -*- coding: utf-8 -*-
"""CUDA/runtime diagnosis and managed runtime installer dialog."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QUrl, QThread, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QGuiApplication, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QTextEdit,
    QVBoxLayout,
)

from ysb.i18n.lang_text import tr_ui, LANG_KO
from ysb.editions.local.cuda_runtime_probe import run_full_probe
from ysb.editions.local.cuda_runtime_installer import (
    delete_runtime,
    install_runtime,
    managed_runtime_root,
    runtime_mode,
    runtime_status,
)


class RuntimeInstallWorker(QThread):
    progress = pyqtSignal(object)
    finished_report = pyqtSignal(dict)

    def __init__(self, role: str, parent=None):
        super().__init__(parent)
        self.role = role

    def run(self) -> None:
        try:
            result = install_runtime(self.role, progress=lambda payload: self.progress.emit(payload))
        except Exception as exc:
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}", "role": self.role}
        self.finished_report.emit(result)


class CudaRuntimeDiagnosisDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.lang = getattr(parent, "ui_language", LANG_KO) if parent is not None else LANG_KO
        self.report: dict[str, Any] | None = None
        self.report_path: str = ""
        self.install_worker: RuntimeInstallWorker | None = None
        self.setWindowTitle(self.tr("로컬 CUDA 진단"))
        self.resize(880, 700)
        self._build_ui()
        self.refresh_runtime_status()

    def tr(self, text: str, **kwargs) -> str:
        return tr_ui(text, self.lang, **kwargs)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        intro = QLabel(self.tr("이 PC에서 로컬 GPU 기능을 사용할 수 있는지 확인합니다."))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.status_label = QLabel("", self)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.text = QTextEdit(self)
        self.text.setReadOnly(True)
        try:
            font = QFont("Consolas")
            font.setStyleHint(QFont.StyleHint.Monospace)
            self.text.setFont(font)
        except Exception:
            pass
        self.text.setPlainText(self.tr("진단 실행을 누르면 Torch/Paddle GPU 사용 가능 여부를 확인합니다."))
        layout.addWidget(self.text, 1)

        self.install_status_label = QLabel("", self)
        self.install_status_label.setWordWrap(True)
        self.install_status_label.setVisible(False)
        layout.addWidget(self.install_status_label)

        self.install_progress = QProgressBar(self)
        self.install_progress.setRange(0, 100)
        self.install_progress.setValue(0)
        self.install_progress.setVisible(False)
        layout.addWidget(self.install_progress)

        install_row = QHBoxLayout()
        self.install_torch_btn = QPushButton(self.tr("Torch CUDA 런타임 설치"), self)
        self.install_paddle_btn = QPushButton(self.tr("Paddle GPU 런타임 설치"), self)
        self.delete_runtime_btn = QPushButton(self.tr("GPU 런타임 삭제"), self)
        self.install_torch_btn.clicked.connect(lambda: self.install_runtime_role("torch"))
        self.install_paddle_btn.clicked.connect(lambda: self.install_runtime_role("paddle"))
        self.delete_runtime_btn.clicked.connect(self.delete_managed_runtime)
        install_row.addWidget(self.install_torch_btn)
        install_row.addWidget(self.install_paddle_btn)
        install_row.addWidget(self.delete_runtime_btn)
        install_row.addStretch(1)
        layout.addLayout(install_row)

        btn_row = QHBoxLayout()
        self.run_btn = QPushButton(self.tr("진단 실행"), self)
        self.copy_btn = QPushButton(self.tr("보고서 복사"), self)
        self.folder_btn = QPushButton(self.tr("보고서 폴더 열기"), self)
        self.close_btn = QPushButton(self.tr("닫기"), self)
        self.copy_btn.setEnabled(False)
        self.run_btn.clicked.connect(self.run_probe)
        self.copy_btn.clicked.connect(self.copy_report)
        self.folder_btn.clicked.connect(self.open_runtime_or_report_folder)
        self.close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.run_btn)
        btn_row.addWidget(self.copy_btn)
        btn_row.addWidget(self.folder_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.close_btn)
        layout.addLayout(btn_row)

    def refresh_runtime_status(self) -> None:
        try:
            st = runtime_status()
            torch_state = self.tr("있음") if st.get("torch_exists") else self.tr("없음")
            paddle_state = self.tr("있음") if st.get("paddle_exists") else self.tr("없음")
            self.status_label.setText(f"{self.tr('GPU 런타임 상태')} - Torch: {torch_state} / Paddle: {paddle_state}")
        except Exception as exc:
            self.status_label.setText(str(exc))

    def _set_busy(self, busy: bool) -> None:
        self.run_btn.setEnabled(not busy)
        self.install_torch_btn.setEnabled(not busy)
        self.install_paddle_btn.setEnabled(not busy)
        self.delete_runtime_btn.setEnabled(not busy)
        self.close_btn.setEnabled(not busy)

    def _append_text(self, line: str) -> None:
        cursor = self.text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(str(line) + "\n")
        self.text.setTextCursor(cursor)
        self.text.ensureCursorVisible()

    def _status_label(self, value: str) -> str:
        mapping = {
            "gpu_available": self.tr("GPU 가능"),
            "cpu_runtime_available": self.tr("CPU 가능"),
            "torch_runtime_missing": self.tr("Torch 런타임 없음"),
            "paddle_runtime_missing": self.tr("Paddle 런타임 없음"),
        }
        return mapping.get(str(value or ""), str(value or "-"))

    def _selected_line(self, title: str, section: dict[str, Any]) -> list[str]:
        selected = section.get("selected") or {}
        if not selected:
            return [f"{title}: {self.tr('검사 대상 없음')}"]
        path = selected.get("candidate_python") or selected.get("python") or ""
        installed = self.tr("설치됨") if selected.get("installed") else self.tr("미설치")
        if section.get("role") == "torch":
            gpu = self.tr("GPU 통과") if section.get("gpu_ready") else self.tr("GPU 미통과")
            detail = f"torch {selected.get('version') or '-'} / cuda build {selected.get('cuda_build') or '-'}"
        else:
            gpu = self.tr("GPU 통과") if section.get("gpu_ready") else self.tr("GPU 미통과")
            detail = f"paddle {selected.get('version') or '-'} / cuda compiled {selected.get('cuda_compiled')}"
        return [f"{title}: {installed} / {gpu}", f"  - {detail}", f"  - {path}"]

    def format_report(self, report: dict[str, Any]) -> str:
        lines: list[str] = []
        lines.append(self.tr("로컬 CUDA 진단 결과"))
        lines.append("=" * 52)
        lines.append(f"{self.tr('검사 시간')}: {report.get('created_at', '-')}")
        lines.append(f"{self.tr('소요 시간')}: {report.get('elapsed_sec', '-')}s")
        lines.append("")

        nvidia = report.get("nvidia") or {}
        lines.append(f"[NVIDIA]")
        if nvidia.get("available"):
            lines.append(f"{self.tr('nvidia-smi')}: OK")
            lines.append(f"{self.tr('드라이버 CUDA 표시값')}: {nvidia.get('cuda_version') or '-'}")
            for idx, gpu in enumerate(nvidia.get("gpus") or []):
                lines.append(f"  GPU {idx}: {gpu.get('name') or '-'} / Driver {gpu.get('driver_version') or '-'} / VRAM {gpu.get('memory_total_mb') or '-'} MB / CC {gpu.get('compute_capability') or '-'}")
            rec = nvidia.get("recommendation") or {}
            lines.append(f"  Torch hint: {rec.get('torch_bundle_hint') or '-'}")
            lines.append(f"  Paddle hint: {rec.get('paddle_bundle_hint') or '-'}")
        else:
            lines.append(f"{self.tr('nvidia-smi')}: {self.tr('감지 안 됨')}")
            lines.append(f"  {nvidia.get('error') or '-'}")
        lines.append("")

        lines.extend(self._selected_line("[Torch]", report.get("torch") or {}))
        lines.append(f"  {self.tr('후보 수')}: {(report.get('torch') or {}).get('candidate_count', 0)}")
        lines.append("")
        lines.extend(self._selected_line("[Paddle]", report.get("paddle") or {}))
        lines.append(f"  {self.tr('후보 수')}: {(report.get('paddle') or {}).get('candidate_count', 0)}")
        lines.append("")

        lines.append("[YSB Engines]")
        engines = report.get("ysb_engines") or {}
        for key in ("lama_inpaint", "manga_ocr", "comic_text_detector", "paddle_ocr"):
            lines.append(f"  {key}: {self._status_label(engines.get(key, ''))}")
        lines.append("")

        lines.append(f"[{self.tr('권장 조치')}]")
        recs = report.get("recommendations") or []
        if not recs:
            lines.append(f"  - {self.tr('추가 권장 조치가 없습니다.')}")
        for rec in recs:
            text = rec.get("en") if str(self.lang).lower().startswith("en") else rec.get("ko")
            lines.append(f"  - [{rec.get('level', '-')}] {text}")
        lines.append("")
        if report.get("report_path"):
            lines.append(f"{self.tr('보고서 저장 위치')}: {report.get('report_path')}")
        if report.get("report_save_error"):
            lines.append(f"{self.tr('보고서 저장 실패')}: {report.get('report_save_error')}")
        return "\n".join(lines)

    def handle_install_progress(self, payload) -> None:
        try:
            if isinstance(payload, dict):
                typ = str(payload.get("type") or "")
                if typ == "stage":
                    cur = int(payload.get("current") or 0)
                    total = max(1, int(payload.get("total") or 1))
                    pct = int(round(cur * 100 / total))
                    self.install_progress.setVisible(True)
                    self.install_progress.setRange(0, 100)
                    self.install_progress.setValue(max(0, min(100, pct)))
                    self.install_status_label.setVisible(True)
                    self.install_status_label.setText(str(payload.get("text") or ""))
                    self._append_text(f"[{cur}/{total}] {payload.get('text') or ''}")
                    return
                if typ == "download_progress":
                    pct = int(payload.get("percent") or 0)
                    package = str(payload.get("package") or "")
                    line = (
                        f"{package + ' - ' if package else ''}"
                        f"{payload.get('current_text') or ''} / {payload.get('total_text') or ''} "
                        f"({pct}%, {payload.get('speed_text') or ''})"
                    )
                    self.install_progress.setVisible(True)
                    self.install_progress.setRange(0, 100)
                    self.install_progress.setValue(max(0, min(100, pct)))
                    self.install_status_label.setVisible(True)
                    self.install_status_label.setText(line)
                    # Do not spam the text box for every raw byte update; keep the label live.
                    now = __import__('time').perf_counter()
                    last = float(getattr(self, "_last_install_progress_log_time", 0.0) or 0.0)
                    if now - last >= 1.0 or pct in (0, 100):
                        self._last_install_progress_log_time = now
                        self._append_text(line)
                    return
                if typ == "package":
                    pkg = str(payload.get("package") or "")
                    self.install_status_label.setVisible(True)
                    self.install_status_label.setText(f"패키지 준비 중: {pkg}")
                    self._append_text(str(payload.get("line") or pkg))
                    return
                if typ == "command":
                    self._append_text(str(payload.get("text") or ""))
                    return
                if typ == "error":
                    self._append_text(str(payload.get("text") or payload))
                    return
            self._append_text(str(payload))
        except Exception:
            try:
                self._append_text(str(payload))
            except Exception:
                pass

    def install_runtime_role(self, role: str) -> None:
        role_name = "Torch CUDA" if role == "torch" else "Paddle GPU"
        msg = self.tr("선택한 GPU 런타임을 자동으로 다운로드하고 준비합니다. 시간이 오래 걸리고 인터넷 연결이 필요합니다. 계속할까요?")
        if QMessageBox.question(self, self.tr("로컬 런타임 설치"), msg) != QMessageBox.StandardButton.Yes:
            return
        self.text.setPlainText(f"{role_name} {self.tr('설치 시작')}\n")
        self.install_status_label.setVisible(True)
        self.install_status_label.setText(self.tr("설치 준비 중..."))
        self.install_progress.setVisible(True)
        self.install_progress.setRange(0, 100)
        self.install_progress.setValue(0)
        self._last_install_progress_log_time = 0.0
        self._set_busy(True)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.install_worker = RuntimeInstallWorker(role, self)
        self.install_worker.progress.connect(self.handle_install_progress)
        self.install_worker.finished_report.connect(self.install_finished)
        self.install_worker.start()

    def install_finished(self, result: dict) -> None:
        QApplication.restoreOverrideCursor()
        self._set_busy(False)
        try:
            self.install_progress.setRange(0, 100)
            self.install_progress.setValue(100 if result.get("ok") else self.install_progress.value())
            self.install_status_label.setText(self.tr("설치 완료") if result.get("ok") else self.tr("설치 실패"))
        except Exception:
            pass
        self.refresh_runtime_status()
        self._append_text("")
        self._append_text(json.dumps(result, ensure_ascii=False, indent=2))
        try:
            if self.parent_window is not None and hasattr(self.parent_window, "audit_boundary_event"):
                self.parent_window.audit_boundary_event(
                    "LOCAL_CUDA_RUNTIME_INSTALL_DONE",
                    ok=bool(result.get("ok")),
                    role=result.get("role"),
                    runtime_mode=result.get("runtime_mode"),
                    runtime_root=result.get("runtime_root"),
                    stage=result.get("stage"),
                    error=result.get("error"),
                )
        except Exception:
            pass
        if result.get("ok"):
            QMessageBox.information(self, self.tr("로컬 런타임 설치"), self.tr("설치가 끝났습니다. 진단 실행으로 GPU 사용 가능 여부를 확인하세요."))
        else:
            QMessageBox.warning(self, self.tr("로컬 런타임 설치 실패"), str(result.get("message") or result.get("error") or result.get("stage") or result))

    def delete_managed_runtime(self) -> None:
        root = managed_runtime_root()
        msg = self.tr("설치된 Torch/Paddle GPU 런타임을 삭제합니다. 계속할까요?")
        if QMessageBox.question(self, self.tr("GPU 런타임 삭제"), msg) != QMessageBox.StandardButton.Yes:
            return
        try:
            result = delete_runtime(None)
            self.text.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
            self.refresh_runtime_status()
        except Exception as exc:
            QMessageBox.warning(self, self.tr("GPU 런타임 삭제 실패"), str(exc))

    def run_probe(self) -> None:
        self.run_btn.setEnabled(False)
        self.text.setPlainText(self.tr("진단 중입니다. Torch/Paddle GPU를 실제로 실행해 확인하므로 잠시 걸릴 수 있습니다."))
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            report = run_full_probe(write_report=True)
            self.report = report
            self.report_path = str(report.get("report_path") or "")
            self.text.setPlainText(self.format_report(report))
            self.copy_btn.setEnabled(True)
            self.refresh_runtime_status()
            try:
                if self.parent_window is not None and hasattr(self.parent_window, "audit_boundary_event"):
                    engines = report.get("ysb_engines") or {}
                    self.parent_window.audit_boundary_event(
                        "LOCAL_CUDA_RUNTIME_PROBE_DONE",
                        torch_gpu=bool((report.get("torch") or {}).get("gpu_ready")),
                        paddle_gpu=bool((report.get("paddle") or {}).get("gpu_ready")),
                        runtime_mode=report.get("runtime_mode"),
                        runtime_root=report.get("runtime_root"),
                        lama=engines.get("lama_inpaint"),
                        paddle_ocr=engines.get("paddle_ocr"),
                    )
            except Exception:
                pass
        except Exception as exc:
            QMessageBox.critical(self, self.tr("로컬 CUDA 진단 실패"), str(exc))
            self.text.setPlainText(f"{self.tr('로컬 CUDA 진단 실패')}\n\n{exc}")
        finally:
            QApplication.restoreOverrideCursor()
            self.run_btn.setEnabled(True)

    def copy_report(self) -> None:
        if not self.report:
            return
        try:
            QGuiApplication.clipboard().setText(json.dumps(self.report, ensure_ascii=False, indent=2))
            QMessageBox.information(self, self.tr("보고서 복사"), self.tr("진단 보고서를 클립보드에 복사했습니다."))
        except Exception as exc:
            QMessageBox.warning(self, self.tr("보고서 복사 실패"), str(exc))

    def open_runtime_or_report_folder(self) -> None:
        try:
            folder = managed_runtime_root()
            if self.report_path:
                folder = Path(self.report_path).parent
            else:
                folder.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        except Exception as exc:
            QMessageBox.warning(self, self.tr("보고서 폴더 열기 실패"), str(exc))
