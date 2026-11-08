// Barn station map as a printed fascia plate for Touch Toggles.
//
// Same plant as ops/station_maps/scripts/render_barn_station_map.py, in sheet inches with y
// down, so the two can be compared directly. Switch 7's dots move to the
// toggle's 3/8 in hole pitch, which pulls Main East up to Y_MAIN below.
//
// Prints face down for a smooth, flush face: the colours are inlays in the first
// layers, one STL per colour, and the back pockets print open with no supports.
//   z 0 .. inlay_t       face: white, black, teal, gold side by side
//   inlay_t .. skin_t    white skin over the toggles, LED holes only
//   skin_t .. total_t    pockets with crush ribs, wire channels to the edge
//
// Pocket, rib, skin and wire-channel method is the one proven on
// toggle_test_sw13.scad; sizes are the caliper measurements in README.md.
//
//   ./docs/benchwork/station_maps_3d/build.sh
//   openscad -D 'part="teal"' -o teal.stl station_map_barn.scad

part = "all";  // all (colour preview) | white | black | teal | gold

/* [Fit: confirm against the frame] */
sheet_w = 203.2;       // 8 in
sheet_h = 127.0;       // 5 in
frame_clearance = 0.5; // total, each axis
plate_r = 3.0;         // corner radius
skin_t = 1.0;          // over the toggles, as in the SW13 test
inlay_t = 0.6;         // three 0.2 layers
hole_clearance = 0.2;

/* [Measured toggles, mm] */
toggle_w = 17.7;
toggle_t = 5.1;
housing_t = 5.8;       // third-light housing
combo_len = 28.6;      // two-light toggle + third light, joined
combo_w = 18.2;
back_gap = 0.2;        // deepest part sits this far below the back, so tape lies flat

/* [Pocket fit, as the SW13 test] */
pocket_clearance = 0.3;  // total, each axis
rib_d = 1.0;
rib_protrude = 0.35;     // into the pocket; 0.2 mm interference a side
lead_in = 1.0;           // rib taper at the back so the toggle starts easily
wire_slot_w = 13.0;      // ribbon is 3.8 wide but its position varies

/* [Touch Toggle, inches, from the spec drawing] */
pitch_in = 0.375;
hole_in = 3 / 16;

/* [Switch 7] */
// Which of the three crossover dots is the separate indicator; the toggle takes
// the other two, so this must be an end dot.
indicator_dot = 2;     // 0 top, 2 bottom

/* [Print limits for a 0.4 nozzle] */
ring_w = 1.3;
track_w = 1.3;
siding_w = 1.1;

$fn = 48;
IN = 25.4;

total_t = skin_t + housing_t + back_gap;
pocket_depth = total_t - skin_t;
pocket_w = toggle_w + pocket_clearance;
RIB_OFFSET = pocket_w / 4;

RUN = 0.5;
RISE = 1.0;
SLOPE_LEN = sqrt(RUN * RUN + RISE * RISE);
UX = RUN / SLOPE_LEN;
UY = RISE / SLOPE_LEN;
SLOPE_DEG = atan2(RUN, RISE);

Y_EH1 = 1.12;
Y_EH2 = 1.68;
Y_EH3 = 2.24;
Y_BARN = 3.20;
Y_MAIN = Y_BARN + 2 * pitch_in * UY;

X_WEST = 0.32;
X_EH = 0.95;
X_EAST = 7.68;

SW13 = [6.92, Y_BARN];
SW9 = [4.55, Y_EH3];
SW7_TOP = [2.05, Y_BARN];
SW7_MID = SW7_TOP + pitch_in * [UX, UY];
SW7_BOT = SW7_TOP + 2 * pitch_in * [UX, UY];
SW7_TOGGLE = indicator_dot == 2 ? (SW7_TOP + SW7_MID) / 2 : (SW7_MID + SW7_BOT) / 2;
SW7_INDICATOR = indicator_dot == 2 ? SW7_BOT : SW7_TOP;

