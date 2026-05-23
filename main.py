"""YSB Translator Tool compatibility/default entry point.

Source run BAT files are split into two explicit launchers:
- run_lite_v2.1.0.bat
- run_local_v2.1.0.bat

Direct ``python main.py`` remains a compatibility/default Lite entry point.
"""

from ysb.editions.current import set_current_edition

set_current_edition("lite")

from ysb.ui.main_window import run_app


if __name__ == "__main__":
    run_app()
