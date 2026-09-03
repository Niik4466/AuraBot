# AuraBot - Discord Bot Backend con LangChain & Ollama

Backend de AuraBot para Discord, orquestado con **LangChain** y modelos locales servidos mediante **Ollama**. Diseñado con una arquitectura desacoplada y preparado para despliegue local o contenerizado con Docker.

## Requisitos

- Python 3.10
- [uv](https://github.com/astral-sh/uv) para gestión de dependencias y empaquetado
- Ollama en ejecución local o remota
- Token de bot de Discord (con **Message Content Intent** activado en el Discord Developer Portal)

## Estructura del Proyecto

```text
AuraBot/
├── config.json              # Configuración principal (Discord, Ollama, Storage)
├── config.example.json      # Plantilla de ejemplo para configuración
├── data/
│   └── personal_prompts.json# Almacenamiento persistente de prompts de usuario
├── Dockerfile               # Imagen Docker en base a Python 3.10 y uv
├── docker-compose.yml       # Orquestación del backend contenerizado
├── .dockerignore
├── .python-version          # Especificación de versión (3.10)
├── pyproject.toml           # Dependencias y metadatos del proyecto uv
└── src/
    └── aurabot/
        ├── __init__.py      # Exportación de módulos y punto de entrada
        ├── bot.py           # Backend del bot Discord (eventos, comandos, cogs)
        ├── config.py        # Clase Config para carga y validación de config.json
        ├── llm.py           # Clase LLM: prompts, comportamiento y orquestación
        ├── mcp.py           # Conexión y gestión de servidores MCP (stdio/SSE)
        ├── storage.py       # Almacenamiento asíncrono de personal prompts
        └── tooling.py       # Motor Zero-Shot Tooling (tool binding y ReAct loop)
```

## Configuración (`config.json`)

Edita el archivo `config.json` en la raíz del proyecto:

```json
{
  "provider": "ollama",
  "discord": {
    "token": "TU_DISCORD_BOT_TOKEN"
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
    "prompts_file": "data/personal_prompts.json"
  }
}
```

### Opciones de Proveedor (`provider`)
- `"ollama"`: Utiliza un modelo local servido por **Ollama** mediante `ChatOllama` de LangChain.
- `"openrouter"`: Utiliza la API de **OpenRouter** mediante `ChatOpenAI` de LangChain.

> **Nota para Docker**: Si usas Ollama en tu máquina host (fuera del contenedor Docker), puedes configurar `"base_url": "http://host.docker.internal:11434"`.




## Ejecución Local con `uv`

1. **Instalar dependencias y sincronizar entorno virtual**:
   ```bash
   uv sync
   ```

2. **Iniciar el bot**:
   ```bash
   uv run aurabot
   ```
   o directamente:
   ```bash
   uv run python -m aurabot.bot
   ```

## Ejecución con Docker / Docker Compose

1. **Construir y levantar el contenedor**:
   ```bash
   docker compose up --build -d
   ```

2. **Ver logs en tiempo real**:
   ```bash
   docker compose logs -f
   ```

3. **Detener el contenedor**:
   ```bash
   docker compose down
   ```

## Comandos del Bot (Slash Commands)

- `/personal_prompt set <prompt>`: Configura un prompt de personalidad personalizado para tu usuario.
- `/personal_prompt view`: Consulta tu prompt personalizado actual.
- `/personal_prompt clear`: Restablece la personalidad a los valores predeterminados.
