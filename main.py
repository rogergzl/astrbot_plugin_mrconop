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
from astrbot.api.message_components import Plain, At
from astrbot.api import logger
from astrbot.api import AstrBotConfig
from astrbot.core.utils.session_waiter import session_waiter, SessionController

from .core.transport import rcon_command, rcon_command_pool, get_pool
from .core.database import Database
from .core.log_listener import LogListenerManager

from .core.utils import strip_mc_color, safe_json_read, safe_json_write, _is_valid_player_name

from .core.permission import is_admin as _core_is_admin
from .core.permission import is_allowed as _core_is_allowed
from .core.permission import _get_group_id as _core_get_group_id
from .core.permission import _match_dangerous as _core_match_dangerous
from .core.permission import _extract_full_after_cmd as _core_extract_full_after_cmd

from .core.rate_limit import _check_rate as _core_check_rate
from .core.rate_limit import _touch_rate as _core_touch_rate
from .core.rate_limit import _acquire_lock as _core_acquire_lock
from .core.rate_limit import _rate_key as _core_rate_key
from .core.rate_limit import _ps_key as _core_ps_key

from .core.audit import _audit as _core_audit
from .core.audit import _audit_web as _core_audit_web
from .core.audit import _audit_web_cmd as _core_audit_web_cmd
from .core.audit import _audit_auto as _core_audit_auto

from .core.rcon_executor import rcn_send as _core_rcn_send
from .core.rcon_executor import transport_send as _core_transport_send
from .core.rcon_executor import execute_and_reply as _core_execute_and_reply
from .core.rcon_executor import execute_on_conf as _core_execute_on_conf
from .core.rcon_executor import schedule_select_timeout as _core_schedule_select_timeout

from .core.server_manager import _save_cmd_tpls_init as _core_save_cmd_tpls_init
from .core.server_manager import _save_online_triggers as _core_save_online_triggers
from .core.server_manager import _save_script_settings as _core_save_script_settings
from .core.server_manager import _save_quick_cmd_settings as _core_save_quick_cmd_settings
from .core.server_manager import _save_custom_cmds as _core_save_custom_cmds
from .core.server_manager import _check_online_triggers as _core_check_online_triggers
from .core.server_manager import _load_mcserv as _core_load_mcserv
from .core.server_manager import _save_mcserv as _core_save_mcserv
from .core.server_manager import _get_group_serv_data as _core_get_group_serv_data
from .core.server_manager import _save_group_serv_data as _core_save_group_serv_data
from .core.server_manager import _get_mc_server_status as _core_get_mc_server_status
from .core.server_manager import _format_server_status as _core_format_server_status

from .core.online_tracker import _get_online_player_list as _core_get_online_player_list
from .core.online_tracker import _load_tracker_overrides as _core_load_tracker_overrides
from .core.online_tracker import _save_tracker_overrides as _core_save_tracker_overrides
from .core.online_tracker import _load_general_overrides as _core_load_general_overrides
from .core.online_tracker import _save_general_overrides as _core_save_general_overrides
from .core.online_tracker import _save_event_macros_json as _core_save_event_macros_json
from .core.online_tracker import _load_event_macros_json as _core_load_event_macros_json
from .core.online_tracker import _load_server_log_configs as _core_load_server_log_configs
from .core.online_tracker import _save_server_log_configs as _core_save_server_log_configs
from .core.online_tracker import _get_tracker_config as _core_get_tracker_config
from .core.online_tracker import _send_tracker_notify as _core_send_tracker_notify
from .core.online_tracker import _online_tracker_loop as _core_online_tracker_loop
from .core.online_tracker import _load_ranking_state as _core_load_ranking_state

from .core.log_events import _init_log_listeners as _core_init_log_listeners
from .core.log_events import _on_log_event as _core_on_log_event
from .core.log_events import _get_group_umo as _core_get_group_umo
from .core.log_events import _resolve_group_display_name as _core_resolve_group_display_name
from .core.log_events import _relay_log_event_to_groups as _core_relay_log_event_to_groups
from .core.log_events import _execute_event_macros as _core_execute_event_macros

from .core.relay import _get_relay_override as _core_get_relay_override
from .core.relay import _save_relay_overrides as _core_save_relay_overrides
from .core.relay import _load_relay_overrides as _core_load_relay_overrides
from .core.relay import _get_relay_conf as _core_get_relay_conf
from .core.relay import _get_relay_config as _core_get_relay_config
from .core.relay import _on_mc_chat as _core_on_mc_chat
from .core.relay import _relay_to_mc as _core_relay_to_mc

from .core.help import cmd_help as _core_cmd_help

