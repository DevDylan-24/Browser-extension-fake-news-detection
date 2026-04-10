/* ============================================================
   FactGuard AI — popup.js
   Handles all view navigation, auth simulation, scan flow,
   speedometer rendering, and dashboard population.
   ============================================================ */

// ─── App State ────────────────────────────────────────────────
const state = {
  isLoggedIn: false,
  user: null,          // { name, email, initials }
  lastScan: null,      // { score, verdict, url, signals, summary, time }
  currentView: 'loggedout',
  previousView: null,
};

// ─── DOM References ───────────────────────────────────────────
const views = {
  loggedout:      document.getElementById('view-loggedout'),
  login:          document.getElementById('view-login'),
  signup:         document.getElementById('view-signup'),
  loggedin:       document.getElementById('view-loggedin'),
  scanning:       document.getElementById('view-scanning'),
  results:        document.getElementById('view-results'),
  dashboard:      document.getElementById('view-dashboard'),
  historydetail:  document.getElementById('view-history-detail'),
};

const headerSub      = document.getElementById('header-sub');
const mainHeader     = document.getElementById('main-header');
const resultsFooter  = document.getElementById('results-footer');
const scanBar        = document.getElementById('scan-bar');

// ─── View Router ──────────────────────────────────────────────
function showView(name) {
  Object.values(views).forEach(v => v.classList.remove('active'));
  if (views[name]) views[name].classList.add('active');
  state.previousView = state.currentView;
  state.currentView = name;

  // These views have their own internal header — hide the shared one
  const selfHeaded = ['dashboard', 'historydetail'];
  mainHeader.style.display = selfHeaded.includes(name) ? 'none' : 'flex';

  // Results footer only visible on results view
  resultsFooter.classList.toggle('hidden', name !== 'results');

  const subs = {
    loggedout:     'Fake News Detector',
    login:         'Log In',
    signup:        'Create Account',
    loggedin:      'Fake News Detector',
    scanning:      'Analysing...',
    results:       'Scan Complete',
    dashboard:     'Dashboard',
    historydetail: 'Scan Details',
  };
  headerSub.textContent = subs[name] || 'FactGuard AI';
}

// ─── Auth Helpers ─────────────────────────────────────────────
function doLoginSuccess(userData, token) {
  const name = userData.name || '';
  const parts = name.trim().split(' ');
  const initials = parts.length >= 2
    ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
    : name.slice(0, 2).toUpperCase();

  state.isLoggedIn = true;
  state.user       = { name, email: userData.email, initials, id: userData.id };
  state.token      = token;

  chrome.storage.local.set({ factguard_token: token, factguard_user: userData });

  document.getElementById('user-name-display').textContent = name;
  document.getElementById('user-avatar').textContent       = initials;
}

function doLogout() {
  state.isLoggedIn = false;
  state.user       = null;
  state.token      = null;
  chrome.storage.local.remove(['factguard_token', 'factguard_user']);
  ['login-email','login-password','signup-name','signup-email','signup-password','signup-confirm']
    .forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  hideError('login-error');
  hideError('signup-error');
  showView('loggedout');
}

function showError(id, msg) {
  const el = document.getElementById(id);
  if (!el) return;
  if (msg) el.textContent = msg;
  el.classList.remove('hidden');
}

function hideError(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add('hidden');
}

// ─── API BASE ─────────────────────────────────────────────────
const API = 'http://localhost:5000';

function authHeaders() {
  const h = { 'Content-Type': 'application/json' };
  if (state.token) h['Authorization'] = `Bearer ${state.token}`;
  return h;
}

async function apiPost(path, body) {
  const res = await fetch(`${API}${path}`, {
    method:  'POST',
    headers: authHeaders(),
    body:    JSON.stringify(body),
  });
  return { status: res.status, data: await res.json() };
}

async function apiGet(path) {
  const res = await fetch(`${API}${path}`, { headers: authHeaders() });
  return { status: res.status, data: await res.json() };
}

// ─── Build result object from full server response ────────────
function buildResult(apiResponse) {
  // Server now returns the already-adjusted score when images were analysed
  const score = apiResponse.score !== undefined
    ? apiResponse.score
    : Math.round((1 - apiResponse.probability) * 100);

  let verdict, color;
  if (score >= 70)      { verdict = 'Credible';    color = 'green'; }
  else if (score >= 40) { verdict = 'Uncertain';   color = 'amber'; }
  else                  { verdict = 'Likely Fake'; color = 'red';   }

  return {
    score,
    verdict,
    color,
    signals:        apiResponse.signals        || [],
    imageSignals:   apiResponse.image_signals  || [],
    summary:        apiResponse.summary        || '',
    contentSummary: apiResponse.content_summary || '',
  };
}

