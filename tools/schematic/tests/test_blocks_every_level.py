"""The block layer of every level, pinned (archive/history/wiki/projects/level-unification-handoff.md, step 5). Two views:

- the committed block and occupancy rows of devices.csv, read as plain CSV: staging's row by row (name, role, control
  point, trial name; its parts: name, part_of, trial name; occupancy: blocks and detector), and every level's other
  columns by a digest, so a change to any cell of those rows is seen. Every level's block and occupancy rows are
  the one block builder's (written_by and part_of are left out of the digests). The links are part rows: staging's
  14 and main and upper's 25, with no block or occupancy rows of their own; Track Scale is one block, none of it in
  OS Switch 7. Every level's trial names are switch-and-leg keys, so a new export's edge ids leave every row as it
  is (Readers' renumber test);
- the block layer the readers build from those rows: staging_device_map.load's {strand: blocks} over the staging
  drawing, by the drawing's own keys (OS placeholders and track pieces, from the first end of each piece), and the
  main and upper rows build_device_map.build() writes.

A change here is a change to where blocks are, which needs Signal Mast Logic discovery and the owner's approval of the
panel (the approval fingerprints rule).
"""
from __future__ import annotations

import hashlib
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))     # repo_read_only.py

import build_device_map as bdm  # noqa: E402
import staging_device_map as sdm  # noqa: E402
from hartlib import devices  # noqa: E402
from plugin_needed import skip_or_fail  # noqa: E402
from repo_read_only import RepoReadOnly  # noqa: E402

DEVICES = bdm.OUT

