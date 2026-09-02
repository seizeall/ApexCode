# API 配置说明

ApexCode 使用 OpenAI Chat Completions 兼容接口，也支持 Anthropic Messages 兼容网关。密钥只从本机 `.env` 或环境变量读取，不会写入代码仓库。

## Windows 一键版

安装版：双击 `ApexCode-Setup.exe`，程序安装到 `%LOCALAPPDATA%\ApexCode`，创建桌面快捷方式，并首次打开 `.env`。填写配置、保存并重启 ApexCode 即可。

便携版：解压 `ApexCode-Windows.zip`，将 `.env.example` 复制为 `.env`，用记事本打开并至少填写 `CODING_AGENT_API_KEY`，然后双击 `ApexCode.exe`。程序会自动打开 `http://127.0.0.1:8000`，工作区是同目录的 `workspace` 文件夹。

也可以在网页右上角点击“API 配置”，填写 API Base URL、API Key、Model Name 和本地工作区绝对路径。保存后立即对后续任务生效；接口不会把密钥返回给浏览器，密钥只保存在本机未入库的 `.env`。Agent 的列目录、读取、搜索、写入、补丁和命令工具只能操作该工作区，不能越界访问其他路径。

任务执行时，页面会持续显示当前阶段和已用时间；执行详情只展示精简后的工具摘要，不传输完整文件正文或大段命令日志。工作区包含 `index.html` 后，顶部“预览网站”按钮会自动启用并在应用内渲染。对于 Vite、React 等工程，先让 Agent 执行构建，预览器会优先选择 `dist/index.html` 或 `build/index.html`。

界面字段映射：`API_BASE_URL` 对应 `CODING_AGENT_BASE_URL`，`API_KEY` 对应 `CODING_AGENT_API_KEY`，`MODEL_NAME` 对应 `CODING_AGENT_MODEL`。

### OpenAI / OpenAI 兼容网关

```env
CODING_AGENT_API_KEY=sk-你的密钥
CODING_AGENT_BASE_URL=https://api.openai.com/v1
CODING_AGENT_MODEL=gpt-4o-mini
```

常见兼容网关只需替换 `BASE_URL` 和 `MODEL`，例如 `https://your-gateway.example.com/v1`。`BASE_URL` 可以填写到 `/v1`，程序会自动请求 `/chat/completions`；也可以直接填写完整的 `/chat/completions` 地址。

### Anthropic Messages 兼容网关

```env
CODING_AGENT_API_KEY=sk-ant-你的密钥
CODING_AGENT_BASE_URL=https://api.anthropic.com/v1
CODING_AGENT_MODEL=claude-3-5-sonnet-latest
```

程序会自动识别 URL 中的 `anthropic`，转换为 Messages 请求，并发送 `x-api-key` 和 `anthropic-version` 请求头。

## 可调参数

`CODING_AGENT_WORKSPACE` 工作区路径（源码运行时使用；一键版固定为 `workspace`）；`CODING_AGENT_MAX_STEPS` 单任务最大轮数，默认 12；`CODING_AGENT_MAX_TOOL_CALLS` 工具调用上限，默认 40；`CODING_AGENT_COMMAND_TIMEOUT` 本地命令超时秒数，默认 30；`CODING_AGENT_MODEL_TIMEOUT` 模型请求超时秒数，默认 60；`CODING_AGENT_MODEL_MAX_TOKENS` 单次模型输出上限，默认 2048，降低该值可减少等待时间；`CODING_AGENT_MODEL_RETRIES` 网络失败重试次数，默认 2。

不要把真实 `.env` 提交到 Git。遇到“未配置 API key”时，检查文件名是否确实为 `.env`、是否与 exe 同目录，以及是否重启了程序。

## HTTP 接口

服务启动后可访问 `/api/docs` 查看 Swagger。主要接口：`GET /api/config` 配置状态；`POST /api/sessions` 新建会话；`GET /api/sessions` 会话列表；`POST /api/sessions/{id}/messages` 提交任务（`mode` 为 `ask`、`plan` 或 `full`）；`GET /api/runs/{id}/events` SSE 执行事件和进度心跳；`POST /api/runs/{id}/cancel` 停止任务；`POST /api/workspace/upload` 上传文件；`GET /api/workspace/tree` 查看工作区目录；`GET /api/preview/candidates` 获取网站预览入口。
