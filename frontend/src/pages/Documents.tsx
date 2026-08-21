import React, { useState, useEffect, useRef } from 'react';
import {
  Button, Empty, Spin, Typography, Tabs, Tag, Table, Alert, App as AntApp,
  Space, Image as AntImage,
} from 'antd';
import {
  UploadOutlined, FileTextOutlined, EyeOutlined,
  RocketOutlined, AppstoreOutlined, PictureOutlined, TableOutlined,
  ApartmentOutlined,
} from '@ant-design/icons';

const { Title, Text, Paragraph } = Typography;

const API = process.env.REACT_APP_API_URL || 'http://localhost:8000';

interface DocumentItem {
  filename: string;
  file_size: number;
  parsed: boolean;
  indexed: boolean;
  upload_time?: string;
  analyzed?: boolean;
  page_count?: number;
  has_vector_index?: boolean;
  chunk_count?: number;
}

interface ProductGroup {
  category_name: string;
  category_page: number;
  en_name: string;
  features: string[];
  intro_products: { model: string; category: string; specs: Record<string, string>; page: number }[];
  spec_products: { model: string; category: string; specs: Record<string, string>; page: number }[];
  spec_page: number | null;
  images?: { url: string; description: string; page: number; width?: number; height?: number }[];
  subsections?: { type: string; content: string }[];
  raw_text?: string;
  image_count?: number;
}

interface ProductImage {
  page: number;
  index: number;
  width: number;
  height: number;
  description: string;
  url: string;
}

interface TableBlock {
  title: string;
  headers: string[];
  rows: string[][];
  page: number;
}

interface ClassifiedContent {
  product_groups?: ProductGroup[];
  tables?: TableBlock[];
  product_images?: ProductImage[];
  contact_info?: { address?: string; phone?: string; website?: string; email?: string } | null;
  summary?: { total_pages?: number; total_tokens?: number; total_images?: number };
}

