import chromadb
import os

class VectorKnowledgeBase:
    def __init__(self):
        # 在本地创建一个持久化的向量数据库文件夹
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "vector_db")
        self.client = chromadb.PersistentClient(path=db_path)

        # 获取或创建名为 "xfusion_manuals" 的集合
        self.collection = self.client.get_or_create_collection(name="xfusion_manuals")

        # 如果库是空的，自动注入一些测试的"超聚变官方知识"
        if self.collection.count() == 0:
            self._inject_seed_knowledge()

    def _inject_seed_knowledge(self):
        """塞入赛场可能用到的救命知识 (赛前你可以疯狂往这里加东西)"""
        print("[RAG] 检测到知识库为空，正在注入超聚变特种运维手册...")
        documents = [
            # ==================== GPU / DGX OS 专项 ====================
            "FusionXpark 遇到 DGX OS 显卡掉线时，请勿重启系统，应优先执行 nvidia-smi -r。",
            "nvidia-smi 返回 No devices were found 时，先执行 lspci | grep -i nvidia 确认硬件是否被识别，再检查 nvidia-persistenced 服务是否运行。",
            "GPU 显存泄漏导致 OOM 时，使用 fuser -v /dev/nvidia* 找出占用进程，优先 kill 僵尸进程而非重启驱动。",

            # ==================== Nginx / Web 服务 ====================
            "若 Nginx 报 502 Bad Gateway 且带有 socket 拒绝报错，通常是 php-fpm 进程卡死，请执行 systemctl restart php-fpm。",
            "Nginx 报 504 Gateway Timeout 时，检查后端服务响应时间。先查看后端服务日志，再用 curl 从本机直连后端端口测试延迟。必要时调大 proxy_read_timeout。",
            "Nginx 报 403 Forbidden 时，90% 的情况是文件权限不足或 index 指令配置错误。检查 nginx 用户是否有读权限，以及目录是否缺少 x 权限。",
            "Nginx 报 bind() to 0.0.0.0:80 failed (98: Address already in use) 时，说明 80 端口被占用。用 ss -tlnp | grep :80 找出占用进程，kill 掉后再启动。",
            "Nginx 配置语法检查：修改任何 /etc/nginx/ 下文件后，必须先执行 nginx -t 测试配置语法，确认 OK 后再 reload。千万不要在语法报错时直接 restart。",
            "Nginx 报 upstream timed out 时，不要急着调大超时参数。先用 curl -v http://127.0.0.1:后端端口 确认后端服务是否真的在响应，排查是不是后端挂了而非超时不够。",
            "Nginx 日志默认在 /var/log/nginx/access.log 和 /var/log/nginx/error.log。排查问题时先看 error.log 的最后 50 行，99% 的根因都在里面。",

            # ==================== Apache 专项 ====================
            "Apache 报 AH00558: Could not reliably determine the server's fully qualified domain name 只是警告，不影响服务。在 /etc/apache2/apache2.conf 末尾加 ServerName localhost 即可消除。",
            "Apache 报 Address already in use: AH00072 时，说明有其他进程占用了 Apache 的监听端口。使用 ss -tlnp 或 lsof -i 排查端口冲突。",

            # ==================== MySQL / MariaDB ====================
            "MySQL 报 Can't connect to local MySQL server through socket 时，先检查 mysqld 进程是否存活：systemctl status mysql 或 ps aux | grep mysqld。",
            "MySQL 报 Too many connections 时，说明连接数打满。先执行 SHOW PROCESSLIST 查看当前连接，临时增大 max_connections：SET GLOBAL max_connections = 500。然后排查是哪个应用连接泄漏。",
            "MySQL 报 Table is marked as crashed 时，说明表损坏。进入 MySQL 执行 REPAIR TABLE 表名; 或使用 myisamchk 工具修复。如果是 InnoDB，尝试 innodb_force_recovery 模式启动后导出数据。",
            "MySQL 磁盘满导致写入失败时，先用 df -h 确认磁盘使用率，再用 du -sh /var/lib/mysql/* 找出大库或大表。必要时清理 binlog：PURGE BINARY LOGS BEFORE NOW() - INTERVAL 3 DAY。",
            "MySQL 慢查询排查：先查看是否开启慢查询日志 SHOW VARIABLES LIKE 'slow_query%'。如果开启了，分析 /var/lib/mysql/*-slow.log 找出执行时间超过 long_query_time 的 SQL 语句。",

            # ==================== PostgreSQL ====================
            "PostgreSQL 报 could not connect to server: Connection refused 时，先检查 pg_hba.conf 是否允许当前 IP 连接，再确认 listen_addresses 是否包含了 '*' 或目标 IP。",
            "PostgreSQL 报 FATAL: sorry, too many clients already 时，增大 max_connections 需要重启，但临时可以先 kill 掉空闲连接：SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle'。",

            # ==================== Docker 容器 ====================
            "Docker 容器状态为 Exited(137) 时，说明容器被 OOM Killer 杀掉了。查看容器内存限制 docker inspect 容器名 | grep Memory，并增大内存限制或排查容器内内存泄漏。",
            "Docker 报 Cannot connect to the Docker daemon 时，先确认 dockerd 是否运行：systemctl status docker。如果服务是 active 的但仍报错，检查 DOCKER_HOST 环境变量是否错误指向了不存在的 socket。",
            "Docker 容器日志过多导致磁盘满：docker system prune -a --volumes 清理无用容器和卷，或设置每个容器的日志上限 --log-opt max-size=10m --log-opt max-file=3。",
            "Docker 镜像拉取慢或失败时，先测试 docker pull hello-world 确认 Docker Hub 可达性。如果墙或断网，配置国内镜像加速器 /etc/docker/daemon.json 中的 registry-mirrors。",
            "Docker 容器内 DNS 解析失败时，检查宿主机的 /etc/docker/daemon.json 中的 dns 配置。临时验证可以在容器内直接 nslookup 目标域名，排查是 DNS 服务器不可达还是域名本身解析失败。",

            # ==================== 磁盘 / 存储 ====================
            "df -h 显示磁盘未满但写入报 No space left on device 时，极有可能是 inode 用完了。执行 df -i 查看 inode 使用率。inode 耗尽通常是小文件过多（如 session 文件、缓存文件、邮件队列）。",
            "磁盘 I/O 过高导致系统响应慢：先用 iostat -x 1 5 查看磁盘利用率（%util）和等待时间（await）。用 iotop -o 找出读写最多的进程，再决定限流还是 kill。",
            "某个目录占用过大想清理时，用 du -sh /* 2>/dev/null | sort -hr | head -20 找出根目录下最大的 20 个目录逐层排查。不要直接用 rm -rf 删除不明内容。",
            "lvm 逻辑卷满需要扩容：先用 vgs 确认卷组有剩余空间，再执行 lvextend -L +1G /dev/卷组名/逻辑卷名 -r（-r 自动扩容文件系统）。如果卷组也没空间了，需要先加物理磁盘或扩容分区。",

            # ==================== CPU / 内存 / 性能 ====================
            "系统 CPU 使用率高但 top 看不到异常进程时，可能是短命进程或内核线程。用 perf top 或 pidstat -l 1 捕获高频切换的短命进程。",
            "free -m 显示 available 内存很低但 used 内存也不高时，不要慌——Linux 的内存管理会把空闲内存用作缓存（buff/cache），这部分在需要时会自动释放。真正需要关注的是 swap 使用量。",
            "Swap 使用持续增长说明物理内存不足。用 smem -rs uss 查看哪个进程实际占用内存最多（RSS 可能包含共享内存，USS 更准）。考虑增加物理内存或限制进程内存。",
            "大量僵尸进程（状态为 Z）堆积时，这些进程已经结束但父进程未 wait 回收。找到父进程（ps -eo ppid,pid,stat,cmd | grep 'Z'）并向其发送 SIGCHLD 信号。如果父进程是 init/systemd，僵尸会自动回收。",
            "服务器负载（load average）持续很高但 CPU 使用率不高时，通常是在等 I/O。用 iostat 查看磁盘 await 指标，用 iotop 找出读写元凶。如果是 NFS 卡顿，也会导致 D 状态进程积压推高 load。",

            # ==================== 网络诊断 ====================
            "遇到 172.20 网段 SSH 无法连接时，大概率是靶机的 ufw 防火墙拦截了 22 端口，请通过控制台放行。",
            "网络不通排查流程：先 ping 网关确认本地网络正常，再 ping 目标 IP 确认路由可达，然后 telnet 目标 IP 端口 确认端口开放。如果是 DNS 解析失败，用 nslookup 或 dig 检查。",
            "curl 返回 Could not resolve host 时，检查 /etc/resolv.conf 中的 nameserver 是否可访问。临时更换 DNS：`echo 'nameserver 114.114.114.114' | sudo tee /etc/resolv.conf`。",
            "端口被占用排查：ss -tlnp 查看所有 TCP 监听端口及其进程。lsof -i :端口号 查特定端口。fuser 端口号/tcp 找出占用进程 PID 后直接 kill。",
            "防火墙排查：iptables -L -n -v 查看规则链和命中计数。ufw status verbose 查看 ufw 状态。注意 Docker 会自动添加 iptables 规则，可能绕过 ufw 限制。",
            "网络丢包排查：mtr 目标IP 做持续路由追踪，比 ping 和 traceroute 更直观。重点关注丢包率在哪个跳数开始出现，判断是本端、中间路由还是对端的问题。",
            "SSL 证书过期导致 HTTPS 访问失败时，用 openssl s_client -connect 域名:443 -servername 域名 2>/dev/null | openssl x509 -noout -dates 查看证书有效期。",

            # ==================== Systemd 服务管理 ====================
            "systemctl status 服务名 显示服务状态异常时，第一时间执行 journalctl -u 服务名 -n 50 --no-pager 看最近的日志。日志里面一定有线索，不要猜。",
            "systemctl start 服务失败且没有明显报错时，先执行 systemctl cat 服务名 看 Unit 文件内容，再用 journalctl -xe 查看系统级日志。常见原因：ExecStart 路径写错、用户权限不足、依赖服务未启动。",
            "修改了 systemd unit 文件后必须执行 systemctl daemon-reload 才能生效。这是最常见的踩坑点——改了配置没 reload，重启服务用的还是旧配置。",
            "服务设置了 Restart=always 但反复重启失败时，systemd 会触发 StartLimitBurst 限制然后停止尝试。查看 systemctl status 服务名 输出中是否有 start request repeated too quickly 提示。",

            # ==================== 包管理器 ====================
            "apt update 报 lock 或 lock-frontend 错误时，说明有另一个 apt 进程或图形化更新程序占用了锁。先 ps aux | grep apt 找出残留进程并 kill，再用 rm -f /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/cache/apt/archives/lock 删锁，最后执行 dpkg --configure -a 修复中断的安装。",
            "apt install 报 Unmet dependencies 时，先执行 apt update 更新包列表，再尝试 apt --fix-broken install 自动修复依赖。如果还不行，用 apt-cache policy 包名 查看版本详情。",
            "yum/dnf 安装卡死或报错时，先 kill 掉残留的 yum/dnf 进程，再执行 rm -f /var/run/yum.pid。如果 rpmdb 损坏，执行 rpm --rebuilddb 重建数据库。",
            "pip install 报 externally-managed-environment 错误时，要么使用虚拟环境（python -m venv venv && source venv/bin/activate），要么加 --break-system-packages 标志（不推荐）。优先用 venv 隔离环境。",

            # ==================== SSH 远程管理 ====================
            "SSH 连接报 Permission denied (publickey,password) 时，先用 ssh -v 目标 看详细日志。可能是密码错误、密钥权限不对（~/.ssh 目录应为 700，密钥文件 600），或者 sshd 配置禁用了密码登录。",
            "SSH 连接成功但立即断开 Connection closed by remote host 时，可能是 sshd 配置了 AllowUsers/DenyUsers 限制，或者用户的 shell 写错了（如 /sbin/nologin）。检查 /etc/ssh/sshd_config 和 /etc/passwd。",
            "SSH 免密登录配置失败：确保本地公钥（~/.ssh/id_rsa.pub）已追加到目标机器的 ~/.ssh/authorized_keys，且目标机器上 ~/.ssh 权限为 700，authorized_keys 权限为 600。同时检查 /etc/ssh/sshd_config 中 PubkeyAuthentication yes 是否启用。",

            # ==================== 文件系统 / 权限 ====================
            "【Linux 高级防坑指南/权限越权】：在需要 root 权限修改系统级配置文件（如 /etc/sudoers, /etc/ssh/sshd_config）时，严禁使用 `sudo echo 'x' >> file`，这会导致 Permission denied。标准且唯一的极客解法是使用管道符配合 tee 命令，格式为：`echo 'x' | sudo tee -a /path/to/file`。如果你在排查中需要修改配置，请务必使用此格式！",
            "文件系统只读（Read-only file system）时，说明文件系统检测到异常并自动切换为只读保护。先执行 dmesg | tail -50 查看内核日志确认原因。如果是磁盘坏块，立即备份数据。临时修复：mount -o remount,rw /。",
            "chmod 或 chown 误操作导致系统关键文件权限异常时，可以用 rpm --setperms 包名 或 dpkg --verify 对比原始权限，或者用 getfacl/setfacl 精细化恢复。",
            "查找占用磁盘空间的大文件：find / -type f -size +1G 2>/dev/null。查找最近 24 小时内修改的文件：find / -type f -mtime -1 2>/dev/null。查找指定目录下大于 100M 的文件：find /目标目录 -type f -size +100M -exec ls -lh {} \\;。",

            # ==================== 日志排查 ====================
            "排查任何服务问题时，优先看四个地方：1) systemctl status 服务名 看最后几行动态；2) journalctl -u 服务名 -n 100 --no-pager 看 journal 日志；3) /var/log/下对应服务的日志文件；4) dmesg | tail -30 看内核日志（OOM、磁盘错误、网络断开等底层事件）。",
            "journalctl 常用排查技巧：按时间范围查 journalctl --since '2025-01-01 10:00:00' --until '2025-01-01 11:00:00'；按优先级查 journalctl -p err -n 50；实时跟踪 journalctl -f -u 服务名。",
            "日志中频繁出现 Out of memory: Kill process 说明 OOM Killer 在工作。用 dmesg | grep -i oom 查看被杀进程记录。用 free -h 和 top 分析内存使用，可能需要增加物理内存或限制进程内存。",

            # ==================== 进程管理 ====================
            "kill -9 是最后手段。标准流程：先用 kill -15（SIGTERM）优雅终止进程，给进程清理资源的机会。等待 5-10 秒后检查进程是否还在，如果还活着再用 kill -9。直接 kill -9 可能导致数据丢失或 socket 文件残留。",
            "某个进程 CPU 100% 但不知道在干什么：用 strace -p PID -c 统计系统调用分布，或用 strace -p PID 实时查看系统调用序列。用 lsof -p PID 查看进程打开了哪些文件和网络连接。",
            "服务进程假死不响应请求但进程还在：先看 lsof -p PID 看是否卡在某个文件或网络连接上。再看 cat /proc/PID/stack 查看内核栈，判断是卡在 I/O 等待还是死锁。",

            # ==================== 安全 / 防火墙 ====================
            "发现陌生进程疑似挖矿木马时，先查看 /proc/PID/exe 确认是从哪个可执行文件启动的，再检查 crontab -l 和 systemctl list-timers 看是否有持久化定时任务。确认恶意后，kill -9 进程，删除可执行文件和定时任务，最后检查 /etc/passwd 和 authorized_keys 有没有被添加后门账户。",
            "检查是否有异常网络连接：ss -tlnp 看所有监听端口，ss -tanp 看所有建立中的连接。重点排查监听在非标准端口且进程名可疑的连接。netstat -tlnp 是备用命令。",
            "用户登录安全检查：last -20 看最近登录记录。who 看当前在线用户。cat /var/log/auth.log | grep Failed 看失败的登录尝试。如果发现大量外网 IP 的暴力破解尝试，建议安装 fail2ban。",
            "sudo 提权安全检查：grep -E 'sudo.*COMMAND' /var/log/auth.log 查看最近所有的 sudo 执行记录。visudo 检查 /etc/sudoers 是否有可疑的 NOPASSWD 配置。",

            # ==================== 常见报错快速修复 ====================
            "cannot create regular file ... Permission denied：权限不足，需要 sudo 或用 chmod/chown 修改目标目录权限。",
            "command not found：命令未安装或不在 PATH 中。先用 which 命令名 查路径。如果是未安装，用包管理器安装：apt install 包名 或 yum install 包名。",
            "Segmentation fault (core dumped)：程序发生段错误，通常是内存越界访问。用 dmesg | tail 查看内核记录。如果是你自己编译的代码，用 gdb 加载 core dump 分析。如果是系统服务，尝试重装该软件包。",
            "Too many open files：文件描述符上限被耗尽。先查当前限制 ulimit -n，临时调大 ulimit -n 65535。永久修改需编辑 /etc/security/limits.conf 加 * - nofile 65535。同时排查是否有文件句柄泄漏（lsof 看到大量重复文件的进程）。",
            "Connection refused：目标端口没有被任何进程监听，或者 iptables 规则 REJECT 了该端口。先在本机 ss -tlnp | grep 端口 确认监听存在，再 iptables -L INPUT 检查防火墙规则。",
            "No route to host：网络层不可达，通常是机器不在同一网段且没有路由配置。先 ping 网关确认本地网络正常，再 traceroute 目标 IP 定位断在哪里。",

            # ==================== 性能快速诊断 ====================
            "系统突然变慢的黄金四步排查法：1) top 看 CPU 和内存、负载（load average）；2) free -h 看内存和 swap；3) df -h 和 df -i 看磁盘和 inode；4) iostat -x 1 3 看磁盘 I/O。这四步能在 30 秒内定位 80% 的性能问题。",
            "网站响应慢但服务器负载正常时，问题可能在网络延迟或带宽。用 curl -w '@curl-format.txt' -o /dev/null -s 目标URL 看各阶段耗时（DNS、TCP、SSL、TTFB、传输）。特别注意 time_starttransfer（TTFB），它反映后端处理时间。",

            # ==================== 安全红线 / FATAL ====================
            "严禁在任何情况下执行 rm -rf / 或以 / 为目标的递归删除命令，即使加了 --no-preserve-root 也不行。清理系统垃圾文件必须在指定目录范围内操作。",
            "严禁修改 /etc/passwd、/etc/shadow、/etc/sudoers 而不备份。修改前必须 cp 一份带 .bak 后缀的备份。如果 sudoers 改错，用 pkexec visudo 或进入单用户模式恢复。",

            # ==================== DGX OS / NVIDIA GPU 专项 ====================
            "DGX OS 是基于 Ubuntu 的 NVIDIA 定制操作系统，常用于 AI 训练。DGX OS 常见问题：DCGM 版本不匹配、NVSM 健康检查报空文件夹、Mellanox 固件不自动更新、nvidia-release-upgrade 虚假报错。排查 GPU 问题时先跑 nvidia-smi 和 dcgmi discovery -l。",
            "DGX OS 上如果 nvidia-smi 卡住或超时，通常是因为 GPU 驱动状态异常或某个 GPU 已掉线。先用 lspci | grep -i nvidia 确认所有 GPU 在 PCIe 总线上可见，再检查 nvidia-persistenced 服务是否运行，最后尝试 nvidia-smi -r 重置 GPU。",
            "DGX OS 上运行 AI 训练时出现 CUDA out of memory (OOM) 错误，不要立即减小 batch size。先用 nvidia-smi 查看是否有其他进程占用了 GPU 显存（fuser -v /dev/nvidia*），kill 掉僵尸进程后再试。如果显存确实不足，降低模型精度（如 FP16）或使用梯度累积。",
            "DGX OS 上 nvidia-fabricmanager 服务对多 GPU 通信至关重要。如果 NCCL 初始化失败或报 network error，先检查 fabricmanager 状态：systemctl status nvidia-fabricmanager。如果挂了，重启它：systemctl restart nvidia-fabricmanager。",
            "DGX OS 上 /tmp 目录跑 MPI 任务可能导致系统变慢甚至内核 BUG。因为 ext4 上的 /tmp 不是为高频 I/O 设计的。解决方法：让 MPI 任务使用 /dev/shm（tmpfs），例如 export TMPDIR=/dev/shm。",

            # ==================== Systemd 深度排错 ====================
            "systemd 服务反复重启后突然停止，日志出现 start-limit-hit 时，说明服务在 StartLimitIntervalSec（默认10秒）内失败次数超过 StartLimitBurst（默认5次），systemd 判定为故障风暴并拒绝继续重启。解决方法：先修复根因，再执行 systemctl reset-failed 服务名 清除失败计数器，然后重新启动。",
            "systemd 服务报 status=203/EXEC 错误时，说明 systemd 无法执行 ExecStart 中指定的程序。常见原因：(1) 可执行文件路径写错了；(2) 文件缺少执行权限 (chmod +x)；(3) SELinux 或 AppArmor 阻止了执行。用 ls -la 检查文件是否存在且有 x 权限，用 ausearch -m avc 查 SELinux 拦截日志。",
            "systemd 的 KillMode=process 有风险：如果设为 process 而非默认的 control-group，系统只杀主进程而不杀子进程，可能导致僵尸进程堆积最终触发 OOM。除非有特殊需求，否则保持 KillMode=control-group（默认值）最安全。",
            "systemd 依赖关系排查：systemctl list-dependencies 服务名 看正向依赖，systemctl list-dependencies --reverse 服务名 看反向依赖。如果服务因依赖未启动而卡住，考虑把非关键的 Requires= 换成 Wants=，避免级联故障。",
            "systemd 服务启动超时：如果服务启动后卡在 activating 状态然后超时失败，检查 TimeoutStartSec 是否设得太短（默认 90 秒）。如果应用确实启动慢（如加载大模型），增大该值。同时用 journalctl -u 服务名 -f 实时跟踪启动过程看卡在哪里。",
            "systemd 服务开机启动但不执行：先确认 enable 了：systemctl is-enabled 服务名。如果显示 static 或 disabled，执行 systemctl enable 服务名。如果 unit 文件中 WantedBy= 写错了，服务也不会在预期的 target 下启动。",
            "修改 systemd unit 后执行 systemctl daemon-reload 是最基本的操作，但很多人会忘记。如果你改了 /etc/systemd/system/ 下的任何 .service 文件但服务行为没变，99% 是因为没 reload。",

            # ==================== Docker 容器深度排错 ====================
            "Docker 容器状态 Exited(137) 表示被 SIGKILL 强制杀掉，99% 的情况是 OOM Killer 干的。先用 docker inspect 容器名 --format='{{.State.OOMKilled}}' 确认是否为 OOM 导致的。如果是，增大内存限制 docker update -m 2g 容器名，或排查应用内存泄漏。",
            "Docker 容器报 exit code 139 (SIGSEGV) 表示段错误，通常是程序内存越界访问。用 dmesg | tail -20 查看内核记录的段错误详情。如果是 Python 程序，检查是否有 C 扩展版本不兼容；如果是 Java，检查 JVM 参数和堆外内存使用。",
            "Docker 容器反复重启排查流程：1) docker ps -a 看退出码；2) docker logs --tail 200 容器名 看最后日志；3) docker inspect 容器名 | grep -i oom 确认是否 OOM；4) docker stats --no-stream 容器名 看资源使用；5) dmesg -T | grep -i oom 看系统级 OOM 事件。",
            "Docker 容器镜像拉取失败或超时：先 docker pull hello-world 测试 Docker Hub 连通性。如果不通，检查 /etc/docker/daemon.json 中的 registry-mirrors 配置，或设置 HTTP 代理。国内环境建议配置阿里云或中科大镜像加速器。",
            "Docker 容器日志撑爆磁盘：默认 Docker 不限制日志大小！在 /etc/docker/daemon.json 中配置：{\"log-driver\":\"json-file\",\"log-opts\":{\"max-size\":\"100m\",\"max-file\":\"3\"}}，然后 systemctl restart docker。已有的日志用 truncate -s 0 /var/lib/docker/containers/*/*-json.log 清理。",
            "Docker 健康检查失败但容器进程正常：健康检查的 start_period 可能太短，应用还没完全启动。在 Dockerfile 中增大 HEALTHCHECK 的 --start-period=60s。如果应用监听端口变了，健康检查的 curl 目标也需要对应更新。",
            "Docker 容器内 DNS 解析失败：Docker 默认用宿主机的 /etc/resolv.conf。如果宿主机 DNS 有问题，容器也会受影响。临时解决：docker run --dns 114.114.114.114 指定 DNS。永久解决：在 /etc/docker/daemon.json 中设置 dns 字段。",
            "Docker 容器网络不通：先确认容器网络模式 docker inspect 容器名 | grep NetworkMode。默认 bridge 模式下，容器通过 docker0 网桥通信。用 docker network inspect bridge 查看子网配置。如果容器间通信失败，检查 iptables FORWARD 链是否被防火墙拦截。",

            # ==================== OOM Killer 高级处理 ====================
            "OOM Killer 频繁杀掉关键服务进程时，不要只加内存了事。先排查根因：用 ps aux --sort=-%mem | head -20 找出内存大户，用 smem -rs uss 看真实内存占用。如果是内存泄漏，需要修复应用代码；如果是正常的高内存需求，调整 oom_score_adj：echo -500 > /proc/PID/oom_score_adj 降低被杀优先级。",
            "oom_score_adj 范围是 -1000（永不杀）到 1000（优先杀）。保护关键服务：echo -1000 > /proc/$(systemctl show 服务名 -p MainPID --value)/oom_score_adj。查看某个进程当前的 oom_score：cat /proc/PID/oom_score，数值越高越容易被杀。",
            "OOM Killer 日志解读：dmesg | grep -i 'killed process' 或 journalctl -k | grep -i oom。日志中会显示被杀进程名、PID、触发 OOM 时的内存快照（Total-VM、anon-rss、file-rss）。分析这些数值可以判断是哪个进程吃了最多的内存。",

            # ==================== 磁盘问题深度排查 ====================
            "rm 删除大文件后 df -h 不释放空间：因为有一个正在运行的进程仍然持有该文件的句柄。用 lsof | grep deleted 或 lsof +L1 找出这些幽灵文件，记下 PID 和 FD 号。用 > /proc/PID/fd/FD号 清空文件内容（不杀进程立即释放空间），或重启持有句柄的进程。",
            "journald 日志占满磁盘：journalctl --disk-usage 查看当前日志占用的磁盘空间。journalctl --vacuum-time=7d 只保留最近 7 天日志。journalctl --vacuum-size=500M 限制日志总大小不超过 500M。永久设置：编辑 /etc/systemd/journald.conf，设置 SystemMaxUse=500M。",
            "logrotate 配置错误导致日志不轮转：logrotate -d /etc/logrotate.conf 做 dry-run 测试，会告诉你每条规则会怎么处理但不真正执行。常见问题：su 指令缺失（在较新系统上）、dateformat 格式不匹配、missingok 和 nomissingok 矛盾。",

            # ==================== 网络深度诊断 ====================
            "大量 TIME_WAIT 连接耗尽临时端口：ss -s 查看当前 TIME_WAIT 数量。如果过多，在 /etc/sysctl.conf 中设置：net.ipv4.tcp_tw_reuse=1（复用 TIME_WAIT 端口）和 net.ipv4.ip_local_port_range=1024 65535（扩大可用端口范围）。严禁使用 tcp_tw_recycle（内核 4.12+ 已废弃，在 NAT 环境下会丢包）。",
            "服务监听在 0.0.0.0 但外部无法访问：逐层排查：(1) 本机 curl localhost:端口 确认服务正常；(2) ss -tlnp | grep 端口 确认监听地址是 0.0.0.0 而不是 127.0.0.1；(3) iptables -L INPUT 或 ufw status 确认防火墙放行；(4) 如果用了云服务器，检查安全组规则。",
            "tcpdump 高效抓包排查网络问题：tcpdump -i 网卡名 -nn 'port 端口号' -w /tmp/capture.pcap 把包写入文件避免刷屏，然后用 tcpdump -r /tmp/capture.pcap 分析。只抓特定主机：tcpdump -i eth0 host 目标IP and port 80。排查 HTTP 问题时加 -A 以 ASCII 显示包内容。",
            "curl 排查 HTTP 问题常用参数：curl -v 显示详细请求/响应头；curl -w '@format.txt' -o /dev/null -s 输出时间分解（DNS解析、TCP握手、SSL握手、TTFB、总时间）；curl -k 跳过 SSL 证书验证（仅测试用）；curl --resolve 域名:端口:IP 绕过 DNS 直连指定 IP 测试。",

            # ==================== 安全审计与入侵检测 ====================
            "检查系统是否被入侵的快速审计清单：(1) last -20 看最近登录；(2) who 看当前在线用户；(3) lastb | head -20 看最近失败登录尝试；(4) cat /var/log/auth.log | grep 'Failed password' | tail -20 看密码暴力破解；(5) ss -tlnp 看所有监听端口是否有可疑服务；(6) crontab -l 和 cat /etc/crontab 看是否有可疑定时任务。",
            "发现异常进程疑似挖矿木马：(1) lsof -p PID 查看进程打开了哪些文件和网络连接；(2) cat /proc/PID/exe 确认可执行文件路径，用 md5sum 算 hash 对比；(3) 检查 ~/.ssh/authorized_keys 是否有异常公钥；(4) systemctl list-timers 查看系统级定时任务。确认恶意后：kill -9 PID、删除可执行文件和定时任务、清除后门公钥。",
            "auditd 审计关键文件变更：安装 auditd 后，设置规则监控 /etc/passwd、/etc/shadow、/etc/sudoers 的写操作。ausearch -k user_modify -i 查看最近的账户变更记录。aureport -au -i 查看认证事件报告。要修改 auditd 规则，编辑 /etc/audit/rules.d/audit.rules 后重启 auditd。",
            "fail2ban 防止 SSH 暴力破解：安装后编辑 /etc/fail2ban/jail.local，设置 [sshd] 段 enabled=true, maxretry=5, bantime=3600, findtime=600。这样 10 分钟内失败 5 次的 IP 将被封禁 1 小时。fail2ban-client status sshd 查看当前封禁状态。",
            "查找系统中有 SUID 权限的文件（可用于本地提权）：find / -perm -4000 -type f 2>/dev/null。正常情况下 /usr/bin/passwd、/usr/bin/sudo 有 SUID 是正常的。如果发现 /tmp 或 /home 下的文件有 SUID 位，高度可疑。查找所有用户可写文件：find / -perm -0002 -type f ! -path '/proc/*' 2>/dev/null。",
            "Linux 安全基线快速检查脚本：用 awk -F: '($2 == \"\" || $2 == \"!\") {print $1}' /etc/shadow 检查空密码账户；awk -F: '($3 == 0) {print $1}' /etc/passwd 检查 UID 为 0 的非 root 账户；grep '^PermitRootLogin' /etc/ssh/sshd_config 确认 root SSH 登录是否禁用。",

            # ==================== 高负载低 CPU 专项 ====================
            "系统负载（load average）很高但 CPU 使用率低，99% 是 I/O 瓶颈。负载不仅统计正在用 CPU 的进程，还统计等待 I/O 的 D 状态进程。用 ps aux | grep ' D' 找出 D 状态进程（不可中断睡眠），用 iostat -x 1 5 看磁盘 await 和 %util 指标。常见根因：NFS 挂载卡顿、磁盘硬件故障、大量 swap 换入换出。",
            "top 中 %wa (iowait) 很高说明 CPU 在等磁盘。用 iotop -o 找出正在做 I/O 的前几个进程。如果是数据库进程，查看慢查询日志；如果是 Web 服务器，检查是否在频繁写 access log。SSD 上 await 超过 10ms 就已经偏高了，HDD 上超过 50ms 需要关注。",

            # ==================== 关键内核参数调优 ====================
            "内核参数临时修改：sysctl -w 参数名=值。永久修改：写入 /etc/sysctl.conf 或 /etc/sysctl.d/99-custom.conf，然后 sysctl -p 使其生效。调优前先用 sysctl -a | grep 关键词 查看当前值，调一个测一个，不要批量改。",
            "TCP 连接优化常用内核参数：net.core.somaxconn=1024（增大 TCP 监听队列）；net.ipv4.tcp_max_syn_backlog=2048（增大 SYN 队列）；net.ipv4.tcp_fin_timeout=30（缩短 FIN_WAIT2 超时）。这些参数可以缓解高并发下的连接建立失败问题。",
            "进程可打开文件数限制（Too many open files）：ulimit -n 看软限制，ulimit -n 65535 临时调大。永久生效需编辑 /etc/security/limits.conf 添加：* soft nofile 65535 和 * hard nofile 65535。对于 systemd 管理的服务，还要在 unit 文件中设置 LimitNOFILE=65535。",

            # ==================== GPU 与 CUDA 专项 ====================
            "CUDA 程序报 CUDA_ERROR_OUT_OF_MEMORY 但 nvidia-smi 显示有剩余显存：可能是显存碎片化导致的。其他进程虽然总显存占用不多，但分散在不同区域导致没有足够大的连续块。解决方法：先 kill 掉所有非必要的 GPU 进程，或者设置 CUDA_VISIBLE_DEVICES 环境变量限制程序只使用特定 GPU。",
            "nvidia-smi 报 Unable to determine the device handle：通常是驱动问题或 GPU 掉线。先执行 nvidia-smi -r 尝试 GPU 复位，如果仍不行，检查 dmesg 中是否有 nvidia 相关的错误日志。最坏情况需要重启系统或重装驱动。",
            "多 GPU 训练时 NCCL 报错 unhandled system error 或 transport error：通常是因为 GPU 间通信（NVLink/PCIe）有问题。检查 nvidia-smi topo -m 看 GPU 拓扑，确认所有 GPU 间都有 NVLink 或 PCIe 连接。如果是容器环境，需要 --ipc=host 和 --gpus all 参数。",

            # ==================== 数据库应急处理 ====================
            "MySQL/PostgreSQL 数据库连接数突然打满：先不要直接重启数据库（会断开所有现有连接导致业务中断）。在 MySQL 中先 SHOW FULL PROCESSLIST 看正在执行什么查询，批量 kill 掉慢查询或空闲连接：SELECT CONCAT('KILL ',id,';') FROM information_schema.processlist WHERE time>300 OR command='Sleep'。",
            "数据库主从同步延迟：MySQL 中 SHOW SLAVE STATUS\\G 查看 Seconds_Behind_Master 值。如果持续增长，检查是否有大事务在主库提交、从库是否有磁盘 I/O 瓶颈、网络是否丢包。临时跳过当前卡住的语句：SET GLOBAL SQL_SLAVE_SKIP_COUNTER=1; START SLAVE;（有数据不一致风险）。",

            # ==================== 文件系统应急 ====================
            "文件系统进入只读模式（Read-only file system）：这是 Linux 的保护机制，说明文件系统检测到了异常。用 dmesg | tail -30 查看内核日志确认原因（通常是磁盘坏块或 I/O 错误）。在确认硬件无问题后，mount -o remount,rw / 恢复读写。但在此之前必须确保重要数据已备份。",
            "fstab 配置错误导致系统无法启动：如果在 /etc/fstab 中加了错误的挂载项，系统可能启动到 emergency mode。修复方法：启动时在 GRUB 内核命令行加上 emergency 或 init=/bin/bash 进入紧急 shell，注释掉 /etc/fstab 中错误的行，然后重启。加 nofail 挂载选项可以防止非关键分区挂载失败阻止启动。",
        ]
        ids = [f"doc_{i}" for i in range(len(documents))]

        # 自动将文本转化为向量并存入本地数据库
        self.collection.add(documents=documents, ids=ids)

    def search_manual(self, query: str, top_k: int = 2) -> str:
        """
        RAG 动作：语义搜索官方手册
        参数：query: 遇到的报错信息或排查疑问
        """
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k
            )

            if not results['documents'][0]:
                return f"知识库中没有找到与 '{query}' 相关的官方手册建议。"

            # 把检索到的文本拼接起来喂给大模型
            context = "\n".join([f"- {doc}" for doc in results['documents'][0]])
            return f"从《超聚变运维手册》中检索到以下相关指引：\n{context}"

        except Exception as e:
            return f"检索知识库失败: {str(e)}"

# 测试沙盒
if __name__ == "__main__":
    rag = VectorKnowledgeBase()
    print(rag.search_manual("Nginx 502 怎么办？"))
