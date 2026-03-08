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

// ─── Scan Logic ───────────────────────────────────────────────

// Mock data pool for demo purposes
const mockScans = [
  {
    score: 87,
    verdict: 'Credible',
    color: 'green',
    signals: [
      { type: 'ok',   text: 'Author identity verified against known bylines' },
      { type: 'ok',   text: 'Domain established over 10 years ago' },
      { type: 'ok',   text: 'Primary sources cited and verifiable' },
      { type: 'warn', text: 'One external link leads to opinion content' },
      { type: 'ok',   text: 'No sensationalist language patterns found' },
    ],
    summary: 'This article meets most credibility standards. Sources are traceable and the writing style is measured and factual. Minor concern with one linked opinion piece.',
  },
  {
    score: 62,
    verdict: 'Uncertain',
    color: 'amber',
    signals: [
      { type: 'bad',  text: 'Sensationalist headline language detected' },
      { type: 'warn', text: 'Author credibility could not be verified' },
      { type: 'ok',   text: 'Domain registered over 5 years ago' },
      { type: 'warn', text: '2 of 5 cited sources are unreliable' },
      { type: 'ok',   text: 'No known plagiarised content found' },
    ],
    summary: 'This article uses emotionally charged language and references unverified sources. Exercise caution before sharing. Cross-check with established outlets.',
  },
  {
    score: 21,
    verdict: 'Likely False',
    color: 'red',
    signals: [
      { type: 'bad', text: 'Multiple claims contradict verified facts' },
      { type: 'bad', text: 'Domain registered within the last 3 months' },
      { type: 'bad', text: 'Author is unverifiable — likely pseudonym' },
      { type: 'warn', text: 'Extreme emotional language throughout' },
      { type: 'bad', text: 'No credible sources cited anywhere in article' },
    ],
    summary: 'This article exhibits strong indicators of misinformation. Several factual claims have been debunked by independent fact-checkers. Do not share without thorough verification.',
  },
];

document.getElementById("analyse-btn-lo").addEventListener("click", async () => {

    let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    chrome.tabs.sendMessage(tab.id, { action: "extractContent" }, (response) => {

        console.log(response);

        document.getElementById("result").innerText =
            "Text length: " + response.text.length +
            "\nImages found: " + response.images.length;
    });

});

function runScan() {
  showView('scanning');
  scanBar.style.width = '0%';

  // Animate progress bar
  let progress = 0;
  const interval = setInterval(() => {
    progress += Math.random() * 18 + 4;
    if (progress > 95) progress = 95;
    scanBar.style.width = progress + '%';
  }, 200);

  // Pick a random mock result
  const result = mockScans[Math.floor(Math.random() * mockScans.length)];

  setTimeout(() => {
    clearInterval(interval);
    scanBar.style.width = '100%';

    setTimeout(() => {
      // Get current tab URL if in extension context, else use mock
      if (typeof chrome !== 'undefined' && chrome.tabs) {
        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
          const url = tabs[0]?.url || 'unknown page';
          finishScan(result, url);
        });
      } else {
        finishScan(result, 'newswebsite.com/article/demo-story');
      }
    }, 300);
  }, 2200);
}

function finishScan(result, url) {
  // Store last scan
  state.lastScan = {
    score:   result.score,
    verdict: result.verdict,
    color:   result.color,
    url,
    signals: result.signals,
    summary: result.summary,
    time:    'Just now',
  };

  // Render score bar
  renderScoreBar(result.score, result.color);

  // Render score text
  const colorMap = { green: 'var(--green)', amber: 'var(--amber)', red: 'var(--red)' };
  const c = colorMap[result.color];
  const numEl = document.getElementById('score-number');
  const verdictEl = document.getElementById('score-verdict');
  numEl.textContent = result.score + '%';
  numEl.style.color = c;
  verdictEl.textContent = result.verdict;
  verdictEl.style.color = c;

  // Render signals
  const signalsList = document.getElementById('signals-list');
  signalsList.innerHTML = result.signals.map(s =>
    `<div class="signal-row">
       <div class="signal-dot ${s.type}"></div>
       <div class="signal-text">${s.text}</div>
     </div>`
  ).join('');

  document.getElementById('analysis-summary').textContent = result.summary;

  showView('results');
}

// ─── Score Bar Rendering ──────────────────────────────────────
function renderScoreBar(score, colorKey) {
  const colorMap = { green: '#00f5a0', amber: '#ffb020', red: '#ff4d6d' };
  const color = colorMap[colorKey] || '#ffb020';

  // Gradient fill: always red→amber→green across full bar,
  // clipped by the actual score width.
  const fill = document.getElementById('score-bar-fill');
  fill.style.width = score + '%';
  fill.style.background = `linear-gradient(90deg, #ff4d6d 0%, #ffb020 40%, #00f5a0 100%)`;
  // Clip the gradient to only show up to the score position
  // by setting background-size relative to the full track
  fill.style.backgroundSize = `${(100 / score) * 100}% 100%`;
  fill.style.backgroundRepeat = 'no-repeat';
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
