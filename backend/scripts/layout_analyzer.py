"""
PDF 布局分析模块
分析页面布局，识别内容区域类型
"""

from typing import List, Dict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LayoutAnalyzer:
    """布局分析器"""
    
    @staticmethod
    def analyze_text_blocks(text_blocks: List[Dict], page_width: float, page_height: float) -> Dict:
        """
        分析文本块布局
        
        Args:
            text_blocks: 文本块列表
            page_width: 页面宽度
            page_height: 页面高度
            
        Returns:
            布局分析结果
        """
        if not text_blocks:
            return {
                'block_count': 0,
                'has_title': False,
                'has_footer': False,
                'column_count': 1,
                'text_coverage': 0.0
            }
        
        # 计算文本覆盖率
        total_text_area = sum(block['width'] * block['height'] for block in text_blocks)
        page_area = page_width * page_height
        text_coverage = total_text_area / page_area if page_area > 0 else 0
        
        # 检测标题（通常在页面顶部）
        top_blocks = [b for b in text_blocks if b['bbox'][1] < page_height * 0.2]
        has_title = len(top_blocks) > 0
        
        # 检测页脚（通常在页面底部）
        bottom_blocks = [b for b in text_blocks if b['bbox'][3] > page_height * 0.9]
        has_footer = len(bottom_blocks) > 0
        
        # 检测列数（简单方法：按 X 坐标聚类）
        x_positions = [b['bbox'][0] for b in text_blocks]
        column_count = LayoutAnalyzer._estimate_columns(x_positions, page_width)
        
        return {
            'block_count': len(text_blocks),
            'has_title': has_title,
            'has_footer': has_footer,
            'column_count': column_count,
            'text_coverage': text_coverage,
            'top_block_count': len(top_blocks),
            'bottom_block_count': len(bottom_blocks)
        }
    
    @staticmethod
    def _estimate_columns(x_positions: List[float], page_width: float) -> int:
        """估算列数"""
        if not x_positions:
            return 1
        
        # 按 X 坐标排序
        sorted_x = sorted(set(x_positions))
        
        # 如果所有文本块的 X 坐标相近，认为是单列
        if len(sorted_x) <= 2:
            return 1
        
        # 计算相邻 X 坐标的间隔
        gaps = []
        for i in range(1, len(sorted_x)):
            gap = sorted_x[i] - sorted_x[i-1]
            if gap > page_width * 0.1:  # 大于页面宽度的 10%
                gaps.append(gap)
        
        # 列数 = 大间隔数 + 1
        return len(gaps) + 1 if gaps else 1
    
    @staticmethod
    def classify_content_regions(text_blocks: List[Dict], tables: List[Dict], 
                                images: List[Dict], page_width: float, 
                                page_height: float) -> List[Dict]:
        """
        分类内容区域
        
        Args:
            text_blocks: 文本块列表
            tables: 表格列表
            images: 图片列表
            page_width: 页面宽度
            page_height: 页面高度
            
        Returns:
            内容区域列表
        """
        regions = []
        
        # 添加文本区域
        for block in text_blocks:
            regions.append({
                'type': 'text',
                'bbox': block['bbox'],
                'data': block
            })
        
        # 添加表格区域
        for table in tables:
            regions.append({
                'type': 'table',
                'bbox': table['bbox'],
                'data': table
            })
        
        # 添加图片区域
        for image in images:
            if 'positions' in image:
                for pos in image['positions']:
                    regions.append({
                        'type': 'image',
                        'bbox': pos['bbox'],
                        'data': image
                    })
        
        # 按从上到下、从左到右排序
        regions.sort(key=lambda r: (r['bbox'][1], r['bbox'][0]))
        
        return regions
    
    @staticmethod
    def detect_overlap(bbox1: List[float], bbox2: List[float]) -> bool:
        """
        检测两个区域是否重叠
        
        Args:
            bbox1: [x0, y0, x1, y1]
            bbox2: [x0, y0, x1, y1]
            
        Returns:
            是否重叠
        """
        return not (bbox1[2] < bbox2[0] or  # bbox1 在 bbox2 左侧
                   bbox1[0] > bbox2[2] or  # bbox1 在 bbox2 右侧
                   bbox1[3] < bbox2[1] or  # bbox1 在 bbox2 上方
                   bbox1[1] > bbox2[3])    # bbox1 在 bbox2 下方
    
    @staticmethod
    def merge_nearby_regions(regions: List[Dict], threshold: float = 10.0) -> List[Dict]:
        """
        合并相邻的同类型区域
        
        Args:
            regions: 区域列表
            threshold: 距离阈值
            
        Returns:
            合并后的区域列表
        """
        if not regions:
            return []
        
        merged = []
        current_group = [regions[0]]
        
        for i in range(1, len(regions)):
            current = regions[i]
            prev = regions[i-1]
            
            # 检查是否同类型且距离较近
            if (current['type'] == prev['type'] and 
                current['bbox'][1] - prev['bbox'][3] < threshold):
                current_group.append(current)
            else:
                # 合并当前组
                if len(current_group) == 1:
                    merged.append(current_group[0])
                else:
                    merged.append(LayoutAnalyzer._merge_group(current_group))
                current_group = [current]
        
        # 处理最后一组
        if len(current_group) == 1:
            merged.append(current_group[0])
        else:
            merged.append(LayoutAnalyzer._merge_group(current_group))
        
        return merged
    
    @staticmethod
    def _merge_group(group: List[Dict]) -> Dict:
        """合并一组区域"""
        if not group:
            return None
        
        # 计算合并后的 bbox
        x0 = min(r['bbox'][0] for r in group)
        y0 = min(r['bbox'][1] for r in group)
        x1 = max(r['bbox'][2] for r in group)
        y1 = max(r['bbox'][3] for r in group)
        
        return {
            'type': group[0]['type'],
            'bbox': [x0, y0, x1, y1],
            'data': [r['data'] for r in group]
        }
    
    @staticmethod
    def analyze_page_layout(page_info: Dict) -> Dict:
        """
        完整的页面布局分析
        
        Args:
            page_info: 包含文本块、表格、图片等信息的字典
            
        Returns:
            布局分析结果
        """
        text_blocks = page_info.get('text_blocks', [])
        tables = page_info.get('tables', [])
        images = page_info.get('images', [])
        page_width = page_info.get('page_width', 595)
        page_height = page_info.get('page_height', 842)
        
        # 分析文本布局
        text_analysis = LayoutAnalyzer.analyze_text_blocks(text_blocks, page_width, page_height)
        
        # 分类内容区域
        regions = LayoutAnalyzer.classify_content_regions(
            text_blocks, tables, images, page_width, page_height
        )
        
        # 统计各类型区域数量
        region_counts = {}
        for region in regions:
            region_type = region['type']
            region_counts[region_type] = region_counts.get(region_type, 0) + 1
        
        return {
            'page_num': page_info.get('page_num', 1),
            'page_width': page_width,
            'page_height': page_height,
            'text_analysis': text_analysis,
            'region_counts': region_counts,
            'total_regions': len(regions),
            'regions': regions,
            'complexity': LayoutAnalyzer._calculate_complexity(text_analysis, region_counts)
        }
    
    @staticmethod
    def _calculate_complexity(text_analysis: Dict, region_counts: Dict) -> str:
        """计算页面复杂度"""
        score = 0
        
        # 文本块数量
        block_count = text_analysis.get('block_count', 0)
        if block_count > 10:
            score += 2
        elif block_count > 5:
            score += 1
        
        # 列数
        column_count = text_analysis.get('column_count', 1)
        if column_count > 2:
            score += 2
        elif column_count > 1:
            score += 1
        
        # 表格和图片
        if region_counts.get('table', 0) > 0:
            score += 2
        if region_counts.get('image', 0) > 2:
            score += 2
        elif region_counts.get('image', 0) > 0:
            score += 1
        
        # 分级
        if score >= 6:
            return 'high'
        elif score >= 3:
            return 'medium'
        else:
            return 'low'


if __name__ == "__main__":
    # 测试代码
    sample_page_info = {
        'page_num': 1,
        'page_width': 595,
        'page_height': 842,
        'text_blocks': [
            {'bbox': [50, 50, 500, 100], 'width': 450, 'height': 50, 'text': '标题'},
            {'bbox': [50, 150, 500, 300], 'width': 450, 'height': 150, 'text': '正文'},
        ],
        'tables': [
            {'bbox': [50, 350, 500, 500]}
        ],
        'images': [
            {'positions': [{'bbox': [50, 550, 300, 700]}]}
        ]
    }
    
    result = LayoutAnalyzer.analyze_page_layout(sample_page_info)
    print(f"页面复杂度: {result['complexity']}")
    print(f"文本覆盖率: {result['text_analysis']['text_coverage']:.2%}")
    print(f"区域统计: {result['region_counts']}")
    print(f"总区域数: {result['total_regions']}")
