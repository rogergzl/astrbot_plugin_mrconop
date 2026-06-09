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
        self._ext_db = None  # 外部数据库实例
        self._storage_mode = "local"  # local / external / dual
        self._read_source = "local"   # local / external
        self._ensure_schema()

    def configure_external(self, ext_type: str = "", host: str = "", port: int = 3306,
                           user: str = "", password: str = "", database: str = "",
                           ext_db_path: str = ""):
        """配置外部数据库"""
        if ext_type == "sqlite" and ext_db_path:
            try:
                self._ext_db = ExternalSQLiteDB(ext_db_path)
                logger.info(f"[mrcon] 外部数据库已配置: sqlite -> {ext_db_path}")
            except Exception as e:
                logger.error(f"[mrcon] 外部数据库连接失败: {e}")
                self._ext_db = None
        elif ext_type == "mysql" and host and database:
            try:
                self._ext_db = ExternalMySQLDB(
                    host=host, port=int(port) if port else 3306,
                    user=user, password=password, database=database,
                )
                logger.info(f"[mrcon] 外部数据库已配置: mysql -> {host}:{port}/{database}")
            except Exception as e:
                logger.error(f"[mrcon] 外部 MySQL 数据库连接失败: {e}")
                self._ext_db = None
        elif ext_type == "postgresql" and host and database:
            logger.info(f"[mrcon] 外部数据库类型 postgresql 预留，当前仅支持 SQLite/MySQL")
            self._ext_db = None

    def set_storage_mode(self, storage_mode: str, read_source: str = "local"):
        """设置存储模式: local / external / dual"""
        self._storage_mode = storage_mode
        self._read_source = read_source

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
                    CREATE TABLE IF NOT EXISTS online_state (
                        server_name TEXT NOT NULL,
                        player_name TEXT NOT NULL,
                        gid TEXT DEFAULT '',
                        login_at INTEGER NOT NULL,
                        UNIQUE(server_name, player_name)
                    );
                    CREATE TABLE IF NOT EXISTS exchange_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        group_id TEXT DEFAULT '',
                        name TEXT NOT NULL,
                        description TEXT DEFAULT '',
                        rcon_cmd TEXT NOT NULL,
                        cost_points INTEGER NOT NULL DEFAULT 0,
                        enabled INTEGER NOT NULL DEFAULT 1
                    );
                    CREATE TABLE IF NOT EXISTS lottery_prizes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        group_id TEXT DEFAULT '',
                        name TEXT NOT NULL,
                        description TEXT DEFAULT '',
                        probability REAL NOT NULL DEFAULT 0.1,
                        count INTEGER NOT NULL DEFAULT 1,
                        rcon_cmd TEXT NOT NULL,
                        cost_points INTEGER NOT NULL DEFAULT 0,
                        enabled INTEGER NOT NULL DEFAULT 1
                    );
                    CREATE TABLE IF NOT EXISTS lottery_wins (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        qq_id TEXT NOT NULL,
                        mc_id TEXT NOT NULL,
                        group_id TEXT NOT NULL,
                        prize_name TEXT NOT NULL,
                        prize_cmd TEXT NOT NULL,
                        win_time INTEGER NOT NULL,
                        redeemed INTEGER NOT NULL DEFAULT 0
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
                try:
                    conn.execute("ALTER TABLE players ADD COLUMN vip_level INTEGER DEFAULT 0")
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
                    target = conn.execute("SELECT * FROM players WHERE qq_id = ?", (new_qq,)).fetchone()
                    if target is None:
                        # 目标 QQ 不存在：直接改旧记录的 qq_id（更新主键）
                        conn.execute("UPDATE players SET qq_id = ? WHERE qq_id = ?", (new_qq, str(qq_id)))
                    else:
                        # 目标 QQ 已存在：合并数据（点数累加、签到取大），删除旧记录
                        old = conn.execute("SELECT * FROM players WHERE qq_id = ?", (str(qq_id),)).fetchone()
                        if old:
                            conn.execute(
                                "UPDATE players SET points = points + COALESCE(?, 0), "
                                "checkin_streak = MAX(COALESCE(checkin_streak, 0), COALESCE(?, 0)) "
                                "WHERE qq_id = ?",
                                (old["points"] or 0, old["checkin_streak"] or 0, new_qq),
                            )
                            conn.execute("DELETE FROM players WHERE qq_id = ?", (str(qq_id),))
                    qq_id = new_qq
                else:
                    # 确保玩家存在（同连接内操作）
                    row = conn.execute("SELECT qq_id FROM players WHERE qq_id = ?", (str(qq_id),)).fetchone()
                    if row is None:
                        now = int(time.time())
                        conn.execute(
                            "INSERT INTO players (qq_id, mc_id, points, checkin_streak, last_checkin_date, first_login, last_login, created_at) VALUES (?, '', 0, 0, '', NULL, NULL, ?)",
                            (str(qq_id), now),
                        )
                allowed = {"mc_id", "points", "checkin_streak", "last_checkin_date", "first_login", "last_login", "vip_level"}
                sets = {k: v for k, v in updates.items() if k in allowed}
                if not sets:
                    return
                cols = ", ".join(f"{k}=?" for k in sets)
                vals = list(sets.values()) + [str(qq_id)]
                conn.execute(f"UPDATE players SET {cols} WHERE qq_id = ?", vals)
                conn.commit()
            finally:
                conn.close()

    def checkin_player(self, qq_id: str, today: str, base_pts: int, streak_bonus: int) -> dict:
        """原子签到操作：在同一个锁/事务内完成读取→计算→写入，避免与Web编辑产生竞态。
        返回 {success, mc_id, streak, gained_pts, total_pts, already_checked}"""
        with self._lock:
            conn = self._connect()
            try:
                # 确保玩家存在
                row = conn.execute("SELECT * FROM players WHERE qq_id = ?", (str(qq_id),)).fetchone()
                if row is None:
                    conn.execute(
                        "INSERT INTO players (qq_id, mc_id, points, checkin_streak, last_checkin_date, first_login, last_login, created_at) VALUES (?, '', 0, 0, '', NULL, NULL, ?)",
                        (str(qq_id), int(time.time())),
                    )
                    conn.commit()
                    row = conn.execute("SELECT * FROM players WHERE qq_id = ?", (str(qq_id),)).fetchone()
                p = dict(row) if row else {}
                mc_id = p.get("mc_id", "")
                last = p.get("last_checkin_date", "")
                if last == today:
                    return {"success": True, "mc_id": mc_id, "already_checked": True}
                streak = p.get("checkin_streak", 0)
                if last:
                    try:
                        last_dt = time.strptime(last, "%Y-%m-%d")
                        today_dt = time.strptime(today, "%Y-%m-%d")
                        diff = (time.mktime(today_dt) - time.mktime(last_dt)) / 86400
                        if diff <= 1:
                            streak += 1
                        else:
                            streak = 1
                    except ValueError:
                        streak = 1
                else:
                    streak = 1
                pts = base_pts + (streak - 1) * streak_bonus
                # 原子更新：points 用 += 形式避免覆盖并发编辑
                conn.execute(
                    "UPDATE players SET checkin_streak = ?, last_checkin_date = ?, points = points + ? WHERE qq_id = ?",
                    (streak, today, pts, str(qq_id)),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM players WHERE qq_id = ?", (str(qq_id),)).fetchone()
                total = dict(row).get("points", 0) if row else 0
                return {"success": True, "mc_id": mc_id, "streak": streak, "gained_pts": pts, "total_pts": total}
            finally:
                conn.close()

    def bind_player(self, qq_id: str, mc_id: str, bonus_pts: int = 0) -> dict:
        """原子绑定操作：在同一锁内检查是否已绑定→写入，points 用增量避免覆盖并发编辑。
        返回 {success, mc_id, already_bound, old_mc_id, total_pts}"""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute("SELECT * FROM players WHERE qq_id = ?", (str(qq_id),)).fetchone()
                now = int(time.time())
                if row is None:
                    conn.execute(
                        "INSERT INTO players (qq_id, mc_id, points, checkin_streak, last_checkin_date, first_login, last_login, created_at) VALUES (?, ?, ?, 0, '', ?, ?, ?)",
                        (str(qq_id), mc_id, bonus_pts, now, now, now),
                    )
                    conn.commit()
                    return {"success": True, "mc_id": mc_id, "total_pts": bonus_pts}
                p = dict(row)
                if p.get("mc_id"):
                    return {"success": False, "mc_id": mc_id, "already_bound": True, "old_mc_id": p["mc_id"]}
                conn.execute(
                    "UPDATE players SET mc_id = ?, first_login = ?, last_login = ?, points = points + ? WHERE qq_id = ?",
                    (mc_id, now, now, bonus_pts, str(qq_id)),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM players WHERE qq_id = ?", (str(qq_id),)).fetchone()
                total = dict(row).get("points", 0) if row else 0
                return {"success": True, "mc_id": mc_id, "total_pts": total}
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
        targets = self._get_target_db(for_write=True)
        for db in targets:
            db._add_online_session_impl(server, player, start_ts, end_ts)

    def _add_online_session_impl(self, server: str, player: str, start_ts: int, end_ts: int):
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

    def delete_online_sessions_before(self, before_timestamp: int) -> int:
        """删除指定时间戳之前的在线会话记录，返回删除行数"""
        targets = self._get_target_db(for_write=True)
        total = 0
        for db in targets:
            total += db._delete_online_sessions_before_impl(before_timestamp)
        return total

    def _delete_online_sessions_before_impl(self, before_timestamp: int) -> int:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM online_sessions WHERE end_ts < ?",
                    (before_timestamp,),
                )
                conn.commit()
                return cur.rowcount
            finally:
                conn.close()

    def get_player_total_seconds(self, player: str, max_age_hours: int = 0) -> int:
        """获取玩家累计在线秒数。max_age_hours>0 时仅统计最近N小时内的记录"""
        with self._lock:
            conn = self._connect()
            try:
                if max_age_hours > 0:
                    cutoff = int(time.time()) - max_age_hours * 3600
                    row = conn.execute(
                        "SELECT SUM(end_ts - start_ts) as total FROM online_sessions WHERE player_name = ? AND end_ts >= ?",
                        (player, cutoff),
                    ).fetchone()
                else:
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
                    """SELECT p.qq_id, p.mc_id, p.points, p.checkin_streak, p.last_checkin_date,
                              p.first_login, p.last_login, p.created_at, p.vip_level,
                              COALESCE(SUM(s.end_ts - s.start_ts), 0) / 60 AS total_online_min
                       FROM players p
                       LEFT JOIN online_sessions s ON s.player_name = p.mc_id AND p.mc_id != ''
                       GROUP BY p.qq_id
                       ORDER BY p.created_at DESC LIMIT ?""",
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

    # ==================== 在线状态持久化 ====================

    def _get_target_db(self, for_write: bool = True):
        """获取目标数据库连接：根据存储模式返回 local / external / both"""
        if for_write:
            if self._storage_mode == "external" and self._ext_db:
                return [self._ext_db]
            elif self._storage_mode == "dual":
                dbs = [self]
                if self._ext_db:
                    dbs.append(self._ext_db)
                return dbs
        else:  # read
            if self._read_source == "external" and self._ext_db:
                return [self._ext_db]
        return [self]

    def save_online_state(self, server_name: str, player_name: str, gid: str, login_at: int):
        """保存单个在线状态"""
        targets = self._get_target_db(for_write=True)
        for db in targets:
            db._save_online_state_impl(server_name, player_name, gid, login_at)

    def _save_online_state_impl(self, server_name: str, player_name: str, gid: str, login_at: int):
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO online_state (server_name, player_name, gid, login_at) VALUES (?, ?, ?, ?)",
                    (server_name, player_name, str(gid), login_at),
                )
                conn.commit()
            finally:
                conn.close()

    def remove_online_state(self, server_name: str, player_name: str):
        """移除单个在线状态"""
        targets = self._get_target_db(for_write=True)
        for db in targets:
            db._remove_online_state_impl(server_name, player_name)

    def _remove_online_state_impl(self, server_name: str, player_name: str):
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "DELETE FROM online_state WHERE server_name=? AND player_name=?",
                    (server_name, player_name),
                )
                conn.commit()
            finally:
                conn.close()

    def load_online_state(self) -> list:
        """加载所有在线状态，返回 [{server_name, player_name, gid, login_at}]"""
        source = self
        if self._read_source == "external" and self._ext_db:
            source = self._ext_db
        return source._load_online_state_impl()

    def _load_online_state_impl(self) -> list:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT server_name, player_name, gid, login_at FROM online_state"
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def clear_online_state(self):
        """清空所有在线状态"""
        targets = self._get_target_db(for_write=True)
        for db in targets:
            db._clear_online_state_impl()

    def _clear_online_state_impl(self):
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM online_state")
                conn.commit()
            finally:
                conn.close()


