"""
RAG API 路由 - 检索增强生成
"""
import os
import json
import re
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.rag_service import rag_service
from app.services.llm_service import llm_service
from app.services.vision_service import get_gpt_analysis, ANALYSIS_BASE
from app.api.auth import current_user
from app.services.web_search_service import search_web
from app.services.lead_scoring import score_lead
from app.api.auth import db
from sqlalchemy import text

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


class ChatRequest(BaseModel):
    query: str
    top_k: int = 5
    doc: Optional[str] = None
    history: Optional[list] = None
    mode: str = "knowledge"  # knowledge / competitor / industry
    context_query: Optional[str] = None
    role: str = "customer_service"
    session_id: Optional[str] = None
    force_web: bool = False


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


@router.post("/rag/chat")
async def chat(request: ChatRequest, user=Depends(current_user)):
    """RAG 问答（检索 + LLM 生成）"""
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    # 销售线索：基于本轮+已保存对话按固定规则动态评分。
    lead = {"score": 0, "level": "low", "signals": {}}
    if request.role == "sales" and request.session_id:
        with db().connect() as conn:
            rows = conn.execute(text("SELECT content FROM chat_messages WHERE session_id=:s ORDER BY created_at"), {"s": request.session_id}).mappings().all()
        lead = score_lead("\n".join(r["content"] for r in rows) + "\n" + request.query)
        with db().begin() as conn:
            conn.execute(text("UPDATE chat_sessions SET lead_score=:score, lead_level=:level, lead_signals=CAST(:signals AS JSONB) WHERE id=:s AND user_id=:u"), {"score":lead["score"],"level":lead["level"],"signals":json.dumps(lead["signals"]),"s":request.session_id,"u":user["id"]})
    
    # 自动判断是否需要联网：用户无需选择搜索模式。
    need_web, web_mode = await llm_service.decide_web_search(request.query)
    q_lower = request.query.lower()
    web_keywords = ("最新", "最近", "当前", "截至目前", "行业动态", "行业趋势", "竞品", "竞争对手", "市场份额", "市场现状", "政策", "法规", "新闻")
    if any(word in q_lower for word in web_keywords):
        need_web = True
        if any(word in q_lower for word in ("竞品", "竞争对手", "竞标", "对比")):
            web_mode = "competitor"
        else:
            web_mode = "industry"
    # 企业产品/型号/参数优先使用知识库；不要因“氢能/重卡”等词误触发联网。
    internal_terms = ("氢璞", "产品", "型号", "参数", "配置", "产能", "纯度", "压力", "电耗", "重卡", "燃料电池", "pem", "aem", "电解槽")
    time_or_market_terms = ("最新", "最近", "当前", "截至目前", "行业动态", "行业趋势", "竞品", "竞争对手", "市场份额", "市场现状", "政策", "法规", "新闻")
    if any(term in q_lower for term in internal_terms) and not any(term in q_lower for term in time_or_market_terms):
        need_web = False
    if need_web:
        web_query = request.query + (" 氢能 竞品" if web_mode == "competitor" else " 氢能 行业动态")
        sources = await search_web(web_query)
        if sources:
            answer = await llm_service.generate_web_answer(request.query, sources, web_mode, request.role)
            return {"query": request.query, "answer": answer, "results": [], "count": 0, "followups": [], "web_sources": sources, "mode": web_mode, "lead": lead}
        # 联网无结果：继续走下面的企业知识库检索，不直接返回空网页结果。

    if request.role == "sales":
        lead_instruction = {"high":"当前客户为高意向（>=70）：主动推荐匹配产品，明确下一步方案、技术交流或商务推进。", "medium":"当前客户为中意向：主动给出初步匹配，并优先补齐一个关键选型条件。", "low":"当前客户为低意向：以需求探索和价值教育为主，不强推产品。"}[lead["level"]]
        request.history = (request.history or []) + [{"role":"system","content":lead_instruction}]

    # 1. 搜索相关文档；短追问继承上一轮主题，避免丢失 PEM 上下文。
    effective_query = request.query
    if request.context_query:
        effective_query = f"{request.context_query} {request.query}"
    
    # 检测产品列表类查询
    product_list_keywords = ("产品有哪些", "有哪些产品", "所有产品", "产品列表", "产品型号", "全部产品", "产品介绍", "介绍.*产品", "你们的产品", "公司产品")
    is_product_list_query = any(kw in request.query for kw in product_list_keywords)
    logger.info(f"Query: '{request.query}', is_product_list_query={is_product_list_query}")
    
    is_pem = any(term in effective_query.lower() for term in ("pem", "质子交换膜", "制氢系统", "制氢设备", "cesp"))
    
    # 产品列表查询需要更多结果，并添加产品型号关键词
    if is_product_list_query:
        search_top_k = 30
        # 添加产品相关关键词帮助检索
        effective_query = effective_query + " ST100G2 ST200G3 CESP250 CESP500 CESP1000 电堆 制氢系统"
    elif is_pem:
        search_top_k = max(request.top_k, 20)
    elif request.role == "sales":
        search_top_k = max(request.top_k, 10)
    else:
        search_top_k = request.top_k
    
    results = await rag_service.search(
        query=(effective_query + " CESP250 CESP500 CESP1000") if is_pem else effective_query,
        top_k=search_top_k,
        doc_filter=request.doc,
    )
    
    # PEM 撬装系统的官方产品页是 P17。该类问题必须收敛到同一产品页，
    # 防止另一份宣传册的通用图片或 CESP 型号表混入回答。
    # 产品列表查询跳过此过滤
    pem_terms = ("pem", "质子交换膜", "制氢系统", "制氢设备", "cesp")
    if not is_product_list_query and not request.doc and any(term in effective_query.lower() for term in pem_terms):
        pem_results = [r for r in results if r.get("doc", "").startswith("01 氢璞2025产品单页") and r.get("page") in (17, 18)]
        if pem_results:
            results = pem_results

    # 2. 无可靠企业资料时，走“无结果卡 + 可选联网”降级链路。
    # 低于该阈值的向量结果只作为弱相关，不直接交给模型当作事实依据。
    max_score = max((float(r.get("score", 0) or 0) for r in results), default=0)
    no_reliable_result = not results or max_score < 0.15
    if no_reliable_result:
        should_web, web_mode = await llm_service.decide_web_search(effective_query)
        if request.force_web:
            should_web = True
        if should_web:
            sources = await search_web(effective_query + (" 氢能 竞品" if web_mode == "competitor" else " 氢能 行业动态"))
            if sources:
                answer = await llm_service.generate_web_answer(effective_query, sources, web_mode, request.role)
                if request.session_id:
                    title = await llm_service.generate_title(request.query, answer)
                    with db().begin() as conn:
                        conn.execute(text("UPDATE chat_sessions SET session_name=:n WHERE id=:s AND user_id=:u"), {"n": title, "s": request.session_id, "u": user["id"]})
                return {"query": request.query, "answer": answer, "results": [], "count": 0, "followups": [], "web_sources": sources, "mode": web_mode, "lead": lead, "no_result": False, "web_available": True}
        answer = f"暂未在当前企业资料中找到“{request.query}”的可靠信息。你可以换一种说法，或补充产品型号、应用场景和关键参数。"
        return {"query": request.query, "answer": answer, "results": [], "count": 0, "followups": [], "web_sources": [], "mode": "knowledge", "lead": lead, "no_result": True, "web_available": bool(should_web)}

    # 3. LLM 生成回答
    # 产品列表查询：直接提取型号，不依赖 LLM
    logger.info(f"is_product_list_query={is_product_list_query}, results_count={len(results)}")
    if is_product_list_query:
        # 返回产品分类（不是具体型号）
        answer = """目前可查询到以下产品：

**燃料电池电堆系列**：
- 氢璞第四代碳复合板电堆
- 氢璞第五代碳复合板电堆
- 氢璞第六代碳复合板电堆
- 氢璞第七代碳复合板电堆
- 氢璞阴极封闭式空冷电堆
- 氢璞金属电堆

**燃料电池系统**：
- 氢璞E200氢燃料电池系统
- 氢璞船用燃料电池系统

**制氢设备**：
- 氢璞撬装式PEM制氢系统

请问您想详细了解哪一款产品的参数和特性？"""
    else:
        answer = await llm_service.generate_answer(
            query=effective_query,
            search_results=results,
            history=request.history,
            role=request.role,
        )
    followups = await llm_service.generate_followups(request.query, results)

    # 4. 首轮问答后自动生成会话标题
    if request.session_id:
        with db().connect() as conn:
            msg_count = conn.execute(
                text("SELECT COUNT(*) FROM chat_messages WHERE session_id=:s"),
                {"s": request.session_id},
            ).scalar() or 0
        if msg_count <= 1:
            title = await llm_service.generate_title(request.query, answer)
            with db().begin() as conn:
                conn.execute(
                    text("UPDATE chat_sessions SET session_name=:n WHERE id=:s AND user_id=:u"),
                    {"n": title, "s": request.session_id, "u": user["id"]},
                )

    return {
        "query": request.query,
        "answer": answer,
        "results": results,
        "count": len(results),
        "followups": followups,
        "web_sources": [],
        "mode": "knowledge",
        "lead": lead,
        "no_result": False,
        "web_available": False,
    }


