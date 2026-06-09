import asyncio
import time

from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Plain
from astrbot.api import logger

from .utils import strip_mc_color


async def cmd_exchange_list(plugin, event: AstrMessageEvent):
    if not plugin.pdb_enabled:
        yield event.plain_result("玩家数据库功能未开启")
        return
    gid = plugin._get_group_id(event) or ""
    items = plugin.db.get_exchange_items(gid)
    if not items:
        yield event.plain_result("当前群暂无可用兑换项")
        return
    lines = ["📦 可用兑换项:"]
    for it in items:
        status = "✅" if it.get("enabled") else "⛔"
        lines.append(f"{status} #{it['id']} {it['name']} — {it['cost_points']}积分")
        if it.get("description"):
            lines.append(f"   {it['description']}")
    yield event.plain_result("\n".join(lines))


async def cmd_exchange(plugin, event: AstrMessageEvent, item_id: str = ""):
    if not plugin.pdb_enabled:
        yield event.plain_result("玩家数据库功能未开启")
        return
    gid = plugin._get_group_id(event)
    if not gid:
        yield event.plain_result("仅在群聊中可使用兑换功能")
        return
    try:
        iid = int(item_id)
    except ValueError:
        yield event.plain_result("用法: /兑换 <编号>\n先用 /兑换列表 查看可用项目")
        return
    qq_id = str(event.get_sender_id())
    p = plugin.db.get_player(qq_id)
    if not p or not p.get("mc_id"):
        yield event.plain_result("请先用 /绑定 绑定 MC 账号")
        return
    item = plugin.db.get_exchange_item(iid)
    if not item or str(item.get("group_id", "")) != gid:
        yield event.plain_result("❌ 兑换项不属于当前群")
        return
    result = plugin.db.redeem_exchange(qq_id, p["mc_id"], iid)
    if not result["success"]:
        yield event.plain_result(f"❌ {result['error_msg']}")
        return
    conf = plugin.group_map.get(gid)
    if not conf:
        yield event.plain_result(
            f"✅ 已兑换 {result['item_name']}，消耗 {result['cost']} 积分\n"
            f"💰 剩余积分: {result['total_pts']}\n"
            f"⚠️ 当前群未配置服务器，RCON命令手动执行: {result['rcon_cmd']}"
        )
        return
    try:
        async for msg in plugin._execute_on_conf(event, conf, result['rcon_cmd'],
                                                 f"兑换#{iid} {result['item_name']}"):
            yield msg
        yield event.plain_result(
            f"✅ 兑换成功: {result['item_name']}\n"
            f"💰 消耗 {result['cost']} 积分 | 剩余: {result['total_pts']}"
        )
    except Exception:
        yield event.plain_result(
            f"✅ 已兑换 {result['item_name']}，消耗 {result['cost']} 积分\n"
            f"💰 剩余积分: {result['total_pts']}\n"
            f"⚠️ RCON执行异常，命令: {result['rcon_cmd']}"
        )
