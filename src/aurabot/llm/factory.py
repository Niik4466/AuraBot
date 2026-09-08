import logging

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from aurabot.config import OllamaConfig, OpenRouterConfig

logger = logging.getLogger("DiscordBot")


def create_chat_model(
    provider: str,
    ollama_cfg: OllamaConfig,
    openrouter_cfg: OpenRouterConfig,
) -> BaseChatModel:
    """
    Instantiates the LangChain chat model for the configured provider
    (Ollama for local inference, OpenRouter via the OpenAI-compatible API).
    """
    if provider == "openrouter":
        logger.info(
            "Initializing LangChain ChatOpenAI for OpenRouter (model=%s, base_url=%s, temperature=%.2f)",
            openrouter_cfg.model,
            openrouter_cfg.base_url,
            openrouter_cfg.temperature,
        )
        return ChatOpenAI(
            base_url=openrouter_cfg.base_url,
            api_key=openrouter_cfg.api_key or "missing_key",
            model=openrouter_cfg.model,
            temperature=openrouter_cfg.temperature,
        )

    # Default to Ollama
    logger.info(
        "Initializing LangChain ChatOllama (model=%s, base_url=%s, temperature=%.2f)",
        ollama_cfg.model,
        ollama_cfg.get_clean_base_url(),
        ollama_cfg.temperature,
    )
    return ChatOllama(
        model=ollama_cfg.model,
        base_url=ollama_cfg.get_clean_base_url(),
        temperature=ollama_cfg.temperature,
    )
