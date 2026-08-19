#!/usr/bin/env python3
"""Sync the Barn interlocking signal changes into the CATS master panels.

Mirrors the JMRI changes:
- West Yard East Yard T6 (westbound dwarf) moved from the 116-117 boundary
  (grid 14,7 RIGHT) to east of Switch 103 (grid 21,7 RIGHT).
- New dwarf West Yard North OS 116 on 116's north leg (grid 18,7 TOP).
- New dwarf South Yard East OS 104 on the ladder below Switch 103
  (grid 21,7 BOTTOM), mirroring East End South OS 110 at (31,7).

Apply to HART_Master.xml and HART_Master_ABS.xml, then rerun
build_hart_master_ctc_hold.py and build_hart_master_abs_hold.py.
"""
import re
import sys

SIG = """<SECSIGNAL>
          {name}
          <PANELSIGNAL SIGLOCATION="{loc}" SIGORIENT="{orient}" SIGPANTYPE="LAMP1" />
          <PHYSIGNAL>single</PHYSIGNAL>
        </SECSIGNAL>"""


def edit(path):
    txt = open(path).read()
    # ABS masters use CATS-internal signals with a "CATS " name prefix
    prefix = "CATS " if ("CATS West Yard East Yard T6" in txt) else ""

    # 1. remove the old Yard T6 signal at (14,7)
    pat = re.compile(r'\s*<SECSIGNAL>\s*%sWest Yard East Yard T6\s*<PANELSIGNAL[^>]*>\s*<PHYSIGNAL>single</PHYSIGNAL>\s*</SECSIGNAL>' % prefix)
    txt, n = pat.subn('', txt)
    assert n == 1, "%s: Yard T6 signal removals=%d" % (path, n)

    # helper: insert a signal at the end of a given edge of a given section
    def insert(section_xy, edge, sig):
        x, y = section_xy
        sec = re.search(r'<SECTION X="%d" Y="%d">.*?</SECTION>' % (x, y), txt, re.S)
        assert sec, "section (%d,%d) not found" % (x, y)
        body = sec.group(0)
        em = re.search(r'(<SEC_EDGE EDGE="%s"\s*>)(.*?)(</SEC_EDGE>)' % edge, body, re.S)
        assert em, "(%d,%d) %s edge not found or self-closing" % (x, y, edge)
        new_edge = em.group(1) + em.group(2) + "        " + sig + "\n      " + em.group(3)
        new_body = body[:em.start()] + new_edge + body[em.end():]
        return txt.replace(body, new_body)

    txt = insert((21, 7), "RIGHT",
                 SIG.format(name=prefix + "West Yard East Yard T6", loc="LOWRIGHT", orient="LEFT"))
    txt = insert((18, 7), "TOP",
                 SIG.format(name=prefix + "West Yard North OS 116", loc="RIGHTLOW", orient="BOTTOM"))
    txt = insert((21, 7), "BOTTOM",
                 SIG.format(name=prefix + "South Yard East OS 104", loc="LEFTUP", orient="TOP"))

    open(path, "w").write(txt)
    print("%s: 1 signal moved, 2 added (prefix=%r)" % (path, prefix))


if __name__ == "__main__":
    for p in sys.argv[1:]:
        edit(p)
