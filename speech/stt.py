import speech_recognition as sr
from utils.logger import logger

import speech_recognition as sr
from utils.logger import logger

# Singleton instances to preserve calibration state across calls
_recognizer = None
_microphone = None
_calibrated = False

def get_stt_components():
    """Initializes and returns the shared Recognizer and Microphone singletons."""
    global _recognizer, _microphone
    if _recognizer is None:
        _recognizer = sr.Recognizer()
        _recognizer.dynamic_energy_threshold = True
    if _microphone is None:
        _microphone = sr.Microphone()
    return _recognizer, _microphone

def calibrate_mic(duration: float = 1.5):
    """Calibrates the microphone for ambient noise. Call this once at startup."""
    global _calibrated
    recognizer, microphone = get_stt_components()
    try:
        with microphone as source:
            logger.info(f"Calibrating microphone for ambient noise... ({duration} seconds)")
            print(f"\n[Calibrating microphone for {duration}s... Please stay quiet]", flush=True)
            recognizer.adjust_for_ambient_noise(source, duration=duration)
            _calibrated = True
            logger.info("Microphone calibration complete.")
            print("[Microphone calibrated successfully. Ready to listen!]", flush=True)
    except Exception as e:
        logger.error(f"Failed to calibrate microphone: {e}")

def listen_mic(timeout: int = 5, phrase_time_limit: int = 8, calibrate: bool = False) -> str:
    """Listens to the system's microphone, using the calibrated microphone, and returns transcribed text.
    
    Args:
        timeout: Maximum seconds to wait for a phrase to start.
        phrase_time_limit: Maximum seconds to let a phrase continue.
        calibrate: Force recalibration before listening.
    
    Returns:
        Transcribed string or empty string if listening fails or times out.
    """
    global _calibrated
    recognizer, microphone = get_stt_components()
    
    if calibrate or not _calibrated:
        calibrate_mic()
        
    try:
        with microphone as source:
            logger.info("🎙️ Listening...")
            print("\n[Listening... Speak now]", flush=True)
            
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            
            logger.info("Processing voice recording and transcribing...")
            print("[Processing Speech...]", flush=True)
            
            # Transcribe audio using Google Web Speech (Free, built-in, keyless, highly accurate)
            transcription = recognizer.recognize_google(audio)
            logger.info(f"Successfully transcribed speech: '{transcription}'")
            return transcription.strip()
            
    except sr.WaitTimeoutError:
        logger.debug("Speech recognition timed out (no speech detected).")
        return ""
    except sr.UnknownValueError:
        logger.debug("Speech recognition could not understand the audio stream.")
        return ""
    except sr.RequestError as e:
        logger.error(f"Speech recognition service request error: {e}")
        return ""
    except Exception as e:
        logger.exception("Unexpected error in speech-to-text pipeline:")
        return ""
