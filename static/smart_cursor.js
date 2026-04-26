/**
 * smart_cursor.js — Nightion Smart Cursor Mode
 * AI-powered contextual code assistant that captures screen context,
 * analyzes code problems, and provides streaming solutions.
 *
 * Features:
 *   - Screen capture with countdown overlay
 *   - Streaming AI responses with markdown rendering
 *   - Persistent context sidebar with suggestion cards
 *   - Ambient particle background animation
 *   - Keyboard shortcuts (Ctrl+Shift+C, Ctrl+K, Enter)
 *   - Conversation history within the session
 */

'use strict';

// ── Module State ──────────────────────────────────────────────────────────────
let _scCfg = null;
let _scWs = null;
let _scHistory = [];          // conversation history
let _scContext = null;        // last captured context (screenshot analysis text)
let _scStreaming = false;
let _scStreamContent = '';
let _scStreamEl = null;
let _scParticlesRAF = null;
let _scCaptureActive = false;
let _scCountdownInterval = null;
let _scAbortCtrl = null;

// ── DOM Refs ──────────────────────────────────────────────────────────────────
let _scResponseArea = null;
let _scInput = null;
let _scSendBtn = null;
let _scCaptureBtn = null;
let _scClearBtn = null;
let _scStatusBadge = null;
let _scStatusText = null;
let _scContextDisplay = null;
let _scSuggestionsList = null;
let _scCaptureOverlay = null;
let _scTokenCounter = null;
let _scParticlesCanvas = null;

// ═══════════════════════════════════════════════════════════════════════════════
//  PUBLIC INIT
// ═══════════════════════════════════════════════════════════════════════════════
function initSmartCursor(cfg, wsRef) {
  _scCfg = cfg;
  _scWs = wsRef;

  // Grab DOM refs
  _scResponseArea    = document.getElementById('sc-response-area');
  _scInput           = document.getElementById('sc-input');
  _scSendBtn         = document.getElementById('sc-send-btn');
  _scCaptureBtn      = document.getElementById('sc-capture-btn');
  _scClearBtn        = document.getElementById('sc-clear-btn');
  _scStatusBadge     = document.getElementById('sc-status-badge');
  _scStatusText      = document.getElementById('sc-status-text');
  _scContextDisplay  = document.getElementById('sc-context-display');
  _scSuggestionsList = document.getElementById('sc-suggestions-list');
  _scCaptureOverlay  = document.getElementById('sc-capture-overlay');
  _scTokenCounter    = document.getElementById('sc-token-counter');
  _scParticlesCanvas = document.getElementById('sc-particles-canvas');

  _bindEvents();
  _initParticles();
  _setStatus('ready', 'Ready');
}

function destroySmartCursor() {
  if (_scParticlesRAF) cancelAnimationFrame(_scParticlesRAF);
}

// ═══════════════════════════════════════════════════════════════════════════════
//  WS MESSAGE HANDLER
// ═══════════════════════════════════════════════════════════════════════════════
function handleSmartCursorWsMessage(data) {
  if (data.type === 'token' && _scStreaming) {
    _scStreamContent += data.content || '';
    if (_scStreamEl) {
      _scStreamEl.innerHTML = _renderMarkdown(_scStreamContent) + '<span class="stream-cursor">▌</span>';
      _scStreamEl.scrollTop = _scStreamEl.scrollHeight;
      _scrollResponseBottom();
    }
    if (_scTokenCounter) {
      _scTokenCounter.textContent = `${_scStreamContent.length} chars`;
    }
    return true;
  }

  if (data.type === 'think_token' && _scStreaming) {
    // We could show thinking but keep it minimal in smart cursor
    return true;
  }

  if (data.type === 'done' && _scStreaming) {
    _finalizeStream();
    return true;
  }

  return false;
}

