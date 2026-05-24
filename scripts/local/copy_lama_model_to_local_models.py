"""Copy/download SimpleLaMa model into local_models/lama/big-lama.pt.

Usage:
    .venv\\Scripts\\python.exe scripts\\local\\copy_lama_model_to_local_models.py

The script first checks torch hub cache used by simple-lama-inpainting. If the
model is missing, it instantiates SimpleLama once so the package can download it,
then copies the cached big-lama.pt into local_models/lama/.
"""
from __future__ import annotations

import shutil
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> int:
    root = project_root()
    target_dir = root / "local_models" / "lama"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "big-lama.pt"

    from torch.hub import get_dir

    cache = Path(get_dir()) / "checkpoints" / "big-lama.pt"
    if not cache.exists():
        print(f"[INFO] LaMa cache not found: {cache}")
        print("[INFO] Loading SimpleLama once. It may download the model now...")
        from simple_lama_inpainting import SimpleLama
        _ = SimpleLama()

    if not cache.exists():
        print(f"[ERROR] LaMa model was not found after download attempt: {cache}")
        return 1

    shutil.copy2(cache, target)
    print(f"[OK] Copied LaMa model:")
    print(f"     from: {cache}")
    print(f"       to: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
