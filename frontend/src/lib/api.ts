/**
 * 统一 API 层
 * 封装所有后端请求，统一错误处理
 */
const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = 'ApiError';
  }
}

function getToken(): string | null {
  try {
    const auth = JSON.parse(localStorage.getItem('qingpu_auth') || 'null');
    return auth?.token || null;
  } catch {
    return null;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    localStorage.removeItem('qingpu_auth');
    window.location.reload();
    throw new ApiError(401, '登录已过期，请重新登录');
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new ApiError(res.status, err.detail || `请求失败 (${res.status})`);
  }

  return res.json();
}

export const api = {
  // 认证
  login: (username: string, password: string) =>
    request<{ token: string; user: any }>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),

  register: (data: { username: string; email: string; password: string; user_type: string; admin_code?: string }) =>
    request<{ token: string; user: any }>('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  me: () => request<{ user: any }>('/api/v1/auth/me'),

  // 会话
  getSessions: () => request<{ sessions: any[] }>('/api/v1/auth/sessions'),
  createSession: (name: string, role: string) =>
    request<{ session: any }>('/api/v1/auth/sessions', {
      method: 'POST',
      body: JSON.stringify({ name, role }),
    }),
  deleteSession: (id: string) =>
    request<void>(`/api/v1/auth/sessions/${id}`, { method: 'DELETE' }),
  updateSessionRole: (id: string, role: string) =>
    request<void>(`/api/v1/auth/sessions/${id}/role`, {
      method: 'PUT',
      body: JSON.stringify({ role, name: '' }),
    }),
  getMessages: (sessionId: string) =>
    request<{ messages: any[] }>(`/api/v1/auth/sessions/${sessionId}/messages`),

  // RAG 问答
  chat: (data: { query: string; role: string; session_id?: string; force_web?: boolean }) =>
    request<any>('/api/v1/rag/chat', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  search: (query: string, topK = 5) =>
    request<any>('/api/v1/rag/search', {
      method: 'POST',
      body: JSON.stringify({ query, top_k: topK }),
    }),

  indexDocument: (filename: string) =>
    request<any>(`/api/v1/rag/index/${encodeURIComponent(filename)}`, { method: 'POST' }),

  // 文档
  listDocuments: () => request<{ documents: any[] }>('/api/v1/documents/list'),
  uploadDocument: (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return request<any>('/api/v1/documents/upload', {
      method: 'POST',
      body: fd,
      headers: {},
    });
  },
  analyzeDocument: (filename: string) =>
    request<any>(`/api/v1/documents/analyze/${encodeURIComponent(filename)}`, { method: 'POST' }),
  getClassified: (filename: string) =>
    request<any>(`/api/v1/documents/classified/${encodeURIComponent(filename)}`),

  // 管理
  adminOverview: () => request<any>('/api/v1/admin/overview'),
  adminUsers: () => request<any>('/api/v1/admin/users'),
  adminLeads: () => request<any>('/api/v1/admin/leads'),
  adminSessionDetail: (sessionId: string) =>
    request<any>(`/api/v1/admin/sessions/${sessionId}`),
  adminDownloadProposal: (sessionId: string) =>
    `${API_BASE}/api/v1/admin/leads/${sessionId}/sales-plan.docx`,
};

export default api;