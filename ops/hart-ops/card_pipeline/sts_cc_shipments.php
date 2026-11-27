<?php
// Writes every STS shipment, with its commodity, car code and both locations, to /tmp/cc_shipments.json and
// echoes the count. generate_cc_waybill_labels.py passes the code below this header to php -r in the STS web
// container, then copies the file out.

require "/var/www/html/sts/open_db.php";
$dbc = open_db();
$sql = "SELECT s.id, s.code,
  COALESCE(c.description,\"\") AS consignment,
  COALESCE(cc.code,\"\") AS car_code,
  COALESCE(loc_u.code,\"\") AS unload_loc,
  COALESCE(rout_u.station,\"\") AS unload_sta,
  COALESCE(loc_u.track,\"\") AS unload_trk,
  COALESCE(loc_u.spot,\"\") AS unload_spot,
  COALESCE(NULLIF(loc_u.rpt_station,\"\"), rout_u.station, \"\") AS unload_rpt,
  COALESCE(loc_l.code,\"\") AS load_loc,
  COALESCE(rout_l.station,\"\") AS load_sta,
  COALESCE(loc_l.track,\"\") AS load_trk,
  COALESCE(loc_l.spot,\"\") AS load_spot,
  COALESCE(NULLIF(loc_l.rpt_station,\"\"), rout_l.station, \"\") AS load_rpt,
  COALESCE(s.special_instructions,\"\") AS special,
  COALESCE(loc_u.color,\"\") AS unload_color,
  COALESCE(loc_l.color,\"\") AS load_color,
  COALESCE(s.description,\"\") AS description,
  COALESCE(s.remarks,\"\") AS remarks
FROM shipments s
LEFT JOIN commodities c ON c.id = s.consignment
LEFT JOIN car_codes cc ON cc.id = s.car_code
LEFT JOIN locations loc_u ON loc_u.id = s.unloading_location
LEFT JOIN routing rout_u ON rout_u.id = loc_u.station
LEFT JOIN locations loc_l ON loc_l.id = s.loading_location
LEFT JOIN routing rout_l ON rout_l.id = loc_l.station
ORDER BY s.code";
$rs = mysqli_query($dbc, $sql);
$out = [];
while ($row = mysqli_fetch_assoc($rs)) { $out[] = $row; }
file_put_contents("/tmp/cc_shipments.json", json_encode($out, JSON_UNESCAPED_UNICODE));
echo count($out);
