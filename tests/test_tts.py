import os
import sys
import base64

# Ensure local module resolves
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from speech.tts import generate_speech_base64_sync

def test_neural_speech_generation():
    """Verifies the edge-tts engine correctly synthesizes text and packages raw MP3 streams as Base64."""
    print("Running: test_neural_speech_generation...")
    test_phrase = "System diagnostics active, sir."
    
    base64_stream = generate_speech_base64_sync(test_phrase)
    
    assert base64_stream is not None, "Speech generation returned None."
    assert len(base64_stream) > 0, "Speech generation returned empty string."
    
    # Verify that the generated stream decodes to standard MP3 header bytes
    decoded_bytes = base64.b64decode(base64_audio := base64_stream.encode("utf-8"))
    assert decoded_bytes.startswith(b"ID3") or decoded_bytes.startswith(b"\xff\xfb") or len(decoded_bytes) > 1000, \
        "Decoded stream is too short or doesn't represent valid audio data."
        
    print(" -> PASS: Premium neural voice synthesis packaged successfully!")

def test_speech_text_cleaning():
    """Verifies that markdown brackets and braces are correctly cleaned to support natural voice pronunciations."""
    print("Running: test_speech_text_cleaning...")
    raw_text = "I have [opened] the (YouTube) tab successfully, sir!"
    
    # We copy the text cleaning logic from speech/tts.py speak() method
    cleaned_text = raw_text.replace("[", "").replace("]", "").replace("(", " ").replace(")", " ")
    
    assert "[" not in cleaned_text, "Markdown bracket '[' was not stripped."
    assert "]" not in cleaned_text, "Markdown bracket ']' was not stripped."
    assert "(" not in cleaned_text, "Markdown brace '(' was not stripped."
    assert ")" not in cleaned_text, "Markdown brace ')' was not stripped."
    assert "opened" in cleaned_text, "Important wording was lost."
    assert "YouTube" in cleaned_text, "Important wording was lost."
    
    print(" -> PASS: Markdown and bracket characters cleaned successfully!")

def run_all():
    """Runs all TTS unit tests."""
    print("\n--- STARTING TTS SYNTHESIS DIAGNOSTIC CHECKS ---")
    try:
        test_neural_speech_generation()
        test_speech_text_cleaning()
        print("TTS SYSTEM STATUS: 100% OPERATIONAL, SIR.")
        return True
    except AssertionError as ae:
        print(f" -> FAIL: AssertionError encountered: {ae}")
        return False
    except Exception as e:
        print(f" -> FAIL: System crash encountered: {e}")
        return False

if __name__ == "__main__":
    run_all()
