/**
 * Nexus App — Frontend Controller
 * Handles WebSocket chat, voice I/O, code runner, RAG
 */

// ── State ──────────────────────────────────────────────────────────────────
const WS_URL = `ws://${location.host}/ws/chat`;
const API = "/api";
let ws = null;
let isListening = false;
let recognition = null;
let synth = window.speechSynthesis;
let hasStartedChat = false;

// ── DOM Refs ────────────────────────────────────────────────────────────────
const messagesEl      = document.getElementById("messages");
const welcomeScreen   = document.getElementById("welcome-screen");
const chatInput       = document.getElementById("chat-input");
const btnSend         = document.getElementById("btn-send");
const btnVoice        = document.getElementById("btn-voice");
const btnLearn        = document.getElementById("btn-learn");
const learnInput      = document.getElementById("learn-input");
const learnSource     = document.getElementById("learn-source");
const learnStatus     = document.getElementById("learn-status");
const memoryCount     = document.getElementById("memory-count");
const btnRun          = document.getElementById("btn-run");
const codeInput       = document.getElementById("code-input");
const codeOutput      = document.getElementById("code-output");
const codeTimeout     = document.getElementById("code-timeout");
const ragToggle       = document.getElementById("rag-toggle");
const typingIndicator = document.getElementById("typing-indicator");
const speakingIndicator = document.getElementById("speaking-indicator");
const foxSpeakingLogo = document.getElementById("fox-speaking-container");
const btnStopSpeech   = document.getElementById("btn-stop-speech");
const statusDot       = document.getElementById("status-dot");
const statusText      = document.getElementById("status-text");

// Modals
const teachModal      = document.getElementById('teach-modal');
const runnerModal     = document.getElementById('runner-modal');
const statsModal      = document.getElementById('stats-modal');
const statsBody       = document.getElementById("stats-body");

const btnTeachModal   = document.getElementById('btn-teach-modal');
const btnRunModal     = document.getElementById('btn-run-modal');
const btnStatsModal   = document.getElementById('btn-stats');

document.getElementById('close-teach').addEventListener('click', () => teachModal.classList.add('hidden'));
document.getElementById('close-runner').addEventListener('click', () => runnerModal.classList.add('hidden'));
document.getElementById('close-stats').addEventListener('click', () => statsModal.classList.add('hidden'));

// Close modals when clicking outside
[teachModal, runnerModal, statsModal].forEach(m => {
  m.addEventListener('click', e => { if (e.target === m) m.classList.add('hidden'); });
});

btnTeachModal.addEventListener('click', () => teachModal.classList.remove('hidden'));
btnRunModal.addEventListener('click', () => runnerModal.classList.remove('hidden'));

const btnClearHistory = document.getElementById("btn-clear-history");
const btnClearMemory  = document.getElementById("btn-clear-memory");

// ── WebSocket ───────────────────────────────────────────────────────────────
btnStopSpeech.addEventListener("click", () => {
  if (synth) synth.cancel();
  if (speakingIndicator) speakingIndicator.classList.add("hidden");
  if (foxSpeakingLogo) foxSpeakingLogo.classList.remove("active-glow");
});

function connectWS() {
  ws = new WebSocket(WS_URL);
  
  ws.onopen = () => {
    setStatus("online", "Online");
    checkHealth();
  };
  
  ws.onclose = () => {
    setStatus("offline", "Reconnect...");
    setTimeout(connectWS, 3000);
  };
  
  ws.onerror = () => {
    setStatus("offline", "Error");
  };
  
  ws.onmessage = (e) => {
    const data = JSON.parse(e.data);
    
    if (data.type === "token") {
      appendToken(data.content);
    } else if (data.type === "done") {
      finalizeMessage(data.rag_used);
    } else if (data.type === "error") {
      finalizeMessage(false, "⚠️ Error: " + data.content);
    }
  };
}

// ── Status ──────────────────────────────────────────────────────────────────
function setStatus(state, text) {
  statusDot.className = "status-dot " + state;
  if(statusText) statusText.textContent = text;
}

async function checkHealth() {
  try {
    const r = await fetch(`${API}/health`);
    const d = await r.json();
    if (d.ollama === "online" && d.model_ready) {
      setStatus("online", "Ready");
    } else if (d.ollama === "online") {
      setStatus("warn", "Starting...");
    } else {
      setStatus("offline", "Offline");
    }
    updateMemoryCount();
  } catch {
    setStatus("offline", "Offline");
  }
}

// ── Message Rendering ───────────────────────────────────────────────────────
let currentBubble  = null;
let currentContent = "";

function switchToChatMode() {
  if (!hasStartedChat) {
    hasStartedChat = true;
    welcomeScreen.classList.add("hidden");
    messagesEl.classList.remove("hidden");
  }
}

