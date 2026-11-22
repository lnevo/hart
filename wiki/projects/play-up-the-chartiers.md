# /play: Up the Chartiers

Status: active

- **Owner:** lnevo. Plan agreed 2026-11-22; not started.
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

## The runs (proposal, to check against the sources first)

| Run | Era | Railroad and route | Rules |
|---|---|---|---|
| Coal extra | 1949 | PRR Chartiers Branch, Carnegie toward Washington, with the mine branches | 1949 Standard Code: timetable, superiority, train orders, semaphores at the crossings with the Montour, P&WV and B&O |
| Passenger train | 1949 | PRR Chartiers Branch passenger train, Pittsburgh to Washington (the branch ran passengers until 1952) | Standard Code: a first-class schedule, meets with freights and extras, orders at the open offices, protection when stopped |
| Ore transfer | 1980s | PC&Y (half P&LE, half Conrail), Scully Yard to the Y Interchange on Neville Island; or the P&LE main through McKees Rocks | Signals and yard limits; ties the run to the island game |
| Warrant run | 1997 | Pittsburgh & Ohio Central over the Chartiers Branch and the PC&Y, meeting NS at Duff Junction and CSX at POV Junction | GCOR track warrants, dark territory, yard limits |

Facts to confirm before any build (from `www/library/chartiers-valley-railroads.html`, `www/data/chartiers-lineage.json` and the archive): stations and mileposts on the Chartiers Branch; a 1949 passenger schedule; the P&LE's signals around McKees Rocks; whether the PC&Y ran under timetable and train orders or yard limits; what authority POHC used in 1997. Where a source is silent, fill the detail in without comment (rule 2 below).

## Navigation (one game)

- The start screen gets two groups: **On the island** (the seven P&OV shifts) and **Up the Chartiers** (the road runs). Each card shows its era and which deck sections it covers.
- A coverage strip at the top shows the eight deck sections and which runs test each, so a player can pick a run for a weak section.
- The game keeps the name Extra East: Neville Island unless the owner renames it (open question below). Page id `play` stays under Behind the Scenes in `site.json`.
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
5. **Daily only where the draw varies.** A run gets Today's run only if its draws change it meaningfully from day to day (Extra East's 1949, modern and signals runs do); otherwise practice only, with the guard in `begin()`.
6. **Look:** the dusk coke-works theme with steel-grey paper, no tan. The pixel-art title and share card style stay. Maps follow the cleaned schematic: even rows, 45° connections, labels clear of track and engines, no "not to scale" note.
7. **Writing:** the site voice rules; `tools/audit/check_ai_speak.py` and the `voice-reviewer` agent on all new text.
8. **Checks before merge:** the fake-DOM play-through (every run to the end, many draws), the portal unit tests, `build_play_answers.js --check`, `/code-review medium`, and a look in Chrome. Then deploy with `www/scripts/deploy_hartrailroad.sh`.

## Steps

1. Confirm the facts above from the library and the archive; write them into this page.
2. Reorganize the start screen into the two groups and the coverage strip, with the seven shifts unchanged.
3. Port the engine pieces and the Chartiers line data; build the 1949 coal extra first.
4. Add the passenger run, then the 1980s signaled run, then the 1997 warrant run, one PR each.
5. Extend the answer key and its test; add a share card if the title screen changes.
6. Update `wiki/STATUS.md` and close this page.

## Open questions for the owner

- The game's name once it spans the Chartiers (keep Extra East: Neville Island, or rename).
- Which run carries the passengers: the 1949 PRR train (recommended, since it fits the Standard Code) or a later one.
- Whether the 1980s run is the PC&Y ore transfer or the P&LE main through McKees Rocks.
