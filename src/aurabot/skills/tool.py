from langchain_core.tools import tool

from aurabot.skills.manager import skills_manager


@tool
def load_skill(name: str) -> str:
    """Loads the full instructions (markdown body) of an active skill by its exact name.

    Use this tool when the conversation matches one of the skills listed in the
    'Active Skills' section of the system prompt, before answering.

    Args:
        name: Exact name of the skill (e.g. 'ejemplo').
    """
    skill = skills_manager.get_skill(name)
    if not skill:
        valid = ", ".join(sorted(s.name for s in skills_manager.list_skills())) or "ninguna"
        return f"Error: skill '{name}' no existe. Skills disponibles: {valid}."
    return f"# Skill: {skill.name}\n\n{skill.body}"
