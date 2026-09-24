<!-- AGENT_HANDOFF_PROTOCOL:START -->
# Codex Agent Handoff Protocol

Layout: multi-document

## Required Startup Routine

Before making a plan or editing files, read:

1. `AGENT_HANDOFF.md`
2. `.agent-handoff/snapshot.md`
3. `.agent-handoff/risks.md`
4. `.agent-handoff/backlog.md`
5. Additional `.agent-handoff/` files only when needed by the current task, following the Recovery Reading Order in `AGENT_HANDOFF.md`
6. The source files directly relevant to the user's current request

Use the handoff files as continuity memory, but verify implementation details from source files before changing behavior.

## Default Implementation Standard

For non-trivial development work, target production/commercial-grade quality by default rather than minimum viable implementation. Prefer robust, maintainable solutions with appropriate validation, runtime and edge-case consideration, and clear reporting of what was and was not tested. Keep scope aligned with the user's request; do not add unrelated features or speculative abstractions.

## Stable File Reading Protocol

To avoid Read tool line-number or offset drift:

1. Prefer dedicated search/read tools for ordinary file lookup, content search, and file reads.
2. Confirm file size before reading large or volatile files, using line counts or targeted searches when needed.
3. Search for exact targets first, then read small exact ranges around those targets.
4. Keep Read ranges no larger than 240 lines unless the file is known to be small.
5. If Read returns unexpected empty output, offset warnings, stale snippets, inconsistent line numbers, `file is shorter than the provided offset`, or an API termination after a Read attempt, stop paging with Read for that file immediately.
6. Treat Read `offset` as a line number, not a character offset. Never retry the same out-of-range offset, and never guess by adding zeros or using large approximate offsets. If the tool reports the file has N lines, all follow-up Read offsets for that file must be within `0..N`.
7. Recover from Read offset failure by re-anchoring with a targeted `Grep` for the section/title/symbol, or by reading a small known-valid range such as offset `0`; only then read a small range around the confirmed line number.
8. When Read becomes unreliable, use shell verification commands such as `wc -l`, `rg -n`, and `sed -n '<start>,<end>p'` with quoted paths; keep ranges small and record that fallback in validation notes when relevant.
9. Treat read-only shell inspection commands (`wc`, `rg`, `grep`, `sed -n`, `ls`, `pwd`, and non-mutating `git status`/`git diff`/`git log`/`git ls-files`) as safe query operations. They should be pre-approved in project settings where possible so source verification does not require repeated manual approval.
10. Do not propose or edit code based on uncertain offsets; re-anchor with search results first.

## Continuation Recovery Guard

If the user says `continue`, `继续`, `Continue from where you left off.`, or any equivalent continuation request, treat it as an explicit instruction to resume the task. Do not answer `No response requested.` and do not stop silently. First state the last known objective and next concrete action, then continue. If context is insufficient, recover from the handoff files and task-relevant source files before acting.

## Durable Handoff Memory

The repository uses multi-document durable handoff memory:

- `AGENT_HANDOFF.md`: index and recovery route
- `.agent-handoff/snapshot.md`: current objective, status, next actions, active files, blockers, and open questions
- `.agent-handoff/workspace.md`: repository map, entry points, commands, and stable context
- `.agent-handoff/decisions.md`: durable decisions with reasons and evidence
- `.agent-handoff/work-log.md`: recent operational work
- `.agent-handoff/validation.md`: validation commands/checks and results
- `.agent-handoff/backlog.md`: pending work
- `.agent-handoff/risks.md`: risks, blockers, unknowns, and confirmations
- `.agent-handoff/archive.md`: compressed old history

Maintain the smallest relevant file. Do not put all state into `AGENT_HANDOFF.md`; it is an index.

## Handoff Size Discipline

- Keep `AGENT_HANDOFF.md` short; it is an index.
- Keep `.agent-handoff/snapshot.md` short, current, and action-oriented.
- Keep only recent, still-relevant work in `.agent-handoff/work-log.md`.
- Prefer updating existing bullets over appending duplicate or contradictory notes.
- Move stale long history to `.agent-handoff/archive.md`.
- In an ongoing uninterrupted chat, reread only relevant handoff files after compaction, resume, uncertainty, or task changes.

## Mandatory Closeout Protocol

Before any final response for a non-trivial task, update the relevant handoff files without waiting for the user to ask.

Minimum required updates:

- Refresh `.agent-handoff/snapshot.md` with current objective, status, next actions, active files, blockers, and open questions.
- Add or update `.agent-handoff/work-log.md` when files or task status changed.
- Add `.agent-handoff/validation.md` entries for commands/checks run or intentionally not run.
- Record durable decisions in `.agent-handoff/decisions.md`.
- Update `.agent-handoff/backlog.md` and `.agent-handoff/risks.md` when follow-ups, blockers, risks, or unknowns changed.
- Remove or rewrite stale state that would mislead the next agent.

If the task was purely conversational and no project state changed, no file update is required.

## Work Discipline

- Do not assume which subproject is active. Infer it from the user request, handoff files, and repository evidence.
- Prefer existing project conventions over new abstractions.
- Read files before editing them.
- Keep edits scoped to the task.
- Do not modify generated dependency folders unless explicitly asked.
- Never revert unrelated user or agent changes.
- Record validation honestly. If tests or checks were not run, say so in handoff files and in the final response.

## Session Closeout Checklist

Before final response, update the relevant `.agent-handoff/` files with final task status, files changed, commands/checks run and outcomes, and remaining risks, blockers, open questions, or next steps.
<!-- AGENT_HANDOFF_PROTOCOL:END -->
