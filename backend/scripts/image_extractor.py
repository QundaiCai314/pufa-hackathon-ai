"""
PDF 图片提取模块
使用 PyMuPDF 提取 PDF 中的嵌入图片
"""

import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Dict, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ImageExtractor:
    """图片提取器"""
    
    def __init__(self, pdf_path: str):
        """
        初始化提取器
        
        Args:
            pdf_path: PDF 文件路径
        """
        self.pdf_path = Path(pdf_path)
        self.doc: Optional[fitz.Document] = None
    
    def open(self):
        """打开 PDF 文档"""
        try:
            self.doc = fitz.open(self.pdf_path)
            logger.info(f"成功打开 PDF: {self.pdf_path.name}")
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
    
    def detect_images(self, page_num: int) -> List[Dict]:
        """
        检测页面中的图片
        
        Args:
            page_num: 页码（从 0 开始）
            
        Returns:
            图片列表
        """
        if not self.doc:
            raise ValueError("PDF 文档未打开")
        
        try:
            page = self.doc[page_num]
            image_list = page.get_images(full=True)
            
            result = []
            for img_index, img_info in enumerate(image_list):
                xref = img_info[0]
                
                # 获取图片基本信息
                try:
                    base_image = self.doc.extract_image(xref)
                    
                    result.append({
                        'image_index': img_index,
                        'xref': xref,
                        'width': base_image['width'],
                        'height': base_image['height'],
                        'colorspace': base_image['colorspace'],
                        'bpc': base_image['bpc'],  # bits per component
                        'ext': base_image['ext'],  # image extension
                        'size': len(base_image['image'])  # bytes
                    })
                except Exception as e:
                    logger.warning(f"获取图片信息失败 (xref={xref}): {e}")
                    result.append({
                        'image_index': img_index,
                        'xref': xref,
                        'error': str(e)
                    })
            
            logger.info(f"检测到 {len(result)} 张图片 (页 {page_num + 1})")
            return result
            
        except Exception as e:
            logger.error(f"检测图片失败 (页 {page_num + 1}): {e}")
            return []
    
    def extract_image(self, page_num: int, image_index: int, output_dir: str) -> Optional[str]:
        """
        提取指定图片
        
        Args:
            page_num: 页码（从 0 开始）
            image_index: 图片索引
            output_dir: 输出目录
            
        Returns:
            输出文件路径
        """
        if not self.doc:
            raise ValueError("PDF 文档未打开")
        
        try:
            page = self.doc[page_num]
            image_list = page.get_images(full=True)
            
            if image_index >= len(image_list):
                logger.warning(f"图片索引 {image_index} 超出范围")
                return None
            
            xref = image_list[image_index][0]
            base_image = self.doc.extract_image(xref)
            
            # 保存图片
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            image_ext = base_image['ext']
            image_bytes = base_image['image']
            
            filename = f"page_{page_num + 1:03d}_img_{image_index:02d}.{image_ext}"
            output_file = output_path / filename
            
            with open(output_file, 'wb') as f:
                f.write(image_bytes)
            
            logger.info(f"提取图片: {filename} ({len(image_bytes)} bytes)")
            return str(output_file)
            
        except Exception as e:
            logger.error(f"提取图片失败 (页 {page_num + 1}, 图 {image_index}): {e}")
            return None
    
    def extract_all_images(self, page_num: int, output_dir: str) -> List[Dict]:
        """
        提取页面中的所有图片
        
        Args:
            page_num: 页码（从 0 开始）
            output_dir: 输出目录
            
        Returns:
            提取结果列表
        """
        images = self.detect_images(page_num)
        
        result = []
        for idx, img_info in enumerate(images):
            if 'error' in img_info:
                result.append({
                    **img_info,
                    'path': None
                })
            else:
                path = self.extract_image(page_num, idx, output_dir)
                result.append({
                    **img_info,
                    'path': path
                })
        
        logger.info(f"提取了 {len(result)} 张图片 (页 {page_num + 1})")
        return result
    
    def get_image_positions(self, page_num: int) -> List[Dict]:
        """
        获取图片在页面中的位置
        
        Args:
            page_num: 页码（从 0 开始）
            
        Returns:
            图片位置列表
        """
        if not self.doc:
            raise ValueError("PDF 文档未打开")
        
        try:
            page = self.doc[page_num]
            image_list = page.get_images(full=True)
            
            result = []
            for img_index, img_info in enumerate(image_list):
                xref = img_info[0]
                
                # 查找图片的所有位置（同一图片可能在页面上出现多次）
                image_rects = []
                for item in page.get_image_info(xrefs=True):
                    if item['xref'] == xref:
                        image_rects.append({
                            'bbox': [item['bbox'][0], item['bbox'][1], item['bbox'][2], item['bbox'][3]],
                            'width': item['width'],
                            'height': item['height'],
                            'transform': item.get('transform', None)
                        })
                
                if image_rects:
                    result.append({
                        'image_index': img_index,
                        'xref': xref,
                        'positions': image_rects
                    })
            
            return result
            
        except Exception as e:
            logger.error(f"获取图片位置失败 (页 {page_num + 1}): {e}")
            return []
    
    def analyze_images(self, page_num: int) -> Dict:
        """
        分析页面图片情况
        
        Args:
            page_num: 页码（从 0 开始）
            
        Returns:
            图片分析结果
        """
        images = self.detect_images(page_num)
        
        total_size = sum(img.get('size', 0) for img in images if 'size' in img)
        large_images = [img for img in images if img.get('width', 0) > 200 or img.get('height', 0) > 200]
        
        return {
            'page_num': page_num + 1,
            'image_count': len(images),
            'total_size': total_size,
            'has_images': len(images) > 0,
            'large_image_count': len(large_images),
            'images': images
        }


if __name__ == "__main__":
    # 测试代码
    test_pdf = r"C:\Users\34515\.astrbot\data\attachments\01 氢璞2025产品单页（1023）校正稿.pdf"
    output_dir = r"I:\pufa-hackathon-ai\data\analysis\test_images"
    
    with ImageExtractor(test_pdf) as extractor:
        # 检测所有页面的图片
        for page_num in range(min(3, len(extractor.doc))):
            analysis = extractor.analyze_images(page_num)
            print(f"\n页 {analysis['page_num']}: {analysis['image_count']} 张图片")
            print(f"  总大小: {analysis['total_size'] / 1024:.1f} KB")
            print(f"  大图数量: {analysis['large_image_count']}")
            
            if analysis['has_images']:
                # 提取图片
                extracted = extractor.extract_all_images(page_num, output_dir)
                print(f"  已提取: {len(extracted)} 张")
