import asyncio
import time
import os
import re
import json

from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Plain, At
from astrbot.api import logger

from .utils import strip_mc_color


def _load_player_db(plugin):
    return {"players": {}, "compensations": []}


def _save_player_db(plugin, data):
    pass


async def cmd_bind(plugin, event: AstrMessageEvent, mc_id: str = "", rest: str = ""):
    if not plugin.pdb_enabled:
        yield event.plain_result("玩家数据库功能未开启")
        return
    sender_qq = str(event.get_sender_id())
    is_global_admin = plugin.is_admin(sender_qq)
    gid = plugin._get_group_id(event)
    is_group_admin = False
    if gid and gid in plugin.group_servers:
        for srv in plugin.group_servers[gid]:
            wl = [str(x) for x in srv.get("whitelist_qqs", [])]
            if sender_qq in wl:
                is_group_admin = True
                break

    if rest.strip():
        if not is_global_admin and not is_group_admin:
            yield event.plain_result("❌ 你没有管理员权限，不能帮别人绑定。用法: /绑定 <你的MC ID>")
            return
        target_qq = mc_id.strip()
        target_mc = rest.strip()
        if not target_qq.isdigit():
            yield event.plain_result("❌ QQ号必须是纯数字\n用法: /绑定 <QQ号> <MC ID>")
            return
        if not is_global_admin:
            if not gid:
                yield event.plain_result("❌ 仅在群聊中可使用管理员绑定功能")
                return
        result = plugin.db.bind_player(target_qq, target_mc, plugin.pdb_new_pts)
        if result.get("already_bound"):
            yield event.plain_result(f"❌ 该QQ已绑定 MC 账号 {result['old_mc_id']}，不能重复绑定")
            return
        yield event.plain_result(f"✅ 已为 QQ {target_qq} 绑定 MC 账号: {target_mc}\n🎁 获得新玩家奖励 {plugin.pdb_new_pts} 积分！\n💰 总积分: {result['total_pts']}")
        return

    if not mc_id:
        hint = "用法: /绑定 <你的MC ID>"
        if is_global_admin or is_group_admin:
            hint += "\n管理员用法: /绑定 <QQ号> <MC ID>"
        yield event.plain_result(hint)
        return
    result = plugin.db.bind_player(sender_qq, mc_id, plugin.pdb_new_pts)
    if result.get("already_bound"):
        yield event.plain_result(f"❌ 你已绑定 {result['old_mc_id']}，不能重复绑定")
        return
    yield event.plain_result(f"✅ 已绑定 MC 账号: {mc_id}\n🎁 获得新玩家奖励 {plugin.pdb_new_pts} 积分！\n💰 总积分: {result['total_pts']}")


async def cmd_checkin(plugin, event: AstrMessageEvent):
    if not plugin.pdb_enabled:
        yield event.plain_result("玩家数据库功能未开启")
        return
    qq_id = str(event.get_sender_id())
    today = time.strftime("%Y-%m-%d")
    result = plugin.db.checkin_player(qq_id, today, plugin.pdb_checkin_pts, plugin.pdb_streak_bonus)
    if not result.get("mc_id"):
        yield event.plain_result("请先用 /绑定 绑定 MC 账号再签到")
        return
    if result.get("already_checked"):
        yield event.plain_result("你今天已经签到过了！")
        return
    yield event.plain_result(
        f"✅ 签到成功！连续签到 {result['streak']} 天\n"
        f"💰 +{result['gained_pts']} 积分 | 总积分: {result['total_pts']}"
    )


async def cmd_mystats(plugin, event: AstrMessageEvent):
    if not plugin.pdb_enabled:
        yield event.plain_result("玩家数据库功能未开启")
        return
    qq_id = str(event.get_sender_id())
    p = plugin._ensure_player(qq_id)
    lines = [
        f"📊 {event.get_sender_name()} 的统计",
        f"MC ID: {p.get('mc_id', '未绑定')}",
        f"💰 积分: {p.get('points', 0)}",
        f"📅 连续签到: {p.get('checkin_streak', 0)} 天",
        f"🕐 首次登录: {time.strftime('%Y-%m-%d', time.localtime(p['first_login'])) if p.get('first_login') else '未知'}",
    ]
    yield event.plain_result("\n".join(lines))
