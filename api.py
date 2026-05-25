import os
import sys
import json
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Ensure local module imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.assistant import Assistant
from utils.logger import logger

app = FastAPI(title="JARVBOI API")

# Enable CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Assistant (we keep a single instance for context memory)
try:
    assistant = Assistant()
except Exception as e:
    logger.exception(f"Failed to initialize assistant: {e}")
    assistant = None

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
    Useful if WebSockets are not used.
    """
    if not assistant:
        return {"error": "Assistant not initialized"}
    
    responses = list(assistant.execute(request.message))
    final_response = next((r.get("response") for r in responses if r.get("type") == "final_response"), "")
    
    return {"response": final_response, "steps": responses}

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

    try:
        while True:
            data = await websocket.receive_text()
            
            try:
                # Expecting JSON or plain text
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

            # We must run the synchronous assistant.execute generator
            # For better async compatibility, ideally we'd run this in a threadpool, 
            # but for now we iterate over it directly. If it blocks the event loop, 
            # we should use run_in_executor. Since it's a local bot, it's acceptable for now.
            
            # Send an acknowledgement
            await websocket.send_json({"type": "status", "status": "processing"})
            
            try:
                for step in assistant.execute(user_message):
                    # step is a dictionary yielded by the assistant
                    await websocket.send_json(step)
                    # Yield control to the event loop so messages send immediately
                    await asyncio.sleep(0.01)
                    
            except Exception as e:
                logger.exception("Error during execution loop")
                await websocket.send_json({"type": "error", "message": str(e)})

            await websocket.send_json({"type": "status", "status": "idle"})

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.exception("WebSocket error")

if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
