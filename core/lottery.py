import asyncio
import random
import time

from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Plain
from astrbot.api import logger

from .utils import strip_mc_color


async def cmd_lottery(plugin, event: AstrMessageEvent):
    if not plugin.pdb_enabled:
        yield event.plain_result("玩家数据库功能未开启")
        return
    gid = plugin._get_group_id(event)
    if not gid:
        yield event.plain_result("仅在群聊中可使用抽奖功能")
        return
    qq_id = str(event.get_sender_id())
    p = plugin.db.get_player(qq_id)
    if not p or not p.get("mc_id"):
        yield event.plain_result("请先用 /绑定 绑定 MC 账号")
        return
    result = plugin.db.draw_lottery(qq_id, p["mc_id"], gid)
    if not result["success"]:
        yield event.plain_result(f"❌ {result['error_msg']}")
        return
    if not result["results"]:
        yield event.plain_result(
            f"🎰 很遗憾，未中奖！消耗 {result['cost']} 积分\n💰 剩余积分: {result['total_pts']}"
        )
        return
    lines = ["🎉 恭喜中奖！"]
    for r in result["results"]:
        lines.append(f"🏆 {r['prize_name']} (兑奖编号 #{r['win_id']})")
    lines.append(f"💰 消耗 {result['cost']} 积分 | 剩余: {result['total_pts']}")
    lines.append("使用 /兑奖 <编号> 兑换奖品")
    yield event.plain_result("\n".join(lines))


async def cmd_lottery_prizes(plugin, event: AstrMessageEvent):
    gid = plugin._get_group_id(event)
    if not gid:
        yield event.plain_result("仅在群聊中使用")
        return
    prizes = plugin.db.get_lottery_prizes(gid)
    if not prizes:
        yield event.plain_result("当前群暂未配置奖品")
        return
    lines = ["🎁 可抽取奖品:"]
    for p in prizes:
        prob = f"{p['probability']*100:.0f}%"
        cost = f" ({p['cost_points']}积分/次)" if p.get("cost_points") else ""
        lines.append(f"🏆 {p['name']} — 概率 {prob}{cost}")
        if p.get("description"):
            lines.append(f"   {p['description']}")
    yield event.plain_result("\n".join(lines))


async def cmd_lottery_redeem(plugin, event: AstrMessageEvent, win_id: str = ""):
    if not plugin.pdb_enabled:
        yield event.plain_result("玩家数据库功能未开启")
        return
    gid = plugin._get_group_id(event)
    if not gid:
        yield event.plain_result("仅在群聊中使用")
        return
    try:
        wid = int(win_id)
    except ValueError:
        yield event.plain_result("用法: /兑奖 <中奖编号>\n用 /我的中奖 查看中奖记录")
        return
    result = plugin.db.redeem_lottery_win(wid)
    if not result["success"]:
        yield event.plain_result(f"❌ {result['error_msg']}")
        return
    conf = plugin.group_map.get(gid)
    if conf:
        try:
            async for msg in plugin._execute_on_conf(event, conf, result['prize_cmd'],
                                                     f"兑奖#{wid} {result['prize_name']}"):
                yield msg
        except Exception:
            yield event.plain_result(
                f"✅ 已兑 {result['prize_name']}\n⚠️ RCON执行异常，命令: {result['prize_cmd']}"
            )
            return
        yield event.plain_result(f"✅ 兑奖成功: {result['prize_name']}")
    else:
        yield event.plain_result(
            f"✅ 已兑 {result['prize_name']}\n"
            f"⚠️ 当前群未配置服务器，命令: {result['prize_cmd']}"
        )


async def cmd_lottery_my_wins(plugin, event: AstrMessageEvent):
    gid = plugin._get_group_id(event)
    if not gid:
        yield event.plain_result("仅在群聊中使用")
        return
    qq_id = str(event.get_sender_id())
    wins = plugin.db.get_lottery_wins(qq_id=qq_id, group_id=gid)
    if not wins:
        yield event.plain_result("你还没有中奖记录\n用 /抽奖 试试手气！")
        return
    lines = ["🎖️ 你的中奖记录:"]
    for w in wins[:10]:
        status = "✅ 已兑" if w["redeemed"] else "⏳ 待兑换"
        ts = time.strftime("%m/%d %H:%M", time.localtime(w["win_time"])) if w.get("win_time") else "-"
        lines.append(f"#{w['id']} {w['prize_name']} ({ts}) {status}")
    if len(wins) > 10:
        lines.append(f"...共 {len(wins)} 条记录")
    yield event.plain_result("\n".join(lines))