STAGING_BLOCKS = (
    ('OS Switch 1', 'os', 'Brick', 'OS Switch 1'),
    ('OS Switch 3', 'os', 'Brick', 'OS Switch 3'),
    ('OS Switch 5', 'os', 'Plane', 'OS Switch 5'),
    ('OS Switch 7', 'os', 'Barn', 'OS 7 A-13C'),
    ('OS Switch 7b', 'xover_corner', 'Barn', 'OS 7 A-5B'),
    ('OS Switch 9', 'os', 'Engine House', 'OS Switch 9'),
    ('OS Switch 11', 'os', 'Engine House', 'OS Switch 11'),
    ('OS Switch 13', 'os', 'Engine House', 'OS Switch 13'),
    ('OS Switch 15', 'os', 'South Yard', 'OS Switch 15'),
    ('OS Switch 17', 'os', 'South Yard', 'OS Switch 17'),
    ('OS Switch 19', 'os', 'South Yard', 'OS Switch 19'),
    ('OS Switch 21', 'os', 'South Yard', 'OS Switch 21'),
    ('OS Switch 23a', 'xover_corner', 'East End', 'OS 23 A-1A'),
    ('OS Switch 23b', 'xover_corner', 'East End', 'OS 23 A-31B'),
    ('OS Switch 25', 'os', 'East End', 'OS Switch 25'),
    ('OS Switch 27', 'os', 'East End', 'OS Switch 27'),
    ('OS Switch 29', 'os', 'East End', 'OS Switch 29'),
    ('OS Switch 31', 'os', 'East End', 'OS Switch 31'),
    ('OS Switch 33', 'os', 'East End', 'OS Switch 33'),
    ('OS Switch 35a', 'xover_corner', 'Princess', 'OS 35 A-33A'),
    ('OS Switch 35b', 'xover_corner', 'Princess', 'OS 35 A-39A, Track 35A-39A 1/2'),
    ('OS Switch 37', 'os', 'Princess', 'OS Switch 37'),
    ('OS Switch 39', 'os', 'Princess', 'OS Switch 39, Track 35A-39A 2/2'),
    ('Track Barn', 'track', 'Barn;Engine House', 'Track 7A-13C'),
    ('Track Brick-Plane', 'track', 'Brick;Plane', 'Track 1C-5A #1, Track 1C-5A #2'),
    ('Track EH-1', 'track', 'Barn;Engine House', 'Track 11B-end'),
    ('Track EH-2', 'track', 'Barn;Engine House', 'Track 9B-end'),
    ('Track EH-3', 'track', 'Barn;Engine House', 'Track 9C-end'),
    ('Track East Ext', 'track', 'Plane;Barn', 'Track 5B-7A'),
    ('Track East Lead', 'track', 'East End;Princess', 'Track 33A-35A'),
    ('Track Helix Inner', 'helix', 'Princess;CP 127', 'Track 37B-helix'),
    ('Track Helix Outer', 'helix', 'Princess;CP 127', 'Track 39B-helix'),
    ('Track K-1', 'track', 'Princess', 'Track 37C-39C #2'),
    ('Track K-2', 'track', 'Princess', 'Track 37C-39C #1'),
    ('Track Main East', 'track', 'Barn;East End', 'Track 7B-33C'),
    ('Track Main West', 'track', 'Brick;East End', 'Track 1A-23A'),
    ('Track S-1', 'track', 'South Yard;East End', 'Track 17C-29C'),
    ('Track S-2', 'track', 'South Yard;East End', 'Track 19C-27C'),
    ('Track S-3', 'track', 'South Yard;East End', 'Track 21C-25C'),
    ('Track S-4', 'track', 'South Yard;East End', 'Track 21B-25B'),
    ('Track S-R', 'track', 'South Yard;East End', 'Track 15B-23B'),
    ('Track Scale', 'track', 'Plane;Barn', 'Track 5C-7B'),
    ('Track W-1', 'track', 'Brick;West Yard', 'Track 3B-end'),
    ('Track W-2', 'track', 'Brick;West Yard', 'Track 3C-end'),
    ('Track West Ext', 'track', 'East End;Princess', 'Track 23B-35B'),
)
# (name, part_of, trial_name) of staging's parts: pieces of track inside another block
STAGING_PARTS = (
    ('Track 1-3 at 1', 'OS Switch 1', 'Track 1B-3A 1/2'),
    ('Track 1-3 at 3', 'OS Switch 3', 'Track 1B-3A 2/2'),
    ('Track 9-11', 'OS Switch 9', 'Track 9A-11C'),
    ('Track 11-13', 'OS Switch 11', 'Track 11A-13B'),
    ('Track 13-15', 'OS Switch 15', 'Track 13A-15A'),
    ('Track 15-17', 'OS Switch 15', 'Track 15C-17A'),
    ('Track 17-19', 'OS Switch 17', 'Track 17B-19A'),
    ('Track 19-21', 'OS Switch 19', 'Track 19B-21A'),
    ('Track 23-31', 'OS Switch 31', 'Track 23A-31B'),
    ('Track 25-27', 'OS Switch 25', 'Track 25A-27B'),
    ('Track 27-29', 'OS Switch 27', 'Track 27A-29B'),
    ('Track 29-31', 'OS Switch 29', 'Track 29A-31C'),
    ('Track 31-33', 'OS Switch 31', 'Track 31A-33B'),
    ('Track 35-37', 'OS Switch 35a', 'Track 35B-37A'),
)
STAGING_OCCUPANCY = (
    ('BS Barn', 'track', 'Track Barn', 'M2S1300'),
    ('BS Brick-Plane', 'track', 'Track Brick-Plane', 'M2S405'),
    ('BS EH-1', 'track', 'Track EH-1', 'M2S1306'),
    ('BS EH-2', 'track', 'Track EH-2', 'M2S1305'),
    ('BS EH-3', 'track', 'Track EH-3', 'M2S1304'),
    ('BS East Ext', 'track', 'Track East Ext', 'M2S406'),
    ('BS East Lead', 'track', 'Track East Lead', 'M2S106'),
    ('BS K-1', 'track', 'Track K-1', 'M2S100'),
    ('BS K-2', 'track', 'Track K-2', 'M2S101'),
    ('BS Main East', 'track', 'Track Main East', 'M2S202'),
    ('BS Main West', 'track', 'Track Main West', 'M2S200'),
    ('BS S-1', 'track', 'Track S-1', 'M2S206'),
    ('BS S-2', 'track', 'Track S-2', 'M2S205'),
    ('BS S-3', 'track', 'Track S-3', 'M2S204'),
    ('BS S-4', 'track', 'Track S-4', 'M2S203'),
    ('BS S-R', 'track', 'Track S-R', 'M2S207'),
    ('BS Scale', 'track', 'Track Scale', 'M2S407'),
    ('BS Switch 1', 'os', 'OS Switch 1', 'M2S401'),
    ('BS Switch 3', 'os', 'OS Switch 3', 'M2S400'),
    ('BS Switch 5', 'os', 'OS Switch 5', 'M2S404'),
    ('BS Switch 7', 'os', 'OS Switch 7', 'M2S1302'),
    ('BS Switch 7b', 'xover_corner', 'OS Switch 7b', 'M2S1303'),
    ('BS Switch 9', 'os', 'OS Switch 9', 'M2S1307'),
    ('BS Switch 11', 'os', 'OS Switch 11', 'M2S1301'),
    ('BS Switch 13', 'os', 'OS Switch 13', 'M2S300'),
    ('BS Switch 15', 'os', 'OS Switch 15', 'M2S301'),
    ('BS Switch 17', 'os', 'OS Switch 17', 'M2S302'),
    ('BS Switch 19', 'os', 'OS Switch 19', 'M2S304'),
    ('BS Switch 21', 'os', 'OS Switch 21', 'M2S306'),
    ('BS Switch 23a', 'xover_corner', 'OS Switch 23a', 'M2S1203'),
    ('BS Switch 23b', 'xover_corner', 'OS Switch 23b', 'M2S1205'),
    ('BS Switch 25', 'os', 'OS Switch 25', 'M2S1200'),
    ('BS Switch 27', 'os', 'OS Switch 27', 'M2S1202'),
    ('BS Switch 29', 'os', 'OS Switch 29', 'M2S1204'),
    ('BS Switch 31', 'os', 'OS Switch 31', 'M2S1206'),
    ('BS Switch 33', 'os', 'OS Switch 33', 'M2S1207'),
    ('BS Switch 35a', 'xover_corner', 'OS Switch 35a', 'M2S105'),
    ('BS Switch 35b', 'xover_corner', 'OS Switch 35b', 'M2S104'),
    ('BS Switch 37', 'os', 'OS Switch 37', 'M2S102'),
    ('BS Switch 39', 'os', 'OS Switch 39', 'M2S103'),
    ('BS W-1', 'track', 'Track W-1', 'M2S403'),
    ('BS W-2', 'track', 'Track W-2', 'M2S402'),
    ('BS West Ext', 'track', 'Track West Ext', 'M2S107'),
    ('unused Block 2-2', 'spare', '', 'M2S201'),
    ('unused Block 3-8', 'spare', '', 'M2S307'),
)

