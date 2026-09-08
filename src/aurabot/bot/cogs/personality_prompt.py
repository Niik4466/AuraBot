import discord
from discord import app_commands
from discord.ext import commands

from aurabot.storage import prompt_storage


class PersonalPromptCog(commands.Cog):
    """
    Slash commands for user-specific personality customization.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(
        name="personal_prompt",
        description="Manage your personal AI personality prompt",
    )

    @group.command(name="set", description="Set your personal prompt for the bot")
    async def set_prompt(self, interaction: discord.Interaction, prompt: str):
        await prompt_storage.set_personal_prompt(interaction.user.id, prompt)
        await interaction.response.send_message(
            "✅ Your personal prompt has been saved!", ephemeral=True
        )

    @group.command(name="view", description="View your current personal prompt")
    async def view_prompt(self, interaction: discord.Interaction):
        prompt = await prompt_storage.get_personal_prompt(interaction.user.id)
        if prompt:
            await interaction.response.send_message(
                f"**Your Personal Prompt:**\n{prompt}", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "You haven't set a personal prompt yet. Use `/personal_prompt set`.",
                ephemeral=True,
            )

    @group.command(
        name="clear", description="Clear your personal prompt and revert to default"
    )
    async def clear_prompt(self, interaction: discord.Interaction):
        removed = await prompt_storage.clear_personal_prompt(interaction.user.id)
        if removed:
            await interaction.response.send_message(
                "✅ Your personal prompt has been cleared. I will use my default personality with you.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "You don't have a personal prompt set.", ephemeral=True
            )
