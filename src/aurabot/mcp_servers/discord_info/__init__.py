from mcp.server.fastmcp import FastMCP

# Initialize FastMCP Server
mcp = FastMCP("DiscordInfo")

# Importing the tools module registers all @mcp.tool handlers
from aurabot.mcp_servers.discord_info import tools  # noqa: E402, F401

__all__ = ["mcp"]