# (name, jmri_name, layout_block, assignment) of staging's parts: each a JMRI block of its own on its block's
# occupancy sensor, named IB:AUTO:<n> and ILB<n> by the next free number (part_bean_names)
STAGING_PART_BEANS = (
    ('Track 1-3 at 1', 'IB:AUTO:0052', 'ILB52', 'virtual'),
    ('Track 1-3 at 3', 'IB:AUTO:0054', 'ILB54', 'virtual'),
    ('Track 9-11', 'IB:AUTO:0056', 'ILB56', 'virtual'),
    ('Track 11-13', 'IB:AUTO:0057', 'ILB57', 'virtual'),
    ('Track 13-15', 'IB:AUTO:0058', 'ILB58', 'virtual'),
    ('Track 15-17', 'IB:AUTO:0059', 'ILB59', 'virtual'),
    ('Track 17-19', 'IB:AUTO:0060', 'ILB60', 'virtual'),
    ('Track 19-21', 'IB:AUTO:0061', 'ILB61', 'virtual'),
    ('Track 23-31', 'IB:AUTO:0063', 'ILB63', 'virtual'),
    ('Track 25-27', 'IB:AUTO:0064', 'ILB64', 'virtual'),
    ('Track 27-29', 'IB:AUTO:0070', 'ILB70', 'virtual'),
    ('Track 29-31', 'IB:AUTO:0071', 'ILB71', 'virtual'),
    ('Track 31-33', 'IB:AUTO:0073', 'ILB73', 'virtual'),
    ('Track 35-37', 'IB:AUTO:0078', 'ILB78', 'virtual'),
)

