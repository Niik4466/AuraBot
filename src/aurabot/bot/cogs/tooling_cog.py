import logging

import discord
from discord import app_commands
from discord.ext import commands

from aurabot.llm import llm
from aurabot.mcp import mcp_manager

logger = logging.getLogger("DiscordBot")


class ToolingCog(commands.Cog):
    """
    Slash commands for bot tools and MCP capabilities.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="fetch-tools",
        description="Muestra el catálogo de herramientas disponibles para el bot",
    )
    async def fetch_tools(self, interaction: discord.Interaction):
        # We defer ephemerally so the reply is only visible to the user and avoids timeouts
        await interaction.response.defer(ephemeral=True)

        try:
            # Refresh the catalog (progressive disclosure: schemas are bound on
            # demand by the model via activate_tools, not all at once)
            tools = await mcp_manager.get_tools(force_refresh=True)
            tools_by_server = await mcp_manager.get_tools_by_server(force_refresh=True)
            llm.tooling.update_catalog(tools, tools_by_server=tools_by_server)

            if not tools:
                await interaction.followup.send(
                    "🔧 **Herramientas disponibles:**\nActualmente no hay herramientas configuradas o disponibles.",
                    ephemeral=True,
                )
                return

            embed = discord.Embed(
                title="🛠️ Herramientas Disponibles",
                description=f"El bot tiene **{len(tools)}** herramienta(s) disponible(s):",
                color=discord.Color.blue(),
            )

            for tool in tools:
                desc = tool.description.strip() if tool.description else "Sin descripción disponible."
                if len(desc) > 300:
                    desc = desc[:297] + "..."
                embed.add_field(
                    name=f"🔹 `{tool.name}`",
                    value=desc,
                    inline=False,
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error("Error in /fetch-tools command: %s", e, exc_info=True)
            await interaction.followup.send(
                f"❌ Error al consultar las herramientas: {e}",
                ephemeral=True,
            )