// ─── Scan ─────────────────────────────────────────────────────
function runScan() {
  showView('scanning');
  scanBar.style.width = '0%';

  // Read the image analysis toggle — stored on state so it persists across views
  const analyseImages = state.imageAnalysisEnabled || false;

  let progress = 0;
  const interval = setInterval(() => {
    progress += Math.random() * 12 + 3;
    if (progress > 90) progress = 90;
    scanBar.style.width = progress + '%';
  }, 200);

  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs[0];
    const url = tab?.url || '';

    chrome.tabs.sendMessage(tab.id, { action: 'extractContent' }, async (response) => {
      try {
        if (chrome.runtime.lastError || !response) {
          throw new Error('Could not extract page content.');
        }
        const text   = response.text.substring(0, 10000);
        const images = response.images || [];

        const { status, data } = await apiPost('/predict', {
          text,
          url,
          images,
          analyse_images: analyseImages,
        });

        if (status !== 200) throw new Error(data.error || 'Analysis failed.');

        clearInterval(interval);
        scanBar.style.width = '100%';

        setTimeout(() => finishScan(buildResult(data), url), 300);
      } catch (err) {
        clearInterval(interval);
        scanBar.style.width = '0%';
        showScanError(err.message);
      }
    });
  });
}

// ─── Signal Row Renderer (shared by scan results + history detail) ────────────
function renderSignalRows(signals) {
  if (!signals || signals.length === 0) return '';
  return signals.map(s => `
    <div class="signal-row">
      <div class="signal-dot ${s.type}"></div>
      <div class="signal-text">
        <span class="signal-label">${s.label || ''}</span>
        ${s.detail  ? `<span class="signal-detail">${s.detail}</span>`           : ''}
        ${s.snippet ? `<span class="signal-snippet">"${s.snippet}"</span>` : ''}
      </div>
    </div>`).join('');
}

function finishScan(result, url) {
  state.lastScan = {
    score:          result.score,
    verdict:        result.verdict,
    color:          result.color,
    url,
    signals:        result.signals,
    imageSignals:   result.imageSignals,
    summary:        result.summary,
    contentSummary: result.contentSummary,
    time:           'Just now',
  };

  renderScoreBar(result.score);

  const colorMap = { green: 'var(--green)', amber: 'var(--amber)', red: 'var(--red)' };
  const c = colorMap[result.color];
  document.getElementById('score-number').textContent  = result.score + '%';
  document.getElementById('score-number').style.color  = c;
  document.getElementById('score-verdict').textContent = result.verdict;
  document.getElementById('score-verdict').style.color = c;

  // Text signals
  document.getElementById('signals-list').innerHTML = renderSignalRows(result.signals);

  // Image signals — only shown when image analysis was enabled and returned results
  const imgCard = document.getElementById('image-analysis-card');
  if (result.imageSignals && result.imageSignals.length > 0) {
    document.getElementById('image-signals-list').innerHTML = renderSignalRows(result.imageSignals);
    imgCard.style.display = '';
  } else {
    imgCard.style.display = 'none';
  }

  document.getElementById('content-summary').textContent  = result.contentSummary || '';
  document.getElementById('analysis-summary').textContent = result.summary || '';
  const summaryCard = document.getElementById('summary-card');
  summaryCard.style.display = (result.contentSummary || result.summary) ? '' : 'none';

  showView('results');
}

// ─── Scan Error ───────────────────────────────────────────────
function showScanError(message) {
  document.getElementById('score-number').textContent  = '—';
  document.getElementById('score-number').style.color  = 'var(--text-dim)';
  document.getElementById('score-verdict').textContent = 'Error';
  document.getElementById('score-verdict').style.color = 'var(--red)';
  document.getElementById('score-bar-fill').style.width = '0%';
  document.getElementById('signals-list').innerHTML = `
    <div class="signal-row">
      <div class="signal-dot bad"></div>
      <div class="signal-text"><span class="signal-label">${message || 'An unexpected error occurred.'}</span></div>
    </div>`;
  document.getElementById('analysis-summary').textContent =
    'Could not complete the analysis. Make sure the server is running and try rescanning.';
  showView('results');
}

