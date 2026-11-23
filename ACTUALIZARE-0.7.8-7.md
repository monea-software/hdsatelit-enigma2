# HD Satelit 0.7.8: actualizarea 7 din meniu, ZGEMMA H8.2H SE

Actualizarea 7 a imaginii 0.7.8 aduce un singur pachet nou: `gstreamer1.0-plugin-dvbmediasink` 1.0+git256+66ff8280+66ff8288da-r1.hds4.1, numai pentru
ZGEMMA H8.2H SE (mașina `h8se`). Pachetele actualizării 6 (`enigma2-hdsatelit` r2 pe H8.2H SE și H8.2H Plus, în
`ACTUALIZARE-0.7.8-6.md`) și celelalte pachete ale feedului rămân.

Pachetul e făcut de rețeta `gstreamer1.0-plugin-dvbmediasink` a mediului OE-Alliance, cu aceeași sursă ca în imaginea 0.7.8, și
cu `meta-local/recipes-local/gstreamer/gstreamer1.0-plugin-dvbmediasink.bbappend` de aici: peticele de până acum și, numai pe
`h8se`, peticul `files/0005-dvbvideosink-continue-dupa-play.patch` și `.1` în plus la `PR`. Reparația: pe driverul acestui
receptor, o comandă `VIDEO_PLAY` primită după `VIDEO_FREEZE` lasă decodorul oprit până la un `VIDEO_CONTINUE`; când formatul
imaginii ajunge la `dvbvideosink` abia după trecerea în redare (filme și fluxuri fără sunet, sau cu sunetul venit târziu), redarea
pornea fără imagine. Peticul trimite `VIDEO_CONTINUE` după `VIDEO_PLAY` când elementul e deja în redare.

Față de eticheta `v0.7.8-h8r2` se schimbă numai rețeta dvbmediasink din `meta-local/` (bbappend-ul și peticul 0005) și acest
fișier; `enigma2/`, `skin/`, `LICENSE` și `README.md` sunt cele ale versiunii 0.7.8.

Construirea pachetului: pașii din `README.md`, cu `make MACHINEBUILD=zgemmah8se DISTRO=hdsatelit init` și
`bitbake gstreamer1.0-plugin-dvbmediasink` în loc de `bitbake hdsatelit-image`. Rezultatul:
`tmp/deploy/ipk/h8se/gstreamer1.0-plugin-dvbmediasink_1.0+git256+66ff8280+66ff8288da-r1.hds4.1_h8se.ipk`.

# HD Satelit 0.7.8: menu update 7, ZGEMMA H8.2H SE

Update 7 of the 0.7.8 image brings a single new package: `gstreamer1.0-plugin-dvbmediasink` 1.0+git256+66ff8280+66ff8288da-r1.hds4.1, only for the
ZGEMMA H8.2H SE (machine `h8se`). The packages of update 6 (`enigma2-hdsatelit` r2 on the H8.2H SE and H8.2H Plus, in
`ACTUALIZARE-0.7.8-6.md`) and the other packages of the feed stay.

The package is built by the `gstreamer1.0-plugin-dvbmediasink` recipe of the OE-Alliance environment, with the same source as
in the 0.7.8 image, and with `meta-local/recipes-local/gstreamer/gstreamer1.0-plugin-dvbmediasink.bbappend` here: the earlier
patches and, only on `h8se`, the patch `files/0005-dvbvideosink-continue-dupa-play.patch` and an extra `.1` in `PR`. The
fix: on the driver of this receiver, a `VIDEO_PLAY` command received after `VIDEO_FREEZE` keeps the decoder stopped until a
`VIDEO_CONTINUE`; when the picture format reaches `dvbvideosink` only after playback has started (films and streams without
sound, or with sound arriving late), playback started without a picture. The patch sends `VIDEO_CONTINUE` after
`VIDEO_PLAY` when the element is already playing.

Compared with the `v0.7.8-h8r2` tag only the dvbmediasink recipe in `meta-local/` (the bbappend and patch 0005) and this file
change; `enigma2/`, `skin/`, `LICENSE` and `README.md` are those of version 0.7.8.

Building the package: the steps in `README.md`, with `make MACHINEBUILD=zgemmah8se DISTRO=hdsatelit init` and
`bitbake gstreamer1.0-plugin-dvbmediasink` instead of `bitbake hdsatelit-image`. The result:
`tmp/deploy/ipk/h8se/gstreamer1.0-plugin-dvbmediasink_1.0+git256+66ff8280+66ff8288da-r1.hds4.1_h8se.ipk`.
