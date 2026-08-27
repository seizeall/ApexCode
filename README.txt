ApexCode 是一个本地优先的编程智能体。它通过兼容接口理解任务，在限定工作区内读取文件、搜索文本、修改文件和运行开发命令；有副作用的操作会先等待确认。CLI 与网页使用同一套 Agent 核心。

安装：
1. Python 3.10+ 创建虚拟环境：python -m venv .venv；Windows 激活：.venv\\Scripts\\Activate.ps1
2. 安装依赖：pip install -r requirements.txt
3. 复制 .env.example 为 .env，或设置 CODING_AGENT_API_KEY、CODING_AGENT_BASE_URL、CODING_AGENT_MODEL、CODING_AGENT_WORKSPACE。

运行 CLI：python -m app.cli "检查 examples/demo_project 并整理 TODO"
运行网页：python -m uvicorn app.web.app:app --host 127.0.0.1 --port 8000，然后打开 http://127.0.0.1:8000
测试：pytest

项目不使用 Agent 框架或托管执行工具。模型只负责提出计划和工具调用，本地服务负责路径校验、确认、执行和错误回传。当前版本不提供删除文件工具，网页任务状态通过 SSE 实时更新。
