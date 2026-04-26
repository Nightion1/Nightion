# Project Synopsis

## Nightion — A Fully Offline AI Coding Assistant

| Field | Details |
|---|---|
| **Project Title** | Nightion — A Fully Offline AI Coding Assistant |
| **Submitted by** | Neural Vortex |
| **Department** | CSE (DS) |
| **College** | KIET Group of Institutions, Ghaziabad |
| **Academic Year** | 2025–2026 |

---

## 1. Introduction

Artificial Intelligence has transformed software development through tools like GitHub Copilot, ChatGPT, and Amazon CodeWhisperer. However, these tools share a critical limitation: they require constant internet connectivity and process user data on external cloud servers. This creates privacy risks, vendor lock-in, and inaccessibility in offline environments.

**Nightion** addresses these challenges by providing a fully offline AI coding assistant that runs entirely on the user's local machine. Built as a solo developer project, it uses the gemma4 language model served locally via Ollama and provides a feature-rich web interface.

---

## 2. Problem Definition

### 2.1 Existing Challenges

1. **Privacy Concerns** — Cloud-based AI tools transmit code and queries to external servers, exposing potentially sensitive or proprietary information.
2. **Internet Dependency** — Complete reliance on network connectivity renders these tools useless during outages, competitive exams, or in restricted environments.
3. **Cost Barriers** — Premium AI coding tools require paid subscriptions, creating accessibility barriers for students and independent developers.
4. **Limited Customization** — Cloud tools offer minimal control over model behavior, system prompts, and knowledge management.

### 2.2 Need for the Project

A locally-hosted AI coding assistant that matches the capabilities of cloud-based tools while providing complete privacy, offline operation, and full user control over the system.

---

## 3. Objectives

1. **Build a fully offline AI coding assistant** that processes all queries locally using the gemma4 language model.
2. **Implement multi-modal interaction** including chat, vision-based code generation (See & Code), and voice mode.
3. **Design a robust security architecture** with guards, sandboxes, capability gates, and output verification to prevent destructive AI actions.
4. **Create a persistent knowledge system** using SQLite, ChromaDB vectors, and a knowledge graph with confidence dynamics.
5. **Develop a real-time streaming interface** with WebSocket-based token streaming for reasoning transparency.
6. **Enable desktop integration** including native app control and human-like auto-typing into external editors.

---

## 4. Scope

### 4.1 In Scope

- Conversational AI chat with real-time streaming
- Code generation and explanation
- DSA problem solving with structured methodology
- Screenshot-based code extraction and generation (See & Code)
- System-wide smart cursor with hotkey activation
- Voice interaction with animated character
- Desktop application control (40+ Windows apps)
- RAG with ChromaDB vector store
- Persistent memory (SQLite truth graph)
- Knowledge graph with confidence-based learning
- Multi-layer security (guards, sandbox, verifier)
- Comprehensive testing (37 test files)
- Telemetry dashboard for trace inspection

### 4.2 Out of Scope

- Cloud deployment or multi-user support
- Mobile application
- Non-Windows desktop control
- Training or fine-tuning the language model
- Real-time collaboration features

---

## 5. Methodology

### 5.1 Development Approach

Iterative, phase-based development with continuous testing and hardening. The project evolved through 30+ development phases, each adding capabilities and strengthening existing components.

### 5.2 System Architecture

The system follows a **layered agent architecture**:

1. **Presentation Layer** — Vanilla HTML/CSS/JS frontend served as static files
2. **API Layer** — FastAPI with REST and WebSocket endpoints
3. **Orchestration Layer** — Query processing, context building, and LLM streaming
4. **Intelligence Layer** — RAG, vector search, knowledge graph, and intent routing
5. **Security Layer** — Guards, sandboxes, capability gates, and output verification
6. **Persistence Layer** — SQLite databases, ChromaDB vectors, and JSON memory

### 5.3 Key Algorithms & Techniques