function addMessage(role, content, ragUsed = false) {
  switchToChatMode();
  
  const isUser = role === "user";
  const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  
  const foxSvg = '<svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" width="100%" height="100%"><path d="M 60,150 C 20,100 40,40 85,60 L 95,30 L 110,60 C 110,60 130,55 140,75 C 160,85 170,100 180,110 C 160,100 140,95 120,90 C 110,110 80,120 60,150 Z" fill="#f97316"/><path d="M 115,100 C 95,120 95,150 145,150 C 125,160 85,160 95,130 C 95,130 105,120 115,100 Z" fill="#fafafa"/></svg>';
  
  const wrap = document.createElement("div");
  wrap.className = `message ${isUser ? "user-message" : "assistant-message"}`;
  wrap.innerHTML = `
    <div class="msg-avatar">${isUser ? "U" : foxSvg}</div>
    <div class="msg-body">
      <div class="msg-header">
        <span class="msg-name">${isUser ? "You" : "Nightion"}</span>
      </div>
      <div class="msg-content"></div>
    </div>
  `;
  
  const msgContent = wrap.querySelector(".msg-content");
  if (content) {
    msgContent.innerHTML = isUser ? escHtml(content) : renderMarkdown(content);
  }
  
  messagesEl.appendChild(wrap);
  scrollBottom();
  return msgContent;
}

function startStreaming() {
  currentContent = "";

  switchToChatMode();
  const foxSvg = '<svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" width="100%" height="100%"><path d="M 60,150 C 20,100 40,40 85,60 L 95,30 L 110,60 C 110,60 130,55 140,75 C 160,85 170,100 180,110 C 160,100 140,95 120,90 C 110,110 80,120 60,150 Z" fill="#f97316"/><path d="M 115,100 C 95,120 95,150 145,150 C 125,160 85,160 95,130 C 95,130 105,120 115,100 Z" fill="#fafafa"/></svg>';

  const wrap = document.createElement("div");
  wrap.className = "message assistant-message";
  wrap.innerHTML = `
    <div class="msg-avatar">${foxSvg}</div>
    <div class="msg-body" style="width:100%;max-width:85%">
      <div class="msg-header"><span class="msg-name">Nightion</span></div>
      <div class="msg-content"></div>
    </div>
  `;
  messagesEl.appendChild(wrap);

  currentBubble = wrap.querySelector(".msg-content");
  currentBubble.innerHTML = '<span class="stream-cursor">▋</span>';

  typingIndicator.classList.remove("hidden");
  btnSend.disabled = true;
  scrollBottom();
}

function appendToken(token) {
  currentContent += token;
  updateAnswerBubble();
  scrollBottom();
}



function updateAnswerBubble() {
  if (!currentBubble) return;
  if (currentContent) {
    currentBubble.innerHTML =
      '<span style="color:#fafafa;white-space:pre-wrap">' +
      escHtml(currentContent) + '</span>' +
      '<span class="stream-cursor">▋</span>';
  }
}

