"""File helpers: atomic writes (a crash never leaves a half-written file) and content hashes."""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Union


def write_atomic(path: Union[str, Path], text: str) -> None:
    """Write via a temp file in the same directory, then rename over the target."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()
