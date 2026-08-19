import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Table, Button, Upload, message, Modal, Tag, Typography,
  Empty, Descriptions, List, Space, Progress, Badge, Image as AntImage,
  Tooltip, Select, Spin, Alert, Tabs,
} from 'antd';
import {
  UploadOutlined, FilePdfOutlined, EyeOutlined, ReloadOutlined,
  CheckCircleOutlined, CloseCircleOutlined, LoadingOutlined,
  ThunderboltOutlined, TableOutlined, UnorderedListOutlined,
  PhoneOutlined, AppstoreOutlined,
} from '@ant-design/icons';
import { documentApi, type DocumentInfo, type ClassifiedContent } from '../services/api';

const { Title, Text, Paragraph } = Typography;

const PAGE_TYPE_LABELS: Record<string, string> = {
  cover: '封面',
  product_spec: '产品参数',
  company_intro: '企业介绍',
  solution: '解决方案',
  other: '其他',
};

const DocumentsPage: React.FC = () => {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState<string | null>(null);
  const [detailModal, setDetailModal] = useState(false);
  const [detailFilename, setDetailFilename] = useState('');
  const [classified, setClassified] = useState<ClassifiedContent | null>(null);
  const [classifiedLoading, setClassifiedLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('overview');

  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await documentApi.list();
      setDocuments(resp.documents || []);
    } catch (err: any) {
      message.error('获取文档列表失败: ' + err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchDocuments(); }, [fetchDocuments]);

  const handleUpload = async (file: File) => {
    setUploading(true);
    try {
      await documentApi.upload(file);
      message.success(`${file.name} 上传成功`);
      fetchDocuments();
    } catch (err: any) {
      message.error('上传失败: ' + err.message);
    } finally {
      setUploading(false);
    }
    return false;
  };

  const handleAnalyze = async (filename: string) => {
    setAnalyzing(filename);
    try {
      message.loading({ content: 'GPT-5.6 Luna 正在逐页分析...', key: 'analyze', duration: 0 });
      const result = await documentApi.analyze(filename);
      message.success({ content: `分析完成: ${result.total_pages} 页, ${result.total_tokens} tokens`, key: 'analyze' });
      fetchDocuments();
    } catch (err: any) {
      message.error({ content: '分析失败: ' + err.message, key: 'analyze' });
    } finally {
      setAnalyzing(null);
    }
  };

  const handleViewContent = async (filename: string) => {
    setDetailFilename(filename);
    setDetailModal(true);
    setActiveTab('overview');
    setClassified(null);
    setClassifiedLoading(true);
    try {
      const result = await documentApi.getClassified(filename);
      setClassified(result);
    } catch (err: any) {
      // If not analyzed yet, show prompt
      message.warning('该文档尚未进行 GPT 分析，请先点击"AI分析"');
    } finally {
      setClassifiedLoading(false);
    }
  };

  const columns = [
    {
      title: '文件名', dataIndex: 'filename', key: 'filename',
      render: (text: string) => (
        <Space><FilePdfOutlined style={{ color: '#ff4d4f' }} /><Text copyable>{text}</Text></Space>
      ),
    },
    {
      title: '大小', dataIndex: 'file_size', key: 'file_size',
      render: (s: number) => s < 1048576 ? `${(s/1024).toFixed(1)} KB` : `${(s/1048576).toFixed(2)} MB`,
    },
    {
      title: '状态', dataIndex: 'parsed', key: 'parsed',
      render: (p: boolean) => p ? <Tag icon={<CheckCircleOutlined />} color="success">已解析</Tag> : <Tag icon={<CloseCircleOutlined />}>未解析</Tag>,
    },
    {
      title: '操作', key: 'action',
      render: (_: any, r: DocumentInfo) => (
        <Space>
          <Button type="primary" size="small" icon={<ThunderboltOutlined />}
            loading={analyzing === r.filename}
            onClick={() => handleAnalyze(r.filename)}>
            AI分析
          </Button>
          <Button size="small" icon={<EyeOutlined />}
            onClick={() => handleViewContent(r.filename)}>
            查看
          </Button>
        </Space>
      ),
    },
  ];

  // ============ 渲染分类内容 ============

  const renderOverview = () => {
    if (!classified) return <Empty description="无数据" />;
    return (
      <Space direction="vertical" style={{ width: '100%' }} size={16}>
        <Descriptions bordered column={3} size="small">
          <Descriptions.Item label="产品大类">{classified.product_groups.length}</Descriptions.Item>
          <Descriptions.Item label="具体型号">{classified.product_groups.reduce((s, g) => s + g.spec_products.length, 0)}</Descriptions.Item>
          <Descriptions.Item label="表格">{classified.tables.length}</Descriptions.Item>
          <Descriptions.Item label="产品图片">{classified.product_images.length}</Descriptions.Item>
          <Descriptions.Item label="Token消耗">{classified.summary.total_tokens}</Descriptions.Item>
        </Descriptions>

        {classified.contact_info && (
          <Card size="small" title={<Space><PhoneOutlined /> 联系信息</Space>}>
            <Descriptions column={1} size="small">
              {classified.contact_info.address && <Descriptions.Item label="地址">{classified.contact_info.address}</Descriptions.Item>}
              {classified.contact_info.phone && <Descriptions.Item label="电话">{classified.contact_info.phone}</Descriptions.Item>}
              {classified.contact_info.website && <Descriptions.Item label="网址">{classified.contact_info.website}</Descriptions.Item>}
              {classified.contact_info.email && <Descriptions.Item label="邮箱">{classified.contact_info.email}</Descriptions.Item>}
            </Descriptions>
          </Card>
        )}

        <Card size="small" title="产品大类总览">
          <List size="small" dataSource={classified.product_groups} renderItem={(group) => (
            <List.Item>
              <Space>
                <Tag color="blue">{group.category_name}</Tag>
                <Text type="secondary">P{group.category_page}</Text>
                {group.spec_page && <Text type="secondary">→ P{group.spec_page}</Text>}
                <Badge count={group.spec_products.length} style={{ backgroundColor: '#1890ff' }} />
              </Space>
            </List.Item>
          )} />
        </Card>
      </Space>
    );
  };

  const renderProducts = () => {
    if (!classified || classified.product_groups.length === 0) return <Empty description="无产品参数" />;
    
    // 统计所有型号数
    const totalModels = classified.product_groups.reduce((sum, g) => sum + g.spec_products.length, 0);
    
    return (
      <Space direction="vertical" style={{ width: '100%' }} size={24}>
        <Alert message={`共 ${classified.product_groups.length} 个产品大类，${totalModels} 个具体型号`} type="info" showIcon />
        {classified.product_groups.map((group, idx) => (
          <Card
            key={idx}
            size="small"
            title={
              <Space>
                <Tag color="blue" style={{ fontSize: 14, padding: '4px 12px' }}>{group.category_name}</Tag>
                {group.en_name && <Text type="secondary" style={{ fontSize: 13 }}>{group.en_name}</Text>}
                <Text type="secondary">P{group.category_page}</Text>
                {group.spec_page && <Text type="secondary">参数页 P{group.spec_page}</Text>}
                <Badge count={group.spec_products.length} />
              </Space>
            }
          >
            {/* 产品特点 */}
            {group.features && group.features.length > 0 && (
              <div style={{ marginBottom: 12, padding: 12, background: '#f6ffed', borderRadius: 8, border: '1px solid #b7eb8f' }}>
                <Text strong style={{ color: '#52c41a' }}>产品特点</Text>
                <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {group.features.map((f, i) => (
                    <Tag key={i} color="green" style={{ fontSize: 13, padding: '2px 10px' }}>{f}</Tag>
                  ))}
                </div>
              </div>
            )}
            
            {/* 具体型号参数表 */}
            {group.spec_products.length > 0 && (
              <div>
                <Text strong style={{ color: '#1890ff' }}>具体型号参数</Text>
                {group.spec_products.map((p, i) => (
                  <div key={i} style={{ marginTop: 8, padding: 12, background: '#fafafa', borderRadius: 8 }}>
                    <Space style={{ marginBottom: 8 }}>
                      <Tag color="blue" style={{ fontSize: 13 }}>{p.model}</Tag>
                      {p.category && <Tag>{p.category}</Tag>}
                    </Space>
                    <Descriptions column={2} size="small" bordered>
                      {Object.entries(p.specs || {}).map(([k, v]) => (
                        <Descriptions.Item key={k} label={k}>{v}</Descriptions.Item>
                      ))}
                    </Descriptions>
                  </div>
                ))}
              </div>
            )}
            
            {group.spec_products.length === 0 && group.intro_products.length === 0 && (
              <Text type="secondary">（无详细参数）</Text>
            )}
          </Card>
        ))}
      </Space>
    );
  };

  const renderTables = () => {
    if (!classified || classified.tables.length === 0) return <Empty description="无表格" />;
    return (
      <Space direction="vertical" style={{ width: '100%' }} size={16}>
        {classified.tables.map((table, idx) => (
          <Card key={idx} size="small" title={`${table.title || '表格'} - 第${table.page}页`}>
            <Table
              size="small"
              bordered
              pagination={false}
              dataSource={table.rows.map((row, i) => ({ key: i, ...Object.fromEntries(row.map((v, j) => [table.headers[j] || `col${j}`, v])) }))}
              columns={table.headers.map((h, j) => ({ title: h, dataIndex: h || `col${j}`, key: h || `col${j}` }))}
            />
          </Card>
        ))}
      </Space>
    );
  };

  const renderImages = () => {
    if (!classified || classified.product_images.length === 0) return <Empty description="无产品图片" />;
    
    // 按 product_group 的介绍页配对图片
    const introPages = classified.product_groups.map(g => g.category_page);
    
    return (
      <Space direction="vertical" style={{ width: '100%' }} size={24}>
        <Alert message={`共 ${classified.product_images.length} 张产品图片，点击可放大`} type="info" showIcon />
        {classified.product_groups.map((group) => {
          // 找该大类的图片（介绍页上的图片）
          const groupImgs = classified.product_images.filter(img => img.page === group.category_page);
          if (groupImgs.length === 0) return null;
          
          return (
            <Card
              key={group.category_page}
              size="small"
              title={
                <Space>
                  <Tag color="blue" style={{ fontSize: 14 }}>{group.category_name}</Tag>
                  <Text type="secondary">P{group.category_page}</Text>
                </Space>
              }
            >
              <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                {groupImgs.map((img) => (
                  <div key={img.index} style={{ width: 300 }}>
                    <AntImage
                      src={`${process.env.REACT_APP_API_URL || 'http://localhost:8000'}${encodeURI(img.url)}`}
                      alt={img.description || `P${img.page}图${img.index}`}
                      style={{ width: '100%', borderRadius: 8, border: '1px solid #f0f0f0' }}
                      placeholder={
                        <div style={{ width: '100%', height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#fafafa', borderRadius: 8 }}>
                          <Spin size="large" />
                        </div>
                      }
                    />
                    {img.description && (
                      <Paragraph style={{ marginTop: 8, marginBottom: 0, fontSize: 12, color: '#666' }}>
                        {img.description}
                      </Paragraph>
                    )}
                  </div>
                ))}
              </div>
            </Card>
          );
        })}
      </Space>
    );
  };

  // ============ Tab 配置 ============
  const tabItems = classified ? [
    { key: 'overview', label: <Space><AppstoreOutlined /> 概览</Space>, children: renderOverview() },
    { key: 'products', label: <Space><ThunderboltOutlined /> 产品参数 ({classified.product_groups.reduce((s, g) => s + g.spec_products.length, 0)})</Space>, children: renderProducts() },
    { key: 'tables', label: <Space><TableOutlined /> 表格 ({classified.tables.length})</Space>, children: renderTables() },
    { key: 'images', label: <Space><FilePdfOutlined /> 产品图片 ({classified.product_images.length})</Space>, children: renderImages() },
  ] : [];

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      <Card
        title={<Title level={4}>📄 文档管理</Title>}
        extra={
          <Space>
            <Upload accept=".pdf" showUploadList={false} beforeUpload={handleUpload}>
              <Button icon={<UploadOutlined />} loading={uploading}>上传 PDF</Button>
            </Upload>
            <Button icon={<ReloadOutlined />} onClick={fetchDocuments} loading={loading}>刷新</Button>
          </Space>
        }
      >
        {analyzing && (
          <Card size="small" style={{ marginBottom: 16 }}>
            <Space direction="vertical" style={{ width: '100%' }}>
              <Space><LoadingOutlined spin /><Text>GPT-5.6 Luna 正在分析: {analyzing}</Text></Space>
              <Progress percent={95} status="active" />
              <Text type="secondary">逐页视觉识别中，18页约需3-5分钟...</Text>
            </Space>
          </Card>
        )}

        <Alert
          style={{ marginBottom: 16 }}
          message="使用 GPT-5.6 Luna 多模态视觉模型分析 PDF"
          description="点击「AI分析」按钮，Luna 将逐页识别产品参数、表格、图片类型，替代 MinerU OCR。"
          type="info"
          showIcon
        />

        <Table
          columns={columns}
          dataSource={documents}
          rowKey="filename"
          loading={loading}
          pagination={false}
        />
      </Card>

      {/* 内容浏览弹窗 */}
      <Modal
        title={`内容浏览: ${detailFilename}`}
        open={detailModal}
        onCancel={() => { setDetailModal(false); setClassified(null); }}
        footer={null}
        width={1100}
        styles={{ body: { maxHeight: '75vh', overflow: 'auto' } }}
      >
        {classifiedLoading ? (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <Spin size="large" />
            <Paragraph style={{ marginTop: 16 }}>正在加载分析结果...</Paragraph>
          </div>
        ) : classified ? (
          <Tabs items={tabItems} activeKey={activeTab} onChange={setActiveTab} />
        ) : (
          <Empty description="请先点击「AI分析」按钮进行分析" >
            <Button type="primary" icon={<ThunderboltOutlined />}
              loading={analyzing === detailFilename}
              onClick={() => handleAnalyze(detailFilename)}>
              开始 AI 分析
            </Button>
          </Empty>
        )}
      </Modal>
    </div>
  );
};

export default DocumentsPage;
