# 🐳 Docker 全栈一键启动指南

## 📋 前置要求

**只需要安装一个软件：Docker Desktop**

---

## 🔧 第一步：安装 Docker Desktop

### Windows 系统：

1. 访问：https://www.docker.com/products/docker-desktop/
2. 点击 **"Download for Windows"**
3. 双击下载的安装包 `Docker Desktop Installer.exe`
4. 按提示安装（需要启用 WSL 2 或 Hyper-V）
5. 安装完成后**重启电脑**
6. 启动 Docker Desktop（会看到一个鲸鱼图标）

### 验证安装：

打开命令行（Win+R 输入 cmd），执行：

```bash
docker --version
docker-compose --version
```

如果看到版本号，说明安装成功！

---

## ⚙️ 第二步：配置 OpenAI API Key

1. 用记事本打开项目根目录的 `.env` 文件
2. 找到这行：
   ```
   OPENAI_API_KEY=sk-your-key-here
   ```
3. 把 `sk-your-key-here` 替换成你的真实 API Key
4. 保存文件

**如何获取 API Key？**
- 访问：https://platform.openai.com/api-keys
- 登录后点击 "Create new secret key"
- 复制生成的 key

---

## 🚀 第三步：一键启动所有服务

### 方法 1：命令行启动（推荐）

1. 打开命令行（Win+R 输入 cmd）
2. 进入项目目录：
   ```bash
   cd I:\pufa-hackathon-ai
   ```
3. 启动所有服务：
   ```bash
   docker-compose up -d
   ```

### 方法 2：双击启动脚本

直接双击项目根目录的 `start.bat` 文件

---

## ⏱️ 第四步：等待服务启动

第一次启动需要下载镜像和安装依赖，大约 **5-10 分钟**。

### 查看启动进度：

```bash
docker-compose logs -f
```

按 `Ctrl+C` 退出日志查看（不会停止服务）

### 查看服务状态：

```bash
docker-compose ps
```

**所有服务都显示 `Up` 就说明启动成功了！**

---

## 🌐 第五步：访问应用

### 前端（用户界面）：
```
http://localhost:3000
```

### 后端 API 文档：
```
http://localhost:8000/docs
```

### Qdrant 管理界面：
```
http://localhost:6333/dashboard
```

---

## 📊 服务说明

| 服务 | 端口 | 说明 |
|------|------|------|
| frontend | 3000 | React 前端 |
| backend | 8000 | FastAPI 后端 |
| postgres | 5432 | PostgreSQL 数据库 |
| qdrant | 6333 | 向量数据库 |
| redis | 6379 | 缓存 |

---

## 🛠️ 常用命令

### 启动所有服务：
```bash
docker-compose up -d
```

### 停止所有服务：
```bash
docker-compose down
```

### 重启某个服务：
```bash
docker-compose restart backend
```

### 查看日志：
```bash
# 查看所有服务日志
docker-compose logs -f

# 查看某个服务日志
docker-compose logs -f backend
```

### 进入容器内部：
```bash
# 进入后端容器
docker-compose exec backend bash

# 进入数据库容器
docker-compose exec postgres psql -U postgres -d qingpu_ai
```

### 重新构建镜像（代码更新后）：
```bash
docker-compose up -d --build
```

### 完全清理（删除所有数据）：
```bash
docker-compose down -v
```

---

## 🐛 常见问题

### 问题 1：端口被占用

**错误信息：**
```
Error: bind: address already in use
```

**解决方案：**
1. 检查是否有其他程序占用端口：
   ```bash
   netstat -ano | findstr :3000
   netstat -ano | findstr :8000
   ```
2. 关闭占用端口的程序，或修改 `docker-compose.yml` 中的端口映射

---

### 问题 2：Docker Desktop 启动失败

**错误信息：**
```
WSL 2 installation is incomplete
```

**解决方案：**
1. 启用 WSL 2：
   ```bash
   wsl --install
   ```
2. 重启电脑
3. 再次启动 Docker Desktop

---

### 问题 3：后端启动失败

**查看日志：**
```bash
docker-compose logs backend
```

**常见原因：**
- OpenAI API Key 未配置或无效
- 数据库连接失败（等待 postgres 启动完成）

**解决方案：**
1. 检查 `.env` 文件中的 `OPENAI_API_KEY`
2. 等待 1-2 分钟让数据库完全启动
3. 重启后端：
   ```bash
   docker-compose restart backend
   ```

---

### 问题 4：前端无法访问后端

**检查：**
1. 后端是否启动成功：
   ```bash
   curl http://localhost:8000/docs
   ```
2. 检查 `.env` 中的 `REACT_APP_API_URL`

---

## 📝 开发流程

### 修改后端代码：

1. 编辑 `backend/` 目录下的文件
2. 保存后，后端会自动重启（热重载）
3. 刷新浏览器查看效果

### 修改前端代码：

1. 编辑 `frontend/` 目录下的文件
2. 保存后，前端会自动更新（热重载）
3. 浏览器自动刷新

### 安装新的依赖：

**后端：**
1. 编辑 `backend/requirements.txt`
2. 重新构建：
   ```bash
   docker-compose up -d --build backend
   ```

**前端：**
1. 进入容器：
   ```bash
   docker-compose exec frontend sh
   ```
2. 安装依赖：
   ```bash
   npm install <package-name>
   ```
3. 退出容器：
   ```bash
   exit
   ```

---

## 🗑️ 清理与重置

### 停止并删除所有容器：
```bash
docker-compose down
```

### 删除所有数据卷（重置数据库）：
```bash
docker-compose down -v
```

### 清理 Docker 系统缓存：
```bash
docker system prune -a
```

---

## 🎉 成功标志

当你看到以下界面时，说明部署成功：

1. ✅ `http://localhost:3000` - 显示前端登录页面
2. ✅ `http://localhost:8000/docs` - 显示 API 文档
3. ✅ `http://localhost:6333/dashboard` - 显示 Qdrant 管理界面

---

## 📞 需要帮助？

如果遇到问题：

1. 查看日志：`docker-compose logs -f`
2. 检查服务状态：`docker-compose ps`
3. 参考上面的"常见问题"部分
4. 或者询问 AI 助手

---

## 🚀 下一步

现在环境已经搭建好了，可以开始：

1. 上传 PDF 文档到 `data/raw/` 目录
2. 运行文档处理脚本
3. 开始使用 AI 智能助手！

详细使用方法请参考 `README.md`
