import asyncio
import itertools
import json
import os
import re
import time

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import At, Plain
from astrbot.api.star import Context, Star, StarTools

from .log_listener import LogListenerManager
from .rcon_executor import rcn_send as _rcn_send
from .transport import get_pool
from .utils import strip_mc_color


def _init_log_listeners(plugin):
    seen = set()
    for gid, srvs in plugin.group_servers.items():
        for srv in srvs:
            sn = srv.get("server_name", "unknown")
            log_mode = str(srv.get("log_mode", "") or "").strip()
            if not log_mode:
                legacy_path = str(srv.get("log_path", "") or "").strip()
                if legacy_path and legacy_path not in seen:
                    seen.add(legacy_path)
                    plugin._log_listener.add(sn, legacy_path)
                continue
            if log_mode == "file":
                log_paths = srv.get("log_paths", [])
                if isinstance(log_paths, str):
                    log_paths = [p.strip() for p in log_paths.split(",") if p.strip()]
                for lp in log_paths:
                    lp = str(lp).strip()
                    if lp and lp not in seen:
                        seen.add(lp)
                        plugin._log_listener.add(sn, lp)
            elif log_mode == "folder":
                folder = str(srv.get("log_folder", "") or "").strip()
                pattern = str(srv.get("log_file_pattern", "latest.log") or "latest.log").strip()
                if folder:
                    lp = os.path.join(folder, pattern).replace("\\", "/")
                    if lp not in seen:
                        seen.add(lp)
                        plugin._log_listener.add(sn, lp)
    if seen:
        plugin._log_listener.start(lambda *args: _on_log_event(plugin, *args))
    else:
        logger.warning("[mrcon] 日志监听已启用但无服务器配置 log_path，请在服务器管理中填写日志路径")


async def _on_log_event(plugin, server_name: str, event_type: str, player: str, raw_line: str):
    logger.info(f"[LogEvent] [{server_name}] {event_type}: {player} ({raw_line[:60]})")

    DEDUP_WINDOW = 5.0
    _now = time.time()
    _key = (server_name, event_type, player)
    if _key in plugin._recent_log_events:
        if _now - plugin._recent_log_events[_key] < DEDUP_WINDOW:
            logger.debug(f"[mrcon] 日志事件去重跳过 [{server_name}] {event_type} {player}")
            return
    plugin._recent_log_events[_key] = _now
    stale = [k for k, ts in plugin._recent_log_events.items() if _now - ts > DEDUP_WINDOW * 2]
    for k in stale:
        plugin._recent_log_events.pop(k, None)

    if plugin.log_listener_enabled:
        await _relay_log_event_to_groups(plugin, server_name, event_type, player, raw_line)
    else:
        logger.info(f"[mrcon] 日志互通 [总闸关闭] [{server_name}] {event_type} 已拦截（请在Web面板 ⚙️全局设置 中开启📡日志监听开关）")

    await _execute_event_macros(plugin, server_name, event_type, player, raw_line)

    if event_type == "chat":
        await _execute_event_macros(plugin, server_name, "player_chat", player, raw_line)

    if event_type == "player_join":
        if plugin._is_valid_player_name(player):
            plugin._known_real_players.add(player.lower())
        p = plugin.db.find_player_by_mc_id(player)
        if not p:
            if plugin._is_valid_player_name(player):
                plugin.db.insert_player_raw("_imported_" + player, player, 50, int(time.time()))
            await _execute_event_macros(plugin, server_name, "player_first_join", player, raw_line)
        if plugin.admin_mc_ids and player in plugin.admin_mc_ids:
            await _execute_event_macros(plugin, server_name, "admin_join", player, raw_line)
        vip_level = int(p.get("vip_level", 0) or 0) if p else 0
        if vip_level > 0:
            await _execute_event_macros(plugin, server_name, "vip_join", player, raw_line, vip_level=vip_level)
    elif event_type == "player_leave":
        p = plugin.db.find_player_by_mc_id(player)
        vip_level = int(p.get("vip_level", 0) or 0) if p else 0
        if vip_level > 0:
            await _execute_event_macros(plugin, server_name, "vip_leave", player, raw_line, vip_level=vip_level)
    elif event_type == "player_death":
        p = plugin.db.find_player_by_mc_id(player)
        vip_level = int(p.get("vip_level", 0) or 0) if p else 0
        if vip_level > 0:
            await _execute_event_macros(plugin, server_name, "vip_death", player, raw_line, vip_level=vip_level)
        if not p:
            if plugin._is_valid_player_name(player) and player.lower() in plugin._known_real_players:
                plugin.db.insert_player_raw("_imported_" + player, player, 50, int(time.time()))
            await _execute_event_macros(plugin, server_name, "player_first_death", player, raw_line)


