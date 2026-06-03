import os
import base64
import asyncio
import subprocess
import edge_tts
from utils.logger import logger

def generate_speech_base64_sync(text: str, voice: str = "en-GB-RyanNeural") -> str:
    """Synchronously generates neural speech using edge-tts and returns a base64 encoded MP3 string."""
    try:
        # Create a new local event loop to execute the asynchronous edge-tts pipeline synchronously
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        temp_file = "temp_voice.mp3"
        communicate = edge_tts.Communicate(text, voice)
        loop.run_until_complete(communicate.save(temp_file))
        loop.close()
        
        if os.path.exists(temp_file):
            with open(temp_file, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("utf-8")
            try:
                os.remove(temp_file)
            except Exception:
                pass
            return encoded
    except Exception as e:
        logger.error(f"Failed to generate neural base64 speech: {e}")
    return ""

def play_mp3_local_nonblocking(file_path: str):
    """Plays an MP3 file locally on Windows asynchronously in a background subprocess."""
    escaped_path = os.path.abspath(file_path).replace("'", "''")
    
    # Using PresentationCore assemblies standard Media Player
    cmd = (
        "Add-Type -AssemblyName PresentationCore; "
        "$player = New-Object System.Windows.Media.MediaPlayer; "
        f"$player.Open('{escaped_path}'); "
        "$player.Play(); "
        "while ($player.NaturalDuration.HasTimeSpan -eq $false) { Start-Sleep -m 20 }; "
        "Start-Sleep -m [int]($player.NaturalDuration.TimeSpan.TotalMilliseconds + 200)"
    )
    
    try:
        subprocess.Popen(
            ["powershell", "-Command", cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW  # Run completely hidden on Windows
        )
        logger.info(f"[TTS] Background local PresentationCore playback process launched for: {file_path}")
    except Exception as e:
        logger.error(f"Failed to spawn background local playback process: {e}")

def speak(text: str):
    """Natively speaks the given text using premium neural TTS (en-GB-RyanNeural) asynchronously."""
    if not text:
        return
        
    logger.info(f"[TTS Speak Input]: {text}")
    
    # Clean the text of brackets/markdown links to make speech sound clean and fluent
    clean_text = text.replace("[", "").replace("]", "").replace("(", " ").replace(")", " ")
    
    # Detect dynamically if there is a running WebSocket server with active front-end UI connections
    has_ui_client = False
    try:
        # Avoid circular imports by importing locally
        from api import active_connections
        if active_connections:
            has_ui_client = True
    except Exception:
        pass
        
    # Generate the high-quality base64 neural audio stream
    base64_audio = generate_speech_base64_sync(clean_text)
    
    if not base64_audio:
        logger.error("[TTS] Failed to generate base64 audio for speech.")
        return
        
    if has_ui_client:
        # Electron front-end is connected. Broadcast the audio over WebSockets so the client plays it natively
        try:
            from api import broadcast_to_ui
            logger.info("[TTS] Streaming premium neural voice over WebSockets to client UI.")
            broadcast_to_ui({"type": "speak", "audio": base64_audio})
        except Exception as ws_err:
            logger.error(f"[TTS] Failed to stream over WebSockets: {ws_err}")
    else:
        # CLI standalone mode. Play locally in a background non-blocking thread
        logger.info("[TTS] Operating in CLI standalone mode. Triggering async local playback.")
        try:
            # Save the raw audio stream to a temporary scratch file
            scratch_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scratch")
            os.makedirs(scratch_dir, exist_ok=True)
            temp_path = os.path.join(scratch_dir, "tts_output.mp3")
            
            with open(temp_path, "wb") as f:
                f.write(base64.b64decode(base64_audio))
                
            play_mp3_local_nonblocking(temp_path)
        except Exception as local_err:
            logger.error(f"[TTS] Native local audio playback failed: {local_err}")
