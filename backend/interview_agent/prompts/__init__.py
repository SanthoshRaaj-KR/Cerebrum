"""Role and mode prompt templates, looked up by the config-declared names.

Adding a role or mode means: add it to config.yaml's interviewer.roles/modes,
add a module here, and register it below. Nothing else needs to change.
"""

from __future__ import annotations

from interview_agent.profile import CandidateProfile
from interview_agent.prompts import (
    ai_engineer,
    backend_engineer,
    computer_fundamentals,
    full_stack_developer,
    resume_projects,
    system_design,
)

_ROLES: dict[str, str] = {
    "ai_engineer": ai_engineer.PROMPT,
    "backend_engineer": backend_engineer.PROMPT,
    "full_stack_developer": full_stack_developer.PROMPT,
}

_MODES: dict[str, object] = {
    "resume_projects": resume_projects.build,
    "computer_fundamentals": lambda _profile: computer_fundamentals.PROMPT,
    "system_design": lambda _profile: system_design.PROMPT,
}


def role_prompt(role: str) -> str:
    try:
        return _ROLES[role]
    except KeyError:
        raise ValueError(f"unknown role: {role!r}") from None


def mode_prompt(mode: str, profile: CandidateProfile | None) -> str:
    try:
        builder = _MODES[mode]
    except KeyError:
        raise ValueError(f"unknown mode: {mode!r}") from None
    return builder(profile)  # type: ignore[operator]
