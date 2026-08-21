"""
多模态文档分析服务

使用 GPT-5.6 Luna 视觉模型逐页分析 PDF 渲染图，
替代 MinerU OCR 对图文混排文档的糟糕识别效果。
"""

import os
import json
import base64
import logging
import asyncio
import re
from typing import Optional
from urllib.parse import quote
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# Configuration from environment
API_KEY = os.getenv("OPENAI_API_KEY", "")
API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
VISION_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-5.6-luna")

# Analysis output directory
ANALYSIS_BASE = "/app/data/analysis"


# The system prompt for structured document analysis
SYSTEM_PROMPT = """你是一个专业的技术文档分析助手。请仔细分析图片中的产品资料页面，提取所有可见内容。

要求：
1. 识别页面中的所有产品型号和参数表格，输出结构化数据
2. 提取所有文本内容（标题、正文、参数、联系方式等）
3. 识别图片类型并分类（产品图/参数表/数据图表/流程图/地图/品牌标识/二维码/其他）
4. 如果有表格，提取完整的行列结构
5. 如果有联系方式，提取地址、电话、网址、邮箱
6. 对每张图片的描述不要提及它在页面中的位置（如"页面左上角""底部右侧"等），只描述图片内容本身
7. 为每张图片提供边界框坐标 bbox: [x_min, y_min, x_max, y_max]，坐标值为 0-1 的归一化比例（相对于整页宽高），左上角为 [0,0]，右下角为 [1,1]

输出 JSON 格式，包含以下字段：
{
  "page_title": "页面标题",
  "page_type": "cover|product_spec|company_intro|solution|other",
  "products": [
    {
      "model": "型号",
      "category": "产品分类（如：燃料电池电堆/制氢系统等）",
      "specs": {"参数名": "参数值", ...}
    }
  ],
  "tables": [
    {
      "title": "表格标题",
      "headers": ["列1", "列2", ...],
      "rows": [["值1", "值2", ...], ...]
    }
  ],
  "text_blocks": [
    {"type": "title|paragraph|list_item|caption", "content": "文本内容"}
  ],
  "images": [
    {"type": "product_image|chart|flowchart|map|logo|qr_code|other", "description": "图片内容描述（不要提及位置）", "bbox": [x_min, y_min, x_max, y_max]}
  ],
  "contact_info": {
    "address": "", "phone": "", "website": "", "email": ""
  },
  "raw_text": "页面所有可见文字的连续文本"
}

只输出 JSON，不要其他内容。"""


async def analyze_page(
    image_path: str,
    page_num: int,
    client: httpx.AsyncClient,
) -> dict:
    """分析单页渲染图，返回结构化 JSON"""
    
    # Read image as base64
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    
    # Determine mime type
    ext = os.path.splitext(image_path)[1].lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"
    
    payload = {
        "model": VISION_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"请分析第 {page_num} 页的内容。"},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
                ],
            },
        ],
        "max_tokens": 4000,
    }
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    
    r = await client.post(f"{API_BASE}/chat/completions", headers=headers, json=payload)
    
    if r.status_code != 200:
        logger.error(f"API error on page {page_num}: {r.status_code} {r.text[:200]}")
        return {"page_num": page_num, "error": f"API {r.status_code}: {r.text[:200]}"}
    
    data = r.json()
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    
    # Parse JSON from response (handle markdown code fences)
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()
    if content.startswith("json"):
        content = content[4:].strip()
    
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        # Try to find JSON in the content
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                result = json.loads(content[start:end])
            except json.JSONDecodeError:
                result = {"raw_content": content}
        else:
            result = {"raw_content": content}
    
    result["page_num"] = page_num
    result["_usage"] = {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }
    
    return result


