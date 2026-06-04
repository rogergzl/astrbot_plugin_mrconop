import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from astrbot.api import logger


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._ensure_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self):
        with self._lock:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            conn = self._connect()
            try:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS players (
                        qq_id TEXT PRIMARY KEY,
                        mc_id TEXT DEFAULT '',
                        points INTEGER DEFAULT 0,
                        checkin_streak INTEGER DEFAULT 0,
                        last_checkin_date TEXT DEFAULT '',
                        first_login INTEGER,
                        last_login INTEGER,
                        created_at INTEGER
                    );
                    CREATE TABLE IF NOT EXISTS online_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        server_name TEXT NOT NULL,
                        player_name TEXT NOT NULL,
                        start_ts INTEGER NOT NULL,
                        end_ts INTEGER NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_sessions_player ON online_sessions(player_name, server_name, start_ts);
                    CREATE TABLE IF NOT EXISTS compensations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        qq_id TEXT NOT NULL,
                        mc_id TEXT NOT NULL,
                        group_id TEXT DEFAULT '',
                        rcon_cmd TEXT NOT NULL,
                        description TEXT NOT NULL,
                        time INTEGER NOT NULL,
                        status TEXT DEFAULT 'pending'
                    );
                """)
                try:
                    conn.execute("ALTER TABLE compensations ADD COLUMN rcon_cmd TEXT NOT NULL DEFAULT ''")
                except sqlite3.OperationalError:
                    pass
                try:
                    conn.execute("ALTER TABLE compensations ADD COLUMN group_id TEXT DEFAULT ''")
                except sqlite3.OperationalError:
                    pass
                conn.commit()
            finally:
                conn.close()

    def find_player_by_mc_id(self, mc_id: str) -> dict | None:
        """通过 MC ID 查找玩家。返回 player dict 或 None。"""
        if not mc_id: return None
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute("SELECT * FROM players WHERE mc_id=?", (mc_id,))
                row = cur.fetchone()
                if row: return dict(row)
                return None
            finally: conn.close()

    def insert_player_raw(self, qq_id: str, mc_id: str = None, points: int = 50, created_at: int = None):
        """直接插入玩家记录（不检查是否存在）。"""
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute(
                    "INSERT OR IGNORE INTO players (qq_id, mc_id, points, checkin_streak, created_at) VALUES (?, ?, ?, 0, ?)",
                    (qq_id, mc_id if mc_id else None, points, created_at or int(time.time())))
                conn.commit()
                return cur.rowcount > 0
            finally: conn.close()

    def migrate_from_json(self, player_db_path: str, sessions_path: str):
        with self._lock:
            conn = self._connect()
            try:
                if os.path.exists(player_db_path):
                    try:
                        with open(player_db_path, "r", encoding="utf-8") as f:
                            old_db = json.load(f)
                    except Exception:
                        old_db = {}
                    players = old_db.get("players", {})
                    for qq_id, p in players.items():
                        conn.execute(
                            """INSERT OR REPLACE INTO players
                               (qq_id, mc_id, points, checkin_streak, last_checkin_date,
                                first_login, last_login, created_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (str(qq_id), str(p.get("mc_id", "")), int(p.get("points", 0)),
                             int(p.get("checkin_streak", 0)), str(p.get("last_checkin_date", "")),
                             int(p.get("first_login", 0) or 0), int(p.get("last_login", 0) or 0),
                             int(p.get("created_at", 0) or int(time.time()))),
                        )
                    comps = old_db.get("compensations", [])
                    for c in comps:
                        conn.execute(
                            """INSERT OR REPLACE INTO compensations
                               (id, qq_id, mc_id, description, time, status)
                               VALUES (?, ?, ?, ?, ?, ?)""",
                            (int(c.get("id", 0)), str(c.get("qq_id", "")), str(c.get("mc_id", "")),
                             str(c.get("desc", c.get("description", ""))), int(c.get("time", 0)),
                             str(c.get("status", "pending"))),
                        )
                    backup = player_db_path + ".bak." + str(int(time.time()))
                    try:
                        os.rename(player_db_path, backup)
                    except Exception:
                        pass
                    logger.info("[mrcon] player_db JSON 已迁移到 SQLite")

                if os.path.exists(sessions_path):
                    try:
                        with open(sessions_path, "r", encoding="utf-8") as f:
                            old_sessions = json.load(f)
                    except Exception:
                        old_sessions = {}
                    totals = old_sessions.get("totals", {})
                    for key, secs in totals.items():
                        parts = key.split(":", 1)
                        if len(parts) == 2:
                            srv, player = parts
                            now = int(time.time())
                            conn.execute(
                                "INSERT INTO online_sessions (server_name, player_name, start_ts, end_ts) VALUES (?, ?, ?, ?)",
                                (srv, player, now - int(secs), now),
                            )
                    backup = sessions_path + ".bak." + str(int(time.time()))
                    try:
                        os.rename(sessions_path, backup)
                    except Exception:
                        pass
                    logger.info("[mrcon] online_sessions JSON 已迁移到 SQLite")
                conn.commit()
            finally:
                conn.close()

    def ensure_player(self, qq_id: str) -> dict:
        """确保玩家记录存在，仅创建空记录（不设置 MC ID、积分等）"""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute("SELECT * FROM players WHERE qq_id = ?", (str(qq_id),)).fetchone()
                if row is None:
                    now = int(time.time())
                    conn.execute(
                        "INSERT INTO players (qq_id, mc_id, points, checkin_streak, last_checkin_date, first_login, last_login, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (str(qq_id), "", 0, 0, "", None, None, now),
                    )
                    conn.commit()
                    row = conn.execute("SELECT * FROM players WHERE qq_id = ?", (str(qq_id),)).fetchone()
                return dict(row) if row else {}
            finally:
                conn.close()

    def update_player(self, qq_id: str, updates: dict):
        with self._lock:
            conn = self._connect()
            try:
                # 支持修改 QQ 号（更换绑定）
                new_qq = str(updates.pop("qq_id", "")).strip() if "qq_id" in updates else ""
                if new_qq and new_qq != qq_id:
                    self.ensure_player(new_qq)
                    conn.execute("UPDATE players SET qq_id = ? WHERE qq_id = ?", (new_qq, str(qq_id)))
                    qq_id = new_qq
                else:
                    self.ensure_player(qq_id)
                allowed = {"mc_id", "points", "checkin_streak", "last_checkin_date", "first_login", "last_login"}
                sets = {k: v for k, v in updates.items() if k in allowed}
                if not sets:
                    return
                cols = ", ".join(f"{k}=?" for k in sets)
                vals = list(sets.values()) + [str(qq_id)]
                conn.execute(f"UPDATE players SET {cols} WHERE qq_id = ?", vals)
                conn.commit()
            finally:
                conn.close()

    def get_player(self, qq_id: str) -> dict:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute("SELECT * FROM players WHERE qq_id = ?", (str(qq_id),)).fetchone()
                return dict(row) if row else {}
            finally:
                conn.close()

    def add_online_session(self, server: str, player: str, start_ts: int, end_ts: int):
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO online_sessions (server_name, player_name, start_ts, end_ts) VALUES (?, ?, ?, ?)",
                    (server, player, start_ts, end_ts),
                )
                conn.commit()
            finally:
                conn.close()

    def get_player_total_seconds(self, player: str) -> int:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT SUM(end_ts - start_ts) as total FROM online_sessions WHERE player_name = ?",
                    (player,),
                ).fetchone()
                return int(row["total"] or 0) if row else 0
            finally:
                conn.close()

    def get_online_time_ranking(self, limit: int = 15, server_names: list = None) -> list:
        """获取在线时长排行，可选按服务器名列表过滤；server_names=[] 返回空"""
        if server_names is not None and len(server_names) == 0:
            return []
        with self._lock:
            conn = self._connect()
            try:
                if server_names:
                    placeholders = ",".join(["?"] * len(server_names))
                    rows = conn.execute(
                        f"""SELECT server_name, player_name, SUM(end_ts - start_ts) as total
                           FROM online_sessions WHERE server_name IN ({placeholders})
                           GROUP BY server_name, player_name
                           ORDER BY total DESC LIMIT ?""",
                        (*server_names, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """SELECT server_name, player_name, SUM(end_ts - start_ts) as total
                           FROM online_sessions GROUP BY server_name, player_name
                           ORDER BY total DESC LIMIT ?""",
                        (limit,),
                    ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def add_compensation(self, qq_id: str, mc_id: str, group_id: str, rcon_cmd: str, desc: str) -> int:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "INSERT INTO compensations (qq_id, mc_id, group_id, rcon_cmd, description, time, status) VALUES (?, ?, ?, ?, ?, ?, 'pending')",
                    (str(qq_id), str(mc_id), str(group_id), str(rcon_cmd), str(desc), int(time.time())),
                )
                conn.commit()
                return cur.lastrowid
            finally:
                conn.close()

    def get_compensation(self, comp_id: int) -> dict:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute("SELECT * FROM compensations WHERE id=?", (comp_id,)).fetchone()
                return dict(row) if row else {}
            finally:
                conn.close()

    def get_pending_compensations(self) -> list:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute("SELECT * FROM compensations WHERE status='pending' ORDER BY time ASC LIMIT 20").fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_all_compensations(self, status: str = "", limit: int = 100) -> list:
        with self._lock:
            conn = self._connect()
            try:
                if status and status != "all":
                    rows = conn.execute(
                        "SELECT * FROM compensations WHERE status=? ORDER BY time DESC LIMIT ?",
                        (status, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM compensations ORDER BY time DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def count_compensations(self, status: str = "") -> int:
        with self._lock:
            conn = self._connect()
            try:
                if status and status != "all":
                    row = conn.execute(
                        "SELECT COUNT(*) as cnt FROM compensations WHERE status=?",
                        (status,),
                    ).fetchone()
                else:
                    row = conn.execute("SELECT COUNT(*) as cnt FROM compensations").fetchone()
                return int(row["cnt"]) if row else 0
            finally:
                conn.close()

    def count_players(self) -> int:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute("SELECT COUNT(*) as cnt FROM players").fetchone()
                return int(row["cnt"]) if row else 0
            finally:
                conn.close()

    def get_all_players(self, limit: int = 200) -> list:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT qq_id, mc_id, points, checkin_streak, last_checkin_date, created_at FROM players ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def delete_player(self, qq_id: str) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute("DELETE FROM players WHERE qq_id = ?", (str(qq_id),))
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def update_compensation(self, comp_id: int, status: str):
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("UPDATE compensations SET status=? WHERE id=?", (status, comp_id))
                conn.commit()
            finally:
                conn.close()
