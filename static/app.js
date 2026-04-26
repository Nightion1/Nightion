/**
 * Nightion App — Frontend Controller
 * gemma4 offline model, streaming WebSocket chat
 * Features: real-time live <think> blocks (auto-collapse after output), syntax-highlighted code with copy
 */

// ── State ──────────────────────────────────────────────────────────────────
const WS_URL = `ws://${location.host}/ws/chat`;
const API = "/api";
let ws = null;
let isConnected = false;
let isListening = false;
let recognition = null;
let synth = window.speechSynthesis;
let hasStartedChat = false;
const SESSION_ID = "default_session";

// ── DOM Refs ────────────────────────────────────────────────────────────────
const messagesEl        = document.getElementById("messages");
const welcomeScreen     = document.getElementById("welcome-screen");
const chatInput         = document.getElementById("chat-input");
const btnSend           = document.getElementById("btn-send");
const btnVoice          = document.getElementById("btn-voice");
const memoryCount       = document.getElementById("memory-count");
const btnRun            = document.getElementById("btn-run");
const codeInput         = document.getElementById("code-input");
const codeOutput        = document.getElementById("code-output");
const codeTimeout       = document.getElementById("code-timeout");
const ragToggle         = document.getElementById("rag-toggle");
const typingIndicator   = document.getElementById("typing-indicator");
const speakingIndicator = document.getElementById("speaking-indicator");
const foxSpeakingLogo   = document.getElementById("fox-speaking-container");
const btnStopSpeech     = document.getElementById("btn-stop-speech");
const statusDot         = document.getElementById("status-dot");
const statusText        = document.getElementById("status-text");

// Modals
const runnerModal   = document.getElementById('runner-modal');
const statsModal    = document.getElementById('stats-modal');
const statsBody     = document.getElementById("stats-body");
const tracesModal   = document.getElementById('traces-modal');
const tracesList    = document.getElementById('traces-list');
const traceViewer   = document.getElementById('trace-viewer');
const btnRunModal   = document.getElementById('btn-run-modal');
const btnStatsModal = document.getElementById('btn-stats');
const btnTracesModal= document.getElementById('btn-traces-modal');

document.getElementById('close-runner').addEventListener('click', () => runnerModal.classList.add('hidden'));
document.getElementById('close-stats').addEventListener('click',  () => statsModal.classList.add('hidden'));
document.getElementById('close-traces').addEventListener('click', () => tracesModal.classList.add('hidden'));

[runnerModal, statsModal, tracesModal].forEach(m => {
  m.addEventListener('click', e => { if (e.target === m) m.classList.add('hidden'); });
});

btnRunModal.addEventListener('click', () => runnerModal.classList.remove('hidden'));
btnTracesModal.addEventListener('click', async () => {
  tracesModal.classList.remove('hidden');
  await loadTracesList();
});

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
    isConnected = true;
    setStatus("online", "Online");
    checkHealth();
  };

  ws.onclose = () => {
    isConnected = false;
    setStatus("offline", "Reconnecting...");
    setTimeout(connectWS, 3000);
  };

  ws.onerror = () => {
    isConnected = false;
    setStatus("offline", "Error");
  };

  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);

      if (data.type === 'think_token') {
        // Live reasoning token — stream into the thinking block
        appendThinkToken(data.content || '');
      } else if (data.type === 'token') {
        // Live response token — preserve ALL whitespace (spaces, newlines)
        const content = data.content || '';
        appendToken(content);
      } else if (data.type === 'done') {
        finalizeMessage(data.rag_used, null, data.trace_id);
      } else if (data.type === 'error') {
        finalizeMessage(false, '⚠️ ' + (data.content || 'Unknown error'));
      }
    } catch (err) {
      console.error('[WS] Parse error:', err, e.data);
    }
  };
}

// ── Status ──────────────────────────────────────────────────────────────────
function setStatus(state, text) {
  if (statusDot) statusDot.className = "status-dot " + state;
  if (statusText) statusText.textContent = text;
}

async function checkHealth() {
  try {
    const r = await fetch(`${API}/health`);
    const d = await r.json();
    if (d.ollama === "online" && d.model_ready) {
      setStatus("online", `Ready · ${d.model || 'gemma4'}`);
    } else {
      setStatus("offline", "Ollama Offline");
    }
    updateMemoryCount();
  } catch {
    setStatus("offline", "Server Offline");
  }
}

