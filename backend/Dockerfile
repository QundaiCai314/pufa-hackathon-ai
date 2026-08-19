# ============================================================
# 氢璞 AI 后端 Dockerfile
# 基于 Python 3.11，集成 MinerU PDF 解析能力
# ============================================================

FROM python:3.11-slim AS base

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    libgl1 \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# ---- 阶段1: 安装基础 Python 依赖 ----
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# ---- 阶段2: 安装 MinerU 及其依赖 ----
# MinerU 相关包（固定版本，避免环境污染）
RUN pip install --no-cache-dir \
    magic-pdf==1.3.12 \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

# transformers 降级（MinerU 需要旧版 API）
RUN pip install --no-cache-dir transformers==4.49.0 -i https://pypi.tuna.tsinghua.edu.cn/simple

# timm
RUN pip install --no-cache-dir timm==1.0.28 -i https://pypi.tuna.tsinghua.edu.cn/simple

# pycocotools（detectron2 依赖）
RUN pip install --no-cache-dir pycocotools -i https://pypi.tuna.tsinghua.edu.cn/simple

# detectron2 从源码编译安装
RUN pip install --no-cache-dir 'git+https://github.com/facebookresearch/detectron2.git@v0.6'

# ---- 阶段3: 复制 MinerU 修复文件 ----
COPY scripts/mineru/ /app/scripts/mineru/

# 复制项目文件
COPY . .

# 创建必要的目录
RUN mkdir -p data/raw data/processed data/images data/mineru_output /root/.cache/mineru

# ---- 阶段4: 运行 MinerU 初始化脚本 ----
# 注：模型下载需要网络连接，约 8-10 GB 空间
# 在首次 build 时会执行；如果需要跳过，设置环境变量 SKIP_MINERU_SETUP=1
RUN if [ "$SKIP_MINERU_SETUP" = "1" ]; then \
        echo "Skipping MinerU setup"; \
    else \
        chmod +x /app/scripts/mineru/setup_mineru.sh && \
        /app/scripts/mineru/setup_mineru.sh; \
    fi

# 暴露端口
EXPOSE 8000

# 启动命令（由 docker-compose 覆盖）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
