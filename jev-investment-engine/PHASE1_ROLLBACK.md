# Jev Phase 1 rollback plan

Rollback order is intentionally CODE FIRST, DATABASE SECOND.

## 1. Code rollback

Promote/redeploy the last known-good Jev production commit before changing database constraints.

The old API safely ignores additive columns and the `jev_attempts` table.

## 2. Database rollback

Do not delete attempt history.

If Stage 2 needs to be backed out:

- remove the Stage 2 immutability triggers/functions,
- make `jev_evaluations.evaluation_kind` nullable again.

If Stage 1 itself must be retired after code rollback:

- preserve `jev_attempts` by renaming it to an archival name such as
  `jev_attempts_rollback_20260928`,
- keep existing evaluation rows and classifications,
- do not delete ids 1-6,
- do not drop historical attempt data.

This rollback is intentionally non-destructive. Schema cleanup can happen later after
the preserved data is reviewed.
