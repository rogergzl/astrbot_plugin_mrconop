"""Minecraft 服务端日志文件监听 — 解析事件 + 全量日志缓冲区供 Web 查看"""
import asyncio
import collections
import json
import logging
import os
import re
import time

logger = logging.getLogger("mrcon.log_listener")

# ── 默认日志行分类模式（按优先级排列） ──────────────────────────
DEFAULT_LOG_PATTERNS = [
    # 标签格式的异步聊天 [Async Chat Thread - #N/INFO]: <Player> Message
    ("chat", re.compile(r'<\s*(\w+)\s*>\s+(.+)')),
    # 指令
    ("command", re.compile(r'(\w+) issued server command:')),
    # 事件
    ("player_join", re.compile(r'(\w+) joined the game')),
    ("player_leave", re.compile(r'(\w+) left the game')),
    ("player_chat", re.compile(r'<\s*(\w+)\s*>\s+(.+)')),  # 预置类型（与 chat 同正则），实际由 main._on_log_event 从 chat 事件派生；供自定义覆写
    ("player_death", re.compile(
        r'(\w+) (?:drowned|'
        r'fell|went up in flames|burned to death|starved to death|'
        r'was squished|was pricked to death|walked into|experienced kinetic energy|'
        r'blew up|was blown up|was fireballed|was stung to death|'
        r'hit the ground too hard|fell out of the world|'
        r'was impaled by|withered away|died|suffocated|'
        r'was poked to death|was obliterated|'
        r'was squashed|froze to death|'
        r'discovered the floor was lava|'
        r'went off with a bang|'
        r'was pummeled|was skewered|was roasted|was shredded)'
    )),
    ("player_advancement", re.compile(r'(\w+) has (?:completed the challenge|made the advancement)')),
    # 玩家复活
    ("player_respawn", re.compile(r'(\w+) (?:respawned|has respawned|returned to life|awoke|has come back)')),
    # 玩家被踢出 / 断连
    ("player_kick", re.compile(r'(\w+) lost connection:')),
    # PVP 击杀: 玩家被另一玩家击杀
    ("player_death_pvp", re.compile(r'(\w+) was (?:slain|killed|shot|frozen) by (\w+)')),
    # 物品获得
    ("player_item_get", re.compile(r'(\w+) has (?:obtained|acquired|received)')),
    # 服务器生命周期
    ("server_start", re.compile(r'Done \([^)]+\)!')),
    ("server_stop", re.compile(r'Stopping(?: the)? server')),
    ("server_reload", re.compile(r'Reloading')),
    # Boss 击杀 (通用模组)
    ("boss_kill", re.compile(r'(\w+) (?:has defeated|killed|slain) (?!the )(.+)')),
    # TPS / 性能 / 内存告警 (Server 端日志)
    ("tps_low", re.compile(r"Can't keep up!")),  # Vanilla/Paper "Can't keep up! Is the server overloaded?"
    ("tps_critical", re.compile(r"Running\s+\d+ms\s+or\s+\d+\s+ticks\s+behind")),  # 严重延迟告警
    ("memory_high", re.compile(r"(?:Memory|OutOfMemory|Out of memory)")),  # 内存告警
    ("server_perf_issue", re.compile(r"(?:overloaded|server\s+is\s+lagging|skipping\s+\d+\s+tick)")),  # 综合性能异常
    # RCON 连接日志（标记为 system）
    ("system", re.compile(r'Thread RCON Client')),
    # 模组日志（标记为 system）
    ("system", re.compile(r'\[(?:AstrBot|[Mm]rcon|Enigmatic Legacy|Ice and Fire|Tetra|[Bb]elt)[^\]]*\]')),
]

EventCallback = None  # type: ignore

# ── 全量日志缓冲区 ─────────────────────────────────────────
MAX_LOG_ENTRIES = 2000


def _classify_line_static(line: str, patterns: list | None = None) -> tuple[str, str, str]:
    """静态分类函数，接受 patterns 参数。返回 (type, player, extra)"""
    if patterns is None:
        patterns = DEFAULT_LOG_PATTERNS
    for etype, ptn in patterns:
        m = ptn.search(line)
        if m:
            try:
                player = m.group(1)
            except IndexError:
                player = ""
            try:
                extra = m.group(2) if etype in ("chat",) else ""
            except IndexError:
                extra = ""
            return (etype, player, extra)
    return ("other", "", "")


# ── LogWatcher ─────────────────────────────────────────────

