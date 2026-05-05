import sys
import os
import re
# 把 core 目录加到环境变量，方便导入咱们的脚手架
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.ssh_executor import RobustSSHClient

class SystemProbes:
    def __init__(self, ssh_client: RobustSSHClient):
        self.ssh = ssh_client

    def get_env_info(self) -> str:
        """【深度环境快照】获取 OS、身份，外加宏观的 CPU、内存与磁盘状态"""
        try:
            # 🚀 补丁 2：一条命令，把开局视野全部点亮！
            command = (
                "echo '[OS]'; cat /etc/os-release | grep PRETTY_NAME; "
                "echo '[User]'; whoami; "
                "echo '[Memory]'; free -h | awk 'NR==2{print \"Total: \"$2\", Free/Avail: \"$4\"/\"$7}'; "
                "echo '[Disk]'; df -h / | awk 'NR==2{print \"/ Usage: \"$5\" (Free: \"$4\")\"}'"
            )
            res = self.ssh.execute_command(command, timeout=5)

            if res.get("status") == "success":
                # 把乱糟糟的多行输出稍微清洗一下，变成紧凑的快照字符串
                snapshot = res["stdout"].replace('PRETTY_NAME=', '').replace('"', '').replace('\n', ' | ')
                return f"【环境快照】 {snapshot}"
            return "【环境快照】 未知 Linux 操作系统 (探针执行失败)"
        except Exception:
            return "【环境快照】 探测失败，请谨慎使用特权命令。"

    def get_system_load(self) -> str:
        """
        探针 1：一键获取 CPU、内存、磁盘的全局状态。
        极其适合作为大模型接入靶机后的第一条"望闻问切"命令。
        """
        command = """
        echo "=== CPU & Load ==="; uptime;
        echo -e "\n=== Memory ==="; free -m;
        echo -e "\n=== Disk ==="; df -h -x tmpfs -x devtmpfs
        """
        result = self.ssh.execute_command(command, timeout=10)
        if result["status"] == "success":
            return result["stdout"]
        return f"获取系统负载失败: {result['stderr']} {result.get('message', '')}"

    def check_port_status(self, port: int) -> str:
        """
        探针 2：检查某个特定端口是否存活或被占用。
        赛场高频题：比如 Nginx 挂了，或者 8080 被占用。
        增加容错机制，尝试多种命令防止靶机环境不一致。
        """
        # 🚀 补丁 3：lsof 加上 -n (不解析IP) 和 -P (不解析端口名)，彻底斩断断网时的 DNS 阻塞陷阱！
        command = f"ss -tuln | grep -E ':{port}\\b' || netstat -tuln | grep -E ':{port}\\b' || lsof -i :{port} -n -P"
        res = self.ssh.execute_command(command, timeout=10)

        if res.get("status") == "success" and res["stdout"].strip():
            return f"端口 {port} 被占用。详情:\n{res['stdout']}"
        else:
            return f"端口 {port} 未被占用或监听。"

    def fetch_error_logs(self, service_name: str, lines: int = 20) -> str:
        """获取服务的错误日志（双路嗅探：Systemd + 传统日志目录）"""
        # 🚀 补丁 1 (重申)：探针防线，绝对拒绝命令注入！
        if not re.match(r'^[\w\.-@]+$', service_name):
            return "安全拦截：服务名包含非法字符，拒绝查询。"

        # 🚀 补丁 4：为 journalctl 增加 15 秒强制超时，防止巨型日志拖死整个 Agent
        cmd_systemd = f"journalctl -u {service_name} -p \"err..alert\" --no-pager -n {lines}"
        res1 = self.ssh.execute_command(cmd_systemd, timeout=15)

        if res1.get("status") == "success" and res1.get("stdout", "").strip():
            return f"[Systemd 日志探测结果]:\n{res1['stdout']}"

        # 这里也补上超时
        cmd_file = (
            f"tail -n {lines} /var/log/{service_name}/*error*.log 2>/dev/null || "
            f"tail -n {lines} /var/log/{service_name}.log 2>/dev/null"
        )
        res2 = self.ssh.execute_command(cmd_file, timeout=15)

        if res2.get("status") == "success" and res2.get("stdout", "").strip():
            return f"[传统文件日志探测结果]:\n{res2['stdout']}"

        return f"在 journalctl 和 /var/log 常见路径下均未发现 {service_name} 的明显报错日志。"

    def test_http_connectivity(self, target: str = "http://localhost") -> str:
        """
        【外部网络探针】测试特定 URL 或 IP 的 HTTP 连通性，排查防火墙拦截或服务假死
        """
        # 🛡️ 安全锁：必须是以 http/https 开头，或者纯 IP/域名格式，绝不允许包含空格、分号、管道符！
        if not re.match(r'^(https?://)?[\w\.-]+(:\d+)?(/[^\s;|&]*)?$', target):
            return "安全拦截：Target URL 格式不合法或包含危险字符，拒绝测试。"

        # 使用 curl 进行测试，-I 仅获取请求头，-m 5 设置 5 秒超时，-s 静默模式
        cmd = f"curl -I -m 5 -s {target}"
        res = self.ssh.execute_command(cmd)

        if res.get("status") == "success" and "HTTP/" in res["stdout"]:
            # 提取第一行状态码，比如 "HTTP/1.1 200 OK"
            status_line = res["stdout"].split('\n')[0]
            return f"连通性测试成功: {target} 返回 {status_line}。说明服务正常且未被防火墙拦截。"
        elif res.get("status") == "timeout":
            return f"连通性测试超时: 无法访问 {target}。端口可能被 iptables/ufw 拦截，或网络路由不可达。"
        else:
            return f"连通性测试失败: {target} 拒绝连接或返回异常。错误详情: {res['stderr']}"

# ================= 测试沙盒 =================
if __name__ == "__main__":
    # 使用 .env 中的真实靶机信息
    import os
    from dotenv import load_dotenv
    load_dotenv()

    ssh = RobustSSHClient(
        host=os.getenv("TARGET_HOST", "172.20.10.8"),
        user=os.getenv("TARGET_USER", "wl"),
        password=os.getenv("TARGET_PASSWORD", "4399")
    )

    if ssh.connect():
        probes = SystemProbes(ssh)

        print("\n[执行探针 1: 系统全局负载]")
        print(probes.get_system_load())

        print("\n[执行探针 2: 探测 22 端口]")
        print(probes.check_port_status(22))

        print("\n[执行探针 3: 拉取 sshd 服务的报错日志]")
        print(probes.fetch_error_logs("sshd", 10))

        ssh.close()
