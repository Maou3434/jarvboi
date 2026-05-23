# Automation package
from automation.browser_agent import BrowserAgent

# Cached global singleton BrowserAgent session
_browser_agent = None

def get_browser_agent() -> BrowserAgent:
    """Returns the cached global BrowserAgent instance."""
    global _browser_agent
    if _browser_agent is None:
        _browser_agent = BrowserAgent()
    return _browser_agent
