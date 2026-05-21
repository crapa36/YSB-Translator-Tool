"""YSB Translator Tool entry point.

The application code is organized under the ``ysb`` package.
This file is intentionally kept small so build scripts and users can keep
running ``python main.py`` as before.

v2.0.0 packaging note:
Use a direct import instead of runpy/run_module so PyInstaller can follow the
package graph without heavy blanket hidden-imports.
"""

from ysb.ui.main_window import run_app


if __name__ == "__main__":
    run_app()
