# /play: Up the Chartiers

Status: done (2026-11-22)

- **Owner:** lnevo. Plan agreed 2026-11-22; all steps done 2026-11-22: four Chartiers runs live beside the seven island shifts; across the game every deck section is tested.
- **Goal:** one game at [`/play/`](https://www.hartrailroad.com/play/) that covers the whole C&E study deck. The Neville Island shifts cover the yard rules; new road runs "Up the Chartiers" cover what they cannot: the timetable, superiority, train orders, track warrants, signals and semaphores. One run carries passengers.
- **Today:** `www/play/` holds seven P&OV shifts (`runs.js`), the engine (`play.js`), the answer key (`answers.html`, built by `www/scripts/build_play_answers.js`) and the share card (`make_share_cards.py play-neville`). Extra East on the invented Kestrel Valley stays at `exam/run.html`, unchanged.

## What each part covers

| Deck section | Neville Island now | Up the Chartiers (planned) |
|---|---|---|
| Definitions | 22 questions | more, on road terms |
| Superiority & movement | none | 1949 freight and passenger runs |
| Train orders | none | 1949 runs |
| Signals & whistles | whistles and bell only | 1980s signaled run: block and interlocking signals |
| Semaphores | none | 1949 runs, interlockings at the crossings |
| Yard limits | 3 | McKees Rocks, Carnegie, Washington |
| Track warrants | none | 1997 run |
| GCOR crew & speed | 18 | more |

## The runs (decided 2026-11-22)

| Run | Era | Railroad and route | Rules |
|---|---|---|---|
| Coal extra | 1949 | PRR Chartiers Branch, Carnegie toward Washington, with the mine branches | 1949 Standard Code: timetable, superiority, train orders, semaphores at the junctions with the P&WV, the Montour and the B&O |
| Passenger train | 1949 | PRR Chartiers Branch passenger train, Pittsburgh to Washington. It meets a B&O train at Tylerdale (MP 21.8), where the Tylerdale Connecting joins the main; the run stays the PRR's | Standard Code: a first-class schedule, meets with freights and extras, orders at the open offices, protection when stopped |
| Ore transfer | 1980s | PC&Y (half P&LE, half Conrail), Scully Yard to the Y Interchange on Neville Island | Signals and yard limits; ties the run to the island game |
| Warrant run | 1997 | Pittsburgh Industrial Railroad (RailTex; POHC only from December 2000) over the Chartiers track and the PC&Y, meeting Conrail at Duff Junction and CSX at POV Junction | GCOR track warrants, dark territory, yard limits |

## Focus of each run (owner, 2026-11-22)

Coverage is judged across the whole game: the island shifts and all four Chartiers runs together. Runs may overlap; each has a focus and stays a working day, not a quiz.

| Run | Focus | Also comes up |
|---|---|---|
| 1949 coal extra | Superiority and movement (an extra against regular trains, S-87 margins, Rule 86, double-track D-rules); semaphores at the interlockings | One meet order; yard limits at Carnegie |
| 1949 passenger train | Train orders (forms, clearance, the order board, the B&O meet at Tylerdale); the first-class schedule; protection when stopped (Rule 99) | Whistles, semaphores |
| 1980s PC&Y ore transfer | Signals (block and interlocking aspects at the P&LE crossing and Neville); yard limits | Definitions, GCOR crew rules |
| 1997 PIR warrant run | Track warrants, dark territory | Yard limits, GCOR |

A run asks about 15 to 20 questions, near the island shifts' 7 to 13; the passenger run, the train-order run, may ask up to 23. The coal extra ties up at Arden once the Manifold loads are out. Both 1949 runs share one fixed time-table, as an employee time-table would; the draws vary the orders, late trains and events, not the schedule.

## Facts (step 1, 2026-11-22)

Sources: `www/library/chartiers-valley-railroads.html` and its sources, [Wikipedia: Chartiers Branch](https://en.wikipedia.org/wiki/Chartiers_Branch), [Metzger, Pennsylvania Trolley Museum](https://pa-trolley.org/a-short-history-of-the-chartiers-valley-rr-line/), the 1996 STB notice and the 1998 RRB determination for PIR. The media archive holds nothing on the Chartiers.

**Chartiers Branch, 1949**
- Mileposts from Carnegie (Mansfield), MP 0: Bridgeville MP 4 (Bridgeville & McDonald branch to Cecil and Bishop), Hills MP 8.6 (Montour), Houston MP 15.3 (Westland branch), Washington about MP 23.6. Pittsburgh to Carnegie is about 8 miles (32 miles Pittsburgh–Washington in 1926).
- Stations in order: Glenn, Woodville, Bower Hill, Kirwan, Bridgeville, Mayview, Boyce, Hills, Canonsburg, Houston, Arden, Washington. Mileposts not found for the others; place them between the known ones.
- Track: double Carnegie–Houston (since 1904), single Houston–Washington (owner's choice; the source says only "single by 1951"). Bell's (Greer) Tunnel is double track; Glenn tunnel was opened to a cut in 1898.
- Signals: the branch had signals until 4 August 1959; their type is not recorded. Offices, towers and the PRR division are not found.
- Passenger service: nine daily round trips in 1926, about 1.5 hours (express about 1 hour); last train 20 July 1952. No 1949 schedule found.
- Mine branches in 1949: Bridgeville & McDonald (at Bridgeville), Westland (at Houston, MP 15.3), with two spurs off it to the Palanka mines (Midland No. 1 closed 9 March 1949, so the 1949 runs do not work it; not drawn), and Manifold (junction not found; the game puts it at Arden). Palanka research 2026-11-22: Wikipedia Chartiers Branch, Coal Camp USA after Giosta 1970.
- Junctions: PC&Y at Glenn and Woodville; P&WV about a mile west of Bridgeville (Washington side); Montour at Hills; B&O by the Tylerdale Connecting, which joins the main at Tylerdale, about MP 21.8 (moved there from Washington 2026-11-22 after the prototype review).

**PC&Y, 1980s:** jointly owned, own operating staff; reached the island through Neville interlocking (about PLE 5.7) and crossed the P&LE main near McKees Rocks (about PLE 3.75). Not found: an ore move from Scully to Neville, the method of operation, the signal type.

**PIR, 1997:** in business from 7 December 1996; interchange with Conrail, CSX and PAM; incidental CSX trackage rights on the island. Not found: its operating authority, dark territory, yard limits, the dispatcher.

Everything marked not found is filled in by the game without comment (rule 2).

## Navigation (one game)

- The start screen gets two groups: **On the island** (the seven P&OV shifts) and **Up the Chartiers** (the road runs). Each card shows its era and which deck sections it covers.
- A coverage strip at the top shows the eight deck sections and which runs test each, so a player can pick a run for a weak section.
- The game is renamed **Extra East: HART Railroad** (owner, 2026-11-22). Page id `play` stays under Behind the Scenes in `site.json`.
- One answer key, `play/answers.html`, grouped by group, then run. Extend `build_play_answers.js` to read the road runs.

## Engine

- The road runs need Extra East's time-table, train-order, track-warrant and signal machinery, now in `exam/run.js` (`makeTT`, `checkMove`, `orderBoard`, `warrantCopy`, `startSIG`, `signals.js`). Copy what is needed into `www/play/` and give it the Chartiers line data (stations, mileposts, sidings, offices, interlockings). Do not change `exam/run.js`; Extra East keeps working as it is.
- The road runs go in a new `www/play/road.js` (or one file per run) beside `runs.js`, registered the same way.
- The scale of a run (`pace`), the marks, the end screen and the record stay as in `play.js`.

## Rules already decided (keep them; owner, 2026-11-22)

1. **Questions test the study deck only.** Every question is a rule from the C&E deck (Standard Code, GCOR, the guides). History sets the scene and links its source inline; it is never the thing asked.
2. **No disclaimers in play.** Cards, scenes and instructions stay in the story. The introduction says once where the material comes from and that the game fills in the rest. No "for the game", "invented" or "the blog does not say".
3. **Real people** appear only in history notes and quotes, never as a character who makes a mistake. Tragedies (the 1945 carbon plant explosion, the 1987 ladle house death) stay out.
4. **Names follow the year:** plants, railroads and owners as they were in the run's year (`plants-lineage.json`, `chartiers-lineage.json`).
5. **No daily run.** Every run is a new draw. Extra East's daily run was removed on 2026-11-22 (owner), so neither game has one.
6. **Look:** the dusk coke-works theme with steel-grey paper, no tan. The pixel-art title and share card style stay. Maps follow the cleaned schematic: even rows, 45° connections, labels clear of track and engines, no "not to scale" note.
7. **Writing:** the site voice rules; `tools/audit/check_ai_speak.py` and the `voice-reviewer` agent on all new text.
8. **Checks before merge:** the fake-DOM play-through (every run to the end, many draws), the portal unit tests, `build_play_answers.js --check`, `/code-review medium`, and a look in Chrome. Then deploy with `www/scripts/deploy_hartrailroad.sh`.

## Steps

1. ~~Confirm the facts from the library and the archive.~~ Done 2026-11-22 (Facts above).
2. ~~Reorganize the start screen into the groups and the coverage strip.~~ Done 2026-11-22: the rename, the On the island group, a deck-section strip and a Tests line on each card, from a `covers` list on each run (checked by `test_play_answers.py`). The Up the Chartiers group goes in with its first run, so the page never shows an empty group.
3. ~~Port the engine pieces and the Chartiers line data; build the 1949 coal extra.~~ Done 2026-11-22 (PR #993): Extra 4619 South, Carnegie to Arden, about 15 questions, focused on superiority and semaphores.
4. Add the passenger run, then the 1980s signaled run, then the 1997 warrant run, one PR each. Passenger run done 2026-11-22 (PR #996): No 307 South, Carnegie to Washington, three drawn order sets, a Rule 99 stop, the B&O meet at Washington, about 20 questions; with a shared road engine (`www/play/road-engine.js`) and one fixed 1949 time-table. The start screen was made compact the same day (PR #995): groups as tabs, a row per run, section chips. PC&Y ore transfer done 2026-11-22 (PR #998): 1981, Scully Yard to the Y Interchange before #105 goes on duty, through yard limits, the McKees Rocks interlocking at the P&LE crossing and Neville interlocking; about 19 questions on signals and yard limits. Rule books (owner): GCOR for yard limits and crew rules, the Standard Code aspects for signals. The group line reads Chartiers Valley · 1949 to 1997. PIR warrant run done 2026-11-22 (PR #1000): 1997, PIR Local, the south turn: McKees Rocks, the Conrail interchange at Duff, four track warrants (114, 118, 121, 125) to Canonsburg and back, a cut over the CSX diamond to POV Junction; about 19 questions, at least 13 on track warrants. The warrant form is Extra East's, ported to `www/play/warrant.js`; a copy error costs 2 minutes and a miss (owner). The answer key lists the four warrants.
5. ~~Extend the answer key and its test.~~ Done with each run. The share card was not changed: its stamp already reads Extra East · HART Railroad.
6. ~~Update `wiki/STATUS.md` and close this page.~~ Done 2026-11-22.

## Decided 2026-11-22

- Name: Extra East: HART Railroad.
- Passengers: the 1949 PRR train, with a meet with a B&O train at Tylerdale, short of Washington.
- 1980s run: the PC&Y ore transfer.
- 1949 track: double to Houston, single beyond.
- Warrant run: stays 1997, as the Pittsburgh Industrial Railroad with Conrail at Duff.
