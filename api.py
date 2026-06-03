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

# For activation sound alerts on Windows
try:
    import winsound
except ImportError:
    winsound = None

# Ensure local module imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.assistant import Assistant
from utils.logger import logger

app = FastAPI(title="JARVBOI API")

# Enable CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances and event loop references
assistant = None
active_connections = set()
main_loop = None

try:
    assistant = Assistant()
except Exception as e:
    logger.exception(f"Failed to initialize assistant: {e}")

class ChatRequest(BaseModel):
    message: str

@app.get("/status")
def get_status():
    if assistant:
        return {"status": "online", "model": "connected"}
    return {"status": "error", "message": "Assistant not initialized"}

@app.post("/chat")
def chat_endpoint(request: ChatRequest):
    """
    HTTP endpoint for basic chat (non-streaming).
    """
    if not assistant:
        return {"error": "Assistant not initialized"}
    
    responses = list(assistant.execute(request.message))
    final_response = next((r.get("response") for r in responses if r.get("type") == "final_response"), "")
    
    return {"response": final_response, "steps": responses}

# Helper to broadcast JSON messages thread-safely to all connected client UIs
def broadcast_to_ui(data):
    global main_loop
    if main_loop and active_connections:
        asyncio.run_coroutine_threadsafe(broadcast_all(data), main_loop)

async def broadcast_all(data):
    for ws in list(active_connections):
        try:
            await ws.send_json(data)
        except Exception:
            try:
                active_connections.remove(ws)
            except KeyError:
                pass

# Background Voice Thread Loop for Wake Word Activation
def background_voice_loop():
    global main_loop, assistant
    logger.info("[Voice Server] Background wake-word listening loop started.")
    
    # Wait for the main asyncio loop to be ready
    while main_loop is None:
        time.sleep(0.5)

    from speech import calibrate_mic, listen_mic, speak
    
    try:
        calibrate_mic(duration=1.0)
    except Exception as e:
        logger.error(f"[Voice Server] Failed to calibrate mic: {e}")

    if not assistant:
        try:
            assistant = Assistant()
        except Exception as e:
            logger.exception("[Voice Server] Failed to initialize Assistant in thread:")
            return

    logger.info("[Voice Server] Mic calibrated. Listening continuously for wake word ('Jarvis' / 'Jarvboi')...")
    
    while True:
        try:
            # 1. Listen for short phrases (energy threshold adjustment) to capture the wake word
            phrase = listen_mic(timeout=3, phrase_time_limit=3)
            if not phrase:
                continue

            clean_phrase = phrase.lower().strip()
            # Recognize "jarvis" or "jarvboi"
            if "jarvis" in clean_phrase or "jarvboi" in clean_phrase or "jarvis" in clean_phrase.replace(" ", ""):
                logger.info(f"[Voice Server] Wake word detected: '{clean_phrase}'")
                
                # Play futuristic confirmation chime (2 short high-pitched beeps)
                if winsound:
                    try:
                        winsound.Beep(1200, 80)
                        winsound.Beep(1600, 100)
                    except Exception:
                        pass

                # Notify UI of listening state
                broadcast_to_ui({"type": "status", "status": "listening"})
                broadcast_to_ui({"type": "system", "message": "🎙️ Jarvis Activated. Listening..."})

                # 2. Listen for the actual command
                command = listen_mic(timeout=8, phrase_time_limit=9)
                if not command:
                    logger.info("[Voice Server] No command detected after activation.")
                    if winsound:
                        try:
                            winsound.Beep(800, 150)
                        except Exception:
                            pass
                    broadcast_to_ui({"type": "status", "status": "idle"})
                    broadcast_to_ui({"type": "system", "message": "Voice Activation: Timeout / No command detected."})
                    continue

                logger.info(f"[Voice Server] Spoken Command received: '{command}'")
                
                # Append command to chat history and start processing animation
                broadcast_to_ui({"type": "voice_command", "message": command})
                broadcast_to_ui({"type": "status", "status": "processing"})

                # 3. Process spoken command through the assistant's modular logic
                final_response = ""
                try:
                    for step in assistant.execute(command):
                        # Broadcast thoughts, tools, results, and responses
                        broadcast_to_ui(step)
                        if step.get("type") == "final_response":
                            final_response = step.get("response", "")
                except Exception as e:
                    logger.exception("[Voice Server] Assistant execution failed:")
                    broadcast_to_ui({"type": "error", "message": f"Voice Pipeline Error: {e}"})

                # 4. Speak response vocally
                if final_response:
                    # Notify UI that Jarvis is speaking
                    broadcast_to_ui({"type": "status", "status": "speaking"})
                    speak(final_response)
                    
                    # Prevent microphone from recording the speaker playback by suspending capture
                    word_count = len(final_response.split())
                    speech_duration = max(2.0, (word_count / 2.5) + 0.8)
                    logger.info(f"[Voice Server] Suspended mic listening for {speech_duration:.2f}s during speech output.")
                    time.sleep(speech_duration)

                # Reset state back to idle
                broadcast_to_ui({"type": "status", "status": "idle"})
                
        except Exception as e:
            logger.exception("[Voice Server] Error in voice detection cycle:")
            time.sleep(1)

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket endpoint for real-time streaming of thoughts, tools, and responses.
    """
    await websocket.accept()
    if not assistant:
        await websocket.send_json({"type": "error", "message": "Assistant not initialized."})
        await websocket.close()
        return

    active_connections.add(websocket)
    logger.info(f"WebSocket client connected. Active clients: {len(active_connections)}")
    
    try:
        while True:
            data = await websocket.receive_text()
            
            try:
                payload = json.loads(data)
                user_message = payload.get("message", "")
            except json.JSONDecodeError:
                user_message = data
                
            if not user_message.strip():
                continue
                
            if user_message.lower() == "clear":
                assistant.memory.clear()
                await websocket.send_json({
                    "type": "system",
                    "message": "Conversation history cleared."
                })
                continue

            await websocket.send_json({"type": "status", "status": "processing"})
            
            try:
                for step in assistant.execute(user_message):
                    # Send execution steps to this websocket client
                    await websocket.send_json(step)
                    await asyncio.sleep(0.01)
                    
            except Exception as e:
                logger.exception("Error during execution loop")
                await websocket.send_json({"type": "error", "message": str(e)})

            await websocket.send_json({"type": "status", "status": "idle"})

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.exception("WebSocket error")
    finally:
        try:
            active_connections.remove(websocket)
        except KeyError:
            pass
        logger.info(f"WebSocket client disconnected. Active clients: {len(active_connections)}")

@app.on_event("startup")
async def startup_event():
    global main_loop
    main_loop = asyncio.get_running_loop()
    # Launch background thread for voice activation sidecar
    voice_thread = threading.Thread(target=background_voice_loop, daemon=True)
    voice_thread.start()

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("[FastAPI] Shutdown sequence initiated. Cleaning up active resources...")
    # Close any active WebSocket connections
    for ws in list(active_connections):
        try:
            await ws.close()
        except Exception:
            pass
    active_connections.clear()
    
    # Clean up temporary scratch assets (temp images and audio)
    try:
        scratch_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scratch")
        if os.path.exists(scratch_dir):
            for f in os.listdir(scratch_dir):
                if f.endswith((".mp3", ".png", ".jpg")):
                    try:
                        os.remove(os.path.join(scratch_dir, f))
                    except Exception:
                        pass
    except Exception:
        pass
    logger.info("[FastAPI] Clean shutdown completed successfully.")

if __name__ == "__main__":
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=False)
