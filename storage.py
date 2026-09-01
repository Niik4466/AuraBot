import json
import os
import asyncio
import logging

logger = logging.getLogger("DiscordBot")

class PromptStorage:
    def __init__(self, filename="personal_prompts.json"):
        self.filename = filename
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(self.filename):
            with open(self.filename, "w", encoding="utf-8") as f:
                json.dump({}, f)

    async def get_personal_prompt(self, user_id: int) -> str | None:
        return await asyncio.to_thread(self._read_prompt, str(user_id))

    def _read_prompt(self, user_id_str: str) -> str | None:
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get(user_id_str)
        except Exception as e:
            logger.error(f"Error reading prompt storage: {e}")
            return None

    async def set_personal_prompt(self, user_id: int, prompt: str) -> None:
        await asyncio.to_thread(self._write_prompt, str(user_id), prompt)

    def _write_prompt(self, user_id_str: str, prompt: str) -> None:
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            data[user_id_str] = prompt
            
            with open(self.filename, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error writing to prompt storage: {e}")

    async def clear_personal_prompt(self, user_id: int) -> bool:
        """
        Removes the personal prompt for the given user_id.
        Returns True if a prompt was removed, False if it didn't exist.
        """
        return await asyncio.to_thread(self._delete_prompt, str(user_id))

    def _delete_prompt(self, user_id_str: str) -> bool:
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if user_id_str in data:
                del data[user_id_str]
                with open(self.filename, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                return True
            return False
        except Exception as e:
            logger.error(f"Error clearing prompt from storage: {e}")
            return False
