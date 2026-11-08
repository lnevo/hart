// SW13 test panel: one one-light Touch Toggle in a 2 x 2 in plate.
//
// Tests fit, crush-rib retention and touch through a 1.0 mm skin before the
// next station map. Toggle sizes are the caliper measurements in README.md.
//
// Prints face down with no supports: skin on the bed, pocket open at the back.
//   z 0 .. letter_t       face; SW13 recessed here
//   0 .. skin_t           skin over the toggle, LED hole only
//   skin_t .. total_t     pocket, crush ribs, wire slot out the bottom edge
//
// One colour: print part="body" alone (SW13 stays recessed).
// Two colour: load body + letters as one object; the letters fill the recess.
//   ./docs/benchwork/station_maps_3d/build.sh

part = "all";  // all (colour preview) | body | letters

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

/* [Label] */
label = "SW13";
letter_t = 0.6;
letter_size = 8;
pocket_y = -5;           // pocket centre below plate centre, label above
label_y = 14.5;

$fn = 48;

total_t = skin_t + toggle_t + back_gap;
pocket_w = toggle_w + pocket_clearance;
pocket_depth = total_t - skin_t;

module plate2d() {
  offset(r = plate_r) square(plate_w - 2 * plate_r, center = true);
}

module label2d() {
  translate([0, label_y])
    text(label, size = letter_size, font = "Arial Black", halign = "center", valign = "center");
}

module led2d() {
  translate([0, pocket_y]) circle(d = led_d + led_clearance);
}

// Pocket plus a slot from its bottom wall out through the plate's bottom edge.
module pocket2d() {
  translate([0, pocket_y]) square(pocket_w, center = true);
  translate([-wire_slot_w / 2, -plate_w]) square([wire_slot_w, plate_w + pocket_y]);
}

// Two ribs on each of the left, right and top walls; the bottom wall is the slot.
RIB_OFFSET = pocket_w / 4;
RIBS = [
  for (s = [-1, 1]) [[-pocket_w / 2, pocket_y + s * RIB_OFFSET], [1, 0]],
  for (s = [-1, 1]) [[pocket_w / 2, pocket_y + s * RIB_OFFSET], [-1, 0]],
  for (s = [-1, 1]) [[s * RIB_OFFSET, pocket_y + pocket_w / 2], [0, -1]],
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
    translate([0, 0, -1]) linear_extrude(letter_t + 1) label2d();
    translate([0, 0, -1]) linear_extrude(total_t + 2) led2d();
    translate([0, 0, skin_t]) linear_extrude(pocket_depth + 1) pocket2d();
  }
  // Clip ribs to the plate so none pokes out through the wire slot.
  intersection() {
    union() for (r = RIBS) rib(r[0], r[1]);
    linear_extrude(total_t) plate2d();
  }
}

module letters() {
  linear_extrude(letter_t) label2d();
}

// Turn the face onto the bed so the label reads correctly once picked up.
mirror([1, 0, 0]) {
  if (part == "body") body();
  else if (part == "letters") letters();
  else {
    color("white") body();
    color([0.08, 0.08, 0.08]) letters();
  }
}
