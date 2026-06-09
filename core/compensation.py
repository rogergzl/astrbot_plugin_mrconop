import asyncio
import time

from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Plain
from astrbot.api import logger

from .utils import strip_mc_color


async def cmd_compensate(plugin, event: AstrMessageEvent, text: str = "", rest=None):
    if not plugin.pdb_enabled:
        yield event.plain_result("玩家数据库未开启")
        return
    qq_id = str(event.get_sender_id())
    if not plugin.pdb_comp_enabled:
        if qq_id not in plugin.admin_qqs and qq_id not in plugin.pdb_comp_whitelist:
            yield event.plain_result("⚠️ 补偿功能仅白名单可用，你不在白名单中")
            return
    p = plugin._ensure_player(qq_id)
    if not p.get("mc_id"):
        yield event.plain_result("请先用 /绑定 绑定 MC 账号")
        return
    parts = []
    if isinstance(text, str) and text:
        parts.append(text)
    if isinstance(rest, list):
        parts += [str(r) for r in rest if str(r)]
    elif isinstance(rest, str) and rest:
        parts.append(rest)
    rcon_cmd = " ".join(parts)
    if not rcon_cmd:
        yield event.plain_result("用法: /理赔 <完整RCON命令>\n例: /理赔 give PlayerName diamond 64")
        return
    banned = plugin._check_comp_blacklist(rcon_cmd)
    if banned:
        yield event.plain_result(f"⚠️ 命令中包含禁止物品 [{banned}]，申请自动驳回")
        return
    gid = plugin._get_group_id(event)
    desc = f"{p['mc_id']} 申请: {rcon_cmd}"
    comp_id = plugin.db.add_compensation(qq_id, p["mc_id"], gid, rcon_cmd, desc)
    if plugin.pdb_comp_admin:
        yield event.plain_result(f"📝 补偿申请已提交 (#{comp_id})\n命令: {rcon_cmd}\n请等待管理员审批")
    else:
        plugin.db.update_compensation(comp_id, "approved")
        yield event.plain_result(f"✅ 补偿申请已自动通过 (#{comp_id})\n命令: {rcon_cmd}")


async def cmd_comp_list(plugin, event: AstrMessageEvent):
    if not plugin.is_allowed(event):
        yield event.plain_result("仅管理员可查看")
        return
    pending = plugin.db.get_pending_compensations()
    if not pending:
        yield event.plain_result("暂无待处理的补偿申请")
        return
    lines = ["📋 待处理补偿申请:"]
    for c in pending[:10]:
        lines.append(f"  #{c['id']} {c['mc_id']}({c['qq_id']}): {c.get('rcon_cmd', c.get('description', ''))[:60]}")
    lines.append("使用 /同意理赔 <ID> 批准 或 /拒绝理赔 <ID> 拒绝")
    yield event.plain_result("\n".join(lines))


async def cmd_comp_approve(plugin, event: AstrMessageEvent, comp_id: str = ""):
    if not plugin.is_allowed(event):
        yield event.plain_result("仅管理员可审批")
        return
    try:
        cid = int(comp_id)
    except ValueError:
        yield event.plain_result("用法: /同意理赔 <申请ID>")
        return
    comp = plugin.db.get_compensation(cid)
    if not comp:
        yield event.plain_result(f"未找到申请 #{cid}")
        return
    if comp.get("status") != "pending":
        yield event.plain_result(f"申请 #{cid} 已处理")
        return
    rcon_cmd = comp.get("rcon_cmd", "")
    if not rcon_cmd:
        yield event.plain_result(f"申请 #{cid} 无有效命令")
        return
    plugin.db.update_compensation(cid, "approved")
    yield event.plain_result(f"✅ 已批准 #{cid}，正在执行 `{rcon_cmd}` ...")
    gid = comp.get("group_id", "") or plugin._get_group_id(event)
    conf = plugin.group_map.get(gid)
    if not conf:
        confs = plugin.group_servers.get(gid) if gid else None
        conf = (confs[0] if confs and len(confs) == 1 else None)
    if not conf:
        yield event.plain_result(f"⚠️ 申请所在群未配置服务器，无法自动执行")
        return
    async for msg in plugin._execute_on_conf(event, conf, rcon_cmd, f"补偿#{cid}"):
        yield msg


async def cmd_comp_reject(plugin, event: AstrMessageEvent, comp_id: str = ""):
    if not plugin.is_allowed(event):
        yield event.plain_result("仅管理员可审批")
        return
    try:
        cid = int(comp_id)
    except ValueError:
        yield event.plain_result("用法: /拒绝理赔 <申请ID>")
        return
    comp = plugin.db.get_compensation(cid)
    if not comp:
        yield event.plain_result(f"未找到申请 #{cid}")
        return
    plugin.db.update_compensation(cid, "rejected")
    yield event.plain_result(f"❌ 已拒绝补偿申请 #{cid}")
