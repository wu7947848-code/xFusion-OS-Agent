# xFusion-OS-Agent

An LLM-powered autonomous agent system with LLMOps monitoring, SSH-based remote execution, and automated system remediation capabilities.

## Features
- **LLM-Powered Automation:** Intelligent agent with flexible LLM routing
- **LLMOps Monitoring:** Integrated with Phoenix/OpenInference for observability
- **Remote Execution:** SSH-based command execution on target systems
- **Automated Remediation:** System probe and remediation agent tools
- **Alerting:** Feishu (Lark) integration for real-time notifications
- **Lightweight RAG:** Built-in retrieval-augmented generation for knowledge access
- **Audit Logging:** Comprehensive action tracing and audit trails
- **RESTful API:** FastAPI backend with streaming response support
- **Containerized:** Docker and docker-compose deployment

## Tech Stack
- **Backend:** Python, FastAPI
- **LLM:** Anthropic Claude API
- **Observability:** Phoenix / OpenInference
- **Deployment:** Docker, docker-compose
- **Frontend:** HTML/JavaScript

## Quick Start


## Project Structure
- `api.py` - FastAPI application entry point
- `core/` - Core engine (agent orchestration, LLM routing, SSH executor, audit logging)
- `agent_tools/` - Tool implementations (RAG, system probes, remediation, alerts)
- `deploy/` - Deployment configurations
- `index.html` - Web dashboard