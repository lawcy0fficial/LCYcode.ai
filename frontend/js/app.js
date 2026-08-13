const chatLog = document.getElementById('chatLog');
const codeTabs = document.getElementById('codeTabs');
const codeView = document.getElementById('codeView');
const fileCount = document.getElementById('fileCount');
const files = {};
const fileDiffs = {};  // path -> { before, after, lines: [{type, text}] } from the last mutating tool call
let activeFile = null;
// Persist the session id across page reloads so a conversation's context
// (prior task summaries) carries forward instead of resetting every visit.
let sessionId = localStorage.getItem('lcycode_session_id') || null;
let autoContinue = localStorage.getItem('lcycode_auto_continue') !== 'false'; // default on

function addMsg(cls, text) {
  const el = document.createElement('div');
  el.className = 'msg ' + cls;
  el.textContent = text;
  chatLog.appendChild(el);
  chatLog.scrollTop = chatLog.scrollHeight;
}

let streamingEl = null;
function appendToken(stage, delta) {
  if (!streamingEl) {
    streamingEl = document.createElement('div');
    streamingEl.className = 'msg system streaming';
    streamingEl.dataset.stage = stage;
    chatLog.appendChild(streamingEl);
  }
  streamingEl.textContent += delta;
  chatLog.scrollTop = chatLog.scrollHeight;
}
function clearStreaming() {
  if (streamingEl) {
    streamingEl.remove();
    streamingEl = null;
  }
}

function setStage(stage) {
  const states = LCYLogic.railStageStates(stage);
  document.querySelectorAll('.stage').forEach(s => {
    s.classList.remove('active', 'done');
    if (states[s.dataset.stage] === 'active') s.classList.add('active');
    else if (states[s.dataset.stage] === 'done') s.classList.add('done');
  });
}

function tagStageProvider(stage, provider) {
  const el = document.querySelector(`.stage[data-stage="${stage}"] .provider-tag`);
  if (!el) return;
  el.textContent = provider;
  el.className = 'provider-tag' + (provider === 'ollama' ? ' local' : ' cloud');
}

function renderTabs() {
  codeTabs.innerHTML = '';
  Object.keys(files).forEach(path => {
    const tab = document.createElement('div');
    tab.className = 'tab' + (path === activeFile ? ' active' : '');
    tab.textContent = path;
    tab.onclick = () => { activeFile = path; renderTabs(); renderCode(); };
    codeTabs.appendChild(tab);
  });
  fileCount.textContent = Object.keys(files).length + ' files';
}

function renderCode() {
  codeView.innerHTML = '';
  if (!activeFile) return;
  const diff = fileDiffs[activeFile];
  if (diff && diff.lines) {
    diff.lines.forEach(line => {
      const div = document.createElement('div');
      div.className = 'diff-line diff-' + line.type;
      const prefix = line.type === 'add' ? '+ ' : line.type === 'del' ? '- ' : '  ';
      div.textContent = prefix + line.text;
      codeView.appendChild(div);
    });
  } else {
    codeView.textContent = files[activeFile] || '';
  }
}

// Line-based diff via LCYLogic.diffLines (see frontend/js/logic.js) —
// pulled out so it's unit-testable without a browser.

async function loadStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    const box = document.getElementById('providers');
    box.innerHTML = '';

    const badge = document.getElementById('offlineBadge');
    if (data.offline_only) {
      badge.style.display = 'block';
      badge.textContent = data.ollama.reachable ? 'OFFLINE MODE — ollama live' : 'OFFLINE MODE — ollama unreachable';
      badge.className = 'offline-badge ' + (data.ollama.reachable ? 'ok' : 'bad');
    } else {
      badge.style.display = 'none';
    }

    Object.keys(data).forEach(p => {
      if (p === 'offline_only') return;
      const row = document.createElement('div');
      row.className = 'provider-row';
      const { on, label } = LCYLogic.providerRowInfo(p, data[p]);
      row.innerHTML = `<span><span class="dot ${on ? '' : 'off'}"></span>${label}</span>`;
      box.appendChild(row);
    });
  } catch (e) { /* backend not up yet */ }
}
loadStatus();
setInterval(loadStatus, 15000);

async function send() {
  const input = document.getElementById('msgInput');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  addMsg('user', text);
  hideContinue();
  clearProviderTags();
  clearStreaming();
  await streamFrom('/api/chat', { message: text, session_id: sessionId, auto_continue: autoContinue });
}

function clearProviderTags() {
  document.querySelectorAll('.provider-tag').forEach(el => { el.textContent = ''; el.className = 'provider-tag'; });
}

async function continueRun() {
  hideContinue();
  addMsg('system', '→ continuing unfinished build...');
  await streamFrom('/api/chat/continue', { session_id: sessionId, auto_continue: autoContinue });
}

