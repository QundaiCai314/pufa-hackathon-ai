import React, { useEffect, useState } from 'react';
import { ConfigProvider, Layout, Typography, Spin, Alert, Menu } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import {
  HomeOutlined, FileTextOutlined,
} from '@ant-design/icons';
import axios from 'axios';
import DocumentsPage from './pages/Documents';
import './App.css';

const { Header, Content, Footer, Sider } = Layout;
const { Title, Paragraph } = Typography;

interface SystemInfo {
  status?: string;
  message?: string;
  version?: string;
  app_name?: string;
  company?: string;
  description?: string;
  features?: string[];
}

const HomePage: React.FC = () => {
  const [systemInfo, setSystemInfo] = useState<SystemInfo>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:8000';
        const rootResponse = await axios.get(`${apiUrl}/`);
        const infoResponse = await axios.get(`${apiUrl}/api/v1/info`);
        setSystemInfo({ ...rootResponse.data, ...infoResponse.data });
        setLoading(false);
      } catch (err: any) {
        setError(err.message || '无法连接到后端服务');
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '100px 0' }}>
        <Spin size="large" />
        <Paragraph style={{ marginTop: 20 }}>正在连接后端服务...</Paragraph>
      </div>
    );
  }

  if (error) {
    return (
      <Alert
        message="连接失败"
        description={`无法连接到后端服务: ${error}`}
        type="error"
        showIcon
      />
    );
  }

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto' }}>
      <Alert
        message="🎉 系统运行正常"
        description={
          <div>
            <Paragraph><strong>版本：</strong>{systemInfo.version} | <strong>环境：</strong>Docker 全栈部署</Paragraph>
            <Paragraph><strong>企业：</strong>{systemInfo.company}</Paragraph>
            <Paragraph><strong>描述：</strong>{systemInfo.description}</Paragraph>
            {systemInfo.features && (
              <div>
                <strong>核心功能：</strong>
                <ul style={{ marginTop: 8 }}>
                  {systemInfo.features.map((f, i) => <li key={i}>{f}</li>)}
                </ul>
              </div>
            )}
          </div>
        }
        type="success"
        showIcon
      />
    </div>
  );
};

const App: React.FC = () => {
  const [currentPage, setCurrentPage] = useState('home');

  return (
    <ConfigProvider locale={zhCN}>
      <Layout style={{ minHeight: '100vh' }}>
        <Header style={{ display: 'flex', alignItems: 'center' }}>
          <Title level={3} style={{ color: 'white', margin: 0, marginRight: 40 }}>
            氢璞 AI 智能助手
          </Title>
          <Menu
            theme="dark"
            mode="horizontal"
            selectedKeys={[currentPage]}
            onClick={({ key }) => setCurrentPage(key)}
            items={[
              { key: 'home', icon: <HomeOutlined />, label: '首页' },
              { key: 'documents', icon: <FileTextOutlined />, label: '文档管理' },
            ]}
            style={{ flex: 1, minWidth: 0 }}
          />
        </Header>

        <Content style={{ padding: '24px 24px' }}>
          {currentPage === 'home' && <HomePage />}
          {currentPage === 'documents' && <DocumentsPage />}
        </Content>

        <Footer style={{ textAlign: 'center' }}>
          氢璞 AI 智能助手 ©2026 - 浦发·IGNITE 未来能源黑客松
        </Footer>
      </Layout>
    </ConfigProvider>
  );
};

export default App;
