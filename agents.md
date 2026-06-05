# 🤖 JARVBOI - Developer & Agent Onboarding Guide

Welcome! This document provides technical context, architecture rules, and guidelines for other AI coding agents (or human developers) acting on the **Jarvboi** repository. Use this guide to understand system components, data flows, communication protocols, and common implementation pitfalls.

---

## 🏛️ System Architecture & Codebase Map

Jarvboi runs as a multi-process, event-driven desktop client:
1.  **Electron Shell (`electron-main.js`)**: Orchestrates the frontend window, manages system tray operations, and spawns the Python sidecar server.
2.  **Vite HUD (`ui/`)**: A glassmorphic web dashboard that communicates with the Python sidecar via WebSockets.
3.  **FastAPI Sidecar Server (`api.py`)**: Runs the WebSocket server, coordinates LLM calls, hosts automation tools, and executes the background voice loop.

### Key File Responsibilities
*   [api.py](file:///c:/ML_Projects/jarvboi/api.py): Handles WebSocket routes, JSON message serialization, and runs the background thread for voice activation.
*   [core/assistant.py](file:///c:/ML_Projects/jarvboi/core/assistant.py): Coordinates execution loops, executes tools, handles LLM provider fallbacks, and packages automation steps into custom skills.
*   [services/llm_service.py](file:///c:/ML_Projects/jarvboi/services/llm_service.py): Wraps Ollama and Gemini API endpoints, switching providers when offline or requested.
*   [services/speech_service.py](file:///c:/ML_Projects/jarvboi/services/speech_service.py): Audio interface providing mic calibration, speech recognition (STT via online Google API or offline `faster-whisper`), and speech generation (TTS via `edge-tts`).
*   [services/event_bus.py](file:///c:/ML_Projects/jarvboi/services/event_bus.py): In-memory publish-subscribe broker decoupling server actions.
*   [tools/registry.py](file:///c:/ML_Projects/jarvboi/tools/registry.py): Central schema and function registry for tools exposed to the LLM.

---

## 🎙️ State Machine & Voice Loop Logic

The assistant transitions through states defined in [core/state.py](file:///c:/ML_Projects/jarvboi/core/state.py):
*   `IDLE` 🔵: Ambient resting state. Counter-rotates outer visual rings.
*   `LISTENING` 🟢: Capturing microphone audio. AI orb pulses cyan.
*   `THINKING` / `PROCESSING` 🟡: LLM query execution or tool running. AI orb rotates rapidly.
*   `SPEAKING` 🟣: Playback of synthesized base64 voice streams.
*   `AWAITING_SKILL_SAVE`: Prompting user to save a completed workflow.

### Wake-Word Bypass Protocol
During confirmation tasks (e.g. asking to switch to Gemini, boot Ollama in WSL, or save a skill), the system enters confirmation mode. In this mode, the voice activation loop:
1.  Temporarily disables the `"Jarvis"`/`"Jarvboi"` wake-word lock.
2.  Listens directly for affirmative (`yes`, `sure`, `ok`) or negative (`no`, `decline`) phrases.
3.  Implements a 3-turn retry warning if recognition fails before timing out and returning to `IDLE`.

---

## 🧠 Memory Subsystem V2 (Obsidian Graph & Vectors)

Jarvboi implements an advanced Obsidian-based long-term memory system managed by [services/memory_service.py](file:///c:/ML_Projects/jarvboi/services/memory_service.py) and code inside [memory/](file:///c:/ML_Projects/jarvboi/memory/).

### 1. File Structure & Vault Initialization
The vault is stored at `Obsidian/Memories/` and divided into categories:
*   `People/`, `Projects/`, `Concepts/`, `Daily/`, `Meetings/`, `Procedures/`, `Archive/`

All notes are written with standard YAML frontmatter:
```markdown
---
created_at: 1717624102.0
importance: 7.2
type: concept
---
# Note Title
Note body containing markdown text and Wikilinks...
```

### 2. Turn-Based Promotion Pipeline
When a user-assistant conversation turn terminates:
1.  An asynchronous event `save_memory` is published on the Event Bus.
2.  A background worker queue consumes the transaction in [services/memory_service.py](file:///c:/ML_Projects/jarvboi/services/memory_service.py#L208).
3.  [MemoryExtractor](file:///c:/ML_Projects/jarvboi/memory/extractor.py) queries the LLM to extract semantic facts, entity links, and categories.
4.  [ImportanceScorer](file:///c:/ML_Projects/jarvboi/memory/scorer.py) rates importance `[1-10]`. If above a threshold, it gets promoted to the Obsidian Vault.
5.  [ObsidianLinker](file:///c:/ML_Projects/jarvboi/memory/linker.py) formats markdown body pages and injects Wikilinks `[[concept_or_person]]` to connect notes.
6.  [ObsidianVault](file:///c:/ML_Projects/jarvboi/memory/vault.py) handles filesystem writes. If incoming facts conflict with existing notes, it appends details to a `## Conflicting Information` section.
7.  The [ObsidianGraph](file:///c:/ML_Projects/jarvboi/memory/graph.py) and [ObsidianIndexer](file:///c:/ML_Projects/jarvboi/memory/indexer.py) rebuild the entity relational map and update the local vector index in `scratch/vector_memory.json`.

### 3. Embeddings & Jaccard Retrieval Fallbacks
For semantic retrieval:
*   **Gemini Mode**: Calls Google's `text-embedding-004` model.
*   **Ollama Mode**: Tries `nomic-embed-text` via Ollama `/api/embeddings`.
*   **Offline Mode**: If APIs fail or are offline, the retriever falls back to Jaccard word-overlap token matching (`utils/text_helpers.py`).

### 4. Memory Reflection Loop
The [MemoryReflector](file:///c:/ML_Projects/jarvboi/memory/reflector.py) runs on a background thread. Every 6 hours, it scans daily notes, consolidates entities, rewrites verbose notes, and updates structural metadata.

---

## 🔌 Communication & WebSockets Specification

All UI communication occurs over `ws://127.0.0.1:8000/ws/chat`.

### Outbound Events (Server -> UI)
*   `{"type": "status", "status": "listening" | "processing" | "speaking" | "idle"}`: Sets the orb state.
*   `{"type": "thought", "thought": "Thinking process text..."}`: Updates the UI reasoning panel.
*   `{"type": "tool_start", "tool_name": "...", "tool_args": {...}}`: Logs starting tools.
*   `{"type": "tool_end", "tool_name": "...", "result": "..."}`: Logs tool outputs.
*   `{"type": "speak", "audio": "UklGRi..."}`: Streams Base64-encoded audio chunks.
*   `{"type": "stop_audio"}`: Ceases any active visual and audio playback in the HUD.
*   `{"type": "final_response", "response": "..."}`: Delivers the final text response.

### Inbound Events (UI -> Server)
*   `{"message": "user text command"}`: Sends text query.
*   `{"type": "interrupt"}`: Interrupts speaking or tool loops immediately.

---

## 🛠️ Tool Registry & LLM Schema Format

Any tool exposed to the assistant MUST be registered in [tools/registry.py](file:///c:/ML_Projects/jarvboi/tools/registry.py).

### How to Create and Register a Tool
Write your automation logic in [tools/](file:///c:/ML_Projects/jarvboi/tools/) and register it with the `@register_tool` decorator:
```python
from tools.registry import register_tool

@register_tool(
    name="system_set_volume",
    description="Sets the host operating system volume level.",
    parameters={
        "type": "object",
        "properties": {
            "volume_level": {
                "type": "integer",
                "description": "Target volume percentage from 0 to 100."
            }
        },
        "required": ["volume_level"]
    }
)
def system_set_volume(volume_level: int) -> str:
    # Volume setting code here...
    return f"Volume successfully set to {volume_level}%."
```

### LLM Dialogue Structure Rules
When calling tools, the LLM is instructed to yield responses in two turns:
1.  **Turn 1 (Execution)**: The assistant responds with a JSON containing the `"tool_name"` and `"tool_args"`. The `"response"` field MUST be left empty.
2.  **Turn 2 (Reporting)**: Once the tool executes and yields a result, the assistant receives the output in its memory history, sets `"tool_name"` to `null`, and returns the final polite verbal confirmation in the `"response"` field.

---

## ⚠️ Developer Caveats & Critical Gotchas

1.  **Thread Concurrency**: FastAPI runs on the main asyncio loop. The background wake-word listener thread (`background_voice_loop`) is a separate Python OS thread.
2.  **Async/Sync Event Bus Synchronization**: The `EventBus` class contains a reference to the primary FastAPI async loop (set via `event_bus.set_async_loop(main_loop)`). Any events published from the voice loop thread (such as state changes or audio events) MUST use `asyncio.run_coroutine_threadsafe` inside the event bus to safely schedules callbacks in the main event thread.
3.  **Windows OS Locking**: Library routines such as `winsound`, `pygetwindow`, and visual click captures require Windows focus privileges. If testing headless or via virtual shells, GUI calls (such as `pyautogui.click()`) might raise OS display hooks errors.
4.  **Audio Self-Transcription Feedback**: When the assistant is speaking (`AssistantState.SPEAKING`), the background loop suspends the microphone listener thread. If you modify the TTS playback routines, ensure the listener remains paused until audio output is fully played to prevent the assistant from hearing and transcribing its own voice.
5.  **Browser CDP URL Connection**: The Playwright wrapper inside [tools/browser.py](file:///c:/ML_Projects/jarvboi/tools/browser.py) connects to an existing Chrome instance via Chrome DevTools Protocol (`BROWSER_CONNECT_CDP=True` and port `9222`). Make sure your browser has debugging enabled or set headless mode to false for isolated sessions.

---

## 🧪 Testing System Diagnostics

Run system diagnostics to verify your changes did not break core features:
```powershell
# Run all diagnostics test suites
.\venv\Scripts\python.exe tests/run_tests.py
```
To run specific module validations, execute their respective files inside the `tests/` directory (e.g., `tests/test_memory_service.py`).
