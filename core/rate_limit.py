import asyncio
import time

from .permission import _get_group_id


def _rate_key(plugin, event) -> str:
    return f"{_get_group_id(plugin, event)}:{event.get_sender_id()}"


def _ps_key(plugin, event) -> str:
    return f"{_get_group_id(plugin, event)}:{event.get_sender_id()}"


def _check_rate(plugin, key: str) -> int:
    if plugin.rate_limit_ms <= 0 and not plugin.rate_enabled:
        return 0
    now = int(time.time() * 1000)
    now_s = int(time.time())
    if not plugin.rate_enabled:
        last = int(plugin.rate_state.get(key, {}).get("last_exec", 0) or 0)
        if now - last < plugin.rate_limit_ms:
            return plugin.rate_limit_ms - (now - last)
        return 0
    state = plugin.rate_state.get(key)
    if state is None:
        state = {"timestamps": [], "interval_ms": plugin.rate_base_ms, "last_exec": 0}
        plugin.rate_state[key] = state
    timestamps = [ts for ts in state["timestamps"] if now_s - ts <= plugin.rate_window_s]
    state["timestamps"] = timestamps
    if plugin.rate_auto_recovery and not timestamps:
        last_exec_s = state.get("last_exec", 0) // 1000
        if last_exec_s and now_s - last_exec_s >= plugin.rate_recovery_s:
            state["interval_ms"] = plugin.rate_base_ms
    count = len(timestamps)
    interval = state["interval_ms"]
    if count >= plugin.rate_threshold:
        over_count = count - plugin.rate_threshold + 1
        interval = min(plugin.rate_max_ms, plugin.rate_base_ms + over_count * plugin.rate_increment_ms)
        state["interval_ms"] = interval
    last_exec = state.get("last_exec", 0) or 0
    if last_exec and now - last_exec < interval:
        return interval - (now - last_exec)
    return 0


def _touch_rate(plugin, key: str):
    now = int(time.time() * 1000)
    if plugin.rate_enabled:
        state = plugin.rate_state.get(key)
        if state is None:
            state = {"timestamps": [], "interval_ms": plugin.rate_base_ms, "last_exec": 0}
            plugin.rate_state[key] = state
        state["timestamps"].append(int(time.time()))
        state["last_exec"] = now
    elif plugin.rate_limit_ms > 0:
        state = plugin.rate_state.get(key)
        if state is None:
            state = {"timestamps": [], "interval_ms": plugin.rate_limit_ms, "last_exec": 0}
            plugin.rate_state[key] = state
        state["last_exec"] = now


def _acquire_lock(plugin, key: str):
    lock = plugin.group_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        plugin.group_locks[key] = lock
    return lock
