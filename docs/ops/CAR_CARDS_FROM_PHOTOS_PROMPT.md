# Make your own car cards from photos

This prompt has an AI coding agent build you a tool for car and locomotive cards. You give it a folder of phone photos of your cars. It crops and straightens each one, reads the reporting marks and number, and puts every photo on a review sheet that you check in your browser. Once you approve the sheet, it prints poker-size cards, nine to a sheet. Each card shows the photo, the road name, the number and a short description.

It is the same workflow we use for our fleet, described on [Car cards from photos](https://www.hartrailroad.com/ai/operations.html#cards). The prompt leaves out the steps that send our cars on to JMRI Operations Pro, our traffic simulator and our website.

## What you need

- An AI coding agent that can read and write files and run commands on your computer, such as Claude Code, Cursor or Codex. A chat window is not enough, because the agent has to run the tool and look at the photos.
- Python 3, and [Tesseract](https://github.com/tesseract-ocr/tesseract) for reading text. Ask the agent to install them if you don't have them.
- Photos of your cars taken the same way every time: side-on at about car height, on a short piece of track, in front of a plain grey backdrop.
- Card stock. We print on poker-size sticker sheets, nine to a US-letter page. Change the size and the 3×3 grid in the prompt if yours is different.

## How to use it

1. Make an empty folder and open the agent in it.
2. Paste the prompt below. Change anything in it that doesn't fit your railroad first: card size, logo, form number, car types.
3. The agent shows you its plan before it writes any code. After that it stops at the end of each stage and tells you what to check. Look at the crops and the review sheet carefully. Lettering on model cars is hard for a computer to read, so expect to correct some numbers.
4. Start with a batch of five to ten cars of one type. When those print well, do the rest of the fleet.

## The prompt

```text
Build me a small Python tool that turns photos of my model railroad cars and
locomotives into printable equipment cards. Work in stages. Nothing moves to
the next stage until I approve the one before it, and every stage ends with
something I can look at.

SETUP
- Python 3 with a .venv. Use Pillow, numpy, scipy, opencv-python, pytesseract
  (with Tesseract installed) and python-docx.
- One command, bin/cars, with the subcommands below.
- Folders: photos/incoming/ (my phone photos; names like IMG_1234 are fine),
  batches/<name>/ (one folder per batch), images/final/ (approved card
  images), data/cars.csv and data/locos.csv (the records), output/ (print
  files).

HOW I TAKE THE PHOTOS
Each car sits on a short piece of track in front of a plain grey backdrop,
shot side-on at about car height. Below the track is a darker strip of
table.

STAGE 1: REVIEW (bin/cars review [--batch NAME])
For each new photo:
- Crop and straighten it. The crop ends at the track, so the table strip is
  left out. Keep a margin around the car. Cut the crop to the shape of the
  card's picture.
- Read the reporting marks and road number with OCR, on the finished crop.
  Lettering on model cars is often low-contrast (gold on silver, white on
  grey), so as well as plain brightness try a colour difference such as red
  minus blue, and keep whichever reads best.
- Measure sharpness (variance of the Laplacian) and flag blurry photos.
- Every photo starts as a car. A file whose name starts loco_ or engine_
  starts as a locomotive.
- Write batches/<name>/review.csv, one row per photo, with these columns:
  photo, kind (car or loco), reporting_marks, road_number, car_type,
  length_ft, description, crop, ocr_text, blur, flags, ai_note, status
  (pending, approved, rejected or recorded).
- Flags: blurry, no-number, no-marks, number-length (a different number of
  digits from the rest of the batch), duplicate (the same car twice in the
  batch, or already in data/), crop-fallback, maybe-loco, ai-disagrees.
- Write batches/<name>/review.html, a contact sheet I open in a browser:
  each crop beside its fields. Every field is editable and status is a
  drop-down. Add a "Download review.csv" button.
- Give each photo an "Adjust crop" button. It opens a picker where I drag,
  zoom and rotate inside a frame the shape of the card picture, and it saves
  the box as X,Y,W,H,ANGLE in the crop column.
- Never overwrite a batch. To redo one, I use a new name.

STAGE 1B: YOUR CHECK (when I ask for it)
Look at each crop yourself and read the reporting marks, number and car
type (boxcar, hopper, tank car, flatcar, locomotive and so on) as printed on
the car. Write a JSON file shaped {photo: {marks, number, type, note}}, and
build bin/cars ai-notes <batch> <file> to merge it into the sheet. Your
reading is only a suggestion: never change the OCR columns or the status.
Where you disagree with the OCR, add ai-disagrees. Where you think a car is
a locomotive, or a locomotive is a car, add ai-says-loco or ai-says-car.

STAGE 1C: MY CORRECTIONS
- bin/cars sheet-import <batch> <downloaded review.csv> loads my browser
  edits, works out the flags again and re-cuts any crop I changed.
- bin/cars fill <batch> --set car_type=Hopper --set reporting_marks=CSX sets
  a column on every row, for a batch of one kind of car. It then fills each
  row's empty details from the best row in the batch and lists any row that
  disagrees.
- bin/cars kind <batch> loco IMG_1.png IMG_2.png switches photos between car
  and loco.
- bin/cars approve <batch> approves every row with no flags. It refuses
  while any row has no AI note, unless I add --no-ai. I approve or reject
  flagged rows myself.

STAGE 2: RECORDS (bin/cars records <batch> [--dry-run])
Add approved cars to data/cars.csv and approved locomotives to
data/locos.csv. Copy each approved image to images/final/<ID>.png, where
the ID is the marks and number with no spaces. Mark those rows recorded and
write a manifest.csv in the batch folder. Refuse while any row is still
pending. A photo can't give a locomotive's model, length or builder, so add
bin/cars locos set "<ROAD NUMBER>" model=... length_ft=... builder=... and
bin/cars locos status, which lists what each locomotive still needs.

LOCOMOTIVE PICTURES
Don't use the car crop on locomotives: it crops them too tight, tilts them
and overexposes them. Write loco_backdrop.py instead. It takes an upright
photo and a box I draw by eye around the loco and track, with a margin.
- Leave the loco and track exactly as photographed: no rotation, no
  exposure change.
- Find the loco as the largest area that isn't the backdrop's colour.
- Replace everything else with a smooth, neutral grey gradient fitted to
  the original backdrop, and add a soft shadow under the track.
- Take a --target grey so every locomotive comes out on the same backdrop.
The two units of a pair should face opposite ways.

STAGE 3: CARDS (bin/cars cards [--mark-printed] [--all])
Build one .docx of poker-size cards (about 2.5 x 3.5 in), nine per US-letter
page in a 3x3 table that lines up with a poker sticker sheet. Each card has:
- a small railroad logo at the top left (assets/logo.png, or an empty box
  if there is none);
- the equipment type in bold capitals at the top right (HOPPER, BOXCAR,
  LOCOMOTIVE);
- the photo, taking up about half the card;
- three labelled lines, each with a small line icon: ROAD NAME, ROAD NUMBER
  and DESCRIPTION. The description is short, such as "Covered hopper ·
  40'" or "SW1200 · 45' · EMD";
- a footer with a form number and revision, such as "Form CC-001 Rev A".
Style it like modern railroad operating paperwork: plain sans-serif type,
bold condensed headings, black and white only, a heavy outer border, thin
inner lines, light grey shading on the header and footer only, and nothing
that prints badly on a laser printer.
By default, build only the cards not yet printed. --mark-printed records
them as printed once I've printed them, and --all builds the whole fleet.
Locomotive cards come from data/locos.csv in the same way.

TESTS
- A reference test: the card for one known car must match a saved copy.
- Unit tests for building the ID, the flag rules, the description and the
  checks that stop a stage running before the one before it is approved.

Before you write any code, show me your plan and the review.csv columns.
After each stage, stop and tell me what to check.
```

## Notes from our runs

- Our OCR settings were tuned on one batch of hoppers with stencilled lettering. On other cars the OCR may read nothing at all. The AI check and your own corrections on the review sheet make up for it.
- Use the crop picker on photos that came out wrong. If a whole batch crops badly, ask the agent to fix the crop code instead.
- Locomotives get their road and number from the photo, and that's all. You type in the model, length and builder.
- The agent decides how to word each description, such as when a hopper counts as covered. If your railroad has its own conventions, list them in the prompt.
