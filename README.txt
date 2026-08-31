ApexCode 是一个本地优先的编程智能体。它通过兼容接口理解任务，在限定工作区内读取文件、搜索文本、修改文件和运行开发命令；有副作用的操作会先等待确认。CLI 与网页使用同一套 Agent 核心。

安装：
1. Python 3.10+ 创建虚拟环境：python -m venv .venv；Windows 激活：.venv\\Scripts\\Activate.ps1
2. 安装依赖：pip install -r requirements.txt
3. 复制 .env.example 为 .env，或设置 CODING_AGENT_API_KEY、CODING_AGENT_BASE_URL、CODING_AGENT_MODEL、CODING_AGENT_WORKSPACE。

运行 CLI：python -m app.cli --mode ask "检查 examples/demo_project 并整理 TODO"
模式：`ask` 先让模型确认需求；`plan` 只输出执行计划，不使用本地工具；`full` 在工作区和危险命令拦截仍有效的前提下自动完成，不逐次询问确认。
运行网页：python -m uvicorn app.web.app:app --host 127.0.0.1 --port 8000，然后打开 http://127.0.0.1:8000
测试：pytest

项目不使用 Agent 框架或托管执行工具。模型只负责提出计划和工具调用，本地服务负责路径校验、确认、执行和错误回传。可用工具包括列目录、读文件、文本搜索、写文件、应用 unified diff 补丁和运行命令；当前版本不提供删除文件工具。网页支持上传单个文件或整个项目目录，上传内容只会写入当前工作区；默认单个上传文件不超过 10 MB、单次总量不超过 100 MB，最多 200 个文件，可通过 `CODING_AGENT_MAX_UPLOAD_FILE_BYTES` 和 `CODING_AGENT_MAX_UPLOAD_TOTAL_BYTES` 调整。图片会按二进制文件保存，当前模型工具不会直接解析图片内容。网页任务状态通过 SSE 实时更新，执行详情默认收起；对话区提供可展开的执行过程摘要，不展示模型内部思考。会话支持新建、重命名、删除和历史恢复。

工程边界：会话历史保存到工作区下被忽略的 .apexcode/sessions.json；上下文超过 80000 字符时保留最近消息；模型请求默认最多重试 2 次，单个任务最多 12 轮、40 次工具调用。网页提供停止任务按钮，取消会终止正在等待或运行中的本地命令。真实密钥只从环境变量或未入库的 .env 读取。
