import subprocess
from utils.logger import logger

def speak(text: str):
    """Natively speaks the given text offline on Windows using System.Speech.Synthesis."""
    if not text:
        return
        
    logger.info(f"[TTS Speak]: {text}")
    
    # Clean the text of brackets/markdown links to make speech sound clean
    clean_text = text.replace("[", "").replace("]", "").replace("(", " ").replace(")", " ")
    
    # Escape quotes for PowerShell string passing
    escaped_text = clean_text.replace('"', '`"').replace("'", "`'")
    
    # PowerShell command to initialize .NET Synthesizer and speak
    cmd = (
        "Add-Type -AssemblyName System.Speech; "
        f"$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$synth.Speak(\"{escaped_text}\")"
    )
    
    try:
        subprocess.run(
            ["powershell", "-Command", cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW  # Hide console window on Windows
        )
    except Exception as e:
        logger.error(f"TTS Speech synthesis failed: {e}")