// ─── Score Bar ────────────────────────────────────────────────
function renderScoreBar(score) {
  const fill = document.getElementById('score-bar-fill');
  fill.style.transition = 'none';
  fill.style.width = '0%';
  fill.style.background = 'linear-gradient(90deg, #ff4d6d 0%, #ffb020 45%, #00f5a0 100%)';
  fill.getBoundingClientRect();
  fill.style.transition = 'width 0.9s cubic-bezier(0.22, 1, 0.36, 1)';
  fill.style.width = score + '%';
}

// ─── History Detail View ──────────────────────────────────────
function showHistoryDetail(scan) {
  // Derive domain for the sub-header
  let domain = scan.url;
  try { domain = new URL(scan.url).hostname; } catch {}
  document.getElementById('hist-detail-domain').textContent = domain;

  // Score bar
  const colorMap = { green: 'var(--green)', amber: 'var(--amber)', red: 'var(--red)' };
  const c = colorMap[scan.color] || 'var(--text-mid)';

  const hdFill = document.getElementById('hd-score-bar-fill');
  hdFill.style.transition = 'none';
  hdFill.style.width = '0%';
  hdFill.style.background = 'linear-gradient(90deg, #ff4d6d 0%, #ffb020 45%, #00f5a0 100%)';
  hdFill.getBoundingClientRect();
  hdFill.style.transition = 'width 0.9s cubic-bezier(0.22, 1, 0.36, 1)';
  hdFill.style.width = scan.score + '%';

  // Score number + verdict
  const numEl     = document.getElementById('hd-score-number');
  const verdictEl = document.getElementById('hd-score-verdict');
  numEl.textContent     = scan.score + '%';
  numEl.style.color     = c;
  verdictEl.textContent = scan.verdict;
  verdictEl.style.color = c;

  // Source URL link
  const urlLink = document.getElementById('hd-url-link');
  urlLink.href          = scan.url;
  urlLink.textContent   = scan.url;
  urlLink.title         = scan.url;

  // Signals — use shared renderer
  const signals = scan.signals || [];
  document.getElementById('hd-signals-list').innerHTML = signals.length
    ? renderSignalRows(signals)
    : '<div class="nav-caption" style="padding:8px 0;">No signal data stored.</div>';

  // Summaries
  const contentSum  = scan.content_summary || '';
  const assessment  = scan.summary         || '';
  document.getElementById('hd-content-summary').textContent  = contentSum;
  document.getElementById('hd-analysis-summary').textContent = assessment;
  document.getElementById('hd-summary-card').style.display   =
    (contentSum || assessment) ? '' : 'none';

  showView('historydetail');

  // Scroll the detail view back to top
  const detailView = document.getElementById('view-history-detail');
  const inner = detailView.querySelector('.view-inner');
  if (inner) inner.scrollTop = 0;
}