class ExternalMySQLDB:
    """外部 MySQL 数据库，提供与 ExternalSQLiteDB 同构的接口"""

    def __init__(self, host: str, port: int, user: str, password: str, database: str):
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._database = database
        self._lock = threading.RLock()
        self._ensure_schema()

    def _connect(self):
        import pymysql
        conn = pymysql.connect(
            host=self._host,
            port=self._port,
            user=self._user,
            password=self._password,
            database=self._database,
            charset='utf8mb4',
            autocommit=False,
        )
        return conn

    def _ensure_schema(self):
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS online_state (
                        server_name VARCHAR(255) NOT NULL,
                        player_name VARCHAR(255) NOT NULL,
                        gid VARCHAR(64) DEFAULT '',
                        login_at BIGINT NOT NULL,
                        UNIQUE KEY uk_srv_player (server_name, player_name)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS online_sessions (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        server_name VARCHAR(255) NOT NULL,
                        player_name VARCHAR(255) NOT NULL,
                        start_ts BIGINT NOT NULL,
                        end_ts BIGINT NOT NULL,
                        INDEX idx_player_srv (player_name, server_name, start_ts)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                conn.commit()
            finally:
                conn.close()

    def _save_online_state_impl(self, server_name: str, player_name: str, gid: str, login_at: int):
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO online_state (server_name, player_name, gid, login_at) "
                    "VALUES (%s, %s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE gid=VALUES(gid), login_at=VALUES(login_at)",
                    (server_name, player_name, str(gid), login_at),
                )
                conn.commit()
            finally:
                conn.close()

    def _remove_online_state_impl(self, server_name: str, player_name: str):
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute(
                    "DELETE FROM online_state WHERE server_name=%s AND player_name=%s",
                    (server_name, player_name),
                )
                conn.commit()
            finally:
                conn.close()

    def _load_online_state_impl(self) -> list:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute("SELECT server_name, player_name, gid, login_at FROM online_state")
                rows = cur.fetchall()
                return [
                    {"server_name": r[0], "player_name": r[1], "gid": r[2], "login_at": r[3]}
                    for r in rows
                ]
            finally:
                conn.close()

    def _clear_online_state_impl(self):
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute("DELETE FROM online_state")
                conn.commit()
            finally:
                conn.close()

    def _add_online_session_impl(self, server: str, player: str, start_ts: int, end_ts: int):
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO online_sessions (server_name, player_name, start_ts, end_ts) "
                    "VALUES (%s, %s, %s, %s)",
                    (server, player, start_ts, end_ts),
                )
                conn.commit()
            finally:
                conn.close()

    def _delete_online_sessions_before_impl(self, before_timestamp: int) -> int:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute(
                    "DELETE FROM online_sessions WHERE end_ts < %s",
                    (before_timestamp,),
                )
                conn.commit()
                return cur.rowcount
            finally:
                conn.close()

    def _get_online_sessions_impl(self, limit: int = 50) -> list:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT server_name, player_name, start_ts, end_ts "
                    "FROM online_sessions ORDER BY start_ts DESC LIMIT %s",
                    (limit,),
                )
                rows = cur.fetchall()
                return [
                    {"server_name": r[0], "player_name": r[1], "start_ts": r[2], "end_ts": r[3]}
                    for r in rows
                ]
            finally:
                conn.close()

    def _get_player_sessions_impl(self, player_name: str, limit: int = 50) -> list:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT server_name, player_name, start_ts, end_ts "
                    "FROM online_sessions WHERE player_name=%s "
                    "ORDER BY start_ts DESC LIMIT %s",
                    (player_name, limit),
                )
                rows = cur.fetchall()
                return [
                    {"server_name": r[0], "player_name": r[1], "start_ts": r[2], "end_ts": r[3]}
                    for r in rows
                ]
            finally:
                conn.close()

    def get_online_sessions(self, limit: int = 50) -> list:
        """获取最近的在线会话记录"""
        source = self
        if self._read_source == "external" and self._ext_db:
            source = self._ext_db
        return source._get_online_sessions_impl(limit)

    def _get_online_sessions_impl(self, limit: int = 50) -> list:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT server_name, player_name, start_ts, end_ts FROM online_sessions ORDER BY start_ts DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_player_sessions(self, player_name: str, limit: int = 50) -> list:
        """获取单个玩家的在线会话记录"""
        source = self
        if self._read_source == "external" and self._ext_db:
            source = self._ext_db
        return source._get_player_sessions_impl(player_name, limit)

    def _get_player_sessions_impl(self, player_name: str, limit: int = 50) -> list:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT server_name, player_name, start_ts, end_ts FROM online_sessions WHERE player_name=? ORDER BY start_ts DESC LIMIT ?",
                    (player_name, limit),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    # ==================== 积分兑换 ====================

    def get_exchange_items(self, group_id: str = "") -> list:
        """获取指定群的兑换项列表"""
        with self._lock:
            conn = self._connect()
            try:
                if group_id:
                    rows = conn.execute(
                        "SELECT * FROM exchange_items WHERE group_id=? ORDER BY id",
                        (str(group_id),),
                    ).fetchall()
                else:
                    rows = conn.execute("SELECT * FROM exchange_items ORDER BY group_id, id").fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_exchange_item(self, item_id: int) -> dict:
        """获取单个兑换项"""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute("SELECT * FROM exchange_items WHERE id=?", (item_id,)).fetchone()
                return dict(row) if row else {}
            finally:
                conn.close()

    def add_exchange_item(self, group_id: str, name: str, description: str,
                          rcon_cmd: str, cost_points: int) -> int:
        """添加兑换项，返回id"""
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "INSERT INTO exchange_items (group_id, name, description, rcon_cmd, cost_points) VALUES (?, ?, ?, ?, ?)",
                    (str(group_id), name, description, rcon_cmd, cost_points),
                )
                conn.commit()
                return cur.lastrowid
            finally:
                conn.close()

    def update_exchange_item(self, item_id: int, updates: dict):
        """更新兑换项"""
        with self._lock:
            conn = self._connect()
            try:
                allowed = {"name", "description", "rcon_cmd", "cost_points", "enabled"}
                sets = {k: v for k, v in updates.items() if k in allowed}
                if not sets:
                    return
                cols = ", ".join(f"{k}=?" for k in sets)
                vals = list(sets.values()) + [item_id]
                conn.execute(f"UPDATE exchange_items SET {cols} WHERE id=?", vals)
                conn.commit()
            finally:
                conn.close()

    def delete_exchange_item(self, item_id: int):
        """删除兑换项"""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM exchange_items WHERE id=?", (item_id,))
                conn.commit()
            finally:
                conn.close()

    def redeem_exchange(self, qq_id: str, mc_id: str, item_id: int) -> dict:
        """原子兑换操作：检查积分→扣除→返回指令。
        返回 {success, rcon_cmd, item_name, cost, total_pts, error_msg}"""
        with self._lock:
            conn = self._connect()
            try:
                item = conn.execute(
                    "SELECT * FROM exchange_items WHERE id=?",
                    (item_id,),
                ).fetchone()
                if not item:
                    return {"success": False, "error_msg": "兑换项不存在"}
                item = dict(item)
                if not item.get("enabled"):
                    return {"success": False, "error_msg": "该兑换项已关闭"}
                cost = item["cost_points"]
                player = conn.execute(
                    "SELECT * FROM players WHERE qq_id=?",
                    (str(qq_id),),
                ).fetchone()
                if not player:
                    return {"success": False, "error_msg": "玩家记录不存在"}
                player = dict(player)
                if not player.get("mc_id"):
                    return {"success": False, "error_msg": "请先绑定MC账号"}
                if player["points"] < cost:
                    return {"success": False, "error_msg": f"积分不足，需要 {cost} 积分，当前 {player['points']} 积分"}
                conn.execute(
                    "UPDATE players SET points = points - ? WHERE qq_id = ?",
                    (cost, str(qq_id)),
                )
                conn.commit()
                row = conn.execute("SELECT points FROM players WHERE qq_id=?", (str(qq_id),)).fetchone()
                return {
                    "success": True,
                    "rcon_cmd": item["rcon_cmd"].replace("{player}", mc_id),
                    "item_name": item["name"],
                    "cost": cost,
                    "total_pts": row["points"] if row else 0,
                }
            finally:
                conn.close()

    # ==================== 抽奖 ====================

    def get_lottery_prizes(self, group_id: str = "") -> list:
        """获取抽奖奖品列表（仅启用的）"""
        with self._lock:
            conn = self._connect()
            try:
                if group_id:
                    rows = conn.execute(
                        "SELECT * FROM lottery_prizes WHERE group_id=? AND enabled=1 ORDER BY id",
                        (str(group_id),),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM lottery_prizes WHERE enabled=1 ORDER BY group_id, id"
                    ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_all_lottery_prizes(self, group_id: str = "") -> list:
        """获取抽奖奖品列表（包括禁用的，管理用）"""
        with self._lock:
            conn = self._connect()
            try:
                if group_id:
                    rows = conn.execute(
                        "SELECT * FROM lottery_prizes WHERE group_id=? ORDER BY id",
                        (str(group_id),),
                    ).fetchall()
                else:
                    rows = conn.execute("SELECT * FROM lottery_prizes ORDER BY group_id, id").fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def add_lottery_prize(self, group_id: str, name: str, description: str,
                          probability: float, count: int, rcon_cmd: str,
                          cost_points: int) -> int:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "INSERT INTO lottery_prizes (group_id, name, description, probability, count, rcon_cmd, cost_points) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (str(group_id), name, description, probability, count, rcon_cmd, cost_points),
                )
                conn.commit()
                return cur.lastrowid
            finally:
                conn.close()

    def update_lottery_prize(self, prize_id: int, updates: dict):
        with self._lock:
            conn = self._connect()
            try:
                allowed = {"name", "description", "probability", "count", "rcon_cmd", "cost_points", "enabled"}
                sets = {k: v for k, v in updates.items() if k in allowed}
                if not sets:
                    return
                cols = ", ".join(f"{k}=?" for k in sets)
                vals = list(sets.values()) + [prize_id]
                conn.execute(f"UPDATE lottery_prizes SET {cols} WHERE id=?", vals)
                conn.commit()
            finally:
                conn.close()

    def delete_lottery_prize(self, prize_id: int):
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM lottery_prizes WHERE id=?", (prize_id,))
                conn.commit()
            finally:
                conn.close()

    def draw_lottery(self, qq_id: str, mc_id: str, group_id: str,
                     cost_per_draw: int = 10) -> dict:
        """原子抽奖：扣积分 + 随机抽奖品 + 记录中奖。
        返回 {success, results:[{prize_name, prize_cmd, win_id}], total_pts, error_msg}"""
        import random as _random
        with self._lock:
            conn = self._connect()
            try:
                player = conn.execute(
                    "SELECT * FROM players WHERE qq_id=?", (str(qq_id),)
                ).fetchone()
                if not player:
                    return {"success": False, "error_msg": "玩家记录不存在"}
                player = dict(player)
                if not player.get("mc_id"):
                    return {"success": False, "error_msg": "请先绑定MC账号"}
                prizes = conn.execute(
                    "SELECT * FROM lottery_prizes WHERE group_id=? AND enabled=1",
                    (str(group_id),),
                ).fetchall()
                if not prizes:
                    return {"success": False, "error_msg": "该群暂未配置奖品"}
                # 计算消耗（取所有奖品中最低的）
                costs = [p["cost_points"] for p in prizes if p["cost_points"] > 0]
                actual_cost = cost_per_draw if cost_per_draw > 0 else (min(costs) if costs else 10)
                if player["points"] < actual_cost:
                    return {"success": False, "error_msg": f"积分不足，需要 {actual_cost} 积分，当前 {player['points']} 积分"}
                conn.execute(
                    "UPDATE players SET points = points - ? WHERE qq_id = ?",
                    (actual_cost, str(qq_id)),
                )
                # 抽取奖品
                now = int(time.time())
                results = []
                for prize in prizes:
                    prize = dict(prize)
                    if _random.random() <= prize["probability"]:
                        for _ in range(prize["count"]):
                            cur = conn.execute(
                                "INSERT INTO lottery_wins (qq_id, mc_id, group_id, prize_name, prize_cmd, win_time) VALUES (?, ?, ?, ?, ?, ?)",
                                (str(qq_id), mc_id, str(group_id), prize["name"],
                                 prize["rcon_cmd"].replace("{player}", mc_id), now),
                            )
                            results.append({
                                "prize_name": prize["name"],
                                "prize_cmd": prize["rcon_cmd"].replace("{player}", mc_id),
                                "win_id": cur.lastrowid,
                            })
                conn.commit()
                row = conn.execute("SELECT points FROM players WHERE qq_id=?", (str(qq_id),)).fetchone()
                return {
                    "success": True,
                    "results": results,
                    "total_pts": row["points"] if row else 0,
                    "cost": actual_cost,
                }
            finally:
                conn.close()

    def get_lottery_wins(self, qq_id: str = "", group_id: str = "", redeemed: int = None) -> list:
        """获取中奖记录"""
        with self._lock:
            conn = self._connect()
            try:
                conditions = []
                params = []
                if qq_id:
                    conditions.append("qq_id=?")
                    params.append(str(qq_id))
                if group_id:
                    conditions.append("group_id=?")
                    params.append(str(group_id))
                if redeemed is not None:
                    conditions.append("redeemed=?")
                    params.append(redeemed)
                query = "SELECT * FROM lottery_wins"
                if conditions:
                    query += " WHERE " + " AND ".join(conditions)
                query += " ORDER BY win_time DESC LIMIT 200"
                rows = conn.execute(query, params).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def redeem_lottery_win(self, win_id: int) -> dict:
        """兑奖：标记为已兑"""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM lottery_wins WHERE id=?", (win_id,)
                ).fetchone()
                if not row:
                    return {"success": False, "error_msg": "中奖记录不存在"}
                row = dict(row)
                if row["redeemed"]:
                    return {"success": False, "error_msg": "已兑过奖"}
                conn.execute(
                    "UPDATE lottery_wins SET redeemed=1 WHERE id=?", (win_id,)
                )
                conn.commit()
                return {"success": True, "prize_cmd": row["prize_cmd"], "prize_name": row["prize_name"]}
            finally:
                conn.close()


