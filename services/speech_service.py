import os
import base64
import asyncio
import subprocess
import threading
import speech_recognition as sr
import edge_tts
from typing import Optional, Tuple, Any
from config.settings import Settings
from utils.logger import logger

class SpeechService:
    """Consolidated Speech service handling low-latency Speech-To-Text (STT) 
    and neural Text-To-Speech (TTS) with playback interruption support.
    """
    
    def __init__(self, event_bus=None):
        self.event_bus = event_bus
        self.interrupted = False
        
        # STT singletons
        self._recognizer = None
        self._microphone = None
        self._calibrated = False
        self._whisper_model = None
        
        # TTS active state
        self._active_tts_process = None
        
        if self.event_bus:
            self.event_bus.subscribe("interrupt", self._on_interrupt)
            
    def _on_interrupt(self, data=None):
        """Callback executing when interrupt events are emitted on the bus."""
        logger.info("[SpeechService] Interruption signal received.")
        self.interrupted = True
        self.stop_local_playback()
        
    def get_stt_components(self) -> Tuple[sr.Recognizer, sr.Microphone]:
        """Initializes and returns shared speech recognition singletons."""
        if self._recognizer is None:
            self._recognizer = sr.Recognizer()
            self._recognizer.dynamic_energy_threshold = False
            self._recognizer.energy_threshold = 300
            self._recognizer.pause_threshold = 0.5
            self._recognizer.phrase_threshold = 0.3
            self._recognizer.non_speaking_duration = 0.3
        if self._microphone is None:
            self._microphone = sr.Microphone()
        return self._recognizer, self._microphone

    def get_whisper_model(self) -> Any:
        """Lazily initializes and returns local Faster-Whisper model singleton."""
        if self._whisper_model is None:
            try:
                from faster_whisper import WhisperModel
                model_size = Settings.WHISPER_MODEL_SIZE
                logger.info(f"[SpeechService] Initializing local Faster-Whisper model ({model_size})...")
                self._whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
                logger.info("[SpeechService] Faster-Whisper model loaded successfully.")
            except Exception as e:
                logger.error(f"[SpeechService] Failed to load Faster-Whisper: {e}. Falling back to Google Web Speech API.")
                self._whisper_model = False
        return self._whisper_model

    def calibrate_mic(self, duration: float = 1.0):
        """Calibrates microphone for ambient noise levels once at startup."""
        recognizer, microphone = self.get_stt_components()
        try:
            with microphone as source:
                logger.info(f"[SpeechService] Calibrating microphone for ambient noise... ({duration}s)")
                recognizer.adjust_for_ambient_noise(source, duration=duration)
                self._calibrated = True
                logger.info("[SpeechService] Microphone calibration complete.")
        except Exception as e:
            logger.error(f"[SpeechService] Failed to calibrate microphone: {e}")

    def listen_mic(self, timeout: int = 5, phrase_time_limit: int = 8, force_calibrate: bool = False) -> Optional[str]:
        """Listens to microphone, transcribes audio, and returns text."""
        recognizer, microphone = self.get_stt_components()
        
        if force_calibrate or not self._calibrated:
            self.calibrate_mic()
            
        try:
            with microphone as source:
                logger.info("[SpeechService] Microphone listening...")
                audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
                logger.info("[SpeechService] Transcription processing started...")
                
                # Check backend STT setting
                if Settings.STT_BACKEND == "whisper":
                    whisper_model = self.get_whisper_model()
                    if whisper_model:
                        # Write audio data to WAV scratch file
                        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                        scratch_dir = os.path.join(project_root, "scratch")
                        os.makedirs(scratch_dir, exist_ok=True)
                        temp_wav_path = os.path.join(scratch_dir, "temp_stt.wav")
                        
                        with open(temp_wav_path, "wb") as f:
                            f.write(audio.get_wav_data())
                            
                        try:
                            segments, info = whisper_model.transcribe(
                                temp_wav_path,
                                beam_size=5,
                                vad_filter=True,
                                vad_parameters=dict(min_speech_duration_ms=250)
                            )
                            transcription_text = " ".join([segment.text for segment in segments]).strip()
                            logger.info(f"[SpeechService] Transcribed (Whisper): '{transcription_text}'")
                            return transcription_text
                        finally:
                            if os.path.exists(temp_wav_path):
                                try:
                                    os.remove(temp_wav_path)
                                except Exception:
                                    pass
                    else:
                        # Fallback to Google
                        transcription = recognizer.recognize_google(audio, language=Settings.STT_LANGUAGE)
                        logger.info(f"[SpeechService] Transcribed (Google Fallback): '{transcription}'")
                        return transcription.strip()
                else:
                    # Google Web Speech API
                    transcription = recognizer.recognize_google(audio, language=Settings.STT_LANGUAGE)
                    logger.info(f"[SpeechService] Transcribed (Google): '{transcription}'")
                    return transcription.strip()
                    
        except sr.WaitTimeoutError:
            logger.debug("[SpeechService] Speech recognition timed out.")
            return None
        except sr.UnknownValueError:
            logger.debug("[SpeechService] Speech recognition could not understand audio.")
            return ""
        except sr.RequestError as e:
            logger.error(f"[SpeechService] Request error in speech recognition: {e}")
            return ""
        except Exception as e:
            logger.exception("[SpeechService] Unexpected STT error:")
            return ""

    def generate_speech_base64(self, text: str, voice: str = "en-GB-RyanNeural") -> str:
        """Generates neural speech base64 MP3 stream using edge-tts synchronously."""
        try:
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
            logger.error(f"[SpeechService] Failed to generate TTS audio: {e}")
        return ""

    def play_mp3_local_nonblocking(self, file_path: str):
        """Plays an MP3 file locally in a hidden Windows subprocess."""
        escaped_path = os.path.abspath(file_path).replace("'", "''")
        cmd = (
            "Add-Type -AssemblyName PresentationCore; "
            "$player = New-Object System.Windows.Media.MediaPlayer; "
            f"$player.Open('{escaped_path}'); "
            "$player.Play(); "
            "while ($player.NaturalDuration.HasTimeSpan -eq $false) { Start-Sleep -m 20 }; "
            "Start-Sleep -m [int]($player.NaturalDuration.TimeSpan.TotalMilliseconds + 200)"
        )
        
        try:
            self.stop_local_playback()
            self._active_tts_process = subprocess.Popen(
                ["powershell", "-Command", cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            logger.info(f"[SpeechService] Background local audio playback launched.")
        except Exception as e:
            logger.error(f"[SpeechService] Failed to play local audio: {e}")

    def stop_local_playback(self):
        """Kills any active local media player subprocesses to interrupt playback."""
        if self._active_tts_process:
            try:
                self._active_tts_process.terminate()
                self._active_tts_process.wait(timeout=0.5)
                logger.info("[SpeechService] Local speech playback process stopped.")
            except Exception:
                pass
            self._active_tts_process = None

    def speak(self, text: str, has_ui_client: bool = False):
        """Speaks text using edge-tts. Publishes 'speak_audio' if HUD UI is connected."""
        if not text:
            return
            
        self.interrupted = False
        logger.info(f"[SpeechService Speak]: {text}")
        
        clean_text = text.replace("[", "").replace("]", "").replace("(", " ").replace(")", " ")
        base64_audio = self.generate_speech_base64(clean_text)
        
        if not base64_audio:
            return
            
        if self.event_bus:
            # Notify event bus of speech audio availability
            self.event_bus.publish("speak_audio", {"audio": base64_audio})
            
        if not has_ui_client:
            # Standalone CLI mode - play locally
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            scratch_dir = os.path.join(project_root, "scratch")
            os.makedirs(scratch_dir, exist_ok=True)
            temp_path = os.path.join(scratch_dir, "tts_output.mp3")
            
            try:
                with open(temp_path, "wb") as f:
                    f.write(base64.b64decode(base64_audio))
                self.play_mp3_local_nonblocking(temp_path)
            except Exception as e:
                logger.error(f"[SpeechService] Local playback failed: {e}")
