import os
import sys
import json
import asyncio
import traceback
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# --- 赛场绝杀：企业级 LLMOps 监控与生命周期管理 ---
import phoenix as px
from openinference.instrumentation.anthropic import AnthropicInstrumentor

# 🚀 补丁 4：TTY 环境检测与 CI/CD 适配
IS_INTERACTIVE = sys.stdin.isatty()
if not IS_INTERACTIVE:
    logging.warning("检测到非交互式环境 (Non-TTY)！Agent 将运行在守护进程模式。为遵循 CI/CD 失效安全原则，所有需要 HITL 授权的高危命令将被自动静默拒绝。")
IS_DAEMON = not IS_INTERACTIVE  # 守护进程模式标志

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 【启动时执行】
    try:
        session = px.launch_app(port=6006)
        AnthropicInstrumentor().instrument()
        print(f"[LLMOps] Phoenix 监控台已启动: {session.url}")
    except Exception as e:
        print(f"[LLMOps] 监控启动失败 (可能是端口被占用): {e}")

    yield  # 把控制权交还给 FastAPI 运行业务逻辑

    # 【关闭时执行】（比如你在终端按 Ctrl+C）
    print("[SYSTEM] 正在安全关闭服务...")

# 将 lifespan 挂载到 FastAPI 实例上
app = FastAPI(title="xFusion OS-Agent API", lifespan=lifespan)

# 导入核心引擎
from core.llm_router import ModelRouter
from core.agent_engine import ReActAgent
from core.ssh_executor import RobustSSHClient
from core.audit_logger import AuditDB
from agent_tools.system_probes import SystemProbes
from agent_tools.system_remediator import SystemRemediator
from agent_tools.lightweight_rag import VectorKnowledgeBase

# 实例化全局审计库
audit_db = AuditDB()

# 🚀 补丁 1：全局单例化 RAG，避免每次请求重复加载模型导致耗时和 OOM
global_rag_db = VectorKnowledgeBase()

load_dotenv()

# 允许跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 定义请求格式
class TaskRequest(BaseModel):
    task: str
    session_id: str  # 前端生成的唯一会话标识，用于审计追踪
    resume_tool_name: str = None    # 挂起待确认的工具名（授权后继续执行）
    resume_tool_params: dict = None  # 挂起待确认的工具参数
    history_context: str = None     # 前世记忆：Agent 挂起前的全部上下文

# ================= Pydantic 输入模型定义（赛场绝杀：强类型工具约束）=================
class GetSystemLoadInput(BaseModel):
    """获取系统负载探针 - 无需任何参数"""
    pass

class CheckPortInput(BaseModel):
    """检查特定端口是否被占用及对应进程状态"""
    port: int = Field(..., description="需要检查的端口号，必须是整数，例如 80、443、3306")

class FetchLogsInput(BaseModel):
    """精准拉取报错日志，用于排查故障根因"""
    service_name: str = Field(..., description="系统服务名称，例如 nginx、mysql、php-fpm")
    lines: int = Field(default=20, description="日志行数，默认 20 行，最大不超过 200 行")

class TestHttpConnectivityInput(BaseModel):
    """外部网络连通性探针，测试 HTTP 目标是否可访问"""
    target: str = Field(default="http://localhost", description="测试目标 URL 或 IP，例如 http://localhost、http://192.168.1.10:8080")

class KillProcessInput(BaseModel):
    """强制结束指定进程，用于处理卡死或资源泄露的服务"""
    pid: str = Field(..., description="进程 ID，必须是字符串形式，例如 '12345'")
    force: bool = Field(default=False, description="是否强制 kill，配合 SIGKILL 信号使用")

class RestartServiceInput(BaseModel):
    """重启系统服务，用于恢复服务异常或配置更新后生效"""
    service_name: str = Field(..., description="需要重启的系统服务名称，例如 nginx、mysql、docker")

