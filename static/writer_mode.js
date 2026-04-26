/**
 * writer_mode.js — Nightion Writer Mode
 * Monaco Editor (right 60%) + Chat history panel (left 40%) + Vision Pipeline.
 *
 * See & Code Pipeline (Ctrl+Shift+V or "👁️ See & Code" button):
 *   1. Instant screenshot + parallel countdown in chat panel
 *   2. POST /api/see-and-code (pyautogui + vision AI → code)
 *   3. Code into Monaco → "Ready!" state
 *   4. POST /api/type-humanlike (waits for click → human-like typing)
 *
 * Type Anywhere: POST /api/type-anywhere with Monaco code, with ESC cancel safety.
 *
 * All countdown values read from _wcfg (voice_mode.countdown_seconds).
 */

'use strict';

// ── Module state ──────────────────────────────────────────────────────────────
let _wcfg = null;
let _monacoEditor = null;
let _monacoLoaded = false;
let _writerWs = null;          // shared WS reference
let _writerMessages = [];      // simplified chat history for writer panel
let _typeCountdownTimer = null;
let _escCancelActive = false;

// See & Code state
let _seeCodeActive = false;       // true while pipeline is running
let _seeCodeAbortController = null; // AbortController for fetch cancellation
let _seeCodeCountdownInterval = null;

// ── DOM refs (populated on init) ──────────────────────────────────────────────
let _writerChatList = null;
let _writerChatInput = null;
let _writerSendBtn = null;
let _monacoContainer = null;
let _outputPanel = null;
let _countdownOverlay = null;
let _typeCountdownOverlay = null;
let _typeAnywhereBtn = null;
let _langLabel = null;
let _seeCodeBtn = null;

// ═══════════════════════════════════════════════════════════════════════════════
//  PUBLIC INIT
// ═══════════════════════════════════════════════════════════════════════════════
function initWriterMode(cfg, wsRef) {
  _wcfg   = cfg;
  _writerWs = wsRef;

  _writerChatList    = document.getElementById('writer-chat-list');
  _writerChatInput   = document.getElementById('writer-chat-input');
  _writerSendBtn     = document.getElementById('writer-send-btn');
  _monacoContainer   = document.getElementById('monaco-container');
  _outputPanel       = document.getElementById('writer-output-panel');
  _countdownOverlay  = document.getElementById('vision-countdown-overlay');
  _typeCountdownOverlay = document.getElementById('type-countdown-overlay');
  _typeAnywhereBtn   = document.getElementById('type-anywhere-btn');
  _langLabel         = document.getElementById('writer-lang-label');
  _seeCodeBtn        = document.getElementById('see-code-btn');

  _loadMonaco();
  _bindWriterEvents();

  // Register Ctrl+Shift+V globally — mode_switcher will gate by active panel
  window._writerCtrlShiftV = _onCtrlShiftV;
}

function destroyWriterMode() {
  // Cleanup is safe — Monaco stays loaded for reuse
  _cancelSeeAndCode();
}

// ── Public API ────────────────────────────────────────────────────────────────
function handleWriterWsMessage(data) {
  // Forward chat tokens to writer panel chat list
  if (data.type === 'token') {
    _appendWriterToken(data.content || '');
    return false; // let mode_switcher also let app.js see it
  }
  if (data.type === 'done') {
    _finalizeWriterMessage();
    // Check if last message contains code we should push to Monaco
    _tryExtractCodeToMonaco();
    return false;
  }
  return false;
}

