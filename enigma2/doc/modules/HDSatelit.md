# HDSatelit/: the resources of the HDSatelit theme

This note is kept in `doc/modules/` and not inside `HDSatelit/`, because parts of that folder are copied whole to
the receiver.

## What is in the folder

- `skin.xml`: the HDSatelit FHD theme (1920x1080): colours, fonts, windows and the screens of the image.
  Its header names Monea Software for HD Satelit as the owner; the theme is declared closed in its build recipe
  for now (see `README.md`).
- `meniu/alb/`, `meniu/deschis/`, `meniu/inchis/`: the menu icons in three colours (made from Google Material
  Symbols, Apache License 2.0); `meniu/dala/`: the frames of the menu tiles at each text size. The tile menu is
  drawn by `lib/python/Components/HdsDale.py`.
- `liste/`, `navigator/`, `retea/`, `icon/`, `icons/`, `bar/`, `bs/`, `epg/`: the pictures of the channel list and
  the other lists, of the file browsers, of the network icon in the bars, of the volume and mute windows, of the
  bars and of the programme guide.
- `fonts/`: the theme fonts `Hds*.ttf` (Open Sans and Noto, SIL Open Font License 1.1, `OFL.txt`).
- `afisaj-color/`: the pictures of the colour front display (LCD) of the receivers that have one: `480x320/` and
  `400x240/` (robot face, states, icons), `orbita/` (the "Orbita" layouts for 400x240, 480x320 and 800x480, each
  with a `manifest.json`) and `fonturi/` (Noto Sans, OFL). They are drawn by
  `lib/python/Components/HdsAfisajColor.py` and `HdsAfisajRandare.py`.
- `display/skin_display.xml`: the skin of the colour LCD at 480x320.
- `hds_bootlogo.py`, `bootlogo_osd.py`: the HD Satelit boot logo and its on-screen overlay.
- `hds_rc*.png`, `picon_default.png`, `prev.png`: the drawn remote control and the default channel logo.

## How it reaches the receiver

- `Makefile.am` at the root copies `afisaj-color/` whole into `/usr/share/enigma2/HDSatelit/afisaj-color/` (and lists
  it in `EXTRA_DIST`); `data/Makefile.am` installs `display/skin_display.xml`.
- The theme as a whole is installed on the receiver by the `hdsatelit-skin` package, made by its own recipe in the
  build layer of the image.
- The other folders of the image find these files under `/usr/share/enigma2/HDSatelit/` (for example
  `Components/HdsDale.py`, `HdsFontInterfata.py`, `HdsFundalPro.py`).

`FILES.md` says, for each file, whether it is ours or comes from another project (fonts, icons).
