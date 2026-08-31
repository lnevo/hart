#!/usr/bin/env python3
"""Generate HART review Cursor canvases (.canvas.tsx) for D2 device map and industry matrix."""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from lib.load_hart_devices import (  # noqa: E402
    GRAMMAR_ROWS,
    KIND_OPTIONS,
    export_legacy_csv,
    load_devices,
    load_legacy_rows,
)

CON = SCRIPTS.parent
CANVAS_DIR = Path.home() / ".cursor/projects/Users-lnevo-hart/canvases"
DEVICE_OUT = CANVAS_DIR / "hart-device-map-d2-review.canvas.tsx"
LEGACY_OUT = CANVAS_DIR / "hart-device-map-d2-legacy.canvas.tsx"
INDUSTRY_OUT = CANVAS_DIR / "hart-industry-matrix.canvas.tsx"
XLSX = CON / "external/hart-ops/industries/HART_Industry_Routing_Matrix.xlsx"

CANVAS_HEADER = """import {
  Callout,
  Code,
  Grid,
  H1,
  H2,
  H3,
  Row,
  Select,
  Stack,
  Stat,
  Table,
  Text,
  TextInput,
  useCanvasState,
} from "cursor/canvas";
"""


def ts_string(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def jsx_static_table(
    headers: list[str],
    rows: list[list[str]],
    *,
    sticky: bool = False,
    max_height: int | None = None,
) -> str:
    """Emit a Table with inline string rows (valid JSX, no f-string brace bugs)."""
    hdr = ", ".join(ts_string(h) for h in headers)
    row_blocks = []
    for row in rows:
        cells = ", ".join(ts_string(c) for c in row)
        row_blocks.append(f"          [{cells}],")
    rows_js = "\n".join(row_blocks)
    props = ["striped"]
    if sticky:
        props.insert(0, "stickyHeader")
    style = f'\n        style={{{{ maxHeight: {max_height} }}}}' if max_height else ""
    props_js = "\n        ".join(props)
    return f"""      <Table
        headers={{[{hdr}]}}
        rows={{[
{rows_js}
        ]}}
        {props_js}{style}
      />"""


def emit_device_canvas(devices: list[dict], source: str) -> str:
    device_lines = ",\n".join(
        "  "
        + json.dumps(
            {
                "kind": d["kind"],
                "unpacked": d.get("unpacked", ""),
                "dcc": d.get("dcc", ""),
                "mqtt": d.get("mqtt", ""),
                "systemName": d["systemName"],
                "userName": d["userName"],
                "comment": d.get("comment", ""),
            },
            ensure_ascii=False,
        )
        for d in devices
    )
    kind_opts = ",\n".join(
        f"  {{ value: {ts_string(v)}, label: {ts_string(l)} }}" for v, l in KIND_OPTIONS
    )
    grammar = jsx_static_table(
        ["Kind", "Unpacked", "DCC", "MQTT", "systemName", "userName", "comment"],
        GRAMMAR_ROWS,
    )

    return f"""{CANVAS_HEADER}
type Kind =
  | "Turnout"
  | "LCC turnout"
  | "Occupancy"
  | "Occupancy (unused)"
  | "OS block"
  | "Block"
  | "Feedback"
  | "Feedback (unused)"
  | "Signal head"
  | "Signal mast"
  | "Virtual mast";

type Device = {{
  kind: Kind;
  unpacked: string;
  dcc: string;
  mqtt: string;
  systemName: string;
  userName: string;
  comment: string;
}};

const DEVICES: Device[] = [
{device_lines}
];

const KIND_OPTIONS = [
{kind_opts}
];

function matchesKind(kind: Kind, filter: string): boolean {{
  if (filter === "all") return true;
  if (filter === "Occupancy") return kind.startsWith("Occupancy");
  if (filter === "Block") return kind === "Block";
  if (filter === "Feedback") return kind.startsWith("Feedback");
  return kind === filter;
}}

function count(prefix: string): number {{
  return DEVICES.filter((d) => d.kind.startsWith(prefix)).length;
}}

export default function HartDeviceMapD2Review() {{
  const [kind, setKind] = useCanvasState("kind", "all");
  const [q, setQ] = useCanvasState("q", "");
  const query = q.trim().toLowerCase();

  const rows = DEVICES.filter((d) => {{
    if (!matchesKind(d.kind, kind)) return false;
    if (!query) return true;
    return [
      d.unpacked,
      d.dcc,
      d.mqtt,
      d.kind,
      d.systemName,
      d.userName,
      d.comment,
    ].some((v) => v.toLowerCase().includes(query));
  }});

  return (
    <Stack gap={{24}} style={{{{ padding: 24, maxWidth: 1280 }}}}>
      <Stack gap={{8}}>
        <H1>HART device map — proposed JMRI names</H1>
        <Text tone="secondary">
          Live beans from jmri/layouts/hart/output/tables.xml. Comment format is
          proposed — review here before D2 promotion. Source: {json.dumps(source)}.
          Historical aliases and merged-map notes:
          consolidation/sor/names/d2_legacy_match.csv
          (separate legacy canvas).
        </Text>
      </Stack>

      <Callout tone="info" title="Address grammar">
        MQTT turnout: Node: 4 Turnout: 0 | DCC: 100 | OU: 1 Ports: 1,2. LCC turnout: same minus DCC.
        Occupancy: Node: 4 Block: 1. Feedback: Node: 4 Sensor: 3 | IN: 1 Ports: 1. Signal head:
        Node: 4 Signal: 6 | OU: 3 Ports: 1,2,3 (spill uses | between OU groups). Mast and OS/track-block
        comments stay the control-point name (plus protected switch on masts).
      </Callout>

      <Grid columns={{4}} gap={{12}}>
        <Stat value={{String(DEVICES.filter((d) => d.kind === "Turnout").length)}} label="Turnouts" />
        <Stat value={{String(DEVICES.filter((d) => d.kind === "LCC turnout").length)}} label="LCC turnouts" />
        <Stat value={{String(count("Occupancy"))}} label="Occupancy" />
        <Stat value={{String(DEVICES.filter((d) => d.kind === "OS block").length)}} label="OS blocks" />
        <Stat value={{String(DEVICES.filter((d) => d.kind === "Block").length)}} label="Track blocks" />
        <Stat value={{String(count("Feedback"))}} label="Feedback" />
        <Stat value={{String(count("Signal head"))}} label="Heads" />
        <Stat value={{String(count("Signal mast"))}} label="Masts" />
        <Stat value={{String(count("Virtual mast"))}} label="Virtual masts" />
      </Grid>

      <H2>Grammar</H2>
{grammar}

      <H2>All devices</H2>
      <H3>
        {{rows.length}} of {{DEVICES.length}} shown
      </H3>
      <Row gap={{12}} align="center">
        <Select
          value={{kind}}
          onChange={{setKind}}
          options={{KIND_OPTIONS}}
          style={{{{ minWidth: 220 }}}}
        />
        <TextInput
          value={{q}}
          onChange={{setQ}}
          placeholder="Filter unpacked, DCC, MQTT, name…"
          type="search"
          style={{{{ flex: 1 }}}}
        />
      </Row>
      <Table
        stickyHeader
        striped
        headers={{[
          "Unpacked",
          "DCC",
          "MQTT",
          "Kind",
          "systemName",
          "userName",
          "comment",
        ]}}
        rows={{rows.map((d) => [
          d.unpacked || "—",
          d.dcc || "—",
          d.mqtt || "—",
          d.kind,
          <Code>{{d.systemName}}</Code>,
          d.userName,
          d.comment || "—",
        ])}}
        style={{{{ maxHeight: 900 }}}}
      />
    </Stack>
  );
}}
"""


def emit_legacy_canvas(rows: list[dict[str, str]], csv_rel: str) -> str:
    legacy_n = len(rows)
    hist_n = sum(1 for r in rows if "historical alias" in r["notes"].lower())
    legacy_lines = ",\n".join(
        "  "
        + json.dumps(
            {
                "layer": r["layer"],
                "hardware": r["hardware"],
                "current": r["current"],
                "proposed": r["proposed"],
                "cp": r.get("cp", ""),
                "notes": r["notes"],
            },
            ensure_ascii=False,
        )
        for r in rows
    )

    return f"""{CANVAS_HEADER}
type LegacyRow = {{
  layer: string;
  hardware: string;
  current: string;
  proposed: string;
  cp: string;
  notes: string;
}};

const LEGACY: LegacyRow[] = [
{legacy_lines}
];

const LAYER_OPTIONS = [
  {{ value: "all", label: "All layers" }},
  {{ value: "turnout", label: "Turnouts" }},
  {{ value: "block", label: "Blocks" }},
  {{ value: "head", label: "Heads" }},
  {{ value: "mast", label: "Masts" }},
  {{ value: "feedback", label: "Feedback" }},
];

export default function HartDeviceMapD2Legacy() {{
  const [layer, setLayer] = useCanvasState("layer", "all");
  const [histOnly, setHistOnly] = useCanvasState("histOnly", "0");
  const [q, setQ] = useCanvasState("q", "");
  const query = q.trim().toLowerCase();
  const onlyHist = histOnly === "1";

  const rows = LEGACY.filter((r) => {{
    if (layer !== "all" && r.layer !== layer) return false;
    if (onlyHist && !r.notes.toLowerCase().includes("historical alias")) return false;
    if (!query) return true;
    return [
      r.layer,
      r.hardware,
      r.current,
      r.proposed,
      r.cp,
      r.notes,
    ].some((v) => v.toLowerCase().includes(query));
  }});

  return (
    <Stack gap={{24}} style={{{{ padding: 24, maxWidth: 1280 }}}}>
      <Stack gap={{8}}>
        <H1>D2 legacy match — aliases &amp; notes</H1>
        <Text tone="secondary">
          Rows from public_name_map_merged.csv with non-empty notes ({legacy_n} total;
          {hist_n} historical aliases). Match on hardware ↔ systemName.
          CSV: {json.dumps(csv_rel)}.
        </Text>
      </Stack>

      <Callout tone="info" title="Not in the main device map">
        Use this table when reconciling CTC renames, block_display merges, or alias rows.
        The primary review canvas shows live beans only — same columns as hart-device-map.
      </Callout>

      <Grid columns={{4}} gap={{12}}>
        <Stat value={{String(LEGACY.length)}} label="Note rows" />
        <Stat value={{String({hist_n})}} label="Historical alias" />
        <Stat value={{String(LEGACY.filter((r) => r.layer === "turnout").length)}} label="Turnout notes" />
        <Stat value={{String(LEGACY.filter((r) => r.layer === "block").length)}} label="Block notes" />
      </Grid>

      <H2>All legacy rows</H2>
      <H3>{{rows.length}} of {{LEGACY.length}} shown</H3>
      <Row gap={{12}} align="center">
        <Select value={{layer}} onChange={{setLayer}} options={{LAYER_OPTIONS}} style={{{{ minWidth: 180 }}}} />
        <Select
          value={{histOnly}}
          onChange={{setHistOnly}}
          options={{[
            {{ value: "0", label: "All notes" }},
            {{ value: "1", label: "Historical alias only" }},
          ]}}
          style={{{{ minWidth: 200 }}}}
        />
        <TextInput
          value={{q}}
          onChange={{setQ}}
          placeholder="Filter hardware, current, proposed, notes…"
          type="search"
          style={{{{ flex: 1 }}}}
        />
      </Row>
      <Table
        stickyHeader
        striped
        headers={{[
          "layer",
          "hardware",
          "current",
          "proposed",
          "cp",
          "notes",
        ]}}
        rows={{rows.map((r) => [
          r.layer,
          <Code>{{r.hardware}}</Code>,
          r.current,
          r.proposed,
          r.cp || "—",
          r.notes,
        ])}}
        style={{{{ maxHeight: 900 }}}}
      />
    </Stack>
  );
}}
"""


def sheet_data(wb, name: str) -> list[dict[str, str]]:
    ws = wb[name]
    raw = list(ws.iter_rows(values_only=True))
    headers = [str(c or "").strip() for c in raw[0]]
    out: list[dict[str, str]] = []
    for row in raw[1:]:
        if not any(row):
            continue
        cells = [str(c or "").strip() for c in row]
        out.append(dict(zip(headers, cells)))
    return out


def emit_industry_canvas(lanes: list[dict], interchange: list[dict]) -> str:
    lane_lines = ",\n".join(
        "  "
        + json.dumps(
            {
                "industry": r.get("Industry", ""),
                "flow": r.get("Flow", ""),
                "commodity": r.get("Commodity / Product", ""),
                "party": r.get("Supplier / Customer", ""),
                "region": r.get("Region", ""),
                "foreign": r.get("Foreign Railroad", ""),
                "interchange": r.get("Interchange", ""),
                "carType": r.get("Car Type", ""),
            },
            ensure_ascii=False,
        )
        for r in lanes
    )
    ix_lines = ",\n".join(
        "  "
        + json.dumps(
            {
                "interchange": r.get("Interchange", ""),
                "location": r.get("Location", ""),
                "foreign": r.get("Foreign Railroads", ""),
                "serving": r.get("Serving Railroad", ""),
                "industries": r.get("Industries Served", ""),
            },
            ensure_ascii=False,
        )
        for r in interchange
    )
    in_n = sum(1 for r in lanes if r.get("Flow") == "IN")
    out_n = sum(1 for r in lanes if r.get("Flow") == "OUT")
    industries = len({r.get("Industry", "") for r in lanes if r.get("Industry")})

    grammar = jsx_static_table(
        [
            "Industry",
            "Flow",
            "Commodity / Product",
            "Supplier / Customer",
            "Region",
            "Foreign Railroad",
            "Interchange",
            "Car Type",
        ],
        [
            [
                "Aristech Chemical",
                "IN",
                "Petrochemical feedstocks",
                "Dow Chemical (Midland, MI)",
                "Midland, MI",
                "NS",
                "NS Interchange",
                "Tank Car",
            ],
            [
                "US Steel",
                "OUT",
                "Steel coils",
                "Regional customers",
                "Local",
                "—",
                "—",
                "Gondola",
            ],
        ],
    )

    return f"""{CANVAS_HEADER}
type Lane = {{
  industry: string;
  flow: string;
  commodity: string;
  party: string;
  region: string;
  foreign: string;
  interchange: string;
  carType: string;
}};

type InterchangeRow = {{
  interchange: string;
  location: string;
  foreign: string;
  serving: string;
  industries: string;
}};

const LANES: Lane[] = [
{lane_lines}
];

const INTERCHANGE: InterchangeRow[] = [
{ix_lines}
];

const FLOW_OPTIONS = [
  {{ value: "all", label: "All lanes" }},
  {{ value: "IN", label: "IN flows" }},
  {{ value: "OUT", label: "OUT flows" }},
  {{ value: "interchange", label: "Interchange matrix" }},
];

export default function HartIndustryMatrixReview() {{
  const [flow, setFlow] = useCanvasState("flow", "all");
  const [q, setQ] = useCanvasState("q", "");
  const query = q.trim().toLowerCase();

  const laneRows = LANES.filter((r) => {{
    if (flow !== "all" && flow !== "interchange" && r.flow !== flow) return false;
    if (flow === "interchange") return false;
    if (!query) return true;
    return [
      r.industry,
      r.flow,
      r.commodity,
      r.party,
      r.region,
      r.foreign,
      r.interchange,
      r.carType,
    ].some((v) => v.toLowerCase().includes(query));
  }});

  const ixRows = INTERCHANGE.filter((r) => {{
    if (flow !== "all" && flow !== "interchange") return false;
    if (flow === "IN" || flow === "OUT") return false;
    if (!query) return true;
    return [
      r.interchange,
      r.location,
      r.foreign,
      r.serving,
      r.industries,
    ].some((v) => v.toLowerCase().includes(query));
  }});

  const shown =
    flow === "interchange"
      ? ixRows.length
      : flow === "all"
        ? laneRows.length + ixRows.length
        : laneRows.length;
  const total = LANES.length + INTERCHANGE.length;

  return (
    <Stack gap={{24}} style={{{{ padding: 24, maxWidth: 1280 }}}}>
      <Stack gap={{8}}>
        <H1>Industry routing matrix — review</H1>
        <Text tone="secondary">
          HART_Industry_Routing_Matrix.xlsx (hart-ops). Cross-check lane changes with
          HART_Spot_Waybills.csv and spot assignments before promotion.
        </Text>
      </Stack>

      <Callout tone="info" title="Lane grammar">
        Each row is one supplier/customer lane: Industry + IN/OUT flow + commodity + party + region.
        Interchange rows map foreign railroad handoffs. When a lane changes, regenerate spot waybills
        and validate STS seed consistency.
      </Callout>

      <Grid columns={{4}} gap={{12}}>
        <Stat value={{String(LANES.length)}} label="HART lanes" />
        <Stat value={{String({in_n})}} label="IN flows" />
        <Stat value={{String({out_n})}} label="OUT flows" />
        <Stat value={{String({industries})}} label="Industries" />
        <Stat value={{String(INTERCHANGE.length)}} label="Interchange rows" />
      </Grid>

      <H2>Grammar</H2>
{grammar}

      <H2>All lanes</H2>
      <H3>
        {{shown}} of {{total}} shown
      </H3>
      <Row gap={{12}} align="center">
        <Select
          value={{flow}}
          onChange={{setFlow}}
          options={{FLOW_OPTIONS}}
          style={{{{ minWidth: 220 }}}}
        />
        <TextInput
          value={{q}}
          onChange={{setQ}}
          placeholder="Filter industry, commodity, car type…"
          type="search"
          style={{{{ flex: 1 }}}}
        />
      </Row>

      {{flow !== "interchange" && (
        <Table
          stickyHeader
          striped
          headers={{[
            "Industry",
            "Flow",
            "Commodity / Product",
            "Supplier / Customer",
            "Region",
            "Foreign Railroad",
            "Interchange",
            "Car Type",
          ]}}
          rows={{laneRows.map((r) => [
            r.industry,
            r.flow,
            r.commodity,
            r.party,
            r.region,
            r.foreign || "—",
            r.interchange || "—",
            r.carType,
          ])}}
          style={{{{ maxHeight: 600 }}}}
        />
      )}}

      {{(flow === "all" || flow === "interchange") && (
        <>
          <H2>Interchange matrix</H2>
          <Table
            stickyHeader
            striped
            headers={{[
              "Interchange",
              "Location",
              "Foreign Railroads",
              "Serving Railroad",
              "Industries Served",
            ]}}
            rows={{ixRows.map((r) => [
              r.interchange,
              r.location,
              r.foreign,
              r.serving,
              r.industries,
            ])}}
          />
        </>
      )}}
    </Stack>
  );
}}
"""


def main() -> int:
    CANVAS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        devices, source = load_devices()
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1

    # Main review: live beans only (matches hart-device-map.canvas.tsx)
    DEVICE_OUT.write_text(emit_device_canvas(devices, source), encoding="utf-8")
    print(f"Wrote {DEVICE_OUT} ({len(devices)} devices)")

    legacy = load_legacy_rows()
    csv_path = export_legacy_csv(legacy)
    LEGACY_OUT.write_text(
        emit_legacy_canvas(legacy, "consolidation/sor/names/d2_legacy_match.csv"),
        encoding="utf-8",
    )
    print(f"Wrote {LEGACY_OUT} ({len(legacy)} legacy rows)")
    print(f"Wrote {csv_path}")

    try:
        import openpyxl
    except ImportError:
        print("openpyxl required for industry canvas", file=sys.stderr)
        return 1
    if not XLSX.is_file():
        print(f"MISSING {XLSX}", file=sys.stderr)
        return 1
    wb = openpyxl.load_workbook(XLSX, read_only=True)
    lanes = sheet_data(wb, "Industry Routing Matrix")
    interchange = sheet_data(wb, "Interchange_Matrix")
    wb.close()
    INDUSTRY_OUT.write_text(emit_industry_canvas(lanes, interchange), encoding="utf-8")
    print(f"Wrote {INDUSTRY_OUT} ({len(lanes)} lanes, {len(interchange)} interchange)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
