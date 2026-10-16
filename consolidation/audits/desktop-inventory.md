# Audit — Desktop/HART root inventory

**Date:** 2026-08-31  
**Script:** `consolidation/scripts/inventory_desktop_hart.py`  
**CSV:** [`sor/desktop/hart_root_inventory.csv`](../sor/desktop/hart_root_inventory.csv)

## Taxonomy (consolidation draft)

| Class | Meaning |
|-------|---------|
| **C** | Operational subtree (Car Cards, Industries, Wiring, …) |
| **D** | Root file basename matches `Car Cards/docs/` published output (duplicate) |
| **E** | Root file content hash matches file under Car Cards |
| **F** | Archive / review candidate at Desktop root |

**Deferred (P4):** ingest F → `hart/docs/archive/`; slim Desktop to README + links.

## Summary

- **C:** 4 entries
- **D:** 4 entries
- **E:** 3 entries
- **F:** 124 entries

## Class C — subtrees

- `Car Cards/` — 30695 files, 3306.7 MB
- `DJ Trains/` — 14 files, 43.4 MB
- `Industries/` — 8 files, 0.7 MB
- `Wiring Documentation/` — 2288 files, 56.9 MB

## Class D — duplicates of Car Cards/docs

- `HART Railroad Scale Operating Instructions.docx` — basename matches Car Cards/docs published output
- `Neville_Island_Dispatcher_Train_List.docx` — basename matches Car Cards/docs published output
- `Neville_Island_Yardmaster_Sequence.docx` — basename matches Car Cards/docs published output
- `TT-23_Route23_NevilleQueen_RevisionA_v6.pptx` — basename matches Car Cards/docs published output

## Class E — hash dup of Car Cards

- `allegheny_ludlam.png` — sha256 prefix matches Car Cards/operator_logos/downloads/allegheny_ludlum.png
- `Logo.png` — sha256 prefix matches Car Cards/card_pipeline/assets/Logo_source.png
- `train_card.prompt` — sha256 prefix matches Car Cards/card_pipeline/assets/train_card.prompt

## Class F — sample (first 20)

- `1956-07-07PWV27-seabass.pdf` — root document — archive taxonomy pending
- `1VFNT00010012.jpg` — root media — archive or move to publications/assets
- `2022-10-16 16_42_35-Google Maps.png` — root media — archive or move to publications/assets
- `2022-10-16 17_37_39-USGS Historical Topographic Map Explorer.png` — root media — archive or move to publications/assets
- `305998346_10219295245405407_8127293654381891772_n.jpg` — root media — archive or move to publications/assets
- `492050449_10224674058232366_5620487153150413068_n.jpg` — root media — archive or move to publications/assets
- `ammonium sulphate.png` — root media — archive or move to publications/assets
- `basic_schematic.pptx` — root document — archive taxonomy pending
- `beckPAdiagram.jpg` — root media — archive or move to publications/assets
- `beckPAmaners.jpg` — root media — archive or move to publications/assets
- `beckPAoroszi.jpg` — root media — archive or move to publications/assets
- `bkPAmaners.jpg` — root media — archive or move to publications/assets
- `bkPAsalamon1.jpg` — root media — archive or move to publications/assets
- `bkPAsalamon2.jpg` — root media — archive or move to publications/assets
- `bkPAunknown.jpg` — root media — archive or move to publications/assets
- `ChartiersTrackScheme.jpg` — root media — archive or move to publications/assets
- `Coke_Ovens.dmg` — large installer image — archive candidate
- `flannery-16-nov-1940.jpg` — root media — archive or move to publications/assets
- `flannery_bolts_em1.jpg` — root media — archive or move to publications/assets
- `flannery_em-1.jpg` — root media — archive or move to publications/assets

## Decision not needed yet

Ingest policy for class F root files waits on **hart-ops** repo creation (P3).