# (level, name, part_of, trial_name) of the main and upper parts: the 25 links, each in the lower-numbered switch's OS
# block or, where a home mast stands at a switch's points facing it, the OS block at its other end (125-129, 201-205,
# 227-231, 229-233); 225's in the corner block of its leg
MAIN_UPPER_PARTS = (
    ('2', 'Track 101-103', 'OS Switch 101', 'Track 101AB-103AA'),
    ('2', 'Track 105-109', 'OS Switch 105', 'Track 105A-109C'),
    ('2', 'Track 109-111', 'OS Switch 109', 'Track 109A-111B'),
    ('2', 'Track 111-117', 'OS Switch 111', 'Track 111A-117B'),
    ('2', 'Track 113-115', 'OS Switch 113', 'Track 113A-115C'),
    ('2', 'Track 115-117', 'OS Switch 115', 'Track 115A-117C'),
    ('2', 'Track 117-119', 'OS Switch 117', 'Track 117A-119AA'),
    ('2', 'Track 121-123', 'OS Switch 121', 'Track 121BA-123C'),
    ('2', 'Track 123-125', 'OS Switch 123', 'Track 123A-125AA'),
    ('2', 'Track 125-129', 'OS Switch 129', 'Track 125BA-129A'),
    ('2', 'Track 127-131 2', 'OS Switch 127', 'Track 127BA-131BA'),
    ('3', 'Track 201-203', 'OS Switch 201', 'Track 201B-203A'),
    ('3', 'Track 201-205', 'OS Switch 205', 'Track 201C-205A'),
    ('3', 'Track 201-219', 'OS Switch 201', 'Track 201A-219B #1, Track 201A-219B #2'),
    ('3', 'Track 205-209', 'OS Switch 205', 'Track 205C-209A'),
    ('3', 'Track 213-215', 'OS Switch 213', 'Track 213B-215A'),
    ('3', 'Track 219-221', 'OS Switch 219', 'Track 219A-221AA'),
    ('3', 'Track 225-227', 'OS Switch 225c', 'Track 225A-227A'),
    ('3', 'Track 225-229', 'OS Switch 225b', 'Track 225D-229A'),
    ('3', 'Track 227-231', 'OS Switch 231', 'Track 227B-231A'),
    ('3', 'Track 229-233', 'OS Switch 233', 'Track 229B-233A'),
    ('3', 'Track 231-237', 'OS Switch 231', 'Track 231C-237A'),
    ('3', 'Track 235-243', 'OS Switch 235', 'Track 235B-243AA'),
    ('3', 'Track 237-239', 'OS Switch 237', 'Track 237B-239A'),
    ('3', 'Track 239-245', 'OS Switch 239', 'Track 239C-245AA'),
)

