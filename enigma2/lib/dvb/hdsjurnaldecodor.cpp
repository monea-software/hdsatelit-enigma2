/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsjurnaldecodor.cpp: jurnalul decodoarelor (vezi hdsjurnaldecodor.h). Scris de la zero. Pe firul principal.
 */

#include <lib/dvb/hdsjurnaldecodor.h>

#include <lib/base/hdsjurnal.h>

#include <errno.h>
#include <stdio.h>
#include <string.h>

namespace hdsjdecodor
{

static const char *const COMPONENTA = "decodor";
enum { DISPOZITIVE = 4, FRANA_MS = 10000 };

/* Jurnalizarea pastreaza eroarea driverului, inclusiv la iesirile fara scriere. */
struct PastrareErrno
{
	const int valoare;
	PastrareErrno() : valoare(errno) {}
	~PastrareErrno() { errno = valoare; }
};

const char *numeVideo(int t)
{
	switch (t)
	{
	case 0: return "MPEG2";
	case 1: return "H264";
	case 3: return "VC1";
	case 4: return "MPEG4";
	case 5: return "VC1-SM";
	case 6: return "MPEG1";
	case 7: return "H265";
	case 16: return "AVS";
	default: return "?";
	}
}

const char *numeAudio(int t)
{
	static const char *const T[] = { "MPEG", "AC3", "DTS", "AAC", "HE-AAC", "LPCM", "DTS-HD", "E-AC3" };
	return (t >= 0 && t < 8) ? T[t] : "?";
}

void eroare(const char *dispozitiv, int dev, const char *ce, int err, const char *codec)
{
	PastrareErrno pastreaza;
	static hdsjurnal::Frana frana(FRANA_MS);
	unsigned long sarite = 0;
	if (!frana.lasa(sarite))
		return;
	char sar[48] = "";
	if (sarite)
		snprintf(sar, sizeof(sar), " (%lu erori nescrise inainte)", sarite);
	hdsjurnal::scrief(COMPONENTA, hdsjurnal::EROARE, dispozitiv, "%s%d %s refuzat%s%s: %s (errno %d)%s", dispozitiv, dev,
		ce, codec ? " pentru " : "", codec ? codec : "", strerror(err), err, sar);
}

void sursaDemux(const char *dispozitiv, int dev)
{
	PastrareErrno pastreaza;
	static unsigned int scrise = 0;
	unsigned int bit = (dispozitiv[0] == 'v' ? 1u : 0x100u) << (dev & 7);
	if (scrise & bit)
		return;
	scrise |= bit;
	hdsjurnal::scrief(COMPONENTA, hdsjurnal::INFO, dispozitiv, "%s%d sursa DEMUX aleasa", dispozitiv, dev);
}

struct Ultim
{
	int latime, inaltime, aspect, cadre, progresiv, gama;
};

void evenimentVideo(int dev, int tip, int a, int b, int c)
{
	PastrareErrno pastreaza;
	static Ultim ultim[DISPOZITIVE];
	static int initializat = 0;
	if (!initializat)
	{
		for (int i = 0; i < DISPOZITIVE; ++i)
			ultim[i].latime = ultim[i].inaltime = ultim[i].aspect = ultim[i].cadre = ultim[i].progresiv =
				ultim[i].gama = -1;
		initializat = 1;
	}
	if (dev < 0 || dev >= DISPOZITIVE)
		return;
	Ultim &u = ultim[dev];
	switch (tip)
	{
	case 1:
		if (u.latime == a && u.inaltime == b && u.aspect == c)
			return;
		u.latime = a;
		u.inaltime = b;
		u.aspect = c;
		hdsjurnal::scrief(COMPONENTA, hdsjurnal::INFO, "video", "video%d imagine %dx%d %s", dev, a, b,
			c == 3 ? "16:9" : (c == 2 ? "4:3" : "?"));
		break;
	case 2:
		if (u.cadre == a)
			return;
		u.cadre = a;
		hdsjurnal::scrief(COMPONENTA, hdsjurnal::INFO, "video", "video%d %d.%03d cadre/s", dev, a / 1000, a % 1000);
		break;
	case 16:
		if (u.progresiv == a)
			return;
		u.progresiv = a;
		hdsjurnal::scrief(COMPONENTA, hdsjurnal::INFO, "video", "video%d %s", dev, a ? "progresiva" : "intretesuta");
		break;
	case 17:
	{
		if (u.gama == a)
			return;
		u.gama = a;
		static const char *const G[] = { "SDR", "HDR", "HDR10", "HLG" };
		hdsjurnal::scrief(COMPONENTA, hdsjurnal::INFO, "video", "video%d gama %s", dev, (a >= 0 && a < 4) ? G[a] : "?");
		break;
	}
	default:
		break;
	}
}

}
