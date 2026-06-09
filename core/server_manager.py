import asyncio
import json
import os
import time

from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Plain, At
from astrbot.api import logger

from .utils import safe_json_read, safe_json_write
from .transport import rcon_command, rcon_command_pool, get_pool


def _load_mcserv(plugin) -> dict:
    return safe_json_read(plugin.mcserv_path, {"servers": {}, "config": {}})


def _save_mcserv(plugin, data: dict):
    safe_json_write(plugin.mcserv_path, data)


def _save_cmd_tpls_init(plugin):
    try:
        tp = plugin.cmd_templates_path
        os.makedirs(os.path.dirname(tp), exist_ok=True)
        with open(tp, "w", encoding="utf-8") as f:
            json.dump(plugin.cmd_templates, f, ensure_ascii=False, indent=2)
        logger.info("[mrcon] 已创建示例命令模板文件")
    except Exception as e:
        logger.warning(f"[mrcon] 命令模板文件创建失败: {e}")


def _save_online_triggers(plugin):
    try:
        tp = plugin.online_triggers_path
        os.makedirs(os.path.dirname(tp), exist_ok=True)
        with open(tp, "w", encoding="utf-8") as f:
            json.dump(plugin.online_triggers, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"[mrcon] 保存上线触发器失败: {e}")


def _save_script_settings(plugin):
    try:
        sp = plugin.script_settings_path
        os.makedirs(os.path.dirname(sp), exist_ok=True)
        with open(sp, "w", encoding="utf-8") as f:
            json.dump(plugin.script_settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"[mrcon] 保存脚本启停设置失败: {e}")


def _save_quick_cmd_settings(plugin):
    try:
        sp = plugin.quick_cmd_settings_path
        os.makedirs(os.path.dirname(sp), exist_ok=True)
        with open(sp, "w", encoding="utf-8") as f:
            json.dump(plugin.quick_cmd_settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"[mrcon] 保存快捷命令启停设置失败: {e}")


def _save_custom_cmds(plugin):
    try:
        sp = plugin.custom_cmds_path
        os.makedirs(os.path.dirname(sp), exist_ok=True)
        with open(sp, "w", encoding="utf-8") as f:
            json.dump(plugin.custom_cmds, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"[mrcon] 保存自定义命令映射失败: {e}")


async def _check_online_triggers(plugin, player: str, srv_name: str, gid: str, conf: dict, now: int):
    for t in plugin.online_triggers:
        if not t.get("enabled"):
            continue
        tplayer = str(t.get("player", "")).strip()
        if not tplayer:
            continue
        match_type = t.get("match_type", "exact")
        if match_type == "exact":
            if player.lower() != tplayer.lower():
                continue
        elif match_type == "contains":
            if tplayer.lower() not in player.lower():
                continue
        else:
            continue
        cd_sec = int(t.get("cooldown_seconds", 0))
        if cd_sec > 0:
            cd_map = plugin._trigger_cooldowns.setdefault(t["name"], {})
            last = cd_map.get(player, 0)
            if now - last < cd_sec:
                continue
            cd_map[player] = now
        cmds = t.get("commands", [])
        if not isinstance(cmds, list):
            cmds = [str(cmds)]
        for cmd in cmds:
            cmd = str(cmd).replace("{player}", player).replace("{PLAYER}", player)
            try:
                resp = await plugin._rcn_send(
                    conf["rcon_host"], int(conf["rcon_port"]),
                    conf["rcon_password"], cmd,
                )
                logger.info(f"[mrcon] 触发器 [{t['name']}] 执行: {cmd} -> {resp[:80]}")
            except Exception as e:
                logger.warning(f"[mrcon] 触发器 [{t['name']}] 失败: {cmd} -> {e}")


def _get_group_serv_data(plugin, group_id: str) -> dict:
    gpath = os.path.join(plugin.plugin_data_dir, f"mcserv_{group_id}.json")
    return safe_json_read(gpath, {"servers": {}, "config": {}})


def _save_group_serv_data(plugin, group_id: str, data: dict):
    gpath = os.path.join(plugin.plugin_data_dir, f"mcserv_{group_id}.json")
    safe_json_write(gpath, data)


