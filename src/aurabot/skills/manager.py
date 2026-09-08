import logging
from pathlib import Path
from typing import Sequence

from aurabot.config import config
from aurabot.skills.models import Skill
from aurabot.skills.parser import SkillParseError, parse_skill

logger = logging.getLogger("DiscordBot")

SKILL_FILE_NAME = "SKILL.md"


class SkillsManager:
    """
    Discovers Agent Skills from the skills directory, and builds the
    progressive-disclosure prompt section for the skills a user activated.
    """

    def __init__(self, skills_dir: str | Path | None = None):
        self.skills_dir = Path(skills_dir) if skills_dir else config.skills_dir_path
        self._skills: dict[str, Skill] = {}

    def discover(self) -> list[Skill]:
        """
        Scans the skills directory and (re)loads every valid SKILL.md found.
        Invalid skills (bad frontmatter, name/folder mismatch, duplicates)
        are skipped with a warning.
        """
        self._skills = {}

        if not self.skills_dir.exists():
            logger.warning("Skills directory not found: %s", self.skills_dir)
            return []

        for folder in sorted(self.skills_dir.iterdir()):
            if not folder.is_dir():
                continue
            skill_file = folder / SKILL_FILE_NAME
            if not skill_file.exists():
                continue

            try:
                skill = parse_skill(skill_file)
            except SkillParseError as e:
                logger.warning("Skipping invalid skill %s: %s", folder.name, e)
                continue

            if skill.name != folder.name:
                logger.warning(
                    "Skipping skill in folder '%s': frontmatter name '%s' does not match folder name",
                    folder.name,
                    skill.name,
                )
                continue

            if skill.name in self._skills:
                logger.warning("Skipping duplicated skill name '%s'", skill.name)
                continue

            self._skills[skill.name] = skill

        logger.info("Discovered %d skill(s): %s", len(self._skills), list(self._skills))
        return self.list_skills()

    def reload(self) -> list[Skill]:
        """
        Re-scans the skills directory (for skills added at runtime).
        """
        return self.discover()

    def list_skills(self) -> list[Skill]:
        return list(self._skills.values())

    def get_skill(self, name: str) -> Skill | None:
        return self._skills.get(name.strip())

    def get_body(self, name: str) -> str | None:
        skill = self.get_skill(name)
        return skill.body if skill else None

    def build_prompt_section(self, active_names: Sequence[str]) -> str:
        """
        Builds the progressive-disclosure prompt section for the skills the
        requesting user has activated. Only names + descriptions are included;
        the full body is retrieved on demand via the load_skill tool.
        """
        skills = [self._skills[n] for n in active_names if n in self._skills]
        if not skills:
            return ""

        lines = ["Active Skills (activated for this user):"]
        for skill in skills:
            lines.append(f"- `{skill.name}`: {skill.description}")
        lines.append(
            "When the conversation matches one of these skills, call the "
            "`load_skill` tool with the skill name to read its full instructions "
            "before answering."
        )
        return "\n".join(lines)


# Singleton instance
skills_manager = SkillsManager()
