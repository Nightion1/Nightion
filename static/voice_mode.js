/**
 * voice_mode.js — Nightion Voice/Fox Mode
 * Full-screen black canvas, matrix rain, animated SVG fox, 4 states.
 * All sizes/speeds read from voiceCfg (passed from mode_switcher.js via initVoiceMode).
 *
 * Fox States: idle | listening | thinking | speaking
 * WebSocket events handled: {"type":"fox_state","state":"...", "text":"..."}
 */

'use strict';

// ── Module-level state ────────────────────────────────────────────────────────
let _vcfg = null;          // voice config from config.json
let _foxState = 'idle';
let _matrixInterval = null;
let _foxAnimFrame = null;
let _foxScale = 1.0;
let _foxScaleTarget = 1.0;
let _foxGlowAlpha = 0.4;
let _subtitleWords = [];
let _subtitleWordIdx = 0;
let _subtitleInterval = null;
let _dotsInterval = null;
let _voiceWsRef = null;    // reference to main WS for fox_state messages
let _escCancelFn = null;   // ESC key handler (shared with writer_mode)

// ── DOM references (populated on init) ───────────────────────────────────────
let _matrixCanvas = null;
let _matrixCtx = null;
let _foxContainer = null;
let _foxImg = null;
let _subtitleEl = null;
let _micDot = null;

// ── Matrix rain internal ──────────────────────────────────────────────────────
const MATRIX_CHARS = '01{}();=>/<>[]!&|^~'.split('');
let _matrixDrops = [];
let _matrixSpeed = 1;   // frames to skip between draws (lower = faster)
let _matrixFrame = 0;

// ═══════════════════════════════════════════════════════════════════════════════
//  PUBLIC INIT — called by mode_switcher.js when Voice tab first activated
// ═══════════════════════════════════════════════════════════════════════════════
function initVoiceMode(voiceCfg, wsRef) {
  _vcfg = voiceCfg;
  _voiceWsRef = wsRef;

  _matrixCanvas  = document.getElementById('voice-matrix-canvas');
  _foxContainer  = document.getElementById('fox-avatar-wrap');
  _foxImg        = document.getElementById('fox-svg-img');
  _subtitleEl    = document.getElementById('fox-subtitle');
  _micDot        = document.getElementById('voice-mic-dot');

  _resizeMatrix();
  window.addEventListener('resize', _resizeMatrix);

  _startMatrixRain();
  _startFoxScaleLoop();
  _setFoxStateTo('idle');

  // Click fox → toggle listening
  _foxContainer.addEventListener('click', _onFoxClick);

  // Space key → toggle listening (only when voice panel is visible)
  document.addEventListener('keydown', _onVoiceKeyDown);
}

// ── Cleanup — called when switching away from Voice tab ───────────────────────
function destroyVoiceMode() {
  window.removeEventListener('resize', _resizeMatrix);
  document.removeEventListener('keydown', _onVoiceKeyDown);
  if (_foxContainer) _foxContainer.removeEventListener('click', _onFoxClick);
  if (_matrixInterval) { clearInterval(_matrixInterval); _matrixInterval = null; }
  if (_foxAnimFrame) { cancelAnimationFrame(_foxAnimFrame); _foxAnimFrame = null; }
  if (_subtitleInterval) { clearInterval(_subtitleInterval); _subtitleInterval = null; }
  if (_dotsInterval) { clearInterval(_dotsInterval); _dotsInterval = null; }
}

// ── Public state setter — called by mode_switcher when fox_state WS event ────
function setFoxState(state, text) {
  _setFoxStateTo(state, text);
}

