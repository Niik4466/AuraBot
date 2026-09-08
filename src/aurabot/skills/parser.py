import logging
from pathlib import Path

import frontmatter

from aurabot.skills.models import Skill

logger = logging.getLogger("DiscordBot")

REQUIRED_FIELDS = ("name", "description")


class SkillParseError(Exception):
    """
    Raised when a SKILL.md file is missing required frontmatter fields.
    """


def parse_skill(skill_file: Path) -> Skill:
    """
    Parses a SKILL.md file (YAML frontmatter + markdown body) into a Skill.

    Raises SkillParseError if 'name' or 'description' are missing or empty.
    """
    post = frontmatter.load(skill_file)

    name = str(post.get("name", "")).strip()
    description = str(post.get("description", "")).strip()

    missing = [f for f in REQUIRED_FIELDS if not (name if f == "name" else description)]
    if missing:
        raise SkillParseError(f"missing frontmatter field(s) {missing} in {skill_file}")

    return Skill(name=name, description=description, body=post.content, path=skill_file)