// ═══════════════════════════════════════════════════════════════════════════════
//  MONACO LOADER
// ═══════════════════════════════════════════════════════════════════════════════
function _loadMonaco() {
  if (_monacoLoaded) { _onMonacoReady(); return; }

  if (window.require && window.monaco) {
    _monacoLoaded = true;
    _onMonacoReady();
    return;
  }

  // Load monaco-editor from CDN
  const loaderScript = document.createElement('script');
  loaderScript.src = 'https://cdn.jsdelivr.net/npm/monaco-editor@0.44.0/min/vs/loader.js';
  loaderScript.onload = () => {
    require.config({ paths: { vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.44.0/min/vs' } });
    require(['vs/editor/editor.main'], () => {
      _monacoLoaded = true;
      _onMonacoReady();
    });
  };
  loaderScript.onerror = () => {
    if (_monacoContainer) {
      _monacoContainer.innerHTML = '<div style="color:#ef4444;padding:24px;font-family:monospace">Monaco Editor failed to load. Check internet connection.</div>';
    }
  };
  document.head.appendChild(loaderScript);
}

function _onMonacoReady() {
  if (!_monacoContainer || _monacoEditor) return;

  // Apply Monaco dark theme matching Nightion palette
  monaco.editor.defineTheme('nightion-dark', {
    base: 'vs-dark',
    inherit: true,
    rules: [
      { token: 'comment', foreground: '52525b', fontStyle: 'italic' },
      { token: 'keyword', foreground: 'FF6B00', fontStyle: 'bold' },
      { token: 'string', foreground: 'f97316' },
      { token: 'number', foreground: 'fbbf24' },
    ],
    colors: {
      'editor.background': '#09090b',
      'editor.foreground': '#fafafa',
      'editor.lineHighlightBackground': '#18181b',
      'editorCursor.foreground': '#FF6B00',
      'editor.selectionBackground': '#FF6B0030',
      'editorLineNumber.foreground': '#3f3f46',
      'editorLineNumber.activeForeground': '#FF6B00',
      'editor.inactiveSelectionBackground': '#FF6B0020',
      'scrollbarSlider.background': '#27272a',
      'scrollbarSlider.hoverBackground': '#3f3f46',
    }
  });

  _monacoEditor = monaco.editor.create(_monacoContainer, {
    value: '// Nightion Writer — code will appear here\n// Press Ctrl+Shift+V or click "👁️ See & Code" to capture screen\n',
    language: 'python',
    theme: 'nightion-dark',
    fontSize: 14,
    fontFamily: '"JetBrains Mono", "Fira Code", monospace',
    fontLigatures: true,
    wordWrap: 'on',
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    automaticLayout: true,
    padding: { top: 16, bottom: 16 },
    lineNumbers: 'on',
    renderLineHighlight: 'line',
    smoothScrolling: true,
    cursorBlinking: 'smooth',
    cursorSmoothCaretAnimation: true,
  });

  // Bind Ctrl+Shift+V inside Monaco too
  _monacoEditor.addCommand(
    monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyV,
    () => _onCtrlShiftV()
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
//  WRITER CHAT (left panel)
// ═══════════════════════════════════════════════════════════════════════════════
let _currentWriterBubble = null;
let _currentWriterContent = '';

function _bindWriterEvents() {
  if (_writerSendBtn) {
    _writerSendBtn.addEventListener('click', _sendWriterMessage);
  }
  if (_writerChatInput) {
    _writerChatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        _sendWriterMessage();
      }
    });
  }

  // See & Code button — toggles between start and cancel
  if (_seeCodeBtn) {
    _seeCodeBtn.addEventListener('click', () => {
      if (_seeCodeActive) {
        _cancelSeeAndCode();
      } else {
        _onCtrlShiftV();
      }
    });
  }

  // Run button
  const runBtn = document.getElementById('writer-run-btn');
  if (runBtn) runBtn.addEventListener('click', _runMonacoCode);

  // Type Anywhere button
  if (_typeAnywhereBtn) {
    _typeAnywhereBtn.addEventListener('click', triggerTypeAnywhere);
  }

  // Clear output
  const clearOutBtn = document.getElementById('writer-clear-output');
  if (clearOutBtn) clearOutBtn.addEventListener('click', () => {
    if (_outputPanel) _outputPanel.textContent = '';
  });

  // Lang selector
  const langSelect = document.getElementById('writer-lang-select');
  if (langSelect) langSelect.addEventListener('change', () => {
    if (_monacoEditor) {
      const model = _monacoEditor.getModel();
      if (model) monaco.editor.setModelLanguage(model, langSelect.value);
    }
    if (_langLabel) _langLabel.textContent = langSelect.options[langSelect.selectedIndex].text;
  });

  // Global ESC handler for See & Code cancellation
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && _seeCodeActive) {
      e.preventDefault();
      _cancelSeeAndCode();
    }
  });
}

