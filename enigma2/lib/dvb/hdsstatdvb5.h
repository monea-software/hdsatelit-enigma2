/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsstatdvb5.h: nivelul, calitatea si erorile semnalului din statisticile DVBv5 (FE_GET_PROPERTY: DTV_STAT_CNR,
 * DTV_STAT_SIGNAL_STRENGTH, DTV_STAT_POST_ERROR_BIT_COUNT, DTV_STAT_ERROR_BLOCK_COUNT), pentru driverele care nu mai
 * raspund la citirile vechi FE_READ_SNR / FE_READ_SIGNAL_STRENGTH / FE_READ_BER.
 *
 * DE CE (XBS8, 22.11.2026; forumul 801, Vu+ Uno 4K SE 0.7.7): tunerul USB Xbox One DVB-T2 (demodulatorul mn88472,
 * tunerul tda18250) arata puterea si calitatea 0 %, desi imaginea e buna. Driverul mn88472 (si in Linux 4.12+, si in
 * nucleul Vu+ 4.1 dupa peticul din stratul nostru, mn88472-dvbv5-statistici.patch) da valorile numai prin DTV_STAT_*;
 * citirile vechi intorc EOPNOTSUPP.
 *
 * CE FACE: numai cand citirea veche a dat eroare, eDVBFrontend::hdsCitesteBrut (lib/dvb/frontend.cpp) cere aici
 * statistica DVBv5 si o aduce la scara pe care o asteapta restul imaginii:
 *   calitatea: FE_SCALE_DECIBEL (miimi de dB) -> sutimi de dB (cum da hdscal::calitateTuner, lib/dvb/hdscalitate.h);
 *              procentul se face apoi ca la celelalte tunere cu formula (ter_max 24 dB, cab_max 42 dB, sat_max 16 dB);
 *   nivelul:   FE_SCALE_RELATIVE (0..65535) -> la fel ca FE_READ_SIGNAL_STRENGTH (0..65535);
 *   erorile:   FE_SCALE_COUNTER (contor care tot creste) -> cate au venit de la citirea trecuta, ca FE_READ_BER la
 *              majoritatea driverelor; intai bitii gresiti dupa corectie, altfel blocurile (pachetele) gresite.
 * Tunerele care raspund la citirile vechi nu trec pe aici: purtarea lor ramane aceeasi.
 *
 * Fara nimic din enigma2 (ioctl-ul se da ca parametru), ca sa se probeze pe PC.
 *
 * Scris de la zero pentru imaginea HD Satelit.
 */
#ifndef __lib_dvb_hdsstatdvb5_h
#define __lib_dvb_hdsstatdvb5_h

#include <errno.h>
#include <string.h>
#include <stdint.h>
#include <sys/ioctl.h>
#include <linux/dvb/frontend.h>

namespace hdsstat
{

/* contorul de erori: cat a crescut de la citirea trecuta (prima citire: 0) */
struct Contor
{
	bool are;
	unsigned long long ultim;
	Contor(): are(false), ultim(0) {}
	unsigned int crestere(unsigned long long acum)
	{
		unsigned long long d = (are && acum >= ultim) ? acum - ultim : 0;
		are = true;
		ultim = acum;
		return d > 0xffffffffULL ? 0xffffffffU : (unsigned int)d;
	}
};

/* starea pe tuner: de unde a venit ultima calitate si contoarele erorilor */
struct Stare
{
	bool snr_dvb5;   // ultima citire a calitatii a venit din DTV_STAT_CNR (deci e deja in sutimi de dB)
	Contor biti, blocuri;
	Stare(): snr_dvb5(false) {}
	void goleste() { snr_dvb5 = false; biti = Contor(); blocuri = Contor(); }
};

#if defined(DTV_STAT_CNR) && defined(DTV_STAT_SIGNAL_STRENGTH) && defined(DTV_STAT_ERROR_BLOCK_COUNT)

/* miimi de dB (FE_SCALE_DECIBEL) -> sutimi de dB, intre 0 si 65535 */
inline bool calitateSutimiDb(const struct dtv_stats &s, unsigned int &v)
{
	if (s.scale != FE_SCALE_DECIBEL)
		return false;
	long long x = s.svalue / 10;
	v = x < 0 ? 0 : (x > 65535 ? 65535 : (unsigned int)x);
	return true;
}

/* FE_SCALE_RELATIVE: 0..65535, ca FE_READ_SIGNAL_STRENGTH */
inline bool nivelRelativ(const struct dtv_stats &s, unsigned int &v)
{
	if (s.scale != FE_SCALE_RELATIVE)
		return false;
	v = s.uvalue > 65535 ? 65535 : (unsigned int)s.uvalue;
	return true;
}

/* o statistica (primul strat); 0 sau errno; EOPNOTSUPP cand driverul nu o da (len 0 sau FE_SCALE_NOT_AVAILABLE) */
template <class Io>
int citeste(Io io, int fd, uint32_t cmd, struct dtv_stats &s)
{
	struct dtv_property p;
	struct dtv_properties seq;
	memset(&p, 0, sizeof(p));
	p.cmd = cmd;
	seq.num = 1;
	seq.props = &p;
	errno = 0;
	if (io(fd, FE_GET_PROPERTY, &seq) < 0)
		return errno ? errno : EIO;
	if (p.u.st.len < 1 || p.u.st.stat[0].scale == FE_SCALE_NOT_AVAILABLE)
		return EOPNOTSUPP;
	s = p.u.st.stat[0];
	return 0;
}

/* calitatea in sutimi de dB; 0 sau errno */
template <class Io>
int calitate(Io io, int fd, unsigned int &v)
{
	struct dtv_stats s;
	int e = citeste(io, fd, DTV_STAT_CNR, s);
	if (e)
		return e;
	return calitateSutimiDb(s, v) ? 0 : EOPNOTSUPP;
}

/* nivelul 0..65535; 0 sau errno */
template <class Io>
int nivel(Io io, int fd, unsigned int &v)
{
	struct dtv_stats s;
	int e = citeste(io, fd, DTV_STAT_SIGNAL_STRENGTH, s);
	if (e)
		return e;
	return nivelRelativ(s, v) ? 0 : EOPNOTSUPP;
}

/* erorile de la citirea trecuta: bitii dupa corectie, altfel blocurile; 0 sau errno */
template <class Io>
int erori(Io io, int fd, Stare &st, unsigned int &v)
{
	struct dtv_stats s;
	if (!citeste(io, fd, DTV_STAT_POST_ERROR_BIT_COUNT, s) && s.scale == FE_SCALE_COUNTER)
	{
		v = st.biti.crestere(s.uvalue);
		return 0;
	}
	int e = citeste(io, fd, DTV_STAT_ERROR_BLOCK_COUNT, s);
	if (e)
		return e;
	if (s.scale != FE_SCALE_COUNTER)
		return EOPNOTSUPP;
	v = st.blocuri.crestere(s.uvalue);
	return 0;
}

#else /* antete DVB fara statistici: nimic de citit */

template <class Io> int calitate(Io, int, unsigned int &) { return EOPNOTSUPP; }
template <class Io> int nivel(Io, int, unsigned int &) { return EOPNOTSUPP; }
template <class Io> int erori(Io, int, Stare &, unsigned int &) { return EOPNOTSUPP; }

#endif

}

#endif
