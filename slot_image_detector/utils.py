from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from slugify import slugify


def safe_slug(value: str) -> str:
    return slugify(value, separator="-") or "unknown"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def to_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=True, separators=(",", ":"))