function _sendWriterMessage() {
  if (!_writerChatInput) return;
  const text = _writerChatInput.value.trim();
  if (!text) return;

  _addWriterChatBubble('user', text);
  _writerChatInput.value = '';

  // Check for voice-write triggers
  const lc = text.toLowerCase();
  if (_matchesVisionTrigger(lc)) {
    _addWriterChatBubble('system', '🔍 Triggering vision pipeline from your command...');
    setTimeout(() => _onCtrlShiftV(), 400);
    return;
  }
  if (_matchesDirectCodeTrigger(lc)) {
    const subject = _extractSubject(lc);
    _generateCodeDirect(subject || text);
    return;
  }

  // Regular chat through main WS
  if (_writerWs && _writerWs.readyState === WebSocket.OPEN) {
    _startWriterStreaming();
    _writerWs.send(JSON.stringify({
      message: text,
      use_rag: true,
      session_id: 'writer_session'
    }));
  }
}

function _matchesVisionTrigger(lc) {
  return lc.includes('write code here for this question') ||
         lc.includes('code this question') ||
         lc.includes('solve this') && lc.includes('here');
}

function _matchesDirectCodeTrigger(lc) {
  return (lc.includes('write code for') || lc.includes('generate code for')) && lc.includes('here');
}

function _extractSubject(lc) {
  const m = lc.match(/(?:write|generate) code for (.+?) here/);
  return m ? m[1] : null;
}

function _addWriterChatBubble(role, content) {
  if (!_writerChatList) return;
  const div = document.createElement('div');
  div.className = `wchat-bubble wchat-${role}`;
  div.textContent = content;
  _writerChatList.appendChild(div);
  _writerChatList.scrollTop = _writerChatList.scrollHeight;
  return div;
}

/** Add a styled status bubble with icon and optional animation class */
function _addStatusBubble(icon, text, className) {
  if (!_writerChatList) return null;
  const div = document.createElement('div');
  div.className = `wchat-bubble wchat-system see-code-status ${className || ''}`;
  div.innerHTML = `<span class="see-code-icon">${icon}</span> ${_escHtml(text)}`;
  _writerChatList.appendChild(div);
  _writerChatList.scrollTop = _writerChatList.scrollHeight;
  return div;
}

