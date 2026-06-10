import asyncio
import json
import os
import re
import time

from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Plain, At
from astrbot.api import logger

from .utils import strip_mc_color
from .transport import get_pool
from .rcon_executor import rcn_send as _rcn_send


def _get_relay_override(plugin, gid: str) -> dict:
    gid = str(gid)
    ov = plugin._relay_overrides.get(gid)
    if isinstance(ov, list):
        if ov:
            return ov[0]
        ov.append({})
        return ov[0]
    if isinstance(ov, dict):
        return ov
    plugin._relay_overrides[gid] = {}
    return plugin._relay_overrides[gid]


def _save_relay_overrides(plugin):
    try:
        with open(plugin.relay_overrides_path, 'w', encoding='utf-8') as f:
            json.dump(plugin._relay_overrides, f, ensure_ascii=False, indent=2)
        plugin.config.setdefault("relay", {})["group_settings"] = plugin._relay_overrides
        plugin.config.save_config()
    except Exception as e:
        logger.error(f"[mrcon] 保存 relay_overrides 失败: {e}")


def _load_relay_overrides(plugin):
    if os.path.exists(plugin.relay_overrides_path):
        try:
            with open(plugin.relay_overrides_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                combined = {}
                cfg_gs = plugin.config.get("relay", {}).get("group_settings", {})
                if isinstance(cfg_gs, dict):
                    combined.update(cfg_gs)
                combined.update(data)
                plugin._relay_overrides = combined
                logger.info(f"[mrcon] 从 relay_overrides.json 加载了 {len(combined)} 个群的 relay 配置")
                return
        except Exception as e:
            logger.warning(f"[mrcon] 读取 relay_overrides.json 失败: {e}")


def _get_relay_conf(plugin, gid: str):
    override = _get_relay_override(plugin, gid)
    srv_name = override.get("server_name")
    if srv_name:
        srvs = plugin.group_servers.get(str(gid), [])
        for s in srvs:
            if s.get("server_name") == srv_name:
                return s
    return plugin.group_map.get(gid)


def _get_relay_config(plugin, gid: str) -> dict:
    override = _get_relay_override(plugin, gid)
    conf = _get_relay_conf(plugin, gid) or {}
    mode = override.get("mode", "off")
    if mode == "off":
        return {
            "enabled": False, "group_to_mc": False, "mc_to_group": False,
            "mode": "off", "format_group": plugin.relay_fmt_group,
            "format_mc": plugin.relay_fmt_mc,
            "format_mc_log": None,
            "require_msay": False,
            "server_name": None, "_resolved_server": conf.get("server_name") or conf.get("name", "未配置"),
        }
    elif mode == "global":
        return {
            "enabled": plugin.relay_enabled,
            "group_to_mc": plugin.relay_group_to_mc,
            "mc_to_group": plugin.relay_mc_to_group,
            "mode": "global",
            "format_group": plugin.relay_fmt_group,
            "format_mc": plugin.relay_fmt_mc,
            "format_mc_log": getattr(plugin, "relay_fmt_mc_log", None),
            "require_msay": plugin.relay_require_msay,
            "server_name": override.get("server_name"),
            "_resolved_server": conf.get("server_name") or conf.get("name", "未配置"),
        }
    else:
        return {
            "enabled": override.get("enabled", True),
            "group_to_mc": override.get("group_to_mc", plugin.relay_group_to_mc),
            "mc_to_group": override.get("mc_to_group", False),
            "mode": "custom",
            "format_group": override.get("format_group", plugin.relay_fmt_group),
            "format_mc": override.get("format_mc", plugin.relay_fmt_mc),
            "format_mc_log": override.get("format_mc_log", None),
            "require_msay": override.get("require_msay", plugin.relay_require_msay),
            "server_name": override.get("server_name", None),
            "_resolved_server": conf.get("server_name") or conf.get("name", "未配置"),
        }


async def _relay_to_mc(plugin, event: AstrMessageEvent, user_name: str, message: str):
    gid = plugin._get_group_id(event)
    cfg = _get_relay_config(plugin, gid)
    if not cfg["enabled"] or not cfg["group_to_mc"]:
        return
    conf = _get_relay_conf(plugin, gid)
    if not conf:
        return
    try:
        fmt = cfg["format_group"].replace("{name}", user_name).replace("{msg}", message)
        escaped = json.dumps(fmt)
        cmd = f"tellraw @a {escaped}"
        host = conf.get("rcon_host")
        port = conf.get("rcon_port")
        password = conf.get("rcon_password")
        resp = await _rcn_send(host, port, password, cmd)
        svn = conf.get("server_name") or conf.get("name", "")
        plugin._audit_auto("relay", cmd[:200], str(resp)[:200] if resp else "", True,
                           event_type="relay", server_name=svn)
    except Exception as e:
        logger.debug(f"[mrcon] relay to MC failed: {e}")
        plugin._audit_auto("relay", f"tellraw @a [gid={gid}]", str(e)[:200], False,
                           event_type="relay", server_name="")


async def cmd_msay(plugin, event: AstrMessageEvent, text: str = "", rest=None):
    gid = plugin._get_group_id(event)
    cfg = _get_relay_config(plugin, gid)
    if not cfg["enabled"] or not cfg["group_to_mc"]:
        yield event.plain_result("当前群消息互通未开启")
        return
    parts = []
    if isinstance(text, str) and text:
        parts.append(text)
    if isinstance(rest, list):
        parts += [str(r) for r in rest if str(r)]
    elif isinstance(rest, str) and rest:
        parts.append(rest)
    msg = " ".join(parts)
    if not msg:
        yield event.plain_result("用法: /msay <消息内容>")
        return
    user_name = str(event.get_sender_name() or "")
    await _relay_to_mc(plugin, event, user_name, msg)
    yield event.plain_result(f"已发送 → {cfg['_resolved_server']}")


async def _on_mc_chat(plugin, server_name: str, player: str, message: str) -> int:
    count = 0
    candidate_entries: dict[str, list[dict]] = {}
    for gid, entries in list(plugin._relay_overrides.items()):
        gid = str(gid)
        candidate_entries.setdefault(gid, [])
        entry_list = entries if isinstance(entries, list) else ([entries] if isinstance(entries, dict) else [])
        candidate_entries[gid].extend(entry_list)

    # 自动补充 group_servers 中绑定当前服务器但无 relay 配置的群（全局模式）
    if plugin.relay_mc_to_group:
        for gid, srvs in plugin.group_servers.items():
            gid = str(gid)
            if gid in candidate_entries:
                continue
            for srv in (srvs or []):
                if not isinstance(srv, dict):
                    continue
                sn = srv.get("server_name") or srv.get("name", "")
                if sn == server_name:
                    candidate_entries.setdefault(gid, []).append({"mode": "global"})
                    break

    for gid, entry_list in candidate_entries.items():
        gid = str(gid)
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
            if not isinstance(entry, dict):
                continue
            mode = entry.get("mode", "off")
            if mode == "off":
                continue
            if mode == "global":
                if not plugin.relay_mc_to_group:
                    continue
                fmt = plugin.relay_fmt_mc
            elif mode == "custom":
                if not entry.get("mc_to_group"):
                    continue
                fmt = entry.get("format_mc", plugin.relay_fmt_mc)
            else:
                continue
            text = fmt.replace("{player}", player).replace("{msg}", message).replace("{server}", server_name)
            gname = plugin._resolve_group_display_name(gid)
            try:
                umo = plugin._get_group_umo(gid)
                chain = MessageChain(chain=[Plain(text)])
                await plugin.context.send_message(umo, chain)
                count += 1
                plugin._audit_auto("relay", text[:200], f"→{gname}({gid})", True,
                                   event_type="chat", server_name=server_name, group_id=gid)
            except Exception as e:
                logger.error(f"[mrcon] MC→群转发失败 [{gname}({gid})]: {e}")
                plugin._audit_auto("relay", f"MC→群转发失败 [{server_name}]", str(e)[:200], False,
                                   event_type="chat", server_name=server_name, group_id=gid)
    if count == 0:
        logger.debug(f"[mrcon] MC 服 {server_name} 消息无匹配群")
    else:
        logger.info(f"[mrcon] MC 服 {server_name} 消息已分发到 {count} 个群")
    return count


async def cmd_relay(plugin, event: AstrMessageEvent, sub: str = "", val: str = ""):
    if not plugin.is_allowed(event):
        yield event.plain_result("仅管理员可操作")
        return
    gid = str(plugin._get_group_id(event))
    ovr = _get_relay_override(plugin, gid)
    cfg = _get_relay_config(plugin, gid)
    sub = sub.strip().lower()
    val = val.strip()

    if not sub:
        global_srv = plugin.group_map.get(gid, {})
        relay_srv = _get_relay_conf(plugin, gid) or {}
        srv_display = relay_srv.get("server_name") or relay_srv.get("name") or global_srv.get("name") or "未配置"
        mode_label = {"off": "❌ 不互通", "global": "🔵 遵循全局", "custom": "🟢 独立配置"}.get(cfg["mode"], cfg["mode"])
        log_relay_eff = False
        _mode = cfg["mode"]
        if _mode == "global":
            log_relay_eff = plugin.log_listener_enabled
        elif _mode == "custom":
            log_relay_eff = bool(ovr.get("m2g_log_enabled", False))
        log_relay_label = "✅ 开" if log_relay_eff else "❌ 关"
        if _mode == "global" and not log_relay_eff:
            log_relay_label += "（全局未开启）"
        elif _mode == "custom" and not log_relay_eff:
            log_relay_label += "（本群未开启）"
        yield event.plain_result(
            f"📋 本群消息互联配置\n"
            f"  模式: {mode_label}\n"
            f"  群→服转发: {'✅ 开' if cfg['group_to_mc'] else '❌ 关'}\n"
            f"  服→群转发: {'✅ 开' if cfg['mc_to_group'] else '❌ 关'}\n"
            f"  服→群(日志): {log_relay_label}\n"
            f"  仅 /msay: {'✅ 开（只允许命令互通）' if cfg.get('require_msay') else '❌ 关（自动转发群消息）'}\n"
            f"  服→群日志格式: {cfg.get('format_mc_log') or '(同服→群格式)'}\n"
            f"  目标服务器: {srv_display}\n"
            f"  全局默认: 群→服={'✅' if plugin.relay_group_to_mc else '❌'} 服→群={'✅' if plugin.relay_mc_to_group else '❌'} 仅msay={'✅' if plugin.relay_require_msay else '❌'} 日志总闸={'✅' if plugin.relay_mc_to_group_log else '❌'}\n"
            f"\n格式占位: {{name}}=群昵称 {{msg}}=消息内容\n"
            f"\n子命令: 开|关|模式|群到服|服到群|服到群日志|仅msay|格式|日志格式|服|重置\n"
            f"例: /消息互通 模式 custom\n"
            f"    /消息互通 群到服 开\n"
            f"    /消息互通 服到群日志 开\n"
            f"    /消息互通 仅msay 开（开启后只会通过 /msay 命令转发）\n"
            f"    /消息互通 格式 [QQ] {name}: {msg}\n"
            f"    /消息互通 日志格式 [日志] {player}: {msg}\n"
            f"    /消息互通 服 生存一区\n"
            f"    /消息互通 重置"
        )
        return

    if sub == "重置":
        plugin._relay_overrides.pop(gid, None)
        _save_relay_overrides(plugin)
        yield event.plain_result("🔵 已重置为全局默认配置")
        return

    if sub in ("on", "1", "开", "开启", "启用"):
        ovr["mode"] = "custom"
        ovr["enabled"] = True
        ovr["group_to_mc"] = True
        _save_relay_overrides(plugin)
        yield event.plain_result("✅ 本群消息互通已开启（群→服转发已启用，模式: 独立配置）")
        return

    if sub in ("off", "0", "关", "关闭", "禁用"):
        ovr["mode"] = "off"
        _save_relay_overrides(plugin)
        yield event.plain_result("❌ 本群消息互通已关闭（模式: 不互通）")
        return

    if sub == "格式" or sub == "format":
        if not val:
            yield event.plain_result("用法: /消息互通 格式 <文本>  ({name}=群昵称 {msg}=消息)")
            return
        ovr["format_group"] = val
        _save_relay_overrides(plugin)
        yield event.plain_result(f"✅ 转发格式已设为: {val}")
        return

    if sub in ("服", "服务器", "server"):
        srvs = plugin.group_servers.get(gid, [])
        if not srvs:
            yield event.plain_result("当前群未绑定任何服务器，请在 Web 面板「服务器管理」中添加")
            return
        lines = ["📡 本群绑定的服务器（消息互通自动关联）:"]
        for s in srvs:
            sn = s.get("server_name", "")
            lines.append(f"  • {sn}")
        yield event.plain_result("\n".join(lines) + "\n无需手动设置，服务器已自动关联")
        return

    if sub in ("模式", "mode"):
        if val not in ("off", "global", "custom"):
            yield event.plain_result("用法: /消息互通 模式 <off|global|custom>\noff=不互通 global=遵循全局 custom=独立配置")
            return
        ovr["mode"] = val
        _save_relay_overrides(plugin)
        labels = {"off": "❌ 不互通", "global": "🔵 遵循全局", "custom": "🟢 独立配置"}
        yield event.plain_result(f"✅ 消息互通模式已设为: {labels.get(val, val)}")
        return

    if sub in ("群到服", "group_to_mc", "gtm"):
        if val not in ("on", "1", "开", "开启", "启用", "off", "0", "关", "关闭", "禁用"):
            yield event.plain_result("用法: /消息互通 群到服 <开|关>")
            return
        v = val in ("on", "1", "开", "开启", "启用")
        ovr["mode"] = "custom"
        ovr["group_to_mc"] = v
        _save_relay_overrides(plugin)
        yield event.plain_result(f"✅ 群→服转发已{'开启' if v else '关闭'}（模式: 独立配置）")
        return

    if sub in ("服到群", "mc_to_group", "mtg"):
        if val not in ("on", "1", "开", "开启", "启用", "off", "0", "关", "关闭", "禁用"):
            yield event.plain_result("用法: /消息互通 服到群 <开|关>")
            return
        v = val in ("on", "1", "开", "开启", "启用")
        ovr["mode"] = "custom"
        ovr["mc_to_group"] = v
        _save_relay_overrides(plugin)
        yield event.plain_result(f"✅ 服→群转发已{'开启' if v else '关闭'}（模式: 独立配置）")
        return

    if sub in ("服到群日志", "mc_to_group_log", "mtgl"):
        if val not in ("on", "1", "开", "开启", "启用", "off", "0", "关", "关闭", "禁用"):
            yield event.plain_result("用法: /消息互通 服到群日志 <开|关>")
            return
        v = val in ("on", "1", "开", "开启", "启用")
        ovr["mode"] = "custom"
        ovr["m2g_log_enabled"] = v
        _save_relay_overrides(plugin)
        yield event.plain_result(f"✅ 本群服→群日志转发已{'开启' if v else '关闭'}（独立配置，基于日志监听 ~0.5s 延迟）")
        return

    if sub in ("仅msay", "msay_only", "require_msay", "msay"):
        if val not in ("on", "1", "开", "开启", "启用", "off", "0", "关", "关闭", "禁用"):
            yield event.plain_result("用法: /消息互通 仅msay <开|关>\n开启后只会通过 /msay 命令转发消息，不自动转发群消息")
            return
        v = val in ("on", "1", "开", "开启", "启用")
        ovr["mode"] = "custom"
        ovr["require_msay"] = v
        _save_relay_overrides(plugin)
        yield event.plain_result(f"✅ 仅 /msay 命令互通已{'开启' if v else '关闭'}（模式: 独立配置）{' 只有通过 /msay 命令才能发消息到 MC' if v else ' 群内所有消息将自动转发到 MC'}")
        return

    if sub in ("日志格式", "log_format", "fmt_log"):
        if not val:
            yield event.plain_result("用法: /消息互通 日志格式 <文本>  ({player}=玩家名 {msg}=消息 {server}=服名)")
            return
        ovr["mode"] = "custom"
        ovr["format_mc_log"] = val
        _save_relay_overrides(plugin)
        yield event.plain_result(f"✅ 服→群日志转发格式已设为: {val}")
        return

    yield event.plain_result(
        f"未知子命令: {sub}\n"
        f"可用: 开|关|格式|日志格式|服|重置\n"
        f"直接 /消息互通 查看状态"
    )


async def _on_group_message(plugin, event: AstrMessageEvent):
    gid = plugin._get_group_id(event)
    umo = event.unified_msg_origin
    plugin._last_umo[str(gid)] = umo
    if not plugin._umo_prefix and umo:
        idx = umo.rfind(":")
        plugin._umo_prefix = umo[:idx + 1] if idx > 0 else umo + ":"
    async for msg in _flush_pending_msgs(plugin, event):
        yield msg
    cfg = _get_relay_config(plugin, gid)
    if not cfg["enabled"] or not cfg["group_to_mc"]:
        return
    if cfg.get("require_msay", False):
        return
    text = str(getattr(event, "message_str", "") or "")
    if not text or text.startswith("/"):
        return
    user_name = str(event.get_sender_name() or "")
    await _relay_to_mc(plugin, event, user_name, text)


async def _flush_pending_msgs(plugin, event: AstrMessageEvent):
    gid = plugin._get_group_id(event)
    sender = str(event.get_sender_id())
    if plugin.tracker_notify_target == "group":
        msgs = plugin._pending_msgs.pop(str(gid), None)
        if msgs:
            for msg in msgs:
                yield event.plain_result(msg)
    else:
        pass


async def _flush_admin_dm(plugin, event: AstrMessageEvent):
    if plugin.tracker_notify_target != "admin_dm":
        return
    sender = str(event.get_sender_id())
    if not plugin.is_allowed(event):
        return
    for gid in list(plugin._pending_msgs.keys()):
        msgs = plugin._pending_msgs.pop(gid, None)
        if msgs:
            gname = plugin._resolve_group_display_name(gid)
            for msg in msgs:
                yield event.plain_result(f"[{gname}] {msg}")
