# 小满 · 陪伴型 Agent（最小闭环）

一个能在你 iPhone/iPad 上聊天、并会**主动给你发消息**的私人陪伴 agent。
数据全在你自己电脑上，注重隐私。

## 它现在能做什么
- 用 PWA 聊天页和 AI 聊天（可加到 iPhone 主屏，像个 App）
- AI 会在你长时间不说话时，**主动通过 Bark 推送一条消息**到你手机
- 聊天记录、状态都存在本地 `companion.db`，不过任何第三方平台

## 架构
```
iPhone(PWA 聊天 + Bark 收推送)  ←→  你电脑上的 FastAPI 后端  →  DeepSeek/Claude API
                                         └ SQLite(本地数据)
```

---

## 第一次运行（Windows）

### 1. 装 Python
如果没装，去 https://www.python.org 下载 3.10+，安装时勾选「Add Python to PATH」。

### 2. 装依赖
在项目目录打开 PowerShell（注意你电脑上要用 `py`，不是 `python`）：
```powershell
py -m pip install -r requirements.txt
```

### 3. 配置 .env
把 `.env.example` 复制一份改名为 `.env`，填上：
- `LLM_API_KEY`：去 https://platform.deepseek.com 注册拿一个 key
- `BARK_URL`：稍后配（见下），先留空也能聊天

### 4. 启动后端
```powershell
py -m uvicorn main:app --host 0.0.0.0 --port 8000
```
看到 `主动消息调度已启动` 就成功了。

### 5. 手机上打开
- 电脑上浏览器先访问 http://localhost:8000 测试能聊天
- 查你电脑局域网 IP：PowerShell 跑 `ipconfig`，找「IPv4 地址」（形如 192.168.x.x）
- iPhone 连**同一个 WiFi**，Safari 打开 `http://192.168.x.x:8000`
- 点 Safari 分享 → 「添加到主屏幕」，就有个 App 图标了

---

## 配 Bark（让它能主动找你）
1. iPhone App Store 装 **Bark**
2. 打开 App，它会给你一串 URL，形如 `https://api.day.app/xxxxxxxx`
3. 整个粘进 `.env` 的 `BARK_URL`，重启后端

调小 `.env` 里的 `PROACTIVE_IDLE_HOURS`（比如改成 `0.1`）可以快速测试主动推送。

---

## 注意
- 电脑关机/睡眠时后端就停了，AI 不会主动发消息。想 24 小时常驻，以后租台云服务器把这套代码丢上去即可。
- 想改 AI 的性格：改 `config.py` 里的 `PERSONA`。

## 下一步（还没做）
- 长期记忆（向量检索）→ 升级到 PostgreSQL + pgvector
- 敏感信息脱敏
- 工具调用（查天气/日程等）
