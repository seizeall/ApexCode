let sessionId = null;
let currentRun = null;
let selectedMode = 'ask';
let detailEvents = [];
let nameDialogResolve = null;
let apiConfig = null;
const modeHelp = {full: '直接完成任务，安全边界仍然有效', ask: '先确认需求，再决定下一步', plan: '只生成执行计划，不修改工作区'};
const $ = (id) => document.getElementById(id);

async function request(url, options) {
  const response = await fetch(url, options);
  const text = await response.text();
  let data;
  try { data = JSON.parse(text); } catch (_) { data = {detail: text}; }
  if (!response.ok) throw new Error(data.detail || `请求失败 (${response.status})`);
  return data;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
}

function formatBytes(bytes) {
  if (bytes >= 1024 * 1024) return `${Math.round(bytes / (1024 * 1024))} MB`;
  return `${Math.round(bytes / 1024)} KB`;
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

function setComposerBusy(busy) {
  const button = $('send-button');
  const textarea = $('prompt');
  if (!button || !textarea) return;
  button.disabled = busy;
  button.classList.toggle('is-sending', busy);
  button.querySelector('.send-label').textContent = busy ? '处理中' : '开始任务';
  textarea.disabled = busy;
}

function renderInlineProcess() {
  const panel = $('process-panel');
  const list = $('process-list');
  if (!panel || !list) return;
  panel.classList.toggle('hidden', detailEvents.length === 0);
  list.innerHTML = '';
  detailEvents.forEach(event => {
    const item = detailLabel(event);
    if (!item) return;
    const row = document.createElement('div');
    row.className = `process-item ${item.tone}`;
    row.innerHTML = '<span class="process-dot"></span><div><strong></strong><p></p></div>';
    row.querySelector('strong').textContent = item.label;
    const compact = item.text.length > 240 ? `${item.text.slice(0, 240)}…` : item.text;
    row.querySelector('p').textContent = compact;
    list.appendChild(row);
  });
}

function renderSessions(items) {
  const list = $('sessions');
  list.innerHTML = '';
  (items || []).forEach(item => {
    const row = document.createElement('div');
    row.className = `session-item ${item.session_id === sessionId ? 'active' : ''}`;
    row.innerHTML = '<button class="session-open" type="button"><span class="session-title"></span><small></small></button><div class="session-actions"><button class="session-action rename" type="button" title="重命名会话" aria-label="重命名会话">✎</button><button class="session-action remove" type="button" title="删除会话" aria-label="删除会话">×</button></div>';
    row.querySelector('.session-title').textContent = item.title || '新会话';
    row.querySelector('small').textContent = `${item.message_count || 0} 条消息`;
    row.querySelector('.session-open').onclick = () => restoreSession(item.session_id);
    row.querySelector('.rename').onclick = () => renameSession(item);
    row.querySelector('.remove').onclick = () => deleteSession(item);
    list.appendChild(row);
  });
}

function detailLabel(event) {
  if (event.type === 'step') return {label: '工作阶段', text: event.message, tone: 'step'};
  if (event.type === 'tool_start') return {label: `调用工具 · ${event.tool}`, text: JSON.stringify(event.arguments, null, 2), tone: 'tool'};
  if (event.type === 'tool_result') return {label: `工具返回 · ${event.tool}`, text: JSON.stringify(event.result, null, 2), tone: event.result?.ok === false ? 'error' : 'result'};
  if (event.type === 'approval_required') return {label: '等待确认', text: event.action === 'write_file' ? '等待允许修改文件' : (event.action === 'apply_patch' ? '等待允许应用文件补丁' : '等待允许执行命令'), tone: 'approval'};
  if (event.type === 'approval_auto') return {label: '自动确认', text: event.action === 'write_file' ? '完全模式已允许文件修改' : (event.action === 'apply_patch' ? '完全模式已允许应用文件补丁' : '完全模式已允许命令执行'), tone: 'approval'};
  if (event.type === 'error') return {label: '执行错误', text: event.message || '未知错误', tone: 'error'};
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

function openNameDialog({rename = false, value = ''} = {}) {
  $('session-modal-title').textContent = rename ? '重命名会话' : '新建会话';
  $('session-modal-submit').textContent = rename ? '保存名称' : '创建会话';
  $('session-name').value = value;
  $('session-name-error').textContent = '';
  $('session-name')?.classList.remove('invalid');
  $('session-modal').classList.remove('hidden');
  $('session-name').focus();
  return new Promise(resolve => { nameDialogResolve = resolve; });
}

function closeNameDialog(value = null) {
  $('session-modal').classList.add('hidden');
  if (nameDialogResolve) { const resolve = nameDialogResolve; nameDialogResolve = null; resolve(value); }
}

function applyConfigStatus(config) {
  apiConfig = config;
  $('workspace-label').textContent = config.workspace || $('workspace-label').textContent;
  $('connection').classList.toggle('ready', Boolean(config.configured));
  $('connection').innerHTML = `<i></i>${config.configured ? '模型已配置' : '等待配置 API Key'}`;
  const limits = config.upload_limits;
  if (limits) {
    $('upload-file-button').title = `上传文件（单个不超过 ${formatBytes(limits.max_file_bytes)}）`;
    $('upload-project-button').title = `上传项目（单个文件不超过 ${formatBytes(limits.max_file_bytes)}，总量不超过 ${formatBytes(limits.max_total_bytes)}）`;
  }
}

async function refreshConfig() {
  const config = await request('/api/config');
  applyConfigStatus(config);
  return config;
}

async function openApiDialog() {
  try {
    const config = apiConfig || await refreshConfig();
    $('api-base-url').value = config.base_url || '';
    $('api-model').value = config.model || '';
    $('api-key').value = '';
    $('api-key').type = 'password';
    $('api-config-state').textContent = config.configured ? 'API Key 已配置，留空将保留原密钥。' : '';
    $('api-config-state').classList.toggle('success', Boolean(config.configured));
    $('api-modal').classList.remove('hidden');
    $('api-base-url').focus();
  } catch (error) {
    addEvent('配置读取失败', error.message, 'error');
  }
}

function closeApiDialog() {
  $('api-key').value = '';
  $('api-modal').classList.add('hidden');
}

async function saveApiConfig() {
  const button = $('api-modal-submit');
  const state = $('api-config-state');
  state.classList.remove('success');
  state.textContent = '';
  button.disabled = true;
  button.textContent = '保存中';
  try {
    await request('/api/config', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({base_url: $('api-base-url').value, api_key: $('api-key').value, model: $('api-model').value}),
    });
    await refreshConfig();
    closeApiDialog();
  } catch (error) {
    state.textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = '保存配置';
  }
}

async function newSession(askForName = true) {
  const name = askForName ? await openNameDialog() : '';
  if (name === null) return;
  const data = await request('/api/sessions', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name: name.trim()}) });
  sessionId = data.session_id;
  detailEvents = [];
  $('timeline').innerHTML = '<div class="welcome"><div class="welcome-icon">⌘</div><h2>从一个真实任务开始</h2><p>描述你希望完成的编程工作，Agent 会先检查工作区，再请求必要的操作确认。</p></div>';
  setStatus('待命');
  setRunning(false);
  setComposerBusy(false);
  $('details-toggle').classList.add('hidden'); toggleDetails(false); renderDetails();
  renderInlineProcess();
  await refreshSessions();
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
  await refreshSessions();
  setStatus('待命'); setRunning(false); setComposerBusy(false); $('details-toggle').classList.add('hidden'); toggleDetails(false); renderDetails(); renderInlineProcess();
}

