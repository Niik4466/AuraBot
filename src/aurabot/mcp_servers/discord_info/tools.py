from datetime import datetime
from typing import Any

import httpx
import discord
from mcp.server.fastmcp import FastMCP

from aurabot.config import config
from aurabot.config.timeutils import format_local
from aurabot.mcp_servers.discord_info import mcp
from aurabot.mcp_servers.discord_info.gateway import ensure_client, resolve_target_guilds
from aurabot.mcp_servers.discord_info.matching import find_member
from aurabot.mcp_servers.discord_info.presence import resolve_full_presence
from aurabot.mcp_servers.discord_info.search import (
    MAX_MESSAGES_LIMIT,
    ScanHit,
    SearchScope,
    format_author_label,
    message_matches_filters,
    parse_contains_keywords,
    parse_has_types,
    parse_time_filter,
    resolve_default_channel,
    resolve_dm_channel,
    resolve_search_channels,
    scan_messages,
)
from aurabot.tooling.context import read_active_context

BASE_URL = "https://discord.com/api/v10"


@mcp.tool()
async def get_user_profile(query: str, guild_id: str = "") -> str:
    """
    Retrieves the Discord profile for a user strictly in the server where it was requested.
    Includes status (online/idle/dnd/offline), description/custom status, active music/activities (Spotify/games),
    server nickname, roles, and join date.
    Args:
        query: The username, nickname, or user ID to look up (e.g. 'niik4466' or '890066279778631720').
        guild_id: Optional ID or name of the Discord server/guild. If omitted, automatically uses the active server.
    """
    client = await ensure_client()
    clean_query = query.strip().lstrip("@").lower()

    # Search strictly in the resolved target guild(s)
    target_guilds = resolve_target_guilds(client, guild_id)

    matched_member, matched_guild = find_member(target_guilds, query)

    if matched_member and matched_guild:
        custom_status, activities, status_display = resolve_full_presence(
            client=client,
            user_id=matched_member.id,
            member=matched_member,
        )
        roles = [r.name for r in matched_member.roles if r.name != "@everyone"]
        joined_str = (
            matched_member.joined_at.strftime("%Y-%m-%d")
            if matched_member.joined_at
            else "N/A"
        )
        created_str = matched_member.created_at.strftime("%Y-%m-%d")

        activities_formatted = (
            "\n  - " + "\n  - ".join(activities)
            if activities
            else "Ninguna actividad reportada en este momento"
        )

        return (
            f"👤 **Perfil de Usuario en Servidor ({matched_guild.name}):**\n"
            f"- **Usuario:** `{matched_member.name}`\n"
            f"- **Nombre / Apodo en Servidor:** {matched_member.display_name}\n"
            f"- **ID de Discord:** `{matched_member.id}`\n"
            f"- **Estado Actual:** {status_display}\n"
            f"- **Descripción / Estado Personalizado:** {custom_status}\n"
            f"- **Actividades / Música:** {activities_formatted}\n"
            f"- **Fecha de Ingreso al Servidor:** {joined_str}\n"
            f"- **Cuenta Creada:** {created_str}\n"
            f"- **Roles ({len(roles)}):** {', '.join(roles) if roles else 'Ninguno'}\n"
            f"- **Es Bot:** {'Sí' if matched_member.bot else 'No'}"
        )

    # Fallback to REST API if member not found in server cache
    token = config.discord_token
    headers = {"Authorization": f"Bot {token}"}
    async with httpx.AsyncClient() as http_client:
        if clean_query.isdigit() and len(clean_query) >= 17:
            user_res = await http_client.get(f"{BASE_URL}/users/{clean_query}", headers=headers)
            if user_res.status_code == 200:
                u = user_res.json()
                return (
                    f"👤 **Perfil Global de Discord (ID: {u.get('id')}):**\n"
                    f"- **Usuario:** `{u.get('username')}`\n"
                    f"- **Nombre Global:** {u.get('global_name') or 'N/A'}\n"
                    f"- **Descripción:** {u.get('bio') or 'Sin descripción'}\n"
                    f"- **Es Bot:** {'Sí' if u.get('bot') else 'No'}"
                )

    server_context_hint = f" en el servidor '{target_guilds[0].name}'" if target_guilds else ""
    return f"No se encontró al usuario '{query}'{server_context_hint}."