function along(p, dy) = [p[0] + (RUN / RISE) * dy, p[1] + dy];
SW11 = along(SW13, Y_EH3 - Y_BARN);
EH1_JOIN = along(SW13, Y_EH1 - Y_BARN);
EH2_JOIN = along(SW9, Y_EH2 - Y_EH3);

SINGLE_TOGGLES = [SW9, SW11, SW13];
HOLES = concat(SINGLE_TOGGLES, [SW7_TOP, SW7_MID, SW7_BOT]);

// Sheet inches (y down) to centred mm (y up).
function mm(p) = [(p[0] - 4) * IN, (2.5 - p[1]) * IN];

module at(p) { translate(mm(p)) children(); }

module line2(a, b, w) {
  hull() {
    at(a) circle(d = w);
    at(b) circle(d = w);
  }
}

module arrow(p, dir) {
  at(p) polygon([[0, 0], [-dir * 3.6, 1.9], [-dir * 3.6, -1.9]]);
}

module label(p, s, size = 3.6, halign = "center", font = "Arial:style=Bold") {
  at(p) text(s, size = size, font = font, halign = halign, valign = "baseline");
}

module holes2d() {
  for (p = HOLES) at(p) circle(d = hole_in * IN + hole_clearance);
}

module rings2d() {
  for (p = HOLES) at(p) circle(d = hole_in * IN + hole_clearance + 2 * ring_w);
}

// ---- Pockets, ribs and wire channels (method from toggle_test_sw13.scad) ----
//
// Each toggle has a local frame at its centre, x along the LED row and the
// ribbon leaving through the local -y wall. A channel runs from that wall
// straight out through the plate edge. The single toggles share one frame
// turned to point their channel at the nearest clear edge; Switch 7 is turned
// along the crossover.

// Single one-light toggles: [centre, turn]. The turn points the local -y wall
// (the ribbon side) along the channel: 0 is down the sheet, -90 is west.
SINGLES = [
  [SW9, 0],
  [SW11, -90],
  [SW13, -90],
];

// Switch 7 frame: x runs from the toggle towards the third light.
SW7_ANGLE = indicator_dot == 2 ? atan2(-UY, UX) : atan2(UY, -UX);
SW7_X_MIN = -(toggle_w + pocket_clearance) / 2;
SW7_X_MAX = combo_len - toggle_w / 2 + pocket_clearance / 2;
SW7_LED_X = 1.5 * pitch_in * IN;
HOUSING_W = combo_w + pocket_clearance;
HOUSING_SLOT_W = 9.0;
SW7_STUB = 26;         // channel from the Switch 7 pocket before it joins the bus

module local(p, ang) { at(p) rotate(ang) children(); }

module single_pocket2d() {
  square(pocket_w, center = true);
}

module sw7_pocket2d() {
  translate([SW7_X_MIN, -pocket_w / 2]) square([pocket_w, pocket_w]);
  translate([SW7_X_MAX - HOUSING_W, -HOUSING_W / 2]) square([HOUSING_W, HOUSING_W]);
  // One stub for the toggle ribbon and the third light's wire.
  translate([-wire_slot_w / 2, -SW7_STUB])
    square([SW7_LED_X + HOUSING_SLOT_W / 2 + wire_slot_w / 2, SW7_STUB]);
}

// ---- Wiring: every channel joins one trunk that leaves through the bottom edge ----
//
// SW9's channel runs straight down as the trunk. SW13 and SW11 run west into it.
// Switch 7's stub drops to a bus under its pocket, which joins the trunk from the
// left. All wires leave together through one notch, so one connector serves.
function mm_pt(p, ang, q) = [p[0] + q[0] * cos(ang) - q[1] * sin(ang), p[1] + q[0] * sin(ang) + q[1] * cos(ang)];

TRUNK_X = mm(SW9)[0];
BUS_Y = -53;
EXIT_Y = -sheet_h;
SW7_JOIN = mm_pt(mm(SW7_TOGGLE), SW7_ANGLE, [SW7_LED_X / 2, -SW7_STUB / 2]);
SW11_BEND_X = 33;      // clear of SW9's pocket

