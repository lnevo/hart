# ADR-019 — hart-ops moves into the hart repo

- **Status:** Accepted. Amends ADR-007, ADR-010, ADR-013 and ADR-015 where they name `external/hart-ops`.
- **Date:** 2026-11-09
- **Deciders:** lnevo

## Context

hart-ops (car repository, car cards, waybills, intake, publications, industry routing, logos) was a private repo checked out as the `external/hart-ops` submodule. Almost everything it reads and writes is in hart: photos in `ops/car-cards/`, batches in `ops/intake/`, the Operations Pro roster, the website gallery, `docs/ops`, and the STS inputs in `external/sts-helpers`. Keeping it separate cost a second "point hart-ops at…" PR for every change (24 of them in two weeks), left the main checkout on stale code after each merge, forced its worktrees to sit under `external/`, and its tests never ran in CI.

A check on 2026-11-09 found no personal data in it: no email addresses, phone numbers, addresses or secrets. Two things stood in the way of making it public, and both are dealt with here.

## Decision

1. hart-ops lives at `ops/hart-ops/` in this repo. It came in as one snapshot of `lnevo/hart-ops` at `b82b317`, without its history, because two old commits spell out the private name. `lnevo/hart-ops` is archived as the history record.
2. The private name is never written in a file. The checks that keep it off the cards and the website compare word pairs against a SHA-256 fingerprint (`ops/hart-ops/card_pipeline/private_name.py`), and `tools/audit/check_public_text.py` runs the same check over every tracked file, Office files included.
3. Office files carry no person's name in their author fields. The same audit fails on one, and `--fix` blanks it. Library names (python-docx, python-pptx, openpyxl) are allowed.
4. Logos move too; `ops/hart-ops/operator_logos/SOURCES.md` records where every file came from and how sure that is. They are used non-commercially to identify real companies, and stay as they are. The Apostrophe Games sticker template is their file, so it stays out of git: the card tools read a local copy and print the download link when it is missing.
5. The hart-ops tests run in `tools/check.sh` and in CI (`ops/hart-ops/requirements-test.txt`). The working environment is `ops/hart-ops/.venv`.

## Consequences

- One PR per change. `bin/cars` and the publication scripts keep working unchanged, because `ops/hart-ops` sits at the same depth as `external/hart-ops` did.
- `external/` holds only submodules and the STS data again; hart-ops is no longer one of them.
- Logos are trademarks of their owners, used for reference on a non-commercial layout; SOURCES.md says so and invites removal requests. Several have no recorded origin; those are marked there.
- A new machine needs the sticker template downloaded once before printing cards.
