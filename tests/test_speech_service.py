import os
import sys
import unittest
from unittest.mock import MagicMock, patch, mock_open
import base64

# Ensure local module resolves
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.speech_service import SpeechService
from services.event_bus import EventBus
from config.settings import Settings
import speech_recognition as sr

class MockCommunicate:
    def __init__(self, text, voice):
        self.text = text
        self.voice = voice
    async def stream(self):
        yield {"type": "audio", "data": b"ID3" + b"\x00" * 100}

# Mock edge_tts Communicator
import edge_tts
edge_tts.Communicate = MockCommunicate

class TestSpeechService(unittest.TestCase):

    def setUp(self):
        self.event_bus = EventBus()
        self.speech_service = SpeechService(event_bus=self.event_bus)

    def tearDown(self):
        self.speech_service.stop_local_playback()

    @patch("speech_recognition.Microphone")
    def test_calibrate_mic(self, mock_mic_cls):
        """Verifies that calibrate_mic adjusts the threshold based on ambient noise."""
        mock_mic = MagicMock()
        mock_mic_cls.return_value = mock_mic
        
        # Mock Microphone context manager
        mock_mic.__enter__.return_value = "mock_source"
        
        # Mock adjust_for_ambient_noise
        recognizer_mock = MagicMock()
        with patch.object(self.speech_service, "get_stt_components", return_value=(recognizer_mock, mock_mic)):
            self.speech_service.calibrate_mic(duration=0.5)
            
            recognizer_mock.adjust_for_ambient_noise.assert_called_once_with("mock_source", duration=0.5)
            self.assertTrue(self.speech_service._calibrated)

    @patch("speech_recognition.Microphone")
    @patch("urllib.request.urlopen")
    def test_listen_mic_google_success(self, mock_urlopen, mock_mic_cls):
        """Verifies successful speech recognition using Google Web Speech API."""
        mock_mic = MagicMock()
        mock_mic_cls.return_value = mock_mic
        mock_mic.__enter__.return_value = "mock_source"
        
        recognizer_mock = MagicMock()
        # Mock listen returning a dummy audio object
        mock_audio = MagicMock()
        recognizer_mock.listen.return_value = mock_audio
        # Mock recognize_google returning text
        recognizer_mock.recognize_google.return_value = "hello jarvis"
        
        with patch.object(self.speech_service, "get_stt_components", return_value=(recognizer_mock, mock_mic)):
            # Set STT backend to google
            with patch.object(Settings, "STT_BACKEND", "google"):
                self.speech_service._calibrated = True
                result = self.speech_service.listen_mic()
                
                recognizer_mock.listen.assert_called_once()
                recognizer_mock.recognize_google.assert_called_once_with(mock_audio, language=Settings.STT_LANGUAGE)
                self.assertEqual(result, "hello jarvis")

    @patch("speech_recognition.Microphone")
    def test_listen_mic_whisper_success(self, mock_mic_cls):
        """Verifies successful speech recognition using Whisper backend."""
        mock_mic = MagicMock()
        mock_mic_cls.return_value = mock_mic
        mock_mic.__enter__.return_value = "mock_source"
        
        recognizer_mock = MagicMock()
        mock_audio = MagicMock()
        mock_audio.get_wav_data.return_value = b"RIFF...wav_data"
        recognizer_mock.listen.return_value = mock_audio
        
        # Mock Whisper Model
        mock_whisper = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "transcribed by whisper"
        mock_whisper.transcribe.return_value = ([mock_segment], None)
        
        with patch.object(self.speech_service, "get_stt_components", return_value=(recognizer_mock, mock_mic)):
            with patch.object(self.speech_service, "get_whisper_model", return_value=mock_whisper):
                with patch.object(Settings, "STT_BACKEND", "whisper"):
                    self.speech_service._calibrated = True
                    
                    # Mock open to write temp wav file
                    m_open = mock_open()
                    # Mock os.remove and os.path.exists to prevent file system operations
                    with patch("builtins.open", m_open), patch("os.remove") as mock_remove, patch("os.path.exists", return_value=True):
                        result = self.speech_service.listen_mic()
                        
                        mock_whisper.transcribe.assert_called_once()
                        self.assertEqual(result, "transcribed by whisper")
                        mock_remove.assert_called_once()

    @patch("speech_recognition.Microphone")
    def test_listen_mic_whisper_fallback(self, mock_mic_cls):
        """Verifies that Whisper falls back to Google if Whisper initialization returns False/fails."""
        mock_mic = MagicMock()
        mock_mic_cls.return_value = mock_mic
        mock_mic.__enter__.return_value = "mock_source"
        
        recognizer_mock = MagicMock()
        mock_audio = MagicMock()
        recognizer_mock.listen.return_value = mock_audio
        recognizer_mock.recognize_google.return_value = "google output"
        
        with patch.object(self.speech_service, "get_stt_components", return_value=(recognizer_mock, mock_mic)):
            # get_whisper_model returns False when loading fails
            with patch.object(self.speech_service, "get_whisper_model", return_value=False):
                with patch.object(Settings, "STT_BACKEND", "whisper"):
                    self.speech_service._calibrated = True
                    result = self.speech_service.listen_mic()
                    
                    recognizer_mock.recognize_google.assert_called_once_with(mock_audio, language=Settings.STT_LANGUAGE)
                    self.assertEqual(result, "google output")

    @patch("speech_recognition.Microphone")
    def test_listen_mic_timeout_and_exceptions(self, mock_mic_cls):
        """Verifies error handling when listening times out or fails to recognize."""
        mock_mic = MagicMock()
        mock_mic_cls.return_value = mock_mic
        mock_mic.__enter__.return_value = "mock_source"
        
        recognizer_mock = MagicMock()
        self.speech_service._calibrated = True
        
        with patch.object(self.speech_service, "get_stt_components", return_value=(recognizer_mock, mock_mic)):
            with patch.object(Settings, "STT_BACKEND", "google"):
                # Case 1: Timeout
                recognizer_mock.listen.side_effect = sr.WaitTimeoutError()
                result = self.speech_service.listen_mic()
                self.assertIsNone(result)
                
                # Case 2: Unknown Value (ambient noise / unrecognized speech)
                recognizer_mock.listen.side_effect = None
                recognizer_mock.listen.return_value = MagicMock()
                recognizer_mock.recognize_google.side_effect = sr.UnknownValueError()
                result = self.speech_service.listen_mic()
                self.assertEqual(result, "")
                
                # Case 3: Request Error (network offline, etc)
                recognizer_mock.recognize_google.side_effect = sr.RequestError("No connection")
                result = self.speech_service.listen_mic()
                self.assertEqual(result, "")

    def test_generate_speech_base64(self):
        """Verifies neural base64 audio is generated and correct header bytes are present."""
        base64_data = self.speech_service.generate_speech_base64("hello")
        self.assertIsNotNone(base64_data)
        decoded = base64.b64decode(base64_data)
        self.assertTrue(decoded.startswith(b"ID3"))

    @patch("subprocess.Popen")
    def test_play_mp3_local_nonblocking(self, mock_popen):
        """Verifies local audio player triggers PowerShell command execution."""
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc
        
        self.speech_service.play_mp3_local_nonblocking("test.mp3")
        
        # Verify Popen called with powershell execution
        mock_popen.assert_called_once()
        cmd_args = mock_popen.call_args[0][0]
        self.assertEqual(cmd_args[0], "powershell")
        self.assertIn("System.Windows.Media.MediaPlayer", cmd_args[2])
        self.assertEqual(self.speech_service._active_tts_process, mock_proc)

    @patch("subprocess.Popen")
    def test_stop_local_playback(self, mock_popen):
        """Verifies stop_local_playback terminates running Powershell process."""
        mock_proc = MagicMock()
        self.speech_service._active_tts_process = mock_proc
        
        self.speech_service.stop_local_playback()
        
        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once_with(timeout=0.5)
        self.assertIsNone(self.speech_service._active_tts_process)

    @patch("subprocess.Popen")
    def test_speak_cli_mode(self, mock_popen):
        """Verifies speak in CLI mode (has_ui_client=False) writes file and triggers player."""
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc
        
        m_open = mock_open()
        
        # Subscribe a mock event handler
        mock_event_handler = MagicMock()
        mock_event_handler.__name__ = "mock_event_handler"
        self.event_bus.subscribe("speak_audio", mock_event_handler)
        
        with patch("builtins.open", m_open), patch("os.makedirs"):
            self.speech_service.speak("text representation", has_ui_client=False)
            
            # Verify event bus still broadcasts speak_audio for any connected frontend
            mock_event_handler.assert_called_once()
            event_data = mock_event_handler.call_args[0][0]
            self.assertIn("audio", event_data)
            
            # Verify temporary file written
            m_open.assert_called_once()
            handle = m_open()
            handle.write.assert_called_once()
            
            # Verify playback launched
            mock_popen.assert_called_once()

    def test_interruption_event(self):
        """Verifies that publishing interrupt on event bus terminates local playback and sets flag."""
        mock_proc = MagicMock()
        self.speech_service._active_tts_process = mock_proc
        
        # Trigger event bus publish
        self.event_bus.publish("interrupt")
        
        self.assertTrue(self.speech_service.interrupted)
        mock_proc.terminate.assert_called_once()

def run_all() -> bool:
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSpeechService)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()

if __name__ == "__main__":
    run_all()
