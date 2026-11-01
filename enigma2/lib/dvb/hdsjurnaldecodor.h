/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsjurnaldecodor.h: jurnalul decodoarelor video si audio (/home/root/logs/hds-decodor.log, forma din
 * lib/base/hdsjurnal.h), chemat din decoder.cpp.
 *
 * CE SE SCRIE (numai date tehnice):
 *   EROARE  dispozitivul care nu se deschide, sursa DEMUX refuzata (placile cu libreader), codecul refuzat de driver
 *           (VIDEO_SET_STREAMTYPE, AUDIO_SET_BYPASS_MODE), filtrul PES refuzat, pornirea refuzata (VIDEO_PLAY,
 *           AUDIO_PLAY), cu errno; acelasi fel de eroare cel mult o data la 10 s (cele sarite se numara).
 *   INFO    sursa DEMUX aleasa (o data pe dispozitiv in procesul de acum), marimea imaginii, cadrele pe secunda,
 *           imaginea progresiva sau intretesuta si gama (SDR, HDR, HDR10, HLG), numai cand se schimba fata de randul
 *           de dinainte (zap-urile intre canale la fel nu scriu nimic).
 * Exemplu: "2026-10-29T08:14:05Z [INFO] [video] video0 imagine 1920x1080 16:9"
 *
 * Scris de la zero pentru imaginea HD Satelit.
 */
#ifndef __lib_dvb_hdsjurnaldecodor_h
#define __lib_dvb_hdsjurnaldecodor_h

namespace hdsjdecodor
{

/* dispozitiv = "video" sau "audio"; ce = apelul refuzat; codec = numele codecului, 0 daca nu e cazul */
void eroare(const char *dispozitiv, int dev, const char *ce, int err, const char *codec = 0);
void sursaDemux(const char *dispozitiv, int dev);
/* evenimentele decodorului video: tip 1 marimea (latime, inaltime, aspect 2 = 4:3, 3 = 16:9), 2 cadrele (in miimi pe
   secunda), 16 progresiva (0/1), 17 gama (0 SDR, 1 HDR, 2 HDR10, 3 HLG) */
void evenimentVideo(int dev, int tip, int a, int b, int c);
const char *numeVideo(int tip);
const char *numeAudio(int tip);

}

#endif
