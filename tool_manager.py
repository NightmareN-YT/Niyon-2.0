from tools.web import search
from tools.weather import get_weather
from tools.calculator import calculate


def run_tool(tool_name: str, argument: str):
    if tool_name == "web":
        return search(argument)

    elif tool_name == "weather":
        return get_weather(argument)

    elif tool_name == "calculator":
        return calculate(argument)

    raise ValueError(f"Unknown tool: {tool_name}")