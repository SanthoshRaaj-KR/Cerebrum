NAME = "System Design — LLD"
BLURB = (
    "Class design, SOLID and object modelling. The machine-coding round: "
    "make it work, then make it extensible."
)
DIMS = ("Modelling", "Extensibility", "Clarity")

PROMPT = """\
MODE: System Design, low level (LLD) / object-oriented design.

This is the machine-coding or class-design round. Not distributed systems -
one service, designed properly. What's tested is whether they can turn a
vague problem into classes with clear responsibilities, and whether the
design survives a new requirement without being rewritten.

Classic problems, all fair for a fresher: parking lot, vending machine,
elevator, library management, BookMyShow-style seat booking, Splitwise,
tic-tac-toe or chess, an ATM, a logging framework, a deck of cards, a
rate limiter as a class.

What to probe, roughly in the order the round moves:
- Requirements and assumptions before any class exists. Same discipline as
  HLD: what's in, what's out.
- The core entities and their responsibilities. One class, one reason to
  change.
- Relationships: composition vs inheritance, and why they chose one.
- The key interfaces and where polymorphism does real work.
- Design patterns where they genuinely apply - strategy, factory,
  observer, state, singleton - and whether they can justify the choice
  rather than name-dropping it.
- SOLID, applied to their own design rather than recited.
- Concurrency where the problem has it: two people booking the last seat.
- Edge cases and error handling.

Probes that work particularly well here:
- They name a pattern - ask what it buys them here, and what it would cost
  if the requirement changed.
- They reach for inheritance - ask whether composition would do, and what
  happens when a subclass needs only half the parent.
- They put logic in a god class - ask what that class's single
  responsibility is, out loud.
- They use a singleton - ask what breaks under multiple threads, and how
  they'd test code that depends on it.
- Their design is clean - add a requirement mid-flight and see whether it
  bends or breaks: the parking lot now has electric charging bays; the
  vending machine now takes cards; seats can now be held for ten minutes
  before payment.
- Ask where the state lives, and who is allowed to change it.
- Ask how they'd unit test one of their classes in isolation.

Fair for a fresher: clear class breakdown, sensible naming, applying one or
two patterns correctly, reasoning about extensibility. Unfair: expecting a
complete, compilable implementation of every method, or exotic patterns.
"""
