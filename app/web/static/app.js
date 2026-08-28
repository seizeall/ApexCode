let sessionId = null;
let currentRun = null;
let selectedMode = 'ask';
let detailEvents = [];
const modeHelp = {full: '直接完成任务，安全边界仍然有效', ask: '先确认需求，再决定下一步', plan: '只生成执行计划，不修改工作区'};
const $ = (id) => document.getElementById(id);

async function request(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error((await response.text()) || `请求失败 (${response.status})`);
  return response.json();
}

function addEvent(label, text, type = '') {
  const timeline = $('timeline');
  const welcome = timeline.querySelector('.welcome');
  if (welcome) welcome.remove();
  const el = document.createElement('div');
  el.className = `event ${type}`;
  el.innerHTML = `<span class="event-label">${label}</span><div></div>`;
  el.lastElementChild.textContent = text;
  timeline.appendChild(el);
  timeline.scrollTop = timeline.scrollHeight;
}

function setStatus(text, cls = 'idle') { $('run-status').textContent = text; $('run-status').className = `status-pill ${cls}`; }

function detailLabel(event) {
  if (event.type === 'step') return {label: '工作阶段', text: event.message, tone: 'step'};
  if (event.type === 'tool_start') return {label: `调用工具 · ${event.tool}`, text: JSON.stringify(event.arguments, null, 2), tone: 'tool'};
  if (event.type === 'tool_result') return {label: `工具返回 · ${event.tool}`, text: JSON.stringify(event.result, null, 2), tone: event.result?.ok === false ? 'error' : 'result'};
  if (event.type === 'approval_required') return {label: '等待确认', text: event.action === 'write_file' ? '等待允许修改文件' : '等待允许执行命令', tone: 'approval'};
  if (event.type === 'approval_auto') return {label: '自动确认', text: event.action === 'write_file' ? '完全模式已允许文件修改' : '完全模式已允许命令执行', tone: 'approval'};
  return null;
}

function renderDetails() {
  const list = $('details-list');
  if (!detailEvents.length) { list.innerHTML = '<div class="muted">完成一次任务后，这里会保留执行记录。</div>'; return; }
  list.innerHTML = '';
  detailEvents.forEach(event => {
    const item = detailLabel(event); if (!item) return;
    const row = document.createElement('div'); row.className = `detail-item ${item.tone}`;
    row.innerHTML = `<span class="detail-marker"></span><div><div class="detail-label"></div><pre class="detail-text"></pre></div>`;
    row.querySelector('.detail-label').textContent = item.label;
    row.querySelector('.detail-text').textContent = item.text;
    list.appendChild(row);
  });
}

function toggleDetails(open) {
  $('details-drawer').classList.toggle('open', open);
  $('details-backdrop').classList.toggle('hidden', !open);
  $('details-drawer').setAttribute('aria-hidden', String(!open));
}

async function loadTree() {
  try {
    const data = await request('/api/workspace/tree');
    $('workspace-path').textContent = data.path || '工作区';
    const tree = $('file-tree'); tree.innerHTML = '';
    (data.entries || []).forEach(item => {
      const row = document.createElement('div'); row.className = `tree-item ${item.type === 'directory' ? 'dir' : ''}`;
      row.innerHTML = `<span class="tree-icon">${item.type === 'directory' ? '▾' : '·'}</span><span></span>`;
      row.lastElementChild.textContent = item.name; tree.appendChild(row);
    });
  } catch (error) { $('file-tree').innerHTML = `<div class="muted">${error.message}</div>`; }
}

async function newSession() {
  const data = await request('/api/sessions', { method: 'POST' });
  sessionId = data.session_id;
  detailEvents = [];
  $('sessions').innerHTML = '<button class="session-item active">新会话<small>刚刚创建</small></button>';
  $('timeline').innerHTML = '<div class="welcome"><div class="welcome-icon">⌘</div><h2>从一个真实任务开始</h2><p>描述你希望完成的编程工作，Agent 会先检查工作区，再请求必要的操作确认。</p></div>';
  setStatus('待命');
  $('details-toggle').classList.add('hidden'); toggleDetails(false); renderDetails();
}

async function sendPrompt(prompt) {
  if (!sessionId) await newSession();
  if (!prompt.trim()) return;
  $('prompt').value = ''; setStatus('处理中', 'running');
  const data = await request(`/api/sessions/${sessionId}/messages`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({prompt, mode: selectedMode}) });
  currentRun = data.run_id;
  detailEvents = []; $('details-toggle').classList.remove('hidden'); renderDetails();
  const stream = new EventSource(`/api/runs/${currentRun}/events`);
  stream.onmessage = (message) => {
    const event = JSON.parse(message.data);
    if (event.type === 'status') return;
    if (['step', 'tool_start', 'tool_result', 'approval_required', 'approval_auto'].includes(event.type)) { detailEvents.push(event); renderDetails(); }
    if (event.type === 'error') setStatus('执行失败', 'failed');
    if (event.type === 'approval_required') showApproval(event);
    if (event.type === 'done') { addEvent('最终结果', event.message, event.status === 'completed' ? 'assistant' : 'error'); setStatus(event.status === 'completed' ? '已完成' : '执行失败', event.status === 'completed' ? 'done' : 'failed'); stream.close(); loadTree(); }
  };
  stream.onerror = () => { if (currentRun) setStatus('连接中断', 'failed'); stream.close(); };
}

function showApproval(event) {
  $('approval-title').textContent = event.action === 'write_file' ? '准备修改文件' : '准备执行命令';
  $('approval-detail').textContent = JSON.stringify(event.payload, null, 2);
  $('approval-modal').classList.remove('hidden');
  const finish = async (allowed) => { $('approval-modal').classList.add('hidden'); await request(`/api/runs/${currentRun}/approvals/${event.approval_id}`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({allowed})}); };
  $('approval-allow').onclick = () => finish(true); $('approval-deny').onclick = () => finish(false);
}

async function init() {
  $('new-session').onclick = newSession; $('new-session-side').onclick = newSession; $('refresh-tree').onclick = loadTree;
  $('details-toggle').onclick = () => toggleDetails(true); $('details-close').onclick = () => toggleDetails(false); $('details-backdrop').onclick = () => toggleDetails(false);
  $('composer').onsubmit = (e) => { e.preventDefault(); sendPrompt($('prompt').value); };
  $('prompt').onkeydown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendPrompt(e.target.value); } };
  document.querySelectorAll('[data-prompt]').forEach(button => button.onclick = () => sendPrompt(button.dataset.prompt));
  document.querySelectorAll('[data-mode]').forEach(button => button.onclick = () => {
    selectedMode = button.dataset.mode;
    document.querySelectorAll('[data-mode]').forEach(item => item.classList.toggle('active', item === button));
    $('mode-help').textContent = modeHelp[selectedMode];
  });
  try { const cfg = await request('/api/config'); $('workspace-label').textContent = cfg.workspace; $('connection').innerHTML = `<i></i>${cfg.configured ? '模型已配置' : '等待配置 API Key'}`; if (cfg.configured) $('connection').classList.add('ready'); } catch (error) { $('connection').textContent = '服务未连接'; }
  await loadTree(); await newSession();
}
init();
