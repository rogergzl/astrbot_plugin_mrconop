import asyncio
import json
import time

from astrbot.api import logger

from .audit import _audit
from .permission import _get_group_id
from .rate_limit import _acquire_lock, _check_rate, _rate_key, _touch_rate
from .transport import get_pool, rcon_command, rcon_command_pool
from .utils import strip_mc_color


async def schedule_select_timeout(plugin, event, key: str):
    try:
        await asyncio.sleep(max(1, int(plugin.select_ttl)))
        rec = plugin.pending_select.get(key)
        if not rec:
            return
        try:
            dl = int(rec.get("deadline", 0))
        except Exception:
            dl = 0
        if int(time.time()) >= dl:
            del plugin.pending_select[key]
            await event.send(event.plain_result("选择超时，请重新发送命令"))
    except Exception:
        pass


async def rcn_send(plugin, host: str, port: int, password: str, cmd: str) -> str:
    if plugin.rcn_persistent:
        return await rcon_command_pool(host, port, password, cmd)
    else:
        return await rcon_command(host, port, password, cmd)


async def transport_send(plugin, payload_json: str) -> str:
    try:
        data = json.loads(payload_json)
    except Exception:
        data = {}
    host = data.get("host")
    port = data.get("port")
    password = data.get("password")
    cmd = str(data.get("cmd", "") or "").strip()
    resp = await rcn_send(plugin, host, port, password, cmd)
    return resp


async def execute_and_reply(plugin, event, command: str, desc: str):
    user_name = event.get_sender_name()
    sender_qq = str(event.get_sender_id())
    named = f"{user_name}({sender_qq})"
    key = _rate_key(plugin, event)
    wait = _check_rate(plugin, key)
    if wait > 0:
        yield event.plain_result(f"当前繁忙，请在 {int((wait+999)//1000)} 秒后重试")
        return
    lock = _acquire_lock(plugin, key)
    async with lock:
        gid = _get_group_id(plugin, event)
        confs = plugin.group_servers.get(gid) if gid else None
        conf = (confs[0] if confs and len(confs) == 1 else (plugin.group_map.get(gid) if gid else None))
        if conf is None:
            partial = plugin.partial_map.get(gid)
            if partial:
                missing = ", ".join(partial.get("missing", []))
                slot = partial.get("slot", "该群槽位")
                yield event.plain_result(f"当前群槽位配置不完整(缺少: {missing})，请在 {slot} 填写完整 RCON 配置。")
            else:
                yield event.plain_result("当前群未配置 RCON 槽位，请管理员在配置中填好地址/端口/密码。")
            return
        host = conf.get("rcon_host")
        port = conf.get("rcon_port")
        password = conf.get("rcon_password")
        try:
            payload = json.dumps({
                "host": host, "port": port, "password": password, "cmd": command,
            }, ensure_ascii=False)
            resp = await transport_send(plugin, payload)
            cresp = strip_mc_color(resp)
            _touch_rate(plugin, key)
            _audit(plugin, event, command, True, resp)
            logger.info(f"RCON 执行结果: {resp}")
            yield event.plain_result(f"你好, {named}, 已尝试执行 `{command}` ({desc})\n\n服务器返回：\n{cresp}")
        except Exception as e:
            _audit(plugin, event, command, False, str(e))
            logger.error(f"RCON 执行失败: {e}")
            yield event.plain_result(f"你好, {named}, 操作失败：{e}")


async def execute_on_conf(plugin, event, conf: dict, command: str, desc: str):
    user_name = event.get_sender_name()
    sender_qq = str(event.get_sender_id())
    named = f"{user_name}({sender_qq})"
    key = _rate_key(plugin, event)
    wait = _check_rate(plugin, key)
    if wait > 0:
        yield event.plain_result(f"当前繁忙，请在 {int((wait+999)//1000)} 秒后重试")
        return
    lock = _acquire_lock(plugin, key)
    async with lock:
        try:
            payload = json.dumps({
                "host": conf.get("rcon_host"), "port": conf.get("rcon_port"),
                "password": conf.get("rcon_password"), "cmd": command,
            }, ensure_ascii=False)
            resp = await transport_send(plugin, payload)
            cresp = strip_mc_color(resp)
            _touch_rate(plugin, key)
            _audit(plugin, event, command, True, resp)
            logger.info(f"RCON 执行结果: {resp}")
            yield event.plain_result(f"你好, {named}, 已尝试执行 `{command}` ({desc})\n\n服务器返回：\n{cresp}")
        except Exception as e:
            _audit(plugin, event, command, False, str(e))
            logger.error(f"RCON 执行失败: {e}")
            yield event.plain_result(f"你好, {named}, 操作失败：{e}")
