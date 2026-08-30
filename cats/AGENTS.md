# CATS in this repo

`cats/` is **HART** panels, bindings, launchers, and docs. It is not the CATS application source.

**Upstream (open source):** [Kb0oys/cats](https://bitbucket.org/Kb0oys/cats/src/master/)

```bash
./tools/cats/fetch_cats_src.sh    # → tools/cats/src-repo/ (gitignored)
```

Read Java there (`tools/cats/src-repo/cats/layout/items/TrackGroup.java`, …).

**Do not** `jar xf` / decompile `cats.jar` or `designer.jar` into `cats/` or the repo root. That dumps `.class` next to our panels and is not source. If you need a method, clone Bitbucket; `javap` on `/Applications/JMRI/cats.jar` is a last resort and stays in `/tmp`.

Runtime install is the 3.2 zip + optional `tools/cats/patches/cats-pts-nullguard.jar` overlay (javassist, not a decompiled tree). See [`tools/cats/patches/README.md`](../tools/cats/patches/README.md).
