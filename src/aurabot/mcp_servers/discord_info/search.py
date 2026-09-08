import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import discord

from aurabot.config.timeutils import format_local

# Search caps shared by the message search tools
MAX_MESSAGES_LIMIT = 50
MAX_SCAN_PER_CHANNEL = 500
MAX_CHARS_PER_MESSAGE = 400
MAX_TOTAL_CHARS = 6000

_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
_RELATIVE_PATTERN = re.compile(r"(\d+)\s*(m|h|d|w)")
_RELATIVE_DELTAS = {
    "m": timedelta(minutes=1),
    "h": timedelta(hours=1),
    "d": timedelta(days=1),
    "w": timedelta(weeks=1),
}
_VALID_HAS_TYPES = {"image", "video", "file", "link", "embed", "sticker"}


@dataclass
class ScanHit:
    timestamp: datetime
    channel_name: str
    author_label: str
    content: str
    reaction_count: int
    attachment_count: int


@dataclass
class ScanResult:
    hits: list[ScanHit]
    truncated: bool = False


def parse_time_filter(value: str) -> datetime | None:
    """
    Parses a time filter as an ISO date ('YYYY-MM-DD'), a datetime
    ('YYYY-MM-DD HH:MM'), or a relative offset ('30m', '24h', '7d', '30d').
    Returns an aware UTC datetime, or None if the value is invalid or empty.
    """
    if not value:
        return None
    raw = value.strip().lower()

    relative = _RELATIVE_PATTERN.fullmatch(raw)
    if relative:
        amount = int(relative.group(1))
        return datetime.now(timezone.utc) - amount * _RELATIVE_DELTAS[relative.group(2)]

    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def parse_contains_keywords(value: str) -> list[str]:
    """
    Parses a comma-separated keyword list into lowercase keywords (OR match).
    """
    return [k.strip().lower() for k in value.split(",") if k.strip()]


def parse_has_types(value: str) -> set[str]:
    """
    Parses a comma-separated content-type list. Unknown types are ignored.
    """
    return {t.strip().lower() for t in value.split(",") if t.strip().lower() in _VALID_HAS_TYPES}


def format_author_label(user: Any) -> str:
    """
    Formats a message author as: username (social_name).
    Kept local to this module so the MCP server subprocess does not need to
    import the bot stack.
    """
    username = getattr(user, "name", "user")
    display_name = getattr(user, "display_name", None)
    if display_name and display_name.strip() and display_name.strip() != username:
        return f"{username} ({display_name.strip()})"
    return username


def message_matches_filters(
    msg: discord.Message,
    contains_keywords: list[str] | None = None,
    has_types: set[str] | None = None,
    min_reactions: int = 0,
    pinned_only: bool = False,
) -> bool:
    """
    Client-side filter predicate for messages (content keywords, content types,
    reactions and pinned status).
    """
    if pinned_only and not msg.pinned:
        return False

    total_reactions = sum(r.count for r in msg.reactions)
    if total_reactions < min_reactions:
        return False

    if has_types and not _message_has_types(msg, has_types):
        return False

    if contains_keywords:
        content = msg.clean_content.lower()
        if not any(k in content for k in contains_keywords):
            return False

    return True


def _message_has_types(msg: discord.Message, has_types: set[str]) -> bool:
    content_types = {a.content_type for a in msg.attachments if a.content_type}
    for t in has_types:
        if t == "image" and any(ct.startswith("image") for ct in content_types):
            return True
        if t == "video" and any(ct.startswith("video") for ct in content_types):
            return True
        if t == "file" and msg.attachments:
            return True
        if t == "link" and _URL_PATTERN.search(msg.clean_content):
            return True
        if t == "embed" and msg.embeds:
            return True
        if t == "sticker" and msg.stickers:
            return True
    return False


