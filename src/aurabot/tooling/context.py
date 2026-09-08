import json
import logging
from pathlib import Path

logger = logging.getLogger("DiscordBot")

# Shared contract between the bot process and the MCP server subprocess:
# the bot persists the active conversation context here, and MCP tools
# read it to resolve the "active" guild when none is passed explicitly.
CONTEXT_FILE = Path("data/current_context.json")


def save_current_context(context: dict) -> None:
    """
    Persists the current conversation context (guild, channel) for MCP tools.
    """
    try:
        CONTEXT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONTEXT_FILE, "w", encoding="utf-8") as f:
            json.dump(context, f)
    except Exception as e:
        logger.debug("Could not persist current_context.json: %s", e)


def read_active_context() -> dict:
    """
    Reads the full active conversation context (guild_id, channel_id,
    channel_name, is_dm) from the context file. Returns {} if absent/invalid.
    """
    if CONTEXT_FILE.exists():
        try:
            with open(CONTEXT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}


def read_active_guild_id() -> str:
    """
    Reads the active guild ID from the context file if present.
    Empty string means no active guild (e.g. a DM conversation).
    """
    return str(read_active_context().get("guild_id") or "").strip()
