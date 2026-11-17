# Speed matching prompts

Two prompts to paste into an AI coding agent (Claude Code or similar) that can run commands
against a JMRI layout. Both are written so anyone can use them; nothing in them is specific to
one railroad.

1. [Measuring block lengths you do not know](#prompt-1-block-lengths-you-do-not-know): how the
   block lengths on our test loop were worked out from timed runs and one known loop length.
2. [Starting speed matching with AI](#prompt-2-starting-speed-matching-with-ai): requirements,
   prerequisites, safety rules and the steps, for a first speed-matching job.

## How the unknown lengths were done

The block table had lengths that were guesses. A speed is distance over time, so wrong lengths
give wrong speeds. Two things were known: the track plan gave the length of the whole loop the
loco runs around, and the plan showed where the turnouts are. It did not show where the block
gaps are.

- **Share of the lap.** At one throttle step, once the loco has settled, it runs at one speed.
  So the share of a lap's time it spends in a block is that block's share of the loop length.
  Block length = (time in block / lap time) x loop length. Taking the median over many laps,
  at steps 24 and up (of 126), for two locos running opposite ways, gave lengths with a spread
  of 1 to 4 cm per block.
- **Pinned to the turnouts.** The turnouts are on the plan, so each turnout's detection section
  was placed on the plan's turnout centre, and the blocks between two turnouts share out the
  plan distance between them by time. Pins closer together than about half a metre were left
  out, because a few cm of gap placement turns into a large error over a short stretch.
- **Track that is not on the plan.** A crossover and an engine terminal were built after the
  plan. For those, the loco ran at a steady step between two pinned turnouts, and the time to
  each unknown section placed it along that stretch. Two passes at different steps agreed
  within 27 mm. A larger difference would have meant the loco was still speeding up.
- **Checks.** With the new lengths, each block's speed should come out close to the loop
  average. The lengths of the long blocks agreed within 1% between the two directions, so
  grades did not bias them much; short turnout sections differed by up to 15% (about 5 cm).
- **Detection quirks.** Current detection lets a standing loco read free (keep its lights on),
  a block can light again behind the loco, and the first two readings after a step change are
  thrown away.

Each length carries where it came from (plan, inferred, tape) so later work knows which ones
to trust.

---

## Prompt 1: block lengths you do not know

```text
I want to measure the lengths of the detection blocks on my model railroad using timed runs,
because I do not have reliable lengths. I use JMRI. Work with me step by step and show me your
plan before anything moves.

What I have (fill in):
- A closed loop the loco can run around without stopping, with block detection on: <list of
  blocks/sensors in running order, or ask me to export them from the JMRI block table>
- One known length: <the whole loop length from my track plan (AnyRail, XTrackCAD, SCARM...),
  or one block measured with a tape>
- Turnout positions on the plan, if I have them: <yes/no>
- Detection type: <current sensing / optical / RailCom / other>
- How you can reach JMRI: <JMRI web/JSON server, a jython script I load, or a file you drop
  into a watched folder>

Method I want:
1. Record every sensor change with a timestamp while one loco runs laps at a fixed throttle
   step. Warm the loco up first (a few laps) and throw that data away. Throw away the first
   two sensor events after any step change.
2. For each lap, each block's length is (time in that block / lap time) x the known loop
   length. If I only have one taped block, scale from that block instead. Use the median over
   laps, and only steps where the loco runs steadily (not creep steps). Run both directions,
   and a second loco if I have one, and report the spread per block.
3. If turnout positions are on the plan, pin each turnout's detection section to the plan's
   turnout centre and share out the plan distance between neighbouring pins by time. Skip
   pins that are very close together.
4. For track that is not on the plan, do timed passes at two different steps between two
   known points and locate the unknown sections along that stretch. If the two passes disagree
   by more than a few cm, the loco was not at steady speed: start it further back.
5. Check the result: recompute each block's speed with the new lengths; each should be close
   to the loop average. Show me any block that is not.
6. Give me a table of block, length in mm and inches, spread, and where each length came from
   (plan, inferred, tape). Do not change my JMRI tables until I say so, and only with PanelPro
   closed.

Watch for: a standing loco reading free (lights or sound keep current flowing), a block
lighting again behind the loco, hidden stub tracks that share a detector with a visible block,
and grades that change speed within a lap.

Safety: only one loco moves. Stop it with its own throttle at speed 0. Never use emergency
stop on all locos, never switch track power, never throw turnouts unless I ask. Give me a way
to stop a running job at once.
```

---

## Prompt 2: starting speed matching with AI

```text
I want to speed match the locomotives on my model railroad with your help, and write measured
speed profiles into their JMRI roster entries. Before doing anything, check the prerequisites
below with me, ask me what is missing (several questions at a time, multiple choice where you
can, your recommendation first), then show me a plan and wait for my yes.

Requirements (ask me about each):
- JMRI version, and the command station and how JMRI connects to it.
- Can the command station program on the main (POM)? Is there a programming track?
- A detected loop where one loco can run laps without stopping, and the list of its blocks in
  running order.
- Block lengths, and where they came from (plan, tape, guess). If they are guesses, we measure
  them first (I have a separate prompt for that).
- A roster entry for each loco, with the right address and long/short flag, and decoder make.
- How you can run things in JMRI: the JMRI web/JSON server, a jython script I load, or a file
  you drop into a folder JMRI watches.
- Which loco is the reference (not changed) and which are matched to it, and whether they run
  as a consist, which way each one faces, and which one leads.

Prerequisites before the first run:
- Read each decoder on the programming track and save the values: CV2 to CV6, CV25, CV29,
  CV66, CV67 to CV94, CV95 and the back-EMF CVs. Compare them with the roster and stop if
  they differ.
- Settle back-EMF first. Check that the speed table is switched on where it should be (CV29
  bit 4, CV25). Tell me about known traps for my decoder brand.
- Clean track and wheels. Only the test loco on the loop. I am not operating while it runs.

Safety rules (do not relax these without asking me):
- Only the test loco moves. Stop it with its own throttle at speed 0. Never emergency-stop
  everything, never switch track power, never throw turnouts unless I ask.
- Every decoder write goes through one small guard: the address comes from the roster only;
  refuse address 0 (broadcast), a short address outside 1 to 127, an address shared by two
  roster entries, or a loco in an active consist (break the consist first). Allowed CVs only
  (3, 4, 25, 66, 67 to 94, 95); never CV1, CV8, CV17 to 19, and CV29 only on the programming
  track.
- Writes are a dry run by default and print address, CV, old and new value. Save a rollback
  file before any real write.
- A kill switch I can use at any time, and a log of every step, sensor event and write.

Measuring:
- Warm up (about 3 laps or 60 s at a middle step), discarded.
- Steps such as 8, 16, 24, 32, 48, 64, 96 and 126 (add creep steps 2 to 6 if I want them),
  then 126 again at the end to check drift.
- Speed over known block lengths, not whole laps: every block at low steps, spans of a few
  blocks at high steps. A step ends when the last 5 readings agree within 2% or after 12
  readings; report their median.
- Both directions. For a consist, compare the locos in the directions they actually run in
  it (the trailing loco is often reversed).

Matching:
- Agree a tolerance with me first. Run-to-run repeat is often about 2%, more at slow steps,
  so about 5% is a fair target; tighter chases noise.
- Change only the matched loco. Propose the changes (trims CV66/CV95, speed table entries,
  start voltage), write them on the main through the guard, measure again, and repeat until
  every step is within tolerance or a set number of rounds.
- Match momentum (CV3, CV4) too: start each loco from rest, send speed 0 at the same sensor,
  and compare where and when each stops.

Finishing:
- Write the measured speeds into each roster entry's speed profile (JMRI Dispatcher and
  warrants use them for stopping), then read the decoders back on the programming track and
  update the roster.
- Remake the consist and test it as a pair.
- Write me a short record: what was measured, what changed (old and new CV values), the
  result table, and anything left to do.
```
