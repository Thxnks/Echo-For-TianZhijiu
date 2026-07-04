"""滚动对话摘要：当前 session 消息积累到一定量后，调用 LLM 生成摘要。

摘要只写稳定上下文、重要事件、未完成事项、用户偏好，不写无意义寒暄。
这个功能必须容错：摘要失败不影响聊天。
"""
import db
import llm
import config

# 每积累多少条新消息就更新一次摘要
SUMMARY_EVERY_MESSAGES = 30

_SUMMARY_SYSTEM = (
    "你是一个对话摘要器。从下面用户和 AI 的对话片段中，提取值得长期记录的摘要。\n"
    "规则：\n"
    "- 只记录稳定上下文、重要事件、未完成事项、用户偏好、情绪倾向\n"
    "- 不写无意义的寒暄、天气、日常问候\n"
    "- 用简短中文，2~5 句话即可\n"
    "- 如果有之前的摘要，新的摘要要融合旧信息（去重、更新过时信息）\n"
    "- 如果这段对话没有什么值得记录的，输出：无"
)


def maybe_summarize():
    """检查当前 session 是否需要更新摘要，需要就调用 LLM 更新。容错：失败不影响聊天。"""
    session_id = db.current_session_id()
    if not session_id:
        return

    total = db.message_count_in_session(session_id)
    prev = db.get_session_summary(session_id)
    prev_until = prev["updated_until_message_id"] if prev else 0

    # 上次摘要之后的新消息数不够，不更新
    new_since_last = total - prev_until
    if new_since_last < SUMMARY_EVERY_MESSAGES:
        return

    # 拉取上次摘要之后的消息
    messages = db.messages_after(prev_until)
    if not messages:
        return

    transcript = "\n".join(
        f"{'用户' if m['role'] == 'user' else 'AI'}: {m['content']}" for m in messages
    )
    old_summary = prev["summary"] if prev else "（暂无）"

    try:
        out = llm.chat([
            {"role": "system", "content": _SUMMARY_SYSTEM},
            {"role": "user", "content": (
                f"【之前的摘要】\n{old_summary}\n\n"
                f"【新增对话片段】\n{transcript}\n\n"
                "请输出融合后的新摘要（2~5 句中文）："
            )},
        ]).strip()
    except Exception as e:
        print(f"[summary] LLM 摘要生成失败：{e}")
        return

    if not out or out == "无":
        return

    # 写入摘要，更新到最新消息 id
    last_id = max(m["id"] for m in messages)
    try:
        db.upsert_session_summary(session_id, out, last_id)
        print(f"[summary] 摘要已更新（session={session_id}，覆盖至消息 #{last_id}）")
    except Exception as e:
        print(f"[summary] 摘要写入失败：{e}")
