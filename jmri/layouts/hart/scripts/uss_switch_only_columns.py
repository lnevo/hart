#!/usr/bin/env python3
"""Add switch-only CTC columns for USS plants that currently have only a Local lock.

Eight Master 4 yard plants (Switches 9, 11, 17, 19, 21, 25, 27, 29) already have
LOCKTOGGLE icons on the 20-column board. They were never given switch levers, so
the field can still throw them while the dispatcher has no N/R handle. This
module inserts the missing CTC internals + code-button data.

Safe to re-run.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(Path(__file__).resolve().parent))

# slot, SwitchNumber (IS odd), SignalEtcNumber (existing LOCKTOGGLE), UniqueID, GUIColumn, turnout
NEW_COLUMNS = (
    (4, 31, 32, 28, 5, "Switch 9"),
    (5, 33, 34, 29, 9, "Switch 11"),
    (8, 35, 36, 30, 13, "Switch 17"),
    (9, 37, 38, 31, 17, "Switch 19"),
    (10, 39, 40, 32, 18, "Switch 21"),
    (12, 13, 14, 33, 19, "Switch 25"),
    (13, 15, 16, 34, 20, "Switch 27"),
    (14, 19, 20, 35, 21, "Switch 29"),
)

ODD_SUFFIXES = ("LEVER", "SWNI", "SWRI")
EVEN_SUFFIXES = (
    "CB",
    "CALLON",
    "LDGK",
    "NGK",
    "RDGK",
    "LDGL",
    "NGL",
    "RDGL",
    "UNLOCKEDINDICATOR",
)

COLUMN_XML = """    <ctcCodeButtonData>
      <UniqueID>{uid}</UniqueID>
      <SwitchNumber>{sw}</SwitchNumber>
      <SignalEtcNumber>{sig}</SignalEtcNumber>
      <GUIColumnNumber>{col}</GUIColumnNumber>
      <CodeButtonInternalSensor>IS{sig}:CB</CodeButtonInternalSensor>
      <OSSectionOccupiedExternalSensor />
      <OSSectionOccupiedExternalSensor2 />
      <OSSectionSwitchSlavedToUniqueID>-1</OSSectionSwitchSlavedToUniqueID>
      <GUIGeneratedAtLeastOnceAlready>false</GUIGeneratedAtLeastOnceAlready>
      <CodeButtonDelayTime>0</CodeButtonDelayTime>
      <SIDI_Enabled>false</SIDI_Enabled>
      <SIDI_LeftInternalSensor>IS{sig}:LDGK</SIDI_LeftInternalSensor>
      <SIDI_NormalInternalSensor>IS{sig}:NGK</SIDI_NormalInternalSensor>
      <SIDI_RightInternalSensor>IS{sig}:RDGK</SIDI_RightInternalSensor>
      <SIDI_CodingTimeInMilliseconds>2000</SIDI_CodingTimeInMilliseconds>
      <SIDI_TimeLockingTimeInMilliseconds>3000</SIDI_TimeLockingTimeInMilliseconds>
      <SIDI_TrafficDirection>RIGHT</SIDI_TrafficDirection>
      <SIDI_LeftRightTrafficSignals />
      <SIDI_RightLeftTrafficSignals />
      <SIDL_Enabled>false</SIDL_Enabled>
      <SIDL_LeftInternalSensor>IS{sig}:LDGL</SIDL_LeftInternalSensor>
      <SIDL_NormalInternalSensor>IS{sig}:NGL</SIDL_NormalInternalSensor>
      <SIDL_RightInternalSensor>IS{sig}:RDGL</SIDL_RightInternalSensor>
      <SWDI_Enabled>true</SWDI_Enabled>
      <SWDI_NormalInternalSensor>IS{sw}:SWNI</SWDI_NormalInternalSensor>
      <SWDI_ReversedInternalSensor>IS{sw}:SWRI</SWDI_ReversedInternalSensor>
      <SWDI_ExternalTurnout>{turnout}</SWDI_ExternalTurnout>
      <SWDI_CodingTimeInMilliseconds>2000</SWDI_CodingTimeInMilliseconds>
      <SWDI_FeedbackDifferent>false</SWDI_FeedbackDifferent>
      <SWDI_GUITurnoutType>0</SWDI_GUITurnoutType>
      <SWDI_GUITurnoutLeftHand>false</SWDI_GUITurnoutLeftHand>
      <SWDI_GUICrossoverLeftHand>false</SWDI_GUICrossoverLeftHand>
      <SWDL_Enabled>true</SWDL_Enabled>
      <SWDL_InternalSensor>IS{sw}:LEVER</SWDL_InternalSensor>
      <CO_Enabled>false</CO_Enabled>
      <CO_CallOnToggleInternalSensor>IS{sig}:CALLON</CO_CallOnToggleInternalSensor>
      <CO_GroupingsList />
      <TRL_Enabled>false</TRL_Enabled>
      <TRL_LeftRules />
      <TRL_RightRules />
      <TUL_Enabled>true</TUL_Enabled>
      <TUL_DispatcherInternalSensorLockToggle>IS{sig}:LOCKTOGGLE</TUL_DispatcherInternalSensorLockToggle>
      <TUL_ExternalTurnout>{turnout}</TUL_ExternalTurnout>
      <TUL_ExternalTurnoutFeedbackDifferent>false</TUL_ExternalTurnoutFeedbackDifferent>
      <TUL_DispatcherInternalSensorUnlockedIndicator>IS{sig}:UNLOCKEDINDICATOR</TUL_DispatcherInternalSensorUnlockedIndicator>
      <TUL_NoDispatcherControlOfSwitch>false</TUL_NoDispatcherControlOfSwitch>
      <TUL_ndcos_WhenLockedSwitchStateIsClosed>true</TUL_ndcos_WhenLockedSwitchStateIsClosed>
      <TUL_GUI_IconsEnabled>true</TUL_GUI_IconsEnabled>
      <TUL_LockImplementation>0</TUL_LockImplementation>
      <TUL_AdditionalExternalTurnouts />
      <IL_Enabled>false</IL_Enabled>
      <IL_Signals />
    </ctcCodeButtonData>
