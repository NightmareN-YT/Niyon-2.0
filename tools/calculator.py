from tool_models import ToolResult

def calculate(expression: str) -> ToolResult:
    answer = eval(expression)

    return ToolResult(
        success=True,
        content=str(answer),
    )