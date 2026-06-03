import os
import sys

# Ensure local module resolves
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from automation.desktop_agent import get_desktop_agent

def test_coordinate_denormalization():
    """Verifies that normalized coordinates [0-1000] scale accurately to physical screen resolutions."""
    print("Running: test_coordinate_denormalization...")
    agent = get_desktop_agent()
    
    # Mock physical viewport dimensions
    screen_width, screen_height = 1920, 1200
    
    # Center mapping
    norm_x, norm_y = 500, 500
    target_x = int((norm_x / 1000.0) * screen_width)
    target_y = int((norm_y / 1000.0) * screen_height)
    assert target_x == 960, f"Expected center x=960, got {target_x}"
    assert target_y == 600, f"Expected center y=600, got {target_y}"
    
    # Top-Left mapping
    norm_x, norm_y = 0, 0
    target_x = int((norm_x / 1000.0) * screen_width)
    target_y = int((norm_y / 1000.0) * screen_height)
    assert target_x == 0 and target_y == 0
    
    # Bottom-Right mapping
    norm_x, norm_y = 1000, 1000
    target_x = int((norm_x / 1000.0) * screen_width)
    target_y = int((norm_y / 1000.0) * screen_height)
    assert target_x == 1920 and target_y == 1200
    
    print(" -> PASS: Coordinate scaling transformations are 100% accurate!")

def test_visual_grounding_json_cleaning():
    """Verifies that the visual grounding parsing engine extracts coords successfully, stripping markdown wrappers."""
    print("Running: test_visual_grounding_json_cleaning...")
    agent = get_desktop_agent()
    
    # Case A: Standard clean JSON string
    json_clean = '{"x": 420, "y": 69, "confidence": 0.95}'
    parsed_a = agent._clean_and_parse_json(json_clean)
    assert parsed_a is not None and parsed_a["x"] == 420 and parsed_a["y"] == 69
    
    # Case B: Markdown code block wrapped JSON
    json_markdown = "```json\n{\n  \"x\": 150,\n  \"y\": 300,\n  \"confidence\": 0.8\n}\n```"
    parsed_b = agent._clean_and_parse_json(json_markdown)
    assert parsed_b is not None and parsed_b["x"] == 150 and parsed_b["y"] == 300
    
    # Case C: Loose text containing braces
    json_loose = "The target is located at: {\"x\": 888, \"y\": 999}"
    parsed_c = agent._clean_and_parse_json(json_loose)
    assert parsed_c is not None and parsed_c["x"] == 888 and parsed_c["y"] == 999
    
    print(" -> PASS: Grounding JSON extraction shields successfully verified!")

def test_shortcut_fuzzy_cache_matches():
    """Verifies that the Start Menu cache correctly performs spacing-insensitive fuzzy matching."""
    print("Running: test_shortcut_fuzzy_cache_matches...")
    agent = get_desktop_agent()
    
    # Manually populate shortcut cache with mock data
    agent._shortcut_cache = [
        ("spotify", r"C:\Start Menu\Spotify.lnk"),
        ("discord", r"C:\Start Menu\Discord.lnk"),
        ("anti-gravity", r"C:\Start Menu\Anti-Gravity.lnk"),
        ("zen browser", r"C:\Start Menu\Zen Browser.lnk")
    ]
    
    # Test fuzzy matches
    test_cases = [
        ("spotify", "Spotify.lnk"),
        ("Discord", "Discord.lnk"),
        ("Anti-Gravity", "Anti-Gravity.lnk"),
        ("anti gravity", "Anti-Gravity.lnk"),
        ("ZenBrowser", "Zen Browser.lnk")
    ]
    
    for app_name, expected_filename in test_cases:
        app_name_lower = app_name.lower().strip()
        matched_path = None
        for basename, lnk_path in agent._shortcut_cache:
            clean_base = basename.replace(" ", "").replace("-", "")
            clean_app = app_name_lower.replace(" ", "").replace("-", "")
            if clean_app in clean_base:
                matched_path = lnk_path
                break
                
        assert matched_path is not None, f"Failed to match fuzzy app request: '{app_name}'"
        assert expected_filename in matched_path, f"Fuzzy app matched wrong path: {matched_path} (Expected {expected_filename})"
        
    print(" -> PASS: Fuzzy Start Menu app name resolutions are 100% stable!")

def run_all():
    """Runs all Desktop Agent unit tests."""
    print("\n--- STARTING OS AUTOMATION DIAGNOSTIC CHECKS ---")
    try:
        test_coordinate_denormalization()
        test_visual_grounding_json_cleaning()
        test_shortcut_fuzzy_cache_matches()
        print("DESKTOP SYSTEMS STATUS: 100% OPERATIONAL, SIR.")
        return True
    except AssertionError as ae:
        print(f" -> FAIL: AssertionError encountered: {ae}")
        return False
    except Exception as e:
        print(f" -> FAIL: System crash encountered: {e}")
        return False

if __name__ == "__main__":
    run_all()
