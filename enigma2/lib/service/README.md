# lib/service

The services of enigma2 in C++: what can be played or recorded. `servicedvb.cpp` plays a DVB channel (live,
timeshift, recordings), `servicedvbrecord.cpp` records it, `servicemp3.cpp` plays files and internet streams through
GStreamer, `servicefs.cpp` lists folders, `listboxservice.cpp` draws the rows of the channel list, `event.cpp` holds
the programme events. Python reaches them through `eServiceCenter` and `iPlayableService`.

## What we changed in the 2011 files

- `servicemp3.cpp`: the GStreamer player for internet TV and films: subtitles (text, picture and WebVTT), seeking,
  internet radio, teletext.
- `servicedvb.cpp`: subtitles and teletext on DVB channels and in timeshift, radio channels, the SoftCSA
  descrambling loop (`softdecoder`) and the sound equalizer (`hdsegalizator`).
- `listboxservice.cpp`: the channel list rows (channel logo, progress bar of the current event, the encrypted mark).
- `servicedvbrecord.cpp`: recording of channels descrambled in software (SoftCSA).

## Added files

The `hds*` files are written by HD Satelit; the SoftCSA decoder loop comes from the authors named in its headers.
`FILES.md` gives the origin of every file.

- `hdsegalizator.cpp/.h`, `hdsegalizator_dsp.h`, `hdsegalizator_flux.h`: the equalizer for radio stations, done in the
  processor (Menu > Audio > Equalizer), with its sound processing and stream reading.
- `hdsfluxhttp.cpp/.h`, `hdshttp.h`, `hdshttporigin.h`: a live MPEG transport stream read over HTTP (a local relay or
  a server on the network) as the source of a playback channel, and the HTTP identity of each playback.
- `hdssubimagini.cpp/.h`: picture subtitles of films (VobSub, PGS); `hdssubtitrareceas.h`, `hdssubtitraresincron.h`:
  the clock and the synchronisation of subtitles on DVB services.
- `hdsjurnalzap.cpp/.h`: the zap log (`/home/root/logs/hds-zap.log`, same format as `lib/base/hdsjurnal.h`).
- `hdsreleut2.h`: recognises a channel played through the local T2-MI relay of the image (`lib/python/Hds/DabT2`).
- `hdssoftcsapornire.h`: when the SoftCSA loop starts early; `servicedvbsoftdecoder.cpp/.h` and
  `iservicescrambled.h`: the SoftCSA decoder loop (authors named in the headers).
- `hdsradioonline.h`, `hdsvorbire.h`: passive copies of the sound that is playing, for the radio analyser and the
  speech recognition; they change nothing in the playback.

`Makefile.am` lists the sources. The Python side is in `lib/python/Components/` (for example `HdsEgalizator.py`,
`HdsJurnalZapFlux.py`, `HdsSubtitrariFilm.py`, `HdsSoftCsa.py`).
