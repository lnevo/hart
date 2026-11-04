# Sending STS car moves to JMRI

When you run a session on STS, JMRI Operations Pro can show the same railroad:
every car where STS has it, with the same load and the same next stop. JMRI's
car roster, manifests and CATS then match the session. STS is the master; JMRI
is refreshed from it (ADR-016).

## Before a session

1. Start JMRI on the Pi as usual. The deploy puts `sts_car_sync.py` in its
   Start Up, and the JMRI web server is already on.
2. In STS, open **Operations → Send Cars to JMRI**. The top box should say
   **Ready**. If it says JMRI is not answering, JMRI is closed or its web server
   is off. If it says the script is not running, deploy to the Pi and restart
   JMRI.

## Refreshing JMRI

Use either:

- **The Operations button.** **Preview** shows what JMRI would change, car by
  car. **Send to JMRI** makes the change and saves Operations in JMRI.
- **The workflow step.** In the session editor, add **Send Cars to JMRI**
  (under *During*) after the steps that move cars, or at the end of the session.
  It runs with the session. If JMRI is off, the step is skipped and the session
  carries on.

Sending twice is harmless: the second send changes nothing.

## What to look at in the preview

- **Not sent.** `Unavailable` cars, and cars with no STS location. Out of
  service still reaches JMRI through `bin/cars publish`.
- **"JMRI would refuse it on …".** STS has the car on a track JMRI does not
  allow for that car type. The car goes where STS has it anyway. Fix the car in
  STS if it is a slip. As of 2026-11-03 there are three: BO 11027 and BO 11137
  (coke hoppers at Aristech Chemical Unload) and NW 12986 (at Shenango).
- **"left alone by JMRI".** The car is on a built JMRI train. Terminate or reset
  that train in JMRI and send again.

## After the session

JMRI has saved the new car state into the Pi's Operations files. Run
`make ops-pull` and commit before the next deploy, or the deploy replaces it
(ADR-015).

## Reference

- Plugin, settings and the full STS-to-JMRI table:
  `external/sts-plugins/plugins/jmri_ops/README.md`
- Name map: `external/sts-plugins/plugins/jmri_ops/maps/hart.json`
- STS setting: `external/sts-docker-data/config/jmri_ops.json` holds the JMRI
  url, `http://minipc-e5h6x.local:12080` for the Pi
- JMRI side: `jmri/layouts/hart/scripts/sts_car_sync.py`, tested by
  `jmri/layouts/hart/scripts/tests/test_sts_car_sync.py`