function finalizeMessage(ragUsed, errorText) {
  typingIndicator.classList.add("hidden");
  btnSend.disabled = false;

  if (errorText && currentBubble) {
    currentBubble.innerHTML = renderMarkdown(errorText);
  }

  if (currentBubble) {
    currentBubble.innerHTML = renderMarkdown(currentContent);
    highlightCode(currentBubble);
    addCopyButtons(currentBubble);

    // Voice: skip code blocks
    let spokenText = currentContent.replace(/```[\s\S]*?```/g, " ");
    spokenText = spokenText.replace(/`([^`]+)`/g, "$1");
    spokenText = spokenText.replace(/[#*~_]/g, "").replace(/\n+/g, " ").trim();
    if (spokenText.length > 0) speak(spokenText);
  }

  currentBubble = null;
  currentContent = "";
  scrollBottom();
}

// ── Markdown Renderer ───────────────────────────────────────────────────────
function renderMarkdown(text) {
  text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    return `<pre><code class="language-${lang || "plaintext"}">${escHtml(code.trim())}</code></pre>`;
  });
  text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
  text = text.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  text = text.replace(/\*(.+?)\*/g, '<em>$1</em>');
  text = text.replace(/^### (.+)$/gm, '<strong style="font-size:1.1em;color:var(--accent)">$1</strong>');
  text = text.replace(/^## (.+)$/gm, '<strong style="font-size:1.15em;color:var(--accent)">$1</strong>');
  text = text.replace(/^# (.+)$/gm, '<strong style="font-size:1.2em;color:var(--accent)">$1</strong>');
  text = text.replace(/^\s*[-*] (.+)$/gm, '<li>$1</li>');
  text = text.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
  text = text.replace(/\n{2,}/g, '</p><p>');
  text = `<p>${text}</p>`;
  text = text.replace(/<p><\/p>/g, '');
  return text;
}

function escHtml(t) { return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function highlightCode(el) { el.querySelectorAll("pre code").forEach(block => { hljs.highlightElement(block); }); }

function addCopyButtons(el) {
  el.querySelectorAll("pre").forEach(pre => {
    if (pre.querySelector(".copy-btn")) return;
    const btn = document.createElement("button");
    btn.className = "copy-btn";
    btn.textContent = "Copy";
    btn.onclick = () => {
      const code = pre.querySelector("code")?.innerText || "";
      navigator.clipboard.writeText(code).then(() => {
        btn.textContent = "✓ Copied!";
        setTimeout(() => btn.textContent = "Copy", 2000);
      });
    };
    pre.style.position = "relative";
    pre.appendChild(btn);
  });
}

function scrollBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// ── Send Message ─────────────────────────────────────────────────────────────
function sendMessage() {
  const text = chatInput.value.trim();
  if (!text || btnSend.disabled) return;
  
  addMessage("user", text);
  chatInput.value = "";
  autoResize(chatInput);
  
  if (ws && ws.readyState === WebSocket.OPEN) {
    startStreaming();
    ws.send(JSON.stringify({
      message: text,
      use_rag: ragToggle.checked
    }));
  } else {
    addMessage("assistant", "⚠️ Not connected to server. Make sure `server.py` is running.");
  }
}

btnSend.addEventListener("click", sendMessage);
chatInput.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});
chatInput.addEventListener("input", () => autoResize(chatInput));

function autoResize(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 150) + "px";
}

// ── Voice Input ──────────────────────────────────────────────────────────────
function initVoice() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    btnVoice.title = "Voice not supported";
    btnVoice.style.opacity = "0.4";
    return;
  }
  recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.lang = "en-US";
  
  recognition.onresult = (e) => {
    const transcript = Array.from(e.results).map(r => r[0].transcript).join("");
    chatInput.value = transcript;
    autoResize(chatInput);
  };
  recognition.onend = () => {
    isListening = false;
    btnVoice.classList.remove("listening");
    if (chatInput.value.trim()) sendMessage();
  };
  recognition.onerror = () => {
    isListening = false;
    btnVoice.classList.remove("listening");
  };
}

btnVoice.addEventListener("click", () => {
  if (synth) synth.cancel(); // 🛑 Instantly stop AI from talking
  if (speakingIndicator) speakingIndicator.classList.add("hidden");
  if (foxSpeakingLogo) foxSpeakingLogo.classList.remove("active-glow");
  if (!recognition) return;
  
  if (isListening) {
    recognition.stop();
  } else {
    chatInput.value = "";
    isListening = true;
    btnVoice.classList.add("listening");
    recognition.start();
  }
});

function speak(text) {
  if (!synth) return;
  synth.cancel();
  const utt = new SpeechSynthesisUtterance(text);
  
  const voices = synth.getVoices();
  const preferred = ["Zira", "Hazel", "Samantha", "Google UK English Female", "Female", "Woman"];
  let selectedVoice = null;
  for (let name of preferred) {
    selectedVoice = voices.find(v => v.name.toLowerCase().includes(name.toLowerCase()));
    if (selectedVoice) break;
  }
  if (selectedVoice) utt.voice = selectedVoice;
  
  utt.rate = 0.9; 
  utt.pitch = 1.0; 
  utt.volume = 0.8;

  utt.onstart = () => { 
    if (speakingIndicator) speakingIndicator.classList.remove("hidden"); 
    if (foxSpeakingLogo) foxSpeakingLogo.classList.add("active-glow");
  };
  utt.onend = () => { 
    if (speakingIndicator) speakingIndicator.classList.add("hidden"); 
    if (foxSpeakingLogo) foxSpeakingLogo.classList.remove("active-glow");
  };
  utt.onerror = () => { 
    if (speakingIndicator) speakingIndicator.classList.add("hidden"); 
    if (foxSpeakingLogo) foxSpeakingLogo.classList.remove("active-glow");
  };
  
  window.currentUtt = utt; // Prevent garbage collection bug in Chrome
  synth.speak(utt);
}

// ── Teach (Memory) ─────────────────────────────────────────────────────────
btnLearn.addEventListener("click", async () => {
  const text = learnInput.value.trim();
  if (!text) return;
  
  btnLearn.textContent = "⏳...";
  btnLearn.disabled = true;
  
  try {
    const r = await fetch(`${API}/learn`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ text, source: learnSource.value.trim() || "user" })
    });
    const d = await r.json();
    
    if (d.success) {
      learnStatus.textContent = d.message;
      learnInput.value = "";
      learnSource.value = "";
      memoryCount.textContent = d.total_knowledge;
    }
  } catch (e) {
    learnStatus.textContent = "❌ Server error.";
  } finally {
    btnLearn.textContent = "TEACH";
    btnLearn.disabled = false;
    learnStatus.classList.remove("hidden");
    setTimeout(() => learnStatus.classList.add("hidden"), 5000);
  }
});

// ── Code Runner ─────────────────────────────────────────────────────────────
btnRun.addEventListener("click", async () => {
  const code = codeInput.value.trim();
  if (!code) return;
  
  btnRun.textContent = "⏳...";
  btnRun.disabled = true;
  codeOutput.className = "code-output";
  codeOutput.textContent = "Executing...";
  codeOutput.classList.remove("hidden");
  
  try {
    const r = await fetch(`${API}/execute`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ code, timeout: parseInt(codeTimeout.value) || 10 })
    });
    const d = await r.json();
    
    if (d.success) {
      codeOutput.className = "code-output success";
      codeOutput.textContent = d.stdout || "(no output)";
    } else {
      codeOutput.className = "code-output error";
      codeOutput.textContent = d.error || d.stderr || d.stdout || "Unknown error";
    }
    if (d.duration) codeOutput.textContent += `\n\n[⏱️ ${d.duration}s]`;
  } catch (e) {
    codeOutput.className = "code-output error";
    codeOutput.textContent = "❌ Sever error.";
  } finally {
    btnRun.textContent = "RUN CODE";
    btnRun.disabled = false;
  }
});

// ── Stats Modal ──────────────────────────────────────────────────────────────
btnStatsModal.addEventListener("click", async () => {
  statsModal.classList.remove("hidden");
  statsBody.innerHTML = "Loading...";
  try {
    const [statsR, healthR] = await Promise.all([
      fetch(`${API}/stats`).then(r => r.json()),
      fetch(`${API}/health`).then(r => r.json())
    ]);
    statsBody.innerHTML = `
      <div class="stat-row"><span>Model</span><strong>${statsR.model}</strong></div>
      <div class="stat-row"><span>Status</span><strong style="color:${healthR.ollama==='online'?'#22c55e':'#ef4444'}">${healthR.ollama}</strong></div>
      <div class="stat-row"><span>Memory Chunks</span><strong>${statsR.rag_stats.total_chunks}</strong></div>
      <div class="stat-row"><span>Conversations</span><strong>${statsR.conversation_turns}</strong></div>
    `;
  } catch {
    statsBody.innerHTML = "❌ Could not load stats.";
  }
});

// ── Clear Buttons ─────────────────────────────────────────────────────────
btnClearHistory.addEventListener("click", async () => {
  if (!confirm("Clear chat?")) return;
  await fetch(`${API}/history`, { method: "DELETE" });
  messagesEl.innerHTML = "";
  hasStartedChat = false;
  welcomeScreen.classList.remove("hidden");
  messagesEl.classList.add("hidden");
});

btnClearMemory.addEventListener("click", async () => {
  if (!confirm("Wipe ALL memory?")) return;
  await fetch(`${API}/memory`, { method: "DELETE" });
  memoryCount.textContent = "0";
  teachModal.classList.add("hidden");
});

// ── Memory Count ─────────────────────────────────────────────────────────
async function updateMemoryCount() {
  try {
    const r = await fetch(`${API}/stats`);
    const d = await r.json();
    memoryCount.textContent = d.rag_stats.total_chunks;
  } catch {}
}

// ── Init ──────────────────────────────────────────────────────────────────
initVoice();
connectWS();

setInterval(checkHealth, 15000);

// ── Hovering Matrix Speaking Visualizer ──────────────────────────────────────
// Start background matrix animation
createMatrixFox('fox-speaking-canvas', 120, 12);

// ── Matrix Fox Logo ─────────────────────────────────────────────────────────
function createMatrixFox(canvasId, resolution, fontSize) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  
  canvas.width = resolution;
  canvas.height = resolution;
  
  const chars = '0123456789'.split('');
  const columns = canvas.width / fontSize;
  const drops = [];
  for (let x = 0; x < columns; x++) drops[x] = Math.random() * -50; 
  
  function drawMatrix() {
    ctx.fillStyle = 'rgba(0, 0, 0, 0.15)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    ctx.fillStyle = '#f97316'; // Orange var(--accent)
    ctx.font = 'bold ' + fontSize + 'px "JetBrains Mono", monospace';
    
    for (let i = 0; i < drops.length; i++) {
      const text = chars[Math.floor(Math.random() * chars.length)];
      ctx.fillText(text, i * fontSize, drops[i] * fontSize);
      if (drops[i] * fontSize > canvas.height && Math.random() > 0.95) drops[i] = 0;
      drops[i]++;
    }
  }
  
  setInterval(drawMatrix, 50);
}

// Initialize Animated Logos
createMatrixFox('center-fox-canvas', 200, 16);
createMatrixFox('fox-canvas', 100, 12);
