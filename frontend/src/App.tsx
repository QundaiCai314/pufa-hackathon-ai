import React, { useState, useEffect, useRef } from 'react';
import {
  Layout, Menu, Button, App as AntApp,
} from 'antd';
import {
  HomeOutlined, FileTextOutlined, MessageOutlined, SettingOutlined,
  PlusOutlined, LogoutOutlined, DeleteOutlined,
} from '@ant-design/icons';
import Login from './pages/Login';
import Home from './pages/Home';
import Chat from './pages/Chat';
import Documents from './pages/Documents';
import Admin from './pages/Admin';
import './App.css';

const { Sider, Content } = Layout;

// 持久化登录态
const AUTH_KEY = 'qingpu_auth';
const getAuth = () => { try { return JSON.parse(localStorage.getItem(AUTH_KEY) || 'null'); } catch { return null; } };
const setAuth = (v: any) => localStorage.setItem(AUTH_KEY, JSON.stringify(v));
const clearAuth = () => localStorage.removeItem(AUTH_KEY);

type Page = 'home' | 'chat' | 'documents' | 'admin';

interface SidebarSession {
  id: string;
  session_name: string;
  created_at: string;
  updated_at: string;
}

const App: React.FC = () => {
  const { message } = AntApp.useApp();
  const [auth, setAuthState] = useState<any>(getAuth());
  const [currentPage, setCurrentPage] = useState<Page>('home');
  const [chatPreset, setChatPreset] = useState<string | undefined>(undefined);
  const [sidebarSessions, setSidebarSessions] = useState<SidebarSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  const isAdmin = !!auth?.user?.is_admin;
  const token = auth?.token;
  const authHeaders: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};

  const loadSidebarSessions = async () => {
    if (!token) return;
    try {
      const res = await fetch(`${process.env.REACT_APP_API_URL || 'http://localhost:8000'}/api/v1/auth/sessions`, { headers: authHeaders });
      if (res.ok) setSidebarSessions((await res.json()).sessions || []);
    } catch { /* sidebar history is non-blocking */ }
  };

  useEffect(() => { loadSidebarSessions(); }, [token]);

  useEffect(() => {
    document.title = '氢璞 AI · 企业知识助手';
  }, []);

  if (!auth?.token) return <Login onLogin={(d) => { setAuth(d); setAuthState(d); }} />;

  const logout = () => {
    clearAuth();
    setAuthState(null);
    message.success('已退出登录');
  };

  const goChat = (preset?: string, sessionId?: string) => {
    setChatPreset(preset);
    setActiveSessionId(sessionId || null);
    setCurrentPage('chat');
  };

  const createSidebarSession = async () => {
    try {
      const res = await fetch(`${process.env.REACT_APP_API_URL || 'http://localhost:8000'}/api/v1/auth/sessions`, { method: 'POST', headers: { ...authHeaders, 'Content-Type': 'application/json' }, body: JSON.stringify({ session_name: '新对话', assistant_role: 'customer_service' }) });
      if (!res.ok) return;
      const s = (await res.json()).session;
      setSidebarSessions(prev => [s, ...prev]);
      goChat(undefined, s.id);
    } catch { message.error('创建对话失败'); }
  };

  const deleteSidebarSession = async (id: string) => {
    try {
      const res = await fetch(`${process.env.REACT_APP_API_URL || 'http://localhost:8000'}/api/v1/auth/sessions/${id}`, { method: 'DELETE', headers: authHeaders });
      if (!res.ok) throw new Error();
      setSidebarSessions(prev => prev.filter(s => s.id !== id));
      if (activeSessionId === id) setActiveSessionId(null);
      message.success('已删除对话');
    } catch { message.error('删除失败'); }
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={260} style={{ background: '#fbfbf7', borderRight: '1px solid #ecece4' }}>
        <div style={{ padding: 20, display: 'flex', flexDirection: 'column', height: '100%' }}>
          <div
            onClick={() => setCurrentPage('home')}
            style={{
              display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer',
              padding: '4px 6px', marginBottom: 28,
            }}
          >
            <div style={{
              width: 30, height: 30, borderRadius: 8, background: '#111',
              color: '#fff', display: 'grid', placeItems: 'center',
              fontWeight: 700, fontSize: 15,
            }}>氢</div>
            <div style={{ fontSize: 15, fontWeight: 600, letterSpacing: -0.3 }}>氢璞 AI</div>
          </div>

          <Button
            type="primary" size="large" icon={<PlusOutlined />}
            onClick={createSidebarSession}
            className="sidebar-new-chat"
            style={{
              marginBottom: 22, height: 42, borderRadius: 8,
              fontWeight: 600,
            }}
            block
          >新对话</Button>

          <div style={{ fontSize: 12, color: '#9c9b96', padding: '0 10px', marginBottom: 6 }}>导航</div>
          <Menu
            mode="inline"
            selectedKeys={[currentPage]}
            onClick={({ key }) => setCurrentPage(key as Page)}
            style={{ background: 'transparent', border: 'none', flex: 1 }}
            items={[
              { key: 'home', icon: <HomeOutlined />, label: '首页' },
              { key: 'chat', icon: <MessageOutlined />, label: '智能问答' },
              { key: 'documents', icon: <FileTextOutlined />, label: '知识库' },
              ...(isAdmin ? [{ key: 'admin', icon: <SettingOutlined />, label: '管理后台' }] : []),
            ]}
          />

          <div className="sidebar-history">
            <div className="sidebar-section-label"><span>最近对话</span><span>{sidebarSessions.length || ''}</span></div>
            <div className="sidebar-history-list">
              {sidebarSessions.length === 0 ? <div className="sidebar-history-empty">暂无历史记录</div> : sidebarSessions.slice(0, 12).map((s) => (
                <div key={s.id} className={`sidebar-history-item ${s.id === activeSessionId ? 'is-active' : ''}`} onClick={() => goChat(undefined, s.id)} title={s.session_name || '新对话'}>
                  <span className="sidebar-history-name">{s.session_name || '新对话'}</span>
                  <Button type="text" size="small" className="sidebar-history-delete" icon={<DeleteOutlined />} onClick={(e) => { e.stopPropagation(); deleteSidebarSession(s.id); }} />
                </div>
              ))}
            </div>
          </div>

          <div style={{
            padding: 12, borderTop: '1px solid #ecece4',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{
                width: 30, height: 30, borderRadius: '50%',
                background: '#f0eee6', display: 'grid', placeItems: 'center',
                color: '#111', fontWeight: 600,
              }}>{(auth.user?.username || 'U')[0].toUpperCase()}</div>
              <div style={{ fontSize: 13 }}>
                <div style={{ fontWeight: 500 }}>{auth.user?.username}</div>
                <div style={{ color: '#9c9b96', fontSize: 11 }}>
                  {isAdmin ? '管理员' : '客户'}
                </div>
              </div>
            </div>
            <Button type="text" icon={<LogoutOutlined />} onClick={logout} title="退出" />
          </div>
        </div>
      </Sider>

      <Content style={{ background: '#fff' }}>
        {currentPage === 'home' && <Home auth={auth} onStartChat={goChat} onOpenDocs={() => setCurrentPage('documents')} />}
        {currentPage === 'chat' && <Chat key={activeSessionId || 'new-chat'} auth={auth} preset={chatPreset} initialSessionId={activeSessionId} clearPreset={() => setChatPreset(undefined)} onSessionsChange={(sessions: SidebarSession[]) => { if (sessions.length > 0) setSidebarSessions(sessions); }} />}
        {currentPage === 'documents' && <Documents auth={auth} isAdmin={isAdmin} />}
        {currentPage === 'admin' && isAdmin && <Admin auth={auth} />}
      </Content>
    </Layout>
  );
};

export default App;