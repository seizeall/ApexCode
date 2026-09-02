# ApexCode

<p align="center">
  <b>一个轻量级Coding Agent工作台</b>
</p>



<p align="center">
  Task Planning · Local Tool Execution · Iterative Verification · Web Preview
</p>


ApexCode是一个**简单的的Coding Agent**。它不依赖第三方Agent框架，而是直接实现“模型决策→本地工具调用→结果回填→继续决策”的Agent循环，使大语言模型能够在受约束的本地工作区中自主读取代码、搜索内容、修改文件、应用补丁、执行开发命令。

项目同时提供**Web UI、CLI和Windows一键运行版本**，兼容OpenAI Chat Completions风格接口与Anthropic Messages风格接口，并通过工作区路径限制、危险命令拦截、参数校验、执行超时和上下文裁剪等机制提高本地Agent执行的安全性与稳定性。

- **项目名称：**ApexCode
- **核心语言：**Python 3.10+
- **参数与Schema校验：**Pydantic
- **支持接口：**OpenAI-compatible API、Anthropic-compatible API
- **项目仓库：**https://github.com/seizeall/ApexCode
- **EXE安装包**：

---

## 1. 项目描述

<p align="center">
  <img src="docs/assets/apexcode-overview.png" alt="ApexCode Overview" width="100%">
</p>


<p align="center">
  <b>Figure 1. Overview of ApexCode.</b>
</p>


ApexCode的核心工作流可以概括为三个不断迭代的阶段：**Task Planning→Tool Execution→Verification & Update**。用户通过Web UI或CLI提交任务后，Agent结合对话历史和当前工作区状态进行决策；当模型需要真实文件或执行结果时，通过ToolRegistry调用本地工具；工具结果重新写回模型上下文，模型据此继续修改、验证或修复，直到任务完成、用户取消或触发安全终止条件。

---

## 2. 核心能力

ApexCode目前主要提供以下能力：

- **自主分析编程任务：**根据用户需求决定是否读取文件、搜索代码、修改项目或执行命令。
- **本地文件操作：**支持目录浏览、文本读取、全局搜索、文件写入和补丁修改。
- **本地命令执行：**能够在指定工作区中执行测试、编译、构建等开发命令。
- **Plan / Full双模式：**
  - `plan`：只生成执行计划，不调用工具、不修改文件。
  - `full`：允许Agent自主调用工具并完成任务。
- **多轮Agent循环：**每次工具结果都会回填模型上下文，使模型能够根据真实执行结果继续推理和修复。
- **上下文管理：**会话历史持久化，并在上下文超过预算时保留系统提示和最近对话。
- **安全执行：**限制文件访问范围，拦截危险命令，限制文件大小和命令执行时间。
- **实时执行反馈：**通过SSE持续向Web前端发送阶段、工具调用和运行状态。
- **网站自动预览：**自动发现`index.html`以及`dist/`、`build/`等构建目录中的入口，并在内置预览器中展示。
- **多模型接口兼容：**同时适配OpenAI-compatible和Anthropic-compatible接口。
- **Windows一键运行：**提供安装版和便携版，无需手动启动Python服务。

---

## 3. 项目文件结构

```text
ApexCode/
├── .apexcode/
│   └── sessions.json
│
├── app/
│   ├── agent/
│   │   └── service.py
│   ├── model/
│   │   └── client.py
│   ├── tools/
│   │   └── registry.py
│   ├── web/
│   │   ├── app.py
│   │   └── static/
│   │       ├── index.html
│   │       ├── app.js
│   │       └── styles.css
│   ├── cli.py
│   ├── config.py
│   ├── safety.py
│   └── session_store.py
│
├── examples/
│   └── demo_project/
│       ├── apex_flowboard/
│       ├── frontend_demo/
│       ├── bubble_sort.py
│       ├── todo.py
│       └── ...
│
├── installer/
│   ├── install.ps1
│   └── ApexCode-Setup.sed.template
│
├── release/
│   ├── ApexCode/
│   ├── ApexCode-Setup.exe
│   ├── ApexCode-Windows.zip
│   └── ApexCode-Source.zip
│
├── tests/
│   ├── test_agent.py
│   ├── test_launcher.py
│   ├── test_model.py
│   ├── test_safety.py
│   ├── test_tools.py
│   └── test_web.py
│
├── .env.example
├── API_CONFIG.md
├── build_windows.ps1
├── desktop_launcher.py
├── pyproject.toml
├── requirements.txt
├── run_web.ps1
└── README.md
```

### 3.1 核心目录说明

