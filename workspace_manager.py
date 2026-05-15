import json
import os
import shutil
import sys
from pathlib import Path

APP_FOLDER_NAME = "YSB_Translator"
CONFIG_FOLDER_NAME = "YSBTranslator"
CONFIG_FILE_NAME = "workspace_config.json"


def user_documents_dir() -> Path:
    # Windows 기본값: C:\Users\사용자\Documents. 다른 OS에서는 홈/Documents 사용.
    home = Path.home()
    docs = home / "Documents"
    return docs if docs.exists() else home


def default_workspace_root() -> Path:
    return user_documents_dir() / APP_FOLDER_NAME


def app_config_dir() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / CONFIG_FOLDER_NAME
    return Path.home() / f".{APP_FOLDER_NAME}"


def config_path() -> Path:
    return app_config_dir() / CONFIG_FILE_NAME


def load_workspace_config() -> dict:
    try:
        p = config_path()
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}



def configured_workspace_root_raw() -> Path | None:
    """설정 파일에 저장된 작업 루트만 가져온다. 폴더를 만들지 않는다."""
    cfg = load_workspace_config()
    value = cfg.get("workspace_root")
    if value:
        try:
            return Path(value)
        except Exception:
            return None
    return None


def pending_workspace_root_raw() -> Path | None:
    """예약된 작업 루트만 가져온다. 폴더를 만들지 않는다."""
    cfg = load_workspace_config()
    value = cfg.get("pending_workspace_root")
    if value:
        try:
            return Path(value)
        except Exception:
            return None
    return None


def configured_workspace_root_exists() -> bool:
    """저장된 작업 루트가 실제 폴더로 존재하는지 확인한다. 폴더를 새로 만들지 않는다."""
    root = configured_workspace_root_raw()
    return bool(root and root.exists() and root.is_dir())


def save_workspace_config(data: dict):
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(dict(data or {}), f, ensure_ascii=False, indent=2)


def ensure_workspace_structure(root: str | Path):
    root = Path(root)
    for name in ("cache", "temp", "workspaces"):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def _safe_move_workspace(old_root: Path, new_root: Path):
    old_root = old_root.resolve()
    new_root = new_root.resolve()
    if old_root == new_root:
        ensure_workspace_structure(new_root)
        return
    if not old_root.exists():
        raise FileNotFoundError(f"저장된 기존 작업 폴더를 찾을 수 없습니다: {old_root}")
    if new_root.exists() and any(new_root.iterdir()):
        # 대상 폴더가 비어 있지 않으면 루트 자체 이동 대신 하위 항목을 병합한다.
        ensure_workspace_structure(new_root)
        for child in old_root.iterdir():
            target = new_root / child.name
            if target.exists():
                continue
            shutil.move(str(child), str(target))
    else:
        new_root.parent.mkdir(parents=True, exist_ok=True)
        if new_root.exists():
            shutil.rmtree(new_root, ignore_errors=True)
        shutil.move(str(old_root), str(new_root))
    ensure_workspace_structure(new_root)


def apply_pending_workspace_move_if_needed() -> Path:
    cfg = load_workspace_config()
    current = Path(cfg.get("workspace_root") or default_workspace_root())
    pending = cfg.get("pending_workspace_root")
    if pending:
        pending_path = Path(pending)
        try:
            _safe_move_workspace(current, pending_path)
            cfg["workspace_root"] = str(pending_path)
            cfg.pop("pending_workspace_root", None)
            save_workspace_config(cfg)
            current = pending_path
        except Exception:
            # 이동 실패 시 기존 루트를 유지한다. 실패 내용은 프로그램 시작 후 옵션 창에서 다시 처리하게 한다.
            current = Path(cfg.get("workspace_root") or default_workspace_root())
    ensure_workspace_structure(current)
    return current


def get_workspace_root() -> Path:
    return apply_pending_workspace_move_if_needed()


def set_workspace_root(path: str | Path):
    cfg = load_workspace_config()
    cfg["workspace_root"] = str(Path(path))
    cfg.pop("pending_workspace_root", None)
    save_workspace_config(cfg)
    ensure_workspace_structure(path)


def schedule_workspace_root_change(path: str | Path):
    cfg = load_workspace_config()
    cfg.setdefault("workspace_root", str(get_workspace_root()))
    cfg["pending_workspace_root"] = str(Path(path))
    save_workspace_config(cfg)


def workspace_subdir(name: str) -> Path:
    root = get_workspace_root()
    p = root / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def cache_dir() -> Path:
    return workspace_subdir("cache")


def temp_dir() -> Path:
    return workspace_subdir("temp")


def workspaces_dir() -> Path:
    return workspace_subdir("workspaces")


def packages_dir() -> Path:
    # 호환용: 더 이상 packages 폴더를 만들지 않고, 기본 패키지 저장 위치는 문서 폴더를 사용한다.
    p = user_documents_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p

def default_package_dir() -> Path:
    p = user_documents_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p