from .core.player_manager import _load_player_db as _core_load_player_db
from .core.player_manager import _save_player_db as _core_save_player_db
from .core.player_manager import cmd_bind as _core_cmd_bind
from .core.player_manager import cmd_checkin as _core_cmd_checkin
from .core.player_manager import cmd_mystats as _core_cmd_mystats

from .core.compensation import cmd_compensate as _core_cmd_compensate
from .core.compensation import cmd_comp_list as _core_cmd_comp_list
from .core.compensation import cmd_comp_approve as _core_cmd_comp_approve
from .core.compensation import cmd_comp_reject as _core_cmd_comp_reject

from .core.exchange import cmd_exchange_list as _core_cmd_exchange_list
from .core.exchange import cmd_exchange as _core_cmd_exchange

from .core.lottery import cmd_lottery as _core_cmd_lottery
from .core.lottery import cmd_lottery_prizes as _core_cmd_lottery_prizes
from .core.lottery import cmd_lottery_redeem as _core_cmd_lottery_redeem
from .core.lottery import cmd_lottery_my_wins as _core_cmd_lottery_my_wins

from .core.relay import cmd_msay as _core_cmd_msay
from .core.relay import cmd_relay as _core_cmd_relay
from .core.relay import _on_group_message as _core_on_group_message
from .core.relay import _flush_pending_msgs as _core_flush_pending_msgs
from .core.relay import _flush_admin_dm as _core_flush_admin_dm

from .core.vote import cmd_mrcon as _core_cmd_mrcon
from .core.vote import cmd_select_server as _core_cmd_select_server
from .core.vote import cmd_rc_agree as _core_cmd_rc_agree
from .core.vote import cmd_rc_oppose as _core_cmd_rc_oppose
from .core.vote import cmd_rc_pass as _core_cmd_rc_pass
from .core.vote import cmd_rc_veto as _core_cmd_rc_veto

from .core.macro import cmd_macro as _core_cmd_macro
from .core.macro import cmd_script as _core_cmd_script
from .core.macro import cmd_custom as _core_cmd_custom

from .core.server_manager import cmd_mc as _core_cmd_mc
from .core.server_manager import cmd_mcget as _core_cmd_mcget
from .core.server_manager import cmd_mclist as _core_cmd_mclist
from .core.server_manager import cmd_mcadd as _core_cmd_mcadd
from .core.server_manager import cmd_mcdel as _core_cmd_mcdel
from .core.server_manager import cmd_mcup as _core_cmd_mcup
from .core.server_manager import cmd_mcshare as _core_cmd_mcshare
from .core.server_manager import cmd_mcunshare as _core_cmd_mcunshare
from .core.server_manager import cmd_mccleanup as _core_cmd_mccleanup
from .core.server_manager import cmd_mcset as _core_cmd_mcset
from .core.server_manager import cmd_onlinetime as _core_cmd_onlinetime

from .core.online_tracker import cmd_tracker_set as _core_cmd_tracker_set


