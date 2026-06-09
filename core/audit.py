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


def _audit_auto(plugin, category: str, cmd: str, detail: str = "", ok: bool = True):
    """自动/系统触发的 RCON 命令审计（事件宏、触发器、relay、在线提醒等）。
    受 audit.skip_categories 配置控制，可屏蔽高频类别。
    """
    try:
        if not plugin.audit_auto_enabled:
            return
        # 检查是否在跳过类别中
        skip_categories = getattr(plugin, "audit_skip_categories", [])
        if category in skip_categories:
            return
        rec = {
            "time": int(time.time()),
            "category": category,
            "sender_id": "0",
            "sender_name": "auto",
            "group_id": "",
            "cmd": cmd,
            "ok": bool(ok),
            "resp": str(detail)[:2000],
        }
        os.makedirs(plugin.plugin_data_dir, exist_ok=True)
        with open(plugin.audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass
