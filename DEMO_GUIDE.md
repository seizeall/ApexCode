# Apex Flowboard 构建演示

## 演示目标

展示 Agent 如何先规划、再调用本地工具构建完整动态前端，最后通过内置预览器完成验收。整个过程在当前工作区执行，计划文件、页面代码和验证结果均可检查。

## 推荐演示

## 演示步骤

1. 启动 ApexCode，确认工作区为项目根目录。
2. 新建会话，选择“计划”模式，输入以下提示词：

   `在 examples/demo_project/apex_flowboard 中规划一个完整的动态项目执行看板。先创建详细的 PLAN.md，说明用户场景、信息架构、数据结构、核心交互、响应式策略、实施阶段和验收标准；计划模式只写计划，不实现网页。`

3. 打开生成的 `examples/demo_project/apex_flowboard/PLAN.md`，确认计划包含明确的完成标准。
4. 切换“完全”模式，输入以下提示词：

   `严格按照 examples/demo_project/apex_flowboard/PLAN.md 一步一步完成网站构建。实现任务新建、编辑、删除、状态推进、组合筛选、实时统计、活动记录和 localStorage 持久化；完成桌面与移动端验证，修复发现的问题并总结结果。`

5. 展开“执行过程”，查看读取文件、写入补丁、运行检查和阶段进度事件。
6. 点击顶部“预览网站”，候选入口默认选择 `examples/demo_project/apex_flowboard/index.html`。
7. 现场新建任务、切换筛选、推进状态并点击刷新，证明统计联动和状态持久化。
8. 缩窄窗口检查单列移动布局，再回到 Agent 查看测试与验收总结。

## 讲解重点

- Plan 模式先产生可审计的 `PLAN.md`，Full 模式按计划执行本地工具。
- 任务数据和活动记录保存在浏览器 `localStorage`，无需后端即可动态运行。
- Agent 循环在 `app/agent/service.py`，工具定义与执行在 `app/tools/registry.py`。
- 路径校验和危险命令拦截在 `app/safety.py`，模型输出在 `app/model/client.py` 统一解析。
- SSE 持续输出进度与工具事件，最终成果可直接在隔离的内置预览器中运行。
