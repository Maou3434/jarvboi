import inspect
from typing import Callable, Dict, Any, List

class Tool:
    """Represents a dynamically registered tool executable by the assistant."""
    
    def __init__(self, name: str, description: str, parameters: Dict[str, Any], func: Callable):
        self.name = name
        self.description = description
        self.parameters = parameters  # JSON Schema format
        self.func = func
        
    def execute(self, **kwargs) -> str:
        """Executes the underlying tool function with validation and error handling."""
        try:
            # Match parameters using inspect signature to avoid passing extra arguments
            sig = inspect.signature(self.func)
            has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
            
            if has_var_keyword:
                valid_args = kwargs
            else:
                valid_args = {}
                for name, param in sig.parameters.items():
                    if name in kwargs:
                        valid_args[name] = kwargs[name]
                    elif param.default is not inspect.Parameter.empty:
                        # Parameter has a default value, let Python handle it
                        pass
            
            result = self.func(**valid_args)
            return str(result)
        except Exception as e:
            return f"Error executing tool '{self.name}': {str(e)}"

class ToolRegistry:
    """Manages all registered tools for the assistant."""
    
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        
    def register(self, name: str, description: str, parameters: Dict[str, Any] = None):
        """Decorator to register a function as an assistant tool.
        
        Args:
            name: The tool name used by the LLM (e.g. 'open_google').
            description: Detailed explanation of what the tool does and when to use it.
            parameters: JSON schema of the expected arguments. Defaults to empty object.
        """
        def decorator(func: Callable):
            params = parameters or {
                "type": "object",
                "properties": {},
                "required": []
            }
            tool_instance = Tool(name, description, params, func)
            self._tools[name] = tool_instance
            return func
        return decorator
        
    def get_tool(self, name: str) -> Tool:
        """Retrieves a registered tool by its name."""
        return self._tools.get(name)
        
    def list_tools(self) -> List[Dict[str, Any]]:
        """Returns tool schema list formatted for the LLM system instructions."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters
            }
            for tool in self._tools.values()
        ]

# Central Tool Registry Instance
registry = ToolRegistry()
register_tool = registry.register
