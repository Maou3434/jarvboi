import webbrowser
from tools.registry import register_tool

@register_tool(
    name="open_website",
    description="Opens any specific website URL in the user's default web browser.",
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
    """Opens a website URL in the system browser."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    return f"Successfully opened website: {url}"
