import os
import sys
import json
import asyncio
import threading
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# For winsound double-beeps on Windows
try:
    import winsound
except ImportError:
    winsound = None

# Ensure local module imports resolve
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.event_bus import EventBus
from services.llm_service import LLMService
from services.memory_service import MemoryService
from services.speech_service import SpeechService
from core.assistant import Assistant
from core.state import AssistantState
from utils.logger import logger

app = FastAPI(title="JARVBOI API (Event-Driven)")

# Enable CORS for the Vite UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Global Orchestration Services ---
event_bus = EventBus()
llm_service = LLMService()
memory_service = MemoryService(event_bus=event_bus)
speech_service = SpeechService(event_bus=event_bus)
assistant = Assistant(
    event_bus=event_bus,
    llm_service=llm_service,
    memory_service=memory_service,
    speech_service=speech_service
)

active_connections = set()
main_loop = None


# --- Event Bus Subscribers for WebSocket Streaming ---
async def on_state_changed(state: AssistantState):
    """Broadcasts visual status updates to HUD UI clients."""
    await broadcast_all({"type": "status", "status": state.to_ui_status()})

async def on_thought(data: dict):
    """Streams LLM reasoning diagnostics to UI clients."""
    await broadcast_all({"type": "thought", "thought": data.get("thought", "")})

async def on_tool_start(data: dict):
    """Signals tool execution starts to UI logs."""
    await broadcast_all({
        "type": "tool_start",
        "tool_name": data.get("tool_name"),
        "tool_args": data.get("tool_args", {})
    })

async def on_tool_end(data: dict):
    """Signals tool execution completions to UI logs."""
    await broadcast_all({
        "type": "tool_end",
        "tool_name": data.get("tool_name"),
        "result": str(data.get("result", ""))
    })

async def on_speak_audio(data: dict):
    """Streams neural base64 TTS audio to HUD UI clients."""
    await broadcast_all({"type": "speak", "audio": data.get("audio", "")})

# Subscribe async handlers to the event bus
event_bus.subscribe("state_changed", on_state_changed)
event_bus.subscribe("assistant_thought", on_thought)
event_bus.subscribe("tool_start", on_tool_start)
event_bus.subscribe("tool_end", on_tool_end)
event_bus.subscribe("speak_audio", on_speak_audio)


# --- API Routes ---
class ChatRequest(BaseModel):
    message: str

@app.get("/status")
def get_status():
    if assistant:
        return {"status": "online", "model": llm_service.provider}
    return {"status": "error", "message": "Assistant not initialized"}

@app.post("/chat")
def chat_endpoint(request: ChatRequest):
    """HTTP POST endpoint for basic non-streaming chat."""
    if not assistant:
        return {"error": "Assistant not initialized"}
    
    responses = list(assistant.execute(request.message))
    final_response = next((r.get("response") for r in responses if r.get("type") == "final_response"), "")
    return {"response": final_response, "steps": responses}


# --- WebSocket Broadcast Utilities ---
def broadcast_to_ui(data):
    """Helper to broadcast payloads thread-safely from background workers."""
    global main_loop
    if main_loop and active_connections:
        asyncio.run_coroutine_threadsafe(broadcast_all(data), main_loop)

async def broadcast_all(data):
    """Sends JSON package to all connected WebSocket HUD UI clients."""
    for ws in list(active_connections):
        try:
            await ws.send_json(data)
        except Exception:
            try:
                active_connections.remove(ws)
            except KeyError:
                pass