def _get_group_umo(plugin, gid: str) -> str:
    cached = plugin._last_umo.get(str(gid))
    if cached:
        return cached
    if plugin._umo_prefix:
        return f"{plugin._umo_prefix}{gid}"
    return f"aiocqhttp:GroupMessage:{gid}"


def _resolve_group_display_name(plugin, gid: str) -> str:
    return plugin.group_names.get(str(gid), str(gid))


async def _relay_log_event_to_groups(plugin, server_name: str, event_type: str, player: str, raw_line: str):
    import re as _re
    message = ""
    if event_type == "chat":
        m_chat = _re.search(r'<\s*\w+\s*>\s+(.+)', raw_line)
        if m_chat:
            message = m_chat.group(1).strip()
        else:
            return
    elif event_type == "player_join":
        message = f"{player} 加入了服务器"
    elif event_type == "player_leave":
        message = f"{player} 离开了服务器"
    elif event_type == "player_death":
        m_death = _re.search(r'\w+\s+(.+)', raw_line)
        message = m_death.group(1).strip() if m_death else f"{player} 死亡"
    elif event_type == "player_advancement":
        m_adv = _re.search(r'\w+ has (.+)', raw_line)
        message = m_adv.group(1).strip() if m_adv else f"{player} 获得成就"
    elif event_type == "command":
        message = f"[命令] {player}: {raw_line.strip()}"
    elif event_type == "system":
        msg = raw_line.strip()
        if len(msg) > 300:
            msg = msg[:297] + "..."
        message = f"[系统] {msg}"
    else:
        msg = raw_line.strip()
        if len(msg) > 300:
            msg = msg[:297] + "..."
        message = msg

    forwarded = {}

    candidate_entries: dict[str, list[dict]] = {}
    for gid, entries in list(plugin._relay_overrides.items()):
        gid = str(gid)
        candidate_entries.setdefault(gid, [])
        entry_list = entries if isinstance(entries, list) else ([entries] if isinstance(entries, dict) else [])
        candidate_entries[gid].extend(entry_list)

    for gid, entry_list in candidate_entries.items():
        gid = str(gid)
        if gid in forwarded:
            continue
        gid_srvs = plugin.group_servers.get(gid, [])
        gid_map = plugin.group_map.get(gid, {})
        matched_srv = False
        for srv in (gid_srvs or []):
            if not isinstance(srv, dict):
                continue
            sn = srv.get("server_name") or srv.get("name", "")
            if sn == server_name:
                matched_srv = True
                break
        if not matched_srv and isinstance(gid_map, dict):
            sn = gid_map.get("server_name") or gid_map.get("name", "")
            if sn == server_name:
                matched_srv = True
        if not matched_srv:
            continue
        for entry in entry_list:
            mode = entry.get("mode", "off")
            if mode == "off":
                continue
            if mode == "global":
                if not plugin.log_listener_enabled:
                    continue
            elif mode == "custom":
                if not entry.get("m2g_log_enabled", False):
                    continue
            else:
                continue
            allowed_types = entry.get("log_types", [])
            expanded_types = []
            for t in (allowed_types or []):
                for pt in str(t).split(","):
                    pt = pt.strip()
                    if pt:
                        expanded_types.append(pt)
            if expanded_types and event_type not in expanded_types:
                continue
            if mode == "global":
                fmt = getattr(plugin, "relay_fmt_mc_log", None) or plugin.relay_fmt_mc
            elif mode == "custom":
                fmt = entry.get("format_mc_log") or entry.get("format_mc", plugin.relay_fmt_mc)
            else:
                continue
            text = fmt.replace("{player}", player).replace("{msg}", message).replace("{server}", server_name)
            entry_prefixes = entry.get("log_type_prefixes", {}) if mode == "custom" else {}
            prefix = entry_prefixes.get(event_type) or (plugin.log_type_prefixes or {}).get(event_type, "")
            if prefix:
                text = f"{prefix} {text}"
            gname = _resolve_group_display_name(plugin, gid)
            try:
                umo = _get_group_umo(plugin, gid)
                chain = MessageChain(chain=[Plain(text)])
                await plugin.context.send_message(umo, chain)
                forwarded[gid] = gname
                logger.info(f"[mrcon] 日志转发 MC→群 [{server_name}] -> {gname}({gid}) {text[:60]}")
            except Exception as e:
                logger.error(f"[mrcon] 日志互通 MC→群 失败 [{gname}({gid})]: {e}")
    if forwarded:
        gnames = ", ".join(f"{n}({g})" for g, n in forwarded.items())
        logger.info(f"[mrcon] 日志互通 MC→群 [{server_name}] {event_type} → {len(forwarded)} 群: {gnames}")
    else:
        logger.debug(f"[mrcon] 日志互通 MC→群 [{server_name}] {event_type} 未转发（无匹配群或日志类型/开关未启用）")