# (level, name, trial_name) of the main and upper block rows but the parts: switch-and-leg keys, as staging's (not
# AnyRail plan edges such as "Track e33 1"), the OS blocks keyed by their own name
MAIN_UPPER_TRIALS = (
    ('2', 'OS Switch 101', 'OS Switch 101'),
    ('2', 'OS Switch 103', 'OS Switch 103'),
    ('2', 'OS Switch 105', 'OS Switch 105'),
    ('2', 'OS Switch 107', 'OS Switch 107'),
    ('2', 'OS Switch 109', 'OS Switch 109'),
    ('2', 'OS Switch 111', 'OS Switch 111'),
    ('2', 'OS Switch 113', 'OS Switch 113'),
    ('2', 'OS Switch 115', 'OS Switch 115'),
    ('2', 'OS Switch 117', 'OS Switch 117'),
    ('2', 'OS Switch 119', 'OS Switch 119'),
    ('2', 'OS Switch 121', 'OS Switch 121'),
    ('2', 'OS Switch 123', 'OS Switch 123'),
    ('2', 'OS Switch 125', 'OS Switch 125'),
    ('2', 'OS Switch 127', 'OS Switch 127'),
    ('2', 'OS Switch 129', 'OS Switch 129'),
    ('2', 'OS Switch 131', 'OS Switch 131'),
    ('2', 'Track 101 Spur 1', 'Track 101AA-end'),
    ('2', 'Track 101 Spur 2', 'Track 101BB-end'),
    ('2', 'Track 101-111', 'Track 101BA-111C'),
    ('2', 'Track 103 Spur', 'Track 103BB-end'),
    ('2', 'Track 103-105 1', 'Track 103AB-105B'),
    ('2', 'Track 103-105 2', 'Track 103BA-105C'),
    ('2', 'Track 107 Loop 1', 'Track 107B-107C #1'),
    ('2', 'Track 107 Loop 2', 'Track 107B-107C #2'),
    ('2', 'Track 107-109', 'Track 107A-109B'),
    ('2', 'Track 113 Spur 1', 'Track 113B-end'),
    ('2', 'Track 113 Spur 2', 'Track 113C-end'),
    ('2', 'Track 115 Spur', 'Track 115B-end'),
    ('2', 'Track 119 Spur', 'Track 119BB-end'),
    ('2', 'Track 119-121', 'Track 119BA-121BC'),
    ('2', 'Track 119-123', 'Track 119AB-123B'),
    ('2', 'Track 121 Spur', 'Track 121AA-end'),
    ('2', 'Track 121-125', 'Track 121AB-125BC'),
    ('2', 'Track 125-127', 'Track 125AB-127AA'),
    ('2', 'Track 127-131 1', 'Track 127AB-131AB'),
    ('2', 'Track 129 Spur 1', 'Track 129B-end'),
    ('2', 'Track 129 Spur 2', 'Track 129C-end'),
    ('2', 'Track Helix Outer', 'Track 131AA-helix'),
    ('3', 'OS Switch 201', 'OS Switch 201'),
    ('3', 'OS Switch 203', 'OS Switch 203'),
    ('3', 'OS Switch 205', 'OS Switch 205'),
    ('3', 'OS Switch 207', 'OS Switch 207'),
    ('3', 'OS Switch 209', 'OS Switch 209'),
    ('3', 'OS Switch 211', 'OS Switch 211'),
    ('3', 'OS Switch 213', 'OS Switch 213'),
    ('3', 'OS Switch 215', 'OS Switch 215'),
    ('3', 'OS Switch 217', 'OS Switch 217'),
    ('3', 'OS Switch 219', 'OS Switch 219'),
    ('3', 'OS Switch 221', 'OS Switch 221'),
    ('3', 'OS Switch 223', 'OS Switch 223'),
    ('3', 'OS Switch 225a', 'OS Switch 225a'),
    ('3', 'OS Switch 225b', 'OS Switch 225b'),
    ('3', 'OS Switch 225c', 'OS Switch 225c'),
    ('3', 'OS Switch 225d', 'OS Switch 225d'),
    ('3', 'OS Switch 227', 'OS Switch 227'),
    ('3', 'OS Switch 229', 'OS Switch 229'),
    ('3', 'OS Switch 231', 'OS Switch 231'),
    ('3', 'OS Switch 233', 'OS Switch 233'),
    ('3', 'OS Switch 235', 'OS Switch 235'),
    ('3', 'OS Switch 237', 'OS Switch 237'),
    ('3', 'OS Switch 239', 'OS Switch 239'),
    ('3', 'OS Switch 241', 'OS Switch 241'),
    ('3', 'OS Switch 243', 'OS Switch 243'),
    ('3', 'OS Switch 245', 'OS Switch 245'),
    ('3', 'Track 127-221', 'Track 127BB-221BA'),
    ('3', 'Track 203-207', 'Track 203C-207A'),
    ('3', 'Track 203-211', 'Track 203B-211BB'),
    ('3', 'Track 205 Spur', 'Track 205B-end'),
    ('3', 'Track 207-211', 'Track 207B-211AA'),
    ('3', 'Track 207-213', 'Track 207C-213A'),
    ('3', 'Track 209 Spur 1', 'Track 209B-end'),
    ('3', 'Track 209 Spur 2', 'Track 209C-end'),
    ('3', 'Track 211-217 1', 'Track 211AB-217BB'),
    ('3', 'Track 211-217 2', 'Track 211BA-217AA'),
    ('3', 'Track 213 Spur', 'Track 213C-end'),
    ('3', 'Track 215 Spur 1', 'Track 215B-end'),
    ('3', 'Track 215 Spur 2', 'Track 215C-end'),
    ('3', 'Track 217-219', 'Track 217BA-219C'),
    ('3', 'Track 217-221', 'Track 217AB-221BB'),
    ('3', 'Track 221-223', 'Track 221AB-223A'),
    ('3', 'Track 223-225 1', 'Track 223B-225C'),
    ('3', 'Track 223-225 2', 'Track 223C-225B'),
    ('3', 'Track 227-241 1', 'Track 227C-241B #1'),
    ('3', 'Track 227-241 2', 'Track 227C-241B #2'),
    ('3', 'Track 229-241', 'Track 229C-241A'),
    ('3', 'Track 231 Spur', 'Track 231B-end'),
    ('3', 'Track 233-235', 'Track 233C-235A'),
    ('3', 'Track 233-243', 'Track 233B-243BB'),
    ('3', 'Track 235 Spur', 'Track 235C-end'),
    ('3', 'Track 237-245', 'Track 237C-245BB'),
    ('3', 'Track 239 Spur', 'Track 239B-end'),
    ('3', 'Track 241 Spur', 'Track 241C-end'),
    ('3', 'Track 243 Spur 1', 'Track 243AB-end'),
    ('3', 'Track 243 Spur 2', 'Track 243BA-end'),
    ('3', 'Track 245 Spur 1', 'Track 245AB-end'),
    ('3', 'Track 245 Spur 2', 'Track 245BA-end'),
    ('3', 'Track Helix Inner', 'Track 131BB-helix'),
)

