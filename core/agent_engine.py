import json
import asyncio
from pydantic import BaseModel
from typing import Callable, Type, Dict, Any
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent_tools.feishu_alert import FeishuAlerter

# 🚀 补丁 2：赛博朋克终端颜色引擎
class ConsoleColors:
    MAGENTA = '\033[95m'    # 洋红：代表 Agent 正在深度思考 (Thought)
    CYAN = '\033[96m'       # 青色：代表调用了探针或 RAG 知识库
    GREEN = '\033[92m'      # 绿色：代表执行成功
    RED_BOLD = '\033[1;31m' # 加粗红色：代表触发高危安全拦截！
    YELLOW = '\033[93m'     # 黄色：代表系统警告或假成功打回
    RESET = '\033[0m'       # 颜色重置

def print_cyber(text: str, color: str):
    """带颜色的终端输出，仅用于后端炫技展示"""
    print(f"{color}{text}{ConsoleColors.RESET}", flush=True)

class AgentMemory:
    """【冠军级架构】分级记忆管理器：核心记忆（永不遗忘） + 工作记忆（滑动窗口）"""

    def __init__(self, core_task: str, env_info: str, max_history_turns: int = 3):
        self.max_history_turns = max_history_turns
        self.turns = []  # 短期工作记忆：只存最近几步的操作和报错

        # ★ 核心记忆：将终极目标和靶机环境固化，大模型绝对不会跑偏
        self.core_memory = (
            f"【终极任务目标】: {core_task}\n"
            f"【当前靶机环境】: {env_info}"
        )

    def add_turn(self, thought: str, tool_name: str, params: dict, observation: str):
        """添加一轮短期记忆（动作与结果）"""
        # 对超长输出进行物理截断，防止脏数据污染
        safe_obs = str(observation)[:500] + "\n...[日志过长已截断]" if len(str(observation)) > 500 else str(observation)

        turn_data = (
            f"[思考]: {thought}\n"
            f"[动作]: 调用 {tool_name}，参数: {json.dumps(params, ensure_ascii=False)}\n"
            f"[观察结果]: {safe_obs}\n"
        )
        self.turns.append(turn_data)

        # 滑动窗口挤出最老的记录，保护内存
        if len(self.turns) > self.max_history_turns:
            self.turns.pop(0)

    def get_context(self) -> str:
        """组装供大模型阅读的上下文 = 核心记忆 + 短期记忆"""
        context = f"{self.core_memory}\n\n"

        if not self.turns:
            context += "尚无操作记录，请开始你的第一步排查规划。"
            return context

        context += "以下是你最近几轮的操作记录（旧记录已被系统折叠，请专注当下）：\n"
        for i, turn in enumerate(self.turns):
            context += f"--- 第 {i+1} 轮 ---\n{turn}\n"
        return context


