import asyncio
import json
import time

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import At, Plain
from astrbot.core.utils.session_waiter import SessionController, session_waiter

from .rcon_executor import execute_on_conf as _execute_on_conf, execute_and_reply
from .utils import strip_mc_color


async def cmd_mrcon(plugin, event: AstrMessageEvent, text: str = "", rest=None):
    sender_qq = str(event.get_sender_id())
    user_name = event.get_sender_name()
    named = f"{user_name}({sender_qq})"
    parts = []
    if isinstance(text, str) and text:
        parts.append(text)
    if isinstance(rest, list):
        parts += [str(r) for r in rest if str(r)]
    elif isinstance(rest, str) and rest:
        parts.append(rest)
    elif rest is not None:
        parts.append(str(rest))
    params_tail = " ".join(parts).strip()
    full_cmd = plugin._extract_full_after_cmd(event, params_tail)
    if not full_cmd:
        yield event.plain_result(f"你好, {named}, 请输入要转发的命令。")
        return
    gid = plugin._get_group_id(event)
    servers = plugin.group_servers.get(gid) or []
    conf = (servers[0] if len(servers) == 1 else (plugin.group_map.get(gid) if gid else None))
    pub_cmds = conf.get("public_commands", []) if conf else []
    vote_enabled = bool(conf.get("vote_enabled", False)) if conf else False
    head = full_cmd.split()[0] if full_cmd else ""
    is_public = (head in pub_cmds) or any(full_cmd.startswith(p) for p in pub_cmds)
    if not is_public and not plugin.is_allowed(event):
        yield event.plain_result("抱歉，你没有权限执行此操作。")
        return
    if not plugin.is_admin(str(event.get_sender_id())) and plugin._match_dangerous(full_cmd):
        yield event.plain_result("该命令被策略禁止执行")
        return
    if conf is None and not servers:
        partial = plugin.partial_map.get(gid)
        if partial:
            missing = ", ".join(partial.get("missing", []))
            slot = partial.get("slot", "该群槽位")
            yield event.plain_result(f"当前群槽位配置不完整(缺少: {missing})，请在 {slot} 填写完整 RCON 配置。")
        else:
            yield event.plain_result("当前群未配置 RCON 槽位，请管理员在配置中填好地址/端口/密码。")
        return
    if len(servers) > 1:
        key = plugin._ps_key(event)
        plugin.pending_select[key] = {
            "cmd": full_cmd,
            "options": servers,
            "deadline": int(time.time()) + max(5, plugin.select_ttl),
        }
        lines = ["当前群配置了多个 RCON 服务器，请选择编号："]
        for idx, c in enumerate(servers, start=1):
            lines.append(f"{idx}. {c.get('display_name')}")
        lines.append(f"请在 {plugin.select_ttl} 秒内回复编号（直接发送数字即可），或使用 /选服 <编号>")
        await event.send(event.plain_result("\n".join(lines)))

        @session_waiter(timeout=plugin.select_ttl, record_history_chains=False)
        async def select_digit_waiter(controller: SessionController, ev: AstrMessageEvent):
            raw = str(getattr(ev, "message_str", "") or "").strip()
            if not raw.isdigit():
                return
            try:
                i = int(raw)
            except Exception:
                return
            rec = plugin.pending_select.get(key) or {}
            options = rec.get("options", []) or servers
            if i < 1 or i > len(options):
                return
            conf = options[i - 1]
            cmd = rec.get("cmd", full_cmd)
            if plugin._ps_key(ev) != key:
                return
            try:
                del plugin.pending_select[key]
            except Exception:
                pass
            async for msg in _execute_on_conf(plugin, ev, conf, cmd, f"选择服务器#{i}:{conf.get('display_name') or conf.get('server_name')}"):
                await ev.send(msg)
            controller.stop()

        try:
            await select_digit_waiter(event)
        except Exception:
            pass

        asyncio.create_task(plugin._schedule_select_timeout(event, key))
        return
    if is_public and vote_enabled:
        gid2 = gid
        rec = plugin.exec_votes.get(gid2)
        if rec:
            yield event.plain_result("当前已有进行中的命令投票")
            return
        plugin.exec_votes[gid2] = {
            "cmd": full_cmd,
            "votes": {},
            "threshold": int(conf.get("vote_threshold", 3)),
            "ttl": int(conf.get("vote_ttl", 60)),
            "min_agree": int(conf.get("vote_min_agree_on_timeout", 1)),
            "tie_strategy": str(conf.get("vote_tie_strategy", "fail")),
            "await_admin": False,
        }
        async def settle_vote():
            await asyncio.sleep(plugin.exec_votes[gid2]["ttl"])
            rec2 = plugin.exec_votes.get(gid2)
            if not rec2:
                return
            agree = sum(1 for v in rec2["votes"].values() if v)
            disagree = sum(1 for v in rec2["votes"].values() if not v)
            thr = rec2["threshold"]
            cmd2 = rec2["cmd"]
            if agree >= thr:
                del plugin.exec_votes[gid2]
                async for msg in execute_and_reply(plugin, event, cmd2, "投票通过执行"):
                    await event.send(msg)
                return
            if agree >= rec2["min_agree"] and agree == disagree:
                st = rec2["tie_strategy"].lower()
                if st == "pass":
                    del plugin.exec_votes[gid2]
                    async for msg in execute_and_reply(plugin, event, cmd2, "平票通过执行"):
                        await event.send(msg)
                    return
                if st == "admin":
                    rec2["await_admin"] = True
                    await event.send(event.plain_result(f"投票时间到（平票，等待管理员裁决）！命令 `{cmd2}`"))
                    at = int(conf.get("admin_decide_ttl", 120))
                    async def admin_timeout():
                        await asyncio.sleep(at)
                        rec3 = plugin.exec_votes.get(gid2)
                        if not rec3 or not rec3.get("await_admin", False):
                            return
                        cmd3 = rec3["cmd"]
                        del plugin.exec_votes[gid2]
                        await event.send(event.plain_result(f"管理员裁决超时！命令 `{cmd3}` 被否决"))
                    asyncio.create_task(admin_timeout())
                else:
                    del plugin.exec_votes[gid2]
                    await event.send(event.plain_result(f"投票时间到（平票，策略=否决）！命令 `{cmd2}` 被否决"))
            else:
                del plugin.exec_votes[gid2]
                await event.send(event.plain_result(f"投票时间到！命令 `{cmd2}` 被否决"))
        asyncio.create_task(settle_vote())
        return
    async for msg in execute_and_reply(plugin, event, full_cmd, "命令转发"):
        yield msg


