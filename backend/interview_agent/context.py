"""What the interviewer knows about who it's talking to.

Its own module so both prompts/ and research.py can take it without either
importing the interview session that owns it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CandidateContext:
    """The round decides the role, so neither is typed in any more.

    `role` is the chosen mode's DEFAULT_ROLE and `level` follows
    candidate.fresher in config.yaml. Asking someone to pick "SDE &
    Backend" and then type "Backend Engineer" underneath it was asking the
    same question twice, and let the two disagree.

    `resume` is optional now. Only the résumé round needs one - it is the
    material for that round - and every other round is grounded in what
    the role's interviews actually ask, which needs no CV at all.
    """

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