// ── Message State ─────────────────────────────────────────────
let currentBubble     = null;  // .msg-content div for current assistant message
let currentContent    = "";   // accumulated full text (think + response)
let thinkContent      = "";   // accumulated think text
let responseContent   = "";   // accumulated response text
let thinkBlockEl      = null;  // live .think-block element shown during reasoning
let thinkBodyEl       = null;  // .think-body inside that block
let responseEl        = null;  // span holding live response tokens

function switchToChatMode() {
  if (!hasStartedChat) {
    hasStartedChat = true;
    welcomeScreen.classList.add("hidden");
    messagesEl.classList.remove("hidden");
  }
}

// ── Message Rendering ───────────────────────────────────────────────────────
const FOX_SVG = `<svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" width="100%" height="100%">
  <path d="M 60,150 C 20,100 40,40 85,60 L 95,30 L 110,60 C 110,60 130,55 140,75 C 160,85 170,100 180,110 C 160,100 140,95 120,90 C 110,110 80,120 60,150 Z" fill="#f97316"/>
  <path d="M 115,100 C 95,120 95,150 145,150 C 125,160 85,160 95,130 C 95,130 105,120 115,100 Z" fill="#fafafa"/>
</svg>`;

function addMessage(role, content, ragUsed = false) {
  switchToChatMode();
  const isUser = role === "user";
  const wrap = document.createElement("div");
  wrap.className = `message ${isUser ? "user-message" : "assistant-message"}`;
  wrap.innerHTML = `
    <div class="msg-avatar">${isUser ? "U" : FOX_SVG}</div>
    <div class="msg-body">
      <div class="msg-header"><span class="msg-name">${isUser ? "You" : "Nightion · gemma4"}</span></div>
      <div class="msg-content"></div>
    </div>
  `;
  const msgContent = wrap.querySelector(".msg-content");
  if (content) {
    msgContent.innerHTML = isUser ? escHtml(content) : renderMarkdown(content);
    if (!isUser) {
      highlightCode(msgContent);
      addCopyButtons(msgContent);
    }
  }
  messagesEl.appendChild(wrap);
  scrollBottom();
  return msgContent;
}

function startStreaming() {
  currentContent    = "";
  thinkContent      = "";
  responseContent   = "";
  thinkBlockEl      = null;
  thinkBodyEl       = null;
  responseEl        = null;
  switchToChatMode();

  const wrap = document.createElement("div");
  wrap.className = "message assistant-message";
  wrap.innerHTML = `
    <div class="msg-avatar">${FOX_SVG}</div>
    <div class="msg-body">
      <div class="msg-header">
        <span class="msg-name">Nightion · gemma4</span>
      </div>
      <div class="msg-content"><span class="stream-cursor">▋</span></div>
    </div>
  `;
  messagesEl.appendChild(wrap);
  currentBubble = wrap.querySelector(".msg-content");

  typingIndicator.classList.remove("hidden");
  btnSend.disabled = true;
  scrollBottom();
}

// Append a live reasoning token — shows a thinking block in real-time
function appendThinkToken(token) {
  thinkContent += token;
  currentContent += token;

  if (!thinkBlockEl && currentBubble) {
    // Create the live think block (starts expanded with spinner)
    thinkBlockEl = document.createElement("div");
    thinkBlockEl.className = "think-block think-live";
    thinkBlockEl.innerHTML = `
      <div class="think-header">
        <span class="think-icon">⚡</span>
        <span class="think-label">Reasoning…</span>
        <span class="think-chevron">▴</span>
      </div>
      <div class="think-body"></div>
    `;
    thinkBodyEl = thinkBlockEl.querySelector(".think-body");

    // Remove the initial cursor and insert think block
    currentBubble.innerHTML = "";
    currentBubble.appendChild(thinkBlockEl);
  }

  if (thinkBodyEl) {
    thinkBodyEl.textContent = thinkContent;  // plain text inside think block
    thinkBodyEl.scrollTop = thinkBodyEl.scrollHeight;
  }
  scrollBottom();
}

// ── Live Markdown Streaming (GPT/Claude-style) ──────────────────────────────
// Debounce timer for syntax highlighting during streaming
let _hlDebounce = null;

