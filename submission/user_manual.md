# User Manual

## Nightion — Installation & Usage Guide

**Version:** 30.0
**Platform:** Windows 10/11
**Author:** Neural Vortex — KIET Group of Institutions, Ghaziabad

---

## Table of Contents

1. [System Requirements](#1-system-requirements)
2. [Installation](#2-installation)
3. [Starting Nightion](#3-starting-nightion)
4. [Using Chat Mode](#4-using-chat-mode)
5. [Using See & Code (Writer Mode)](#5-using-see--code-writer-mode)
6. [Using Smart Cursor](#6-using-smart-cursor)
7. [Using Voice Mode](#7-using-voice-mode)
8. [Desktop App Control](#8-desktop-app-control)
9. [Telemetry Dashboard](#9-telemetry-dashboard)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. System Requirements

### Hardware

| Component | Minimum | Recommended |
|---|---|---|
| CPU | 4-core x64 | 8-core+ x64 |
| RAM | 8 GB | 16 GB+ |
| Disk Space | 10 GB free | 20 GB+ free |
| GPU | Not required | NVIDIA with CUDA |

### Software

- **Windows 10 or 11** (64-bit)
- **Python 3.10 or newer** — [Download](https://python.org/downloads)
- **Ollama** — [Download](https://ollama.com/download)
- **A modern web browser** (Chrome, Edge, Firefox)

---

## 2. Installation

### Step 1: Install Python

1. Download Python 3.10+ from https://python.org/downloads
2. During installation, **check "Add Python to PATH"**
3. Verify: open Command Prompt and run:
   ```
   python --version
   ```

### Step 2: Install Ollama

1. Download and install Ollama from https://ollama.com/download
2. Open a terminal and pull the gemma4 model:
   ```
   ollama pull gemma4
   ```
3. Wait for the download to complete (several GB).

### Step 3: Install Nightion

1. Extract the Nightion project folder to your preferred location (e.g., `D:\Nightion`)
2. Open Command Prompt in the Nightion folder
3. Install Python dependencies:
   ```
   pip install -r requirements.txt
   ```

---

## 3. Starting Nightion

### Option A: One-Click Launcher (Recommended)

1. Navigate to the Nightion folder
2. **Double-click `nightion.bat`**
3. The launcher will:
   - Clear any existing processes on port 8999
   - Start Ollama
   - Launch the Nightion server
   - Open your browser to http://127.0.0.1:8999
   - Start the Smart Cursor background listener

### Option B: Manual Start

1. Start Ollama (if not already running):
   ```
   ollama serve
   ```
2. In a new terminal, navigate to the Nightion folder and run:
   ```
   python -m uvicorn nightion_core:app --host 0.0.0.0 --port 8999 --reload
   ```
3. Open http://127.0.0.1:8999 in your browser.

---

## 4. Using Chat Mode

Chat Mode is the default mode when you open Nightion.

### Sending a Message

1. Type your question or request in the text input at the bottom
2. Press **Enter** or click the send button
3. Watch the AI respond in real-time with token streaming

### Features

- **Reasoning Transparency:** Click on the "Thinking" block to expand/collapse the AI's reasoning process
- **Code Blocks:** Generated code appears with syntax highlighting and a copy button
- **Markdown:** Responses are rendered with full markdown formatting
- **RAG:** Enable/disable knowledge retrieval by toggling the RAG option
- **Session History:** Conversation persists within the session

### Example Queries

- "Explain how binary search works"
- "Write a Python function to merge two sorted linked lists"
- "What is the time complexity of quicksort?"
- "Open notepad" (triggers desktop control)

---

## 5. Using See & Code (Writer Mode)

See & Code lets you screenshot any coding problem and get a generated solution.

### Step-by-Step

1. Click the **"Writer"** tab in the mode switcher
2. Open the coding problem you want to solve in another window (e.g., LeetCode)
3. Click **"Capture Screenshot"**
   - Nightion will Alt+Tab to the previous window
   - Take a screenshot
   - Alt+Tab back to Nightion
4. The captured screenshot appears in the preview area
5. Select the **programming language** from the dropdown
6. Click **"Generate Code"**
7. Wait for the AI to analyze the image and generate code
8. The generated code appears with syntax highlighting
9. Click **"Type Code"** and then click on the target text field in any editor
10. Nightion will auto-type the code with human-like timing

### Auto-Typing Features

- Realistic character-by-character typing (35–70ms per character)
- Occasional burst typing (5–8 chars at high speed)
- Simulated typos with backspace correction (~4% after 50 chars)
- Protected characters and keywords never get typo'd
- Cancel anytime by clicking the cancel button

---

## 6. Using Smart Cursor

Smart Cursor provides system-wide AI assistance via a hotkey.

### How to Use

1. Make sure Nightion is running (started via `nightion.bat`)
2. Press **Ctrl+Shift+0** anywhere on your desktop
3. A snipping-tool-style selector appears
4. **Drag to select** the screen region you want the AI to read
5. Wait for the AI to process the captured region
6. **Click** on any text field where you want the answer typed
7. The AI response is typed automatically at human speed

---

## 7. Using Voice Mode

1. Click the **"Voice"** tab in the mode switcher
2. The animated fox character appears with a matrix-style background
3. Interact with the AI through voice
4. The fox animates based on state: idle → listening → speaking
5. AI responses are read aloud via speech synthesis

---

## 8. Desktop App Control

You can ask Nightion to open or close applications using natural language.

### Example Commands

- "Open notepad"
- "Open calculator"
- "Open Chrome"
- "Open VS Code"
- "Open Windows Terminal"
- "Open file explorer"

### Supported Apps (40+)

System, browsers, dev tools, media players, office suite, messaging apps, and more. See `desktop_action_manager.py` for the full registry.

### Safety

- Destructive actions (close, delete, uninstall) are **blocked** unless explicitly confirmed
- The safety guard evaluates risk before executing any action

---

## 9. Telemetry Dashboard

View detailed traces of every request processed by Nightion.

1. Navigate to http://127.0.0.1:8999/static/logs_dashboard.html
2. Browse all request traces with timestamps
3. Inspect:
   - Router decisions (intent, confidence, reasoning)
   - Execution plans
   - Tool runs
   - Final responses with status

---

## 10. Troubleshooting

### "Ollama is not running"

- Start Ollama manually: `ollama serve`
- Or restart via the `nightion.bat` launcher

### "Port 8999 is already in use"

- The launcher auto-kills existing processes on port 8999
- Manually: `netstat -ano | findstr :8999` to find the PID, then `taskkill /f /pid <PID>`

### "Model returned an empty response"

- Ensure gemma4 is pulled: `ollama pull gemma4`
- Check Ollama logs for errors
- Restart Ollama and try again

### "Browser shows connection refused"

- Wait a few seconds for the server to fully start
- Check the terminal for error messages
- Verify the server is running at http://127.0.0.1:8999

### "See & Code captures the wrong window"

- Make sure the target window (e.g., LeetCode) was the **last active window** before clicking capture
- The system uses Alt+Tab to switch to the previous window

### "Auto-typing types in the wrong place"

- Click exactly on the text field where you want the code typed
- Ensure the text field has focus before the typing begins
- Some editors may need to be in "insert mode"

---

**For additional support, refer to the full documentation in `documentation.txt`.**
