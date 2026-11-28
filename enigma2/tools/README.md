# tools

Programs and scripts that are built or installed with the interface, plus the tools used on a PC. `Makefile.am`
lists exactly what is built and installed (`bin_SCRIPTS`, `bin_PROGRAMS`, `EXTRA_DIST`); the other files stay in the
source.

## Installed on the receiver

- `enigma2.sh.in`: the start script of the interface: the checks before each start, the safe mode after repeated
  unclean ends (`Components/HdsModSigur.py`), the fallback below.
- `hds-blindscan.c`: the blind scan on the satellite tuner, a separate process started on demand by
  `lib/python/Components/HdsCautareOarba.py` (screen `Screens/ScanerOarba.py`, web page `/oarba`); on boards where it
  does not know the tuner path it refuses and touches nothing.
- `hds-rezerva.sh.in`, `hds-rezerva-ecran.py`: what the receiver shows when enigma2 does not reach its interface: a
  picture on the TV and a web page, made without enigma2.
- `hds-raport.sh.in`: the steps of every start and the technical report of a start that failed, with BusyBox only.
- `hds-actualizare-intrerupta.py`: at start, finishes a package update that was stopped half way.
- `hds-wifi-reporneste.py`: restarts the chip of a USB Wi-Fi card, as if the stick were taken out and put back.
- `hds-nume-local`, `hds-nume-local.py`: publish the local name of the receiver (`hdsatelit.local`) on the home
  network; installed by the `hdsatelit-nume-local` package, so they are only in `EXTRA_DIST` here.
- `libopen.c`: the small library from 2011 that is preloaded with enigma2.

## Used on a PC

- `file_origins.py`: writes `FILES.md`, the list of the files of this tree by origin (unchanged from the enigma2
  base, modified, added from other sources, added by HD Satelit). Run it, and commit `FILES.md`, before every
  version tag; `--check` says whether the committed list is up to date.
- `hds-rezerva-litere.py`: makes the letter table of the fallback picture from `data/fonts/DejaVuSansMono-Bold.ttf`.
- `genmetaindex.py`, `svg2skin.py`, `convert_argb_png.c`, `create_picon_links.py`, `host_tools/`: the helpers from
  2011 (plugin index, skin and picture conversion, picon links, satellite list converter).
