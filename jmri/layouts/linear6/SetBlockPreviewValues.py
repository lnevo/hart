# MANUAL: Scripting -> Run Script... after panel is fully loaded.
# Or: python/jython from PanelPro once labels are visible.
import jmri

VALUES = {
  "IB1": "SW116",
  "IB15": "T6",
  "IB18": "SW119",
  "IB19": "SW118",
  "IB20": "T9",
  "IB21": "T10",
  "IB22": "T11",
  "IB3": "T1",
  "IB6": "SW117b",
  "IB8": "SW117",
  "IB:AUTO:0001": "9602",
  "IB:AUTO:0003": "MW",
  "IB:AUTO:0005": "B100",
  "IB:AUTO:0007": "YT5",
  "IB:AUTO:0008": "YT4",
  "IB:AUTO:0010": "MKR",
  "IB:AUTO:0012": "YT1",
  "IB:AUTO:0016": "YT2",
  "IB:AUTO:0017": "EL",
  "IB:AUTO:0020": "WYT1",
  "IB:AUTO:0022": "WYT2",
  "IB:AUTO:0026": "YT3",
  "IB:AUTO:0030": "SW112",
  "IB:AUTO:0031": "SW102",
  "IB:AUTO:0032": "SW114",
  "IB:AUTO:0033": "SW100",
  "IB:AUTO:0034": "SW111a",
  "IB:AUTO:0035": "SW101",
  "IB:AUTO:0036": "SW107",
  "IB:AUTO:0037": "SW108",
  "IB:AUTO:0038": "SW106",
  "IB:AUTO:0039": "SW111b",
  "IB:AUTO:0040": "SW115",
  "IB:AUTO:0041": "SW103",
  "IB:AUTO:0042": "SW110",
  "IB:AUTO:0043": "SW109",
  "IB:AUTO:0044": "SW104",
  "IB:AUTO:0045": "SW105",
  "IB:AUTO:0046": "SW113a",
  "IB:AUTO:0047": "SW113b",
  "IB:AUTO:0048": "MKP",
  "IB:AUTO:0050": "WME",
  "IB:AUTO:0051": "EME"
}

bm = jmri.InstanceManager.getDefault(jmri.BlockManager)
n = 0
missing = 0
for sn, val in VALUES.items():
    b = bm.getBySystemName(sn)
    if b is None:
        b = bm.getBlock(sn)
    if b is None:
        missing += 1
        continue
    b.setValue(val)
    n += 1
print("SetBlockPreviewValues: set %d (missing %d)" % (n, missing))
