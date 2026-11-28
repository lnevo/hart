# Share thumbnails: what the owner wants

The mechanics (`share-cards.json`, `share_cards.py`, `make_share_cards.py`, hub cards) are in the Share thumbnails item of [`www/README.md`](../../www/README.md). This page records the owner's choices, set 2026-11-09 and 2026-11-10.

- A thumbnail shows the page's own subject, preferably the real thing the page is about: a screenshot of the actual tool or figure (track scale after a weigh, the STS home page, a wiring node, a speed chart, the timetable from its document) beat generic layout photos every time. Corrected first picks: a locomotive on the device roster, car cards on too many pages, a generic diagram on the build story.
- The owner cares most about the articles. Paperwork-type pages share one picture only when the owner names it (`"shared": true`); never share a picture across pages unasked, and ask before reusing an existing card. When no honest picture exists, the site card or a named shared card is better than a weak invented one.
- The Prototype section stays on the global thumbnail unless an article already carries a good picture; make no new pictures for history articles.
- A drawn or composed card has its recipe in `www/scripts/make_share_cards.py` ("generators need to be in the repo").
- 2026-11-14: too many cards were screenshots or recompositions of the page's own UI: "think outside the box literally next time". The C&E exam card (a composed deck UI) was accepted, but fewer like it. For a new card, first look for a subject from the real world: a train order flimsy, a semaphore, a rulebook page, a layout photo of the thing, a drawn object. Use the page's own UI only when nothing like that exists.
- Hub cards (2026-11-10): 2:1 strips, colour muted (not grey) until hover; a centred crop is fine. A blank band reads as a missing picture, so every card in a marked grid gets a real picture (the `links` table covers sections and GitHub links).
- An owner pick overrides the real-world-first rule: on 2026-11-16 the station maps index and live map pages were set to the generated South Yard sheet (recipe `crew-maps-south-yard`).
- The owner reviews card by card in a live gallery and accepts each change merged and deployed as it is made.
