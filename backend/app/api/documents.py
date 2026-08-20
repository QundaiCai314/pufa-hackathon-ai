"""
文档内容 API 路由

提供 PDF 解析后的结构化内容查询和图片访问。
"""

import os
import json
import re
import logging
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from typing import Optional

from app.services.mineru_service import mineru_service
from app.services.vision_service import (
    analyze_document as gpt_analyze_document,
    get_gpt_analysis,
    get_classified_content,
)
from app.services.vision_service import ANALYSIS_BASE
from app.services.image_enrich import enrich_image_descriptions

logger = logging.getLogger(__name__)

router = APIRouter(tags=["documents"])

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/data/raw")


# ============================================================
# 内部工具函数
# ============================================================

def _get_auto_dir(filename: str) -> str:
    """根据文件名查找 MinerU 输出的 auto 目录（包含实际文件的那个）"""
    base_name = Path(filename).stem
    output_base = mineru_service.output_base

    # MinerU 创建嵌套目录: output_base/文件名/文件名/auto/
    # 先尝试精确匹配
    candidate = os.path.join(output_base, base_name, base_name, "auto")
    if os.path.isdir(candidate) and any(f.endswith(".md") or f.endswith("_content_list.json") for f in os.listdir(candidate)):
        return candidate
    candidate = os.path.join(output_base, base_name, "auto")
    if os.path.isdir(candidate) and any(f.endswith(".md") or f.endswith("_content_list.json") for f in os.listdir(candidate)):
        return candidate

    # 递归查找包含实际文件的 auto 目录
    for root, dirs, files in os.walk(output_base):
        if "auto" in dirs:
            auto_path = os.path.join(root, "auto")
            if os.path.isdir(auto_path):
                auto_files = os.listdir(auto_path)
                if any(f.endswith(".md") or f.endswith("_content_list.json") for f in auto_files):
                    return auto_path

    raise HTTPException(404, f"Parse result not found for: {filename}")


def _load_content_list(filename: str) -> list:
    """加载 content_list.json"""
    auto_dir = _get_auto_dir(filename)
    for f in os.listdir(auto_dir):
        if f.endswith("_content_list.json"):
            with open(os.path.join(auto_dir, f), "r", encoding="utf-8") as fh:
                return json.load(fh)
    return []


def _classify_text_item(item: dict) -> str:
    """对 text 项进行细分类"""
    text = (item.get("text") or "").strip()
    level = item.get("text_level", 1)

    if not text:
        return "empty"
    
    # 标题（text_level > 1 或以 # 开头）
    if level and int(level) > 1:
        return "title"
    if text.startswith("#"):
        return "title"
    
    # 纯符号/短字符（可能是 OCR 噪声）
    if len(text) <= 2:
        return "symbol"
    
    # 纯数字
    if re.match(r'^[\d\s.\-]+$', text):
        return "number"
    
    # 包含电话/网址/邮箱
    if any(k in text for k in ["电话", "网址", "邮箱", "http", "www.", "@"]):
        return "contact"
    
    # 包含产品参数特征
    if any(k in text for k in ["功率", "寿命", "成本", "电压", "电流", "kW", "MW", "V", "A", "W/", "Nm³", "kPa", "MPa"]):
        return "spec"
    
    # 默认正文
    return "paragraph"


def _classify_content_list(content_list: list, source_file: str) -> list:
    """对整个 content_list 进行分类标注，过滤掉无意义的噪声项"""
    classified = []
    for item in content_list:
        if item.get("type") == "image":
            img_path = item.get("img_path", "")
            if not img_path:
                continue  # 跳过没有路径的空图片项
            new_item = dict(item)
            new_item["category"] = "image"
            new_item["img_url"] = f"/api/v1/documents/image/{source_file}?path={img_path}"
            classified.append(new_item)
        elif item.get("type") == "text":
            text = (item.get("text") or "").strip()
            if not text:
                continue  # 跳过空文本
            cat = _classify_text_item(item)
            if cat in ("empty", "symbol"):
                continue  # 跳过纯符号噪声
            new_item = dict(item)
            new_item["category"] = cat
            classified.append(new_item)
        else:
            new_item = dict(item)
            new_item["category"] = item.get("type", "other")
            classified.append(new_item)
    
    return classified


