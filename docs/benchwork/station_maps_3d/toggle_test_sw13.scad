// SW13 test panel: one one-light Touch Toggle in a 2 x 2 in plate.
//
// Tests fit, crush-rib retention and touch through a 1.0 mm skin before the
// next station map. Toggle sizes are the caliper measurements in README.md.
//
// Prints face down with no supports: skin on the bed, pocket open at the back.
//   z 0 .. ink_t          face; track and SW13 recessed here
//   0 .. skin_t           skin over the toggle, LED hole only
//   skin_t .. total_t     pocket, crush ribs, wire slot out the bottom edge
//
// Face: a horizontal main through the switch, with a spur going north from the
// junction and then west. A ring round the LED marks the switch, as on Barn.
//
// One colour: print part="body" alone (track and SW13 stay recessed).
// Two colour: load body + ink as one object; the ink fills the recess.
//   ./docs/benchwork/station_maps_3d/build.sh

part = "all";  // all (colour preview) | body | ink

/* [Plate] */
plate_w = 50.8;        // 2 in
plate_r = 3.0;         // corner radius
skin_t = 1.0;
back_gap = 0.4;        // toggle sits this far below the back, so tape lies flat

/* [One-light toggle, measured] */
toggle_w = 17.7;
toggle_t = 5.1;
led_d = 4.76;          // 3/16 in, from the spec drawing, centred

/* [Fit] */
pocket_clearance = 0.3;  // total, each axis
led_clearance = 0.2;
rib_d = 1.0;
rib_protrude = 0.35;     // into the pocket; 0.2 mm interference a side
lead_in = 1.0;           // rib taper at the back so the toggle starts easily
wire_slot_w = 13.0;      // ribbon is 3.8 wide but its position varies

/* [Face] */
ink_t = 0.6;
track_w = 1.3;
ring_w = 1.3;
edge_inset = 3.0;        // track ends this far inside the plate edge
pocket_x = -4;           // switch left of centre, label to the right of the spur
pocket_y = 0;
spur_y = 13;             // where the spur turns west
label = "SW13";
letter_size = 5.5;
label_pos = [10.5, 16];

$fn = 48;

total_t = skin_t + toggle_t + back_gap;
pocket_w = toggle_w + pocket_clearance;
pocket_depth = total_t - skin_t;

module plate2d() {
  offset(r = plate_r) square(plate_w - 2 * plate_r, center = true);
}

module label2d() {
  translate(label_pos)
    text(label, size = letter_size, font = "Arial Black", halign = "center", valign = "center");
}

SWITCH = [pocket_x, pocket_y];
EDGE = plate_w / 2 - edge_inset;

module led2d() {
  translate(SWITCH) circle(d = led_d + led_clearance);
}

module line2(a, b) {
  hull() {
    translate(a) circle(d = track_w);
    translate(b) circle(d = track_w);
  }
}

module ink2d() {
  difference() {
    union() {
      line2([-EDGE, pocket_y], [EDGE, pocket_y]);       // main
      line2(SWITCH, [pocket_x, spur_y]);                // spur north
      line2([pocket_x, spur_y], [-EDGE, spur_y]);       // then west
      translate(SWITCH) circle(d = led_d + led_clearance + 2 * ring_w);
      label2d();
    }
    led2d();
  }
}

// Pocket plus a slot from its bottom wall out through the plate's bottom edge.
module pocket2d() {
  translate(SWITCH) square(pocket_w, center = true);
  translate([pocket_x - wire_slot_w / 2, -plate_w]) square([wire_slot_w, plate_w + pocket_y]);
}

// Two ribs on each of the left, right and top walls; the bottom wall is the slot.
RIB_OFFSET = pocket_w / 4;
RIBS = [
  for (s = [-1, 1]) [[pocket_x - pocket_w / 2, pocket_y + s * RIB_OFFSET], [1, 0]],
  for (s = [-1, 1]) [[pocket_x + pocket_w / 2, pocket_y + s * RIB_OFFSET], [-1, 0]],
  for (s = [-1, 1]) [[pocket_x + s * RIB_OFFSET, pocket_y + pocket_w / 2], [0, -1]],
];

module rib(p, n) {
  // Cylinder centred so it stands rib_protrude proud of the wall.
  c = p + n * (rib_protrude - rib_d / 2);
  translate([c[0], c[1], skin_t]) hull() {
    cylinder(d = rib_d, h = pocket_depth - lead_in);
    translate(-n * rib_protrude) cylinder(d = rib_d, h = pocket_depth);
  }
}

module body() {
  difference() {
    linear_extrude(total_t) plate2d();
    translate([0, 0, -1]) linear_extrude(ink_t + 1) ink2d();
    translate([0, 0, -1]) linear_extrude(total_t + 2) led2d();
    translate([0, 0, skin_t]) linear_extrude(pocket_depth + 1) pocket2d();
  }
  // Clip ribs to the plate so none pokes out through the wire slot.
  intersection() {
    union() for (r = RIBS) rib(r[0], r[1]);
    linear_extrude(total_t) plate2d();
  }
}

module ink() {
  linear_extrude(ink_t) ink2d();
}

// Turn the face onto the bed so the label reads correctly once picked up.
mirror([1, 0, 0]) {
  if (part == "body") body();
  else if (part == "ink") ink();
  else {
    color("white") body();
    color([0.08, 0.08, 0.08]) ink();
  }
}
