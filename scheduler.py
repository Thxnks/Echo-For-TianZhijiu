"""主动消息调度。APScheduler 定时醒来，决定要不要主动找用户。

帖子提到的"行动回流"：agent 主动发的消息也会写回 messages，
这样你回它的时候，它知道刚才是自己先开的口。
"""
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler

import config
import db
import context
import llm
import push


def _seconds_since(iso_str: str | None) -> float:
    if not iso_str:
        return 1e9
    t = datetime.fromisoformat(iso_str)
    return (datetime.now(timezone.utc) - t).total_seconds()


def _hours_since(iso_str: str | None) -> float:
    return _seconds_since(iso_str) / 3600


def _minutes_since(iso_str: str | None) -> float:
    return _seconds_since(iso_str) / 60


def _in_active_hours() -> bool:
    """是否在活跃时段（支持跨午夜，如 9点~次日3点）。"""
    hour = datetime.now().hour
    s, e = config.ACTIVE_START_HOUR, config.ACTIVE_END_HOUR
    return (s <= hour < e) if s < e else (hour >= s or hour < e)


def _is_online_in_chat() -> bool:
    """用户此刻是否开着聊天页（前端心跳还新鲜）。"""
    return _seconds_since(db.get_meta("last_seen_online")) <= config.ONLINE_PRESENCE_WINDOW_SECONDS


def maybe_nudge_when_phone_active():
    """你在玩手机（快捷指令上报）但没来聊天 → Bark 推一条戳你。"""
    if not _in_active_hours():
        return
    # 已经开着聊天页了，交给"在线主动开口"，不用 Bark
    if _is_online_in_chat():
        return
    # 不在玩手机（最近没有快捷指令上报）
    if _minutes_since(db.get_meta("last_phone_active")) > config.PHONE_ACTIVE_WINDOW_MINUTES:
        return
    # 最近才聊过，不打扰
    last_user = db.last_user_message_time()
    if _minutes_since(last_user.isoformat() if last_user else None) < config.PHONE_IGNORE_IDLE_MINUTES:
        return
    # Bark 冷却（与离线推送共用一个时间戳，避免双重打扰）
    if _minutes_since(db.get_meta("last_proactive_at")) < config.PHONE_NUDGE_COOLDOWN_MINUTES:
        return

    hint = "用户正在玩手机（在用别的 App），但一直没来找你聊天。"
    text = llm.chat(context.build_context(proactive_hint=hint))
    db.add_message("assistant", text, source="proactive")
    db.set_meta("last_proactive_at", datetime.now(timezone.utc).isoformat())
    push.push_to_phone(text)
    print("[phone-nudge] 在玩手机却没理它，已 Bark 推送：", text)


def maybe_send_online_nudge():
    """用户在线（前端有心跳）但有一小会儿没说话 → 在聊天框里主动开口。不走 Bark。"""
    # 不在线就交给 Bark 那个 job
    if _seconds_since(db.get_meta("last_seen_online")) > config.ONLINE_PRESENCE_WINDOW_SECONDS:
        return
    # 刚说过话，不打扰
    last_user = db.last_user_message_time()
    if _seconds_since(last_user.isoformat() if last_user else None) < config.ONLINE_IDLE_SECONDS:
        return
    # 冷却中，防刷屏
    if _seconds_since(db.get_meta("last_online_nudge_at")) < config.ONLINE_NUDGE_COOLDOWN_SECONDS:
        return

    hint = "用户正在线上看着聊天窗口，但有一小会儿没说话了。"
    text = llm.chat(context.build_context(proactive_hint=hint))
    db.add_message("assistant", text, source="proactive")  # 写回历史，前端轮询会拉到
    db.set_meta("last_online_nudge_at", datetime.now(timezone.utc).isoformat())
    print("[online-nudge] 在线主动开口：", text)


def maybe_send_proactive():
    """每次醒来跑一次：判断是否该主动找用户（离线很久 → Bark）。"""
    if not _in_active_hours():
        return

    # 用户多久没说话
    last_user = db.last_user_message_time()
    idle_h = _hours_since(last_user.isoformat() if last_user else None)
    if idle_h < config.PROACTIVE_IDLE_HOURS:
        return

    # 距上次"主动找你"也要有冷却，别刷屏（至少和 idle 阈值一样久）
    if _hours_since(db.get_meta("last_proactive_at")) < config.PROACTIVE_IDLE_HOURS:
        return

    hint = f"用户已经有一段时间没和你说话了（约 {int(idle_h)} 小时）。"
    msgs = context.build_context(proactive_hint=hint)
    text = llm.chat(msgs)

    # 行动回流：写回历史 + 标记时间，再推到手机
    db.add_message("assistant", text, source="proactive")
    db.set_meta("last_proactive_at", datetime.now(timezone.utc).isoformat())
    push.push_to_phone(text)
    print("[proactive] 已主动发送：", text)


def start_scheduler():
    sched = BackgroundScheduler(timezone="Asia/Shanghai")
    # 离线几小时 → Bark 推送
    sched.add_job(maybe_send_proactive, "interval", minutes=30,
                  id="proactive", max_instances=1)
    # 在线但没说话 → 聊天框里主动开口
    sched.add_job(maybe_send_online_nudge, "interval", seconds=15,
                  id="online_nudge", max_instances=1)
    # 在玩手机但没来聊天（靠快捷指令上报）→ Bark 推送
    sched.add_job(maybe_nudge_when_phone_active, "interval", minutes=2,
                  id="phone_nudge", max_instances=1)
    sched.start()
    print("[scheduler] 主动消息调度已启动（离线→Bark；在线→聊天框；玩手机没理它→Bark）")
    return sched