class SearchManualInput(BaseModel):
    """搜索官方运维手册，当遇到不认识的报错时获取排查灵感"""
    query: str = Field(..., description="遇到的错误信息、异常关键词或排查疑问")

class ClearLockInput(BaseModel):
    """急救动作：强行解除包管理器死锁，无需任何参数"""
    pass

class ForceSudoInput(BaseModel):
    """【救命兜底工具】当常规 sudo 因 tty/权限失败时，使用 stdin 盲注密码强行提权"""
    command: str = Field(..., description="需要在 sudo 提权下执行的任意系统命令")

class ExecuteArbitraryShellInput(BaseModel):
    """【终极兜底工具】当所有预设工具失效时，执行自定义 shell 命令（受 FATAL_PATTERNS 保护）"""
    command: str = Field(..., description="需要在靶机上执行的 shell 命令")
    justification: str = Field(..., description="调用此工具的理由说明，用于审计追踪")

class DockerOpsInput(BaseModel):
    """容器急救箱：对指定 Docker 容器执行 restart/stop/logs/inspect/rm 操作"""
    container_id: str = Field(..., description="Docker 容器名称或 ID，例如 nginx-prod 或 abc123def")
    action: str = Field(..., description="操作类型，仅支持: restart, stop, logs, inspect, rm")

def create_agent():
    """创建并配置 Agent"""
    ssh_client = RobustSSHClient(
        host=os.getenv("TARGET_HOST", "172.20.10.8"),
        user=os.getenv("TARGET_USER", "wl"),
        password=os.getenv("TARGET_PASSWORD", "4399")
    )

    if not ssh_client.connect():
        return None, "SSH 连接失败"

    probes = SystemProbes(ssh_client)
    remediator = SystemRemediator(ssh_client)

    router = ModelRouter()
    agent = ReActAgent(router, is_daemon=IS_DAEMON)

    # 注册探针工具（诊断）
    agent.register_tool(
        name="get_system_load",
        description="获取靶机当前的 CPU 和内存负载情况",
        func=probes.get_system_load,
        input_model=GetSystemLoadInput
    )
    agent.register_tool(
        name="check_port",
        description="检查服务器特定端口的占用情况",
        func=probes.check_port_status,
        input_model=CheckPortInput
    )
    agent.register_tool(
        name="fetch_error_logs",
        description="精准拉取报错日志",
        func=probes.fetch_error_logs,
        input_model=FetchLogsInput
    )
    agent.register_tool(
        name="test_http_connectivity",
        description="外部网络连通性探针，测试 HTTP 目标是否可访问。必杀技：修复 Nginx 后验证真实生效状态",
        func=probes.test_http_connectivity,
        input_model=TestHttpConnectivityInput
    )

    # 注册动作工具（治愈）
    agent.register_tool(
        name="kill_process",
        description="强制结束指定进程",
        func=remediator.kill_process,
        input_model=KillProcessInput
    )
    agent.register_tool(
        name="restart_service",
        description="重启系统服务（如 Nginx/MySQL）",
        func=remediator.restart_service,
        input_model=RestartServiceInput
    )

    # 注册 RAG 知识库检索工具（引用全局单例，0 毫秒开销）
    agent.register_tool(
        name="search_manual",
        description="当你遇到不认识的报错、或者不知道下一步该怎么排查时，搜索官方运维手册获取灵感",
        func=global_rag_db.search_manual,
        input_model=SearchManualInput
    )

    # 注册包管理器锁清理工具
    agent.register_tool(
        name="clear_package_manager_lock",
        description="当执行 apt/yum 安装失败，且错误日志提示 locked / lock-frontend / resource temporarily unavailable 时，必须立即调用此工具强制释放包管理器锁",
        func=remediator.clear_package_manager_lock,
        input_model=ClearLockInput
    )

    # 注册 Sudo 盲注救命工具（当 tty 报错时的兜底方案）
    agent.register_tool(
        name="force_sudo_execute",
        description="【救命兜底工具】当常规 sudo 操作因为要求 terminal 或权限不足而失败时，使用 stdin 盲注密码强行提权执行命令",
        func=remediator.force_sudo_execute,
        input_model=ForceSudoInput
    )

    # 注册终极兜底武器（瑞士军刀 + HITL 双重封印）
    agent.register_tool(
        name="execute_arbitrary_shell",
        description="【终极兜底工具】上帝模式。当你遇到了极其罕见的组件（如自研中间件），或者常规的 systemd 探针、日志探测完全查不到线索时，你可以调用此工具执行任意原生的 Linux Shell 命令（如 find, awk, 自定义脚本等）。注意：此工具极度危险，调用将触发警报并等待指挥官授权。",
        func=remediator.execute_arbitrary_shell,
        input_model=ExecuteArbitraryShellInput
    )

    # 注册 Docker 容器急救工具
    agent.register_tool(
        name="docker_ops",
        description="Docker 容器急救箱。当微服务架构下某个容器挂了、频繁重启、或需要查看崩溃日志时使用。支持 restart（重启）、stop（停止）、logs（拉取最后50行日志，含 stderr）、inspect（查看容器详配）、rm（强制删除僵尸容器）。",
        func=remediator.docker_ops,
        input_model=DockerOpsInput
    )

    return ssh_client, agent, probes

