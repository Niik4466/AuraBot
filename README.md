# AuraBot - Discord Bot Backend with LangChain & Ollama

AuraBot backend for Discord, orchestrated with **LangChain** and local models served through **Ollama**. Built with a decoupled architecture, an Agent Skills system, and MCP tool integration. Ready for local or containerized deployment with Docker.

## Requirements

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) for dependency management and packaging
- Ollama running locally or remotely
- A Discord bot token (with **Message Content Intent** enabled in the Discord Developer Portal)

## Project Structure

```text
AuraBot/
├── main.py                     # Standalone entry point
├── config.json                 # Main configuration (Discord, LLM provider, Storage, MCP)
├── config.example.json         # Example configuration template
├── skills/                     # Agent Skills library (Agent Skills standard)
│   └── <skill-name>/
│       └── SKILL.md            # Skill definition (YAML frontmatter + instructions)
├── data/                       # Runtime state (gitignored)
│   ├── personal_prompts.json   # Persistent per-user personality prompts
│   ├── active_skills.json      # Per-user active skills
│   └── current_context.json    # Tooling conversation context
├── Dockerfile                  # Docker image based on Python and uv
├── docker-compose.yml          # Containerized backend orchestration
├── .dockerignore
├── .python-version             # Python version pin
├── pyproject.toml              # uv project dependencies and metadata
└── src/
    └── aurabot/
        ├── __init__.py         # Package exports and entry point
        ├── bot/                # Discord bot layer
        │   ├── app.py          # AuraBot client, cogs setup and command sync
        │   ├── events.py       # Event handlers (messages, LLM orchestration)
        │   ├── messages.py     # Message helpers
        │   └── cogs/           # Slash command cogs
        │       ├── personality_prompt.py  # /personal_prompt
        │       ├── skills_cog.py          # /skills
        │       └── tooling_cog.py         # /fetch_tools
        ├── config/             # Configuration loading and validation
        │   ├── loader.py
        │   ├── models.py       # Config dataclasses (Discord, Ollama, Storage, MCP)
        │   └── timeutils.py
        ├── llm/                # Language model layer
        │   ├── engine.py       # LLM orchestration (prompts, behavior, history)
        │   ├── factory.py      # Chat model factory (Ollama / OpenRouter)
        │   ├── history.py      # Conversation history management
        │   └── prompts.py      # System prompts
        ├── mcp/                # MCP server connection and tool management
        │   └── manager.py
        ├── mcp_servers/
        │   └── discord_info/   # Built-in MCP server for Discord introspection
        ├── skills/             # Agent Skills system
        │   ├── manager.py      # Skill discovery and lifecycle
        │   ├── parser.py       # SKILL.md frontmatter parsing
        │   ├── models.py
        │   └── tool.py         # load_skill tool exposed to the LLM
        ├── storage/            # Async JSON persistence
        │   ├── prompt_storage.py
        │   └── skills_storage.py
        └── tooling/            # Zero-Shot Tooling engine
            ├── engine.py       # Tool binding and ReAct loop
            ├── context.py
            └── metatools.py
```

## Configuration (`config.json`)

Edit the `config.json` file at the project root (see `config.example.json`):

```json
{
  "provider": "ollama",
  "discord": {
    "token": "YOUR_DISCORD_BOT_TOKEN"
  },
  "ollama": {
    "base_url": "http://localhost:11434",
    "model": "gemma4:26b",
    "temperature": 0.7
  },
  "OpenRouter": {
    "api_key": "sk-or-v1-xxxxxxxxxxxx",
    "model": "deepseek/deepseek-chat",
    "temperature": 0.7
  },
  "storage": {
    "prompts_file": "data/personal_prompts.json",
    "active_skills_file": "data/active_skills.json",
    "skills_dir": "skills"
  },
  "mcp_servers": {
    "fetch": {
      "command": "uvx",
      "args": ["mcp-server-fetch"]
    }
  }
}
```

### Provider Options (`provider`)
- `"ollama"`: Uses a local model served by **Ollama** through LangChain's `ChatOllama`.
- `"openrouter"`: Uses the **OpenRouter** API through LangChain's `ChatOpenAI`.

> **Docker note**: If you run Ollama on your host machine (outside the Docker container), you can set `"base_url": "http://host.docker.internal:11434"`.

## Agent Skills

AuraBot supports an Agent Skills system compatible with the [Agent Skills](https://agentskills.io) standard. Each skill lives in its own folder under `skills/` and is defined by a `SKILL.md` file with YAML frontmatter:

```markdown
---
name: my-skill
description: What the skill does and when the model should apply it.
---

# My Skill

Instructions the model will follow when the skill is active.
```

Users activate skills per-user with `/skills load <name>`; the bot can also discover and load skills autonomously through the `load_skill` tool, which is always available to the LLM.

## Running Locally with `uv`

1. **Install dependencies and sync the virtual environment**:
   ```bash
   uv sync
   ```

2. **Start the bot**:
   ```bash
   uv run aurabot
   ```
   or directly:
   ```bash
   uv run python main.py
   ```

## Running with Docker / Docker Compose

1. **Build and start the container**:
   ```bash
   docker compose up --build -d
   ```

2. **Follow logs in real time**:
   ```bash
   docker compose logs -f
   ```

3. **Stop the container**:
   ```bash
   docker compose down
   ```

## Bot Commands (Slash Commands)

### `/personal_prompt`
- `/personal_prompt set <prompt>`: Set a custom personality prompt for your user.
- `/personal_prompt view`: View your current custom prompt.
- `/personal_prompt clear`: Reset your personality to the defaults.

### `/skills`
- `/skills list`: List all available skills.
- `/skills load <name>`: Activate a skill for your user.
- `/skills unload <name>`: Deactivate an active skill.
- `/skills view <name>`: Show a skill's full definition.
- `/skills reload`: Re-scan the `skills/` directory.

### `/fetch_tools`
- Refreshes the MCP tool catalog used by the Zero-Shot Tooling engine.
