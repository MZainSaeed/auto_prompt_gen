// State
let pollInterval = null;
let currentJobId = null;
let isGenerating = false;

// Elements
const el = {
  // Nav & Quota
  accountLabel: document.getElementById('accountLabel'),
  accountDot: document.getElementById('accountDot'),
  btnSwitchAccount: document.getElementById('btnSwitchAccount'),
  quotaGemini: document.getElementById('quotaBarGemini'),
  quotaValGemini: document.getElementById('quotaValGemini'),
  quotaClaude: document.getElementById('quotaBarClaude'),
  quotaValClaude: document.getElementById('quotaValClaude'),
  quotaRefresh: document.getElementById('quotaRefresh'),

  // Files & Actions
  inputFile: document.getElementById('inputFile'),
  outputFile: document.getElementById('outputFile'),
  resumeBadge: document.getElementById('resumeBadge'),
  resumeText: document.getElementById('resumeText'),
  btnStart: document.getElementById('btnStart'),
  btnStop: document.getElementById('btnStop'),
  btnRetry: document.getElementById('btnRetry'),
  btnOpen: document.getElementById('btnOpen'),
  elapsedTimer: document.getElementById('elapsedTimer'),
  cardFiles: document.getElementById('cardFiles'),

  // Progress
  progressFill: document.getElementById('progressFill'),
  progressGlow: document.getElementById('progressGlow'),
  progressBatch: document.getElementById('progressBatch'),
  progressPct: document.getElementById('progressPct'),
  progressScenes: document.getElementById('progressScenes'),
  progressMeta: document.getElementById('progressMeta'),
  
  // Log
  logBody: document.getElementById('logBody'),

  // Modals
  modalBackdrop: document.getElementById('modalBackdrop'),
  accountModal: document.getElementById('accountModal'),
  accountList: document.getElementById('accountList'),
  saveBackdrop: document.getElementById('saveBackdrop'),
  saveDialog: document.getElementById('saveDialog'),
  saveLabel: document.getElementById('saveLabel'),
  toast: document.getElementById('toast'),
};

// ==========================================
// Initialization
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
  fetchAccountInfo();
  fetchQuota();
  
  // Auto-load last used paths
  const lastInput = localStorage.getItem('lastInput');
  const lastOutput = localStorage.getItem('lastOutput');
  if (lastInput) el.inputFile.value = lastInput;
  if (lastOutput) el.outputFile.value = lastOutput;
  if (lastInput) checkResume();
  
  // Check for resume when input changes
  el.inputFile.addEventListener('input', debounce(() => {
    localStorage.setItem('lastInput', el.inputFile.value);
    checkResume();
  }, 500));
  
  el.outputFile.addEventListener('input', debounce(() => {
    localStorage.setItem('lastOutput', el.outputFile.value);
  }, 500));
  
  // Periodically update quota (every 5 mins)
  setInterval(fetchQuota, 300000);
});

// ==========================================
// API Handlers
// ==========================================

async function fetchAccountInfo() {
  try {
    const res = await fetch('/api/account');
    const data = await res.json();
    if (data.label) {
      el.accountLabel.textContent = '✓ Connected';
      el.accountLabel.style.color = 'var(--ok)';
      el.accountDot.classList.add('active');
    } else {
      el.accountLabel.textContent = '✓ Connected';
      el.accountLabel.style.color = 'var(--ok)';
      el.accountDot.classList.add('active');
    }
  } catch (err) {
    el.accountLabel.textContent = 'Disconnected';
    el.accountDot.classList.remove('active');
  }
}

async function fetchQuota() {
  el.quotaRefresh.classList.add('spinning');
  try {
    const res = await fetch('/api/quota');
    const data = await res.json();
    
    // Gemini
    const gemPct = data.gemini_pct;
    if (gemPct !== null) {
      el.quotaValGemini.textContent = `${gemPct.toFixed(0)}%`;
      el.quotaGemini.style.width = `${gemPct}%`;
      el.quotaGemini.style.background = getQuotaGradient(gemPct);
    } else {
      el.quotaValGemini.textContent = 'Err';
    }
    
    // Claude
    const claudePct = data.claude_pct;
    if (claudePct !== null) {
      el.quotaValClaude.textContent = `${claudePct.toFixed(0)}%`;
      el.quotaClaude.style.width = `${claudePct}%`;
    } else {
      el.quotaValClaude.textContent = '—';
      el.quotaClaude.style.width = '0%';
    }
  } catch (err) {
    console.error('Quota fetch failed:', err);
  } finally {
    setTimeout(() => el.quotaRefresh.classList.remove('spinning'), 500);
  }
}

