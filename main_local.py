"""YSB Tool Local entry point.

v2.1.0 selects the Local edition shell and enables the supported Local OCR stack:
comic_text_detector + PaddleOCR.

This entry point intentionally keeps *all* YSB imports inside the guarded block.
If a frozen Local build dies during early imports, it writes stage/crash logs next
to the EXE or under %LOCALAPPDATA%\\YSBTranslator\\logs.
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

ENTRY_NAME = "YSB Tool Local"
_STAGE_FILE = "ysb_startup_stage.log"
_CRASH_FILE = "ysb_startup_crash.log"
_FAULT_FILE = "ysb_startup_faulthandler.log"
_FAULT_HANDLE = None


def _candidate_log_dirs() -> list[Path]:
    dirs: list[Path] = []
    try:
        if getattr(sys, "frozen", False):
            dirs.append(Path(sys.executable).resolve().parent)
    except Exception:
        pass
    try:
        local = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if local:
            dirs.append(Path(local) / "YSBTranslator" / "logs")
    except Exception:
        pass
    try:
        dirs.append(Path.cwd())
    except Exception:
        pass
    try:
        dirs.append(Path(__file__).resolve().parent)
    except Exception:
        pass
    return dirs


def _write_text_file(name: str, text: str, *, append: bool = False) -> Path | None:
    for d in _candidate_log_dirs():
        try:
            d.mkdir(parents=True, exist_ok=True)
            p = d / name
            mode = "a" if append else "w"
            with p.open(mode, encoding="utf-8", errors="replace") as f:
                f.write(text)
            return p
        except Exception:
            continue
    return None


def _stage(message: str) -> None:
    text = (
        f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{ENTRY_NAME}] {message}\n"
        f"  executable: {getattr(sys, 'executable', '')}\n"
        f"  frozen: {getattr(sys, 'frozen', False)}\n"
        f"  cwd: {os.getcwd()}\n"
        f"  argv: {sys.argv!r}\n"
    )
    _write_text_file(_STAGE_FILE, text, append=True)


def _enable_faulthandler() -> None:
    global _FAULT_HANDLE
    try:
        import faulthandler
        for d in _candidate_log_dirs():
            try:
                d.mkdir(parents=True, exist_ok=True)
                _FAULT_HANDLE = (d / _FAULT_FILE).open("a", encoding="utf-8", errors="replace")
                _FAULT_HANDLE.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} {ENTRY_NAME} faulthandler enabled ===\n")
                _FAULT_HANDLE.flush()
                faulthandler.enable(file=_FAULT_HANDLE, all_threads=True)
                return
            except Exception:
                continue
    except Exception:
        pass


def _show_error(exc: BaseException, log_path: Path | None) -> None:
    message = f"프로그램 시작 중 오류가 발생했습니다.\n\n{exc}"
    if log_path:
        message += f"\n\n로그: {log_path}"
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, ENTRY_NAME, 0x10)
            return
        except Exception:
            pass
    try:
        print(message, file=sys.stderr)
    except Exception:
        pass


def main() -> int:
    _enable_faulthandler()
    _stage("entry started before YSB imports")

    try:
        _stage("importing ysb.editions.current")
        from ysb.editions.current import set_current_edition

        _stage("setting edition: local")
        set_current_edition("local")

        _stage("importing ysb.ui.main_window.run_app")
        from ysb.ui.main_window import run_app

        _stage("calling run_app")
        run_app()
        _stage("run_app returned normally")
        return 0
    except SystemExit as exc:
        # QApplication/run_app may exit through SystemExit(0). That is a
        # normal close path, not a startup crash. Do not show a false error
        # dialog containing only "0".
        try:
            code = int(exc.code or 0)
        except Exception:
            code = 1
        if code == 0:
            _stage("run_app raised SystemExit(0); treating as normal exit")
            return 0
        text = "\n".join([
            f"{ENTRY_NAME} startup crash",
            time.strftime("%Y-%m-%d %H:%M:%S"),
            f"executable: {getattr(sys, 'executable', '')}",
            f"frozen: {getattr(sys, 'frozen', False)}",
            f"cwd: {os.getcwd()}",
            f"argv: {sys.argv!r}",
            "",
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        ])
        log_path = _write_text_file(_CRASH_FILE, text, append=False)
        _show_error(exc, log_path)
        return code or 1
    except BaseException as exc:
        text = "\n".join([
            f"{ENTRY_NAME} startup crash",
            time.strftime("%Y-%m-%d %H:%M:%S"),
            f"executable: {getattr(sys, 'executable', '')}",
            f"frozen: {getattr(sys, 'frozen', False)}",
            f"cwd: {os.getcwd()}",
            f"argv: {sys.argv!r}",
            "",
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        ])
        log_path = _write_text_file(_CRASH_FILE, text, append=False)
        _show_error(exc, log_path)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
