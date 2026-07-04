"""本地 embedding：用 sentence-transformers 把文本转成向量，供语义检索使用。

初版只支持 EMBEDDING_PROVIDER=local。
模型首次加载会自动下载（约 100MB），之后缓存到本地。
"""
import config

_model = None


def _get_model():
    """lazy load：第一次调用 embed() 时才加载模型，不影响启动速度。"""
    global _model
    if _model is not None:
        return _model
    if config.EMBEDDING_PROVIDER != "local":
        raise ValueError(f"不支持的 EMBEDDING_PROVIDER: {config.EMBEDDING_PROVIDER}")
    from sentence_transformers import SentenceTransformer
    _model = SentenceTransformer(config.EMBEDDING_MODEL)
    return _model


def embed(text: str) -> list[float]:
    """把一段文本转成归一化后的向量。失败时返回空列表，不让聊天主流程崩溃。"""
    if not text or not text.strip():
        return []
    try:
        model = _get_model()
        vec = model.encode(text.strip(), normalize_embeddings=True)
        return vec.tolist()
    except Exception as e:
        print(f"[embedder] embedding 失败：{e}")
        return []
