"""YSB Tool Lite entry point."""

from __future__ import annotations

import sys

from ysb.editions.current import set_current_edition
from ysb.utils.crash_guard import append_startup_stage, show_startup_error_message, write_startup_crash_log


ENTRY_NAME = "YSB Tool Lite"


def main() -> int:
    append_startup_stage("entry started", entry_name=ENTRY_NAME)
    set_current_edition("lite")
    append_startup_stage("edition set: lite", entry_name=ENTRY_NAME)
    from ysb.ui.main_window import run_app
    append_startup_stage("ysb.ui.main_window imported", entry_name=ENTRY_NAME)
    run_app()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        log_path = write_startup_crash_log(exc, entry_name=ENTRY_NAME)
        show_startup_error_message(exc, log_path, title=ENTRY_NAME)
        raise SystemExit(1)