CHANNELS = [
  [mm(SW9), [TRUNK_X, EXIT_Y]],
  [mm(SW13), [TRUNK_X, mm(SW13)[1]]],
  [mm(SW11), [SW11_BEND_X, mm(SW11)[1]], [SW11_BEND_X, mm(SW13)[1]]],
  [SW7_JOIN, [SW7_JOIN[0], BUS_Y], [TRUNK_X, BUS_Y]],
];

module channel2d(pts) {
  for (i = [0 : len(pts) - 2]) hull() {
    translate(pts[i]) circle(d = wire_slot_w);
    translate(pts[i + 1]) circle(d = wire_slot_w);
  }
}

module pockets2d() {
  for (s = SINGLES) local(s[0], s[1]) single_pocket2d();
  local(SW7_TOGGLE, SW7_ANGLE) sw7_pocket2d();
  for (c = CHANNELS) channel2d(c);
}

// A rib at p standing rib_protrude proud of the wall whose inward normal is n.
module rib(p, n) {
  c = p + n * (rib_protrude - rib_d / 2);
  translate([c[0], c[1], skin_t]) hull() {
    cylinder(d = rib_d, h = pocket_depth - lead_in);
    translate(-n * rib_protrude) cylinder(d = rib_d, h = pocket_depth);
  }
}

// Left, right and top walls, two ribs each; the bottom wall is where the channel leaves.
SINGLE_RIBS = [
  for (s = [-1, 1]) [[-pocket_w / 2, s * RIB_OFFSET], [1, 0]],
  for (s = [-1, 1]) [[pocket_w / 2, s * RIB_OFFSET], [-1, 0]],
  for (s = [-1, 1]) [[s * RIB_OFFSET, pocket_w / 2], [0, -1]],
];

// Switch 7: both end walls, plus one on the top wall by the toggle and one by
// the housing. The side walls hold the toggle and housing at their own width.
SW7_RIBS = [
  for (s = [-1, 1]) [[SW7_X_MIN, s * RIB_OFFSET], [1, 0]],
  for (s = [-1, 1]) [[SW7_X_MAX, s * RIB_OFFSET], [-1, 0]],
  [[-RIB_OFFSET, pocket_w / 2], [0, -1]],
  [[SW7_LED_X, HOUSING_W / 2], [0, -1]],
];

module ribs3d() {
  for (s = SINGLES) local(s[0], s[1]) for (r = SINGLE_RIBS) rib(r[0], r[1]);
  local(SW7_TOGGLE, SW7_ANGLE) for (r = SW7_RIBS) rib(r[0], r[1]);
}

PILLS = [
  [[1.86, Y_BARN + pitch_in * UY], "7"],
  [[4.92, 2.05], "9"],
  [[6.80, 2.05], "11"],
  [[6.50, 3.00], "13"],
];

module pill_shape(p, s) {
  w = len(s) > 1 ? 9.6 : 7.2;
  at(p) offset(r = 1.2) square([w - 2.4, 4.8], center = true);
}

module pill_digits(p, s) {
  at(p) text(s, size = 4.2, font = "Arial:style=Bold", halign = "center", valign = "center");
}

module pills_solid2d() {
  for (x = PILLS) pill_shape(x[0], x[1]);
}

module pills2d() {
  for (x = PILLS) difference() {
    pill_shape(x[0], x[1]);
    pill_digits(x[0], x[1]);
  }
}

COMPASS = [0.82, 4.52];
COMPASS_R = 7;

module compass_ring2d() {
  at(COMPASS) difference() {
    circle(r = COMPASS_R);
    circle(r = COMPASS_R - 1.1);
  }
}

module needle_north2d() {
  at(COMPASS) polygon([[0, COMPASS_R - 1.8], [1.5, 0], [-1.5, 0]]);
}

