import logging
from typing import Any

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from aurabot.config import config

logger = logging.getLogger("DiscordBot")


class MCPManager:
    """
    Manages connections to external Model Context Protocol (MCP) servers (stdio, SSE, etc.)
    and discovers tools exposed by those servers for LangChain.
    """

    def __init__(self, server_configs: dict[str, dict[str, Any]] | None = None):
        self.raw_configs = (
            server_configs if server_configs is not None else getattr(config, "mcp_servers", {})
        )
        self.client: MultiServerMCPClient | None = None
        self._custom_tools: list[BaseTool] = []
        self._cached_tools: list[BaseTool] | None = None
        self._cached_by_server: dict[str, list[BaseTool]] | None = None
        self._initialized: bool = False

    def register_tool(self, tool: BaseTool) -> None:
        """
        Registers a local LangChain tool alongside MCP tools.
        """
        self._custom_tools.append(tool)
        self._cached_tools = None
        self._cached_by_server = None
        logger.info("Registered custom tool: %s", tool.name)

    def _normalize_connections(self) -> dict[str, dict[str, Any]]:
        """
        Normalizes server configuration dictionaries into formats expected by
        MultiServerMCPClient (StdioConnection or SSEConnection).
        """
        connections: dict[str, dict[str, Any]] = {}
        for name, cfg in self.raw_configs.items():
            if not isinstance(cfg, dict):
                continue

            transport = cfg.get("transport")
            if not transport:
                # Infer transport from keys
                transport = "sse" if "url" in cfg else "stdio"

            if transport == "stdio":
                connections[name] = {
                    "transport": "stdio",
                    "command": cfg.get("command", ""),
                    "args": cfg.get("args", []),
                    "env": cfg.get("env"),
                    "cwd": cfg.get("cwd"),
                }
            elif transport == "sse":
                connections[name] = {
                    "transport": "sse",
                    "url": cfg.get("url", ""),
                    "headers": cfg.get("headers"),
                }
            else:
                logger.warning("Unsupported MCP transport '%s' for server '%s'", transport, name)

        return connections

    async def initialize(self) -> None:
        """
        Initializes the MultiServerMCPClient with the configured servers.
        """
        if self._initialized:
            return

        connections = self._normalize_connections()
        if not connections:
            logger.info("No external MCP servers configured.")
            self.client = MultiServerMCPClient({})
            self._initialized = True
            return

        logger.info(
            "Initializing MCPManager with %d server(s): %s",
            len(connections),
            list(connections.keys()),
        )
        try:
            self.client = MultiServerMCPClient(connections)
            self._initialized = True
        except Exception as e:
            logger.error("Failed to initialize MultiServerMCPClient: %s", e, exc_info=True)
            self.client = MultiServerMCPClient({})

    async def get_tools(self, force_refresh: bool = False) -> list[BaseTool]:
        """
        Retrieves all tools available from connected MCP servers plus custom registered tools.
        """
        if self._cached_tools is not None and not force_refresh:
            return self._cached_tools

        if not self._initialized:
            await self.initialize()

        mcp_tools: list[BaseTool] = []
        if self.client:
            try:
                mcp_tools = await self.client.get_tools()
                logger.info("Discovered %d tool(s) from MCP servers", len(mcp_tools))
            except Exception as e:
                logger.error("Error retrieving tools from MCP servers: %s", e, exc_info=True)

        all_tools = list(self._custom_tools) + mcp_tools
        self._cached_tools = all_tools
        return all_tools

    async def get_tools_by_server(
        self, force_refresh: bool = False
    ) -> dict[str, list[BaseTool]]:
        """
        Groups tools by MCP server (plus '_custom' for locally registered
        tools). Used for progressive disclosure: activate_tools can enable a
        whole server's tools at once.
        """
        if self._cached_by_server is not None and not force_refresh:
            return self._cached_by_server

        grouped: dict[str, list[BaseTool]] = {}
        for tool in self._custom_tools:
            grouped.setdefault("_custom", []).append(tool)

        if not self._initialized:
            await self.initialize()

        if self.client:
            for server_name in self.client.connections:
                try:
                    grouped[server_name] = await self.client.get_tools(server_name=server_name)
                except Exception as e:
                    logger.error(
                        "Error retrieving tools from server '%s': %s", server_name, e, exc_info=True
                    )

        self._cached_by_server = grouped
        return grouped

    async def close(self) -> None:
        """
        Closes active sessions if any.
        """
        self._cached_tools = None
        self._cached_by_server = None
        self._initialized = False


# Singleton instance
mcp_manager = MCPManager()
