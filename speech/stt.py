import os
import speech_recognition as sr
from utils.logger import logger
from config.settings import Settings

# Singleton instances to preserve calibration and Whisper states across calls
_recognizer = None
_microphone = None
_calibrated = False
_whisper_model = None

def get_stt_components():
    """Initializes and returns the shared Recognizer and Microphone singletons."""
    global _recognizer, _microphone
    if _recognizer is None:
        _recognizer = sr.Recognizer()
        _recognizer.dynamic_energy_threshold = True
    if _microphone is None:
        _microphone = sr.Microphone()
    return _recognizer, _microphone

def get_whisper_model():
    """Lazily initializes and returns the local Faster-Whisper model singleton."""
    global _whisper_model
    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel
            model_size = Settings.WHISPER_MODEL_SIZE
            logger.info(f"Initializing local Faster-Whisper model ({model_size})...")
            print(f"[Loading local Whisper model '{model_size}'... Please wait]", flush=True)
            
            # Using CPU with float32/int8 depending on what is available/fast
            # tiny.en is default, which runs super fast on cpu with int8
            _whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
            logger.info("Faster-Whisper model loaded successfully.")
            print("[Local Whisper model loaded successfully. Ready!]", flush=True)
        except Exception as e:
            logger.exception("Failed to load Faster-Whisper model. Falling back to Google Web Speech API.")
            print(f"[Whisper Load Error: {e}. Falling back to Google Web Speech API]", flush=True)
            _whisper_model = False  # Mark as False to indicate load failure
    return _whisper_model

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
            logger.info("[Mic] Listening...")
            print("\n[Listening... Speak now]", flush=True)
            
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            
            logger.info("Processing voice recording and transcribing...")
            print("[Processing Speech...]", flush=True)
            
            # Select STT backend based on settings
            if Settings.STT_BACKEND == "whisper":
                whisper_model = get_whisper_model()
                
                # If whisper model loaded successfully, use it
                if whisper_model:
                    # Write speech recognition AudioData to a temporary WAV file
                    scratch_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scratch")
                    os.makedirs(scratch_dir, exist_ok=True)
                    temp_wav_path = os.path.join(scratch_dir, "temp_stt.wav")
                    
                    with open(temp_wav_path, "wb") as f:
                        f.write(audio.get_wav_data())
                        
                    try:
                        logger.info("Running transcription via Faster-Whisper...")
                        segments, info = whisper_model.transcribe(temp_wav_path, beam_size=5)
                        
                        transcription_text = ""
                        for segment in segments:
                            transcription_text += segment.text + " "
                            
                        transcription = transcription_text.strip()
                        logger.info(f"Successfully transcribed speech (Whisper): '{transcription}'")
                        return transcription
                    finally:
                        if os.path.exists(temp_wav_path):
                            try:
                                os.remove(temp_wav_path)
                            except Exception:
                                pass
                else:
                    # Fallback to Google if Whisper failed to load
                    logger.info("Whisper was not initialized. Falling back to Google Web Speech API...")
                    transcription = recognizer.recognize_google(audio)
                    logger.info(f"Successfully transcribed speech (Google fallback): '{transcription}'")
                    return transcription.strip()
            else:
                # Use Google Web Speech
                transcription = recognizer.recognize_google(audio)
                logger.info(f"Successfully transcribed speech (Google): '{transcription}'")
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
