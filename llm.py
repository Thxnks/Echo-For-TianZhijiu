"""调 LLM。用 OpenAI 兼容接口，所以 DeepSeek / Claude / 任何兼容服务都能用。"""
from openai import OpenAI
import config

_client = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL)


def chat(messages: list[dict]) -> str:
    """messages: [{"role": "system/user/assistant", "content": "..."}]"""
    resp = _client.chat.completions.create(
        model=config.LLM_MODEL,
        messages=messages,
        temperature=0.8,
    )
    return resp.choices[0].message.content.strip()
