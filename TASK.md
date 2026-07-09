# AI Automations Analyst: practical project

> Source of truth: https://ai-specialist-builder-practical-project-production.up.railway.app/
> This file is a self-contained copy so the repo stands on its own. If the two ever disagree, the hosted brief wins.

## Objective

Show how you solve problems on an unfamiliar codebase, and show that you get what makes software usable by a team, not just functional.

## The core task

You've been handed a half-built internal dictation app. Do three things:

1. **Get oriented.** Clone the repo, run it, read the code, and write down the confusions and breaks you hit along the way.

2. **Move it forward.** Spend most of your time making the app better inside the time budget. You decide what "forward" means: fixing bugs, improving the core experience, hardening rough edges, or adding capabilities. Sensible prioritization counts for more than raw feature count.

3. **Document what's still needed.** Write a tight 1-2 page analysis (`WRITEUP.md`) covering:
   - Gaps to usability
   - Your prioritization for the next two weeks
   - Real-world readiness: accuracy, error handling, auth, privacy, cost, reliability, onboarding
   - Trade-offs you made
   - Open questions for stakeholders

## A note on direction

The prototype is a single-user, local macOS desktop app that saves to flat JSON files. The scoring rewards a dependable data model, and it rewards things that are harder to show in a purely local tool: shared multi-user data, accounts, access control, team handoff.

Worth being precise here. A real local data model is easy to add natively (SQLite, say). But a single local database file is one person's data on one laptop, not a shared team system. How far up that ladder you go, local store, local-first with sync, or a networked backend, is a judgment call. Make it on purpose, and explain why.

## Deliverables

- A forked or branched repo with your working code.
- `WRITEUP.md`, your findings and reasoning (there's a template in the repo).
- Setup notes for running whatever you built (update the "Running the prototype" section of the `README`, or add your own).
- Everything in by the deadline.

## How your work is scored

| Criterion | Focus |
|-----------|-------|
| **Problem-solving** | Speed of orientation, spotting priorities, making real progress under constraint |
| **Structure** | Dependable foundation: data model, database, workflows, performance, extensible architecture |
| **UI & UX** | Visual appeal, intuitiveness, low friction for non-technical users |
| **Team readiness** | Multi-user support, accounts, access control, handoff capability |
| **Product thinking** | Quality of the writeup: realistic, prioritized, ownership-minded |
| **Craft** | Effective use of AI tools, clear communication of your decisions |

> We're not grading on how many features you finish. Thoughtful and unfinished beats thoughtless and voluminous.

## Time and constraints

- **Time budget:** about 4-6 focused hours.
- **Effort cap:** please don't go past ~6 hours. Prioritizing under constraint is part of what we're looking at.
- **Approach:** use any AI tools and libraries. Restructure the code freely. Make assumptions and write them down.
- **Ownership:** the work should reflect your own reasoning and decisions.
