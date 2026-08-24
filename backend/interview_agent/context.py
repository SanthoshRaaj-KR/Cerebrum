"""What the interviewer knows about who it's talking to.

Its own module so both prompts/ and planner.py can take it without either
importing the interview session that owns it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CandidateContext:
    role: str = ""
    level: str = ""
    resume: str = ""

    # A whole resume in every turn's system prompt is mostly wasted context
    # once the interview is running - the model has already mined it for the
    # opening question and the history carries the thread from there.
    MAX_RESUME_CHARS = 6000

    def resume_text(self) -> str:
        text = (self.resume or "").strip()
        if len(text) > self.MAX_RESUME_CHARS:
            return text[: self.MAX_RESUME_CHARS] + "\n[...resume truncated]"
        return text

    def describe(self) -> str:
        """The candidate block injected into every mode's prompt."""
        lines = ["CANDIDATE"]
        lines.append(f"Target role: {self.role.strip() or 'unspecified'}")
        lines.append(f"Level: {self.level.strip() or 'unspecified'}")
        resume = self.resume_text()
        if resume:
            lines.append("\nRésumé (their own words):\n" + resume)
        else:
            lines.append(
                "\nNo résumé provided. Open by asking them to introduce "
                "themselves and their background, and work from that."
            )
        return "\n".join(lines)
