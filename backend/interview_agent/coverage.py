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


# How hard the questions on one competency have got. Every competency
# starts at BASICS and climbs one rung per answer that genuinely held up -
# this is what makes a good answer buy a harder question rather than a
# sideways one. It never falls: a wrong answer at APPLIED means the next
# question digs into that same ground, not that the ground resets.
BASICS, APPLIED, EDGE = 1, 2, 3
MAX_LEVEL = EDGE

_LEVEL_NAMES = {
    BASICS: "basics",
    APPLIED: "applied",
    EDGE: "edge cases and trade-offs",
}

_LEVEL_BRIEF = {
    BASICS: (
        "Start at the straightforward end: can they name it, define it, say "
        "what it is for."
    ),
    APPLIED: (
        "They have the basics here, so do NOT ask those again. Move up a "
        "level: where they actually used it, why that choice over the "
        "obvious alternative, what they measured, what it cost them."
    ),
    EDGE: (
        "They have handled this at two levels already. Take it to the top of "
        "what is fair for a fresher: what breaks at ten times the load, "
        "where the abstraction leaks, which trade-off they would take and "
        "why. Genuinely hard, still answerable by a good new graduate."
    ),
}


def level_name(level: int) -> str:
    return _LEVEL_NAMES.get(level, _LEVEL_NAMES[BASICS])


def level_brief(level: int) -> str:
    return _LEVEL_BRIEF.get(level, _LEVEL_BRIEF[BASICS])


@dataclass
class CoverageLedger:
    """Which competencies the candidate has shown something on, how
    strongly, and how hard the questions on each have got - carried across
    the whole interview, independent of how much of the raw transcript is
    still in context."""

    touched: dict[str, int] = field(default_factory=dict)
    # Competencies pushed on twice with weak answers - the edge of what the
    # candidate knows here has been found, so they count as done even though
    # `touched` may still be 0 for them.
    exhausted: set[str] = field(default_factory=set)
    # Per competency, how hard the questions on it have got. See BASICS /
    # APPLIED / EDGE above. Absent means nobody has asked about it yet.
    level: dict[str, int] = field(default_factory=dict)

    def record(
        self,
        evidenced: list[str],
        strength: int,
        focus: str = "",
        exhausted: bool = False,
        held_up: bool = False,
    ) -> None:
        for name in evidenced:
            self.touched[name] = max(self.touched.get(name, 0), strength)
        # A focused question that proved nothing still puts the competency
        # on the board, so it isn't mistaken for never-asked ground.
        if focus and focus not in self.touched:
            self.touched[focus] = 0
        if focus:
            self.level.setdefault(focus, BASICS)
            # An answer that held up buys a harder question on the same
            # ground - that is the whole reward for getting it right, and
            # it is what stops a strong candidate being asked six variations
            # of the same easy thing. A weak answer leaves the level where
            # it is; the ladder in questionnaire.py handles digging in.
            if held_up:
                self.level[focus] = min(MAX_LEVEL, self.level[focus] + 1)
        if focus and exhausted:
            self.exhausted.add(focus)

    def level_of(self, name: str) -> int:
        """How hard to pitch the next question on this competency."""
        return self.level.get(name, BASICS)

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
        climbed = [
            f"{n} (now at {level_name(self.level[n])})"
            for n in all_competencies
            if self.level.get(n, BASICS) > BASICS
        ]
        lead = (
            f"COVERAGE - {len(settled)} of {total} competencies have a read. "
            f"Nothing shown yet on: {', '.join(open_ground)}."
        )
        if climbed:
            # Where they have already proved themselves, so a return visit
            # goes harder instead of re-asking something they cleared.
            lead += f" Already answered well on: {'; '.join(climbed)}."
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
