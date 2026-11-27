"""Which held requests the admin has already been told about, so each is announced once."""

import json
import os
from pathlib import Path


def load(path: str) -> set[int]:
    try:
        return {int(i) for i in json.loads(Path(path).read_text(encoding="utf-8"))["told"]}
    except (OSError, ValueError, KeyError, TypeError):
        return set()  # worst case: one repeat alert


def save(path: str, told: set[int]) -> None:
    tmp = Path(path + ".tmp")
    tmp.write_text(json.dumps({"told": sorted(told)}), encoding="utf-8")
    os.replace(tmp, path)
