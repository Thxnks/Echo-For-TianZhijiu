"""SQLite 数据层。所有聊天记录、状态都存在本地 companion.db 文件里。

表：
- messages：聊天历史（用户/AI/主动消息都进这里）
- meta：键值表，存"上次主动找你的时间""当前心情"等状态
- memories：长期记忆事实 + embedding 向量
- sessions：对话分组
- session_summaries：滚动对话摘要
"""
import json
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
        c.execute("""
            CREATE TABLE IF NOT EXISTS session_summaries (
                session_id INTEGER PRIMARY KEY,
                summary TEXT NOT NULL DEFAULT '',
                updated_until_message_id INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL
            )
        """)
        # 迁移：老库的 messages 没有 session_id 列，补上
        cols = [r[1] for r in c.execute("PRAGMA table_info(messages)").fetchall()]
        if "session_id" not in cols:
            c.execute("ALTER TABLE messages ADD COLUMN session_id INTEGER")

        # 迁移：memories 增加 embedding / source / importance / last_used_at
        mem_cols = [r[1] for r in c.execute("PRAGMA table_info(memories)").fetchall()]
        if "embedding" not in mem_cols:
            c.execute("ALTER TABLE memories ADD COLUMN embedding TEXT")
        if "source" not in mem_cols:
            c.execute("ALTER TABLE memories ADD COLUMN source TEXT DEFAULT 'distill'")
        if "importance" not in mem_cols:
            c.execute("ALTER TABLE memories ADD COLUMN importance INTEGER DEFAULT 1")
        if "last_used_at" not in mem_cols:
            c.execute("ALTER TABLE memories ADD COLUMN last_used_at TEXT")

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


def add_memory(fact: str, embedding: list[float] | None = None,
                source: str = "distill", importance: int = 1):
    """存一条长期记忆事实；fact 唯一，重复的自动忽略。
    embedding 用 JSON 字符串保存，可为 None（先存事实，后补向量）。
    """
    embedding_json = json.dumps(embedding) if embedding else None
    with _conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO memories (fact, embedding, source, importance, created_at) "
            "VALUES (?,?,?,?,?)",
            (fact, embedding_json, source, importance, _now()),
        )


def all_memories(limit: int = 200):
    """取最近 limit 条记忆的事实文本列表（向后兼容旧接口）。"""
    with _conn() as c:
        rows = c.execute(
            "SELECT fact FROM memories ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return list(reversed([r["fact"] for r in rows]))


def all_memory_rows(limit: int = 200) -> list[dict]:
    """取最近 limit 条记忆的完整行（含 embedding / source / importance / last_used_at）。"""
    with _conn() as c:
        rows = c.execute(
            "SELECT id, fact, embedding, source, importance, last_used_at, created_at "
            "FROM memories ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    result = []
    for r in reversed(rows):
        d = dict(r)
        # 把 JSON 字符串还原为 list，方便调用方直接用
        if d.get("embedding"):
            try:
                d["embedding"] = json.loads(d["embedding"])
            except (json.JSONDecodeError, TypeError):
                d["embedding"] = None
        else:
            d["embedding"] = None
        result.append(d)
    return result


def update_memory_embedding(fact: str, embedding: list[float]):
    """为已有 memory 补写 embedding 向量。"""
    embedding_json = json.dumps(embedding) if embedding else None
    with _conn() as c:
        c.execute(
            "UPDATE memories SET embedding=? WHERE fact=?",
            (embedding_json, fact),
        )


def touch_memory(fact: str):
    """更新 last_used_at，标记这条记忆被检索命中过。"""
    with _conn() as c:
        c.execute(
            "UPDATE memories SET last_used_at=? WHERE fact=?",
            (_now(), fact),
        )


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


# ---- 滚动对话摘要 ----

def get_session_summary(session_id: int | None = None) -> dict | None:
    """获取当前或指定 session 的摘要。"""
    if session_id is None:
        session_id = current_session_id()
    with _conn() as c:
        row = c.execute(
            "SELECT session_id, summary, updated_until_message_id, updated_at "
            "FROM session_summaries WHERE session_id=?", (session_id,)
        ).fetchone()
    return dict(row) if row else None


def upsert_session_summary(session_id: int, summary: str, updated_until_message_id: int):
    """写入或更新 session 摘要。"""
    with _conn() as c:
        c.execute(
            "INSERT INTO session_summaries (session_id, summary, updated_until_message_id, updated_at) "
            "VALUES (?,?,?,?) "
            "ON CONFLICT(session_id) DO UPDATE SET "
            "summary=excluded.summary, updated_until_message_id=excluded.updated_until_message_id, "
            "updated_at=excluded.updated_at",
            (session_id, summary, updated_until_message_id, _now()),
        )


def message_count_in_session(session_id: int | None = None) -> int:
    """当前 session 的消息总数。"""
    if session_id is None:
        session_id = current_session_id()
    with _conn() as c:
        row = c.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE session_id=?", (session_id,)
        ).fetchone()
    return row["n"] if row else 0
