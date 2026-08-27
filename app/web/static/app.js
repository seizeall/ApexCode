let sessionId = null;
let currentRun = null;
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
  $('sessions').innerHTML = '<button class="session-item active">新会话<small>刚刚创建</small></button>';
  $('timeline').innerHTML = '<div class="welcome"><div class="welcome-icon">⌘</div><h2>从一个真实任务开始</h2><p>描述你希望完成的编程工作，Agent 会先检查工作区，再请求必要的操作确认。</p></div>';
  setStatus('待命');
}

async function sendPrompt(prompt) {
  if (!sessionId) await newSession();
  if (!prompt.trim()) return;
  $('prompt').value = ''; addEvent('USER TASK', prompt, 'user'); setStatus('排队中', 'running');
  const data = await request(`/api/sessions/${sessionId}/messages`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({prompt}) });
  currentRun = data.run_id; $('run-log').innerHTML = '<div class="log-entry">任务已创建</div>';
  const stream = new EventSource(`/api/runs/${currentRun}/events`);
  stream.onmessage = (message) => {
    const event = JSON.parse(message.data);
    if (event.type === 'status') return;
    if (event.type === 'step') { addEvent('AGENT', event.message); $('run-log').innerHTML += `<div class="log-entry">${event.message}</div>`; }
    if (event.type === 'assistant') addEvent('AGENT RESPONSE', event.message, 'assistant');
    if (event.type === 'tool_start') addEvent(`TOOL · ${event.tool}`, JSON.stringify(event.arguments, null, 2), 'tool');
    if (event.type === 'tool_result') $('run-log').innerHTML += `<div class="log-entry">${event.tool} 已返回</div>`;
    if (event.type === 'error') { addEvent('ERROR', event.message, 'error'); setStatus('执行失败', 'failed'); }
    if (event.type === 'approval_required') showApproval(event);
    if (event.type === 'done') { addEvent('DONE', event.message, event.status === 'completed' ? 'assistant' : 'error'); setStatus(event.status === 'completed' ? '已完成' : '执行失败', event.status === 'completed' ? 'done' : 'failed'); stream.close(); loadTree(); }
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
  $('composer').onsubmit = (e) => { e.preventDefault(); sendPrompt($('prompt').value); };
  $('prompt').onkeydown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendPrompt(e.target.value); } };
  document.querySelectorAll('[data-prompt]').forEach(button => button.onclick = () => sendPrompt(button.dataset.prompt));
  try { const cfg = await request('/api/config'); $('workspace-label').textContent = cfg.workspace; $('connection').innerHTML = `<i></i>${cfg.configured ? '模型已配置' : '等待配置 API Key'}`; if (cfg.configured) $('connection').classList.add('ready'); } catch (error) { $('connection').textContent = '服务未连接'; }
  await loadTree(); await newSession();
}
init();