export default function Documents({ auth, isAdmin }: { auth: any; isAdmin: boolean }) {
  const { message } = AntApp.useApp();
  const token = auth?.token;
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [classified, setClassified] = useState<ClassifiedContent | null>(null);
  const [activeTab, setActiveTab] = useState('groups');
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const authHeaders = {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  const loadDocs = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/v1/documents/list`, { headers: authHeaders });
      if (!res.ok) throw new Error('加载列表失败');
      const data = await res.json();
      setDocs(data.documents || []);
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  const loadClassified = async (filename: string) => {
    try {
      const res = await fetch(
        `${API}/api/v1/documents/classified/${encodeURIComponent(filename)}`,
        { headers: authHeaders },
      );
      if (!res.ok) throw new Error('加载分析结果失败');
      const data: ClassifiedContent = await res.json();
      setClassified(data);
    } catch (e: any) {
      message.error(e.message);
      setClassified(null);
    }
  };

  useEffect(() => {
    loadDocs();
  }, [token]);

  const handleFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        if (!file.name.toLowerCase().endsWith('.pdf')) {
          message.warning(`${file.name} 不是 PDF，已跳过`);
          continue;
        }
        const formData = new FormData();
        formData.append('file', file);
        const res = await fetch(`${API}/api/v1/documents/upload`, {
          method: 'POST', body: formData, headers: authHeaders,
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || '上传失败');
        }
        const data = await res.json();
        message.success(`已上传 ${file.name}`);

        // 自动触发解析
        await fetch(`${API}/api/v1/documents/parse?filename=${encodeURIComponent(file.name)}&parse_mode=auto`, {
          method: 'POST', headers: authHeaders,
        });
        message.success(`已解析 ${file.name}`);
      }
      await loadDocs();
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setUploading(false);
    }
  };

  const handleAnalyze = async (filename: string) => {
    setAnalyzing(filename);
    try {
      const res = await fetch(
        `${API}/api/v1/documents/analyze/${encodeURIComponent(filename)}`,
        { method: 'POST', headers: authHeaders },
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || '启动分析失败');
      }
      message.success('已启动 AI 分析，请稍候');

      // 轮询状态
      const poll = setInterval(async () => {
        try {
          const sres = await fetch(
            `${API}/api/v1/documents/analysis_status/${encodeURIComponent(filename)}`,
            { headers: authHeaders },
          );
          const sd = await sres.json();
          if (sd.status === 'completed' || sd.status === 'failed') {
            clearInterval(poll);
            setAnalyzing(null);
            if (sd.status === 'completed') {
              message.success('AI 分析完成');
              await loadDocs();
              if (selected === filename) await loadClassified(filename);
            } else {
              message.error('分析失败：' + (sd.error || ''));
            }
          }
        } catch {
          clearInterval(poll);
          setAnalyzing(null);
        }
      }, 3000);
    } catch (e: any) {
      message.error(e.message);
      setAnalyzing(null);
    }
  };

  const handleIndex = async (filename: string) => {
    try {
      const res = await fetch(
        `${API}/api/v1/rag/index/${encodeURIComponent(filename)}`,
        { method: 'POST', headers: authHeaders },
      );
      if (!res.ok) throw new Error('索引失败');
      const data = await res.json();
      if (data.status === 'already_indexed') {
        message.info('该文档已索引，无需重复操作');
      } else {
        message.success('已加入向量索引，可在问答中使用');
      }
      await loadDocs();
    } catch (e: any) {
      message.error(e.message);
    }
  };

  const openDoc = async (filename: string) => {
    setSelected(filename);
    setClassified(null);
    await loadClassified(filename);
  };

  const formatBytes = (n: number) => {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1024 / 1024).toFixed(2)} MB`;
  };

  // 详情面板
  if (selected && classified) {
    const groups = classified.product_groups || [];
    const tables = classified.tables || [];
    const images = classified.product_images || [];

    return (
      <div style={{ padding: '32px 40px', maxWidth: 980, margin: '0 auto' }}>
        <Space style={{ marginBottom: 18 }}>
          <Button onClick={() => { setSelected(null); setClassified(null); }}>← 返回列表</Button>
          <Title level={4} style={{ margin: 0 }}>{selected}</Title>
        </Space>

        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24,
        }}>
          {[
            { label: '章节', value: groups.length, icon: <AppstoreOutlined /> },
            { label: '产品图片', value: images.length, icon: <PictureOutlined /> },
            { label: '表格', value: tables.length, icon: <TableOutlined /> },
            { label: '关键特性', value: groups.reduce((s, g) => s + (g.features?.length || 0), 0), icon: <RocketOutlined /> },
          ].map((s, i) => (
            <div key={i} style={{
              background: '#fff', border: '1px solid #ecece4', borderRadius: 12, padding: '16px 18px',
            }}>
              <div style={{ fontSize: 12, color: '#9c9b96', display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                {s.icon} {s.label}
              </div>
              <div style={{ fontSize: 24, fontWeight: 600 }}>{s.value}</div>
            </div>
          ))}
        </div>

        <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
          {
            key: 'groups', label: '内容概览',
            children: groups.length === 0 ? <Empty description="暂无内容" /> : (
              <div>
                {/* 封面/标题区 */}
                {groups[0] && (
                  <div style={{
                    background: 'linear-gradient(135deg, #f0f7f4 0%, #e8f4f8 100%)',
                    borderRadius: 16, padding: '32px 36px', marginBottom: 24,
                  }}>
                    <Title level={2} style={{ margin: 0, fontWeight: 600 }}>{groups[0].category_name}</Title>
                    {groups[0].en_name && <Text style={{ fontSize: 14, color: '#6b7280' }}>{groups[0].en_name}</Text>}
                    {groups[0].raw_text && (
                      <Paragraph style={{ marginTop: 16, fontSize: 14, color: '#4b5563', lineHeight: 1.8 }}>
                        {groups[0].raw_text.substring(0, 300)}
                      </Paragraph>
                    )}
                  </div>
                )}

                {/* 内容卡片流 */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
                  {groups.slice(1).map((g, i) => (
                    <div key={i} style={{
                      background: '#fff', border: '1px solid #e5e7eb', borderRadius: 12, padding: '20px 24px',
                      transition: 'box-shadow 0.2s',
                    }}>
                      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 8 }}>
                        <Title level={5} style={{ margin: 0, fontWeight: 600, flex: 1 }}>{g.category_name}</Title>
                        {g.en_name && <Tag style={{ fontSize: 11, marginLeft: 8, flexShrink: 0 }}>{g.en_name}</Tag>}
                      </div>
                      {g.features?.length > 0 && (
                        <div style={{ marginBottom: 12 }}>
                          {g.features.slice(0, 3).map((f, j) => (
                            <div key={j} style={{ fontSize: 13, color: '#374151', marginBottom: 4, display: 'flex', gap: 6 }}>
                              <span style={{ color: '#10b981', flexShrink: 0 }}>•</span>
                              <span>{f}</span>
                            </div>
                          ))}
                          {g.features.length > 3 && (
                            <Text type="secondary" style={{ fontSize: 12 }}>+{g.features.length - 3} 项</Text>
                          )}
                        </div>
                      )}
                      {g.raw_text && g.raw_text.length > 10 && (
                        <Paragraph style={{ fontSize: 13, color: '#6b7280', lineHeight: 1.7 }} ellipsis={{ rows: 4 }}>
                          {g.raw_text}
                        </Paragraph>
                      )}
                      {(g.images || []).length > 0 && (
                        <div style={{ marginTop: 12, display: 'grid', gridTemplateColumns: `repeat(${Math.min((g.images || []).length, 3)}, 1fr)`, gap: 6 }}>
                          {(g.images || []).slice(0, 3).map((img, j) => (
                            <AntImage
                              key={j}
                              src={`${API}${img.url}`}
                              alt={img.description}
                              style={{ width: '100%', borderRadius: 6, aspectRatio: '1', objectFit: 'cover' }}
                              fallback="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='100' height='100'%3E%3Crect width='100' height='100' fill='%23f0f0f0'/%3E%3Ctext x='50' y='50' text-anchor='middle' dy='.3em' fill='%23999' font-size='12'%3E无图片%3C/text%3E%3C/svg%3E"
                            />
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ),
          },
          {
            key: 'tables', label: '表格',
            children: tables.length === 0 ? <Empty description="暂无表格" /> : (
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                {tables.map((t, i) => (
                  <div key={i} style={{
                    background: '#fff', border: '1px solid #ecece4', borderRadius: 12, padding: 20,
                  }}>
                    <div style={{ marginBottom: 10, fontWeight: 500 }}>{t.title || `表格 (P${t.page})`}</div>
                    <Table
                      size="small" pagination={false}
                      dataSource={t.rows.map((r, j) => ({ key: j, ...Object.fromEntries(r.map((v, k) => [t.headers[k] || `col${k}`, v])) }))}
                      columns={t.headers.map((h, j) => ({ title: h, dataIndex: h || `col${j}`, key: h || `col${j}` }))}
                      scroll={{ x: 'max-content' }}
                    />
                  </div>
                ))}
              </Space>
            ),
          },
          {
            key: 'images', label: '产品图片',
            children: images.length === 0 ? <Empty description="暂无产品图片" /> : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}>
                {images.map((img, i) => (
                  <div key={i} style={{
                    background: '#fff', border: '1px solid #ecece4', borderRadius: 12,
                    padding: 12,
                  }}>
                    <AntImage
                      src={img.url ? `${API}${img.url}` : `${API}/api/v1/documents/image/${encodeURIComponent(selected!)}?page=${img.page}&index=${img.index}`}
                      alt={img.description}
                      style={{ width: '100%', borderRadius: 8 }}
                      fallback="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='100' height='100'%3E%3Crect width='100' height='100' fill='%23f0f0f0'/%3E%3Ctext x='50' y='50' text-anchor='middle' dy='.3em' fill='%23999' font-size='12'%3E无图片%3C/text%3E%3C/svg%3E"
                    />
                    <Paragraph style={{ marginTop: 10, marginBottom: 0, fontSize: 13, color: '#5f5e5a' }} ellipsis={{ rows: 3 }}>
                      {img.description || '产品图片'}
                    </Paragraph>
                    <div style={{ fontSize: 11, color: '#9c9b96', marginTop: 4 }}>P{img.page} · {img.width}×{img.height}</div>
                  </div>
                ))}
              </div>
            ),
          },
        ]} />
      </div>
    );
  }

  // 列表面板
  return (
    <div style={{ padding: '32px 40px', maxWidth: 1080, margin: '0 auto' }}>
      <Title level={3} style={{ marginTop: 0, fontWeight: 600, letterSpacing: -0.5 }}>
        企业知识库
      </Title>
      <Paragraph type="secondary" style={{ marginBottom: 28 }}>
        上传氢璞资料，AI 自动解析、视觉分析与向量化索引。
      </Paragraph>

      {/* 上传区 */}
      <div
        onClick={() => fileInputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files); }}
        style={{
          border: `2px dashed ${dragOver ? '#111' : '#ecece4'}`,
          borderRadius: 14, padding: '36px 24px',
          textAlign: 'center', cursor: 'pointer',
          background: dragOver ? '#f0eee6' : '#fff',
          transition: 'all 0.15s', marginBottom: 24,
        }}
      >
        <UploadOutlined style={{ fontSize: 28, color: '#9c9b96', marginBottom: 10 }} />
        <div style={{ fontWeight: 500, marginBottom: 4 }}>点击或拖拽 PDF 文件到此处</div>
        <Text type="secondary" style={{ fontSize: 13 }}>上传后自动触发解析与视觉分析</Text>
        <input
          ref={fileInputRef} type="file" multiple accept=".pdf"
          style={{ display: 'none' }}
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {uploading && <Alert message="正在上传并解析..." type="info" showIcon style={{ marginBottom: 16 }} />}

      {loading ? (
        <div style={{ textAlign: 'center', padding: 60 }}><Spin /></div>
      ) : docs.length === 0 ? (
        <Empty description="暂无文档，请先上传" />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14 }}>
          {docs.map((d) => (
            <div key={d.filename} style={{
              background: '#fff', border: '1px solid #ecece4', borderRadius: 12, padding: 18,
              display: 'flex', flexDirection: 'column', gap: 10,
            }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                <FileTextOutlined style={{ color: '#5f5e5a', fontSize: 20, marginTop: 2 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontWeight: 500, fontSize: 14,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>{d.filename}</div>
                  <div style={{ fontSize: 12, color: '#9c9b96' }}>{formatBytes(d.file_size)}</div>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {d.parsed && <Tag color="default" style={{ borderRadius: 6 }}>已解析</Tag>}
                {d.parsed && <Tag color="green" style={{ borderRadius: 6 }}>AI 分析</Tag>}
                {d.indexed && <Tag color="blue" style={{ borderRadius: 6 }}>已索引</Tag>}
                {d.has_vector_index && <Tag color="blue" style={{ borderRadius: 6 }}>向量索引</Tag>}
              </div>
              <div style={{ display: 'flex', gap: 6, marginTop: 'auto' }}>
                <Button
                  size="small" icon={<EyeOutlined />}
                  onClick={() => openDoc(d.filename)}
                  disabled={!d.parsed}
                >查看</Button>
                <Button
                  size="small" icon={<RocketOutlined />}
                  loading={analyzing === d.filename}
                  onClick={() => handleAnalyze(d.filename)}
                  disabled={!d.parsed}
                >{d.parsed ? '重新分析' : 'AI 分析'}</Button>
                <Button
                  size="small" icon={<ApartmentOutlined />}
                  onClick={() => handleIndex(d.filename)}
                  disabled={!d.parsed || d.indexed}
                >{d.indexed ? '已索引' : '索引'}</Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}