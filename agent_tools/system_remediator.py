import sys
import os
import re
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.ssh_executor import RobustSSHClient

class SystemRemediator:
    def __init__(self, ssh_client: RobustSSHClient):
        self.ssh = ssh_client

    def kill_process(self, pid: str, force: bool = False) -> str:
        """
        动作 1：进程绞肉机。
        赛场高频题：某个挖矿木马或死锁进程占满了 CPU，需要强制杀掉。
        """
        # 🛡️ 安全锁：PID 必须是纯数字
        if not str(pid).isdigit():
            return "安全拦截：PID 必须是纯数字，拒绝执行。"

        signal = "-9" if force else "-15"
        command = f"kill {signal} {pid}"
        result = self.ssh.execute_command(command, timeout=5)

        if result["status"] == "success":
            return f"成功发送结束信号 ({signal}) 给进程 {pid}。"
        return f"结束进程 {pid} 失败: {result['stderr']}"

    def restart_service(self, service_name: str) -> str:
        """
        动作 2：服务唤醒器。
        赛场高频题：修改了 Nginx/MySQL 配置后，必须重启服务才能生效。
        """
        # 🛡️ 优化安全锁：放宽对 `@` 符号的支持，以兼容 Systemd 实例化服务
        # 注意：坚决不要支持 `*` 号通配符，防止大模型执行 systemctl restart * 导致整个服务器雪崩
        if not re.match(r'^[\w\.-@]+$', service_name):
            return "安全拦截：服务名包含非法字符，拒绝执行。"

        command = f"systemctl restart {service_name}"
        result = self.ssh.execute_command(command, timeout=20) # 重启服务可能较慢

        if result["status"] == "success":
            # 立即跟一个 status 检查，确保真的起来了
            status_check = self.ssh.execute_command(f"systemctl is-active {service_name}", timeout=5)
            if "active" in status_check["stdout"]:
                 return f"服务 {service_name} 已成功重启并处于 active 状态。"
            return f"服务 {service_name} 重启命令已发送，但当前状态异常: {status_check['stdout']} {status_check['stderr']}"

        return f"重启服务 {service_name} 失败: {result['stderr']}"

    def docker_ops(self, container_id: str, action: str) -> str:
        """
        动作 3：容器急救箱。
        赛场高频题：微服务架构下的某个容器挂了，或者需要查看特定容器的崩溃日志。
        """
        # 🛡️ 加入 rm 高危动作白名单
        valid_actions = ["restart", "stop", "logs", "inspect", "rm"]
        if action not in valid_actions:
            return f"无效操作，仅支持: {', '.join(valid_actions)}"

        # 🛡️ 安全锁：容器名/ID 格式校验
        if not re.match(r'^[\w\.-]+$', container_id):
            return "安全拦截：容器 ID/名称 包含非法字符。"

        if action == "rm":
            # 加入 -f 强制删除，应对 CrashLoopBackOff 的僵尸容器
            command = f"docker rm -f {container_id}"
        elif action == "logs":
            # 🚀 补丁 2 (重申)：追加 2>&1，强制捕获 Java/Python 崩溃在 stderr 里的绝命堆栈
            command = f"docker logs --tail 50 {container_id} 2>&1"
        else:
            command = f"docker {action} {container_id}"

        res = self.ssh.execute_command(command, timeout=30)
        if res.get("status") == "success":
            # 如果 stdout 有内容就返回 stdout，否则提示操作完成
            return res.get("stdout", "").strip() or f"容器 {container_id} 的 {action} 操作已成功执行。"
        else:
            # 如果执行失败（比如容器不存在），必须把底层报错（可能在 stderr）返回给大模型
            err_msg = res.get("stderr", "").strip() or res.get("stdout", "").strip()
            return f"执行失败: {err_msg}"

    def clear_package_manager_lock(self) -> str:
        """
        急救动作：强行解除包管理器 (apt/yum/dnf) 的死锁状态
        """
        # 🚀 补丁 5：暴力清锁后，顺手执行 dpkg --configure -a 修复残局，防止满地狼藉
        rescue_cmd = (
            "sudo killall -9 apt apt-get dpkg yum dnf 2>/dev/null || true; "
            "sudo rm -f /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/cache/apt/archives/lock; "
            "sudo dpkg --configure -a 2>/dev/null || true"
        )
        res = self.ssh.execute_command(rescue_cmd, timeout=30)

        if res.get("status") == "success":
            return "已成功清理包管理器锁文件，并修复了中断的 dpkg 状态。现在可以安全地重新使用 apt 安装软件了。"
        else:
            return f"清理锁文件失败，可能需要手动介入。报错信息: {res.get('stderr')}"

    def force_sudo_execute(self, command: str) -> str:
        """
        【救命兜底工具】当常规的 sudo 操作因为 tty 或权限失败时，使用 stdin 盲注密码强行提权
        """
        # 🛡️ 致命防御：由于绕过了顶层执行器，必须在这里手动拦截毁灭性命令！
        from core.ssh_executor import FATAL_PATTERNS
        for pattern in FATAL_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return "安全拦截：盲注命令命中系统级毁灭模式，已被物理斩断！"

        # 🚀 防御性检查：如果探针已判定靶机为 NOPASSWD，直接绕过盲注逻辑
        sudo_needs_pwd = getattr(self.ssh, 'sudo_needs_password', None)
        if sudo_needs_pwd is False:
            # NOPASSWD 靶机：直接执行，无需密码
            wrapped_cmd = f"sudo sh -c '{command}'"
            try:
                paramiko_client = self.ssh.conn.client
                stdin, stdout, stderr = paramiko_client.exec_command(wrapped_cmd, get_pty=False)
                out = stdout.read().decode('utf-8').strip()
                err = stderr.read().decode('utf-8').strip()
                if err:
                    return f"执行报错: {err}"
                return out or "操作已成功执行 (无输出)。"
            except Exception as e:
                return f"NOPASSWD 模式执行失败: {str(e)}"

        # 需要密码的靶机：执行盲注逻辑
        pwd = getattr(self.ssh, 'password', None)
        if not pwd:
            return "强制 Sudo 失败：未找到可用的靶机密码。"

        # 使用 sh -c 包装，防止复杂的管道符被中断
        wrapped_cmd = f"sudo -S sh -c '{command}'"

        try:
            # 获取底层 Paramiko client
            paramiko_client = self.ssh.conn.client
            stdin, stdout, stderr = paramiko_client.exec_command(wrapped_cmd, get_pty=False)

            # 🚀 初赛神级逻辑：向 stdin 加密通道里塞入字节流密码并回车
            stdin.write(pwd + '\n')
            stdin.flush()

            out = stdout.read().decode('utf-8').strip()
            err = stderr.read().decode('utf-8').strip()

            # 清理可能的 [sudo] password for root: 提示信息
            err_clean = err.replace(f"[sudo] password for {self.ssh.user}:", "").strip()

            if err_clean and not out:
                return f"执行报错: {err_clean}"
            return out or "操作已成功执行 (无输出)。"

        except Exception as e:
            return f"盲注提权执行失败: {str(e)}"

    def execute_arbitrary_shell(self, command: str, justification: str) -> str:
        """
        【终极兜底工具】仅当所有预设探针和修复工具失效，且必须执行复杂的复合排查或特殊命令时调用。
        """
        # 这个工具本身不做任何正则拦截！因为它是为了突破限制而生的。
        # 它的安全完全依赖于：1. 底层 ssh_executor 的 FATAL 拦截；2. 引擎层的 HITL 拦截。

        # 为了防患于未然，我们对常见的破坏性动作再做一层极其宽泛的警告（不阻断，只警告）
        warning_msg = ""
        dangerous_keywords = ["rm ", "mv ", "chmod ", "chown ", "wget ", "curl ", ">", ">>"]
        if any(keyword in command for keyword in dangerous_keywords):
            warning_msg = "[危险动作预警] 包含文件修改或网络下载操作。\n"

        # 调用底层的执行器
        res = self.ssh.execute_command(command, timeout=30)

        if res.get("status") == "success":
            out = res.get("stdout", "").strip() or "命令已执行，无控制台输出。"
            return f"{warning_msg}执行结果:\n{out}"
        else:
            err = res.get("stderr", "").strip() or res.get("stdout", "").strip()
            return f"兜底执行失败:\n{err}"