# the staging layer: {drawing key: blocks from the key's first end}
STAGING_LAYER = {
    'OS 23 A-1A': ('OS Switch 23a',),
    'OS 23 A-31B': ('OS Switch 23b',),
    'OS 35 A-33A': ('OS Switch 35a',),
    'OS 35 A-39A': ('OS Switch 35b',),
    'OS 7 A-13C': ('OS Switch 7',),
    'OS 7 A-5B': ('OS Switch 7b',),
    'OS Switch 1': ('OS Switch 1',),
    'OS Switch 11': ('OS Switch 11',),
    'OS Switch 13': ('OS Switch 13',),
    'OS Switch 15': ('OS Switch 15',),
    'OS Switch 17': ('OS Switch 17',),
    'OS Switch 19': ('OS Switch 19',),
    'OS Switch 21': ('OS Switch 21',),
    'OS Switch 25': ('OS Switch 25',),
    'OS Switch 27': ('OS Switch 27',),
    'OS Switch 29': ('OS Switch 29',),
    'OS Switch 3': ('OS Switch 3',),
    'OS Switch 31': ('OS Switch 31',),
    'OS Switch 33': ('OS Switch 33',),
    'OS Switch 37': ('OS Switch 37',),
    'OS Switch 39': ('OS Switch 39',),
    'OS Switch 5': ('OS Switch 5',),
    'OS Switch 9': ('OS Switch 9',),
    'Track 11A-13B': ('Track 11-13',),
    'Track 11B-end': ('Track EH-1',),
    'Track 13A-15A': ('Track 13-15',),
    'Track 15B-23B': ('Track S-R',),
    'Track 15C-17A': ('Track 15-17',),
    'Track 17B-19A': ('Track 17-19',),
    'Track 17C-29C': ('Track S-1',),
    'Track 19B-21A': ('Track 19-21',),
    'Track 19C-27C': ('Track S-2',),
    'Track 1A-23A': ('Track Main West',),
    'Track 1B-3A': ('Track 1-3 at 1', 'Track 1-3 at 3'),
    'Track 1C-5A #1': ('Track Brick-Plane',),
    'Track 1C-5A #2': ('Track Brick-Plane',),
    'Track 21B-25B': ('Track S-4',),
    'Track 21C-25C': ('Track S-3',),
    'Track 23A-31B': ('Track 23-31',),
    'Track 23B-35B': ('Track West Ext',),
    'Track 25A-27B': ('Track 25-27',),
    'Track 27A-29B': ('Track 27-29',),
    'Track 29A-31C': ('Track 29-31',),
    'Track 31A-33B': ('Track 31-33',),
    'Track 33A-35A': ('Track East Lead',),
    'Track 35A-39A': ('OS Switch 35b', 'OS Switch 39'),
    'Track 35B-37A': ('Track 35-37',),
    'Track 37B-helix': ('Track Helix Inner',),
    'Track 37C-39C #1': ('Track K-2',),
    'Track 37C-39C #2': ('Track K-1',),
    'Track 39B-helix': ('Track Helix Outer',),
    'Track 3B-end': ('Track W-1',),
    'Track 3C-end': ('Track W-2',),
    'Track 5B-7A': ('Track East Ext',),
    'Track 5C-7B': ('Track Scale',),
    'Track 7A-13C': ('Track Barn',),
    'Track 7B-33C': ('Track Main East',),
    'Track 9A-11C': ('Track 9-11',),
    'Track 9B-end': ('Track EH-2',),
    'Track 9C-end': ('Track EH-3',),
}