@app.post("/api/execute")
async def execute_task(request: TaskRequest):
    """
    核心接口：接收任务，返回 SSE 实时数据流
    """
    async def event_generator():
        # 1. 建立 SSH 通道
        yield f"data: {json.dumps({'type': 'status', 'content': '正在建立 SSH 通道...'})}\n\n"
        await asyncio.sleep(0.3)

        ssh_client, agent, probes = create_agent()
        if ssh_client is None:
            error_msg = {"type": "error", "content": agent}
            audit_db.log_event(request.session_id, request.task, 0, "error", error_msg)
            yield f"data: {json.dumps(error_msg)}\n\n"
            yield f"data: [DONE]\n\n"
            return

        yield f"data: {json.dumps({'type': 'status', 'content': 'SSH 通道建立成功，Agent 思考引擎启动...'})}\n\n"
        await asyncio.sleep(0.3)

        # 2. 启动 Agent 流式循环
        task = request.task
        is_sensitive = False  # 默认走云端 API

        # 【Pre-flight Check】获取靶机环境情报，注入 System Prompt
        env_info = probes.get_env_info()

        try:
            # 🚀 补丁 2：HITL 授权接续逻辑
            if request.resume_tool_name:
                # 🚀 容错守卫：检测 history_context 是否丢失
                if not request.history_context:
                    yield f"data: {json.dumps({'status': 'warning', 'step': 0, 'type': 'error', 'content': '【严重警告】接收到授权请求但 history_context 为空！Agent 将失去此前所有记忆，可能产生不可预测行为。建议终止任务并重新开始。'})}\n\n"

                yield f"data: {json.dumps({'status': 'info', 'step': 0, 'type': 'start', 'content': f'接收到指挥官授权，正在校验参数并执行 [{request.resume_tool_name}]...'})}\n\n"

                tool_info = agent.tools[request.resume_tool_name]
                tool_func = tool_info["func"]
                input_model = tool_info.get("input_model")

                try:
                    # 🚀 终极装甲：利用 Pydantic 强行清洗前端传来的脏数据！
                    # 这会自动将 "80" 转为 80，并将缺失的 default 参数（如 lines=20）补齐
                    if input_model:
                        validated_params = input_model(**request.resume_tool_params).model_dump()
                    else:
                        validated_params = request.resume_tool_params

                    # 强行执行工具 (使用清洗后且绝对安全的 validated_params)
                    if asyncio.iscoroutinefunction(tool_func):
                        obs = await tool_func(**validated_params)
                    else:
                        obs = await asyncio.to_thread(tool_func, **validated_params)

                    audit_db.log_event(request.session_id, request.task, 1, "forced_execution", f"{request.resume_tool_name} => {obs}")
                    yield f"data: {json.dumps({'status': 'success', 'step': 1, 'type': 'observation', 'content': f'强制执行成功，输出结果: {str(obs)[:200]}'})}\n\n"

                    # 执行完毕后，把结果塞回给大脑，让它继续接下来的审查（Critic）和总结
                    # 🚀 优化 Prompt 权重：用高亮分隔符隔离历史记忆与最新指令
                    history_prefix = f"{request.history_context}\n" if request.history_context else ""
                    resume_task = (
                        f"{history_prefix}"
                        f"==================================================\n"
                        f"🚨 【系统最高优先级通知】 🚨\n"
                        f"指挥官已手动授权并执行了高危动作: {request.resume_tool_name}。\n"
                        f"动作返回的真实结果如下：\n"
                        f"{obs}\n"
                        f"==================================================\n"
                        f"请你立刻切换到 Critic (审查者) 角色，审查上述结果是否符合预期。\n"
                        f"如果问题已解决，请汇报最终结论；如果依然报错，请重新规划下一步。"
                    )

                    async for event in agent.run_stream(resume_task, env_info=env_info, is_sensitive=False):
                        audit_db.log_event(
                            session_id=request.session_id,
                            task=request.task,
                            step=event.get("step", 0),
                            event_type=event.get("type", "unknown"),
                            content=event.get("content", "") + str(event.get("params", ""))
                        )
                        yield f"data: {json.dumps(event)}\n\n"
                        await asyncio.sleep(0.05)
                except Exception as e:
                    audit_db.log_event(request.session_id, request.task, 1, "forced_execution_error", str(e))
                    yield f"data: {json.dumps({'status': 'error', 'step': 1, 'type': 'error', 'content': f'授权执行失败: {str(e)}'})}\n\n"
                finally:
                    ssh_client.close()
                    yield f"data: [DONE]\n\n"
                return  # 授权流处理完毕，直接结束

            # 如果不是授权请求，走正常的思考流程
            async for event in agent.run_stream(task, env_info=env_info, is_sensitive=is_sensitive):
                # ★ 核心绝杀：在推送给前端的同时，落入本地审计数据库！
                audit_db.log_event(
                    session_id=request.session_id,
                    task=request.task,
                    step=event.get("step", 0),
                    event_type=event.get("type", "unknown"),
                    content=event.get("content", "") + str(event.get("params", ""))
                )

                # 🚀 补丁 4：拦截最后的成功消息，加上赛博朋克极客味战报
                if event.get("type") == "final_answer":
                    raw_summary = event.get("content", "任务完成。")
                    polished_summary = (
                        f"🟢 <b>[Agent 终极战报]</b>\n"
                        f"────────────────────\n"
                        f"{raw_summary}\n"
                        f"────────────────────\n"
                        f"🛡️ xFusion-OS-Agent 已将靶机状态稳定，安全拦截网持续运作中。"
                    )
                    event["content"] = polished_summary
                    yield f"data: {json.dumps(event)}\n\n"
                else:
                    yield f"data: {json.dumps(event)}\n\n"
                # 异步并发处理得极快，缩短等待间隔
                await asyncio.sleep(0.05)
        except Exception as e:
            # 🚀 补丁 4：记录详尽的报错堆栈到数据库
            error_details = traceback.format_exc()
            audit_db.log_event(request.session_id, request.task, 0, "fatal_error", error_details)

            # 给前端的报错依然保持安全和简洁
            yield f"data: {json.dumps({'type': 'error', 'content': f'引擎内部异常，已记录审计日志。摘要: {str(e)}'})}\n\n"
        finally:
            ssh_client.close()

        yield f"data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "ok"}

# 启动命令: uvicorn api:app --reload --port 8000
