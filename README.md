# ApexCode


**Git 仓库：** https://github.com/seizeall/ApexCode

## 快速开始

Windows：运行 `release/ApexCode-Setup.exe`，或解压便携包后双击 `ApexCode.exe`。在“API 配置”填写接口、Key、模型和工作区，再选择“完全”模式。

源码：

```powershell
pip install -r requirements.txt
python -m uvicorn app.web.app:app --host 127.0.0.1 --port 8000
```

访问 `http://127.0.0.1:8000`。若 exe 未打开网页，请退出旧程序、释放 `8000` 端口后重试。

## 特色功能

- 在工作区内读写、搜索、应用补丁和执行命令，拦截越界路径及危险命令。
- 通过 SSE 展示任务阶段、耗时和精简工具摘要，不暴露逐字内部思维链。
- 自动识别 HTML 或构建入口，在隔离的内置预览器中运行动态网站。
- 兼容 OpenAI Chat Completions 与 Anthropic Messages 接口。

## 实现逻辑

- **对话历史与上下文：** 消息持久化到 `.apexcode/sessions.json`；超过预算时保留系统提示与最近对话。
- **工具定义与本地执行：** `ToolRegistry` 以 Schema 声明工具并校验参数；`safe_path` 限制工作区，命令经安全检查、确认和超时控制后由本地子进程执行。
- **模型输出解析：** 适配两类模型响应并统一为 `content + tool_calls`，兼容内容块、函数调用和 JSON 信封。
- **循环终止条件：** 工具结果回填上下文；无工具调用、达到次数上限、用户取消或拒绝时结束。
- **错误处理：** 模型请求支持重试和超时；无效 JSON、参数、文件及命令错误转换为可读 SSE 事件并安全收尾。
