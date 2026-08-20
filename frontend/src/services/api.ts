import axios from 'axios';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 600000,
});

export interface DocumentInfo {
  filename: string;
  file_size: number;
  parsed: boolean;
}

export interface ProductSpec {
  model: string;
  category: string;
  specs: Record<string, string>;
  page: number;
}

export interface ProductGroup {
  category_name: string;
  category_page: number;
  en_name: string;
  features: string[];
  intro_products: ProductSpec[];
  spec_products: ProductSpec[];
  spec_page: number | null;
}

export interface ProductImage {
  page: number;
  index: number;
  width: number;
  height: number;
  description: string;
  url: string;
}

// === 宣传册类型 ===
export interface BrochureImage {
  type: string;
  type_label: string;
  description: string;
  page: number;
  index?: number;
  width?: number;
  height?: number;
  has_file?: boolean;
  url?: string;
}

export interface BrochureSubsection {
  type: 'heading' | 'paragraph';
  content: string;
}

export interface BrochureSection {
  page_num: number;
  title: string;
  page_type: string;
  page_type_label: string;
  subsections: BrochureSubsection[];
  list_items: string[];
  captions: string[];
  images_by_type: Record<string, BrochureImage[]>;
  all_images: BrochureImage[];
  image_count: number;
  raw_text: string;
}

export interface ClassifiedContent {
  doc_type?: string;  // 'brochure' or undefined (product catalog)
  // product catalog fields
  product_groups?: ProductGroup[];
  // brochure fields
  sections?: BrochureSection[];
  // shared fields
  documents?: Array<{ page: number; page_title: string; page_type: string; raw_text: string }>;
  tables?: Array<{ title: string; headers: string[]; rows: string[][]; page: number }>;
  product_images?: ProductImage[];
  contact_info?: { address?: string; phone?: string; website?: string; email?: string } | null;
  summary?: { total_pages?: number; total_tokens?: number; total_images?: number; image_type_stats?: Record<string, number> };
}

export const documentApi = {
  upload: async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const resp = await api.post('/api/v1/documents/upload', formData);
    return resp.data;
  },

  parse: async (filename: string, parseMode: string = 'auto') => {
    const resp = await api.post('/api/v1/documents/parse', null, {
      params: { filename, parse_mode: parseMode },
    });
    return resp.data;
  },

  list: async () => {
    const resp = await api.get('/api/v1/documents/list');
    return resp.data;
  },

  // GPT-5.6 Luna 多模态分析
  analyze: async (filename: string, pageCount?: number) => {
    const resp = await api.post(`/api/v1/documents/analyze/${encodeURIComponent(filename)}`, null, {
      params: pageCount ? { page_count: pageCount } : {},
    });
    return resp.data;
  },

  getAnalysisStatus: async (filename: string) => {
    const resp = await api.get(`/api/v1/documents/analysis_status/${encodeURIComponent(filename)}`);
    return resp.data;
  },

  getClassified: async (filename: string): Promise<ClassifiedContent> => {
    const resp = await api.get(`/api/v1/documents/classified/${encodeURIComponent(filename)}`);
    return resp.data;
  },

  // 旧版 MinerU content API（保留兼容）
  getContent: async (filename: string, params?: {
    category?: string;
    page?: number;
    min_length?: number;
  }) => {
    const resp = await api.get(`/api/v1/documents/content/${encodeURIComponent(filename)}`, {
      params,
    });
    const data = resp.data;
    data.items = (data.items || []).map((item: any) => {
      if (item.img_url && item.img_url.startsWith('/')) {
        item.img_url = `${API_BASE}${item.img_url}`;
      }
      return item;
    });
    return data;
  },

  imageUrl: (filename: string, imgPath: string) => {
    return `${API_BASE}/api/v1/documents/image/${encodeURIComponent(filename)}?path=${encodeURIComponent(imgPath)}`;
  },

  // === RAG 语义搜索 ===
  ragSearch: async (query: string, topK: number = 5, doc?: string) => {
    const resp = await api.post('/api/v1/rag/search', {
      query,
      top_k: topK,
      doc,
    });
    return resp.data;
  },

  // === 索引管理 ===
  ragIndex: async (filename: string) => {
    const resp = await api.post(`/api/v1/rag/index/${encodeURIComponent(filename)}`);
    return resp.data;
  },

  ragStats: async () => {
    const resp = await api.get('/api/v1/rag/stats');
    return resp.data;
  },

  ragDeleteIndex: async (filename: string) => {
    const resp = await api.delete(`/api/v1/rag/index/${encodeURIComponent(filename)}`);
    return resp.data;
  },
};
