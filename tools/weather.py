from tool_models import ToolResult

def get_weather(city: str) -> ToolResult:
    return ToolResult(
        success=True,
        content="Weather tool placeholder"
    )