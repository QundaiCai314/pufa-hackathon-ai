import React, { useState, useEffect, useRef } from 'react';
import {
  Input, Button, List, Tag, Typography, Spin, Empty, Space, Image, Modal,
  Drawer, Popconfirm, Select, Card, Tooltip, App as AntApp,
} from 'antd';
import {
  PlusOutlined, DeleteOutlined, HistoryOutlined, GlobalOutlined, ArrowUpOutlined,
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const { TextArea } = Input;

const API = process.env.REACT_APP_API_URL || 'http://localhost:8000';

interface SearchResult {
  score: number;
  text: string;
  doc: string;
  page: number;
  type: string;
  category: string;
  case_name: string;
  source: string;
  table_headers?: string[];
  table_rows?: string[][];
  table_title?: string;
}

interface WebSource {
  title: string;
  url: string;
  snippet?: string;
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  answer?: string;
  results?: SearchResult[];
  timestamp: Date;
  followups?: string[];
  web_sources?: WebSource[];
  no_result?: boolean;
  web_available?: boolean;
}

interface ChatSession {
  id: string;
  session_name: string;
  assistant_role?: string;
  created_at: string;
  updated_at: string;
}

const ROLE_OPTIONS = [
  { value: 'customer_service', label: '智能客服' },
  { value: 'sales', label: '金牌销售' },
  { value: 'technical_support', label: '技术专家' },
];

export default function Chat({ auth, preset, clearPreset }: { auth: any; preset?: string; clearPreset?: () => void }) {
  const { message } = AntApp.useApp();
  const token = auth?.token;
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [role, setRole] = useState('customer_service');
  const [selectionOpen, setSelectionOpen] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);
  const [compareModels, setCompareModels] = useState<string[]>(['CESP250', 'CESP500']);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailModel, setDetailModel] = useState('');
  const [detailResults, setDetailResults] = useState<SearchResult[]>([]);
  const [latestProposal, setLatestProposal] = useState<{ id: string; version_no: number; title: string } | null>(null);
  const [exportingProposal, setExportingProposal] = useState(false);
  const [selection, setSelection] = useState({
    scene: '', scale: '', pressure: '', purity: '', deployment: '', energy: '',
  });
  const [profile, setProfile] = useState<Record<string, string>>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const profileRequiredFields = ['应用场景', '目标规模', '压力要求', '部署方式', '能源来源'];
  const profileLabels: Record<string, string> = {
    '应用场景': '应用场景', '目标规模': '目标规模', '压力要求': '压力要求',
    '纯度要求': '纯度要求', '部署方式': '部署方式', '能源来源': '能源来源',
  };
  const profileMissing = profileRequiredFields.filter(field => !profile[field]);

  const authHeaders = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  const loadSessions = async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API}/api/v1/auth/sessions`, { headers: authHeaders });
      if (!res.ok) return;
      const data = await res.json();
      setSessions(data.sessions || []);
      if (!sessionId && data.length > 0) {
        loadSession(data[0].id);
      }
    } catch {
      // 忽略后台加载错误
    }
  };

  const createSession = async (roleName = role) => {
    if (!token) return null;
    try {
      const res = await fetch(`${API}/api/v1/auth/sessions`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({ session_name: '新对话', assistant_role: roleName }),
      });
      if (!res.ok) return null;
      const data = await res.json();
      const s = data.session;
      setSessions((prev) => [s, ...prev]);
      setSessionId(s.id);
      setRole(s.assistant_role || 'customer_service');
      setMessages([]);
      return s.id;
    } catch {
      return null;
    }
  };

  const loadSession = async (id: string) => {
    if (!token) return;
    try {
      const res = await fetch(`${API}/api/v1/auth/sessions/${id}`, { headers: authHeaders });
      if (!res.ok) return;
      const s = await res.json();
      setSessionId(s.id);
      setRole(s.assistant_role || 'customer_service');
      const hist = (s.messages || []).map((m: any) => ({
        id: m.id || String(Math.random()),
        role: m.role,
        content: m.content,
        answer: m.role === 'assistant' ? m.content : undefined,
        timestamp: new Date(m.created_at || Date.now()),
      }));
      setMessages(hist);
      setHistoryOpen(false);
    } catch {
      // 忽略
    }
  };

  const deleteSession = async (id: string) => {
    if (!token) return;
    try {
      await fetch(`${API}/api/v1/auth/sessions/${id}`, { method: 'DELETE', headers: authHeaders });
      const next = sessions.filter((s) => s.id !== id);
      setSessions(next);
      if (sessionId === id) {
        if (next.length > 0) {
          loadSession(next[0].id);
        } else {
          setSessionId(null);
          setMessages([]);
        }
      }
      message.success('已删除对话');
    } catch {
      message.error('删除失败');
    }
  };

  useEffect(() => {
    loadSessions();
  }, [token]);

  useEffect(() => {
    if (preset) {
      setInput(preset);
      if (clearPreset) clearPreset();
    }
  }, [preset]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleAddToCompare = (model: string) => {
    setCompareModels(prev => prev.includes(model) ? prev : [...prev, model]);
    message.success(`${model} 已加入对比`);
    setCompareOpen(true);
  };

  const openSourceDocument = (result: SearchResult) => {
    if (!result.doc) {
      message.info('当前结果没有可定位的原始文档名称');
      return;
    }
    const filename = result.doc.toLowerCase().endsWith('.pdf') ? result.doc : `${result.doc}.pdf`;
    window.open(`${API}/api/v1/documents/file/${encodeURIComponent(filename)}#page=${result.page || 1}`, '_blank', 'noopener,noreferrer');
  };

  const saveProposal = async () => {
    if (!sessionId || !messages.length || exportingProposal) { message.warning('请先生成一份方案或完成一次对话'); return; }
    const assistant = [...messages].reverse().find(m => m.role === 'assistant');
    if (!assistant) { message.warning('请先生成方案内容'); return; }
    setExportingProposal(true);
    try {
      const res = await fetch(`${API}/api/v1/auth/sessions/${sessionId}/proposals`, { method: 'POST', headers: authHeaders, body: JSON.stringify({ title: `项目技术方案-${new Date().toLocaleDateString()}`, profile, content: assistant.content, results: assistant.results || [] }) });
      if (!res.ok) throw new Error('保存失败');
      const data = await res.json(); setLatestProposal(data.proposal); message.success(`方案 V${data.proposal.version_no} 已保存，可导出 Word、PDF 或 Excel`);
    } catch { message.error('方案保存失败，请稍后重试'); } finally { setExportingProposal(false); }
  };

  const downloadProposal = async (format: 'docx' | 'pdf' | 'xlsx') => {
    if (!sessionId || !latestProposal) { message.info('请先保存方案版本'); return; }
    const res = await fetch(`${API}/api/v1/auth/sessions/${sessionId}/proposals/${latestProposal.id}/${format}`, { headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) } });
    if (!res.ok) { message.error('导出失败'); return; }
    const blob = await res.blob(); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href=url; a.download=`proposal_v${latestProposal.version_no}.${format}`; a.click(); URL.revokeObjectURL(url);
  };

  const openProductDetail = (model: string, results?: SearchResult[]) => {
    setDetailModel(model);
    setDetailResults((results || []).filter(r => r.text.toUpperCase().includes(model.toUpperCase())));
    setDetailOpen(true);
  };

  const getProductModels = (results?: SearchResult[]) => {
    const models = new Set<string>();
    (results || []).forEach(r => {
      const found = r.text.match(/(?:ST\d+[A-Z0-9]*|CESP\d+|E\d+)/gi) || [];
      found.forEach(model => models.add(model.toUpperCase()));
    });
    return Array.from(models).slice(0, 6);
  };

  const handleGeneratePlan = () => {
    if (!Object.keys(profile).length) {
      message.warning('请先通过智能选型填写项目需求');
      setSelectionOpen(true);
      return;
    }
    setRole('sales');
    const profileText = Object.entries(profile).map(([k, v]) => `${k}=${v}`).join('；');
    handleSend(`请基于以下项目需求生成一份技术方案初稿：${profileText}。请按“项目概述、需求理解、推荐产品、核心参数、系统配置建议、适用条件、风险与待确认事项、下一步计划”输出。只使用企业资料中明确的信息，缺失内容必须标注“待确认”，不得编造价格、交付周期、认证或性能承诺。`);
  };

  const handleRiskCheck = () => {
    if (!Object.keys(profile).length) {
      message.warning('请先通过智能选型填写项目需求');
      setSelectionOpen(true);
      return;
    }
    setRole('technical_support');
    const profileText = Object.entries(profile).map(([k, v]) => `${k}=${v}`).join('；');
    handleSend(`请审查以下项目需求的技术风险和缺失条件：${profileText}。请按“已满足条件、潜在风险、必须确认的信息、建议下一步”输出。只依据企业资料，不能编造参数或安全结论。`);
  };

  const compareCategory = (model: string) => {
    if (model.startsWith('CESP')) return 'PEM制氢系统';
    if (model.startsWith('OCEAN')) return '船用燃料电池系统';
    if (model.startsWith('E')) return '燃料电池系统';
    return '燃料电池电堆';
  };

  const compareCategories = Array.from(new Set(compareModels.map(compareCategory)));
  const handleCompareSubmit = () => {
    if (compareModels.length < 2) {
      message.warning('请至少选择两款产品进行对比');
      return;
    }
    if (compareCategories.length > 1) {
      message.info('已选择不同产品类别，AI 将分开说明参数差异，不会将它们视为同类产品替代。');
    }
    setCompareOpen(false);
    setRole('technical_support');
    handleSend(`请对比以下产品：${compareModels.join('、')}。请使用Markdown表格列出资料中明确的共同参数和差异，并说明各自适用场景、主要差异、选择建议和待确认条件。不得编造缺失参数。`);
  };

  const handleSelectionSubmit = () => {
    const profileData: Record<string, string> = {};
    if (selection.scene) profileData['应用场景'] = selection.scene;
    if (selection.scale) profileData['目标规模'] = selection.scale;
    if (selection.pressure) profileData['压力要求'] = selection.pressure;
    if (selection.purity) profileData['纯度要求'] = selection.purity;
    if (selection.deployment) profileData['部署方式'] = selection.deployment;
    if (selection.energy) profileData['能源来源'] = selection.energy;
    setProfile(prev => ({ ...prev, ...profileData }));

    const details = [
      selection.scene && `应用场景：${selection.scene}`,
      selection.scale && `目标规模：${selection.scale}`,
      selection.pressure && `用氢/出口压力：${selection.pressure}`,
      selection.purity && `氢气纯度要求：${selection.purity}`,
      selection.deployment && `部署方式：${selection.deployment}`,
      selection.energy && `能源来源：${selection.energy}`,
    ].filter(Boolean).join('；');
    if (!details) {
      message.warning('请至少填写应用场景或目标规模');
      return;
    }
    setSelectionOpen(false);
    setRole('sales');
    handleSend(`请根据以下项目需求进行产品选型，并给出需求画像、推荐结论、匹配依据、待确认条件和下一步建议：${details}`);
  };

  const handleSend = async (forcedQuery?: string, forceWeb = false) => {
    const query = (forcedQuery || input).trim();
    if (!query || loading) return;
    const profileContext = Object.keys(profile).length > 0
      ? `【当前项目需求画像：${Object.entries(profile).map(([k, v]) => `${k}=${v}`).join('；')}】`
      : '';
    const requestQuery = profileContext && !query.includes('当前项目需求画像')
      ? `${profileContext}
${query}`
      : query;

    let activeSessionId = sessionId;
    if (!activeSessionId) {
      activeSessionId = await createSession();
      if (!activeSessionId) return;
    }

    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: query,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!forcedQuery) setInput('');
    setLoading(true);

    try {
      const resp = await fetch(`${API}/api/v1/rag/chat`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({
          query: requestQuery,
          role,
          session_id: activeSessionId,
          force_web: forceWeb,
        }),
      });

      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.detail || '请求失败');
      }

      const data = await resp.json();
      const botMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: data.answer || '',
        answer: data.answer || '',
        results: data.results || [],
        timestamp: new Date(),
        followups: data.followups || [],
        web_sources: data.web_sources || [],
        no_result: !!data.no_result,
        web_available: !!data.web_available,
      };

      setMessages((prev) => [...prev, botMsg]);
      // 首轮问答后，后端自动生成标题，刷新会话列表
      if (messages.filter((m) => m.role === 'user').length <= 1) {
        loadSessions();
      }
    } catch (e: any) {
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: `请求出错: ${e.message || '网络连接异常'}`,
          timestamp: new Date(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleRoleChange = async (nextRole: string) => {
    setRole(nextRole);
    if (sessionId) {
      try {
        await fetch(`${API}/api/v1/auth/sessions/${sessionId}/role`, {
          method: 'PUT',
          headers: authHeaders,
          body: JSON.stringify({ role: nextRole, name: '' }),
        });
      } catch {
        // 忽略
      }
    }
  };

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', height: '100vh',
      background: '#fbfbf7', position: 'relative',
    }}>
      {/* 顶栏 */}
      <div style={{
        padding: '12px 24px', borderBottom: '1px solid #ecece4',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        background: '#fbfbf7', zIndex: 10,
      }}>
        <Space size={12}>
          <Select
            value={role}
            onChange={handleRoleChange}
            options={ROLE_OPTIONS}
            style={{ width: 120 }}
            variant="borderless"
          />
          {sessionId && (
            <span style={{ fontSize: 13, color: '#9c9b96' }}>
              当前会话
            </span>
          )}
        </Space>

        <Space size={8}>
          <Button size="small" onClick={saveProposal} loading={exportingProposal}>保存方案版本</Button>
          {latestProposal && <>
            <Button size="small" onClick={() => downloadProposal('docx')}>Word</Button>
            <Button size="small" onClick={() => downloadProposal('pdf')}>PDF</Button>
            <Button size="small" onClick={() => downloadProposal('xlsx')}>Excel</Button>
          </>}
          <Button
            type="text" icon={<HistoryOutlined />}
            onClick={() => setHistoryOpen(true)}
          >
            历史记录 ({sessions.length})
          </Button>
          <Button
            type="text" icon={<PlusOutlined />}
            onClick={() => createSession()}
          >
            新建
          </Button>
        </Space>
      </div>

      {/* 项目需求画像 */}
      {Object.keys(profile).length > 0 && (
        <div style={{
          margin: '0 auto 12px', maxWidth: 800, padding: '10px 14px',
          background: '#fffdf5', border: '1px solid #f0e6b8', borderRadius: 10,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 7 }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: '#7c5d15' }}>当前项目需求画像</span>
            <Space size={10}>
              <Button type="text" size="small" onClick={handleGeneratePlan} style={{ fontSize: 11, color: '#166534', padding: 0 }}>
                生成方案
              </Button>
              <Button type="text" size="small" onClick={handleRiskCheck} style={{ fontSize: 11, color: '#8a6511', padding: 0 }}>
                风险检查
              </Button>
              <Button type="text" size="small" onClick={() => setProfile({})} style={{ fontSize: 11, color: '#a18a52', padding: 0 }}>
                清除
              </Button>
            </Space>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {Object.entries(profile).map(([key, value]) => (
              <span key={key} style={{ fontSize: 11, color: '#6b5a2a', background: '#fff8d9', borderRadius: 5, padding: '4px 8px' }}>
                {key}：{value}
              </span>
            ))}
          </div>
          <div style={{ marginTop: 7, fontSize: 11, color: '#a18a52' }}>
            AI 会结合这份画像进行后续产品推荐与方案分析
          </div>
          <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ flex: 1, height: 5, borderRadius: 4, background: '#f1e8bd', overflow: 'hidden' }}>
              <div style={{ width: `${Math.round(((profileRequiredFields.length - profileMissing.length) / profileRequiredFields.length) * 100)}%`, height: '100%', background: '#c89524', borderRadius: 4 }} />
            </div>
            <span style={{ fontSize: 10, color: '#8c722d', whiteSpace: 'nowrap' }}>
              信息完整度 {Math.round(((profileRequiredFields.length - profileMissing.length) / profileRequiredFields.length) * 100)}%
            </span>
          </div>
          {profileMissing.length > 0 && (
            <div style={{ marginTop: 6, fontSize: 11, color: '#9a7b32' }}>
              建议补充：{profileMissing.map(field => profileLabels[field]).join('、')}
            </div>
          )}
        </div>
      )}

      {/* 消息滚动区 */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '32px 24px 140px' }}>
        <div style={{ maxWidth: 800, margin: '0 auto' }}>
          {messages.length === 0 && (
            <div style={{ textAlign: 'center', padding: '80px 0 40px' }}>
              <div style={{
                width: 44, height: 44, borderRadius: 12, background: '#111',
                color: '#fff', display: 'grid', placeItems: 'center', margin: '0 auto 16px',
                fontSize: 20, fontWeight: 700,
              }}>氢</div>
              <h2 style={{ fontSize: 24, fontWeight: 600, margin: 0, marginBottom: 8, letterSpacing: -0.5 }}>
                企业知识与智能销售助手
              </h2>
              <p style={{ color: '#7a7973', fontSize: 14, margin: 0 }}>
                随时询问氢璞产品、电堆技术参数、工况、应用场景或寻求销售方案。
              </p>
            </div>
          )}

          {messages.map((m) => (
            <div key={m.id} style={{ marginBottom: 28 }}>
              {m.role === 'user' ? (
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
                  <div style={{
                    background: '#f0eee6', padding: '10px 16px', borderRadius: 16,
                    maxWidth: '80%', fontSize: 15, lineHeight: 1.5, color: '#191919',
                  }}>
                    {m.content}
                  </div>
                </div>
              ) : (
                <div>
                  {/* 答案正文 */}
                  <div className="ppx-markdown" style={{
                    background: '#fff', border: '1px solid #ecece4', borderRadius: 14,
                    padding: '20px 24px',
                  }}>
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {m.content}
                    </ReactMarkdown>

                    {/* 回答依据摘要 */}
                    {((m.results && m.results.length > 0) || (m.web_sources && m.web_sources.length > 0)) && (
                      <div style={{
                        marginTop: 16, paddingTop: 12, borderTop: '1px solid #f0eee6',
                        display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8,
                      }}>
                        <span style={{ fontSize: 11, color: '#6b7280' }}>回答依据</span>
                        {m.results && m.results.length > 0 && <Tag style={{ margin: 0, fontSize: 11, color: '#166534', background: '#f0fdf4', borderColor: '#bbf7d0' }}>
                          企业资料 · {m.results.length} 条
                        </Tag>}
                        {m.web_sources && m.web_sources.length > 0 && <Tag style={{ margin: 0, fontSize: 11, color: '#9a3412', background: '#fff7ed', borderColor: '#fed7aa' }}>
                          公开网页 · {m.web_sources.length} 条
                        </Tag>}
                        {m.results && m.results.some(r => r.source) && (
                          <Tag style={{ margin: 0, fontSize: 11, color: '#1d4ed8', background: '#eff6ff', borderColor: '#bfdbfe' }}>
                            图片资料 · {m.results.filter(r => r.source).length} 张
                          </Tag>
                        )}
                        {m.results && <span style={{ fontSize: 11, color: '#9c9b96' }}>
                          {Array.from(new Set(m.results.map(r => r.doc).filter(Boolean))).slice(0, 2).join('、')}
                        </span>}
                        {m.web_sources && m.web_sources.length > 0 && (!m.results || m.results.length === 0) && (
                          <span style={{ fontSize: 11, color: '#9c9b96' }}>公开信息可能随时间变化，请以原始网页为准</span>
                        )}
                      </div>
                    )}

                    {/* 无结果降级建议卡 */}
                    {m.no_result && (
                      <div style={{
                        marginTop: 16, paddingTop: 14, borderTop: '1px solid #f0eee6',
                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      }}>
                        <div style={{ fontSize: 13, color: '#7a7973' }}>
                          资料库暂无完全匹配内容。需要扩大搜索吗？
                        </div>
                        <Button
                          size="small" icon={<GlobalOutlined />}
                          onClick={() => handleSend(messages[messages.indexOf(m) - 1]?.content, true)}
                        >
                          联网检索
                        </Button>
                      </div>
                    )}
                  </div>

                  {/* 产品快捷卡片 */}
                  {getProductModels(m.results).length > 0 && (
                    <div style={{ marginTop: 12 }}>
                      <div style={{ fontSize: 11, color: '#9c9b96', marginBottom: 6 }}>
                        本轮识别的产品
                      </div>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        {getProductModels(m.results).map(model => (
                          <div key={model} style={{
                            minWidth: 142, padding: '10px 12px', borderRadius: 9,
                            background: '#fff', border: '1px solid #dbeafe',
                          }}>
                            <div
                              onClick={() => openProductDetail(model, m.results)}
                              style={{ fontWeight: 650, fontSize: 13, color: '#1e3a5f', cursor: 'pointer' }}
                            >{model}</div>
                            <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>
                              {model.startsWith('CESP') ? 'PEM制氢系统' : model.startsWith('ST') ? '燃料电池电堆' : '燃料电池系统'}
                            </div>
                            <Space size={8}>
                              <Button
                                type="link" size="small" style={{ padding: 0, height: 18, fontSize: 11, color: '#2563eb' }}
                                onClick={() => openProductDetail(model, m.results)}
                              >
                                查看详情
                              </Button>
                              <Button
                                type="link" size="small" style={{ padding: 0, height: 18, fontSize: 11, color: '#2563eb' }}
                                onClick={() => handleAddToCompare(model)}
                              >
                                加入对比
                              </Button>
                            </Space>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 相关产品图片：仅展示检索结果中的图片来源 */}
                  {m.results && m.results.some(r => r.source) && (
                    <div style={{ marginTop: 12 }}>
                      <div style={{ fontSize: 11, color: '#9c9b96', marginBottom: 6 }}>
                        相关产品图片
                      </div>
                      <Image.PreviewGroup>
                        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                          {m.results.filter(r => r.source).slice(0, 4).map((r, i) => {
                            const imageUrl = r.source.startsWith('http') ? r.source : `${API}${r.source}`;
                            return (
                              <Image
                                key={i}
                                src={imageUrl}
                                alt={r.text || '相关产品图片'}
                                width={120}
                                height={82}
                                preview={{ mask: '查看大图' }}
                                style={{ objectFit: 'cover', borderRadius: 8, border: '1px solid #e5e7eb' }}
                              />
                            );
                          })}
                        </div>
                      </Image.PreviewGroup>
                    </div>
                  )}

                  {/* 知识库来源 - 缩小版 */}
                  {m.results && m.results.length > 0 && (
                    <div style={{ marginTop: 10 }}>
                      <div style={{ fontSize: 11, color: '#9c9b96', marginBottom: 6 }}>
                        参考资料 ({m.results.length})
                      </div>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        {m.results.slice(0, 4).map((r, i) => (
                          <div key={i} style={{
                            background: '#f8f9fa', borderRadius: 6, padding: '6px 10px',
                            fontSize: 11, color: '#6b7280', maxWidth: 180,
                            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                          }}>
                            {r.doc || '资料'} · P{r.page}
                          </div>
                        ))}
                        {m.results.length > 4 && (
                          <div style={{
                            background: '#f8f9fa', borderRadius: 6, padding: '6px 10px',
                            fontSize: 11, color: '#9c9b96',
                          }}>
                            +{m.results.length - 4}
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* 联网来源 - 缩小版 */}
                  {m.web_sources && m.web_sources.length > 0 && (
                    <div style={{ marginTop: 10 }}>
                      <div style={{ fontSize: 11, color: '#9c9b96', marginBottom: 6 }}>
                        联网来源
                      </div>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        {m.web_sources.slice(0, 3).map((w, i) => (
                          <a
                            key={i} href={w.url} target="_blank" rel="noreferrer"
                            style={{
                              background: '#eff6ff', borderRadius: 6, padding: '6px 10px',
                              fontSize: 11, color: '#2563eb', maxWidth: 180,
                              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                              textDecoration: 'none',
                            }}
                          >
                            {w.title}
                          </a>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 推荐追问 - 突出样式 */}
                  {m.followups && m.followups.length > 0 && (
                    <div style={{ marginTop: 16 }}>
                      <div style={{ fontSize: 12, color: '#9c9b96', marginBottom: 10 }}>
                        继续提问
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                        {m.followups.map((f, i) => (
                          <div
                            key={i}
                            onClick={() => handleSend(f)}
                            style={{
                              background: 'linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%)',
                              border: '1px solid #bbf7d0',
                              borderRadius: 10,
                              padding: '12px 16px',
                              fontSize: 13,
                              color: '#166534',
                              cursor: 'pointer',
                              transition: 'all 0.2s',
                              display: 'flex',
                              alignItems: 'center',
                              gap: 8,
                            }}
                            onMouseEnter={(e) => {
                              e.currentTarget.style.background = 'linear-gradient(135deg, #dcfce7 0%, #d1fae5 100%)';
                              e.currentTarget.style.borderColor = '#86efac';
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.background = 'linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%)';
                              e.currentTarget.style.borderColor = '#bbf7d0';
                            }}
                          >
                            <span style={{ color: '#10b981', fontSize: 14 }}>→</span>
                            {f}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div style={{
              background: '#fff', border: '1px solid #ecece4', borderRadius: 14,
              padding: '20px 24px', display: 'flex', alignItems: 'center', gap: 12,
            }}>
              <Spin size="small" />
              <span style={{ fontSize: 14, color: '#7a7973' }}>正在研读资料并组织答案...</span>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* 底部悬浮输入框 */}
      <div className="ppx-input-wrapper">
        <TextArea
          className="ppx-input-textarea"
          placeholder="询问产品性能、选型建议、电堆功率..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          autoSize={{ minRows: 1, maxRows: 4 }}
        />
        <div className="ppx-input-actions">
          <Space size={8}>
            <Button
              size="small"
              onClick={() => setCompareOpen(true)}
              style={{ borderRadius: 14, borderColor: '#dbeafe', color: '#1d4ed8', background: '#eff6ff' }}
            >
              产品对比
            </Button>
            <Button
              size="small"
              onClick={() => setSelectionOpen(true)}
              style={{ borderRadius: 14, borderColor: '#bbf7d0', color: '#166534', background: '#f0fdf4' }}
            >
              智能选型
            </Button>
            <Tag color="default" style={{ margin: 0, borderRadius: 12, background: '#f0eee6', border: 'none', color: '#5f5e5a' }}>
              {role === 'customer_service' ? '智能客服' : role === 'sales' ? '金牌销售' : '技术专家'}
            </Tag>
          </Space>
          <Button
            type="primary" shape="circle" icon={<ArrowUpOutlined />}
            disabled={!input.trim() || loading}
            onClick={() => handleSend()}
            style={{
              background: '#111', borderColor: '#111', width: 32, height: 32,
            }}
          />
        </div>
      </div>

      {/* 产品参数详情 */}
      <Modal
        title={`${detailModel} · 产品资料详情`}
        open={detailOpen}
        onCancel={() => setDetailOpen(false)}
        footer={<Button onClick={() => handleAddToCompare(detailModel)}>加入对比</Button>}
        width={680}
      >
        <div style={{ color: '#7a7973', fontSize: 12, marginBottom: 12 }}>
          以下内容来自本轮企业知识库检索；字段按原始资料展示。
        </div>
        {detailResults.length === 0 ? (
          <div style={{ color: '#9c9b96', fontSize: 13 }}>本轮未检索到该型号的结构化参数，可通过“加入对比”继续查询。</div>
        ) : detailResults.map((result, i) => (
          <div key={i} style={{ borderTop: i ? '1px solid #f0eee6' : 'none', paddingTop: i ? 12 : 0, marginTop: i ? 12 : 0 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 12, color: '#6b7280', marginBottom: 8 }}>
              <span>{result.doc || '企业资料'} · 第 {result.page} 页</span>
              <Button type="link" size="small" onClick={() => openSourceDocument(result)} style={{ padding: 0, fontSize: 11 }}>
                查看原文
              </Button>
            </div>
            {result.table_headers && result.table_rows && result.table_rows.length > 0 ? (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                  <thead><tr>{result.table_headers.map((header, idx) => <th key={idx} style={{ textAlign: 'left', background: '#f8f9fa', padding: '7px 8px', border: '1px solid #e5e7eb' }}>{header}</th>)}</tr></thead>
                  <tbody>{result.table_rows.map((row, rowIdx) => <tr key={rowIdx}>{row.map((cell, cellIdx) => <td key={cellIdx} style={{ padding: '7px 8px', border: '1px solid #e5e7eb', verticalAlign: 'top' }}>{cell}</td>)}</tr>)}</tbody>
                </table>
              </div>
            ) : (
              <div style={{ whiteSpace: 'pre-wrap', fontSize: 12, lineHeight: 1.7, color: '#374151' }}>{result.text}</div>
            )}
          </div>
        ))}
      </Modal>

      {/* 产品对比表单 */}
      <Modal
        title="产品对比"
        open={compareOpen}
        onCancel={() => setCompareOpen(false)}
        onOk={handleCompareSubmit}
        okText="开始对比"
        cancelText="取消"
      >
        <div style={{ color: '#7a7973', fontSize: 13, marginBottom: 14 }}>
          选择至少两款产品，AI 将从企业资料中提取参数并说明差异。
        </div>
        <Select
          mode="multiple"
          value={compareModels}
          onChange={setCompareModels}
          style={{ width: '100%' }}
          placeholder="选择产品型号"
          options={[
            { value: 'CESP250', label: 'CESP250 · PEM制氢系统' },
            { value: 'CESP500', label: 'CESP500 · PEM制氢系统' },
            { value: 'CESP1000', label: 'CESP1000 · PEM制氢系统' },
            { value: 'ST35F', label: 'ST35F · 燃料电池电堆' },
            { value: 'ST40F', label: 'ST40F · 燃料电池电堆' },
            { value: 'ST50F', label: 'ST50F · 燃料电池电堆' },
            { value: 'ST70FA', label: 'ST70FA · 燃料电池电堆' },
            { value: 'ST97V', label: 'ST97V · 燃料电池电堆' },
            { value: 'ST100G2', label: 'ST100G2 · 燃料电池电堆' },
            { value: 'ST107V', label: 'ST107V · 燃料电池电堆' },
            { value: 'ST150V', label: 'ST150V · 燃料电池电堆' },
            { value: 'ST200G3', label: 'ST200G3 · 燃料电池电堆' },
            { value: 'ST240VIC', label: 'ST240VIC · 燃料电池电堆' },
            { value: 'ST280VID', label: 'ST280VID · 燃料电池电堆' },
            { value: 'ST300VIC', label: 'ST300VIC · 燃料电池电堆' },
            { value: 'ST490VID', label: 'ST490VID · 燃料电池电堆' },
            { value: 'ST600VIIIA', label: 'ST600VIIIA · 燃料电池电堆' },
            { value: 'ST0D4AII', label: 'ST0D4AII · 燃料电池电堆' },
            { value: 'ST0D8AII', label: 'ST0D8AII · 燃料电池电堆' },
            { value: 'ST1D3AII', label: 'ST1D3AII · 燃料电池电堆' },
            { value: 'ST1D4AII', label: 'ST1D4AII · 燃料电池电堆' },
            { value: 'ST1D6AII', label: 'ST1D6AII · 燃料电池电堆' },
            { value: 'ST2D2AII', label: 'ST2D2AII · 燃料电池电堆' },
            { value: 'E200', label: 'E200 · 燃料电池系统' },
            { value: 'OCEAN100', label: 'OCEAN100 · 船用燃料电池系统' },
            { value: 'OCEAN200', label: 'OCEAN200 · 船用燃料电池系统' },
          ]}
        />
        {compareModels.length > 0 && (
          <div style={{ marginTop: 12, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {compareCategories.map(category => (
              <Tag key={category} style={{ margin: 0, fontSize: 11 }} color={category === 'PEM制氢系统' ? 'green' : 'blue'}>
                {category} · {compareModels.filter(model => compareCategory(model) === category).length} 款
              </Tag>
            ))}
          </div>
        )}
        {compareCategories.length > 1 && (
          <div style={{ marginTop: 10, padding: '8px 10px', background: '#fff7ed', border: '1px solid #fed7aa', borderRadius: 7, color: '#9a3412', fontSize: 11, lineHeight: 1.6 }}>
            当前包含不同产品类别。AI 会分别列出各类产品的明确参数，并说明哪些指标不能直接横向比较。
          </div>
        )}
      </Modal>

      {/* 智能选型表单 */}
      <Modal
        title="智能产品选型"
        open={selectionOpen}
        onCancel={() => setSelectionOpen(false)}
        onOk={handleSelectionSubmit}
        okText="开始选型"
        cancelText="取消"
        width={520}
      >
        <div style={{ color: '#7a7973', fontSize: 13, marginBottom: 16 }}>
          填写项目条件，AI 将自动生成需求画像、推荐产品和待确认信息。至少填写一项即可开始。
        </div>
        <div style={{ display: 'grid', gap: 12 }}>
          <Input
            addonBefore="应用场景"
            placeholder="如：风光制氢、重卡、船舶、分布式发电"
            value={selection.scene}
            onChange={e => setSelection({ ...selection, scene: e.target.value })}
          />
          <Input
            addonBefore="目标规模"
            placeholder="如：500Nm³/h、100kW、1000Nm³/h"
            value={selection.scale}
            onChange={e => setSelection({ ...selection, scale: e.target.value })}
          />
          <Input
            addonBefore="压力要求"
            placeholder="如：3MPag；没有可留空"
            value={selection.pressure}
            onChange={e => setSelection({ ...selection, pressure: e.target.value })}
          />
          <Input
            addonBefore="纯度要求"
            placeholder="如：99.999%；没有可留空"
            value={selection.purity}
            onChange={e => setSelection({ ...selection, purity: e.target.value })}
          />
          <Input
            addonBefore="部署方式"
            placeholder="如：撬装式、集装箱式、车载"
            value={selection.deployment}
            onChange={e => setSelection({ ...selection, deployment: e.target.value })}
          />
          <Input
            addonBefore="能源来源"
            placeholder="如：风电、光伏、电网；没有可留空"
            value={selection.energy}
            onChange={e => setSelection({ ...selection, energy: e.target.value })}
          />
        </div>
      </Modal>

      {/* 历史对话抽屉 */}
      <Drawer
        title="对话历史"
        placement="right"
        onClose={() => setHistoryOpen(false)}
        open={historyOpen}
        width={340}
      >
        <List
          dataSource={sessions}
          renderItem={(s) => (
            <List.Item
              style={{
                cursor: 'pointer', padding: '12px 8px', borderRadius: 8,
                background: s.id === sessionId ? '#f0eee6' : 'transparent',
              }}
              actions={[
                <Popconfirm
                  key="del" title="确定删除此对话？"
                  onConfirm={(e) => { e?.stopPropagation(); deleteSession(s.id); }}
                >
                  <Button type="text" size="small" icon={<DeleteOutlined />} onClick={(e) => e.stopPropagation()} />
                </Popconfirm>,
              ]}
              onClick={() => loadSession(s.id)}
            >
              <List.Item.Meta
                title={<div style={{ fontWeight: 500, fontSize: 14 }}>{s.session_name || '新对话'}</div>}
                description={
                  <div style={{ fontSize: 12, color: '#9c9b96' }}>
                    {new Date(s.updated_at || s.created_at).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                  </div>
                }
              />
            </List.Item>
          )}
        />
      </Drawer>
    </div>
  );
}