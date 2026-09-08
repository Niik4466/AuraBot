import asyncio
import logging

import discord
from discord.ext import commands

from aurabot.bot.messages import format_user_label, format_user_name, split_message
from aurabot.config import config
from aurabot.llm import llm
from aurabot.mcp import mcp_manager
from aurabot.skills import skills_manager
from aurabot.storage import prompt_storage, skills_storage
from aurabot.tooling import build_tools_index

logger = logging.getLogger("DiscordBot")

# One lock per channel: serializes reply generation so concurrent triggers
# (e.g. two mentions in quick succession) don't run in parallel with stale
# history and end up answering multiple users in one message.
_channel_locks: dict[int, asyncio.Lock] = {}


def _get_channel_lock(channel_id: int) -> asyncio.Lock:
    lock = _channel_locks.get(channel_id)
    if lock is None:
        lock = asyncio.Lock()
        _channel_locks[channel_id] = lock
    return lock


async def _fetch_reply_chain(
    channel: discord.abc.Messageable,
    trigger_message: discord.Message,
    bot_user_id: int,
    bot_name: str,
    max_hops: int = 5,
) -> list[tuple[str, str, bool]]:
    """
    Walks up the reply chain of the trigger message (oldest first), collecting
    the messages the trigger user was replying to. Used as extra context so the
    bot understands the thread of conversation even if those messages fall
    outside the recent-history window.
    """
    chain: list[discord.Message] = []
    seen: set[int] = {trigger_message.id}
    reference = trigger_message.reference

    while reference and reference.message_id and len(chain) < max_hops:
        message_id = reference.message_id
        if message_id in seen:
            break
        seen.add(message_id)

        parent = reference.resolved
        # duck-typed check: resolved may be a discord.Message (or None/deleted)
        if not (
            parent is not None
            and getattr(parent, "id", None) == message_id
            and hasattr(parent, "clean_content")
        ):
            try:
                parent = await channel.fetch_message(message_id)
            except discord.HTTPException:
                break

        chain.append(parent)
        reference = parent.reference

    chain.reverse()
    return [
        (
            bot_name if m.author.id == bot_user_id else format_user_label(m.author, m.created_at),
            m.clean_content,
            m.author.id == bot_user_id,
        )
        for m in chain
    ]


async def _fetch_user_history(
    mcp_tools: list,
    trigger_message: discord.Message,
    limit: int = 20,
) -> str:
    """
    Fetches the user's recent messages (top `limit`) via the MCP
    get_user_recent_messages tool: their latest interactions in the current
    server (or the DM conversation). Returns "" if unavailable or on error.
    """
    tool = next((t for t in mcp_tools if t.name == "get_user_recent_messages"), None)
    if tool is None:
        return ""

    tool_input: dict = {"user": str(trigger_message.author.id), "limit": limit}
    if trigger_message.guild:
        tool_input["guild_id"] = str(trigger_message.guild.id)

    try:
        result = await asyncio.wait_for(tool.ainvoke(tool_input), timeout=15)
    except Exception as e:
        logger.warning("Could not fetch user history: %s", e)
        return ""

    text = str(result).strip()
    if not text or text.startswith(("No se encontró", "Error", "Para buscar")):
        return ""
    return text


async def _fetch_channel_history(
    channel: discord.abc.Messageable,
    bot_user_id: int,
    bot_name: str,
    trigger_message: discord.Message,
    limit: int = 20,
) -> list[tuple[str, str, bool]]:
    """
    Fetches recent channel messages (oldest first) to build the conversational
    history. Excludes the trigger message itself, and only includes messages
    sent strictly BEFORE the trigger: the per-channel lock may have made us
    wait, and messages that arrived meanwhile (other users chatting) must not
    appear before the trigger in the prompt — the trigger is the last user turn.
    """
    history: list[tuple[str, str, bool]] = []
    async for m in channel.history(limit=limit, oldest_first=False):
        if m.id == trigger_message.id:
            continue
        if m.created_at >= trigger_message.created_at:
            continue
        is_bot = (m.author.id == bot_user_id)
        author_label = bot_name if is_bot else format_user_label(m.author, m.created_at)
        history.append((author_label, m.clean_content, is_bot))

    history.reverse()
    return history


def setup_events(bot: commands.Bot) -> None:
    """
    Registers the message event handlers on the bot client.
    """

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

            # Serialize per channel: the second trigger waits here and only
            # then fetches fresh history (which now includes the previous reply)
            async with _get_channel_lock(message.channel.id):
                history = await _fetch_channel_history(
                    message.channel, bot.user.id, bot_name, message
                )

                # Retrieve personal prompt and active skills for user
                user_prompt = await prompt_storage.get_personal_prompt(message.author.id)
                user_skills = await skills_storage.get_active_skills(message.author.id)
                user_author_name = format_user_label(message.author, message.created_at)

                # Progressive disclosure sections + extra context
                mcp_tools = await mcp_manager.get_tools()
                skills_section = skills_manager.build_prompt_section(user_skills)
                tools_section = build_tools_index(mcp_tools)
                reply_chain = (
                    await _fetch_reply_chain(message.channel, message, bot.user.id, bot_name)
                    if message.reference else []
                )
                user_history = await _fetch_user_history(mcp_tools, message)

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
                        skills_section=skills_section,
                        tools_section=tools_section,
                        reply_chain=reply_chain,
                        user_history_section=user_history,
                    )

                if not reply_text:
                    reply_text = config.fallback_message

                for chunk in split_message(reply_text):
                    await message.reply(chunk)

        except Exception as e:
            logger.error("Error processing message in bot: %s", e, exc_info=True)
            await message.reply(config.fallback_message)