"""

SENSOR_XML = """    <sensor inverted="false">
      <systemName>{sys}</systemName>
      <userName>{user}</userName>
      <comment>{comment}</comment>
    </sensor>
"""


def _needed_sensors() -> list[str]:
    names: list[str] = []
    for _slot, sw, sig, _uid, _col, _to in NEW_COLUMNS:
        for suffix in ODD_SUFFIXES:
            names.append("IS%d:%s" % (sw, suffix))
        for suffix in EVEN_SUFFIXES:
            names.append("IS%d:%s" % (sig, suffix))
    return names


def ensure_columns(text: str) -> str:
    from refresh_bean_comments import ctc_comment, ctc_user_name, refresh_comments

    missing_sensors = [
        name for name in _needed_sensors() if "<systemName>%s</systemName>" % name not in text
    ]
    if missing_sensors:
        blobs = []
        for name in missing_sensors:
            blobs.append(
                SENSOR_XML.format(
                    sys=name,
                    user=ctc_user_name(name) or name,
                    comment=ctc_comment(name) or "",
                )
            )
        insert = "".join(blobs)
        marker = '      <systemName>IS40:LOCKTOGGLE</systemName>'
        idx = text.find(marker)
        if idx < 0:
            raise RuntimeError("IS40:LOCKTOGGLE sensor not found")
        end = text.find("</sensor>", idx) + len("</sensor>")
        text = text[:end] + "\n" + insert + text[end:]

    added = 0
    for _slot, sw, sig, uid, col, turnout in NEW_COLUMNS:
        if re.search(
            r"<ctcCodeButtonData>\s*<UniqueID>%d</UniqueID>" % uid,
            text,
        ):
            continue
        if re.search(
            r"<SwitchNumber>%d</SwitchNumber>" % sw,
            text,
        ):
            continue
        xml = COLUMN_XML.format(uid=uid, sw=sw, sig=sig, col=col, turnout=turnout)
        if "</ctcdata>" not in text:
            raise RuntimeError("no </ctcdata>")
        text = text.replace("</ctcdata>", xml + "  </ctcdata>", 1)
        added += 1

    text = re.sub(
        r"<NextUniqueNumber>\d+</NextUniqueNumber>",
        "<NextUniqueNumber>36</NextUniqueNumber>",
        text,
        count=1,
    )
    text, _n = refresh_comments(text)
    return text


def main() -> int:
    import sys

    paths = [
        ROOT / "jmri/layouts/hart/output/tables.xml",
        ROOT / "tables/new_tables.xml",
    ]
    write = "--apply" in sys.argv
    for path in paths:
        if not path.is_file():
            continue
        updated = ensure_columns(path.read_text(encoding="utf-8"))
        print("%s: columns ready" % path.relative_to(ROOT))
        if write:
            path.write_text(updated, encoding="utf-8")
    if not write:
        print("dry-run (pass --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
