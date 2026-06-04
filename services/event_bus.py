import asyncio
import threading
from typing import Callable, Dict, List, Any, Optional
from utils.logger import logger

class EventBus:
    """A thread-safe Event Bus that supports both synchronous and asynchronous subscribers."""
    
    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        
    def set_async_loop(self, loop: asyncio.AbstractEventLoop):
        """Associates the main asyncio event loop to dispatch async coroutines thread-safely."""
        self._loop = loop
        logger.debug(f"[EventBus] Main asyncio event loop associated.")
        
    def subscribe(self, event_type: str, callback: Callable):
        """Subscribes a callback to an event type."""
        with self._lock:
            if event_type not in self._listeners:
                self._listeners[event_type] = []
            if callback not in self._listeners[event_type]:
                self._listeners[event_type].append(callback)
                logger.debug(f"[EventBus] Callback '{callback.__name__}' subscribed to '{event_type}'")
                
    def unsubscribe(self, event_type: str, callback: Callable):
        """Unsubscribes a callback from an event type."""
        with self._lock:
            if event_type in self._listeners and callback in self._listeners[event_type]:
                self._listeners[event_type].remove(callback)
                logger.debug(f"[EventBus] Callback '{callback.__name__}' unsubscribed from '{event_type}'")
                
    def publish(self, event_type: str, data: Any = None):
        """Publishes an event thread-safely to all registered subscribers."""
        print(f"[EventBus PRINT] Publishing event '{event_type}', active listeners: {list(self._listeners.keys())}")
        logger.debug(f"[EventBus] Publishing event '{event_type}'")
        with self._lock:
            listeners = list(self._listeners.get(event_type, []))
            
        print(f"[EventBus PRINT] Found listeners for '{event_type}': {[l.__name__ for l in listeners]}")
        for listener in listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    # Async callback
                    if self._loop and self._loop.is_running():
                        asyncio.run_coroutine_threadsafe(listener(data), self._loop)
                    else:
                        logger.warning(
                            f"[EventBus] Async listener '{listener.__name__}' for '{event_type}' "
                            f"skipped because the event loop is not running or not set."
                        )
                else:
                    # Sync callback
                    listener(data)
            except Exception as e:
                logger.error(f"[EventBus] Error executing listener '{listener.__name__}' on event '{event_type}': {e}")
