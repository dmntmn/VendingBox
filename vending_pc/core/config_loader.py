import json
from pathlib import Path


def load_config(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    assert "items" in data and "ports" in data and "timeouts" in data
    return data
