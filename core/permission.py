import re

from astrbot.api.event import AstrMessageEvent


def is_admin(plugin, qqid: str) -> bool:
    return qqid in plugin.admin_qqs


def _get_group_id(plugin, event: AstrMessageEvent) -> str:
    for name in ["get_group_id", "get_target_id", "get_chat_id", "get_session_id", "get_group", "get_channel_id"]:
        f = getattr(event, name, None)
        if callable(f):
            try:
                v = f()
            except Exception:
                v = None
            if v:
                return str(v)
    for name in ["group_id", "group", "channel_id", "chat_id"]:
        if hasattr(event, name):
            v = getattr(event, name)
            if v:
                return str(v)
    return ""


def is_allowed(plugin, event: AstrMessageEvent) -> bool:
    qq = str(event.get_sender_id())
    if qq in plugin.admin_qqs:
        return True
    gid = _get_group_id(plugin, event)
    wl = []
    if gid and gid in plugin.group_map:
        wl = plugin.group_map[gid].get("whitelist_qqs", [])
    return qq in set(str(x) for x in wl)


def _match_dangerous(plugin, cmd: str) -> bool:
    s = cmd.lower()
    for it in plugin.dangerous_blacklist:
        if str(it).lower() in s:
            return True
    return False


def _extract_full_after_cmd(plugin, event: AstrMessageEvent, fallback: str) -> str:
    cmd_names = ["/mrcon", "/执行", "/mcmd", "mrcon", "执行", "mcmd"]
    raw_candidates = []
    for name in [
        "get_message_text", "get_plain_text", "get_text", "get_raw_text",
        "raw_text", "text", "content", "message_str",
    ]:
        f = getattr(event, name, None)
        val = None
        if callable(f):
            try:
                val = f()
            except Exception:
                val = None
        elif hasattr(event, name):
            val = getattr(event, name, None)
        if isinstance(val, str) and val:
            raw_candidates.append(val)
    msg_obj = None
    get_message_fn = getattr(event, "get_message", None)
    get_messages_fn = getattr(event, "get_messages", None)
    if callable(get_message_fn):
        try:
            msg_obj = get_message_fn()
        except Exception:
            msg_obj = None
    elif callable(get_messages_fn):
        try:
            msg_obj = get_messages_fn()
        except Exception:
            msg_obj = None
    elif hasattr(event, "message"):
        msg_obj = getattr(event, "message", None)
    if isinstance(msg_obj, list):
        parts = []
        for it in msg_obj:
            t = None
            if isinstance(it, str):
                t = it
            elif isinstance(it, dict):
                if isinstance(it.get("text"), str):
                    t = it.get("text")
                elif isinstance(it.get("data"), dict) and isinstance(it.get("data", {}).get("text"), str):
                    t = it.get("data", {}).get("text")
            elif hasattr(it, "text") and isinstance(getattr(it, "text", None), str):
                t = getattr(it, "text")
            if isinstance(t, str) and t:
                parts.append(t)
        if parts:
            raw_candidates.append(" ".join(parts))
    elif isinstance(msg_obj, dict):
        t = None
        if isinstance(msg_obj.get("text"), str):
            t = msg_obj.get("text")
        elif isinstance(msg_obj.get("content"), str):
            t = msg_obj.get("content")
        if isinstance(t, str) and t:
            raw_candidates.append(t)
    if hasattr(event, "message_obj"):
        mo = getattr(event, "message_obj")
        chain = getattr(mo, "message", None)
        if isinstance(chain, list):
            parts2 = []
            for seg in chain:
                if hasattr(seg, "text") and isinstance(getattr(seg, "text", None), str):
                    tt = getattr(seg, "text")
                    if tt:
                        parts2.append(tt)
            if parts2:
                raw_candidates.append(" ".join(parts2))
    raw = fallback
    if raw_candidates:
        raw = max(raw_candidates, key=len)
    text = str(raw or "").strip()
    patterns = [r"^.*?(?:/mrcon|mrcon|/执行|执行|/mcmd|mcmd)\s+(.+)$"]
    for pat in patterns:
        m = re.match(pat, text, flags=re.IGNORECASE | re.DOTALL)
        if m:
            tail = m.group(1).strip()
            if tail:
                return tail
    lowered = text.lower()
    for cn in cmd_names:
        i = lowered.find(cn)
        if i >= 0:
            tail = text[i + len(cn):].strip()
            if tail:
                return tail
    return fallback
