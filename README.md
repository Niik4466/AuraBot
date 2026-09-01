# Discord Bot with Ollama Integration

This bot integrates Discord with a local Ollama instance, allowing for AI chat with customizable personalities.

## Setup

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Configure Environment**:
    - Edit `.env` and add your `DISCORD_BOT_TOKEN`.
    - Ensure `OLLAMA_URL` points to your running Ollama instance (default: `http://localhost:11434/api/chat`).
    - **Important**: Go to the [Discord Developer Portal](https://discord.com/developers/applications), select your application, go to the "Bot" tab, and enable **Message Content Intent**. This is required for the bot to read messages.

3.  **Run the Bot**:
    ```bash
    python bot.py
    ```

## Features

-   **Chat with AI**: Mention `@BotName` or reply to its messages to chat.
-   **Personalities**: Use `/personal_prompt set <prompt>` to give the bot a specific personality for you.
-   **Context Aware**: The bot reads the last 30 messages in the channel to understand the conversation context.

## Commands

-   `/personal_prompt set <prompt>`: Set your personal prompt.
-   `/personal_prompt view`: View your current personal prompt.
