# 🌌 Nightion — Your Personal AI Coding Brain

> *Like Jarvis, but for code. Runs entirely on your PC.*

---

## What is Nightion?

**Nightion** is a locally-running AI coding assistant powered by **DeepSeek-Coder** (via Ollama). It:

- 💬 **Chats about code** in any language — writes, debugs, explains, optimizes
- 🧠 **Learns in real time** — paste docs/code into the Teach panel and it remembers permanently
- ⚡ **Runs Python** — execute code inline from the browser
- 🎙️ **Understands voice** — talk to it with your microphone
- 🔒 **100% private** — runs locally, no data sent to any cloud

---

## Requirements

- **Python 3.10+** — [python.org](https://www.python.org/downloads/)
- **Ollama** — [ollama.com/download/windows](https://ollama.com/download/windows)
- ~8 GB RAM (16 GB recommended for best experience)
- GPU optional (NVIDIA) — speeds up responses significantly

---

## Setup (One Time)

```bat
setup.bat
```

This will:
1. Install all Python dependencies
2. Verify Ollama is installed
3. Download the `deepseek-coder:6.7b` model (~3.8 GB)

---

## Launch Nightion

```bat
start_nightion.bat
```

Then open **http://localhost:8000** in your browser (it opens automatically).

---

## Features

| Feature | Description |
|---|---|
| 💬 Chat | Ask anything about code — streaming responses |
| 🧠 Teach | Paste code/docs → Nightion remembers permanently |
| ⚡ Code Runner | Execute Python snippets with output |
| 🎙️ Voice | Speak your question, hear the first answer |
| 📊 Stats | See model info, memory size, conversation turns |
| 🔄 "Use Memory" toggle | Enable/disable RAG context per message |

---

## Project Structure

```
Nightion/
├── server.py           ← FastAPI backend (main brain)
├── rag_engine.py       ← Real-time learning via ChromaDB
├── code_runner.py      ← Python sandbox
├── requirements.txt    ← Dependencies
├── setup.bat           ← One-click installer
├── start_nightion.bat  ← Launch script
├── static/
│   ├── index.html      ← Jarvis-style UI
│   ├── style.css       ← Dark space theme
│   └── app.js          ← Chat, voice, streaming logic
└── nightion_memory/    ← Persistent knowledge store (auto-created)
```

---

## How "Real-Time Learning" Works

Nightion uses **RAG (Retrieval-Augmented Generation)**:

1. You paste code, documentation, or facts into the **Teach** panel
2. Nightion embeds it using a local model and stores it in **ChromaDB** (a vector database on your PC)
3. Every time you ask a question, Nightion **retrieves the most relevant knowledge** and includes it in the context
4. This happens **automatically and permanently** — the memory survives restarts

> This is functionally equivalent to real-time training for a local assistant, without requiring a supercomputer.

---

## Tips

- Say *"Teach Nightion"* what your project does — it will always know the context
- Use the **🎙️ voice button** for hands-free coding questions
- The **"Use Memory" toggle** lets you bypass RAG for general questions
- Click **📊** in the header to check if the model is loaded and ready

---

*Nightion — Built for programmers who want their own AI.*
