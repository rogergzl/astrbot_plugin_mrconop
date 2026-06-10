import asyncio
import json
import os
import re
import time

from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Plain, At
from astrbot.api import logger

from .utils import safe_json_read, safe_json_write, strip_mc_color
from .transport import get_pool, rcon_command_pool
from .rcon_executor import rcn_send as _rcn_send

_PLAYER_NAME_RE = re.compile(r'^[a-zA-Z0-9_]{3,16}$')


def _is_valid_player_name(name: str) -> bool:
    return bool(name and _PLAYER_NAME_RE.match(name))


async def _get_online_player_list(plugin, conf: dict) -> list:
    method = plugin.tracker_method
    if method == "rcon":
        try:
            raw = await _rcn_send(
                conf["rcon_host"], conf["rcon_port"], conf["rcon_password"], "list"
            )
            if ":" in raw:
                names_part = raw.split(":", 1)[1].strip()
                return [n.strip() for n in names_part.split(",") if n.strip()]
        except Exception:
            pass
    elif method == "mcstatus":
        try:
            st = await plugin._get_mc_server_status(conf["rcon_host"], str(conf.get("game_port", 25565)))
            if st["online"]:
                return st["players"]
        except Exception:
            pass
    return []


def _load_tracker_overrides(plugin) -> dict:
    fpath = os.path.join(plugin.plugin_data_dir, "tracker_overrides.json")
    plugin._tracker_overrides_file = fpath
    if os.path.exists(fpath):
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                logger.info(f"[mrcon] 从文件加载群追踪覆盖: {len(data)} 个群")
                return data
        except Exception as e:
            logger.warning(f"[mrcon] 读取tracker_overrides.json失败: {e}")
    tracker_cfg = plugin.config.get("online_tracker", {})
    data = tracker_cfg.get("group_overrides", {}) if isinstance(tracker_cfg, dict) else {}
    if data:
        logger.info(f"[mrcon] 从config加载群追踪覆盖: {len(data)} 个群，将迁移至JSON文件")
        plugin._tracker_overrides = data
        _save_tracker_overrides(plugin)
        try:
            tracker_cfg.pop("group_overrides", None)
            plugin.config["online_tracker"] = tracker_cfg
            plugin.config.save_config()
            logger.info("[mrcon] 已清除config.yaml中的旧group_overrides")
        except Exception:
            pass
    return data


def _save_tracker_overrides(plugin):
    ov = getattr(plugin, '_tracker_overrides', {})
    if not isinstance(ov, dict):
        ov = {}
    try:
        fpath = getattr(plugin, '_tracker_overrides_file', None)
        if fpath:
            os.makedirs(os.path.dirname(fpath), exist_ok=True)
            with open(fpath, 'w', encoding='utf-8') as f:
                json.dump(ov, f, ensure_ascii=False, indent=2)
            logger.debug(f"[mrcon] tracker覆盖已保存到文件: {len(ov)} 个群")
    except Exception as e:
        logger.warning(f"[mrcon] 保存tracker覆盖到文件失败: {e}")
    try:
        plugin.config.setdefault("online_tracker", {})["group_overrides"] = ov
        plugin.config.save_config()
    except Exception as e:
        logger.debug(f"[mrcon] tracker覆盖config写入: {e}")


def _load_general_overrides(plugin) -> dict:
    fpath = os.path.join(plugin.plugin_data_dir, "general_overrides.json")
    plugin._general_overrides_file = fpath
    if os.path.exists(fpath):
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                logger.info(f"[mrcon] 从文件加载通用覆盖: {list(data.keys())}")
                return data
        except Exception as e:
            logger.warning(f"[mrcon] 读取general_overrides.json失败: {e}")
    return {}


def _save_general_overrides(plugin):
    gc = plugin.config.get("general", {}) if isinstance(plugin.config.get("general", {}), dict) else {}
    keys_to_save = ["event_macro_game_prefix", "game_notify_prefix"]
    data = {k: gc.get(k, "") for k in keys_to_save}
    try:
        fpath = getattr(plugin, '_general_overrides_file', None)
        if fpath:
            os.makedirs(os.path.dirname(fpath), exist_ok=True)
            with open(fpath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"[mrcon] 通用覆盖已保存到文件")
    except Exception as e:
        logger.warning(f"[mrcon] 保存通用覆盖失败: {e}")


def _save_event_macros_json(plugin):
    fpath = os.path.join(plugin.plugin_data_dir, "event_macros.json")
    try:
        os.makedirs(plugin.plugin_data_dir, exist_ok=True)
        with open(fpath, 'w', encoding='utf-8') as f:
            json.dump(plugin._event_macros, f, ensure_ascii=False, indent=2)
        logger.debug(f"[mrcon] 事件宏已保存到 event_macros.json")
    except Exception as e:
        logger.warning(f"[mrcon] 保存事件宏 JSON 失败: {e}")


