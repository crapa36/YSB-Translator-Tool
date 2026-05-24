"""YSB Tool Lite entry point."""

from __future__ import annotations

from ysb.editions.current import set_current_edition
from ysb.utils.crash_guard import show_startup_error_message, write_startup_crash_log


ENTRY_NAME = "YSB Tool Lite"


def main() -> int:
    # Release entry point: do not create normal startup stage logs in the
    # package folder.  Only write a crash log if startup actually fails.
    set_current_edition("lite")
    from ysb.ui.main_window import run_app
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
