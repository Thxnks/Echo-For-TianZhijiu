"""SQLite 数据层。所有聊天记录、状态都存在本地 companion.db 文件里。

帖子第5点：数据库是"关系连续性的底座"。这里先做最小版：
- messages：聊天历史（用户/AI/主动消息都进这里）
- meta：键值表，存"上次主动找你的时间""当前心情"等状态
等加长期记忆时，再加 memories 表 + 向量检索。
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "companion.db"


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                role      TEXT NOT NULL,          -- user / assistant
                content   TEXT NOT NULL,
                source    TEXT NOT NULL DEFAULT 'chat',  -- chat / proactive
                created_at TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                fact  TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        # 迁移：老库的 messages 没有 session_id 列，补上
        cols = [r[1] for r in c.execute("PRAGMA table_info(messages)").fetchall()]
        if "session_id" not in cols:
            c.execute("ALTER TABLE messages ADD COLUMN session_id INTEGER")
    _ensure_default_session()


def _ensure_default_session():
    """保证至少有一个 session，并把没归属的旧消息收进第一个 session。"""
    with _conn() as c:
        n = c.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
        if n == 0:
            c.execute("INSERT INTO sessions (title, created_at) VALUES (?,?)",
                      ("默认对话", _now()))
        first_id = c.execute("SELECT id FROM sessions ORDER BY id ASC LIMIT 1").fetchone()["id"]
        c.execute("UPDATE messages SET session_id=? WHERE session_id IS NULL", (first_id,))
    if not get_meta("current_session_id"):
        set_meta("current_session_id", str(first_id))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_session_id() -> int:
    return int(get_meta("current_session_id") or 0)


def create_session(title: str | None = None) -> int:
    """新建一个 session 并切换为当前。"""
    if not title:
        title = "对话 " + datetime.now().strftime("%m-%d %H:%M")
    with _conn() as c:
        cur = c.execute("INSERT INTO sessions (title, created_at) VALUES (?,?)",
                        (title, _now()))
        sid = cur.lastrowid
    set_meta("current_session_id", str(sid))
    return sid


def switch_session(sid: int):
    set_meta("current_session_id", str(sid))


def list_sessions():
    with _conn() as c:
        rows = c.execute(
            "SELECT id, title, created_at FROM sessions ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def add_message(role: str, content: str, source: str = "chat", session_id: int | None = None) -> int:
    if session_id is None:
        session_id = current_session_id()
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO messages (role, content, source, created_at, session_id) VALUES (?,?,?,?,?)",
            (role, content, source, _now(), session_id),
        )
        return cur.lastrowid


def recent_messages(limit: int):
    """当前 session 的最近 limit 条消息。"""
    sid = current_session_id()
    with _conn() as c:
        rows = c.execute(
            "SELECT id, role, content, created_at FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
            (sid, limit),
        ).fetchall()
    return list(reversed([dict(r) for r in rows]))


def messages_after(after_id: int):
    """当前 session 里 id 大于 after_id 的消息——前端轮询用，拉到 agent 主动发的新消息。"""
    sid = current_session_id()
    with _conn() as c:
        rows = c.execute(
            "SELECT id, role, content FROM messages WHERE id > ? AND session_id=? ORDER BY id",
            (after_id, sid),
        ).fetchall()
    return [dict(r) for r in rows]


def last_user_message_time():
    with _conn() as c:
        row = c.execute(
            "SELECT created_at FROM messages WHERE role='user' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return datetime.fromisoformat(row["created_at"]) if row else None


def add_memory(fact: str):
    """存一条长期记忆事实；fact 唯一，重复的自动忽略。"""
    with _conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO memories (fact, created_at) VALUES (?,?)",
            (fact, _now()),
        )


def all_memories(limit: int = 200):
    """取最近 limit 条记忆，按时间正序返回（老的在前）。"""
    with _conn() as c:
        rows = c.execute(
            "SELECT fact FROM memories ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return list(reversed([r["fact"] for r in rows]))


def get_meta(key: str, default=None):
    with _conn() as c:
        row = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(key: str, value: str):
    with _conn() as c:
        c.execute(
            "INSERT INTO meta (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
