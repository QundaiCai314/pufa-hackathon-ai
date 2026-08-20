import React, { useState, useRef, useEffect } from 'react';
import { Input, Button, List, Tag, Typography, Spin, Empty, Card, Space, Tooltip } from 'antd';
import { SendOutlined, FileTextOutlined, PictureOutlined, TableOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { documentApi } from '../services/api';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

interface SearchResult {
  score: number;
  text: string;
  doc: string;
  page: number;
  type: string;
  category: string;
  case: string;
  source: string;
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  results?: SearchResult[];
  timestamp: Date;
}

const TYPE_ICONS: Record<string, React.ReactNode> = {
  product_image: <PictureOutlined />,
  table: <TableOutlined />,
  text: <FileTextOutlined />,
  title: <FileTextOutlined />,
  paragraph: <FileTextOutlined />,
};

const TYPE_LABELS: Record<string, string> = {
  product_image: '产品图片',
  table: '表格',
  text: '文本',
  title: '标题',
  paragraph: '段落',
};

const TYPE_COLORS: Record<string, string> = {
  product_image: 'blue',
  table: 'green',
  text: 'default',
  title: 'purple',
  paragraph: 'default',
};

const ChatPage: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const response = await documentApi.ragSearch(userMessage.content, 5);
      
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.results?.length
          ? `找到 ${response.results.length} 个相关内容：`
          : '未找到相关内容，请尝试其他关键词。',
        results: response.results || [],
        timestamp: new Date(),
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (error: any) {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `搜索出错：${error.message}`,
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

  const renderResult = (result: SearchResult, index: number) => {
    const typeLabel = TYPE_LABELS[result.type] || result.type;
    const typeColor = TYPE_COLORS[result.type] || 'default';
    const typeIcon = TYPE_ICONS[result.type] || <FileTextOutlined />;

    return (
      <Card
        key={index}
        size="small"
        style={{ marginBottom: 8 }}
        bodyStyle={{ padding: '12px' }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
          <Space>
            <Tag color={typeColor} icon={typeIcon}>
              {typeLabel}
            </Tag>
            {result.category && <Tag color="orange">{result.category}</Tag>}
            {result.case && <Tag color="cyan">{result.case}</Tag>}
          </Space>
          <Tooltip title="相关度分数">
            <Tag color={result.score > 0.7 ? 'green' : result.score > 0.5 ? 'orange' : 'red'}>
              {(result.score * 100).toFixed(0)}%
            </Tag>
          </Tooltip>
        </div>
        
        <Paragraph style={{ marginBottom: 8 }} ellipsis={{ rows: 3, expandable: true }}>
          {result.text}
        </Paragraph>
        
        <div style={{ fontSize: 12, color: '#888' }}>
          <FileTextOutlined /> {result.doc} · 第 {result.page} 页
          {result.source && (
            <span style={{ marginLeft: 8 }}>
              <a href={result.source} target="_blank" rel="noopener noreferrer">
                查看原图
              </a>
            </span>
          )}
        </div>
      </Card>
    );
  };

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', height: 'calc(100vh - 200px)', display: 'flex', flexDirection: 'column' }}>
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 0' }}>
        {messages.length === 0 ? (
          <Empty
            description="输入问题开始搜索"
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
                }}
              >
                <div
                  style={{
                    maxWidth: '80%',
                    padding: '12px 16px',
                    borderRadius: 12,
                    background: msg.role === 'user' ? '#1890ff' : '#f5f5f5',
                    color: msg.role === 'user' ? '#fff' : '#333',
                  }}
                >
                  <div style={{ marginBottom: msg.results ? 12 : 0 }}>{msg.content}</div>
                  {msg.results && msg.results.length > 0 && (
                    <div>
                      {msg.results.map((r, i) => renderResult(r, i))}
                    </div>
                  )}
                </div>
              </List.Item>
            )}
          />
        )}
        {loading && (
          <div style={{ textAlign: 'center', padding: 20 }}>
            <Spin tip="搜索中..." />
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
            placeholder="输入问题搜索文档内容（Enter 发送，Shift+Enter 换行）"
            autoSize={{ minRows: 1, maxRows: 4 }}
            style={{ flex: 1 }}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            loading={!input.trim() || loading}
          >
            发送
          </Button>
        </Space.Compact>
      </div>
    </div>
  );
};

export default ChatPage;
