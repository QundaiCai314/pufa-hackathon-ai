"""
PDF 表格检测与提取模块
使用 pdfplumber 检测和提取表格结构
"""

import pdfplumber
from pathlib import Path
from typing import List, Dict, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TableDetector:
    """表格检测器"""
    
    def __init__(self, pdf_path: str):
        """
        初始化检测器
        
        Args:
            pdf_path: PDF 文件路径
        """
        self.pdf_path = Path(pdf_path)
        self.doc: Optional[pdfplumber.PDF] = None
    
    def open(self):
        """打开 PDF 文档"""
        try:
            self.doc = pdfplumber.open(self.pdf_path)
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
    
    def detect_tables(self, page_num: int) -> List[Dict]:
        """
        检测页面中的表格
        
        Args:
            page_num: 页码（从 0 开始）
            
        Returns:
            表格列表
        """
        if not self.doc:
            raise ValueError("PDF 文档未打开")
        
        try:
            page = self.doc.pages[page_num]
            tables = page.find_tables()
            
            result = []
            for idx, table in enumerate(tables):
                # 提取表格数据来获取行列数
                try:
                    table_data = table.extract()
                    row_count = len(table_data) if table_data else 0
                    col_count = len(table_data[0]) if table_data and len(table_data) > 0 else 0
                except:
                    row_count = 0
                    col_count = 0
                
                result.append({
                    'table_index': idx,
                    'bbox': table.bbox,
                    'rows': row_count,
                    'cols': col_count
                })
            
            logger.info(f"检测到 {len(result)} 个表格 (页 {page_num + 1})")
            return result
            
        except Exception as e:
            logger.error(f"检测表格失败 (页 {page_num + 1}): {e}")
            return []
    
    def extract_table(self, page_num: int, table_index: int = 0) -> Optional[Dict]:
        """
        提取指定表格的数据
        
        Args:
            page_num: 页码（从 0 开始）
            table_index: 表格索引
            
        Returns:
            表格数据字典
        """
        if not self.doc:
            raise ValueError("PDF 文档未打开")
        
        try:
            page = self.doc.pages[page_num]
            tables = page.find_tables()
            
            if table_index >= len(tables):
                logger.warning(f"表格索引 {table_index} 超出范围")
                return None
            
            table = tables[table_index]
            data = table.extract()
            
            if not data:
                return None
            
            # 提取表头和数据行
            headers = data[0] if data else []
            rows = data[1:] if len(data) > 1 else []
            
            # 转换为字典列表
            table_dict = []
            for row in rows:
                row_dict = {}
                for idx, cell in enumerate(row):
                    header = headers[idx] if idx < len(headers) else f"列{idx+1}"
                    row_dict[header] = cell
                table_dict.append(row_dict)
            
            return {
                'table_index': table_index,
                'bbox': table.bbox,
                'headers': headers,
                'rows': rows,
                'row_count': len(rows),
                'col_count': len(headers),
                'data': table_dict,
                'raw_data': data
            }
            
        except Exception as e:
            logger.error(f"提取表格失败 (页 {page_num + 1}, 表 {table_index}): {e}")
            return None
    
    def extract_all_tables(self, page_num: int) -> List[Dict]:
        """
        提取页面中的所有表格
        
        Args:
            page_num: 页码（从 0 开始）
            
        Returns:
            表格数据列表
        """
        if not self.doc:
            raise ValueError("PDF 文档未打开")
        
        try:
            page = self.doc.pages[page_num]
            tables = page.find_tables()
            
            result = []
            for idx in range(len(tables)):
                table_data = self.extract_table(page_num, idx)
                if table_data:
                    result.append(table_data)
            
            logger.info(f"提取了 {len(result)} 个表格 (页 {page_num + 1})")
            return result
            
        except Exception as e:
            logger.error(f"提取所有表格失败 (页 {page_num + 1}): {e}")
            return []
    
    def analyze_table_structure(self, page_num: int) -> Dict:
        """
        分析页面表格结构
        
        Args:
            page_num: 页码（从 0 开始）
            
        Returns:
            表格分析结果
        """
        tables = self.detect_tables(page_num)
        
        total_cells = 0
        for table in tables:
            total_cells += table['rows'] * table['cols']
        
        return {
            'page_num': page_num + 1,
            'table_count': len(tables),
            'total_cells': total_cells,
            'has_tables': len(tables) > 0,
            'tables': tables
        }
    
    def estimate_table_quality(self, table_data: Dict) -> Dict:
        """
        评估表格数据质量
        
        Args:
            table_data: 表格数据
            
        Returns:
            质量评估结果
        """
        if not table_data:
            return {
                'quality': 'none',
                'confidence': 0.0,
                'issues': ['表格数据为空']
            }
        
        issues = []
        
        # 检查空单元格比例
        total_cells = table_data['row_count'] * table_data['col_count']
        empty_cells = 0
        
        for row in table_data['rows']:
            for cell in row:
                if not cell or str(cell).strip() == '':
                    empty_cells += 1
        
        empty_ratio = empty_cells / total_cells if total_cells > 0 else 0
        
        if empty_ratio > 0.5:
            issues.append(f'空单元格比例过高: {empty_ratio:.1%}')
        
        # 检查表头质量
        if not table_data['headers'] or all(not h for h in table_data['headers']):
            issues.append('缺少表头')
        
        # 评估置信度
        confidence = 1.0 - empty_ratio * 0.5
        
        if issues:
            quality = 'low' if confidence < 0.5 else 'medium'
        else:
            quality = 'high'
        
        return {
            'quality': quality,
            'confidence': confidence,
            'empty_ratio': empty_ratio,
            'issues': issues
        }


if __name__ == "__main__":
    # 测试代码
    test_pdf = r"C:\Users\34515\.astrbot\data\attachments\02（已压缩）氢璞2025宣传册（0905）-解决方案全.pdf"
    
    with TableDetector(test_pdf) as detector:
        # 检测第一页表格
        for page_num in range(min(5, len(detector.doc.pages))):
            analysis = detector.analyze_table_structure(page_num)
            print(f"\n页 {analysis['page_num']}: {analysis['table_count']} 个表格")
            
            if analysis['has_tables']:
                # 提取表格数据
                tables = detector.extract_all_tables(page_num)
                for table in tables:
                    print(f"  表 {table['table_index']}: {table['row_count']} 行 x {table['col_count']} 列")
                    quality = detector.estimate_table_quality(table)
                    print(f"    质量: {quality['quality']} (置信度: {quality['confidence']:.2f})")
                    if quality['issues']:
                        print(f"    问题: {quality['issues']}")
