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

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
}

function inlineMarkdown(value) {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/__([^_]+)__/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
}

function markdownToHtml(markdown) {
  const lines = String(markdown).replace(/\r\n?/g, '\n').split('\n');
  const output = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (/^```/.test(line.trim())) {
      const language = line.trim().slice(3).trim();
      const code = [];
      index += 1;
      while (index < lines.length && !/^```/.test(lines[index].trim())) { code.push(lines[index]); index += 1; }
      if (index < lines.length) index += 1;
      output.push(`<pre class="markdown-code"><code class="language-${escapeHtml(language)}">${escapeHtml(code.join('\n'))}</code></pre>`);
      continue;
    }
    if (line.includes('|') && index + 1 < lines.length && /^\s*\|?\s*:?-{3,}/.test(lines[index + 1])) {
      const parseRow = (row) => row.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(cell => cell.trim());
      const headers = parseRow(line); index += 2; const rows = [];
      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) { rows.push(parseRow(lines[index])); index += 1; }
      output.push(`<div class="markdown-table-wrap"><table class="markdown-table"><thead><tr>${headers.map(cell => `<th>${inlineMarkdown(cell)}</th>`).join('')}</tr></thead><tbody>${rows.map(row => `<tr>${headers.map((_, cellIndex) => `<td>${inlineMarkdown(row[cellIndex] || '')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`);
      continue;
    }
    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) { output.push(`<h${heading[1].length}>${inlineMarkdown(heading[2])}</h${heading[1].length}>`); index += 1; continue; }
    if (/^\s*[-*+]\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^\s*[-*+]\s+/.test(lines[index])) { items.push(lines[index].replace(/^\s*[-*+]\s+/, '')); index += 1; }
      output.push(`<ul>${items.map(item => `<li>${inlineMarkdown(item)}</li>`).join('')}</ul>`); continue;
    }
    if (!line.trim()) { index += 1; continue; }
    const paragraph = [line]; index += 1;
    while (index < lines.length && lines[index].trim() && !/^```/.test(lines[index].trim()) && !/^(#{1,3})\s+/.test(lines[index])) { paragraph.push(lines[index]); index += 1; }
    output.push(`<p>${inlineMarkdown(paragraph.join('\n')).replace(/\n/g, '<br>')}</p>`);
  }
  return output.join('');
}

function addEvent(label, text, type = '') {
  const timeline = $('timeline');
  const welcome = timeline.querySelector('.welcome');
  if (welcome) welcome.remove();
  const el = document.createElement('div');
  el.className = `event ${type}`;
  const isUser = type === 'user-question';
  const identity = isUser ? '你' : 'ApexCode';
  const displayLabel = isUser ? '你的提问' : label;
  el.innerHTML = `<div class="message-meta"><span class="message-avatar">${identity[0]}</span><span class="event-label">${displayLabel}</span></div><div class="message-body"></div>`;
  const body = el.querySelector('.message-body');
  if (type === 'assistant' || type === 'error') body.innerHTML = markdownToHtml(text);
  else body.textContent = text;
  timeline.appendChild(el);
  timeline.scrollTop = timeline.scrollHeight;
}

function setStatus(text, cls = 'idle') { $('run-status').textContent = text; $('run-status').className = `status-pill ${cls}`; }

function setRunning(running) { $('cancel-run').classList.toggle('hidden', !running); }

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
  setRunning(false);
  $('details-toggle').classList.add('hidden'); toggleDetails(false); renderDetails();
}

async function restoreSession(id) {
  const data = await request(`/api/sessions/${id}/history`);
  sessionId = id;
  detailEvents = [];
  $('timeline').innerHTML = '';
  const visible = (data.messages || []).filter(message => (message.role === 'user' && message.content) || (message.role === 'assistant' && message.content));
  if (!visible.length) {
    $('timeline').innerHTML = '<div class="welcome"><div class="welcome-icon">⌘</div><h2>从一个真实任务开始</h2><p>描述你希望完成的编程工作，Agent 会先检查工作区，再请求必要的操作确认。</p></div>';
  } else {
    visible.forEach(message => addEvent(message.role === 'user' ? '你的提问' : '最终结果', message.content, message.role === 'user' ? 'user-question' : 'assistant'));
  }
  $('sessions').innerHTML = `<button class="session-item active">恢复的会话<small>${visible.length} 条消息</small></button>`;
  setStatus('待命'); setRunning(false); $('details-toggle').classList.add('hidden'); toggleDetails(false); renderDetails();
}

async function sendPrompt(prompt) {
  if (!sessionId) await newSession();
  if (!prompt.trim()) return;
  $('prompt').value = '';
  addEvent('你的提问', prompt, 'user-question');
  setStatus('处理中', 'running');
  const data = await request(`/api/sessions/${sessionId}/messages`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({prompt, mode: selectedMode}) });
  currentRun = data.run_id;
  setRunning(true);
  detailEvents = []; $('details-toggle').classList.remove('hidden'); renderDetails();
  const stream = new EventSource(`/api/runs/${currentRun}/events`);
  stream.onmessage = (message) => {
    const event = JSON.parse(message.data);
    if (event.type === 'status') return;
    if (['step', 'tool_start', 'tool_result', 'approval_required', 'approval_auto'].includes(event.type)) { detailEvents.push(event); renderDetails(); }
    if (event.type === 'error') setStatus('执行失败', 'failed');
    if (event.type === 'approval_required') showApproval(event);
    if (event.type === 'done') { addEvent('最终结果', event.message, event.status === 'completed' ? 'assistant' : 'error'); setStatus(event.status === 'completed' ? '已完成' : (event.status === 'cancelled' ? '已取消' : '执行失败'), event.status === 'completed' ? 'done' : 'failed'); setRunning(false); stream.close(); loadTree(); }
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
  $('cancel-run').onclick = async () => { if (currentRun) await request(`/api/runs/${currentRun}/cancel`, {method: 'POST'}); };
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
  await loadTree();
  try {
    const saved = await request('/api/sessions');
    const latest = saved.sessions?.[saved.sessions.length - 1];
    if (latest) await restoreSession(latest.session_id); else await newSession();
  } catch (error) { await newSession(); }
}
init();
