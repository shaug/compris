# Cognitive debt

This is the problem compris exists to solve. [cognitive-shaping-doctrine.md]
states the standard that answers it; [cognitive-driven-development.md] records
the program that builds it.

## The debt

Cognitive debt is accumulated understanding that lives in developers' minds
rather than in the code — the fragmentation of shared comprehension about what a
program does, why it was built that way, and how it can safely be changed. The
term and its framing are Margaret Storey's, in [Cognitive debt].

It is not technical debt under another name, and the distinction is the whole
point. Technical debt is a property of the artifact: design and implementation
choices that later impede comprehension. Cognitive debt is a property of the
people. It "lives in developers' minds" and shows up in what they are able to
attempt. You pay technical debt down by editing code. You cannot pay cognitive
debt down that way, because what is missing was never in the code to begin with.

Underneath sits Naur's claim, which Storey restates: a program is a theory held
in the minds of the developers who built it. Source is a projection of that
theory, not the theory itself. Lose the theory and the code survives — intact,
passing its tests, and modifiable only by guesswork.

Storey's symptom list is a description of that end state. Team members hesitate
to change things for fear of what will break. Knowledge concentrates in a few
people. The system becomes a black box. Simple modifications start failing. The
project is paralyzed while the code still works.

## Why agents change the problem

Cognitive debt has always accrued — through turnover, haste, scale, and the
reluctance to slow down. What changes when agents become the primary vector of
implementation is the rate, and the default.

Agents generate correct code faster than any human forms a theory of it.
Geoffrey Litt's [Understanding is the new bottleneck] names the consequence: the
constraint on the work stops being how fast code can be written and becomes how
fast it can be understood. Nothing about a correct diff builds a theory of the
change in a human mind. Under agentic implementation, cognitive debt is what
accrues when nobody intervenes — the neutral outcome, not the negligent one.

This is why velocity is the wrong headline number for an agent suite. A suite
that ships more merged pull requests per week while the humans lose the plot has
not made the project faster. It has moved the cost somewhere that does not show
up in the metric, and Storey's answer stands: velocity without understanding is
not sustainable.

## What understanding is for

Two things, and the second is the one usually left out.

**Verification.** You cannot approve what you do not understand. A review that
rubber-stamps an unread diff produces the artifact of review and none of its
value.

**Participation.** Litt's sharper claim: a human without a current theory of the
system cannot direct the next loop either. They can only accept or reject what
is proposed to them. Conceptual fluency is what makes the next instruction worth
giving — so understanding is what keeps a human a creative participant in the
work, not merely its gate.

The verification argument alone would justify understanding the changes you are
asked to sign off on. The participation argument justifies understanding the
system you are building, which is a larger obligation and the one that decays
quietly.

Neither argument asks agents to slow to human reading speed. The goal is to keep
the theory of the program in human minds while agents write the code.

## compris's response is structural

Most prescriptions in this space are presentational: they meet a mind with the
change as produced, and work to explain it well — narrative diffs, interactive
walkthroughs, explorable models. Litt's three techniques are all of this kind,
and they are good.

compris intervenes earlier. It constrains the shape of the work so the change
fits a theory a human can hold, rather than producing changes that then need
heroic explanation. The two interventions compose; they are not substitutes, and
compris is the upstream one.

Three commitments follow, and each is already load-bearing in the suite.

- **Shape.** Work is broken apart by what a reviewer can understand, and that is
  the binding constraint rather than a nicety observed when there is time. The
  standard, its calibration, and its breakdown rules are
  [cognitive-shaping-doctrine.md].

- **Publicity.** A theory that dies with the context that produced it was never
  shared. A plan file is local, ephemeral, and single-agent; a tracker has
  durable identity, real dependency edges, visibility to the organization, and
  survival across handoffs and context loss. That is why compris is
  ticket-driven rather than plan-driven, and it is the same argument as Storey's
  remedy against tribal knowledge.

- **Why, not just what.** Storey asks for the rationale to be recorded, not only
  the change. compris requires a design document for every ticket, scaled to the
  work, and its review lenses return reasoning rather than a verdict alone.

`compris` is French for *understood* — what the suite claims at the moment work
changes hands. The claim is the point of the name, and this document is what it
would mean to have earned it.

## What this does not claim

Three limits, stated so nothing here reads as more than it is.

compris does not measure cognitive debt. Nothing in the suite observes whether a
human understood a changeset; shape judgment establishes that a change *could*
be understood in one sitting, which is a precondition and not evidence.

compris does not gate on understanding. Shape is always judged, and whether an
`exceeds` verdict blocks anything is the consuming project's decision. There is
deliberately no speed regulator — no mechanism that holds work until
comprehension is demonstrated. That failure mode is diagnosed here and not yet
answered.

And no structural intervention can make someone read. Shaping the work to fit a
mind is necessary for the theory to survive. It is not sufficient, and the
remaining distance is not a thing a skill suite closes.

<!-- inline reference link definitions. please keep alphabetized -->

[cognitive debt]: https://margaretstorey.com/blog/2026/02/09/cognitive-debt/
[cognitive-driven-development.md]: cognitive-driven-development.md
[cognitive-shaping-doctrine.md]: cognitive-shaping-doctrine.md
[understanding is the new bottleneck]: https://www.geoffreylitt.com/2026/07/02/understanding-is-the-new-bottleneck
