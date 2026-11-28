# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Optiunile sink-urilor receptorului, peste DVBMEDIASINK_CONFIG al masinii:
# - fara --with-wma: driverul nu are decodor WMA, deci sunetul WMA 1/2 nu se trimite comprimat placii; il decodeaza pe
#   procesor gstreamer1.0-libav (peste FFmpeg-ul LGPL al imaginii) si placa primeste PCM;
# - --with-aac-loas: AAC in LOAS/LATM (filme si fluxuri IPTV) merge la decodorul placii ca AAC HE, acelasi decodor care
#   reda AAC-ul canalelor. Sink-ul ia AAC numai cu profile=lc (si LOAS); AAC-ul refuzat (Main, SSR, LTP) il decodeaza in procesor
#   elementul faad, numai pe masinile care il au (Broadcom si ZGEMMA H8.2H Plus, packagegroups/hdsatelit-base.bbappend);
# - --with-vb6: VP6 (fisiere FLV vechi) la decodorul placii. Codul optiunii se atinge numai pentru fluxurile
#   video/x-vp6 si video/x-vp6-flash (caps-urile si STREAMTYPE_VB6 din gstdvbvideosink.c, in ramura comuna cu VP8, VP9
#   si Spark, deja pornite pe masina), deci celelalte formate raman neschimbate; driverul placii are decodorul VP6
#   (hi_vfmw.ko: VP6DEC_*, VP6F, VP6A).
# Constructia se opreste daca configure nu a primit optiunile (HAVE_AAC_LOAS, HAVE_VB6) sau daca HAVE_WMA a ramas.
DVBMEDIASINK_CONFIG:remove = "--with-wma"
DVBMEDIASINK_CONFIG:append = " --with-aac-loas --with-vb6"

# MI7 (15.11.2026): dvbvideosink citeste evenimentele video (marimea imaginii) si in bucla de dupa EOS (POLLPRI); fisierele
# TS scurte, servite repede pe HTTP, ramaneau fara marime (proba OCT pe SF8008). Peticul e facut pe sursa fixata in
# recipes-local/hds-dts-ac3/gstreamer1.0-plugin-dvbmediasink.bbappend (SRCREV 66ff8288) si atinge numai gstdvbvideosink.c.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI += "file://0001-dvbvideosink-evenimente-video-dupa-eos.patch"

# H.264 cu intrarea avc3 (filmele DVB-DASH, de pilda BBC; HbbTV): avcC fara SPS/PPS (parametrii vin in
# flux) lasa codec_data NULL si lungimea NAL 0, deci render nu punea start code si placa primea prefixele de lungime:
# imagine neagra cu sunet. Peticul citeste avcC si fara SPS (lungimea NAL, codec_data si gol, ca la H.265); ramura veche
# (un SPS si un PPS) neschimbata. Facut pe aceeasi sursa fixata (66ff8288), dupa 0001; atinge numai set_caps.
SRC_URI += "file://0002-dvbvideosink-avc3-fara-parametri-in-avcc.patch"

# IPR7 (22.11.2026): potopul "audio cursize ... > 01048576" / "video cursize ... > 33554432" din jurnalul nucleului
# (Viper 4K V20, driverul DVB HiSilicon) la filmele si fluxurile VOD date mai repede decat se reda. poll() pe audio0 si
# video0 raspunde POLLOUT si cu tamponul ES plin, write() e refuzat (EAGAIN sau 0) si sink-ul il relua imediat; driverul
# scrie un rand la fiecare refuz (~90 pe secunda, 11 minute la un film HLS, masurat pe receptor). Peticul asteapta dupa
# refuzurile la rand (n * 20 ms, cel mult 200 ms) pe pipe-ul de oprire, deci zap-ul si flush-ul raman pe loc. Facut pe
# aceeasi sursa fixata, dupa 0001 si 0002; intra cu fuzz 0 si inainte, si dupa peticul DTS -> AC3 din hds-dts-ac3.
# NUMAI pe u57 (Viper 4K V20), singurul driver pe care s-a masurat; pe celelalte placi (SF8008 HiSilicon fara printk,
# Broadcom cu poll care asteapta) se pune abia dupa o proba pe placa aceea.
SRC_URI:append:u57 = " file://0004-dvbsink-asteapta-dupa-scrierea-refuzata.patch"

