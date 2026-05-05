# 使用官方轻量级 Python 镜像
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 赛场防坑：安装底层系统依赖（因为容器内默认没有 SSH 客户端和网络测试工具）
RUN apt-get update && apt-get install -y \
    openssh-client \
    iputils-ping \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖清单并安装
# 注意：提前在本地生成好 requirements.txt (包含 pydantic, paramiko, requests, python-dotenv 等)
COPY requirements.txt .
# 🚀 赛前排雷：强制使用清华源，并设置超时和重试机制，防止卡死
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --default-timeout=100 -r requirements.txt

# 🛡️ 赛场防断网绝杀：提前触发 ChromaDB 下载默认的 Embedding 模型，并打包进镜像缓存
RUN python -c "from chromadb.utils import embedding_functions; embedding_functions.DefaultEmbeddingFunction()(['test_cache'])"

# 复制代码库
COPY . .

# 🚀 修正启动入口：启动 API 网关，并监听所有 IP 的 8080 端口
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8080"]
