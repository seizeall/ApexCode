const STORAGE_KEY = "focus-list-demo-v1";
const input = document.querySelector("#task-input");
const list = document.querySelector("#task-list");
const empty = document.querySelector("#empty-state");
let tasks = loadTasks();
let filter = "all";

function loadTasks() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]"); } catch { return []; }
}

function saveTasks() { localStorage.setItem(STORAGE_KEY, JSON.stringify(tasks)); }

function addTask() {
  const title = input.value.trim();
  if (!title) return;
  tasks.unshift({ id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()), title, done: false });
  input.value = "";
  saveTasks();
  render();
  input.focus();
}

function visibleTasks() { return tasks.filter((task) => filter === "all" || (filter === "done" ? task.done : !task.done)); }

function render() {
  const visible = visibleTasks();
  list.innerHTML = visible.map((task) => `<li class="task ${task.done ? "done" : ""}" data-id="${task.id}"><button class="task-check" type="button" aria-label="切换完成状态"></button><span class="task-label">${escapeHtml(task.title)}</span><button class="delete" type="button" aria-label="删除任务">×</button></li>`).join("");
  empty.hidden = visible.length > 0;
  const done = tasks.filter((task) => task.done).length;
  document.querySelector("#count-all").textContent = tasks.length;
  document.querySelector("#count-active").textContent = tasks.length - done;
  document.querySelector("#count-done").textContent = done;
  document.querySelector("#progress-value").textContent = `${tasks.length ? Math.round(done / tasks.length * 100) : 0}%`;
}

function escapeHtml(value) { return value.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[char])); }

document.querySelector("#add-task").addEventListener("click", addTask);
input.addEventListener("keydown", (event) => { if (event.key === "Enter") addTask(); });
document.querySelector(".filters").addEventListener("click", (event) => {
  const button = event.target.closest(".filter");
  if (button) { filter = button.dataset.filter; document.querySelectorAll(".filter").forEach((item) => item.classList.toggle("active", item === button)); render(); }
  if (event.target.closest("#clear-done")) { tasks = tasks.filter((task) => !task.done); saveTasks(); render(); }
});
list.addEventListener("click", (event) => {
  const item = event.target.closest(".task");
  if (!item) return;
  const task = tasks.find((candidate) => candidate.id === item.dataset.id);
  if (event.target.closest(".task-check")) task.done = !task.done;
  if (event.target.closest(".delete")) tasks = tasks.filter((candidate) => candidate.id !== item.dataset.id);
  saveTasks();
  render();
});
render();
