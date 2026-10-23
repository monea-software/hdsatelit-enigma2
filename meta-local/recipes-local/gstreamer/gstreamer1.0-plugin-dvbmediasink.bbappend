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

PR:append = ".hds1"

do_configure:append() {
	h=${B}/config.h
	[ -f "$h" ] || h=${S}/config.h
	grep -q '^#define HAVE_AAC_LOAS 1' "$h" || bbfatal "dvbmediasink: lipseste HAVE_AAC_LOAS in $h"
	grep -q '^#define HAVE_VB6 1' "$h" || bbfatal "dvbmediasink: lipseste HAVE_VB6 in $h"
	if grep -q '^#define HAVE_WMA 1' "$h"; then
		bbfatal "dvbmediasink: HAVE_WMA e inca pornit"
	fi
}
