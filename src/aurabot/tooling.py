import json
import logging
from pathlib import Path
from typing import Sequence, Any
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, ToolMessage
from langchain_core.tools import BaseTool

logger = logging.getLogger("DiscordBot")


class ZeroShotTooling:
    """
    Zero-Shot Tool-Calling execution engine for LangChain chat models.
    Orchestrates tool binding, model invocation, tool detection, execution,
    and iterative multi-step reasoning.
    """

    def __init__(
        self,
        chat_model: BaseChatModel,
        tools: Sequence[BaseTool] | None = None,
        max_iterations: int = 5,
    ):
        self.chat_model = chat_model
        self.tools: list[BaseTool] = list(tools) if tools else []
        self.max_iterations = max_iterations
        self._tools_by_name: dict[str, BaseTool] = {t.name: t for t in self.tools}
        self._bound_model = (
            self.chat_model.bind_tools(self.tools) if self.tools else self.chat_model
        )

    def update_tools(self, tools: Sequence[BaseTool]) -> None:
        """
        Updates active tools and re-binds them to the chat model.
        """
        self.tools = list(tools)
        self._tools_by_name = {t.name: t for t in self.tools}
        self._bound_model = (
            self.chat_model.bind_tools(self.tools) if self.tools else self.chat_model
        )
        logger.info("Updated ZeroShotTooling with %d tool(s): %s", len(self.tools), list(self._tools_by_name.keys()))

    def update_chat_model(self, chat_model: BaseChatModel) -> None:
        """
        Updates the underlying chat model (e.g. when switching provider).
        """
        self.chat_model = chat_model
        self._bound_model = (
            self.chat_model.bind_tools(self.tools) if self.tools else self.chat_model
        )

    @property
    def has_tools(self) -> bool:
        """Returns True if any tools are currently bound."""
        return len(self.tools) > 0

    async def execute(
        self,
        messages: list[BaseMessage],
        current_context: dict[str, Any] | None = None,
    ) -> str:
        """
        Executes the Zero-Shot tool loop:
        1. Model inspects input messages (system, history, human).
        2. Decides zero-shot whether to call a tool or answer directly.
        3. If tool_calls exist, auto-injects active context (like current guild_id), runs tools, feeds back ToolMessages.
        4. Synthesizes final answer once model stops requesting tools.
        """
        if current_context:
            try:
                context_file = Path("data/current_context.json")
                context_file.parent.mkdir(parents=True, exist_ok=True)
                with open(context_file, "w", encoding="utf-8") as f:
                    json.dump(current_context, f)
            except Exception as e:
                logger.debug("Could not persist current_context.json: %s", e)

        if not self.has_tools:
            response = await self.chat_model.ainvoke(messages)
            return str(response.content)

        current_messages = list(messages)

        for iteration in range(self.max_iterations):
            logger.debug("Zero-shot tooling iteration %d/%d", iteration + 1, self.max_iterations)
            response = await self._bound_model.ainvoke(current_messages)

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
                        tool = self._tools_by_name.get(tool_name)
                        tool_schema = getattr(tool, "args", {}) if tool else {}
                        if "guild_id" in tool_schema or "guild" in str(tool_name):
                            tool_args["guild_id"] = active_gid
                            logger.info(
                                "Auto-injected current guild_id='%s' into tool '%s'",
                                active_gid,
                                tool_name,
                            )

                logger.info("Model requested tool '%s' with args: %s", tool_name, tool_args)
                tool = self._tools_by_name.get(tool_name)

                if not tool:
                    error_msg = f"Error: Tool '{tool_name}' is not available."
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
