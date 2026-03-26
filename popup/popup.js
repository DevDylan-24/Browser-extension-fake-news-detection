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
  loggedout:  document.getElementById('view-loggedout'),
  login:      document.getElementById('view-login'),
  signup:     document.getElementById('view-signup'),
  loggedin:   document.getElementById('view-loggedin'),
  scanning:   document.getElementById('view-scanning'),
  results:    document.getElementById('view-results'),
  dashboard:  document.getElementById('view-dashboard'),
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

  // Header visibility — dashboard has its own header
  mainHeader.style.display = (name === 'dashboard') ? 'none' : 'flex';

  // Results footer — only visible on results view
  resultsFooter.classList.toggle('hidden', name !== 'results');

  // Update header subtitle
  const subs = {
    loggedout: 'Fake News Detector',
    login:     'Log In',
    signup:    'Create Account',
    loggedin:  'Fake News Detector',
    scanning:  'Analysing...',
    results:   'Scan Complete',
    dashboard: 'Dashboard',
  };
  headerSub.textContent = subs[name] || 'FactGuard AI';
}

// ─── Auth Helpers ─────────────────────────────────────────────
function doLogin(name, email) {
  const parts = name.trim().split(' ');
  const initials = parts.length >= 2
    ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
    : name.slice(0, 2).toUpperCase();

  state.isLoggedIn = true;
  state.user = { name: name.trim(), email, initials };

  document.getElementById('user-name-display').textContent = name.trim();
  document.getElementById('user-avatar').textContent = initials;
}

function doLogout() {
  state.isLoggedIn = false;
  state.user = null;
  // Clear form fields
  ['login-email', 'login-password', 'signup-name', 'signup-email', 'signup-password', 'signup-confirm']
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

// ─── API ──────────────────────────────────────────────────────
async function analyseText(text) {
  const response = await fetch('http://localhost:5000/predict', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  if (!response.ok) throw new Error(`Server error: ${response.status}`);
  return response.json(); // expects { probability: 0.0–1.0 }
}

// ─── Build result object from full server response ────────────
function buildResult(apiResponse) {
  const probability = apiResponse.probability;
  const credibility = Math.round((1 - probability) * 100);

  let verdict, color;
  if (credibility >= 70)      { verdict = 'Credible';     color = 'green'; }
  else if (credibility >= 40) { verdict = 'Uncertain';    color = 'amber'; }
  else                        { verdict = 'Likely Fake';  color = 'red';   }

  return {
    score:          credibility,
    verdict,
    color,
    signals:        apiResponse.signals        || [],
    summary:        apiResponse.summary        || '',
    contentSummary: apiResponse.content_summary || '',
  };
}

// ─── Scan ─────────────────────────────────────────────────────
function runScan() {
  showView('scanning');
  scanBar.style.width = '0%';

  // Animate the loading bar while waiting for the API
  let progress = 0;
  const interval = setInterval(() => {
    progress += Math.random() * 12 + 3;
    if (progress > 90) progress = 90;
    scanBar.style.width = progress + '%';
  }, 200);

  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs[0];
    const url = tab?.url || 'unknown page';

    chrome.tabs.sendMessage(tab.id, { action: 'extractContent' }, async (response) => {
      try {
        if (chrome.runtime.lastError || !response) {
          throw new Error('Could not extract page content.');
        }

        // Trim to 10,000 chars as per original implementation
        const text = response.text.substring(0, 10000);
        const analysis = await analyseText(text);

        clearInterval(interval);
        scanBar.style.width = '100%';

        setTimeout(() => {
          const result = buildResult(analysis);
          finishScan(result, url);
        }, 300);

      } catch (err) {
        clearInterval(interval);
        scanBar.style.width = '0%';
        showScanError(err.message);
      }
    });
  });
}