async function streamFrom(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  showStop();

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const { events, remainder } = LCYLogic.parseSSEBuffer(buffer);
      buffer = remainder;
      for (const event of events) handleEvent(event);
    }
  } finally {
    hideStop();
  }
}

function showStop() {
  document.getElementById('stopBtn').style.display = 'inline-block';
}
function hideStop() {
  document.getElementById('stopBtn').style.display = 'none';
}
async function stopRun() {
  if (!sessionId) return;
  hideStop();
  addMsg('system', '⏹ stopping...');
  try {
    await fetch('/api/chat/cancel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    });
  } catch (e) { /* the in-flight stream's own error handling covers this */ }
}

function showContinue() {
  document.getElementById('continueBar').style.display = 'flex';
}
function hideContinue() {
  document.getElementById('continueBar').style.display = 'none';
}

function handleEvent(event) {
  switch (event.type) {
    case 'session':
      sessionId = event.session_id;
      localStorage.setItem('lcycode_session_id', sessionId);
      break;
    case 'stage':
      setStage(event.stage);
      { const label = event.stage === 'RESUME' ? 'RESUME (continuing build)' : event.stage;
        addMsg('system', `→ ${label}${event.iteration ? ' (iteration ' + event.iteration + ')' : ''}`); }
      break;
    case 'model_response':
      tagStageProvider(event.stage, event.provider);
      clearStreaming();
      break;
    case 'token':
      appendToken(event.stage, event.delta);
      break;
    case 'auto_continue':
      addMsg('system', `↻ auto-continuing (${event.iterations_so_far}/${event.ceiling} iterations so far)...`);
      break;
    case 'auto_continue_ceiling_hit':
      addMsg('err', `Safety ceiling reached at ${event.iterations} iterations without completing.`);
      break;
    case 'tool_calling_fallback_hint':
      addMsg('tool', `⚠ ${event.message}`);
      break;
    case 'describe_result':
      addMsg('system', event.data.summary || JSON.stringify(event.data));
      break;
    case 'plan_result':
      addMsg('system', (event.data.steps || []).map(s => `${s.id}. ${s.title}`).join('\n'));
      break;
    case 'tool_call':
      addMsg('tool', `⚙ ${event.tool}  ${event.note || ''}`);
      if (['write_file', 'edit_file', 'append_file'].includes(event.tool) && event.args && event.args.path) {
        if (!(event.args.path in files)) files[event.args.path] = '(pending...)';
        activeFile = event.args.path;
        renderTabs(); renderCode();
      }
      break;
    case 'tool_result': {
      const res = event.result || {};
      if (res.path) {
        if (event.tool === 'delete_file') {
          delete files[res.path];
          delete fileDiffs[res.path];
          if (activeFile === res.path) activeFile = Object.keys(files)[0] || null;
        } else if (res.diff) {
          fileDiffs[res.path] = {
            before: res.diff.before, after: res.diff.after,
            lines: LCYLogic.diffLines(res.diff.before || '', res.diff.after || ''),
          };
          files[res.path] = res.diff.after || '';
        } else if (res.content !== undefined) {
          files[res.path] = res.content;  // e.g. read_file — plain view, no diff
          delete fileDiffs[res.path];
        }
        renderTabs(); renderCode();
      }
      break;
    }
    case 'review_result':
      if (event.data.feedback) addMsg('system', 'review: ' + event.data.feedback);
      break;
    case 'final':
      if (event.data.complete) {
        addMsg('system', `Done in ${event.data.iterations} iteration(s).`);
      } else if (event.data.cancelled) {
        addMsg('system', `⏹ Stopped after ${event.data.iterations} iteration(s). Progress was saved.`);
        showContinue();
      } else {
        addMsg('system', `Paused after ${event.data.iterations} iteration(s) (hit the iteration cap).`);
        showContinue();
      }
      break;
    case 'error':
      addMsg('err', 'error: ' + event.message);
      break;
  }
}

document.getElementById('sendBtn').onclick = send;
document.getElementById('stopBtn').onclick = stopRun;
document.getElementById('msgInput').addEventListener('keydown', e => { if (e.key === 'Enter') send(); });
document.getElementById('continueBtn').onclick = continueRun;
document.getElementById('autoContinueToggle').checked = autoContinue;
document.getElementById('autoContinueToggle').onchange = (e) => {
  autoContinue = e.target.checked;
  localStorage.setItem('lcycode_auto_continue', autoContinue);
};
document.getElementById('newSessionBtn').onclick = () => {
  sessionId = null;
  localStorage.removeItem('lcycode_session_id');
  chatLog.innerHTML = '';
  hideContinue();
  clearProviderTags();
  clearStreaming();
  Object.keys(files).forEach(k => delete files[k]);
  Object.keys(fileDiffs).forEach(k => delete fileDiffs[k]);
  activeFile = null;
  renderTabs(); renderCode();
  addMsg('system', 'Started a new session.');
};