@router.post("/rag/chat/stream")
async def chat_stream(request: ChatRequest, user=Depends(current_user)):
    """RAG 问答（流式输出）"""
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    # 1. 搜索相关文档；短追问继承上一轮主题，避免丢失 PEM 上下文。
    effective_query = request.query
    if request.context_query:
        effective_query = f"{request.context_query} {request.query}"
    is_pem = any(term in effective_query.lower() for term in ("pem", "质子交换膜", "制氢系统", "制氢设备", "cesp"))
    results = await rag_service.search(
        query=(effective_query + " CESP250 CESP500 CESP1000") if is_pem else effective_query,
        top_k=max(request.top_k, 20) if is_pem else (max(request.top_k, 10) if request.role == "sales" else request.top_k),
        doc_filter=request.doc,
    )
    
    pem_terms = ("pem", "质子交换膜", "制氢系统", "制氢设备", "cesp")
    if not request.doc and any(term in effective_query.lower() for term in pem_terms):
        pem_results = [r for r in results if r.get("doc", "").startswith("01 氢璞2025产品单页") and r.get("page") in (17, 18)]
        if pem_results:
            results = pem_results

    # 2. 流式生成
    async def generate():
        async for chunk in llm_service.generate_answer_stream(
            query=request.query,
            search_results=results,
            history=request.history,
        ):
            yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/rag/index/{filename}")
async def index_document(filename: str):
    """索引文档到 Qdrant"""
    # 先检查是否已索引，避免重复全量重建导致超时
    if rag_service.is_indexed(filename):
        return IndexResponse(doc=filename, chunks_indexed=0, status="already_indexed")
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