// ═══════════════════════════════════════════════════════════════════════════════
//  PRIVATE — State machine
// ═══════════════════════════════════════════════════════════════════════════════
function _setFoxStateTo(state, text) {
  _foxState = state;
  _clearSubtitleAnimations();

  const idleSize    = (_vcfg && _vcfg.fox_idle_size)    || 300;
  const speakSize   = (_vcfg && _vcfg.fox_speak_size)   || 420;
  const speedIdle   = (_vcfg && _vcfg.matrix_speed_idle)     || 1;
  const speedListen = (_vcfg && _vcfg.matrix_speed_listening) || 2;
  const speedSpeak  = (_vcfg && _vcfg.matrix_speed_speaking)  || 3;

  // Update fox container size
  const targetPx = (state === 'idle' || state === 'thinking') ? idleSize : speakSize;
  _foxContainer.style.width  = targetPx + 'px';
  _foxContainer.style.height = targetPx + 'px';

  switch (state) {

    case 'idle':
      _matrixSpeed      = speedIdle;
      _foxScaleTarget   = 1.0;
      _foxGlowAlpha     = 0.35;
      _foxContainer.classList.remove('state-listening', 'state-thinking', 'state-speaking');
      _foxContainer.classList.add('state-idle');
      _setSubtitle('');
      _micDot.classList.remove('mic-active');
      break;

    case 'listening':
      _matrixSpeed      = speedListen;
      _foxScaleTarget   = 1.0;   // size change handled by CSS + width/height
      _foxGlowAlpha     = 0.8;
      _foxContainer.classList.remove('state-idle', 'state-thinking', 'state-speaking');
      _foxContainer.classList.add('state-listening');
      _setSubtitle('Listening...');
      _micDot.classList.add('mic-active');
      break;

    case 'thinking':
      _matrixSpeed      = speedListen;
      _foxScaleTarget   = 1.0;
      _foxGlowAlpha     = 0.55;
      _foxContainer.classList.remove('state-idle', 'state-listening', 'state-speaking');
      _foxContainer.classList.add('state-thinking');
      _animateThinkingDots();
      _micDot.classList.remove('mic-active');
      break;

    case 'speaking':
      _matrixSpeed      = speedSpeak;
      _foxScaleTarget   = 1.0;  // oscillation handled in anim loop
      _foxGlowAlpha     = 1.0;
      _foxContainer.classList.remove('state-idle', 'state-listening', 'state-thinking');
      _foxContainer.classList.add('state-speaking');
      if (text) _animateWordByWord(text);
      else _setSubtitle('');
      _micDot.classList.remove('mic-active');
      break;

    default:
      _setFoxStateTo('idle');
  }
}

// ── Subtitle helpers ──────────────────────────────────────────────────────────
function _setSubtitle(txt) {
  if (_subtitleEl) _subtitleEl.textContent = txt;
}

function _clearSubtitleAnimations() {
  if (_subtitleInterval)  { clearInterval(_subtitleInterval);  _subtitleInterval = null; }
  if (_dotsInterval)      { clearInterval(_dotsInterval);      _dotsInterval = null; }
}

function _animateWordByWord(text) {
  const words = text.split(' ');
  let idx = 0;
  _setSubtitle('');
  _subtitleInterval = setInterval(() => {
    if (idx >= words.length) {
      clearInterval(_subtitleInterval);
      _subtitleInterval = null;
      return;
    }
    _subtitleEl.textContent += (idx > 0 ? ' ' : '') + words[idx];
    idx++;
  }, 120);
}

function _animateThinkingDots() {
  const base = 'Thinking';
  let count = 0;
  _setSubtitle(base + '...');
  _dotsInterval = setInterval(() => {
    count = (count + 1) % 4;
    const dots = '.'.repeat(count || 1);
    _setSubtitle(base + dots);
  }, 500);
}

// ── Fox scale oscillation (speaking state 1.0 ↔ 1.3 rhythm) ─────────────────
let _foxOscAngle = 0;

