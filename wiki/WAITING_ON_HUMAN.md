# Waiting on you

## Operations Pro plugin: merge order

Your decisions, in this order:

1. **Decide backup retention (fault #19).** Each `ops_apply` leaves a backup set. Recommended: never delete, only warn when they build up. The alternative is keeping the newest N, which throws away undo points.
2. **Review and merge `agent/claude/ops-fixes` into `main` in model-railroad-skills.** It holds the fault fixes and includes `agent/claude/ops-showcase`, so the showcase railroad lands too.
3. **Move the hart submodule pointer** for `external/model-railroad-skills` to that `main`. Until then the hart checkout does not show the fixes or the showcase.
4. **Merge hart branch `agent/claude/opspro-showcase-copy`.** It adds `docs/ops/opspro-showcase/`, the fault list and the fix prompt. Skip it if the plugin's copy is enough, though the fault list exists only there.
5. **Mark the plugin production,** as in [`STATUS.md`](STATUS.md) under Future goals.
6. **Test a marketplace install** of the production version.

ADR-004 locks still hold: current host JMRI, **CATS** throws CTC switches. Live desks are **CATS CTC** / **CATS ABS** ([ADR-012](decisions/ADR-012-one-digicon-source.md)).

Railroad work that is still open is in [`STATUS.md`](STATUS.md) (Owed) and [`projects/hart-panel.md`](projects/hart-panel.md) (Remaining).

## Future goals (not a gate)

- **Speed matching** — choose the method, then replace the synthesized profiles: [`projects/speedmatching.md`](projects/speedmatching.md)
