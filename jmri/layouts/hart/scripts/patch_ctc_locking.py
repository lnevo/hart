#!/usr/bin/env python3
"""Patch JMRI CTC locking so the machine matches the live layout.

  * SW112 Closed = OS East Lead ↔ 110, Thrown = OS Main East (icon + eastbound TRL)
  * SW114 / SW115 traffic direction BOTH (balloon). JMRI requires a
    unique mast in each SIDI list; 113 stays RIGHT (its homes face east).
  * SW111 eastbound OS Main West → OS West Main Ext TRL rule

Edits jmri/layouts/hart/output/tables.xml ctcdata in place.
Safe to re-run.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"

RULE_111_EAST_WME = """        <TRL_TrafficLockingRule>
          <UserRuleNumber> Rule #:2</UserRuleNumber>
          <RuleEnabled>Enabled</RuleEnabled>
          <DestinationSignalOrComment>Mast 36RA</DestinationSignalOrComment>
          <switches>
            <switch>
              <UserText>17/18</UserText>
              <SwitchAlignment>Normal</SwitchAlignment>
              <UniqueID>21</UniqueID>
            </switch>
          </switches>
          <OccupancyExternalSensors>
            <sensor>Block 12-4</sensor>
            <sensor>Block 1-8</sensor>
          </OccupancyExternalSensors>
          <OptionalExternalSensors />
        </TRL_TrafficLockingRule>
"""

RULES_114_RIGHT = """      <TRL_RightRules>
        <TRL_TrafficLockingRule>
          <UserRuleNumber> Rule #:1</UserRuleNumber>
          <RuleEnabled>Enabled</RuleEnabled>
          <DestinationSignalOrComment>Mast 38LA</DestinationSignalOrComment>
          <switches>
            <switch>
              <UserText>27/28</UserText>
              <SwitchAlignment>Normal</SwitchAlignment>
              <UniqueID>26</UniqueID>
            </switch>
          </switches>
          <OccupancyExternalSensors>
            <sensor>Block 1-3</sensor>
          </OccupancyExternalSensors>
          <OptionalExternalSensors />
        </TRL_TrafficLockingRule>
        <TRL_TrafficLockingRule>
          <UserRuleNumber> Rule #:2</UserRuleNumber>
          <RuleEnabled>Enabled</RuleEnabled>
          <DestinationSignalOrComment>Mast 38LB</DestinationSignalOrComment>
          <switches>
            <switch>
              <UserText>27/28</UserText>
              <SwitchAlignment>Reverse</SwitchAlignment>
              <UniqueID>26</UniqueID>
            </switch>
          </switches>
          <OccupancyExternalSensors>
            <sensor>Block 1-3</sensor>
            <sensor>Block 1-2</sensor>
          </OccupancyExternalSensors>
          <OptionalExternalSensors />
        </TRL_TrafficLockingRule>
      </TRL_RightRules>
"""

RULES_115_RIGHT = """      <TRL_RightRules>
        <TRL_TrafficLockingRule>
          <UserRuleNumber> Rule #:1</UserRuleNumber>
          <RuleEnabled>Enabled</RuleEnabled>
          <DestinationSignalOrComment>Mast 40LA</DestinationSignalOrComment>
          <switches>
            <switch>
              <UserText>29/30</UserText>
              <SwitchAlignment>Normal</SwitchAlignment>
              <UniqueID>27</UniqueID>
            </switch>
          </switches>
          <OccupancyExternalSensors>
            <sensor>Block 1-4</sensor>
          </OccupancyExternalSensors>
          <OptionalExternalSensors />
        </TRL_TrafficLockingRule>
        <TRL_TrafficLockingRule>
          <UserRuleNumber> Rule #:2</UserRuleNumber>
          <RuleEnabled>Enabled</RuleEnabled>
          <DestinationSignalOrComment>Mast 40LB</DestinationSignalOrComment>
          <switches>
            <switch>
              <UserText>29/30</UserText>
              <SwitchAlignment>Reverse</SwitchAlignment>
              <UniqueID>27</UniqueID>
            </switch>
          </switches>
          <OccupancyExternalSensors>
            <sensor>Block 1-4</sensor>
            <sensor>Block 1-1</sensor>
          </OccupancyExternalSensors>
          <OptionalExternalSensors />
        </TRL_TrafficLockingRule>
      </TRL_RightRules>
