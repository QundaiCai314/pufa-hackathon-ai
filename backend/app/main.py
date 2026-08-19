"""
氢璞 AI 智能助手 - 后端主应用
"""

import os
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# 路由
from app.api.documents import router as documents_router

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# 创建 FastAPI 应用
app = FastAPI(
    title="氢璞 AI 智能助手 API",
    description="企业知识库与智能服务助手 - 基于 RAG 的企业知识与智能服务系统",
    version="1.0.0",
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# 注册路由
# ============================================================
app.include_router(documents_router, prefix="/api/v1/documents", tags=["documents"])

# TODO: 待注册路由
# - /api/v1/chat - 聊天接口
# - /api/v1/content - 内容管理
# - /api/v1/admin - 管理后台


# ============================================================
# 基础接口
# ============================================================

@app.get("/")
async def root():
    """根路径 - 健康检查"""
    return {
        "status": "ok",
        "message": "氢璞 AI 智能助手 API 运行正常",
        "version": "1.0.0",
        "environment": os.getenv("ENV", "development"),
    }


@app.get("/health")
async def health_check():
    """健康检查接口"""
    # 检查各服务连接状态
    checks = {}

    # 数据库
    try:
        import sqlalchemy
        db_url = os.getenv("DATABASE_URL", "")
        if db_url:
            engine = sqlalchemy.create_engine(db_url)
            with engine.connect() as conn:
                conn.execute(sqlalchemy.text("SELECT 1"))
            checks["database"] = "connected"
        else:
            checks["database"] = "not_configured"
    except Exception as e:
        checks["database"] = f"error: {str(e)[:100]}"

    # Qdrant
    try:
        from qdrant_client import QdrantClient
        qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))
        client = QdrantClient(host=qdrant_host, port=qdrant_port)
        client.get_collections()
        checks["qdrant"] = "connected"
    except Exception as e:
        checks["qdrant"] = f"error: {str(e)[:100]}"

    # Redis
    try:
        import redis
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        r = redis.from_url(redis_url)
        r.ping()
        checks["redis"] = "connected"
    except Exception as e:
        checks["redis"] = f"error: {str(e)[:100]}"

    # MinerU
    import shutil
    checks["mineru"] = "installed" if shutil.which("magic-pdf") else "not_installed"

    all_healthy = all(v in ("connected", "installed") for v in checks.values())

    return {
        "status": "healthy" if all_healthy else "degraded",
        "services": checks,
    }


@app.get("/api/v1/info")
async def get_info():
    """获取系统信息"""
    return {
        "app_name": "氢璞 AI 智能助手",
        "company": "北京氢璞创能科技有限公司",
        "description": "基于 RAG 的企业知识库与智能客服系统",
        "features": [
            "多模态内容理解（文本、表格、图片、图表、地图）",
            "智能对话与问答",
            "产品推荐",
            "知识库管理",
            "人工审核与修正",
            "MinerU PDF 解析（OCR + 版面分析）",
        ],
        "endpoints": {
            "documents_upload": "/api/v1/documents/upload",
            "documents_parse": "/api/v1/documents/parse",
            "documents_result": "/api/v1/documents/result/{filename}",
            "documents_list": "/api/v1/documents/list",
            "mineru_health": "/api/v1/documents/health/mineru",
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
