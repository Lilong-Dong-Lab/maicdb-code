# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the actual label strings used in this repo's issue tracker.

| Label in mattpocock/skills | Label in our tracker | Meaning                                  |
| -------------------------- | -------------------- | ---------------------------------------- |
| `needs-triage`             | `needs-triage`       | Maintainer needs to evaluate this issue  |
| `needs-info`               | `needs-info`         | Waiting on reporter for more information |
| `ready-for-agent`          | `ready-for-agent`    | Fully specified, ready for an AFK agent  |
| `ready-for-human`          | `ready-for-human`    | Requires human implementation            |
| `wontfix`                  | `wontfix`            | Will not be actioned                     |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding label string from this table.

Edit the "Label in our tracker" column to match whatever vocabulary you actually use.

## Trigger clauses gate `ready-for-agent`

A ticket whose body carries a `Trigger (do NOT do before …)` clause is **not** `ready-for-agent` until the trigger fires. Deferring: remove `ready-for-agent` (keep the ticket open), run the ticket's census command, and record the result in a comment. Restoring: re-run the census when a new data tag ships; on a fired trigger, tick nothing — comment the count and re-apply the label.

The label is the surface every skill trusts; the body is the truth. A `/implement` run that picks a trigger-gated ticket by label alone builds work the ticket forbids — and CLAUDE.md's adjudication rule makes that override look legitimate at PR time. Witness: #12 carried `ready-for-agent` with an un-fired trigger (census 0 rows, 2026-11-07); caught only because the ticket body was read before scoping.