class LogWatcher:
    """监视单个 Minecraft 日志文件"""

    def __init__(self, log_path: str, server_name: str, classify_fn=None):
        self.log_path = log_path
        self.server_name = server_name
        self._position = 0
        self._inode = 0
        self._classify_fn = classify_fn or _classify_line_static

    def start(self):
        """跳到文件末尾（只处理新行）"""
        try:
            if os.path.exists(self.log_path):
                self._position = os.path.getsize(self.log_path)
                self._inode = os.stat(self.log_path).st_ino
                logger.info(f"[LogWatcher] {self.server_name} 监听 {self.log_path} pos={self._position}")
            else:
                logger.warning(f"[LogWatcher] {self.server_name} 日志文件不存在: {self.log_path}")
        except Exception as e:
            logger.warning(f"[LogWatcher] {self.server_name} start error: {e}")

    def poll(self) -> list[dict]:
        """同步读取新行，返回结构化日志条目列表"""
        entries = []
        try:
            if not os.path.exists(self.log_path):
                return entries
            # 检测日志轮转（inode 变化）
            try:
                st = os.stat(self.log_path)
                if st.st_ino != self._inode and self._inode:
                    logger.debug(f"[LogWatcher] {self.server_name} 日志已轮转")
                    self._position = 0
                self._inode = st.st_ino
            except OSError:
                return entries
            current_size = os.path.getsize(self.log_path)
            if current_size < self._position:
                self._position = 0
            if current_size <= self._position:
                return entries
            with open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(self._position)
                new_data = f.read()
                self._position = f.tell()
            _now = time.time()
            for line in new_data.splitlines():
                line = line.strip()
                if not line:
                    continue
                etype, player, extra = self._classify_fn(line)
                entries.append({
                    "ts": _now,
                    "server": self.server_name,
                    "type": etype,
                    "player": player,
                    "extra": extra,
                    "text": line,
                })
        except Exception as e:
            logger.debug(f"[LogWatcher] poll error {self.log_path}: {e}")
        return entries


# ── LogListenerManager ─────────────────────────────────────

