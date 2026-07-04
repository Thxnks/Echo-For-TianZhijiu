"""build_context()：每一轮发给 LLM 的内容是动态拼装的（帖子第2点）。

这是整个系统的核心。聊天和"主动找你"都用它，只是 trigger 不同。
"""
from datetime import datetime, timezone
import config
import db


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


# ---- 相关性记忆检索 ----
# 思路：用字符 bigram（相邻两字）的重叠度来判断"这条记忆和当前话题有多相关"。
# 中文没有空格分词，bigram 是不依赖任何第三方库的最简方案。
# 等上数据库（pgvector 之类）后可以换成向量检索，但接口不变。

def _relevant_memories(query: str, top_n: int = 10) -> list[str]:
    """从全部记忆里挑出和 query 最相关的 top_n 条。

    - query 可以是用户输入，也可以是主动模式下的 proactive_hint
    - 相关性用字符 bigram 重叠数打分
    - 兜底：如果一条都没匹配到，返回最新的几条记忆
    """
    all_mem = db.all_memories(200)          # 从数据库拉全部记忆（目前量小，够用）
    if not all_mem:
        return []

    query = query.strip()
    # 太短的查询（如"嗯""好"）→ 直接返回最新记忆
    if len(query) < 2:
        return all_mem[-top_n:]

    # 生成查询的 bigram 集合
    q_bigrams = {query[i:i + 2] for i in range(len(query) - 1)}
    if not q_bigrams:
        return all_mem[-top_n:]

    # 给每条记忆打分
    scored = []
    for mem in all_mem:
        m_bigrams = {mem[i:i + 2] for i in range(len(mem) - 1)}
        score = len(q_bigrams & m_bigrams)
        scored.append((score, mem))

    # 按分数降序排列
    scored.sort(key=lambda x: x[0], reverse=True)

    # 先取有重叠的（真正相关的）
    relevant = [m for s, m in scored if s > 0][:top_n]

    # 兜底：相关的不够 top_n 条，用最新的记忆补足
    if len(relevant) < min(top_n, 5):
        for m in reversed(all_mem):          # 最新在尾部
            if m not in relevant:
                relevant.append(m)
            if len(relevant) >= min(top_n, 5):
                break

    return relevant


def build_context(user_input: str | None = None, proactive_hint: str | None = None) -> list[dict]:
    """组装"当前现场包"。
    - user_input 有值：普通聊天
    - proactive_hint 有值：主动找用户（没有用户新输入）
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M %A")
    idle = _human_idle(db.last_user_message_time())

    # 1. 基础身份 + 当前时间 + 距上次对话多久 + 相关性记忆（system 层）
    system = (
        f"{config.PERSONA}\n\n"
        f"【当前时间】{now}\n"
        f"【对话间隔】{idle}\n"
    )

    # 1.5 长期记忆：只带和当前话题【相关】的（相关性检索替代全量 dump）
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