"""


def slice_column(text, uid):
    start = text.index("<ctcCodeButtonData>\n      <UniqueID>%s</UniqueID>" % uid)
    end = text.index("</ctcCodeButtonData>", start) + len("</ctcCodeButtonData>")
    return start, end, text[start:end]


def main():
    path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else TABLES
    text = path.read_text()
    notes = []

    # --- SW112: eastbound to 113a is Closed (OS East Lead), not Thrown ---
    s, e, col = slice_column(text, "24")
    old = col
    col = col.replace(
        """            <switch>
              <UserText>23/24</UserText>
              <SwitchAlignment>Reverse</SwitchAlignment>
              <UniqueID>24</UniqueID>
            </switch>
          </switches>
          <OccupancyExternalSensors>
            <sensor>Block 12-8</sensor>
            <sensor>Block 1-7</sensor>""",
        """            <switch>
              <UserText>23/24</UserText>
              <SwitchAlignment>Normal</SwitchAlignment>
              <UniqueID>24</UniqueID>
            </switch>
          </switches>
          <OccupancyExternalSensors>
            <sensor>Block 12-8</sensor>
            <sensor>Block 1-7</sensor>""",
        1,
    )
    if col == old:
        notes.append("112 right-rule alignment already Normal (or pattern missed)")
    else:
        notes.append("112 eastbound TRL: Reverse → Normal (OS East Lead ↔ 110)")
    text = text[:s] + col + text[e:]

    # --- SW111: missing eastbound OS Main West → OS West Main Ext ---
    s, e, col = slice_column(text, "21")
    if "Mast 36RA" in col.split("<TRL_RightRules>")[-1]:
        notes.append("111 eastbound 113b rule already present")
    else:
        col = col.replace("</TRL_RightRules>", RULE_111_EAST_WME + "      </TRL_RightRules>", 1)
        notes.append("111 added RIGHT dest Mast 36RA (OS Main West → WME)")
        text = text[:s] + col + text[e:]

    # --- Balloon: 114 / 115 BOTH (113 stays RIGHT — no unused westbound mast) ---
    s, e, col = slice_column(text, "25")
    col2 = col.replace(
        "<SIDI_TrafficDirection>BOTH</SIDI_TrafficDirection>",
        "<SIDI_TrafficDirection>RIGHT</SIDI_TrafficDirection>",
        1,
    )
    notes.append("113 traffic direction RIGHT" if col2 != col else "113 already RIGHT")
    text = text[:s] + col2 + text[e:]

    s, e, col = slice_column(text, "26")
    col = col.replace(
        "<SIDI_TrafficDirection>LEFT</SIDI_TrafficDirection>",
        "<SIDI_TrafficDirection>BOTH</SIDI_TrafficDirection>",
        1,
    )
    if "<SIDI_LeftRightTrafficSignals />" in col:
        col = col.replace(
            "<SIDI_LeftRightTrafficSignals />",
            "<SIDI_LeftRightTrafficSignals>\n        <signal>Mast 2035</signal>\n      </SIDI_LeftRightTrafficSignals>",
            1,
        )
        notes.append("114 LTR += Mast 2035")
    if "<TRL_RightRules />" in col:
        col = col.replace("<TRL_RightRules />", RULES_114_RIGHT.rstrip(), 1)
        notes.append("114 BOTH + eastbound TRL rules")
    else:
        notes.append("114 right rules already filled")
    text = text[:s] + col + text[e:]

    s, e, col = slice_column(text, "27")
    col = col.replace(
        "<SIDI_TrafficDirection>LEFT</SIDI_TrafficDirection>",
        "<SIDI_TrafficDirection>BOTH</SIDI_TrafficDirection>",
        1,
    )
    if "<SIDI_LeftRightTrafficSignals />" in col:
        col = col.replace(
            "<SIDI_LeftRightTrafficSignals />",
            "<SIDI_LeftRightTrafficSignals>\n        <signal>Mast 2036</signal>\n      </SIDI_LeftRightTrafficSignals>",
            1,
        )
        notes.append("115 LTR += Mast 2036")
    if "<TRL_RightRules />" in col:
        col = col.replace("<TRL_RightRules />", RULES_115_RIGHT.rstrip(), 1)
        notes.append("115 BOTH + eastbound TRL rules")
    else:
        notes.append("115 right rules already filled")
    text = text[:s] + col + text[e:]

    path.write_text(text)
    print("patched", path)
    for n in notes:
        print(" ", n)


if __name__ == "__main__":
    main()