function getQuotaGradient(pct) {
  if (pct > 50) return 'linear-gradient(90deg, #4b8f41, #6aad5a)';
  if (pct > 15) return 'linear-gradient(90deg, #b07e1c, #c4932a)';
  return 'linear-gradient(90deg, #a63024, #c44a3a)';
}

el.quotaRefresh.addEventListener('click', fetchQuota);

// ==========================================
// File Browser Handlers
// ==========================================

function triggerFileInput() {
  const fi = document.getElementById('htmlFileInput');
  if (fi) fi.click();
}

async function handleHtmlFileSelect(input) {
  if (!input.files || input.files.length === 0) return;
  const file = input.files[0];
  
  const formData = new FormData();
  formData.append('file', file);
  
  showToast('Loading file...', 'info');
  try {
    const res = await fetch('/api/upload', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    if (data.success && data.path) {
      el.inputFile.value = data.path;
      localStorage.setItem('lastInput', data.path);
      checkResume();
      
      const autoOut = data.path.replace(/\.docx$/i, '_prompts.docx');
      el.outputFile.value = autoOut;
      localStorage.setItem('lastOutput', autoOut);
      showToast('File selected: ' + file.name, 'ok');
    } else {
      showToast(data.error || 'Upload failed', 'error');
    }
  } catch (err) {
    showToast('Failed to load file', 'error');
  } finally {
    input.value = '';
  }
}

async function browseFile(type, btn) {
  if (type === 'input') {
    triggerFileInput();
    return;
  }
  
  const targetBtn = btn || (window.event ? window.event.currentTarget : null);
  const oldText = targetBtn ? targetBtn.textContent : 'Browse';
  if (targetBtn) {
    targetBtn.textContent = 'Opening…';
    targetBtn.disabled = true;
  }
  try {
    const res = await fetch(`/api/browse?type=${type}`);
    const data = await res.json();
    if (data.path) {
      el.outputFile.value = data.path;
      localStorage.setItem('lastOutput', data.path);
    }
  } catch (err) {
    console.error('Browse error:', err);
    showToast('Failed to open file dialog', 'error');
  } finally {
    if (targetBtn) {
      targetBtn.textContent = oldText;
      targetBtn.disabled = false;
    }
  }
}

async function checkResume() {
  const path = el.inputFile.value.trim();
  if (!path) {
    el.resumeBadge.style.display = 'none';
    return;
  }
  
  try {
    const res = await fetch('/api/check_resume', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input_path: path })
    });
    const data = await res.json();
    if (data.resumable && data.job_id) {
      el.resumeText.textContent = `Resume available: ${data.completed}/${data.total} scenes already done`;
      el.resumeBadge.style.display = 'flex';
    } else {
      el.resumeBadge.style.display = 'none';
    }
  } catch (err) {
    el.resumeBadge.style.display = 'none';
  }
}

// ==========================================
// Generation Flow
// ==========================================

let startTime = null;
let timerInterval = null;

async function startGeneration() {
  const input = el.inputFile.value.trim();
  const output = el.outputFile.value.trim();
  
  if (!input || !output) {
    showToast('Please provide both input and output files.', 'warn');
    return;
  }
  
  clearLog();
  el.btnStart.style.display = 'none';
  if (el.btnRetry) el.btnRetry.style.display = 'none';
  el.btnStop.style.display = 'inline-flex';
  el.btnOpen.style.display = 'none';
  el.resumeBadge.style.display = 'none';
  el.cardFiles.classList.add('running');
  
  el.progressMeta.textContent = 'Running…';
  updateProgress(0, 'Starting…', '0 / ? scenes');
  
  startTime = Date.now();
  timerInterval = setInterval(updateTimer, 1000);
  isGenerating = true;
  
  try {
    const res = await fetch('/api/generate/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input_path: input, output_path: output })
    });
    const data = await res.json();
    if (data.error) {
      handleGenerationError(data.error);
      return;
    }
    
    pollInterval = setInterval(pollWorker, 500);
  } catch (err) {
    handleGenerationError(err.message);
  }
}

async function stopGeneration() {
  if (!isGenerating) return;
  
  try {
    await fetch('/api/generate/stop', { method: 'POST' });
    appendLog('warn', 'Stop requested — waiting for current batch to finish…');
    el.progressMeta.textContent = 'Stopping…';
  } catch (err) {
    showToast('Failed to send stop signal.', 'error');
  }
}