# (rows, sha256) of each level's block and occupancy rows but the parts, every column but written_by, part_of,
# jmri_bean (only ever set on a level-less row), id (test_device_ids pins it) and trial_name (pinned row by row
# above, on every level), joined by commas, one row a line, in file order. Main and upper's block rows carry
# their jmri_name and layout_block from block_numbering.csv, assignment virtual; staging's two spare detectors have
# detector none
DIGESTS = {"1": (90, '13524895795db40f896526a17529683fecfc34cceabffe91310db5d52087c72c'), "2": (76, '11ec552cde7611930d48ca4862f85672735dfd547527fc2deb44290a02d32200'), "3": (118, '98683379569be6ee2435fa4c9f7836562d3efa094475658862da5628703dec3d')}
# cats_discipline: the owner's CATS cell on 45 staging blocks; the pins hold what the builders make
SKIP = {level: ("written_by", "trial_name", "part_of", "jmri_bean", "id", "start", "bean_comment", "cats_discipline")
        for level in "123"}


def committed() -> list[dict]:
    # devices.load also validates the master on load, which the plain csv read did not; the rows are the same
    return [r.cells() for r in devices.load(DEVICES)]


def digest(rows: list[dict], level: str) -> tuple[int, str]:
    cols = [c for c in rows[0] if c not in SKIP[level]]
    sel = [r for r in rows if r["level"] == level and r["layer"] in ("block", "occupancy") and r["role"] != "part"]
    return len(sel), hashlib.sha256("\n".join(",".join(r[c] for c in cols) for r in sel).encode()).hexdigest()


class Committed(unittest.TestCase):
    """devices.csv as committed: plain CSV, no builder."""

    @classmethod
    def setUpClass(cls):
        cls.rows = committed()

    def test_staging_block_rows(self):
        got = tuple((r["user_name"], r["role"], r["cp"], r["trial_name"]) for r in self.rows
                    if r["level"] == "1" and r["layer"] == "block" and r["role"] != "part")
        self.assertEqual(got, STAGING_BLOCKS)

    def test_staging_parts(self):
        got = tuple((r["user_name"], r["part_of"], r["trial_name"]) for r in self.rows
                    if r["level"] == "1" and r["role"] == "part")
        self.assertEqual(got, STAGING_PARTS)
        beans = tuple((r["user_name"], r["jmri_name"], r["layout_block"], r["assignment"]) for r in self.rows
                      if r["level"] == "1" and r["role"] == "part")
        self.assertEqual(beans, STAGING_PART_BEANS)

    def test_main_and_upper_parts(self):
        got = tuple((r["level"], r["user_name"], r["part_of"], r["trial_name"]) for r in self.rows
                    if r["level"] != "1" and r["role"] == "part")
        self.assertEqual(got, MAIN_UPPER_PARTS)

    def test_every_parts_label_is_optional_on_every_level(self):
        """A part's block contents icon may be left out on every level: preferences.json's
        optional_block_contents (staging's le_labels, main's and upper's le_band_labels) lists exactly the level's
        parts, by block ID (the plugin reads their names from the merged view, hartlib.layer_files.merged). The
        plugin reads the list from the preferences only, so it is kept there and held to the device master here."""
        import json
        prefs = json.loads((bdm.OVERRIDES.parent / "preferences.json").read_text(encoding="utf-8"))
        got = {"1": prefs["staging"]["le_labels"]["optional_block_contents"],
               "2": prefs["main_upper"]["le_band_labels"]["Main"]["optional_block_contents"],
               "3": prefs["main_upper"]["le_band_labels"]["Upper"]["optional_block_contents"]}
        want = {lv: [r["id"] for r in self.rows if r["level"] == lv and r["role"] == "part"] for lv in "123"}
        self.assertEqual(got, want)

    def test_main_and_upper_trial_names(self):
        got = tuple((r["level"], r["user_name"], r["trial_name"]) for r in self.rows
                    if r["level"] != "1" and r["layer"] == "block" and r["role"] != "part")
        self.assertEqual(got, MAIN_UPPER_TRIALS)

    def test_staging_occupancy_rows(self):
        got = tuple((r["user_name"], r["role"], r["blocks"], r["system_name"]) for r in self.rows
                    if r["level"] == "1" and r["layer"] == "occupancy")
        self.assertEqual(got, STAGING_OCCUPANCY)

    def test_every_levels_block_and_occupancy_cells(self):
        for level in "123":
            with self.subTest(level=level):
                self.assertEqual(digest(self.rows, level), DIGESTS[level])


