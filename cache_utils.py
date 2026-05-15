import os
import sys
from pathlib import Path

CACHE_FOLDER_NAME = "ysik_cache"


def get_app_dir() -> Path:
    """Return the folder where the program/script is running from."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(sys.argv[0]).resolve().parent


def get_cache_dir() -> Path:
    path = get_app_dir() / CACHE_FOLDER_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_cache_file(name: str) -> Path:
    return get_cache_dir() / name
