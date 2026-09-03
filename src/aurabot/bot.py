import logging
import discord
from discord import app_commands
from discord.ext import commands

from aurabot.config import config
from aurabot.storage import PromptStorage
from aurabot.llm import llm
from aurabot.mcp import mcp_manager

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("DiscordBot")

# Storage initialization
prompt_storage = PromptStorage()


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


class ToolingCog(commands.Cog):
    """
    Slash commands for bot tools and MCP capabilities.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="fetch-tools",
        description="Muestra todas las herramientas disponibles para el bot",
    )
    async def fetch_tools(self, interaction: discord.Interaction):
        # We defer ephemerally so the reply is only visible to the user and avoids timeouts
        await interaction.response.defer(ephemeral=True)

        try:
            tools = await mcp_manager.get_tools()
            llm.tooling.update_tools(tools)

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


class AuraBot(commands.Bot):
    """
    Core Discord Bot client.
    """

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        intents.members = True
        intents.presences = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.add_cog(PersonalPromptCog(self))
        await self.add_cog(ToolingCog(self))
        try:
            await llm.load_tools()
        except Exception as e:
            logger.warning("Could not initialize MCP tools on setup: %s", e)

        try:
            synced = await self.tree.sync()
            logger.info("Synced %d command(s) globally.", len(synced))
        except Exception as e:
            logger.error("Failed to sync commands: %s", e)

    async def on_ready(self):
        logger.info("Logged in as %s (ID: %s)", self.user, self.user.id)


bot = AuraBot()


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


@bot.event
async def on_message(message: discord.Message):
    # Ignore messages from bots (including self)
    if message.author.bot:
        return

    # Check if bot is mentioned or replied to
    is_mentioned = bot.user in message.mentions
    is_reply_to_bot = (
        message.reference
        and message.reference.resolved
        and isinstance(message.reference.resolved, discord.Message)
        and message.reference.resolved.author.id == bot.user.id
    )

    if not (is_mentioned or is_reply_to_bot):
        await bot.process_commands(message)
        return

    try:
        bot_name = bot.user.display_name if bot.user else "AuraBot"

        # Fetch recent channel messages to provide conversational history with explicit roles
        history: list[tuple[str, str, bool]] = []
        async for m in message.channel.history(limit=20, oldest_first=False):
            if m.id == message.id:
                continue
            is_bot = (m.author.id == bot.user.id)
            author_label = bot_name if is_bot else format_user_name(m.author)
            history.append((author_label, m.clean_content, is_bot))

        history.reverse()

        # Retrieve personal prompt for user
        user_prompt = await prompt_storage.get_personal_prompt(message.author.id)
        user_author_name = format_user_name(message.author)

        logger.info(
            "Processing message from [%s] in #%s",
            user_author_name,
            getattr(message.channel, "name", "DM"),
        )

        guild_id = str(message.guild.id) if message.guild else None
        guild_name = message.guild.name if message.guild else None
        channel_id = str(message.channel.id)
        channel_name = getattr(message.channel, "name", "DM")

        async with message.channel.typing():
            reply_text = await llm.generate_reply(
                bot_name=bot_name,
                author_name=user_author_name,
                user_message=message.clean_content,
                personal_prompt=user_prompt,
                channel_history=history,
                guild_id=guild_id,
                guild_name=guild_name,
                channel_id=channel_id,
                channel_name=channel_name,
            )

        if not reply_text:
            reply_text = config.fallback_message

        # Discord message length limit is 2000 characters
        if len(reply_text) > 2000:
            for i in range(0, len(reply_text), 2000):
                chunk = reply_text[i:i + 2000]
                await message.reply(chunk)
        else:
            await message.reply(reply_text)

    except Exception as e:
        logger.error("Error processing message in bot: %s", e, exc_info=True)
        await message.reply(config.fallback_message)


def main():
    token = config.discord_token
    if not token:
        logger.error("Discord bot token not configured. Please check config.json.")
        return

    bot.run(token)


if __name__ == "__main__":
    main()
