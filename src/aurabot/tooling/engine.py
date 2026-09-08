import logging
from typing import Any, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.tools import BaseTool

from aurabot.tooling.context import save_current_context
from aurabot.tooling.metatools import ACTIVATE_TOOLS_NAME, create_activate_tools_tool, extract_names_args

logger = logging.getLogger("DiscordBot")


class ZeroShotTooling:
    """
    Zero-Shot Tool-Calling execution engine for LangChain chat models with
    progressive disclosure:

    - Level 1: the system prompt carries a compact tools index (no schemas).
    - Level 2: each response starts with only the meta-tools (activate_tools)
      plus always-active tools (e.g. load_skill). The model binds more tool
      schemas on demand via activate_tools, by tool or MCP server name.
    - Level 3: activated tools are called normally during the loop.

    Tool activation state is LOCAL to each execute() call, so concurrent
    responses for different users never share activations.
    """

    def __init__(
        self,
        chat_model: BaseChatModel,
        max_iterations: int = 8,
    ):
        self.chat_model = chat_model
        self.max_iterations = max_iterations
        self._catalog_by_name: dict[str, BaseTool] = {}
        self._tools_by_server: dict[str, list[BaseTool]] = {}
        self._always_active: list[BaseTool] = []

    def update_catalog(
        self,
        tools: Sequence[BaseTool],
        tools_by_server: dict[str, list[BaseTool]] | None = None,
    ) -> None:
        """
        Refreshes the tools catalog (schemas stay unbound until the model
        activates them during a response).
        """
        self._catalog_by_name = {t.name: t for t in tools}
        self._tools_by_server = tools_by_server or {}
        logger.info(
            "Updated tooling catalog with %d tool(s): %s",
            len(self._catalog_by_name),
            list(self._catalog_by_name),
        )

    def set_always_active(self, tools: Sequence[BaseTool]) -> None:
        """
        Tools that stay bound on every response without requiring activation
        (e.g. the skills' load_skill tool).
        """
        self._always_active = list(tools)
        logger.info(
            "Always-active tools: %s", [t.name for t in self._always_active]
        )

    def update_chat_model(self, chat_model: BaseChatModel) -> None:
        """
        Updates the underlying chat model (e.g. when switching provider).
        """
        self.chat_model = chat_model

    @property
    def has_context(self) -> bool:
        """True if there is any catalog entry or always-active tool to expose."""
        return bool(self._catalog_by_name or self._always_active)

    def _resolve_activations(self, names: list[str]) -> tuple[list[str], list[str]]:
        """
        Resolves requested names against the catalog, by exact tool name or by
        MCP server name. Returns (activated_tool_names, unknown_names).
        """
        catalog_lower = {k.lower(): k for k in self._catalog_by_name}
        servers_lower = {k.lower(): v for k, v in self._tools_by_server.items()}

        activated: list[str] = []
        seen: set[str] = set()
        unknown: list[str] = []

        for raw in names:
            key = str(raw).strip().lower().strip("`").lstrip("@").lstrip("#")
            if not key:
                continue

            if key in catalog_lower:
                real = catalog_lower[key]
                if real not in seen:
                    seen.add(real)
                    activated.append(real)
            elif key in servers_lower:
                for tool in servers_lower[key]:
                    if tool.name not in seen:
                        seen.add(tool.name)
                        activated.append(tool.name)
            else:
                unknown.append(str(raw))

        return activated, unknown

    def activate_tools(self, names: list[str]) -> str:
        """
        Public activation entry point (shared state, used outside of execute,
        e.g. by tests or manual tooling). For per-response activation the
        engine builds an isolated closure inside execute().
        """
        activated, unknown = self._resolve_activations(names)
        return self._activation_summary(activated, unknown)

    @staticmethod
    def _activation_summary(activated: list[str], unknown: list[str]) -> str:
        parts = []
        if activated:
            parts.append(f"✅ Activadas {len(activated)} herramienta(s): {', '.join(activated)}")
        if unknown:
            parts.append(
                f"⚠️ No encontradas en el catálogo: {', '.join(unknown)}. "
                "Usa nombres exactos de 'Available tools' o de un servidor MCP."
            )
        return "\n".join(parts) if parts else "No se activó ninguna herramienta."

    async def execute(
        self,
        messages: list[BaseMessage],
        current_context: dict[str, Any] | None = None,
    ) -> str:
        """
        Executes the progressive-disclosure tool loop:
        1. Starts each response with only meta-tools + always-active tools.
        2. Model decides zero-shot whether to activate more tools or answer.
        3. activate_tools binds requested schemas for subsequent iterations.
        4. Tool results are fed back as ToolMessages until the model answers.
        """
        if current_context:
            save_current_context(current_context)

        if not self.has_context:
            response = await self.chat_model.ainvoke(messages)
            return str(response.content)

        # Per-request tool state: isolated per execute() call (multi-user safe)
        runtime: dict[str, Any] = {
            "by_name": {t.name: t for t in self._always_active},
            "bound": self.chat_model,
        }

        def rebind() -> None:
            meta = [create_activate_tools_tool(activate_fn)]
            tools = [*meta, *runtime["by_name"].values()]
            runtime["bound"] = (
                self.chat_model.bind_tools(tools) if tools else self.chat_model
            )

        def activate_fn(names: list[str]) -> str:
            activated, unknown = self._resolve_activations(names)
            for name in activated:
                runtime["by_name"][name] = self._catalog_by_name[name]
            rebind()
            summary = self._activation_summary(activated, unknown)
            logger.info("activate_tools: %s", summary.replace("\n", " | "))
            return summary

        rebind()

        current_messages = list(messages)

        for iteration in range(self.max_iterations):
            logger.debug("Zero-shot tooling iteration %d/%d", iteration + 1, self.max_iterations)
            response = await runtime["bound"].ainvoke(current_messages)

            # Check if model requested tool execution
            tool_calls = getattr(response, "tool_calls", None)
            if not tool_calls:
                # Zero-shot completion: model answered directly without needing more tools
                return str(response.content)

            # Append assistant response containing tool_calls
            current_messages.append(response)

            for call in tool_calls:
                tool_name = call.get("name")
                tool_args = call.get("args", {})
                tool_id = call.get("id", f"call_{iteration}_{tool_name}")

                # Auto-inject current guild_id if missing and tool supports it
                if current_context and current_context.get("guild_id"):
                    active_gid = str(current_context["guild_id"])
                    if "guild_id" not in tool_args or not tool_args.get("guild_id"):
                        tool = runtime["by_name"].get(tool_name)
                        tool_schema = getattr(tool, "args", {}) if tool else {}
                        if "guild_id" in tool_schema or "guild" in str(tool_name):
                            tool_args["guild_id"] = active_gid
                            logger.info(
                                "Auto-injected current guild_id='%s' into tool '%s'",
                                active_gid,
                                tool_name,
                            )

                logger.info("Model requested tool '%s' with args: %s", tool_name, tool_args)

                # Meta-tool: activation is handled in-process, never via by_name
                if str(tool_name or "").strip().lower() == ACTIVATE_TOOLS_NAME:
                    summary = activate_fn(extract_names_args(tool_args))
                    current_messages.append(
                        ToolMessage(content=summary, tool_call_id=tool_id)
                    )
                    continue

                tool = runtime["by_name"].get(tool_name)

                if not tool:
                    error_msg = (
                        f"Error: Tool '{tool_name}' is not active. "
                        "Call activate_tools with its name (or its server name) first."
                    )
                    logger.warning(error_msg)
                    current_messages.append(ToolMessage(content=error_msg, tool_call_id=tool_id))
                    continue

                try:
                    tool_output = await tool.ainvoke(tool_args)
                    logger.info("Tool '%s' returned: %s", tool_name, str(tool_output)[:200])
                    current_messages.append(
                        ToolMessage(content=str(tool_output), tool_call_id=tool_id)
                    )
                except Exception as e:
                    logger.error("Error executing tool '%s': %s", tool_name, e, exc_info=True)
                    current_messages.append(
                        ToolMessage(
                            content=f"Error executing tool '{tool_name}': {e}",
                            tool_call_id=tool_id,
                        )
                    )

        # Max iterations reached, request final synthesis without further tool calls
        final_response = await self.chat_model.ainvoke(current_messages)
        return str(final_response.content)
