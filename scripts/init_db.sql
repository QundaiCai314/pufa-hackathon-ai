-- 数据库初始化脚本
-- 创建扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 创建内容表（多态表，存储所有类型的内容）
CREATE TABLE IF NOT EXISTS content_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content_type VARCHAR(50) NOT NULL,  -- text/table/image/chart/map/flowchart
    source_file VARCHAR(255),
    page_number INT,
    
    -- 通用字段
    title VARCHAR(500),
    description TEXT,
    tags TEXT[],
    
    -- AI 分析结果
    ai_metadata JSONB,
    
    -- 类型特定数据
    text_content TEXT,
    vector_id VARCHAR(255),
    table_data JSONB,
    image_path VARCHAR(500),
    geojson JSONB,
    locations TEXT[],
    chart_data JSONB,
    
    -- 人工审核
    verified BOOLEAN DEFAULT FALSE,
    human_corrections JSONB,
    
    -- 时间戳
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_content_type ON content_items(content_type);
CREATE INDEX IF NOT EXISTS idx_source_file ON content_items(source_file);
CREATE INDEX IF NOT EXISTS idx_verified ON content_items(verified);
CREATE INDEX IF NOT EXISTS idx_tags ON content_items USING GIN(tags);

-- 创建内容关联表
CREATE TABLE IF NOT EXISTS content_relations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    from_content_id UUID REFERENCES content_items(id) ON DELETE CASCADE,
    to_content_id UUID REFERENCES content_items(id) ON DELETE CASCADE,
    relation_type VARCHAR(50),
    confidence FLOAT,
    verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 创建用户表（管理后台用）
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 创建会话表（聊天记录）
CREATE TABLE IF NOT EXISTS chat_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    session_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 创建消息表
CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,  -- user/assistant
    content TEXT NOT NULL,
    metadata JSONB,  -- 附加的图片、表格等
    created_at TIMESTAMP DEFAULT NOW()
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_session_messages ON chat_messages(session_id, created_at);

-- 插入默认管理员用户（密码：admin123）
INSERT INTO users (username, email, hashed_password, is_admin)
VALUES ('admin', 'admin@qingpu.ai', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5lBjMGKy9BX6u', TRUE)
ON CONFLICT (username) DO NOTHING;

-- 完成提示
SELECT 'Database initialized successfully!' AS message;