| 文件 / 目录               | 作用                                                         |
| ------------------------- | ------------------------------------------------------------ |
| `app/agent/service.py`    | Agent核心循环。负责系统提示词、Plan/Full模式、上下文裁剪、模型请求、工具调用、结果回填、循环终止与运行事件输出。 |
| `app/model/client.py`     | 模型通信层。负责构造OpenAI/Anthropic请求、网络重试、响应解析，以及将不同模型的返回格式统一为`content + tool_calls`。 |
| `app/tools/registry.py`   | 本地工具注册与执行中心。定义6种工具、参数Schema、文件读写、搜索、补丁应用和命令执行逻辑。 |
| `app/safety.py`           | 安全层。保证文件路径不离开工作区，并拦截删除、格式化、关机、危险Git命令等高风险操作。 |
| `app/session_store.py`    | 本地会话持久化。负责读取、保存、重命名、删除会话及其元数据。 |
| `app/config.py`           | 配置管理。读取`.env`和环境变量，管理API、模型、工作区、超时、上下文长度等参数。 |
| `app/web/app.py`          | FastAPI后端。提供会话、任务、SSE、配置、工作区浏览和网页预览等接口。 |
| `app/web/static/`         | ApexCode Web前端页面、交互脚本和样式。                       |
| `app/cli.py`              | 命令行入口，可直接从终端向Agent提交任务。                    |
| `desktop_launcher.py`     | Windows桌面版入口。自动选择本地端口、创建工作区、启动Web服务并打开浏览器。 |
| `examples/demo_project/`  | 用于展示Agent编码、修改、构建和验证能力的示例项目。          |
| `tests/`                  | 自动化测试，覆盖Agent、模型解析、安全策略、工具、Web API和启动逻辑。 |
| `release/`                | Windows安装版、便携版以及发布材料。                          |
| `.apexcode/sessions.json` | 当前工作区的会话历史持久化文件。                             |
| `.env.example`            | API和运行参数的配置模板，不包含真实密钥。                    |

---

# 4. 重要逻辑详解

## 4.1 对话历史与上下文管理

ApexCode的会话状态由`app/session_store.py`和`app/agent/service.py`共同负责。

### 会话持久化

每个会话拥有独立的`session_id`，完整历史默认存储在：

```text
.apexcode/sessions.json
```

`SessionStore`提供：

```text
load()       读取全部会话
get()        获取指定会话
save()       保存会话历史
rename()     修改会话名称
delete()     删除会话
metadata()   读取会话元数据
```

写入时不会直接覆盖原文件，而是先写入临时文件：

```text
.sessions.json.tmp
```

随后通过`replace()`原子替换正式文件，从而减少程序异常退出造成JSON文件损坏的概率。内部同时使用`asyncio.Lock`，避免多个异步请求同时修改会话文件产生竞争。

### 上下文组成

Agent每轮请求模型时，上下文大致由以下信息构成：

```text
System Prompt
Previous User / Assistant Messages
Previous Tool Calls
Previous Tool Results
Current User Prompt
```

因此模型不仅能够看到用户之前说了什么，也能看到自己已经读取过哪些文件、执行过哪些命令以及对应结果。

### 上下文裁剪

为了避免历史无限增长，`trim_context()`会计算消息文本总长度。当上下文超过：

```env
CODING_AGENT_MAX_CONTEXT_CHARS=1000000
```

系统会：

1. 始终保留System Prompt；
2. 从最新消息开始向前保留；
3. 优先保留最近的Agent交互；
4. 删除较旧的历史；
5. 通过SSE发送`context_trimmed`事件通知前端。

这种策略保证Agent在长任务中仍能保留**最近、最相关的执行状态**。

---

## 4.2 Plan模式与Full模式

ApexCode在同一个Agent核心上提供两种运行模式。

### Plan模式

Plan模式用于任务规划和人工审阅。

系统提示会额外加入：

```text
当前是计划模式：
只输出分阶段执行计划、涉及文件和验证方式，
不调用工具，不修改任何内容。
```

此时模型调用时不会提供工具Schema，因此模型无法直接修改本地项目。

适合：

- 开始复杂项目之前生成开发计划；
- 查看Agent准备修改哪些文件；
- 在正式执行前人工审查技术路线。

### Full模式

Full模式用于实际执行。

模型可以使用全部本地工具，自主执行：

```text
Read → Search → Modify → Run → Verify → Fix
```

直到任务完成。

---

## 4.3 工具的定义与本地执行

ApexCode没有使用LangChain、AutoGen等Agent框架，而是在`ToolRegistry`中自行实现工具注册、Schema声明、参数校验和本地执行。

当前共提供**6种工具**：

