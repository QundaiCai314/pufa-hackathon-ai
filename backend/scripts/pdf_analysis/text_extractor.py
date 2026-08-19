"""
PDF 文本提取模块
使用 PyMuPDF 和 pdfplumber 双引擎提取文本
"""

import fitz  # PyMuPDF
import pdfplumber
from pathlib import Path
from typing import List, Dict, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TextExtractor:
    """文本提取器"""
    
    def __init__(self, pdf_path: str):
        """
        初始化提取器
        
        Args:
            pdf_path: PDF 文件路径
        """
        self.pdf_path = Path(pdf_path)
        self.fitz_doc: Optional[fitz.Document] = None
        self.plumber_doc: Optional[pdfplumber.PDF] = None
    
    def open(self):
        """打开 PDF 文档"""
        try:
            self.fitz_doc = fitz.open(self.pdf_path)
            self.plumber_doc = pdfplumber.open(self.pdf_path)
            logger.info(f"成功打开 PDF: {self.pdf_path.name}")
            return self
        except Exception as e:
            logger.error(f"打开 PDF 失败: {e}")
            raise
    
    def close(self):
        """关闭 PDF 文档"""
        if self.fitz_doc:
            self.fitz_doc.close()
            self.fitz_doc = None
        if self.plumber_doc:
            self.plumber_doc.close()
            self.plumber_doc = None
    
    def __enter__(self):
        return self.open()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def extract_text_fitz(self, page_num: int) -> str:
        """
        使用 PyMuPDF 提取文本
        
        Args:
            page_num: 页码（从 0 开始）
            
        Returns:
            文本内容
        """
        if not self.fitz_doc:
            raise ValueError("PDF 文档未打开")
        
        try:
            page = self.fitz_doc[page_num]
            text = page.get_text("text")
            return text
        except Exception as e:
            logger.error(f"PyMuPDF 提取文本失败 (页 {page_num + 1}): {e}")
            return ""
    
    def extract_text_plumber(self, page_num: int) -> str:
        """
        使用 pdfplumber 提取文本
        
        Args:
            page_num: 页码（从 0 开始）
            
        Returns:
            文本内容
        """
        if not self.plumber_doc:
            raise ValueError("PDF 文档未打开")
        
        try:
            page = self.plumber_doc.pages[page_num]
            text = page.extract_text()
            return text or ""
        except Exception as e:
            logger.error(f"pdfplumber 提取文本失败 (页 {page_num + 1}): {e}")
            return ""
    
    def extract_text_blocks_fitz(self, page_num: int) -> List[Dict]:
        """
        使用 PyMuPDF 提取文本块（包含位置信息）
        
        Args:
            page_num: 页码（从 0 开始）
            
        Returns:
            文本块列表
        """
        if not self.fitz_doc:
            raise ValueError("PDF 文档未打开")
        
        try:
            page = self.fitz_doc[page_num]
            blocks = page.get_text("blocks")
            
            result = []
            for block in blocks:
                # block: (x0, y0, x1, y1, "text", block_no, block_type)
                if len(block) >= 7:
                    x0, y0, x1, y1, text, block_no, block_type = block[:7]
                    
                    # 只保留文本块（block_type == 0）
                    if block_type == 0 and text.strip():
                        result.append({
                            'block_no': block_no,
                            'bbox': [x0, y0, x1, y1],
                            'text': text.strip(),
                            'width': x1 - x0,
                            'height': y1 - y0
                        })
            
            return result
        except Exception as e:
            logger.error(f"提取文本块失败 (页 {page_num + 1}): {e}")
            return []
    
    def extract_text_words(self, page_num: int) -> List[Dict]:
        """
        使用 pdfplumber 提取单词级文本（更精确的位置）
        
        Args:
            page_num: 页码（从 0 开始）
            
        Returns:
            单词列表
        """
        if not self.plumber_doc:
            raise ValueError("PDF 文档未打开")
        
        try:
            page = self.plumber_doc.pages[page_num]
            words = page.extract_words()
            
            result = []
            for word in words:
                result.append({
                    'text': word['text'],
                    'x0': word['x0'],
                    'y0': word['top'],
                    'x1': word['x1'],
                    'y1': word['bottom'],
                    'width': word['x1'] - word['x0'],
                    'height': word['bottom'] - word['top']
                })
            
            return result
        except Exception as e:
            logger.error(f"提取单词失败 (页 {page_num + 1}): {e}")
            return []
    
    def extract_page(self, page_num: int) -> Dict:
        """
        提取单页的所有文本信息
        
        Args:
            page_num: 页码（从 0 开始）
            
        Returns:
            包含多种提取结果的字典
        """
        return {
            'page_num': page_num + 1,
            'text_fitz': self.extract_text_fitz(page_num),
            'text_plumber': self.extract_text_plumber(page_num),
            'text_blocks': self.extract_text_blocks_fitz(page_num),
            'text_words': self.extract_text_words(page_num)
        }
    
    def analyze_text_quality(self, page_num: int) -> Dict:
        """
        分析文本质量
        
        Args:
            page_num: 页码（从 0 开始）
            
        Returns:
            文本质量分析结果
        """
        text_fitz = self.extract_text_fitz(page_num)
        text_plumber = self.extract_text_plumber(page_num)
        
        # 检测乱码
        def has_garbled_text(text: str) -> bool:
            if not text:
                return False
            # 检查是否有大量非中文、非英文、非数字字符
            valid_chars = sum(1 for c in text if c.isalnum() or c.isspace() or '\u4e00' <= c <= '\u9fff')
            return valid_chars / len(text) < 0.5 if text else True
        
        fitz_garbled = has_garbled_text(text_fitz)
        plumber_garbled = has_garbled_text(text_plumber)
        
        return {
            'page_num': page_num + 1,
            'fitz_length': len(text_fitz),
            'plumber_length': len(text_plumber),
            'fitz_garbled': fitz_garbled,
            'plumber_garbled': plumber_garbled,
            'need_ocr': fitz_garbled and plumber_garbled,
            'best_engine': 'plumber' if len(text_plumber) > len(text_fitz) else 'fitz'
        }


if __name__ == "__main__":
    # 测试代码
    test_pdf = r"C:\Users\34515\.astrbot\data\attachments\00_企业资料说明.pdf"
    
    with TextExtractor(test_pdf) as extractor:
        # 提取第一页
        result = extractor.extract_page(0)
        print(f"PyMuPDF 文本长度: {len(result['text_fitz'])}")
        print(f"pdfplumber 文本长度: {len(result['text_plumber'])}")
        print(f"文本块数量: {len(result['text_blocks'])}")
        print(f"单词数量: {len(result['text_words'])}")
        
        # 分析文本质量
        quality = extractor.analyze_text_quality(0)
        print(f"\n文本质量分析: {quality}")
        
        # 显示前 200 个字符
        print(f"\nPyMuPDF 文本预览:\n{result['text_fitz'][:200]}")
        print(f"\npdfplumber 文本预览:\n{result['text_plumber'][:200]}")
