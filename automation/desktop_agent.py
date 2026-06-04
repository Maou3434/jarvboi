import os
import glob
import re
import subprocess
import time
import base64
import json
import urllib.request
from typing import Dict, Any, Optional, List, Tuple

from config.settings import Settings
from utils.logger import logger

class DesktopAgent:
    """Orchestrates local API automation and vision-based pointer control on Windows."""

    def __init__(self):
        self.api_key = Settings.GEMINI_API_KEY
        self.model = Settings.GEMINI_MODEL
        # Memory caching for Windows Start Menu shortcuts to boost launch speeds (<2ms subsequent lookups)
        self._shortcut_cache: Optional[List[Tuple[str, str]]] = None

    def refresh_shortcut_cache(self):
        """Recursively scans Windows Start Menu locations and caches shortcut names and paths."""
        logger.info("[Desktop Agent] Building Start Menu shortcuts cache...")
        cache = []
        user_profile = os.getenv("USERPROFILE", "")
        start_menu_paths = [
            r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
            os.path.join(user_profile, r"AppData\Roaming\Microsoft\Windows\Start Menu\Programs")
        ]

        for base_path in start_menu_paths:
            if not os.path.exists(base_path):
                continue
            
            # Recursively gather all shortcut files
            try:
                lnk_files = glob.glob(os.path.join(base_path, "**", "*.lnk"), recursive=True)
                for lnk_path in lnk_files:
                    # Cache standard shortcut filename (without extension) along with its absolute path
                    basename = os.path.splitext(os.path.basename(lnk_path))[0].lower().strip()
                    cache.append((basename, lnk_path))
            except Exception as e:
                logger.error(f"[Desktop Agent] Error scanning directory '{base_path}': {e}")
                
        self._shortcut_cache = cache
        logger.info(f"[Desktop Agent] Cache successfully built with {len(cache)} application shortcuts.")

    def launch_application(self, app_name: str) -> str:
        """Finds and launches an application by name, utilizing Start Menu caching with Direct Command fallbacks."""
        app_name_lower = app_name.lower().strip()
        logger.info(f"[Desktop Agent] Searching shortcut cache for application: '{app_name}'")

        # Lazily initialize the shortcut cache on first request
        if self._shortcut_cache is None:
            self.refresh_shortcut_cache()

        # Search matching shortcut names in the cache
        found_shortcut = None
        for basename, lnk_path in self._shortcut_cache:
            # Match exactly or by substring, ignoring spacing variations (e.g. 'Anti-Gravity' vs 'Anti Gravity')
            clean_base = basename.replace(" ", "").replace("-", "")
            clean_app = app_name_lower.replace(" ", "").replace("-", "")
            if clean_app in clean_base:
                found_shortcut = lnk_path
                break

        if found_shortcut:
            try:
                logger.info(f"[Desktop Agent] Cache HIT! Launching shortcut: '{found_shortcut}'")
                os.startfile(found_shortcut)
                return f"Successfully opened '{app_name}' from Start Menu shortcut."
            except Exception as e:
                logger.error(f"[Desktop Agent] Failed to start cached shortcut: {e}")

        # Cache Miss Fallback: Re-scan Start Menu in case new apps were installed
        logger.info(f"[Desktop Agent] Cache MISS. Performing a fresh re-scan of Start Menu...")
        self.refresh_shortcut_cache()
        for basename, lnk_path in self._shortcut_cache:
            clean_base = basename.replace(" ", "").replace("-", "")
            clean_app = app_name_lower.replace(" ", "").replace("-", "")
            if clean_app in clean_base:
                try:
                    logger.info(f"[Desktop Agent] Match found after re-scan: '{lnk_path}'")
                    os.startfile(lnk_path)
                    return f"Successfully opened '{app_name}' after Start Menu re-scan."
                except Exception as inner_e:
                    logger.error(f"[Desktop Agent] Failed to start re-scanned shortcut: {inner_e}")

        # Core OS Shell Fallback: try spawning via CMD shell for standard system commands (e.g. notepad, calc)
        try:
            logger.info(f"[Desktop Agent] Application shortcut not found. Spawning command '{app_name}' directly via CMD shell...")
            subprocess.Popen(app_name, shell=True)
            return f"Successfully launched '{app_name}' via command shell."
        except Exception as e:
            logger.exception(f"[Desktop Agent] Failed shell fallback for '{app_name}':")
            return f"Could not locate or open application '{app_name}'. Error: {str(e)}"

    def focus_window(self, window_title: str) -> str:
        """Locates a running window by title and brings it to the foreground."""
        window_title_lower = window_title.lower().strip()
        logger.info(f"[Desktop Agent] Locating open window matching: '{window_title}'")

        try:
            import pygetwindow as gw
            
            # Find matching window by substring
            all_windows = gw.getAllWindows()
            matching_windows = [
                w for w in all_windows 
                if w.title and (window_title_lower in w.title.lower() or window_title_lower.replace(" ", "") in w.title.lower().replace(" ", ""))
            ]

            if matching_windows:
                win = matching_windows[0]
                logger.info(f"[Desktop Agent] Found matching window: '{win.title}'. Activating...")
                
                if win.isMinimized:
                    win.restore()
                win.activate()
                return f"Successfully brought open window '{win.title}' to the foreground."
            
        except Exception as e:
            logger.warning(f"[Desktop Agent] Direct pygetwindow focus failed: {e}. Attempting native win32 fallback...")

        # Fallback: Native Win32 API calls via ctypes (highly robust against Windows focus blocking)
        try:
            import ctypes
            EnumWindows = ctypes.windll.user32.EnumWindows
            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
            GetWindowText = ctypes.windll.user32.GetWindowTextW
            GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
            IsWindowVisible = ctypes.windll.user32.IsWindowVisible
            ShowWindow = ctypes.windll.user32.ShowWindow
            SetForegroundWindow = ctypes.windll.user32.SetForegroundWindow
            IsIconic = ctypes.windll.user32.IsIconic

            found_hwnd = []

            def foreach_window(hwnd, lParam):
                if IsWindowVisible(hwnd):
                    length = GetWindowTextLength(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        GetWindowText(hwnd, buff, length + 1)
                        title = buff.value.lower()
                        if window_title_lower in title or window_title_lower.replace(" ", "") in title.replace(" ", ""):
                            found_hwnd.append(hwnd)
                            return False  # Stop enumeration
                return True

            EnumWindows(EnumWindowsProc(foreach_window), 0)

            if found_hwnd:
                hwnd = found_hwnd[0]
                # SW_RESTORE is 9, SW_SHOW is 5
                if IsIconic(hwnd):
                    ShowWindow(hwnd, 9)
                ShowWindow(hwnd, 5)
                SetForegroundWindow(hwnd)
                return f"Successfully brought matching window to the foreground via native OS hooks."
            
        except Exception as win32_err:
            logger.error(f"[Desktop Agent] Win32 window focus fallback failed: {win32_err}")

        return f"Could not find any running window with title containing '{window_title}' to focus."

    def visual_click(self, element_description: str, double_click: bool = False) -> str:
        """Captures a screenshot, queries Gemini Vision to detect coordinates, and clicks on the target."""
        logger.info(f"[Desktop Agent] Initiating vision-based click for: '{element_description}'")

        try:
            import mss
            import pyautogui
            from PIL import Image
        except ImportError as err:
            logger.error(f"[Desktop Agent] Missing visual libraries: {err}")
            return "Visual automation libraries are not loaded. Please verify dependencies are installed."

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        scratch_dir = os.path.join(project_root, "scratch")
        os.makedirs(scratch_dir, exist_ok=True)
        temp_screenshot = os.path.join(scratch_dir, "temp_desktop.png")
        temp_optimized = os.path.join(scratch_dir, "temp_desktop_opt.jpg")

        try:
            # 1. Capture screen buffer
            logger.info("[Desktop Agent] Capturing desktop screenshot...")
            with mss.mss() as sct:
                sct.shot(output=temp_screenshot)

            if not os.path.exists(temp_screenshot):
                raise FileNotFoundError("Failed to capture desktop screenshot buffer.")

            # 2. Resize and compress to optimize API latency
            logger.info("[Desktop Agent] Optimizing screenshot for Gemini Vision API...")
            img = Image.open(temp_screenshot)
            if img.mode != 'RGB':
                img = img.convert('RGB')

            width, height = img.size
            max_dimension = 1024
            
            # Downscale preserving ratio
            if width > max_dimension or height > max_dimension:
                if width > height:
                    new_width = max_dimension
                    new_height = int(height * (max_dimension / width))
                else:
                    new_height = max_dimension
                    new_width = int(width * (max_dimension / height))
                logger.info(f"[Desktop Agent] Resizing screenshot from {width}x{height} to {new_width}x{new_height}")
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            img.save(temp_optimized, "JPEG", quality=80)

            # 3. Base64 encode for API payload
            with open(temp_optimized, "rb") as image_file:
                encoded_image = base64.b64encode(image_file.read()).decode("utf-8")

            # 4. Perform visual grounding call to Gemini 2.5
            logger.info("[Desktop Agent] Querying Gemini Vision API for visual grounding coordinates...")
            coordinates = self._query_gemini_grounding(encoded_image, element_description)
            
            if not coordinates:
                return f"Could not visually resolve the coordinate for '{element_description}' on your screen."

            norm_x, norm_y = coordinates.get("x"), coordinates.get("y")
            logger.info(f"[Desktop Agent] Visual target grounded. Normalized Coordinates: x={norm_x}, y={norm_y}")

            # 5. Denormalize coordinates to match actual physical screen size
            screen_width, screen_height = pyautogui.size()
            target_x = int((norm_x / 1000.0) * screen_width)
            target_y = int((norm_y / 1000.0) * screen_height)
            logger.info(f"[Desktop Agent] Denormalized physical coordinates: x={target_x}, y={target_y} on {screen_width}x{screen_height} screen")

            # 6. Smooth Human-like pointer movement
            logger.info(f"[Desktop Agent] Gliding pointer to ({target_x}, {target_y}) and executing click...")
            # pyautogui.easeOutQuad provides a organic easing decelerating curve
            pyautogui.moveTo(target_x, target_y, duration=0.6, tween=pyautogui.easeOutQuad)
            
            if double_click:
                pyautogui.doubleClick()
                action_str = "double-clicked"
            else:
                pyautogui.click()
                action_str = "clicked"

            return f"Successfully moved pointer and {action_str} on the visual element: '{element_description}'."

        except Exception as e:
            logger.exception("[Desktop Agent] Error in visual_click workflow:")
            return f"Failed visual interaction. Error: {str(e)}"
        
        finally:
            # Clean up temporary scratch image files
            for temp_file in [temp_screenshot, temp_optimized]:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except Exception:
                        pass

    def _clean_and_parse_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Extracts and parses JSON coordinate mappings securely, stripping markdown block overrides."""
        text = text.strip()
        
        # 1. Check for standard markdown code blocks (e.g. ```json ... ```)
        markdown_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if markdown_match:
            try:
                return json.loads(markdown_match.group(1))
            except json.JSONDecodeError:
                pass
                
        # 2. Extract outermost curly braces as fallback
        first_brace = text.find('{')
        last_brace = text.rfind('}')
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            try:
                return json.loads(text[first_brace:last_brace + 1])
            except json.JSONDecodeError:
                pass
                
        # 3. Standard JSON parse fallback
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"[Desktop Agent] Failed to parse grounding JSON output: {text}")
            return None

    def _query_gemini_grounding(self, base64_image: str, query: str) -> Optional[Dict[str, float]]:
        """Queries the Gemini API with standard REST request, sending the screenshot and fetching grounding coords."""
        if not self.api_key:
            logger.error("[Desktop Agent] Gemini API key is missing. Visual grounding is not possible.")
            return None

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        system_instruction = (
            "You are the visual coordinate locator for Jarvboi, a Windows desktop assistant.\n"
            "Analyze the attached screenshot of the Windows desktop and determine the exact pixel coordinates [x, y] representing the center of the element matching the user's request.\n"
            "CRITICAL: The coordinates you return MUST be normalized to a scale of 0 to 1000 for both width (x) and height (y).\n"
            "For example, the top-left corner is [0, 0], the exact center is [500, 500], and the bottom-right corner is [1000, 1000].\n"
            "Double-check your targets. If the user wants a browser tab (like 'YouTube in Firefox'), locate the tab in Firefox's tab/title bar.\n"
            "If they want to open a desktop app, locate the icon or shortcut on the desktop.\n"
            "You MUST respond with a single valid JSON object containing exactly three keys: 'x' (integer 0-1000), 'y' (integer 0-1000), and 'confidence' (float 0.0-1.0).\n"
            "Do NOT wrap the JSON in markdown code blocks."
        )

        user_prompt = f"Find the normalized center coordinates [x, y] of: '{query}'"

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": user_prompt},
                        {
                            "inlineData": {
                                "mimeType": "image/jpeg",
                                "data": base64_image
                            }
                        }
                    ]
                }
            ],
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            },
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json"
            }
        }

        headers = {"Content-Type": "application/json"}
        data = json.dumps(payload).encode("utf-8")

        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=15.0) as response:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)

                candidates = res_json.get("candidates", [])
                if not candidates:
                    logger.warning("[Desktop Agent] No candidates returned from Gemini Vision.")
                    return None

                content_text = candidates[0]["content"]["parts"][0]["text"].strip()
                logger.info(f"[Desktop Agent] Raw Grounding Output:\n{content_text}")

                # Secure parsing utilizing JSON extraction layer
                parsed_coords = self._clean_and_parse_json(content_text)
                if parsed_coords and "x" in parsed_coords and "y" in parsed_coords:
                    return {
                        "x": float(parsed_coords["x"]),
                        "y": float(parsed_coords["y"]),
                        "confidence": float(parsed_coords.get("confidence", 1.0))
                    }
        except Exception as e:
            logger.error(f"[Desktop Agent] Grounding API request failed: {e}")
            
        return None

# Singleton desktop agent instances
_desktop_agent = None

def get_desktop_agent() -> DesktopAgent:
    global _desktop_agent
    if _desktop_agent is None:
        _desktop_agent = DesktopAgent()
    return _desktop_agent
