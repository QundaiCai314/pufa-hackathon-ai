"""
嵌入服务 - 使用 OpenAI Embeddings API
"""
import os
import logging
from typing import List, Optional
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# 嵌入模型配置 - 使用 text-embedding-3-large
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMENSIONS = 3072


class EmbeddingService:
    """OpenAI 嵌入服务"""

    def __init__(self):
        # 使用独立的嵌入 API key，4sapi 代理
        api_key = os.getenv("EMBEDDING_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
        api_base = os.getenv("EMBEDDING_API_BASE", "https://4sapi.org/v1")
        self.client = AsyncOpenAI(api_key=api_key, base_url=api_base)
        self.model = EMBEDDING_MODEL

    async def embed_text(self, text: str) -> List[float]:
        """将单条文本转换为向量"""
        response = await self.client.embeddings.create(
            model=self.model,
            input=text[:8192],
        )
        return response.data[0].embedding

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量文本向量化"""
        texts = [t[:8192] for t in texts]
        response = await self.client.embeddings.create(
            model=self.model,
            input=texts,
        )
        return [item.embedding for item in response.data]

    async def embed_query(self, query: str) -> List[float]:
        """查询文本向量化"""
        return await self.embed_text(query)


# 单例
embedding_service = EmbeddingService()
