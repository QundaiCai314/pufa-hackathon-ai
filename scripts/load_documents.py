"""
PDF 文档加载和向量化脚本
功能：提取 PDF 内容 → 清洗文本 → 分段 → 向量化 → 存入 Qdrant
"""

import os
import re
import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Dict

# LangChain
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import Qdrant
from langchain.docstore.document import Document

# Qdrant
from qdrant_client import QdrantClient


class PDFProcessor:
    """PDF 处理器"""
    
    def __init__(self, data_dir: str = "../data"):
        self.data_dir = Path(data_dir)
        self.raw_dir = self.data_dir / "raw"
        self.processed_dir = self.data_dir / "processed"
        
        # 创建目录
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
    
    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """从 PDF 提取文本"""
        print(f"📄 正在处理: {pdf_path}")
        
        doc = fitz.open(pdf_path)
        text = ""
        
        for page_num, page in enumerate(doc, start=1):
            page_text = page.get_text()
            text += f"\n\n=== 第 {page_num} 页 ===\n\n{page_text}"
        
        doc.close()
        print(f"✅ 提取完成，共 {len(doc)} 页，{len(text)} 字符")
        return text
    
    def clean_text(self, text: str) -> str:
        """清洗文本"""
        # 去除多余空格
        text = re.sub(r'[ \t]+', ' ', text)
        
        # 去除多余换行（保留段落分隔）
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # 去除页码
        text = re.sub(r'第\s*\d+\s*页', '', text)
        text = re.sub(r'Page\s*\d+', '', text)
        
        # 去除特殊符号（保留中文标点）
        # text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s\.\,\!\?\-\(\)\：\；\、\《\》\[\]\/]', '', text)
        
        return text.strip()
    
    def split_text(self, text: str) -> List[Document]:
        """分段"""
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,           # 每段 800 字（考虑中文）
            chunk_overlap=100,        # 重叠 100 字
            length_function=len,
            separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""]
        )
        
        chunks = splitter.split_text(text)
        
        # 转成 LangChain Document 对象
        documents = [
            Document(
                page_content=chunk,
                metadata={"source": "氢璞创能资料", "chunk_id": i}
            )
            for i, chunk in enumerate(chunks)
        ]
        
        print(f"📝 分段完成，共 {len(documents)} 段")
        return documents
    
    def process_all_pdfs(self) -> List[Document]:
        """处理所有 PDF"""
        all_documents = []
        
        # 遍历 raw 目录下的所有 PDF
        pdf_files = list(self.raw_dir.glob("*.pdf"))
        
        if not pdf_files:
            print("⚠️  警告：data/raw/ 目录下没有 PDF 文件")
            print("请把 PDF 文件放到 data/raw/ 目录")
            return []
        
        for pdf_path in pdf_files:
            print(f"\n{'='*50}")
            print(f"处理文件: {pdf_path.name}")
            print(f"{'='*50}")
            
            # 1. 提取文本
            text = self.extract_text_from_pdf(str(pdf_path))
            
            # 2. 清洗
            text = self.clean_text(text)
            
            # 3. 保存清洗后的文本
            output_file = self.processed_dir / f"{pdf_path.stem}.txt"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"💾 保存到: {output_file}")
            
            # 4. 分段
            documents = self.split_text(text)
            
            # 添加文件名到 metadata
            for doc in documents:
                doc.metadata["filename"] = pdf_path.name
            
            all_documents.extend(documents)
        
        return all_documents


def load_to_qdrant(documents: List[Document], collection_name: str = "qingpu_knowledge"):
    """加载到 Qdrant 向量数据库"""
    
    print(f"\n{'='*50}")
    print(f"🚀 开始向量化并存入 Qdrant")
    print(f"{'='*50}")
    
    # 初始化 Embeddings
    print("📡 初始化 OpenAI Embeddings...")
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-large",
        # 如果用国产模型，替换成对应的配置
    )
    
    # 连接 Qdrant
    print("🔌 连接 Qdrant 数据库...")
    client = QdrantClient(host="localhost", port=6333)
    
    # 存储向量
    print(f"💾 存储 {len(documents)} 个文档段落...")
    vectorstore = Qdrant.from_documents(
        documents=documents,
        embedding=embeddings,
        collection_name=collection_name,
        client=client,
    )
    
    print(f"✅ 完成！向量数据库已创建，集合名称: {collection_name}")
    
    return vectorstore


def main():
    """主函数"""
    print("""
    ╔══════════════════════════════════════════════════╗
    ║     氢璞创能 - PDF 文档处理与向量化工具          ║
    ╚══════════════════════════════════════════════════╝
    """)
    
    # 1. 处理 PDF
    processor = PDFProcessor(data_dir="../data")
    documents = processor.process_all_pdfs()
    
    if not documents:
        print("\n❌ 没有处理任何文档，程序退出")
        return
    
    print(f"\n{'='*50}")
    print(f"📊 统计信息")
    print(f"{'='*50}")
    print(f"总文档段落: {len(documents)}")
    print(f"平均段落长度: {sum(len(d.page_content) for d in documents) // len(documents)} 字符")
    
    # 2. 询问是否加载到 Qdrant
    choice = input("\n是否将文档加载到 Qdrant 向量数据库？(y/n): ").strip().lower()
    
    if choice == 'y':
        # 检查环境变量
        if not os.getenv("OPENAI_API_KEY"):
            print("\n⚠️  警告：未设置 OPENAI_API_KEY 环境变量")
            print("请先设置: export OPENAI_API_KEY='your-key'")
            return
        
        load_to_qdrant(documents)
    else:
        print("\n✅ 文本处理完成！文件保存在 data/processed/ 目录")
        print("💡 你可以稍后运行向量化步骤")


if __name__ == "__main__":
    main()