function _startFoxScaleLoop() {
  function loop() {
    _foxAnimFrame = requestAnimationFrame(loop);

    if (_foxState === 'speaking') {
      // Oscillate scale with sine wave
      _foxOscAngle += 0.045;
      const osc = 1.0 + 0.22 * Math.abs(Math.sin(_foxOscAngle));
      _foxImg.style.transform = `scale(${osc.toFixed(3)})`;

      // Oscillate glow intensity
      const glow = 0.6 + 0.4 * Math.abs(Math.sin(_foxOscAngle));
      _foxImg.style.filter = `drop-shadow(0 0 ${Math.round(glow * 48)}px rgba(255,107,0,${glow.toFixed(2)}))`;

    } else if (_foxState === 'thinking') {
      // Slowly rotate glow angle — achieved by rotating the corona ring
      _foxOscAngle += 0.008;
      const rotDeg = (_foxOscAngle * 57.3) % 360;
      _foxImg.style.transform = `scale(1)`;
      _foxImg.style.filter =
        `drop-shadow(0 0 18px rgba(255,107,0,0.5)) ` +
        `hue-rotate(${Math.round(rotDeg * 0.1)}deg)`;

    } else if (_foxState === 'listening') {
      _foxOscAngle += 0.03;
      const pulse = 1.0 + 0.06 * Math.abs(Math.sin(_foxOscAngle));
      _foxImg.style.transform = `scale(${pulse.toFixed(3)})`;
      _foxImg.style.filter = `drop-shadow(0 0 32px rgba(255,107,0,0.85))`;

    } else {
      // idle — gentle breathing
      _foxOscAngle += 0.01;
      const breathe = 1.0 + 0.025 * Math.abs(Math.sin(_foxOscAngle));
      _foxImg.style.transform = `scale(${breathe.toFixed(3)})`;
      _foxImg.style.filter = `drop-shadow(0 0 18px rgba(255,107,0,0.35))`;
    }
  }
  loop();
}

// ═══════════════════════════════════════════════════════════════════════════════
//  MATRIX RAIN
// ═══════════════════════════════════════════════════════════════════════════════
function _resizeMatrix() {
  if (!_matrixCanvas) return;
  _matrixCanvas.width  = window.innerWidth;
  _matrixCanvas.height = window.innerHeight;
  _matrixCtx = _matrixCanvas.getContext('2d');
  _initDrops();
}

function _initDrops() {
  if (!_matrixCanvas) return;
  const fontSize = 16;
  const cols = Math.floor(_matrixCanvas.width / fontSize);
  _matrixDrops = [];
  for (let i = 0; i < cols; i++) {
    _matrixDrops[i] = Math.random() * -(_matrixCanvas.height / fontSize);
  }
}

function _drawMatrixFrame() {
  const ctx = _matrixCtx;
  const w   = _matrixCanvas.width;
  const h   = _matrixCanvas.height;
  const fontSize = 16;

  // Fade trail — using opacity to create depth
  ctx.fillStyle = 'rgba(0,0,0,0.13)';
  ctx.fillRect(0, 0, w, h);

  ctx.font = `bold ${fontSize}px "JetBrains Mono", monospace`;

  for (let i = 0; i < _matrixDrops.length; i++) {
    const ch  = MATRIX_CHARS[Math.floor(Math.random() * MATRIX_CHARS.length)];
    const x   = i * fontSize;
    const y   = _matrixDrops[i] * fontSize;

    // Depth effect: leading char is bright, trail fades
    const depthFactor = 0.3 + 0.7 * Math.random();
    ctx.fillStyle = `rgba(255,107,0,${(depthFactor * 0.85).toFixed(2)})`;
    ctx.fillText(ch, x, y);

    // Reset drop when off screen
    if (y > h && Math.random() > (0.975 - _matrixSpeed * 0.01)) {
      _matrixDrops[i] = 0;
    }
    _matrixDrops[i] += 1;
  }
}

