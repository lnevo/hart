// Barn station map as a printed fascia plate for Touch Toggles.
//
// Same plant as cats/scripts/render_barn_station_map.py, in sheet inches with y
// down, so the two can be compared directly. Switch 7's dots move to the
// toggle's 3/8 in hole pitch, which pulls Main East up to Y_MAIN below.
//
// Prints face down for a smooth, flush face: the colours are inlays in the first
// layers, one STL per colour, and the back pockets print open with no supports.
//   z 0 .. inlay_t       face: white, black, teal, gold side by side
//   inlay_t .. total_t   white body, pockets open at total_t
//
//   ./cats/station_maps_3d/build.sh
//   openscad -D 'part="teal"' -o teal.stl station_map_barn.scad

part = "all";  // all (colour preview) | white | black | teal | gold

/* [Fit: confirm against the frame and a real toggle] */
sheet_w = 203.2;       // 8 in
sheet_h = 127.0;       // 5 in
frame_clearance = 0.5; // total, each axis
total_t = 3.0;
inlay_t = 0.6;         // three 0.2 layers
pocket_depth = 1.8;    // from the back; leaves total_t - pocket_depth of skin
pocket_clearance = 0.4;
hole_clearance = 0.2;

/* [Touch Toggle, inches, from touch-toggle-dimensions] */
plate_in = 0.75;
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

module pocket2d(p, rot = 0) {
  at(p) rotate(rot) square(plate_in * IN + pocket_clearance, center = true);
}

module pockets2d() {
  for (p = SINGLE_TOGGLES) pocket2d(p);
  pocket2d(SW7_TOGGLE, SLOPE_DEG);
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

  rings2d();

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
  square([sheet_w - frame_clearance, sheet_h - frame_clearance], center = true);
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
  compass_ring2d();
  needle_south2d();
}

module gold2d() {
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
  translate([0, 0, inlay_t]) linear_extrude(total_t - pocket_depth - inlay_t) difference() {
    outline2d();
    holes2d();
  }
  translate([0, 0, total_t - pocket_depth]) linear_extrude(pocket_depth) difference() {
    outline2d();
    pockets2d();
    holes2d();
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