function _escHtml(t) {
  if (!t) return '';
  return t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/** Add an inline animated countdown to the chat panel */
function _addCountdownBubble() {
  if (!_writerChatList) return null;
  const div = document.createElement('div');
  div.className = 'wchat-bubble wchat-system see-code-countdown-bubble';
  div.innerHTML = `
    <div class="see-code-countdown-inner">
      <div class="see-code-countdown-label">Capturing in</div>
      <div class="see-code-countdown-num" id="see-code-countdown-live">5</div>
    </div>
  `;
  _writerChatList.appendChild(div);
  _writerChatList.scrollTop = _writerChatList.scrollHeight;
  return div;
}

function _startWriterStreaming() {
  _currentWriterContent = '';
  _currentWriterBubble = _addWriterChatBubble('assistant', '▋');
}

function _appendWriterToken(token) {
  _currentWriterContent += token;
  if (_currentWriterBubble) {
    _currentWriterBubble.textContent = _currentWriterContent + '▋';
    _writerChatList.scrollTop = _writerChatList.scrollHeight;
  }
}

function _finalizeWriterMessage() {
  if (_currentWriterBubble) {
    _currentWriterBubble.textContent = _currentWriterContent;
    _currentWriterBubble = null;
  }
}

function _tryExtractCodeToMonaco() {
  if (!_currentWriterContent && !_writerMessages) return;
  const text = _currentWriterContent;
  const codeMatch = text.match(/```(\w*)\n?([\s\S]*?)```/);
  if (codeMatch) {
    const lang = codeMatch[1] || 'python';
    const code = codeMatch[2].trim();
    _setMonacoCode(code, lang);
    _addWriterChatBubble('system', `✅ Code auto-inserted into editor (${lang})`);
    _showTypeAnywhereBtn(code);
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
//  SEE & CODE PIPELINE (NEW)
// ═══════════════════════════════════════════════════════════════════════════════
function _onCtrlShiftV() {
  // Only run when writer panel is visible
  const writerPanel = document.getElementById('writer-panel');
  if (!writerPanel || writerPanel.classList.contains('mode-panel--hidden')) return;

  if (_seeCodeActive) {
    _cancelSeeAndCode();
    return;
  }

  triggerSeeAndCode();
}

async function triggerSeeAndCode() {
  if (_seeCodeActive) return;
  _seeCodeActive = true;

  // ── Update button to Cancel mode ───────────────────────────────────────
  if (_seeCodeBtn) {
    _seeCodeBtn.textContent = '⛔ Cancel';
    _seeCodeBtn.classList.add('cancel-mode');
  }

  const language = _currentEditorLang();
  const countdownSecs = (_wcfg && _wcfg.countdown_seconds) ? Math.min(_wcfg.countdown_seconds, 5) : 5;

  // ── Step 1: Show countdown FIRST (screenshot taken AFTER countdown) ────
  _addStatusBubble('👁', `Reading screen in ${language.toUpperCase()} mode...`, 'see-code-reading');

  const countdownBubble = _addCountdownBubble();
  const countdownNumEl = countdownBubble ? countdownBubble.querySelector('.see-code-countdown-num') : null;

  // Countdown animation — runs fully before we screenshot
  let count = countdownSecs;
  await new Promise((resolve) => {
    if (countdownNumEl) countdownNumEl.textContent = count;

    _seeCodeCountdownInterval = setInterval(() => {
      count--;
      if (countdownNumEl) countdownNumEl.textContent = Math.max(count, 0);
      if (count <= 0) {
        clearInterval(_seeCodeCountdownInterval);
        _seeCodeCountdownInterval = null;
        resolve();
      }
    }, 1000);
  });

  // Remove countdown bubble
  if (countdownBubble && countdownBubble.parentNode) {
    countdownBubble.remove();
  }

  // Check if cancelled during countdown
  if (!_seeCodeActive) return;

  // ── Step 2: NOW take screenshot + generate code (Alt+Tab captures the other window) ──
  const statusBubble = _addStatusBubble('🧠', 'Switching to target window & capturing...', 'see-code-generating');

  _seeCodeAbortController = new AbortController();

  let result;
  try {
    const resp = await fetch('/api/see-and-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ language }),
      signal: _seeCodeAbortController.signal,
    });
    result = await resp.json();
  } catch (err) {
    if (err.name === 'AbortError') return;
    result = { success: false, error: err.message };
  }

  // Check if cancelled
  if (!_seeCodeActive) return;

  // Remove generating status
  if (statusBubble && statusBubble.parentNode) {
    statusBubble.remove();
  }

  if (!result || !result.success || !result.code) {
    const errMsg = (result && result.error) || (result && result.analysis) || 'No code generated';
    _addStatusBubble('❌', `Failed: ${errMsg}`, 'see-code-error');
    _resetSeeCodeState();
    return;
  }

  // ── Step 3: Insert code into Monaco ────────────────────────────────────
  const code = result.code;
  const detectedLang = result.language || language;

  _setMonacoCode(code, detectedLang);
  _addStatusBubble('✅', `${detectedLang.toUpperCase()} solution ready (${code.split('\n').length} lines)`, 'see-code-ready');

  if (result.analysis && result.analysis.length > 10) {
    _addWriterChatBubble('system', `🔍 ${result.analysis.substring(0, 200)}${result.analysis.length > 200 ? '...' : ''}`);
  }

  // ── Step 4: Show "Ready! Click outside to type" ────────────────────────
  const readyBubble = _addStatusBubble('🎯', 'Ready! Click anywhere outside Nightion to start typing...', 'see-code-ready see-code-waiting-click');

  // Kick off human-like typing (waits for external click)
  try {
    const typeResp = await fetch('/api/type-humanlike', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
    });
    const typeResult = await typeResp.json();

    // Remove waiting bubble
    if (readyBubble && readyBubble.parentNode) {
      readyBubble.remove();
    }

    if (typeResult.success) {
      if (typeResult.method === 'humanlike_cancelled') {
        _addStatusBubble('🛑', 'Typing cancelled.', '');
      } else {
        _addStatusBubble('✅', `Done! Typed ${typeResult.chars_typed} chars with human-like speed.`, 'see-code-done');
      }
    } else {
      _addStatusBubble('⚠️', `Typing issue: ${typeResult.error || 'Unknown'}`, 'see-code-error');
    }
  } catch (err) {
    if (readyBubble && readyBubble.parentNode) readyBubble.remove();
    _addStatusBubble('❌', `Type error: ${err.message}`, 'see-code-error');
  }

  _resetSeeCodeState();
}

function _cancelSeeAndCode() {
  if (!_seeCodeActive) return;

  // 1. Abort any in-flight fetch
  if (_seeCodeAbortController) {
    try { _seeCodeAbortController.abort(); } catch (_) {}
    _seeCodeAbortController = null;
  }

  // 2. Clear countdown timer
  if (_seeCodeCountdownInterval) {
    clearInterval(_seeCodeCountdownInterval);
    _seeCodeCountdownInterval = null;
  }

  // 3. Cancel humanlike typing on backend
  fetch('/api/type-humanlike/cancel', { method: 'POST' }).catch(() => {});

  // 4. Show cancelled message
  _addStatusBubble('🛑', 'See & Code cancelled.', '');

  _resetSeeCodeState();
}

function _resetSeeCodeState() {
  _seeCodeActive = false;
  _seeCodeAbortController = null;

  if (_seeCodeBtn) {
    _seeCodeBtn.textContent = '👁️ See & Code';
    _seeCodeBtn.classList.remove('cancel-mode');
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
//  LEGACY VISION PIPELINE (kept for backwards compat / chat triggers)
// ═══════════════════════════════════════════════════════════════════════════════
async function triggerVisionPipeline() {
  // Redirect to new pipeline
  triggerSeeAndCode();
}

// ═══════════════════════════════════════════════════════════════════════════════
//  TYPE ANYWHERE (legacy clipboard-paste method)
// ═══════════════════════════════════════════════════════════════════════════════
function triggerTypeAnywhere() {
  const code = _monacoEditor ? _monacoEditor.getValue() : '';
  if (!code || !code.trim() || code.startsWith('// Nightion Writer')) {
    _addWriterChatBubble('system', '⚠️ No code in editor to type.');
    return;
  }

  const countdownSecs = (_wcfg && _wcfg.countdown_seconds) || 5;
  _showTypeCountdown(countdownSecs, code);
}

function _showTypeCountdown(secs, code) {
  if (!_typeCountdownOverlay) return;

  _typeCountdownOverlay.classList.remove('overlay-hidden');
  _escCancelActive = true;

  const numEl = document.getElementById('type-countdown-num');
  let count = secs;
  if (numEl) numEl.textContent = count;

  // ESC cancel handler
  const onEsc = (e) => {
    if (e.key === 'Escape' && _escCancelActive) {
      clearInterval(_typeCountdownTimer);
      _typeCountdownOverlay.classList.add('overlay-hidden');
      _escCancelActive = false;
      document.removeEventListener('keydown', onEsc);
      _addWriterChatBubble('system', '🛑 Type Anywhere cancelled (ESC pressed).');
    }
  };
  document.addEventListener('keydown', onEsc);

  _typeCountdownTimer = setInterval(async () => {
    count--;
    if (numEl) numEl.textContent = count;

    if (count <= 0) {
      clearInterval(_typeCountdownTimer);
      document.removeEventListener('keydown', onEsc);
      _escCancelActive = false;
      _typeCountdownOverlay.classList.add('overlay-hidden');

      // Fire the type request
      await _executeTypeAnywhere(code);
    }
  }, 1000);
}

async function _executeTypeAnywhere(code) {
  _addWriterChatBubble('system', '⌨️ Typing code at cursor position...');
  try {
    const resp = await fetch('/api/type-anywhere', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code })
    });
    if (resp.ok) {
      const d = await resp.json();
      if (d.success) {
        _addWriterChatBubble('system', `✅ Code typed successfully (${d.chars_typed || '?'} chars) via ${d.method || 'clipboard'}.`);
      } else {
        _addWriterChatBubble('system', `❌ Type failed: ${d.error || 'Unknown error'}`);
      }
    } else {
      _addWriterChatBubble('system', '❌ Type Anywhere API returned error.');
    }
  } catch (err) {
    _addWriterChatBubble('system', '❌ Could not reach backend: ' + err.message);
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
//  DIRECT CODE GENERATION
// ═══════════════════════════════════════════════════════════════════════════════
async function _generateCodeDirect(subject) {
  _addWriterChatBubble('system', `🧠 Generating code for: "${subject}"...`);
  try {
    const resp = await fetch('/api/vision-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ analysis: subject, language: _currentEditorLang(), direct: true })
    });
    if (resp.ok) {
      const d = await resp.json();
      if (d.code) {
        _setMonacoCode(d.code, d.language || 'python');
        _addWriterChatBubble('system', `✅ Code generated (${d.language || 'python'}). Ready to type anywhere.`);
        _showTypeAnywhereBtn(d.code);
      }
    }
  } catch (err) {
    _addWriterChatBubble('system', '❌ Generation error: ' + err.message);
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
//  MONACO HELPERS
// ═══════════════════════════════════════════════════════════════════════════════
function _setMonacoCode(code, lang) {
  if (!_monacoEditor) return;
  const model = _monacoEditor.getModel();
  if (model) {
    model.setValue(code);
    const safeLang = lang.toLowerCase().replace('c++', 'cpp').replace('c#', 'csharp');
    monaco.editor.setModelLanguage(model, safeLang);
  }
  if (_langLabel) _langLabel.textContent = lang;

  const langSelect = document.getElementById('writer-lang-select');
  if (langSelect) {
    const opt = Array.from(langSelect.options).find(o => o.value === lang || o.value === lang.toLowerCase());
    if (opt) langSelect.value = opt.value;
  }
}

function _currentEditorLang() {
  const sel = document.getElementById('writer-lang-select');
  return sel ? sel.value : 'python';
}

function _showTypeAnywhereBtn(code) {
  if (_typeAnywhereBtn) {
    _typeAnywhereBtn.classList.remove('btn-hidden');
    _typeAnywhereBtn.textContent = `⌨️ Type Anywhere (${(_wcfg && _wcfg.countdown_seconds) || 5}s)`;
  }
}

async function _runMonacoCode() {
  const code = _monacoEditor ? _monacoEditor.getValue() : '';
  if (!code.trim()) return;

  if (_outputPanel) {
    _outputPanel.textContent = 'Running...';
    _outputPanel.className = 'writer-output-panel';
  }

  try {
    const resp = await fetch('/api/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, timeout: 15 })
    });
    const d = await resp.json();
    if (_outputPanel) {
      _outputPanel.textContent = d.success
        ? (d.stdout || '(no output)')
        : (d.error || d.stderr || 'Unknown error');
      _outputPanel.className = 'writer-output-panel' + (d.success ? '' : ' output-error');
    }
  } catch (err) {
    if (_outputPanel) {
      _outputPanel.textContent = '❌ Server error: ' + err.message;
      _outputPanel.className = 'writer-output-panel output-error';
    }
  }
}

// ── Expose public API ─────────────────────────────────────────────────────────
window.NightionWriterMode = {
  init:              initWriterMode,
  destroy:           destroyWriterMode,
  handleWsMessage:   handleWriterWsMessage,
  triggerVision:     triggerSeeAndCode,
  triggerTypeAnywhere: triggerTypeAnywhere,
};