# ============================================================
# 路由
# ============================================================

@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """上传 PDF 文档"""
    filename = file.filename or "unknown.pdf"
    ext = os.path.splitext(filename)[1].lower()
    if ext != ".pdf":
        raise HTTPException(400, f"Unsupported file type: {ext}")

    file_path = os.path.join(UPLOAD_DIR, filename)
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    return {
        "status": "ok",
        "filename": filename,
        "file_size": os.path.getsize(file_path),
    }


@router.post("/parse")
async def parse_document(filename: str = "", parse_mode: str = "auto"):
    """解析 PDF 文档"""
    if not filename:
        raise HTTPException(400, "filename is required")

    file_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(404, f"File not found: {filename}")

    result = await mineru_service.parse_pdf(
        pdf_path=file_path,
        source_file=filename,
        parse_mode=parse_mode,
    )

    if result["status"] == "error":
        raise HTTPException(500, f"Parse failed: {result.get('error', 'Unknown')}")

    content_list = result.get("content_list") or []
    summary = mineru_service.get_content_summary(content_list)

    return {
        "status": "ok",
        "filename": filename,
        "page_count": result.get("page_count", 0),
        "stats": result.get("stats", {}),
        "markdown_length": len(result.get("markdown") or ""),
        "markdown_preview": (result.get("markdown") or "")[:500],
        "content_list_count": len(content_list),
        "content_summary": summary,
        "images": result.get("images", []),
        "message": f"Successfully parsed {result.get('page_count', 0)} pages.",
    }


@router.get("/list")
async def list_documents():
    """列出所有文档"""
    documents = []
    if os.path.exists(UPLOAD_DIR):
        for f in sorted(os.listdir(UPLOAD_DIR)):
            if f.lower().endswith(".pdf"):
                file_path = os.path.join(UPLOAD_DIR, f)
                parsed = False
                try:
                    _get_auto_dir(f)
                    parsed = True
                except:
                    pass
                documents.append({
                    "filename": f,
                    "file_size": os.path.getsize(file_path),
                    "parsed": parsed,
                })

    return {"status": "ok", "documents": documents, "total": len(documents)}


@router.get("/content/{filename}")
async def get_content(
    filename: str,
    category: Optional[str] = Query(None, description="按分类筛选: title/paragraph/image/spec/contact/number"),
    page: Optional[int] = Query(None, description="按页码筛选"),
    min_length: int = Query(3, description="最小文本长度，默认过滤短噪声"),
):
    """
    获取文档的结构化内容列表，按分类组织。
    """
    content_list = _load_content_list(filename)
    classified = _classify_content_list(content_list, filename)

    # 统计各分类数量（已过滤后的）
    category_stats = {}
    for item in classified:
        cat = item.get("category", "other")
        category_stats[cat] = category_stats.get(cat, 0) + 1

    # 额外筛选
    filtered = classified
    if category:
        filtered = [item for item in filtered if item.get("category") == category]
    if page is not None:
        filtered = [item for item in filtered if item.get("page_idx") == page]
    if min_length > 0:
        filtered = [item for item in filtered if item.get("category") == "image" or len((item.get("text") or "")) >= min_length]

    # 页码列表
    pages = sorted(set(item.get("page_idx", 0) for item in classified))

    return {
        "status": "ok",
        "filename": filename,
        "total_items": len(classified),
        "filtered_items": len(filtered),
        "category_stats": category_stats,
        "pages": pages,
        "items": filtered,
    }


