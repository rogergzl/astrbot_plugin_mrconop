"""Minecraft 服务端日志文件监听 — 解析事件 + 全量日志缓冲区供 Web 查看"""
import asyncio
import collections
import logging
import os
import re
import time

logger = logging.getLogger("mrcon.log_listener")

# ── 日志行分类模式（按优先级排列） ──────────────────────────
_LOG_PATTERNS = [
    # 标签格式的异步聊天 [Async Chat Thread - #N/INFO]: <Player> Message
    ("chat", re.compile(r'<\s*(\w+)\s*>\s+(.+)')),
    # 指令
    ("command", re.compile(r'(\w+) issued server command:')),
    # 事件
    ("player_join", re.compile(r'(\w+) joined the game')),
    ("player_leave", re.compile(r'(\w+) left the game')),
    ("player_death", re.compile(
        r'(\w+) (?:was shot by|was slain by|was killed by|was frozen by|drowned|'
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
    # RCON 连接日志（标记为 system）
    ("system", re.compile(r'Thread RCON Client')),
    # 模组日志（标记为 system）
    ("system", re.compile(r'\[(?:AstrBot|[Mm]rcon|Enigmatic Legacy|Ice and Fire|Tetra|[Bb]elt)\w*\]')),
]

EventCallback = None  # type: ignore

# ── 全量日志缓冲区 ─────────────────────────────────────────
MAX_LOG_ENTRIES = 2000


def _classify_line(line: str) -> tuple[str, str, str]:
    """返回 (type, player, extra)。type: chat/command/player_*/system/other"""
    for etype, pattern in _LOG_PATTERNS:
        m = pattern.search(line)
        if m:
            player = m.group(1)
            extra = m.group(2) if etype in ("chat",) else ""
            return (etype, player, extra)
    return ("other", "", "")


def _is_info_line(line: str) -> bool:
    """过滤：只保留有意义的信息行"""
    return bool(re.search(r'Thread.*(?:INFO|WARN|ERROR)\]', line))


# ── LogWatcher ─────────────────────────────────────────────

class LogWatcher:
    """监视单个 Minecraft 日志文件"""

    def __init__(self, log_path: str, server_name: str):
        self.log_path = log_path
        self.server_name = server_name
        self._position = 0
        self._inode = 0

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
                etype, player, extra = _classify_line(line)
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

    def __init__(self):
        self._watchers: dict[str, LogWatcher] = {}
        self._task: asyncio.Task | None = None
        self._running = False
        # 全量缓冲区（线程安全由 asyncio 单线程保证）
        self._buffer: collections.deque = collections.deque(maxlen=MAX_LOG_ENTRIES)

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
        w = LogWatcher(log_path, server_name)
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
        self.clear()
        logger.info("[LogListener] 已停止")

    async def _run(self):
        while self._running:
            await asyncio.sleep(self.POLL_INTERVAL)
            for watcher in list(self._watchers.values()):
                try:
                    entries = watcher.poll()
                    for entry in entries:
                        # 存入缓冲区
                        self._buffer.append(entry)
                        # 事件回调（chat + 游戏事件都触发）
                        etype = entry["type"]
                        if etype in ("player_join", "player_leave", "player_death", "player_advancement", "chat"):
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
