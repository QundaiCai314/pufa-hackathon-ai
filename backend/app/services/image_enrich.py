"""
产品图片增强描述

读取已有 GPT 分析结果，将提取的产品图片单独发给 GPT，
附带该页的产品大类信息，生成结合上下文的图片描述。
"""

import os, json, base64, asyncio, logging, re
import httpx

logger = logging.getLogger(__name__)

API_KEY = os.getenv("OPENAI_API_KEY", "")
API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
VISION_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-5.6-luna")
ANALYSIS_BASE = "/app/data/analysis"

IMG_PROMPT = """你是一个产品技术文档专家。请根据以下产品信息和图片，生成一段简洁的产品图片描述。

要求：
1. 不要提及图片在页面中的位置（如"页面右下角"等）
2. 结合产品名称、型号、技术特征来描述图片内容
3. 只用中文描述，不要出现任何英文单词（品牌英文名也不要）
4. 格式统一为：产品名称 + 结构特征 + 技术特点
5. 一句话，不超过80字

示例：
- "氢璞第四代碳复合板燃料电池电堆，采用超薄复合板多层堆叠结构，两端配备多路进出接口，具备易集成和可扩展特点"
- "氢璞阴极封闭式空冷燃料电池电堆，采用闭式阴极空气冷却设计，顶部集成多组风扇模块，无需外部冷却泵"
"""


async def enrich_image_descriptions(doc_name: str):
    """
    读取已有分析结果，为每张产品图生成结合上下文的描述。
    只发送产品图（小图），不重新分析整页。
    """
    # 读取已有的 combined.json
    combined_path = os.path.join(ANALYSIS_BASE, doc_name, "gpt_analysis", "combined.json")
    with open(combined_path, "r", encoding="utf-8") as f:
        analysis = json.load(f)
    
    # 读取 manifest 获取实际图片路径
    manifest_path = os.path.join(ANALYSIS_BASE, doc_name, "manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    
    # 构建每页的产品上下文
    page_context = {}
    for page in analysis.get("pages", []):
        pn = page.get("page_num", 0)
        products = page.get("products", [])
        title = page.get("page_title", "")
        
        # 构建上下文文本
        ctx_parts = [f"页面标题: {title}"]
        for p in products:
            model = p.get("model", "")
            cat = p.get("category", "")
            specs = p.get("specs", {})
            if model:
                ctx_parts.append(f"产品: {model} ({cat})")
            if specs:
                spec_str = "; ".join(f"{k}: {v}" for k, v in specs.items())
                ctx_parts.append(f"  参数: {spec_str}")
        page_context[pn] = "\n".join(ctx_parts)
    
    # 收集需要处理的图片（产品图，过滤背景和大图）
    images_to_process = []
    for p in manifest.get("pages", []):
        pn = p["page_num"]
        imgs = p.get("images", {}).get("data", [])
        for idx, img in enumerate(imgs):
            w, h = img["width"], img["height"]
            # 只处理产品图：过滤小图标和整页背景
            if w > 100 and h > 100 and not (w > 700 and h > 1000):
                images_to_process.append({
                    "page": pn,
                    "index": idx,
                    "path": img["path"],
                    "context": page_context.get(pn, ""),
                })
    
    logger.info(f"Enriching {len(images_to_process)} product images for {doc_name}")
    
    # 并发处理
    semaphore = asyncio.Semaphore(3)
    
    async with httpx.AsyncClient(timeout=60) as client:
        async def process_one(img_info):
            async with semaphore:
                pn = img_info["page"]
                idx = img_info["index"]
                img_path = img_info["path"]
                context = img_info["context"]
                
                # Read image
                with open(img_path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode()
                
                ext = os.path.splitext(img_path)[1].lower()
                mime = "image/png" if ext == ".png" else "image/jpeg"
                
                payload = {
                    "model": VISION_MODEL,
                    "messages": [
                        {"role": "system", "content": IMG_PROMPT},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"产品上下文信息：\n{context}\n\n请描述这张产品图片。"},
                                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
                            ],
                        },
                    ],
                    "max_tokens": 300,
                }
                
                headers = {
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json",
                }
                
                r = await client.post(f"{API_BASE}/chat/completions", headers=headers, json=payload)
                
                if r.status_code != 200:
                    logger.error(f"API error P{pn} idx{idx}: {r.status_code}")
                    return {"page": pn, "index": idx, "description": ""}
                
                content = r.json()["choices"][0]["message"]["content"].strip()
                # 后处理：去掉括号内的英文说明（如"（NOWOGEN FUEL CELL STACK）"）
                content = re.sub(r'（[A-Za-z\s\-\d]+）', '', content)
                content = re.sub(r'\([A-Za-z\s\-\d]+\)', '', content)
                logger.info(f"P{pn} img{idx}: {content[:80]}")
                return {"page": pn, "index": idx, "description": content}
        
        results = await asyncio.gather(*[process_one(img) for img in images_to_process])
    
    # 更新 combined.json 中的 images 描述
    # 找到每个 page 的 images 列表，更新 type=product_image 的 description
    desc_map = {(r["page"], r["index"]): r["description"] for r in results}
    
    for page in analysis.get("pages", []):
        pn = page.get("page_num", 0)
        imgs = page.get("images", [])
        product_img_idx = 0
        for img in imgs:
            if img.get("type") == "product_image":
                # 找到对应的 extracted image index
                # manifest 中过滤后的第 product_img_idx 个就是
                manifest_page = next((p for p in manifest["pages"] if p["page_num"] == pn), None)
                if manifest_page:
                    extracted = [
                        (i, im) for i, im in enumerate(manifest_page.get("images", {}).get("data", []))
                        if im["width"] > 100 and im["height"] > 100
                        and not (im["width"] > 700 and im["height"] > 1000)
                    ]
                    if product_img_idx < len(extracted):
                        real_idx = extracted[product_img_idx][0]
                        key = (pn, real_idx)
                        if key in desc_map:
                            img["description"] = desc_map[key]
                product_img_idx += 1
    
    # 保存更新后的 combined.json
    with open(combined_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Updated {len(results)} image descriptions in combined.json")
    return {"updated": len(results), "images": results}
