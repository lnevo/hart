#!/usr/bin/env python3
"""Take the West Yard ladder out of CTC signal control.

  * Remove virtual masts West Yard North OS 116 and South Yard East OS 104
    (LE icons, layoutturnout attachments, SML, CTC SIDI/TRL).
  * Move West Yard East Yard T6 back onto TO117.B (yard lead into Barn).
  * 116 / 103 become switch-only CTC columns (no signal levers).
  * T6 is a 117 westbound home again.
  * Default lock toggles for 116, 103, and 110 to Local (ACTIVE).

Safe to re-run. Edits:
  jmri/layouts/hart/output/tables.xml
  jmri/layouts/hart/output/hart_prod.xml
  jmri/layouts/hart/ctc/GUIObjects.xml
  cats/panels/HART_Master.xml
  cats/panels/HART_Master_ABS.xml
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"
HART_PROD = ROOT / "jmri/layouts/hart/output/hart_prod.xml"
GUI = ROOT / "jmri/layouts/hart/ctc/GUIObjects.xml"
CATS_CTC = ROOT / "cats/panels/HART_Master.xml"
CATS_ABS = ROOT / "cats/panels/HART_Master_ABS.xml"

DROP_MASTS = ("South Yard East OS 104", "West Yard North OS 116")
T6 = "West Yard East Yard T6"

SIG_T6 = """        <SECSIGNAL>
          {name}
          <PANELSIGNAL SIGLOCATION="LOWLEFT" SIGORIENT="LEFT" SIGPANTYPE="LAMP1" />
          <PHYSIGNAL>single</PHYSIGNAL>
        </SECSIGNAL>"""

TRL_T6_WEST = """        <TRL_TrafficLockingRule>
          <UserRuleNumber> Rule #:2</UserRuleNumber>
          <RuleEnabled>Enabled</RuleEnabled>
          <DestinationSignalOrComment>Plane East OS 102</DestinationSignalOrComment>
          <switches>
            <switch>
              <UserText>7/8</UserText>
              <SwitchAlignment>Normal</SwitchAlignment>
              <UniqueID>16</UniqueID>
            </switch>
          </switches>
          <OccupancyExternalSensors>
            <sensor>Block 13-3</sensor>
            <sensor>Block 4-8</sensor>
          </OccupancyExternalSensors>
          <OptionalExternalSensors />
        </TRL_TrafficLockingRule>
