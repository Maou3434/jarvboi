import os
import sys
# Add current directory to path to ensure local module imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Safely reconfigure standard output streams to handle unencodable characters (e.g. emojis on CP1252 terminals)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')

from core.assistant import Assistant
from utils.logger import logger

def print_header():
    """Prints a beautiful CLI header for the assistant."""
    print("=" * 60)
    print(" " * 15 + "JARVBOI - Modular Local AI Assistant")
    print(" " * 14 + "Phase 1 Active | Powered by Ollama & Mistral")
    print("=" * 60)
    print("Type 'exit' to quit, 'clear' to reset conversation history.")
    print("-" * 60)

def main():
    # Pre-checks: Ensure Ollama is running is handled by OllamaLLM client itself
    try:
        assistant = Assistant()
    except Exception as e:
        print(f"\n[ERROR] Failed to initialize assistant: {e}")
        print("Please make sure Ollama is installed and running locally.")
        sys.exit(1)
        
    print_header()
    
    while True:
        try:
            user_input = input("\nYou: ").strip()
            
            if not user_input:
                continue
                
            if user_input.lower() == "exit":
                print("\nGoodbye!")
                break
                
            if user_input.lower() == "clear":
                assistant.memory.clear()
                print("\nAssistant: Conversation history cleared!")
                continue
                
            print("\n[Processing...]", flush=True)
            
            # Execute assistant pipeline
            for step in assistant.execute(user_input):
                step_type = step.get("type")
                
                if step_type == "thought":
                    thought = step.get("thought", "")
                    if thought:
                        # Print thought in a muted, clean format
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
                    response = step.get("response", "")
                    print(f"\nAssistant: {response}", flush=True)
                    
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            logger.exception("An unhandled error occurred in the chat loop:")
            print(f"\nAssistant: Sorry, I encountered an internal error: {e}")

if __name__ == "__main__":
    main()