# 使用 Node.js 20 LTS（通过国内镜像源）
FROM docker.m.daocloud.io/library/node:20-alpine

# 设置工作目录
WORKDIR /app

# 复制 package.json 和 package-lock.json
COPY package*.json ./

# 安装依赖（使用淘宝镜像加速）
RUN npm config set registry https://registry.npmmirror.com && \
    npm install

# 复制项目文件
COPY . .

# 暴露端口
EXPOSE 3000

# 启动开发服务器
CMD ["npm", "start"]
