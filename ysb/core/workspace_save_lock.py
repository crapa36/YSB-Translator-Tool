from __future__ import annotations

import threading

# Shared lock for all background writers that touch project.json / manifest.json.
# View-layer saves and workspace image-delta saves may run in different QRunnable
# instances, so they must not write project.json concurrently.
PROJECT_JSON_SAVE_LOCK = threading.RLock()