class ReActAgent:
    def __init__(self, router, max_loops: int = 10, is_daemon: bool = False):
        self.router = router
        self.max_loops = max_loops
        self.tools: Dict[str, Dict[str, Any]] = {}
        self.is_daemon = is_daemon  # 🚀 补丁 4：守护进程模式标志

    # ================= 核心升级 1：Pydantic 强类型工具注册 =================
    def register_tool(self, name: str, description: str, func: Callable, input_model: Type[BaseModel]):
        """
        升级版注册工具：必须传入一个 Pydantic BaseModel 作为参数类型约束
        """
        # Pydantic v2 直接生成标准的 JSON Schema
        schema = input_model.model_json_schema()

        self.tools[name] = {
            "func": func,
            "description": description,
            "input_model": input_model,  # 🚀 存储 Pydantic 模型用于运行时校验
            # 将 Pydantic 生成的结构转换为大模型原生 Tool 格式
            "input_schema": {
                "type": "object",
                "properties": schema.get("properties", {}),
                "required": schema.get("required", [])
            }
        }

    def _get_tool_schemas(self) -> list:
        return [
            {
                "name": name,
                "description": info["description"],
                "input_schema": info["input_schema"]
            }
            for name, info in self.tools.items()
        ]

    # ================= 核心升级 2：滑动窗口记忆驱动 =================
    async def run_stream(self, user_task: str, env_info: str = "未知环境", is_sensitive: bool = True):
        yield {"status": "info", "step": 0, "type": "start", "content": f"接受任务: {user_task} | 探测环境: {env_info}"}

        # ★ 配合分级记忆：在初始化时把终极任务和环境死死锁进核心记忆里
        memory = AgentMemory(core_task=user_task, env_info=env_info, max_history_turns=6)
        tools_schema = self._get_tool_schemas()

        # ★ 偷师 OS-Copilot：结构化的多角色系统法则
        system_prompt = """你是一个部署在 Linux 环境下的顶级 OS Agent。
你必须在内心以"多智能体协作"的模式执行任务，完成【规划-执行-审查】的逻辑闭环。

【多角色思维法则】
1. 规划者 (Planner)：在每次行动前，先明确当前进度，并制定下一步的安全排查策略。谋定而后动。
2. 执行者 (Actor)：严格根据规划调用相应的工具。如果遇到高风险操作，必须在思考中向用户警示。
3. 审查者 (Critic)：拿到工具返回的日志结果后，必须立刻审查是否符合预期。如果报错或偏离目标，绝对不允许直接回复完成，必须分析原因并重新规划！

【输出格式要求】
在你 Thought (思考) 环节中，必须清晰地展现这三个角色的逻辑。
当得出最终结论时，用清晰专业的语言汇报发现的问题、执行的动作与恢复结果。"""

        # 初始化飞书告警器
        alerter = FeishuAlerter()

        for step in range(1, self.max_loops + 1):
            yield {"status": "info", "step": step, "type": "loop_start", "content": f"--- [思考回合 {step}/{self.max_loops}] ---"}

            # 因为记忆库已经自带了任务目标，这里传入 current_prompt 时直接调 get_context 即可
            context = memory.get_context()

            # 🚀 补丁 3：融入"防降级"理念的尾部核对单
            tail_reinforcement = (
                "\n=========================================\n"
                "🚨 【Agent 执行强制核对单 (必读)】 🚨\n"
                "1. 你必须严格返回 JSON 格式，绝不能输出多余的文本！\n"
                "2. 如果尚未解决问题，必须选择 'tool_name' 执行动作！\n"
                "3. ⚠️ 【防降级审核规则】：如果你在之前的步骤中发现了深层报错（如日志报错），最终验证时绝不能用浅层命令（如仅查进程存活）来敷衍了事。你必须证明根本报错已被修复！\n"
                "4. 如果你认为问题已经彻底解决，请将 'tool_name' 设为 'none'，并在 'thought' 中输出最终排查报告。\n"
                "=========================================\n"
            )

            # 把核对单死死焊在 Prompt 的最后面
            final_user_prompt = f"{context}{tail_reinforcement}"

            # 异步等待大模型响应，释放主线程
            action_data = await self.router.generate_response(
                prompt=final_user_prompt,
                system_prompt=system_prompt,
                tools=tools_schema,
                is_sensitive=is_sensitive
            )

            if action_data.get("type") == "error":
                yield {"status": "error", "step": step, "type": "error", "content": action_data["content"]}
                break

            if action_data.get("thought"):
                yield {"status": "success", "step": step, "type": "thought", "content": action_data["thought"]}
                # 🚀 赛博朋克：终端输出 Agent 思考过程
                print_cyber(f"\n🧠 [Agent 思考中]: {action_data['thought']}", ConsoleColors.MAGENTA)

            # 🚀 补丁 3：假成功探测器 - 解决大模型"偷懒幻觉"问题
            tool_name = action_data.get("tool_name")

            if (tool_name == "none" or tool_name is None) and action_data.get("final_answer"):
                # 获取工作记忆里最近的动作
                recent_actions = [turn for turn in memory.turns if "[动作]" in turn]

                # 只有探针（没有修复动作）的情况
                only_probes = all(
                    any(probe in action for probe in ["check_port", "get_system_load", "fetch_error_logs", "search_manual", "test_http"])
                    for action in recent_actions
                ) if recent_actions else False

                if recent_actions and only_probes:
                    # 强制打回，逼迫它去用 remediator 工具！
                    yield {"status": "warning", "step": step, "type": "observation", "content": "【系统强制干预】检测到假成功陷阱：你只调用了探针工具而未执行任何修复动作，已强制打回重审！"}

                    # 把警告塞给记忆，让它继续循环
                    memory.add_turn(
                        action_data.get("thought", ""),
                        "（系统拦截假成功）",
                        {},
                        "系统检测到：只执行了探针诊断，未执行任何 kill/restart 等修复动作。已强制打回，要求调用自愈工具！"
                    )
                    continue
                else:
                    # 不是假成功，正常结束
                    yield {"status": "success", "step": step, "type": "final_answer", "content": action_data["final_answer"]}
                    return

            tool_name = action_data["tool_name"]
            if tool_name in self.tools:
                tool_params = action_data["tool_params"]

                # === 冠军级设计：高风险操作风控 ===
                # 🚀 补丁：将兜底工具加入最高级别的拦截名单！
                RISKY_TOOLS = ["kill_process", "restart_service", "clear_package_manager_lock", "execute_arbitrary_shell"]

                # 如果任务包含 [强制执行] 标记，则跳过拦截（用于自动化流程）
                if tool_name in RISKY_TOOLS and "[强制执行]" not in user_task:
                    # 🚀 补丁 4：守护进程模式下直接静默拒绝，防止 CI/CD 流水线卡死
                    if self.is_daemon:
                        print_cyber(f"\n🚫 [守护进程模式] 高危动作 {tool_name} 被自动拒绝。", ConsoleColors.RED_BOLD)
                        memory.add_turn(action_data.get("thought", ""), tool_name, tool_params, "系统拦截：守护进程模式下高危命令被静默拒绝。")
                        yield {"status": "error", "step": step, "type": "observation", "content": f"[安全拦截] 守护进程模式下，高危操作 [{tool_name}] 被系统自动拒绝。如需执行，请切换至交互式终端。"}
                        continue  # 不 return，继续让 Agent 想办法

                    # 获取当前这轮的全部上下文记忆
                    current_memory_snapshot = memory.get_context()

                    warning_msg = f"系统安全锁触发：即将在生产环境执行高风险操作 [{tool_name}]，参数: {tool_params}。等待指挥官授权。"

                    # 🚀 剧场效应绝杀：在此刻向手机发送飞书卡片！
                    try:
                        alerter.send_warning_card(
                            title="⚠️ 拦截到高危指令",
                            content=f"Agent 试图调用: {tool_name}\n目标参数: {tool_params}\n请在指挥台确认是否放行。"
                        )
                    except Exception as e:
                        print(f"飞书告警发送失败: {e}")

                    # 🚀 赛博朋克：终端输出高危拦截警告
                    print_cyber(f"\n🚨 [风控拦截]: 高危动作 {tool_name} 已挂起，等待指挥官授权！", ConsoleColors.RED_BOLD)

                    yield {
                        "status": "warning",
                        "step": step,
                        "type": "confirmation_required",
                        "content": warning_msg,
                        "tool_name": tool_name,
                        "tool_params": tool_params,
                        "history_context": current_memory_snapshot  # 🚀 打包发送记忆
                    }
                    # 保存这轮记忆，以便授权后继续
                    memory.add_turn(action_data.get("thought", ""), tool_name, tool_params, "安全锁拦截：等待用户二次确认。")
                    return  # 强制中断本次生成器，等待前端指令
                # ==================================

                yield {"status": "info", "step": step, "type": "action", "content": f"调用工具: {tool_name}", "params": tool_params}

                # 🚀 赛博朋克：RAG 知识库检索时输出青色提示
                if tool_name == "search_manual":
                    print_cyber(f"\n🔍 [检索知识库]: 正在查询 '{tool_params.get('query')}'...", ConsoleColors.CYAN)

                try:
                    tool_info = self.tools[tool_name]
                    func = tool_info["func"]
                    # 🚀 补丁 3：利用 Pydantic 强转并补齐默认值！
                    input_model = tool_info.get("input_model")
                    if input_model:
                        # 这一步会自动校验类型，并把 default 字段补上
                        validated_params = input_model(**tool_params).model_dump()
                    else:
                        validated_params = tool_params

                    # 顶级架构师的魔法：套上 30 秒硬性熔断器
                    if asyncio.iscoroutinefunction(func):
                        observation = await asyncio.wait_for(func(**validated_params), timeout=30.0)
                    else:
                        observation = await asyncio.wait_for(asyncio.to_thread(func, **validated_params), timeout=30.0)

                    obs_display = str(observation)[:300] + "..." if len(str(observation)) > 300 else str(observation)
                    yield {"status": "success", "step": step, "type": "observation", "content": obs_display}

                # 新增：专门捕获超时异常
                except asyncio.TimeoutError:
                    observation = f"执行超时 (Timeout)！可能靶机卡死或命令陷入死循环，请更换策略。"
                    yield {"status": "error", "step": step, "type": "observation", "content": observation}

                # 🚀 补丁 3：Fail-Closed 审计原则
                # 任何底层工具的崩溃（断连、类型错误），全部标记为致命故障，强制中断并请求人工介入
                except Exception as e:
                    error_details = str(e)
                    observation = f"[致命系统故障] 工具执行引擎发生异常: {error_details}。"

                    # 触发高危挂起，要求人类介入
                    yield {
                        "status": "warning",
                        "step": step,
                        "type": "confirmation_required",
                        "content": f"系统安全机制触发 (Fail-Closed)：工具 [{tool_name}] 执行时底层引擎崩溃。为防止状态失控，已强制挂起。请指挥官检查报错：{error_details}",
                        "tool_name": tool_name,
                        "tool_params": tool_params,
                        "history_context": memory.get_context()
                    }
                    return  # 直接结束当前生成，等待前端发来新指令

                # 核心：将这一轮的完整结果塞入滑动窗口，老记录会被自动挤掉！
                memory.add_turn(action_data.get("thought", ""), tool_name, tool_params, observation)
            else:
                yield {"status": "warning", "step": step, "type": "error", "content": f"未知工具: {tool_name}"}
                memory.add_turn(action_data.get("thought", ""), tool_name, {}, "系统报错：该工具不存在，请查阅可用工具列表。")

        yield {"status": "error", "step": self.max_loops, "type": "error", "content": "[X] 超过最大循环次数，任务强制阻断。"}

