# Presentation Outline

## Nightion — A Fully Offline AI Coding Assistant

> Slide-by-slide outline for the project presentation.
> Estimated duration: **15–20 minutes**

---

### Slide 1: Title Slide

- **Title:** Nightion — A Fully Offline AI Coding Assistant
- **Subtitle:** Privacy-First AI for Coding, Vision, and Desktop Automation
- **Submitted by:** Neural Vortex
- **College:** KIET Group of Institutions, Ghaziabad
- _Visual:_ Nightion fox logo, dark theme background

---

### Slide 2: Problem Statement

- Cloud AI tools (Copilot, ChatGPT) require internet & send data to external servers
- Privacy risk for sensitive/proprietary code
- Unavailable offline (exams, restricted networks)
- Expensive subscription costs
- _Visual:_ Comparison table — cloud tools vs offline needs

---

### Slide 3: Proposed Solution

- **Nightion** — Fully offline AI assistant running on your machine
- Uses **gemma4** model via **Ollama** (local inference)
- Web-based UI via **FastAPI** + vanilla JS
- Zero data leaves the machine
- _Visual:_ High-level system diagram

---

### Slide 4: Key Features

- 💬 AI Chat with real-time streaming
- 🧠 Code generation with RAG
- 📐 Structured DSA problem solving
- 👁️ See & Code — screenshot → code → auto-type
- 🖱️ Smart Cursor — system-wide hotkey
- 🎙️ Voice Mode with animated fox
- 🖥️ Desktop app control (40+ Windows apps)
- _Visual:_ Feature icons grid

---

### Slide 5: Architecture

- Layered agent architecture diagram
- Presentation → API → Orchestration → Intelligence → Security → Persistence
- _Visual:_ Full architecture diagram from documentation

---

### Slide 6: Technology Stack

| Component    | Technology              |
| ------------ | ----------------------- |
| Model        | gemma4 via Ollama       |
| Backend      | FastAPI + Uvicorn       |
| Frontend     | HTML/CSS/JS             |
| Vector Store | ChromaDB + MiniLM-L6-v2 |
| Database     | SQLite (WAL mode)       |
| Vision       | gemma4 multimodal       |
| Testing      | pytest (37 test files)  |

---

### Slide 7: Intent Classification

- Vector-based semantic classification (not regex)
- all-MiniLM-L6-v2 sentence-transformer
- ~100+ canonical examples embedded in ChromaDB
- 6 intents: GREETING, CODE, DSA, GENERAL, APP_CONTROL, BROWSER
- False-positive blocking for safety
- _Visual:_ Classification pipeline flow diagram

---

### Slide 8: Memory & Knowledge System

- SQLite Truth Graph — 6 tables (episodic, patterns, preferences, facts, chat, language)
- Knowledge Graph — bidirectional edges, confidence dynamics (+0.1 / -0.2)
- ChromaDB Vector Store — semantic search for RAG
- Context Injection — top-3 ranked knowledge injected into prompts
- _Visual:_ ER diagram of key tables

---

### Slide 9: Security Architecture

- 7 independent safety layers (defense-in-depth)
- Pre-check guard → Intent safety → Capability gates → Sandbox → Patch safety → Tool contracts → Tri-state verifier
- Blocked dangerous imports, destructive keywords, AST validation
- 100% destructive action blocking in tests
- _Visual:_ Security layers diagram

---

### Slide 10: See & Code Pipeline

1. Screenshot capture (Alt+Tab, pyautogui, resize)
2. gemma4 vision analysis (multimodal prompt)
3. Code extraction (10 languages supported)
4. Human-like auto-typing (35-70ms, bursts, typo simulation)

- _Visual:_ Pipeline flow with sample screenshot → code output

---

### Slide 11: Smart Cursor

- System-wide Ctrl+Shift+0 hotkey
- Snipping-tool-style region selection
- AI analyzes captured region
- Click anywhere to auto-type the result
- _Visual:_ Demo video or screenshot sequence

---

### Slide 12: Live Demo

- **Demo 1:** Chat mode — ask a coding question, show streaming + reasoning
- **Demo 2:** See & Code — capture a LeetCode problem, generate code, auto-type
- **Demo 3:** App control — "open notepad", "open calculator"
- _(3–5 minutes)_

---

### Slide 13: Testing & Results

- 37 test files covering core, safety, adversarial, chaos, integration
- Categories: Unit → Integration → Adversarial → Chaos → Performance
- Intent classification accuracy: >90%
- Destructive action blocking: 100%
- _Visual:_ Test results summary table or pytest output screenshot

---

### Slide 14: Conclusion

- Successfully built a fully offline, privacy-first AI coding assistant
- Matches cloud tools in capability without any internet dependency
- Comprehensive security prevents destructive actions
- Persistent knowledge grows with usage

---

### Slide 15: Future Work

1. Cross-platform support (macOS, Linux)
2. Multi-model switching (Llama, Mistral, etc.)
3. IDE extensions (VS Code, IntelliJ)
4. Plugin system for third-party tools
5. Collaborative mode on local network
6. Model fine-tuning pipeline

---

### Slide 16: Thank You & Q&A

- **Thank You!**
- _Neural Vortex — KIET Group of Institutions, Ghaziabad_
- Open for questions

---

## Presentation Tips

- Use dark-themed slides to match Nightion's aesthetic (#1a1a2e background, #FF6B00 accents)
- Include animated GIFs or short video clips for See & Code and Smart Cursor demos
- Keep text minimal on slides — use visuals and diagrams
- Prepare a live demo on your actual machine
- Have backup screenshots/videos in case the live demo has issues