PR:append = ".hds4"

do_configure:append() {
	h=${B}/config.h
	[ -f "$h" ] || h=${S}/config.h
	grep -q '^#define HAVE_AAC_LOAS 1' "$h" || bbfatal "dvbmediasink: lipseste HAVE_AAC_LOAS in $h"
	grep -q '^#define HAVE_VB6 1' "$h" || bbfatal "dvbmediasink: lipseste HAVE_VB6 in $h"
	if grep -q '^#define HAVE_WMA 1' "$h"; then
		bbfatal "dvbmediasink: HAVE_WMA e inca pornit"
	fi
}

do_compile:append() {
	grep -q 'video_event_post' ${S}/gstdvbvideosink.c || bbfatal "dvbmediasink: peticul evenimentelor video dupa EOS nu e aplicat"
	grep -q 'avcC without SPS (avc3)' ${S}/gstdvbvideosink.c || bbfatal "dvbmediasink: peticul avc3 (avcC fara SPS) nu e aplicat"
}

do_compile:append:u57() {
	grep -q 'dvbsink_refuz_asteapta(self->unlockfd\[0\]' ${S}/gstdvbaudiosink.c || bbfatal "dvbmediasink: peticul scrierii refuzate (IPR7) lipseste din dvbaudiosink"
	grep -q 'dvbsink_refuz_asteapta(self->unlockfd\[0\]' ${S}/gstdvbvideosink.c || bbfatal "dvbmediasink: peticul scrierii refuzate (IPR7) lipseste din dvbvideosink"
}

# SEF1 (23.11.2026): pe ZGEMMA H8.2H SE (driverul Airdigital h8se) un VIDEO_PLAY primit dupa VIDEO_FREEZE ramane inghetat pana la
# un VIDEO_CONTINUE. dvbvideosink nu face preroll, deci cand nimic nu face preroll inaintea lui (film sau flux fara sunet, ori un
# sunet care vine tarziu) caps-urile vin dupa PAUSED_TO_PLAYING, iar ordinea era FREEZE, CONTINUE, STREAMTYPE, PLAY: decodorul nu
# pornea, fara nicio eroare (proba pe receptor: 3 din 3 porniri fara imagine au pornit dupa o pauza si o redare). Peticul trimite
# CONTINUE dupa PLAY cand elementul e deja in PLAYING. Facut pe aceeasi sursa fixata, dupa 0001 si 0002; atinge numai set_caps.
# NUMAI pe h8se, singurul driver pe care s-a masurat.
SRC_URI:append:h8se = " file://0005-dvbvideosink-continue-dupa-play.patch"
PR:append:h8se = ".1"

do_compile:append:h8se() {
	grep -q 'VIDEO_CONTINUE after VIDEO_PLAY' ${S}/gstdvbvideosink.c || bbfatal "dvbmediasink: peticul CONTINUE dupa PLAY (SEF1) lipseste"
}

