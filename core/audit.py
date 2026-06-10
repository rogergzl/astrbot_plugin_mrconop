import json
import os
import time

from .utils import strip_mc_color
from .permission import _get_group_id


def _write_jsonl(plugin, rec: dict):
    """写入 JSONL 文件（兼容旧逻辑）"""
    if not getattr(plugin, "audit_jsonl_keep", True):
        return
    try:
        os.makedirs(plugin.plugin_data_dir, exist_ok=True)
        with open(plugin.audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _write_db(plugin, rec: dict):
    """写入数据库（新逻辑）"""
    try:
        if not getattr(plugin, "audit_db_enabled", False):
            return
        plugin.db.add_audit_log(
            time_ts=rec["time"],
            category=rec.get("category", "cmd"),
            cmd=rec.get("cmd", ""),
            sender_id=rec.get("sender_id", "0"),
            sender_name=rec.get("sender_name", ""),
            group_id=rec.get("group_id", ""),
            group_name=rec.get("group_name", ""),
            event_type=rec.get("event_type", ""),
            server_name=rec.get("server_name", ""),
            ok=rec.get("ok", True),
            resp=rec.get("resp", ""),
        )
    except Exception:
        pass


def _audit(plugin, event, cmd: str, ok: bool, resp: str, category: str = "cmd",
           event_type: str = "", server_name: str = ""):
    try:
        group_id = _get_group_id(plugin, event)
        rec = {
            "time": int(time.time()),
            "category": category,
            "event_type": event_type,
            "sender_id": str(event.get_sender_id()),
            "sender_name": str(event.get_sender_name()),
            "group_id": group_id,
            "group_name": plugin.group_names.get(group_id, ""),
            "server_name": server_name,
            "cmd": cmd,
            "ok": bool(ok),
            "resp": strip_mc_color(str(resp))[:2000],
        }
        _write_jsonl(plugin, rec)
        _write_db(plugin, rec)
    except Exception:
        pass


def _audit_web(plugin, op: str, detail: str = "", ok: bool = True, operator: str = "web",
               event_type: str = "", server_name: str = ""):
    try:
        rec = {
            "time": int(time.time()),
            "category": "web",
            "event_type": event_type,
            "sender_id": "0",
            "sender_name": operator,
            "group_id": "",
            "group_name": "",
            "server_name": server_name,
            "cmd": op,
            "ok": bool(ok),
            "resp": str(detail)[:2000],
        }
        _write_jsonl(plugin, rec)
        _write_db(plugin, rec)
    except Exception:
        pass


def _audit_web_cmd(plugin, op: str, detail: str = "", ok: bool = True, operator: str = "web",
                   event_type: str = "", server_name: str = ""):
    try:
        rec = {
            "time": int(time.time()),
            "category": "web_rcon",
            "event_type": event_type,
            "sender_id": "0",
            "sender_name": operator,
            "group_id": "",
            "group_name": "",
            "server_name": server_name,
            "cmd": op,
            "ok": bool(ok),
            "resp": str(detail)[:2000],
        }
        _write_jsonl(plugin, rec)
        _write_db(plugin, rec)
    except Exception:
        pass


def _audit_auto(plugin, category: str, cmd: str, detail: str = "", ok: bool = True,
                event_type: str = "", server_name: str = "", group_id: str = "",
                sender_name: str = "auto"):
    """自动/系统触发的 RCON 命令审计（事件宏、触发器、relay、在线提醒等）。
    受 audit.skip_categories 配置控制，可屏蔽高频类别。
    """
    try:
        if not plugin.audit_auto_enabled:
            return
        skip_categories = getattr(plugin, "audit_skip_categories", [])
        if category in skip_categories:
            return
        rec = {
            "time": int(time.time()),
            "category": category,
            "event_type": event_type,
            "sender_id": "0",
            "sender_name": sender_name,
            "group_id": str(group_id or ""),
            "group_name": plugin.group_names.get(str(group_id or ""), ""),
            "server_name": server_name,
            "cmd": cmd,
            "ok": bool(ok),
            "resp": str(detail)[:2000],
        }
        _write_jsonl(plugin, rec)
        _write_db(plugin, rec)
    except Exception:
        pass
