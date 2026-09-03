"""The interview's sense of time.

Real interviews are a clock, not a question counter: you open easy, spend
most of the middle on substance, push hardest near the end, then wrap up
because time is gone - not because a fixed plan ran out of slots.

Everything here is pure and synchronous; nothing calls out to a model. The
clock is timestamp-based (started_at + duration) rather than turn-counted,
so it stays correct across a page refresh - the browser recomputes the
countdown from the same two numbers the backend used to derive phase.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

# Fractions of the total budget where each phase ends. Tuned for a 40-minute
# interview: ~5 min settling in, the bulk of the middle on substance, the
# last stretch pushing hardest, then a real wrap-up rather than a hard cut.
_OPENING_END = 0.12
_CORE_END = 0.60
_DEPTH_END = 0.88

_PHASE_GUIDANCE = {
    "opening": (
        "Settle them in. Still technical, but the most approachable ground "
        "you have - anchor it in something they've actually built if you can. "
        "Never open with the hardest thing on your mind."
    ),
    "core": (
        "This is the substance of the interview. Go deep on two or three "
        "areas rather than skimming everything - consecutive questions "
        "working the same area from different angles is good interviewing."
    ),
    "depth": (
        "Push the hardest ground you have left. Escalate on whatever has "
        "held up so far, and spend less patience on ground that clearly "
        "isn't there."
    ),
    "closing": (
        "Time is almost up. Ask at most one more substantive question, then "
        "wrap up like a person would - thank them for their time, ask if "
        "they have any questions for you, and end the interview. Do not "
        "open a new deep topic this late."
    ),
}


@dataclass
class Clock:
    started_at: float
    duration_seconds: int

    @classmethod
    def start(cls, duration_minutes: int) -> "Clock":
        return cls(started_at=time.time(), duration_seconds=duration_minutes * 60)

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, time.time() - self.started_at)

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.duration_seconds - self.elapsed_seconds)

    @property
    def fraction_used(self) -> float:
        if self.duration_seconds <= 0:
            return 1.0
        return min(1.0, self.elapsed_seconds / self.duration_seconds)

    @property
    def expired(self) -> bool:
        return self.remaining_seconds <= 0

    @property
    def phase(self) -> str:
        f = self.fraction_used
        if f < _OPENING_END:
            return "opening"
        if f < _CORE_END:
            return "core"
        if f < _DEPTH_END:
            return "depth"
        return "closing"

    def render(self, coverage_note: str = "") -> str:
        """The block injected into the interviewer's system prompt each
        turn - the thing that makes it pace itself without a script."""
        mins_elapsed = int(self.elapsed_seconds // 60)
        mins_left = int(self.remaining_seconds // 60) + (
            1 if self.remaining_seconds % 60 else 0
        )
        phase = self.phase
        lines = [
            f"CLOCK - you are {mins_elapsed} minute(s) into a "
            f"{self.duration_seconds // 60}-minute interview, about "
            f"{mins_left} minute(s) left. Phase: {phase}.",
            _PHASE_GUIDANCE[phase],
        ]
        if coverage_note:
            lines.append(coverage_note)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "startedAt": self.started_at,
            "durationSeconds": self.duration_seconds,
            "elapsedSeconds": round(self.elapsed_seconds, 1),
            "remainingSeconds": round(self.remaining_seconds, 1),
            "phase": self.phase,
            "expired": self.expired,
        }