function appendToken(token) {
  responseContent += token;
  currentContent  += token;

  if (!currentBubble) return;

  // Ensure response container element exists
  if (!responseEl) {
    responseEl = document.createElement("div");
    responseEl.className = "stream-response final-response";
    currentBubble.appendChild(responseEl);
  }

  // Remove streaming cursor from think block if it's still there
  const oldCursor = currentBubble.querySelector(".stream-cursor");
  if (oldCursor) oldCursor.remove();

  // ── Live markdown render — progressively render as tokens arrive ──
  // This gives the GPT/Claude "typing with formatting" look
  responseEl.innerHTML =
    renderMarkdown(responseContent) +
    `<span class="stream-cursor">▋</span>`;

  // Debounced syntax highlighting — every 400ms during streaming
  clearTimeout(_hlDebounce);
  _hlDebounce = setTimeout(() => {
    highlightCode(responseEl);
  }, 400);

  scrollBottom();
}

function finalizeMessage(ragUsed, errorText, traceId) {
  typingIndicator.classList.add("hidden");
  btnSend.disabled = false;
  clearTimeout(_hlDebounce);

  if (!currentBubble) return;

  if (errorText) {
    currentBubble.innerHTML = `<span style="color:#ef4444">${escHtml(errorText)}</span>`;
    currentBubble = null;
    currentContent = "";
    thinkContent = "";
    responseContent = "";
    scrollBottom();
    return;
  }

  // ── Collapse the live reasoning block ─────────────────────────
  // Capture a LOCAL reference to the DOM element before nulling the module var.
  // This way the click handler's closure still works after finalizeMessage resets state.
  const thinkBlock = thinkBlockEl;
  if (thinkBlock) {
    thinkBlock.classList.remove("think-live");
    thinkBlock.classList.add("collapsed");

    const hdr = thinkBlock.querySelector(".think-header");
    if (hdr) {
      hdr.innerHTML = `
        <span class="think-icon think-done-icon">💡</span>
        <span class="think-label">Reasoning complete</span>
        <span class="think-hint">(click ▴ to expand)</span>
        <span class="think-chevron">▾</span>
      `;

      // Toggle expand/collapse on HEADER click — uses local `thinkBlock` ref
      hdr.addEventListener("click", (e) => {
        e.stopPropagation();
        thinkBlock.classList.toggle("collapsed");
        const chevron = thinkBlock.querySelector(".think-chevron");
        const hint    = thinkBlock.querySelector(".think-hint");
        if (thinkBlock.classList.contains("collapsed")) {
          if (chevron) chevron.textContent = "▾";
          if (hint)    hint.textContent = "(click ▴ to expand)";
        } else {
          if (chevron) chevron.textContent = "▴";
          if (hint)    hint.textContent = "(click ▾ to collapse)";
        }
      });
    }
  }

  // ── Final render — full markdown with syntax highlighting + copy buttons ──
  if (responseEl) {
    responseEl.remove();
    responseEl = null;
  }
  const cursor = currentBubble.querySelector(".stream-cursor");
  if (cursor) cursor.remove();

  const finalEl = document.createElement("div");
  finalEl.className = "final-response";
  finalEl.innerHTML = renderMarkdown(responseContent || currentContent);
  currentBubble.appendChild(finalEl);
  highlightCode(finalEl);
  addCopyButtons(finalEl);

  if (traceId) {
    const traceLink = document.createElement("div");
    traceLink.className = "trace-link-pin";
    traceLink.style.cssText = "margin-top:8px;font-size:0.82rem;";
    traceLink.innerHTML = `<a href="javascript:void(0)" onclick="openTraceModal('${traceId}')" style="color:var(--accent);text-decoration:none;">[🔍 View Trace]</a>`;
    currentBubble.parentNode.appendChild(traceLink);
  }

  // Voice: skip code and think blocks
  let spokenText = (responseContent || currentContent)
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/<think>[\s\S]*?<\/think>/g, " ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/[#*~_]/g, "")
    .replace(/\n+/g, " ")
    .trim();
  if (spokenText.length > 0) speak(spokenText);

  currentBubble   = null;
  currentContent  = "";
  thinkContent    = "";
  responseContent = "";
  thinkBlockEl    = null;
  thinkBodyEl     = null;
  responseEl      = null;
  scrollBottom();
}

