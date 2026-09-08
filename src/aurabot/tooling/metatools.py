from collections.abc import Callable
from typing import Any

from langchain_core.tools import BaseTool, tool

CATALOG_DESC_MAX_CHARS = 120
ACTIVATE_TOOLS_NAME = "activate_tools"


def build_tools_index(catalog: list[BaseTool]) -> str:
    """
    Builds the compact 'Available Tools' prompt section (progressive
    disclosure level 1): tool names + one-line descriptions, without JSON
    schemas. Returns an empty string if the catalog is empty.
    """
    if not catalog:
        return ""

    lines = ["Available tools (schemas are NOT loaded yet):"]
    for t in catalog:
        desc = ""
        if t.description:
            first_line = t.description.strip().splitlines()[0].strip()
            if len(first_line) > CATALOG_DESC_MAX_CHARS:
                first_line = first_line[:CATALOG_DESC_MAX_CHARS - 3] + "..."
            desc = first_line
        lines.append(f"- `{t.name}`: {desc}" if desc else f"- `{t.name}`")
    lines.append(
        "To use any of these tools, first call the `activate_tools` tool with "
        "the exact tool name(s) or the MCP server name(s) to activate."
    )
    return "\n".join(lines)


def create_activate_tools_tool(activate_fn: Callable[[list[str]], str]) -> BaseTool:
    """
    Creates the 'activate_tools' meta-tool bound to a per-response activation
    function. The model uses it to bind real tool schemas (level 2 of
    progressive disclosure) before calling them (level 3).
    """

    @tool
    def activate_tools(names: list[str]) -> str:
        """Activates tools from the available-tools catalog so they can be called.

        Accepts exact tool names and/or MCP server names (activating a server
        enables all of its tools). Always call this tool before using any
        tool listed in 'Available tools'.

        Args:
            names: Tool names (e.g. ['get_user_profile']) or MCP server names
                (e.g. ['discord_info']).
        """
        return activate_fn(names or [])

    activate_tools.name = ACTIVATE_TOOLS_NAME
    return activate_tools


def extract_names_args(args: Any) -> list[str]:
    """
    Extracts the names list from activate_tools call args, tolerating the
    shapes different models emit: {'names': [...]}, {'name': 'x'},
    {'names': 'x'} or a bare list.
    """
    if isinstance(args, dict):
        value = args.get("names", args.get("name"))
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple, set)):
            return [str(v) for v in value]
        return [str(value)]
    if isinstance(args, (list, tuple)):
        return [str(v) for v in args]
    return [str(args)]
