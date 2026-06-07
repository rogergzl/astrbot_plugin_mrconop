import asyncio
import json
import os
import re
import time
from pathlib import Path
from io import BytesIO
from collections import defaultdict

try:
    from PIL import Image as PILImage, ImageDraw, ImageFont
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api.message_components import Plain
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


@register("mrcon", "lindagao", "MC 综合管理插件", "3.11.1")
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

        # ---- Web 管理面板配置 ----
        web_cfg = self.config.get("web_panel", {})
        if not isinstance(web_cfg, dict):
            web_cfg = {}
        self.web_panel_enabled = bool(web_cfg.get("enabled", False))
        self.web_panel_host = str(web_cfg.get("host", "0.0.0.0") or "0.0.0.0")
        self.web_panel_port = int(web_cfg.get("port", 9949) or 9949)
        self.web_panel_password = str(web_cfg.get("password", "") or "")
        self.web_panel_session_timeout = int(web_cfg.get("session_timeout", 600) or 600)
        self._web_panel = None  # 延迟初始化
        self._web_panel_task = None

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
        self.tracker_enabled = bool(tracker_cfg.get("enabled", True))
        self.tracker_interval = int(tracker_cfg.get("poll_interval_seconds", 60) or 60)
        self.tracker_method = str(tracker_cfg.get("query_method", "rcon") or "rcon")
        self.tracker_notify = bool(tracker_cfg.get("notify_enabled", False))
        self.tracker_notify_target = str(tracker_cfg.get("notify_target", "group") or "group")
        self.tracker_notify_intervals = sorted(
            [int(x) for x in (tracker_cfg.get("notify_intervals", [60, 120, 360]) or [])], reverse=True
        )
        self.tracker_kick_enabled = bool(tracker_cfg.get("auto_kick_enabled", False))
        self.tracker_kick_threshold = int(tracker_cfg.get("auto_kick_threshold", 720) or 720)
        self.tracker_kick_reason = str(tracker_cfg.get("auto_kick_reason", "你已连续在线过久，请休息一下！") or "")
        self.tracker_notify_game = bool(tracker_cfg.get("notify_in_game", False))
        self.tracker_game_format = str(tracker_cfg.get("notify_game_format", "§e[在线提醒] {player} 已连续在线 {duration}，注意休息！") or "")
        self.tracker_ban_minutes = int(tracker_cfg.get("auto_kick_ban_minutes", 30) or 30)
        self.ranking_reset_hours = int(tracker_cfg.get("ranking_reset_interval_hours", 0) or 0)  # 0=不自动重置
        self._last_ranking_reset = 0
        self._pending_msgs = {}     # gid → [(msg, group_name)]
        self._last_umo = {}         # gid → unified_msg_origin
        self._tracker_overrides = {}  # gid → {notify_enabled, notify_target, notify_intervals, kick_enabled, kick_threshold, kick_reason}
        self._pending_unbans = {}   # player_key → (unban_time, conf)

        relay_cfg = self.config.get("relay", {})
        if not isinstance(relay_cfg, dict):
            relay_cfg = {}
        self.relay_enabled = bool(relay_cfg.get("enabled", False))
        self.relay_group_to_mc = bool(relay_cfg.get("group_to_mc", False))
        self.relay_mc_to_group = bool(relay_cfg.get("mc_to_group", False))
        self.relay_fmt_group = str(relay_cfg.get("format_group", "[QQ] {name}: {msg}"))
        self.relay_fmt_mc = str(relay_cfg.get("format_mc", "[MC] {player}: {msg}"))
        self.relay_require_msay = bool(relay_cfg.get("require_msay", False))  # 是否仅允许 /msay 命令互通
        self._relay_overrides = relay_cfg.get("group_settings", {})  # gid → [{server_name, ...}] 从配置持久化加载

        player_db_cfg = self.config.get("player_db", {})
        if not isinstance(player_db_cfg, dict):
            player_db_cfg = {}
        self.pdb_enabled = bool(player_db_cfg.get("enabled", False))
        self.pdb_checkin_pts = int(player_db_cfg.get("checkin_points", 10) or 10)
        self.pdb_streak_bonus = int(player_db_cfg.get("checkin_streak_bonus", 2) or 2)
        self.pdb_new_pts = int(player_db_cfg.get("new_player_points", 50) or 50)
        self.pdb_comp_enabled = bool(player_db_cfg.get("compensation_enabled", False))
        self.pdb_comp_whitelist = set(str(x) for x in player_db_cfg.get("compensation_whitelist", []))
        self.pdb_comp_admin = bool(player_db_cfg.get("compensation_require_admin", True))
        self.pdb_comp_blacklist = list(player_db_cfg.get("compensation_blacklist", []))

        # 在线数据库配置
        online_db_cfg = self.config.get("online_db", {})
        if not isinstance(online_db_cfg, dict):
            online_db_cfg = {}
        # 优先从 player_db 读取统一存储配置，回退到 online_db
        pdb_cfg = self.config.get("player_db", {})
        if not isinstance(pdb_cfg, dict):
            pdb_cfg = {}
        def _dbcfg(key, default):
            v = pdb_cfg.get(key)
            if v is not None and v != "":
                return v
            v = online_db_cfg.get(key)
            if v is not None and v != "":
                return v
            return default
        self.online_db_storage_mode = str(_dbcfg("storage_mode", "local"))
        self.online_db_read_source = str(_dbcfg("read_source", "local"))
        self.online_db_ext_type = str(_dbcfg("external_type", "sqlite"))
        self.online_db_ext_host = str(_dbcfg("external_host", ""))
        self.online_db_ext_port = int(_dbcfg("external_port", 0) or 0)
        self.online_db_ext_user = str(_dbcfg("external_user", ""))
        self.online_db_ext_password = str(_dbcfg("external_password", ""))
        self.online_db_ext_database = str(_dbcfg("external_database", ""))
        self.online_db_ext_path = str(_dbcfg("external_db_path", ""))

        self.group_map = {}
        self.group_servers = {}
        self.partial_map = {}
        self.exec_votes = {}
        self.group_locks = {}
        self.rate_state = {}
        self.configured_groups = []
        self.named_server_pool = []
        self.group_names = {}
        self.server_templates = []
        self.cmd_templates = []
        self.online_triggers = []
        self._trigger_cooldowns = {}

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
                    # 新旧格式兼容：旧格式无 enabled 字段，默认启用
                    if isinstance(m, dict) and "enabled" in m:
                        self.macros[name] = {
                            "commands": [str(c) for c in cmds],
                            "enabled": bool(m.get("enabled", True)),
                        }
                    else:
                        self.macros[name] = {
                            "commands": [str(c) for c in cmds],
                            "enabled": True,
                        }

        # 读取群号列表（独立于群服绑定）
        groups_cfg = self.config.get("groups", [])
        if isinstance(groups_cfg, list):
            self.configured_groups = [str(g).strip() for g in groups_cfg if str(g).strip()]
        logger.info(f"[mrcon] 已配置群号列表: {self.configured_groups}")

        # 读取群号显示名称
        gn = self.config.get("group_names", {})
        if isinstance(gn, dict):
            self.group_names = {str(k): str(v) for k, v in gn.items()}
        logger.info(f"[mrcon] 群名称: {self.group_names}")

        # 读取服务器配置模板
        self.server_templates_path = os.path.join(self.plugin_data_dir, "server_templates.json")
        try:
            if os.path.exists(self.server_templates_path):
                with open(self.server_templates_path, "r", encoding="utf-8") as f:
                    self.server_templates = json.load(f)
                    if not isinstance(self.server_templates, list):
                        self.server_templates = []
            logger.info(f"[mrcon] 已加载 {len(self.server_templates)} 个服务器模板")
        except Exception as e:
            logger.warning(f"[mrcon] 服务器模板加载失败: {e}")
            self.server_templates = []

        # 读取参数化命令模板（首次自动创建示例模板）
        self.cmd_templates_path = os.path.join(self.plugin_data_dir, "cmd_templates.json")
        try:
            if os.path.exists(self.cmd_templates_path):
                with open(self.cmd_templates_path, "r", encoding="utf-8") as f:
                    self.cmd_templates = json.load(f)
                    if not isinstance(self.cmd_templates, list):
                        self.cmd_templates = []
            if not self.cmd_templates:
                self.cmd_templates = [
                    {
                        "name": "设置属性",
                        "desc": "添加玩家属性修饰符 (移速/攻击力/生命等)",
                        "enabled": False,
                        "commands": [
                            "/attribute {player} {attribute} modifier add {uuid} {modifier_name} {value} {operation}"
                        ],
                        "params": [
                            {"key": "player", "label": "玩家ID", "default": ""},
                            {"key": "attribute", "label": "属性类型", "default": "minecraft:generic.movement_speed"},
                            {"key": "uuid", "label": "修饰符UUID", "default": ""},
                            {"key": "modifier_name", "label": "修饰符名称", "default": "bonus"},
                            {"key": "value", "label": "数值", "default": "0.1"},
                            {"key": "operation", "label": "运算方式(add/multiply_base/multiply_total)", "default": "add"},
                        ],
                    },
                    {
                        "name": "查询UUID",
                        "desc": "获取玩家的UUID (可复制到属性命令中使用)",
                        "enabled": False,
                        "commands": ["data get entity {player} UUID"],
                        "params": [
                            {"key": "player", "label": "玩家ID", "default": ""}
                        ],
                    },
                    {
                        "name": "设置移速",
                        "desc": "快速设置玩家基础移动速度",
                        "enabled": False,
                        "commands": [
                            "/attribute {player} minecraft:generic.movement_speed base set {speed}"
                        ],
                        "params": [
                            {"key": "player", "label": "玩家ID", "default": ""},
                            {"key": "speed", "label": "速度值 (默认0.1)", "default": "0.1"},
                        ],
                    },
                    {
                        "name": "睡觉比例",
                        "desc": "设置跳过夜晚所需的睡觉玩家百分比",
                        "enabled": False,
                        "commands": ["/gamerule playersSleepingPercentage {ratio}"],
                        "params": [
                            {"key": "ratio", "label": "比例 (1-100)", "default": "50"}
                        ],
                    },
                ]
                self._save_cmd_tpls_init()
            logger.info(f"[mrcon] 已加载 {len(self.cmd_templates)} 个命令模板")
        except Exception as e:
            logger.warning(f"[mrcon] 命令模板加载失败: {e}")
            self.cmd_templates = []

        # 读取玩家上线触发器（首次自动创建示例）
        self.online_triggers_path = os.path.join(self.plugin_data_dir, "online_triggers.json")
        try:
            if os.path.exists(self.online_triggers_path):
                with open(self.online_triggers_path, "r", encoding="utf-8") as f:
                    self.online_triggers = json.load(f)
                    if not isinstance(self.online_triggers, list):
                        self.online_triggers = []
            if not self.online_triggers:
                self.online_triggers = [
                    {
                        "name": "自动设置移速",
                        "enabled": False,
                        "player": "",
                        "match_type": "exact",
                        "commands": [
                            "/attribute {player} minecraft:generic.movement_speed base set {speed}"
                        ],
                        "cooldown_seconds": 300,
                        "note": "玩家上线时自动设置移动速度 (填写玩家名后启用)",
                    },
                    {
                        "name": "上线欢迎",
                        "enabled": False,
                        "player": "",
                        "match_type": "exact",
                        "commands": [
                            "/tellraw {player} {\"text\":\"欢迎回来! 今日在线奖励已发放\"}"
                        ],
                        "cooldown_seconds": 3600,
                        "note": "玩家上线时发送欢迎消息",
                    },
                ]
                self._save_online_triggers()
            logger.info(f"[mrcon] 已加载 {len(self.online_triggers)} 个上线触发器")
        except Exception as e:
            logger.warning(f"[mrcon] 上线触发器加载失败: {e}")
            self.online_triggers = []

        # 读取脚本启停设置
        self.script_settings_path = os.path.join(self.plugin_data_dir, "script_settings.json")
        self.script_settings = {}  # {filename: {"enabled": bool}}
        try:
            if os.path.exists(self.script_settings_path):
                with open(self.script_settings_path, "r", encoding="utf-8") as f:
                    self.script_settings = json.load(f)
                    if not isinstance(self.script_settings, dict):
                        self.script_settings = {}
            logger.info(f"[mrcon] 已加载脚本启停设置 ({len(self.script_settings)} 项)")
        except Exception as e:
            logger.warning(f"[mrcon] 脚本启停设置加载失败: {e}")
            self.script_settings = {}

        # 读取快捷命令启停设置
        self.quick_cmd_settings_path = os.path.join(self.plugin_data_dir, "quick_cmd_settings.json")
        self.quick_cmd_settings = {}  # {cmd_text: {"enabled": bool}}
        try:
            if os.path.exists(self.quick_cmd_settings_path):
                with open(self.quick_cmd_settings_path, "r", encoding="utf-8") as f:
                    self.quick_cmd_settings = json.load(f)
                    if not isinstance(self.quick_cmd_settings, dict):
                        self.quick_cmd_settings = {}
            logger.info(f"[mrcon] 已加载快捷命令启停设置 ({len(self.quick_cmd_settings)} 项)")
        except Exception as e:
            logger.warning(f"[mrcon] 快捷命令启停设置加载失败: {e}")
            self.quick_cmd_settings = {}

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
            # 新格式：纯字符串 = 未绑定的服务器名称
            if isinstance(srv, str):
                name = srv.strip()
                if name:
                    self.named_server_pool.append(name)
                    logger.info(f"[mrcon] 未绑定服务器名称: {name}")
                continue
            # 旧格式：dict = 完整服务器配置（含 group_id）
            if not isinstance(srv, dict):
                continue
            gid = str(srv.get("group_id", "") or "").strip()
            name = str(srv.get("name", "") or srv.get("server_name", "") or "").strip()
            # 跳过无效条目
            if not gid or not name:
                if gid:
                    self.partial_map[gid] = {"missing": ["缺少 group_id 或 name"], "slot": f"服务器 #{i}"}
                continue

            host = srv.get("rcon_host", "") or ""
            port = srv.get("rcon_port", 25575)
            password = srv.get("rcon_password", "") or ""
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

            try:
                port = int(port)
                game_port_int = int(game_port)
            except Exception:
                port = 25575
                game_port_int = 25565

            web_mgmt = bool(srv.get("web_management_enabled", True))
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
                "web_management_enabled": web_mgmt,
                "slot_index": i,
                "server_name": name,
                "display_name": name,
            }
            logger.info(
                f"[mrcon] 加载服务器 gid={gid} name={name} "
                f"host={host} port={port} web_mgmt={web_mgmt}"
            )
            self.group_map[gid] = conf
            arr = self.group_servers.get(gid) or []
            arr.append(conf)
            self.group_servers[gid] = arr

        # 启动摘要：列出所有群及其服务器的 web_management_enabled 状态
        total_servers = sum(len(srvs) for srvs in self.group_servers.values())
        logger.info(
            f"[mrcon] 服务器加载完成: {len(self.group_servers)} 个群, "
            f"{total_servers} 台已绑定服务器, "
            f"{len(self.named_server_pool)} 个未绑定名称"
        )
        if self.named_server_pool:
            logger.info(f"[mrcon] 未绑定服务器名称: {self.named_server_pool}")
        for gid, srvs in self.group_servers.items():
            for s in srvs:
                logger.info(
                    f"[mrcon]   gid={gid} name={s.get('server_name','?')} "
                    f"web_mgmt={s.get('web_management_enabled')} "
                    f"host={s.get('rcon_host','?')}"
                )

        # 兼容旧版 string 格式 config，转换为 list 格式
        if isinstance(servers_raw, str) and servers_raw.strip():
            try:
                self.config["servers"] = servers  # servers 已通过 json.loads 解析为 list
                self.config.save_config()
                logger.info("[mrcon] 已将 servers 配置从 string 格式迁移到 list 格式")
            except Exception as e:
                logger.warning(f"[mrcon] servers 配置格式迁移失败: {e}")

        self.mcserv_path = os.path.join(self.plugin_data_dir, "mc_servers.json")
        self.player_db_path = os.path.join(self.plugin_data_dir, "player_db.json")
        self.online_sessions_path = os.path.join(self.plugin_data_dir, "online_sessions.json")
        self.db_path = os.path.join(self.plugin_data_dir, "mrcon.db")
        self.db = Database(self.db_path)
        self.db.set_storage_mode(self.online_db_storage_mode, self.online_db_read_source)
        # 配置外部数据库
        if self.online_db_storage_mode in ("external", "dual") and self.online_db_ext_path:
            self.db.configure_external(
                ext_type=self.online_db_ext_type,
                host=self.online_db_ext_host,
                port=self.online_db_ext_port,
                user=self.online_db_ext_user,
                password=self.online_db_ext_password,
                database=self.online_db_ext_database,
                ext_db_path=self.online_db_ext_path,
            )
        self.db.migrate_from_json(self.player_db_path, self.online_sessions_path)
        self._online_cache = {}
        self._last_online_refresh = 0
        self._tracker_task = None

    async def initialize(self):
        try:
            os.makedirs(self.plugin_data_dir, exist_ok=True)
            os.makedirs(self.scripts_dir, exist_ok=True)
        except Exception:
            pass
        if self.tracker_enabled:
            self._tracker_task = asyncio.create_task(self._online_tracker_loop())
        # 从数据库恢复在线状态
        try:
            state_rows = self.db.load_online_state()
            for row in state_rows:
                sn = row.get("server_name", "")
                pn = row.get("player_name", "")
                gid = str(row.get("gid", ""))
                la = row.get("login_at", 0)
                if sn and pn:
                    sid = f"{sn}:{pn}"
                    self._online_cache[sid] = {
                        "login_at": la, "player": pn, "server": sn,
                        "gid": gid, "notified": set(), "kicked": False,
                    }
            logger.info(f"[mrcon] 从数据库恢复了 {len(state_rows)} 条在线状态")
        except Exception as e:
            logger.warning(f"[mrcon] 加载在线状态失败: {e}")
        # 启动 Web 管理面板
        if self.web_panel_enabled:
            try:
                from .web_panel import WebServer
                self._web_panel = WebServer(self, host=self.web_panel_host, port=self.web_panel_port, session_timeout=self.web_panel_session_timeout)
                if self.web_panel_password and not self._web_panel.is_password_configured():
                    self._web_panel.set_password(self.web_panel_password)
                self._web_panel_task = asyncio.create_task(self._web_panel.run())
            except Exception as e:
                logger.warning(f"[mrcon] Web 面板启动失败: {e}")

    async def terminate(self):
        if self._web_panel_task:
            self._web_panel_task.cancel()
            try:
                await asyncio.wait_for(self._web_panel_task, timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                pass
            self._web_panel_task = None
        if self._web_panel:
            try:
                await self._web_panel.stop()
            except Exception:
                pass
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

    def _audit(self, event: AstrMessageEvent, cmd: str, ok: bool, resp: str, category: str = "cmd"):
        try:
            rec = {
                "time": int(time.time()),
                "category": category,
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

    def _audit_web(self, op: str, detail: str = "", ok: bool = True, operator: str = "web"):
        """Web 操作审计日志"""
        try:
            rec = {
                "time": int(time.time()),
                "category": "web",
                "sender_id": "0",
                "sender_name": operator,
                "group_id": "",
                "cmd": op,
                "ok": bool(ok),
                "resp": str(detail)[:2000],
            }
            os.makedirs(self.plugin_data_dir, exist_ok=True)
            with open(self.audit_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _audit_web_cmd(self, op: str, detail: str = "", ok: bool = True, operator: str = "web"):
        """Web 命令转发审计"""
        try:
            rec = {
                "time": int(time.time()),
                "category": "web_rcon",
                "sender_id": "0",
                "sender_name": operator,
                "group_id": "",
                "cmd": op,
                "ok": bool(ok),
                "resp": str(detail)[:2000],
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
        cmd_names = ["/mrcon", "/执行", "/mcmd", "mrcon", "执行", "mcmd"]
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
        patterns = [r"^.*?(?:/mrcon|mrcon|/执行|执行|/mcmd|mcmd)\s+(.+)$"]
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

    def _save_cmd_tpls_init(self):
        """首次初始化命令模板文件"""
        try:
            tp = self.cmd_templates_path
            os.makedirs(os.path.dirname(tp), exist_ok=True)
            with open(tp, "w", encoding="utf-8") as f:
                json.dump(self.cmd_templates, f, ensure_ascii=False, indent=2)
            logger.info("[mrcon] 已创建示例命令模板文件")
        except Exception as e:
            logger.warning(f"[mrcon] 命令模板文件创建失败: {e}")

    def _save_online_triggers(self):
        """保存上线触发器"""
        try:
            tp = self.online_triggers_path
            os.makedirs(os.path.dirname(tp), exist_ok=True)
            with open(tp, "w", encoding="utf-8") as f:
                json.dump(self.online_triggers, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[mrcon] 保存上线触发器失败: {e}")

    def _save_script_settings(self):
        """保存脚本启停设置"""
        try:
            sp = self.script_settings_path
            os.makedirs(os.path.dirname(sp), exist_ok=True)
            with open(sp, "w", encoding="utf-8") as f:
                json.dump(self.script_settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[mrcon] 保存脚本启停设置失败: {e}")

    def _save_quick_cmd_settings(self):
        """保存快捷命令启停设置"""
        try:
            sp = self.quick_cmd_settings_path
            os.makedirs(os.path.dirname(sp), exist_ok=True)
            with open(sp, "w", encoding="utf-8") as f:
                json.dump(self.quick_cmd_settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[mrcon] 保存快捷命令启停设置失败: {e}")

    async def _check_online_triggers(self, player: str, srv_name: str, gid: str, conf: dict, now: int):
        for t in self.online_triggers:
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
            # 检查冷却
            cd_sec = int(t.get("cooldown_seconds", 0))
            if cd_sec > 0:
                cd_map = self._trigger_cooldowns.setdefault(t["name"], {})
                last = cd_map.get(player, 0)
                if now - last < cd_sec:
                    continue
                cd_map[player] = now
            # 执行命令
            cmds = t.get("commands", [])
            if not isinstance(cmds, list):
                cmds = [str(cmds)]
            for cmd in cmds:
                cmd = str(cmd).replace("{player}", player).replace("{PLAYER}", player)
                try:
                    resp = await rcon_command(
                        conf["rcon_host"], int(conf["rcon_port"]),
                        conf["rcon_password"], cmd,
                    )
                    logger.info(f"[mrcon] 触发器 [{t['name']}] 执行: {cmd} -> {resp[:80]}")
                except Exception as e:
                    logger.warning(f"[mrcon] 触发器 [{t['name']}] 失败: {cmd} -> {e}")

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

    def _get_tracker_config(self, gid: str) -> dict:
        """获取某群的在线监控配置，优先群内覆盖，否则回退全局"""
        override = self._tracker_overrides.get(str(gid), {})
        return {
            "notify": override.get("notify_enabled", self.tracker_notify),
            "notify_target": override.get("notify_target", self.tracker_notify_target),
            "notify_intervals": override.get("notify_intervals", self.tracker_notify_intervals),
            "notify_game": override.get("notify_in_game", self.tracker_notify_game),
            "notify_game_format": override.get("notify_game_format", self.tracker_game_format),
            "kick_enabled": override.get("kick_enabled", self.tracker_kick_enabled),
            "kick_threshold": override.get("kick_threshold", self.tracker_kick_threshold),
            "kick_reason": override.get("kick_reason", self.tracker_kick_reason),
            "ban_minutes": override.get("ban_minutes", self.tracker_ban_minutes),
        }

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
                    tcfg = self._get_tracker_config(gid)
                    online = await self._get_online_player_list(conf)
                    srv_name = conf.get("server_name", "unknown")
                    # 检查到期解封
                    for key in list(self._pending_unbans.keys()):
                        ub = self._pending_unbans[key]
                        if now >= ub["unban_at"]:
                            try:
                                await rcon_command(
                                    ub["conf"]["rcon_host"], ub["conf"]["rcon_port"],
                                    ub["conf"]["rcon_password"], f"pardon {ub['player']}",
                                )
                                logger.info(f"[mrcon] 自动解封 {ub['player']} @ {ub['conf'].get('server_name', '?')}")
                            except Exception:
                                pass
                            del self._pending_unbans[key]
                    for player in online:
                        sid = f"{srv_name}:{player}"
                        if sid not in self._online_cache:
                            self._online_cache[sid] = {
                                "login_at": now, "player": player, "server": srv_name,
                                "gid": gid, "notified": set(), "kicked": False,
                            }
                            try:
                                self.db.save_online_state(srv_name, player, str(gid), now)
                            except Exception:
                                pass
                            # 检查上线触发器
                            await self._check_online_triggers(player, srv_name, str(gid), conf, now)
                        cache = self._online_cache[sid]
                        session_mins = (now - cache["login_at"]) // 60
                        # 通知检查（群内 + 游戏内）
                        if tcfg["notify"]:
                            intervals = sorted(tcfg["notify_intervals"], reverse=True)
                            for threshold in intervals:
                                if session_mins >= threshold and threshold not in cache["notified"]:
                                    cache["notified"].add(threshold)
                                    h = threshold // 60
                                    m = threshold % 60
                                    if h > 0:
                                        dur_text = f"{h}时{m}分" if m else f"{h}小时"
                                    else:
                                        dur_text = f"{m}分钟"
                                    msg = f"⏰ {player} 已在 [{srv_name}] 连续在线 {dur_text}"
                                    self._pending_msgs.setdefault(str(gid), []).append(msg)
                                    # 游戏内提醒
                                    if tcfg["notify_game"]:
                                        game_msg = tcfg["notify_game_format"].replace("{player}", player).replace("{duration}", dur_text)
                                        try:
                                            await rcon_command(
                                                conf["rcon_host"], conf["rcon_port"],
                                                conf["rcon_password"], f"say {game_msg}",
                                            )
                                        except Exception as e:
                                            logger.error(f"[mrcon] 游戏内提醒失败: {e}")
                        # 踢出检查 + 封禁
                        if tcfg["kick_enabled"] and not cache["kicked"] and session_mins >= tcfg["kick_threshold"]:
                            cache["kicked"] = True
                            reason = tcfg["kick_reason"].replace("{player}", player)
                            kick_cmd = f"kick {player} {reason}"
                            try:
                                await rcon_command(
                                    conf["rcon_host"], conf["rcon_port"],
                                    conf["rcon_password"], kick_cmd,
                                )
                                logger.info(f"[mrcon] 自动踢出 {player} @ {srv_name}: {reason}")
                                msg = f"🚫 {player} 连续在线超过 {tcfg['kick_threshold']} 分钟，已被自动踢出 [{srv_name}]"
                                # 踢出后封禁
                                ban_mins = tcfg["ban_minutes"]
                                if ban_mins > 0:
                                    await rcon_command(
                                        conf["rcon_host"], conf["rcon_port"],
                                        conf["rcon_password"], f"ban {player} {reason}",
                                    )
                                    self._pending_unbans[f"{srv_name}:{player}"] = {
                                        "unban_at": now + ban_mins * 60,
                                        "player": player, "conf": conf,
                                    }
                                    msg += f"，已封禁 {ban_mins} 分钟"
                            except Exception as e:
                                logger.error(f"[mrcon] 自动踢出失败: {e}")
                                msg = f"⚠️ {player} 超时需踢出但执行失败 [{srv_name}]: {e}"
                            self._pending_msgs.setdefault(str(gid), []).append(msg)
                    for sid in list(self._online_cache.keys()):
                        s = self._online_cache[sid]
                        if s["server"] == srv_name and s["player"] not in online:
                            self.db.add_online_session(srv_name, s["player"], s["login_at"], now)
                            try:
                                self.db.remove_online_state(srv_name, s["player"])
                            except Exception:
                                pass
                            del self._online_cache[sid]
                # 定时重置在线时长排行
                if self.ranking_reset_hours > 0:
                    last = self._last_ranking_reset
                    if last == 0:
                        self._last_ranking_reset = now
                    elif (now - last) >= self.ranking_reset_hours * 3600:
                        try:
                            self.db._connect().cursor().execute("DELETE FROM online_sessions")
                            self.db._connect().commit()
                            self._last_ranking_reset = now
                            logger.info(f"[mrcon] 已自动重置在线时长排行（间隔 {self.ranking_reset_hours} 小时）")
                        except Exception as e:
                            logger.error(f"[mrcon] 自动重置排行失败: {e}")
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

    def _ensure_player(self, qq_id: str) -> dict:
        return self.db.ensure_player(str(qq_id))

    def _update_player(self, qq_id: str, updates: dict):
        self.db.update_player(str(qq_id), updates)

    # ==============================================================
    # MC 查询命令
    # ==============================================================
    @filter.command("mc", desc="查询所有MC服务器状态", alias={"查询"})
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

    @filter.command("mcget", desc="查询单个服务器详情", alias={"服详情"})
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

    @filter.command("mclist", desc="列出所有MC服务器", alias={"服列表"})
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

    @filter.command("mcadd", desc="添加MC服务器", alias={"加服"})
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

    @filter.command("mcdel", desc="删除MC服务器", alias={"删服"})
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

    @filter.command("改服", desc="更新MC服务器", alias={"mcup"})
    async def cmd_mcup(self, event: AstrMessageEvent, name: str = "", new_name: str = "", new_addr: str = ""):
        if not self.is_allowed(event):
            yield event.plain_result("仅管理员可更新服务器")
            return
        if not name:
            yield event.plain_result("用法: /改服 <名称> [新名称] [新地址]")
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

    @filter.command("共享服", desc="共享服务器到其他群", alias={"mcshare"})
    async def cmd_mcshare(self, event: AstrMessageEvent, name: str = "", target_gid: str = ""):
        if not self.is_admin(str(event.get_sender_id())):
            yield event.plain_result("仅超级管理员可共享服务器")
            return
        if not name or not target_gid:
            yield event.plain_result("用法: /共享服 <名称> <目标群ID>")
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

    @filter.command("取消共享", desc="取消共享", alias={"mcunshare"})
    async def cmd_mcunshare(self, event: AstrMessageEvent, name: str = "", target_gid: str = ""):
        if not self.is_admin(str(event.get_sender_id())):
            yield event.plain_result("仅超级管理员可取消共享")
            return
        if not name or not target_gid:
            yield event.plain_result("用法: /取消共享 <名称> <目标群ID>")
            return
        dst = self._get_group_serv_data(target_gid)
        if name not in dst.get("servers", {}):
            yield event.plain_result(f"目标群没有叫 {name} 的服务器")
            return
        del dst["servers"][name]
        self._save_group_serv_data(target_gid, dst)
        yield event.plain_result(f"✅ 已取消共享服务器 {name}（群 {target_gid}）")

    @filter.command("清理服", desc="清理失效服务器", alias={"mccleanup"})
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

    @filter.command("查询设置", desc="设置查询显示项", alias={"mcset"})
    async def cmd_mcset(self, event: AstrMessageEvent, key: str = "", value: str = ""):
        if not self.is_allowed(event):
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
        setattr(self, attr_map[cfg_key], val == "1")
        yield event.plain_result(f"✅ 已设置 {cfg_key} = {'显示' if val == '1' else '隐藏'}")

    @filter.command("在线时长", desc="查看玩家在线时长排行", alias={"onlinetime"})
    async def cmd_onlinetime(self, event: AstrMessageEvent, target: str = ""):
        """在线时长排行：默认本群排行，支持按服名/玩家名筛选"""
        if not self.tracker_enabled:
            yield event.plain_result("在线时长监控未开启")
            return
        gid = self._get_group_id(event)
        data = self._get_group_serv_data(gid) if gid else {}
        servers_dict = data.get("servers", {})
        srv_names = list(servers_dict.keys()) if servers_dict else []
        target = target.strip()
        if not target:
            # 默认：本群排行
            if srv_names:
                ranking = self.db.get_online_time_ranking(15, srv_names)
                scope = f"本群 ({len(srv_names)} 服)"
            else:
                ranking = self.db.get_online_time_ranking(15, srv_names)
                scope = "本群"
        elif target in srv_names:
            # 指定服务器名
            ranking = self.db.get_online_time_ranking(15, [target])
            scope = target
        else:
            # 查指定玩家
            secs = self.db.get_player_total_seconds(target)
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

    # ==============================================================
    # 在线提醒群内配置（覆盖全局默认）
    # ==============================================================
    @filter.command("在线提醒", desc="当前群的在线提醒与踢出设置（管理员）")
    async def cmd_tracker_set(self, event: AstrMessageEvent, sub: str = "", val1: str = "", val2: str = ""):
        if not self.is_allowed(event):
            yield event.plain_result("仅管理员可配置")
            return
        gid = str(self._get_group_id(event))
        if not gid:
            yield event.plain_result("请在群内使用此命令")
            return
        ovr = self._tracker_overrides.setdefault(gid, {})
        sub = sub.strip()
        val1 = val1.strip()
        val2 = val2.strip()
        gcfg = self._get_tracker_config(gid)

        if not sub:
            # 状态
            ni = gcfg["notify_intervals"]
            gf = gcfg.get("notify_game_format", "")
            yield event.plain_result(
                f"📋 本群在线提醒配置\n"
                f"  提醒开关: {'✅ 开' if gcfg['notify'] else '❌ 关'}\n"
                f"  提醒目标: {gcfg['notify_target']}\n"
                f"  提醒节点: {ni} (分钟)\n"
                f"  游戏提醒: {'✅ 开' if gcfg.get('notify_game') else '❌ 关'}\n"
                f"  游戏格式: {gf}\n"
                f"  踢出开关: {'✅ 开' if gcfg['kick_enabled'] else '❌ 关'}\n"
                f"  踢出阈值: {gcfg['kick_threshold']} 分钟\n"
                f"  踢出封禁: {gcfg.get('ban_minutes', 0)} 分钟\n"
                f"  踢出原因: {gcfg['kick_reason']}\n"
                f"  {'🟢 群内覆盖' if ovr else '🔵 沿用全局默认'}\n"
                f"\n游戏格式占位: {{player}}=玩家名 {{duration}}=时长\n"
                f"MC颜色码: §a绿 §b青 §c红 §e黄 §l粗体 §n下划线\n"
                f"\n快速: /在线提醒 开,游戏提醒=开,踢出=开,阈值=720,封禁=30\n"
                f"分步: 开|关|节点|目标|游戏提醒|游戏格式|踢出|封禁|重置"
            )
            return

        # === 逗号分隔批量配置 ===
        if "," in sub or "=" in sub:
            raw = str(getattr(event, "message_str", "") or "").strip()
            idx = raw.find(sub)
            bulk = raw[idx:] if idx >= 0 else sub
            parts = bulk.split(",") if "," in bulk else [bulk]
            updated = []
            for p in parts:
                p = p.strip()
                if not p:
                    continue
                if "=" in p:
                    k, v = p.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k == "开" or k == "关":
                        ovr["notify_enabled"] = (k == "开")
                    elif k == "目标":
                        if v in ("group", "admin_dm"): ovr["notify_target"] = v
                    elif k == "节点":
                        try:
                            ovr["notify_intervals"] = sorted([int(x.strip()) for x in v.split(",") if x.strip()], reverse=True)
                        except ValueError:
                            pass
                    elif k == "游戏提醒":
                        ovr["notify_in_game"] = v.lower() in ("开", "1", "true", "yes")
                    elif k == "游戏格式":
                        ovr["notify_game_format"] = v
                    elif k == "踢出":
                        ovr["kick_enabled"] = v.lower() in ("开", "1", "true", "yes")
                    elif k == "阈值":
                        try: ovr["kick_threshold"] = int(v)
                        except ValueError: pass
                    elif k == "封禁":
                        try: ovr["ban_minutes"] = int(v)
                        except ValueError: pass
                    elif k == "原因":
                        ovr["kick_reason"] = v
                    updated.append(f"{k}={v}")
                else:
                    if p == "开":
                        ovr["notify_enabled"] = True
                        updated.append("开")
                    elif p == "关":
                        ovr["notify_enabled"] = False
                        updated.append("关")
                    elif p == "重置":
                        self._tracker_overrides.pop(gid, None)
                        yield event.plain_result("🔵 已重置为全局默认配置")
                        return
            yield event.plain_result(f"✅ 已更新: {', '.join(updated) if updated else '(无变更)'}")
            return

        # === 分步子命令 ===
        if sub == "重置":
            self._tracker_overrides.pop(gid, None)
            yield event.plain_result("🔵 已重置为全局默认配置")
            return

        if sub in ("开", "关"):
            ovr["notify_enabled"] = (sub == "开")
            yield event.plain_result(f"✅ 本群在线提醒已{'开启' if sub == '开' else '关闭'}")
            return

        if sub == "节点":
            if not val1:
                yield event.plain_result("用法: /在线提醒 节点 <60,120,360>")
                return
            try:
                intervals = sorted([int(x.strip()) for x in val1.split(",") if x.strip()], reverse=True)
                if not intervals:
                    raise ValueError
                ovr["notify_intervals"] = intervals
                yield event.plain_result(f"✅ 提醒节点已设为: {intervals} 分钟")
            except ValueError:
                yield event.plain_result("节点格式错误，例: /在线提醒 节点 60,120,360")
            return

        if sub == "目标":
            if val1 not in ("group", "admin_dm"):
                yield event.plain_result("目标应为 group 或 admin_dm")
                return
            ovr["notify_target"] = val1
            yield event.plain_result(f"✅ 提醒目标已设为: {val1}")
            return

        if sub == "游戏提醒":
            if val1.lower() in ("开", "1", "true", "yes"):
                ovr["notify_in_game"] = True
                yield event.plain_result("✅ 游戏内提醒已开启")
            elif val1.lower() in ("关", "0", "false", "no"):
                ovr["notify_in_game"] = False
                yield event.plain_result("✅ 游戏内提醒已关闭")
            else:
                yield event.plain_result("用法: /在线提醒 游戏提醒 开|关")
            return

        if sub == "游戏格式":
            raw = str(getattr(event, "message_str", "") or "").strip()
            idx = raw.find("游戏格式")
            if idx >= 0:
                fmt = raw[idx + 4:].strip()
                if fmt:
                    ovr["notify_game_format"] = fmt
                    yield event.plain_result("✅ 游戏内提醒格式已更新")
                    return
            yield event.plain_result("用法: /在线提醒 游戏格式 <文案>  ({player}=玩家 {duration}=时长)")
            return

        if sub == "封禁":
            try:
                ovr["ban_minutes"] = int(val1)
                yield event.plain_result(f"✅ 踢出后封禁时长已设为 {val1} 分钟（0=不封禁）")
            except ValueError:
                yield event.plain_result("封禁时长应为数字（分钟），0=不封禁")
            return

        if sub == "踢出":
            if val1 == "开":
                ovr["kick_enabled"] = True
                if val2:
                    try:
                        ovr["kick_threshold"] = int(val2)
                    except ValueError:
                        yield event.plain_result("踢出阈值应为数字（分钟）")
                        return
                yield event.plain_result(f"✅ 踢出已开启（阈值 {ovr.get('kick_threshold', gcfg['kick_threshold'])} 分钟）")
            elif val1 == "关":
                ovr["kick_enabled"] = False
                yield event.plain_result("✅ 踢出已关闭")
            elif val1 == "原因":
                raw = str(getattr(event, "message_str", "") or "").strip()
                for needle in ("踢出 原因 ", "踢出 原因"):
                    idx = raw.find(needle)
                    if idx >= 0:
                        reason = raw[idx + len(needle):].strip()
                        if reason:
                            ovr["kick_reason"] = reason
                            yield event.plain_result("✅ 踢出原因已更新")
                            return
                yield event.plain_result("用法: /在线提醒 踢出 原因 <文本>")
                return
            else:
                yield event.plain_result("用法: /在线提醒 踢出 开 [阈值] | 踢出 关 | 踢出 原因 <文本>")
            return

        yield event.plain_result("未知子命令。可用: 开|关|节点|目标|游戏提醒|游戏格式|踢出|封禁|重置")

    # ==============================================================
    # 玩家数据库命令
    # ==============================================================
    @filter.command("绑定", desc="绑定MC账号（新玩家注册）", alias={"bind"})
    async def cmd_bind(self, event: AstrMessageEvent, mc_id: str = "", rest: str = ""):
        if not self.pdb_enabled:
            yield event.plain_result("玩家数据库功能未开启")
            return
        sender_qq = str(event.get_sender_id())
        is_global_admin = self.is_admin(sender_qq)
        gid = self._get_group_id(event)
        is_group_admin = False
        if gid and gid in self.group_servers:
            for srv in self.group_servers[gid]:
                wl = [str(x) for x in srv.get("whitelist_qqs", [])]
                if sender_qq in wl:
                    is_group_admin = True
                    break

        if rest.strip():
            # 管理员模式: /绑定 <目标QQ> <MC_ID>
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
            result = self.db.bind_player(target_qq, target_mc, self.pdb_new_pts)
            if result.get("already_bound"):
                yield event.plain_result(f"❌ 该QQ已绑定 MC 账号 {result['old_mc_id']}，不能重复绑定")
                return
            yield event.plain_result(f"✅ 已为 QQ {target_qq} 绑定 MC 账号: {target_mc}\n🎁 获得新玩家奖励 {self.pdb_new_pts} 积分！\n💰 总积分: {result['total_pts']}")
            return

        # 普通模式: /绑定 <MC_ID>
        if not mc_id:
            hint = "用法: /绑定 <你的MC ID>"
            if is_global_admin or is_group_admin:
                hint += "\n管理员用法: /绑定 <QQ号> <MC ID>"
            yield event.plain_result(hint)
            return
        result = self.db.bind_player(sender_qq, mc_id, self.pdb_new_pts)
        if result.get("already_bound"):
            yield event.plain_result(f"❌ 你已绑定 {result['old_mc_id']}，不能重复绑定")
            return
        yield event.plain_result(f"✅ 已绑定 MC 账号: {mc_id}\n🎁 获得新玩家奖励 {self.pdb_new_pts} 积分！\n💰 总积分: {result['total_pts']}")

    @filter.command("签到", desc="每日签到（需先绑定MC账号）", alias={"checkin"})
    async def cmd_checkin(self, event: AstrMessageEvent):
        if not self.pdb_enabled:
            yield event.plain_result("玩家数据库功能未开启")
            return
        qq_id = str(event.get_sender_id())
        today = time.strftime("%Y-%m-%d")
        result = self.db.checkin_player(qq_id, today, self.pdb_checkin_pts, self.pdb_streak_bonus)
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

    @filter.command("我的", desc="查看个人统计", alias={"mystats"})
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

    @filter.command("理赔", desc="申请物品补偿（输入完整RCON命令）", alias={"赔", "comp", "compensate"})
    async def cmd_compensate(self, event: AstrMessageEvent, text: str = "", rest=None):
        if not self.pdb_enabled:
            yield event.plain_result("玩家数据库未开启")
            return
        qq_id = str(event.get_sender_id())
        if not self.pdb_comp_enabled:
            if qq_id not in self.admin_qqs and qq_id not in self.pdb_comp_whitelist:
                yield event.plain_result("⚠️ 补偿功能仅白名单可用，你不在白名单中")
                return
        p = self._ensure_player(qq_id)
        if not p.get("mc_id"):
            yield event.plain_result("请先用 /绑定 绑定 MC 账号")
            return
        # 仅转发 /理赔 后面的命令，不带前缀
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

    @filter.command("理赔列表", desc="查看补偿申请列表", alias={"赔单", "comp_list"})
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
        lines.append("使用 /同意理赔 <ID> 批准 或 /拒绝理赔 <ID> 拒绝")
        yield event.plain_result("\n".join(lines))

    @filter.command("同意理赔", desc="批准补偿并执行RCON", alias={"comp_approve"})
    async def cmd_comp_approve(self, event: AstrMessageEvent, comp_id: str = ""):
        if not self.is_allowed(event):
            yield event.plain_result("仅管理员可审批")
            return
        try:
            cid = int(comp_id)
        except ValueError:
            yield event.plain_result("用法: /同意理赔 <申请ID>")
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

    @filter.command("拒绝理赔", desc="拒绝补偿申请", alias={"comp_reject"})
    async def cmd_comp_reject(self, event: AstrMessageEvent, comp_id: str = ""):
        if not self.is_allowed(event):
            yield event.plain_result("仅管理员可审批")
            return
        try:
            cid = int(comp_id)
        except ValueError:
            yield event.plain_result("用法: /拒绝理赔 <申请ID>")
            return
        comp = self.db.get_compensation(cid)
        if not comp:
            yield event.plain_result(f"未找到申请 #{cid}")
            return
        self.db.update_compensation(cid, "rejected")
        yield event.plain_result(f"❌ 已拒绝补偿申请 #{cid}")

    # ==============================================================
    # 积分兑换
    # ==============================================================

    @filter.command("兑换列表", desc="查看可用兑换项", alias={"shop", "exlist"})
    async def cmd_exchange_list(self, event: AstrMessageEvent):
        if not self.pdb_enabled:
            yield event.plain_result("玩家数据库功能未开启")
            return
        gid = self._get_group_id(event) or ""
        items = self.db.get_exchange_items(gid)
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

    @filter.command("兑换", desc="使用积分兑换物品", alias={"redeem", "ex", "buy"})
    async def cmd_exchange(self, event: AstrMessageEvent, item_id: str = ""):
        if not self.pdb_enabled:
            yield event.plain_result("玩家数据库功能未开启")
            return
        gid = self._get_group_id(event)
        if not gid:
            yield event.plain_result("仅在群聊中可使用兑换功能")
            return
        try:
            iid = int(item_id)
        except ValueError:
            yield event.plain_result("用法: /兑换 <编号>\n先用 /兑换列表 查看可用项目")
            return
        qq_id = str(event.get_sender_id())
        p = self.db.get_player(qq_id)
        if not p or not p.get("mc_id"):
            yield event.plain_result("请先用 /绑定 绑定 MC 账号")
            return
        # 检查兑换项属于当前群
        item = self.db.get_exchange_item(iid)
        if not item or str(item.get("group_id", "")) != gid:
            yield event.plain_result("❌ 兑换项不属于当前群")
            return
        result = self.db.redeem_exchange(qq_id, p["mc_id"], iid)
        if not result["success"]:
            yield event.plain_result(f"❌ {result['error_msg']}")
            return
        # 执行 RCON 命令
        conf = self.group_map.get(gid)
        if not conf:
            yield event.plain_result(
                f"✅ 已兑换 {result['item_name']}，消耗 {result['cost']} 积分\n"
                f"💰 剩余积分: {result['total_pts']}\n"
                f"⚠️ 当前群未配置服务器，RCON命令手动执行: {result['rcon_cmd']}"
            )
            return
        try:
            async for msg in self._execute_on_conf(event, conf, result['rcon_cmd'],
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

    # ==============================================================
    # 抽奖
    # ==============================================================

    @filter.command("抽奖", desc="消耗积分抽取奖品", alias={"lottery", "draw"})
    async def cmd_lottery(self, event: AstrMessageEvent):
        if not self.pdb_enabled:
            yield event.plain_result("玩家数据库功能未开启")
            return
        gid = self._get_group_id(event)
        if not gid:
            yield event.plain_result("仅在群聊中可使用抽奖功能")
            return
        qq_id = str(event.get_sender_id())
        p = self.db.get_player(qq_id)
        if not p or not p.get("mc_id"):
            yield event.plain_result("请先用 /绑定 绑定 MC 账号")
            return
        result = self.db.draw_lottery(qq_id, p["mc_id"], gid)
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

    @filter.command("奖品列表", desc="查看当前群可抽取的奖品", alias={"prizes", "jp"})
    async def cmd_lottery_prizes(self, event: AstrMessageEvent):
        gid = self._get_group_id(event)
        if not gid:
            yield event.plain_result("仅在群聊中使用")
            return
        prizes = self.db.get_lottery_prizes(gid)
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

    @filter.command("兑奖", desc="兑换中奖奖品", alias={"redeem_prize", "claim"})
    async def cmd_lottery_redeem(self, event: AstrMessageEvent, win_id: str = ""):
        if not self.pdb_enabled:
            yield event.plain_result("玩家数据库功能未开启")
            return
        gid = self._get_group_id(event)
        if not gid:
            yield event.plain_result("仅在群聊中使用")
            return
        try:
            wid = int(win_id)
        except ValueError:
            yield event.plain_result("用法: /兑奖 <中奖编号>\n用 /我的中奖 查看中奖记录")
            return
        result = self.db.redeem_lottery_win(wid)
        if not result["success"]:
            yield event.plain_result(f"❌ {result['error_msg']}")
            return
        # 执行RCON
        conf = self.group_map.get(gid)
        if conf:
            try:
                async for msg in self._execute_on_conf(event, conf, result['prize_cmd'],
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

    @filter.command("我的中奖", desc="查看我的中奖记录", alias={"mywins", "wins"})
    async def cmd_lottery_my_wins(self, event: AstrMessageEvent):
        gid = self._get_group_id(event)
        if not gid:
            yield event.plain_result("仅在群聊中使用")
            return
        qq_id = str(event.get_sender_id())
        wins = self.db.get_lottery_wins(qq_id=qq_id, group_id=gid)
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

    # ==============================================================
    # 群服消息互联
    # ==============================================================
    @filter.command("msay", desc="主动发送消息到MC（群服互联前缀命令）", alias={"群说", "服说", "mcsay"})
    async def cmd_msay(self, event: AstrMessageEvent, text: str = "", rest=None):
        """群内通过 /msay <消息> 主动发送消息到对应 MC 服务器"""
        gid = self._get_group_id(event)
        cfg = self._get_relay_config(gid)
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
        await self._relay_to_mc(event, user_name, msg)
        # 也回复群内确认
        yield event.plain_result(f"已发送 → {cfg['_resolved_server']}")

    def _get_relay_override(self, gid: str) -> dict:
        """获取群 relay override（兼容 list [{...}] 与 dict {...}，返回可变引用）"""
        gid = str(gid)
        ov = self._relay_overrides.get(gid)
        if isinstance(ov, list):
            if ov:
                return ov[0]
            ov.append({})
            return ov[0]
        if isinstance(ov, dict):
            return ov
        self._relay_overrides[gid] = {}
        return self._relay_overrides[gid]

    def _save_relay_overrides(self):
        """持久化群服互联覆盖配置到 config"""
        self.config["relay"]["group_settings"] = self._relay_overrides
        try:
            self.config.save_config()
        except Exception as e:
            logger.error(f"[mrcon] 保存 relay_overrides 失败: {e}")

    def _get_relay_config(self, gid: str) -> dict:
        """获取某群的消息互联配置，支持 mode: off/global/custom"""
        override = self._get_relay_override(gid)
        conf = self._get_relay_conf(gid) or {}
        mode = override.get("mode", "off")
        if mode == "off":
            return {
                "enabled": False, "group_to_mc": False, "mc_to_group": False,
                "mode": "off", "format_group": self.relay_fmt_group,
                "format_mc": self.relay_fmt_mc,
                "require_msay": False,
                "server_name": None, "_resolved_server": conf.get("server_name") or conf.get("name", "未配置"),
            }
        elif mode == "global":
            return {
                "enabled": self.relay_enabled,
                "group_to_mc": self.relay_group_to_mc,
                "mc_to_group": self.relay_mc_to_group,
                "mode": "global",
                "format_group": self.relay_fmt_group,
                "format_mc": self.relay_fmt_mc,
                "require_msay": self.relay_require_msay,
                "server_name": override.get("server_name"),
                "_resolved_server": conf.get("server_name") or conf.get("name", "未配置"),
            }
        else:  # custom
            return {
                "enabled": override.get("enabled", True),  # 独立配置默认启用，不受全局 relay_enabled 影响
                "group_to_mc": override.get("group_to_mc", self.relay_group_to_mc),
                "mc_to_group": override.get("mc_to_group", False),
                "mode": "custom",
                "format_group": override.get("format_group", self.relay_fmt_group),
                "format_mc": override.get("format_mc", self.relay_fmt_mc),
                "require_msay": override.get("require_msay", self.relay_require_msay),
                "server_name": override.get("server_name", None),
                "_resolved_server": conf.get("server_name") or conf.get("name", "未配置"),
            }

    def _get_relay_conf(self, gid: str):
        """获取群的 relay 目标服务器配置"""
        override = self._get_relay_override(gid)
        srv_name = override.get("server_name")
        if srv_name:
            srvs = self.group_servers.get(str(gid), [])
            for s in srvs:
                if s.get("server_name") == srv_name:
                    return s
        return self.group_map.get(gid)
    async def _on_mc_chat(self, server_name: str, player: str, message: str) -> int:
        """MC 服→QQ 群消息转发，根据 relay 配置分发到匹配的群"""
        count = 0
        for gid, entries in list(self._relay_overrides.items()):
            gid = str(gid)
            entry_list = entries if isinstance(entries, list) else ([entries] if isinstance(entries, dict) else [])
            for entry in entry_list:
                if not isinstance(entry, dict):
                    continue
                if entry.get("server_name") != server_name:
                    continue
                mode = entry.get("mode", "off")
                if mode == "off":
                    continue
                if mode == "global":
                    if not self.relay_mc_to_group:
                        continue
                    fmt = self.relay_fmt_mc
                elif mode == "custom":
                    if not entry.get("mc_to_group"):
                        continue
                    fmt = entry.get("format_mc", self.relay_fmt_mc)
                else:
                    continue
                text = fmt.replace("{player}", player).replace("{msg}", message).replace("{server}", server_name)
                try:
                    umo = f"napcat:GroupMessage:{gid}"
                    chain = MessageChain(chain=[Plain(text)])
                    await self.context.send_message(umo, chain)
                    count += 1
                except Exception as e:
                    logger.error(f"[mrcon] MC→群转发失败 {gid}: {e}")
        if count == 0:
            logger.debug(f"[mrcon] MC 服 {server_name} 消息无匹配群")
        else:
            logger.info(f"[mrcon] MC 服 {server_name} 消息已分发到 {count} 个群")
        return count

    async def _relay_to_mc(self, event: AstrMessageEvent, user_name: str, message: str):
        gid = self._get_group_id(event)
        cfg = self._get_relay_config(gid)
        if not cfg["enabled"] or not cfg["group_to_mc"]:
            return
        conf = self._get_relay_conf(gid)
        if not conf:
            return
        try:
            fmt = cfg["format_group"].replace("{name}", user_name).replace("{msg}", message)
            escaped = json.dumps(fmt)
            cmd = f"tellraw @a {escaped}"
            host = conf.get("rcon_host")
            port = conf.get("rcon_port")
            password = conf.get("rcon_password")
            await rcon_command(host, port, password, cmd)
        except Exception as e:
            logger.debug(f"[mrcon] relay to MC failed: {e}")

    @filter.command("消息互通", desc="群服消息互联配置（管理员）", alias={"relay"})
    async def cmd_relay(self, event: AstrMessageEvent, sub: str = "", val: str = ""):
        if not self.is_allowed(event):
            yield event.plain_result("仅管理员可操作")
            return
        gid = str(self._get_group_id(event))
        ovr = self._get_relay_override(gid)
        cfg = self._get_relay_config(gid)
        sub = sub.strip().lower()
        val = val.strip()

        if not sub:
            # 状态展示
            global_srv = self.group_map.get(gid, {})
            relay_srv = self._get_relay_conf(gid) or {}
            srv_display = relay_srv.get("server_name") or relay_srv.get("name") or global_srv.get("name") or "未配置"
            mode_label = {"off": "❌ 不互通", "global": "🔵 遵循全局", "custom": "🟢 独立配置"}.get(cfg["mode"], cfg["mode"])
            yield event.plain_result(
                f"📋 本群消息互联配置\n"
                f"  模式: {mode_label}\n"
                f"  群→服转发: {'✅ 开' if cfg['group_to_mc'] else '❌ 关'}\n"
                f"  服→群转发: {'✅ 开' if cfg['mc_to_group'] else '❌ 关'}\n"
                f"  仅 /msay: {'✅ 开（只允许命令互通）' if cfg.get('require_msay') else '❌ 关（自动转发群消息）'}\n"
                f"  格式: {cfg['format_group']}\n"
                f"  目标服务器: {srv_display}\n"
                f"  全局默认: 群→服={'✅' if self.relay_group_to_mc else '❌'} 服→群={'✅' if self.relay_mc_to_group else '❌'} 仅msay={'✅' if self.relay_require_msay else '❌'}\n"
                f"\n格式占位: {{name}}=群昵称 {{msg}}=消息内容\n"
                f"\n子命令: 开|关|模式|群到服|服到群|仅msay|格式|服|重置\n"
                f"例: /消息互通 模式 custom\n"
                f"    /消息互通 群到服 开\n"
                f"    /消息互通 仅msay 开（开启后只会通过 /msay 命令转发）\n"
                f"    /消息互通 格式 [QQ] {name}: {msg}\n"
                f"    /消息互通 服 生存一区\n"
                f"    /消息互通 重置"
            )
            return

        if sub == "重置":
            self._relay_overrides.pop(gid, None)
            self._save_relay_overrides()
            yield event.plain_result("🔵 已重置为全局默认配置")
            return

        if sub in ("on", "1", "开", "开启", "启用"):
            ovr["mode"] = "custom"
            ovr["enabled"] = True
            ovr["group_to_mc"] = True
            self._save_relay_overrides()
            yield event.plain_result("✅ 本群消息互通已开启（群→服转发已启用，模式: 独立配置）")
            return

        if sub in ("off", "0", "关", "关闭", "禁用"):
            ovr["mode"] = "off"
            self._save_relay_overrides()
            yield event.plain_result("❌ 本群消息互通已关闭（模式: 不互通）")
            return

        if sub == "格式" or sub == "format":
            if not val:
                yield event.plain_result("用法: /消息互通 格式 <文本>  ({name}=群昵称 {msg}=消息)")
                return
            ovr["format_group"] = val
            self._save_relay_overrides()
            yield event.plain_result(f"✅ 转发格式已设为: {val}")
            return

        if sub in ("服", "服务器", "server"):
            if not val:
                # 列出可选服务器
                srvs = self.group_servers.get(gid, [])
                if not srvs:
                    yield event.plain_result("当前群未绑定任何服务器")
                    return
                lines = ["可选服务器:"]
                for s in srvs:
                    sn = s.get("server_name", "")
                    marker = " ← 当前" if ovr.get("server_name") == sn else ""
                    lines.append(f"  • {sn}{marker}")
                yield event.plain_result("\n".join(lines))
                return
            # 校验服务器名是否存在
            srvs = self.group_servers.get(gid, [])
            matched = None
            for s in srvs:
                if s.get("server_name", "") == val:
                    matched = val
                    break
            if matched is None:
                yield event.plain_result(f"未找到服务器「{val}」，请用 /mclist 查看已绑定服务器")
                return
            ovr["server_name"] = val
            self._save_relay_overrides()
            yield event.plain_result(f"✅ 消息互通目标服务器已设为: {val}")
            return

        if sub in ("模式", "mode"):
            if val not in ("off", "global", "custom"):
                yield event.plain_result("用法: /消息互通 模式 <off|global|custom>\noff=不互通 global=遵循全局 custom=独立配置")
                return
            ovr["mode"] = val
            self._save_relay_overrides()
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
            self._save_relay_overrides()
            yield event.plain_result(f"✅ 群→服转发已{'开启' if v else '关闭'}（模式: 独立配置）")
            return

        if sub in ("服到群", "mc_to_group", "mtg"):
            if val not in ("on", "1", "开", "开启", "启用", "off", "0", "关", "关闭", "禁用"):
                yield event.plain_result("用法: /消息互通 服到群 <开|关>")
                return
            v = val in ("on", "1", "开", "开启", "启用")
            ovr["mode"] = "custom"
            ovr["mc_to_group"] = v
            self._save_relay_overrides()
            yield event.plain_result(f"✅ 服→群转发已{'开启' if v else '关闭'}（模式: 独立配置）")
            return

        if sub in ("仅msay", "msay_only", "require_msay", "msay"):
            if val not in ("on", "1", "开", "开启", "启用", "off", "0", "关", "关闭", "禁用"):
                yield event.plain_result("用法: /消息互通 仅msay <开|关>\n开启后只会通过 /msay 命令转发消息，不自动转发群消息")
                return
            v = val in ("on", "1", "开", "开启", "启用")
            ovr["mode"] = "custom"
            ovr["require_msay"] = v
            self._save_relay_overrides()
            yield event.plain_result(f"✅ 仅 /msay 命令互通已{'开启' if v else '关闭'}（模式: 独立配置）{' 只有通过 /msay 命令才能发消息到 MC' if v else ' 群内所有消息将自动转发到 MC'}")
            return

        yield event.plain_result(
            f"未知子命令: {sub}\n"
            f"可用: 开|关|格式|服|重置\n"
            f"直接 /消息互通 查看状态"
        )

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def _on_group_message(self, event: AstrMessageEvent):
        gid = self._get_group_id(event)
        # 存储 UMO 并刷新生效中的通知消息
        self._last_umo[str(gid)] = event
        async for msg in self._flush_pending_msgs(event):
            yield msg
        cfg = self._get_relay_config(gid)
        if not cfg["enabled"] or not cfg["group_to_mc"]:
            return
        if cfg.get("require_msay", False):
            return  # 仅允许 /msay 命令互通，不自动转发群消息
        text = str(getattr(event, "message_str", "") or "")
        if not text or text.startswith("/"):
            return
        user_name = str(event.get_sender_name() or "")
        await self._relay_to_mc(event, user_name, text)

    async def _flush_pending_msgs(self, event: AstrMessageEvent):
        """释放攒积的在线提醒消息"""
        gid = self._get_group_id(event)
        sender = str(event.get_sender_id())
        if self.tracker_notify_target == "group":
            # 群内模式：从群消息触发时直接发到该群
            msgs = self._pending_msgs.pop(str(gid), None)
            if msgs:
                for msg in msgs:
                    yield event.plain_result(msg)
        else:
            # 管理员私聊模式：攒积消息，等管理员私聊bot时发送
            pass

    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    async def _flush_admin_dm(self, event: AstrMessageEvent):
        """管理员私聊时，刷新生效的在线提醒"""
        if self.tracker_notify_target != "admin_dm":
            return
        sender = str(event.get_sender_id())
        if not self.is_allowed(event):
            return
        for gid in list(self._pending_msgs.keys()):
            msgs = self._pending_msgs.pop(gid, None)
            if msgs:
                for msg in msgs:
                    yield event.plain_result(f"[群{gid}] {msg}")

    # ==============================================================
    # RCON 命令（原有 + mcing 迁移）
    # ==============================================================
    @filter.command("mrcon", desc="将后续文本原样转发到 RCON 控制台", alias={"执行", "mcmd"})
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
            lines.append(f"请在 {self.select_ttl} 秒内回复编号（直接发送数字即可），或使用 /选服 <编号>")
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

    @filter.command("选服", desc="选择 RCON 服务器编号", alias={"rc选", "rcsel", "rcserver"})
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
            yield event.plain_result("请输入有效编号，如 /选服 1")
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

    @filter.command("宏", desc="执行宏命令", alias={"rcm", "rcmacro"})
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
        mc = self.macros.get(name)
        if not mc:
            yield event.plain_result("未找到该宏定义")
            return
        if not mc.get("enabled", True):
            yield event.plain_result(f"宏「{name}」已被禁用")
            return
        cmds = mc["commands"]
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

    @filter.command("脚本", desc="执行脚本文件", alias={"rcs", "rcscript"})
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
        # 检查启用状态（默认启用，除非明确禁用）
        ss = self.script_settings.get(filename, {})
        if not ss.get("enabled", True):
            yield event.plain_result(f"脚本「{filename}」已被禁用")
            return
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

    # ==============================================================
    # 帮助
    # ==============================================================
    @filter.command("rchelp", desc="查看所有可用命令（图片版）", alias={"rc帮助", "帮助", "help", "mchelp"})
    async def cmd_help(self, event: AstrMessageEvent):
        if not _HAS_PIL:
            yield event.plain_result(
                "━━━ MRCon 命令帮助 ━━━\n\n"
                "🖥️ MC查询: /mc /mcget /mclist /mcset /在线时长 /在线提醒\n"
                "⚙️ 服务器管理: /mcadd /mcdel /mcup /mcshare /mcunshare /mccleanup\n"
                "🎯 RCON: /mrcon /选服 /宏 /脚本 /rc赞同 /rc反对\n"
                "👤 玩家: /绑定 /签到 /我的 /理赔 /理赔列表\n"
                "💱 积分: /兑换列表 /兑换\n"
                "🎰 抽奖: /抽奖 /奖品列表 /兑奖 /我的中奖\n"
                "🔗 互联: /msay /消息互通\n"
                "🌐 Web面板: http://localhost:9949\n\n"
                "━━━ 详细帮助请升级 Pillow 后查看 ━━━\n"
                "pip install Pillow"
            )
            return
        img_bytes = self._render_help_image()
        path = os.path.join(self.plugin_data_dir, "_tmp_help.png")
        with open(path, "wb") as f:
            f.write(img_bytes.read())
        try:
            from astrbot.api.message_components import Image as ImgComp, Plain as PlComp
            yield event.chain_result(MessageChain([ImgComp.fromFileSystem(path)]))
        except Exception:
            try:
                yield event.image_result(path)
            except Exception:
                yield event.plain_result("帮助图片已生成: " + path)

    def _render_help_image(self) -> BytesIO:
        # 字体检测
        font_paths = [
            os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "msyh.ttc"),
            os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "simhei.ttf"),
            os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "simsun.ttc"),
            "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ]
        font_path = None
        for fp in font_paths:
            if os.path.exists(fp):
                font_path = fp
                break
        # 颜色 / 尺寸
        BG = "#181825"       # 深色底
        FG = "#cdd6f4"       # 正文
        HL = "#89b4fa"       # 标题蓝
        AC = "#a6e3a1"       # 命令绿
        SUB = "#6c7086"      # 副标题灰
        DIV = "#45475a"      # 分隔线色
        W = 820
        PAD_X, PAD_Y = 24, 18
        LINE_H = 26
        HEAD_H = 38
        # 字体
        try:
            font = ImageFont.truetype(font_path or "", 16) if font_path else ImageFont.load_default()
            font_sm = ImageFont.truetype(font_path or "", 13) if font_path else ImageFont.load_default()
            font_hd = ImageFont.truetype(font_path or "", 20) if font_path else ImageFont.load_default()
        except Exception:
            font = font_sm = font_hd = ImageFont.load_default()
        # 帮助内容 (section_header, [(command, desc)])
        sections = [
            ("🖥️ MC 查询", [
                ("/mc", "所有服务器状态 + 在线玩家"),
                ("/mcget <名>", "单服详情"),
                ("/mclist", "服务器列表"),
                ("/mcset <项> 1|0", "设置显示项"),
                ("/在线时长 [服|玩家]", "在线排行"),
                ("/在线提醒", "配置提醒与踢出"),
            ]),
            ("⚙️ 服务器", [
                ("/mcadd <名> <IP:端口>", "添加"),
                ("/mcdel <名>", "删除"),
                ("/mcup <名> [新名] [新址]", "更新"),
                ("/mcshare|mcunshare <名> <群>", "共享 / 取消"),
                ("/mccleanup", "清理失效服务器"),
            ]),
            ("🎯 RCON", [
                ("/mrcon <命令>", "执行 RCON 命令"),
                ("/选服 <编号>", "选择目标服务器"),
                ("/宏 <名> [参数]", "执行预设宏"),
                ("/脚本 <文件名>", "执行脚本"),
                ("/rc赞同|反对  /rc通过|否决", "投票 + 裁决"),
            ]),
            ("👤 玩家", [
                ("/绑定 <MC_ID>", "绑定 MC 账号"),
                ("/签到", "每日签到"),
                ("/我的", "积分与统计"),
                ("/理赔 <命令>", "申请物品补偿"),
                ("/理赔列表 | 同意|拒绝理赔", "审批管理"),
            ]),
            ("💱 积分 & 🎰 抽奖", [
                ("/兑换列表 /兑换 <编号>", "积分兑换"),
                ("/抽奖 /奖品列表", "积分抽奖"),
                ("/兑奖 <编号> /我的中奖", "兑奖 / 中奖记录"),
            ]),
            ("🔗 群服互联", [
                ("/msay <消息>", "发消息到 MC 公屏"),
                ("/消息互通 开|关", "开关互通"),
                ("/消息互通 模式 off|global|custom", "转发模式"),
                ("/消息互通 群到服|服到群 开|关", "方向开关"),
                ("/消息互通 服 <名>", "指定目标服务器"),
                ("/消息互通 格式 <文本>", "自定义格式 {name}/{msg}"),
                ("/消息互通 重置", "恢复默认"),
            ]),
            ("🌐 Web 面板", [
                ("http://localhost:9949", "浏览器管理面板"),
                ("v" + self._get_version(), "自启: web_panel.enabled=true"),
            ]),
        ]
        # 计算高度
        total_h = PAD_Y * 2  # 上下padding
        for title, cmds in sections:
            total_h += HEAD_H + 4
            total_h += len(cmds) * LINE_H + 10
        total_h += 30  # footer
        # 创建图片
        img = PILImage.new("RGB", (W, total_h), BG)
        draw = ImageDraw.Draw(img)
        y = PAD_Y
        # 标题
        draw.text((PAD_X, y), "━━━  MRCon 命令帮助  ━━━", fill=HL, font=font_hd)
        y += HEAD_H + 8
        draw.line([(PAD_X, y), (W - PAD_X, y)], fill=DIV, width=1)
        y += 10
        for title, cmds in sections:
            draw.text((PAD_X, y), title, fill=HL, font=font)
            y += HEAD_H
            for cmd, desc in cmds:
                cmd_w = draw.textlength(cmd, font=font_sm)
                draw.text((PAD_X, y + 2), cmd, fill=AC, font=font_sm)
                draw.text((PAD_X + cmd_w + 14, y + 2), desc, fill=FG, font=font_sm)
                y += LINE_H
            y += 6
            draw.line([(PAD_X, y), (W - PAD_X, y)], fill=DIV, width=1)
            y += 10
        draw.text((PAD_X, y), "输入  /rchelp  随时查看此帮助", fill=SUB, font=font_sm)
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    def _get_version(self) -> str:
        try:
            import yaml
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metadata.yaml")
            with open(p, "r", encoding="utf-8") as f:
                m = yaml.safe_load(f)
                return str(m.get("version", "?"))
        except Exception:
            return "?"