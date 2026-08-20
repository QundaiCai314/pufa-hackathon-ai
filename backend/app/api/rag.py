"""
RAG API 路由 - 检索增强生成
"""
import os
import json
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.rag_service import rag_service
from app.services.vision_service import get_gpt_analysis, ANALYSIS_BASE

logger = logging.getLogger(__name__)

router = APIRouter(tags=["rag"])


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    doc: Optional[str] = None
    type: Optional[str] = None


class IndexResponse(BaseModel):
    doc: str
    chunks_indexed: int
    status: str


@router.post("/rag/search")
async def search(request: SearchRequest):
    """语义搜索"""
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    results = await rag_service.search(
        query=request.query,
        top_k=request.top_k,
        doc_filter=request.doc,
        type_filter=request.type,
    )
    return {"query": request.query, "results": results, "count": len(results)}


@router.post("/rag/index/{filename}")
async def index_document(filename: str):
    """索引文档到 Qdrant"""
    analysis = get_gpt_analysis(filename)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found. Run analysis first.")
    
    # 读取 crops_metadata.json
    crops_meta = {}
    crops_path = os.path.join(ANALYSIS_BASE, filename, "crops_metadata.json")
    if os.path.exists(crops_path):
        with open(crops_path, "r", encoding="utf-8") as f:
            crops_meta = json.load(f)
    
    chunks = await rag_service.index_document(filename, analysis, crops_meta)
    return IndexResponse(doc=filename, chunks_indexed=chunks, status="success")


@router.delete("/rag/index/{filename}")
async def delete_index(filename: str):
    """删除文档索引"""
    rag_service.delete_document(filename)
    return {"doc": filename, "status": "deleted"}


@router.get("/rag/stats")
def get_stats():
    """获取索引统计"""
    return rag_service.get_stats()
