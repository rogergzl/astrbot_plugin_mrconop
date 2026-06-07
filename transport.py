import asyncio
import logging
import struct
import time

logger = logging.getLogger("mrcon.rcon")

class AsyncRcon:
    def __init__(self, host: str, port: int, password: str):
        self.host = host
        self.port = port
        self.password = password
        self.reader = None
        self.writer = None

    async def connect(self):
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        await self._send_packet(0, 3, self.password)
        await self._recv_packet()

    async def send_cmd(self, command: str) -> str:
        await self._send_packet(1, 2, command)
        _, _, body = await self._recv_packet()
        return body

    async def close(self):
        if self.writer:
            try:
                self.writer.close()
                await asyncio.wait_for(self.writer.wait_closed(), timeout=5)
            except (asyncio.TimeoutError, Exception):
                pass
            self.writer = None
            self.reader = None

    async def _send_packet(self, req_id: int, ptype: int, payload: str):
        data = struct.pack("<ii", req_id, ptype) + payload.encode() + b"\x00\x00"
        length = struct.pack("<i", len(data))
        self.writer.write(length + data)
        await self.writer.drain()

    async def _recv_packet(self):
        length_bytes = await self.reader.readexactly(4)
        length = struct.unpack("<i", length_bytes)[0]
        data = await self.reader.readexactly(length)
        req_id, ptype = struct.unpack("<ii", data[:8])
        body = data[8:].rstrip(b"\x00").decode(errors="ignore")
        return req_id, ptype, body


class RconPool:
    """RCON 长连接池：按 (host, port, password) 维护持久连接，避免短连接风暴"""

    def __init__(self):
        self._conns: dict[tuple, AsyncRcon] = {}
        self._locks: dict[tuple, asyncio.Lock] = {}
        self._last_used: dict[tuple, float] = {}
        self._keepalive_task: asyncio.Task = None
        self._keepalive_interval = 180  # 默认3分钟保活（可在 configure() 覆盖）
        self._idle_disconnect = 0       # 0=不自动断开空闲连接
        self._keepalive_cmd = "list"

    def configure(self, keepalive_interval: int = None, idle_disconnect: int = None):
        """运行时更新保活/空闲参数。间隔变更时自动重启保活任务"""
        if keepalive_interval is not None:
            old = self._keepalive_interval
            self._keepalive_interval = keepalive_interval
            if keepalive_interval != old:
                logger.info(f"[RCON池] 保活间隔 {old}s → {keepalive_interval}s")
                self._restart_keepalive()
        if idle_disconnect is not None:
            self._idle_disconnect = idle_disconnect
            logger.info(f"[RCON池] 空闲断开 {'禁用' if idle_disconnect <= 0 else f'{idle_disconnect}s'}")

    def _key(self, host: str, port: int, password: str) -> tuple:
        return (host, str(port), password)

    def _start_keepalive(self):
        """启动保活后台任务（幂等）"""
        if self._keepalive_interval <= 0:
            return
        if self._keepalive_task is None or self._keepalive_task.done():
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())

    def _restart_keepalive(self):
        """重启保活任务（用于间隔变更时）"""
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
        self._keepalive_task = None
        if self._keepalive_interval > 0:
            self._start_keepalive()

    async def _keepalive_loop(self):
        """保活循环：定期发送心跳命令 + 空闲连接回收"""
        while True:
            await asyncio.sleep(self._keepalive_interval)
            now = time.time()
            for key in list(self._conns.keys()):
                rcon = self._conns.get(key)
                if rcon is None:
                    continue

                # 检查写端是否已被动关闭（MC 服务端断开）
                if rcon.writer is None or rcon.writer.is_closing():
                    logger.info(f"[RCON池] 连接已被动断开 {key[0]}:{key[1]}（MC服务端关闭）")
                    try:
                        await rcon.close()
                    except Exception:
                        pass
                    self._conns.pop(key, None)
                    continue

                # 空闲断开检查
                last = self._last_used.get(key, 0)
                idle_secs = now - last
                if self._idle_disconnect > 0 and idle_secs > self._idle_disconnect:
                    logger.info(f"[RCON池] 主动断开空闲连接 {key[0]}:{key[1]}（空闲 {idle_secs:.0f}s > {self._idle_disconnect}s）")
                    try:
                        await rcon.close()
                    except Exception:
                        pass
                    self._conns.pop(key, None)
                    continue

                # 跳过正在执行命令的连接
                lock = self._locks.get(key)
                if lock and lock.locked():
                    continue

                # 发送心跳
                try:
                    async with self._locks[key]:
                        await rcon.send_cmd(self._keepalive_cmd)
                except Exception:
                    logger.info(f"[RCON池] 保活时连接断开 {key[0]}:{key[1]}（将在下次使用时重连）")
                    try:
                        await rcon.close()
                    except Exception:
                        pass
                    self._conns.pop(key, None)

    async def _ensure_conn(self, key: tuple, host: str, port: int, password: str) -> AsyncRcon:
        """确保连接可用，断线自动重连"""
        rcon = self._conns.get(key)
        if rcon is None or rcon.writer is None or rcon.writer.is_closing():
            if rcon:
                if rcon.writer and rcon.writer.is_closing():
                    logger.info(f"[RCON池] 使用时发现连接已断开 {host}:{port}，重建中")
                try:
                    await rcon.close()
                except Exception:
                    pass
            rcon = AsyncRcon(host, port, password)
            await rcon.connect()
            self._conns[key] = rcon
            self._last_used[key] = time.time()
            self._start_keepalive()
            logger.info(f"[RCON池] 新建长连接 {host}:{port}")
        return rcon

    async def execute(self, host: str, port: int, password: str, command: str) -> str:
        key = self._key(host, port, password)
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()

        async with self._locks[key]:
            try:
                rcon = await self._ensure_conn(key, host, port, password)
                self._last_used[key] = time.time()
                result = await rcon.send_cmd(command)
                return result
            except Exception:
                logger.info(f"[RCON池] 命令执行时连接异常 {host}:{port}，尝试重建")
                try:
                    rcon = self._conns.get(key)
                    if rcon:
                        await rcon.close()
                except Exception:
                    pass
                self._conns.pop(key, None)
                rcon = await self._ensure_conn(key, host, port, password)
                self._last_used[key] = time.time()
                result = await rcon.send_cmd(command)
                return result

    async def close_all(self):
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
            self._keepalive_task = None
        for key in list(self._conns.keys()):
            rcon = self._conns.pop(key, None)
            if rcon:
                try:
                    await rcon.close()
                except Exception:
                    pass
        self._locks.clear()
        logger.info("[RCON池] 已关闭所有长连接")


# 全局连接池实例
_pool = RconPool()


def get_pool() -> RconPool:
    return _pool


async def rcon_command(host: str, port: int, password: str, command: str) -> str:
    """执行RCON命令（快捷方式，每次新建连接后关闭）"""
    rcon = AsyncRcon(host, port, password)
    await rcon.connect()
    try:
        return await rcon.send_cmd(command)
    finally:
        await rcon.close()


async def rcon_command_pool(host: str, port: int, password: str, command: str) -> str:
    """执行RCON命令（长连接池模式，连接自动维护复用）"""
    return await _pool.execute(host, port, password, command)