module needle_south2d() {
  at(COMPASS) polygon([[0, -(COMPASS_R - 1.8)], [1.5, 0], [-1.5, 0]]);
}

module ink2d() {
  // Horizontals
  line2([X_WEST, Y_BARN], [X_EAST, Y_BARN], track_w);
  line2([X_WEST, Y_MAIN], [X_EAST, Y_MAIN], track_w);
  line2([X_EH, Y_EH1], EH1_JOIN, siding_w);
  line2([X_EH, Y_EH2], EH2_JOIN, siding_w);
  line2([X_EH, Y_EH3], SW11, siding_w);

  // One slope: 7 xover, 13 to EH-1, EH-2 to 9
  line2(SW7_TOP, SW7_BOT, track_w);
  line2(SW13, EH1_JOIN, siding_w);
  line2(EH2_JOIN, SW9, siding_w);

  arrow([X_WEST - 0.06, Y_BARN], -1);
  arrow([X_WEST - 0.06, Y_MAIN], -1);
  arrow([X_EAST + 0.06, Y_BARN], 1);
  arrow([X_EAST + 0.06, Y_MAIN], 1);

  // No ring round each LED hole: thin closed loops on the first layer would not stick.

  at([4, 0.52]) text("BARN", size = 10, font = "Arial Black", halign = "center");

  gap = 0.07;
  label([SW7_TOP[0] - 0.62, Y_BARN - gap], "Scale");
  label([4.55, Y_BARN - gap], "Barn");
  label([4.55, Y_MAIN - gap], "Main East");
  label([2.35, Y_EH1 - gap], "EH-1");
  label([2.35, Y_EH2 - gap], "EH-2");
  label([2.35, Y_EH3 - gap], "EH-3");

  label([0.95, (Y_BARN + Y_MAIN) / 2 + 0.05], "to Plane", 3.0);
  label([X_EAST - 0.16, Y_BARN + 0.33], "to South Yard", 3.0, "right");
  label([X_EAST - 0.16, Y_MAIN - gap], "to East End", 3.0, "right");

  at(COMPASS) translate([0, COMPASS_R + 1.2])
    text("N", size = 3.2, font = "Arial:style=Bold", halign = "center");
}

module outline2d() {
  offset(r = plate_r)
    square([sheet_w - frame_clearance - 2 * plate_r, sheet_h - frame_clearance - 2 * plate_r], center = true);
}

module black2d() {
  difference() {
    ink2d();
    pills_solid2d();
    holes2d();
  }
}

module teal2d() {
  pills2d();
  needle_south2d();
}

// The ring keeps gold over the slicer's 9 mm^3 limit, below which an STL is taken for inches.
module gold2d() {
  compass_ring2d();
  needle_north2d();
}

module white_part() {
  linear_extrude(inlay_t) difference() {
    outline2d();
    black2d();
    teal2d();
    gold2d();
    holes2d();
  }
  translate([0, 0, inlay_t]) linear_extrude(skin_t - inlay_t) difference() {
    outline2d();
    holes2d();
  }
  translate([0, 0, skin_t]) linear_extrude(pocket_depth) difference() {
    outline2d();
    pockets2d();
    holes2d();
  }
  // Clip the ribs to the plate so none pokes out through a channel.
  intersection() {
    ribs3d();
    linear_extrude(total_t) outline2d();
  }
}

// Turn the face onto the bed so the map reads correctly once picked up.
module face_down() {
  mirror([1, 0, 0]) children();
}

face_down() {
  if (part == "white") white_part();
  else if (part == "black") linear_extrude(inlay_t) black2d();
  else if (part == "teal") linear_extrude(inlay_t) teal2d();
  else if (part == "gold") linear_extrude(inlay_t) gold2d();
  else {
    color("white") white_part();
    color([0.08, 0.08, 0.08]) linear_extrude(inlay_t) black2d();
    color([0.06, 0.28, 0.38]) linear_extrude(inlay_t) teal2d();
    color([0.79, 0.60, 0.16]) linear_extrude(inlay_t) gold2d();
  }
}
