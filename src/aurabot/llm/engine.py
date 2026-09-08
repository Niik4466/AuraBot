import logging
import re
from typing import Sequence

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from aurabot.config import config, OllamaConfig, OpenRouterConfig
from aurabot.llm.factory import create_chat_model
from aurabot.llm.history import to_langchain_messages
from aurabot.llm.prompts import build_system_prompt
from aurabot.mcp import mcp_manager
from aurabot.tooling import ZeroShotTooling

logger = logging.getLogger("DiscordBot")


class LLM:
    """
    Encapsulates LLM behavior, prompt construction, and LangChain integration.
    Supports switching between Ollama (local) and OpenRouter (cloud) using the same LangChain pipeline.
    Utilizes structured LangChain message roles: 'system', 'user', and 'assistant'.
    """

    FALLBACK_MESSAGE = config.fallback_message or "I'm not avaible in this moment, try again later."

    def __init__(
        self,
        provider: str | None = None,
        ollama_cfg: OllamaConfig | None = None,
        openrouter_cfg: OpenRouterConfig | None = None,
    ):
        self.provider = (provider or config.provider).lower().strip()
        self.ollama_cfg = ollama_cfg or config.ollama
        self.openrouter_cfg = openrouter_cfg or config.openrouter

        # Instantiate the appropriate LangChain chat model based on provider
        self.chat_model = create_chat_model(
            provider=self.provider,
            ollama_cfg=self.ollama_cfg,
            openrouter_cfg=self.openrouter_cfg,
        )

        # Standard LCEL chain with explicit roles:
        # 1. System role: Persona, rules, and style examples
        # 2. Chat history placeholder: Sequence of HumanMessage (user) and AIMessage (assistant)
        # 3. Human role: Current user trigger message
        self.prompt_template = ChatPromptTemplate.from_messages([
            ("system", "{system_prompt}"),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{user_content}"),
        ])
        self.output_parser = StrOutputParser()
        self.chain = self.prompt_template | self.chat_model | self.output_parser

        # Zero-Shot Tooling engine connection
        self.tooling = ZeroShotTooling(chat_model=self.chat_model)

    async def load_tools(self) -> None:
        """
        Refreshes the tools catalog from MCPManager for progressive disclosure
        (schemas are bound on demand by the model via activate_tools).
        """
        tools = await mcp_manager.get_tools()
        tools_by_server = await mcp_manager.get_tools_by_server()
        self.tooling.update_catalog(tools, tools_by_server=tools_by_server)

    @property
    def model_name(self) -> str:
        if self.provider == "openrouter":
            return self.openrouter_cfg.model
        return self.ollama_cfg.model

    @staticmethod
    def _clean_response(text: str) -> str:
        """
        Strips reasoning tags (<think>...</think>) and unnecessary whitespace.
        """
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        return cleaned if cleaned else text.strip()

    async def generate_reply(
        self,
        bot_name: str,
        author_name: str,
        user_message: str,
        personal_prompt: str | None = None,
        channel_history: Sequence[tuple[str, str, bool] | tuple[str, str]] | None = None,
        guild_id: str | None = None,
        guild_name: str | None = None,
        channel_id: str | None = None,
        channel_name: str | None = None,
        skills_section: str = "",
        tools_section: str = "",
        reply_chain: Sequence[tuple[str, str, bool]] | None = None,
        user_history_section: str = "",
    ) -> str:
        """
        Generates a bot reply using structured LangChain message roles (system, user, assistant).
        Includes progressive-disclosure sections for active skills and the tools catalog.
        """
        try:
            system_prompt = build_system_prompt(
                bot_name=bot_name,
                personal_prompt=personal_prompt,
                guild_id=guild_id,
                guild_name=guild_name,
                channel_id=channel_id,
                channel_name=channel_name,
                skills_section=skills_section,
                tools_section=tools_section,
                user_history_section=user_history_section,
            )
            chat_history_messages = to_langchain_messages(
                bot_name=bot_name,
                channel_history=channel_history,
            )
            chain_block = ""
            if reply_chain:
                chain_lines = "\n".join(
                    f"{'[AuraBot (you)]' if is_bot else f'[{author}]'}: {content}"
                    for author, content, is_bot in reply_chain
                )
                chain_block = (
                    "Conversation thread (the messages this user was replying to, "
                    f"oldest first):\n{chain_lines}\n\n"
                )

            user_content = (
                f"{chain_block}"
                f"[{author_name}] (this is the message that triggered you: it mentions "
                f"or replies to you. Reply ONLY to this user about this message): {user_message}"
            )

            current_context = {
                "guild_id": guild_id or "",
                "guild_name": guild_name or "",
                "channel_id": channel_id or "",
                "channel_name": channel_name or "",
                "is_dm": guild_id is None,
            }

            logger.debug(
                "Generating reply for %s via LangChain (%s, model=%s) with %d history messages (guild=%s)",
                author_name,
                self.provider,
                self.model_name,
                len(chat_history_messages),
                guild_name,
            )
            # If there is a tools catalog (meta-tools + skills), execute through
            # the ZeroShotTooling engine; otherwise use the plain LCEL chain
            if self.tooling.has_context:
                messages: list[BaseMessage] = [
                    SystemMessage(content=system_prompt),
                    *chat_history_messages,
                    HumanMessage(content=user_content),
                ]
                raw_response = await self.tooling.execute(
                    messages=messages,
                    current_context=current_context,
                )
            else:
                raw_response = await self.chain.ainvoke({
                    "system_prompt": system_prompt,
                    "chat_history": chat_history_messages,
                    "user_content": user_content,
                })
            return self._clean_response(raw_response)

        except Exception as e:
            logger.error(
                "Error communicating with %s via LangChain: %s",
                self.provider,
                e,
                exc_info=True,
            )
            return self.FALLBACK_MESSAGE

    async def generate_from_messages(self, messages: list[BaseMessage]) -> str:
        """
        Directly invokes the underlying chat model with BaseMessage objects.
        """
        try:
            response = await self.chat_model.ainvoke(messages)
            content = response.content
            if isinstance(content, str):
                return self._clean_response(content)
            return str(content)
        except Exception as e:
            logger.error(
                "Error communicating with %s via LangChain: %s",
                self.provider,
                e,
                exc_info=True,
            )
            return self.FALLBACK_MESSAGE


# Singleton LLM instance
llm = LLM()