| Tool          | 功能                     |
| ------------- | ------------------------ |
| `list_files`  | 列出工作区中的文件与目录 |
| `read_file`   | 读取文本文件             |
| `search_text` | 在工作区中搜索文本       |
| `write_file`  | 新建或覆盖文件           |
| `apply_patch` | 对已有文件应用补丁       |
| `run_command` | 在工作区中执行开发命令   |

### Tool Schema

每个工具都会向模型暴露类似Function Calling的Schema。例如：

```json
{
  "type": "function",
  "function": {
    "name": "read_file",
    "description": "读取工作区内的文本文件。",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string"
        }
      },
      "required": ["path"]
    }
  }
}
```

模型并不是输出自然语言表示“我要读取文件”，而是生成结构化调用：

```json
{
  "name": "read_file",
  "arguments": {
    "path": "app/main.py"
  }
}
```

### 参数校验

工具参数在执行前会经过Pydantic模型校验：

```text
ListFilesArgs
ReadFileArgs
SearchTextArgs
WriteFileArgs
RunCommandArgs
ApplyPatchArgs
```

所有参数模型均设置：

```python
extra="forbid"
```

因此模型输出不存在于Schema中的额外字段时会被拒绝，而不是直接交给系统执行。

### 本地执行

工具运行位置固定为：

```text
CODING_AGENT_WORKSPACE
```

例如命令执行本质上使用：

```python
asyncio.create_subprocess_shell(
    command,
    cwd=workspace
)
```

因此测试、构建等操作均发生在用户指定的本地工作区。

### Tool Result回填

工具执行结束后，真实结果会重新加入消息列表：

```text
Assistant:
    tool_call = run_command(...)

Tool:
    returncode = 0
    stdout = ...
    stderr = ...
```

下一轮模型请求便可以根据真实执行结果继续决策。

这构成了ApexCode最核心的闭环：

```text
LLM Decision
    ↓
Tool Call
    ↓
Local Environment
    ↓
Tool Result
    ↓
LLM Decision
```

---

## 4.4 本地安全执行机制

Coding Agent能够直接操作用户文件和终端，因此ApexCode将安全控制放在工具执行之前，而不是单纯依赖模型自觉。

### 工作区路径限制

所有文件操作首先经过：

```python
safe_path(workspace, path)
```

系统会将目标路径解析为绝对路径，并检查：

```text
target.relative_to(workspace)
```

如果目标文件不属于工作区，则立即抛出`SafetyError`。

因此以下访问会被阻止：

```text
../../other_project
/etc/...
C:\Windows\...
```

### 危险命令拦截

`validate_command()`会阻止典型高风险命令，包括：

```text
format
shutdown
rm
del
erase
Remove-Item
git clean
git reset --hard
git checkout --
```

同时禁止通过：

```text
cd
pushd
set-location
```

绕过当前工作区。

### 命令超时

本地命令默认最长运行：

```env
CODING_AGENT_COMMAND_TIMEOUT=30
```

系统每隔约0.5秒检查进程状态。如果超过截止时间，则直接终止子进程并返回：

```json
{
  "ok": false,
  "timeout": true
}
```

### 用户取消

Web任务运行时维护`cancel_event`。

如果用户点击停止：

```text
cancel_event.set()
```

Agent循环和正在运行的命令都会检查该状态，并安全停止当前任务。

---

## 4.5 模型输出的解析

不同模型供应商对于Function Calling的返回结构并不完全一致，因此ApexCode在`app/model/client.py`中设计了统一的消息标准化层。

最终Agent内部统一使用：

```json
{
  "role": "assistant",
  "content": "...",
  "tool_calls": [...]
}
```

### 支持的返回形式

`normalize_message()`能够处理多种模型输出：

#### 1. 标准OpenAI Tool Calls

```json
{
  "role": "assistant",
  "tool_calls": [...]
}
```

#### 2. Legacy Function Call

```json
{
  "function_call": {
    "name": "...",
    "arguments": "..."
  }
}
```

#### 3. 内容块形式

部分兼容模型可能返回：

```json
[
  {
    "type": "text",
    "text": "..."
  },
  {
    "type": "tool_use",
    "name": "...",
    "input": {}
  }
]
```

程序会提取文本和工具调用并转化为统一格式。

#### 4. JSON Envelope

部分模型可能把工具调用作为JSON文本输出：

```json
{
  "content": "",
  "tool_calls": [...]
}
```

ApexCode也会尝试解析这种格式。

### Anthropic适配

如果`BASE_URL`包含`anthropic`，系统自动切换为Anthropic Messages请求格式：