// ═══════════════════════════════════════════════════════════════════════════════
//  EVENT BINDING
// ═══════════════════════════════════════════════════════════════════════════════
function _bindEvents() {
  // Send button
  if (_scSendBtn) {
    _scSendBtn.addEventListener('click', _sendQuestion);
  }

  // Input: Enter to send (Shift+Enter for newline)
  if (_scInput) {
    _scInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        _sendQuestion();
      }
    });
    // Auto-resize textarea
    _scInput.addEventListener('input', () => {
      _scInput.style.height = 'auto';
      _scInput.style.height = Math.min(_scInput.scrollHeight, 120) + 'px';
    });
  }

  // Capture button
  if (_scCaptureBtn) {
    _scCaptureBtn.addEventListener('click', () => {
      if (_scCaptureActive) {
        _cancelCapture();
      } else {
        _startCapture();
      }
    });
  }

  // Clear button
  if (_scClearBtn) {
    _scClearBtn.addEventListener('click', _clearAll);
  }

  // Global keyboard shortcuts (only active when smartcursor panel is visible)
  document.addEventListener('keydown', (e) => {
    const panel = document.getElementById('smartcursor-panel');
    if (!panel || panel.classList.contains('mode-panel--hidden')) return;

    // Ctrl+Shift+C → Capture
    if (e.ctrlKey && e.shiftKey && e.code === 'KeyC') {
      e.preventDefault();
      if (!_scCaptureActive) _startCapture();
    }

    // Ctrl+K → Focus input (quick action)
    if (e.ctrlKey && e.code === 'KeyK') {
      e.preventDefault();
      if (_scInput) _scInput.focus();
    }

    // ESC → Cancel capture if active
    if (e.key === 'Escape' && _scCaptureActive) {
      e.preventDefault();
      _cancelCapture();
    }
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
//  SEND QUESTION
// ═══════════════════════════════════════════════════════════════════════════════
function _sendQuestion() {
  if (!_scInput || _scStreaming) return;
  const text = _scInput.value.trim();
  if (!text) return;

  _scInput.value = '';
  _scInput.style.height = 'auto';

  // Build prompt with context
  let fullPrompt = text;
  if (_scContext) {
    fullPrompt = `[SCREEN CONTEXT]\n${_scContext}\n\n[USER QUESTION]\n${text}`;
  }

  // Add user message to UI
  _addMessage('user', text);

  // Start streaming response
  _startStream();
  _setStatus('thinking', 'Thinking...');

  // Send via WS
  if (_scWs && _scWs.readyState === WebSocket.OPEN) {
    _scWs.send(JSON.stringify({
      message: fullPrompt,
      use_rag: true,
      session_id: 'smart_cursor_session'
    }));
  } else {
    // Fallback: try through REST
    _sendViaRest(fullPrompt);
  }
}

async function _sendViaRest(prompt) {
  try {
    const resp = await fetch('/api/vision-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ analysis: prompt, language: _getSelectedLang(), direct: true })
    });

    if (!resp.ok) {
      _scStreamContent = `❌ Server error (HTTP ${resp.status})`;
      _finalizeStream();
      return;
    }

    const data = await resp.json();
    if (data.code) {
      _scStreamContent = '```' + (_getSelectedLang() || 'python') + '\n' + data.code + '\n```';
    } else {
      _scStreamContent = data.error || 'No response from model.';
    }
    _finalizeStream();
  } catch (err) {
    _scStreamContent = '❌ Error: ' + err.message;
    _finalizeStream();
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
//  SCREEN CAPTURE
// ═══════════════════════════════════════════════════════════════════════════════
async function _startCapture() {
  if (_scCaptureActive) return;
  _scCaptureActive = true;
  _setStatus('capturing', 'Capturing...');

  if (_scCaptureBtn) {
    _scCaptureBtn.textContent = '⛔ Cancel';
    _scCaptureBtn.classList.add('sc-btn--cancel');
  }

  // Show countdown overlay
  const countdownSecs = 3;
  if (_scCaptureOverlay) {
    _scCaptureOverlay.classList.remove('overlay-hidden');
  }
  const numEl = document.getElementById('sc-capture-countdown');
  let count = countdownSecs;
  if (numEl) numEl.textContent = count;

  await new Promise((resolve) => {
    _scCountdownInterval = setInterval(() => {
      count--;
      if (numEl) numEl.textContent = Math.max(count, 0);
      if (count <= 0) {
        clearInterval(_scCountdownInterval);
        _scCountdownInterval = null;
        resolve();
      }
    }, 1000);
  });

  // Hide overlay
  if (_scCaptureOverlay) _scCaptureOverlay.classList.add('overlay-hidden');

  // Check if cancelled during countdown
  if (!_scCaptureActive) return;

  // Take screenshot via API
  _setStatus('analyzing', 'Analyzing screen...');

  _scAbortCtrl = new AbortController();
  let result;
  try {
    const resp = await fetch('/api/see-and-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ language: _getSelectedLang(), no_switch: true }),
      signal: _scAbortCtrl.signal
    });

    // Guard against HTTP 500 / non-JSON responses
    if (!resp.ok) {
      let errText = `Server error (HTTP ${resp.status})`;
      try { const errBody = await resp.json(); errText = errBody.detail || errBody.error || errText; } catch (_) {}
      result = { success: false, error: errText };
    } else {
      result = await resp.json();
    }
  } catch (err) {
    if (err.name === 'AbortError') return;
    result = { success: false, error: err.message };
  }

  if (!_scCaptureActive) return;

  if (result && result.success) {
    // Store context
    _scContext = result.analysis || result.code || 'Screen captured successfully.';

    // Show context in sidebar
    _showContext(_scContext);

    // If code was generated, show it as a response
    if (result.code) {
      _addMessage('assistant', '```' + (result.language || _getSelectedLang()) + '\n' + result.code + '\n```\n\n' + (result.analysis || ''));
      _generateSuggestions(result.code, result.analysis || '');
    } else if (result.analysis) {
      _addMessage('assistant', result.analysis);
    }

    _setStatus('ready', 'Context captured');
  } else {
    const errMsg = (result && result.error) || 'Capture failed';
    _addMessage('system', '❌ ' + errMsg);
    _setStatus('error', 'Capture failed');
    setTimeout(() => _setStatus('ready', 'Ready'), 3000);
  }

  _resetCaptureState();
}

function _cancelCapture() {
  if (!_scCaptureActive) return;

  if (_scCountdownInterval) {
    clearInterval(_scCountdownInterval);
    _scCountdownInterval = null;
  }
  if (_scAbortCtrl) {
    try { _scAbortCtrl.abort(); } catch (_) {}
    _scAbortCtrl = null;
  }
  if (_scCaptureOverlay) _scCaptureOverlay.classList.add('overlay-hidden');

  _addMessage('system', '🛑 Capture cancelled.');
  _resetCaptureState();
  _setStatus('ready', 'Ready');
}

function _resetCaptureState() {
  _scCaptureActive = false;
  _scAbortCtrl = null;
  if (_scCaptureBtn) {
    _scCaptureBtn.textContent = '📸 Capture';
    _scCaptureBtn.classList.remove('sc-btn--cancel');
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
//  STREAMING
// ═══════════════════════════════════════════════════════════════════════════════
function _startStream() {
  _scStreaming = true;
  _scStreamContent = '';

  // Create response bubble
  const msgDiv = _createMessageEl('assistant');
  const contentEl = msgDiv.querySelector('.sc-msg-content');
  contentEl.innerHTML = '<span class="stream-cursor">▌</span>';
  _scStreamEl = contentEl;

  if (_scResponseArea) {
    _removeHero();
    _scResponseArea.appendChild(msgDiv);
    _scrollResponseBottom();
  }
}

function _finalizeStream() {
  _scStreaming = false;
  if (_scStreamEl) {
    _scStreamEl.innerHTML = _renderMarkdown(_scStreamContent);
    _highlightCodeBlocks(_scStreamEl);
    _scStreamEl = null;
  }
  _setStatus('ready', 'Ready');
  if (_scTokenCounter) _scTokenCounter.textContent = '';

  // Store in history
  _scHistory.push({ role: 'assistant', content: _scStreamContent });

  // Generate suggestions from response
  _generateSuggestions(_scStreamContent, '');
}

// ═══════════════════════════════════════════════════════════════════════════════
//  MESSAGE UI
// ═══════════════════════════════════════════════════════════════════════════════
function _addMessage(role, content) {
  const msgDiv = _createMessageEl(role);
  const contentEl = msgDiv.querySelector('.sc-msg-content');
  contentEl.innerHTML = _renderMarkdown(content);
  _highlightCodeBlocks(contentEl);

  if (_scResponseArea) {
    _removeHero();
    _scResponseArea.appendChild(msgDiv);
    _scrollResponseBottom();
  }

  _scHistory.push({ role, content });
}

function _createMessageEl(role) {
  const div = document.createElement('div');
  div.className = `sc-msg sc-msg--${role}`;

  const avatar = document.createElement('div');
  avatar.className = 'sc-msg-avatar';
  if (role === 'user') {
    avatar.textContent = '👤';
  } else if (role === 'assistant') {
    avatar.textContent = '🎯';
  } else {
    avatar.textContent = 'ℹ️';
  }

  const body = document.createElement('div');
  body.className = 'sc-msg-body';

  const label = document.createElement('div');
  label.className = 'sc-msg-label';
  label.textContent = role === 'user' ? 'You' : role === 'assistant' ? 'Smart Cursor' : 'System';

  const content = document.createElement('div');
  content.className = 'sc-msg-content';

  body.appendChild(label);
  body.appendChild(content);
  div.appendChild(avatar);
  div.appendChild(body);

  return div;
}

function _removeHero() {
  if (!_scResponseArea) return;
  const hero = _scResponseArea.querySelector('.sc-hero');
  if (hero) hero.remove();
}

function _scrollResponseBottom() {
  if (_scResponseArea) {
    _scResponseArea.scrollTop = _scResponseArea.scrollHeight;
  }
}

function _clearAll() {
  _scHistory = [];
  _scContext = null;
  _scStreamContent = '';

  if (_scResponseArea) {
    _scResponseArea.innerHTML = `
      <div class="sc-hero">
        <div class="sc-hero-icon">🎯</div>
        <h2 class="sc-hero-title">Smart Cursor</h2>
        <p class="sc-hero-subtitle">AI-powered contextual code assistant.<br>Capture your screen, ask questions, get instant solutions.</p>
        <div class="sc-hero-shortcuts">
          <div class="sc-shortcut-pill"><kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>C</kbd> Capture</div>
          <div class="sc-shortcut-pill"><kbd>Enter</kbd> Send question</div>
          <div class="sc-shortcut-pill"><kbd>Ctrl</kbd>+<kbd>K</kbd> Quick action</div>
        </div>
      </div>`;
  }

  if (_scContextDisplay) {
    _scContextDisplay.innerHTML = '<div class="sc-empty-state">No context captured yet.<br>Click <strong>📸 Capture</strong> or type a question below.</div>';
  }

  if (_scSuggestionsList) {
    _scSuggestionsList.innerHTML = `
      <div class="sc-suggestion-card sc-suggestion--placeholder">
        <span class="sc-suggestion-icon">⚡</span>
        <span>Ask a question or capture screen to get AI suggestions</span>
      </div>`;
  }

  _setStatus('ready', 'Ready');
}

// ═══════════════════════════════════════════════════════════════════════════════
//  CONTEXT SIDEBAR
// ═══════════════════════════════════════════════════════════════════════════════
function _showContext(text) {
  if (!_scContextDisplay) return;

  const truncated = text.length > 500 ? text.substring(0, 500) + '...' : text;

  _scContextDisplay.innerHTML = `
    <div class="sc-context-card">
      <div class="sc-context-badge">📷 Screen Capture</div>
      <div class="sc-context-text">${_escHtml(truncated)}</div>
      <div class="sc-context-meta">${text.length} chars captured</div>
    </div>`;
}

function _generateSuggestions(code, analysis) {
  if (!_scSuggestionsList) return;

  const suggestions = [];

  // Generate contextual suggestions based on content
  if (code && code.includes('def ')) {
    suggestions.push({ icon: '🧪', text: 'Write unit tests for this function', action: 'Write comprehensive unit tests for this code' });
  }
  if (code && code.includes('class ')) {
    suggestions.push({ icon: '📖', text: 'Explain this class structure', action: 'Explain the class structure, design patterns, and methods used in this code' });
  }
  if (code) {
    suggestions.push({ icon: '⚡', text: 'Optimize this code', action: 'Optimize this code for better performance and readability' });
    suggestions.push({ icon: '🐛', text: 'Find potential bugs', action: 'Analyze this code for potential bugs, edge cases, and security issues' });
    suggestions.push({ icon: '📝', text: 'Add comments & docs', action: 'Add detailed inline comments and docstrings to this code' });
  }
  if (analysis && analysis.length > 20) {
    suggestions.push({ icon: '💡', text: 'Alternative approach', action: 'Suggest an alternative algorithm or approach to solve this problem' });
  }

  // Always provide generic suggestions
  if (suggestions.length === 0) {
    suggestions.push(
      { icon: '🔍', text: 'Explain the code on screen', action: 'Explain the code visible on the captured screen' },
      { icon: '⚡', text: 'Suggest improvements', action: 'What improvements can be made to the visible code?' },
      { icon: '🧪', text: 'Write tests', action: 'Write unit tests for the code on screen' }
    );
  }

  _scSuggestionsList.innerHTML = suggestions.map(s => `
    <div class="sc-suggestion-card" onclick="window.NightionSmartCursor._useSuggestion('${_escAttr(s.action)}')">
      <span class="sc-suggestion-icon">${s.icon}</span>
      <span>${_escHtml(s.text)}</span>
    </div>
  `).join('');
}

function _useSuggestion(text) {
  if (_scInput) {
    _scInput.value = text;
    _scInput.focus();
    _sendQuestion();
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
//  STATUS MANAGEMENT
// ═══════════════════════════════════════════════════════════════════════════════
function _setStatus(state, text) {
  if (_scStatusText) _scStatusText.textContent = text;
  if (_scStatusBadge) {
    _scStatusBadge.className = 'sc-status-badge';
    _scStatusBadge.classList.add(`sc-status--${state}`);
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
//  AMBIENT PARTICLES
// ═══════════════════════════════════════════════════════════════════════════════
function _initParticles() {
  if (!_scParticlesCanvas) return;

  const ctx = _scParticlesCanvas.getContext('2d');
  const particles = [];
  const PARTICLE_COUNT = 60;

  function resize() {
    const panel = document.getElementById('smartcursor-panel');
    if (!panel) return;
    _scParticlesCanvas.width = panel.clientWidth;
    _scParticlesCanvas.height = panel.clientHeight;
  }
  resize();
  window.addEventListener('resize', resize);

  // Create particles
  for (let i = 0; i < PARTICLE_COUNT; i++) {
    particles.push({
      x: Math.random() * _scParticlesCanvas.width,
      y: Math.random() * _scParticlesCanvas.height,
      vx: (Math.random() - 0.5) * 0.3,
      vy: (Math.random() - 0.5) * 0.3,
      radius: Math.random() * 2 + 0.5,
      alpha: Math.random() * 0.4 + 0.1,
      hue: Math.random() > 0.5 ? 25 : 30, // orange range
    });
  }

  function animate() {
    const panel = document.getElementById('smartcursor-panel');
    if (!panel || panel.classList.contains('mode-panel--hidden')) {
      _scParticlesRAF = requestAnimationFrame(animate);
      return;
    }

    ctx.clearRect(0, 0, _scParticlesCanvas.width, _scParticlesCanvas.height);

    particles.forEach(p => {
      p.x += p.vx;
      p.y += p.vy;

      // Wrap around edges
      if (p.x < 0) p.x = _scParticlesCanvas.width;
      if (p.x > _scParticlesCanvas.width) p.x = 0;
      if (p.y < 0) p.y = _scParticlesCanvas.height;
      if (p.y > _scParticlesCanvas.height) p.y = 0;

      ctx.beginPath();
      ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
      ctx.fillStyle = `hsla(${p.hue}, 100%, 60%, ${p.alpha})`;
      ctx.fill();
    });

    // Draw connections between nearby particles
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 120) {
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.strokeStyle = `rgba(255, 107, 0, ${0.06 * (1 - dist / 120)})`;
          ctx.lineWidth = 0.5;
          ctx.stroke();
        }
      }
    }

    _scParticlesRAF = requestAnimationFrame(animate);
  }

  animate();
}

// ═══════════════════════════════════════════════════════════════════════════════
//  MARKDOWN RENDERING (lightweight)
// ═══════════════════════════════════════════════════════════════════════════════
function _renderMarkdown(text) {
  if (!text) return '';

  let html = _escHtml(text);

  // Code blocks: ```lang\ncode\n```
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const langLabel = lang || 'code';
    return `<pre class="sc-code-block"><div class="sc-code-header"><span>${langLabel.toUpperCase()}</span><button class="sc-copy-btn" onclick="navigator.clipboard.writeText(this.closest('pre').querySelector('code').textContent);this.textContent='✓ Copied';setTimeout(()=>this.textContent='Copy',1500)">Copy</button></div><code class="language-${langLabel}">${code}</code></pre>`;
  });

  // Inline code: `code`
  html = html.replace(/`([^`]+)`/g, '<code class="sc-inline-code">$1</code>');

  // Bold: **text**
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

  // Italic: *text*
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

  // Headers
  html = html.replace(/^### (.+)$/gm, '<h4 class="sc-md-h3">$1</h4>');
  html = html.replace(/^## (.+)$/gm, '<h3 class="sc-md-h2">$1</h3>');
  html = html.replace(/^# (.+)$/gm, '<h2 class="sc-md-h1">$1</h2>');

  // Lists
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>)/gs, '<ul class="sc-md-ul">$1</ul>');

  // Line breaks
  html = html.replace(/\n/g, '<br>');

  return html;
}

function _highlightCodeBlocks(container) {
  if (!container || typeof hljs === 'undefined') return;
  container.querySelectorAll('pre code').forEach(block => {
    try { hljs.highlightElement(block); } catch (_) {}
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
//  HELPERS
// ═══════════════════════════════════════════════════════════════════════════════
function _getSelectedLang() {
  const sel = document.getElementById('sc-lang-select');
  return sel ? sel.value : 'python';
}

function _escHtml(t) {
  if (!t) return '';
  return t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function _escAttr(t) {
  if (!t) return '';
  return t.replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

// ═══════════════════════════════════════════════════════════════════════════════
//  PUBLIC API
// ═══════════════════════════════════════════════════════════════════════════════
window.NightionSmartCursor = {
  init:            initSmartCursor,
  destroy:         destroySmartCursor,
  handleWsMessage: handleSmartCursorWsMessage,
  _useSuggestion:  _useSuggestion,
};
