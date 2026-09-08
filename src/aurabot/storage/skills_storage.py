import asyncio
import json
import logging
from pathlib import Path

from aurabot.config import config

logger = logging.getLogger("DiscordBot")


class SkillsStorage:
    """
    Asynchronous JSON storage mapping each Discord user to the list of
    skill names they activated: {user_id: [skill_name, ...]}.
    """

    def __init__(self, filepath: str | Path | None = None):
        self.filepath = Path(filepath) if filepath else config.active_skills_file_path
        self._ensure_file()

    def _ensure_file(self):
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        if not self.filepath.exists():
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump({}, f)

    def _read_all(self) -> dict:
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.error(f"Error reading skills storage: {e}")
            return {}

    def _write_all(self, data: dict) -> None:
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error writing skills storage: {e}")

    async def get_active_skills(self, user_id: int) -> list[str]:
        return await asyncio.to_thread(self._read_active, str(user_id))

    def _read_active(self, user_id_str: str) -> list[str]:
        active = self._read_all().get(user_id_str, [])
        return [s for s in active if isinstance(s, str)]

    async def activate_skill(self, user_id: int, skill_name: str) -> None:
        await asyncio.to_thread(self._write_activate, str(user_id), skill_name)

    def _write_activate(self, user_id_str: str, skill_name: str) -> None:
        data = self._read_all()
        active = data.get(user_id_str, [])
        if skill_name not in active:
            active.append(skill_name)
        data[user_id_str] = active
        self._write_all(data)

    async def deactivate_skill(self, user_id: int, skill_name: str) -> bool:
        return await asyncio.to_thread(self._write_deactivate, str(user_id), skill_name)

    def _write_deactivate(self, user_id_str: str, skill_name: str) -> bool:
        data = self._read_all()
        active = data.get(user_id_str, [])
        if skill_name not in active:
            return False
        active.remove(skill_name)
        data[user_id_str] = active
        self._write_all(data)
        return True


# Singleton storage instance
skills_storage = SkillsStorage()
