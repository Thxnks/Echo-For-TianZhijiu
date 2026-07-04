"""build_context()：每一轮发给 LLM 的内容是动态拼装的。

这是整个系统的核心。聊天和"主动找你"都用它，只是 trigger 不同。
记忆检索：语义向量 > bigram > 兜底。
"""
import math
from datetime import datetime, timezone
import config
import db
import embedder


def _human_idle(last_user_time) -> str:
    if not last_user_time:
        return "你们还没聊过天。"
    delta = datetime.now(timezone.utc) - last_user_time
    h = delta.total_seconds() / 3600
    if h < 1:
        return "你们刚刚还在聊。"
    if h < 24:
        return f"距离用户上次说话已经过去约 {int(h)} 小时。"
    return f"距离用户上次说话已经过去约 {int(h / 24)} 天。"


# ---- 相似度 ----

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """两个向量的余弦相似度。归一化向量等价于 dot product。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    # 归一化向量下直接返回 dot
    return max(0.0, dot)


# ---- 相关性记忆检索 ----
# 优先用语义向量（embedding），没有 embedding 或向量检索失败时 fallback 到 bigram。
# bigram 是不依赖任何第三方库的最简方案，中文友好。

def _bigram_memories(query: str, candidates: list[dict], top_n: int) -> list[dict]:
    """bigram fallback：用字符 bigram 重叠度打分，从 candidates 中挑出 top_n 条。"""
    q_bigrams = {query[i:i + 2] for i in range(len(query) - 1)}
    if not q_bigrams:
        return []
    scored = []
    for m in candidates:
        fact = m["fact"]
        m_bigrams = {fact[i:i + 2] for i in range(len(fact) - 1)}
        score = len(q_bigrams & m_bigrams)
        scored.append((score, m))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for s, m in scored if s > 0][:top_n]


def _relevant_memories(query: str, top_n: int = 8) -> list[str]:
    """从全部记忆里挑出和 query 最相关的 top_n 条。

    策略：语义向量检索 → bigram fallback → 最近记忆兜底。
    - query 太短：直接返回最近记忆（不浪费 embedding 计算）
    - 有 embedding 的记忆用 cosine 相似度排序
    - 没有 embedding 或全部没命中时 fallback 到 bigram
    """
    query = query.strip()
    # 太短的查询（如"嗯""好"）→ 直接返回最近记忆
    if len(query) < 2:
        recent = db.all_memories(top_n)
        return recent[-top_n:] if recent else []

    all_rows = db.all_memory_rows(200)
    if not all_rows:
        return []

    # 1. 尝试语义向量检索
    q_vec = embedder.embed(query)
    if q_vec:
        scored = []
        for row in all_rows:
            if row.get("embedding"):
                score = _cosine_similarity(q_vec, row["embedding"])
                if score >= config.MEMORY_VECTOR_MIN_SCORE:
                    scored.append((score, row["fact"]))
        if scored:
            scored.sort(key=lambda x: x[0], reverse=True)
            result = [fact for _, fact in scored[:top_n]]
            # 标记命中记忆（用于后续分析热度）
            for fact in result:
                try:
                    db.touch_memory(fact)
                except Exception:
                    pass
            return result

    # 2. Fallback: bigram
    bigram_result = _bigram_memories(query, all_rows, top_n)
    if bigram_result:
        return [m["fact"] for m in bigram_result]

    # 3. 兜底：返回最新记忆
    recent = db.all_memories(top_n)
    return recent[-top_n:] if recent else []


def build_context(user_input: str | None = None, proactive_hint: str | None = None) -> list[dict]:
    """组装"当前现场包"。
    - user_input 有值：普通聊天
    - proactive_hint 有值：主动找用户（没有用户新输入）
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M %A")
    idle = _human_idle(db.last_user_message_time())

    # 1. 基础身份 + 当前时间 + 距上次对话多久（system 层）
    system = (
        f"{config.PERSONA}\n\n"
        f"【当前时间】{now}\n"
        f"【对话间隔】{idle}\n"
    )

    # 1.5 滚动对话摘要（如果有）
    summary_row = db.get_session_summary()
    if summary_row and summary_row.get("summary"):
        system += (
            "\n【最近对话摘要 — 本段对话到目前为止发生的重要事件和用户提到的关键信息】\n"
            f"{summary_row['summary']}\n"
        )

    # 1.6 长期记忆：语义向量检索，只带和当前话题【相关】的
    query = (user_input or proactive_hint or "").strip()
    if query:
        relevant = _relevant_memories(query)
        if relevant:
            system += "\n【关于用户（你记得的事 — 只列出和当前话题相关的）】\n"
            system += "\n".join(f"- {m}" for m in relevant) + "\n"

    messages = [{"role": "system", "content": system}]

    # 2. 最近对话（history 层）
    for m in db.recent_messages(config.RECENT_MESSAGES_LIMIT):
        messages.append({"role": m["role"], "content": m["content"]})

    # 3a. 普通聊天：带上用户这一轮新输入
    if user_input is not None:
        messages.append({"role": "user", "content": user_input})

    # 3b. 主动模式：没有用户输入，给一条 system 指令让它自己开口
    if proactive_hint is not None:
        messages.append({
            "role": "system",
            "content": (
                f"现在没有用户的新消息。{proactive_hint} "
                "请你像真人一样，主动给 TA 发一条简短、自然的微信消息。"
                "直接输出消息内容，不要解释、不要加引号。"
            ),
        })

    return messages
