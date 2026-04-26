# Abstract

## Nightion — A Fully Offline AI Coding Assistant

**Submitted by:** Neural Vortex
**Department:** CSE (DS)
**College:** KIET Group of Institutions, Ghaziabad
**Academic Year:** 2025–2026

---

### Problem Statement

Existing AI coding assistants (ChatGPT, GitHub Copilot, etc.) require constant internet connectivity and send user data to external cloud servers. This raises significant privacy concerns, especially for students and developers working on proprietary or sensitive code. Additionally, these tools are unavailable in offline environments such as competitive exams, restricted networks, or low-connectivity areas.

### Proposed Solution

**Nightion** is a fully offline AI coding assistant that runs entirely on the user's local machine. It leverages the **gemma4** large language model served via **Ollama** and provides a rich web-based interface built with **FastAPI** and vanilla JavaScript. The system offers conversational AI chat, code generation, DSA problem solving, vision-based code extraction from screenshots, human-like auto-typing, desktop application control, and persistent memory — all without any cloud dependency.

### Key Features

- **100% Offline Operation** — No internet required; all processing happens locally.
- **Privacy-First Design** — Zero data leaves the user's machine.
- **Multi-Modal Interaction** — Chat mode, writer/see-and-code mode, and voice mode.
- **Vision-Based Code Generation** — Screenshot any coding problem and receive a complete solution.
- **Human-Like Auto-Typing** — Types generated code into external editors with realistic timing, bursts, and typo simulation.
- **Retrieval-Augmented Generation (RAG)** — ChromaDB vector store with sentence-transformers for context-aware responses.
- **Persistent Knowledge Graph** — Concept graph with confidence dynamics for continuous learning.

### Technology Stack

- **Backend:** Python 3.10+, FastAPI, Uvicorn
- **Frontend:** Vanilla HTML/CSS/JavaScript
- **AI Model:** gemma4 via Ollama (fully local)
- **Database:** SQLite (WAL mode)
- **Vector Store:** ChromaDB + all-MiniLM-L6-v2
- **Testing:** pytest (37 test files)

### Results

The system successfully provides a privacy-preserving, fully offline AI coding assistant with real-time streaming responses, accurate intent classification via semantic vector routing, and a comprehensive safety architecture. Testing covers core functionality, adversarial cases, chaos engineering, and performance benchmarks.

### Conclusion

Nightion demonstrates that a production-quality AI coding assistant can be built and operated entirely offline, providing privacy-first AI assistance without compromising on features or user experience.

---

**Keywords:** Offline AI, Coding Assistant, Large Language Model, Privacy, RAG, Vision-Based Code Generation, Natural Language Processing
