from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Skill:
    """
    A parsed Agent Skill: a folder with a SKILL.md file containing YAML
    frontmatter (name, description) and markdown instructions.
    """
    name: str
    description: str
    body: str
    path: Path
