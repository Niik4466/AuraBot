import discord


def _matches_query(member: discord.Member, clean_query: str) -> bool:
    return (
        clean_query == member.name.lower()
        or (member.nick and clean_query == member.nick.lower())
        or (member.global_name and clean_query == member.global_name.lower())
        or clean_query in member.name.lower()
    )


def find_member(
    guilds: list[discord.Guild], query: str
) -> tuple[discord.Member | None, discord.Guild | None]:
    """
    Finds a member across the given guilds by numeric ID, username, nickname,
    or global name. Returns (member, guild) or (None, None) if not found.
    """
    clean_query = query.strip().lstrip("@").lower()

    for guild in guilds:
        # 1. Match by numeric ID
        if clean_query.isdigit():
            m = guild.get_member(int(clean_query))
            if m:
                return m, guild

        # 2. Match by username, nickname or global name
        for m in guild.members:
            if _matches_query(m, clean_query):
                return m, guild

    return None, None
