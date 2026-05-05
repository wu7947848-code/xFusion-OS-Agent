# ============================================================================
# xFusion OS-Agent 战术指挥台 (Makefile)
# 作用：将繁琐的 Docker 和环境拉起命令封装为极客指令
# 用法：直接在终端输入 `make` 查看可用指令
# ============================================================================

.PHONY: help start stop restart build logs clean-data vllm

# 终端颜色变量
CYAN  := \033[36m
GREEN := \033[32m
RED   := \033[31m
RESET := \033[0m

# 默认目标：显示帮助菜单
help:
	@echo "$(CYAN)=====================================================$(RESET)"
	@echo "$(CYAN)      xFusion OS-Agent // Mission Control Panel      $(RESET)"
	@echo "$(CYAN)=====================================================$(RESET)"
	@echo "使用方法: make [指令]"
	@echo ""
	@echo "$(GREEN)核心行动:$(RESET)"
	@echo "  make start      - 后台一键拉起 Agent 业务容器 (不含大模型)"
	@echo "  make stop       - 停止并移除所有相关容器"
	@echo "  make restart    - 重启 Agent 业务容器"
	@echo "  make build      - 强制重新构建 Docker 镜像 (修改依赖后使用)"
	@echo "  make logs       - 实时追踪 Agent 后端运行日志"
	@echo ""
	@echo "$(GREEN)大模型与底层支持:$(RESET)"
	@echo "  make vllm       - 执行本地算力拉起脚本 (启动 GLM 模型引擎)"
	@echo ""
	@echo "$(RED)危险操作 (Danger Zone):$(RESET)"
	@echo "  make clean-data - 彻底清空 SQLite 审计日志与 ChromaDB 向量缓存"
	@echo "$(CYAN)=====================================================$(RESET)"

# 后台拉起 Agent
start:
	@echo "$(GREEN)[+] 正在拉起 OS-Agent 核心引擎...$(RESET)"
	docker-compose up -d os-agent

# 停止容器
stop:
	@echo "$(RED)[-] 正在关闭并移除所有引擎...$(RESET)"
	docker-compose down

# 重启容器（开发调试高频使用）
restart: stop start

# 强制重构镜像
build:
	@echo "$(CYAN)[*] 正在重新构建装甲镜像... 这可能需要一点时间。$(RESET)"
	docker-compose build --no-cache os-agent

# 跟踪日志
logs:
	@echo "$(CYAN)[*] 正在接入日志流 (按 Ctrl+C 退出)...$(RESET)"
	docker-compose logs -f --tail=100 os-agent

# 唤醒本地大模型
vllm:
	@echo "$(GREEN)[+] 正在点燃 vLLM 算力引擎...$(RESET)"
	bash start_local_llm.sh

# 物理级清洗（重置环境）
clean-data:
	@echo "$(RED)[!] 警告：即将清空所有持久化数据（审计日志、知识库缓存）...$(RESET)"
	docker-compose down -v
	rm -rf data/*
	rm -rf vector_db/*
	@echo "$(GREEN)[+] 清洗完成，系统已恢复至出厂状态。$(RESET)"
