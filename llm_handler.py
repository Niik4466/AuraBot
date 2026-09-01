import requests
import logging
import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("DiscordBot")

# Changed default to /api/generate as the payload uses 'prompt' instead of 'messages'
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")

async def call_ollama(prompt: str, system_prompt: str) -> str:
    """
    Sends a generation request to the Ollama API using the specified format.
    """
    full_prompt = f"System: {system_prompt}\n\nUser: {prompt}\n[AriaBot]:"
    
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": full_prompt,
        "stream": False,
        "options": {"temperature": 0.7},
        "think": False
    }
    
    def _make_request():
        try:
            r = requests.post(OLLAMA_URL, json=payload, timeout=120)
            r.raise_for_status()
            data = r.json()
            response_text = data.get("response", "").strip()
            return response_text
        except Exception as e:
            logger.error(f"Error communicating with Ollama: {e}")
            return f"Error comunicándose con Ollama: {e}"

    # Run blocking request in a separate thread to avoid blocking the event loop
    return await asyncio.to_thread(_make_request)
