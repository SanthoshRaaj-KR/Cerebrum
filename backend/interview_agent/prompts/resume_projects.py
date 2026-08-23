from __future__ import annotations

from interview_agent.profile import CandidateProfile

_NO_RESUME = """This interview mode is RESUME & PROJECTS, but no resume has \
been uploaded yet. Ask the candidate to briefly introduce themselves, their \
background, and one project they're proud of, then run the interview from \
whatever they tell you."""


def build(profile: CandidateProfile | None) -> str:
    if profile is None:
        return _NO_RESUME

    project_lines = (
        "\n".join(
            f"- {p.name}: {p.description} (tech: {', '.join(p.tech) or 'unspecified'})"
            for p in profile.projects
        )
        or "(no projects listed)"
    )

    return f"""This interview mode is RESUME & PROJECTS. Ask questions \
grounded in the candidate's actual resume below - pick a project or a \
listed skill and dig into it: what they built, why they made specific \
technical choices, what broke, what they'd do differently. Do not ask \
about skills or projects that are not listed here.

Candidate: {profile.name or "unknown"}
Education: {"; ".join(profile.education) or "unspecified"}
Skills: {", ".join(profile.skills) or "unspecified"}
Experience: {"; ".join(profile.experience) or "none listed"}
Projects:
{project_lines}
"""
