import webbrowser
from tools.registry import register_tool
from automation import get_browser_agent

@register_tool(
    name="open_website",
    description="Opens any specific website URL in the user's default system web browser (lightweight, non-interactive). Use this if you just want to open a URL for the user to look at directly.",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The full URL of the website to open (e.g. 'https://google.com')."
            }
        },
        "required": ["url"]
    }
)
def open_website(url: str) -> str:
    """Opens a website URL in the default system browser."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    return f"Successfully opened website: {url}"

@register_tool(
    name="browser_navigate",
    description="Launches an interactive Playwright browser and navigates to the specified URL. Use this when you need to perform further automated steps like clicking, typing, or reading site content.",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The full URL to navigate to (e.g. 'https://google.com')."
            }
        },
        "required": ["url"]
    }
)
def browser_navigate(url: str) -> str:
    """Navigates the interactive Playwright browser agent to a URL."""
    agent = get_browser_agent()
    return agent.navigate(url)

@register_tool(
    name="browser_click",
    description="Clicks on a visible element (e.g. button, link, tab) in the interactive browser. Match by text label or standard CSS selector.",
    parameters={
        "type": "object",
        "properties": {
            "selector_or_text": {
                "type": "string",
                "description": "The text label of the element (e.g. 'Sign In') or a CSS selector."
            }
        },
        "required": ["selector_or_text"]
    }
)
def browser_click(selector_or_text: str) -> str:
    """Clicks on an element in the browser."""
    agent = get_browser_agent()
    return agent.click(selector_or_text)

@register_tool(
    name="browser_type",
    description="Types text into an input field or text box in the interactive browser. Matches by placeholder name or standard CSS selector.",
    parameters={
        "type": "object",
        "properties": {
            "selector_or_text": {
                "type": "string",
                "description": "The placeholder name of the input box (e.g. 'Search') or a CSS selector."
            },
            "text": {
                "type": "string",
                "description": "The text content to enter."
            }
        },
        "required": ["selector_or_text", "text"]
    }
)
def browser_type(selector_or_text: str, text: str) -> str:
    """Types text into an input field in the browser."""
    agent = get_browser_agent()
    return agent.type_text(selector_or_text, text)

@register_tool(
    name="browser_close",
    description="Closes the current interactive browser automation session.",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def browser_close() -> str:
    """Closes the browser session."""
    agent = get_browser_agent()
    agent.close()
    return "Interactive browser automation session closed successfully."
