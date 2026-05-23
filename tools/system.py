import ctypes
from tools.registry import register_tool
from utils.logger import logger

@register_tool(
    name="system_media_play_pause",
    description="Sends a system-wide multimedia Play/Pause keyboard key event. Natively pauses or resumes any active audio/video playback (such as YouTube videos, Spotify, or media players) globally on Windows.",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def system_media_play_pause() -> str:
    """Pauses or plays any active media system-wide on Windows."""
    try:
        # Virtual Key Code for Media Play/Pause is 0xB3 (179)
        # Send key down event
        ctypes.windll.user32.keybd_event(0xB3, 0, 0, 0)
        # Send key up event
        ctypes.windll.user32.keybd_event(0xB3, 0, 2, 0)
        
        logger.info("Successfully dispatched global VK_MEDIA_PLAY_PAUSE keyboard event.")
        return "Successfully sent system-wide Play/Pause keyboard command to active media."
    except Exception as e:
        logger.exception("Failed to dispatch global media event:")
        return f"Failed to send system media event: {e}"