"""


def _count(pat: str, text: str) -> int:
    return len(re.findall(pat, text))


def strip_virtual_masts(text: str) -> str:
    for name in DROP_MASTS:
        text, n = re.subn(
            r"\s*<virtualsignalmast class=\"[^\"]+\">\s*"
            r"<systemName>[^<]+</systemName>\s*"
            rf"<userName>{re.escape(name)}</userName>.*?"
            r"</virtualsignalmast>",
            "",
            text,
            count=1,
            flags=re.S,
        )
        print(f"  virtual mast {name}: removed {n}")
    return text


def strip_mast_icons(text: str) -> str:
    for name in DROP_MASTS:
        text, n = re.subn(
            rf'\s*<signalmasticon signalmast="{re.escape(name)}"[^/]*/>',
            "",
            text,
        )
        print(f"  icon {name}: removed {n}")
    # T6 back onto the 117–116 yard lead (original Digicon placement)
    text, n = re.subn(
        rf'(<signalmasticon signalmast="{re.escape(T6)}" )x="\d+" y="\d+"',
        rf'\1x="520" y="322"',
        text,
    )
    print(f"  icon {T6}: moved to 520,322 ({n})")
    return text


def rebind_layout_turnouts(text: str) -> str:
    def drop_child(ident: str, tag: str, name: str, blob: str) -> str:
        pat = (
            rf'(<layoutturnout ident="{ident}"[^>]*>)(.*?)(</layoutturnout>)'
        )

        def repl(m: re.Match) -> str:
            body, k = re.subn(
                rf"\s*<{tag}>{re.escape(name)}</{tag}>",
                "",
                m.group(2),
            )
            print(f"  {ident} {tag} {name}: removed {k}")
            return m.group(1) + body + m.group(3)

        out, n = re.subn(pat, repl, blob, count=1, flags=re.S)
        if n != 1:
            print(f"  WARN: {ident} block not found")
        return out

    text = drop_child("TOL15", "signalCMast", "South Yard East OS 104", text)
    text = drop_child("TO1", "signalCMast", "West Yard North OS 116", text)
    text = drop_child("TOR14", "signalBMast", T6, text)

    # Attach T6 to TO117.B if missing
    def add_t6(m: re.Match) -> str:
        body = m.group(2)
        if f"<signalBMast>{T6}</signalBMast>" in body:
            print(f"  TO117 signalBMast {T6}: already present")
            return m.group(0)
        # insert after last existing signal*Mast, or before close
        if re.search(r"<signal[ABCD]Mast>", body):
            body = re.sub(
                r"(</signal[ABCD]Mast>)(?!.*</signal[ABCD]Mast>)",
                rf"\1\n      <signalBMast>{T6}</signalBMast>",
                body,
                count=1,
                flags=re.S,
            )
        else:
            body = f"\n      <signalBMast>{T6}</signalBMast>" + body
        print(f"  TO117 signalBMast {T6}: added")
        return m.group(1) + body + m.group(3)

    text, n = re.subn(
        r'(<layoutturnout ident="TO117"[^>]*>)(.*?)(</layoutturnout>)',
        add_t6,
        text,
        count=1,
        flags=re.S,
    )
    if n != 1:
        print("  WARN: TO117 not found")
    return text


def strip_sml(text: str) -> str:
    # Remove whole source-logic blocks for dropped masts
    for name in DROP_MASTS:
        text, n = re.subn(
            rf"\s*<signalmastlogic source=\"{re.escape(name)}\">.*?"
            r"</signalmastlogic>",
            "",
            text,
            count=1,
            flags=re.S,
        )
        print(f"  SML source {name}: removed {n}")

    # Remove dest entries pointing at dropped masts (any source)
    for name in DROP_MASTS:
        text, n = re.subn(
            rf"\s*<destinationMast destination=\"{re.escape(name)}\">.*?"
            r"</destinationMast>",
            "",
            text,
            flags=re.S,
        )
        print(f"  SML dest {name}: removed {n}")
    return text


def disable_column_signals(text: str, unique_id: str, label: str) -> str:
    pat = (
        rf"(<ctcCodeButtonData>\s*<UniqueID>{unique_id}</UniqueID>.*?"
        r")(</ctcCodeButtonData>)"
    )

    def repl(m: re.Match) -> str:
        body = m.group(1)
        body = re.sub(r"<SIDI_Enabled>true</SIDI_Enabled>",
                      "<SIDI_Enabled>false</SIDI_Enabled>", body, count=1)
        body = re.sub(r"<SIDL_Enabled>true</SIDL_Enabled>",
                      "<SIDL_Enabled>false</SIDL_Enabled>", body, count=1)
        body = re.sub(r"<TRL_Enabled>true</TRL_Enabled>",
                      "<TRL_Enabled>false</TRL_Enabled>", body, count=1)
        body = re.sub(
            r"<SIDI_LeftRightTrafficSignals>.*?</SIDI_LeftRightTrafficSignals>",
            "<SIDI_LeftRightTrafficSignals />",
            body,
            count=1,
            flags=re.S,
        )
        body = re.sub(
            r"<SIDI_RightLeftTrafficSignals>.*?</SIDI_RightLeftTrafficSignals>",
            "<SIDI_RightLeftTrafficSignals />",
            body,
            count=1,
            flags=re.S,
        )
        body = re.sub(
            r"<TRL_LeftRules>.*?</TRL_LeftRules>",
            "<TRL_LeftRules />",
            body,
            count=1,
            flags=re.S,
        )
        body = re.sub(
            r"<TRL_RightRules>.*?</TRL_RightRules>",
            "<TRL_RightRules />",
            body,
            count=1,
            flags=re.S,
        )
        print(f"  CTC uid {unique_id} ({label}): SIDI/SIDL/TRL off")
        return body + m.group(2)

    out, n = re.subn(pat, repl, text, count=1, flags=re.S)
    if n != 1:
        print(f"  WARN: ctc column uid {unique_id} not found")
    return out


def patch_117_homes(text: str) -> str:
    # Add T6 as 117 westbound home
    old = (
        "<SIDI_RightLeftTrafficSignals>\n"
        "        <signal>West Yard East OS 117b</signal>\n"
        "      </SIDI_RightLeftTrafficSignals>"
    )
    new = (
        "<SIDI_RightLeftTrafficSignals>\n"
        "        <signal>West Yard East OS 117b</signal>\n"
        f"        <signal>{T6}</signal>\n"
        "      </SIDI_RightLeftTrafficSignals>"
    )
    if f"<signal>{T6}</signal>" in text.split("<UniqueID>16</UniqueID>", 1)[-1][:2500]:
        print(f"  CTC 117 RTL: {T6} already listed")
    else:
        if old not in text:
            print("  WARN: 117 RTL block not found")
        else:
            text = text.replace(old, new, 1)
            print(f"  CTC 117 RTL: added {T6}")

    # Add westbound TRL for T6 → Plane OS 102 if missing
    uid16 = re.search(
        r"<ctcCodeButtonData>\s*<UniqueID>16</UniqueID>.*?</ctcCodeButtonData>",
        text,
        re.S,
    )
    if uid16 and "Plane East OS 102" in uid16.group(0).split("<TRL_RightRules>")[0]:
        print("  CTC 117 left TRL: Plane OS 102 already present")
        return text
    text, n = re.subn(
        r"(<UniqueID>16</UniqueID>.*?<TRL_LeftRules>.*?)(</TRL_LeftRules>)",
        rf"\1{TRL_T6_WEST}\2",
        text,
        count=1,
        flags=re.S,
    )
    print(f"  CTC 117 left TRL: added T6→Plane OS 102 ({n})")
    return text


def strip_trl_dest(text: str, dest: str) -> str:
    text, n = re.subn(
        rf"\s*<TRL_TrafficLockingRule>\s*"
        rf"<UserRuleNumber>[^<]*</UserRuleNumber>\s*"
        rf"<RuleEnabled>[^<]*</RuleEnabled>\s*"
        rf"<DestinationSignalOrComment>{re.escape(dest)}</DestinationSignalOrComment>"
        r".*?</TRL_TrafficLockingRule>",
        "",
        text,
        flags=re.S,
    )
    print(f"  CTC TRL dest {dest}: removed {n}")
    return text


def add_local_defaults_logix(text: str) -> str:
    """ACTIVE (data=2) on 116/103/110 lock toggles when CTC reloads."""
    if "IS10:LOCKTOGGLE" in text.split("IX:CTC:REVDEF:C1")[-1][:2000]:
        print("  Logix REVDEF: lock toggles already present")
        return text
    needle = (
        '      <conditionalAction option="1" type="9" systemName="IS29:LEVER" '
        'data="4" delay="0" string="" />'
    )
    extra = (
        '      <conditionalAction option="1" type="9" systemName="IS10:LOCKTOGGLE" '
        'data="2" delay="0" string="" />\n'
        '      <conditionalAction option="1" type="9" systemName="IS12:LOCKTOGGLE" '
        'data="2" delay="0" string="" />\n'
        '      <conditionalAction option="1" type="9" systemName="IS22:LOCKTOGGLE" '
        'data="2" delay="0" string="" />'
    )
    if needle not in text:
        print("  WARN: REVDEF lever actions not found")
        return text
    text = text.replace(needle, needle + "\n" + extra, 1)
    text = text.replace(
        "Set 100/112/114/115 levers Reverse",
        "Set reverse levers + 116/103/110 local",
        1,
    )
    print("  Logix REVDEF: 116/103/110 LOCKTOGGLE → ACTIVE (Local)")
    return text


def strip_signal_levers(text: str) -> str:
    """Remove USS signal lever + L/N/R lamps for columns 10 (116) and 12 (103)."""
    # Multisensor signal levers
    for tip in (
        r",IS10:NGL,IS10:RDGL",
        r"IS12:LDGL,IS12:NGL,",
    ):
        text, n = re.subn(
            rf'\s*<multisensoricon\b[^>]*>\s*<tooltip>{re.escape(tip)}</tooltip>'
            r'.*?</multisensoricon>',
            "",
            text,
            flags=re.S,
        )
        print(f"  GUI signal lever {tip}: removed {n}")

    for sensor in (
        "IS10:NGK", "IS10:RDGK", "IS10:LDGK",
        "IS12:LDGK", "IS12:NGK", "IS12:RDGK",
    ):
        text, n = re.subn(
            rf'\s*<sensoricon sensor="{sensor}"[^>]*>.*?</sensoricon>',
            "",
            text,
            flags=re.S,
        )
        if n:
            print(f"  GUI lamp {sensor}: removed {n}")

    # Lever numbers 10 and 12 (not switch numbers 9/11)
    for num, x in (("10", "428"), ("12", "493")):
        text, n = re.subn(
            rf'\s*<positionablelabel x="{x}" y="470"[^>]*>\s*'
            rf'<tooltip>Text Label</tooltip>\s*'
            rf'<text>{num}</text>.*?</positionablelabel>'
            r'|'
            rf'\s*<positionablelabel x="{x}" y="470"[^>]*text="{num}".*?'
            r'</positionablelabel>',
            "",
            text,
            flags=re.S,
        )
        # GUIObjects uses text= attribute; tables paneleditor may nest <text>
        print(f"  GUI label {num}: removed {n}")

    # Fallback: label with text="10" or "12" at y="470"
    for num in ("10", "12"):
        text, n = re.subn(
            rf'\s*<positionablelabel [^>]*y="470"[^>]*text="{num}"[^>]*>.*?'
            r'</positionablelabel>',
            "",
            text,
            flags=re.S,
        )
        if n:
            print(f"  GUI label {num} (attr): removed {n}")
    return text


def restore_cats_t6(path: Path) -> None:
    txt = path.read_text()
    prefix = "CATS " if "CATS West Yard East Yard T6" in txt else ""
    names = {
        "t6": prefix + T6,
        "n116": prefix + "West Yard North OS 116",
        "n104": prefix + "South Yard East OS 104",
    }

    def drop_sig(name: str, blob: str) -> str:
        pat = (
            rf"\s*<SECSIGNAL>\s*{re.escape(name)}\s*"
            r"<PANELSIGNAL[^>]*>\s*<PHYSIGNAL>single</PHYSIGNAL>\s*</SECSIGNAL>"
        )
        out, n = re.subn(pat, "", blob)
        print(f"  {path.name}: removed {name} ({n})")
        return out

    txt = drop_sig(names["n116"], txt)
    txt = drop_sig(names["n104"], txt)
    txt = drop_sig(names["t6"], txt)

    # Insert T6 on (14,7) RIGHT — east edge of OS 117 on the yard lead
    sec = re.search(r'<SECTION X="14" Y="7">.*?</SECTION>', txt, re.S)
    if not sec:
        print(f"  WARN: {path.name} section (14,7) missing")
        path.write_text(txt)
        return
    body = sec.group(0)
    if names["t6"] in body:
        print(f"  {path.name}: T6 already on (14,7)")
        path.write_text(txt)
        return
    em = re.search(
        r'(<SEC_EDGE EDGE="RIGHT"\s*>)(.*?)(</SEC_EDGE>)',
        body,
        re.S,
    )
    if not em:
        print(f"  WARN: {path.name} (14,7) RIGHT edge missing")
        path.write_text(txt)
        return
    sig = SIG_T6.format(name=names["t6"])
    new_edge = em.group(1) + em.group(2) + sig + "\n      " + em.group(3)
    new_body = body[: em.start()] + new_edge + body[em.end() :]
    txt = txt.replace(body, new_body)
    print(f"  {path.name}: T6 restored at (14,7) RIGHT")
    path.write_text(txt)


def patch_le_file(path: Path, ctc: bool) -> None:
    print(f"\n== {path.relative_to(ROOT)} ==")
    text = path.read_text()
    text = strip_virtual_masts(text)
    text = strip_mast_icons(text)
    text = rebind_layout_turnouts(text)
    text = strip_sml(text)
    if ctc:
        text = disable_column_signals(text, "17", "SW116")
        text = disable_column_signals(text, "18", "SW103")
        text = patch_117_homes(text)
        text = strip_trl_dest(text, "South Yard East OS 104")
        text = strip_trl_dest(text, "West Yard North OS 116")
        text = add_local_defaults_logix(text)
        text = strip_signal_levers(text)
    path.write_text(text)


def main() -> int:
    patch_le_file(TABLES, ctc=True)
    if HART_PROD.is_file():
        patch_le_file(HART_PROD, ctc=False)
    print(f"\n== {GUI.relative_to(ROOT)} ==")
    gui = strip_signal_levers(GUI.read_text())
    GUI.write_text(gui)
    print(f"\n== CATS masters ==")
    restore_cats_t6(CATS_CTC)
    restore_cats_t6(CATS_ABS)
    print("\nDone. Rebuild CATS hold copies next:")
    print("  python3 cats/scripts/build_hart_master_ctc_hold.py")
    print("  python3 cats/scripts/build_hart_master_abs_hold.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
