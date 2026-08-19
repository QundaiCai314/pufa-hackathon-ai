"""
PDF OCR 模块
使用多种 OCR 引擎提取图片中的文本
支持 Tesseract、PaddleOCR 等
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional
from PIL import Image
import io

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OCRExtractor:
    """OCR 文本提取器"""
    
    def __init__(self, engine: str = "auto"):
        """
        初始化 OCR 引擎
        
        Args:
            engine: OCR 引擎选择 ("auto", "tesseract", "paddleocr")
        """
        self.engine = engine
        self.ocr_instance = None
        self._init_engine()
    
    def _init_engine(self):
        """初始化 OCR 引擎"""
        if self.engine == "auto":
            # 优先尝试 PaddleOCR（中文效果好）
            try:
                from paddleocr import PaddleOCR
                # PaddleOCR 2.7 API
                self.ocr_instance = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)
                self.engine = "paddleocr"
                logger.info("已加载 PaddleOCR 2.7 引擎（中文优化）")
                return
            except Exception as e:
                logger.warning(f"PaddleOCR 加载失败: {e}")
            
            # 尝试 Tesseract
            try:
                import pytesseract
                # 测试是否可用
                pytesseract.get_tesseract_version()
                self.ocr_instance = pytesseract
                self.engine = "tesseract"
                logger.info("已加载 Tesseract 引擎")
                return
            except Exception as e:
                logger.warning(f"Tesseract 加载失败: {e}")
            
            logger.error("未找到可用的 OCR 引擎！请安装 PaddleOCR 或 Tesseract")
            self.engine = None
        
        elif self.engine == "paddleocr":
            from paddleocr import PaddleOCR
            # PaddleOCR 2.7 API
            self.ocr_instance = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)
            logger.info("已加载 PaddleOCR 2.7 引擎")
        
        elif self.engine == "tesseract":
            import pytesseract
            self.ocr_instance = pytesseract
            logger.info("已加载 Tesseract 引擎")
    
    def is_available(self) -> bool:
        """检查 OCR 引擎是否可用"""
        return self.ocr_instance is not None
    
    def extract_from_image(self, image_path: str) -> Dict:
        """
        从图片文件提取文本
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            提取结果字典
        """
        if not self.is_available():
            return {
                'success': False,
                'text': '',
                'error': 'OCR 引擎不可用'
            }
        
        try:
            if self.engine == "paddleocr":
                return self._extract_paddleocr(image_path)
            elif self.engine == "tesseract":
                return self._extract_tesseract(image_path)
            else:
                return {
                    'success': False,
                    'text': '',
                    'error': f'不支持的引擎: {self.engine}'
                }
        except Exception as e:
            logger.error(f"OCR 提取失败: {e}")
            return {
                'success': False,
                'text': '',
                'error': str(e)
            }
    
    def _extract_paddleocr(self, image_path: str) -> Dict:
        """使用 PaddleOCR 提取"""
        # PaddleOCR 2.7 API
        result = self.ocr_instance.ocr(str(image_path), cls=True)
        
        if not result or not result[0]:
            return {
                'success': True,
                'engine': 'paddleocr',
                'text': '',
                'blocks': [],
                'confidence': 0.0
            }
        
        # 解析结果
        blocks = []
        all_text = []
        total_confidence = 0.0
        
        for line in result[0]:
            if not line:
                continue
            
            box = line[0]  # 坐标
            text_info = line[1]  # (文本, 置信度)
            text = text_info[0]
            confidence = text_info[1]
            
            blocks.append({
                'bbox': box,
                'text': text,
                'confidence': confidence
            })
            all_text.append(text)
            total_confidence += confidence
        
        avg_confidence = total_confidence / len(blocks) if blocks else 0.0
        
        return {
            'success': True,
            'engine': 'paddleocr',
            'text': '\n'.join(all_text),
            'blocks': blocks,
            'confidence': avg_confidence
        }
    
    def _extract_tesseract(self, image_path: str) -> Dict:
        """使用 Tesseract 提取"""
        image = Image.open(image_path)
        
        # 提取文本
        text = self.ocr_instance.image_to_string(image, lang='chi_sim+eng')
        
        # 提取详细信息（包含位置）
        data = self.ocr_instance.image_to_data(image, lang='chi_sim+eng', output_type=self.ocr_instance.Output.DICT)
        
        # 解析块
        blocks = []
        n_boxes = len(data['text'])
        
        for i in range(n_boxes):
            if int(data['conf'][i]) > 0:  # 置信度 > 0
                blocks.append({
                    'bbox': [
                        data['left'][i],
                        data['top'][i],
                        data['left'][i] + data['width'][i],
                        data['top'][i] + data['height'][i]
                    ],
                    'text': data['text'][i],
                    'confidence': float(data['conf'][i]) / 100.0
                })
        
        avg_confidence = sum(b['confidence'] for b in blocks) / len(blocks) if blocks else 0.0
        
        return {
            'success': True,
            'engine': 'tesseract',
            'text': text.strip(),
            'blocks': blocks,
            'confidence': avg_confidence
        }
    
    def extract_from_pil_image(self, pil_image: Image.Image) -> Dict:
        """
        从 PIL Image 对象提取文本
        
        Args:
            pil_image: PIL Image 对象
            
        Returns:
            提取结果字典
        """
        if not self.is_available():
            return {
                'success': False,
                'text': '',
                'error': 'OCR 引擎不可用'
            }
        
        # 保存到临时文件
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            pil_image.save(tmp.name, 'PNG')
            tmp_path = tmp.name
        
        try:
            result = self.extract_from_image(tmp_path)
            return result
        finally:
            # 清理临时文件
            try:
                Path(tmp_path).unlink()
            except:
                pass


def detect_best_ocr_engine() -> Optional[str]:
    """
    检测最佳可用的 OCR 引擎
    
    Returns:
        引擎名称或 None
    """
    # 尝试 PaddleOCR
    try:
        from paddleocr import PaddleOCR
        return "paddleocr"
    except:
        pass
    
    # 尝试 Tesseract
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return "tesseract"
    except:
        pass
    
    return None


if __name__ == "__main__":
    # 测试代码
    print("检测可用的 OCR 引擎...")
    best_engine = detect_best_ocr_engine()
    
    if best_engine:
        print(f"✓ 找到 OCR 引擎: {best_engine}")
        
        ocr = OCRExtractor(engine=best_engine)
        
        # 测试图片（如果有）
        test_image = r"I:\pufa-hackathon-ai\data\analysis\00_企业资料说明\page_001\render.png"
        if Path(test_image).exists():
            print(f"\n测试图片: {test_image}")
            result = ocr.extract_from_image(test_image)
            
            if result['success']:
                print(f"✓ OCR 成功")
                print(f"  引擎: {result['engine']}")
                print(f"  置信度: {result['confidence']:.2%}")
                print(f"  文本长度: {len(result['text'])} 字符")
                print(f"  文本块数: {len(result['blocks'])}")
                print(f"\n文本预览:\n{result['text'][:200]}")
            else:
                print(f"✗ OCR 失败: {result.get('error', '未知错误')}")
    else:
        print("✗ 未找到可用的 OCR 引擎")
        print("\n请安装以下之一:")
        print("  - PaddleOCR: pip install paddleocr")
        print("  - Tesseract: 下载安装 + pip install pytesseract")
