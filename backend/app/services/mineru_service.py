"""
MinerU PDF 解析服务

封装 MinerU (magic-pdf) 的 PDF 解析能力，提供：
- PDF 解析为 Markdown + JSON
- 内容列表（content_list）结构化提取
- 图片提取
- 解析结果存储到数据库
"""

import os
import json
import shutil
import subprocess
import asyncio
import logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class MinerUService:
    """MinerU PDF 解析服务"""

    def __init__(self):
        self.output_base = os.getenv("MINERU_OUTPUT_DIR", "/app/data/mineru_output")
        os.makedirs(self.output_base, exist_ok=True)

    async def parse_pdf(
        self,
        pdf_path: str,
        source_file: Optional[str] = None,
        parse_mode: str = "auto",
    ) -> dict:
        """
        解析 PDF 文件，返回结构化内容。

        Args:
            pdf_path: PDF 文件的绝对路径
            source_file: 源文件名（用于输出目录命名）
            parse_mode: 解析模式，auto/ocr/txt

        Returns:
            dict with keys:
                - status: success/error
                - output_dir: 输出目录路径
                - markdown: Markdown 文本内容
                - content_list: 结构化内容列表
                - images: 图片文件列表
                - page_count: 页数
                - error: 错误信息（如有）
        """
        if not os.path.exists(pdf_path):
            return {"status": "error", "error": f"PDF not found: {pdf_path}"}

        # 确定输出目录名（保留中文，magic-pdf 支持中文目录名）
        if source_file:
            output_name = Path(source_file).stem
        else:
            output_name = Path(pdf_path).stem

        output_dir = os.path.join(self.output_base, output_name)

        # 如果输出目录已存在，先清理
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)

        os.makedirs(output_dir, exist_ok=True)

        # 构建 magic-pdf 命令
        cmd = [
            "magic-pdf",
            "-p", pdf_path,
            "-o", output_dir,
            "-m", parse_mode,
        ]

        logger.info(f"Starting MinerU parse: {pdf_path} -> {output_dir}")

        try:
            # 在线程池中运行子进程（避免阻塞事件循环）
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace")[-2000:]
                logger.error(f"MinerU failed (exit {proc.returncode}): {error_msg}")
                return {"status": "error", "error": error_msg, "output_dir": output_dir}

            logger.info(f"MinerU parse completed: {output_dir}")

        except FileNotFoundError:
            return {"status": "error", "error": "magic-pdf command not found. Is MinerU installed?"}
        except Exception as e:
            logger.error(f"MinerU exception: {e}")
            return {"status": "error", "error": str(e), "output_dir": output_dir}

        # magic-pdf 会在 output_dir 下创建同名子目录/auto/ 结构
        # 递归查找 auto 目录
        auto_dir = None
        for root, dirs, files in os.walk(output_dir):
            if "auto" in dirs:
                auto_dir = os.path.join(root, "auto")
                break
        if not auto_dir:
            auto_dir = output_dir

        # 读取结果
        return self._collect_results(auto_dir, output_dir, output_name)

    def _collect_results(self, auto_dir: str, output_dir: str, name: str) -> dict:
        """收集解析结果"""
        result = {
            "status": "success",
            "output_dir": output_dir,
            "markdown": None,
            "content_list": None,
            "images": [],
            "page_count": 0,
        }

        # Markdown 文件 - 查找任意 .md 文件
        if os.path.exists(auto_dir):
            for f in os.listdir(auto_dir):
                if f.endswith(".md"):
                    with open(os.path.join(auto_dir, f), "r", encoding="utf-8") as fh:
                        result["markdown"] = fh.read()
                    break

        # content_list.json - 查找任意 _content_list.json
        if os.path.exists(auto_dir):
            for f in os.listdir(auto_dir):
                if f.endswith("_content_list.json"):
                    with open(os.path.join(auto_dir, f), "r", encoding="utf-8") as fh:
                        result["content_list"] = json.load(fh)
                    break

        # 图片
        images_dir = os.path.join(auto_dir, "images")
        if os.path.exists(images_dir):
            images = sorted(os.listdir(images_dir))
            result["images"] = [os.path.join("images", img) for img in images]

        # 页数
        if result["content_list"]:
            pages = set()
            for item in result["content_list"]:
                if "page_idx" in item:
                    pages.add(item["page_idx"])
            result["page_count"] = len(pages) if pages else 0

        # 统计信息
        if result["content_list"]:
            text_count = sum(1 for i in result["content_list"] if i.get("type") == "text")
            image_count = sum(1 for i in result["content_list"] if i.get("type") == "image")
            result["stats"] = {
                "total_items": len(result["content_list"]),
                "text_items": text_count,
                "image_items": image_count,
            }

        return result

    def get_content_summary(self, content_list: list) -> dict:
        """从 content_list 提取摘要信息"""
        if not content_list:
            return {}

        pages = set()
        text_items = []
        for item in content_list:
            if "page_idx" in item:
                pages.add(item["page_idx"])
            if item.get("type") == "text":
                text = item.get("text", "").strip()
                if len(text) > 2:
                    text_items.append({"page": item.get("page_idx", 0), "text": text})

        return {
            "page_count": len(pages),
            "total_items": len(content_list),
            "meaningful_text_count": len(text_items),
            "text_preview": text_items[:10],
        }


# 全局单例
mineru_service = MinerUService()
