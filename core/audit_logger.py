import sqlite3
import json
from datetime import datetime
from typing import Any
import os

class AuditDB:
    def __init__(self):
        # 🚀 优化：将数据库放在独立的 data 文件夹下，方便 Docker 整体挂载
        base_dir = os.path.dirname(os.path.dirname(__file__))
        data_dir = os.path.join(base_dir, "data")
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)

        db_path = os.path.join(data_dir, "audit_logs.db")
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()

        # 初始化表结构
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS os_agent_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                timestamp TEXT,
                task TEXT,
                step INTEGER,
                event_type TEXT,
                content TEXT
            )
        ''')
        self.conn.commit()

    def log_event(self, session_id: str, task: str, step: int, event_type: str, content: Any):
        """记录单条事件"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 将参数或内容统一转为 JSON 字符串存储
        safe_content = json.dumps(content, ensure_ascii=False) if isinstance(content, dict) else str(content)

        self.cursor.execute(
            "INSERT INTO os_agent_audit (session_id, timestamp, task, step, event_type, content) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, now, task, step, event_type, safe_content)
        )
        self.conn.commit()

    def close(self):
        """关闭数据库连接"""
        self.conn.close()

# ================= 测试沙盒 =================
if __name__ == "__main__":
    db = AuditDB()
    db.log_event("test_session_001", "检查80端口", 1, "thought", "我需要先检查80端口是否被占用")
    db.log_event("test_session_001", "检查80端口", 2, "action", {"tool_name": "check_port", "params": {"port": 80}})
    db.log_event("test_session_001", "检查80端口", 3, "observation", "端口80空闲，未被占用")
    print("审计日志写入成功！")
    db.close()