```text
OpenAI internal messages
        ↓
_anthropic_request()
        ↓
Anthropic Messages API
        ↓
_anthropic_response()
        ↓
Unified ApexCode message
```

因此上层Agent循环不需要知道当前实际使用的是哪一种模型接口。

---

## 4.6 Agent循环

Full模式的核心逻辑位于：

```text
app/agent/service.py
```

其核心思想可以写成：

```python
while True:
    messages = trim_context(messages)

    response = model.complete(
        messages,
        tools=registry.schemas()
    )

    message = normalize_message(response)
    messages.append(message)

    if no_tool_calls:
        return final_answer

    for tool_call in tool_calls:
        result = registry.call(...)
        messages.append(tool_result)
```

实际代码还加入了安全检查、参数解析、SSE事件、取消机制、错误处理和源码输出纠正。

### 一轮Agent执行

每一轮主要经历：

```text
① 检查是否取消
        ↓
② 裁剪上下文
        ↓
③ 请求模型
        ↓
④ 标准化模型输出
        ↓
⑤ 判断是否存在tool_calls
        ↓
⑥ 解析工具参数
        ↓
⑦ 执行工具
        ↓
⑧ 将结果加入messages
        ↓
⑨ 进入下一轮
```

---

## 4.7 循环终止条件

Agent不会无限执行。当前存在多种终止条件。

### 条件1：模型不再调用工具

这是最正常的结束方式。

当：

```python
tool_calls == []
```

系统认为模型已经完成任务，直接返回模型最终文本。

### 条件2：用户主动取消

用户通过Web界面点击“停止任务”后：

```python
cancel_event.is_set() == True
```

Agent立即结束。

### 条件3：工具操作被取消

如果某个工具返回：

```json
{
  "cancelled": true
}
```

Agent终止当前任务。

### 条件4：工具调用数量达到上限

如果设置：

```env
CODING_AGENT_MAX_TOOL_CALLS
```

当累计工具调用即将超过限制时，任务停止。

默认配置可以保持为空，表示不由该参数人为限制。

### 条件5：Plan模式单轮结束

Plan模式不进入工具循环，模型输出规划后立即返回。

### 关于`max_steps`

配置中保留：

```env
CODING_AGENT_MAX_STEPS
```

用于兼容和扩展，但当前核心循环主要依赖**任务完成、用户取消和工具调用限制**来结束，而不是强制固定轮数。

---

## 4.8 源码输出自动纠正

Coding Agent常见的一个问题是：

> 模型虽然被要求修改文件，却直接把完整代码粘贴在聊天框中。

ApexCode在Full模式下使用`looks_like_source()`检测这种情况。

例如模型返回大量：

```text
<html>
<script>
function ...
```

但没有调用任何工具时，Agent不会立即结束，而是自动追加一条纠正指令：

```text
不要直接在回复中粘贴源码。
请改用write_file或apply_patch将完整代码写入工作区，
并在写入后运行必要的验证命令。
```

随后重新调用模型。

这使Agent更加偏向真正完成：

```text
Generate → Write → Run → Verify
```

而不是仅仅：

```text
Generate → Chat Output
```

---

## 4.9 错误处理

ApexCode将错误分成模型层、工具层和任务层处理。

### 模型请求错误

模型请求通过HTTPX发送。

支持：

```env
CODING_AGENT_MODEL_TIMEOUT=60
CODING_AGENT_MODEL_RETRIES=2
```

网络失败时采用简单退避：

```text
1s → 2s → ...
```

并重新请求模型。

如果最终仍失败，则转换为统一的`ModelError`返回给Agent。

### 非法模型响应

以下情况会被显式检查：

```text
message不是对象
role格式异常
tool_calls不是数组
工具调用缺少name
arguments格式错误
模型返回非JSON响应
缺少choices.message
```

不会直接让异常结构进入本地工具执行流程。

### 工具参数错误

工具调用参数首先通过：

```python
json.loads(...)
```

随后通过Pydantic Schema验证。

如果失败，会生成结构化工具结果：

```json
{
  "ok": false,
  "error": "..."
}
```

该错误也会被回填给模型，使模型有机会自行修正参数后重新调用。

### 文件错误

文件不存在、文件过大、路径越界、编码错误和补丁上下文不匹配等问题，都会被转换为可读错误，而不会使整个服务直接崩溃。

### 命令错误

命令执行结果同时保留：

```text
returncode
stdout
stderr
timeout
```

模型能够读取这些真实信息并继续修复代码。

---

## License

当前仓库如未单独提供`LICENSE`文件，则项目的使用、复制和分发权限以仓库所有者后续声明为准。
