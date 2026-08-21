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
                        "case_name": crop.get("case", ""),
                        "source": f"/api/v1/documents/extracted_image/{doc_name}/{pn}/{block_idx}",
                    }
                ))

            # 3. 将产品规格字典索引为标准二列表，避免参数只存在于正文时无法结构化展示。
            for product in page.get("products", []):
                specs = product.get("specs", {}) or {}
                if not specs:
                    continue
                model = str(product.get("model", "产品规格"))
                headers = ["参数", model]
                rows = [[str(key), str(value)] for key, value in specs.items()]
                table_text = self._table_to_text({"headers": headers, "rows": rows})
                vec = await embedding_service.embed_text(f"{product.get('category', '')} {table_text}")
                point_id = self._make_id(table_text, doc_name, pn, 998)
                points.append(PointStruct(
                    id=point_id,
                    vector=vec,
                    payload={
                        "doc": doc_name,
                        "page": pn,
                        "type": "table",
                        "text": table_text,
                        "table_headers": headers,
                        "table_rows": rows,
                        "table_title": product.get("category", "产品规格"),
                    }
                ))

            # 4. 索引文档中原有表格（修正表头 + OCR 混淆）
            for table in page.get("tables", []):
                headers = list(table.get("headers", []))
                rows = [list(r) for r in table.get("rows", [])]
                if not headers or not rows:
                    continue
                
                # 修正：如果第一列是"参数"且其他列是型号，转置表格
                # 原始：[参数, CESP250, CESP500, ...] → 转置为：[型号, 参数1, 参数2, ...]
                if headers[0] == "参数" and len(headers) > 2:
                    # 检查其他列是否是型号（包含字母和数字）
                    other_headers = headers[1:]
                    is_model = all(any(c.isalpha() for c in h) and any(c.isdigit() for c in h) for h in other_headers if h)
                    if is_model:
                        # 转置：型号为行，参数为列
                        new_headers = ["型号"] + [str(r[0]) for r in rows]
                        new_rows = []
                        for col_idx in range(1, len(headers)):
                            new_row = [headers[col_idx]] + [str(r[col_idx]) if col_idx < len(r) else "" for r in rows]
                            new_rows.append(new_row)
                        headers = new_headers
                        rows = new_rows
                
                # 修复 OCR 混淆："产氧量"→"产氢量"
                fixed_rows = []
                seen_names = {}
                for row in rows:
                    if not row:
                        fixed_rows.append(row)
                        continue
                    name = str(row[0])
                    if name in seen_names:
                        seen_names[name] += 1
                        new_row = list(row)
                        if "氢" in name:
                            new_row[0] = name.replace("氢", "氧")
                        fixed_rows.append(new_row)
                    else:
                        seen_names[name] = 1
                        fixed_rows.append(row)
                
                table_text = self._table_to_text({"headers": headers, "rows": fixed_rows})
                if len(table_text) < 20:
                    continue
                vec = await embedding_service.embed_text(table_text)
                point_id = self._make_id(table_text, doc_name, pn, 999)
                points.append(PointStruct(
                    id=point_id,
                    vector=vec,
                    payload={
                        "doc": doc_name,
                        "page": pn,
                        "type": "table",
                        "text": table_text,
                        "table_headers": headers,
                        "table_rows": fixed_rows,
                        "table_title": table.get("title", ""),
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
                "table_headers": r.payload.get("table_headers", []),
                "table_rows": r.payload.get("table_rows", []),
                "table_title": r.payload.get("table_title", ""),
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

    def is_indexed(self, doc_name: str) -> bool:
        """检查文档是否已向量化"""
        try:
            result = self.client.count(
                collection_name=self.collection_name,
                count_filter=Filter(must=[FieldCondition(key="doc", match=MatchValue(value=doc_name))]),
            )
            return result.count > 0
        except Exception:
            return False

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
