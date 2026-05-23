import webbrowser
import urllib.parse
from tools.registry import register_tool

@register_tool(
    name="open_youtube",
    description="Opens the main YouTube homepage in the default web browser.",
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
    description="Searches YouTube for a given query and opens the search results in the default web browser.",
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