| Technique | Application |
|---|---|
| Cosine Similarity (vector-based) | Intent classification via sentence-transformers |
| SHA-256 Hashing | O(1) knowledge base lookups |
| Retrieval-Augmented Generation | Context injection from vector store |
| Confidence Dynamics | Knowledge graph node strength adjustment |
| AST Parsing | Code patch validation in sandbox |
| NDJSON Streaming | Real-time token delivery from Ollama |

### 5.4 Tools & Technologies

| Component | Technology |
|---|---|
| Language | Python 3.10+ |
| AI Model | gemma4 via Ollama |
| Backend Framework | FastAPI + Uvicorn |
| Frontend | HTML5, CSS3, JavaScript (ES6+) |
| Database | SQLite (WAL mode) |
| Vector Store | ChromaDB + all-MiniLM-L6-v2 |
| Screen Capture | mss, pyautogui |
| Auto-Typing | pynput keyboard controller |
| Testing | pytest |
| Version Control | Git |
| Containerization | Docker |

---

## 6. Modules

### Module 1: Core Engine
- FastAPI application server (`nightion_core.py`)
- Query orchestrator with Ollama streaming (`orchestrator.py`)
- Pydantic schema validation (`schemas.py`)

### Module 2: Intelligence Layer
- Hybrid RAG adapter (`llm_adapter.py`)
- Semantic intent router (`tool_router.py`)
- Vector store with ChromaDB (`vector_store.py`)
- Knowledge context injection (`context_injector.py`)

### Module 3: Memory & Knowledge
- SQLite truth graph (`memory_core.py`)
- Knowledge graph with confidence dynamics (`knowledge_graph.py`)
- Topic-hashed knowledge base (`knowledge_base.py`)

### Module 4: Security & Safety
- Action risk evaluation (`guards.py`)
- Isolated code execution sandbox (`sandbox.py`)
- Capability gates (`capability_policy.py`)
- Tri-state output verification (`verifier.py`)

### Module 5: Desktop & Vision
- Native Windows app launcher (`desktop_action_manager.py`)
- Vision-based code generation with auto-typing (`see_and_code.py`)
- System-wide smart cursor (`smart_cursor.py`)

### Module 6: Frontend
- Chat interface with WebSocket streaming (`index.html`, `app.js`)
- Mode switcher (Chat/Writer/Voice) (`mode_switcher.js`)
- See & Code writer mode (`writer_mode.js`)
- Voice mode with animated fox (`voice_mode.js`)
- Telemetry dashboard (`logs_dashboard.html`)

---

## 7. Expected Outcomes

1. A fully functional offline AI coding assistant accessible at `http://127.0.0.1:8999`
2. Accurate intent classification with >90% precision via semantic vector routing
3. Real-time streaming responses with sub-second first-token latency
4. Successful code generation from screenshots across 10 programming languages
5. Robust security preventing all destructive actions without explicit confirmation
6. Persistent knowledge that grows and refines with usage

---

## 8. Timeline

| Phase | Duration | Deliverable |
|---|---|---|
| Research & Design | Week 1–2 | Architecture design, tech stack selection |
| Core Engine | Week 3–5 | FastAPI server, orchestrator, Ollama integration |
| Intelligence Layer | Week 6–8 | RAG, intent router, vector store |
| Memory System | Week 9–10 | SQLite truth graph, knowledge graph |
| Security Hardening | Week 11–13 | Guards, sandbox, verifier, capability gates |
| Desktop & Vision | Week 14–16 | See & Code, smart cursor, app control |
| Frontend & UX | Week 17–19 | Chat UI, mode switcher, voice mode |
| Testing & Evaluation | Week 20–22 | 37 test files, eval harness, benchmarks |
| Documentation & Submission | Week 23–24 | Report, presentation, demo |

---

## 9. References

1. Ollama — https://ollama.com
2. FastAPI Documentation — https://fastapi.tiangolo.com
3. ChromaDB — https://docs.trychroma.com
4. Sentence-Transformers (all-MiniLM-L6-v2) — https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2
5. Pydantic — https://docs.pydantic.dev
6. PyAutoGUI — https://pyautogui.readthedocs.io
7. pynput — https://pynput.readthedocs.io

---

**Date:** ________________________
**Signature:** ________________________
