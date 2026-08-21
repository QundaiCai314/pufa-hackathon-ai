import React, { useState } from 'react';
import { Input, Button, Tabs, Typography, Radio, Alert, App as AntApp } from 'antd';
import {
  UserOutlined, LockOutlined, MailOutlined, KeyOutlined,
} from '@ant-design/icons';

const API = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const AUTH_KEY = 'qingpu_auth';

export default function Login({ onLogin }: { onLogin: (data: any) => void }) {
  const { message } = AntApp.useApp();
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
      const body = register
        ? { username, email, password, user_type: userType, admin_code: userType === 'admin' ? adminCode : undefined }
        : { username, password };
      const response = await fetch(`${API}/api/v1/auth/${register ? 'register' : 'login'}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || '操作失败');
      localStorage.setItem(AUTH_KEY, JSON.stringify(data));
      onLogin(data);
      message.success(register ? '注册成功，欢迎使用' : '登录成功');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh', display: 'grid', gridTemplateColumns: '1fr 1fr',
      background: '#fbfbf7',
    }}>
      {/* 左侧品牌区 */}
      <div style={{
        background: '#0e0e0e', color: '#fff', padding: '60px 56px',
        display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
        position: 'relative', overflow: 'hidden',
      }}>
        <div style={{ position: 'relative', zIndex: 2 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 10, background: '#fff',
              color: '#0e0e0e', display: 'grid', placeItems: 'center', fontWeight: 700, fontSize: 18,
            }}>氢</div>
            <div style={{ fontSize: 17, fontWeight: 600, letterSpacing: -0.3 }}>氢璞 AI</div>
          </div>
        </div>

        <div style={{ position: 'relative', zIndex: 2, maxWidth: 420 }}>
          <h1 style={{
            fontSize: 44, fontWeight: 600, lineHeight: 1.15, letterSpacing: -1,
            margin: 0, marginBottom: 20,
          }}>
            氢能源企业的<br/>智能知识中枢
          </h1>
          <p style={{ fontSize: 16, lineHeight: 1.6, color: '#a8a8a8', margin: 0 }}>
            基于企业资料库的语义搜索 · 客户对话与意向度评估 · 销售方案文档自动生成。
          </p>
        </div>

        <div style={{ position: 'relative', zIndex: 2, fontSize: 13, color: '#666' }}>
          © 2026 氢璞 AI · 浦发 IGNITE 未来能源黑客松
        </div>

        {/* 装饰光斑（克制） */}
        <div style={{
          position: 'absolute', top: -120, right: -120,
          width: 360, height: 360, borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(80,140,255,0.18), transparent 70%)',
        }} />
      </div>

      {/* 右侧表单区 */}
      <div style={{
        display: 'grid', placeItems: 'center', padding: 40, background: '#fbfbf7',
      }}>
        <div style={{ width: '100%', maxWidth: 380 }}>
          <Typography.Title level={2} style={{
            marginTop: 0, marginBottom: 8, fontWeight: 600, letterSpacing: -0.5,
          }}>{register ? '创建账号' : '欢迎回来'}</Typography.Title>
          <Typography.Paragraph type="secondary" style={{ marginBottom: 28, fontSize: 14 }}>
            {register ? '使用工作邮箱注册以保存对话与方案。' : '登录以继续使用氢璞 AI。'}
          </Typography.Paragraph>

          <Tabs
            activeKey={register ? 'register' : 'login'}
            onChange={(k) => setRegister(k === 'register')}
            items={[{ key: 'login', label: '登录' }, { key: 'register', label: '注册' }]}
            style={{ marginBottom: 24 }}
          />

          <Input
            size="large" prefix={<UserOutlined style={{ color: '#bbb' }} />}
            placeholder="用户名" value={username} onChange={(e) => setUsername(e.target.value)}
            style={{ marginBottom: 12, borderRadius: 10 }}
          />

          {register && (
            <div style={{ marginBottom: 12 }}>
              <Radio.Group value={userType} onChange={(e) => setUserType(e.target.value)}>
                <Radio value="customer">客户</Radio>
                <Radio value="admin">管理用户</Radio>
              </Radio.Group>
            </div>
          )}

          {register && userType === 'admin' && (
            <Input.Password
              size="large" prefix={<KeyOutlined style={{ color: '#bbb' }} />}
              placeholder="管理注册口令" value={adminCode}
              onChange={(e) => setAdminCode(e.target.value)}
              style={{ marginBottom: 12, borderRadius: 10 }}
            />
          )}

          {register && (
            <Input
              size="large" prefix={<MailOutlined style={{ color: '#bbb' }} />}
              placeholder="邮箱" value={email} onChange={(e) => setEmail(e.target.value)}
              style={{ marginBottom: 12, borderRadius: 10 }}
            />
          )}

          <Input.Password
            size="large" prefix={<LockOutlined style={{ color: '#bbb' }} />}
            placeholder="密码（至少6位）" value={password}
            onChange={(e) => setPassword(e.target.value)}
            onPressEnter={submit}
            style={{ marginBottom: 16, borderRadius: 10 }}
          />

          {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16, borderRadius: 8 }} />}

          <Button
            type="primary" size="large" block loading={loading} onClick={submit}
            style={{
              background: '#0e0e0e', borderColor: '#0e0e0e',
              borderRadius: 10, fontWeight: 500, height: 46,
            }}
          >{register ? '注册并登录' : '登录'}</Button>
        </div>
      </div>
    </div>
  );
}