# Decision Log

| Date | Decision | Reason | Evidence |
| --- | --- | --- | --- |
| 2026-09-24 | Use multi-document Agent handoff memory. | Keep current state fast to read while preserving decisions, validation, backlog, and risks in dedicated files. | Bootstrap action. |

## Decision Guidelines

- Record durable decisions only.
- Include reason and evidence.
- Do not record guesses as decisions.
- If evidence is missing, mark it as `UNKNOWN`.