@router.get("/image/{filename}")
async def get_image(filename: str, path: str = ""):
    """获取解析出的图片"""
    auto_dir = _get_auto_dir(filename)
    img_path = os.path.join(auto_dir, path)
    
    if not os.path.exists(img_path):
        raise HTTPException(404, f"Image not found: {path}")

    return FileResponse(img_path, media_type="image/jpeg")


@router.get("/result/{filename}")
async def get_parse_result(filename: str):
    """获取完整解析结果（Markdown + content_list）"""
    auto_dir = _get_auto_dir(filename)
    
    md_content = None
    content_list = None
    
    for f in os.listdir(auto_dir):
        if f.endswith(".md"):
            with open(os.path.join(auto_dir, f), "r", encoding="utf-8") as fh:
                md_content = fh.read()
        elif f.endswith("_content_list.json"):
            with open(os.path.join(auto_dir, f), "r", encoding="utf-8") as fh:
                content_list = json.load(fh)
    
    return {
        "status": "ok",
        "filename": filename,
        "markdown": md_content,
        "content_list": content_list,
    }


@router.get("/health/mineru")
async def mineru_health():
    """检查 MinerU 环境"""
    import shutil as sh
    magic_pdf_path = sh.which("magic-pdf")
    if not magic_pdf_path:
        return {"status": "error", "message": "magic-pdf not found."}

    cache_base = "/root/.cache/mineru"
    ocr_dir = os.path.join(cache_base, "OCR/paddleocr_torch")
    layout_dir = os.path.join(cache_base, "Layout/LayoutLMv3")
    pak_dir = os.path.join(cache_base, "models/opendatalab--PDF-Extract-Kit/snapshots/master")

    return {
        "status": "ok",
        "magic_pdf_path": magic_pdf_path,
        "models": {
            "ocr_models": {
                "exists": os.path.exists(ocr_dir),
                "model_count": len(os.listdir(ocr_dir)) if os.path.exists(ocr_dir) else 0,
            },
            "layoutlmv3": {
                "exists": os.path.exists(layout_dir),
                "has_weights": os.path.exists(os.path.join(layout_dir, "model_final.pth")) if os.path.exists(layout_dir) else False,
            },
            "pdf_extract_kit": {"exists": os.path.exists(pak_dir)},
        },
    }


# ============================================================
# GPT-5.6 Luna 多模态分析 API
# ============================================================

from pydantic import BaseModel
from typing import List, Any


@router.post("/analyze/{filename}")
async def analyze_with_vision(
    filename: str,
    page_count: Optional[int] = Query(None, description="只分析前N页，None则全部分析"),
    concurrency: int = Query(3, description="并发数"),
):
    """
    使用 GPT-5.6 Luna 视觉模型逐页分析 PDF 渲染图。
    需要先有 analysis 渲染图（由 PDF 分析脚本生成）。
    """
    doc_name = Path(filename).stem
    
    # Check if renders exist
    doc_dir = os.path.join(ANALYSIS_BASE, doc_name)
    if not os.path.exists(doc_dir):
        raise HTTPException(404, f"Document renders not found: {doc_dir}. Please run PDF page rendering first.")
    
    result = await gpt_analyze_document(doc_name, page_count, concurrency)
    
    if "error" in result:
        raise HTTPException(500, result["error"])
    
    return {
        "status": "ok",
        "document": doc_name,
        "total_pages": result.get("total_pages", 0),
        "total_tokens": result.get("total_usage", {}).get("total_tokens", 0),
        "pages_analyzed": len(result.get("pages", [])),
    }


@router.get("/classified/{filename}")
async def get_classified_content_api(filename: str):
    """
    获取 GPT 分析后的分类内容，供前端展示。
    返回按类型分类的内容：产品参数表、文本块、图片描述、联系方式等。
    """
    doc_name = Path(filename).stem
    result = get_classified_content(doc_name)
    
    if "error" in result:
        raise HTTPException(404, result["error"])
    
    return result


