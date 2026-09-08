import asyncio

import discord

from aurabot.config import config
from aurabot.tooling.context import read_active_guild_id

# Gateway Discord Client with member & presence intents for real-time status/activities
_intents = discord.Intents.default()
_intents.message_content = True
_intents.members = True
_intents.presences = True

_discord_client = discord.Client(intents=_intents)
_client_ready = asyncio.Event()


@_discord_client.event
async def on_ready():
    _client_ready.set()


async def ensure_client() -> discord.Client:
    """
    Ensures the gateway Discord client is connected and ready.
    """
    token = config.discord_token
    if not token:
        raise ValueError("Discord bot token not found in DISCORD_BOT_TOKEN or config.json")

    if not _client_ready.is_set():
        await _discord_client.login(token)
        asyncio.create_task(_discord_client.connect())
        try:
            await asyncio.wait_for(_client_ready.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            pass
    return _discord_client


def resolve_target_guilds(client: discord.Client, guild_id: str = "") -> list[discord.Guild]:
    """
    Resolves the target guild strictly from the requested guild_id (ID or name)
    or from the active conversation context. Never guesses: if there is no
    explicit request and no active guild (e.g. a DM conversation), returns [].
    """
    active_id = guild_id.strip() if guild_id else read_active_guild_id()
    if not active_id:
        return []

    clean = active_id.lower()
    return [
        g for g in client.guilds
        if str(g.id) == clean or clean in g.name.lower()
    ]