async def cmd_select_server(plugin, event: AstrMessageEvent, index: str = ""):
    key = plugin._ps_key(event)
    rec = plugin.pending_select.get(key)
    if not rec:
        yield event.plain_result("当前没有待选择的命令")
        return
    if int(time.time()) > int(rec.get("deadline", 0)):
        del plugin.pending_select[key]
        yield event.plain_result("选择超时，请重新发送命令")
        return
    try:
        i = int(str(index).strip())
    except Exception:
        yield event.plain_result("请输入有效编号，如 /选服 1")
        return
    options = rec.get("options", [])
    if i < 1 or i > len(options):
        yield event.plain_result("编号超出范围，请重新选择")
        return
    conf = options[i - 1]
    cmd = rec.get("cmd", "")
    del plugin.pending_select[key]
    async for msg in _execute_on_conf(plugin, event, conf, cmd, f"选择服务器#{i}:{conf.get('display_name') or conf.get('server_name')}"):
        yield msg


async def cmd_rc_agree(plugin, event: AstrMessageEvent):
    gid = plugin._get_group_id(event)
    rec = plugin.exec_votes.get(gid)
    if not rec:
        yield event.plain_result("当前没有进行中的命令投票")
        return
    voter_id = str(event.get_sender_id())
    rec["votes"][voter_id] = True
    agree = sum(1 for v in rec["votes"].values() if v)
    disagree = sum(1 for v in rec["votes"].values() if not v)
    threshold = rec["threshold"]
    if agree >= threshold:
        cmd = rec["cmd"]
        del plugin.exec_votes[gid]
        async for msg in execute_and_reply(plugin, event, cmd, "投票通过执行"):
            yield msg
        return
    yield event.plain_result(f"命令 `{rec['cmd']}` 投票进度：赞同({agree}/{threshold}) 反对({disagree}/{threshold})")


async def cmd_rc_oppose(plugin, event: AstrMessageEvent):
    gid = plugin._get_group_id(event)
    rec = plugin.exec_votes.get(gid)
    if not rec:
        yield event.plain_result("当前没有进行中的命令投票")
        return
    voter_id = str(event.get_sender_id())
    rec["votes"][voter_id] = False
    agree = sum(1 for v in rec["votes"].values() if v)
    disagree = sum(1 for v in rec["votes"].values() if not v)
    threshold = rec["threshold"]
    if disagree >= threshold:
        cmd = rec["cmd"]
        del plugin.exec_votes[gid]
        yield event.plain_result(f"命令 `{cmd}` 投票被否决")
        return
    yield event.plain_result(f"命令 `{rec['cmd']}` 投票进度：赞同({agree}/{threshold}) 反对({disagree}/{threshold})")


async def cmd_rc_pass(plugin, event: AstrMessageEvent):
    if not plugin.is_admin(str(event.get_sender_id())):
        yield event.plain_result("仅管理员可用")
        return
    gid = plugin._get_group_id(event)
    rec = plugin.exec_votes.get(gid)
    if not rec:
        yield event.plain_result("当前没有进行中的命令投票")
        return
    if not rec.get("await_admin", False):
        yield event.plain_result("当前不需要管理员裁决")
        return
    cmd = rec["cmd"]
    async for msg in execute_and_reply(plugin, event, cmd, "管理员裁决执行"):
        yield msg
    del plugin.exec_votes[gid]


async def cmd_rc_veto(plugin, event: AstrMessageEvent):
    if not plugin.is_admin(str(event.get_sender_id())):
        yield event.plain_result("仅管理员可用")
        return
    gid = plugin._get_group_id(event)
    rec = plugin.exec_votes.get(gid)
    if not rec:
        yield event.plain_result("当前没有进行中的命令投票")
        return
    if not rec.get("await_admin", False):
        yield event.plain_result("当前不需要管理员裁决")
        return
    cmd = rec["cmd"]
    del plugin.exec_votes[gid]
    yield event.plain_result(f"管理员已裁决否决！命令 `{cmd}` 被否决")