# --- Background Voice Loop (Continuous Listening sidecar) ---
def background_voice_loop():
    global main_loop, assistant, speech_service
    logger.info("[Voice Server] Background wake-word thread started.")
    
    # Wait for asyncio event loop initialization
    while main_loop is None:
        time.sleep(0.1)
        
    try:
        speech_service.calibrate_mic(duration=1.0)
    except Exception as e:
        logger.error(f"[Voice Server] Mic calibration error: {e}")

    logger.info("[Voice Server] Ready. Listening for wake word ('Jarvis' / 'Jarvboi')...")
    
    while True:
        try:
            is_awaiting_confirm = False
            if assistant and (assistant.awaiting_ollama_start or assistant.awaiting_gemini_switch):
                is_awaiting_confirm = True
                
            if is_awaiting_confirm:
                logger.info("[Voice Server] Awaiting confirmation input. Bypassing wake word.")
                assistant.set_state(AssistantState.LISTENING)
                broadcast_to_ui({"type": "system", "message": "🎙️ Awaiting your reply..."})
                
                attempts = 0
                max_attempts = 3
                command = None
                
                while attempts < max_attempts:
                    res = speech_service.listen_mic(timeout=7, phrase_time_limit=6)
                    if res is None:
                        logger.info("[Voice Server] Silence during confirmation wait.")
                        command = None
                        break
                    elif res.strip() == "":
                        attempts += 1
                        if attempts < max_attempts:
                            broadcast_to_ui({"type": "system", "message": "🎙️ I didn't catch that. Could you please repeat?"})
                            if winsound:
                                try: winsound.Beep(900, 150)
                                except Exception: pass
                        else:
                            command = ""
                    else:
                        command = res
                        break
                        
                if not command:
                    logger.info("[Voice Server] No confirmation reply detected. Clearing wait states.")
                    assistant.awaiting_ollama_start = False
                    assistant.awaiting_gemini_switch = False
                    assistant.set_state(AssistantState.IDLE)
                    broadcast_to_ui({"type": "system", "message": "Voice Confirmation: Timeout. Reset to IDLE."})
                    continue
            else:
                # Capture ambient speech checking for wake word
                phrase = speech_service.listen_mic(timeout=3, phrase_time_limit=3)
                if not phrase:
                    continue
                    
                clean_phrase = phrase.lower().strip()
                if "jarvis" in clean_phrase or "jarvboi" in clean_phrase or "jarvis" in clean_phrase.replace(" ", ""):
                    logger.info(f"[Voice Server] Wake word detected: '{clean_phrase}'")
                    if winsound:
                        try:
                            winsound.Beep(1200, 80)
                            winsound.Beep(1600, 100)
                        except Exception:
                            pass
                            
                    assistant.set_state(AssistantState.LISTENING)
                    broadcast_to_ui({"type": "system", "message": "🎙️ Jarvis Activated. Listening..."})
                    
                    command = speech_service.listen_mic(timeout=8, phrase_time_limit=9)
                    if not command:
                        logger.info("[Voice Server] No command detected after activation.")
                        if winsound:
                            try: winsound.Beep(800, 150)
                            except Exception: pass
                        assistant.set_state(AssistantState.IDLE)
                        broadcast_to_ui({"type": "system", "message": "Voice Activation: Timeout / No command."})
                        continue
                else:
                    continue
                    
            logger.info(f"[Voice Server] Spoken Command received: '{command}'")
            broadcast_to_ui({"type": "voice_command", "message": command})
            
            # Process command
            spoken_responses = set()
            try:
                for step in assistant.execute(command):
                    if assistant.interrupted:
                        logger.info("[Voice Server] Command execution interrupted.")
                        break
                    
                    # If step is the final response, speak it vocally
                    if step.get("type") == "final_response":
                        response_text = step.get("response", "")
                        if response_text and response_text not in spoken_responses and response_text != "[Interrupted]":
                            spoken_responses.add(response_text)
                            
                            assistant.set_state(AssistantState.SPEAKING)
                            speech_service.speak(response_text, has_ui_client=bool(active_connections))
                            
                            # Sleep in small slices, checking for interruption
                            word_count = len(response_text.split())
                            speech_duration = max(2.0, (word_count / 2.5) + 0.8)
                            
                            start_sleep = time.time()
                            while time.time() - start_sleep < speech_duration:
                                if assistant.interrupted:
                                    logger.info("[Voice Server] Vocal playback sleep interrupted.")
                                    break
                                time.sleep(0.05)
            except Exception as e:
                logger.exception("[Voice Server] Execution failed:")
                broadcast_to_ui({"type": "error", "message": f"Voice Pipeline Error: {e}"})
                
            assistant.set_state(AssistantState.IDLE)
            
        except Exception as e:
            logger.exception("[Voice Server] Error in voice detection cycle:")
            time.sleep(1)


# --- WebSocket Handler ---
@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    active_connections.add(websocket)
    logger.info(f"WebSocket client connected. Active clients: {len(active_connections)}")
    
    message_queue = asyncio.Queue()

    # Concurrent reader loop
    async def receive_loop():
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    payload = json.loads(data)
                    msg_type = payload.get("type")
                    if msg_type == "interrupt":
                        logger.info("[WebSocket] Interrupt event received from UI.")
                        event_bus.publish("interrupt")
                    elif msg_type == "message" or "message" in payload:
                        await message_queue.put(payload.get("message", ""))
                except json.JSONDecodeError:
                    await message_queue.put(data)
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error(f"Error in websocket receive loop: {e}")

    receive_task = asyncio.create_task(receive_loop())
    
    try:
        while True:
            user_message = await message_queue.get()
            
            if not user_message.strip():
                continue
                
            if user_message.lower() == "clear":
                memory_service.clear()
                await websocket.send_json({
                    "type": "system",
                    "message": "Conversation history cleared."
                })
                continue
                
            try:
                # Execute user message step generator
                for step in assistant.execute(user_message):
                    if assistant.interrupted:
                        break
                    # Send step over websocket
                    await websocket.send_json(step)
                    await asyncio.sleep(0.01)
            except Exception as e:
                logger.exception("Error in assistant execution loop:")
                await websocket.send_json({"type": "error", "message": str(e)})
                
    except Exception as e:
        logger.error(f"WebSocket session error: {e}")
    finally:
        receive_task.cancel()
        try:
            active_connections.remove(websocket)
        except KeyError:
            pass
        logger.info(f"WebSocket client disconnected. Active clients: {len(active_connections)}")


# --- Startup and Shutdown Hooks ---
@app.on_event("startup")
async def startup_event():
    global main_loop
    main_loop = asyncio.get_running_loop()
    event_bus.set_async_loop(main_loop)
    
    # Launch background thread for voice activation
    voice_thread = threading.Thread(target=background_voice_loop, daemon=True)
    voice_thread.start()

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("[FastAPI] Shutdown sequence initiated...")
    for ws in list(active_connections):
        try: await ws.close()
        except Exception: pass
    active_connections.clear()
    memory_service.stop()
    
    # Clean up temporary scratch assets
    try:
        project_root = os.path.dirname(os.path.abspath(__file__))
        scratch_dir = os.path.join(project_root, "scratch")
        if os.path.exists(scratch_dir):
            for f in os.listdir(scratch_dir):
                if f.endswith((".mp3", ".png", ".jpg")):
                    try: os.remove(os.path.join(scratch_dir, f))
                    except Exception: pass
    except Exception:
        pass
    logger.info("[FastAPI] Shutdown completed successfully.")

if __name__ == "__main__":
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=False)
