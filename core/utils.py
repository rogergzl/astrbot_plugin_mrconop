import json
import os
import re
from pathlib import Path

from astrbot.api import logger

_PLAYER_NAME_RE = re.compile(r'^[a-zA-Z0-9_]{3,16}$')


def strip_mc_color(text: str) -> str:
    return re.sub(r"§.", "", text)


def safe_json_read(path: str, default=None):
    if default is None:
        default = {}
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def safe_json_write(path: str, data):
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[mrcon] JSON 写入失败 {path}: {e}")


def _is_valid_player_name(name: str) -> bool:
    return bool(name and _PLAYER_NAME_RE.match(name))