async function sendPrompt(prompt) {
  if (!sessionId) await newSession();
  if (!prompt.trim()) return;
  if (currentRun) {
    const status = await request(`/api/runs/${currentRun}`).catch(() => null);
    if (status && ['queued', 'running', 'waiting'].includes(status.status)) return;
    currentRun = null;
  }
  $('prompt').value = '';
  addEvent('你的提问', prompt, 'user-question');
  setStatus('处理中', 'running');
  setComposerBusy(true);
  let data;
  try {
    data = await request(`/api/sessions/${sessionId}/messages`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({prompt, mode: selectedMode}) });
  } catch (error) {
    addEvent('执行失败', error.message, 'error'); setStatus('执行失败', 'failed'); setRunning(false); setComposerBusy(false); return;
  }
  currentRun = data.run_id;
  setRunning(true);
  detailEvents = []; $('details-toggle').classList.remove('hidden'); renderDetails(); renderInlineProcess();
  const stream = new EventSource(`/api/runs/${currentRun}/events`);
  stream.onmessage = (message) => {
    const event = JSON.parse(message.data);
    if (event.type === 'status') return;
    if (['step', 'tool_start', 'tool_result', 'approval_required', 'approval_auto', 'error'].includes(event.type)) { detailEvents.push(event); renderDetails(); renderInlineProcess(); }
    if (event.type === 'error') setStatus('执行失败', 'failed');
    if (event.type === 'approval_required') { setStatus('等待确认', 'waiting'); showApproval(event); }
    if (event.type === 'done') { addEvent('最终结果', event.message, event.status === 'completed' ? 'assistant' : 'error'); setStatus(event.status === 'completed' ? '已完成' : (event.status === 'cancelled' ? '已取消' : '执行失败'), event.status === 'completed' ? 'done' : 'failed'); setRunning(false); setComposerBusy(false); currentRun = null; stream.close(); refreshSessions(); }
  };
  stream.onerror = () => { if (currentRun) setStatus('连接中断', 'failed'); setComposerBusy(false); stream.close(); };
}

async function refreshSessions() {
  try { renderSessions((await request('/api/sessions')).sessions); } catch (_) { /* 当前会话仍可继续使用 */ }
}

