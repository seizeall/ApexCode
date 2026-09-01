(() => {
  "use strict";

  const STORAGE_KEY = "apex-flowboard-state-v1";
  const STATUS_LABELS = { planned: "待规划", active: "执行中", done: "已完成" };
  const PRIORITY_LABELS = { high: "高优先级", medium: "中优先级", low: "低优先级" };
  const $ = (id) => document.getElementById(id);
  let toastTimer;

  function localDate(offsetDays = 0) {
    const date = new Date();
    date.setHours(12, 0, 0, 0);
    date.setDate(date.getDate() + offsetDays);
    return date.toISOString().slice(0, 10);
  }

  function nowIso(offsetMinutes = 0) {
    return new Date(Date.now() + offsetMinutes * 60_000).toISOString();
  }

  function seedState() {
    return {
      tasks: [
        { id: "task-brief", title: "整理产品需求与验收边界", description: "确认核心场景、数据范围与最终演示路径。", owner: "产品组", priority: "high", status: "done", dueDate: localDate(-2), createdAt: nowIso(-240), updatedAt: nowIso(-180) },
        { id: "task-plan", title: "输出结构化执行计划", description: "拆分页面结构、交互状态、验证标准与交付顺序。", owner: "Apex Agent", priority: "high", status: "done", dueDate: localDate(-1), createdAt: nowIso(-210), updatedAt: nowIso(-150) },
        { id: "task-board", title: "实现动态任务看板", description: "完成三阶段看板、筛选、统计和本地数据持久化。", owner: "前端组", priority: "high", status: "active", dueDate: localDate(1), createdAt: nowIso(-160), updatedAt: nowIso(-42) },
        { id: "task-mobile", title: "验证移动端响应式布局", description: "检查 390px 视口下的文字、控件和任务列布局。", owner: "测试组", priority: "medium", status: "active", dueDate: localDate(2), createdAt: nowIso(-120), updatedAt: nowIso(-35) },
        { id: "task-a11y", title: "补齐键盘与焦点状态", description: "确保表单、弹窗和操作按钮可通过键盘访问。", owner: "体验组", priority: "medium", status: "planned", dueDate: localDate(4), createdAt: nowIso(-100), updatedAt: nowIso(-100) },
        { id: "task-preview", title: "在内置预览器完成验收", description: "启动网站并验证核心交互、持久化与控制台状态。", owner: "测试组", priority: "high", status: "planned", dueDate: localDate(5), createdAt: nowIso(-80), updatedAt: nowIso(-80) },
        { id: "task-docs", title: "更新最终演示说明", description: "记录 Plan 与 Full 模式提示词及点击预览步骤。", owner: "文档组", priority: "low", status: "planned", dueDate: localDate(7), createdAt: nowIso(-60), updatedAt: nowIso(-60) }
      ],
      activities: [
        { id: "activity-3", text: "前端组将“动态任务看板”推进到执行中", at: nowIso(-42) },
        { id: "activity-2", text: "Apex Agent 完成结构化执行计划", at: nowIso(-150) },
        { id: "activity-1", text: "创建 Agent 产品演示站项目", at: nowIso(-240) }
      ]
    };
  }

  function validTask(task) {
    return task && typeof task.id === "string" && typeof task.title === "string" &&
      ["planned", "active", "done"].includes(task.status) &&
      ["high", "medium", "low"].includes(task.priority);
  }

  function loadState() {
    try {
      const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY));
      if (parsed && Array.isArray(parsed.tasks) && parsed.tasks.every(validTask) && Array.isArray(parsed.activities)) {
        return parsed;
      }
    } catch (error) {
      console.warn("无法读取本地演示数据，已恢复默认值。", error);
    }
    return seedState();
  }

  let state = loadState();
  let filters = { query: "", priority: "all", status: "all" };

  function saveState() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (error) {
      showToast("浏览器存储不可用，本次修改仅在当前页面有效");
      console.warn("无法保存本地演示数据。", error);
    }
  }

  function makeId(prefix) {
    if (window.crypto && typeof window.crypto.randomUUID === "function") return `${prefix}-${window.crypto.randomUUID()}`;
    return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function addActivity(text) {
    state.activities.unshift({ id: makeId("activity"), text, at: new Date().toISOString() });
    state.activities = state.activities.slice(0, 12);
  }

  function showToast(message) {
    const toast = $("toast");
    toast.textContent = message;
    toast.classList.add("is-visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("is-visible"), 2400);
  }

  function escapeText(value) {
    const span = document.createElement("span");
    span.textContent = value;
    return span.innerHTML;
  }

  function formatDate(dateString) {
    const date = new Date(`${dateString}T12:00:00`);
    return Number.isNaN(date.getTime()) ? "未设置" : new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric" }).format(date);
  }

  function formatActivityTime(iso) {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "刚刚";
    const minutes = Math.max(0, Math.floor((Date.now() - date.getTime()) / 60_000));
    if (minutes < 1) return "刚刚";
    if (minutes < 60) return `${minutes} 分钟前`;
    if (minutes < 1440) return `${Math.floor(minutes / 60)} 小时前`;
    return new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" }).format(date);
  }

  function isDueSoon(task) {
    if (task.status === "done") return false;
    const today = new Date(`${localDate()}T00:00:00`);
    const due = new Date(`${task.dueDate}T23:59:59`);
    const days = (due - today) / 86_400_000;
    return days >= 0 && days <= 3;
  }

  function matchesFilters(task) {
    const haystack = `${task.title} ${task.description || ""} ${task.owner || ""}`.toLowerCase();
    return (!filters.query || haystack.includes(filters.query)) &&
      (filters.priority === "all" || task.priority === filters.priority) &&
      (filters.status === "all" || task.status === filters.status);
  }

  function taskCard(task) {
    const article = document.createElement("article");
    article.className = `task-card priority-${task.priority}${task.status === "done" ? " is-done" : ""}`;
    article.dataset.id = task.id;
    const initial = (task.owner || "未").trim().slice(0, 1).toUpperCase();
    const nextLabel = task.status === "planned" ? "开始执行" : task.status === "active" ? "标记完成" : "重新打开";
    article.innerHTML = `
      <div class="task-meta"><span class="priority-pill ${task.priority}">${PRIORITY_LABELS[task.priority]}</span><time datetime="${escapeText(task.dueDate)}">截止 ${escapeText(formatDate(task.dueDate))}</time></div>
      <h3>${escapeText(task.title)}</h3>
      <p>${escapeText(task.description || "暂无补充说明。")}</p>
      <div class="task-footer"><span class="task-owner"><i aria-hidden="true">${escapeText(initial)}</i>${escapeText(task.owner || "未分配")}</span><span>${STATUS_LABELS[task.status]}</span></div>
      <div class="task-actions">
        <button class="task-action edit" type="button" data-action="edit">编辑</button>
        <button class="task-action delete" type="button" data-action="delete">删除</button>
        <button class="task-action advance" type="button" data-action="advance">${nextLabel}</button>
      </div>`;
    return article;
  }

  function renderBoard() {
    const visible = state.tasks.filter(matchesFilters);
    ["planned", "active", "done"].forEach((status) => {
      const list = $(`list-${status}`);
      const tasks = visible.filter((task) => task.status === status);
      list.replaceChildren(...tasks.map(taskCard));
      $(`count-${status}`).textContent = String(tasks.length);
      if (!tasks.length) {
        const empty = document.createElement("div");
        empty.className = "empty-state";
        empty.textContent = visible.length ? "当前筛选下，此阶段没有任务。" : "没有匹配的任务，请调整搜索或筛选条件。";
        list.append(empty);
      }
    });
  }

  function renderMetrics() {
    const total = state.tasks.length;
    const active = state.tasks.filter((task) => task.status === "active").length;
    const done = state.tasks.filter((task) => task.status === "done").length;
    const due = state.tasks.filter(isDueSoon).length;
    const percentage = total ? Math.round(done / total * 100) : 0;
    $("metric-total").textContent = String(total);
    $("metric-active").textContent = String(active);
    $("metric-done").textContent = String(done);
    $("metric-due").textContent = String(due);
    $("completion-value").textContent = `${percentage}%`;
    $("completion-bar").style.width = `${percentage}%`;
    $("completion-bar").parentElement.setAttribute("aria-valuenow", String(percentage));
    $("completion-bar").parentElement.setAttribute("role", "progressbar");
    $("completion-bar").parentElement.setAttribute("aria-valuemin", "0");
    $("completion-bar").parentElement.setAttribute("aria-valuemax", "100");
  }

  function renderActivities() {
    const list = $("activity-list");
    const recent = state.activities.slice(0, 5);
    list.replaceChildren(...recent.map((activity) => {
      const item = document.createElement("li");
      item.innerHTML = `<i aria-hidden="true"></i><span>${escapeText(activity.text)}</span><time datetime="${escapeText(activity.at)}">${escapeText(formatActivityTime(activity.at))}</time>`;
      return item;
    }));
    $("activity-count").textContent = `${state.activities.length} 条记录`;
  }

  function render() {
    renderBoard();
    renderMetrics();
    renderActivities();
  }

  function clearErrors() {
    $("title-error").textContent = "";
    $("due-error").textContent = "";
    $("task-title").removeAttribute("aria-invalid");
    $("task-due").removeAttribute("aria-invalid");
  }

  function openTaskDialog(task = null) {
    clearErrors();
    $("task-form").reset();
    $("task-id").value = task?.id || "";
    $("dialog-title").textContent = task ? "编辑任务" : "新建任务";
    $("task-title").value = task?.title || "";
    $("task-description").value = task?.description || "";
    $("task-owner").value = task?.owner || "";
    $("task-due").value = task?.dueDate || localDate(3);
    $("task-priority").value = task?.priority || "medium";
    $("task-status").value = task?.status || "planned";
    $("task-dialog").showModal();
    requestAnimationFrame(() => $("task-title").focus());
  }

  function closeTaskDialog() {
    $("task-dialog").close();
  }

  function validateForm() {
    clearErrors();
    let valid = true;
    if (!$("task-title").value.trim()) {
      $("title-error").textContent = "请输入任务标题。";
      $("task-title").setAttribute("aria-invalid", "true");
      valid = false;
    }
    if (!$("task-due").value) {
      $("due-error").textContent = "请选择截止日期。";
      $("task-due").setAttribute("aria-invalid", "true");
      valid = false;
    }
    return valid;
  }

  function saveTask(event) {
    event.preventDefault();
    if (!validateForm()) return;
    const id = $("task-id").value;
    const existing = state.tasks.find((task) => task.id === id);
    const values = {
      title: $("task-title").value.trim(),
      description: $("task-description").value.trim(),
      owner: $("task-owner").value.trim(),
      dueDate: $("task-due").value,
      priority: $("task-priority").value,
      status: $("task-status").value,
      updatedAt: new Date().toISOString()
    };
    if (existing) {
      Object.assign(existing, values);
      addActivity(`更新任务“${existing.title}”`);
      showToast("任务已更新");
    } else {
      state.tasks.unshift({ id: makeId("task"), createdAt: new Date().toISOString(), ...values });
      addActivity(`创建任务“${values.title}”`);
      showToast("任务已创建");
    }
    saveState();
    render();
    closeTaskDialog();
  }

  function advanceTask(task) {
    const previous = task.status;
    task.status = previous === "planned" ? "active" : previous === "active" ? "done" : "planned";
    task.updatedAt = new Date().toISOString();
    addActivity(`将“${task.title}”从${STATUS_LABELS[previous]}调整为${STATUS_LABELS[task.status]}`);
    saveState();
    render();
    showToast(`任务已进入${STATUS_LABELS[task.status]}`);
  }

  function deleteTask(task) {
    if (!window.confirm(`确认删除任务“${task.title}”？此操作无法撤销。`)) return;
    state.tasks = state.tasks.filter((item) => item.id !== task.id);
    addActivity(`删除任务“${task.title}”`);
    saveState();
    render();
    showToast("任务已删除");
  }

  function handleBoardAction(event) {
    const button = event.target.closest("button[data-action]");
    const card = event.target.closest(".task-card");
    if (!button || !card) return;
    const task = state.tasks.find((item) => item.id === card.dataset.id);
    if (!task) return;
    if (button.dataset.action === "edit") openTaskDialog(task);
    if (button.dataset.action === "advance") advanceTask(task);
    if (button.dataset.action === "delete") deleteTask(task);
  }

  function resetDemo() {
    if (!window.confirm("确认恢复预置任务？当前浏览器中的演示修改将被替换。")) return;
    state = seedState();
    filters = { query: "", priority: "all", status: "all" };
    $("search-input").value = "";
    $("priority-filter").value = "all";
    $("status-filter").value = "all";
    saveState();
    render();
    showToast("演示数据已恢复");
  }

  function bindEvents() {
    $("new-task-button").addEventListener("click", () => openTaskDialog());
    $("close-dialog").addEventListener("click", closeTaskDialog);
    $("cancel-dialog").addEventListener("click", closeTaskDialog);
    $("task-form").addEventListener("submit", saveTask);
    $("reset-button").addEventListener("click", resetDemo);
    $("search-input").addEventListener("input", (event) => { filters.query = event.target.value.trim().toLowerCase(); renderBoard(); });
    $("priority-filter").addEventListener("change", (event) => { filters.priority = event.target.value; renderBoard(); });
    $("status-filter").addEventListener("change", (event) => { filters.status = event.target.value; renderBoard(); });
    $("task-dialog").addEventListener("click", (event) => {
      if (event.target === $("task-dialog")) closeTaskDialog();
    });
    $("task-title").addEventListener("input", clearErrors);
    $("task-due").addEventListener("input", clearErrors);
    document.querySelector(".board").addEventListener("click", handleBoardAction);
  }

  $("current-date").dateTime = localDate();
  $("current-date").textContent = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long", day: "numeric", weekday: "short" }).format(new Date());
  bindEvents();
  render();
})();