def resolve_search_channels(
    guild: discord.Guild,
    channel_name_or_id: str = "",
) -> list[discord.TextChannel]:
    """
    Resolves the text channels to search in a guild: one specific channel by
    name or ID, or all readable text channels.
    """
    if channel_name_or_id:
        clean_ch = channel_name_or_id.strip().lstrip("#").lower()
        for ch in guild.text_channels:
            if str(ch.id) == clean_ch or ch.name.lower() == clean_ch:
                return [ch]
        return []

    return [
        ch for ch in guild.text_channels
        if ch.permissions_for(guild.me).read_messages
        and ch.permissions_for(guild.me).read_message_history
    ]


def _is_private_channel(channel: Any) -> bool:
    """
    Duck-typed check for DM/group-DM channels (discord.py types differ but
    always expose recipient(s) and text channels never do).
    """
    return channel is not None and (
        hasattr(channel, "recipient") or hasattr(channel, "recipients")
    )


async def resolve_dm_channel(client: Any, channel_id: str) -> Any:
    """
    Resolves the current DM conversation channel by ID, first from the client
    cache and then via the REST API (DM channels are not always cached).
    Returns the channel or None if it cannot be accessed.
    """
    clean = str(channel_id or "").strip()
    if not clean.isdigit():
        return None

    try:
        cached = client.get_channel(int(clean))
    except Exception:
        cached = None
    if _is_private_channel(cached):
        return cached

    try:
        fetched = await client.fetch_channel(int(clean))
    except Exception:
        return None
    return fetched if _is_private_channel(fetched) else None


def resolve_default_channel(guild: Any, channel_id: str) -> Any:
    """
    Resolves the current conversation channel (by ID) inside a guild, so
    search tools default to the channel where the user is talking.
    """
    clean = str(channel_id or "").strip()
    if not clean.isdigit():
        return None
    try:
        ch = guild.get_channel(int(clean))
    except Exception:
        return None
    if ch is None or _is_private_channel(ch):
        return None
    if not (hasattr(ch, "guild") and hasattr(ch, "name") and hasattr(ch, "history")):
        return None
    return ch


@dataclass
class SearchScope:
    """
    Where a message search will run: the resolved channels plus the scope
    kind (guild conversation or private DM conversation).
    """
    channels: list
    guild: Any | None = None
    dm: bool = False

    @property
    def label(self) -> str:
        return self.guild.name if self.guild else "esta conversación privada"


async def scan_messages(
    channels: list[discord.TextChannel],
    predicate: Callable[[discord.Message], bool],
    limit: int,
    before: datetime | None = None,
    after: datetime | None = None,
) -> ScanResult:
    """
    Scans channel histories (deepest scan: MAX_SCAN_PER_CHANNEL per channel),
    passing date bounds to the Discord API and applying the predicate
    client-side. Stops early once the message limit or the total character cap
    is reached, flagging the result as truncated.
    """
    hits: list[ScanHit] = []
    total_chars = 0
    truncated = False

    for ch in channels:
        channel_label = getattr(ch, "name", None) or "DM"
        if len(hits) >= limit:
            truncated = True
            break
        try:
            async for msg in ch.history(limit=MAX_SCAN_PER_CHANNEL, before=before, after=after):
                if not predicate(msg):
                    continue

                text = msg.clean_content.strip()
                if len(text) > MAX_CHARS_PER_MESSAGE:
                    text = text[:MAX_CHARS_PER_MESSAGE] + "..."

                total_chars += len(text)
                hits.append(ScanHit(
                    timestamp=msg.created_at,
                    channel_name=channel_label,
                    author_label=format_author_label(msg.author),
                    content=text or "(sin contenido de texto)",
                    reaction_count=sum(r.count for r in msg.reactions),
                    attachment_count=len(msg.attachments),
                ))

                if len(hits) >= limit or total_chars >= MAX_TOTAL_CHARS:
                    truncated = True
                    break
        except (discord.Forbidden, discord.HTTPException):
            continue

    return ScanResult(hits=hits, truncated=truncated)
