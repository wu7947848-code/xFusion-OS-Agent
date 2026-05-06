import os
import json
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from dotenv import load_dotenv

# 加载本地 .env 文件中的密钥
load_dotenv()

# ==================== 多 Provider 自动配置表 ====================
# 决赛现场只需改 PROVIDER 环境变量即可秒级切换
PROVIDER_CONFIG = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/anthropic",
        "api_key_env": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-v4-flash",
    },
    "minimax": {
        "base_url": "https://api.minimaxi.com/anthropic",
        "api_key_env": "MINIMAX_API_KEY",
        "default_model": "MiniMax-M2.7-highspeed",
    },
    "glm": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4/anthropic",
        "api_key_env": "GLM_API_KEY",
        "default_model": "glm-4-plus",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/anthropic",
        "api_key_env": "QWEN_API_KEY",
        "default_model": "qwen-max",
    },
    "kimi": {
        "base_url": "https://api.moonshot.cn/anthropic",
        "api_key_env": "KIMI_API_KEY",
        "default_model": "moonshot-v1-8k",
    },
}


class ModelRouter:
    def __init__(self):
        # 读取 Provider（默认 deepseek-v4-flash）
        provider = os.getenv("PROVIDER", "deepseek").lower()
        config = PROVIDER_CONFIG.get(provider, PROVIDER_CONFIG["deepseek"])

        # 优先用环境变量覆盖，其次用 Provider 默认值
        self.base_url = os.getenv("ANTHROPIC_BASE_URL", config["base_url"])
        self.cloud_model = os.getenv("CLOUD_MODEL", config["default_model"])
        self.local_model = os.getenv("LOCAL_MODEL", "glm-4-9b")

        # API Key：优先 ANTHROPIC_API_KEY，其次 Provider 专属 Key
        self.api_key = (
            os.getenv("ANTHROPIC_API_KEY") or
            os.getenv(config["api_key_env"], "")
        )

        # AsyncAnthropic 异步客户端
        self.client = AsyncAnthropic(
            base_url=self.base_url,
            api_key=self.api_key,
        )

        # 预留赛场上 DGX OS 终端的本地 vLLM 接口地址
        self.local_vllm_url = os.getenv("LOCAL_VLLM_URL", "http://localhost:8000/v1/chat/completions")

        print(f"[Router] Provider={provider} | Model={self.cloud_model} | BaseURL={self.base_url}")
        if not self.api_key:
            print("[Router] ⚠️  未检测到 API Key！请设置 ANTHROPIC_API_KEY 或对应 Provider 的环境变量。")

    async def generate_response(self, prompt: str, system_prompt: str = "你是一个强大的 OS Agent", is_sensitive: bool = False, tools: list = None) -> dict:
        """
        核心路由开关（全链路异步）：
        is_sensitive = True -> 强制走本地算力，数据不出网
        is_sensitive = False -> 走云端 API，追求极速响应
        返回 dict，包含 thought/tool_name/tool_params/final_answer
        """
        if is_sensitive:
            print("[Router] 检测到机密/系统级数据，触发安全隔离，路由至 -> 本地 vLLM 算力节点")
            return await self._call_local_vllm(prompt, system_prompt, tools)
        else:
            print("[Router] 常规任务，追求高并发，路由至 -> 云端 MiniMax API")
            return await self._call_cloud_minimax(prompt, system_prompt, tools)

    def get_tools_spec(self) -> list:
        """
        返回 Anthropic 格式的工具规范列表
        将 Agent 注册的 tools 转换为 API 需要的格式
        """
        # 占位符，实际使用时 agent_engine 会传入真实的 tools 字典
        return []

    async def _call_cloud_minimax(self, prompt: str, system_prompt: str, tools: list = None) -> dict:
        """
        [异步版] 调用云端 API，原生支持 Tool Calling
        """
        if not self.api_key:
            return {"type": "error", "content": "API Key not set. 请设置 ANTHROPIC_API_KEY 或对应 Provider 的环境变量。"}

        max_retries = 2
        for attempt in range(max_retries):
            try:
                # 组装请求参数
                kwargs = {
                    "model": self.cloud_model,
                    "max_tokens": 4096,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,  # 降低温度，让工具调用更精准
                }

                # 如果有工具，则挂载工具
                if tools:
                    kwargs["tools"] = tools

                # 核心异步调用：await 释放主线程，服务不再卡死
                response = await self.client.messages.create(**kwargs)

                result = {"thought": "", "tool_name": "none", "tool_params": {}, "final_answer": ""}

                # Anthropic 规范：模型会返回多个 Block
                for block in response.content:
                    if block.type == "text":
                        # 文本块：要么是思考过程，要么是最终答案
                        result["thought"] += block.text
                    elif block.type == "tool_use":
                        # 工具调用块：API 官方保证了格式的绝对正确！
                        result["tool_name"] = block.name
                        result["tool_params"] = block.input

                # 如果没有调用任何工具，说明它得出了最终结论
                if result["tool_name"] == "none":
                    result["final_answer"] = result["thought"]

                return result

            except Exception as e:
                if attempt < max_retries - 1:
                    import asyncio
                    await asyncio.sleep(1.0)
                    continue
                return {"type": "error", "content": f"API 异步调用失败（重试{max_retries}次后仍失败）: {str(e)}"}

    @staticmethod
    def _anthropic_tools_to_openai(anthropic_tools: list) -> list:
        """将 Anthropic tool 格式转换为 OpenAI function calling 格式"""
        openai_tools = []
        for tool in anthropic_tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {"type": "object", "properties": {}})
                }
            })
        return openai_tools

    async def _call_local_vllm(self, prompt: str, system_prompt: str, tools: list = None) -> dict:
        """调用跑在 FusionXpark 上的本地 vLLM 模型"""
        try:
            # vLLM 默认 API Key 可以随便填，但要有
            client = AsyncOpenAI(
                base_url=self.local_vllm_url.replace("/chat/completions", ""),
                api_key="EMPTY"
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]

            kwargs = {
                "model": self.local_model,  # 决赛现场可切换不同本地模型
                "messages": messages,
                "temperature": 0.1
            }

            # 将 Anthropic 格式工具定义转换为 OpenAI Function Calling 格式
            if tools:
                kwargs["tools"] = self._anthropic_tools_to_openai(tools)

            response = await client.chat.completions.create(**kwargs)
            choice = response.choices[0]

            result = {"thought": "", "tool_name": "none", "tool_params": {}, "final_answer": ""}

            if choice.message.tool_calls:
                tool_call = choice.message.tool_calls[0]
                result["tool_name"] = tool_call.function.name
                result["tool_params"] = json.loads(tool_call.function.arguments)
                # 有些模型会把 thought 放在 message.content 里
                result["thought"] = choice.message.content or f"决定调用工具: {result['tool_name']}"
            else:
                result["final_answer"] = choice.message.content
                result["thought"] = "得出最终结论。"

            return result
        except Exception as e:
            return {"type": "error", "content": f"本地 vLLM 调用失败: {str(e)}"}


# ================= 测试沙盒 =================
if __name__ == "__main__":
    import asyncio

    async def test_router():
        router = ModelRouter()

        print("\n--- 测试 1: 发送常规询问 (查资料) ---")
        res1 = await router.generate_response(
            prompt="请告诉我 Linux 下怎么查看内存占用？",
            is_sensitive=False
        )
        print(f"模型返回: {res1}")

        print("\n--- 测试 2: 发送机密系统日志 (包含真实内网 IP) ---")
        res2 = await router.generate_response(
            prompt="分析以下崩溃日志：192.168.0.1 拒绝访问，Nginx core dumped...",
            is_sensitive=True
        )
        print(f"模型返回: {res2}")

    asyncio.run(test_router())
