from dataclasses import dataclass
from typing import Any


@dataclass
class ToolRequest:
    """A request made by the AI to use a tool."""
    tool: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    """A result returned by a tool."""
    success: bool
    content: str
    error: str | None = None