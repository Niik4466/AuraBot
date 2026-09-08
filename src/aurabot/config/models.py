from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# Repo root (src/aurabot/config/models.py -> project root)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


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
    skills_dir: str = "skills"
    active_skills_file: str = "data/active_skills.json"


@dataclass
class Config:
    provider: str = "ollama"  # "ollama" or "openrouter"
    fallback_message: str = "I'm not avaible in this moment, try again later."
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    openrouter: OpenRouterConfig = field(default_factory=OpenRouterConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    mcp_servers: dict[str, Any] = field(default_factory=dict)

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
        return _PROJECT_ROOT / p

    @property
    def skills_dir_path(self) -> Path:
        p = Path(self.storage.skills_dir)
        if p.is_absolute():
            return p
        return _PROJECT_ROOT / p

    @property
    def active_skills_file_path(self) -> Path:
        p = Path(self.storage.active_skills_file)
        if p.is_absolute():
            return p
        return _PROJECT_ROOT / p