async def _execute_event_macros(plugin, server_name: str, event_type: str, player: str, raw_line: str = "", vip_level: int = 0):
    now = time.time()
    for i, macro in enumerate(plugin._event_macros):
        if not isinstance(macro, dict):
            continue
        if not macro.get("enabled", False):
            continue
        raw_ets = macro.get("event_types", [])
        if not raw_ets or not isinstance(raw_ets, list):
            raw_ets = [macro.get("event_type", "")]
        raw_ets = [et for et in raw_ets if et]
        matched_et = None
        is_str_ets = raw_ets and isinstance(raw_ets[0], str)
        if is_str_ets:
            if event_type not in raw_ets:
                continue
        else:
            for et in raw_ets:
                if isinstance(et, dict) and et.get("type") == event_type:
                    # VIP 等级过滤：宏的 vip_level>0 时仅匹配对应等级
                    et_vip = int(et.get("vip_level", 0) or 0)
                    if et_vip > 0 and et_vip != vip_level:
                        continue
                    matched_et = et
                    break
            if not matched_et:
                continue
        player_filter = (macro.get("player_name", "") or "").strip()
        if player_filter and player_filter != player:
            continue
        event_param = (macro.get("event_param", "") or "").strip()
        if event_param and raw_line and event_param.lower() not in raw_line.lower():
            continue
        conditions = macro.get("conditions", [])
        if conditions and isinstance(conditions, list) and len(conditions) > 0:
            gate_mode = macro.get("gate_mode", "and") or "and"
            cond_results = []
            for cond in conditions:
                if not isinstance(cond, dict):
                    continue
                ct = cond.get("type", "player")
                cv = (cond.get("value", "") or "").strip()
                if not cv:
                    continue
                matched = False
                if ct == "player" and cv == player:
                    matched = True
                elif ct == "content" and raw_line and cv.lower() in raw_line.lower():
                    matched = True
                if cond.get("not", False):
                    matched = not matched
                cond_results.append(matched)
            if gate_mode == "or":
                if cond_results and not any(cond_results):
                    continue
            else:
                if cond_results and not all(cond_results):
                    continue
        cid = str(macro.get("id", str(i)))
        pre_delay = float(matched_et.get("pre_delay", 0) or 0) if matched_et else float(macro.get("delay", 0) or 0)
        post_delay = float(matched_et.get("post_delay", 0) or 0) if matched_et else 0
        per_cmds = matched_et.get("commands", []) if matched_et else []
        if not isinstance(per_cmds, list):
            per_cmds = [str(per_cmds)]
        if pre_delay > 0:
            await asyncio.sleep(pre_delay)
        cooldown = float(macro.get("cooldown", 0) or 0)
        if cid in plugin._event_macro_cooldowns:
            if now < plugin._event_macro_cooldowns[cid]:
                continue
        max_triggers = int(macro.get("max_triggers", 0) or 0)
        trigger_window = int(macro.get("trigger_window", 0) or 0)
        if max_triggers > 0 and trigger_window > 0:
            bucket = plugin._event_macro_freq_buckets.setdefault(cid, [])
            bucket = [t for t in bucket if now - t < trigger_window]
            plugin._event_macro_freq_buckets[cid] = bucket
            if len(bucket) >= max_triggers:
                logger.debug(f"[LogEvent] 宏 '{macro.get('name','?')}' 频率限制已达 {max_triggers}/{trigger_window}s")
                continue
            bucket.append(now)
        target_srv = macro.get("server_name", "")
        cmds = macro.get("commands", [])
        if not isinstance(cmds, list):
            cmds = [str(cmds)]
        srv_conf = None
        bound_gid = None
        for gid, srvs in plugin.group_servers.items():
            for srv in srvs:
                if srv.get("server_name", "") == target_srv:
                    srv_conf = srv
                    bound_gid = str(gid)
                    break
            if srv_conf:
                break
        if not srv_conf:
            logger.debug(f"[LogEvent] 宏 '{macro.get('name','?')}' 目标服务器 '{target_srv}' 未找到")
            continue
        cmds = per_cmds if per_cmds else macro.get("commands", [])
        if not isinstance(cmds, list):
            cmds = [str(cmds)]
        for cmd_entry in cmds:
            if isinstance(cmd_entry, dict):
                cmd = str(cmd_entry.get("cmd", ""))
                cmd_delay = float(cmd_entry.get("delay", 0) or 0)
            else:
                cmd = str(cmd_entry)
                cmd_delay = 0
            if not cmd:
                continue
            if cmd_delay > 0:
                await asyncio.sleep(cmd_delay)
            cmd = cmd.replace("{player}", player).replace("{PLAYER}", player)
            if cmd.strip().lower().startswith("say ") and plugin.event_macro_game_prefix:
                cmd = "say " + plugin.event_macro_game_prefix + " " + cmd[4:].strip()
            try:
                resp = await _rcn_send(plugin,
                    srv_conf["rcon_host"], int(srv_conf["rcon_port"]),
                    srv_conf["rcon_password"], cmd,
                )
                logger.info(f"[LogEvent] 宏 '{macro.get('name','?')}' 执行: {cmd} -> {resp[:80]}")
            except Exception as e:
                logger.warning(f"[LogEvent] 宏 '{macro.get('name','?')}' 失败: {cmd} -> {e}")
        if post_delay > 0:
            await asyncio.sleep(post_delay)
        qq_message = (macro.get("qq_message", "") or "").strip()
        if qq_message and bound_gid:
            qq_msg = (qq_message
                .replace("{player}", player).replace("{PLAYER}", player)
                .replace("{server}", server_name).replace("{SERVER}", server_name)
                .replace("{event_type}", event_type).replace("{EVENT_TYPE}", event_type)
                .replace("{event_param}", macro.get("event_param", "") or ""))
            try:
                umo = _get_group_umo(plugin, bound_gid)
                chain = MessageChain(chain=[Plain(qq_msg)])
                await plugin.context.send_message(umo, chain)
                logger.info(f"[LogEvent] 宏 '{macro.get('name','?')}' QQ通知 → {bound_gid}: {qq_msg[:60]}")
            except Exception as e:
                logger.warning(f"[LogEvent] 宏 '{macro.get('name','?')}' QQ通知失败 ({bound_gid}): {e}")
        if cooldown > 0:
            plugin._event_macro_cooldowns[cid] = now + cooldown
