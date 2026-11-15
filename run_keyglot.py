# PyInstaller entry point
import os
import sys
import traceback

try:
    from keyglot.app import main
    sys.exit(main())
except SystemExit:
    raise
except BaseException:
    from keyglot.config import APP_DIR
    os.makedirs(APP_DIR, exist_ok=True)
    with open(os.path.join(APP_DIR, "crash.log"), "a", encoding="utf-8") as f:
        f.write(traceback.format_exc() + "\n")
    raise
