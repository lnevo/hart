# Reference research: logical track schematics for operators

Method note: web search results were thin and the fetch tool cannot see images, so I downloaded and looked at six diagrams directly (marked SEEN). Everything else is from page text only. Several trains.com PDFs returned HTTP 403 (marked UNVERIFIED). No NORAC/LIRR physical-characteristics book is publicly reachable; I found none and say so rather than guess.

Local copies of the images I viewed (scratch only): /private/tmp/claude-501/-Users-lnevo-hart/d609fb79-b477-4214-a7f1-0e3767b80ea8/scratchpad/img/

## 1. Prototype conventions

### 1.1 Colour code by control system (verified text)
- chicagorailfan.com "Methods of Train Operation" colours track diagrams by territory: black = unsignaled, blue = interlocking limits, green = automatic block signals, red = operation by signal indication (CTC). Yard limits are shown in black. CTC interlockings are often labelled "CP" plus a mile number. https://chicagorailfan.com/opermeth.html
- Same site's "Classic Track Diagrams": manual interlocking towers are blue rectangles holding the interlocking number or letter; remote interlockings are red rectangles; older charts often omit switches at interlockings and take signal locations from the employee timetable. https://www.chicagorailfan.com/clasemp1.html

### 1.2 PRR interlocking sheets, Toledo area (SEEN: walbridge.gif)
Index: https://www.redoveryellow.com/position-light/PRR_Diagrams/itlk_tolj_det_main.html ; image https://www.redoveryellow.com/position-light/PRR_Diagrams/walbridge.gif (2199x1056, 200 dpi scan of a 1957 sheet).
Observed:
- Hand-lettered title block top right: railroad, place name, crossing parties, district; ownership/maintenance block with revision dates (12-1-54, 12-1-55, 1-1-57); sheet number bottom right ("Sh 42").
- Machine data block (US&S Model 14 electro-pneumatic; lever counts: 21 switch, 14 signal, 3 master, 59-lever frame); speed limits per railroad; time-locking note.
- Lines are all one weight, tracks named in place on the line ("P.O.&D.R.R.", "To Toledo", "To Mansfield"); diverging legs drawn at shallow real angles, not 45 degrees (it is a scaled-ish plan, not a schematic).
- Switches numbered at the point, odd numbers with signals as small arrow/semaphore glyphs with letters (a, b, c) for heads and L/R suffix for direction (e.g. 26R, 34L); distances between features in feet on dimension lines; "5.2 Mi. To Olive" / "17.1 Mi. To Gibsonburg" continuation notes with mileage.
- Page text: PRR mileposts measured from Fort St. Union Station Detroit, two-letter tower codes in brackets ([VN], [WR]); warns that orientation is not consistent across sheets (some have "To Detroit" on the left). Trackage rights coloured red on the area map.
Lesson: prototype interlocking sheets keep geometry realistic and carry the information in annotation. A schematic for operators should borrow the annotation vocabulary (numbered switches, signal glyph with facing letter, distance-to-next-point notes, title and revision block) but not the geometry.

