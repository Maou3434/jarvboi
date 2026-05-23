import time
import webbrowser
import urllib.parse
from tools.registry import register_tool
from automation import get_browser_agent
from utils.logger import logger

@register_tool(
    name="open_youtube",
    description="Opens the main YouTube homepage in the user's default system web browser (lightweight, non-interactive).",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def open_youtube() -> str:
    """Opens YouTube."""
    webbrowser.open("https://youtube.com")
    return "Successfully opened YouTube"

@register_tool(
    name="search_youtube",
    description="Searches YouTube for a given query and opens the search results in the default system web browser (lightweight, non-interactive).",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The term or phrase to search YouTube for (e.g. 'lofi hip hop')."
            }
        },
        "required": ["query"]
    }
)
def search_youtube(query: str) -> str:
    """Searches YouTube."""
    encoded_query = urllib.parse.quote(query)
    url = f"https://youtube.com/results?search_query={encoded_query}"
    webbrowser.open(url)
    return f"Successfully searched YouTube for: '{query}'"

@register_tool(
    name="youtube_play_video",
    description="Automatically launches the interactive browser, navigates to YouTube, searches for the specified video query, and plays the first video match. Keeps the browser open so the video continues playing.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The description or name of the video/song to search for and play (e.g. 'lofi hip hop beats')."
            }
        },
        "required": ["query"]
    }
)
def youtube_play_video(query: str) -> str:
    """Automates YouTube search and plays the first matching video."""
    agent = get_browser_agent()
    
    # 1. Start browser and navigate to YouTube
    logger.info("Opening YouTube via Playwright...")
    nav_status = agent.navigate("https://youtube.com")
    if "Error" in nav_status:
        return f"Failed to start YouTube playback: {nav_status}"
        
    page = agent.page
    
    try:
        # 2. Find search input field and fill search query
        logger.info(f"Searching YouTube for query: '{query}'")
        search_input = page.get_by_placeholder("Search")
        
        if search_input.count() > 0:
            search_input.fill(query)
            search_input.press("Enter")
        else:
            # Fallback to standard input ID
            page.fill("input#search", query)
            page.press("input#search", "Enter")
            
        # 3. Wait for search result list to load
        logger.info("Waiting for search results...")
        page.wait_for_selector("ytd-video-renderer", timeout=12000)
        
        # 4. Click the first video result link (bypassing ad overlays if any)
        logger.info("Clicking the first video matching results...")
        video_link = page.locator("ytd-video-renderer a#video-title").first
        
        video_title = video_link.inner_text()
        video_link.click()
        
        # 5. Wait to ensure playback starts
        time.sleep(4.0)
        
        return f"Successfully playing YouTube video: '{video_title}' in the interactive browser."
        
    except Exception as e:
        logger.exception("Error in youtube_play_video workflow:")
        return f"Encountered an error while attempting to play YouTube video: {str(e)}"
