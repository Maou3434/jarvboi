import os
import sys
import time

# Add current directory to path to ensure local module imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Safely reconfigure standard output streams to handle unencodable characters
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')

from core.assistant import Assistant
from speech import speak, listen_mic, calibrate_mic
from utils.logger import logger

from config.settings import Settings

def print_voice_header():
    """Prints a beautiful CLI header for the voice assistant."""
    provider = Settings.LLM_PROVIDER.upper()
    model = Settings.GEMINI_MODEL if Settings.LLM_PROVIDER == "gemini" else Settings.OLLAMA_MODEL
    print("=" * 60)
    print(" " * 15 + "JARVBOI - Voice-Activated Assistant")
    print(" " * 12 + f"Powered by {provider} ({model})")
    print("=" * 60)
    print("Commands: Speak naturally! Say 'exit' or 'goodbye' to quit.")
    print("-" * 60)

def main():
    print_voice_header()
    
    # Vocally introduce startup
    startup_greeting = "Hello! I am Jarvboi, your voice assistant. I am ready to help you control your laptop."
    print(f"\nJarvboi: {startup_greeting}")
    speak(startup_greeting)
    
    # Calibrate microphone once at startup
    calibrate_mic(duration=1.5)
    
    try:
        assistant = Assistant()
    except Exception as e:
        logger.exception("Failed to initialize assistant:")
        error_msg = f"Failed to initialize assistant. Please check your config/API keys. Error: {e}"
        print(f"\n[ERROR] {error_msg}")
        speak(error_msg)
        sys.exit(1)
        
    print("\n[Voice chat loop initialized. Ready for your command!]")
    speak("I am ready for your command.")
    
    while True:
        try:
            # 1. Listen for user voice command
            user_speech = listen_mic(timeout=10, phrase_time_limit=10)
            
            if not user_speech:
                # Silent timeout, loop back to listen again
                continue
                
            print(f"\nYou: {user_speech}", flush=True)
            
            # Check exit conditions
            clean_speech = user_speech.lower().strip().replace(".", "").replace(",", "")
            if clean_speech in ["exit", "quit", "goodbye", "bye bye", "stop listening"]:
                exit_msg = "Goodbye! Turning off voice controls."
                print(f"\nJarvboi: {exit_msg}")
                speak(exit_msg)
                break
                
            print("\n[Processing Voice Command...]", flush=True)
            
            # Execute assistant pipeline
            final_response = ""
            for step in assistant.execute(user_speech):
                step_type = step.get("type")
                
                if step_type == "thought":
                    thought = step.get("thought", "")
                    if thought:
                        print(f"\n[Thinking]: {thought}", flush=True)
                        
                elif step_type == "tool_start":
                    name = step.get("tool_name")
                    args = step.get("tool_args")
                    print(f"[Calling Tool]: {name} with args {args}", flush=True)
                    
                elif step_type == "tool_end":
                    name = step.get("tool_name")
                    result = step.get("result")
                    print(f"[Tool Response]: {result}", flush=True)
                    
                elif step_type == "final_response":
                    final_response = step.get("response", "")
                    print(f"\nJarvboi: {final_response}", flush=True)
            
            # Speak the final response vocally
            if final_response:
                speak(final_response)
                
        except KeyboardInterrupt:
            exit_msg = "Goodbye!"
            print(f"\n\nJarvboi: {exit_msg}")
            speak(exit_msg)
            break
        except Exception as e:
            logger.exception("An error occurred in the voice control loop:")
            error_msg = f"Sorry, I encountered an error: {e}"
            print(f"\nJarvboi: {error_msg}")
            speak(error_msg)
            time.sleep(1)

if __name__ == "__main__":
    main()
