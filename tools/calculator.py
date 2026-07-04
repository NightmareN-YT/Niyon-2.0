import ast
import operator

from tool_models import ToolResult

# Only these node types / operators are ever evaluated — anything else (function calls,
# attribute access, name lookups, imports, etc.) is rejected outright. This is what
# actually prevents arbitrary code execution; eval()/exec() must never be used here.
_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _safe_eval(node):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("Only numeric constants are allowed.")
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        return _ALLOWED_BINOPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return _ALLOWED_UNARYOPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("Expression contains something other than plain arithmetic.")


def calculate(expression: str) -> ToolResult:
    try:
        parsed = ast.parse(expression, mode="eval")
        answer = _safe_eval(parsed)
    except ZeroDivisionError:
        return ToolResult(success=False, content="", error="Division by zero.")
    except Exception as e:
        return ToolResult(success=False, content="", error=f"Invalid expression: {e}")

    return ToolResult(
        success=True,
        content=str(answer),
    )