"""通过 Bark 把主动消息推到 iPhone。Bark 是开源 iOS 推送 App，可自托管。"""
import urllib.parse
import httpx
import config


def push_to_phone(text: str, title: str = "Claude"):
    if not config.BARK_URL:
        print("[push] 未配置 BARK_URL，跳过推送。消息内容：", text)
        return
    # Bark 用法：GET https://api.day.app/<key>/<title>/<body>
    url = f"{config.BARK_URL}/{urllib.parse.quote(title)}/{urllib.parse.quote(text)}"
    try:
        httpx.get(url, timeout=10, params={"group": "companion", "sound": "bell"})
    except Exception as e:
        print("[push] 推送失败：", e)
