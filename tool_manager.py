from tools.web import search
from tools.weather import get_weather
from tools.calculator import calculate
from tool_models import ToolResult

TOOLS = {
    "web": {
        "function": search,
        "description": "Search the web for current events, live data, or anything that may have changed recently.",
    },
    "weather": {
        "function": get_weather,
        "description": "Get current weather for a city.",
    },
    "calculator": {
        "function": calculate,
        "description": "Evaluate a plain arithmetic expression (numbers and +, -, *, /, //, %, ** only).",
    },
}


def run_tool(tool_name: str, argument: str):
    tool = TOOLS.get(tool_name)
    if tool is None:
        return ToolResult(
            success=False,
            content="",
            error=f"Unknown tool: {tool_name}",
        )
    return tool["function"](argument)