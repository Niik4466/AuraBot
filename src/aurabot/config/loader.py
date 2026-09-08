import json
import logging
import os
from pathlib import Path

from aurabot.config.models import (
    Config,
    DiscordConfig,
    OllamaConfig,
    OpenRouterConfig,
    StorageConfig,
)

logger = logging.getLogger("DiscordBot")

# Repo root (src/aurabot/config/loader.py -> project root)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SRC_DIR = Path(__file__).resolve().parents[2]


def find_config_file(path_hint: str | Path | None = None) -> Path | None:
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
        _PROJECT_ROOT / "config.json",
        _SRC_DIR / "config.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def load_config(path: str | Path | None = None) -> Config:
    """
    Loads configuration from config.json with fallbacks and environment overrides.
    """
    config_path = find_config_file(path)
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
    skills_dir = (
        os.getenv("SKILLS_DIR")
        or storage_data.get("skills_dir")
        or "skills"
    )
    active_skills_file = (
        storage_data.get("active_skills_file")
        or "data/active_skills.json"
    )

    # Fallback message
    fallback_message = (
        os.getenv("FALLBACK_MESSAGE")
        or data.get("fallback_message")
        or "No estoy disponible en este momento"
    )

    # MCP Servers configuration
    mcp_servers = data.get("mcp_servers") or data.get("mcpServers") or {}

    return Config(
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
        storage=StorageConfig(
            prompts_file=prompts_file,
            skills_dir=skills_dir,
            active_skills_file=active_skills_file,
        ),
        mcp_servers=mcp_servers,
    )


# Global configuration singleton
config = load_config()