function finishScan(result, url) {
  // Store last scan
  state.lastScan = {
    score:          result.score,
    verdict:        result.verdict,
    color:          result.color,
    url,
    signals:        result.signals,
    summary:        result.summary,
    contentSummary: result.contentSummary,
    time:           'Just now',
  };

  // Render score bar
  renderScoreBar(result.score);

  // Render score text
  const colorMap = { green: 'var(--green)', amber: 'var(--amber)', red: 'var(--red)' };
  const c = colorMap[result.color];
  const numEl     = document.getElementById('score-number');
  const verdictEl = document.getElementById('score-verdict');
  numEl.textContent     = result.score + '%';
  numEl.style.color     = c;
  verdictEl.textContent = result.verdict;
  verdictEl.style.color = c;

  // Render signals — each has { type, label, detail, snippet }
  const signalsList = document.getElementById('signals-list');
  signalsList.innerHTML = result.signals.map(s => `
    <div class="signal-row">
      <div class="signal-dot ${s.type}"></div>
      <div class="signal-text">
        <span class="signal-label">${s.label || ''}</span>
        ${s.detail  ? `<span class="signal-detail">${s.detail}</span>` : ''}
        ${s.snippet ? `<span class="signal-snippet">"${s.snippet}"</span>` : ''}
      </div>
    </div>`
  ).join('');

  // Render content summary (extractive) + credibility assessment
  const contentSummaryEl = document.getElementById('content-summary');
  const assessmentEl     = document.getElementById('analysis-summary');

  contentSummaryEl.textContent = result.contentSummary || '';
  assessmentEl.textContent     = result.summary        || '';

  // Hide the content summary block if the server returned nothing
  const summaryCard = document.getElementById('summary-card');
  summaryCard.style.display = (result.contentSummary || result.summary) ? '' : 'none';

  showView('results');
}

// ─── Scan Error ───────────────────────────────────────────────
function showScanError(message) {
  // Show the results view with an error state instead of scores
  document.getElementById('score-number').textContent = '—';
  document.getElementById('score-number').style.color = 'var(--text-dim)';
  document.getElementById('score-verdict').textContent = 'Error';
  document.getElementById('score-verdict').style.color = 'var(--red)';

  const fill = document.getElementById('score-bar-fill');
  fill.style.width = '0%';

  document.getElementById('signals-list').innerHTML = `
    <div class="signal-row">
      <div class="signal-dot bad"></div>
      <div class="signal-text">${message || 'An unexpected error occurred.'}</div>
    </div>`;
  document.getElementById('analysis-summary').textContent =
    'Could not complete the analysis. Make sure the server is running and try rescanning.';

  showView('results');
}
function renderScoreBar(score) {
  const fill = document.getElementById('score-bar-fill');
  // Reset width to 0 first so the CSS transition animates from scratch each scan
  fill.style.transition = 'none';
  fill.style.width = '0%';
  // Paint the full red→amber→green gradient; element width does the clipping
  fill.style.background = 'linear-gradient(90deg, #ff4d6d 0%, #ffb020 45%, #00f5a0 100%)';
  // Force reflow so the transition fires on the next frame
  fill.getBoundingClientRect();
  fill.style.transition = 'width 0.9s cubic-bezier(0.22, 1, 0.36, 1)';
  fill.style.width = score + '%';
}

// ─── Dashboard Population ─────────────────────────────────────
function populateDashboard() {
  if (!state.lastScan) return;

  const s = state.lastScan;
  const colorClass = s.color;

  document.getElementById('dash-last-url').textContent = s.url;
  document.getElementById('dash-timestamp').textContent = s.time;

  const pill = document.getElementById('dash-score-pill');
  pill.textContent = `⚡ ${s.score}% — ${s.verdict}`;
  pill.className = `score-pill ${colorClass}`;

  document.getElementById('dash-summary').textContent = s.summary;
}

// ─── Event Listeners ──────────────────────────────────────────

// --- Logged-out → Login / Signup
document.getElementById('go-login').addEventListener('click', () => showView('login'));
document.getElementById('go-signup').addEventListener('click', () => showView('signup'));

