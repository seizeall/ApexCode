Git 仓库：https://github.com/seizeall/ApexCode

ApexCode 是一个本地优先的编程智能体。它通过 OpenAI 兼容或 Anthropic Messages 兼容接口理解任务，在限定工作区内列目录、读取和搜索文件、写入文件、应用补丁、运行命令，并用 SSE 网页实时展示阶段进度和精简后的可审计过程。工作区生成 index.html 或前端构建产物后，可以点击顶部“预览网站”在应用内直接渲染。Agent 循环、上下文裁剪、工具定义、模型响应解析、取消、超时、错误处理和危险命令拦截均由本项目自行实现，不使用 LangChain、OpenAI Agents SDK、Code Interpreter 或 Files API。

源码运行：Python 3.10+；`pip install -r requirements.txt`；复制 `.env.example` 为 `.env` 后执行 `python -m uvicorn app.web.app:app --host 127.0.0.1 --port 8000`，浏览器打开 http://127.0.0.1:8000；测试命令为 `pytest`。

Windows 交付：执行 `powershell -ExecutionPolicy Bypass -File build_windows.ps1`，生成安装包 `release/ApexCode-Setup.exe`、便携包及源码包。安装版无需管理员权限，安装后打开生成的 `.env` 填写 API key，再从桌面启动；便携版将 `.env.example` 复制为 `.env` 后双击 exe。完整 API 字段和 HTTP 接口见 `API_CONFIG.md`，两分钟演示脚本见 `DEMO_GUIDE.md`。

手动停止：双击 `Stop-ApexCode.cmd` 可关闭 ApexCode 占用的 8000-8099 端口；也可执行 `powershell -ExecutionPolicy Bypass -File stop_apexcode.ps1 -Port 8000` 关闭指定端口。

响应速度：进度提示按 1 秒刷新；输入框支持拖拽扩大并会随内容自动增高。模型输出上限默认 2048 tokens，可在 `.env` 中调整 `CODING_AGENT_MODEL_MAX_TOKENS`；实际首字延迟仍取决于 API 服务商和网络。

安全边界：真实密钥只从 `.env` 或环境变量读取；路径不能逃逸工作区；不提供删除文件工具；写文件、补丁和命令在询问模式需确认；完全模式也会拦截危险命令。会话历史保存到 `.apexcode/sessions.json`。
