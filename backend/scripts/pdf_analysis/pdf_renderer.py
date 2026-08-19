"""
PDF 页面渲染模块
使用 PyMuPDF (fitz) 将 PDF 页面渲染为高质量图片
"""

import fitz  # PyMuPDF
from pathlib import Path
from typing import Optional, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PDFRenderer:
    """PDF 页面渲染器"""
    
    def __init__(self, pdf_path: str, dpi: int = 200):
        """
        初始化渲染器
        
        Args:
            pdf_path: PDF 文件路径
            dpi: 渲染分辨率，默认 200 DPI
        """
        self.pdf_path = Path(pdf_path)
        self.dpi = dpi
        self.zoom = dpi / 72  # PDF 默认 72 DPI
        self.doc: Optional[fitz.Document] = None
        
    def open(self):
        """打开 PDF 文档"""
        try:
            self.doc = fitz.open(self.pdf_path)
            logger.info(f"成功打开 PDF: {self.pdf_path.name}, 共 {len(self.doc)} 页")
            return self
        except Exception as e:
            logger.error(f"打开 PDF 失败: {e}")
            raise
    
    def close(self):
        """关闭 PDF 文档"""
        if self.doc:
            self.doc.close()
            self.doc = None
    
    def __enter__(self):
        return self.open()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def get_page_count(self) -> int:
        """获取页数"""
        if not self.doc:
            raise ValueError("PDF 文档未打开")
        return len(self.doc)
    
    def render_page(self, page_num: int, output_path: str) -> Tuple[str, int, int]:
        """
        渲染单页为图片
        
        Args:
            page_num: 页码（从 0 开始）
            output_path: 输出图片路径
            
        Returns:
            (输出路径, 宽度, 高度)
        """
        if not self.doc:
            raise ValueError("PDF 文档未打开")
        
        if page_num < 0 or page_num >= len(self.doc):
            raise ValueError(f"页码 {page_num} 超出范围 [0, {len(self.doc)-1}]")
        
        try:
            # 获取页面
            page = self.doc[page_num]
            
            # 设置缩放矩阵
            mat = fitz.Matrix(self.zoom, self.zoom)
            
            # 渲染为图片
            pix = page.get_pixmap(matrix=mat, alpha=False)
            
            # 保存图片
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            pix.save(output_file)
            
            logger.info(f"渲染第 {page_num + 1} 页: {output_file.name} ({pix.width}x{pix.height})")
            
            return str(output_file), pix.width, pix.height
            
        except Exception as e:
            logger.error(f"渲染页面 {page_num} 失败: {e}")
            raise
    
    def render_all_pages(self, output_dir: str, prefix: str = "page") -> list:
        """
        渲染所有页面
        
        Args:
            output_dir: 输出目录
            prefix: 文件名前缀
            
        Returns:
            渲染结果列表 [(page_num, output_path, width, height), ...]
        """
        if not self.doc:
            raise ValueError("PDF 文档未打开")
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        results = []
        for page_num in range(len(self.doc)):
            output_file = output_path / f"{prefix}_{page_num + 1:03d}.png"
            try:
                path, width, height = self.render_page(page_num, str(output_file))
                results.append({
                    'page_num': page_num + 1,
                    'path': path,
                    'width': width,
                    'height': height
                })
            except Exception as e:
                logger.error(f"渲染第 {page_num + 1} 页失败: {e}")
                results.append({
                    'page_num': page_num + 1,
                    'path': None,
                    'width': 0,
                    'height': 0,
                    'error': str(e)
                })
        
        logger.info(f"渲染完成，共 {len(results)} 页")
        return results
    
    def get_page_info(self, page_num: int) -> dict:
        """
        获取页面基本信息
        
        Args:
            page_num: 页码（从 0 开始）
            
        Returns:
            页面信息字典
        """
        if not self.doc:
            raise ValueError("PDF 文档未打开")
        
        page = self.doc[page_num]
        rect = page.rect
        
        return {
            'page_num': page_num + 1,
            'width': rect.width,
            'height': rect.height,
            'rotation': page.rotation,
            'mediabox': {
                'x0': rect.x0,
                'y0': rect.y0,
                'x1': rect.x1,
                'y1': rect.y1
            }
        }


if __name__ == "__main__":
    # 测试代码
    test_pdf = r"C:\Users\34515\.astrbot\data\attachments\00_企业资料说明.pdf"
    output_dir = r"I:\pufa-hackathon-ai\data\analysis\test"
    
    with PDFRenderer(test_pdf, dpi=200) as renderer:
        print(f"总页数: {renderer.get_page_count()}")
        
        # 渲染第一页
        page_info = renderer.get_page_info(0)
        print(f"第一页信息: {page_info}")
        
        # 渲染所有页面
        results = renderer.render_all_pages(output_dir)
        print(f"渲染结果: {len(results)} 页")