# ZGEMMA H8.2H Plus (h8, hi3716mv430): serverul media al platformei (pornit de modulul driverului, cu decodoarele din
# airdigital-libs) nu are drum pentru PCM. AUDIOTYPE_RAW si LPCM (DVD sau Blu-ray) sunt primite de audio0, dar tamponul se umple
# si nu se mai goleste (PTS 0), deci orice sunet decodat in procesor (FLAC, Vorbis, Opus, WMA, ALAC, TrueHD, AAC prin faad) era
# mut, iar redarea ramanea la a doua secunda. Peticul 0006 recodeaza audio/x-raw in MP3 (libmp3lame, deja in imagine prin
# gstreamer1.0-plugins-good-lame; 320 kb/s stereo, 160 mono) si il trimite placii ca AUDIOTYPE_MP3, cu PTS pe fiecare PES, deci
# sunetul ramane sincron cu imaginea si redarea ajunge la sfarsit. MP3 si nu AC3: in bibliotecile platformei AC3 apare numai ca
# trecere spre iesirea digitala (AC3PASSTHROUGH), fara decodor. Facut pe aceeasi sursa fixata, dupa 0001 si 0002 (si dupa peticul DTS -> AC3); atinge numai gstdvbaudiosink.c/.h,
# iar codul intra numai cu HDS_PCM_MP3. Pe h8 si pe h8se (blocul urmator), singurele drivere pe care s-a masurat.
SRC_URI:append:h8 = " file://0006-dvbaudiosink-pcm-recodat-in-mp3.patch"
CFLAGS:append:h8 = " -DHDS_PCM_MP3"
RDEPENDS:${PN}:append:h8 = " libmp3lame"
PR:append:h8 = ".1"

do_compile:append:h8() {
	grep -q 'hds-pcm-mp3' ${S}/gstdvbaudiosink.c || bbfatal "dvbmediasink: peticul PCM recodat in MP3 lipseste"
	grep -aq 'hds-pcm-mp3: codor deschis' ${B}/.libs/libgstdvbaudiosink.so || bbfatal "dvbmediasink: codul HDS_PCM_MP3 nu e in libgstdvbaudiosink.so"
}

# ZGP8 (0.8.0, H8V1 24.11.2026): peticul SEF1 0005 (VIDEO_CONTINUE dupa VIDEO_PLAY cand caps-urile vin in PLAYING) si pe h8:
# driverul Airdigital h8 se poarta ca h8se; masurat pe ZGEMMA H8.2H Plus cu gst-launch, film fara sunet: 0 din 8 porniri cu
# imagine fara el, 8 din 8 cu el. Pozitia in lant ca pe h8se (inainte de 0007 si 0008); 0006 atinge numai sink-ul de sunet.
SRC_URI:append:h8 = " file://0005-dvbvideosink-continue-dupa-play.patch"
PR:append:h8 = ".1"

do_compile:append:h8() {
	grep -q 'VIDEO_CONTINUE after VIDEO_PLAY' ${S}/gstdvbvideosink.c || bbfatal "dvbmediasink: peticul CONTINUE dupa PLAY (SEF1) lipseste pe h8"
}

# ZGEMMA H8.2H SE (h8se, hi3798mv200): acelasi lucru masurat pe receptor cu dvbmediasink-ul de acum (r1.hds4.1): un FLAC trimis
# placii ca PCM e mut si redarea sta la a doua secunda, iar AAC-LC (decodat de placa) se aude. Acelasi petic 0006, peste 0005
# (care atinge numai gstdvbvideosink.c). Revizia urca peste ".1" de la 0005; blocul sta la coada fisierului.
SRC_URI:append:h8se = " file://0006-dvbaudiosink-pcm-recodat-in-mp3.patch"
CFLAGS:append:h8se = " -DHDS_PCM_MP3"
RDEPENDS:${PN}:append:h8se = " libmp3lame"
PR:append:h8se = ".1"

do_compile:append:h8se() {
	grep -q 'hds-pcm-mp3' ${S}/gstdvbaudiosink.c || bbfatal "dvbmediasink: peticul PCM recodat in MP3 lipseste"
	grep -aq 'hds-pcm-mp3: codor deschis' ${B}/.libs/libgstdvbaudiosink.so || bbfatal "dvbmediasink: codul HDS_PCM_MP3 nu e in libgstdvbaudiosink.so"
}

