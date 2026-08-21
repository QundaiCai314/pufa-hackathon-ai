import React, { useState, useEffect } from 'react';
import {
  Typography, Tabs, Table, Tag, Space, Button, Drawer, Spin, App as AntApp,
  Empty, Statistic, Card, Descriptions,
} from 'antd';
import {
  UserOutlined, MessageOutlined, ThunderboltOutlined, FileTextOutlined,
  DownloadOutlined, EyeOutlined,
} from '@ant-design/icons';
import { Radar } from 'react-chartjs-2';
import { Chart as ChartJS, RadialLinearScale, PointElement, LineElement, Filler, Tooltip, Legend } from 'chart.js';

ChartJS.register(RadialLinearScale, PointElement, LineElement, Filler, Tooltip, Legend);

const { Title, Text } = Typography;

const API = process.env.REACT_APP_API_URL || 'http://localhost:8000';

interface Overview {
  users: number;
  sessions: number;
  messages: number;
  leads?: number;
  lead_distribution?: { lead_level: string; count: number }[];
  role_distribution?: { assistant_role: string; count: number }[];
  recent_sessions?: any[];
}

interface UserItem {
  id: number;
  username: string;
  email: string;
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
}

interface HealthProject {
  session_id: string;
  project: string;
  customer: string;
  updated_at: string;
  health: number;
  dimensions: Record<string, number>;
  risks: { level: string; text: string }[];
  has_proposal: boolean;
}

interface LeadItem {
  id: number;
  username: string;
  email?: string;
  session_name?: string;
  lead_score: number;
  lead_level: string;
  lead_signals?: Record<string, any>;
  updated_at?: string;
}

