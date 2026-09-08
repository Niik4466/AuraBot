import discord


def format_status(status: discord.Status) -> str:
    status_map = {
        discord.Status.online: "🟢 En línea",
        discord.Status.idle: "🌙 Ausente / Inactivo",
        discord.Status.dnd: "⛔ No molestar",
        discord.Status.offline: "⚫ Desconectado",
    }
    return status_map.get(status, str(status).capitalize())


def resolve_full_presence(
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

    return custom_status, activities_list, format_status(best_status)