@router.get("/analysis_status/{filename}")
async def get_analysis_status(filename: str):
    """检查文档是否已有 GPT 分析结果"""
    doc_name = Path(filename).stem
    analysis = get_gpt_analysis(doc_name)
    
    if not analysis:
        return {
            "status": "not_analyzed",
            "has_renders": os.path.exists(os.path.join(ANALYSIS_BASE, doc_name)),
        }
    
    return {
        "status": "analyzed",
        "total_pages": analysis.get("total_pages", 0),
        "total_tokens": analysis.get("total_usage", {}).get("total_tokens", 0),
    }


@router.get("/render/{filename}/{page}")
async def get_page_render(filename: str, page: int):
    """获取 PDF 逐页渲染图（PNG）"""
    doc_name = Path(filename).stem
    render_path = os.path.join(ANALYSIS_BASE, doc_name, f"page_{page:03d}", "render.png")
    if not os.path.exists(render_path):
        raise HTTPException(404, f"Render not found: {render_path}")
    return FileResponse(render_path, media_type="image/png")


@router.get("/extracted_image/{filename}/{page}/{index}")
async def get_extracted_image(filename: str, page: int, index: int):
    """获取 PDF 提取的原始图片（按页码和索引）"""
    doc_name = Path(filename).stem
    manifest_path = os.path.join(ANALYSIS_BASE, doc_name, "manifest.json")
    if not os.path.exists(manifest_path):
        raise HTTPException(404, "Manifest not found")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for p in manifest.get("pages", []):
        if p["page_num"] == page:
            imgs = p.get("images", {}).get("data", [])
            if index < len(imgs):
                img_path = imgs[index]["path"]
                if os.path.exists(img_path):
                    ext = os.path.splitext(img_path)[1].lower()
                    mime = "image/png" if ext == ".png" else "image/jpeg"
                    return FileResponse(img_path, media_type=mime)
    raise HTTPException(404, f"Image not found: page {page} index {index}")


@router.get("/crop_image/{doc_name}/{page}/{gpt_index}")
async def get_crop_image(doc_name: str, page: int, gpt_index: str):
    """获取从渲染图裁剪的图片区域，优先返回证书/圆形抠图版本"""
    # 支持 verified_ 前缀（PyMuPDF 精确裁剪）和 crop_ 前缀（GPT bbox 裁剪）
    base_dir = os.path.join(ANALYSIS_BASE, doc_name, f"page_{page:03d}", "crops")
    final_dir = os.path.join(ANALYSIS_BASE, doc_name, f"page_{page:03d}", "final_v6")
    cert_dir = os.path.join(ANALYSIS_BASE, doc_name, f"page_{page:03d}", "certs")
    
    if str(gpt_index).startswith("v"):
        idx = int(gpt_index[1:])
        crop_path = os.path.join(base_dir, f"verified_{idx:02d}.png")
        final_path = os.path.join(final_dir, f"final_{idx}.png")
        cert_path = os.path.join(cert_dir, f"cert_{idx:02d}.png")
    else:
        crop_path = os.path.join(base_dir, f"crop_{gpt_index:02d}.png")
        final_path = None
        cert_path = None
    
    # 优先返回证书版本
    if cert_path and os.path.exists(cert_path):
        return FileResponse(cert_path, media_type="image/png", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    
    # 其次返回圆形抠图版本
    if final_path and os.path.exists(final_path):
        return FileResponse(final_path, media_type="image/png", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    
    if not os.path.exists(crop_path):
        raise HTTPException(404, f"Crop image not found: {crop_path}")
    return FileResponse(crop_path, media_type="image/png", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@router.post("/enrich_images/{filename}")
async def enrich_images(filename: str):
    """用 GPT 为已提取的产品图片生成结合产品上下文的描述"""
    doc_name = Path(filename).stem
    result = await enrich_image_descriptions(doc_name)
    return {"status": "ok", "updated": result["updated"]}
