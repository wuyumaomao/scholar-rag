# Agent Session Prompts

## New Window Startup

```text
Confirm project rules are loaded, then read AGENT_HANDOFF.md and follow its Recovery Reading Order. At minimum read .agent-handoff/snapshot.md, .agent-handoff/risks.md, and .agent-handoff/backlog.md before planning.

Recover the current objective, status, immediate next action, active files, blockers, validation caveats, and source files that need inspection. Read only task-relevant files after that. During the task, update the smallest relevant .agent-handoff file whenever objective, decisions, changed files, validation, risks, blockers, or next steps change. Complete handoff closeout before the final response.
```

## Continue Specific Task

```text
Continue this task: <specific task>.

Treat this as an explicit request to continue execution. Do not answer "No response requested." First state what you believe the previous step was, identify the next concrete action, then continue. If context is insufficient, recover from AGENT_HANDOFF.md and the required .agent-handoff files before acting.

Start by reading AGENT_HANDOFF.md, then .agent-handoff/snapshot.md, .agent-handoff/risks.md, and .agent-handoff/backlog.md. Inspect task-relevant source files. Maintain the multi-document handoff: update snapshot at the start, decisions when durable choices are made, work-log when files change, validation when checks run or are skipped, and risks/backlog when follow-ups or unknowns change.
```

## Closeout

```text
Before ending this turn, update the multi-document handoff: refresh .agent-handoff/snapshot.md, update .agent-handoff/work-log.md, record .agent-handoff/validation.md, update .agent-handoff/backlog.md and .agent-handoff/risks.md, and remove or rewrite stale state. Then report what changed, what was validated, and what remains.
```

## Handoff Quality Review

```text
Review and directly repair the multi-document handoff so a new agent can take over. Check that AGENT_HANDOFF.md is only an index, snapshot is current and short, next actions are concrete, paths are locatable, decisions have reasons and evidence, validation is recorded, and stale, contradictory, speculative, or chat-transcript content is removed.
```
