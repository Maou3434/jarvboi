from services.speech_service import SpeechService

_speech_service = SpeechService()

def speak(text: str):
    _speech_service.speak(text)

def listen_mic(timeout: int = 5, phrase_time_limit: int = 8, calibrate: bool = False) -> str:
    return _speech_service.listen_mic(timeout=timeout, phrase_time_limit=phrase_time_limit, force_calibrate=calibrate)

def calibrate_mic(duration: float = 1.0):
    _speech_service.calibrate_mic(duration=duration)
