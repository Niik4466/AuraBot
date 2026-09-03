import asyncio
import json
import os
from pathlib import Path
from typing import Any
import discord
import httpx
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP Server
mcp = FastMCP("DiscordInfo")

BASE_URL = "https://discord.com/api/v10"

# Gateway Discord Client with member & presence intents for real-time status/activities
_intents = discord.Intents.default()
_intents.message_content = True
_intents.members = True
_intents.presences = True

_discord_client = discord.Client(intents=_intents)
_client_ready = asyncio.Event()


def _get_token() -> str:
    """Retrieves Discord bot token from environment or config.json."""
    token = os.getenv("DISCORD_BOT_TOKEN")
    if token:
        return token.strip()

    config_paths = [
        Path("config.json"),
        Path(__file__).resolve().parent.parent.parent.parent / "config.json",
    ]
    for path in config_paths:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    token = data.get("discord", {}).get("token") or data.get("token")
                    if token:
                        return token.strip()
            except Exception:
                pass
    return ""


def _get_active_guild_id() -> str:
    """Reads the active guild ID from the context file if present."""
    context_file = Path("data/current_context.json")
    if context_file.exists():
        try:
            with open(context_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return str(data.get("guild_id") or "").strip()
        except Exception:
            pass
    return ""


def _resolve_target_guilds(client: discord.Client, guild_id: str = "") -> list[discord.Guild]:
    """
    Resolves the target guilds strictly based on requested guild_id or active context.
    Matches by numeric ID or guild name.
    """
    active_id = guild_id.strip() if guild_id else _get_active_guild_id()
    if active_id:
        clean = active_id.lower()
        matched = [
            g for g in client.guilds
            if str(g.id) == clean or clean in g.name.lower()
        ]
        if matched:
            return matched

    return list(client.guilds)


@_discord_client.event
async def on_ready():
    _client_ready.set()


async def _ensure_client() -> discord.Client:
    """Ensures the gateway Discord client is connected and ready."""
    token = _get_token()
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


def _format_status(status: discord.Status) -> str:
    status_map = {
        discord.Status.online: "🟢 En línea",
        discord.Status.idle: "🌙 Ausente / Inactivo",
        discord.Status.dnd: "⛔ No molestar",
        discord.Status.offline: "⚫ Desconectado",
    }
    return status_map.get(status, str(status).capitalize())


def _resolve_full_presence(
    client: discord.Client, user_id: int, member: discord.Member
) -> tuple[str, list[str], str]:
    """
    Extracts custom status, activities (Spotify music, games, streaming), and online status.
    If the member in the target guild has stripped rich presence (common in large guilds),
    checks across mutual guilds to guarantee capturing active Spotify music or gaming sessions.
    """
    custom_status = "Sin descripción o estado personalizado"
    activities_list: list[str] = []
    best_status = member.status

    # Helper to parse activities
    def parse_acts(acts):
        nonlocal custom_status
        for act in acts:
            if isinstance(act, discord.CustomActivity) and custom_status == "Sin descripción o estado personalizado":
                emoji_str = f"{act.emoji} " if act.emoji else ""
                text_str = act.name or ""
                full_status = f"{emoji_str}{text_str}".strip()
                if full_status:
                    custom_status = full_status
            elif isinstance(act, discord.Spotify):
                track = f"🎵 Spotify: '{act.title}' de {act.artist}"
                if track not in activities_list:
                    activities_list.append(track)
            elif act.type == discord.ActivityType.playing:
                p = f"🎮 Jugando: {act.name}"
                if p not in activities_list:
                    activities_list.append(p)
            elif act.type == discord.ActivityType.streaming:
                s = f"📺 Transmitiendo: {act.name}"
                if s not in activities_list:
                    activities_list.append(s)
            elif act.type == discord.ActivityType.listening:
                l = f"🎧 Escuchando: {act.name}"
                if l not in activities_list:
                    activities_list.append(l)
            elif act.type == discord.ActivityType.watching:
                w = f"🎬 Viendo: {act.name}"
                if w not in activities_list:
                    activities_list.append(w)
            elif (
                act.name
                and not isinstance(act, discord.CustomActivity)
                and f"🔹 {act.name}" not in activities_list
            ):
                activities_list.append(f"🔹 {act.name}")

    # 1. Parse current member activities
    parse_acts(member.activities)

    # 2. Check mutual guilds to ensure music/gaming presence is not missed
    for g in client.guilds:
        if g.id == member.guild.id:
            continue
        other_m = g.get_member(user_id)
        if not other_m:
            continue

        if other_m.status != discord.Status.offline and best_status == discord.Status.offline:
            best_status = other_m.status

        parse_acts(other_m.activities)

    return custom_status, activities_list, _format_status(best_status)


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
    client = await _ensure_client()
    clean_query = query.strip().lstrip("@").lower()

    # Search strictly in the resolved target guild(s)
    target_guilds = _resolve_target_guilds(client, guild_id)

    matched_member: discord.Member | None = None
    matched_guild: discord.Guild | None = None

    for guild in target_guilds:
        # 1. Match by numeric ID
        if clean_query.isdigit():
            m = guild.get_member(int(clean_query))
            if m:
                matched_member = m
                matched_guild = guild
                break

        # 2. Match by username, nickname or global name
        for m in guild.members:
            if (
                clean_query == m.name.lower()
                or (m.nick and clean_query == m.nick.lower())
                or (m.global_name and clean_query == m.global_name.lower())
                or clean_query in m.name.lower()
            ):
                matched_member = m
                matched_guild = guild
                break

        if matched_member:
            break

    if matched_member and matched_guild:
        custom_status, activities, status_display = _resolve_full_presence(
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
    token = _get_token()
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
) -> str:
    """
    Retrieves the last X messages sent by a specific user in the current Discord server.
    Args:
        user: The username, nickname, or user ID whose messages to retrieve.
        limit: Number of recent messages to retrieve (decided by the LLM, max 15).
        channel_name_or_id: Optional channel name (e.g. 'chat-general') or numeric channel ID. If empty, searches the server's main text channels.
        guild_id: Optional server/guild ID. If omitted, uses the active server.
    """
    MAX_MESSAGES_LIMIT = 15
    MAX_CHARS_PER_MESSAGE = 250
    MAX_TOTAL_CHARS = 1500

    clamped_limit = min(max(1, limit), MAX_MESSAGES_LIMIT)
    client = await _ensure_client()
    clean_user = user.strip().lstrip("@").lower()

    # Resolve target guilds strictly based on requested or active guild
    target_guilds = _resolve_target_guilds(client, guild_id)

    target_member: discord.Member | None = None
    target_guild: discord.Guild | None = None

    for g in target_guilds:
        if clean_user.isdigit():
            m = g.get_member(int(clean_user))
            if m:
                target_member = m
                target_guild = g
                break

        for m in g.members:
            if (
                clean_user == m.name.lower()
                or (m.nick and clean_user == m.nick.lower())
                or (m.global_name and clean_user == m.global_name.lower())
                or clean_user in m.name.lower()
            ):
                target_member = m
                target_guild = g
                break

        if target_member:
            break

    if not target_member or not target_guild:
        return f"No se encontró al usuario '{user}' para consultar sus mensajes en el servidor activo."

    # Identify channels to search in
    search_channels: list[discord.TextChannel] = []
    if channel_name_or_id:
        clean_ch = channel_name_or_id.strip().lstrip("#").lower()
        for ch in target_guild.text_channels:
            if str(ch.id) == clean_ch or ch.name.lower() == clean_ch:
                search_channels.append(ch)
                break
    else:
        for ch in target_guild.text_channels:
            permissions = ch.permissions_for(target_guild.me)
            if permissions.read_messages and permissions.read_message_history:
                search_channels.append(ch)

    if not search_channels:
        return "No se encontraron canales de texto accesibles para buscar mensajes."

    collected_messages: list[tuple[str, str, str]] = []
    total_chars_accumulated = 0

    for ch in search_channels:
        if len(collected_messages) >= clamped_limit:
            break
        try:
            async for msg in ch.history(limit=50):
                if msg.author.id == target_member.id and msg.clean_content.strip():
                    text = msg.clean_content.strip()
                    if len(text) > MAX_CHARS_PER_MESSAGE:
                        text = text[:MAX_CHARS_PER_MESSAGE] + "..."

                    timestamp_str = msg.created_at.strftime("%Y-%m-%d %H:%M")
                    collected_messages.append((timestamp_str, ch.name, text))

                    total_chars_accumulated += len(text)
                    if (
                        len(collected_messages) >= clamped_limit
                        or total_chars_accumulated >= MAX_TOTAL_CHARS
                    ):
                        break
        except (discord.Forbidden, discord.HTTPException):
            continue

    if not collected_messages:
        return (
            f"No se encontraron mensajes recientes enviados por {target_member.display_name} "
            f"({target_member.name}) en los canales analizados de {target_guild.name}."
        )

    collected_messages.reverse()

    output_lines = [
        f"💬 **Últimos {len(collected_messages)} mensajes de {target_member.display_name} (`{target_member.name}`) en {target_guild.name}:**"
    ]
    for ts, ch_name, content in collected_messages:
        output_lines.append(f"- `[{ts}]` `#{ch_name}`: {content}")

    return "\n".join(output_lines)


@mcp.tool()
async def get_server_info(guild_id: str = "") -> str:
    """
    Retrieves information about a Discord server (member count, owner, boost status, channels count, etc.).
    Args:
        guild_id: Optional ID or name of the server. If omitted, uses the active server.
    """
    client = await _ensure_client()
    target_guilds = _resolve_target_guilds(client, guild_id)

    if not target_guilds:
        return "El bot no está conectado a ningún servidor en este momento."

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
        guild_id: Optional ID or name of the server. If omitted, uses the active server.
    """
    client = await _ensure_client()
    target_guilds = _resolve_target_guilds(client, guild_id)

    if not target_guilds:
        return "El bot no está conectado a ningún servidor en este momento."

    target_guild = target_guilds[0]
    text_channels = [c.name for c in target_guild.text_channels]
    voice_channels = [c.name for c in target_guild.voice_channels]

    return (
        f"📁 **Canales del Servidor: {target_guild.name} (ID: `{target_guild.id}`):**\n"
        f"- **Canales de Texto ({len(text_channels)}):** {', '.join(text_channels[:25])}\n"
        f"- **Canales de Voz ({len(voice_channels)}):** {', '.join(voice_channels[:15])}"
    )


if __name__ == "__main__":
    mcp.run()
