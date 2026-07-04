from ddgs import DDGS
from tool_models import ToolResult


def search(query: str) -> ToolResult:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))

        if not results:
            return ToolResult(
                success=False,
                content="",
                error="No search results found.",
            )

        output = []

        for i,r in enumerate(results, 1):
            output.append(
                f"""[{i}]
                Title: {r.get("title", "")}
                Summary: {r.get("body", "")[:250]}
                Source: {r.get("href","")}
                """
            )

        return ToolResult(
            success=True,
            content="\n\n".join(output),
        )

    except Exception as e:
        return ToolResult(
            success=False,
            content="",
            error=str(e),
        )