@register("mrcon", "lindagao", "MC 综合管理插件", "4.2.2")
class MrconPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

        admin_cfg = self.config.get("admin", {})
        if not isinstance(admin_cfg, dict):
            admin_cfg = {}
        self.admin_qqs = set(admin_cfg.get("bot_admin_qqs", []) or [])

        web_cfg = self.config.get("web_panel", {})
        if not isinstance(web_cfg, dict):
            web_cfg = {}
        self.web_panel_enabled = bool(web_cfg.get("enabled", False))
        self.web_panel_host = str(web_cfg.get("host", "0.0.0.0") or "0.0.0.0")
        self.web_panel_port = int(web_cfg.get("port", 9949) or 9949)
        self.web_panel_password = str(web_cfg.get("password", "") or "")
        self.web_panel_session_timeout = int(web_cfg.get("session_timeout", 600) or 600)
        self.log_viewer_refresh_ms = int(web_cfg.get("log_viewer_refresh_ms", 10000) or 10000)
        self._web_panel = None
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
        self.rate_whitelist = set(str(s).strip() for s in (rate_limit_cfg.get("whitelist_qqs", []) or []) if str(s).strip())
        self.rate_whitelist_min_delay_ms = int(rate_limit_cfg.get("whitelist_min_delay_ms", 200) or 200)
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
        self.tracker_poll_mode = str(tracker_cfg.get("poll_mode", "frequent") or "frequent")
        self.tracker_idle_interval = int(tracker_cfg.get("poll_idle_interval_seconds", 300) or 300)
        self.tracker_active_interval = int(tracker_cfg.get("poll_active_interval_seconds", 60) or 60)
        self.tracker_method = str(tracker_cfg.get("query_method", "rcon") or "rcon")
        self.tracker_notify = bool(tracker_cfg.get("notify_enabled", False))
        self.tracker_notify_target = str(tracker_cfg.get("notify_target", "group") or "group")
        self.tracker_notify_intervals = sorted(
            [int(x) for x in (tracker_cfg.get("notify_intervals", [60, 120, 360]) or [])], reverse=True
        )
        self.tracker_kick_enabled = bool(tracker_cfg.get("auto_kick_enabled", False))
        self.tracker_kick_threshold = int(tracker_cfg.get("auto_kick_threshold", 720) or 720)
        self.tracker_kick_reason = str(tracker_cfg.get("auto_kick_reason", "") or "§6{player}§r, §a你已在线§e{hours}§a小时§r, §c请休息§d{minutes}§c分钟吧§r")
        self.tracker_notify_game = bool(tracker_cfg.get("notify_in_game", False))
        self.tracker_game_format = str(tracker_cfg.get("notify_game_format", "{player} 已连续在线 {duration}，注意休息！") or "")
        self.tracker_game_prefix = str(tracker_cfg.get("notify_game_prefix", "§e[在线提醒]") or "")
        self.tracker_notify_mention_mode = str(tracker_cfg.get("notify_mention_mode", "player") or "player")
        self.tracker_notify_mention_format = str(tracker_cfg.get("notify_mention_format", "@{qq} {player} 你已{dur_label}在线 {duration}") or "")

        self._known_real_players: set[str] = set()

        self.event_macro_game_prefix = str(general_cfg.get("event_macro_game_prefix", "§b[宏]") or "")
        self.game_notify_prefix = str(general_cfg.get("game_notify_prefix", "§6[通知]") or "")
        self.admin_mc_ids = [s.strip() for s in str(general_cfg.get("admin_mc_ids", "") or "").split(",") if s.strip()]
        self.tracker_ban_minutes = int(tracker_cfg.get("auto_kick_ban_minutes", 30) or 30)
        self.tracker_ban_cmd = str(tracker_cfg.get("auto_kick_ban_cmd", "tempban {player} {minutes}m {reason}") or "tempban {player} {minutes}m {reason}")
        self.tracker_duration_mode = str(tracker_cfg.get("duration_mode", "session") or "session")
        self.ranking_reset_hours = int(tracker_cfg.get("ranking_reset_interval_hours", 24) or 24)
        self._last_ranking_reset = 0
        self._pending_msgs = {}
        self._last_umo = {}
        self._umo_prefix = ""
        self._recent_log_events: dict[tuple, float] = {}
        self._tracker_overrides = {}

        self.log_listener_enabled = bool(tracker_cfg.get("log_listener_enabled", False))
        self.online_history_max_bars = int(tracker_cfg.get("online_history_max_bars", 70) or 70)
        self._log_listener = LogListenerManager()
        log_patterns = tracker_cfg.get("log_patterns", {})
        if log_patterns and isinstance(log_patterns, dict):
            self._log_listener.reload_patterns(log_patterns)
        self._event_macros = list(general_cfg.get("log_event_macros", []) or [])
        self._event_macro_cooldowns: dict[str, float] = {}
        self._event_macro_freq_buckets: dict[str, list[float]] = {}

        relay_cfg = self.config.get("relay", {})
        if not isinstance(relay_cfg, dict):
            relay_cfg = {}
        self.relay_enabled = bool(relay_cfg.get("enabled", False))
        self.relay_group_to_mc = bool(relay_cfg.get("group_to_mc", False))
        self.relay_mc_to_group = bool(relay_cfg.get("mc_to_group", False))
        self.relay_fmt_group = str(relay_cfg.get("format_group", "[QQ] {name}: {msg}"))
        self.relay_fmt_mc = str(relay_cfg.get("format_mc", "[MC] {player}: {msg}"))
        self.relay_fmt_mc_log = str(relay_cfg.get("format_mc_log", "") or "")
        self.relay_require_msay = bool(relay_cfg.get("require_msay", False))
        self.relay_mc_to_group_log = bool(relay_cfg.get("mc_to_group_log", False))
        self.log_type_prefixes = relay_cfg.get("log_type_prefixes", {}) or {}
        self._relay_overrides = relay_cfg.get("group_settings", {})

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

        online_db_cfg = self.config.get("online_db", {})
        if not isinstance(online_db_cfg, dict):
            online_db_cfg = {}
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
        self._log_listener._positions_file = os.path.join(self.plugin_data_dir, "log_positions.json")
        _core_load_ranking_state(self)
        self.relay_overrides_path = os.path.join(self.plugin_data_dir, "relay_overrides.json")
        self._tracker_overrides = self._load_tracker_overrides()
        gov = self._load_general_overrides()
        if gov:
            gc = self.config.setdefault("general", {})
            for k, v in gov.items():
                if k not in gc or not gc[k]:
                    gc[k] = v
            logger.info(f"[mrcon] 通用覆盖已同步到内存: {list(gov.keys())}")
        json_macros = self._load_event_macros_json()
        if json_macros is not None:
            self._event_macros = json_macros
        elif self._event_macros:
            self._save_event_macros_json()
        self.scripts_dir = os.path.join(self.plugin_data_dir, str(general_cfg.get("scripts_dir", "scripts") or "scripts"))
        self.audit_file = os.path.join(self.plugin_data_dir, "audit.log")
        audit_cfg = self.config.get("audit", {})
        self.audit_auto_enabled = bool(audit_cfg.get("auto_enabled", True))
        self.audit_skip_categories = audit_cfg.get("skip_categories", []) or []
        self.pending_select = {}
        self.select_ttl = int(general_cfg.get("select_ttl", 30) or 30)
        self.rcn_persistent = bool(general_cfg.get("rcn_persistent", True))
        self.rcon_keepalive_interval = int(general_cfg.get("rcon_keepalive_interval", 180) or 180)
        self.rcon_idle_disconnect = int(general_cfg.get("rcon_idle_disconnect", 0) or 0)
        if self.rcn_persistent:
            get_pool().configure(
                keepalive_interval=self.rcon_keepalive_interval,
                idle_disconnect=self.rcon_idle_disconnect,
            )

        macros = self.config.get("macro_definitions", [])
        self.macros = {}
        if isinstance(macros, list):
            for m in macros:
                name = str(m.get("name", "")).strip()
                cmds = m.get("commands", [])
                if name and isinstance(cmds, list):
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

        groups_cfg = self.config.get("groups", [])
        if isinstance(groups_cfg, list):
            self.configured_groups = [str(g).strip() for g in groups_cfg if str(g).strip()]
        logger.info(f"[mrcon] 已配置群号列表: {self.configured_groups}")

        gn = self.config.get("group_names", {})
        if isinstance(gn, dict):
            self.group_names = {str(k): str(v) for k, v in gn.items()}
        logger.info(f"[mrcon] 群名称: {self.group_names}")

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

        self.script_settings_path = os.path.join(self.plugin_data_dir, "script_settings.json")
        self.script_settings = {}
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

        self.quick_cmd_settings_path = os.path.join(self.plugin_data_dir, "quick_cmd_settings.json")
        self.quick_cmd_settings = {}
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

        self.custom_cmds_path = os.path.join(self.plugin_data_dir, "custom_cmds.json")
        self.custom_cmds = {}
        try:
            if os.path.exists(self.custom_cmds_path):
                with open(self.custom_cmds_path, "r", encoding="utf-8") as f:
                    self.custom_cmds = json.load(f)
                    if not isinstance(self.custom_cmds, dict):
                        self.custom_cmds = {}
            logger.info(f"[mrcon] 已加载自定义命令映射 ({len(self.custom_cmds)} 群)")
        except Exception as e:
            logger.warning(f"[mrcon] 自定义命令映射加载失败: {e}")
            self.custom_cmds = {}

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
            if isinstance(srv, str):
                name = srv.strip()
                if name:
                    self.named_server_pool.append(name)
                    logger.info(f"[mrcon] 未绑定服务器名称: {name}")
                continue
            if not isinstance(srv, dict):
                continue
            gid = str(srv.get("group_id", "") or "").strip()
            name = str(srv.get("name", "") or srv.get("server_name", "") or "").strip()
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

        _gn_changed = False
        for gid, srvs in self.group_servers.items():
            gid_s = str(gid)
            if gid_s in self.group_names:
                continue
            for srv in srvs:
                if not isinstance(srv, dict):
                    continue
                host = (srv.get("rcon_host") or "").strip()
                web_mgmt = srv.get("web_management_enabled", True)
                if host and web_mgmt:
                    sn = (srv.get("server_name") or srv.get("display_name") or "").strip()
                    if sn:
                        self.group_names[gid_s] = sn
                        _gn_changed = True
                        break
        if _gn_changed:
            self.config["group_names"] = dict(self.group_names)
            try:
                self.config.save_config()
            except Exception as e:
                logger.warning(f"[mrcon] 自动填充 group_names 后保存失败: {e}")
            logger.info(f"[mrcon] group_names 自动填充完成: {self.group_names}")

        self._load_server_log_configs()
        self._load_relay_overrides()

        if isinstance(servers_raw, str) and servers_raw.strip():
            try:
                self.config["servers"] = servers
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
        if self.online_db_storage_mode in ("external", "dual") and (
            self.online_db_ext_path or self.online_db_ext_type == "mysql"
        ):
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
        self._online_duration_triggered = {}
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
        if self.log_listener_enabled:
            self._init_log_listeners()
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
        if self.web_panel_enabled:
            try:
                from .web.server import WebServer
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
        try:
            await self._log_listener.stop()
        except Exception:
            pass
        try:
            await get_pool().close_all()
        except Exception:
            pass
        logger.info("[mrcon] plugin stopped")

    # ==============================================================
    # 薄包装通知方法
    # ==============================================================

    def is_admin(self, qqid: str) -> bool:
        return _core_is_admin(self, qqid)

    def _get_group_id(self, event: AstrMessageEvent) -> str:
        return _core_get_group_id(self, event)

    def _rate_key(self, event: AstrMessageEvent) -> str:
        return _core_rate_key(self, event)

    def _ps_key(self, event: AstrMessageEvent) -> str:
        return _core_ps_key(self, event)

    def _check_rate(self, key: str) -> int:
        return _core_check_rate(self, key)

    def _touch_rate(self, key: str):
        _core_touch_rate(self, key)

    def _acquire_lock(self, key: str):
        return _core_acquire_lock(self, key)

    async def _schedule_select_timeout(self, event: AstrMessageEvent, key: str):
        return await _core_schedule_select_timeout(self, event, key)

    def _audit(self, event: AstrMessageEvent, cmd: str, ok: bool, resp: str, category: str = "cmd"):
        _core_audit(self, event, cmd, ok, resp, category)

    def _audit_web(self, op: str, detail: str = "", ok: bool = True, operator: str = "web"):
        _core_audit_web(self, op, detail, ok, operator)

    def _audit_web_cmd(self, op: str, detail: str = "", ok: bool = True, operator: str = "web"):
        _core_audit_web_cmd(self, op, detail, ok, operator)

    def _audit_auto(self, category: str, cmd: str, detail: str = "", ok: bool = True):
        _core_audit_auto(self, category, cmd, detail, ok)

    def _match_dangerous(self, cmd: str) -> bool:
        return _core_match_dangerous(self, cmd)

    def _extract_full_after_cmd(self, event: AstrMessageEvent, fallback: str) -> str:
        return _core_extract_full_after_cmd(self, event, fallback)

    def is_allowed(self, event: AstrMessageEvent) -> bool:
        return _core_is_allowed(self, event)

    async def _rcn_send(self, host: str, port: int, password: str, cmd: str) -> str:
        return await _core_rcn_send(self, host, port, password, cmd)

    async def transport_send(self, payload_json: str) -> str:
        return await _core_transport_send(self, payload_json)

    async def execute_and_reply(self, event: AstrMessageEvent, command: str, desc: str):
        async for msg in _core_execute_and_reply(self, event, command, desc):
            yield msg

    async def _execute_on_conf(self, event: AstrMessageEvent, conf: dict, command: str, desc: str):
        async for msg in _core_execute_on_conf(self, event, conf, command, desc):
            yield msg

    # ==============================================================
    # MC 服务器 CRUD（原 mcing 功能）
    # ==============================================================
    def _load_mcserv(self) -> dict:
        return _core_load_mcserv(self)

    def _save_mcserv(self, data: dict):
        _core_save_mcserv(self, data)

    def _save_cmd_tpls_init(self):
        _core_save_cmd_tpls_init(self)

    def _save_online_triggers(self):
        _core_save_online_triggers(self)

    def _save_script_settings(self):
        _core_save_script_settings(self)

    def _save_quick_cmd_settings(self):
        _core_save_quick_cmd_settings(self)

    def _save_custom_cmds(self):
        _core_save_custom_cmds(self)

    async def _check_online_triggers(self, player: str, srv_name: str, gid: str, conf: dict, now: int):
        return await _core_check_online_triggers(self, player, srv_name, gid, conf, now)

    def _get_group_serv_data(self, group_id: str) -> dict:
        return _core_get_group_serv_data(self, group_id)

    def _save_group_serv_data(self, group_id: str, data: dict):
        _core_save_group_serv_data(self, group_id, data)

    async def _get_mc_server_status(self, host: str, port: str):
        return await _core_get_mc_server_status(self, host, port)

    def _format_server_status(self, name: str, host: str, port: str, status: dict) -> str:
        return _core_format_server_status(self, name, host, port, status)

    # ==============================================================
    # 在线时长监控
    # ==============================================================
    async def _get_online_player_list(self, conf: dict) -> list:
        return await _core_get_online_player_list(self, conf)

    def _load_tracker_overrides(self) -> dict:
        return _core_load_tracker_overrides(self)

    def _save_tracker_overrides(self):
        _core_save_tracker_overrides(self)

    def _load_general_overrides(self) -> dict:
        return _core_load_general_overrides(self)

    def _save_general_overrides(self):
        _core_save_general_overrides(self)

    def _save_event_macros_json(self):
        _core_save_event_macros_json(self)

    def _load_event_macros_json(self):
        return _core_load_event_macros_json(self)

    def _load_server_log_configs(self):
        _core_load_server_log_configs(self)

    def _save_server_log_configs(self):
        _core_save_server_log_configs(self)

    _PLAYER_NAME_RE = re.compile(r'^[a-zA-Z0-9_]{3,16}$')

    @classmethod
    def _is_valid_player_name(cls, name: str) -> bool:
        return _is_valid_player_name(name)

    def _get_tracker_config(self, gid: str) -> dict:
        return _core_get_tracker_config(self, gid)

    async def _send_tracker_notify(self, gid: str, srv_name: str, player: str,
                                    dur_label: str, dur_text: str, tcfg: dict,
                                    is_kick: bool = False, error_msg: str = ""):
        return await _core_send_tracker_notify(self, gid, srv_name, player,
                                               dur_label, dur_text, tcfg,
                                               is_kick, error_msg)

    async def _online_tracker_loop(self):
        return await _core_online_tracker_loop(self)

    def _init_log_listeners(self):
        _core_init_log_listeners(self)

    async def _on_log_event(self, server_name: str, event_type: str, player: str, raw_line: str):
        return await _core_on_log_event(self, server_name, event_type, player, raw_line)

    def _get_group_umo(self, gid: str) -> str:
        return _core_get_group_umo(self, gid)

    def _resolve_group_display_name(self, gid: str) -> str:
        return _core_resolve_group_display_name(self, gid)

    async def _relay_log_event_to_groups(self, server_name: str, event_type: str, player: str, raw_line: str):
        return await _core_relay_log_event_to_groups(self, server_name, event_type, player, raw_line)

    async def _execute_event_macros(self, server_name: str, event_type: str, player: str, raw_line: str = ""):
        return await _core_execute_event_macros(self, server_name, event_type, player, raw_line)

    # ==============================================================
    # 玩家数据库（核心模块通过 plugin._xxx() 调用）
    # ==============================================================
    def _load_player_db(self) -> dict:
        return _core_load_player_db(self)

    def _save_player_db(self, data: dict):
        _core_save_player_db(self, data)

    def _get_player(self, qq_id: str) -> dict:
        return self.db.get_player(str(qq_id)) or None

    def _ensure_player(self, qq_id: str) -> dict:
        return self.db.ensure_player(str(qq_id))

    def _update_player(self, qq_id: str, updates: dict):
        self.db.update_player(str(qq_id), updates)

    def _check_comp_blacklist(self, rcon_cmd: str) -> str:
        if not self.pdb_comp_blacklist:
            return ""
        words = re.findall(r"\w+", rcon_cmd.lower())
        for banned in self.pdb_comp_blacklist:
            banned_lower = str(banned).lower()
            if banned_lower in words:
                return banned_lower
        return ""

    # ==============================================================
    # MC 查询命令
    # ==============================================================
    @filter.command("mc", desc="查询所有MC服务器状态", alias={"查询"})
    async def cmd_mc(self, event: AstrMessageEvent):
        async for msg in _core_cmd_mc(self, event):
            yield msg

    @filter.command("mcget", desc="查询单个服务器详情", alias={"服详情"})
    async def cmd_mcget(self, event: AstrMessageEvent, name: str = ""):
        async for msg in _core_cmd_mcget(self, event, name):
            yield msg

    @filter.command("mclist", desc="列出所有MC服务器", alias={"服列表"})
    async def cmd_mclist(self, event: AstrMessageEvent):
        async for msg in _core_cmd_mclist(self, event):
            yield msg

    @filter.command("mcadd", desc="添加MC服务器", alias={"加服"})
    async def cmd_mcadd(self, event: AstrMessageEvent, name: str = "", addr: str = ""):
        async for msg in _core_cmd_mcadd(self, event, name, addr):
            yield msg

    @filter.command("mcdel", desc="删除MC服务器", alias={"删服"})
    async def cmd_mcdel(self, event: AstrMessageEvent, name: str = ""):
        async for msg in _core_cmd_mcdel(self, event, name):
            yield msg

    @filter.command("改服", desc="更新MC服务器", alias={"mcup"})
    async def cmd_mcup(self, event: AstrMessageEvent, name: str = "", new_name: str = "", new_addr: str = ""):
        async for msg in _core_cmd_mcup(self, event, name, new_name, new_addr):
            yield msg

    @filter.command("共享服", desc="共享服务器到其他群", alias={"mcshare"})
    async def cmd_mcshare(self, event: AstrMessageEvent, name: str = "", target_gid: str = ""):
        async for msg in _core_cmd_mcshare(self, event, name, target_gid):
            yield msg

    @filter.command("取消共享", desc="取消共享", alias={"mcunshare"})
    async def cmd_mcunshare(self, event: AstrMessageEvent, name: str = "", target_gid: str = ""):
        async for msg in _core_cmd_mcunshare(self, event, name, target_gid):
            yield msg

    @filter.command("清理服", desc="清理失效服务器", alias={"mccleanup"})
    async def cmd_mccleanup(self, event: AstrMessageEvent):
        async for msg in _core_cmd_mccleanup(self, event):
            yield msg

    @filter.command("查询设置", desc="设置查询显示项", alias={"mcset"})
    async def cmd_mcset(self, event: AstrMessageEvent, key: str = "", value: str = ""):
        async for msg in _core_cmd_mcset(self, event, key, value):
            yield msg

    @filter.command("在线时长", desc="查看玩家在线时长排行", alias={"onlinetime"})
    async def cmd_onlinetime(self, event: AstrMessageEvent, target: str = ""):
        async for msg in _core_cmd_onlinetime(self, event, target):
            yield msg

    @filter.command("在线提醒", desc="当前群的在线提醒与踢出设置（管理员）")
    async def cmd_tracker_set(self, event: AstrMessageEvent, sub: str = "", val1: str = "", val2: str = ""):
        async for msg in _core_cmd_tracker_set(self, event, sub, val1, val2):
            yield msg

    # ==============================================================
    # 玩家数据库命令
    # ==============================================================
    @filter.command("绑定", desc="绑定MC账号（新玩家注册）", alias={"bind"})
    async def cmd_bind(self, event: AstrMessageEvent, mc_id: str = "", rest: str = ""):
        async for msg in _core_cmd_bind(self, event, mc_id, rest):
            yield msg

    @filter.command("签到", desc="每日签到（需先绑定MC账号）", alias={"checkin"})
    async def cmd_checkin(self, event: AstrMessageEvent):
        async for msg in _core_cmd_checkin(self, event):
            yield msg

    @filter.command("我的", desc="查看个人统计", alias={"mystats"})
    async def cmd_mystats(self, event: AstrMessageEvent):
        async for msg in _core_cmd_mystats(self, event):
            yield msg

    # ==============================================================
    # 补偿命令
    # ==============================================================
    @filter.command("理赔", desc="申请物品补偿（输入完整RCON命令）", alias={"赔", "comp", "compensate"})
    async def cmd_compensate(self, event: AstrMessageEvent, text: str = "", rest=None):
        async for msg in _core_cmd_compensate(self, event, text, rest):
            yield msg

    @filter.command("理赔列表", desc="查看补偿申请列表", alias={"赔单", "comp_list"})
    async def cmd_comp_list(self, event: AstrMessageEvent):
        async for msg in _core_cmd_comp_list(self, event):
            yield msg

    @filter.command("同意理赔", desc="批准补偿并执行RCON", alias={"comp_approve"})
    async def cmd_comp_approve(self, event: AstrMessageEvent, comp_id: str = ""):
        async for msg in _core_cmd_comp_approve(self, event, comp_id):
            yield msg

    @filter.command("拒绝理赔", desc="拒绝补偿申请", alias={"comp_reject"})
    async def cmd_comp_reject(self, event: AstrMessageEvent, comp_id: str = ""):
        async for msg in _core_cmd_comp_reject(self, event, comp_id):
            yield msg

    # ==============================================================
    # 积分兑换命令
    # ==============================================================
    @filter.command("兑换列表", desc="查看可用兑换项", alias={"shop", "exlist"})
    async def cmd_exchange_list(self, event: AstrMessageEvent):
        async for msg in _core_cmd_exchange_list(self, event):
            yield msg

    @filter.command("兑换", desc="使用积分兑换物品", alias={"redeem", "ex", "buy"})
    async def cmd_exchange(self, event: AstrMessageEvent, item_id: str = ""):
        async for msg in _core_cmd_exchange(self, event, item_id):
            yield msg

    # ==============================================================
    # 抽奖命令
    # ==============================================================
    @filter.command("抽奖", desc="消耗积分抽取奖品", alias={"lottery", "draw"})
    async def cmd_lottery(self, event: AstrMessageEvent):
        async for msg in _core_cmd_lottery(self, event):
            yield msg

    @filter.command("奖品列表", desc="查看当前群可抽取的奖品", alias={"prizes", "jp"})
    async def cmd_lottery_prizes(self, event: AstrMessageEvent):
        async for msg in _core_cmd_lottery_prizes(self, event):
            yield msg

    @filter.command("兑奖", desc="兑换中奖奖品", alias={"redeem_prize", "claim"})
    async def cmd_lottery_redeem(self, event: AstrMessageEvent, win_id: str = ""):
        async for msg in _core_cmd_lottery_redeem(self, event, win_id):
            yield msg

    @filter.command("我的中奖", desc="查看我的中奖记录", alias={"mywins", "wins"})
    async def cmd_lottery_my_wins(self, event: AstrMessageEvent):
        async for msg in _core_cmd_lottery_my_wins(self, event):
            yield msg

    # ==============================================================
    # 群服互联命令
    # ==============================================================
    @filter.command("msay", desc="主动发送消息到MC（群服互联前缀命令）", alias={"群说", "服说", "mcsay"})
    async def cmd_msay(self, event: AstrMessageEvent, text: str = "", rest=None):
        async for msg in _core_cmd_msay(self, event, text, rest):
            yield msg

    def _get_relay_override(self, gid: str) -> dict:
        return _core_get_relay_override(self, gid)

    def _save_relay_overrides(self):
        _core_save_relay_overrides(self)

    def _load_relay_overrides(self):
        _core_load_relay_overrides(self)

    def _get_relay_config(self, gid: str) -> dict:
        return _core_get_relay_config(self, gid)

    def _get_relay_conf(self, gid: str):
        return _core_get_relay_conf(self, gid)

    async def _on_mc_chat(self, server_name: str, player: str, message: str) -> int:
        return await _core_on_mc_chat(self, server_name, player, message)

    async def _relay_to_mc(self, event: AstrMessageEvent, user_name: str, message: str):
        return await _core_relay_to_mc(self, event, user_name, message)

    @filter.command("消息互通", desc="群服消息互联配置（管理员）", alias={"relay"})
    async def cmd_relay(self, event: AstrMessageEvent, sub: str = "", val: str = ""):
        async for msg in _core_cmd_relay(self, event, sub, val):
            yield msg

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def _on_group_message(self, event: AstrMessageEvent):
        async for msg in _core_on_group_message(self, event):
            yield msg

    async def _flush_pending_msgs(self, event: AstrMessageEvent):
        async for msg in _core_flush_pending_msgs(self, event):
            yield msg

    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    async def _flush_admin_dm(self, event: AstrMessageEvent):
        async for msg in _core_flush_admin_dm(self, event):
            yield msg

    # ==============================================================
    # RCON / 投票 / 宏 / 帮助 命令
    # ==============================================================

    @filter.command("mrcon", desc="将后续文本原样转发到 RCON 控制台", alias={"执行", "mcmd"})
    async def mrcon(self, event: AstrMessageEvent, text: str = "", rest=None):
        async for msg in _core_cmd_mrcon(self, event, text, rest):
            yield msg

    @filter.command("选服", desc="选择 RCON 服务器编号", alias={"rc选", "rcsel", "rcserver"})
    async def rcsel(self, event: AstrMessageEvent, index: str = ""):
        async for msg in _core_cmd_select_server(self, event, index):
            yield msg

    @filter.command("rc赞同", desc="对当前命令投票赞同")
    async def rc_agree(self, event: AstrMessageEvent):
        async for msg in _core_cmd_rc_agree(self, event):
            yield msg

    @filter.command("rc反对", desc="对当前命令投票反对")
    async def rc_disagree(self, event: AstrMessageEvent):
        async for msg in _core_cmd_rc_oppose(self, event):
            yield msg

    @filter.command("rc通过", desc="管理员裁决通过")
    async def rc_admin_pass(self, event: AstrMessageEvent):
        async for msg in _core_cmd_rc_pass(self, event):
            yield msg

    @filter.command("rc否决", desc="管理员裁决否决")
    async def rc_admin_reject(self, event: AstrMessageEvent):
        async for msg in _core_cmd_rc_veto(self, event):
            yield msg

    @filter.command("宏", desc="执行宏命令", alias={"rcm", "rcmacro"})
    async def rcmacro(self, event: AstrMessageEvent, name: str = "", args: str = ""):
        async for msg in _core_cmd_macro(self, event, name, args):
            yield msg

    @filter.command("脚本", desc="执行脚本文件", alias={"rcs", "rcscript"})
    async def rcscript(self, event: AstrMessageEvent, filename: str = ""):
        async for msg in _core_cmd_script(self, event, filename):
            yield msg

    @filter.command("rc自定", desc="执行自定义映射的RCON命令", alias={"rccustom"})
    async def cmd_custom(self, event: AstrMessageEvent, alias: str = ""):
        async for msg in _core_cmd_custom(self, event, alias):
            yield msg

    @filter.command("rchelp", desc="查看所有可用命令", alias={"rc帮助", "帮助", "help", "mchelp"})
    async def cmd_help(self, event: AstrMessageEvent):
        async for msg in _core_cmd_help(self, event):
            yield msg

    def _get_version(self) -> str:
        try:
            import yaml
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metadata.yaml")
            with open(p, "r", encoding="utf-8") as f:
                m = yaml.safe_load(f)
                return str(m.get("version", "?"))
        except Exception:
            return "?"