### 1.3 CTC model board (verified text)
- friendstm.org (a working model-railroad CTC): tracks as broad lines, grey vacant, red occupied, green route authorised; dispatcher signals as coloured circles with white lines; intermediate signals as "chicken feet" stick figures; even numbers for controlled points, odd for motorised turnouts, L/R suffix for facing direction; blue text for time of last train. https://friendstm.org/Signals/ModelBoardDescription.shtml
- A 1950s trade article (NYC pushbutton CTC) says the lighted track diagram runs across the top of the machine with levers below each field location. https://casite-773312.cloudaccess.net/images/PDFDocs/PushbuttonCTCMachineonNYCIsFirstofItsKind.pdf (snippet only; I did not open the PDF)
- A 1959 US&S TCC article: 3 ft modular diagram panels each holding 5 to 7 passing tracks, white location names and numbers, power-off lamps. https://jonroma.net/media/signaling/railway-signaling/1959/Pushbutton%20console%20for%20CTC.pdf (search snippet only)
- JMRI USS CTC conventions page exists (https://jmri.org/help/en/html/tools/uss/Conventions.shtml) but returned 403; UNVERIFIED.

### 1.4 Employee timetable and track chart content
- Timetable station tables list passing sidings with capacity in cars, spring switches, derails, special instructions (https://armytransportation.tpub.com/tr06386/Employees-Timetable-66.htm). BNSF Texas subdivision timetable uses a "Capacity Feet" column (https://fobnr.org/wp-content/uploads/2023/08/TEXAS-09-021611.pdf). Canadian rules say siding capacity and cautionary limits go in timetable columns/footnotes (https://tc.canada.ca/en/rail-transportation/rules/2024-2025/canadian-rail-operating-rules/time-time-tables). UP Salt Lake City area timetable defines CTC, ABS, TWC and yard-limit symbols, and a Toledo West subdivision timetable explains station-page markings (yard limits, wyes, spring switches) (https://utahrails.net/pdf/UP-Salt-Lake-City-Area-Timetable-No-2_Oct-29-2000.pdf ; https://davewisniewski.com/bletdiv4/documents/rules/TIME/Toledo%20West%20Subdivision.pdf). Both statements come from search snippets; the UP PDF exceeded the fetch size limit, so symbol shapes are UNVERIFIED.
- Metro-North track charts / interlocking / yard diagram bundle (2015): https://s3.documentcloud.org/documents/2647944/Operations-Metro-North-Railroad-Track-Charts.pdf ; file came back as a 4.8 KB stub, UNVERIFIED. This is the best lead for NORAC-territory physical-characteristics practice.
- Model Railroader note that prototype track charts inspire track plans: https://www.trains.com/wp-content/uploads/2020/10/ra0403_a1.pdf (403, UNVERIFIED).
- Dispatcher-versus-crew split: a forum summary says dispatchers use a main-track-only schematic, crews use detailed ZTS/track charts with names and numbers; local divisions add gate/dock detail (found via search; thread not individually opened, treat as hearsay).

### 1.5 Not found
LIRR/Conrail/PRR "physical characteristics" books, US&S/GRS drawing standards, exact line weights in points. Nothing public turned up. Line-weight guidance below is inferred from model examples, not prototype standards.

## 2. Model railroad examples

| # | Layout | What | URL | Good / bad for a new operator |
|---|---|---|---|---|
| 1 | St Charles Branch (Appalachian Railroad Modeling), multi-deck with helix | SEEN. Straightened crew-training track chart | https://appalachianrailroadmodeling.com/stcharlesbranch/wp-content/uploads/2025/07/Crew-Training-Track-Chart-scaled.jpg (page https://appalachianrailroadmodeling.com/stcharlesbranch/?p=796) | Strong. One horizontal main, branches at 45 degrees with bold bold labels and arrows ("Gin Crk Br", "Baileys Tr Br"), dashed line = hidden/scenicked-over run, boxed letters A-D for hidden-track segments/junction points, WEST | EAST legend with arrows, 2-3 letter town codes in parentheses, thick black bars for industry/yard ends, grey for the off-layout staging stub, small switch-stand glyphs. Weak: no track numbers or capacities. Same site's fascia diagram: thick main, thin sidings, track number across the line, switch knobs show normal and 45-degree diverging legs. |
| 2 | Willow Creek Subdivision (UP free-lance), loop-to-loop | SEEN. "As Built Schematic (Unfolded)" dated 1/29/21 | https://sites.google.com/site/willowcreekrr/track-plan (image URL inside page; Google-hosted) | Clean unfolded line, railroad logo and subdivision name top-left, date bottom-right, off-line yard hanging below main, dotted gaps for scenic breaks, reversing loops drawn as loops, staging yard branching up. Weak: no track numbers, no mileage, no direction legend, no capacities. |
| 3 | Santa Rosalia branch (SP, modeling the SP blog) | SEEN. Per-town schematic in timetable | https://modelingthesp.blogspot.com/2025/10/an-op-session-briefing.html (image https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEh_UZ_r1QBuOxx_WV2B6nyvSyxFNj4LPF1YNkbceyCkxHC4kjCRcWC8MSWKsjXHb0CtJ85NPsycEjg6v6AUqeIPzLCdHlwiHdj8Q77jF__TGT1ECbzPrQ3TOFDbqpEGQV93bO5trRJgMM3x8X0_kWlBNZVs5IAqL9wVa7U42C8yldKqTdgPKi0d3OMrT7I/s1200/SR%20map.jpg) | Good station map: main horizontal, tracks labelled in words on the line ("Siding", "Main Track", "Track 2"), industries as outlined boxes above/below the track they serve, spot numbers (01, 02) as subscripts, depot box, bill box, streets crossing as paired verticals, "To Ballard" / "End of branch" continuation text. Weak: monospaced typewriter font, no capacities, no switch numbers. |
| 4 | Railroad Model Craftsman author's layout (Tyler Whitcomb) | Text only: per-town PowerPoint track diagram with track numbers, industry names, spots, door numbers, mileposts, compass direction; yard schematics on sheet metal with magnets | https://rrmodelcraftsman.com/set-up-your-layout-for-realistic-operations/ | Content list is the best single checklist found for a station map. Images not viewed. States "tracks are usually numbered from the main line outward" (track 1 nearest main). |
| 5 | Gilpin Gulch | Embedded "Current (2020) Track Plan" image; contents not described by page text | https://sites.google.com/view/gilpingulchmodelrailroad/layout-description | UNVERIFIED as a schematic; no legend on page. |
| 6 | Yosemite Valley RR (Jack Burgess), 3 levels | Separate plan per deck (lower, middle, upper) plus PDF; heights given in text (46", 60", 77"); plans oriented to the room, "always face north" | https://yosemitevalleyrr.com/modeling/layout-plans ; article PDF https://www.yosemitevalleyrr.com/about/finished.pdf (not opened) ; Trains.com plan page https://www.trains.com/mrr/how-to/track-plan-database/yosemite-valley-rr-2 | Per-deck overhead maps with heights is exactly your item (c). Not a schematic; no operator-level crew schematic found. |
| 7 | Maumee Route (Bill Darnaby) | GMR 2007 article PDF with track plan and per-town drawings | https://www.trains.com/wp-content/uploads/2020/10/GMR2007_5665.pdf | UNVERIFIED (not opened). No standalone operating schematic found. |
| 8 | Virginian & Ohio (Allen McClelland) | Track plan PDF, MR Jan 2009 | https://trains.com/mrr/how-to/track-plan-database/virginian-and-ohio-3 | UNVERIFIED content. Linear walkaround. |
| 9 | Nickel Plate Road St. Louis Division (Tony Koester) | Plan database entries; MR Planning 2018 PDF says session takes 8 operators about 3 hours | https://trains.com/mrr/how-to/track-plan-database/ho-scale-nickel-plate-road-st-louis-division ; https://www.trains.com/wp-content/uploads/2023/09/Model-Railroad-Planning-2018.pdf | UNVERIFIED (403/not opened). |
| 10 | Siskiyou Line (Joe Fugate) | No operator schematic found | https://model-railroad-hobbyist.com/mrht_siskiyou | Gap. |
| 11 | A&LS (Lionel Strang plan, OpSIG file) | SEEN. Plan, not a schematic: dashed lines for lower-level staging, green line for benchwork edge, blue for walls, scale bar, door, dispatcher desk, staging "Lower Yard directly below Upper Yard" | https://www.opsig.org/files/do_extras/ALSTrackPlan.pdf | Useful contrast and a model for the per-deck overhead map: location names in a condensed sans, scale bar, drawn-by and date credit, deck annotated in text. |
| 12 | John Allen Gorre & Daphetid; N&W Washington Extension; UP Spine Line | Trains PDFs said to include operating schematics / helix drops shown on schematic | https://www.trains.com/wp-content/uploads/2023/09/How-to-Build-Small-Model-Railroads.pdf ; https://trains.com/wp-content/uploads/2020/10/mrr-f0306_norfolk___western_a.pdf ; https://www.trains.com/wp-content/uploads/2020/10/HOscaleUnionPacificSpineLinetrackplan.pdf | All three returned 403; UNVERIFIED, only search snippets ("Helix down to middle and staging levels"). |
| 13 | Lance Mindheim | Searched; no schematic found | https://raildig.com/raildig-guest/lance-mindheim/ | Gap. |

Already in hand, not re-researched: NY&Atlantic (Barraza), North Western Vermont (NER Coupler 303).

## 3. Guidance articles

- NMRA Beginner's Guide Part 9: locations "typically illustrated on a railroad schematic"; detailed schematics include mileposts. https://www.nmra.com/node/4420
- Same guidance in a search snippet: for a large layout an overall schematic shows few names and is supplemented by a schematic per group of locations (town). Source quoted by search tool as NMRA; page https://www.nmra.com/node/4420.
- Gateway NMRA (Schumacher): put a track diagram of each town on the fascia beside the town, annotated with the car types each dock door accepts; keep helixes at the end of runs, not in the operating part of a route. https://www.gatewaynmra.org/?p=257
- Operations clinic (Reading modeler): draw all track including sidings and crossovers, do not worry about scale; start at a yard and work in one direction. https://www.readingmodeler.info/images/files/operationsclinic.pdf (via search snippet; also https://www.scribd.com/doc/244187530/Operations-Clinic)
- Craig Bisgeier, "Ten Commandments of Yard Design": large colour-coded schematic panel and a handout yard diagram with each track's function (snippet only). https://www.ogrforum.com/fileSendAction/fcType/0/fcOid/69425981594635433/filePointer/69425981598447887/fodoid/69425981598447883/Yard%20design.pdf
- NMRA sheet D8k "Layout Planning for Realistic Operation": yard rules of thumb (snippet only; PDF unreadable to the fetcher). https://www.nmra.org/sites/default/files/d8k.pdf
- Trains.com: yard tracks run best under half full (snippet) https://www.trains.com/wp-content/uploads/2020/10/Freight-Yard-Design.pdf
- Multi-deck/helix background: https://www.trains.com/mrr/how-to/expert-tips/5-multideck-layout-design-and-construction-tips ; https://shop.trains.com/products/guide-to-helix-and-staging-design
- Not found: any OpSIG or Layout Design SIG primer on drawing schematics. OpSIG has "Primer TransportationPlan" and bibliography (https://opsig.org/Resources/Primer_TransportationPlan , https://opsig.org/Resources/Bibliography) but I found no drawing standard. The LDSIG Journal is not public via search.

## 4. Software and algorithms

Hobby CAD (no verified detail beyond names): AnyRail, SCARM, WinTrack, 3rd PlanIt, RR-Track, XTrackCAD, Templot, JMRI Layout Editor, Inkscape, Visio. I could not open pages for XTrackCAD, Templot, CATS Designer or Layout Editor; their schematic capability is UNVERIFIED. Practical evidence: the RMC author used PowerPoint, Willow Creek and St Charles charts look like Visio/PowerPoint line drawings (inferred from the SEEN images, not stated).

Algorithms and open-source tools, ranked for a ~40-switch-per-deck graph:
1. **railplot** (Luteberget). CLI and library for schematic linear railway drawings from railML 2.x or its own "sgraph" JSON; outputs SVG, TikZ, PDF, JSON; Lua scripts customise symbols; "simple" and "ertms" styles. Language not stated on page (Cargo.toml present, so Rust). Licence not stated on page. v0.3.1, 105 commits, 14 stars. https://github.com/luteberget/railplot . Based on the SAT approach below; most relevant prior art. Small graphs are its target.
2. **"Drawing with SAT: four methods and a tool for producing railway infrastructure schematics"**, Luteberget and Johansen, Formal Aspects of Computing 33 (2021). Optimises width, height, diagonal length and bends, with symbols and labels. https://link.springer.com/content/pdf/10.1007/s00165-021-00566-z.pdf ; predecessor https://research.chalmers.se/en/publication/514702 ; thesis https://luteberget.github.io/preprints/luteberget-thesis-plain-b5-2019-09-17.pdf . Springer abstract page was not fetched (redirect), so details come from search summaries.
3. **LOOM / octi** (ad-freiburg). GPL-3.0, C++ (CMake), reads/writes GeoJSON graphs, octilinear/ortholinear/hexalinear/orthoradial grid schematisation; optional ILP backends (GLPK, CBC, Gurobi). Targets transit lines, not turnouts, so a track graph would need a custom node-edge encoding. https://github.com/ad-freiburg/loom ; paper Bast, Brosi, Storandt, "Metro Maps on Octilinear Grid Graphs", CGF 2020 https://diglib.eg.org/handle/10.1111/cgf13986 (ILP exact, greedy approximation in fractions of a second).
4. Force-directed octilinear (Chivers and Rodgers 2014, FDOL) and Nöllenburg and Wolf MIP (TU Wien extension) https://www.ac.tuwien.ac.at/?p=5284 ; Brass and Hruby 2026 abstract https://ica-abs.copernicus.org/articles/12/17/2026/ica-abs-12-17-2026.pdf (abstract only; note it says local optimisation loses global shape such as loops). All are overkill for ~40 switches.
5. **tikz-trackschematic** (Martin Scheidt, ISC licence, v0.7.1): symbol library for hand-built track diagrams in TikZ, sublibraries topology, trafficcontrol, vehicles, constructions, electrics, symbology, measures. https://miktex.org/packages/tikz-trackschematic . Good symbol reference; no auto-layout.
6. **railML TrackPlanner** (railML.org) imports railML 3.1/3.2 and draws the schematic automatically; licence/source not found, UNVERIFIED as open. https://www.railml.org/en/software/trackplanner ; railVIVID viewer needs a login and its 3.x visual is unavailable. OpenTrack uses schematic infrastructure views (EMSS2015 paper https://www.msc-les.org/proceedings/emss/2015/EMSS2015_120.pdf). Use-case page: https://wiki3.railml.org/wiki/UC:IS:RailwayInfrastructureVisualisation
7. Signalling-diagram generation from topology: a US patent describes generating a track diagram from topological data then a signalling diagram from positioning rules (https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/8781803). ILP paper on signalling schematics at https://synapsesocial.com/papers/69a76082c6e9836116a2d518 (venue unknown).
8. Esri/ArcGIS "Linear Dispatch" schematic layouts (commercial). https://pro.arcgis.com/en/pro-app/latest/help/data/network-diagrams/linear-dispatch-layout-reference.htm
9. OpenRailwayMap: renders OSM railway data with kilometre posts, switches, track numbers and signals overlays; I found no schematic-plan generation. https://wiki.openstreetmap.org/wiki/OpenRailwayMap

Fit for a small hand-curated graph: because the user's input has trunk lines per deck that can be straightened by hand-ordered rules, a deterministic "main on one horizontal row, each siding/leg placed at +-1 row at 45 degrees" layout with a tiny constraint pass is simpler than a SAT/ILP solver. If automatic placement is wanted, railplot's SAT model is the closest published match; LOOM/octi is the most easily reusable open code but is aimed at line networks.

## 5. Typography and print (observations from SEEN images only)
- St Charles chart: heavy sans (Arial/Helvetica-class), bold title, bold branch names, regular-weight town names with 2-3 letter codes in parentheses, black on white, no colour, grey only for off-layout track. Legible in black and white by design.
- Willow Creek: black lines, small sans labels, logo in two colours, date stamp.
- A&LS plan: condensed sans (Univers Condensed per PDF font list), coloured lines (green edge, blue wall) with dashes as the only vertical-level cue.
- PRR sheet: hand lettering, all-caps italic titles, everything black on white scan.
- Santa Rosalia: monospaced, boxes for industries.
- Page sizes: A&LS is US Letter landscape (PDF 612x792 pt rotated); the others are screen images. No published page-size standard found. Prototype timetable pages are small-book format (not verified).

## (a) Ranked best 8 to imitate
1. St Charles Branch crew track chart (SEEN): https://appalachianrailroadmodeling.com/stcharlesbranch/wp-content/uploads/2025/07/Crew-Training-Track-Chart-scaled.jpg
2. Willow Creek unfolded schematic (SEEN): https://sites.google.com/site/willowcreekrr/track-plan
3. Santa Rosalia town schematic (SEEN): https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEh_UZ_r1QBuOxx_WV2B6nyvSyxFNj4LPF1YNkbceyCkxHC4kjCRcWC8MSWKsjXHb0CtJ85NPsycEjg6v6AUqeIPzLCdHlwiHdj8Q77jF__TGT1ECbzPrQ3TOFDbqpEGQV93bO5trRJgMM3x8X0_kWlBNZVs5IAqL9wVa7U42C8yldKqTdgPKi0d3OMrT7I/s1200/SR%20map.jpg
4. PRR Walbridge interlocking sheet (SEEN), for annotation vocabulary and title/revision block: https://www.redoveryellow.com/position-light/PRR_Diagrams/walbridge.gif
5. St Charles fascia diagram description (thick main, thin siding, numbered tracks, 45-degree knobs): https://appalachianrailroadmodeling.com/stcharlesbranch/?p=796
6. Yosemite Valley per-deck plans with heights: https://yosemitevalleyrr.com/modeling/layout-plans
7. A&LS plan for the overhead per-deck sheet (scale bar, staging note, credit): https://www.opsig.org/files/do_extras/ALSTrackPlan.pdf
8. chicagorailfan territory colour code (interlocking blue, CTC red, yard limits black): https://chicagorailfan.com/opermeth.html
(Barraza and NWV remain your top two; ranked above as additions.)

## (b) Draft style rules the examples agree on
1. One horizontal main line per deck; branches and sidings leave at 45 degrees and return parallel to the main; no curves except reversing loops.
2. Line weight: main heaviest, sidings and yard tracks thin (St Charles fascia; Willow Creek; Santa Rosalia).
3. Hidden or staging track dashed or dotted; off-layout stubs lighter grey (St Charles, Willow Creek, A&LS).
4. Place names bold or larger, with a short code in parentheses (St Charles); industries as outlined boxes touching the track they serve (Santa Rosalia).
5. Track numbering from the main outward, or named in words on the line, repeated at the track (RMC author; Santa Rosalia).
6. Direction legend on every page: arrows with compass or timetable direction (St Charles "WEST | EAST"); "To X" / "End of branch" continuation text at open ends (Santa Rosalia, PRR sheet).
7. Mileposts and distance-to-next-point notes where meaningful (RMC author, PRR sheet, NMRA).
8. Switch and signal numbers at the point with L/R facing suffix (PRR sheet, friendstm board); odd/even convention where used.
9. Title block with name, subdivision/location, date and revision (Willow Creek date stamp, PRR sheet revision block).
10. Overall schematic plus one detail sheet per town or group; per-deck overhead plans with heights stated (NMRA, Yosemite Valley).
11. Black on white is primary; colour only as redundant coding (territory colours, deck colours).

## (c) Open questions where examples disagree
- Orientation: prototype PRR sheets are inconsistent; Yosemite plans fix north; schematics use timetable east/west. Choose one per sheet and always print it.
- Track numbers: numbered from main outward (RMC) versus words on the track (Santa Rosalia) versus none (Willow Creek).
- Capacity in cars: prototype timetables always list it; none of the model examples I saw printed it on the diagram. Test whether it goes on the map or in a side table.
- Hidden track: dotted (Willow Creek, St Charles) versus a labelled box or letter marker (St Charles A-D). Decide whether helix and hidden stretches get a fixed symbol.
- Decks: separate sheets (Yosemite) versus dashed lower level on one plan (A&LS) versus helix drawn inline on a straightened schematic. Prototype gives no precedent.
- Territory colour: prototype uses colour for control type; model examples use none. Only useful if the layout has signalled/CTC/yard-limit zones.
- Geometry fidelity: prototype interlocking sheets keep real angles; model crew charts normalise to 45 degrees. For an operator schematic use 45 degrees, but verify a new reader can still map it to the room.
- Unresolved because sources were inaccessible: Maumee, V&O, Nickel Plate, Gorre & Daphetid, N&W, Metro-North track charts.
