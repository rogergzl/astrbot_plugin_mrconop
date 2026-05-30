import asyncio
import json
import os
import re
import time
from pathlib import Path
from collections import defaultdict
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
from astrbot.api import AstrBotConfig
from astrbot.core.utils.session_waiter import session_waiter, SessionController
from .transport import rcon_command
from .database import Database


# ==============================================================
# 工具函数
# ==============================================================
def strip_mc_color(text: str) -> str:
    return re.sub(r"§.", "", text)


def safe_json_read(path: str, default=None):
    if default is None:
        default = {}
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def safe_json_write(path: str, data):
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[mrcon] JSON 写入失败 {path}: {e}")


@register("mrcon", "lindagao", "MC 综合管理插件（RCON+查询+SQLite+继电器）", "3.2.0")
class MrconPlugin(Star):
    # ==============================================================
    # 初始化
    # ==============================================================
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

        admin_cfg = self.config.get("admin", {})
        if not isinstance(admin_cfg, dict):
            admin_cfg = {}
        self.admin_qqs = set(admin_cfg.get("bot_admin_qqs", []) or [])

        general_cfg = self.config.get("general", {})
        if not isinstance(general_cfg, dict):
            general_cfg = {}

        self.rate_limit_ms = int(admin_cfg.get("rate_limit_ms", 0) or 0)
        rate_limit_cfg = admin_cfg.get("rate_limit", {})
        if not isinstance(rate_limit_cfg, dict):
            rate_limit_cfg = {}
        self.rate_enabled = bool(rate_limit_cfg.get("enabled", False))
        self.rate_base_ms = int(rate_limit_cfg.get("base_interval_ms", 1000) or 1000)
        self.rate_window_s = int(rate_limit_cfg.get("window_minutes", 5) or 5) * 60
        self.rate_threshold = int(rate_limit_cfg.get("threshold_count", 10) or 10)
        self.rate_increment_ms = int(rate_limit_cfg.get("increment_ms", 500) or 500)
        self.rate_max_ms = int(rate_limit_cfg.get("max_interval_ms", 10000) or 10000)
        self.rate_auto_recovery = bool(rate_limit_cfg.get("auto_recovery", True))
        self.rate_recovery_s = int(rate_limit_cfg.get("recovery_minutes", 10) or 10) * 60
        self.dangerous_blacklist = list(admin_cfg.get("dangerous_commands_blacklist", []))

        query_cfg = self.config.get("query", {})
        if not isinstance(query_cfg, dict):
            query_cfg = {}
        self.query_show_addr = bool(query_cfg.get("show_address_port", True))
        self.query_show_ver = bool(query_cfg.get("show_version", True))
        self.query_show_latency = bool(query_cfg.get("show_latency", True))
        self.query_show_count = bool(query_cfg.get("show_online_count", True))
        self.query_show_players = bool(query_cfg.get("show_players_detail", True))
        self.query_render_image = bool(query_cfg.get("render_online_image", False))
        self.query_cleanup_days = int(query_cfg.get("auto_cleanup_days", 10) or 10)

        tracker_cfg = self.config.get("online_tracker", {})
        if not isinstance(tracker_cfg, dict):
            tracker_cfg = {}
        self.tracker_enabled = bool(tracker_cfg.get("enabled", False))
        self.tracker_interval = int(tracker_cfg.get("poll_interval_seconds", 60) or 60)
        self.tracker_method = str(tracker_cfg.get("query_method", "rcon") or "rcon")

        relay_cfg = self.config.get("relay", {})
        if not isinstance(relay_cfg, dict):
            relay_cfg = {}
        self.relay_enabled = bool(relay_cfg.get("enabled", False))
        self.relay_group_to_mc = bool(relay_cfg.get("group_to_mc", True))
        self.relay_mc_to_group = bool(relay_cfg.get("mc_to_group", False))
        self.relay_fmt_group = str(relay_cfg.get("format_group", "[QQ] {name}: {msg}"))
        self.relay_fmt_mc = str(relay_cfg.get("format_mc", "[MC] {player}: {msg}"))

        player_db_cfg = self.config.get("player_db", {})
        if not isinstance(player_db_cfg, dict):
            player_db_cfg = {}
        self.pdb_enabled = bool(player_db_cfg.get("enabled", False))
        self.pdb_checkin_pts = int(player_db_cfg.get("checkin_points", 10) or 10)
        self.pdb_streak_bonus = int(player_db_cfg.get("checkin_streak_bonus", 2) or 2)
        self.pdb_new_pts = int(player_db_cfg.get("new_player_points", 50) or 50)
        self.pdb_comp_enabled = bool(player_db_cfg.get("compensation_enabled", False))
        self.pdb_comp_admin = bool(player_db_cfg.get("compensation_require_admin", True))
        self.pdb_comp_blacklist = list(player_db_cfg.get("compensation_blacklist", []))

        self.group_map = {}
        self.group_servers = {}
        self.partial_map = {}
        self.exec_votes = {}
        self.group_locks = {}
        self.rate_state = {}

        self.plugin_data_dir = StarTools.get_data_dir("mrcon")
        self.scripts_dir = os.path.join(self.plugin_data_dir, str(general_cfg.get("scripts_dir", "scripts") or "scripts"))
        self.audit_file = os.path.join(self.plugin_data_dir, "audit.log")
        self.pending_select = {}
        self.select_ttl = int(general_cfg.get("select_ttl", 30) or 30)

        macros = self.config.get("macro_definitions", [])
        self.macros = {}
        if isinstance(macros, list):
            for m in macros:
                name = str(m.get("name", "")).strip()
                cmds = m.get("commands", [])
                if name and isinstance(cmds, list):
                    self.macros[name] = [str(c) for c in cmds]

        servers_raw = self.config.get("servers", [])
        if isinstance(servers_raw, list):
            servers = servers_raw
        elif isinstance(servers_raw, str) and servers_raw.strip():
            try:
                servers = json.loads(servers_raw)
            except json.JSONDecodeError:
                logger.warning("[mrcon] servers 配置 JSON 解析失败")
                servers = []
        else:
            servers = []
        if not isinstance(servers, list):
            servers = []
        for i, srv in enumerate(servers, start=1):
            if not isinstance(srv, dict):
                srv = {}
            gid = str(srv.get("group_id", "") or "").strip()
            name = str(srv.get("name", "") or "").strip()
            host = srv.get("rcon_host")
            port = srv.get("rcon_port")
            password = srv.get("rcon_password")
            game_port = str(srv.get("game_port", "25565") or "25565")
            wl = srv.get("whitelist_qqs", [])
            publics = srv.get("public_commands", [])
            vote_enabled = bool(srv.get("vote_enabled", False))
            vote_threshold = int(srv.get("vote_threshold", 3))
            vote_ttl = int(srv.get("vote_ttl", 60))
            vote_min_agree_on_timeout = int(srv.get("vote_min_agree_on_timeout", 1))
            tie_strategy = str(srv.get("vote_tie_strategy", "fail"))
            admin_decide_ttl = int(srv.get("admin_decide_ttl", 120))
            relay_ena = bool(srv.get("relay_enabled", False))
            query_ena = bool(srv.get("query_enabled", True))
            if not isinstance(wl, list):
                wl = []
            if not isinstance(publics, list):
                publics = []
            missing = []
            if not gid:
                missing.append("群 ID")
            if not name:
                missing.append("服务器名称")
            if not host:
                missing.append("地址")
            if port is None:
                missing.append("端口")
            if not password:
                missing.append("密码")
            if missing and gid:
                self.partial_map[gid] = {"missing": missing, "slot": f"服务器 #{i}"}
            if missing:
                continue
            try:
                port = int(port)
                game_port_int = int(game_port)
            except Exception:
                continue
            conf = {
                "rcon_host": host,
                "rcon_port": port,
                "rcon_password": password,
                "game_port": game_port_int,
                "whitelist_qqs": wl,
                "public_commands": publics,
                "vote_enabled": vote_enabled,
                "vote_threshold": vote_threshold,
                "vote_ttl": vote_ttl,
                "vote_min_agree_on_timeout": vote_min_agree_on_timeout,
                "vote_tie_strategy": tie_strategy,
                "admin_decide_ttl": admin_decide_ttl,
                "relay_enabled": relay_ena,
                "query_enabled": query_ena,
                "slot_index": i,
                "server_name": name,
                "display_name": name,
            }
            self.group_map[gid] = conf
            arr = self.group_servers.get(gid) or []
            arr.append(conf)
            self.group_servers[gid] = arr

        self.mcserv_path = os.path.join(self.plugin_data_dir, "mc_servers.json")
        self.player_db_path = os.path.join(self.plugin_data_dir, "player_db.json")
        self.online_sessions_path = os.path.join(self.plugin_data_dir, "online_sessions.json")
        self.db_path = os.path.join(self.plugin_data_dir, "mrcon.db")
        self.db = Database(self.db_path)
        self.db.migrate_from_json(self.player_db_path, self.online_sessions_path)
        self._online_cache = {}
        self._tracker_task = None

    async def initialize(self):
        try:
            os.makedirs(self.plugin_data_dir, exist_ok=True)
            os.makedirs(self.scripts_dir, exist_ok=True)
        except Exception:
            pass
        if self.tracker_enabled:
            self._tracker_task = asyncio.create_task(self._online_tracker_loop())

    async def terminate(self):
        if self._tracker_task:
            self._tracker_task.cancel()
            self._tracker_task = None
        logger.info("[mrcon] plugin stopped")

    # ==============================================================
    # 基础工具
    # ==============================================================
    def is_admin(self, qqid: str) -> bool:
        return qqid in self.admin_qqs

    def _get_group_id(self, event: AstrMessageEvent) -> str:
        for name in ["get_group_id", "get_target_id", "get_chat_id", "get_session_id", "get_group", "get_channel_id"]:
            f = getattr(event, name, None)
            if callable(f):
                try:
                    v = f()
                except Exception:
                    v = None
                if v:
                    return str(v)
        for name in ["group_id", "group", "channel_id", "chat_id"]:
            if hasattr(event, name):
                v = getattr(event, name)
                if v:
                    return str(v)
        return ""

    def _rate_key(self, event: AstrMessageEvent) -> str:
        return f"{self._get_group_id(event)}:{event.get_sender_id()}"

    def _ps_key(self, event: AstrMessageEvent) -> str:
        return f"{self._get_group_id(event)}:{event.get_sender_id()}"

    # ==============================================================
    # 速率限制
    # ==============================================================
    def _check_rate(self, key: str) -> int:
        if self.rate_limit_ms <= 0 and not self.rate_enabled:
            return 0
        now = int(time.time() * 1000)
        now_s = int(time.time())
        if not self.rate_enabled:
            last = int(self.rate_state.get(key, {}).get("last_exec", 0) or 0)
            if now - last < self.rate_limit_ms:
                return self.rate_limit_ms - (now - last)
            return 0
        state = self.rate_state.get(key)
        if state is None:
            state = {"timestamps": [], "interval_ms": self.rate_base_ms, "last_exec": 0}
            self.rate_state[key] = state
        timestamps = [ts for ts in state["timestamps"] if now_s - ts <= self.rate_window_s]
        state["timestamps"] = timestamps
        if self.rate_auto_recovery and not timestamps:
            last_exec_s = state.get("last_exec", 0) // 1000
            if last_exec_s and now_s - last_exec_s >= self.rate_recovery_s:
                state["interval_ms"] = self.rate_base_ms
        count = len(timestamps)
        interval = state["interval_ms"]
        if count >= self.rate_threshold:
            over_count = count - self.rate_threshold + 1
            interval = min(self.rate_max_ms, self.rate_base_ms + over_count * self.rate_increment_ms)
            state["interval_ms"] = interval
        last_exec = state.get("last_exec", 0) or 0
        if last_exec and now - last_exec < interval:
            return interval - (now - last_exec)
        return 0

    def _touch_rate(self, key: str):
        now = int(time.time() * 1000)
        if self.rate_enabled:
            state = self.rate_state.get(key)
            if state is None:
                state = {"timestamps": [], "interval_ms": self.rate_base_ms, "last_exec": 0}
                self.rate_state[key] = state
            state["timestamps"].append(int(time.time()))
            state["last_exec"] = now
        elif self.rate_limit_ms > 0:
            state = self.rate_state.get(key)
            if state is None:
                state = {"timestamps": [], "interval_ms": self.rate_limit_ms, "last_exec": 0}
                self.rate_state[key] = state
            state["last_exec"] = now

    def _acquire_lock(self, key: str):
        lock = self.group_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self.group_locks[key] = lock
        return lock

    # ==============================================================
    # RCON 核心
    # ==============================================================
    async def _schedule_select_timeout(self, event: AstrMessageEvent, key: str):
        try:
            await asyncio.sleep(max(1, int(self.select_ttl)))
            rec = self.pending_select.get(key)
            if not rec:
                return
            try:
                dl = int(rec.get("deadline", 0))
            except Exception:
                dl = 0
            if int(time.time()) >= dl:
                del self.pending_select[key]
                await event.send(event.plain_result("选择超时，请重新发送命令"))
        except Exception:
            pass

    def _audit(self, event: AstrMessageEvent, cmd: str, ok: bool, resp: str):
        try:
            rec = {
                "time": int(time.time()),
                "sender_id": str(event.get_sender_id()),
                "sender_name": str(event.get_sender_name()),
                "group_id": self._get_group_id(event),
                "cmd": cmd,
                "ok": bool(ok),
                "resp": strip_mc_color(str(resp))[:2000],
            }
            os.makedirs(self.plugin_data_dir, exist_ok=True)
            with open(self.audit_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _match_dangerous(self, cmd: str) -> bool:
        s = cmd.lower()
        for it in self.dangerous_blacklist:
            if str(it).lower() in s:
                return True
        return False

    def _extract_full_after_cmd(self, event: AstrMessageEvent, fallback: str) -> str:
        cmd_names = ["/mrcon", "/mcmd", "mrcon", "mcmd"]
        raw_candidates = []
        for name in [
            "get_message_text", "get_plain_text", "get_text", "get_raw_text",
            "raw_text", "text", "content", "message_str",
        ]:
            f = getattr(event, name, None)
            val = None
            if callable(f):
                try:
                    val = f()
                except Exception:
                    val = None
            elif hasattr(event, name):
                val = getattr(event, name, None)
            if isinstance(val, str) and val:
                raw_candidates.append(val)
        msg_obj = None
        get_message_fn = getattr(event, "get_message", None)
        get_messages_fn = getattr(event, "get_messages", None)
        if callable(get_message_fn):
            try:
                msg_obj = get_message_fn()
            except Exception:
                msg_obj = None
        elif callable(get_messages_fn):
            try:
                msg_obj = get_messages_fn()
            except Exception:
                msg_obj = None
        elif hasattr(event, "message"):
            msg_obj = getattr(event, "message", None)
        if isinstance(msg_obj, list):
            parts = []
            for it in msg_obj:
                t = None
                if isinstance(it, str):
                    t = it
                elif isinstance(it, dict):
                    if isinstance(it.get("text"), str):
                        t = it.get("text")
                    elif isinstance(it.get("data"), dict) and isinstance(it.get("data", {}).get("text"), str):
                        t = it.get("data", {}).get("text")
                elif hasattr(it, "text") and isinstance(getattr(it, "text", None), str):
                    t = getattr(it, "text")
                if isinstance(t, str) and t:
                    parts.append(t)
            if parts:
                raw_candidates.append(" ".join(parts))
        elif isinstance(msg_obj, dict):
            t = None
            if isinstance(msg_obj.get("text"), str):
                t = msg_obj.get("text")
            elif isinstance(msg_obj.get("content"), str):
                t = msg_obj.get("content")
            if isinstance(t, str) and t:
                raw_candidates.append(t)
        if hasattr(event, "message_obj"):
            mo = getattr(event, "message_obj")
            chain = getattr(mo, "message", None)
            if isinstance(chain, list):
                parts2 = []
                for seg in chain:
                    if hasattr(seg, "text") and isinstance(getattr(seg, "text", None), str):
                        tt = getattr(seg, "text")
                        if tt:
                            parts2.append(tt)
                if parts2:
                    raw_candidates.append(" ".join(parts2))
        raw = fallback
        if raw_candidates:
            raw = max(raw_candidates, key=len)
        text = str(raw or "").strip()
        patterns = [r"^.*?(?:/mrcon|mrcon|/mcmd|mcmd)\s+(.+)$"]
        for pat in patterns:
            m = re.match(pat, text, flags=re.IGNORECASE | re.DOTALL)
            if m:
                tail = m.group(1).strip()
                if tail:
                    return tail
        lowered = text.lower()
        for cn in cmd_names:
            i = lowered.find(cn)
            if i >= 0:
                tail = text[i + len(cn):].strip()
                if tail:
                    return tail
        return fallback

    def is_allowed(self, event: AstrMessageEvent) -> bool:
        qq = str(event.get_sender_id())
        if qq in self.admin_qqs:
            return True
        gid = self._get_group_id(event)
        wl = []
        if gid and gid in self.group_map:
            wl = self.group_map[gid].get("whitelist_qqs", [])
        return qq in set(str(x) for x in wl)

    async def transport_send(self, payload_json: str) -> str:
        try:
            data = json.loads(payload_json)
        except Exception:
            data = {}
        host = data.get("host")
        port = data.get("port")
        password = data.get("password")
        cmd = str(data.get("cmd", "") or "").strip()
        resp = await rcon_command(host, port, password, cmd)
        return resp

    async def execute_and_reply(self, event: AstrMessageEvent, command: str, desc: str):
        user_name = event.get_sender_name()
        sender_qq = str(event.get_sender_id())
        named = f"{user_name}({sender_qq})"
        key = self._rate_key(event)
        wait = self._check_rate(key)
        if wait > 0:
            yield event.plain_result(f"当前繁忙，请在 {int((wait+999)//1000)} 秒后重试")
            return
        lock = self._acquire_lock(key)
        async with lock:
            gid = self._get_group_id(event)
            confs = self.group_servers.get(gid) if gid else None
            conf = (confs[0] if confs and len(confs) == 1 else (self.group_map.get(gid) if gid else None))
            if conf is None:
                partial = self.partial_map.get(gid)
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
                resp = await self.transport_send(payload)
                cresp = strip_mc_color(resp)
                self._touch_rate(key)
                self._audit(event, command, True, resp)
                logger.info(f"RCON 执行结果: {resp}")
                yield event.plain_result(f"你好, {named}, 已尝试执行 `{command}` ({desc})\n\n服务器返回：\n{cresp}")
            except Exception as e:
                self._audit(event, command, False, str(e))
                logger.error(f"RCON 执行失败: {e}")
                yield event.plain_result(f"你好, {named}, 操作失败：{e}")

    async def _execute_on_conf(self, event: AstrMessageEvent, conf: dict, command: str, desc: str):
        user_name = event.get_sender_name()
        sender_qq = str(event.get_sender_id())
        named = f"{user_name}({sender_qq})"
        key = self._rate_key(event)
        wait = self._check_rate(key)
        if wait > 0:
            yield event.plain_result(f"当前繁忙，请在 {int((wait+999)//1000)} 秒后重试")
            return
        lock = self._acquire_lock(key)
        async with lock:
            try:
                payload = json.dumps({
                    "host": conf.get("rcon_host"), "port": conf.get("rcon_port"),
                    "password": conf.get("rcon_password"), "cmd": command,
                }, ensure_ascii=False)
                resp = await self.transport_send(payload)
                cresp = strip_mc_color(resp)
                self._touch_rate(key)
                self._audit(event, command, True, resp)
                logger.info(f"RCON 执行结果: {resp}")
                yield event.plain_result(f"你好, {named}, 已尝试执行 `{command}` ({desc})\n\n服务器返回：\n{cresp}")
            except Exception as e:
                self._audit(event, command, False, str(e))
                logger.error(f"RCON 执行失败: {e}")
                yield event.plain_result(f"你好, {named}, 操作失败：{e}")

    # ==============================================================
    # MC 服务器 CRUD（原 mcing 功能）
    # ==============================================================
    def _load_mcserv(self) -> dict:
        return safe_json_read(self.mcserv_path, {"servers": {}, "config": {}})

    def _save_mcserv(self, data: dict):
        safe_json_write(self.mcserv_path, data)

    def _get_group_serv_data(self, group_id: str) -> dict:
        """读取指定群的 MC 服务器数据文件"""
        gpath = os.path.join(self.plugin_data_dir, f"mcserv_{group_id}.json")
        return safe_json_read(gpath, {"servers": {}, "config": {}})

    def _save_group_serv_data(self, group_id: str, data: dict):
        gpath = os.path.join(self.plugin_data_dir, f"mcserv_{group_id}.json")
        safe_json_write(gpath, data)

    async def _get_mc_server_status(self, host: str, port: str):
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

    def _format_server_status(self, name: str, host: str, port: str, status: dict) -> str:
        addr = f"{host}:{port}" if port else host
        lines = [f"🖥️ 服务器：{name}"]
        if self.query_show_addr:
            lines.append(f"📍 地址：{addr}")
        if not status["online"]:
            lines.append("🔴 状态：离线或查询超时")
            return "\n".join(lines)
        lines.append("🟢 状态：在线")
        if self.query_show_ver:
            lines.append(f"📦 版本：{status['version']}")
        if self.query_show_latency:
            lines.append(f"📶 延迟：{status['latency']}ms")
        if self.query_show_count:
            lines.append(f"👥 人数：{status['players_online']}/{status['players_max']}")
        if self.query_show_players and status["players_online"] > 0:
            lines.append(f"🎮 在线玩家：{', '.join(status['players'])}")
        elif self.query_show_players:
            lines.append("🎮 在线玩家：暂无")
        return "\n".join(lines)

    # ==============================================================
    # 在线时长监控
    # ==============================================================
    async def _get_online_player_list(self, conf: dict) -> list:
        method = self.tracker_method
        if method == "rcon":
            try:
                raw = await rcon_command(
                    conf["rcon_host"], conf["rcon_port"], conf["rcon_password"], "list"
                )
                if ":" in raw:
                    names_part = raw.split(":", 1)[1].strip()
                    return [n.strip() for n in names_part.split(",") if n.strip()]
            except Exception:
                pass
        elif method == "mcstatus":
            try:
                st = await self._get_mc_server_status(conf["rcon_host"], str(conf.get("game_port", 25565)))
                if st["online"]:
                    return st["players"]
            except Exception:
                pass
        return []

    async def _online_tracker_loop(self):
        logger.info("[mrcon] 在线时长监控已启动")
        while True:
            try:
                await asyncio.sleep(max(10, self.tracker_interval))
                now = int(time.time())
                all_servers = []
                for gid, srvs in self.group_servers.items():
                    for srv in srvs:
                        all_servers.append((gid, srv))
                for gid, conf in all_servers:
                    if not conf.get("query_enabled", True):
                        continue
                    online = await self._get_online_player_list(conf)
                    srv_name = conf.get("server_name", "unknown")
                    for player in online:
                        sid = f"{srv_name}:{player}"
                        if sid not in self._online_cache:
                            self._online_cache[sid] = {"login_at": now, "player": player, "server": srv_name}
                    for sid in list(self._online_cache.keys()):
                        s = self._online_cache[sid]
                        if s["server"] == srv_name and s["player"] not in online:
                            self.db.add_online_session(srv_name, s["player"], s["login_at"], now)
                            del self._online_cache[sid]
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[mrcon] 在线监控错误: {e}")

    # ==============================================================
    # 玩家数据库
    # ==============================================================
    def _load_player_db(self) -> dict:
        return {"players": {}, "compensations": []}

    def _save_player_db(self, data: dict):
        pass

    def _get_player(self, qq_id: str) -> dict:
        return self.db.get_player(str(qq_id)) or None

    def _ensure_player(self, qq_id: str, mc_id: str = "") -> dict:
        return self.db.ensure_player(str(qq_id), mc_id)

    def _update_player(self, qq_id: str, updates: dict):
        self.db.update_player(str(qq_id), updates)

    # ==============================================================
    # MC 查询命令
    # ==============================================================
    @filter.command("mc", desc="查询所有MC服务器状态")
    async def cmd_mc(self, event: AstrMessageEvent):
        gid = self._get_group_id(event)
        data = self._get_group_serv_data(gid)
        servers_dict = data.get("servers", {})
        if not servers_dict:
            yield event.plain_result("本群暂无已添加的 MC 服务器。请用 /mcadd <名称> <地址> 添加")
            return
        tasks = {}
        for sname, info in servers_dict.items():
            host = info.get("host", "")
            port = str(info.get("port", "") or "")
            tasks[sname] = asyncio.create_task(self._get_mc_server_status(host, port))
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
            yield event.plain_result(self._format_server_status(sname, host, port, status))
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
            yield event.plain_result(self._format_server_status(sname, host, port, s))

    @filter.command("mcget", desc="查询单个服务器详情")
    async def cmd_mcget(self, event: AstrMessageEvent, name: str = ""):
        if not name:
            yield event.plain_result("用法: /mcget <服务器名称>")
            return
        gid = self._get_group_id(event)
        data = self._get_group_serv_data(gid)
        servers_dict = data.get("servers", {})
        info = servers_dict.get(name)
        if not info:
            yield event.plain_result(f"未找到服务器: {name}")
            return
        host = info.get("host", "")
        port = str(info.get("port", "") or "")
        status = await self._get_mc_server_status(host, port)
        yield event.plain_result(self._format_server_status(name, host, port, status))

    @filter.command("mclist", desc="列出所有MC服务器")
    async def cmd_mclist(self, event: AstrMessageEvent):
        gid = self._get_group_id(event)
        data = self._get_group_serv_data(gid)
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

    @filter.command("mcadd", desc="添加MC服务器")
    async def cmd_mcadd(self, event: AstrMessageEvent, name: str = "", addr: str = ""):
        if not self.is_allowed(event):
            yield event.plain_result("仅管理员可添加服务器")
            return
        if not name or not addr:
            yield event.plain_result("用法: /mcadd <名称> <地址[:端口]>")
            return
        gid = self._get_group_id(event)
        data = self._get_group_serv_data(gid)
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
        self._save_group_serv_data(gid, data)
        display_addr = f"{host}:{port}" if port else host
        yield event.plain_result(f"✅ 已添加服务器: {name} ({display_addr})")

    @filter.command("mcdel", desc="删除MC服务器")
    async def cmd_mcdel(self, event: AstrMessageEvent, name: str = ""):
        if not self.is_allowed(event):
            yield event.plain_result("仅管理员可删除服务器")
            return
        if not name:
            yield event.plain_result("用法: /mcdel <服务器名称>")
            return
        gid = self._get_group_id(event)
        data = self._get_group_serv_data(gid)
        if name not in data.get("servers", {}):
            yield event.plain_result(f"没有叫 {name} 的服务器")
            return
        del data["servers"][name]
        self._save_group_serv_data(gid, data)
        yield event.plain_result(f"✅ 已删除服务器: {name}")

    @filter.command("mcup", desc="更新MC服务器")
    async def cmd_mcup(self, event: AstrMessageEvent, name: str = "", new_name: str = "", new_addr: str = ""):
        if not self.is_allowed(event):
            yield event.plain_result("仅管理员可更新服务器")
            return
        if not name:
            yield event.plain_result("用法: /mcup <名称> [新名称] [新地址]")
            return
        gid = self._get_group_id(event)
        data = self._get_group_serv_data(gid)
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
        self._save_group_serv_data(gid, data)
        yield event.plain_result(f"✅ 已更新服务器: {name}")

    @filter.command("mcshare", desc="共享服务器到其他群")
    async def cmd_mcshare(self, event: AstrMessageEvent, name: str = "", target_gid: str = ""):
        if not self.is_admin(str(event.get_sender_id())):
            yield event.plain_result("仅超级管理员可共享服务器")
            return
        if not name or not target_gid:
            yield event.plain_result("用法: /mcshare <名称> <目标群ID>")
            return
        gid = self._get_group_id(event)
        src = self._get_group_serv_data(gid)
        if name not in src.get("servers", {}):
            yield event.plain_result(f"本群没有叫 {name} 的服务器")
            return
        dst = self._get_group_serv_data(target_gid)
        dst.setdefault("servers", {})
        dst["servers"][name] = src["servers"][name]
        self._save_group_serv_data(target_gid, dst)
        yield event.plain_result(f"✅ 已将服务器 {name} 共享到群 {target_gid}")

    @filter.command("mcunshare", desc="取消共享")
    async def cmd_mcunshare(self, event: AstrMessageEvent, name: str = "", target_gid: str = ""):
        if not self.is_admin(str(event.get_sender_id())):
            yield event.plain_result("仅超级管理员可取消共享")
            return
        if not name or not target_gid:
            yield event.plain_result("用法: /mcunshare <名称> <目标群ID>")
            return
        dst = self._get_group_serv_data(target_gid)
        if name not in dst.get("servers", {}):
            yield event.plain_result(f"目标群没有叫 {name} 的服务器")
            return
        del dst["servers"][name]
        self._save_group_serv_data(target_gid, dst)
        yield event.plain_result(f"✅ 已取消共享服务器 {name}（群 {target_gid}）")

    @filter.command("mccleanup", desc="清理失效服务器")
    async def cmd_mccleanup(self, event: AstrMessageEvent):
        if not self.is_allowed(event):
            yield event.plain_result("仅管理员可清理")
            return
        if self.query_cleanup_days <= 0:
            yield event.plain_result("自动清理已禁用")
            return
        gid = self._get_group_id(event)
        data = self._get_group_serv_data(gid)
        cutoff = int(time.time()) - self.query_cleanup_days * 86400
        deleted = []
        for sname, info in list(data.get("servers", {}).items()):
            if info.get("last_success_time", 0) < cutoff:
                del data["servers"][sname]
                deleted.append(sname)
        self._save_group_serv_data(gid, data)
        if deleted:
            yield event.plain_result(f"✅ 已清理 {len(deleted)} 个失效服务器: {', '.join(deleted)}")
        else:
            yield event.plain_result("没有需要清理的服务器")

    @filter.command("mcset", desc="设置查询显示项")
    async def cmd_mcset(self, event: AstrMessageEvent, *args):
        if not self.is_allowed(event):
            yield event.plain_result("仅管理员可设置")
            return
            return
        args = list(args)
        if not args:
            yield event.plain_result("用法: /mcset <项名> <0|1>  项名: 地址/版本/延迟/在线数量/玩家详细")
            return
        mapping = {
            "地址": "show_address_port", "addr": "show_address_port", "端口": "show_address_port",
            "版本": "show_version", "version": "show_version",
            "延迟": "show_latency", "延时": "show_latency", "ping": "show_latency",
            "在线数量": "show_online_count", "online": "show_online_count",
            "玩家详细": "show_players_detail", "players": "show_players_detail",
        }
        key = mapping.get(str(args[0]).strip())
        val = None
        if key is None and len(args) >= 2:
            key = mapping.get(str(args[1]).strip())
            val = str(args[0]).strip()
        elif key is not None and len(args) >= 2:
            val = str(args[1]).strip()
        if key is None:
            yield event.plain_result(f"未知配置项: {args[0]}。可选: 地址/版本/延迟/在线数量/玩家详细")
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
        setattr(self, attr_map[key], val == "1")
        yield event.plain_result(f"✅ 已设置 {key} = {'显示' if val == '1' else '隐藏'}")

    @filter.command("onlinetime", desc="查看玩家在线时长")
    async def cmd_onlinetime(self, event: AstrMessageEvent, player: str = ""):
        if not self.tracker_enabled:
            yield event.plain_result("在线时长监控未开启")
            return
        if not player:
            ranking = self.db.get_online_time_ranking(15)
            if not ranking:
                yield event.plain_result("暂无在线时长数据")
                return
            lines = ["📊 在线时长排行:"]
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
        else:
            secs = self.db.get_player_total_seconds(player)
            if secs <= 0:
                yield event.plain_result(f"未找到玩家 {player} 的数据")
                return
            mins = secs // 60
            hours = mins // 60
            yield event.plain_result(f"🎮 {player}: {hours}时{mins%60}分")

    # ==============================================================
    # 玩家数据库命令
    # ==============================================================
    @filter.command("bind", desc="绑定MC账号")
    async def cmd_bind(self, event: AstrMessageEvent, mc_id: str = ""):
        if not self.pdb_enabled:
            yield event.plain_result("玩家数据库功能未开启")
            return
        if not mc_id:
            yield event.plain_result("用法: /bind <你的MC ID>")
            return
        qq_id = str(event.get_sender_id())
        p = self._ensure_player(qq_id, mc_id)
        if p["mc_id"] and p["mc_id"] != mc_id:
            yield event.plain_result(f"你已绑定 {p['mc_id']}，不能重复绑定")
            return
        self._update_player(qq_id, {"mc_id": mc_id, "last_login": int(time.time())})
        yield event.plain_result(f"✅ 已绑定 MC 账号: {mc_id}\n🎁 获得新玩家奖励 {self.pdb_new_pts} 积分！")

    @filter.command("checkin", desc="每日签到")
    async def cmd_checkin(self, event: AstrMessageEvent):
        if not self.pdb_enabled:
            yield event.plain_result("玩家数据库功能未开启")
            return
        qq_id = str(event.get_sender_id())
        p = self._ensure_player(qq_id)
        today = time.strftime("%Y-%m-%d")
        last = p.get("last_checkin_date", "")
        if last == today:
            yield event.plain_result("你今天已经签到过了！")
            return
        streak = p.get("checkin_streak", 0)
        if last:
            last_dt = time.strptime(last, "%Y-%m-%d")
            today_dt = time.strptime(today, "%Y-%m-%d")
            diff = (time.mktime(today_dt) - time.mktime(last_dt)) / 86400
            if diff <= 1:
                streak += 1
            else:
                streak = 1
        else:
            streak = 1
        pts = self.pdb_checkin_pts + (streak - 1) * self.pdb_streak_bonus
        self._update_player(qq_id, {
            "checkin_streak": streak,
            "last_checkin_date": today,
            "points": p.get("points", 0) + pts,
        })
        yield event.plain_result(f"✅ 签到成功！连续签到 {streak} 天\n💰 +{pts} 积分 | 总积分: {p.get('points', 0) + pts}")

    @filter.command("mystats", desc="查看个人统计")
    async def cmd_mystats(self, event: AstrMessageEvent):
        if not self.pdb_enabled:
            yield event.plain_result("玩家数据库功能未开启")
            return
        qq_id = str(event.get_sender_id())
        p = self._ensure_player(qq_id)
        lines = [
            f"📊 {event.get_sender_name()} 的统计",
            f"MC ID: {p.get('mc_id', '未绑定')}",
            f"💰 积分: {p.get('points', 0)}",
            f"📅 连续签到: {p.get('checkin_streak', 0)} 天",
            f"🕐 首次登录: {time.strftime('%Y-%m-%d', time.localtime(p['first_login'])) if p.get('first_login') else '未知'}",
        ]
        yield event.plain_result("\n".join(lines))

    def _check_comp_blacklist(self, rcon_cmd: str) -> str:
        if not self.pdb_comp_blacklist:
            return ""
        words = re.findall(r"\w+", rcon_cmd.lower())
        for banned in self.pdb_comp_blacklist:
            banned_lower = str(banned).lower()
            if banned_lower in words:
                return banned_lower
        return ""

    @filter.command("compensate", desc="申请物品补偿（输入完整RCON命令）", alias={"comp"})
    async def cmd_compensate(self, event: AstrMessageEvent, *args):
        if not self.pdb_enabled or not self.pdb_comp_enabled:
            yield event.plain_result("物品补偿功能未开启")
            return
        if not self.is_allowed(event):
            yield event.plain_result("⚠️ 仅白名单用户可使用物品补偿申请")
            return
        qq_id = str(event.get_sender_id())
        p = self._ensure_player(qq_id)
        if not p.get("mc_id"):
            yield event.plain_result("请先用 /bind 绑定 MC 账号")
            return
        rcon_cmd = " ".join(str(a) for a in args).strip()
        if not rcon_cmd:
            yield event.plain_result("用法: /comp <完整RCON命令>\n例: /comp give PlayerName diamond 64")
            return
        banned = self._check_comp_blacklist(rcon_cmd)
        if banned:
            yield event.plain_result(f"⚠️ 命令中包含禁止物品 [{banned}]，申请自动驳回")
            return
        gid = self._get_group_id(event)
        desc = f"{p['mc_id']} 申请: {rcon_cmd}"
        comp_id = self.db.add_compensation(qq_id, p["mc_id"], gid, rcon_cmd, desc)
        if self.pdb_comp_admin:
            yield event.plain_result(f"📝 补偿申请已提交 (#{comp_id})\n命令: {rcon_cmd}\n请等待管理员审批")
        else:
            self.db.update_compensation(comp_id, "approved")
            yield event.plain_result(f"✅ 补偿申请已自动通过 (#{comp_id})\n命令: {rcon_cmd}")

    @filter.command("comp_list", desc="查看补偿申请列表")
    async def cmd_comp_list(self, event: AstrMessageEvent):
        if not self.is_allowed(event):
            yield event.plain_result("仅管理员可查看")
            return
        pending = self.db.get_pending_compensations()
        if not pending:
            yield event.plain_result("暂无待处理的补偿申请")
            return
        lines = ["📋 待处理补偿申请:"]
        for c in pending[:10]:
            lines.append(f"  #{c['id']} {c['mc_id']}({c['qq_id']}): {c.get('rcon_cmd', c.get('description', ''))[:60]}")
        lines.append("使用 /comp_approve <ID> 批准 或 /comp_reject <ID> 拒绝")
        yield event.plain_result("\n".join(lines))

    @filter.command("comp_approve", desc="批准补偿并执行RCON")
    async def cmd_comp_approve(self, event: AstrMessageEvent, comp_id: str = ""):
        if not self.is_allowed(event):
            yield event.plain_result("仅管理员可审批")
            return
        try:
            cid = int(comp_id)
        except ValueError:
            yield event.plain_result("用法: /comp_approve <申请ID>")
            return
        comp = self.db.get_compensation(cid)
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
        self.db.update_compensation(cid, "approved")
        yield event.plain_result(f"✅ 已批准 #{cid}，正在执行 `{rcon_cmd}` ...")
        gid = comp.get("group_id", "") or self._get_group_id(event)
        conf = self.group_map.get(gid)
        if not conf:
            confs = self.group_servers.get(gid) if gid else None
            conf = (confs[0] if confs and len(confs) == 1 else None)
        if not conf:
            yield event.plain_result(f"⚠️ 申请所在群未配置服务器，无法自动执行")
            return
        async for msg in self._execute_on_conf(event, conf, rcon_cmd, f"补偿#{cid}"):
            yield msg

    @filter.command("comp_reject", desc="拒绝补偿申请")
    async def cmd_comp_reject(self, event: AstrMessageEvent, comp_id: str = ""):
        if not self.is_allowed(event):
            yield event.plain_result("仅管理员可审批")
            return
        try:
            cid = int(comp_id)
        except ValueError:
            yield event.plain_result("用法: /comp_reject <申请ID>")
            return
        comp = self.db.get_compensation(cid)
        if not comp:
            yield event.plain_result(f"未找到申请 #{cid}")
            return
        self.db.update_compensation(cid, "rejected")
        yield event.plain_result(f"❌ 已拒绝补偿申请 #{cid}")

    # ==============================================================
    # 群服消息互联
    # ==============================================================
    async def _relay_to_mc(self, event: AstrMessageEvent, user_name: str, message: str):
        gid = self._get_group_id(event)
        conf = self.group_map.get(gid)
        if not conf or not conf.get("relay_enabled"):
            return
        if not self.relay_enabled or not self.relay_group_to_mc:
            return
        try:
            fmt = self.relay_fmt_group.replace("{name}", user_name).replace("{msg}", message)
            escaped = json.dumps(fmt)
            cmd = f"tellraw @a {escaped}"
            host = conf.get("rcon_host")
            port = conf.get("rcon_port")
            password = conf.get("rcon_password")
            await rcon_command(host, port, password, cmd)
        except Exception as e:
            logger.debug(f"[mrcon] relay to MC failed: {e}")

    @filter.command("relay", desc="群服消息互联开关")
    async def cmd_relay(self, event: AstrMessageEvent, action: str = ""):
        if not self.is_allowed(event):
            yield event.plain_result("仅管理员可操作")
            return
        gid = self._get_group_id(event)
        conf = self.group_map.get(gid)
        if not conf:
            yield event.plain_result("当前群未配置服务器")
            return
        if action.lower() in ("on", "1", "开启", "启用"):
            conf["relay_enabled"] = True
            yield event.plain_result("✅ 群服消息互联已开启")
        elif action.lower() in ("off", "0", "关闭", "禁用"):
            conf["relay_enabled"] = False
            yield event.plain_result("✅ 群服消息互联已关闭")
        else:
            status = "开启" if conf.get("relay_enabled", False) else "关闭"
            yield event.plain_result(f"当前群服消息互联: {status}\n可用: /relay on | /relay off")

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def _on_group_message(self, event: AstrMessageEvent):
        gid = self._get_group_id(event)
        conf = self.group_map.get(gid)
        if not conf or not conf.get("relay_enabled") or not self.relay_enabled or not self.relay_group_to_mc:
            return
        text = str(getattr(event, "message_str", "") or "")
        if not text or text.startswith("/"):
            return
        user_name = str(event.get_sender_name() or "")
        await self._relay_to_mc(event, user_name, text)

    # ==============================================================
    # 在线列表
    # ==============================================================
    @filter.command("online", desc="查看MC服务器在线玩家")
    async def cmd_online(self, event: AstrMessageEvent):
        gid = self._get_group_id(event)
        confs = self.group_servers.get(gid) if gid else None
        conf = (confs[0] if confs and len(confs) == 1 else (self.group_map.get(gid) if gid else None))
        if not conf:
            yield event.plain_result("当前群未配置服务器")
            return
        online_list = await self._get_online_player_list(conf)
        if not online_list:
            yield event.plain_result("当前无在线玩家")
            return
        srv_name = conf.get("server_name", "")
        if self.query_render_image:
            yield event.plain_result(f"🖥️ {srv_name} 在线玩家 ({len(online_list)}人)\n{chr(10).join(f'  • {p}' for p in online_list)}")
        else:
            lines = [f"🖥️ {srv_name} 在线玩家 ({len(online_list)}人)"]
            for p in online_list:
                lines.append(f"  • {p}")
            yield event.plain_result("\n".join(lines))

    # ==============================================================
    # RCON 命令（原有 + mcing 迁移）
    # ==============================================================
    @filter.command("mrcon", desc="将后续文本原样转发到 RCON 控制台", alias={"mcmd"})
    async def mrcon(self, event: AstrMessageEvent, text: str = "", rest=None):
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
        full_cmd = self._extract_full_after_cmd(event, params_tail)
        if not full_cmd:
            yield event.plain_result(f"你好, {named}, 请输入要转发的命令。")
            return
        gid = self._get_group_id(event)
        servers = self.group_servers.get(gid) or []
        conf = (servers[0] if len(servers) == 1 else (self.group_map.get(gid) if gid else None))
        pub_cmds = conf.get("public_commands", []) if conf else []
        vote_enabled = bool(conf.get("vote_enabled", False)) if conf else False
        head = full_cmd.split()[0] if full_cmd else ""
        is_public = (head in pub_cmds) or any(full_cmd.startswith(p) for p in pub_cmds)
        if not is_public and not self.is_allowed(event):
            yield event.plain_result("抱歉，你没有权限执行此操作。")
            return
        if not self.is_admin(str(event.get_sender_id())) and self._match_dangerous(full_cmd):
            yield event.plain_result("该命令被策略禁止执行")
            return
        if conf is None and not servers:
            partial = self.partial_map.get(gid)
            if partial:
                missing = ", ".join(partial.get("missing", []))
                slot = partial.get("slot", "该群槽位")
                yield event.plain_result(f"当前群槽位配置不完整(缺少: {missing})，请在 {slot} 填写完整 RCON 配置。")
            else:
                yield event.plain_result("当前群未配置 RCON 槽位，请管理员在配置中填好地址/端口/密码。")
            return
        if len(servers) > 1:
            key = self._ps_key(event)
            self.pending_select[key] = {
                "cmd": full_cmd,
                "options": servers,
                "deadline": int(time.time()) + max(5, self.select_ttl),
            }
            lines = ["当前群配置了多个 RCON 服务器，请选择编号："]
            for idx, c in enumerate(servers, start=1):
                lines.append(f"{idx}. {c.get('display_name')}")
            lines.append(f"请在 {self.select_ttl} 秒内回复编号（直接发送数字即可），或使用 /rcsel <编号>")
            await event.send(event.plain_result("\n".join(lines)))

            @session_waiter(timeout=self.select_ttl, record_history_chains=False)
            async def select_digit_waiter(controller: SessionController, ev: AstrMessageEvent):
                raw = str(getattr(ev, "message_str", "") or "").strip()
                if not raw.isdigit():
                    return
                try:
                    i = int(raw)
                except Exception:
                    return
                rec = self.pending_select.get(key) or {}
                options = rec.get("options", []) or servers
                if i < 1 or i > len(options):
                    return
                conf = options[i - 1]
                cmd = rec.get("cmd", full_cmd)
                if self._ps_key(ev) != key:
                    return
                try:
                    del self.pending_select[key]
                except Exception:
                    pass
                async for msg in self._execute_on_conf(ev, conf, cmd, f"选择服务器#{i}:{conf.get('display_name') or conf.get('server_name')}"):
                    await ev.send(msg)
                controller.stop()

            try:
                await select_digit_waiter(event)
            except Exception:
                pass

            asyncio.create_task(self._schedule_select_timeout(event, key))
            return
        if is_public and vote_enabled:
            gid2 = gid
            rec = self.exec_votes.get(gid2)
            if rec:
                yield event.plain_result("当前已有进行中的命令投票")
                return
            self.exec_votes[gid2] = {
                "cmd": full_cmd,
                "votes": {},
                "threshold": int(conf.get("vote_threshold", 3)),
                "ttl": int(conf.get("vote_ttl", 60)),
                "min_agree": int(conf.get("vote_min_agree_on_timeout", 1)),
                "tie_strategy": str(conf.get("vote_tie_strategy", "fail")),
                "await_admin": False,
            }
            async def settle_vote():
                await asyncio.sleep(self.exec_votes[gid2]["ttl"])
                rec2 = self.exec_votes.get(gid2)
                if not rec2:
                    return
                agree = sum(1 for v in rec2["votes"].values() if v)
                disagree = sum(1 for v in rec2["votes"].values() if not v)
                thr = rec2["threshold"]
                cmd2 = rec2["cmd"]
                if agree >= thr:
                    del self.exec_votes[gid2]
                    async for msg in self.execute_and_reply(event, cmd2, "投票通过执行"):
                        await event.send(msg)
                    return
                if agree >= rec2["min_agree"] and agree == disagree:
                    st = rec2["tie_strategy"].lower()
                    if st == "pass":
                        del self.exec_votes[gid2]
                        async for msg in self.execute_and_reply(event, cmd2, "平票通过执行"):
                            await event.send(msg)
                        return
                    if st == "admin":
                        rec2["await_admin"] = True
                        await event.send(event.plain_result(f"投票时间到（平票，等待管理员裁决）！命令 `{cmd2}`"))
                        at = int(conf.get("admin_decide_ttl", 120))
                        async def admin_timeout():
                            await asyncio.sleep(at)
                            rec3 = self.exec_votes.get(gid2)
                            if not rec3 or not rec3.get("await_admin", False):
                                return
                            cmd3 = rec3["cmd"]
                            del self.exec_votes[gid2]
                            await event.send(event.plain_result(f"管理员裁决超时！命令 `{cmd3}` 被否决"))
                        asyncio.create_task(admin_timeout())
                    else:
                        del self.exec_votes[gid2]
                        await event.send(event.plain_result(f"投票时间到（平票，策略=否决）！命令 `{cmd2}` 被否决"))
                else:
                    del self.exec_votes[gid2]
                    await event.send(event.plain_result(f"投票时间到！命令 `{cmd2}` 被否决"))
            asyncio.create_task(settle_vote())
            return
        async for msg in self.execute_and_reply(event, full_cmd, "命令转发"):
            yield msg

    @filter.command("rcsel", desc="选择 RCON 服务器编号", alias={"rc选", "rcserver"})
    async def rcsel(self, event: AstrMessageEvent, index: str = ""):
        key = self._ps_key(event)
        rec = self.pending_select.get(key)
        if not rec:
            yield event.plain_result("当前没有待选择的命令")
            return
        if int(time.time()) > int(rec.get("deadline", 0)):
            del self.pending_select[key]
            yield event.plain_result("选择超时，请重新发送命令")
            return
        try:
            i = int(str(index).strip())
        except Exception:
            yield event.plain_result("请输入有效编号，如 /rcsel 1")
            return
        options = rec.get("options", [])
        if i < 1 or i > len(options):
            yield event.plain_result("编号超出范围，请重新选择")
            return
        conf = options[i - 1]
        cmd = rec.get("cmd", "")
        del self.pending_select[key]
        async for msg in self._execute_on_conf(event, conf, cmd, f"选择服务器#{i}:{conf.get('display_name') or conf.get('server_name')}"):
            yield msg

    @filter.command("rc赞同", desc="对当前命令投票赞同")
    async def rc_agree(self, event: AstrMessageEvent):
        gid = self._get_group_id(event)
        rec = self.exec_votes.get(gid)
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
            del self.exec_votes[gid]
            async for msg in self.execute_and_reply(event, cmd, "投票通过执行"):
                yield msg
            return
        yield event.plain_result(f"命令 `{rec['cmd']}` 投票进度：赞同({agree}/{threshold}) 反对({disagree}/{threshold})")

    @filter.command("rc反对", desc="对当前命令投票反对")
    async def rc_disagree(self, event: AstrMessageEvent):
        gid = self._get_group_id(event)
        rec = self.exec_votes.get(gid)
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
            del self.exec_votes[gid]
            yield event.plain_result(f"命令 `{cmd}` 投票被否决")
            return
        yield event.plain_result(f"命令 `{rec['cmd']}` 投票进度：赞同({agree}/{threshold}) 反对({disagree}/{threshold})")

    @filter.command("rc通过", desc="管理员裁决通过")
    async def rc_admin_pass(self, event: AstrMessageEvent):
        if not self.is_admin(str(event.get_sender_id())):
            yield event.plain_result("仅管理员可用")
            return
        gid = self._get_group_id(event)
        rec = self.exec_votes.get(gid)
        if not rec:
            yield event.plain_result("当前没有进行中的命令投票")
            return
        if not rec.get("await_admin", False):
            yield event.plain_result("当前不需要管理员裁决")
            return
        cmd = rec["cmd"]
        async for msg in self.execute_and_reply(event, cmd, "管理员裁决执行"):
            yield msg
        del self.exec_votes[gid]

    @filter.command("rc否决", desc="管理员裁决否决")
    async def rc_admin_reject(self, event: AstrMessageEvent):
        if not self.is_admin(str(event.get_sender_id())):
            yield event.plain_result("仅管理员可用")
            return
        gid = self._get_group_id(event)
        rec = self.exec_votes.get(gid)
        if not rec:
            yield event.plain_result("当前没有进行中的命令投票")
            return
        if not rec.get("await_admin", False):
            yield event.plain_result("当前不需要管理员裁决")
            return
        cmd = rec["cmd"]
        del self.exec_votes[gid]
        yield event.plain_result(f"管理员已裁决否决！命令 `{cmd}` 被否决")

    @filter.command("rcmacro", desc="执行宏命令", alias={"rcm"})
    async def rcmacro(self, event: AstrMessageEvent, name: str = "", args: str = ""):
        sender_qq = str(event.get_sender_id())
        user_name = event.get_sender_name()
        named = f"{user_name}({sender_qq})"
        if not self.is_allowed(event):
            yield event.plain_result("抱歉，你没有权限执行此操作。")
            return
        if not name:
            yield event.plain_result(f"你好, {named}, 请输入宏名称。")
            return
        cmds = self.macros.get(name)
        if not cmds:
            yield event.plain_result("未找到该宏定义")
            return
        parts = [p for p in str(args).split() if p]
        key = self._rate_key(event)
        lock = self._acquire_lock(key)
        async with lock:
            for c in cmds:
                cc = c
                for idx, val in enumerate(parts):
                    cc = cc.replace("{" + str(idx) + "}", val)
                if not self.is_admin(str(event.get_sender_id())) and self._match_dangerous(cc):
                    yield event.plain_result("该宏中的命令被策略禁止执行")
                    return
                async for msg in self.execute_and_reply(event, cc, f"宏:{name}"):
                    yield msg

    @filter.command("rcscript", desc="执行脚本文件", alias={"rcs"})
    async def rcscript(self, event: AstrMessageEvent, filename: str = ""):
        sender_qq = str(event.get_sender_id())
        user_name = event.get_sender_name()
        named = f"{user_name}({sender_qq})"
        if not self.is_allowed(event):
            yield event.plain_result("抱歉，你没有权限执行此操作。")
            return
        if not filename:
            yield event.plain_result(f"你好, {named}, 请输入脚本文件名。")
            return
        path = os.path.join(self.scripts_dir, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = [ln.strip() for ln in f.readlines()]
        except Exception as e:
            yield event.plain_result(f"脚本读取失败：{e}")
            return
        key = self._rate_key(event)
        lock = self._acquire_lock(key)
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
                if not self.is_admin(str(event.get_sender_id())) and self._match_dangerous(ln):
                    yield event.plain_result("脚本中的命令被策略禁止执行")
                    return
                async for msg in self.execute_and_reply(event, ln, f"脚本:{filename}"):
                    yield msg