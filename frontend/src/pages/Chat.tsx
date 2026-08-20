import React, { useState, useRef, useEffect } from 'react';
import { Input, Button, List, Tag, Typography, Spin, Empty, Space, Image, Drawer, Popconfirm, Select } from 'antd';
import { SendOutlined, FileTextOutlined, PictureOutlined, TableOutlined, RobotOutlined, UserOutlined, PlusOutlined, DeleteOutlined, HistoryOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const { Text } = Typography;
const { TextArea } = Input;

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

interface ChatSession { id: string; session_name: string; assistant_role?: string; created_at: string; updated_at: string; }

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  answer?: string;
  results?: SearchResult[];
  timestamp: Date;
  followups?: string[];
  web_sources?: { title: string; url: string; snippet?: string }[];
  no_result?: boolean;
  web_available?: boolean;
}







const ChatPage: React.FC<{ token: string }> = ({ token }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [memoryHistory, setMemoryHistory] = useState<any[]>([]);
  const [assistantRole, setAssistantRole] = useState('customer_service');
  const [lead, setLead] = useState<any>(null);
  const authHeaders = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` };
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const api = process.env.REACT_APP_API_URL || 'http://localhost:8000';
  const loadSessions = async () => {
    const response = await fetch(`${api}/api/v1/auth/sessions`, { headers: { Authorization: `Bearer ${token}` } });
    const data = await response.json();
    setSessions(data.sessions || []);
    return data.sessions || [];
  };

  const loadSession = async (session: ChatSession) => {
    const response = await fetch(`${api}/api/v1/auth/sessions/${session.id}/messages`, { headers: { Authorization: `Bearer ${token}` } });
    const data = await response.json();
    setSessionId(session.id);
    setAssistantRole(session.assistant_role || 'customer_service');
    setMessages((data.messages || []).map((m: any) => ({
      id: m.id, role: m.role, content: m.content, timestamp: new Date(m.created_at),
      results: m.metadata?.results || [], followups: m.metadata?.followups || [], answer: m.role === 'assistant' ? m.content : undefined,
    })));
    setHistoryOpen(false);
    fetch(`${api}/api/v1/auth/sessions/${session.id}/memory`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : { history: [] }).then(x => setMemoryHistory(x.history || [])).catch(() => setMemoryHistory([]));
  };

  const createSession = async () => {
    const response = await fetch(`${api}/api/v1/auth/sessions`, { method: 'POST', headers: authHeaders, body: JSON.stringify({ name: '新会话' }) });
    const data = await response.json();
    if (data.session) { setSessions(prev => [data.session, ...prev]); setSessionId(data.session.id); setAssistantRole(data.session.assistant_role || 'customer_service'); setMessages([]); setHistoryOpen(false); }
  };

  const removeSession = async (id: string) => {
    await fetch(`${api}/api/v1/auth/sessions/${id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } });
    const next = sessions.filter(x => x.id !== id); setSessions(next);
    if (id === sessionId) { if (next[0]) loadSession(next[0]); else createSession(); }
  };

  useEffect(() => {
    loadSessions().then(async list => {
      if (list[0]) await loadSession(list[0]);
      else await createSession();
    });
  }, [token]);

  const loadMemory = async () => {
    if (!sessionId) return [];
    const response = await fetch(`${api}/api/v1/auth/sessions/${sessionId}/memory`, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) return [];
    const data = await response.json();
    setMemoryHistory(data.history || []);
    return data.history || [];
  };

  const handleSend = async (suggestedQuery?: string, forceWeb = false) => {
    const question = (suggestedQuery || input).trim();
    if (!question || loading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: question,
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    if (sessionId) fetch(`${process.env.REACT_APP_API_URL || 'http://localhost:8000'}/api/v1/auth/sessions/${sessionId}/messages`, { method: 'POST', headers: authHeaders, body: JSON.stringify({ role: 'user', content: question }) }).catch(() => undefined);
    const query = question;
    const previousUserQuery = [...messages].reverse().find(m => m.role === 'user')?.content;
    setInput('');
    setLoading(true);

    try {
      const response = await fetch(
        `${process.env.REACT_APP_API_URL || 'http://localhost:8000'}/api/v1/rag/chat`,
        {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({ query, top_k: 5, context_query: previousUserQuery, history: memoryHistory, role: assistantRole, session_id: sessionId, force_web: forceWeb }),
        }
      );
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || `请求失败（${response.status}）`);

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: data.answer || '抱歉，无法生成回答。',
        answer: data.answer,
        results: data.results || [],
        followups: data.followups || [],
        web_sources: data.web_sources || [],
        no_result: data.no_result || false,
        web_available: data.web_available || false,
        timestamp: new Date(),
      };

      setMessages(prev => [...prev, assistantMessage]);
      if (data.lead) setLead(data.lead);
      if (sessionId) fetch(`${process.env.REACT_APP_API_URL || 'http://localhost:8000'}/api/v1/auth/sessions/${sessionId}/messages`, { method: 'POST', headers: authHeaders, body: JSON.stringify({ role: 'assistant', content: assistantMessage.content, metadata: { results: assistantMessage.results, followups: assistantMessage.followups, web_sources: assistantMessage.web_sources, mode: data.mode || 'knowledge', role: assistantRole } }) }).catch(() => undefined);
      if (sessionId) { fetch(`${api}/api/v1/auth/sessions/${sessionId}/compact`, { method: 'POST', headers: authHeaders }).catch(() => undefined); loadMemory(); }
    } catch (error: any) {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `出错了：${error.message}`,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const getFollowups = (msg: Message) => msg.followups?.slice(0, 3) || [];

  const renderAnswer = (content: string) => (
    <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
  );

  const renderImageResult = (result: SearchResult) => {
    if (result.type !== 'product_image' || !result.source) return null;
    
    const apiBase = process.env.REACT_APP_API_URL || 'http://localhost:8000';
    const imageUrl = result.source.startsWith('http') ? result.source : `${apiBase}${result.source}`;
    
    return (
      <Image
        src={imageUrl}
        alt={result.category || '产品图片'}
        style={{ maxWidth: 200, maxHeight: 150, objectFit: 'cover', borderRadius: 8 }}
        preview={{ src: imageUrl }}
      />
    );
  };

  const changeRole = async (role: string) => {
    setAssistantRole(role);
    if (sessionId) {
      await fetch(`${api}/api/v1/auth/sessions/${sessionId}/role`, { method: 'PUT', headers: authHeaders, body: JSON.stringify({ role }) }).catch(() => undefined);
      setSessions(prev => prev.map(x => x.id === sessionId ? { ...x, assistant_role: role } : x));
    }
  };

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', height: 'calc(100vh - 200px)', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0 12px', borderBottom: '1px solid #f0f0f0' }}>
        <Space>
          <Button icon={<HistoryOutlined />} onClick={() => setHistoryOpen(true)}>历史对话{sessions.length ? ` (${sessions.length})` : ''}</Button>
          <Select value={assistantRole} onChange={changeRole} style={{ width: 130 }} options={[{ value: 'customer_service', label: '客服' }, { value: 'sales', label: '销售' }, { value: 'technical_support', label: '技术支持' }]} />
          {assistantRole === 'sales' && lead && <Tag color={lead.level === 'high' ? 'red' : lead.level === 'medium' ? 'orange' : 'default'}>意向：{lead.level === 'high' ? '高' : lead.level === 'medium' ? '中' : '低'} {lead.score}</Tag>}
        </Space>
        <Button type="primary" ghost icon={<PlusOutlined />} onClick={createSession}>新建对话</Button>
      </div>
      <Drawer title="历史对话" placement="left" width={320} open={historyOpen} onClose={() => setHistoryOpen(false)} extra={<Button type="primary" size="small" icon={<PlusOutlined />} onClick={createSession}>新建</Button>}>
        <List dataSource={sessions} locale={{ emptyText: '暂无历史对话' }} renderItem={(session) => (
          <List.Item actions={[<Popconfirm title="删除这个会话？" onConfirm={() => removeSession(session.id)}><Button type="text" danger icon={<DeleteOutlined />} /></Popconfirm>] }>
            <Button type="text" style={{ width: 210, textAlign: 'left', overflow: 'hidden', textOverflow: 'ellipsis' }} onClick={() => loadSession(session)}>{session.session_name || '未命名会话'}</Button>
          </List.Item>
        )} />
      </Drawer>

      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 0' }}>
        {messages.length === 0 ? (
          <Empty
            description="输入问题开始智能问答"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          >
            <Space direction="vertical" size="small">
              <Text type="secondary">试试搜索：</Text>
              <Space wrap>
                <Button size="small" onClick={() => setInput('氢能重卡有哪些型号？')}>氢能重卡有哪些型号？</Button>
                <Button size="small" onClick={() => setInput('PEM制氢系统参数')}>PEM制氢系统参数</Button>
                <Button size="small" onClick={() => setInput('公司联系方式')}>公司联系方式</Button>
              </Space>
            </Space>
          </Empty>
        ) : (
          <List
            dataSource={messages}
            renderItem={(msg) => (
              <List.Item
                style={{
                  justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                  border: 'none',
                  padding: '8px 0',
                  display: 'block',
                }}
              >
                {msg.role === 'user' ? (
                  <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                    <div
                      style={{
                        padding: '12px 16px',
                        borderRadius: 12,
                        background: '#1890ff',
                        color: '#fff',
                        maxWidth: '70%',
                      }}
                    >
                      {msg.content}
                    </div>
                    <div style={{ width: 32, height: 32, borderRadius: '50%', background: '#52c41a', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      <UserOutlined style={{ color: '#fff', fontSize: 16 }} />
                    </div>
                  </div>
                ) : (
                  <div style={{ display: 'flex', gap: 8 }}>
                    <div style={{ width: 32, height: 32, borderRadius: '50%', background: '#1890ff', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      <RobotOutlined style={{ color: '#fff', fontSize: 16 }} />
                    </div>
                    <div style={{ flex: 1 }}>
                      {/* AI 回答 - Markdown 渲染 */}
                      <div
                        style={{
                          padding: '12px 16px',
                          borderRadius: 12,
                          background: '#fff',
                          boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
                          lineHeight: 1.8,
                        }}
                        className="markdown-body"
                      >
                        {renderAnswer(msg.content)}
                      </div>

                      {msg.no_result && (
                        <div style={{ marginTop: 12, padding: '14px 16px', border: '1px solid #ffe58f', borderRadius: 8, background: '#fffbe6' }}>
                          <div style={{ fontWeight: 600, marginBottom: 6 }}>未找到匹配资料</div>
                          <div style={{ color: '#666', fontSize: 13, marginBottom: 10 }}>当前企业知识库没有该问题的可靠信息。你可以继续查询或补充更多线索。</div>
                          <Space wrap>
                            {msg.web_available && <Button size="small" type="primary" onClick={() => handleSend(`请联网查询：${msg.content}`, true)}>联网继续查询</Button>}
                            <Button size="small" onClick={() => setInput('请换一种说法：')}>换个说法</Button>
                            <Button size="small" onClick={() => setInput('补充产品型号：')}>补充产品型号</Button>
                            <Button size="small" onClick={() => setInput('请转交技术支持')}>联系技术支持</Button>
                          </Space>
                        </div>
                      )}
                      
                      {/* 图片展示 */}
                      {msg.results && msg.results.filter(r => r.type === 'product_image').length > 0 && (
                        <div style={{ marginTop: 12 }}>
                          <div style={{ fontSize: 12, color: '#888', marginBottom: 8 }}>📷 相关产品图片</div>
                          <Image.PreviewGroup>
                            <Space wrap>
                              {msg.results
                                .filter(r => r.type === 'product_image')
                                .map((r, i) => (
                                  <div key={i} style={{ textAlign: 'center' }}>
                                    {renderImageResult(r)}
                                    <div style={{ fontSize: 11, color: '#666', marginTop: 4 }}>
                                      {r.category}
                                    </div>
                                  </div>
                                ))
                              }
                            </Space>
                          </Image.PreviewGroup>
                        </div>
                      )}

                      {/* 推荐继续提问：仅展示由文档约束生成的可回答问题 */}
                      {getFollowups(msg).length > 0 && (
                        <div style={{ marginTop: 12, padding: '10px 12px', border: '1px solid #d6e4ff', borderRadius: 8, background: '#f7fbff' }}>
                          <div style={{ fontSize: 13, fontWeight: 600, color: '#245b9e', marginBottom: 8 }}>你还可以问</div>
                          <Space wrap size={[8, 8]}>
                            {getFollowups(msg).map((question, i) => (
                              <Button key={i} size="small" disabled={loading} onClick={() => handleSend(question)}>
                                {question}
                              </Button>
                            ))}
                          </Space>
                        </div>
                      )}

                      {msg.web_sources && msg.web_sources.length > 0 && (
                        <div style={{ marginTop: 12, fontSize: 12 }}>
                          <div style={{ color: '#888', marginBottom: 6 }}>联网来源</div>
                          {msg.web_sources.map((source, i) => <div key={i}><a href={source.url} target="_blank" rel="noreferrer">{source.title}</a></div>)}
                        </div>
                      )}
                      

                    </div>
                  </div>
                )}
              </List.Item>
            )}
          />
        )}
        {loading && (
          <div style={{ textAlign: 'center', padding: 20 }}>
            <Spin tip="正在思考..." />
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div style={{ padding: '16px 0', borderTop: '1px solid #f0f0f0' }}>
        <Space.Compact style={{ width: '100%' }}>
          <TextArea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入问题，AI 将基于文档内容回答（Enter 发送，Shift+Enter 换行）"
            autoSize={{ minRows: 1, maxRows: 4 }}
            style={{ flex: 1 }}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={() => handleSend()}
            loading={loading}
            disabled={!input.trim()}
          >
            发送
          </Button>
        </Space.Compact>
      </div>
    </div>
  );
};

export default ChatPage;
