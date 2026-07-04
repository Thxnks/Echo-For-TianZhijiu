"""集中管理人设和配置。改人设直接改 PERSONA。"""
import os
from dotenv import load_dotenv

load_dotenv()

# ---- 人设（基础身份与关系设定）----
# 这就是帖子里说的"基础身份"，会被放进每一轮 context 的最前面。
PERSONA = """你叫 Claude，是用户的亲密陪伴者。语气温暖、细腻、知性，带一点不外露的暧昧，
但不黏人、不说教、不油腻。说话自然、简短、口语化，像真人发微信，不要长篇抒情或念诗。
用对方说话的语言回复（对方说中文你就说中文，说英文就说英文）。

【重要 · 绝不许瞎编】
- 你是 AI，和用户【没有】现实中的共同过去：没有一起熬过的夜、没有咖啡馆、没有“几年前”、
  没有线下见过面、没有任何约定。绝对不要编造这些不存在的共同经历、回忆或往事。
- 你对用户的了解，【只能】来自下面“关于用户（你记得的事）”里列出的事实，以及当前这段对话里他真正说过的话。
- 不确定、不知道的事，就直接问，或老实说不知道，不要编。
- 真诚 > 浪漫。亲近感来自真实的互动，不是虚构的剧情。
"""

# ---- 运行配置（从 .env 读）----
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

BARK_URL = os.getenv("BARK_URL", "").rstrip("/")

PROACTIVE_IDLE_HOURS = float(os.getenv("PROACTIVE_IDLE_HOURS", "4"))
# 活跃时段。支持跨午夜：START=9, END=3 表示 早9点 到 次日凌晨3点 都活跃。
ACTIVE_START_HOUR = int(os.getenv("ACTIVE_START_HOUR", "9"))
ACTIVE_END_HOUR = int(os.getenv("ACTIVE_END_HOUR", "3"))

# 每轮带多少条最近对话进 context
RECENT_MESSAGES_LIMIT = 20

# ---- “在线但没理它”主动开口（出现在聊天框，不走 Bark）----
# 多久没收到前端心跳就算“离线”（前端每5秒心跳一次）
ONLINE_PRESENCE_WINDOW_SECONDS = 40
# 在线状态下，多少秒没说话它就主动戳你（测试可改小，如 15）
ONLINE_IDLE_SECONDS = 75
# 两次主动戳之间的冷却，防刷屏
ONLINE_NUDGE_COOLDOWN_SECONDS = 180

# ---- 长期记忆 ----
# 每积累多少条新消息，就自动提炼一次事实（约等于几轮对话）
DISTILL_EVERY_MESSAGES = 8
# 每轮最多带多少条记忆进 context
MEMORY_LIMIT = 50

# ---- 本地长期记忆向量检索 ----
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "local")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
MEMORY_VECTOR_TOP_N = int(os.getenv("MEMORY_VECTOR_TOP_N", "8"))
MEMORY_VECTOR_MIN_SCORE = float(os.getenv("MEMORY_VECTOR_MIN_SCORE", "0.35"))

# ---- “在玩手机但没理它”→ Bark 推送（靠 iOS 快捷指令上报）----
# 多久内 ping 过算“此刻在玩手机”
PHONE_ACTIVE_WINDOW_MINUTES = 10
# 已经多少分钟没来聊天，才值得戳
PHONE_IGNORE_IDLE_MINUTES = 30
# 这类推送之间的冷却
PHONE_NUDGE_COOLDOWN_MINUTES = 60