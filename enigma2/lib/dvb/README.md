# lib/dvb

The DVB core of enigma2 in C++: the tuners (`frontend.cpp`, `sec.cpp` for LNB, DiSEqC and motor), the demux and
the sections, the channel database (`db.cpp`, the `lamedb` file), the scan (`scan.cpp`), the PMT and the decoders
(`pmt.cpp`, `decoder.cpp`), the programme guide (`epgcache.cpp`), teletext, subtitles and the clock from the
transponder (`dvbtime.cpp`). Python reaches it through SWIG (`lib/python/enigma_python.i`).

## What we changed in the 2011 files

The biggest changes (see `FILES.md` for the full list) are in `frontend.cpp` (DVB-S2 multistream and PLS, T2-MI,
DVB-T/T2 and cable, the dish motor), `sec.cpp` (motor, Unicable I and II), `epgcache.cpp` (guide import, `epg.dat`,
the guard at the exit of the interface), `pmt.cpp` (the HbbTV application table), `scan.cpp` (network table,
terrestrial scan, multistream) and `db.cpp` (multistream and T2-MI fields in `lamedb`, old non-UTF-8 names), and in
`demux.cpp` and `decoder.cpp` (the HiSilicon boards, `HAVE_HISILICON`, and their platform library).

## Added files

Most added files (`hds*`) are written by HD Satelit; `hdsvtuner.cpp/.h` is based on the OE-Alliance enigma2 code and
the SoftCSA files come from the authors named in their headers. `FILES.md` gives the origin of every file. Each file
says in its first lines what it does; much of the logic is in headers with pure functions, so that it can be tested
on a PC without enigma2.

- Tuning and signal: `hdsmultistream.h` (DVB-S2 stream and PLS), `hdsterestru.h` (DVB-T/T2 system and PLP),
  `hdsstatdvb5.h` and `hdscalitate.h` (signal level and quality), `hdscitirifrontend.h` (one tuner reading per
  second shared by all readers), `hdst2mi.h` (tuner choice for T2-MI), `hdstipales.h`, `hdsunicable.h`,
  `hdsvtuner.cpp/.h` (USB DVB tuners through vtuner, based on the OE-Alliance enigma2 code).
- Dish motor: `hdsrotire.cpp/.h` (motor turned on 18 V on tuners that cannot measure the motor current),
  `hdsurmamotor.cpp/.h` (trace of the motor commands).
- Scanning: `hdsfastscan.cpp/.h` and `hdsfastscantabele.cpp/.h` (FastScan of the M7 operators), `hdsretea.cpp/.h`
  (what the NIT says, for `/api/scanare-ultima`), `hdsgrad.h`, `hdslistetext.h`.
- HbbTV and teletext: `hdsait.cpp/.h` (the AIT, application table), `hdsteletext.cpp/.h` (whole teletext pages).
- Sound: `hdsspectru.cpp/.h` (sound level on 32 bands from the compressed frames, for the radio screen).
- Logs: `hdsjurnaltuner.cpp/.h`, `hdsjurnaldecodor.cpp/.h` (tuner and decoder logs, same format as
  `lib/base/hdsjurnal.h`).
- Guards: `hdspazademux.cpp/.h` (the one record channel per demux of the HiSilicon driver), `hdspazavideo.h` (writes
  on video0 and audio0), `hdspazaphi.h` (audio delay writes on the boards with libreader), `hdscedare.h` (channel
  uses that give way to a zap), `hdsepgpoarta.h` (guide importers against the cache being destroyed at exit).
- SoftCSA (software descrambling of CSA-ALT, authors named in the headers): `csaengine.cpp/.h`, `csasession.cpp/.h`,
  `cwhandler.cpp/.h`, `cahandler.cpp/.h`.

`Makefile.am` lists the sources; the Python side of most of these is in `lib/python/Components/Hds*.py`.
