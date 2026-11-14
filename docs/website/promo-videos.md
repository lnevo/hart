# Promo videos

Short videos that advertise www.hartrailroad.com on TikTok and YouTube, made
2026-11-14.

## The videos

All four live in `media/promo/` (the gitignored media mirror, not in git).

| File | Format | Length | Sound | Post to |
|------|--------|--------|-------|---------|
| `hart-promo-build.mp4` | 1080x1920 | 27.8 s | silent | TikTok, Reels, YouTube Shorts |
| `hart-promo-site.mp4` | 1080x1920 | 25.9 s | silent | TikTok, Reels, YouTube Shorts |
| `hart-promo-build-youtube.mp4` | 1920x1080 | 27.8 s | original soundtrack | YouTube |
| `hart-promo-site-youtube.mp4` | 1920x1080 | 25.9 s | original soundtrack | YouTube |

- **Build cut:** "This room was empty." Empty room, quick build cuts, the
  finished layout, the schematic drawing itself, the USS CTC panel, the site.
- **Site cut:** "My model railroad has its own website." A rapid-fire tour of
  the four sections (Prototype, Operations, Behind the Scenes, The Diverging
  Route), one title slam per section and a shot of a page's best feature on
  every beat.

The vertical files are silent on purpose: add a sound from TikTok's own library
when posting. The YouTube files carry an original soundtrack made by
`tools/promo/soundtrack.py` from oscillators and noise. It has no rights holder
and nothing for Content ID to match. Loudness is -14 LUFS.

Left out on purpose: the photo and video thumbnail with the Thomas-style engine
(a licensed character), the DJ's Trains video (someone else's), the 1975 coke
film and the prototype GIFs (rights unclear).

## YouTube description

```
I built a new website for my HO scale model railroad with help from AI. It brings together my research, development, track planning and construction in one place, with tools, ideas and the history of the railroads and industries of Neville Island, Pittsburgh.

🔗 https://www.hartrailroad.com

What's on the site:
• Prototype: the plants, railroads and a century of photos, ads and clippings from Neville Island
• Operations: car cards, waybills, crew sheets and station maps for operating sessions
• Behind the Scenes: the build, the wiring, the signals and the CTC panels
• The Diverging Route: how AI helped with research, track planning, wiring, scripts and paperwork

Follow along as the layout gets built.

#modelrailroad #modeltrains #hoscale #trains #pittsburgh #jmri #ai
```

## Rebuilding

```
.venv/bin/python tools/promo/tiktok_promo.py                              # vertical, both cuts
.venv/bin/python tools/promo/tiktok_promo.py --format landscape --music   # YouTube, both cuts
.venv/bin/python tools/promo/tiktok_promo.py --cuts site                  # one cut
```

Needs ffmpeg, Google Chrome and the root `.venv` (Pillow, numpy, scipy). Fonts
are in `tools/promo/fonts/` (Barlow Condensed, SIL OFL).

Material it reads:

- Layout photos from `media/photos-layout/`.
- The schematic and USS CTC evolution videos in
  `www/assets/behind/panel-evolution/`.
- Phone-width captures of live site pages in `media/promo/shots/`. A missing
  capture is taken again from the live site.

The site cut's shots are pixel offsets into those captures (`site_cut` in
`tiktok_promo.py`). When a page changes, delete its capture, rebuild, and check
the crops by pulling frames with ffmpeg. Headless Chrome on macOS will not lay
a page out narrower than about 500 CSS px, so captures are taken at 500 px and
2.16x, which gives 1080 px; a 390 px capture looks clipped but the site is fine.

The site cut runs on a 0.7 s grid (85.7 BPM) and its soundtrack expects that:
keep every shot at 0.7 s, or change the cue in `soundtrack.py` to match.
