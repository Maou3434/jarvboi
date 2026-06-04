You are building a modular local AI assistant project similar to Jarvis.

IMPORTANT:
The goal is NOT to create a toy demo.
The goal is to create a scalable architecture that starts simple but can evolve into:

* voice assistant
* desktop automation system
* browser automation agent
* autonomous workflow assistant
* multi-tool AI system

The assistant must run locally using:

* Python
* Ollama
* local LLMs (currently Mistral 7B)
* modular tool architecture

DO NOT overengineer early stages.
DO NOT introduce unnecessary frameworks initially.
DO NOT use LangChain/CrewAI/OpenClaw unless absolutely necessary later.

The architecture should prioritize:

* modularity
* maintainability
* scalability
* safety
* clear separation of concerns

==================================================
CURRENT PROJECT STATE
=====================

Currently implemented:

* Python terminal chat loop
* Ollama integration
* conversation history
* basic structured JSON tool calling
* YouTube search tool
* website opening tool

The current architecture:
LLM → structured JSON → Python executor → tool execution

==================================================
PROJECT GOAL
============

Build this into a proper local AI assistant pipeline.

The assistant should eventually support:

* natural conversation
* tool calling
* browser automation
* desktop automation
* voice input/output
* memory
* persistent profiles
* task execution
* local/offline operation
* future autonomous workflows

==================================================
REQUIRED ARCHITECTURE
=====================

The codebase should evolve into:

project_root/
│
├── main.py
├── config/
├── core/
│   ├── assistant.py
│   ├── memory.py
│   ├── router.py
│   ├── llm.py
│   └── state.py
│
├── tools/
│   ├── registry.py
│   ├── youtube.py
│   ├── browser.py
│   ├── system.py
│   └── filesystem.py
│
├── automation/
│   ├── browser_agent.py
│   └── desktop_agent.py
│
├── speech/
│   ├── stt.py
│   ├── tts.py
│   └── wakeword.py
│
├── memory/
│   ├── conversations/
│   └── profiles/
│
└── utils/

==================================================
PHASED IMPLEMENTATION PLAN
==========================

PHASE 1 — Stabilize Core Assistant
Build:

* modular assistant class
* proper tool registry
* structured JSON tool calls
* centralized LLM wrapper
* conversation memory manager
* config system
* error handling
* logging

Requirements:

* avoid hardcoded tool checks
* tools should auto-register
* add retry handling for malformed JSON
* support adding tools dynamically

==================================================

PHASE 2 — Browser Automation
Add:

* Playwright
* browser control
* open URLs
* click elements
* type into websites
* search YouTube automatically
* play first video

Requirements:

* safe browser automation
* modular browser agent
* deterministic execution
* avoid brittle CSS selectors

==================================================

PHASE 3 — Desktop Automation
Add:

* app launching
* keyboard/mouse control
* screenshots
* clipboard access
* file opening
* OS integration

Use:

* pyautogui
* subprocess
* platform-safe utilities

==================================================

PHASE 4 — Voice Assistant
Add:

* Faster-Whisper
* Piper TTS
* microphone input
* speech output
* wake word system

Requirements:

* modular speech pipeline
* low latency
* interruptible speech
* offline operation preferred

==================================================

PHASE 5 — Memory System
Add:

* persistent memory
* user profile storage
* conversation summaries
* vector memory later if needed

Requirements:

* SQLite initially
* modular memory layer
* easy future migration

==================================================

PHASE 6 — Agentic Behavior
ONLY AFTER ALL PRIOR STAGES WORK RELIABLY.

Add:

* planning
* multi-step tasks
* autonomous execution
* task queues
* scheduling
* long-running workflows

Avoid overengineering before this stage.

==================================================
IMPORTANT ENGINEERING RULES
===========================

1. NEVER allow arbitrary code execution directly from model output.

2. ALL model actions must map to:

* validated structured tool calls
* whitelisted functions

3. Keep the architecture modular.

4. Prioritize reliability over “AI magic”.

5. Smaller local models may fail JSON formatting:

* implement validation
* retries
* graceful fallbacks

6. The assistant should degrade gracefully if:

* models fail
* tools fail
* browser crashes

7. Keep interfaces stable:
   assistant.execute(task)

8. The system should later support:

* swapping models
* swapping tools
* cloud/local hybrid execution

==================================================
CURRENT STACK
=============

Current:

* Python
* Ollama
* Mistral 7B

Planned:

* Faster-Whisper
* Piper
* Playwright
* SQLite

==================================================
WHAT TO BUILD NOW
=================

Start by implementing PHASE 1 properly.

Refactor the current prototype into:

* modular architecture
* tool registry
* assistant class
* centralized tool execution
* robust JSON parsing
* config management
* clean file structure

Provide:

* complete code
* explanations
* folder structure
* dependency list
* step-by-step setup
* rationale for design choices

DO NOT jump ahead into advanced autonomous agent frameworks yet.
