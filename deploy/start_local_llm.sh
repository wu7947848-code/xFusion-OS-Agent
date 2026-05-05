#!/bin/bash

# ==========================================
# xFusion-OS-Agent 本地模型一键启动脚本 (vLLM 引擎)
# 赛场稳健增强版：防 OOM + 优雅探活
# ==========================================

# 1. 配置模型路径 (必须修改为你下载模型的绝对路径)
# 假设你已经把 glm-4-9b 下载到了当前目录的 models/glm-4-9b 下
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST_MODEL_DIR="$SCRIPT_DIR/models/glm-4-9b"
CONTAINER_MODEL_DIR="/model/glm-4-9b"

echo "--------------------------------------------------"
echo "🚀 正在启动 xFusion 本地模型推理引擎 (vLLM)"
echo "📂 宿主机模型路径: $HOST_MODEL_DIR"
echo "--------------------------------------------------"

# 2. 检查模型文件夹是否存在
if [ ! -d "$HOST_MODEL_DIR" ]; then
    echo "❌ 错误: 找不到模型文件夹！请确保模型已下载至 $HOST_MODEL_DIR"
    exit 1
fi

# 3. 清理可能残留的同名旧容器
if [ "$(docker ps -aq -f name=xfusion-vllm)" ]; then
    echo "♻️ 发现旧容器，正在清理..."
    docker rm -f xfusion-vllm > /dev/null
fi

# 4. 启动 vLLM 容器 (打上了赛场装甲)
echo "⚡ 正在唤醒 GPU 并加载模型..."

docker run -d --name xfusion-vllm \
    --gpus all \
    --ipc=host \
    -v "$HOST_MODEL_DIR":"$CONTAINER_MODEL_DIR" \
    -p 8000:8000 \
    vllm/vllm-openai:latest \
    --model "$CONTAINER_MODEL_DIR" \
    --served-model-name glm-4-9b \
    --trust-remote-code \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.85 \
    --enforce-eager \
    --dtype auto > /dev/null

# 5. 优雅探活 (等待 API 就绪)
echo -n "⏳ 模型加载中，正在进行显存分配和权重加载(约需1-3分钟)"
# 使用 curl 静默访问模型的健康检查接口，直到返回 HTTP 200
until curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/v1/models | grep -q 200; do
    echo -n "."
    sleep 3
done

echo -e "\n✅ 模型加载完成！API 网关已在 http://localhost:8000 准备就绪。"
echo "--------------------------------------------------"
echo "接下来，请在新的终端窗口运行 docker-compose up 启动 Agent 本体。"
echo "--------------------------------------------------"
