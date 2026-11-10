# AGENTS.md — hart-ops

Car inventory, cards, waybills, publications and industries for HART. Part of the hart repo (ADR-019); it was the separate hart-ops repo until 2026-11-09.

## SoR

- **`data/image_metadata.csv`** is the one car repository: every car, with a blank `source_image` until it is photographed. Not the JMRI Operations Pro GUI.
- Use **`bin/cars`** to add cars and publish them. See `wiki/pipelines/car-workflow.md`.
- `data/car_queue.csv` tracks which new cars still need a card, STS or Operations Pro.
- Do not run `process_car_images.py`: it rewrites the repository from `Images/`.
- **`HART_CAR_IMAGES_FINAL`** — local path to `CarImagesFinal/` (not in git).

## STS

Session/seed scripts live in **`external/sts-helpers`** (sibling submodule). Use `bin/apply_hart_seed.sh` etc.

Do not duplicate `sts-docker-helpers/` in this repo.

## Documents

Created documents live in the hart repo's `docs/` (publications in `docs/ops/`, ADR-010). The scripts in `publications/` generate them. Only the car-card print archive stays here, in `ops/hart-ops/docs/print/`.

## Golden car

**NW32800** — `tests/golden/NW32800.docx`

## Do not commit

- `CarImagesFinal/`, `Images/`, `card_pipeline/output/` (except golden in `tests/golden/`)
- `.venv/`

## Related

- Layout hub: `hart` repo
- ADR: `wiki/decisions/ADR-013-car-repository.md`