async def analyze_document(
    doc_name: str,
    page_count: Optional[int] = None,
    concurrency: int = 3,
) -> dict:
    """
    分析整个文档的所有页面
    
    Args:
        doc_name: 文档名称（不含.pdf）
        page_count: 总页数，None 则自动检测
        concurrency: 并发数
    Returns:
        dict: 包含所有页面分析结果
    """
    doc_dir = os.path.join(ANALYSIS_BASE, doc_name)
    
    if not os.path.exists(doc_dir):
        return {"error": f"Document analysis directory not found: {doc_dir}"}
    
    # Find all render.png files
    pages = []
    for item in sorted(os.listdir(doc_dir)):
        page_dir = os.path.join(doc_dir, item)
        if os.path.isdir(page_dir) and item.startswith("page_"):
            render_path = os.path.join(page_dir, "render.png")
            if os.path.exists(render_path):
                page_num = int(item.replace("page_", ""))
                pages.append((page_num, render_path))
    
    if not pages:
        return {"error": "No page renders found"}
    
    if page_count:
        pages = pages[:page_count]
    
    logger.info(f"Analyzing {len(pages)} pages for {doc_name} with concurrency={concurrency}")
    
    # Create output directory
    output_dir = os.path.join(doc_dir, "gpt_analysis")
    os.makedirs(output_dir, exist_ok=True)
    
    # Analyze pages with concurrency control
    semaphore = asyncio.Semaphore(concurrency)
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    results = []
    
    async with httpx.AsyncClient(timeout=120) as client:
        async def analyze_with_semaphore(page_num, render_path):
            async with semaphore:
                logger.info(f"Analyzing page {page_num}...")
                result = await analyze_page(render_path, page_num, client)
                
                # Save individual page result
                out_file = os.path.join(output_dir, f"page_{page_num:03d}.json")
                with open(out_file, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                
                # Accumulate usage
                usage = result.get("_usage", {})
                total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
                total_usage["completion_tokens"] += usage.get("completion_tokens", 0)
                total_usage["total_tokens"] += usage.get("total_tokens", 0)
                
                logger.info(f"Page {page_num} done: {usage.get('total_tokens', 0)} tokens")
                return result
        
        tasks = [analyze_with_semaphore(pn, rp) for pn, rp in pages]
        results = await asyncio.gather(*tasks)
    
    # Save combined result
    combined = {
        "document_name": doc_name,
        "total_pages": len(results),
        "total_usage": total_usage,
        "pages": sorted(results, key=lambda x: x.get("page_num", 0)),
    }
    
    combined_file = os.path.join(output_dir, "combined.json")
    with open(combined_file, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Analysis complete: {len(results)} pages, {total_usage['total_tokens']} tokens total")

    # 自动生成裁剪图：PyMuPDF 精确裁剪 + GPT 验证 + 矢量图 bbox 补充
    try:
        import fitz
        import base64
        from PIL import Image as PILImage
        from pathlib import Path

        # 找 PDF 文件
        pdf_path = os.path.join("/app/data/raw", doc_name + ".pdf")
        if not os.path.exists(pdf_path):
            for f in os.listdir("/app/data/raw"):
                if f.endswith(".pdf") and Path(f).stem == doc_name:
                    pdf_path = os.path.join("/app/data/raw", f)
                    break

        pdf_doc = fitz.open(pdf_path) if os.path.exists(pdf_path) else None
        crops_meta = {}
        api_key = os.getenv("OPENAI_API_KEY", "")
        api_base = os.getenv("OPENAI_API_BASE", "https://4sapi.org/v1")
        vmodel = os.getenv("OPENAI_VISION_MODEL", "gpt-5.6-luna")

        for page in combined.get("pages", []):
            pn = page["page_num"]
            render_path = os.path.join(ANALYSIS_BASE, doc_name, f"page_{pn:03d}", "render.png")
            if not os.path.exists(render_path):
                continue
            im = PILImage.open(render_path)
            w, h = im.size
            crop_dir = os.path.join(ANALYSIS_BASE, doc_name, f"page_{pn:03d}", "crops")
            os.makedirs(crop_dir, exist_ok=True)

            # === 1. PyMuPDF 真实图片块 ===
            pymupdf_crops = []
            if pdf_doc and pn - 1 < len(pdf_doc):
                pg = pdf_doc[pn - 1]
                sx = w / pg.rect.width
                sy = h / pg.rect.height
                blocks = [b for b in pg.get_text("dict")["blocks"] if b["type"] == 1 and b["width"] > 50 and b["height"] > 50]
                for bi, b in enumerate(blocks):
                    bx1, by1, bx2, by2 = b["bbox"]
                    # 扩展 10 像素安全边距，确保不裁掉内容
                    cx1 = max(0, int(bx1 * sx) - 10)
                    cy1 = max(0, int(by1 * sy) - 10)
                    cx2 = min(w, int(bx2 * sx) + 10)
                    cy2 = min(h, int(by2 * sy) + 10)
                    cp = os.path.join(crop_dir, f"pymupdf_{bi:02d}.png")
                    im.crop((cx1, cy1, cx2, cy2)).save(cp)
                    pymupdf_crops.append({"block_idx": bi, "path": cp})

            # GPT 验证（分批，每批 10 张）
            verified = []
            if pymupdf_crops and api_key:
                batch_size = 10
                for batch_start in range(0, len(pymupdf_crops), batch_size):
                    batch = pymupdf_crops[batch_start:batch_start + batch_size]
                    content = [{"type": "text", "text": "以下是同一页 PDF 中的图片。请判断每张是否是有意义的图片（照片/截图等），排除纯 logo/图标/色块/重复缩略图。输出 JSON 数组 {\"keep\": true/false, \"type\": \"类型(product_image/chart/flowchart/map/other)\", \"description\": \"简短中文描述\"}。"}]
                    for c in batch:
                        with open(c["path"], "rb") as f:
                            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64.b64encode(f.read()).decode()}"}})
                    try:
                        r = httpx.post(
                            f"{api_base}/chat/completions",
                            headers={"Authorization": f"Bearer {api_key}"},
                            json={"model": vmodel, "messages": [{"role": "user", "content": content}], "max_tokens": 2000, "temperature": 0.1},
                            timeout=60
                        )
                        resp = r.json()["choices"][0]["message"]["content"]
                        if resp.startswith("```"):
                            resp = resp.split("```")[1]
                            if resp.startswith("json"):
                                resp = resp[4:]
                        results = json.loads(resp.strip())
                        for crop, gpt_res in zip(batch, results):
                            if gpt_res.get("keep", False):
                                new_path = os.path.join(crop_dir, f"verified_{crop['block_idx']:02d}.png")
                                os.rename(crop["path"], new_path)
                                verified.append({"block_idx": crop["block_idx"], "type": gpt_res.get("type", "other"), "description": gpt_res.get("description", "")})
                            else:
                                os.remove(crop["path"])
                    except Exception as e:
                        logger.warning(f"GPT crop verification failed for P{pn} batch {batch_start//batch_size}: {e}")
                        # Keep unverified
                        for crop in batch:
                            if os.path.exists(crop["path"]):
                                new_path = os.path.join(crop_dir, f"verified_{crop['block_idx']:02d}.png")
                                os.rename(crop["path"], new_path)
                                verified.append({"block_idx": crop["block_idx"], "type": "other", "description": ""})
            else:
                # No GPT, keep all
                for crop in pymupdf_crops:
                    new_path = os.path.join(crop_dir, f"verified_{crop['block_idx']:02d}.png")
                    if os.path.exists(crop["path"]):
                        os.rename(crop["path"], new_path)
                        verified.append({"block_idx": crop["block_idx"], "type": "other", "description": ""})

            # === 2. 矢量图 bbox 补充（PyMuPDF 没检测到但有 GPT bbox 的图） ===
            if pdf_doc and pn - 1 < len(pdf_doc):
                pg = pdf_doc[pn - 1]
                sx = w / pg.rect.width
                sy = h / pg.rect.height
                n_blocks = len([b for b in pg.get_text("dict")["blocks"] if b["type"] == 1 and b["width"] > 50 and b["height"] > 50])
            else:
                n_blocks = 0

            # 如果 PyMuPDF 没检测到足够图片，用 GPT bbox 补充
            for gi, gpt_img in enumerate(page.get("images", [])):
                if gpt_img.get("type") == "logo":
                    continue
                bbox = gpt_img.get("bbox")
                if not bbox or len(bbox) != 4:
                    continue
                desc = gpt_img.get("description", "")
                # 跳过已经有 PyMuPDF 裁剪覆盖的图
                if gi < n_blocks:
                    continue
                gx1 = max(0, int(bbox[0] * w))
                gy1 = max(0, int(bbox[1] * h))
                gx2 = min(w, int(bbox[2] * w))
                gy2 = min(h, int(bbox[3] * h))
                pad_w = max(10, int((gx2 - gx1) * 0.03))
                pad_h = max(10, int((gy2 - gy1) * 0.03))
                cx1 = max(0, gx1 - pad_w)
                cy1 = max(0, gy1 - pad_h)
                cx2 = min(w, gx2 + pad_w)
                cy2 = min(h, gy2 + pad_h)
                if cx2 <= cx1 + 10 or cy2 <= cy1 + 10:
                    continue
                vp = os.path.join(crop_dir, f"verified_{gi:02d}.png")
                im.crop((cx1, cy1, cx2, cy2)).save(vp)
                verified.append({"block_idx": gi, "type": gpt_img.get("type", "other"), "description": desc})

            # === 3. 去重 ===
            seen_desc = set()
            deduped = []
            for c in verified:
                d = c.get("description", "")
                if d and d in seen_desc:
                    cp = os.path.join(crop_dir, f"verified_{c['block_idx']:02d}.png")
                    if os.path.exists(cp):
                        os.remove(cp)
                    continue
                if d:
                    seen_desc.add(d)
                deduped.append(c)

            # === 4. 自动抠图：去掉白边（保守模式，确保不裁掉内容）===
            try:
                import numpy as np
                for c in deduped:
                    cp = os.path.join(crop_dir, f"verified_{c['block_idx']:02d}.png")
                    if not os.path.exists(cp):
                        continue
                    im2 = PILImage.open(cp).convert("RGB")
                    arr = np.array(im2)
                    # 使用更严格的白色阈值（250），只去除接近纯白的边框
                    non_white = (arr < 250).any(axis=2)
                    if not non_white.any():
                        continue
                    rows = np.any(non_white, axis=1)
                    cols = np.any(non_white, axis=0)
                    top = int(np.argmax(rows))
                    bottom = int(len(rows) - 1 - np.argmax(rows[::-1]))
                    left = int(np.argmax(cols))
                    right = int(len(cols) - 1 - np.argmax(cols[::-1]))
                    # 只去除明显白边（>5% 宽度/高度的白边）
                    margin_threshold = 0.05
                    if (top > im2.height * margin_threshold or left > im2.width * margin_threshold or
                        (im2.height - bottom - 1) > im2.height * margin_threshold or
                        (im2.width - right - 1) > im2.width * margin_threshold):
                        # 保留 5 像素安全边距
                        pad = 5
                        im2.crop((max(0, left - pad), max(0, top - pad),
                                  min(im2.width, right + pad), min(im2.height, bottom + pad))).save(cp)
            except Exception as e:
                logger.debug(f"Auto-trim skipped for P{pn}: {e}")

            # === 5. rembg 背景移除（按需手动触发，不在自动流程中）===

            if deduped:
                crops_meta[str(pn)] = deduped

        if pdf_doc:
            pdf_doc.close()

        # 保存元数据
        meta_path = os.path.join(ANALYSIS_BASE, doc_name, "crops_metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(crops_meta, f, ensure_ascii=False, indent=2)
        logger.info(f"Generated crops_metadata.json with {sum(len(v) for v in crops_meta.values())} verified crops")

    except Exception as e:
        logger.warning(f"Failed to generate verified crops: {e}")

    return combined


# ============================================================
# Content query helpers (read from GPT analysis results)
# ============================================================

def get_gpt_analysis(doc_name: str) -> dict:
    """读取 GPT 分析的合并结果"""
    combined_path = os.path.join(ANALYSIS_BASE, doc_name, "gpt_analysis", "combined.json")
    if os.path.exists(combined_path):
        with open(combined_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _is_brochure(analysis: dict) -> bool:
    """判断文档是否是宣传册类型（非产品单页）"""
    pages = analysis.get("pages", [])
    if not pages:
        return False
    # 宣传册特征：大部分页面没有产品参数（products 为空），但有大量 text_blocks
    product_pages = sum(1 for p in pages if p.get("products"))
    total_pages = len(pages)
    # 如果超过 60% 的页面没有产品参数，就是宣传册
    if total_pages > 0 and (total_pages - product_pages) / total_pages > 0.6:
        return True
    # 另一个特征：有 cover 类型页面
    cover_pages = sum(1 for p in pages if p.get("page_type") == "cover")
    if cover_pages >= 1 and product_pages == 0:
        return True
    return False


def _classify_brochure(doc_name: str, analysis: dict) -> dict:
    """
    宣传册分类逻辑：逐页组织，保留全部内容类型。
    """
    # 读取 manifest 获取 PDF 提取的图片
    manifest_path = os.path.join(ANALYSIS_BASE, doc_name, "manifest.json")
    manifest_images = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        for p in manifest.get("pages", []):
            pn = p["page_num"]
            imgs = p.get("images", {}).get("data", [])
            # 过滤：尺寸太小、文件太小（<5KB 的低质量缩略图）、整页背景图
            # 用 MD5 去重
            seen_hashes = set()
            filtered = []
            for i, img in enumerate(imgs):
                if img["width"] <= 100 or img["height"] <= 100:
                    continue
                if img.get("size", 0) <= 5000:
                    continue
                if img["width"] > 700 and img["height"] > 1000:
                    continue
                # MD5 去重
                try:
                    with open(img["path"], "rb") as f:
                        import hashlib
                        md5 = hashlib.md5(f.read()).hexdigest()
                    if md5 in seen_hashes:
                        continue
                    seen_hashes.add(md5)
                except Exception:
                    pass
                filtered.append({"path": img["path"], "width": img["width"], "height": img["height"], "size": img["size"], "index": i})
            manifest_images[pn] = filtered

    # 图片描述映射（enrich 后的结果）
    enriched_path = os.path.join(ANALYSIS_BASE, doc_name, "enriched_images.json")
    enriched_descs = {}
    if os.path.exists(enriched_path):
        with open(enriched_path, "r", encoding="utf-8") as f:
            enriched = json.load(f)
        for item in enriched:
            key = (item.get("page"), item.get("index"))
            enriched_descs[key] = item.get("description", "")

    # PyMuPDF 精确裁剪图元数据（经 GPT 验证）
    crops_meta_path = os.path.join(ANALYSIS_BASE, doc_name, "crops_metadata.json")
    verified_crops = {}
    if os.path.exists(crops_meta_path):
        with open(crops_meta_path, "r", encoding="utf-8") as f:
            verified_crops = json.load(f)

    # 页面类型映射
    type_labels = {
        "cover": "封面", "product_spec": "产品参数", "company_intro": "企业介绍",
        "solution": "解决方案", "other": "其他",
    }

    # 图片类型映射
    img_type_labels = {
        "product_image": "产品图片", "chart": "数据图表", "flowchart": "流程图",
        "map": "地图", "logo": "品牌标识", "qr_code": "二维码", "other": "其他",
    }

    sections = []
    all_tables = []
    contact_info = None

    for page in analysis.get("pages", []):
        pn = page.get("page_num", 0)
        title = page.get("page_title", "")
        ptype = page.get("page_type", "other")

        # 清理标题
        clean_title = title
        # 如果标题中有英文，截取中文部分
        if "/" in title:
            clean_title = title.split("/")[0].strip()
        if "|" in clean_title:
            clean_title = clean_title.split("|")[0].strip()

        # 收集 text_blocks 按 type 分组
        text_blocks = page.get("text_blocks", [])
        titles = [b for b in text_blocks if b.get("type") == "title"]
        paragraphs = [b for b in text_blocks if b.get("type") == "paragraph"]
        list_items = [b for b in text_blocks if b.get("type") == "list_item"]
        captions = [b for b in text_blocks if b.get("type") == "caption"]

        # 清理 list_item 内容（去英文部分）
        clean_list_items = []
        for li in list_items:
            content = li.get("content", "").strip()
            if not content:
                continue
            # 尝试保留中文部分
            lines = content.splitlines()
            cn_lines = [l.strip() for l in lines if re.search(r'[\u4e00-\u9fff]', l)]
            if cn_lines:
                clean_list_items.append(" ".join(cn_lines))
            else:
                clean_list_items.append(content)

        # 清理 captions（去页码、logo 名等）
        clean_captions = []
        for cap in captions:
            c = cap.get("content", "").strip()
            if not c:
                continue
            # 跳过纯页码（如 "07"）或页码+导航（如 "07 | 氢璞介绍"）
            if re.match(r'^\d{1,2}\s*\|', c):
                continue
            # 跳过页脚导航行（如 "Core capability 核心能力 | 12"）
            if re.match(r'^\w+.*\|.*\d{1,2}$', c):
                continue
            # 跳过纯品牌名
            if c in ("NOWOGEN", "Nowogen Introduction"):
                continue
            clean_captions.append(c)

        # 收集图片：优先使用 PyMuPDF 精确裁剪图（经 GPT 验证）
        # crops_metadata.json 存了每页验证后的裁剪图
        page_crops = verified_crops.get(str(pn), [])
        images_by_type: dict[str, list] = {}

        if page_crops:
            # 使用 PyMuPDF 精确裁剪图
            for ci, crop in enumerate(page_crops):
                itype = crop.get("type", "other")
                if itype not in images_by_type:
                    images_by_type[itype] = []
                block_idx = crop["block_idx"]
                crop_path = os.path.join(ANALYSIS_BASE, doc_name, f"page_{pn:03d}", "crops", f"verified_{block_idx:02d}.png")
                if os.path.exists(crop_path):
                    img_entry = {
                        "type": itype,
                        "type_label": img_type_labels.get(itype, "其他"),
                        "description": crop.get("description", ""),
                        "page": pn,
                        "has_file": True,
                        "url": f"/api/v1/documents/crop_image/{quote(doc_name)}/{pn}/v{block_idx}",
                    }
                    # 传递额外字段：ai_description, category, case
                    if crop.get("ai_description"):
                        img_entry["ai_description"] = crop["ai_description"]
                    if crop.get("category"):
                        img_entry["category"] = crop["category"]
                    if crop.get("case"):
                        img_entry["case"] = crop["case"]
                    images_by_type[itype].append(img_entry)
        else:
            # 退回到 GPT bbox + manifest 配对逻辑
            gpt_images = page.get("images", [])
            extracted = manifest_images.get(pn, [])
            gpt_non_logo = [
                (orig_idx, im) for orig_idx, im in enumerate(gpt_images) if im.get("type") != "logo"
            ]
            n_gpt = len(gpt_non_logo)
            n_ext = len(extracted)

            for gi, (orig_idx, gpt_img) in enumerate(gpt_non_logo):
                itype = gpt_img.get("type", "other")
                desc = gpt_img.get("description", "")
                if gi < n_ext:
                    enriched = enriched_descs.get((pn, extracted[gi]["index"]))
                    if enriched:
                        desc = enriched
                if itype not in images_by_type:
                    images_by_type[itype] = []
                if not desc:
                    continue

                crop_path = os.path.join(ANALYSIS_BASE, doc_name, f"page_{pn:03d}", "crops", f"crop_{orig_idx:02d}.png")
                if os.path.exists(crop_path):
                    images_by_type[itype].append({
                        "type": itype,
                        "type_label": img_type_labels.get(itype, "其他"),
                        "description": desc,
                        "page": pn,
                        "has_file": True,
                        "url": f"/api/v1/documents/crop_image/{quote(doc_name)}/{pn}/{orig_idx}",
                    })
                elif gi < n_ext:
                    ext_img = extracted[gi]
                    images_by_type[itype].append({
                        "type": itype,
                        "type_label": img_type_labels.get(itype, "其他"),
                        "description": desc,
                        "page": pn,
                        "index": ext_img["index"],
                        "width": ext_img["width"],
                        "height": ext_img["height"],
                        "has_file": True,
                        "url": f"/api/v1/documents/extracted_image/{quote(doc_name)}.pdf/{pn}/{ext_img['index']}",
                    })
                else:
                    images_by_type[itype].append({
                        "type": itype,
                        "type_label": img_type_labels.get(itype, "其他"),
                        "description": desc,
                        "page": pn,
                        "has_file": False,
                    })

        # 构建该页的所有图片扁平列表（用于渲染）
        all_page_images = []
        for itype, imgs in images_by_type.items():
            all_page_images.extend(imgs)

        # 表格
        for table in page.get("tables", []):
            table["page"] = pn
            all_tables.append(table)

        # 联系方式
        contact = page.get("contact_info")
        if contact and any(contact.values()):
            if not contact_info:
                contact_info = {}
            for k in ["address", "phone", "website", "email"]:
                v = contact.get(k, "")
                if v and not contact_info.get(k):
                    contact_info[k] = v

        # 构建 subsections：将 title+paragraph+caption 按原顺序排列
        subsections = []
        for b in text_blocks:
            bt = b.get("type")
            bc = b.get("content", "").strip()
            if not bc:
                continue
            # 跳过 logo 标题、页脚导航
            if bt == "title" and bc in ("氢璞创能", "NOWOGEN", "氢璨创能"):
                continue
            # 跳过页脚导航行
            if re.match(r'^\d{1,2}\s*\|', bc):
                continue
            if re.match(r'^\w+.*\|.*\d{1,2}$', bc):
                continue
            if bc in ("NOWOGEN", "Nowogen Introduction"):
                continue

            if bt == "title":
                subsections.append({"type": "heading", "content": bc})
            elif bt == "paragraph":
                subsections.append({"type": "paragraph", "content": bc})
            elif bt == "caption":
                subsections.append({"type": "caption", "content": bc})

        section = {
            "page_num": pn,
            "title": clean_title,
            "page_type": ptype,
            "page_type_label": type_labels.get(ptype, "其他"),
            "subsections": subsections,
            "list_items": clean_list_items,
            "captions": clean_captions,
            "images_by_type": images_by_type,
            "all_images": all_page_images,
            "image_count": len(all_page_images),
            "raw_text": page.get("raw_text", ""),
        }
        sections.append(section)

    # 统计
    total_images = sum(len(s["all_images"]) for s in sections)
    img_type_stats = {}
    for s in sections:
        for itype, imgs in s["images_by_type"].items():
            if itype not in img_type_stats:
                img_type_stats[itype] = 0
            img_type_stats[itype] += len(imgs)

    return {
        "doc_type": "brochure",
        "sections": sections,
        "tables": all_tables,
        "contact_info": contact_info,
        "summary": {
            "total_pages": analysis.get("total_pages", 0),
            "total_tokens": analysis.get("total_usage", {}).get("total_tokens", 0),
            "total_images": total_images,
            "image_type_stats": {img_type_labels.get(k, k): v for k, v in img_type_stats.items()},
        },
    }


def _generate_section_summary(title: str, raw_text: str) -> str:
    """用 LLM 为章节生成用户友好的描述"""
    if not raw_text or len(raw_text) < 50:
        return raw_text
    
    # 缓存路径
    cache_dir = os.path.join(ANALYSIS_BASE, "_summaries")
    os.makedirs(cache_dir, exist_ok=True)
    cache_key = f"{hash(title + raw_text[:500])}.txt"
    cache_path = os.path.join(cache_dir, cache_key)
    
    # 读取缓存
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    
    prompt = f"""请将以下宣传册章节的原始文本整理成一段简洁、专业的介绍文字（100-150字）。

章节标题：{title}

原始文本：
{raw_text[:2000]}

要求：
1. 去除重复内容、页码、导航文字
2. 保留关键数据和事实
3. 用流畅的中文描述
4. 不要出现"本文""该页"等指代词
5. 直接输出整理后的文字，不要额外说明"""

    try:
        resp = httpx.post(
            f"{API_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "model": VISION_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 300,
                "temperature": 0.3,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            summary = resp.json()["choices"][0]["message"]["content"].strip()
            # 写入缓存
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(summary)
            return summary
    except Exception as e:
        logger.warning(f"LLM summary failed: {e}")
    
    # 失败时返回清理后的原文
    return re.sub(r'\s+', ' ', raw_text)[:300]


async def _generate_summaries_async(sections: list) -> list:
    """并发生成所有章节的摘要"""
    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(None, _generate_section_summary, s.get("title", ""), s.get("raw_text", ""))
        for s in sections
    ]
    return await asyncio.gather(*tasks)


def get_classified_content(doc_name: str) -> dict:
    """
    从 GPT 分析结果中提取分类后的内容，供前端展示。
    自动判断文档类型：产品单页或宣传册，分别使用不同逻辑。
    """
    analysis = get_gpt_analysis(doc_name)
    if not analysis:
        return {"error": "No GPT analysis found. Please run analysis first."}
    
    # 判断文档类型
    if _is_brochure(analysis):
        result = _classify_brochure(doc_name, analysis)
        # 将宣传册格式转换为前端期望的格式
        all_images = []
        product_groups = []
        sections = result.get("sections", [])
        
        # 并发生成所有章节的摘要
        summaries = asyncio.run(_generate_summaries_async(sections))
        
        for i, section in enumerate(sections):
            for img in section.get("all_images", []):
                all_images.append(img)
            
            product_groups.append({
                "category_name": section.get("title", f"第{section.get('page_num',0)}页"),
                "category_page": section.get("page_num", 0),
                "en_name": section.get("page_type_label", ""),
                "features": section.get("list_items", []),
                "images": section.get("all_images", []),
                "subsections": section.get("subsections", []),
                "summary": summaries[i] if i < len(summaries) else "",
                "image_count": section.get("image_count", 0),
            })
        
        return {
            "doc_type": "brochure",
            "product_groups": product_groups,
            "tables": result.get("tables", []),
            "product_images": all_images,
            "contact_info": result.get("contact_info"),
            "sections": result.get("sections", []),
            "summary": result.get("summary", {}),
        }
    
    classified = {
        "product_groups": [],   # 按大类分组的产品
        "tables": [],
        "product_images": [],  # 产品图片（PDF提取 + GPT描述配对）
        "contact_info": None,
        "documents": [],
        "summary": {
            "total_pages": analysis.get("total_pages", 0),
            "total_tokens": analysis.get("total_usage", {}).get("total_tokens", 0),
        },
    }
    
    # 读取 manifest 获取 PDF 提取的图片路径
    manifest_path = os.path.join(ANALYSIS_BASE, doc_name, "manifest.json")
    manifest_images = {}  # {page_num: [{path, width, height, size}]}
    if os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        for p in manifest.get("pages", []):
            pn = p["page_num"]
            imgs = p.get("images", {}).get("data", [])
            # 过滤掉 68x68 的重复小图（页脚logo/二维码）和 ~800x1100 的整页背景图
            manifest_images[pn] = [
                {"path": img["path"], "width": img["width"], "height": img["height"], "size": img["size"], "index": i}
                for i, img in enumerate(imgs)
                if img["width"] > 100 and img["height"] > 100  # 过滤小图标
                and not (img["width"] > 700 and img["height"] > 1000)  # 过滤整页背景
            ]
    
    pages = analysis.get("pages", [])
    
    # 先收集所有页面信息，包括产品特点（list_item 类型）和英文名
    page_info = []
    for page in pages:
        pn = page.get("page_num", 0)
        title = page.get("page_title", "")
        products = page.get("products", [])
        
        # 提取该页的产品特点（list_item），只保留中文部分
        features = []
        for block in page.get("text_blocks", []):
            if block.get("type") != "list_item":
                continue
            content = block.get("content", "").strip()
            if not content:
                continue
            # 去掉英文部分：按换行分割，只取有中文的行
            lines = content.splitlines()
            cn_lines = [l.strip() for l in lines if re.search(r'[\u4e00-\u9fff]', l)]
            if cn_lines:
                features.append("".join(cn_lines))
            elif content:
                features.append(content)
        
        # 提取英文产品名：优先从 specs 找，其次从标题的 / 分隔，最后从 caption 找全大写多词
        en_name = ""
        # 1. specs 中的"产品英文名"/"英文名称"
        for p in products:
            specs = p.get("specs", {})
            for k, v in specs.items():
                if "英文" in k or "english" in k.lower():
                    en_name = str(v).strip()
                    break
            if en_name:
                break
        # 2. 标题中的 / 分隔
        if not en_name and "/" in title:
            parts = title.split("/")
            if len(parts) > 1:
                en = parts[1].strip()
                if en and any(c.isascii() and c.isalpha() for c in en):
                    en_name = en
        # 3. caption 中全大写多词英文文本（排除单独的 "NOWOGEN"）
        if not en_name:
            for block in page.get("text_blocks", []):
                if block.get("type") != "caption":
                    continue
                c = block.get("content", "").strip()
                ascii_letters = sum(1 for ch in c if ch.isascii() and ch.isalpha())
                if (ascii_letters > 10 and " " in c 
                    and c == c.upper()
                    and c != "NOWOGEN"):
                    en_name = c
                    break
        
        # 判断是否是参数页：标题是"产品参数"，或者有多个带 5+ specs 的产品
        is_spec_page = (
            title.strip() == "产品参数"
            or sum(1 for p in products if len(p.get("specs", {})) >= 5) >= 2
        )
        page_info.append({
            "page_num": pn,
            "title": title,
            "products": products,
            "features": features,
            "en_name": en_name,
            "is_spec_page": is_spec_page,
        })
    
    # 按介绍页+参数页配对组织产品
    i = 0
    while i < len(page_info):
        pi = page_info[i]
        
        if not pi["is_spec_page"]:
            # 这是介绍页 — 产品大类
            # 清理标题：去掉英文部分，只保留中文
            clean_title = pi["title"].split("/")[0].strip().split(" - ")[0].strip()
            if not clean_title:
                clean_title = pi["title"]
            
            group = {
                "category_name": clean_title,
                "category_page": pi["page_num"],
                "en_name": pi["en_name"],
                "features": pi["features"],
                "intro_products": [],
                "spec_products": [],
                "spec_page": None,
            }
            # 介绍页不提取 specs（GPT 对介绍页的提取不统一，特点已通过 features 展示）
            
            # 检查下一页是否是参数页
            if i + 1 < len(page_info) and page_info[i + 1]["is_spec_page"]:
                next_pi = page_info[i + 1]
                group["spec_page"] = next_pi["page_num"]
                for p in next_pi["products"]:
                    group["spec_products"].append({
                        "model": p.get("model", ""),
                        "category": p.get("category", ""),
                        "specs": p.get("specs", {}),
                        "page": next_pi["page_num"],
                    })
                # 也收集下一页的 document 信息
                classified["documents"].append({
                    "page": next_pi["page_num"],
                    "page_title": next_pi["title"],
                    "page_type": next_pi["title"],
                    "raw_text": pages[i + 1].get("raw_text", ""),
                })
                i += 2
            else:
                # 介绍页自己也有参数（如 P17 PEM制氢系统）
                for p in pi["products"]:
                    if len(p.get("specs", {})) >= 5:
                        group["spec_products"].append({
                            "model": p.get("model", ""),
                            "category": p.get("category", ""),
                            "specs": p.get("specs", {}),
                            "page": pi["page_num"],
                        })
                i += 1
        else:
            # 独立参数页（没有前置介绍页）
            clean_title = pi["title"].split("/")[0].strip().split(" - ")[0].strip()
            if not clean_title or clean_title == "产品参数":
                clean_title = f"第{pi['page_num']}页参数"
            
            group = {
                "category_name": clean_title,
                "category_page": pi["page_num"],
                "en_name": pi["en_name"],
                "features": pi["features"],
                "intro_products": [],
                "spec_products": [],
                "spec_page": pi["page_num"],
            }
            for p in pi["products"]:
                group["spec_products"].append({
                    "model": p.get("model", ""),
                    "category": p.get("category", ""),
                    "specs": p.get("specs", {}),
                    "page": pi["page_num"],
                })
            i += 1
        
        classified["product_groups"].append(group)
    
    # 收集产品图片：PDF提取的图片 + GPT描述配对
    for page in pages:
        pn = page.get("page_num", 0)
        
        # 从 GPT 分析中获取该页的 product_image 描述
        gpt_imgs = page.get("images", [])
        gpt_product_descs = [img for img in gpt_imgs if img.get("type") == "product_image"]
        
        # 从 manifest 获取该页提取的图片
        extracted = manifest_images.get(pn, [])
        
        # 配对：PDF提取图 和 GPT product_image 描述
        for i, ext_img in enumerate(extracted):
            desc = gpt_product_descs[i]["description"] if i < len(gpt_product_descs) else ""
            classified["product_images"].append({
                "page": pn,
                "index": ext_img["index"],
                "width": ext_img["width"],
                "height": ext_img["height"],
                "description": desc,
                "url": f"/api/v1/documents/extracted_image/{quote(doc_name)}.pdf/{pn}/{ext_img['index']}",
            })
        
        # 其他分类内容
        for table in page.get("tables", []):
            table["page"] = pn
            classified["tables"].append(table)
        # logo 和 qr_code 只保留一次（放到 contact_info 关联信息里）
        contact = page.get("contact_info")
        if contact and any(contact.values()):
            classified["contact_info"] = contact
    
    return classified