@mcp.tool()
async def get_user_recent_messages(
    user: str,
    limit: int = 5,
    channel_name_or_id: str = "",
    guild_id: str = "",
    contains: str = "",
    has: str = "",
    after: str = "",
    before: str = "",
    min_reactions: int = 0,
    pinned_only: bool = False,
    sort: str = "oldest",
) -> str:
    """
    Retrieves messages sent by a specific user, prioritizing the current conversation.
    By default it ONLY scans the current channel (or the DM conversation). To scan a
    different channel pass channel_name_or_id; to scan another server pass guild_id
    explicitly (ID or name). It never searches other servers on its own initiative.
    Args:
        user: The username, nickname, or user ID whose messages to retrieve.
        limit: Number of messages to retrieve (decided by the LLM, max 50).
        channel_name_or_id: Optional channel name (e.g. 'chat-general') or numeric channel ID. Only needed for a channel other than the current one.
        guild_id: Optional server/guild ID or name. Only needed to search a server other than the current conversation's.
        contains: Comma-separated keywords that must appear in the message content (OR match, case-insensitive). Example: 'examen, tarea'.
        has: Comma-separated content types the message must include (OR match). Values: image, video, file, link, embed, sticker. Example: 'image,link'.
        after: Only messages sent after this date/time. Accepts 'YYYY-MM-DD', 'YYYY-MM-DD HH:MM' or relative offsets like '30m', '24h', '7d', '30d'.
        before: Only messages sent before this date/time. Same formats as 'after'.
        min_reactions: Minimum total reaction count on each message (e.g. 3).
        pinned_only: If true, only include pinned messages.
        sort: Output order: 'oldest' (default) or 'newest'.
    """
    clamped_limit = min(max(1, limit), MAX_MESSAGES_LIMIT)
    client = await ensure_client()

    scope, error = await _resolve_search_scope(client, guild_id, channel_name_or_id)
    if error:
        return error

    if scope.dm:
        author, error = _resolve_dm_author(scope.channels[0], user)
        if error:
            return error
        author_id = author.id
        author_display = format_author_label(author)
    else:
        target_member, _ = find_member([scope.guild], user)
        if not target_member:
            return f"No se encontró al usuario '{user}' para consultar sus mensajes en {scope.label}."
        author_id = target_member.id
        author_display = target_member.display_name

    after_dt, before_dt, invalid = _parse_date_filters(after, before)
    if invalid:
        return invalid

    keywords = parse_contains_keywords(contains)
    types = parse_has_types(has)

    def predicate(msg: discord.Message) -> bool:
        return (
            msg.author.id == author_id
            and message_matches_filters(msg, keywords, types, min_reactions, pinned_only)
        )

    result = await scan_messages(scope.channels, predicate, clamped_limit, before=before_dt, after=after_dt)

    return _format_hits(
        header=f"💬 **Mensajes de {author_display} en {scope.label}:**",
        hits=result.hits,
        sort=sort,
        keywords=keywords,
        types=types,
        after_dt=after_dt,
        before_dt=before_dt,
        min_reactions=min_reactions,
        pinned_only=pinned_only,
        truncated=result.truncated,
    )


