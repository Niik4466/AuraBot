import logging

import discord
from discord import app_commands
from discord.ext import commands

from aurabot.skills import skills_manager
from aurabot.storage import skills_storage

logger = logging.getLogger("DiscordBot")

SKILL_VIEW_MAX_CHARS = 1800


class SkillsCog(commands.Cog):
    """
    Slash commands to manage per-user Agent Skills.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(
        name="skills",
        description="Gestiona tus skills del bot (instrucciones activables)",
    )

    @group.command(name="list", description="Lista las skills disponibles y cuáles tienes activas")
    async def skills_list(self, interaction: discord.Interaction):
        available = skills_manager.list_skills()
        my_active = await skills_storage.get_active_skills(interaction.user.id)

        if not available:
            await interaction.response.send_message(
                "📦 No hay skills disponibles en el catálogo por el momento.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🧩 Skills Disponibles",
            description=f"Tienes **{len(my_active)}** skill(s) activa(s) de **{len(available)}** disponible(s).",
            color=discord.Color.purple(),
        )
        for skill in available:
            status = "✅ activa" if skill.name in my_active else "⬜ inactiva"
            desc = skill.description
            if len(desc) > 150:
                desc = desc[:147] + "..."
            embed.add_field(name=f"`{skill.name}` — {status}", value=desc, inline=False)

        embed.set_footer(text="Usa /skills load <nombre> para activar una skill.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @group.command(name="load", description="Activa una skill para ti")
    async def skills_load(self, interaction: discord.Interaction, name: str):
        skill = skills_manager.get_skill(name)
        if not skill:
            valid = ", ".join(f"`{s.name}`" for s in skills_manager.list_skills()) or "ninguna"
            await interaction.response.send_message(
                f"❌ La skill `{name}` no existe. Skills disponibles: {valid}", ephemeral=True
            )
            return

        await skills_storage.activate_skill(interaction.user.id, skill.name)
        await interaction.response.send_message(
            f"✅ Skill **{skill.name}** activada. La próxima vez que me hables la tendré en cuenta.",
            ephemeral=True,
        )

    @group.command(name="unload", description="Desactiva una skill para ti")
    async def skills_unload(self, interaction: discord.Interaction, name: str):
        removed = await skills_storage.deactivate_skill(interaction.user.id, name.strip())
        if removed:
            await interaction.response.send_message(
                f"✅ Skill **{name.strip()}** desactivada.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"⚠️ No tenías la skill `{name.strip()}` activada.", ephemeral=True
            )

    @group.command(name="view", description="Muestra el contenido completo de una skill")
    async def skills_view(self, interaction: discord.Interaction, name: str):
        skill = skills_manager.get_skill(name)
        if not skill:
            valid = ", ".join(f"`{s.name}`" for s in skills_manager.list_skills()) or "ninguna"
            await interaction.response.send_message(
                f"❌ La skill `{name}` no existe. Skills disponibles: {valid}", ephemeral=True
            )
            return

        body = skill.body
        if len(body) > SKILL_VIEW_MAX_CHARS:
            body = body[:SKILL_VIEW_MAX_CHARS] + "\n\n_(contenido truncado)_"

        await interaction.response.send_message(
            f"🧩 **{skill.name}**\n_{skill.description}_\n\n{body}", ephemeral=True
        )

    @group.command(
        name="reload", description="Re-escanea el directorio de skills (para skills agregadas en caliente)"
    )
    async def skills_reload(self, interaction: discord.Interaction):
        discovered = skills_manager.reload()
        await interaction.response.send_message(
            f"🔄 Catálogo re-escaneado: **{len(discovered)}** skill(s) descubierta(s).",
            ephemeral=True,
        )
