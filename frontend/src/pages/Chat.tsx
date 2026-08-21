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
  const [selection, setSelection] = useState({
    scene: '', scale: '', pressure: '', purity: '', deployment: '', energy: '',
  });
  const messagesEndRef = useRef<HTMLDivElement>(null);

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

  const handleCompareSubmit = () => {
    if (compareModels.length < 2) {
      message.warning('请至少选择两款产品进行对比');
      return;
    }
    setCompareOpen(false);
    setRole('technical_support');
    handleSend(`请对比以下产品：${compareModels.join('、')}。请使用Markdown表格列出资料中明确的共同参数和差异，并说明各自适用场景、主要差异、选择建议和待确认条件。不得编造缺失参数。`);
  };

  const handleSelectionSubmit = () => {
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
          query,
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
            { value: 'ST100G2', label: 'ST100G2 · 燃料电池电堆' },
            { value: 'ST200G3', label: 'ST200G3 · 燃料电池电堆' },
          ]}
        />
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