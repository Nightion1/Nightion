/**
 * mode_switcher.js — Nightion Mode Switcher
 * Manages the 4-tab bar: [💬 Chat] [🦊 Voice] [✍️ Writer] [🎯 Smart Cursor]
 * Loads config from /api/config and initialises sub-modes on first activation.
 *
 * Panels:
 *   chat-panel          → existing chat UI (untouched)
 *   voice-panel         → fox mode + matrix rain
 *   writer-panel        → Monaco + vision pipeline
 *   smartcursor-panel   → AI-powered contextual cursor assistant
 *
 * This file runs AFTER app.js so it can reference the global `ws` from app.js.
 */

'use strict';

// ── State ─────────────────────────────────────────────────────────────────────
let _activeMode = 'chat';
let _voiceInited = false;
let _writerInited = false;
let _smartCursorInited = false;
let _nightionCfg = null;

// ── Panels & tabs ─────────────────────────────────────────────────────────────
const PANELS = ['chat-panel', 'voice-panel', 'writer-panel', 'smartcursor-panel'];
const MODES  = ['chat', 'voice', 'writer', 'smartcursor'];

// ═══════════════════════════════════════════════════════════════════════════════
//  BOOT — runs once DOM is loaded
// ═══════════════════════════════════════════════════════════════════════════════
async function initModeSwitcher() {
  // 1. Load config
  try {
    const r = await fetch('/api/config');
    if (r.ok) _nightionCfg = await r.json();
  } catch (_) {
    _nightionCfg = {};
  }

  // 2. Wire tab buttons
  document.querySelectorAll('.mode-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      const mode = btn.getAttribute('data-mode');
      if (mode) switchMode(mode);
    });
  });

  // 3. Ctrl+Shift+V global — delegate to writer mode only when writer is active
  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.shiftKey && e.code === 'KeyV') {
      e.preventDefault();
      if (_activeMode === 'writer' && window.NightionWriterMode) {
        window.NightionWriterMode.triggerVision();
      }
    }
  });

  // 4. Patch the main WS message handler from app.js to also route to sub-modes
  _patchMainWsHandler();

  // 5. Activate default (Chat) tab
  switchMode('chat');
}

// ═══════════════════════════════════════════════════════════════════════════════
//  MODE SWITCHING
// ═══════════════════════════════════════════════════════════════════════════════
function switchMode(mode) {
  if (!MODES.includes(mode)) return;
  _activeMode = mode;

  // Update tab active state
  document.querySelectorAll('.mode-tab').forEach(btn => {
    btn.classList.toggle('mode-tab--active', btn.getAttribute('data-mode') === mode);
  });

  // Show/hide panels
  PANELS.forEach(panelId => {
    const el = document.getElementById(panelId);
    if (!el) return;
    const isActive = panelId === mode + '-panel';
    el.classList.toggle('mode-panel--hidden', !isActive);
  });

  // Init sub-modes on first activation
  const voiceCfg = (_nightionCfg && _nightionCfg.voice_mode) || _defaultVoiceCfg();

  if (mode === 'voice') {
    if (!_voiceInited && window.NightionVoiceMode) {
      // ws is the global from app.js
      window.NightionVoiceMode.init(voiceCfg, typeof ws !== 'undefined' ? ws : null);
      _voiceInited = true;
    }
  }

  if (mode === 'writer') {
    if (!_writerInited && window.NightionWriterMode) {
      window.NightionWriterMode.init(voiceCfg, typeof ws !== 'undefined' ? ws : null);
      _writerInited = true;
    }
  }

  if (mode === 'smartcursor') {
    if (!_smartCursorInited && window.NightionSmartCursor) {
      window.NightionSmartCursor.init(voiceCfg, typeof ws !== 'undefined' ? ws : null);
      _smartCursorInited = true;
    }
  }

  // When leaving voice mode, pause heavy animations
  if (mode !== 'voice' && _voiceInited && window.NightionVoiceMode) {
    // We do NOT call destroy — just leave it paused (matrix stops drawing offscreen)
    // The rAF loop will continue but won't be visible — minimal CPU
  }
}

// ─── Default config fallback if /api/config fails ─────────────────────────────
function _defaultVoiceCfg() {
  return {
    theme_color: '#FF6B00',
    fox_idle_size: 300,
    fox_speak_size: 420,
    matrix_speed_idle: 1,
    matrix_speed_listening: 2,
    matrix_speed_speaking: 3,
    countdown_seconds: 5
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
//  WS PATCHING — intercept messages for active sub-mode
// ═══════════════════════════════════════════════════════════════════════════════
function _patchMainWsHandler() {
  // We poll until ws is available (app.js creates it asynchronously)
  const pollInterval = setInterval(() => {
    if (typeof ws !== 'undefined' && ws) {
      _attachWsRouter(ws);
      clearInterval(pollInterval);
    }
  }, 200);

  // Also re-attach when WS reconnects (app.js calls connectWS which creates a new ws)
  // Hook into connectWS if available
  const originalConnectWS = window.connectWS;
  if (typeof originalConnectWS === 'function') {
    window.connectWS = function() {
      originalConnectWS.apply(this, arguments);
      // Give it a moment then re-attach
      setTimeout(() => {
        if (typeof ws !== 'undefined' && ws) _attachWsRouter(ws);
      }, 500);
    };
  }
}

function _attachWsRouter(wsObj) {
  const originalOnMessage = wsObj.onmessage;

  wsObj.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);

      // Route fox_state events to voice mode regardless of active panel
      if (data.type === 'fox_state' && window.NightionVoiceMode && _voiceInited) {
        window.NightionVoiceMode.handleWsMessage(data);
      }

      // When voice panel is active: route tokens to fox subtitle
      if (_activeMode === 'voice' && _voiceInited && window.NightionVoiceMode) {
        const consumed = window.NightionVoiceMode.handleWsMessage(data);
        if (consumed) return; // skip app.js handler
      }

      // When writer panel is active: route tokens to writer chat
      if (_activeMode === 'writer' && _writerInited && window.NightionWriterMode) {
        window.NightionWriterMode.handleWsMessage(data);
        // Still let original handler run (so status dot updates etc)
      }

      // When smart cursor panel is active: route tokens to smart cursor
      if (_activeMode === 'smartcursor' && _smartCursorInited && window.NightionSmartCursor) {
        const consumed = window.NightionSmartCursor.handleWsMessage(data);
        if (consumed) return; // skip app.js handler
      }

    } catch (_) {}

    // Always call original handler
    if (originalOnMessage) originalOnMessage.call(wsObj, e);
  };
}

// ─── Expose public API ────────────────────────────────────────────────────────
window.NightionModeSwitcher = { init: initModeSwitcher, switchMode };

// ─── Auto-boot after DOM ──────────────────────────────────────────────────────
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initModeSwitcher);
} else {
  // DOM already ready
  initModeSwitcher();
}
