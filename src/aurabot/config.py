import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger("DiscordBot")


@dataclass
class DiscordConfig:
    token: str = ""


@dataclass
class OllamaConfig:
    base_url: str = "http://localhost:11434"
    model: str = "gemma4:26b"
    temperature: float = 0.7

    def get_clean_base_url(self) -> str:
        """
        Normalizes the base URL by stripping API endpoints like /api/generate or /v1.
        """
        raw = self.base_url.strip()
        parsed = urlparse(raw)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        return raw


@dataclass
class OpenRouterConfig:
    api_key: str = ""
    model: str = "deepseek/deepseek-chat"
    temperature: float = 0.7
    base_url: str = "https://openrouter.ai/api/v1"


@dataclass
class StorageConfig:
    prompts_file: str = "data/personal_prompts.json"


@dataclass
class Config:
    provider: str = "ollama"  # "ollama" or "openrouter"
    fallback_message: str = "No estoy disponible en este momento"
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    openrouter: OpenRouterConfig = field(default_factory=OpenRouterConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    mcp_servers: dict[str, Any] = field(default_factory=dict)



    @classmethod
    def find_config_file(cls, path_hint: str | Path | None = None) -> Path | None:
        """
        Searches for config.json using optional path hint or known directory locations.
        """
        if path_hint:
            p = Path(path_hint)
            if p.exists():
                return p.resolve()

        # Check CONFIG_PATH environment variable
        env_config = os.getenv("CONFIG_PATH")
        if env_config and Path(env_config).exists():
            return Path(env_config).resolve()

        # Check standard project locations
        candidates = [
            Path("config.json"),
            Path(__file__).resolve().parent.parent.parent / "config.json",
            Path(__file__).resolve().parent.parent / "config.json",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()
        return None

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        """
        Loads configuration from config.json with fallbacks and environment overrides.
        """
        config_path = cls.find_config_file(path)
        data: dict = {}

        if config_path:
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                logger.info("Loaded configuration from %s", config_path)
            except Exception as e:
                logger.error("Failed to load %s: %s. Using default configuration.", config_path, e)
        else:
            logger.warning("config.json not found in root or current path. Using default configuration.")

        # Provider selection ("ollama" or "openrouter")
        raw_provider = (
            os.getenv("LLM_PROVIDER")
            or data.get("provider")
            or "ollama"
        ).lower().strip()
        if raw_provider not in ("ollama", "openrouter"):
            logger.warning("Unknown provider '%s', defaulting to 'ollama'", raw_provider)
            provider = "ollama"
        else:
            provider = raw_provider

        # Discord configuration
        discord_data = data.get("discord", {})
        discord_token = (
            os.getenv("DISCORD_BOT_TOKEN")
            or discord_data.get("token")
            or data.get("discord_token")
            or ""
        )

        # Ollama configuration
        ollama_data = data.get("ollama", {})
        ollama_base_url = (
            os.getenv("OLLAMA_BASE_URL")
            or ollama_data.get("base_url")
            or data.get("ollama_base_url")
            or "http://localhost:11434"
        )
        ollama_model = (
            os.getenv("OLLAMA_MODEL")
            or ollama_data.get("model")
            or data.get("ollama_model")
            or "gemma4:26b"
        )
        raw_ollama_temp = (
            os.getenv("OLLAMA_TEMPERATURE")
            or ollama_data.get("temperature")
            or data.get("ollama_temperature")
            or 0.7
        )
        try:
            ollama_temperature = float(raw_ollama_temp)
        except ValueError:
            ollama_temperature = 0.7

        # OpenRouter configuration (named "OpenRouter" in config.json as requested)
        openrouter_data = data.get("OpenRouter") or data.get("openrouter", {})
        openrouter_api_key = (
            os.getenv("OPENROUTER_API_KEY")
            or openrouter_data.get("api_key")
            or ""
        )
        openrouter_model = (
            os.getenv("OPENROUTER_MODEL")
            or openrouter_data.get("model")
            or "deepseek/deepseek-chat"
        )
        raw_or_temp = (
            os.getenv("OPENROUTER_TEMPERATURE")
            or openrouter_data.get("temperature")
            or 0.7
        )
        try:
            openrouter_temperature = float(raw_or_temp)
        except ValueError:
            openrouter_temperature = 0.7

        openrouter_base_url = (
            os.getenv("OPENROUTER_BASE_URL")
            or openrouter_data.get("base_url")
            or "https://openrouter.ai/api/v1"
        )

        # Storage configuration
        storage_data = data.get("storage", {})
        prompts_file = (
            storage_data.get("prompts_file")
            or data.get("prompts_file")
            or "data/personal_prompts.json"
        )

        # Fallback message
        fallback_message = (
            os.getenv("FALLBACK_MESSAGE")
            or data.get("fallback_message")
            or "No estoy disponible en este momento"
        )

        # MCP Servers configuration
        mcp_servers = data.get("mcp_servers") or data.get("mcpServers") or {}

        return cls(
            provider=provider,
            fallback_message=fallback_message,
            discord=DiscordConfig(token=discord_token),
            ollama=OllamaConfig(
                base_url=ollama_base_url,
                model=ollama_model,
                temperature=ollama_temperature,
            ),
            openrouter=OpenRouterConfig(
                api_key=openrouter_api_key,
                model=openrouter_model,
                temperature=openrouter_temperature,
                base_url=openrouter_base_url,
            ),
            storage=StorageConfig(prompts_file=prompts_file),
            mcp_servers=mcp_servers,
        )

    @property
    def discord_token(self) -> str:
        return self.discord.token

    @property
    def ollama_base_url(self) -> str:
        return self.ollama.get_clean_base_url()

    @property
    def ollama_model(self) -> str:
        return self.ollama.model

    @property
    def ollama_temperature(self) -> float:
        return self.ollama.temperature

    @property
    def openrouter_api_key(self) -> str:
        return self.openrouter.api_key

    @property
    def openrouter_model(self) -> str:
        return self.openrouter.model

    @property
    def openrouter_temperature(self) -> float:
        return self.openrouter.temperature

    @property
    def prompts_file_path(self) -> Path:
        p = Path(self.storage.prompts_file)
        if p.is_absolute():
            return p
        root = Path(__file__).resolve().parent.parent.parent
        return root / p


# Global configuration singleton
config = Config.load()