function _startMatrixRain() {
  if (_matrixInterval) clearInterval(_matrixInterval);

  // We drive animation from rAF for smoothness; use _matrixSpeed as frame skip counter
  let frameCount = 0;
  function rainLoop() {
    _matrixInterval = requestAnimationFrame(rainLoop);
    frameCount++;
    // Speed 1 = every frame, Speed 2 = every 2nd frame, Speed 3 = every frame (inverted — Speed 3 means fastest)
    // We'll invert: speed value 1 = slow (draw every 3 frames), 3 = fast (every 1 frame)
    const skipMod = Math.max(1, 4 - Math.round(_matrixSpeed));
    if (frameCount % skipMod === 0) {
      _drawMatrixFrame();
    }
  }
  rainLoop();
}

// ═══════════════════════════════════════════════════════════════════════════════
//  INPUT HANDLERS
// ═══════════════════════════════════════════════════════════════════════════════
let _isVoiceListening = false;
let _voiceRecognition = null;

function _onFoxClick() {
  _toggleVoiceListening();
}

function _onVoiceKeyDown(e) {
  // Only trigger Space when voice panel is active and no input focused
  if (e.code === 'Space' && document.activeElement === document.body) {
    const voicePanel = document.getElementById('voice-panel');
    if (voicePanel && !voicePanel.classList.contains('mode-panel--hidden')) {
      e.preventDefault();
      _toggleVoiceListening();
    }
  }
}

function _toggleVoiceListening() {
  if (_isVoiceListening) {
    _stopVoiceListening();
  } else {
    _startVoiceListening();
  }
}

function _startVoiceListening() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    _setSubtitle('Voice not supported in this browser.');
    return;
  }

  _voiceRecognition = new SR();
  _voiceRecognition.continuous = false;
  _voiceRecognition.interimResults = true;
  _voiceRecognition.lang = 'en-US';

  _voiceRecognition.onresult = (ev) => {
    const transcript = Array.from(ev.results).map(r => r[0].transcript).join('');
    _setSubtitle(transcript);
  };

  _voiceRecognition.onend = () => {
    _isVoiceListening = false;
    const finalText = _subtitleEl ? _subtitleEl.textContent : '';

    if (finalText && finalText !== 'Listening...') {
      _setFoxStateTo('thinking');
      // Forward to main WS chat if available
      if (_voiceWsRef && _voiceWsRef.readyState === WebSocket.OPEN) {
        _voiceWsRef.send(JSON.stringify({
          message: finalText,
          use_rag: true,
          session_id: 'voice_session'
        }));
      }
    } else {
      _setFoxStateTo('idle');
    }
  };

  _voiceRecognition.onerror = () => {
    _isVoiceListening = false;
    _setFoxStateTo('idle');
  };

  _isVoiceListening = true;
  _setFoxStateTo('listening');
  _voiceRecognition.start();
}

function _stopVoiceListening() {
  _isVoiceListening = false;
  if (_voiceRecognition) {
    _voiceRecognition.stop();
    _voiceRecognition = null;
  }
  _setFoxStateTo('idle');
}

// ── Handle WS responses for voice mode fox state updates ─────────────────────
function handleVoiceModeWsMessage(data) {
  if (data.type === 'fox_state') {
    _setFoxStateTo(data.state || 'idle', data.text || '');
    return true; // consumed
  }

  // token stream → show in subtitle during speaking state
  if (data.type === 'token' && _foxState === 'thinking') {
    _setFoxStateTo('speaking', '');
  }
  if (data.type === 'token' && _foxState === 'speaking') {
    if (data.content) {
      // append text to subtitle (strip markdown)
      const clean = data.content.replace(/[`*#_]/g, '').replace(/\n+/g, ' ');
      if (_subtitleEl) _subtitleEl.textContent += clean;
    }
    return true;
  }
  if (data.type === 'done' && _foxState === 'speaking') {
    // After 3s return to idle
    setTimeout(() => _setFoxStateTo('idle'), 3000);
    return true;
  }
  return false;
}

// ── Expose public API ─────────────────────────────────────────────────────────
window.NightionVoiceMode = {
  init: initVoiceMode,
  destroy: destroyVoiceMode,
  setState: setFoxState,
  handleWsMessage: handleVoiceModeWsMessage
};