class Readers(RepoReadOnly, unittest.TestCase):
    """The block layer the readers make of the committed rows (needs the plugin at its pinned commit)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        try:
            band, _o, _c = sdm.staging_band()
        except sdm.lc.BuildError as exc:
            skip_or_fail(exc, "the block pins")
        cls.band = band
        cls.names = sdm.load(band, sdm.LoadOptions(with_masts=False))

    def test_staging_layer(self):
        _t, os_ph, refs = sdm.placeholders(self.band)
        got = {ph: (self.names["os"][n],) for n, ph in os_ph.items()}
        for sid, (piece, against) in refs.items():
            blocks = self.names["blocks"][sid]
            got["Track " + piece] = tuple(blocks[::-1] if against else blocks)
        self.assertEqual(got, STAGING_LAYER)

    def test_main_and_upper_rows_are_the_builders(self):
        import build_layout_le as bl
        try:
            bands, joined, runs, corners = bdm.solve()
        except bl.BuildError as exc:
            skip_or_fail(exc, "the block pins")
        rr = bdm.railroad.Railroad(bdm.sources(), upto="inputs")
        _cp, rows, _parts = bdm.build(bands, joined, runs, bdm.MapInputs.of(rr), corners)
        mine = [(str(r["level"]), r["user_name"], r["trial_name"], r["notes"]) for r in rows
                if r["layer"] in ("block", "occupancy") and str(r["level"]) in ("2", "3")]
        want = [(r["level"], r["user_name"], r["trial_name"], r["notes"]) for r in committed()
                if r["level"] in ("2", "3") and r["layer"] in ("block", "occupancy")
                and r["role"] != "part"]
        self.assertEqual(mine, want)

    def build_rows(self, bands, joined, runs, corners):
        """(level, user name, trial name) of every block row (parts too) the builder writes for `bands`."""
        rr = bdm.railroad.Railroad(bdm.sources(), upto="inputs")
        _cp, rows, parts = bdm.build(bands, joined, runs, bdm.MapInputs.of(rr), corners)
        staging = bdm.staging_rows(bands, joined, runs).rows
        return sorted((str(r["level"]), r["user_name"], r["trial_name"]) for r in rows + parts + staging
                      if r["layer"] == "block")

    def test_a_renumbered_edge_id_leaves_the_rows_unchanged(self):
        """Every level's trial names are switch-and-leg keys, so a new AnyRail export, whose
        edge ids (and the strand ids made of them) change every time, leaves every block row as it is."""
        import build_layout_le as bl
        try:
            bands, joined, runs, corners = bdm.solve()
        except bl.BuildError as exc:
            skip_or_fail(exc, "the block pins")
        want = self.build_rows(bands, joined, runs, corners)
        self.assertEqual(want, sorted((r["level"], r["user_name"], r["trial_name"]) for r in committed()
                                      if r["layer"] == "block"))
        self.assertEqual([x for x in want if re.search(r"\be\d+", x[2])], [])     # no edge id in a trial name
        self.assertEqual(self.build_rows(renumbered(bands), joined, runs, corners), want)


EDGE_ID = re.compile(r"\be(\d+)")


def renumbered(x):
    """A deep copy of `x` (the solved bands) with every plan edge id renumbered, in strand ids, node and strand
    references and edges alike (e0 to e999, e1 to e998, ...), as a new export does: the order of the ids changes too."""
    if isinstance(x, str):
        return EDGE_ID.sub(lambda m: f"e{999 - int(m.group(1))}", x)
    if isinstance(x, dict):
        return {renumbered(k): renumbered(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set, frozenset)):
        return type(x)(renumbered(v) for v in x)
    return x


if __name__ == "__main__":
    unittest.main()
