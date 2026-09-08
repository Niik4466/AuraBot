"""
Timezone utilities shared by the bot process and the MCP server subprocess.
The bot's display timezone comes from the TZ environment variable
(e.g. 'America/Santiago' in docker-compose). Falls back to UTC.
"""
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_UTC = timezone.utc


def local_tz() -> timezone | ZoneInfo:
    """
    Returns the configured display timezone (TZ env var), or UTC if unset
    or unrecognized (e.g. system tzdata missing).
    """
    name = os.environ.get("TZ", "").strip()
    if name:
        try:
            return ZoneInfo(name)
        except Exception:
            pass
    return _UTC


def to_local(dt: datetime) -> datetime:
    """
    Converts a datetime to the display timezone. Naive datetimes are
    assumed to be UTC (Discord timestamps are always UTC-aware anyway).
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_UTC)
    return dt.astimezone(local_tz())


def format_local(dt: datetime, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """
    Formats a datetime in the display timezone.
    """
    return to_local(dt).strftime(fmt)
