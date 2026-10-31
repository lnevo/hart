# Docs

Project write-ups and notes live here.

| Location | Contents |
|----------|----------|
| **This folder** | Live HART publications (canonical outputs) |
| `sts-docker-helpers/docs/` | STS + HART seed operational requirements |
| `sts-docker/AGENTS.md` | STS runtime / Docker agent instructions |
| `archive/docs/` | Finished articles, PDFs, drafts, session invite sources |
| `publications/` | Rebuild scripts for official HART publications |

## Scale Operating Instructions

Canonical file: `HART Railroad Scale Operating Instructions.docx` (Revision D).

Body content and layout are defined in
`publications/rebuild_scale_operating_instructions.py`:

```bash
.venv/bin/python publications/rebuild_scale_operating_instructions.py
```

v1.0 source is archived at `archive/docs/HART Railroad Scale Operating Instructions_v1.0.docx`.

## Dispatcher Train List (DS-01)

Canonical file: `Neville_Island_Dispatcher_Train_List.docx` (Revision D).

```bash
.venv/bin/python publications/rebuild_dispatcher_train_list.py
```

Prior draft archived at `archive/docs/Neville_Island_Dispatcher_Train_List_draft.docx`.

## Yardmaster Sequence (YM-01)

Canonical file: `Neville_Island_Yardmaster_Sequence.docx` (Revision D).

```bash
.venv/bin/python publications/rebuild_yardmaster_sequence.py
```

Prior draft archived at `archive/docs/Neville_Island_Yardmaster_Sequence_draft.docx`.

## Crew Instructions (CI-D749 / CI-NVL / CI-CK1)

One 5×8 sheet per job:

| Pub | File |
|-----|------|
| CI-D749 | `Neville_Island_Crew_D749.docx` |
| CI-NVL | `Neville_Island_Crew_NVL.docx` |
| CI-CK1 | `Neville_Island_Crew_CK1.docx` |

```bash
.venv/bin/python publications/rebuild_crew_instructions.py
```

## Station Map (SM-01)

Canonical file: `Neville_Island_Station_Map.docx` (Revision A).

TT-23-styled subdivision schematic starting at **Brick** (West Yard branch,
Scale–Barn runaround / South Yard lead, East End industries, Princess →
Shenango / McKeesport–McKees Rocks). Asset: `publications/assets/station_map_subdivision.png`.

```bash
.venv/bin/python publications/rebuild_station_map.py
```

## Local Station Maps (SM-02 … SM-05)

Detail schematics with track numbers, switch numbers, and spur names:

| Pub | Area | File |
|-----|------|------|
| SM-02 | West Yard | `Neville_Island_Station_Map_West_Yard.docx` |
| SM-03 | South Yard | `Neville_Island_Station_Map_South_Yard.docx` |
| SM-04 | East End (8×5 landscape) | `Neville_Island_Station_Map_East_End.docx` |
| SM-05 | Shenango | `Neville_Island_Station_Map_Shenango.docx` |
| SM-06 | Barn (Switch 7 / 9 / 11 / 13) | `Neville_Island_Station_Map_Barn.docx` |

Sources: dispatcher panel labels, SM-01 topology, seed industry spot names.

```bash
.venv/bin/python publications/rebuild_local_station_maps.py
```

## New Operator Primer (HB-01)

Canonical file: `Neville_Island_New_Operator_Primer.docx` (Revision A).

Pre-session briefing for new crew. Invite-email sources used for the first
draft live under `archive/docs/session_invites/`.

```bash
.venv/bin/python publications/rebuild_operator_primer.py
```

## Related live files

| File | Notes |
|------|-------|
| `HART_Railroad_Publication_Standards_v1.0.docx` | Visual / numbering standards |
| `TT-23_Route23_NevilleQueen_RevisionA_v6.pptx` | Route 23 employee timetable (trifold) |
