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
    {"type": "product_image|chart|flowchart|map|logo|qr_code|other", "description": "图片内容描述（不要提及位置）"}
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


def get_classified_content(doc_name: str) -> dict:
    """
    从 GPT 分析结果中提取分类后的内容，供前端展示。
    产品按"产品大类 → 具体型号"两级层级组织。
    """
    analysis = get_gpt_analysis(doc_name)
    if not analysis:
        return {"error": "No GPT analysis found. Please run analysis first."}
    
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
                "url": f"/api/v1/documents/extracted_image/{doc_name}.pdf/{pn}/{ext_img['index']}",
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
