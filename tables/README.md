# tables (local Git repo)

JMRI **tables XML** — source snapshot vs working output.

- **`tables.xml`** — read-only source snapshot (do not edit with tools unless explicitly requested).
- **`new_tables.xml`** — working output; apply transformations here.

Dispatcher pipeline input copy: [`../dispatcher/inputs/tables.xml`](../dispatcher/inputs/tables.xml).

To add GitHub later:

```bash
cd tables
git remote add origin git@github.com:<you>/tables.git
git push -u origin main
```
