from fabric import Connection
from invoke.exceptions import CommandTimedOut
from typing import Dict, Any
import re

# >>> 赛场核心加分项：物理级正则黑名单 (模块级常量，供全项目共享) <<<
FATAL_PATTERNS = [
    # --- 基础物理阻断 ---
    r'(?i)rm\s+(?:-[a-z]*[rf][a-z]*\s+)+/(?:etc|boot|var/log|usr|bin|sbin|lib|dev|sys|proc|root|\*?\s*$)',
    r'(?i)find\s+/(?:etc|boot|var|usr|bin|sbin|lib|dev|sys|proc|root)?\b.*-delete',
    r'(?i)(>|>>|dd\s+of=)\s*/dev/(sd[a-z]|nvme\d?|vda|hda)\b',
    r'\bmkfs\b',
    r':\(\)\s*\{\s*:\|:&;?\s*:\}',  # Fork炸弹

    # 🚀 补丁 1：移植初赛的 APT/RedTeam 级别防御
    # 拦截 SSH 公钥后门写入 (防止免密登录持久化)
    r'(?i)(sed\s+-i|(>|>>|tee\s+-a)).*\.ssh/authorized_keys',
    # 拦截恶意定时任务与系统服务后门
    r'(?i)(crontab\s+-[eri]|echo\s+.*(?:>|>>)\s*/var/spool/cron/)',
    r'(?i)(>|>>|sed\s+-i)\s*/etc/(cron\.|crontab)',
    # 拦截容器特权逃逸 (挂载宿主机根目录或特权模式)
    r'(?i)docker\s+(run|create).*?(?:-v|--volume)\s+/(?:host)?\s*:',
    r'(?i)docker\s+(run|create).*?--privileged\b',
    # 拦截内核模块篡改 (Rootkit 准备行为)
    r'(?i)\b(insmod|rmmod|modprobe)\b',
]

# 🚀 补丁 1：ANSI 清洗正则（初赛宝藏，防 Token 污染和 JSON 崩溃）
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

