---
description: "Use when user requests phased execution, end-to-end delivery, auto-run behavior, no approval checkpoints, or complete all phases in sequence. Triggers: phase 1, phase 2, complete all 8 phases, auto run, do not ask approval, just do it all."
name: "Phased Autonomy Execution"
applyTo: "**"
---
# Phased Autonomy Execution

- Treat a phase-based request as an execution contract.
- Execute phases sequentially from the current phase through the final phase without waiting for extra approval between phases.
- After finishing each phase, immediately start the next phase.
- Do not ask for confirmation at phase boundaries unless the user explicitly asks to pause.
- Run the required tools, tests, and validation automatically for each phase.
- Keep progress updates concise and evidence-based with what was done and what starts next.
- If blocked by a hard external dependency (missing credential, unavailable service, permissions, or destructive action requiring explicit consent), state the blocker clearly, apply all non-blocked work, and continue remaining phases where possible.
- If a phase introduces code changes, validate with targeted tests and diagnostics before moving on.
- Avoid proposal-only responses when implementation is feasible in the current environment.
- Preserve existing repository changes that are unrelated; never revert user changes.
- Use this rule as a hard execution preference for this repository unless the user gives a conflicting instruction in the current conversation.