// ─── Dashboard Population ─────────────────────────────────────
async function populateDashboard() {
  const histList = document.getElementById('history-list');
  histList.innerHTML = `<div class="nav-caption" style="padding:16px 0;">Loading history…</div>`;

  if (state.lastScan) {
    const s = state.lastScan;
    document.getElementById('dash-last-url').innerHTML =
      `<a href="${s.url}" target="_blank" class="url-link">${s.url}</a>`;
    document.getElementById('dash-timestamp').textContent = s.time;
    const pill = document.getElementById('dash-score-pill');
    pill.textContent  = `⚡ ${s.score}% — ${s.verdict}`;
    pill.className    = `score-pill ${s.color}`;
    document.getElementById('dash-summary').textContent = s.summary || '';
  }

  try {
    const { status, data } = await apiGet('/history');
    if (status !== 200) throw new Error(data.error || 'Failed to load history.');

    const scans = data.scans || [];
    if (scans.length === 0) {
      histList.innerHTML = `<div class="nav-caption" style="padding:16px 0;">No scans yet.</div>`;
      return;
    }

    // Render list items — store full scan data on each element via data attribute
    histList.innerHTML = scans.map((scan, i) => {
      const d      = new Date(scan.scanned_at);
      const when   = isNaN(d) ? '—' : d.toLocaleDateString(undefined,
        { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
      const domain = (() => { try { return new URL(scan.url).hostname; } catch { return scan.url; } })();
      return `
        <div class="history-item" data-scan-index="${i}" style="cursor:pointer;">
          <div class="hist-score ${scan.color}">${scan.score}%</div>
          <div class="hist-info">
            <strong title="${scan.url}">${domain}</strong>
            <span>${when} — ${scan.verdict}</span>
          </div>
          <span class="hist-arrow">›</span>
        </div>`;
    }).join('');

    // Attach click listener to each item — opens history detail view
    histList.querySelectorAll('.history-item').forEach((el, i) => {
      el.addEventListener('click', () => showHistoryDetail(scans[i]));
    });

  } catch (err) {
    histList.innerHTML = `<div class="nav-caption" style="padding:16px 0;color:var(--red);">Could not load history.</div>`;
  }
}

// ─── Event Listeners ──────────────────────────────────────────

document.getElementById('go-login').addEventListener('click', () => showView('login'));
document.getElementById('go-signup').addEventListener('click', () => showView('signup'));

document.getElementById('login-submit').addEventListener('click', async () => {
  hideError('login-error');
  const email = document.getElementById('login-email').value.trim();
  const pass  = document.getElementById('login-password').value;
  if (!email || !pass) { showError('login-error', 'Please fill in all fields.'); return; }
  if (!email.includes('@')) { showError('login-error', 'Please enter a valid email.'); return; }
  if (pass.length < 8) { showError('login-error', 'Password must be at least 8 characters.'); return; }
  const btn = document.getElementById('login-submit');
  btn.textContent = 'Logging in…'; btn.disabled = true;
  try {
    const { status, data } = await apiPost('/login', { email, password: pass });
    if (status !== 200) {
      showError('login-error', data.errors?.general || data.errors?.email || 'Invalid email or password.');
      return;
    }
    doLoginSuccess(data.user, data.token);
    showView('loggedin');
  } catch { showError('login-error', 'Server unreachable. Is the server running?'); }
  finally { btn.textContent = 'Log In'; btn.disabled = false; }
});

document.getElementById('signup-submit').addEventListener('click', async () => {
  hideError('signup-error');
  const name    = document.getElementById('signup-name').value.trim();
  const email   = document.getElementById('signup-email').value.trim();
  const pass    = document.getElementById('signup-password').value;
  const confirm = document.getElementById('signup-confirm').value;
  if (!name || !email || !pass || !confirm) { showError('signup-error', 'Please fill in all fields.'); return; }
  if (!email.includes('@'))  { showError('signup-error', 'Please enter a valid email.'); return; }
  if (pass.length < 8)       { showError('signup-error', 'Password must be at least 8 characters.'); return; }
  if (!/[A-Z]/.test(pass))   { showError('signup-error', 'Password needs at least one uppercase letter.'); return; }
  if (!/[0-9]/.test(pass))   { showError('signup-error', 'Password needs at least one number.'); return; }
  if (pass !== confirm)      { showError('signup-error', 'Passwords do not match.'); return; }
  const btn = document.getElementById('signup-submit');
  btn.textContent = 'Creating account…'; btn.disabled = true;
  try {
    const { status, data } = await apiPost('/register', { name, email, password: pass, confirm_password: confirm });
    if (status !== 201) {
      const errs = data.errors || {};
      showError('signup-error', errs.email || errs.name || errs.password || errs.general || 'Registration failed.');
      return;
    }
    doLoginSuccess(data.user, data.token);
    showView('loggedin');
  } catch { showError('signup-error', 'Server unreachable. Is the server running?'); }
  finally { btn.textContent = 'Create Account'; btn.disabled = false; }
});

document.getElementById('switch-to-signup').addEventListener('click', () => { hideError('login-error');  showView('signup'); });
document.getElementById('switch-to-login').addEventListener('click',  () => { hideError('signup-error'); showView('login');  });
document.getElementById('back-from-login').addEventListener('click',  () => showView('loggedout'));
document.getElementById('back-from-signup').addEventListener('click', () => showView('loggedout'));

document.getElementById('analyse-btn-lo').addEventListener('click', () => runScan());
document.getElementById('analyse-btn-li').addEventListener('click', () => runScan());

document.getElementById('logout-btn').addEventListener('click',       doLogout);
document.getElementById('footer-logout').addEventListener('click',    doLogout);
document.getElementById('logout-from-dash').addEventListener('click', doLogout);

document.getElementById('go-dashboard').addEventListener('click', async () => {
  showView('dashboard'); await populateDashboard();
});
document.getElementById('dash-close').addEventListener('click', () => showView('loggedin'));
document.getElementById('hist-detail-back').addEventListener('click', () => showView('dashboard'));
document.getElementById('footer-go-dashboard').addEventListener('click', async () => {
  if (!state.isLoggedIn) { showView('loggedout'); return; }
  showView('dashboard'); await populateDashboard();
});
document.getElementById('footer-rescan').addEventListener('click', () => runScan());

// ─── Image Analysis Toggle ─────────────────────────────────────
const imgToggle = document.getElementById('img-analysis-toggle');
const imgToggleLabel = document.getElementById('img-toggle-label');
const uploadZone = document.getElementById('upload-zone');

imgToggle.addEventListener('change', () => {
  const enabled = imgToggle.checked;
  state.imageAnalysisEnabled = enabled;
  imgToggleLabel.textContent = enabled ? 'On' : 'Off';
  uploadZone.classList.toggle('disabled', !enabled);
});

// ─── Dashboard Image Upload ────────────────────────────────────
uploadZone.addEventListener('click', () => {
  if (!state.imageAnalysisEnabled) return;
  document.getElementById('media-upload').click();
});

document.getElementById('media-upload').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;

  // Reset result card
  const resultCard = document.getElementById('media-result');
  resultCard.classList.remove('visible');

  // Show loading state in the upload zone
  uploadZone.innerHTML = `
    <div class="upload-icon">⏳</div>
    <p>Analysing ${file.name}…</p>
    <small>${(file.size / 1024 / 1024).toFixed(2)} MB</small>
  `;

  try {
    // Build a local preview URL
    const previewURL = URL.createObjectURL(file);

    // Send the file to /analyse-image as multipart form data
    const formData = new FormData();
    formData.append('file', file);

    const res = await fetch(`${API}/analyse-image`, {
      method:  'POST',
      headers: { 'Authorization': `Bearer ${state.token}` },
      body:    formData,
    });
    const data = await res.json();

    if (data.error) throw new Error(data.error);

    const pct      = Math.round(data.ai_prob * 100);
    const isAi     = data.is_ai;
    const barColor = isAi
      ? '#ff4d6d'
      : pct >= 40 ? '#ffb020' : '#00f5a0';

    // Restore upload zone
    uploadZone.innerHTML = `
      <div class="upload-icon">🖼</div>
      <p>Drop image here or click to browse</p>
      <small>JPG, PNG, WEBP · Max 10MB</small>
      <input type="file" id="media-upload" accept="image/jpeg,image/png,image/webp" style="display:none;">
    `;
    // Re-attach listener since innerHTML replaced the input
    document.getElementById('media-upload').addEventListener('change', () => {});

    // Populate result card
    document.getElementById('media-result-img').src      = previewURL;
    document.getElementById('media-result-title').textContent = isAi
      ? '⚠ Likely AI-Generated'
      : '✓ Likely Authentic';
    document.getElementById('media-result-title').style.color = barColor;
    document.getElementById('media-result-pct').textContent   = `${pct}%`;
    document.getElementById('media-result-verdict').textContent = data.verdict;

    const bar = document.getElementById('media-result-bar');
    bar.style.width      = '0%';
    bar.style.background = barColor;
    // Animate on next frame
    requestAnimationFrame(() => {
      requestAnimationFrame(() => { bar.style.width = pct + '%'; });
    });

    resultCard.classList.add('visible');

  } catch (err) {
    uploadZone.innerHTML = `
      <div class="upload-icon">❌</div>
      <p style="color:var(--red);">${err.message || 'Analysis failed.'}</p>
      <small>Check server connection and try again.</small>
      <input type="file" id="media-upload" accept="image/jpeg,image/png,image/webp" style="display:none;">
    `;
  }

  // Clear the file input so the same file can be re-uploaded
  e.target.value = '';
});

// ─── Init — restore session from storage ──────────────────────
chrome.storage.local.get(['factguard_token', 'factguard_user'], (stored) => {
  if (stored.factguard_token && stored.factguard_user) {
    doLoginSuccess(stored.factguard_user, stored.factguard_token);
    showView('loggedin');
  } else {
    showView('loggedout');
  }
});