class RobustSSHClient:
    def __init__(self, host: str, user: str, password: str, port: int = 22):
        self.host = host
        self.user = user
        self.password = password
        self.port = port

        # 核心升级：使用 Fabric 的 Connection 对象
        self.conn = Connection(
            host=self.host,
            user=self.user,
            port=self.port,
            connect_kwargs={
                "password": self.password,
                "timeout": 10,             # TCP 连接超时
                "banner_timeout": 15,      # 握手超时
                "look_for_keys": False,    # 禁用本地私钥查找，纯密码登录
                "allow_agent": False,      # 禁用 SSH Agent 转发
            }
        )
        self.is_connected = False
        self.sudo_needs_password = None  # 🚀 缓存：提前探针 sudo 是否需要密码

    def check_sudo_needs_password(self) -> bool:
        """
        提前跑一个无害的 sudo -v 探针，探测靶机 sudo 是否需要密码。
        返回 True = 需要密码（盲注逻辑启用）；False = NOPASSWD（盲注逻辑禁用）。
        """
        try:
            # 使用 get_pty=True 模拟真实 TTY 环境
            stdin, stdout, stderr = self.conn.client.exec_command("sudo -v", get_pty=True)
            # 如果 exec_command 没有抛出异常，立刻读取输出
            # NOPASSWD 情况下 stdout 为空且立即返回；有密码时会阻塞等待输入
            import time
            start = time.time()
            while time.time() - start < 5:
                if stdout.channel.recv_ready():
                    # 读取所有可用输出
                    out = stdout.read().decode('utf-8', errors='ignore')
                    err = stderr.read().decode('utf-8', errors='ignore')
                    # NOPASSWD：输出里不会有 password 提示
                    if "password" in (out + err).lower():
                        self.sudo_needs_password = True
                    else:
                        self.sudo_needs_password = False
                    print(f"[SSH Sudo Probe] NOPASSWD={not self.sudo_needs_password}")
                    return self.sudo_needs_password
                time.sleep(0.2)
            # 超时 → 大概率是需要密码但我们没输入
            self.sudo_needs_password = True
            print("[SSH Sudo Probe] 超时，判定为需要密码")
            return True
        except Exception as e:
            # 探针失败，降级为需要密码（盲注安全）
            self.sudo_needs_password = True
            print(f"[SSH Sudo Probe] 探针异常，降级为需要密码: {e}")
            return True

    def connect(self) -> bool:
        try:
            self.conn.open()
            self.is_connected = True
            print(f"[OK] 成功连接至靶机: {self.host} (Powered by Fabric)")
            # 🚀 补丁：SSH 连接成功后立即探测 sudo 是否需要密码
            self.check_sudo_needs_password()
            return True
        except Exception as e:
            print(f"[X] 连接靶机失败: {str(e)}")
            return False

    def execute_command(self, command: str, timeout: int = 30) -> Dict[str, Any]:
        """
        执行命令：自带原生超时阻断、高危指令拦截、完美剥离标准错误流
        """
        if not self.is_connected:
            return {"status": "error", "message": "SSH 尚未连接"}

        # 使用模块级 FATAL_PATTERNS 进行物理层安全校验
        for pattern in FATAL_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                print(f"[!] 触发物理风控拦截: 拒绝执行 '{command}'")
                return {
                    "status": "error",
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": "【物理安全锁触发】该命令匹配到高危破坏特征（如删库、炸弹，写盘），已被底层系统强行阻断！",
                    "command": command
                }

        try:
            # 核心升级：Fabric 一键执行！
            # hide=True 防止把靶机输出打印到你本地的终端弄脏日志
            # warn=True 遇到错误不直接抛出 Python 异常，而是优雅返回 exit_code
            result = self.conn.run(command, hide=True, warn=True, timeout=timeout)

            # 🚀 绝杀：返回前强行清洗所有的控制字符和颜色代码
            raw_stdout = result.stdout.strip()
            raw_stderr = result.stderr.strip()
            clean_out = ANSI_ESCAPE.sub('', raw_stdout) if raw_stdout else ""
            clean_err = ANSI_ESCAPE.sub('', raw_stderr) if raw_stderr else ""

            # 🚀 补丁 1：物理防爆破截断。限制 stdout 最多返回 2000 字符，stderr 1000 字符
            # 如果超长，自动追加提示，引导大模型使用 tail 或 grep
            max_out_len, max_err_len = 2000, 1000
            if len(clean_out) > max_out_len:
                clean_out = clean_out[:max_out_len] + "\n...[输出过长已被系统物理截断，请使用 grep 过滤或 tail 查看尾部]..."
            if len(clean_err) > max_err_len:
                clean_err = clean_err[:max_err_len] + "\n...[报错过长已被系统物理截断]..."

            # 🚀 补丁 2：多语言报错兜底嗅探。把各种本地化报错翻译成大模型绝对能懂的系统提示
            not_found_keywords = ["No such file or directory", "没有那个文件或目录", "not found", "无法访问"]
            if clean_err and any(k in clean_err for k in not_found_keywords):
                clean_err += "\n[系统提示：目标文件或命令不存在。请先使用 ls 检查路径，或确认服务是否安装。]"

            return {
                "status": "success" if result.ok else "failed",
                "exit_code": result.return_code,
                "stdout": clean_out,
                "stderr": clean_err,
                "command": command
            }

        except CommandTimedOut:
            return {
                "status": "timeout",
                "message": f"警告：命令执行超过设定的 {timeout} 秒，已被强制阻断！",
                "command": command
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"执行期间发生系统异常: {str(e)}",
                "command": command
            }

    def close(self):
        if self.is_connected:
            self.conn.close()
            self.is_connected = False

# ================= 测试沙盒 =================
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()

    ssh = RobustSSHClient(
        host=os.getenv("TARGET_HOST", "172.20.10.8"),
        user=os.getenv("TARGET_USER", "wl"),
        password=os.getenv("TARGET_PASSWORD", "4399")
    )

    if ssh.connect():
        print("\n--- 测试 1: 正常命令探针 (uname -a) ---")
        res1 = ssh.execute_command("uname -a")
        print(res1)

        print("\n--- 测试 2: 错误流分离测试 (ls 一个不存在的目录) ---")
        res2 = ssh.execute_command("ls /this_folder_does_not_exist_999")
        print(res2)

        print("\n--- 测试 3: 极限超时阻断 (要求靶机 sleep 5秒，但限制 2秒必须返回) ---")
        res3 = ssh.execute_command("sleep 5", timeout=2)
        print(res3)

        ssh.close()
