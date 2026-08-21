import React from 'react';
import { Typography, Button, Space, Card } from 'antd';
import {
  MessageOutlined, FileSearchOutlined, RobotOutlined,
  SolutionOutlined, ApiOutlined, FileTextOutlined,
} from '@ant-design/icons';

const { Title, Paragraph } = Typography;

interface Props {
  auth: any;
  onStartChat: (preset?: string) => void;
  onOpenDocs: () => void;
}

export default function Home({ auth, onStartChat, onOpenDocs }: Props) {
  const isAdmin = !!auth?.user?.is_admin;
  const username = auth?.user?.username || '';

  const suggestions = [
    { icon: <SolutionOutlined />, label: '产品对比与选型', prompt: '请对比氢璞主营产品族的型号、应用场景与核心参数差异。' },
    { icon: <FileSearchOutlined />, label: '查技术参数', prompt: '请告诉我氢璞产品的电堆功率、寿命与工况范围。' },
    { icon: <ApiOutlined />, label: '方案与案例', prompt: '请列举氢璞在交通、能源等场景的落地案例与客户收益。' },
    { icon: <RobotOutlined />, label: '我要找客服', prompt: '我需要联系人工客服处理订单和售前问题。' },
  ];

  return (
    <div style={{
      maxWidth: 820, margin: '0 auto', padding: '60px 32px 120px',
      color: '#191919',
    }}>
      <div style={{ marginBottom: 8, color: '#9c9b96', fontSize: 14 }}>
        {new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })}
      </div>
      <Title style={{
        fontSize: 44, fontWeight: 600, letterSpacing: -1.2,
        margin: 0, marginBottom: 14, lineHeight: 1.15,
      }}>{isAdmin ? `晚上好，${username}` : `你好，${username}`}</Title>
      <Paragraph style={{ fontSize: 17, color: '#5f5e5a', marginBottom: 44, lineHeight: 1.6, maxWidth: 620 }}>
        基于氢璞企业资料库的智能问答与销售助理。下面是几个常用入口，也可以直接提问。
      </Paragraph>

      <Space direction="vertical" size={20} style={{ width: '100%' }}>
        <Card
          hoverable
          onClick={() => onStartChat()}
          style={{
            borderRadius: 14, border: '1px solid #ecece4',
            background: '#fff', cursor: 'pointer',
          }}
          styles={{ body: { padding: 22 } }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
            <div style={{
              width: 48, height: 48, borderRadius: 12,
              background: '#0e0e0e', color: '#fff',
              display: 'grid', placeItems: 'center', fontSize: 22,
            }}><MessageOutlined /></div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, fontSize: 16, marginBottom: 4 }}>开始一次智能问答</div>
              <div style={{ fontSize: 13, color: '#7a7973' }}>支持企业资料检索、联网补充与角色化回复</div>
            </div>
            <Button type="text" icon={<MessageOutlined />} />
          </div>
        </Card>

        <Card
          hoverable
          onClick={onOpenDocs}
          style={{
            borderRadius: 14, border: '1px solid #ecece4',
            background: '#fff', cursor: 'pointer',
          }}
          styles={{ body: { padding: 22 } }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
            <div style={{
              width: 48, height: 48, borderRadius: 12,
              background: '#f0eee6', color: '#0e0e0e',
              display: 'grid', placeItems: 'center', fontSize: 22,
            }}><FileTextOutlined /></div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, fontSize: 16, marginBottom: 4 }}>管理企业知识库</div>
              <div style={{ fontSize: 13, color: '#7a7973' }}>上传 PDF · AI 解析 · 自动向量化检索</div>
            </div>
            <Button type="text" icon={<FileTextOutlined />} />
          </div>
        </Card>
      </Space>

      <div style={{ marginTop: 52, marginBottom: 18, fontSize: 13, color: '#9c9b96', letterSpacing: 0.5, textTransform: 'uppercase' }}>
        推荐提问
      </div>
      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12,
      }}>
        {suggestions.map((s, i) => (
          <Card
            key={i}
            hoverable
            onClick={() => onStartChat(s.prompt)}
            style={{
              borderRadius: 12, border: '1px solid #ecece4',
              background: '#fff',
            }}
            styles={{ body: { padding: '16px 18px' } }}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
              <div style={{ color: '#5f5e5a', fontSize: 16, marginTop: 2 }}>{s.icon}</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 500, fontSize: 14, marginBottom: 4 }}>{s.label}</div>
                <div style={{ fontSize: 12, color: '#9c9b96', lineHeight: 1.5 }}>{s.prompt}</div>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}