# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Optiunile sink-urilor receptorului, peste DVBMEDIASINK_CONFIG al masinii:
# - fara --with-wma: driverul nu are decodor WMA, deci sunetul WMA 1/2 nu se trimite comprimat placii; il decodeaza pe
#   procesor gstreamer1.0-libav (peste FFmpeg-ul LGPL al imaginii) si placa primeste PCM;
# - --with-aac-loas: AAC in LOAS/LATM (filme si fluxuri IPTV) merge la decodorul placii ca AAC HE, acelasi decodor care
#   reda AAC-ul canalelor; in imagine nu intra niciun decodor AAC;
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
