import os
import sys
import unittest
from unittest.mock import MagicMock, patch, mock_open

# Ensure local module resolves
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from automation.desktop_agent import get_desktop_agent
from automation.browser_agent import BrowserAgent
from tools.desktop import desktop_launch_application, desktop_focus_window, desktop_visual_click
from tools.system import system_media_play_pause
from tools.youtube import open_youtube, search_youtube, youtube_play_video

class TestToolsExecution(unittest.TestCase):

    # --- Desktop Agent Tool Tests ---

    @patch("os.startfile")
    def test_launch_application_cache_hit(self, mock_startfile):
        """Verifies that launch_application opens a cached app immediately."""
        agent = get_desktop_agent()
        agent._shortcut_cache = [
            ("spotify", "C:\\Start Menu\\Spotify.lnk")
        ]
        
        result = desktop_launch_application("Spotify")
        
        mock_startfile.assert_called_once_with("C:\\Start Menu\\Spotify.lnk")
        self.assertIn("Successfully opened 'Spotify' from Start Menu shortcut", result)

    @patch("os.startfile")
    @patch("subprocess.Popen")
    def test_launch_application_cache_miss_shell_fallback(self, mock_popen, mock_startfile):
        """Verifies that launching a missing app falls back to cmd shell."""
        agent = get_desktop_agent()
        agent._shortcut_cache = []
        
        with patch.object(agent, "refresh_shortcut_cache") as mock_refresh:
            result = desktop_launch_application("calc")
            
            mock_refresh.assert_called_once()
            mock_popen.assert_called_once_with("calc", shell=True)
            self.assertIn("Successfully launched 'calc' via command shell", result)

    @patch("pygetwindow.getAllWindows")
    def test_focus_window_pygetwindow_success(self, mock_get_windows):
        """Verifies focus_window restores and activates a window by title."""
        mock_win = MagicMock()
        mock_win.title = "Firefox Web Browser"
        mock_win.isMinimized = True
        mock_get_windows.return_value = [mock_win]
        
        result = desktop_focus_window("Firefox")
        
        mock_win.restore.assert_called_once()
        mock_win.activate.assert_called_once()
        self.assertIn("Successfully brought open window 'Firefox Web Browser' to the foreground", result)

    @patch("pygetwindow.getAllWindows", side_effect=Exception("Focus Blocked"))
    @patch("ctypes.windll.user32.EnumWindows")
    @patch("ctypes.windll.user32.IsWindowVisible", return_value=True)
    @patch("ctypes.windll.user32.GetWindowTextLengthW", return_value=15)
    @patch("ctypes.windll.user32.GetWindowTextW")
    @patch("ctypes.windll.user32.ShowWindow")
    @patch("ctypes.windll.user32.SetForegroundWindow")
    @patch("ctypes.windll.user32.IsIconic", return_value=True)
    def test_focus_window_win32_fallback(self, mock_iconic, mock_set_foreground, mock_show, mock_get_text, mock_length, mock_visible, mock_enum, mock_pygetwindow):
        """Verifies window focus fallback to win32 ctypes if pygetwindow fails."""
        # Setup EnumWindows callback behavior to mock window title search
        def enum_call(callback, lParam):
            # Create a mock hwnd and call the callback
            callback(12345, 0)
            return True
            
        mock_enum.side_effect = enum_call
        
        # Mock GetWindowTextW writing 'spotify' to the ctypes buffer
        def get_text_call(hwnd, buf, length):
            buf.value = "Spotify Premium"
            return len("Spotify Premium")
        mock_get_text.side_effect = get_text_call
        
        result = desktop_focus_window("Spotify")
        
        mock_show.assert_any_call(12345, 9) # SW_RESTORE
        mock_show.assert_any_call(12345, 5) # SW_SHOW
        mock_set_foreground.assert_called_once_with(12345)
        self.assertIn("Successfully brought matching window to the foreground via native OS hooks", result)

    @patch("mss.mss")
    @patch("PIL.Image.open")
    @patch("pyautogui.size", return_value=(1920, 1080))
    @patch("pyautogui.moveTo")
    @patch("pyautogui.click")
    def test_desktop_visual_click(self, mock_click, mock_move, mock_size, mock_img_open, mock_mss):
        """Verifies visual_click captures screenshot, calls Gemini vision model, and clicks scaled coordinates."""
        agent = get_desktop_agent()
        
        # Mock Gemini visual grounding call
        mock_query = MagicMock(return_value={"x": 500, "y": 500, "confidence": 0.9})
        agent._query_gemini_grounding = mock_query
        
        # Mock PIL image properties
        mock_img = MagicMock()
        mock_img.size = (1920, 1080)
        mock_img.mode = "RGB"
        mock_img_open.return_value = mock_img
        
        # Mock temp file paths cleanup
        m_open = mock_open(read_data=b"dummy_data")
        with patch("builtins.open", m_open), patch("os.makedirs"), patch("os.path.exists", return_value=True), patch("os.remove"):
            result = desktop_visual_click("Firefox close button")
            
            agent._query_gemini_grounding.assert_called_once()
            # Scaling coordinates: x = (500/1000) * 1920 = 960, y = (500/1000) * 1080 = 540
            mock_move.assert_called_once_with(960, 540, duration=0.6, tween=unittest.mock.ANY)
            mock_click.assert_called_once()
            self.assertIn("Successfully moved pointer and clicked on the visual element: 'Firefox close button'", result)

    # --- Browser Agent Tests ---

    @patch("automation.browser_agent.sync_playwright")
    def test_browser_agent_navigate_and_consent(self, mock_playwright):
        """Verifies BrowserAgent starts, navigates, and rejects cookie consent dialogs."""
        agent = BrowserAgent()
        agent.headless = True
        
        # Mock Playwright structure
        mock_p = MagicMock()
        mock_playwright.return_value.start.return_value = mock_p
        mock_browser = MagicMock()
        mock_p.chromium.launch.return_value = mock_browser
        mock_context = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_page.title.return_value = "Example Home Page"
        
        # Mock consent overlay buttons search
        mock_button = MagicMock()
        mock_button.count.return_value = 1
        mock_button.first.is_visible.return_value = True
        mock_page.get_by_role.return_value = mock_button
        
        # Run navigation
        with patch("config.settings.Settings.BROWSER_CONNECT_CDP", False):
            result = agent.navigate("example.com")
            
            mock_page.goto.assert_called_once_with("https://example.com")
            mock_page.get_by_role.assert_any_call("button", name="Reject all", exact=False)
            mock_button.first.click.assert_called_once() # verified consent dismissal click
            self.assertIn("Page Title: 'Example Home Page'", result)

    # --- YouTube & System Media key controls ---

    @patch("webbrowser.open")
    def test_youtube_homepage_and_search(self, mock_web_open):
        """Verifies simple browser open calls for YouTube homepage and search queries."""
        open_youtube()
        mock_web_open.assert_any_call("https://youtube.com")
        
        search_youtube("jazz fusion")
        mock_web_open.assert_any_call("https://youtube.com/results?search_query=jazz%20fusion")

    @patch("tools.youtube.get_browser_agent")
    def test_youtube_play_video_playwright(self, mock_get_browser):
        """Verifies youtube_play_video fills input, clicks first matching video result."""
        mock_agent = MagicMock()
        mock_get_browser.return_value = mock_agent
        mock_agent.navigate.return_value = "Opened YouTube page"
        
        mock_page = MagicMock()
        mock_agent.page = mock_page
        
        # Mock get_by_placeholder("Search") input element
        mock_search_input = MagicMock()
        mock_search_input.count.return_value = 1
        mock_page.get_by_placeholder.return_value = mock_search_input
        
        # Mock search results elements
        mock_video_link = MagicMock()
        mock_video_link.inner_text.return_value = "Lofi beats to study to"
        mock_page.locator.return_value.first = mock_video_link
        
        # Execute tool
        with patch("time.sleep"):
            result = youtube_play_video("lofi beats")
            
            mock_agent.navigate.assert_called_once_with("https://youtube.com")
            mock_search_input.fill.assert_called_with("lofi beats")
            mock_search_input.press.assert_called_with("Enter")
            mock_video_link.click.assert_called_once()
            self.assertIn("Successfully playing YouTube video: 'Lofi beats to study to'", result)

    @patch("ctypes.windll.user32.keybd_event")
    def test_system_media_play_pause(self, mock_keybd_event):
        """Verifies that system_media_play_pause sends global keybd_event virtual key signals."""
        result = system_media_play_pause()
        
        # Virtual Key for Media Play/Pause is 0xB3 (179)
        mock_keybd_event.assert_any_call(0xB3, 0, 0, 0) # Key Down
        mock_keybd_event.assert_any_call(0xB3, 0, 2, 0) # Key Up
        self.assertIn("Successfully sent system-wide Play/Pause keyboard command", result)

def run_all() -> bool:
    suite = unittest.TestLoader().loadTestsFromTestCase(TestToolsExecution)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()

if __name__ == "__main__":
    run_all()
