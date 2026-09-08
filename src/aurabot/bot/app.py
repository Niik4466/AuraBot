import logging

import discord
from discord.ext import commands

from aurabot.bot.cogs import PersonalPromptCog, SkillsCog, ToolingCog
from aurabot.bot.events import setup_events
from aurabot.config import config
from aurabot.llm import llm
from aurabot.mcp import mcp_manager
from aurabot.skills import load_skill, skills_manager

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("DiscordBot")


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
        await self.add_cog(SkillsCog(self))

        # Discover skills and expose load_skill as an always-active tool
        skills_manager.discover()
        mcp_manager.register_tool(load_skill)

        try:
            await llm.load_tools()
            llm.tooling.set_always_active([load_skill])
        except Exception as e:
            logger.warning("Could not initialize MCP tools on setup: %s", e)

        try:
            synced = await self.tree.sync()
            logger.info("Synced %d command(s) globally.", len(synced))
        except Exception as e:
            logger.error("Failed to sync commands: %s", e)

    async def on_ready(self):
        logger.info("Logged in as %s (ID: %s)", self.user, self.user.id)


# Singleton bot instance
bot = AuraBot()
setup_events(bot)


def main():
    token = config.discord_token
    if not token:
        logger.error("Discord bot token not configured. Please check config.json.")
        return

    bot.run(token)
