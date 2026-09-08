from typing import Sequence

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage


def to_langchain_messages(
    bot_name: str,
    channel_history: Sequence[tuple[str, str, bool] | tuple[str, str]] | None,
) -> list[BaseMessage]:
    """
    Converts raw channel history items into structured LangChain message objects with explicit roles:
    - Messages from the bot become AIMessage (assistant role)
    - Messages from users become HumanMessage (user role)
    """
    if not channel_history:
        return []

    chat_messages: list[BaseMessage] = []
    for item in channel_history:
        if len(item) == 3:
            author, content, is_bot = item
        elif len(item) == 2:
            author, content = item
            is_bot = (author == bot_name)
        else:
            continue

        cleaned_content = content.strip()
        if not cleaned_content:
            continue

        if is_bot:
            # Role: assistant (AuraBot's previous responses)
            chat_messages.append(AIMessage(content=cleaned_content))
        else:
            # Role: user (messages from other users in the channel)
            chat_messages.append(HumanMessage(content=f"[{author}]: {cleaned_content}"))

    return chat_messages
