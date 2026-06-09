import asyncio
import json
import os
import re
import time

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Plain

from .rcon_executor import execute_and_reply
from .utils import strip_mc_color


async def cmd_macro(plugin, event: AstrMessageEvent, name: str = "", args: str = ""):
    sender_qq = str(event.get_sender_id())
    user_name = event.get_sender_name()
    named = f"{user_name}({sender_qq})"
    if not plugin.is_allowed(event):
        yield event.plain_result("抱歉，你没有权限执行此操作。")
        return
    if not name:
        yield event.plain_result(f"你好, {named}, 请输入宏名称。")
        return
    mc = plugin.macros.get(name)
    if not mc:
        yield event.plain_result("未找到该宏定义")
        return
    if not mc.get("enabled", True):
        yield event.plain_result(f"宏「{name}」已被禁用")
        return
    cmds = mc["commands"]
    parts = [p for p in str(args).split() if p]
    key = plugin._rate_key(event)
    lock = plugin._acquire_lock(key)
    async with lock:
        for c in cmds:
            cc = c
            for idx, val in enumerate(parts):
                cc = cc.replace("{" + str(idx) + "}", val)
            if not plugin.is_admin(str(event.get_sender_id())) and plugin._match_dangerous(cc):
                yield event.plain_result("该宏中的命令被策略禁止执行")
                return
            async for msg in execute_and_reply(plugin, event, cc, f"宏:{name}"):
                yield msg


async def cmd_script(plugin, event: AstrMessageEvent, filename: str = ""):
    sender_qq = str(event.get_sender_id())
    user_name = event.get_sender_name()
    named = f"{user_name}({sender_qq})"
    if not plugin.is_allowed(event):
        yield event.plain_result("抱歉，你没有权限执行此操作。")
        return
    if not filename:
        yield event.plain_result(f"你好, {named}, 请输入脚本文件名。")
        return
    path = os.path.join(plugin.scripts_dir, filename)
    ss = plugin.script_settings.get(filename, {})
    if not ss.get("enabled", True):
        yield event.plain_result(f"脚本「{filename}」已被禁用")
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f.readlines()]
    except Exception as e:
        yield event.plain_result(f"脚本读取失败：{e}")
        return
    key = plugin._rate_key(event)
    lock = plugin._acquire_lock(key)
    async with lock:
        for ln in lines:
            if not ln:
                continue
            if ln.lower().startswith("sleep "):
                try:
                    sec = float(ln.split(" ", 1)[1])
                except Exception:
                    sec = 0
                if sec > 0:
                    await asyncio.sleep(sec)
                continue
            if not plugin.is_admin(str(event.get_sender_id())) and plugin._match_dangerous(ln):
                yield event.plain_result("脚本中的命令被策略禁止执行")
                return
            async for msg in execute_and_reply(plugin, event, ln, f"脚本:{filename}"):
                yield msg


async def cmd_custom(plugin, event: AstrMessageEvent, alias: str = ""):
    sender_qq = str(event.get_sender_id())
    user_name = event.get_sender_name()
    named = f"{user_name}({sender_qq})"
    if not alias:
        yield event.plain_result(f"你好, {named}, 请输入命令别名。\n用法: /rc自定 <别名>")
        return
    gid = plugin._get_group_id(event)
    if not gid:
        yield event.plain_result("请在群内使用此命令")
        return
    cmds = plugin.custom_cmds.get(gid, [])
    match = None
    for c in cmds:
        if c.get("alias", "").strip() == alias.strip() and c.get("enabled", True):
            match = c
            break
    if not match:
        yield event.plain_result(f"未找到自定义命令「{alias}」")
        return
    wl = match.get("whitelist", [])
    if not plugin.is_admin(sender_qq):
        in_cmd_wl = wl and sender_qq in [str(w) for w in wl]
        if not in_cmd_wl and not plugin.is_allowed(event):
            yield event.plain_result("抱歉，你没有权限执行此自定义命令。")
            return
    rcon_cmd = match.get("rcon_cmd", "")
    if not rcon_cmd:
        yield event.plain_result(f"自定义命令「{alias}」未配置 RCON 命令")
        return
    show_reply = match.get("show_reply", True)
    async for msg in execute_and_reply(plugin, event, rcon_cmd, f"自定:{alias}"):
        if show_reply:
            yield msg
    if not show_reply:
        yield event.plain_result(f"✅ 已执行自定义命令「{alias}」")
