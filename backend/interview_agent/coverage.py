"""What ground the interview has actually covered.

Two jobs, both of which outlive the model's context window:

1. Carry coverage forward once the transcript outgrows remember_turns -
   this ledger is what still remembers "we've never touched testing" after
   the turns that would have shown that have scrolled out.
2. Be the interview's end condition. With no clock, the interview runs
   until every competency is "settled" - shown at thin-or-better, or
   worked until the edge of what the candidate knows was found - and this
   is what knows when that has happened.

Bookkeeping only. Nothing here calls a model and nothing here is a score:
strength is "how much have we seen on this", never "how good were they".
The judgement lives in evaluator.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CoverageLedger:
    """Which competencies the candidate has shown something on, and how
    strongly - carried across the whole interview, independent of how much
    of the raw transcript is still in context."""

    touched: dict[str, int] = field(default_factory=dict)
    # Competencies pushed on twice with weak answers - the edge of what the
    # candidate knows here has been found, so they count as done even though
    # `touched` may still be 0 for them.
    exhausted: set[str] = field(default_factory=set)

    def record(
        self,
        evidenced: list[str],
        strength: int,
        focus: str = "",
        exhausted: bool = False,
    ) -> None:
        for name in evidenced:
            self.touched[name] = max(self.touched.get(name, 0), strength)
        # A focused question that proved nothing still puts the competency
        # on the board, so it isn't mistaken for never-asked ground.
        if focus and focus not in self.touched:
            self.touched[focus] = 0
        if focus and exhausted:
            self.exhausted.add(focus)

    def settled(self, all_names: list[str]) -> list[str]:
        """Competencies with nothing more worth asking: shown at
        thin-or-better, or the edge of what they know was found."""
        return [
            n
            for n in all_names
            if self.touched.get(n, 0) >= 1 or n in self.exhausted
        ]

    def open_ground(self, all_names: list[str]) -> list[str]:
        done = set(self.settled(all_names))
        return [n for n in all_names if n not in done]

    def progress(self, all_names: list[str]) -> float:
        if not all_names:
            return 0.0
        return len(self.settled(all_names)) / len(all_names)

    def render(self, all_competencies: list[str]) -> str:
        if not all_competencies:
            return ""
        settled = self.settled(all_competencies)
        open_ground = [n for n in all_competencies if n not in set(settled)]
        total = len(all_competencies)

        if not open_ground:
            return (
                f"COVERAGE - you now have a read on all {total} competencies "
                "tracked for this role. Push hardest on whatever has held up, "
                "or wrap the interview up; do not open brand-new ground now."
            )

        frac = len(settled) / total
        lead = (
            f"COVERAGE - {len(settled)} of {total} competencies have a read. "
            f"Nothing shown yet on: {', '.join(open_ground)}."
        )
        if frac < 0.34:
            tail = (
                " Still early - go deep on two or three of these rather than "
                "touching all of them at once."
            )
        elif frac < 0.75:
            tail = (
                " Weigh these when you pick new ground, and keep raising the "
                "difficulty."
            )
        else:
            tail = (
                " Near the end of coverage - get something on what's left, "
                "push hardest on what's held up, and don't start a brand-new "
                "deep topic."
            )
        return lead + tail
