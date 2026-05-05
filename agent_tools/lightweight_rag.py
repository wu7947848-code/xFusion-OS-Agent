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
            "FusionXpark 遇到 DGX OS 显卡掉线时，请勿重启系统，应优先执行 nvidia-smi -r。",
            "若 Nginx 报 502 Bad Gateway 且带有 socket 拒绝报错，通常是 php-fpm 进程卡死，请执行 systemctl restart php-fpm。",
            "遇到 172.20 网段 SSH 无法连接时，大概率是靶机的 ufw 防火墙拦截了 22 端口，请通过控制台放行。",
            # 🚀 补丁 1：Linux 权限黑洞终极解法
            "【Linux 高级防坑指南/权限越权】：在需要 root 权限修改系统级配置文件（如 /etc/sudoers, /etc/ssh/sshd_config）时，严禁使用 `sudo echo 'x' >> file`，这会导致 Permission denied。标准且唯一的极客解法是使用管道符配合 tee 命令，格式为：`echo 'x' | sudo tee -a /path/to/file`。如果你在排查中需要修改配置，请务必使用此格式！"
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
