# tools/anyrail

Readers and drawings built from the owner's AnyRail track plan.

- **What may be public.** Exports of the track (geometry, XML export, derived graphs) may go in public repos. The plan's custom objects and buildings may not: their author holds the copyright. The raw `.any` file holds them, so it stays out of every repo. A public test fixture is built from the track only; strip or never read object and building records (owner, 2026-11-13).
- **Reading the format is fine.** The AnyRail licence limits use of the software and claims nothing over output files, so a public reader raises no licence issue (owner, 2026-11-21). Do not flag it again.
- **Identify track by structure, not maker.** The layout uses Peco code 83 and some Walthers (including a double crossover), and AnyRail offers many makers (owner, 2026-11-19, after a brand filter dropped the Walthers double crossover). Track is any part with end point records; system names are read from the file; type comes from the end count and geometry (flex has curve points; four-end parts split into three-way, crossover, slip and diamond); catalog numbers are only a cross-check. Record tags differ per file, so never hardcode them.
- **Tests use small synthetic plans.** Plan files stay private. Ask the owner for one with other makers' parts when a test needs it.