# ================= 实际运行入口 =================
if __name__ == "__main__":
    import os
    import asyncio
    from dotenv import load_dotenv
    from agent_tools.system_probes import SystemProbes
    from agent_tools.system_remediator import SystemRemediator
    from agent_tools.lightweight_rag import VectorKnowledgeBase
    from core.ssh_executor import RobustSSHClient
    from core.llm_router import ModelRouter

    load_dotenv()

    async def run_agent_test():
        # 初始化 SSH 客户端（连接靶机）
        ssh_client = RobustSSHClient(
            host=os.getenv("TARGET_HOST", "172.20.10.8"),
            user=os.getenv("TARGET_USER", "wl"),
            password=os.getenv("TARGET_PASSWORD", "4399")
        )

        if not ssh_client.connect():
            print("[X] SSH 连接失败，Agent 无法启动")
            return

        # 初始化探针工具和动作工具
        probes = SystemProbes(ssh_client)
        remediator = SystemRemediator(ssh_client)
        rag_db = VectorKnowledgeBase()

        # 初始化 Agent
        router = ModelRouter()
        agent = ReActAgent(router)

        # ================= Pydantic 输入模型定义 =================
        class CheckPortInput(BaseModel):
            port: int

        class FetchLogsInput(BaseModel):
            service_name: str
            lines: int = 20

        class RestartServiceInput(BaseModel):
            service_name: str

        class KillProcessInput(BaseModel):
            pid: str
            force: bool = False

        class SearchManualInput(BaseModel):
            query: str

        class GetSystemLoadInput(BaseModel):
            """获取系统负载探针 - 无需任何参数"""
            pass

        # 注册探针工具（诊断）
        agent.register_tool(
            name="get_system_load",
            description="获取 CPU、内存、磁盘的全局状态",
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

        # 注册 RAG 知识库检索工具
        agent.register_tool(
            name="search_manual",
            description="当你遇到不认识的报错、或者不知道下一步该怎么排查时，搜索官方运维手册获取灵感",
            func=rag_db.search_manual,
            input_model=SearchManualInput
        )

        # 启动 Agent（异步迭代）
        task = "网站打不开了，查一下 80 端口是不是挂了"
        async for event in agent.run_stream(task, is_sensitive=False):
            print(f"[{event.get('type', 'unknown')}] {event.get('content', '')}")

        ssh_client.close()

    asyncio.run(run_agent_test())
