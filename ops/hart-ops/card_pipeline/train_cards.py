"""Train cards for the poker-size sticker sheet.

Six cards fill the empty slots after the equipment cards. They use the equipment card
layout: the title box says TRAIN (or STREETCAR), the three data rows are operator, train
symbol and job, and the photo area holds the work orders: the crew steps from the ops
docs, then ruled lines for handwriting.

Sources: Neville_Island_Crew_{D749,NVL,CK1}.docx and Neville_Island_Dispatcher_Train_List.docx
in docs/ops; the P&OV EXTRA job from www/docs/Pittsburgh_Ohio_Valley_Railway.md.
"""
from __future__ import annotations

TRAINS = [
    {"Type": "TRAIN", "RoadName": "CSX", "RoadNumber": "D749",
     "Description": "Neville Island Switcher. Demmler / McKeesport turn",
     "Orders": [
         "1. Find train tied down in West Yard with the inbound block.",
         "2. Get dispatcher clearance; run inbound to South Yard.",
         "3. Set out the Demmler / McKeesport inbound.",
         "4. Engine light to engine terminal; fuel and sand.",
         "5. When called, interchange with Yardmaster; lift outbound.",
         "6. With clearance, depart toward McKeesport.",
         "7. On return, tie down in West Yard; secure the engine.",
     ]},
    {"Type": "TRAIN", "RoadName": "POHC", "RoadNumber": "NVL",
     "Description": "Neville Island Turn. Scully / McKees Rocks",
     "Orders": [
         "1. Assign on the train at Scully Yard with the inbound block.",
         "2. Get dispatcher clearance; run to South Yard.",
         "3. Interchange with Yardmaster; lift the local industry cut.",
         "4. Work Aristech, A. Stucki, Calgon Carbon, Ferrellgas,",
         "    Kosmos Cement and Shenango Coke Works.",
         "5. Return to South Yard; lift the Scully outbound block.",
         "6. With clearance, depart for McKees Rocks / Scully; secure.",
     ]},
    {"Type": "TRAIN", "RoadName": "HART", "RoadNumber": "CK1",
     "Description": "Coke Transfer. Power from the Yardmaster",
     "Orders": [
         "1. Report to Yardmaster for the assigned engine.",
         "2. Calibrate the track scale with the scale test car.",
         "3. Shenango Coke Works pickup and delivery as directed.",
         "4. Weigh the coke pull on the South Yard west-lead scale",
         "    at a steady stretch; no brakes under weigh.",
         "5. Sort and set out weighed cars in South Yard.",
     ]},
    {"Type": "STREETCAR", "RoadName": "PRC", "RoadNumber": "Route 23",
     "Description": "Neville Queen. Streetcar 4678, Barn to McKees Rocks",
     "Orders": [
         "Employee Timetable No. 23, station time.",
         "Eastbound: Barn 9:00 AM to McKees Rocks 10:00 AM.",
         "Westbound: McKees Rocks 4:00 PM to Barn 5:00 PM.",
         "Stop at all scheduled stations unless directed.",
         "Ahead of schedule only by dispatcher authority.",
         "Compare watches before duty. Freight holds until clear.",
     ]},
    {"Type": "TRAIN", "RoadName": "CSX", "RoadNumber": "OCS-1",
     "Description": "Office Car Special. Highest priority",
     "Orders": [
         "Run when scheduled.",
         "Highest priority: dispatcher clears the route.",
     ]},
    {"Type": "TRAIN", "RoadName": "HART", "RoadNumber": "EXTRA",
     "Description": "Extra train. Runs as called by the Dispatcher", "Orders": []},
]


def train_cards() -> list[tuple[dict, None, dict]]:
    """Card tuples in the shape generate_all_cards.generate reads."""
    return [({**t, "Blank": "1"}, None, {}) for t in TRAINS]