@mcp.tool()
async def search_messages(
    limit: int = 10,
    channel_name_or_id: str = "",
    guild_id: str = "",
    contains: str = "",
    has: str = "",
    after: str = "",
    before: str = "",
    min_reactions: int = 0,
    pinned_only: bool = False,
    sort: str = "oldest",
) -> str:
    """
    Searches messages from ANY user in Discord, prioritizing the current conversation.
    By default it ONLY scans the current channel (or the DM conversation). To scan a
    different channel pass channel_name_or_id; to scan another server pass guild_id
    explicitly (ID or name). It never searches other servers on its own initiative.
    Use this to find what was said about a topic, shared links, images, highly reacted messages, etc.
    Args:
        limit: Number of messages to retrieve (decided by the LLM, max 50).
        channel_name_or_id: Optional channel name (e.g. 'chat-general') or numeric channel ID. Only needed for a channel other than the current one.
        guild_id: Optional server/guild ID or name. Only needed to search a server other than the current conversation's.
        contains: Comma-separated keywords that must appear in the message content (OR match, case-insensitive). Example: 'examen, tarea'.
        has: Comma-separated content types the message must include (OR match). Values: image, video, file, link, embed, sticker. Example: 'image,link'.
        after: Only messages sent after this date/time. Accepts 'YYYY-MM-DD', 'YYYY-MM-DD HH:MM' or relative offsets like '30m', '24h', '7d', '30d'.
        before: Only messages sent before this date/time. Same formats as 'after'.
        min_reactions: Minimum total reaction count on each message (e.g. 3).
        pinned_only: If true, only include pinned messages.
        sort: Output order: 'oldest' (default) or 'newest'.
    """
    clamped_limit = min(max(1, limit), MAX_MESSAGES_LIMIT)
    client = await ensure_client()

    scope, error = await _resolve_search_scope(client, guild_id, channel_name_or_id)
    if error:
        return error

    after_dt, before_dt, invalid = _parse_date_filters(after, before)
    if invalid:
        return invalid

    keywords = parse_contains_keywords(contains)
    types = parse_has_types(has)

    def predicate(msg: discord.Message) -> bool:
        return message_matches_filters(msg, keywords, types, min_reactions, pinned_only)

    result = await scan_messages(scope.channels, predicate, clamped_limit, before=before_dt, after=after_dt)

    return _format_hits(
        header=f"🔎 **Resultados de búsqueda en {scope.label}:**",
        hits=result.hits,
        sort=sort,
        keywords=keywords,
        types=types,
        after_dt=after_dt,
        before_dt=before_dt,
        min_reactions=min_reactions,
        pinned_only=pinned_only,
        truncated=result.truncated,
    )


@mcp.tool()
async def get_server_info(guild_id: str = "") -> str:
    """
    Retrieves information about a Discord server (member count, owner, boost status, channels count, etc.).
    Args:
        guild_id: Optional ID or name of the server. If omitted, uses the active conversation's server (in a DM there is none).
    """
    client = await ensure_client()
    target_guilds = resolve_target_guilds(client, guild_id)

    if not target_guilds:
        if guild_id.strip():
            return f"No encontré un servidor accesible llamado '{guild_id.strip()}'."
        return "No hay un servidor activo en esta conversación (¿es un DM?). Indica un servidor con `guild_id` (ID o nombre)."

    target_guild = target_guilds[0]
    online_count = sum(1 for m in target_guild.members if m.status != discord.Status.offline)
    owner = target_guild.owner.name if target_guild.owner else str(target_guild.owner_id)

    return (
        f"🏰 **Información del Servidor: {target_guild.name}**\n"
        f"- **ID del Servidor:** `{target_guild.id}`\n"
        f"- **Descripción:** {target_guild.description or 'Sin descripción'}\n"
        f"- **Miembros Totales:** {target_guild.member_count} (En línea: {online_count})\n"
        f"- **Dueño:** {owner}\n"
        f"- **Nivel de Boosts:** Nivel {target_guild.premium_tier} ({target_guild.premium_subscription_count} boosts)\n"
        f"- **Canales de Texto:** {len(target_guild.text_channels)}\n"
        f"- **Canales de Voz:** {len(target_guild.voice_channels)}\n"
        f"- **Cantidad de Roles:** {len(target_guild.roles)}"
    )


