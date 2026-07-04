"""FastAPI 入口：聊天接口 + 托管 PWA 前端。

启动：  python -m uvicorn main:app --host 0.0.0.0 --port 8000
然后手机/iPad 连同一个 WiFi，浏览器打开  http://<电脑局域网IP>:8000
"""
from datetime import datetime, timezone
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path

import config
import db
import context
import llm
import scheduler
import memory
import summary

app = FastAPI(title="Companion")

STATIC_DIR = Path(__file__).parent / "static"


@app.on_event("startup")
def _startup():
    db.init_db()
    if not config.LLM_API_KEY:
        print("⚠️  还没在 .env 里填 LLM_API_KEY，聊天会失败。")
    scheduler.start_scheduler()


class ChatIn(BaseModel):
    message: str


class SwitchIn(BaseModel):
    id: int


@app.post("/api/chat")
def chat(body: ChatIn, background: BackgroundTasks):
    user_text = body.message.strip()
    if not user_text:
        return {"reply": ""}

    db.add_message("user", user_text)             # 存用户消息
    msgs = context.build_context(user_input=user_text)  # 组装现场包
    reply = llm.chat(msgs)                         # 调 LLM
    reply_id = db.add_message("assistant", reply)  # 行动回流：存 AI 回复
    background.add_task(memory.maybe_distill)      # 后台提炼长期记忆，不阻塞回复
    background.add_task(summary.maybe_summarize)   # 后台更新对话摘要，不阻塞回复
    return {"reply": reply, "id": reply_id}


@app.get("/api/history")
def history():
    return {"messages": db.recent_messages(config.RECENT_MESSAGES_LIMIT)}


@app.get("/api/poll")
def poll(after: int = 0):
    """前端每几秒调一次：① 上报“我在线”（心跳）② 取回 agent 主动发的新消息。"""
    db.set_meta("last_seen_online", datetime.now(timezone.utc).isoformat())
    return {"messages": db.messages_after(after)}


@app.get("/api/phone-active")
def phone_active():
    """iOS 快捷指令在你打开某些 App 时调用：上报“我此刻在玩手机”。"""
    db.set_meta("last_phone_active", datetime.now(timezone.utc).isoformat())
    return {"ok": True}


@app.get("/api/memories")
def memories_list():
    """“个人信息”面板用：返回 Claude 记得的关于你的事。"""
    return {"name": "Claude", "memories": db.all_memories(config.MEMORY_LIMIT)}


@app.get("/api/sessions")
def sessions_list():
    """对话列表 + 当前对话 id。"""
    return {"current": db.current_session_id(), "sessions": db.list_sessions()}


@app.post("/api/session/new")
def session_new():
    """新建一个对话并切换过去。"""
    return {"id": db.create_session()}


@app.post("/api/session/switch")
def session_switch(body: SwitchIn):
    """切换当前对话。"""
    db.switch_session(body.id)
    return {"ok": True}


# ---- 托管 PWA 前端 ----
@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