async function pollWorker() {
  try {
    const res = await fetch('/api/generate/poll');
    const data = await res.json();
    
    // Process events
    for (const ev of data.events) {
      if (ev.type === 'log') {
        appendLog(ev.payload.level, ev.payload.message, ev.payload.timestamp);
      } else if (ev.type === 'progress') {
        const p = ev.payload;
        const pct = p.total_scenes > 0 ? (p.scenes_done / p.total_scenes) * 100 : 0;
        const batchStr = p.batch_index > 0 ? `Batch ${p.batch_index} / ${p.total_batches}` : 'Starting…';
        const scenesStr = `${p.scenes_done.toLocaleString()} / ${p.total_scenes.toLocaleString()} scenes`;
        updateProgress(pct, batchStr, scenesStr);
      } else if (ev.type === 'status') {
        el.progressMeta.textContent = String(ev.payload).replace('_', ' ').toUpperCase();
        if (ev.payload === 'rate_limited' || ev.payload === 'cancelled') {
          el.btnStop.style.display = 'none';
          if (el.btnRetry) el.btnRetry.style.display = 'inline-flex';
          checkResume();
        }
      } else if (ev.type === 'done') {
        handleGenerationComplete(ev.payload);
        return;
      } else if (ev.type === 'error') {
        handleGenerationError(ev.payload);
        return;
      }
    }
    
    if (!data.is_running && data.events.length === 0) {
      handleGenerationEnded();
    }
  } catch (err) {
    console.error('Poll failed:', err);
  }
}

function handleGenerationComplete(outputPath) {
  clearInterval(pollInterval);
  clearInterval(timerInterval);
  isGenerating = false;
  
  updateProgress(100, 'Complete ✓', 'All scenes generated');
  el.progressMeta.textContent = 'COMPLETED';
  
  el.btnStop.style.display = 'none';
  if (el.btnRetry) el.btnRetry.style.display = 'none';
  el.btnStart.style.display = 'inline-flex';
  el.btnOpen.style.display = 'inline-flex';
  el.cardFiles.classList.remove('running');
  
  // Show toast
  showToast('Generation completed successfully!', 'ok');
}

function handleGenerationError(errMessage) {
  clearInterval(pollInterval);
  clearInterval(timerInterval);
  isGenerating = false;
  
  el.progressMeta.textContent = 'FAILED';
  el.btnStop.style.display = 'none';
  el.btnStart.style.display = 'none';
  if (el.btnRetry) el.btnRetry.style.display = 'inline-flex';
  el.cardFiles.classList.remove('running');
  
  appendLog('error', `Halted: ${errMessage}`);
  showToast('Generation halted. Click "Retry Generation" to resume.', 'error');
  checkResume();
}

function handleGenerationEnded() {
  clearInterval(pollInterval);
  clearInterval(timerInterval);
  isGenerating = false;
  
  el.btnStop.style.display = 'none';
  if (el.btnRetry) el.btnRetry.style.display = 'inline-flex';
  el.btnStart.style.display = 'none';
  el.cardFiles.classList.remove('running');
  checkResume();
}

async function openOutput() {
  const output = el.outputFile.value.trim();
  if (!output) return;
  
  try {
    await fetch('/api/open_file', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: output })
    });
  } catch (err) {
    showToast('Failed to open file.', 'error');
  }
}

// ==========================================
// UI Updates
// ==========================================

function updateProgress(pct, batchStr, scenesStr) {
  el.progressFill.style.width = `${pct}%`;
  el.progressGlow.style.width = `${pct}%`;
  el.progressBatch.textContent = batchStr;
  el.progressPct.textContent = `${pct.toFixed(0)}%`;
  el.progressScenes.textContent = scenesStr;
}

function updateTimer() {
  if (!startTime) return;
  const elapsed = Math.floor((Date.now() - startTime) / 1000);
  const m = String(Math.floor(elapsed / 60)).padStart(2, '0');
  const s = String(elapsed % 60).padStart(2, '0');
  el.elapsedTimer.textContent = `Elapsed: ${m}:${s}`;
}

const levelPrefixes = {
  'ok': '✓', 'info': '·', 'warn': '⚠', 'error': '✗', 'resume': '↩'
};

function appendLog(level, message, ts = null) {
  // Remove empty state message if present
  if (el.logBody.querySelector('.log-empty')) {
    el.logBody.innerHTML = '';
  }
  
  if (!ts) {
    const d = new Date();
    ts = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
  }
  
  const prefix = levelPrefixes[level] || '·';
  
  const line = document.createElement('div');
  line.className = `log-line log-${level}`;
  
  line.innerHTML = `
    <span class="log-ts">${ts}</span>
    <span class="log-prefix">${prefix}</span>
    <span class="log-msg">${escapeHtml(message)}</span>
  `;
  
  el.logBody.appendChild(line);
  el.logBody.scrollTop = el.logBody.scrollHeight;
}

function clearLog() {
  el.logBody.innerHTML = '<div class="log-empty">Ready. Select a file and start generation.</div>';
}