// --- Login form
document.getElementById('login-submit').addEventListener('click', () => {
  hideError('login-error');
  const email = document.getElementById('login-email').value.trim();
  const pass  = document.getElementById('login-password').value;

  if (!email || !pass) {
    showError('login-error', 'Please fill in all fields.');
    return;
  }
  if (!email.includes('@')) {
    showError('login-error', 'Please enter a valid email.');
    return;
  }
  if (pass.length < 4) {
    showError('login-error', 'Password too short.');
    return;
  }

  // Simulate login — derive name from email
  const namePart = email.split('@')[0].replace(/[._]/g, ' ');
  const displayName = namePart.split(' ')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');

  doLogin(displayName, email);
  showView('loggedin');
});

// --- Signup form
document.getElementById('signup-submit').addEventListener('click', () => {
  hideError('signup-error');
  const name    = document.getElementById('signup-name').value.trim();
  const email   = document.getElementById('signup-email').value.trim();
  const pass    = document.getElementById('signup-password').value;
  const confirm = document.getElementById('signup-confirm').value;

  if (!name || !email || !pass || !confirm) {
    showError('signup-error', 'Please fill in all fields.');
    return;
  }
  if (!email.includes('@')) {
    showError('signup-error', 'Please enter a valid email.');
    return;
  }
  if (pass.length < 8) {
    showError('signup-error', 'Password must be at least 8 characters.');
    return;
  }
  if (pass !== confirm) {
    showError('signup-error', 'Passwords do not match.');
    return;
  }

  doLogin(name, email);
  showView('loggedin');
});

// --- Cross-links between login and signup
document.getElementById('switch-to-signup').addEventListener('click', () => {
  hideError('login-error');
  showView('signup');
});
document.getElementById('switch-to-login').addEventListener('click', () => {
  hideError('signup-error');
  showView('login');
});

// --- Back buttons
document.getElementById('back-from-login').addEventListener('click', () => showView('loggedout'));
document.getElementById('back-from-signup').addEventListener('click', () => showView('loggedout'));

// --- Analyse buttons (logged out & logged in)
document.getElementById('analyse-btn-lo').addEventListener('click', () => {
  // Allow scan without login — results will just lack save/dashboard features
  runScan();
});

document.getElementById('analyse-btn-li').addEventListener('click', () => {
  runScan();
});

// --- Logout buttons
document.getElementById('logout-btn').addEventListener('click', doLogout);
document.getElementById('footer-logout').addEventListener('click', doLogout);
document.getElementById('logout-from-dash').addEventListener('click', doLogout);

// --- Dashboard button (from logged-in view)
document.getElementById('go-dashboard').addEventListener('click', () => {
  populateDashboard();
  showView('dashboard');
});

// --- Dashboard close
document.getElementById('dash-close').addEventListener('click', () => {
  showView('loggedin');
});

// --- Results footer: go to dashboard
document.getElementById('footer-go-dashboard').addEventListener('click', () => {
  if (!state.isLoggedIn) {
    showView('loggedout');
    return;
  }
  populateDashboard();
  showView('dashboard');
});

// --- Results footer: rescan
document.getElementById('footer-rescan').addEventListener('click', () => {
  runScan();
});

// --- Media upload zone
document.getElementById('upload-zone').addEventListener('click', () => {
  document.getElementById('media-upload').click();
});

document.getElementById('media-upload').addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const zone = document.getElementById('upload-zone');
  zone.innerHTML = `
    <div class="upload-icon">⏳</div>
    <p>Analysing: ${file.name}</p>
    <small>${(file.size / 1024 / 1024).toFixed(2)} MB</small>
  `;
  setTimeout(() => {
    zone.innerHTML = `
      <div class="upload-icon">✅</div>
      <p style="color:var(--green);">No AI generation detected</p>
      <small>${file.name}</small>
    `;
  }, 2500);
});

// --- Media type chips
document.getElementById('chip-image').addEventListener('click', () => {
  document.getElementById('chip-image').classList.toggle('active');
  document.getElementById('chip-video').classList.remove('active');
});
document.getElementById('chip-video').addEventListener('click', () => {
  document.getElementById('chip-video').classList.toggle('active');
  document.getElementById('chip-image').classList.remove('active');
});

// ─── Init ─────────────────────────────────────────────────────
showView('loggedout');
