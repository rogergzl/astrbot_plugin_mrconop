import json
import os
import time

from .utils import strip_mc_color
from .permission import _get_group_id


def _audit(plugin, event, cmd: str, ok: bool, resp: str, category: str = "cmd"):
    try:
        rec = {
            "time": int(time.time()),
            "category": category,
            "sender_id": str(event.get_sender_id()),
            "sender_name": str(event.get_sender_name()),
            "group_id": _get_group_id(plugin, event),
            "cmd": cmd,
            "ok": bool(ok),
            "resp": strip_mc_color(str(resp))[:2000],
        }
        os.makedirs(plugin.plugin_data_dir, exist_ok=True)
        with open(plugin.audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _audit_web(plugin, op: str, detail: str = "", ok: bool = True, operator: str = "web"):
    try:
        rec = {
            "time": int(time.time()),
            "category": "web",
            "sender_id": "0",
            "sender_name": operator,
            "group_id": "",
            "cmd": op,
            "ok": bool(ok),
            "resp": str(detail)[:2000],
        }
        os.makedirs(plugin.plugin_data_dir, exist_ok=True)
        with open(plugin.audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _audit_web_cmd(plugin, op: str, detail: str = "", ok: bool = True, operator: str = "web"):
    try:
        rec = {
            "time": int(time.time()),
            "category": "web_rcon",
            "sender_id": "0",
            "sender_name": operator,
            "group_id": "",
            "cmd": op,
            "ok": bool(ok),
            "resp": str(detail)[:2000],
        }
        os.makedirs(plugin.plugin_data_dir, exist_ok=True)
        with open(plugin.audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass
