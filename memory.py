"""长期记忆：每积累几轮对话，自动把"关于用户值得记住的事"提炼成事实存起来。

帖子第1点：记忆是一个可检索系统，不是一段固定人设。
这里是简版——提炼成事实存进 memories 表，build_context 时全量带上（量大了再上向量检索）。
"""
import db
import llm
import config

_DISTILL_SYSTEM = (
    "你是一个记忆提炼器。从下面的对话中，提取关于【用户】值得长期记住的事实"
    "（个人信息、喜好、经历、计划、在意的事、对AI的称呼习惯、情绪倾向等）。\n"
    "规则：\n"
    "- 只输出【已知事实列表里没有的、新的】事实\n"
    "- 每条一行，简洁的陈述句，不要编号、不要解释、不要客套\n"
    "- 只记关于用户的稳定事实，不记一次性的闲聊\n"
    "- 如果没有值得记的新事实，只输出两个字：无"
)


def maybe_distill():
    """检查是否积累了足够新消息，够了就提炼一次。供后台调用，不阻塞聊天。"""
    last_id = int(db.get_meta("last_distill_id") or 0)
    new_msgs = db.messages_after(last_id)
    if len(new_msgs) < config.DISTILL_EVERY_MESSAGES:
        return

    transcript = "\n".join(
        f"{'用户' if m['role'] == 'user' else 'Claude'}: {m['content']}" for m in new_msgs
    )
    existing = db.all_memories(200)
    existing_block = "\n".join(f"- {f}" for f in existing) or "（暂无）"

    out = llm.chat([
        {"role": "system", "content": _DISTILL_SYSTEM},
        {"role": "user", "content": f"【已知事实】\n{existing_block}\n\n【最近对话】\n{transcript}\n\n请输出新事实："},
    ]).strip()

    if out and out != "无":
        for line in out.splitlines():
            fact = line.strip().lstrip("-•*0123456789. ").strip()
            if fact and fact != "无":
                db.add_memory(fact)

    # 把"已提炼到哪"的指针推进到最新一条
    db.set_meta("last_distill_id", str(max(m["id"] for m in new_msgs)))
    print(f"[memory] 已提炼记忆，当前共 {len(db.all_memories(9999))} 条")
