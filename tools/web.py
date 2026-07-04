from ddgs import DDGS
from tool_models import ToolResult


def search(query: str) -> ToolResult:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))

        if not results:
            return ToolResult(
                success=False,
                content="",
                error="No search results found.",
            )

        output = []

        for i,r in enumerate(results, 1):
            title = r.get("title", "").strip()
            summary = r.get("body", "").strip()[:250]
            url = r.get("href", "").strip()

            output.append(
                f"""Result {i}

        Title:
        {title}

        Summary:
        {summary}

        URL:
        {url}

        ----------------"""
            )

        return ToolResult(
            success=True,
            content="\n".join(output),
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