let toastTimeout;
function showToast(msg, type = 'info') {
  el.toast.textContent = msg;
  el.toast.className = `toast show ${type}`;
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => {
    el.toast.classList.remove('show');
  }, 3000);
}

// ==========================================
// Modals
// ==========================================

el.btnSwitchAccount.addEventListener('click', openAccountModal);

function openAccountModal() {
  el.modalBackdrop.classList.add('open');
  el.accountModal.classList.add('open');
  loadAccounts();
}

function closeAccountModal() {
  el.modalBackdrop.classList.remove('open');
  el.accountModal.classList.remove('open');
}

async function loadAccounts() {
  el.accountList.innerHTML = '<div class="account-empty">Loading…</div>';
  try {
    const res = await fetch('/api/accounts');
    const accounts = await res.json();
    
    if (accounts.length === 0) {
      el.accountList.innerHTML = '<div class="account-empty">No saved accounts yet.<br>Save the current session to get started.</div>';
      return;
    }
    
    el.accountList.innerHTML = '';
    accounts.forEach(acc => {
      const activeClass = acc.is_active ? 'is-active' : '';
      const avatar = acc.label ? acc.label.charAt(0).toUpperCase() : '?';
      
      let dateStr = acc.created_at.substring(0, 10);
      try {
        const d = new Date(acc.created_at);
        if (!isNaN(d)) {
          dateStr = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
        }
      } catch (e) {}
      
      let rightSide = '';
      if (acc.is_active) {
        rightSide = `<span class="account-active-badge">✓ Active</span>`;
      } else {
        rightSide = `
          <button class="btn-acct-switch" onclick="switchAccount('${acc.name}')">Switch →</button>
          <button class="btn-acct-del" onclick="deleteAccount('${acc.name}')" title="Delete">🗑</button>
        `;
      }
      
      const row = document.createElement('div');
      row.className = `account-row ${activeClass}`;
      row.innerHTML = `
        <div class="account-avatar">${avatar}</div>
        <div class="account-info">
          <div class="account-name">${escapeHtml(acc.label)}</div>
          <div class="account-date">Saved ${dateStr}</div>
        </div>
        ${rightSide}
      `;
      el.accountList.appendChild(row);
    });
  } catch (err) {
    el.accountList.innerHTML = '<div class="account-empty">Failed to load accounts.</div>';
  }
}

async function switchAccount(name) {
  try {
    const res = await fetch('/api/accounts/switch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Switched to account '${name}'`, 'ok');
      loadAccounts();
      fetchAccountInfo();
      fetchQuota();
    } else {
      showToast(`Failed to switch: ${data.error}`, 'error');
    }
  } catch (err) {
    showToast('Failed to switch account.', 'error');
  }
}

async function deleteAccount(name) {
  if (!confirm(`Delete saved account '${name}'?\nThis only removes the snapshot.`)) return;
  try {
    await fetch(`/api/accounts/${name}`, { method: 'DELETE' });
    loadAccounts();
  } catch (err) {
    showToast('Failed to delete account.', 'error');
  }
}

function saveCurrentSession() {
  const label = el.accountLabel.textContent.trim();
  if (!label || label === 'Loading…' || label === 'Disconnected' || label === 'Session Active') {
    showToast('Cannot detect account email. Please ensure you are logged in.', 'warn');
    return;
  }
  
  confirmSaveSession(label);
}

function closeSaveDialog() {
  // Unused now, but kept to avoid breaking references
  el.saveBackdrop.style.display = 'none';
  el.saveDialog.style.display = 'none';
  if(el.saveLabel) el.saveLabel.value = '';
}

async function confirmSaveSession(autoLabel = null) {
  const label = autoLabel || (el.saveLabel ? el.saveLabel.value.trim() : '');
  if (!label) {
    showToast('Please enter a label.', 'warn');
    return;
  }
  
  try {
    const res = await fetch('/api/accounts/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ label })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Saved as '${label}'`, 'ok');
      loadAccounts();
      if(autoLabel === null) closeSaveDialog();
    } else {
      showToast(`Failed to save: ${data.error}`, 'error');
    }
  } catch (err) {
    showToast('Failed to save session.', 'error');
  }
}

async function launchLogin() {
  try {
    await fetch('/api/accounts/login', { method: 'POST' });
    showToast('Terminal opened for login.', 'info');
  } catch (err) {
    showToast('Failed to launch terminal.', 'error');
  }
}

// ==========================================
// Utils
// ==========================================
function escapeHtml(unsafe) {
  return String(unsafe)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function debounce(func, wait) {
  let timeout;
  return function(...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => func.apply(this, args), wait);
  };
}
