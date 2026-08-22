import React, { useEffect, useMemo, useState } from 'react';
import { Empty, Select, Spin } from 'antd';
import '../relationship-graph.css';

const API = process.env.REACT_APP_API_URL || 'http://localhost:8000';
type Session = { id: string; session_name: string; updated_at: string; created_at: string };
type Msg = { role: string; content: string; metadata?: any };

const modelsFrom = (results: any[]) => Array.from(new Set(results.flatMap(r => (String(r.text || '').match(/(?:ST\d+[A-Z0-9]*|CESP\d+|E\d+)/gi) || []).map((x: string) => x.toUpperCase())))).slice(0, 3) as string[];

export default function RelationshipGraph({ auth, sessions, initialSessionId }: { auth: any; sessions: Session[]; initialSessionId?: string | null }) {
  const [selected, setSelected] = useState(initialSessionId || sessions[0]?.id || '');
  const [messages, setMessages] = useState<Msg[]>([]);
  const [loading, setLoading] = useState(false);
  const [focus, setFocus] = useState('project');
  const token = auth?.token;
  const headers = { Authorization: `Bearer ${token}` };

  useEffect(() => { if (initialSessionId) setSelected(initialSessionId); }, [initialSessionId]);
  useEffect(() => {
    if (!selected || !token) { setMessages([]); return; }
    setLoading(true); setMessages([]);
    fetch(`${API}/api/v1/auth/sessions/${selected}/messages`, { headers })
      .then(r => r.ok ? r.json() : Promise.reject(new Error('加载失败')))
      .then(d => setMessages(d.messages || []))
      .catch(() => setMessages([])).finally(() => setLoading(false));
  }, [selected, token]);

  const data = useMemo(() => {
    const assistants = messages.filter(m => m.role === 'assistant');
    const latest = assistants[assistants.length - 1];
    let meta: any = latest?.metadata || {};
    if (typeof meta === 'string') { try { meta = JSON.parse(meta); } catch { meta = {}; } }
    const results = Array.isArray(meta.results) ? meta.results : [];
    const profileMsg = [...messages].reverse().find(m => m.role === 'user' && m.content.includes('当前项目需求画像'));
    const profileText = profileMsg?.content.match(/【当前项目需求画像：([^】]+)】/)?.[1] || '';
    const facts = profileText ? profileText.split('；').map(x => x.split('=')) : [];
    const models = modelsFrom(results);
    const sources = Array.from(new Set(results.map((r: any) => r.doc).filter(Boolean))).slice(0, 3) as string[];
    return { facts, models, sources, missing: facts.length ? [] : ['应用场景', '目标规模', '部署方式'], results };
  }, [messages]);
  const detail: Record<string, string> = {
    project: `当前会话包含 ${messages.length} 条消息。`,
    profile: data.facts.length ? data.facts.map(x => `${x[0]}：${x[1]}`).join('；') : '暂无结构化需求画像。可在智能问答中使用“智能选型”补充。',
    products: data.models.length ? `识别到产品：${data.models.join('、')}。` : '当前会话尚未识别出具体产品型号。',
    sources: data.sources.length ? `关联资料：${data.sources.join('、')}。` : '当前会话暂无企业资料来源。',
    risk: data.missing.length ? `待补充：${data.missing.join('、')}。` : '当前需求画像信息完整。',
  };
  return <div className="graph-page">
    <div className="graph-page-head"><div><div className="graph-kicker">KNOWLEDGE MAP</div><h1>关系图谱</h1><p>查看当前会话中需求、产品、资料证据与待确认条件之间的关联。</p></div>
      <Select value={selected || undefined} placeholder="选择一个会话" style={{ width: 230 }} onChange={setSelected} options={sessions.map(s => ({ value: s.id, label: s.session_name || '新对话' }))} />
    </div>
    {!sessions.length ? <Empty description="暂无可分析的会话" /> : loading ? <div className="graph-page-loading"><Spin tip="正在构建关系图谱" /></div> : <>
      <div className="relationship-graph relationship-graph-page"><svg className="graph-links" viewBox="0 0 760 430" preserveAspectRatio="none"><line x1="380" y1="210" x2="178" y2="105" /><line x1="380" y1="210" x2="582" y2="105" /><line x1="380" y1="210" x2="178" y2="324" /><line x1="380" y1="210" x2="582" y2="324" /></svg>
        {([['project','当前项目',selected?'会话已建立':'新建会话','graph-node-project'],['profile','需求画像',data.facts.length?`${data.facts.length} 项已关联`:'待补充','graph-node-profile'],['products','推荐产品',data.models.length?data.models.join(' · '):'等待识别','graph-node-products'],['sources','资料证据',data.sources.length?`${data.sources.length} 份来源`:'暂无来源','graph-node-sources'],['risk','待确认条件',data.missing.length?`${data.missing.length} 项待补充`:'信息完整','graph-node-risk']] as string[][]).map(n => <button key={n[0]} className={`graph-node ${n[3]} ${focus === n[0] ? 'selected' : ''}`} onClick={() => setFocus(n[0])}><b>{n[1]}</b><span>{n[2]}</span></button>)}
      </div><div className="graph-inspector"><span>关联说明</span><strong>{detail[focus]}</strong></div><div className="graph-legend"><i className="legend-project" />项目中心 <i className="legend-profile" />需求与条件 <i className="legend-product" />产品与资料</div></>}
  </div>;
}
