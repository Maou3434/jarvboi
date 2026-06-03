from tools.registry import register_tool
from automation.desktop_agent import get_desktop_agent

@register_tool(
    name="desktop_launch_application",
    description=(
        "Launches an application natively by its name (e.g. 'Anti-Gravity', 'Spotify', 'Discord', 'Notepad'). "
        "Use this as the PRIMARY and preferred tool when the user explicitly requests to open, start, or launch a desktop application, "
        "as it uses local Windows Start Menu shortcuts and runs instantly offline."
    ),
    parameters={
        "type": "object",
        "properties": {
            "app_name": {
                "type": "string",
                "description": "The name of the application to launch (e.g. 'Spotify')."
            }
        },
        "required": ["app_name"]
    }
)
def desktop_launch_application(app_name: str) -> str:
    """Launches an application by name."""
    agent = get_desktop_agent()
    return agent.launch_application(app_name)

@register_tool(
    name="desktop_focus_window",
    description=(
        "Brings an already running application window to the active foreground by matching its title or name "
        "(e.g. 'Firefox', 'Spotify', 'Notepad', 'Anti-Gravity'). "
        "Use this preferred offline tool when the user asks to switch to, show, focus, or bring an already-open window to the front."
    ),
    parameters={
        "type": "object",
        "properties": {
            "window_title": {
                "type": "string",
                "description": "The title or substring name of the window to bring to focus (e.g. 'Firefox')."
            }
        },
        "required": ["window_title"]
    }
)
def desktop_focus_window(window_title: str) -> str:
    """Brings a window to the foreground."""
    agent = get_desktop_agent()
    return agent.focus_window(window_title)

@register_tool(
    name="desktop_visual_click",
    description=(
        "Takes a screenshot of the desktop, visually locates the specified target element using AI screen awareness, "
        "and smoothly glides the mouse pointer to click it. "
        "Use this tool for complex on-screen actions that cannot be done via local APIs, "
        "such as focusing a specific tab inside a running browser (e.g. 'the YouTube tab in Firefox'), "
        "clicking a specific button, or double-clicking custom visual shortcuts on screen."
    ),
    parameters={
        "type": "object",
        "properties": {
            "element_description": {
                "type": "string",
                "description": "A clear, visual description of the target on-screen element to click (e.g. 'the YouTube tab in Firefox titlebar')."
            },
            "double_click": {
                "type": "boolean",
                "description": "Set to True if a double-click is required (e.g. to open a desktop file icon). Defaults to False.",
                "default": False
            }
        },
        "required": ["element_description"]
    }
)
def desktop_visual_click(element_description: str, double_click: bool = False) -> str:
    """Moves the pointer and clicks on a visual element using Gemini vision grounding."""
    agent = get_desktop_agent()
    return agent.visual_click(element_description, double_click)