async def _get_mc_server_status(plugin, host: str, port: str):
    try:
        from mcstatus import JavaServer
        addr = f"{host}:{port}" if port else host
        server = await asyncio.wait_for(JavaServer.async_lookup(addr), timeout=5.0)
        status = await asyncio.wait_for(server.async_status(), timeout=5.0)
        players_list = []
        if status.players.sample:
            players_list = sorted([p.name for p in status.players.sample])
        return {
            "online": True,
            "players": players_list,
            "players_online": status.players.online,
            "players_max": status.players.max,
            "version": status.version.name,
            "latency": int(status.latency),
        }
    except asyncio.TimeoutError:
        return {"online": False}
    except Exception:
        return {"online": False}


def _format_server_status(plugin, name: str, host: str, port: str, status: dict) -> str:
    addr = f"{host}:{port}" if port else host
    lines = [f"🖥️ 服务器：{name}"]
    if plugin.query_show_addr:
        lines.append(f"📍 地址：{addr}")
    if not status["online"]:
        lines.append("🔴 状态：离线或查询超时")
        return "\n".join(lines)
    lines.append("🟢 状态：在线")
    if plugin.query_show_ver:
        lines.append(f"📦 版本：{status['version']}")
    if plugin.query_show_latency:
        lines.append(f"📶 延迟：{status['latency']}ms")
    if plugin.query_show_count:
        lines.append(f"👥 人数：{status['players_online']}/{status['players_max']}")
    if plugin.query_show_players and status["players_online"] > 0:
        lines.append(f"🎮 在线玩家：{', '.join(status['players'])}")
    elif plugin.query_show_players:
        lines.append("🎮 在线玩家：暂无")
    return "\n".join(lines)


async def cmd_mc(plugin, event: AstrMessageEvent):
    gid = plugin._get_group_id(event)
    data = _get_group_serv_data(plugin, gid)
    servers_dict = data.get("servers", {})
    if not servers_dict:
        yield event.plain_result("本群暂无已添加的 MC 服务器。请用 /mcadd <名称> <地址> 添加")
        return
    tasks = {}
    for sname, info in servers_dict.items():
        host = info.get("host", "")
        port = str(info.get("port", "") or "")
        tasks[sname] = asyncio.create_task(_get_mc_server_status(plugin, host, port))
    results = []
    for sname, task in tasks.items():
        try:
            status = await task
        except Exception:
            status = {"online": False}
        info = servers_dict[sname]
        host = info.get("host", "")
        port = str(info.get("port", "") or "")
        results.append((sname, host, port, status))
    if len(results) == 1:
        sname, host, port, status = results[0]
        yield event.plain_result(_format_server_status(plugin, sname, host, port, status))
        return
    total_online = sum(1 for _, _, _, s in results if s["online"])
    total_players = sum(s["players_online"] for _, _, _, s in results if s["online"])
    lines = [f"📊 在线玩家汇总: {total_players}人 | {total_online}/{len(results)} 台在线"]
    for sname, _, _, s in results:
        if s["online"]:
            lines.append(f"  {sname}: {s['players_online']}人")
    lines.append("───")
    yield event.plain_result("\n".join(lines))
    for sname, host, port, s in results:
        yield event.plain_result(_format_server_status(plugin, sname, host, port, s))


async def cmd_mcget(plugin, event: AstrMessageEvent, name: str = ""):
    if not name:
        yield event.plain_result("用法: /mcget <服务器名称>")
        return
    gid = plugin._get_group_id(event)
    data = _get_group_serv_data(plugin, gid)
    servers_dict = data.get("servers", {})
    info = servers_dict.get(name)
    if not info:
        yield event.plain_result(f"未找到服务器: {name}")
        return
    host = info.get("host", "")
    port = str(info.get("port", "") or "")
    status = await _get_mc_server_status(plugin, host, port)
    yield event.plain_result(_format_server_status(plugin, name, host, port, status))


async def cmd_mclist(plugin, event: AstrMessageEvent):
    gid = plugin._get_group_id(event)
    data = _get_group_serv_data(plugin, gid)
    servers_dict = data.get("servers", {})
    if not servers_dict:
        yield event.plain_result("本群暂无已添加的 MC 服务器")
        return
    lines = ["📋 本群 MC 服务器列表:"]
    for sname, info in servers_dict.items():
        host = info.get("host", "")
        port = str(info.get("port", "") or "")
        display_addr = f"{host}:{port}" if port else host
        lines.append(f"  • {sname} → {display_addr}")
    yield event.plain_result("\n".join(lines))