export default function Admin({ auth }: { auth: any }) {
  const { message } = AntApp.useApp();
  const token = auth?.token;
  const authHeaders = { ...(token ? { Authorization: `Bearer ${token}` } : {}) };
  const [activeTab, setActiveTab] = useState('overview');
  const [overview, setOverview] = useState<Overview | null>(null);
  const [users, setUsers] = useState<UserItem[]>([]);
  const [leads, setLeads] = useState<LeadItem[]>([]);
  const [healthProjects, setHealthProjects] = useState<HealthProject[]>([]);
  const [selectedHealth, setSelectedHealth] = useState<HealthProject | null>(null);
  const [loading, setLoading] = useState(false);
  const [leadsLoading, setLeadsLoading] = useState(false);
  const [drawer, setDrawer] = useState<{ lead: LeadItem; messages: any[] } | null>(null);

  useEffect(() => {
    if (activeTab === 'overview') loadOverview();
    if (activeTab === 'users') loadUsers();
    if (activeTab === 'leads') loadLeads();
    if (activeTab === 'health') loadHealth();
  }, [activeTab]);

  const loadOverview = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/v1/admin/overview`, { headers: authHeaders });
      if (!res.ok) throw new Error('加载看板失败');
      setOverview(await res.json());
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  const loadUsers = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/v1/admin/users`, { headers: authHeaders });
      if (!res.ok) throw new Error('加载用户失败');
      const data = await res.json();
      setUsers(data.users || []);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  const loadHealth = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/v1/admin/project-health`, { headers: authHeaders });
      if (!res.ok) throw new Error('加载项目健康度失败');
      const data = await res.json();
      setHealthProjects(data.projects || []);
      setSelectedHealth(data.projects?.[0] || null);
    } catch (e: any) { message.error(e.message); }
    finally { setLoading(false); }
  };

  const loadLeads = async () => {
    setLeadsLoading(true);
    try {
      const res = await fetch(`${API}/api/v1/admin/leads`, { headers: authHeaders });
      if (!res.ok) throw new Error('加载线索失败');
      const data = await res.json();
      setLeads(data.leads || []);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLeadsLoading(false);
    }
  };

  const openLeadDetail = async (lead: LeadItem) => {
    try {
      const res = await fetch(`${API}/api/v1/admin/sessions/${lead.id}`, { headers: authHeaders });
      if (!res.ok) throw new Error('加载对话失败');
      const data = await res.json();
      setDrawer({ lead, messages: data.messages || [] });
    } catch (e: any) {
      message.error(e.message);
    }
  };

  const downloadProposal = async (lead: LeadItem) => {
    try {
      const res = await fetch(`${API}/api/v1/admin/leads/${lead.id}/sales-plan.docx`, { headers: authHeaders });
      if (!res.ok) throw new Error('生成失败');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `sales_proposal_${lead.username}_${Date.now()}.docx`;
      a.click();
      URL.revokeObjectURL(url);
      message.success('销售方案已下载');
    } catch (e: any) {
      message.error(e.message);
    }
  };

  const gradeColor = (g: string) => {
    if (g === 'A') return 'green';
    if (g === 'B') return 'blue';
    if (g === 'C') return 'orange';
    return 'default';
  };

  return (
    <div style={{ padding: '32px 40px', maxWidth: 1180, margin: '0 auto' }}>
      <Title level={3} style={{ marginTop: 0, fontWeight: 600, letterSpacing: -0.5 }}>
        管理后台
      </Title>
      <Text type="secondary" style={{ display: 'block', marginBottom: 24 }}>
        用户、会话与销售线索的集中管理。
      </Text>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'overview', label: '数据看板',
            children: loading ? <Spin /> : overview ? (
              <div>
                <div style={{
                  display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 28,
                }}>
                  {[
                    { title: '用户数', value: overview.users, icon: <UserOutlined /> },
                    { title: '会话数', value: overview.sessions, icon: <MessageOutlined /> },
                    { title: '消息数', value: overview.messages, icon: <ThunderboltOutlined /> },
                    { title: '线索数', value: overview.leads, icon: <FileTextOutlined /> },
                  ].map((s, i) => (
                    <div key={i} style={{
                      background: '#fff', border: '1px solid #ecece4', borderRadius: 12, padding: '18px 22px',
                    }}>
                      <div style={{ fontSize: 12, color: '#9c9b96', display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                        {s.icon} {s.title}
                      </div>
                      <div style={{ fontSize: 28, fontWeight: 600, letterSpacing: -0.5 }}>{s.value}</div>
                    </div>
                  ))}
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                  <div style={{ background: '#fff', border: '1px solid #ecece4', borderRadius: 12, padding: 22 }}>
                    <div style={{ fontWeight: 500, marginBottom: 14 }}>意向等级分布</div>
                    {overview.lead_distribution && overview.lead_distribution.length > 0 ? (
                      <Space direction="vertical" size={8} style={{ width: '100%' }}>
                        {overview.lead_distribution.map((item) => (
                          <div key={item.lead_level} style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span><Tag color={gradeColor(item.lead_level)}>{item.lead_level} 级</Tag></span>
                            <span style={{ fontWeight: 500 }}>{item.count}</span>
                          </div>
                        ))}
                      </Space>
                    ) : <Empty />}
                  </div>

                  <div style={{ background: '#fff', border: '1px solid #ecece4', borderRadius: 12, padding: 22 }}>
                    <div style={{ fontWeight: 500, marginBottom: 14 }}>角色分布</div>
                    {overview.role_distribution && overview.role_distribution.length > 0 ? (
                      <Space direction="vertical" size={8} style={{ width: '100%' }}>
                        {overview.role_distribution.map((item) => (
                          <div key={item.assistant_role} style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span>{item.assistant_role === 'sales' ? '销售' : item.assistant_role === 'customer_service' ? '客服' : '技术'}</span>
                            <span style={{ fontWeight: 500 }}>{item.count}</span>
                          </div>
                        ))}
                      </Space>
                    ) : <Empty />}
                  </div>
                </div>
              </div>
            ) : <Empty />,
          },
          {
            key: 'health', label: '项目健康度',
            children: loading ? <Spin /> : healthProjects.length === 0 ? <Empty description="尚无已保存方案的项目数据" /> : (
              <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: 18 }}>
                <div style={{ borderRight: '1px solid #ecece4', paddingRight: 14 }}>
                  <div style={{ fontSize: 12, color: '#888', marginBottom: 10 }}>仅管理员可见 · 基于已保存方案和资料证据</div>
                  {healthProjects.map(p => <button key={p.session_id} onClick={() => setSelectedHealth(p)} style={{ width: '100%', textAlign: 'left', border: '1px solid #e8e7df', background: selectedHealth?.session_id === p.session_id ? '#f0eee6' : '#fff', borderRadius: 10, padding: '12px 13px', marginBottom: 8, cursor: 'pointer' }}>
                    <div style={{ display:'flex', justifyContent:'space-between', gap:8 }}><b style={{ overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{p.project}</b><span style={{ fontWeight:700 }}>{p.health}</span></div>
                    <div style={{ color:'#8a8983', fontSize:12, marginTop:5 }}>{p.customer} · {p.has_proposal ? '已保存方案' : '待保存方案'}</div>
                  </button>)}
                </div>
                {selectedHealth && <div>
                  <div style={{ display:'flex', alignItems:'baseline', justifyContent:'space-between', marginBottom:10 }}><div><div style={{ fontSize:12,color:'#8a8983' }}>项目健康度 · {selectedHealth.customer}</div><Title level={3} style={{ margin:'3px 0' }}>{selectedHealth.project}</Title></div><div style={{ fontSize:44,fontWeight:700,letterSpacing:-2 }}>{selectedHealth.health}<span style={{ fontSize:15,color:'#888' }}>/100</span></div></div>
                  <div style={{ display:'grid', gridTemplateColumns:'minmax(300px, 1fr) 1fr', gap:22, alignItems:'center' }}>
                    <div style={{ height:310 }}><Radar data={{ labels:Object.keys(selectedHealth.dimensions), datasets:[{ label:'项目健康度', data:Object.values(selectedHealth.dimensions), backgroundColor:'rgba(20,20,18,.12)', borderColor:'#141412', borderWidth:2, pointBackgroundColor:'#141412' }] }} options={{ responsive:true, maintainAspectRatio:false, scales:{ r:{ min:0,max:100,ticks:{ display:false },grid:{ color:'#e4e3dc' },angleLines:{ color:'#e4e3dc' },pointLabels:{ font:{ size:12 } } } }, plugins:{ legend:{ display:false } } }} /></div>
                    <div><div style={{ fontWeight:600,marginBottom:10 }}>风险与可核验信号</div>{selectedHealth.risks.map((r,i)=><div key={i} style={{ padding:'10px 0', borderBottom:'1px solid #efeee8', display:'flex',gap:9 }}><Tag color={r.level==='高'?'red':r.level==='中'?'orange':'green'}>{r.level}风险</Tag><span style={{ fontSize:13 }}>{r.text}</span></div>)}<div style={{ fontSize:12,color:'#8a8983',marginTop:16 }}>评分用于项目跟进排序，不替代工程设计、现场踏勘或人工技术审核。</div></div>
                  </div>
                  <div style={{ display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:10,marginTop:14 }}>{Object.entries(selectedHealth.dimensions).map(([name,value])=><div key={name} style={{ padding:'12px',border:'1px solid #ecece4',borderRadius:9 }}><div style={{fontSize:12,color:'#888'}}>{name}</div><b style={{fontSize:21}}>{value}</b></div>)}</div>
                </div>}
              </div>
            ),
          },
          {
            key: 'users', label: '用户',
            children: (
              <Table
                loading={loading}
                dataSource={users.map((u) => ({ ...u, key: u.id }))}
                pagination={{ pageSize: 10 }}
                columns={[
                  { title: '用户名', dataIndex: 'username', key: 'username' },
                  { title: '邮箱', dataIndex: 'email', key: 'email' },
                  {
                    title: '身份', dataIndex: 'is_admin', key: 'role',
                    render: (v) => <Tag color={v ? 'purple' : 'default'}>{v ? '管理员' : '客户'}</Tag>,
                  },
                  {
                    title: '状态', dataIndex: 'is_active', key: 'active',
                    render: (v) => <Tag color={v ? 'green' : 'red'}>{v ? '正常' : '禁用'}</Tag>,
                  },
                  {
                    title: '注册时间', dataIndex: 'created_at', key: 'created',
                    render: (v) => new Date(v).toLocaleString('zh-CN'),
                  },
                ]}
              />
            ),
          },
          {
            key: 'leads', label: '销售线索',
            children: leadsLoading ? <Spin /> : (
              <Table
                dataSource={leads.map((l) => ({ ...l, key: l.id }))}
                pagination={{ pageSize: 10 }}
                columns={[
                  { title: '客户', dataIndex: 'username', key: 'username' },
                  {
                    title: '意向度', dataIndex: 'lead_score', key: 'lead_score',
                    render: (s) => <strong>{s}</strong>,
                  },
                  {
                    title: '等级', dataIndex: 'lead_level', key: 'lead_level',
                    render: (g) => <Tag color={gradeColor(g)}>{g} 级</Tag>,
                  },
                  {
                    title: '信号', dataIndex: 'lead_signals', key: 'lead_signals',
                    render: (signals: Record<string, any>) => {
                      const keys = signals ? Object.keys(signals) : [];
                      return (
                        <Space size={4} wrap>
                          {keys.slice(0, 2).map((k, i) => <Tag key={i}>{k}</Tag>)}
                          {keys.length > 2 && <Tag>+{keys.length - 2}</Tag>}
                        </Space>
                      );
                    },
                  },
                  {
                    title: '操作', key: 'op',
                    render: (_, l: LeadItem) => (
                      <Space>
                        <Button size="small" icon={<EyeOutlined />} onClick={() => openLeadDetail(l)}>查看</Button>
                        <Button size="small" icon={<DownloadOutlined />} onClick={() => downloadProposal(l)}>方案</Button>
                      </Space>
                    ),
                  },
                ]}
              />
            ),
          },
        ]}
      />

      <Drawer
        title={`线索详情 · ${drawer?.lead.username || ''}`}
        placement="right" width={560}
        open={!!drawer} onClose={() => setDrawer(null)}
      >
        {drawer && (
          <div>
            <Descriptions column={1} bordered size="small" style={{ marginBottom: 20 }}>
              <Descriptions.Item label="意向度">{drawer.lead.lead_score}</Descriptions.Item>
              <Descriptions.Item label="等级"><Tag color={gradeColor(drawer.lead.lead_level)}>{drawer.lead.lead_level} 级</Tag></Descriptions.Item>
              <Descriptions.Item label="会话">{drawer.lead.session_name || drawer.lead.id}</Descriptions.Item>
            </Descriptions>

            <div style={{ fontWeight: 500, marginBottom: 12 }}>最近对话</div>
            {drawer.messages.length === 0 ? <Empty /> : (
              <Space direction="vertical" size={10} style={{ width: '100%' }}>
                {drawer.messages.map((m, i) => (
                  <div key={i} style={{
                    background: m.role === 'user' ? '#f0eee6' : '#fff',
                    border: '1px solid #ecece4', borderRadius: 10,
                    padding: '10px 14px', fontSize: 13,
                  }}>
                    <div style={{ fontSize: 11, color: '#9c9b96', marginBottom: 4 }}>
                      {m.role === 'user' ? '客户' : '氢璞 AI'} · {new Date(m.created_at).toLocaleString('zh-CN')}
                    </div>
                    <div style={{ lineHeight: 1.6 }}>{m.content}</div>
                  </div>
                ))}
              </Space>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
}