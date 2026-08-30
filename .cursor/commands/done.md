# Done

Close out this task using the repo definition of done in `AGENTS.md`:

1. Update `wiki/STATUS.md` if a live decision or railroad state changed.
2. Commit intended changes on the **current** branch (not `main`). Do not wait to be asked.
3. `git push -u origin HEAD` unless already pushed.
4. If live artifacts changed (panels, tables bundle, jython, web home, CTC icons, hart-aar, CATS resources), run:

```bash
./cats/scripts/sync_hart_package.sh --pi
```

Add `--win` or use `--all` when Windows hosts need the same package. Skip deploy for docs-only and say so.

5. Report: commit hash, pushed?, hosts deployed.

Do not commit `.env.local`, credentials, or `tools/cats/src-repo/`. Do not force-push `main`.