// ── Markdown Renderer ───────────────────────────────────────────────────────
function renderMarkdown(text) {
  if (!text) return "";

  // 1. Extract <think> blocks FIRST and replace with placeholders
  const thinkBlocks = [];
  text = text.replace(/<think>\s*([\s\S]*?)\s*<\/think>/g, (_, content) => {
    thinkBlocks.push(content.trim());
    return `%%THINK_${thinkBlocks.length - 1}%%`;
  });
  // Handle unclosed <think>
  text = text.replace(/<think>\s*([\s\S]*)$/, (_, content) => {
    thinkBlocks.push(content.trim());
    return `%%THINK_${thinkBlocks.length - 1}%%`;
  });

  // 2. Extract fenced code blocks into placeholders BEFORE any newline processing
  //    This prevents steps 9/10 from destroying newlines inside <pre> tags.
  const codeBlocks = [];
  text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const safeCode = escHtml(code.trim());
    const langClass = lang ? `language-${lang}` : "language-plaintext";
    codeBlocks.push(`<pre class="code-block-wrap"><code class="${langClass}">${safeCode}</code></pre>`);
    return `%%CODE_${codeBlocks.length - 1}%%`;
  });

  // 3. Inline code
  text = text.replace(/`([^`\n]+)`/g, '<code class="inline-code">$1</code>');

  // 4. Bold / italic
  text = text.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  text = text.replace(/\*(.+?)\*/g, '<em>$1</em>');

  // 5. Headings
  text = text.replace(/^### (.+)$/gm, '<h3 class="md-h3">$1</h3>');
  text = text.replace(/^## (.+)$/gm,  '<h2 class="md-h2">$1</h2>');
  text = text.replace(/^# (.+)$/gm,   '<h1 class="md-h1">$1</h1>');

  // 6. Bullet lists
  text = text.replace(/^[\s]*[-*] (.+)$/gm, '<li>$1</li>');
  text = text.replace(/(<li>.*<\/li>(\n|$))+/gs, '<ul class="md-ul">$&</ul>');

  // 7. Numbered lists
  text = text.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

  // 8. Horizontal rules
  text = text.replace(/^---+$/gm, '<hr class="md-hr">');

  // 9. Paragraphs (double newline → paragraph break)
  text = text.replace(/\n{2,}/g, '</p><p>');
  text = `<p>${text}</p>`;

  // 10. Single newlines → <br> inside paragraphs
  text = text.replace(/([^>])\n([^<])/g, '$1<br>$2');

  // 11. Re-inject think blocks as collapsible <details>
  thinkBlocks.forEach((tb, i) => {
    const tbHtml = escHtml(tb);
    const details = `</p>
<details class="think-block">
  <summary class="think-summary">^ Reasoning <span class="think-hint">(click to expand)</span></summary>
  <div class="think-content">${tbHtml}</div>
