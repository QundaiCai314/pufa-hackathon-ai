import React, { useState, useEffect, useRef } from 'react';
import {
  Input, Button, List, Tag, Typography, Spin, Empty, Space, Image,
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
                  {/* 知识库来源 (Perplexity 来源卡片行) */}
                  {m.results && m.results.length > 0 && (
                    <div style={{ marginBottom: 14 }}>
                      <div style={{ fontSize: 12, color: '#9c9b96', marginBottom: 8, fontWeight: 500 }}>
                        参考资料 ({m.results.length})
                      </div>
                      <div className="ppx-sources-row">
                        {m.results.map((r, i) => (
                          <div key={i} className="ppx-source-card">
                            <div style={{ fontWeight: 600, color: '#111', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {r.doc || '资料片段'}
                            </div>
                            <div style={{ color: '#7a7973', lineHeight: 1.4, height: 32, overflow: 'hidden' }}>
                              {r.text}
                            </div>
                            <div style={{ color: '#9c9b96', fontSize: 11 }}>
                              P{r.page} · 匹配度 {(r.score * 100).toFixed(0)}%
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 联网来源 */}
                  {m.web_sources && m.web_sources.length > 0 && (
                    <div style={{ marginBottom: 14 }}>
                      <div style={{ fontSize: 12, color: '#9c9b96', marginBottom: 8, fontWeight: 500 }}>
                        联网检索结果
                      </div>
                      <div className="ppx-sources-row">
                        {m.web_sources.map((w, i) => (
                          <a
                            key={i} href={w.url} target="_blank" rel="noreferrer"
                            className="ppx-source-card" style={{ textDecoration: 'none' }}
                          >
                            <div style={{ fontWeight: 600, color: '#111', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {w.title}
                            </div>
                            <div style={{ color: '#7a7973', lineHeight: 1.4, height: 32, overflow: 'hidden' }}>
                              {w.snippet || w.url}
                            </div>
                            <div style={{ color: '#2563eb', fontSize: 11, display: 'flex', alignItems: 'center', gap: 4 }}>
                              <GlobalOutlined /> 网页来源
                            </div>
                          </a>
                        ))}
                      </div>
                    </div>
                  )}

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

                  {/* 推荐追问 Chips */}
                  {m.followups && m.followups.length > 0 && (
                    <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      {m.followups.map((f, i) => (
                        <Button
                          key={i} size="small"
                          style={{
                            borderRadius: 14, background: '#fff', borderColor: '#ecece4',
                            color: '#5f5e5a', fontSize: 12,
                          }}
                          onClick={() => handleSend(f)}
                        >
                          {f}
                        </Button>
                      ))}
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