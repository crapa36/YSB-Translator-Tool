"""YSB Tool Local entry point.

v2.1.0 selects the Local edition shell and enables the supported Local OCR stack:
comic_text_detector + external PaddleOCR worker + LOCAL LaMa.

Normal release startup intentionally does not write stage/fault/debug logs into
the package folder.  A crash log is written only when startup actually fails.
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

ENTRY_NAME = "YSB Tool Local"
_CRASH_FILE = "ysb_startup_crash.log"


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


def _write_crash_log(exc: BaseException) -> Path | None:
    text = "\n".join([
        f"{ENTRY_NAME} startup crash",
        f"executable: {getattr(sys, 'executable', '')}",
        f"frozen: {getattr(sys, 'frozen', False)}",
        f"cwd: {os.getcwd()}",
        f"argv: {sys.argv!r}",
        "",
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    ])
    return _write_text_file(_CRASH_FILE, text, append=False)


def main() -> int:
    try:
        from ysb.editions.current import set_current_edition
        set_current_edition("local")
        from ysb.ui.main_window import run_app
        run_app()
        return 0
    except SystemExit as exc:
        # QApplication/run_app may exit through SystemExit(0). That is a
        # normal close path, not a startup crash. Do not show a false error
        # dialog and do not create release-package log leftovers.
        try:
            code = int(exc.code or 0)
        except Exception:
            code = 1
        if code == 0:
            return 0
        log_path = _write_crash_log(exc)
        _show_error(exc, log_path)
        return code or 1
    except BaseException as exc:
        log_path = _write_crash_log(exc)
        _show_error(exc, log_path)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
