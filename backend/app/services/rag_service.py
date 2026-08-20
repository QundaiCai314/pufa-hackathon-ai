"""
RAG 服务 - 向量检索、知识索引
"""
import os
import json
import logging
import hashlib
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue

from app.services.embedding import embedding_service

logger = logging.getLogger(__name__)

# Qdrant 配置
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION_NAME = "hydrogen_knowledge"

# 文本分块配置
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50


class RAGService:
    """RAG 检索增强生成服务"""

    def __init__(self):
        self.client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        self.collection_name = COLLECTION_NAME
        self._ensure_collection()

    def _ensure_collection(self):
        """确保 Qdrant 集合存在"""
        collections = self.client.get_collections().collections
        existing = [c.name for c in collections]
        if self.collection_name not in existing:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=3072,  # text-embedding-3-large 维度
                    distance=Distance.COSINE,
                ),
            )
            logger.info(f"Created collection: {self.collection_name}")

    def _make_id(self, text: str, doc: str, page: int, block_idx: int) -> str:
        """生成唯一 ID"""
        raw = f"{doc}_p{page}_b{block_idx}_{text[:50]}"
        return hashlib.md5(raw.encode()).hexdigest()

    async def index_document(self, doc_name: str, analysis: dict, crops_meta: dict):
        """索引整个文档到 Qdrant"""
        points = []
        pages = analysis.get("pages", [])

        for page in pages:
            pn = page.get("page_num", 0)

            # 1. 索引文本块
            for block in page.get("text_blocks", []):
                content = block.get("content", "").strip()
                if len(content) < 20:
                    continue
                chunks = self._chunk_text(content)
                for ci, chunk in enumerate(chunks):
                    vec = await embedding_service.embed_text(chunk)
                    point_id = self._make_id(chunk, doc_name, pn, ci)
                    points.append(PointStruct(
                        id=point_id,
                        vector=vec,
                        payload={
                            "doc": doc_name,
                            "page": pn,
                            "type": block.get("type", "text"),
                            "text": chunk,
                            "chunk_idx": ci,
                        }
                    ))

            # 2. 索引图片 AI 描述
            page_crops = crops_meta.get(str(pn), [])
            for crop in page_crops:
                desc = crop.get("ai_description", "") or crop.get("description", "")
                if len(desc) < 20:
                    continue
                vec = await embedding_service.embed_text(desc)
                block_idx = crop.get("block_idx", 0)
                point_id = self._make_id(desc, doc_name, pn, block_idx)
                points.append(PointStruct(
                    id=point_id,
                    vector=vec,
                    payload={
                        "doc": doc_name,
                        "page": pn,
                        "type": crop.get("type", "other"),
                        "text": desc,
                        "category": crop.get("category", ""),
                        "case": crop.get("case", ""),
                        "source": f"/api/v1/documents/crop_image/{doc_name}/pn/v{block_idx}",
                    }
                ))

            # 3. 索引表格（Key-Value 展开）
            for table in page.get("tables", []):
                text = self._table_to_text(table)
                if len(text) < 20:
                    continue
                vec = await embedding_service.embed_text(text)
                point_id = self._make_id(text, doc_name, pn, 999)
                points.append(PointStruct(
                    id=point_id,
                    vector=vec,
                    payload={
                        "doc": doc_name,
                        "page": pn,
                        "type": "table",
                        "text": text,
                    }
                ))

        # 批量写入 Qdrant
        if points:
            self.client.upsert(collection_name=self.collection_name, points=points)
            logger.info(f"Indexed {len(points)} chunks for {doc_name}")
            return len(points)
        return 0

    def _chunk_text(self, text: str) -> List[str]:
        """将长文本切分为重叠的 chunks"""
        if len(text) <= CHUNK_SIZE:
            return [text]
        chunks = []
        for i in range(0, len(text), CHUNK_SIZE - CHUNK_OVERLAP):
            chunk = text[i:i + CHUNK_SIZE]
            if len(chunk) >= 20:
                chunks.append(chunk)
        return chunks

    def _table_to_text(self, table: dict) -> str:
        """将表格转为 Key-Value 文本"""
        rows = table.get("rows", [])
        if not rows:
            return ""
        headers = rows[0] if rows else []
        lines = []
        for row in rows[1:]:
            pairs = [f"{headers[i] if i < len(headers) else f'col{i}'}: {cell}" for i, cell in enumerate(row)]
            lines.append("，".join(pairs))
        return "\n".join(lines)

    async def search(
        self,
        query: str,
        top_k: int = 5,
        doc_filter: Optional[str] = None,
        type_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """语义搜索"""
        query_vec = await embedding_service.embed_query(query)

        # 构建过滤条件
        must = []
        if doc_filter:
            must.append(FieldCondition(key="doc", match=MatchValue(value=doc_filter)))
        if type_filter:
            must.append(FieldCondition(key="type", match=MatchValue(value=type_filter)))

        qdrant_filter = Filter(must=must) if must else None

        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vec,
            query_filter=qdrant_filter,
            limit=top_k * 3,
            with_payload=True,
        )

        hits = []
        for r in results:
            hits.append({
                "score": r.score,
                "text": r.payload.get("text", ""),
                "doc": r.payload.get("doc", ""),
                "page": r.payload.get("page", 0),
                "type": r.payload.get("type", ""),
                "category": r.payload.get("category", ""),
                "case": r.payload.get("case", ""),
                "source": r.payload.get("source", ""),
            })

        hits.sort(key=lambda x: x["score"], reverse=True)
        return hits[:top_k]

    def get_stats(self) -> Dict[str, Any]:
        """获取索引统计"""
        try:
            collections = self.client.get_collections().collections
            for c in collections:
                if c.name == self.collection_name:
                    return {
                        "collection": self.collection_name,
                        "status": "exists",
                        "name": c.name,
                    }
            return {"collection": self.collection_name, "status": "not_found"}
        except Exception as e:
            return {"collection": self.collection_name, "error": str(e)[:100]}

    def delete_document(self, doc_name: str):
        """删除文档的所有索引"""
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="doc", match=MatchValue(value=doc_name))]
            ),
        )
        logger.info(f"Deleted index for {doc_name}")


# 单例
rag_service = RAGService()