async def cmd_mcadd(plugin, event: AstrMessageEvent, name: str = "", addr: str = ""):
    if not plugin.is_allowed(event):
        yield event.plain_result("仅管理员可添加服务器")
        return
    if not name or not addr:
        yield event.plain_result("用法: /mcadd <名称> <地址[:端口]>")
        return
    gid = plugin._get_group_id(event)
    data = _get_group_serv_data(plugin, gid)
    if name in data.get("servers", {}):
        yield event.plain_result(f"服务器 {name} 已存在")
        return
    parts = addr.split(":")
    host = parts[0]
    port = parts[1] if len(parts) > 1 else ""
    data.setdefault("servers", {})
    data["servers"][name] = {
        "name": name,
        "host": host,
        "port": port,
        "created_time": int(time.time()),
        "last_success_time": int(time.time()),
    }
    _save_group_serv_data(plugin, gid, data)
    display_addr = f"{host}:{port}" if port else host
    yield event.plain_result(f"✅ 已添加服务器: {name} ({display_addr})")


async def cmd_mcdel(plugin, event: AstrMessageEvent, name: str = ""):
    if not plugin.is_allowed(event):
        yield event.plain_result("仅管理员可删除服务器")
        return
    if not name:
        yield event.plain_result("用法: /mcdel <服务器名称>")
        return
    gid = plugin._get_group_id(event)
    data = _get_group_serv_data(plugin, gid)
    if name not in data.get("servers", {}):
        yield event.plain_result(f"没有叫 {name} 的服务器")
        return
    del data["servers"][name]
    _save_group_serv_data(plugin, gid, data)
    yield event.plain_result(f"✅ 已删除服务器: {name}")


async def cmd_mcup(plugin, event: AstrMessageEvent, name: str = "", new_name: str = "", new_addr: str = ""):
    if not plugin.is_allowed(event):
        yield event.plain_result("仅管理员可更新服务器")
        return
    if not name:
        yield event.plain_result("用法: /改服 <名称> [新名称] [新地址]")
        return
    gid = plugin._get_group_id(event)
    data = _get_group_serv_data(plugin, gid)
    if name not in data.get("servers", {}):
        yield event.plain_result(f"没有叫 {name} 的服务器")
        return
    if new_name and new_name != name:
        if new_name in data["servers"]:
            yield event.plain_result(f"服务器 {new_name} 已存在")
            return
        data["servers"][new_name] = data["servers"].pop(name)
        data["servers"][new_name]["name"] = new_name
        name = new_name
    if new_addr:
        parts = new_addr.split(":")
        data["servers"][name]["host"] = parts[0]
        data["servers"][name]["port"] = parts[1] if len(parts) > 1 else ""
    _save_group_serv_data(plugin, gid, data)
    yield event.plain_result(f"✅ 已更新服务器: {name}")


async def cmd_mcshare(plugin, event: AstrMessageEvent, name: str = "", target_gid: str = ""):
    if not plugin.is_admin(str(event.get_sender_id())):
        yield event.plain_result("仅超级管理员可共享服务器")
        return
    if not name or not target_gid:
        yield event.plain_result("用法: /共享服 <名称> <目标群ID>")
        return
    gid = plugin._get_group_id(event)
    src = _get_group_serv_data(plugin, gid)
    if name not in src.get("servers", {}):
        yield event.plain_result(f"本群没有叫 {name} 的服务器")
        return
    dst = _get_group_serv_data(plugin, target_gid)
    dst.setdefault("servers", {})
    dst["servers"][name] = src["servers"][name]
    _save_group_serv_data(plugin, target_gid, dst)
    yield event.plain_result(f"✅ 已将服务器 {name} 共享到群 {target_gid}")


async def cmd_mcunshare(plugin, event: AstrMessageEvent, name: str = "", target_gid: str = ""):
    if not plugin.is_admin(str(event.get_sender_id())):
        yield event.plain_result("仅超级管理员可取消共享")
        return
    if not name or not target_gid:
        yield event.plain_result("用法: /取消共享 <名称> <目标群ID>")
        return
    dst = _get_group_serv_data(plugin, target_gid)
    if name not in dst.get("servers", {}):
        yield event.plain_result(f"目标群没有叫 {name} 的服务器")
        return
    del dst["servers"][name]
    _save_group_serv_data(plugin, target_gid, dst)
    yield event.plain_result(f"✅ 已取消共享服务器 {name}（群 {target_gid}）")