async function uploadFiles(input) {
  const files = Array.from(input.files || []);
  if (!files.length) return;
  const form = new FormData();
  files.forEach(file => { form.append('files', file, file.name); form.append('paths', file.webkitRelativePath || file.name); });
  try {
    const result = await request('/api/workspace/upload', {method: 'POST', body: form});
    const names = (result.files || []).map(item => item.path).join('、');
    addEvent('上传完成', `已上传 ${result.files?.length || 0} 个文件：${names}`, 'assistant');
  } catch (error) {
    addEvent('上传失败', error.message, 'error');
  } finally {
    input.value = '';
  }
}

async function renameSession(item) {
  const current = item.name || item.title || '';
  const name = await openNameDialog({rename: true, value: current});
  if (name === null || !name.trim() || name.trim() === current) return;
  try {
    await request(`/api/sessions/${item.session_id}`, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name: name.trim()})});
    await refreshSessions();
  } catch (error) { addEvent('操作失败', error.message, 'error'); }
}

async function deleteSession(item) {
  if (!window.confirm(`确定删除“${item.title || '新会话'}”吗？删除后无法恢复。`)) return;
  try {
    await request(`/api/sessions/${item.session_id}`, {method: 'DELETE'});
    if (sessionId === item.session_id) {
      sessionId = null;
      currentRun = null;
      const remaining = (await request('/api/sessions')).sessions || [];
      if (remaining.length) await restoreSession(remaining[remaining.length - 1].session_id); else await newSession(false);
    } else {
      await refreshSessions();
    }
  } catch (error) { addEvent('操作失败', error.message, 'error'); }
}

function showApproval(event) {
  $('approval-title').textContent = event.action === 'write_file' ? '准备修改文件' : (event.action === 'apply_patch' ? '准备应用文件补丁' : '准备执行命令');
  $('approval-detail').textContent = JSON.stringify(event.payload, null, 2);
  $('approval-modal').classList.remove('hidden');
  const finish = async (allowed) => { $('approval-modal').classList.add('hidden'); await request(`/api/runs/${currentRun}/approvals/${event.approval_id}`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({allowed})}); };
  $('approval-allow').onclick = () => finish(true); $('approval-deny').onclick = () => finish(false);
}

async function init() {
  $('new-session').onclick = () => newSession(true); $('new-session-side').onclick = () => newSession(true);
  $('api-settings').onclick = () => openApiDialog();
  $('api-modal-cancel').onclick = () => closeApiDialog();
  $('api-form').onsubmit = (event) => { event.preventDefault(); saveApiConfig(); };
  $('api-modal').onclick = (event) => { if (event.target === $('api-modal')) closeApiDialog(); };
  $('toggle-api-key').onclick = () => {
    const keyInput = $('api-key');
    keyInput.type = keyInput.type === 'password' ? 'text' : 'password';
  };
  $('cancel-run').onclick = async () => { if (currentRun) await request(`/api/runs/${currentRun}/cancel`, {method: 'POST'}); };
  // Labels own the file-picker activation so it remains a trusted user gesture
  // in browsers that block synthetic clicks on hidden file inputs.
  $('file-upload').addEventListener('change', (event) => uploadFiles(event.currentTarget));
  $('project-upload').addEventListener('change', (event) => uploadFiles(event.currentTarget));
  $('details-toggle').onclick = () => toggleDetails(true); $('details-close').onclick = () => toggleDetails(false); $('details-backdrop').onclick = () => toggleDetails(false);
  $('session-modal-cancel').onclick = () => closeNameDialog();
  $('session-modal-submit').onclick = () => {
    const name = $('session-name').value.trim();
    if (!name && $('session-modal-title').textContent === '重命名会话') { $('session-name-error').textContent = '名称不能为空'; $('session-name').focus(); return; }
    closeNameDialog(name);
  };
  $('session-name').onkeydown = (event) => { if (event.key === 'Enter') $('session-modal-submit').click(); if (event.key === 'Escape') closeNameDialog(); };
  $('session-modal').onclick = (event) => { if (event.target === $('session-modal')) closeNameDialog(); };
  $('composer').onsubmit = (e) => { e.preventDefault(); sendPrompt($('prompt').value); };
  $('prompt').onkeydown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendPrompt(e.target.value); } };
  document.querySelectorAll('[data-prompt]').forEach(button => button.onclick = () => sendPrompt(button.dataset.prompt));
  document.querySelectorAll('[data-mode]').forEach(button => button.onclick = () => {
    selectedMode = button.dataset.mode;
    document.querySelectorAll('[data-mode]').forEach(item => item.classList.toggle('active', item === button));
    $('mode-help').textContent = modeHelp[selectedMode];
  });
  try {
    await refreshConfig();
  } catch (error) { $('connection').textContent = '服务未连接'; }
  try {
    const saved = await request('/api/sessions');
    const latest = saved.sessions?.[saved.sessions.length - 1];
    if (latest) await restoreSession(latest.session_id); else await newSession(false);
    renderSessions(saved.sessions);
  } catch (error) { await newSession(); }
}
init();