def _load_event_macros_json(plugin):
    fpath = os.path.join(plugin.plugin_data_dir, "event_macros.json")
    if os.path.exists(fpath):
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                logger.info(f"[mrcon] 从 event_macros.json 加载了 {len(data)} 个事件宏")
                return data
        except Exception as e:
            logger.warning(f"[mrcon] 读取 event_macros.json 失败: {e}")
    return None


def _load_server_log_configs(plugin):
    fpath = os.path.join(plugin.plugin_data_dir, "server_log_configs.json")
    plugin._server_log_configs_file = fpath
    if os.path.exists(fpath):
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict) or not data:
                return
            restored = 0
            for gid, srvs in plugin.group_servers.items():
                for s in srvs:
                    sn = s.get("name", s.get("server_name", ""))
                    if sn in data:
                        lc = data[sn]
                        for key in ("log_path", "log_mode", "log_paths", "log_folder", "log_file_pattern"):
                            if key in lc:
                                s[key] = lc[key]
                        restored += 1
            if restored:
                logger.info(f"[mrcon] 从文件恢复了 {restored} 台服务器日志配置")
        except Exception as e:
            logger.warning(f"[mrcon] 读取server_log_configs.json失败: {e}")


def _save_server_log_configs(plugin):
    data = {}
    for gid, srvs in plugin.group_servers.items():
        for s in srvs:
            sn = s.get("name", s.get("server_name", ""))
            if not sn:
                continue
            entry = {}
            for key in ("log_path", "log_mode", "log_paths", "log_folder", "log_file_pattern"):
                val = s.get(key)
                if val:
                    entry[key] = val
            if entry:
                data[sn] = entry
    if not data:
        return
    try:
        fpath = getattr(plugin, '_server_log_configs_file', None)
        if not fpath:
            fpath = os.path.join(plugin.plugin_data_dir, "server_log_configs.json")
            plugin._server_log_configs_file = fpath
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        with open(fpath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.debug(f"[mrcon] 服务器日志配置已保存到文件: {len(data)} 台")
    except Exception as e:
        logger.warning(f"[mrcon] 保存服务器日志配置失败: {e}")


def _load_ranking_state(plugin):
    """加载持久化的排行状态（_last_ranking_reset 时间戳）"""
    fpath = os.path.join(plugin.plugin_data_dir, "ranking_state.json")
    if os.path.exists(fpath):
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                plugin._last_ranking_reset = int(data.get("last_ranking_reset", 0))
                logger.info(f"[mrcon] 已加载排行状态: last_reset={plugin._last_ranking_reset}")
        except Exception as e:
            logger.warning(f"[mrcon] 加载 ranking_state.json 失败: {e}")


def _save_ranking_state(plugin):
    """持久化排行状态"""
    fpath = os.path.join(plugin.plugin_data_dir, "ranking_state.json")
    try:
        os.makedirs(plugin.plugin_data_dir, exist_ok=True)
        data = {"last_ranking_reset": plugin._last_ranking_reset}
        with open(fpath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"[mrcon] 保存 ranking_state.json 失败: {e}")


def _cleanup_old_ranking_data(plugin, now: int):
    """清理超出单次记录时长的旧排行数据"""
    if plugin.ranking_reset_hours > 0:
        cutoff = now - plugin.ranking_reset_hours * 3600
        try:
            deleted = plugin.db.delete_online_sessions_before(cutoff)
            if deleted > 0:
                logger.info(f"[mrcon] 已清理 {deleted} 条超出 {plugin.ranking_reset_hours} 小时的旧排行记录")
        except Exception as e:
            logger.error(f"[mrcon] 清理旧排行数据失败: {e}")


def _expand_placeholders(template: str, player: str, session_mins: int, ban_mins: int, reason: str = "") -> str:
    """统一占位符替换，踢出原因和封禁命令共用。
    
    占位符:
        {player}  - 玩家名
        {hours}   - 已在线整小时 (session_mins // 60)
        {minutes} - 封禁时长分钟数 (ban_mins)
        {reason}  - 已展开的踢出原因文本 (用于封禁命令嵌入)
    """
    return (template
        .replace("{player}", player)
        .replace("{hours}", str(session_mins // 60))
        .replace("{minutes}", str(ban_mins))
        .replace("{reason}", reason))


def _get_tracker_config(plugin, gid: str) -> dict:
    override = plugin._tracker_overrides.get(str(gid), {})
    if override.get("use_global"):
        override = {}
    return {
        "notify": override.get("notify_enabled", plugin.tracker_notify),
        "notify_target": override.get("notify_target", plugin.tracker_notify_target),
        "notify_intervals": override.get("notify_intervals", plugin.tracker_notify_intervals),
        "notify_game": override.get("notify_in_game", plugin.tracker_notify_game),
        "notify_game_format": override.get("notify_game_format", plugin.tracker_game_format),
        "notify_game_prefix": override.get("notify_game_prefix", plugin.tracker_game_prefix),
        "notify_mention_mode": override.get("notify_mention_mode", plugin.tracker_notify_mention_mode),
        "notify_mention_format": override.get("notify_mention_format", plugin.tracker_notify_mention_format),
        "kick_enabled": override.get("kick_enabled", plugin.tracker_kick_enabled),
        "kick_threshold": override.get("kick_threshold", plugin.tracker_kick_threshold),
        "kick_reason": override.get("kick_reason", plugin.tracker_kick_reason),
        "ban_minutes": override.get("ban_minutes", plugin.tracker_ban_minutes),
        "ban_cmd": override.get("ban_cmd", plugin.tracker_ban_cmd),
        "duration_mode": override.get("duration_mode", plugin.tracker_duration_mode),
    }


async def _send_tracker_notify(plugin, gid: str, srv_name: str, player: str,
                                dur_label: str, dur_text: str, tcfg: dict,
                                is_kick: bool = False, error_msg: str = ""):
    mention_mode = tcfg.get("notify_mention_mode", "player")
    mention_fmt = tcfg.get("notify_mention_format", "@{qq} {player} 你已{dur_label}在线 {duration}")

    qq_id = ""
    try:
        row = plugin.db.find_player_by_mc_id(player)
        if row:
            qq_id = str(row.get("qq_id", ""))
    except Exception:
        pass

    admin_qqs = list(plugin.admin_qqs) if hasattr(plugin, 'admin_qqs') and plugin.admin_qqs else []

    if is_kick:
        if error_msg:
            base_text = f"⚠️ {player} 超时需踢出但执行失败 [{srv_name}]: {error_msg}"
        else:
            base_text = f"🚫 {player} {dur_label}在线超过 {dur_text}，已被自动踢出 [{srv_name}]"
    else:
        base_text = f"⏰ {player} 已在 [{srv_name}] {dur_label}在线 {dur_text}"

    try:
        umo = plugin._get_group_umo(gid)
    except Exception:
        logger.warning(f"[mrcon] 无法获取群 {gid} 的 UMO，跳过通知")
        return

    if mention_mode == "player" and qq_id:
        try:
            chain = MessageChain(chain=[
                At(qq=int(qq_id)),
                Plain(f" {base_text}")
            ])
            await plugin.context.send_message(umo, chain)
        except Exception as e:
            logger.error(f"[mrcon] @玩家通知失败: {e}，降级为纯文本")
            chain = MessageChain(chain=[Plain(base_text)])
            await plugin.context.send_message(umo, chain)

    elif mention_mode == "admin" and admin_qqs:
        chain_parts = []
        for aq in admin_qqs:
            try:
                chain_parts.append(At(qq=int(aq)))
            except Exception:
                pass
        chain_parts.append(Plain(f" {base_text}"))
        try:
            chain = MessageChain(chain=chain_parts)
            await plugin.context.send_message(umo, chain)
        except Exception as e:
            logger.error(f"[mrcon] @管理员通知失败: {e}")
            chain = MessageChain(chain=[Plain(base_text)])
            await plugin.context.send_message(umo, chain)

    elif mention_mode == "custom" and mention_fmt:
        custom_text = mention_fmt.replace("{qq}", qq_id)\
            .replace("{player}", player)\
            .replace("{mc_id}", player)\
            .replace("{duration}", dur_text)\
            .replace("{dur_label}", dur_label)\
            .replace("{server}", srv_name)
        if "@{" in custom_text and qq_id:
            import re
            parts = []
            last_idx = 0
            for m in re.finditer(r'@\{(\w+)\}', custom_text):
                parts.append(Plain(custom_text[last_idx:m.start()]))
                var_name = m.group(1)
                if var_name == "qq" and qq_id:
                    try:
                        parts.append(At(qq=int(qq_id)))
                    except Exception:
                        parts.append(Plain(f"@{qq_id}"))
                elif var_name == "admin" and admin_qqs:
                    for aq in admin_qqs:
                        try:
                            parts.append(At(qq=int(aq)))
                        except Exception:
                            pass
                else:
                    parts.append(Plain(m.group(0)))
                last_idx = m.end()
            parts.append(Plain(custom_text[last_idx:]))
            parts = [p for p in parts if not (isinstance(p, Plain) and not p.text)]
            chain = MessageChain(chain=parts)
        else:
            chain = MessageChain(chain=[Plain(custom_text)])
        try:
            await plugin.context.send_message(umo, chain)
        except Exception as e:
            logger.error(f"[mrcon] 自定义格式通知失败: {e}")

    else:
        chain = MessageChain(chain=[Plain(base_text)])
        await plugin.context.send_message(umo, chain)


async def _online_tracker_loop(plugin):
    logger.info("[mrcon] 在线时长监控已启动")
    while True:
        try:
            if plugin.tracker_poll_mode == "smart":
                interval = plugin.tracker_active_interval if plugin._online_cache else plugin.tracker_idle_interval
            else:
                interval = plugin.tracker_interval
            await asyncio.sleep(max(10, interval))
            now = int(time.time())
            all_servers = []
            for gid, srvs in plugin.group_servers.items():
                for srv in srvs:
                    all_servers.append((gid, srv))
            for gid, conf in all_servers:
                if not conf.get("query_enabled", True):
                    continue
                tcfg = _get_tracker_config(plugin, gid)
                online = await _get_online_player_list(plugin, conf)
                srv_name = conf.get("server_name", "unknown")
                for player in online:
                    sid = f"{srv_name}:{player}"
                    if sid not in plugin._online_cache:
                        cache_entry = {
                            "login_at": now, "player": player, "server": srv_name,
                            "gid": gid, "notified": set(), "kicked": False,
                        }
                        init_mins = 0
                        if tcfg.get("duration_mode", "session") == "cumulative":
                            total_secs = plugin.db.get_player_total_seconds(player, plugin.ranking_reset_hours)
                            init_mins += total_secs // 60
                        if tcfg["notify"]:
                            for threshold in tcfg["notify_intervals"]:
                                if init_mins >= threshold:
                                    cache_entry["notified"].add(threshold)
                        plugin._online_cache[sid] = cache_entry
                        try:
                            plugin.db.save_online_state(srv_name, player, str(gid), now)
                        except Exception:
                            pass
                        try:
                            existing = plugin.db.find_player_by_mc_id(player)
                            if not existing:
                                if _is_valid_player_name(player):
                                    plugin.db.insert_player_raw("_imported_" + player, player, 50, now)
                        except Exception:
                            pass
                        await plugin._check_online_triggers(player, srv_name, str(gid), conf, now)
                    cache = plugin._online_cache[sid]
                    session_mins = (now - cache["login_at"]) // 60
                    duration_mode = tcfg.get("duration_mode", "session")
                    if duration_mode == "cumulative":
                        total_secs = plugin.db.get_player_total_seconds(player, plugin.ranking_reset_hours)
                        session_mins += total_secs // 60
                    dur_label = "累计" if duration_mode == "cumulative" else "连续"
                    if tcfg["notify"]:
                        intervals = sorted(tcfg["notify_intervals"], reverse=True)
                        for threshold in intervals:
                            if session_mins >= threshold and threshold not in cache["notified"]:
                                cache["notified"].add(threshold)
                                h = threshold // 60
                                m = threshold % 60
                                if h > 0:
                                    dur_text = f"{h}时{m}分" if m else f"{h}小时"
                                else:
                                    dur_text = f"{m}分钟"
                                await _send_tracker_notify(
                                    plugin, str(gid), srv_name, player, dur_label, dur_text,
                                    tcfg, is_kick=False
                                )
                                if tcfg["notify_game"]:
                                    prefix = tcfg.get("notify_game_prefix", plugin.tracker_game_prefix)
                                    game_msg = tcfg["notify_game_format"].replace("{player}", player).replace("{duration}", dur_text)
                                    try:
                                        game_cmd = f"say {prefix} {game_msg}"
                                        await _rcn_send(
                                            conf["rcon_host"], conf["rcon_port"],
                                            conf["rcon_password"], game_cmd,
                                        )
                                        plugin._audit_auto("game_notify", game_cmd[:200], "", True,
                                                         event_type="game_notify", server_name=srv_name)
                                    except Exception as e:
                                        logger.error(f"[mrcon] 游戏内提醒失败: {e}")
                                        plugin._audit_auto("game_notify", game_cmd[:200], str(e)[:200], False,
                                                         event_type="game_notify", server_name=srv_name)
                    if tcfg["kick_enabled"] and not cache["kicked"] and session_mins >= tcfg["kick_threshold"]:
                        cache["kicked"] = True
                        ban_mins = tcfg["ban_minutes"]
                        reason = _expand_placeholders(tcfg["kick_reason"], player, session_mins, ban_mins)
                        kick_cmd = f"kick {player} {reason}"
                        try:
                            await _rcn_send(
                                conf["rcon_host"], conf["rcon_port"],
                                conf["rcon_password"], kick_cmd,
                            )
                            logger.info(f"[mrcon] 自动踢出 {player} @ {srv_name}: {reason}")
                            await _send_tracker_notify(
                                plugin, str(gid), srv_name, player, dur_label, f"{tcfg['kick_threshold']}分钟",
                                tcfg, is_kick=True
                            )
                            plugin._audit_web("auto_kick", f"玩家 {player} 在 {srv_name} 因在线过久({tcfg['kick_threshold']}分钟)被自动踢出，原因: {reason}", True, "在线追踪")
                            if ban_mins > 0:
                                ban_cmd_tpl = tcfg.get("ban_cmd", "tempban {player} {minutes}m {reason}")
                                ban_cmd = _expand_placeholders(ban_cmd_tpl, player, session_mins, ban_mins, reason)
                                await _rcn_send(
                                    conf["rcon_host"], conf["rcon_port"],
                                    conf["rcon_password"], ban_cmd,
                                )
                                plugin._audit_web("auto_ban", f"玩家 {player} 在 {srv_name} 被自动封禁 {ban_mins} 分钟，命令: {ban_cmd}", True, "在线追踪")
                        except Exception as e:
                            logger.error(f"[mrcon] 自动踢出失败: {e}")
                            await _send_tracker_notify(
                                plugin, str(gid), srv_name, player, dur_label, f"{tcfg['kick_threshold']}分钟",
                                tcfg, is_kick=True, error_msg=str(e)
                            )
                            plugin._audit_web("auto_kick", f"玩家 {player} 在 {srv_name} 踢出失败: {e}", False, "在线追踪")
                if plugin._event_macros:
                    for macro in plugin._event_macros:
                        if not macro.get("enabled", False):
                            continue
                        event_types = macro.get("event_types") or []
                        if isinstance(event_types, list) and event_types and isinstance(event_types[0], str):
                            event_types = [{"type": et} for et in event_types if et]
                        for et in event_types:
                            if not isinstance(et, dict):
                                continue
                            if et.get("type", "").strip() != "player_online_duration":
                                continue
                            dur_min = int(et.get("duration_minutes", 0) or 0)
                            if dur_min <= 0:
                                continue
                            dur_mode = str(et.get("duration_mode", "session") or "session")
                            macro_id = macro.get("id", "") or macro.get("name", "unknown")
                            for sid, cache in list(plugin._online_cache.items()):
                                if cache["server"] != srv_name:
                                    continue
                                player_name = cache["player"]
                                spec_player = str(macro.get("player_name", "") or "").strip()
                                if spec_player and player_name.lower() != spec_player.lower():
                                    continue
                                trigger_key = f"{macro_id}:{srv_name}:{player_name}"
                                if trigger_key in plugin._online_duration_triggered:
                                    continue
                                now_ts = int(time.time())
                                session_mins_t = (now_ts - cache["login_at"]) // 60
                                total_mins = session_mins_t
                                if dur_mode == "cumulative":
                                    total_secs = plugin.db.get_player_total_seconds(player_name, plugin.ranking_reset_hours)
                                    total_mins += total_secs // 60
                                if total_mins >= dur_min:
                                    plugin._online_duration_triggered[trigger_key] = True
                                    pre_delay = float(et.get("pre_delay", 0) or 0)
                                    per_cmds = et.get("commands", [])
                                    cmds = per_cmds if per_cmds else macro.get("commands", [])
                                    if not isinstance(cmds, list):
                                        cmds = [str(cmds)]
                                    # 查DB获取绑定信息
                                    player_rec = plugin.db.find_player_by_mc_id(player_name) if plugin.pdb_enabled else None
                                    _mc_id = player_rec.get("mc_id", player_name) if player_rec else player_name
                                    _qq_id = str(player_rec.get("qq_id", "")) if player_rec else ""
                                    if pre_delay > 0:
                                        await asyncio.sleep(pre_delay)
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
                                        cmd = cmd.replace("{player}", player_name).replace("{PLAYER}", player_name).replace("{mc_id}", _mc_id).replace("{qq}", _qq_id)
                                        cmd_lower = cmd.strip().lower()
                                        if plugin.event_macro_game_prefix:
                                            if cmd_lower.startswith("say "):
                                                msg = cmd[4:].strip()
                                                cmd = f'tellraw @a {json.dumps(plugin.event_macro_game_prefix + " " + msg)}'
                                            elif cmd_lower.startswith("tell ") or cmd_lower.startswith("msg "):
                                                parts = cmd.strip().split(" ", 2)
                                                if len(parts) >= 3:
                                                    target = parts[1]
                                                    msg = parts[2]
                                                    cmd = f'tellraw {target} {json.dumps(plugin.event_macro_game_prefix + " " + msg)}'
                                        try:
                                            resp = await _rcn_send(
                                                conf["rcon_host"], int(conf["rcon_port"]),
                                                conf["rcon_password"], cmd,
                                            )
                                            logger.info(f"[OnlineDur] 宏 '{macro.get('name','?')}' 触发: {player_name}({total_mins}min) -> {cmd} -> {resp[:80]}")
                                            plugin._audit_auto("online_duration_macro", cmd, str(resp)[:500], True,
                                                             event_type="player_online_duration", server_name=srv_name)
                                        except Exception as e:
                                            logger.warning(f"[OnlineDur] 宏 '{macro.get('name','?')}' 失败: {cmd} -> {e}")
                                            plugin._audit_auto("online_duration_macro", cmd, str(e)[:500], False,
                                                             event_type="player_online_duration", server_name=srv_name)
                                    qq_msg = (macro.get("qq_message") or "").strip()
                                    if qq_msg:
                                        qq_msg = qq_msg.replace("{player}", player_name).replace("{server}", srv_name).replace("{mc_id}", _mc_id).replace("{qq}", _qq_id)
                                        qq_msg = qq_msg.replace("{event_type}", "player_online_duration")
                                        try:
                                            await plugin._send_group_message(str(gid), qq_msg)
                                        except Exception as e:
                                            logger.warning(f"[OnlineDur] QQ通知失败: {e}")
                for sid in list(plugin._online_cache.keys()):
                    s = plugin._online_cache[sid]
                    if s["server"] == srv_name and s["player"] not in online:
                        plugin.db.add_online_session(srv_name, s["player"], s["login_at"], now)
                        try:
                            plugin.db.remove_online_state(srv_name, s["player"])
                        except Exception:
                            pass
                        del plugin._online_cache[sid]
                        to_remove = [k for k in plugin._online_duration_triggered if k.endswith(f":{srv_name}:{s['player']}")]
                        for k in to_remove:
                            del plugin._online_duration_triggered[k]
            if plugin.ranking_reset_hours > 0:
                last = plugin._last_ranking_reset
                if last == 0:
                    plugin._last_ranking_reset = now
                    # 首次启动时，立即清理超出记录时长的旧数据
                    _cleanup_old_ranking_data(plugin, now)
                    _save_ranking_state(plugin)
                elif (now - last) >= plugin.ranking_reset_hours * 3600:
                    _cleanup_old_ranking_data(plugin, now)
                    plugin._last_ranking_reset = now
                    _save_ranking_state(plugin)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[mrcon] 在线监控错误: {e}")


async def cmd_tracker_set(plugin, event: AstrMessageEvent, sub: str = "", val1: str = "", val2: str = ""):
    if not plugin.is_allowed(event):
        yield event.plain_result("仅管理员可配置")
        return
    gid = str(plugin._get_group_id(event))
    if not gid:
        yield event.plain_result("请在群内使用此命令")
        return
    ovr = plugin._tracker_overrides.setdefault(gid, {})
    sub = sub.strip()
    val1 = val1.strip()
    val2 = val2.strip()
    gcfg = _get_tracker_config(plugin, gid)

    if not sub:
        ni = gcfg["notify_intervals"]
        gf = gcfg.get("notify_game_format", "")
        dm = gcfg.get("duration_mode", "session")
        dm_label = "累计在线" if dm == "cumulative" else "单次连续在线"
        mm = gcfg.get("notify_mention_mode", "player")
        mm_label = {"player": "@绑定玩家", "text": "纯文本", "admin": "@管理员", "custom": "自定义格式"}.get(mm, mm)
        mf = gcfg.get("notify_mention_format", "@{qq} {player} 你已{dur_label}在线 {duration}")
        yield event.plain_result(
            f"📋 本群在线提醒配置\n"
            f"  提醒开关: {'✅ 开' if gcfg['notify'] else '❌ 关'}\n"
            f"  提醒目标: {gcfg['notify_target']}\n"
            f"  @模式: {mm_label}\n"
            f"  @格式: {mf}\n"
            f"  提醒节点: {ni} (分钟)\n"
            f"  游戏提醒: {'✅ 开' if gcfg.get('notify_game') else '❌ 关'}\n"
            f"  游戏格式: {gf}\n"
            f"  踢出开关: {'✅ 开' if gcfg['kick_enabled'] else '❌ 关'}\n"
            f"  踢出阈值: {gcfg['kick_threshold']} 分钟\n"
            f"  踢出封禁: {gcfg.get('ban_minutes', 0)} 分钟\n"
            f"  封禁命令: {gcfg.get('ban_cmd', 'tempban {player} {minutes}m {reason}')}\n"
            f"  踢出原因: {gcfg['kick_reason']}\n"
            f"  时长模式: {dm_label}\n"
            f"  {'🟢 使用全局' if ovr.get('use_global') else '🟢 群内覆盖' if ovr else '🔵 沿用全局默认'}\n"
            f"\n游戏格式占位: {{player}}=玩家名 {{duration}}=时长\n"
            f"@格式占位: {{qq}}=QQ号 {{player}}=玩家名 {{mc_id}}=MC ID {{duration}}=时长 {{dur_label}}=在线类型 {{server}}=服务器\n"
            f"@模式: player=@绑定玩家 text=纯文本 admin=@管理员 custom=自定义格式\n"
            f"MC颜色码: §a绿 §b青 §c红 §e黄 §l粗体 §n下划线\n"
            f"\n快速: /在线提醒 开,游戏提醒=开,踢出=开,阈值=720,封禁=30,模式=累计,@模式=player\n"
            f"分步: 开|关|节点|目标|游戏提醒|游戏格式|踢出|封禁|模式|@模式|@格式|重置"
        )
        return

    ovr["use_global"] = False

    if "," in sub or "=" in sub:
        raw = str(getattr(event, "message_str", "") or "").strip()
        idx = raw.find(sub)
        bulk = raw[idx:] if idx >= 0 else sub
        parts = bulk.split(",") if "," in bulk else [bulk]
        updated = []
        for p in parts:
            p = p.strip()
            if not p:
                continue
            if "=" in p:
                k, v = p.split("=", 1)
                k, v = k.strip(), v.strip()
                if k == "开" or k == "关":
                    ovr["notify_enabled"] = (k == "开")
                elif k == "目标":
                    if v in ("group", "admin_dm"): ovr["notify_target"] = v
                elif k == "节点":
                    try:
                        ovr["notify_intervals"] = sorted([int(x.strip()) for x in v.split(",") if x.strip()], reverse=True)
                    except ValueError:
                        pass
                elif k == "游戏提醒":
                    ovr["notify_in_game"] = v.lower() in ("开", "1", "true", "yes")
                elif k == "游戏格式":
                    ovr["notify_game_format"] = v
                elif k == "踢出":
                    ovr["kick_enabled"] = v.lower() in ("开", "1", "true", "yes")
                elif k == "阈值":
                    try: ovr["kick_threshold"] = int(v)
                    except ValueError: pass
                elif k == "封禁":
                    try: ovr["ban_minutes"] = int(v)
                    except ValueError: pass
                elif k == "封禁命令":
                    ovr["ban_cmd"] = v
                elif k == "原因":
                    ovr["kick_reason"] = v
                elif k == "模式":
                    if v in ("session", "cumulative", "连续", "累计"):
                        ovr["duration_mode"] = "cumulative" if v in ("cumulative", "累计") else "session"
                elif k == "@模式":
                    if v in ("player", "text", "admin", "custom"):
                        ovr["notify_mention_mode"] = v
                elif k == "@格式":
                    ovr["notify_mention_format"] = v
                updated.append(f"{k}={v}")
            else:
                if p == "开":
                    ovr["notify_enabled"] = True
                    updated.append("开")
                elif p == "关":
                    ovr["notify_enabled"] = False
                    updated.append("关")
                elif p == "重置":
                    plugin._tracker_overrides.pop(gid, None)
                    _save_tracker_overrides(plugin)
                    yield event.plain_result("🔵 已重置为全局默认配置")
                    return
        _save_tracker_overrides(plugin)
        yield event.plain_result(f"✅ 已更新: {', '.join(updated) if updated else '(无变更)'}")
        return

    if sub == "重置":
        plugin._tracker_overrides.pop(gid, None)
        _save_tracker_overrides(plugin)
        yield event.plain_result("🔵 已重置为全局默认配置")
        return

    if sub in ("开", "关"):
        ovr["notify_enabled"] = (sub == "开")
        _save_tracker_overrides(plugin)
        yield event.plain_result(f"✅ 本群在线提醒已{'开启' if sub == '开' else '关闭'}")
        return

    if sub == "节点":
        if not val1:
            yield event.plain_result("用法: /在线提醒 节点 <60,120,360>")
            return
        try:
            intervals = sorted([int(x.strip()) for x in val1.split(",") if x.strip()], reverse=True)
            if not intervals:
                raise ValueError
            ovr["notify_intervals"] = intervals
            _save_tracker_overrides(plugin)
            yield event.plain_result(f"✅ 提醒节点已设为: {intervals} 分钟")
        except ValueError:
            yield event.plain_result("节点格式错误，例: /在线提醒 节点 60,120,360")
        return

    if sub == "目标":
        if val1 not in ("group", "admin_dm"):
            yield event.plain_result("目标应为 group 或 admin_dm")
            return
        ovr["notify_target"] = val1
        _save_tracker_overrides(plugin)
        yield event.plain_result(f"✅ 提醒目标已设为: {val1}")
        return

    if sub == "游戏提醒":
        if val1.lower() in ("开", "1", "true", "yes"):
            ovr["notify_in_game"] = True
            _save_tracker_overrides(plugin)
            yield event.plain_result("✅ 游戏内提醒已开启")
        elif val1.lower() in ("关", "0", "false", "no"):
            ovr["notify_in_game"] = False
            _save_tracker_overrides(plugin)
            yield event.plain_result("✅ 游戏内提醒已关闭")
        else:
            yield event.plain_result("用法: /在线提醒 游戏提醒 开|关")
        return

    if sub == "游戏格式":
        raw = str(getattr(event, "message_str", "") or "").strip()
        idx = raw.find("游戏格式")
        if idx >= 0:
            fmt = raw[idx + 4:].strip()
            if fmt:
                ovr["notify_game_format"] = fmt
                _save_tracker_overrides(plugin)
                yield event.plain_result("✅ 游戏内提醒格式已更新")
                return
        yield event.plain_result("用法: /在线提醒 游戏格式 <文案>  ({player}=玩家 {duration}=时长)")
        return

    if sub == "封禁":
        try:
            ovr["ban_minutes"] = int(val1)
            if val2:
                ovr["ban_cmd"] = val2
            _save_tracker_overrides(plugin)
            yield event.plain_result(f"✅ 踢出后封禁时长已设为 {val1} 分钟（0=不封禁）\n命令模板: {ovr.get('ban_cmd', 'tempban {player} {minutes}m {reason}')}")
        except ValueError:
            yield event.plain_result("封禁时长应为数字（分钟），0=不封禁，可选第二个参数为命令模板")
        return

    if sub == "踢出":
        if val1 == "开":
            ovr["kick_enabled"] = True
            if val2:
                try:
                    ovr["kick_threshold"] = int(val2)
                except ValueError:
                    yield event.plain_result("踢出阈值应为数字（分钟）")
                    return
            _save_tracker_overrides(plugin)
            yield event.plain_result(f"✅ 踢出已开启（阈值 {ovr.get('kick_threshold', gcfg['kick_threshold'])} 分钟）")
        elif val1 == "关":
            ovr["kick_enabled"] = False
            _save_tracker_overrides(plugin)
            yield event.plain_result("✅ 踢出已关闭")
        elif val1 == "原因":
            raw = str(getattr(event, "message_str", "") or "").strip()
            for needle in ("踢出 原因 ", "踢出 原因"):
                idx = raw.find(needle)
                if idx >= 0:
                    reason = raw[idx + len(needle):].strip()
                    if reason:
                        ovr["kick_reason"] = reason
                        _save_tracker_overrides(plugin)
                        yield event.plain_result("✅ 踢出原因已更新")
                        return
            yield event.plain_result("用法: /在线提醒 踢出 原因 <文本>")
            return
        else:
            yield event.plain_result("用法: /在线提醒 踢出 开 [阈值] | 踢出 关 | 踢出 原因 <文本>")
        return

    if sub == "@模式":
        if val1 not in ("player", "text", "admin", "custom"):
            yield event.plain_result("用法: /在线提醒 @模式 <player|text|admin|custom>\nplayer=@绑定玩家 text=纯文本 admin=@管理员 custom=自定义格式")
            return
        ovr["notify_mention_mode"] = val1
        _save_tracker_overrides(plugin)
        yield event.plain_result(f"✅ @模式已设为: {val1}")
        return

    if sub == "@格式":
        raw = str(getattr(event, "message_str", "") or "").strip()
        idx = raw.find("@格式")
        if idx >= 0:
            fmt = raw[idx + 3:].strip()
            if fmt:
                ovr["notify_mention_format"] = fmt
                _save_tracker_overrides(plugin)
                yield event.plain_result(f"✅ @自定义格式已更新\n占位: {qq} {player} {mc_id} {duration} {dur_label} {server}")
                return
        yield event.plain_result("用法: /在线提醒 @格式 <文案>  ({qq}=QQ {player}=玩家 {duration}=时长 {server}=服务器)")
        return

    yield event.plain_result("未知子命令。可用: 开|关|节点|目标|游戏提醒|游戏格式|踢出|封禁|模式|@模式|@格式|重置")
