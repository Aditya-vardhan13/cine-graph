"""Free-space guard for resumable local model and indexing jobs."""
from pathlib import Path
import shutil


def require_free_space(path: Path, minimum_bytes: int) -> None:
    if minimum_bytes < 0:
        raise ValueError("Minimum free space cannot be negative.")
    available = shutil.disk_usage(path).free
    if available < minimum_bytes:
        raise RuntimeError(f"Insufficient free space: {available} bytes available; {minimum_bytes} bytes required.")