@mcp.tool()
async def list_server_channels(guild_id: str = "") -> str:
    """
    Lists the text and voice channels available in the Discord server.
    Args:
        guild_id: Optional ID or name of the server. If omitted, uses the active conversation's server (in a DM there is none).
    """
    client = await ensure_client()
    target_guilds = resolve_target_guilds(client, guild_id)

    if not target_guilds:
        if guild_id.strip():
            return f"No encontré un servidor accesible llamado '{guild_id.strip()}'."
        return "No hay un servidor activo en esta conversación (¿es un DM?). Indica un servidor con `guild_id` (ID o nombre)."

    target_guild = target_guilds[0]
    text_channels = [c.name for c in target_guild.text_channels]
    voice_channels = [c.name for c in target_guild.voice_channels]

    return (
        f"📁 **Canales del Servidor: {target_guild.name} (ID: `{target_guild.id}`):**\n"
        f"- **Canales de Texto ({len(text_channels)}):** {', '.join(text_channels[:25])}\n"
        f"- **Canales de Voz ({len(voice_channels)}):** {', '.join(voice_channels[:15])}"
    )


async def _resolve_search_scope(
    client: discord.Client,
    guild_id: str,
    channel_name_or_id: str,
) -> tuple[SearchScope | None, str]:
    """
    Resolution contract shared by the message-search tools (never guesses other servers):
      1. Explicit guild_id -> that server; explicit channel or all readable channels.
      2. No guild + DM context -> the current DM conversation channel only.
      3. No guild + guild context -> the current channel only, unless another
         channel was explicitly requested.
    Returns (scope, error_message).
    """
    requested_guild = guild_id.strip()
    requested_channel = channel_name_or_id.strip()

    if requested_guild:
        target_guilds = resolve_target_guilds(client, requested_guild)
        if not target_guilds:
            return None, (
                f"No encontré ningún servidor accesible llamado '{requested_guild}'. "
                "Verifica el nombre o usa el ID numérico."
            )
        guild = target_guilds[0]
        channels = resolve_search_channels(guild, requested_channel)
        if not channels:
            if requested_channel:
                return None, (
                    f"No encontré el canal '#{requested_channel.lstrip('#')}' "
                    f"(o no tengo permisos de lectura) en el servidor '{guild.name}'."
                )
            return None, f"No tengo canales de texto legibles en el servidor '{guild.name}'."
        return SearchScope(channels=channels, guild=guild), ""

    context = read_active_context()

    if context.get("is_dm"):
        dm = await resolve_dm_channel(client, str(context.get("channel_id") or ""))
        if dm is None:
            return None, "No se pudo acceder al canal de esta conversación privada."
        return SearchScope(channels=[dm], dm=True), ""

    active_guild_id = str(context.get("guild_id") or "")
    if not active_guild_id:
        return None, (
            "Esta conversación no tiene un servidor activo. Para buscar mensajes de un "
            "servidor, indica explícitamente el servidor con `guild_id` (ID o nombre)."
        )

    guild = next((g for g in client.guilds if str(g.id) == active_guild_id), None)
    if guild is None:
        return None, (
            "El bot ya no está en el servidor de esta conversación. "
            "Indica otro servidor explícitamente con `guild_id` si lo necesitas."
        )

    if requested_channel:
        channels = resolve_search_channels(guild, requested_channel)
        if not channels:
            return None, (
                f"No encontré el canal '#{requested_channel.lstrip('#')}' "
                f"(o no tengo permisos de lectura) en el servidor '{guild.name}'."
            )
        return SearchScope(channels=channels, guild=guild), ""

    current_channel = resolve_default_channel(guild, str(context.get("channel_id") or ""))
    if current_channel is not None:
        return SearchScope(channels=[current_channel], guild=guild), ""

    # The current channel vanished (deleted or no access); scan all readable channels
    channels = resolve_search_channels(guild, "")
    if not channels:
        return None, f"No tengo canales de texto legibles en el servidor '{guild.name}'."
    return SearchScope(channels=channels, guild=guild), ""


