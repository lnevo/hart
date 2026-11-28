# Real and invented on the site

Owner, 2026-11-18: HART and its P&CV Division are a proto-freelanced successor to the real P&OV (1899 to 31 Jan 1994); the premise is fictional. D749 (CSX) and NVL (POHC) are real train numbers; the job work on the layout is fictional. Route 23 was a real historical streetcar route; the route it runs on the layout is fictional.

- In-world text says "On HART," or "On the layout" instead of calling real trains or routes invented.
- Every published page needs a class in `www/scripts/provenance.json` (`prototype`, `fiction`, `hobby`, `mixed`); the build turns it into JSON-LD and `llms.txt` so crawlers can tell real history from the fiction (see [`www/README.md`](../../www/README.md), Provenance).
- P&CV and P&OV are both deliberate; never normalise one to the other ([`AGENTS.md`](../../AGENTS.md)). The P&OV stays in crew material.
