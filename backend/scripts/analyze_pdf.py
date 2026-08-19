"""
PDF 文档分析主脚本
整合所有模块，生成完整的分析报告
"""

import json
from pathlib import Path
from typing import List, Dict
import logging
from datetime import datetime

from pdf_renderer import PDFRenderer
from text_extractor import TextExtractor
from table_detector import TableDetector
from image_extractor import ImageExtractor
from layout_analyzer import LayoutAnalyzer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PDFAnalyzer:
    """PDF 文档分析器"""
    
    def __init__(self, pdf_path: str, output_dir: str):
        """
        初始化分析器
        
        Args:
            pdf_path: PDF 文件路径
            output_dir: 输出目录
        """
        self.pdf_path = Path(pdf_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.doc_name = self.pdf_path.stem
        self.doc_output_dir = self.output_dir / self.doc_name
        self.doc_output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"初始化分析器: {self.doc_name}")
        logger.info(f"输出目录: {self.doc_output_dir}")
    
    def analyze_document(self, max_pages: int = None) -> Dict:
        """
        分析整个文档
        
        Args:
            max_pages: 最大分析页数（None 表示全部）
            
        Returns:
            文档分析结果
        """
        logger.info(f"开始分析文档: {self.pdf_path.name}")
        
        start_time = datetime.now()
        
        # 打开所有提取器
        renderer = PDFRenderer(str(self.pdf_path))
        text_extractor = TextExtractor(str(self.pdf_path))
        table_detector = TableDetector(str(self.pdf_path))
        image_extractor = ImageExtractor(str(self.pdf_path))
        
        try:
            renderer.open()
            text_extractor.open()
            table_detector.open()
            image_extractor.open()
            
            page_count = renderer.get_page_count()
            pages_to_analyze = min(page_count, max_pages) if max_pages else page_count
            
            logger.info(f"总页数: {page_count}, 将分析: {pages_to_analyze} 页")
            
            # 分析每一页
            pages_analysis = []
            for page_num in range(pages_to_analyze):
                logger.info(f"\n{'='*60}")
                logger.info(f"分析第 {page_num + 1}/{pages_to_analyze} 页")
                logger.info(f"{'='*60}")
                
                page_result = self.analyze_page(
                    page_num, renderer, text_extractor, 
                    table_detector, image_extractor
                )
                pages_analysis.append(page_result)
            
            # 生成文档级别的汇总
            summary = self._generate_summary(pages_analysis)
            
            # 生成清单文件
            manifest = {
                'document_name': self.doc_name,
                'source_file': str(self.pdf_path),
                'analysis_time': start_time.isoformat(),
                'page_count': page_count,
                'analyzed_pages': pages_to_analyze,
                'summary': summary,
                'pages': pages_analysis
            }
            
            # 保存清单
            manifest_file = self.doc_output_dir / 'manifest.json'
            with open(manifest_file, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            
            logger.info(f"\n{'='*60}")
            logger.info(f"分析完成！清单文件: {manifest_file}")
            logger.info(f"{'='*60}")
            
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(f"总耗时: {elapsed:.2f} 秒")
            
            return manifest
            
        finally:
            renderer.close()
            text_extractor.close()
            table_detector.close()
            image_extractor.close()
    
    def analyze_page(self, page_num: int, renderer: PDFRenderer,
                    text_extractor: TextExtractor, table_detector: TableDetector,
                    image_extractor: ImageExtractor) -> Dict:
        """
        分析单页
        
        Args:
            page_num: 页码（从 0 开始）
            renderer: 渲染器
            text_extractor: 文本提取器
            table_detector: 表格检测器
            image_extractor: 图片提取器
            
        Returns:
            页面分析结果
        """
        page_dir = self.doc_output_dir / f"page_{page_num + 1:03d}"
        page_dir.mkdir(exist_ok=True)
        
        # 1. 渲染页面为图片
        logger.info("  [1/6] 渲染页面...")
        render_file = page_dir / f"render.png"
        render_path, render_width, render_height = renderer.render_page(page_num, str(render_file))
        
        # 2. 获取页面信息
        page_info = renderer.get_page_info(page_num)
        
        # 3. 提取文本
        logger.info("  [2/6] 提取文本...")
        text_result = text_extractor.extract_page(page_num)
        text_quality = text_extractor.analyze_text_quality(page_num)
        
        # 保存文本
        text_file = page_dir / "text.txt"
        best_text = text_result['text_plumber'] if text_quality['best_engine'] == 'plumber' else text_result['text_fitz']
        with open(text_file, 'w', encoding='utf-8') as f:
            f.write(best_text)
        
        # 3. 检测表格
        logger.info("  [3/6] 检测表格...")
        table_analysis = table_detector.analyze_table_structure(page_num)
        tables_data = []
        if table_analysis['has_tables']:
            tables_extracted = table_detector.extract_all_tables(page_num)
            for table in tables_extracted:
                quality = table_detector.estimate_table_quality(table)
                tables_data.append({
                    **table,
                    'quality': quality
                })
        
        # 4. 提取图片
        logger.info("  [4/6] 提取图片...")
        image_analysis = image_extractor.analyze_images(page_num)
        images_dir = page_dir / "images"
        images_extracted = []
        if image_analysis['has_images']:
            images_extracted = image_extractor.extract_all_images(page_num, str(images_dir))
        
        # 5. 布局分析
        logger.info("  [5/6] 分析布局...")
        layout_info = {
            'page_num': page_num + 1,
            'page_width': page_info['width'],
            'page_height': page_info['height'],
            'text_blocks': text_result['text_blocks'],
            'tables': [t.get('bbox', [0, 0, 0, 0]) for t in tables_data] if tables_data else [],
            'images': image_analysis.get('images', [])
        }
        layout_result = LayoutAnalyzer.analyze_page_layout(layout_info)
        
        # 6. 生成页面分析报告
        logger.info("  [6/6] 生成报告...")
        page_result = {
            'page_num': page_num + 1,
            'render': {
                'path': str(render_file.relative_to(self.output_dir)),
                'width': render_width,
                'height': render_height
            },
            'page_info': page_info,
            'text': {
                'file': str(text_file.relative_to(self.output_dir)),
                'length': len(best_text),
                'quality': text_quality,
                'block_count': len(text_result['text_blocks']),
                'word_count': len(text_result['text_words'])
            },
            'tables': {
                'count': table_analysis['table_count'],
                'has_tables': table_analysis['has_tables'],
                'data': tables_data
            },
            'images': {
                'count': image_analysis['image_count'],
                'has_images': image_analysis['has_images'],
                'total_size': image_analysis['total_size'],
                'data': images_extracted
            },
            'layout': layout_result
        }
        
        # 保存页面报告
        page_json = page_dir / "analysis.json"
        with open(page_json, 'w', encoding='utf-8') as f:
            json.dump(page_result, f, ensure_ascii=False, indent=2)
        
        logger.info(f"  ✓ 页面分析完成: {page_json}")
        
        return page_result
    
    def _generate_summary(self, pages_analysis: List[Dict]) -> Dict:
        """生成文档摘要"""
        total_text_length = sum(p['text']['length'] for p in pages_analysis)
        total_tables = sum(p['tables']['count'] for p in pages_analysis)
        total_images = sum(p['images']['count'] for p in pages_analysis)
        
        pages_need_ocr = sum(1 for p in pages_analysis if p['text']['quality']['need_ocr'])
        pages_with_tables = sum(1 for p in pages_analysis if p['tables']['has_tables'])
        pages_with_images = sum(1 for p in pages_analysis if p['images']['has_images'])
        
        complexity_counts = {}
        for page in pages_analysis:
            complexity = page['layout']['complexity']
            complexity_counts[complexity] = complexity_counts.get(complexity, 0) + 1
        
        return {
            'total_pages': len(pages_analysis),
            'total_text_length': total_text_length,
            'total_tables': total_tables,
            'total_images': total_images,
            'pages_need_ocr': pages_need_ocr,
            'pages_with_tables': pages_with_tables,
            'pages_with_images': pages_with_images,
            'complexity_distribution': complexity_counts,
            'ocr_required': pages_need_ocr > 0
        }


def main():
    """主函数"""
    # PDF 文件路径
    pdf_files = [
        r"C:\Users\34515\.astrbot\data\attachments\00_企业资料说明.pdf",
        r"C:\Users\34515\.astrbot\data\attachments\01 氢璞2025产品单页（1023）校正稿.pdf",
        r"C:\Users\34515\.astrbot\data\attachments\02（已压缩）氢璞2025宣传册（0905）-解决方案全.pdf"
    ]
    
    # 输出目录
    output_dir = r"I:\pufa-hackathon-ai\data\analysis"
    
    # 分析每个文档
    for pdf_file in pdf_files:
        if not Path(pdf_file).exists():
            logger.warning(f"文件不存在: {pdf_file}")
            continue
        
        logger.info(f"\n{'#'*80}")
        logger.info(f"开始分析: {Path(pdf_file).name}")
        logger.info(f"{'#'*80}\n")
        
        try:
            analyzer = PDFAnalyzer(pdf_file, output_dir)
            manifest = analyzer.analyze_document()
            
            # 打印摘要
            summary = manifest['summary']
            logger.info(f"\n文档摘要:")
            logger.info(f"  总页数: {summary['total_pages']}")
            logger.info(f"  文本总长度: {summary['total_text_length']}")
            logger.info(f"  表格总数: {summary['total_tables']}")
            logger.info(f"  图片总数: {summary['total_images']}")
            logger.info(f"  需要 OCR 页数: {summary['pages_need_ocr']}")
            logger.info(f"  复杂度分布: {summary['complexity_distribution']}")
            
        except Exception as e:
            logger.error(f"分析失败: {e}", exc_info=True)


if __name__ == "__main__":
    main()