</details>
<p>`;
    text = text.replace(`%%THINK_${i}%%`, details);
  });

  // 12. Re-inject code blocks (newlines are safely preserved inside placeholders)
  codeBlocks.forEach((cb, i) => {
    text = text.replace(`%%CODE_${i}%%`, `</p>${cb}<p>`);
  });

  // 13. Clean up empty paragraphs
  text = text.replace(/<p>\s*<\/p>/g, '');
  text = text.replace(/<p>(<(?:details|pre|h[123]|ul|hr)[^>]*>)/g, '$1');
  text = text.replace(/(<\/(?:details|pre|h[123]|ul|hr)>)<\/p>/g, '$1');

  return text;
}

function escHtml(t) {
  if (!t) return "";
  return t
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function highlightCode(el) {
  if (typeof hljs === "undefined") return;
  el.querySelectorAll("pre code").forEach(block => {
    try { hljs.highlightElement(block); } catch(e) {}
  });
}

function addCopyButtons(el) {
  el.querySelectorAll("pre.code-block-wrap").forEach(pre => {
    if (pre.querySelector(".copy-btn")) return;
    const btn = document.createElement("button");
    btn.className = "copy-btn";
    btn.textContent = "Copy";
    btn.onclick = () => {
      const code = pre.querySelector("code")?.innerText || "";
      navigator.clipboard.writeText(code).then(() => {
        btn.textContent = "✓ Copied!";
        btn.style.color = "#22c55e";
        setTimeout(() => {
          btn.textContent = "Copy";
          btn.style.color = "";
        }, 2000);
      }).catch(() => {
        // Fallback for non-secure context
        const ta = document.createElement("textarea");
        ta.value = code;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        btn.textContent = "✓ Copied!";
        setTimeout(() => btn.textContent = "Copy", 2000);
      });
    };
    pre.style.position = "relative";
    pre.appendChild(btn);
  });
}

function scrollBottom() {
  requestAnimationFrame(() => {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  });
}

// ── Send Message ─────────────────────────────────────────────────────────────
function sendMessage() {
  const text = chatInput.value.trim();
  if (!text || btnSend.disabled) return;
  if (!isConnected || !ws || ws.readyState !== WebSocket.OPEN) {
    addMessage("assistant", "⚠️ Not connected to server. Make sure Nightion is running and Ollama is started (`ollama serve`).");
    return;
  }

  addMessage("user", text);
  chatInput.value = "";
  autoResize(chatInput);
  startStreaming();

  ws.send(JSON.stringify({
    message: text,
    use_rag: ragToggle ? ragToggle.checked : false,
    session_id: SESSION_ID,
  }));
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
    if (btnVoice) { btnVoice.title = "Voice not supported"; btnVoice.style.opacity = "0.4"; }
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
    if (btnVoice) btnVoice.classList.remove("listening");
    if (chatInput.value.trim()) sendMessage();
  };
  recognition.onerror = () => {
    isListening = false;
    if (btnVoice) btnVoice.classList.remove("listening");
  };
}

if (btnVoice) {
  btnVoice.addEventListener("click", () => {
    if (synth) synth.cancel();
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
}

function speak(text) {
  if (!synth) return;
  synth.cancel();
  const utt = new SpeechSynthesisUtterance(text);
  const voices = synth.getVoices();
  const preferred = ["Zira", "Hazel", "Samantha", "Google UK English Female"];
  let selectedVoice = null;
  for (let name of preferred) {
    selectedVoice = voices.find(v => v.name.toLowerCase().includes(name.toLowerCase()));
    if (selectedVoice) break;
  }
  if (selectedVoice) utt.voice = selectedVoice;
  utt.rate = 0.9; utt.pitch = 1.0; utt.volume = 0.8;

  utt.onstart = () => {
    if (speakingIndicator) speakingIndicator.classList.remove("hidden");
    if (foxSpeakingLogo) foxSpeakingLogo.classList.add("active-glow");
  };
  utt.onend = () => {
    if (speakingIndicator) speakingIndicator.classList.add("hidden");
    if (foxSpeakingLogo) foxSpeakingLogo.classList.remove("active-glow");
  };
  utt.onerror = utt.onend;
  window.currentUtt = utt;
  synth.speak(utt);
}

// ── Code Runner ─────────────────────────────────────────────────────────────
if (btnRun) {
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
        body: JSON.stringify({ code, timeout: parseInt(codeTimeout.value) || 10 }),
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
      codeOutput.textContent = "❌ Server error.";
    } finally {
      btnRun.textContent = "RUN CODE";
      btnRun.disabled = false;
    }
  });
}

// ── Stats Modal ──────────────────────────────────────────────────────────────
if (btnStatsModal) {
  btnStatsModal.addEventListener("click", async () => {
    statsModal.classList.remove("hidden");
    statsBody.innerHTML = "Loading...";
    try {
      const [statsR, healthR] = await Promise.all([
        fetch(`${API}/stats`).then(r => r.json()),
        fetch(`${API}/health`).then(r => r.json()),
      ]);
      statsBody.innerHTML = `
        <div class="stat-row"><span>Model</span><strong>${statsR.model}</strong></div>
        <div class="stat-row"><span>Ollama</span><strong style="color:${healthR.ollama==='online'?'#22c55e':'#ef4444'}">${healthR.ollama}</strong></div>
        <div class="stat-row"><span>Mode</span><strong>Offline Only</strong></div>
        <div class="stat-row"><span>Internet</span><strong style="color:#a1a1aa">Disabled</strong></div>
      `;
    } catch {
      statsBody.innerHTML = "❌ Could not load stats.";
    }
  });
}

// ── Clear Buttons ─────────────────────────────────────────────────────────
if (btnClearHistory) {
  btnClearHistory.addEventListener("click", async () => {
    await fetch(`${API}/history`, { method: "DELETE" });
    messagesEl.innerHTML = "";
    hasStartedChat = false;
    welcomeScreen.classList.remove("hidden");
    messagesEl.classList.add("hidden");
    currentBubble = null;
    currentContent = "";
  });
}

// ── Memory Count ─────────────────────────────────────────────────────────
async function updateMemoryCount() {
  try {
    const r = await fetch(`${API}/stats`);
    const d = await r.json();
    if (memoryCount) memoryCount.textContent = d.rag_stats?.total_chunks ?? 0;
  } catch {}
}

// ── Telemetry (XAI) ─────────────────────────────────────────────────────────
async function loadTracesList() {
  if (!tracesList) return;
  tracesList.innerHTML = "Loading trace logs...";
  try {
    const res = await fetch('/api/traces');
    const traces = await res.json();
    if (!traces.length) {
      tracesList.innerHTML = "<div style='color:#a1a1aa;font-size:12px;padding:10px;'>No logs yet.</div>";
      return;
    }
    tracesList.innerHTML = "";
    traces.forEach(t => {
      const d = document.createElement("div");
      d.className = "trace-item";
      d.textContent = "Trace " + t.substring(0, 10) + "...";
      d.onclick = () => {
        document.querySelectorAll('.trace-item').forEach(el => el.classList.remove('active'));
        d.classList.add('active');
        viewTrace(t);
      };
      tracesList.appendChild(d);
    });
  } catch(e) { tracesList.innerHTML = "Error loading traces."; }
}

async function viewTrace(id) {
  if (!traceViewer) return;
  traceViewer.innerHTML = "Loading...";
  try {
    const res = await fetch(`/api/traces/${id}`);
    const data = await res.json();
    let html = `<div class="timeline-node">
      <div class="timeline-dot"></div>
      <div class="timeline-title">1. Query</div>
      <div class="timeline-content">${escHtml(data.query)}</div>
    </div>`;
    if (data.final_response?.status) {
      html += `<div class="timeline-node">
        <div class="timeline-dot"></div>
        <div class="timeline-title">2. Response (${data.final_response.status})</div>
        <div class="timeline-content">${escHtml(String(data.final_response.result || "").substring(0, 400))}...</div>
      </div>`;
    }
    traceViewer.innerHTML = html;
  } catch(e) { traceViewer.innerHTML = "Error loading trace."; }
}

function openTraceModal(trace_id) {
  if (tracesModal) tracesModal.classList.remove('hidden');
  viewTrace(trace_id);
}

async function fetchSessionHistory() {
  try {
    const res = await fetch(`/api/session/history?session_id=${SESSION_ID}`);
    const history = await res.json();
    if (history && history.length > 0) {
      welcomeScreen.classList.add("hidden");
      messagesEl.classList.remove("hidden");
      hasStartedChat = true;
      history.forEach(msg => addMessage(msg.role, msg.content));
    }
  } catch (e) {
    console.error("Failed fetching session history:", e);
  }
}

// ── Matrix Fox Canvas ────────────────────────────────────────────────────────
function createMatrixFox(canvasId, resolution, fontSize) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  canvas.width = resolution;
  canvas.height = resolution;
  const chars = '01'.split('');
  const columns = Math.floor(canvas.width / fontSize);
  const drops = Array.from({length: columns}, () => Math.random() * -50);
  function drawMatrix() {
    ctx.fillStyle = 'rgba(0,0,0,0.15)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#f97316';
    ctx.font = `bold ${fontSize}px "JetBrains Mono", monospace`;
    for (let i = 0; i < drops.length; i++) {
      ctx.fillText(chars[Math.floor(Math.random() * chars.length)], i * fontSize, drops[i] * fontSize);
      if (drops[i] * fontSize > canvas.height && Math.random() > 0.95) drops[i] = 0;
      drops[i]++;
    }
  }
  setInterval(drawMatrix, 50);
}

// ── Init ──────────────────────────────────────────────────────────────────
initVoice();
fetchSessionHistory();
connectWS();
setInterval(checkHealth, 20000);

createMatrixFox('fox-speaking-canvas', 120, 12);
createMatrixFox('center-fox-canvas', 200, 16);
createMatrixFox('fox-canvas', 100, 12);
