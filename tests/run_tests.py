import os
import sys

# Ensure local module resolves
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import test_tts
import test_desktop_agent
import test_assistant
import test_skills
import test_db
import test_memory_v2

def print_stark_header():
    """Prints a high-fidelity Stark Industries diagnostic header in the console."""
    print("=" * 70)
    print(" " * 12 + "⚡ STARK INDUSTRIES DIAGNOSTICS & TEST RUNNER ⚡")
    print(" " * 19 + "JARVIS SYSTEMS INTEGRITY VALIDATIONS")
    print("=" * 70)

def main():
    print_stark_header()
    
    # Track diagnostic outcomes
    checks = [
        ("TTS & Premium Speech Synthesis Module", test_tts.run_all),
        ("OS Automation & Viewport Grids Module", test_desktop_agent.run_all),
        ("Jarvis Prompt Coordination & LLM Parsers", test_assistant.run_all),
        ("Jarvis Automatic Skill Writer & Registry Module", test_skills.run_all),
        ("Jarvis Relational SQLite Database Storage Module", test_db.run_all),
        ("Jarvis Obsidian Hybrid Memory System Module", test_memory_v2.run_all)
    ]
    
    failures = []
    successes = []
    
    for name, run_test in checks:
        print(f"\n[RUNNING DIAGNOSTIC]: {name}...")
        passed = run_test()
        if passed:
            successes.append(name)
        else:
            failures.append(name)
            
    print("\n" + "=" * 70)
    print(" " * 22 + "⚡ FINAL DIAGNOSTIC REPORT ⚡")
    print("=" * 70)
    
    for name in successes:
        print(f" [+] PASS : {name:<42} -> [ SECURE ]")
    for name in failures:
        print(f" [-] FAIL : {name:<42} -> [ FAULT DETECTED ]")
        
    print("-" * 70)
    
    if not failures:
        print("  ALL SYSTEMS STABLE - JARVIS CORE IS 100% OPERATIONAL, SIR. ✨")
        print("=" * 70 + "\n")
        sys.exit(0)
    else:
        print(f"  CRITICAL FAULTS DETECTED: {len(failures)} MODULES FAILED TESTING, SIR. ⚠️")
        print("=" * 70 + "\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
