# Camera car identification (proposal)

Status: idea only, written 2026-11-16. Not scheduled and not on the to-do list. Nothing here is built.

A few camera checkpoints read each car as it passes, by its printed number and by how it looks, and report the car ID to JMRI. No tags, stickers or markers go on the cars. The cars only need a reference photo of each side.

## Why cameras instead of RFID

| | RFID tags | Camera, number plus look |
|---|---|---|
| Work on each car | Glass tag fitted underneath | Two reference photos |
| Cost per checkpoint | About $30 per reader | About $150–250 |
| Reliability | Same answer every time | Depends on lighting, speed and legible numbers |
| Hidden track | Works anywhere | Needs controlled lighting |
| Extra output | ID only | Car order, direction, train length, a photo of every car |

Reading the printed number alone is not reliable in HO. Reporting marks are 1–2 mm tall, and weathering, fonts and motion blur all cause misreads. The design below makes up for that by checking two things and comparing them with the train the operating software expects.

## How it works

1. **Reference photos.** Each car gets a side photo from both sides, taken the same way as the intake photos. A small pretrained image model turns each photo into a short fingerprint of the car's look. The fingerprints are stored with the car's road number.
2. **Recording.** Motion detection starts recording when a train reaches the checkpoint. The software splits the train into one image per car, using the gaps at the couplers.
3. **Two readings per car.**
   - OCR reads the reporting marks and number from several frames and keeps the most common reading.
   - The car's image is fingerprinted and compared with the reference fingerprints.
4. **Narrow the choices.** The checkpoint matches against the cars Operations Pro or STS expect in that train, in that order, not against the whole fleet. Matching 15 cars against a list of 15 is a much easier problem than matching against every car on the railroad. The readings confirm the list or flag what does not fit.
5. **Report.** For each car: road number, confidence and the photo crop. A confident match is reported to JMRI. A low-confidence one goes on a "check these" list that the operator confirms on the panel or in STS. The checkpoint never changes car records on its own.

## Known weak spots

- **Look-alike cars.** Groups of identical cars, such as the hoppers, look the same, so only OCR separates them. Those cars need a clean number on the side the camera sees. A second camera on the far side of the track doubles the chances. If they still fail the test, RFID tags on those cars alone is the fallback.
- **Hidden staging and the helix.** Cameras there need their own even lighting. Infrared lighting loses car colour, which weakens the look comparison, so checkpoints go where white light can be added.
- **Speed.** A global shutter camera and a short exposure avoid blur. Checkpoints go where trains run slowly: staging throats and yard leads.

## Hardware for one checkpoint

| Part | Note |
|------|------|
| Raspberry Pi 5 (4 or 8 GB) | One Pi can serve two cameras |
| Raspberry Pi AI accelerator (Hailo) | Runs the image model for each car quickly |
| Raspberry Pi Global Shutter Camera, 1 or 2 | Lens chosen for a 10–15 cm working distance |
| LED light bar, diffused | Even light; steady and flicker-free at the camera's frame rate |
| Plain backdrop opposite the camera | Separates the cars from scenery behind them |

Rough cost $150–250 per checkpoint. Candidate places: staging entry and exit, and the yard lead.

## Software

- Python service on each checkpoint Pi: `picamera2` for capture, OpenCV for motion detection and splitting the train into cars, an OCR engine (PaddleOCR or similar) and the image model on the accelerator.
- A reference-photo tool that builds the fingerprint file from the car photos. The fingerprint file is the only per-car data.
- The expected consist comes read-only from Operations Pro or the STS API.
- Output goes to the broker as a stock JMRI MQTT reporter (`track/reporter/<checkpoint>`) with the road number as the payload. Operations Pro cars carry it in their RFID field. The checkpoint only reports and never publishes `track/cmd`.
- Every pass is saved as an image strip, kept for a while for checking moves after a session.

## First test

Bench test before building anything for the layout:

1. One checkpoint on a test track, with lighting no better than the layout's.
2. 30 cars, including the look-alike hoppers, with reference photos taken.
3. Record runs at operating speed in both directions.
4. Score three methods on the same recordings: OCR alone, look alone, and both together with the expected list.

The design works if both together with the expected list gets close to 99% correct and flags the rest rather than guessing. If only the look-alikes fail, tag those with RFID and keep cameras for the rest.

## Open questions

- How many cars already have usable side photos from intake.
- Which checkpoints are worth the cost, and whether hidden staging can be lit.
- Whether a pass should update car location in STS automatically after operator review, or only show on the panel.