async def cmd_mccleanup(plugin, event: AstrMessageEvent):
    if not plugin.is_allowed(event):
        yield event.plain_result("仅管理员可清理")
        return
    if plugin.query_cleanup_days <= 0:
        yield event.plain_result("自动清理已禁用")
        return
    gid = plugin._get_group_id(event)
    data = _get_group_serv_data(plugin, gid)
    cutoff = int(time.time()) - plugin.query_cleanup_days * 86400
    deleted = []
    for sname, info in list(data.get("servers", {}).items()):
        if info.get("last_success_time", 0) < cutoff:
            del data["servers"][sname]
            deleted.append(sname)
    _save_group_serv_data(plugin, gid, data)
    if deleted:
        yield event.plain_result(f"✅ 已清理 {len(deleted)} 个失效服务器: {', '.join(deleted)}")
    else:
        yield event.plain_result("没有需要清理的服务器")


async def cmd_mcset(plugin, event: AstrMessageEvent, key: str = "", value: str = ""):
    if not plugin.is_allowed(event):
        yield event.plain_result("仅管理员可设置")
        return
    mapping = {
        "地址": "show_address_port", "addr": "show_address_port", "端口": "show_address_port",
        "版本": "show_version", "version": "show_version",
        "延迟": "show_latency", "延时": "show_latency", "ping": "show_latency",
        "在线数量": "show_online_count", "online": "show_online_count",
        "玩家详细": "show_players_detail", "players": "show_players_detail",
    }
    cfg_key = mapping.get(key.strip())
    val = value.strip()
    if cfg_key is None:
        yield event.plain_result(f"未知配置项: {key}。可选: 地址/版本/延迟/在线数量/玩家详细")
        return
    if val not in ("0", "1"):
        yield event.plain_result("值必须为 0(隐藏) 或 1(显示)")
        return
    attr_map = {
        "show_address_port": "query_show_addr",
        "show_version": "query_show_ver",
        "show_latency": "query_show_latency",
        "show_online_count": "query_show_count",
        "show_players_detail": "query_show_players",
    }
    setattr(plugin, attr_map[cfg_key], val == "1")
    yield event.plain_result(f"✅ 已设置 {cfg_key} = {'显示' if val == '1' else '隐藏'}")


async def cmd_onlinetime(plugin, event: AstrMessageEvent, target: str = ""):
    if not plugin.tracker_enabled:
        yield event.plain_result("在线时长监控未开启")
        return
    gid = plugin._get_group_id(event)
    data = _get_group_serv_data(plugin, gid) if gid else {}
    servers_dict = data.get("servers", {})
    srv_names = list(servers_dict.keys()) if servers_dict else []
    target = target.strip()
    if not target:
        if srv_names:
            ranking = plugin.db.get_online_time_ranking(15, srv_names)
            scope = f"本群 ({len(srv_names)} 服)"
        else:
            ranking = plugin.db.get_online_time_ranking(15, srv_names)
            scope = "本群"
    elif target in srv_names:
        ranking = plugin.db.get_online_time_ranking(15, [target])
        scope = target
    else:
        secs = plugin.db.get_player_total_seconds(target)
        if secs <= 0:
            yield event.plain_result(f"未找到玩家 {target} 的数据")
            return
        mins = secs // 60
        hours = mins // 60
        if hours > 0:
            yield event.plain_result(f"🎮 {target}: {hours}时{mins%60}分")
        else:
            yield event.plain_result(f"🎮 {target}: {mins}分")
        return
    if not ranking:
        yield event.plain_result(f"暂无在线时长数据（{scope}）")
        return
    lines = [f"📊 在线时长排行（{scope}）:"]
    for r in ranking:
        secs = r["total"]
        mins = secs // 60
        hours = mins // 60
        name = r["player_name"]
        srv = r["server_name"]
        if hours > 0:
            lines.append(f"  [{srv}] {name}: {hours}时{mins%60}分")
        else:
            lines.append(f"  [{srv}] {name}: {mins}分")
    yield event.plain_result("\n".join(lines))