# H.264 intretesut cu cele doua campuri separate (PAFF) in care al doilea camp poarta PTS-ul primului (canale SD de internet):
# GStreamer 1.28 da sink-ului H.264-ul din TS ca avc (tsdemux nu spune alignment, iar h264parse fixeaza prima forma a capsurilor
# sink-ului), iar al doilea camp al cadrelor de referinta vine fara PTS. render() inlocuia lungimile NAL cu start code numai la
# bufferele cu PTS, deci decodorul pierdea campul: blocuri pe toata imaginea (masurat pe H8.2H Plus, pe Viper 4K V20 si pe Octagon
# SF8008; acelasi flux ca byte-stream era curat pe toate trei). Peticul 0007 le inlocuieste in orice buffer; PES-ul fara PTS ramane
# fara PTS. Facut pe aceeasi sursa fixata, dupa 0001 si 0002; atinge numai render() din gstdvbvideosink.c, cod comun tuturor
# masinilor (nimic din el nu tine de driver), deci e pe toate; pe Broadcom (Vu+, Dreambox, GigaBlue) nemasurat inca pe receptor.
SRC_URI:append = " file://0007-dvbvideosink-lungimi-nal-si-fara-pts.patch"
PR:append = ".1"

do_compile:append() {
	grep -q 'if (has_timestamp ||' ${S}/gstdvbvideosink.c || bbfatal "dvbmediasink: peticul lungimilor NAL fara PTS lipseste"
}

# Prima secunda dupa pornire sau zap pe acelasi H.264 pe campuri: tsdemux incepe segmentul la primul PTS, iar campul al doilea al
# primului IDR (fara PTS, cu DTS-ul inaintea segmentului) era aruncat de basesink, care taie dupa DTS cand lipseste PTS-ul: tot primul
# GOP avea blocuri (masurat pe Octagon SF8008: un singur buffer video aruncat, "out of clipping segment"). Peticul 0008 pastreaza
# bufferul fara PTS cand cel cu PTS dinaintea lui a ramas (ii sterge DTS-ul, nefolosit de render() fara use_dts); PES-ul scris ramane
# acelasi. Facut pe aceeasi sursa fixata, dupa 0007; atinge numai gstdvbvideosink.c/.h, pe toate masinile.
SRC_URI:append = " file://0008-dvbvideosink-camp-fara-pts-pastrat.patch"
PR:append = ".1"

do_compile:append() {
	grep -q 'gst_dvbvideosink_camp_fara_pts' ${S}/gstdvbvideosink.c || bbfatal "dvbmediasink: peticul campului fara PTS pastrat lipseste"
}

# ZGEMMA H8.2H Plus (h8): placa nu decodeaza Dolby (DLB1, 25.11.2026, masurat pe receptor: in bibliotecile platformei AC3 apare numai
# ca AC3PASSTHROUGH, E-AC-3 deloc; canalul ZDF HD pe pista AC-3 si fisierele AC-3 / E-AC-3 raman mute, iar fisierele nu ajung la
# sfarsit, pe PCM si pe trecere directa). Peticul 0009 scoate audio/x-ac3 si audio/x-eac3 din capsurile sink-ului cu HDS_FARA_DOLBY,
# deci playbin pune decodorul din FFmpeg (avdec_ac3, avdec_eac3, din 0.8.0) si sunetul vine ca PCM, recodat in MP3 de 0006. Numai pe
# h8: pe Octagon SF8008 placa decodeaza AC-3 si E-AC-3 (decodorul producatorului), iar pe h8se nu s-a masurat. Canalele DVB nu trec
# prin GStreamer, deci nu se schimba aici. Atinge numai gstdvbaudiosink.c, dupa 0006.
SRC_URI:append:h8 = " file://0009-dvbaudiosink-fara-dolby-pe-h8.patch"
CFLAGS:append:h8 = " -DHDS_FARA_DOLBY"
RDEPENDS:${PN}:append:h8 = " gstreamer1.0-libav"
PR:append:h8 = ".1"

do_compile:append:h8() {
	grep -q 'HDS_FARA_DOLBY' ${S}/gstdvbaudiosink.c || bbfatal "dvbmediasink: peticul fara Dolby (DLB1) lipseste"
	if grep -aq 'audio/x-eac3, framed' ${B}/.libs/libgstdvbaudiosink.so; then
		bbfatal "dvbmediasink: libgstdvbaudiosink.so mai ofera audio/x-eac3 in capsuri pe h8"
	fi
}
