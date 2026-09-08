import discord
from datetime import datetime

from aurabot.config.timeutils import to_local

DISCORD_MESSAGE_LIMIT = 2000


def format_user_name(user: discord.User | discord.Member) -> str:
    """
    Formats a user's name as: username (social_name)
    Example: user1234 (el mas capito)
    """
    username = getattr(user, "name", "user")
    display_name = getattr(user, "display_name", None)
    if display_name and display_name.strip() and display_name.strip() != username:
        return f"{username} ({display_name.strip()})"
    return username


def format_user_label(
    user: discord.User | discord.Member,
    timestamp: datetime | None = None,
) -> str:
    """
    Formats a user's name plus an optional message date as:
    username (social_name) (YYYY-MM-DD)
    Example: user1234 (el mas capito) (2025-12-10)
    """
    label = format_user_name(user)
    if timestamp:
        label = f"{label} ({to_local(timestamp).strftime('%Y-%m-%d')})"
    return label


def split_message(text: str, limit: int = DISCORD_MESSAGE_LIMIT) -> list[str]:
    """
    Splits a text into chunks that fit Discord's message length limit.
    """
    if len(text) <= limit:
        return [text]
    return [text[i:i + limit] for i in range(0, len(text), limit)]
