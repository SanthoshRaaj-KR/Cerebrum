"""The interview modes.

A mode is the whole choice now - it carries its own question territory,
its own rubric dimensions, and its own sense of what a good answer looks
like. What used to be a separate "role" axis is just free text the
candidate types (see context.CandidateContext), because in practice the
mode is what decides which questions get asked.

Adding a mode means: add a module here exporting
NAME/BLURB/DIMS/DEFAULT_ROLE/PROMPT, register it in _MODES below, and add
its key to config.yaml's interviewer.modes.
"""

from __future__ import annotations

from dataclasses import dataclass

from interview_agent.context import CandidateContext
from interview_agent.prompts import (
    ai_engineer,
    computer_fundamentals,
    resume_projects,
    sde_backend,
    system_design_hld,
    system_design_lld,
)


@dataclass(frozen=True)
class Mode:
    key: str
    name: str
    blurb: str
    dims: tuple[str, ...]
    # What target role this round implies, used to prefill the setup form so
    # the candidate confirms a sensible default instead of retyping what the
    # mode already said. It lives with the mode rather than in the console
    # because the mode is what knows it - and because a console guessing at
    # it is how "AI Engineer" ends up researching backend interviews.
    # Empty for rounds with no external role to search for.
    default_role: str
    prompt: str


def _mode(key: str, module) -> Mode:
    return Mode(
        key=key,
        name=module.NAME,
        blurb=module.BLURB,
        dims=tuple(module.DIMS),
        default_role=getattr(module, "DEFAULT_ROLE", ""),
        prompt=module.PROMPT,
    )


_MODES: dict[str, Mode] = {
    m.key: m
    for m in (
        _mode("resume_projects", resume_projects),
        _mode("sde_backend", sde_backend),
        _mode("computer_fundamentals", computer_fundamentals),
        _mode("system_design_hld", system_design_hld),
        _mode("system_design_lld", system_design_lld),
        _mode("ai_engineer", ai_engineer),
    )
}


class UnknownMode(ValueError):
    """No mode registered under that key."""


def get(key: str) -> Mode:
    try:
        return _MODES[key]
    except KeyError:
        raise UnknownMode(f"unknown mode: {key!r}") from None


def known() -> list[str]:
    return list(_MODES)


def mode_prompt(key: str, candidate: CandidateContext) -> str:
    """The mode's own instructions plus who's being interviewed. Every mode
    gets the candidate block - even a system-design round opens better when
    it can pitch the problem near something they've actually worked on."""
    return f"{get(key).prompt}\n\n{candidate.describe()}"