def _resolve_dm_author(dm: Any, user: str) -> tuple[Any | None, str]:
    """
    Resolves the author filter for a DM conversation: only the DM partner(s)
    and the bot itself participate, so `user` must match one of them.
    Returns (user_object, error_message).
    """
    clean = user.strip().lstrip("@").lower()
    participants = list(getattr(dm, "recipients", None) or [])
    single = getattr(dm, "recipient", None)
    if single is not None:
        participants.append(single)
    candidates = [*participants, getattr(dm, "me", None)]

    for candidate in candidates:
        if candidate is None:
            continue
        display = str(getattr(candidate, "display_name", "") or "").lower()
        if clean in {str(candidate.id), candidate.name.lower(), display}:
            return candidate, ""
    return None, (
        f"No se encontró al usuario '{user}' en esta conversación privada. "
        "En un DM solo participan el otro usuario y el bot."
    )


def _parse_date_filters(
    after: str, before: str
) -> tuple[datetime | None, datetime | None, str | None]:
    """
    Parses the after/before time filters. Returns (after_dt, before_dt, error)
    where error is a user-facing message if any filter is invalid.
    """
    after_dt = parse_time_filter(after)
    before_dt = parse_time_filter(before)
    invalid = [
        f"{name}='{value}'"
        for name, value, dt in (("after", after, after_dt), ("before", before, before_dt))
        if value and dt is None
    ]
    if invalid:
        return None, None, (
            f"⚠️ Filtros de fecha inválidos: {', '.join(invalid)}. "
            "Usa 'YYYY-MM-DD', 'YYYY-MM-DD HH:MM' o relativos como '30m', '24h', '7d', '30d'."
        )
    return after_dt, before_dt, None


def _describe_filters(
    keywords: list[str],
    types: set[str],
    after_dt: datetime | None,
    before_dt: datetime | None,
    min_reactions: int,
    pinned_only: bool,
) -> str:
    parts = []
    if keywords:
        parts.append(f"contiene: {', '.join(keywords)}")
    if types:
        parts.append(f"tiene: {', '.join(sorted(types))}")
    if after_dt:
        parts.append(f"desde: {format_local(after_dt)} (hora local)")
    if before_dt:
        parts.append(f"hasta: {format_local(before_dt)} (hora local)")
    if min_reactions > 0:
        parts.append(f"reacciones ≥ {min_reactions}")
    if pinned_only:
        parts.append("solo fijados")
    if not parts:
        return ""
    return f"_Filtros aplicados: {'; '.join(parts)}_"


def _format_hit_line(hit: ScanHit) -> str:
    ts = format_local(hit.timestamp)
    extras = []
    if hit.attachment_count:
        extras.append(f"📎 {hit.attachment_count} adjunto(s)")
    if hit.reaction_count:
        extras.append(f"⭐ {hit.reaction_count}")
    suffix = f"  [{', '.join(extras)}]" if extras else ""
    return f"- `[{ts}]` `#{hit.channel_name}` **{hit.author_label}**: {hit.content}{suffix}"


def _format_hits(
    header: str,
    hits: list[ScanHit],
    sort: str,
    keywords: list[str],
    types: set[str],
    after_dt: datetime | None,
    before_dt: datetime | None,
    min_reactions: int,
    pinned_only: bool,
    truncated: bool,
) -> str:
    if not hits:
        return f"{header}\nNo se encontraron mensajes que cumplan los filtros aplicados."

    ordered = sorted(hits, key=lambda h: h.timestamp)
    if sort.strip().lower() == "newest":
        ordered.reverse()

    lines = [header]
    filters_line = _describe_filters(keywords, types, after_dt, before_dt, min_reactions, pinned_only)
    if filters_line:
        lines.append(filters_line)
    lines.append(f"_Mostrando {len(ordered)} mensaje(s) (orden: {sort.strip().lower() or 'oldest'})._")
    lines.append("")
    lines.extend(_format_hit_line(h) for h in ordered)

    if truncated:
        lines.append("")
        lines.append("_Resultados truncados por límite de cantidad o tamaño; acota los filtros o aumenta 'limit'._")

    return "\n".join(lines)
