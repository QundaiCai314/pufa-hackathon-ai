import React, { useState } from 'react';
import { Alert, Button, Card, Input, Tabs, Typography, Radio } from 'antd';

const API = process.env.REACT_APP_API_URL || 'http://localhost:8000';

export default function Login({ onLogin }: { onLogin: (data: any) => void }) {
  const [register, setRegister] = useState(false);
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [userType, setUserType] = useState('customer');
  const [adminCode, setAdminCode] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const submit = async () => {
    setError(''); setLoading(true);
    try {
      const response = await fetch(`${API}/api/v1/auth/${register ? 'register' : 'login'}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(register ? { username, email, password, user_type: userType, admin_code: userType === 'admin' ? adminCode : undefined } : { username, password }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || '操作失败');
      localStorage.setItem('qingpu_auth', JSON.stringify(data)); onLogin(data);
    } catch (e: any) { setError(e.message); } finally { setLoading(false); }
  };
  return <div style={{ minHeight:'100vh', display:'grid', placeItems:'center', background:'#f5f7fa', padding:20 }}>
    <Card style={{ width:390 }} bordered={false}>
      <Typography.Title level={3} style={{ marginTop:0 }}>氢璞 AI 智能助手</Typography.Title>
      <Typography.Paragraph type="secondary">登录后可保存并管理个人对话记录。</Typography.Paragraph>
      <Tabs activeKey={register ? 'register' : 'login'} onChange={k=>setRegister(k==='register')} items={[{key:'login',label:'登录'},{key:'register',label:'注册'}]} />
      <Input placeholder="用户名或邮箱" value={username} onChange={e=>setUsername(e.target.value)} style={{ marginBottom:12 }} />
      {register && <Radio.Group value={userType} onChange={e=>setUserType(e.target.value)} style={{ marginBottom: 12 }}><Radio value="customer">客户</Radio><Radio value="admin">管理用户</Radio></Radio.Group>}
      {register && userType === 'admin' && <Input.Password placeholder="管理注册口令" value={adminCode} onChange={e=>setAdminCode(e.target.value)} style={{ marginBottom:12 }} />}
      {register && <Input placeholder="邮箱" value={email} onChange={e=>setEmail(e.target.value)} style={{ marginBottom:12 }} />}
      <Input.Password placeholder="密码（至少6位）" value={password} onChange={e=>setPassword(e.target.value)} onPressEnter={submit} style={{ marginBottom:12 }} />
      {error && <Alert type="error" message={error} showIcon style={{ marginBottom:12 }} />}
      <Button type="primary" block loading={loading} onClick={submit}>{register ? '注册并登录' : '登录'}</Button>
    </Card>
  </div>;
}