class ExternalSQLiteDB:
    """外部 SQLite 数据库，与本地同构"""
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.RLock()
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self._ensure_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self):
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS online_state (
                        server_name TEXT NOT NULL,
                        player_name TEXT NOT NULL,
                        gid TEXT DEFAULT '',
                        login_at INTEGER NOT NULL,
                        UNIQUE(server_name, player_name)
                    );
                    CREATE TABLE IF NOT EXISTS online_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        server_name TEXT NOT NULL,
                        player_name TEXT NOT NULL,
                        start_ts INTEGER NOT NULL,
                        end_ts INTEGER NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_ext_sessions_player ON online_sessions(player_name, server_name, start_ts);
                """)
                conn.commit()
            finally:
                conn.close()

    def _save_online_state_impl(self, server_name: str, player_name: str, gid: str, login_at: int):
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO online_state (server_name, player_name, gid, login_at) VALUES (?, ?, ?, ?)",
                    (server_name, player_name, str(gid), login_at),
                )
                conn.commit()
            finally:
                conn.close()

    def _remove_online_state_impl(self, server_name: str, player_name: str):
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "DELETE FROM online_state WHERE server_name=? AND player_name=?",
                    (server_name, player_name),
                )
                conn.commit()
            finally:
                conn.close()

    def _load_online_state_impl(self) -> list:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT server_name, player_name, gid, login_at FROM online_state"
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def _clear_online_state_impl(self):
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM online_state")
                conn.commit()
            finally:
                conn.close()

    def _add_online_session_impl(self, server: str, player: str, start_ts: int, end_ts: int):
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

    def _delete_online_sessions_before_impl(self, before_timestamp: int) -> int:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM online_sessions WHERE end_ts < ?",
                    (before_timestamp,),
                )
                conn.commit()
                return cur.rowcount
            finally:
                conn.close()

    def _get_online_sessions_impl(self, limit: int = 50) -> list:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT server_name, player_name, start_ts, end_ts FROM online_sessions ORDER BY start_ts DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def _get_player_sessions_impl(self, player_name: str, limit: int = 50) -> list:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT server_name, player_name, start_ts, end_ts FROM online_sessions WHERE player_name=? ORDER BY start_ts DESC LIMIT ?",
                    (player_name, limit),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()
