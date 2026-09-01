# 构建演示脚本（2 分钟内）

## 演示目标

展示 Agent 如何读取真实项目、规划修改、调用本地工具生成动态前端，并通过测试验证结果。整个过程在当前工作区执行，模型只负责决策，文件和命令由本地工具完成。

## 推荐演示

1. 双击 `ApexCode.exe`，确认顶部显示“已连接”或先打开配置说明。
2. 新建会话，选择“计划”模式，输入：

   `检查 examples/demo_project，规划一个动态任务清单网页，说明要新增哪些 HTML、CSS、JS 文件以及验证方式。`

3. 切换“完全”模式，输入：

   `在 examples/demo_project/frontend_demo 中创建一个无需后端即可运行的动态任务清单网页：支持新增、完成切换、删除、筛选和 localStorage 持久化；写完后运行可行的检查命令并总结。`

4. 展开“执行过程”，展示 `list_files`、`read_file`、`write_file`/`apply_patch`、`run_command` 事件；如使用“询问”模式，展示写入前的确认弹窗。
5. 打开生成的 `examples/demo_project/frontend_demo/index.html`，现场新增任务、筛选和刷新页面，证明状态持久化。
6. 回到 Agent 输入：`运行项目测试并报告结果`，展示最终测试输出。

## 讲解重点

Agent 循环由 `app/agent/service.py` 自行实现；工具定义和执行在 `app/tools/registry.py`；路径校验和危险命令拦截在 `app/safety.py`；模型返回会在 `app/model/client.py` 统一解析；网页通过 SSE 实时显示可审计事件。没有使用 LangChain、OpenAI Agents SDK、Code Interpreter 或 Files API。