class LogListenerManager:
    """管理多服务器日志监视器 + 全量日志缓冲区"""

    POLL_INTERVAL = 0.5
    POSITION_SAVE_INTERVAL = 30  # 位置持久化间隔（秒）

    def __init__(self, positions_file: str = ""):
        self._watchers: dict[str, LogWatcher] = {}
        self._task: asyncio.Task | None = None
        self._running = False
        # 全量缓冲区（线程安全由 asyncio 单线程保证）
        self._buffer: collections.deque = collections.deque(maxlen=MAX_LOG_ENTRIES)
        # 日志分类模式（可动态配置）
        self._patterns: list = list(DEFAULT_LOG_PATTERNS)
        # 日志文件读取位置持久化路径
        self._positions_file = positions_file
        self._last_position_save = 0.0

    def _classify_line(self, line: str) -> tuple[str, str, str]:
        """使用当前配置的模式分类日志行"""
        return _classify_line_static(line, self._patterns)

    # ── 读取位置持久化 ───────────────────────────────────

    def _load_positions(self) -> dict:
        """从 JSON 文件加载上次保存的读取位置。返回 {key: {position, inode}}"""
        if not self._positions_file or not os.path.isfile(self._positions_file):
            return {}
        try:
            with open(self._positions_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception as e:
            logger.debug(f"[LogListener] 加载日志位置失败: {e}")
        return {}

    def _save_positions(self):
        """将当前所有 watcher 的读取位置写入 JSON 文件"""
        if not self._positions_file:
            return
        try:
            data = {}
            for key, w in self._watchers.items():
                data[key] = {"position": w._position, "inode": w._inode}
            os.makedirs(os.path.dirname(self._positions_file), exist_ok=True)
            with open(self._positions_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            logger.debug(f"[LogListener] 保存日志位置失败: {e}")

    def _restore_positions(self):
        """将已保存的位置恢复到 watcher"""
        saved = self._load_positions()
        if not saved:
            return
        restored = 0
        for key, w in self._watchers.items():
            if key in saved:
                pos_data = saved[key]
                try:
                    # 校验文件未变化（inode 匹配 + 文件大小 >= 位置）
                    if os.path.exists(w.log_path):
                        st = os.stat(w.log_path)
                        if st.st_ino == pos_data.get("inode", 0) and st.st_size >= pos_data.get("position", 0):
                            w._position = pos_data["position"]
                            w._inode = pos_data["inode"]
                            restored += 1
                            logger.info(f"[LogWatcher] {w.server_name} 恢复位置 pos={w._position}")
                            continue
                except Exception:
                    pass
            # 无法恢复则跳到末尾
            w.start()
        if restored:
            logger.info(f"[LogListener] 已恢复 {restored} 个日志文件的读取位置")

    def reload_patterns(self, user_patterns: dict[str, str] | None = None):
        """动态更新日志分类模式。user_patterns: {type: regex_string}，用户模式优先于默认"""
        patterns = list(DEFAULT_LOG_PATTERNS)
        if user_patterns:
            for etype, pattern_str in user_patterns.items():
                if not pattern_str or not str(pattern_str).strip():
                    continue
                try:
                    patterns.insert(0, (etype, re.compile(str(pattern_str))))
                    logger.info(f"[LogListener] 加载用户模式: {etype} = {pattern_str}")
                except re.error as e:
                    logger.warning(f"[LogListener] 用户模式编译失败 {etype}: {e}")
        self._patterns = patterns
        # 更新所有已有 watcher 的分类函数
        for watcher in self._watchers.values():
            watcher._classify_fn = self._classify_line

    def get_patterns(self) -> dict[str, str]:
        """返回当前用户自定义的模式（用于 Web 面板展示）"""
        # 找出用户添加的模式（不在默认列表中的）
        result = {}
        default_strs = {str(ptn.pattern) for _, ptn in DEFAULT_LOG_PATTERNS}
        for etype, ptn in self._patterns:
            ptn_str = str(ptn.pattern)
            if ptn_str not in default_strs:
                if etype not in result:
                    result[etype] = ptn_str
        return result

    # ── 缓冲区读写 ─────────────────────────────────────────

    def push_line(self, entry: dict):
        """手动推入一条日志（供插件记录自身 RCON 操作）"""
        self._buffer.append(entry)

    def get_recent(self, limit: int = 200, types: list[str] | None = None,
                    server: str | None = None, player: str | None = None) -> list[dict]:
        """获取最近的日志条目，支持多维过滤"""
        result = []
        for entry in reversed(self._buffer):
            if types and entry.get("type") not in types:
                continue
            if server and entry.get("server") != server:
                continue
            if player and player.lower() not in entry.get("player", "").lower():
                continue
            result.append(entry)
            if len(result) >= limit:
                break
        return result

    def get_servers(self) -> list[str]:
        """返回正在监听的服务器列表（去重）"""
        names = set()
        for k in self._watchers:
            server = k.split("@@")[0]
            names.add(server)
        return sorted(names)

    # ── 连接管理 ───────────────────────────────────────────

    def _watcher_key(self, server_name: str, log_path: str) -> str:
        return f"{server_name}@@{log_path}"

    def add(self, server_name: str, log_path: str):
        key = self._watcher_key(server_name, log_path)
        if key in self._watchers:
            return
        if not log_path or not os.path.isfile(log_path):
            logger.warning(f"[LogListener] 日志文件不存在: {log_path}")
            return
        w = LogWatcher(log_path, server_name, self._classify_line)
        w.start()
        self._watchers[key] = w

    def remove(self, server_name: str):
        keys = [k for k in self._watchers if k.startswith(server_name + "@@")]
        for k in keys:
            self._watchers.pop(k, None)

    def remove_path(self, server_name: str, log_path: str):
        key = self._watcher_key(server_name, log_path)
        self._watchers.pop(key, None)

    def clear(self):
        self._watchers.clear()

    def start(self, callback):
        """启动后台轮询。callback(server_name, event_type, player, raw_line)"""
        global EventCallback
        EventCallback = callback
        self._running = True
        # 尝试从持久化文件恢复位置（覆盖 add() 中的跳末尾）
        self._restore_positions()
        self._task = asyncio.create_task(self._run())
        logger.info(f"[LogListener] 启动，监听 {len(self._watchers)} 个服务器")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            self._task = None
        self._save_positions()
        self.clear()
        logger.info("[LogListener] 已停止")

    async def _run(self):
        while self._running:
            await asyncio.sleep(self.POLL_INTERVAL)
            now_ts = time.time()
            for watcher in list(self._watchers.values()):
                try:
                    entries = watcher.poll()
                    for entry in entries:
                        # 存入缓冲区
                        self._buffer.append(entry)
                        # 事件回调（chat + 游戏事件都触发）
                        etype = entry["type"]
                        if etype in ("player_join", "player_leave", "player_death", "player_death_pvp", "player_advancement", "player_first_join", "player_first_death", "admin_join", "vip_join", "chat", "player_chat", "command", "system", "other", "player_kick", "player_item_get", "server_start", "server_stop", "server_reload", "boss_kill", "player_respawn"):
                            try:
                                if EventCallback:
                                    await EventCallback(
                                        entry["server"], etype,
                                        entry["player"], entry["text"],
                                    )
                            except Exception as e:
                                logger.debug(f"[LogListener] callback error: {e}")
                except Exception as e:
                    logger.debug(f"[LogListener] poll loop error: {e}")
            # 定期持久化读取位置
            if now_ts - self._last_position_save >= self.POSITION_SAVE_INTERVAL:
                self._save_positions()
                self._last_position_save = now_ts
