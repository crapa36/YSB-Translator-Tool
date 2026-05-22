"""Official YSB launcher entry point.

Use this for .ysbt double-click launching / file association.

v2.0.1 packaging note:
Use a direct import instead of runpy/run_module so PyInstaller can keep the
launcher bundle focused on ysb.core.ysb_launcher instead of guessing the whole
application package.
"""

from ysb.core.ysb_launcher import main


if __name__ == "__main__":
    raise SystemExit(main())
