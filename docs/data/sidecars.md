# Column sidecars

A sidecar `<name>.columns.csv` sits beside a master CSV, describes each of its columns, and gives the rules `tools/ops/check_data.py` checks it against.

The rule is decision 3 of [ADR-039](../../wiki/decisions/ADR-039-data-masters-in-git.md). The `data-schemas` step of `tools/check.sh` runs the checker on every sidecar it finds, so a new sidecar is checked without a change to `tools/pipeline/checks.toml`.

## The sidecar's columns

One row per column of the master, in the master's order. The master's header must be these column names, in that order.

| Column | Meaning |
|--------|---------|
| `column` | The master column the row describes. Required. |
| `file` | Only for a pair master: the file that holds the column, `field` or `generated`. `hartlib.devices` checks it. |
| `description` | What the column holds, for people. Required. |
| `type` | `str`, `int`, `float`, `bool` (`yes` or `no`), `enum` (one of `values`) or `id-list` (items separated by `;`, none empty or given twice). |
| `required` | `yes`, or a condition: the cell is non-empty on every row, or on the rows the condition picks. |
| `key` | `yes`, or a condition. The columns with the same `key` cell form one key: on the rows the condition picks, each of them is non-empty and together they are unique. |
| `refs` | `path/file.csv:column` from the repo root, several separated by `;`. Each value, or each item of an `id-list`, is in one of those columns. |
| `values` | The allowed values of an `enum` column, separated by `;`. Only an `enum` column has them. |

An empty rule cell means no rule. A sidecar may leave off any rule column; only `column` and `description` must be there.

A condition is `col=v1;v2`: the rows whose `col` is one of the values. `col=` picks the rows whose `col` is empty. So `level=2;3` in `required` means required on main and upper, and two keys with the conditions `level=1;2;3` and `level=` key the rows with a level one way and the level-less rows another.

## Which file is the master

The master is `<name>.csv` beside the sidecar. When there is none, it is the pair `<name>_generated.csv` and `<name>_field.csv`, merged as `hartlib.devices` merges the device master: each field row is matched by its key to a generated row and its non-empty cells win, and a field row with no match is added. The rules run on the merged rows.

A `refs` path names a master the same way: `jmri/layouts/hart/data/devices.csv:user_name` reads the merged device pair, so a name the owner gave in `devices_field.csv` counts.

## Running it

```
python3 tools/ops/check_data.py                       # every sidecar in the repo
python3 tools/ops/check_data.py path/x.columns.csv    # one sidecar
```

It walks the repo and leaves out `archive/`, `external/`, `reference/`, `node_modules/`, `tools/cats/src-repo/` and every folder whose name starts with a dot. It prints each problem with the file, the rule and the rows (up to 20 per rule), and exits 1 when any sidecar fails.

## The sidecars today

- `jmri/layouts/hart/data/devices.columns.csv`: the device pair `devices_generated.csv` and `devices_field.csv`. Keys: `level` and `id` on rows with a level, `layer` and `user_name` on a Store's level-less rows. Its `cp`, `blocks`, `protects`, `part_of`, `facing` and `switch` must name stations, control points, devices and switches that exist.
- `jmri/layouts/hart/data/switches.columns.csv`: `switches.csv`. Keys: `half` on main and upper, `os_block` on staging. Staging's legs and ids must name devices that exist, and an `owner` hand must be given.
