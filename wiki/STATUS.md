# Live status — HART / CATS

Updated: 2026-08-07 (agent)

## Now

- **Root cause of blank CATS panel:** `HART_Brick.xml` used invalid `<ROUTEFEEDBACK>` inside SWITCHPOINTS. CATS threw `EmptyStackException` on File→Open.
- **Fix:** Regenerated `cats/panels/HART_Brick.xml` with Designer-valid `SELECTEDREPORT` + `ROUTECOMMAND` (per Armstrong Full).
- **Fallback:** `cats/panels/HART_Brick_magnet.xml` — same Brick geometry, no MQTT wiring (should always paint track).

## Try when back

```bash
cd /Users/lnevo/Panel
./cats/scripts/launch_cats.sh
# File → Open → cats/panels/HART_Brick_magnet.xml   # expect visible Brick grid
# then retry → cats/panels/HART_Brick.xml            # MQTT-bound
```

Do **not** use `sudo`. Launcher must print `JAVA_HOME=.../jdk-17...`.

## Human replies

<!-- leave notes below -->

