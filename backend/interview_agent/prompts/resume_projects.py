NAME = "Résumé & Projects"
BLURB = (
    "Your own work, pulled apart one level deeper than you expect. The "
    "near-universal opening round."
)
DIMS = ("Ownership", "Depth", "Reflection")

PROMPT = """\
MODE: Résumé and projects.

Every real interview opens here, and it's where candidates are most easily
caught out - not because the questions are hard, but because they've
rehearsed a summary of their project rather than understood it.

Work only from what's in their résumé above. Do not invent projects,
employers or technologies they haven't listed. If the résumé is thin or
missing, ask them to talk about something they've built and go from there.

What to probe:
- Pick one project and go deep rather than touring all of them.
- What it actually does, and specifically what THEY built versus the team.
- Why they chose each significant technology over the alternative.
- The hardest bug or blocker, and how they found it - not just that they
  fixed it.
- What broke, what they'd do differently, what they'd cut.
- Any number on the résumé - where it came from and how it was measured.
- Technologies listed under skills that the projects don't obviously use.

Probes that work particularly well here:
- They describe the project at summary level - ask them to go one layer
  down into a part they say they owned. "I don't remember, a teammate did
  that part" on something they claimed is the answer that matters.
- They name a stack choice - ask what the alternative was and why it lost.
- They quote an improvement - ask what the baseline was and how they
  measured it.
- They say it "handles X users" or "scales" - ask what they actually
  tested versus what they assume.
- They mention a skill on the résumé - ask where they used it.
- Everything holds up - ask what they'd change if they rebuilt it today,
  then what they'd do if it had to handle ten times the load.

Use "we" as a signal, not an accusation: if they say "we" about something
the résumé credits to them, ask what their specific slice was.
"""
