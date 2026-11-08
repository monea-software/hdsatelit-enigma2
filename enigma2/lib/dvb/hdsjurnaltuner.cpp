/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsjurnaltuner.cpp: jurnalul tunerelor (vezi hdsjurnaltuner.h). Scris de la zero. Tot ce e aici ruleaza pe firul
 * principal (frontend.cpp), iar scrierea pe disc o face firul din lib/base/hdsjurnal.cpp.
 */

#include <lib/dvb/hdsjurnaltuner.h>

#include <lib/dvb/idvb.h>

#include <stdio.h>
#include <string.h>

namespace hdsjtuner
{

static const char *const COMPONENTA = "tuner";
enum { FRANA_REACORDARE_MS = 30000, FRANA_PIERDUT_MS = 30000, SLOTURI = 16 };

/* tipurile de mai jos au aceleasi valori ca iDVBFrontend (idvb.h); copiate ca fisierul sa se compileze si fara idvb.h */
enum { FE_SAT = 0, FE_CABLU = 1, FE_TERESTRU = 2 };
enum { V_OFF = 0, V_13 = 1, V_18 = 2, V_13_5 = 3, V_18_5 = 4 };

Stare::Stare()
	: pornit_ms(0), reacordare(0), prins_o_data(0), frana_reacordare(FRANA_REACORDARE_MS),
	frana_pierdut(FRANA_PIERDUT_MS)
{
	parametri[0] = lnb[0] = 0;
}

static char litera(int slot)
{
	return (slot >= 0 && slot < 26) ? (char)('A' + slot) : '?';
}

static void adauga(char *buf, size_t n, const char *text)
{
	size_t l = strlen(buf);
	if (l + 1 >= n)
		return;
	snprintf(buf + l, n - l, "%s%s", l ? " " : "", text);
}

/* ------------------------------------------------------------------ detectarea */

static unsigned int s_deschise = 0;  /* bitul slotului: randul de detectare scris */

void deschis(int slot, int dvbid, const char *nume, int tipuri, int multistream, int api)
{
	if (slot < 0 || slot >= SLOTURI || (s_deschise & (1u << slot)))
		return;
	s_deschise |= 1u << slot;
	/* numele de la driver (dvb_frontend_info.name, char[128]): cel mult 63 de semne, fara sa se citeasca dincolo */
	char n[64] = "?";
	if (nume)
	{
		size_t k = 0;
		for (; k < sizeof(n) - 1 && nume[k]; ++k)
			n[k] = nume[k];
		n[k] = 0;
	}
	char sisteme[64] = "";
	if (tipuri & (1 << FE_SAT))
		adauga(sisteme, sizeof(sisteme), "DVB-S/S2");
	if (tipuri & (1 << FE_CABLU))
		adauga(sisteme, sizeof(sisteme), "DVB-C");
	if (tipuri & (1 << FE_TERESTRU))
		adauga(sisteme, sizeof(sisteme), "DVB-T/T2");
	char ver[24] = "";  /* DTV_API_VERSION se citeste numai la tunerele de satelit */
	if (api > 0)
		snprintf(ver, sizeof(ver), " api %d.%d", api >> 8, api & 0xFF);
	hdsjurnal::scrief(COMPONENTA, hdsjurnal::INFO, "detectare", "%c frontend%d \"%s\" sisteme %s%s%s", litera(slot),
		dvbid, n, sisteme[0] ? sisteme : "niciunul", (tipuri & (1 << FE_SAT)) ?
		(multistream ? " multistream da" : " multistream nu") : "", ver);
}

void deschidereCazuta(int slot, int dvbid, int err)
{
	hdsjurnal::scrief(COMPONENTA, hdsjurnal::EROARE, "detectare", "%c frontend%d nu se deschide: %s (errno %d)",
		litera(slot), dvbid, strerror(err), err);
}

/* ------------------------------------------------------------------ parametrii */

static const char *fecSat(int f)
{
	static const char *const T[] = { "auto", "1/2", "2/3", "3/4", "5/6", "7/8", "8/9", "3/5", "4/5", "9/10" };
	if (f >= 0 && f < (int)(sizeof(T) / sizeof(T[0])))
		return T[f];
	return f == 15 ? "fara" : "?";
}

static const char *modSat(int m)
{
	static const char *const T[] = { "auto", "QPSK", "8PSK", "16APSK" };
	return (m >= 0 && m < 4) ? T[m] : "?";
}

static void pozitie(char *buf, size_t n, int orbital)
{
	if (orbital < 0 || orbital > 3600)
		snprintf(buf, n, "?");
	else if (orbital > 1800)
		snprintf(buf, n, "%d.%dW", (3600 - orbital) / 10, (3600 - orbital) % 10);
	else
		snprintf(buf, n, "%d.%dE", orbital / 10, orbital % 10);
}

static void inceput(Stare &s, int reacordare)
{
	s.pornit_ms = hdsjurnal::monotonMs();
	s.reacordare = reacordare;
	s.prins_o_data = 0;
	s.lnb[0] = 0;
}

void textSat(char *buf, size_t n, const eDVBFrontendParametersSatellite &p)
{
	static const char POL[] = { 'H', 'V', 'L', 'R' };
	char poz[16], flux[48] = "";
	pozitie(poz, sizeof(poz), p.orbital_position);
	if (p.is_id >= 0 || p.pls_code > 0)
		snprintf(flux, sizeof(flux), " flux %d pls %d/%d", p.is_id, p.pls_mode, p.pls_code);
	snprintf(buf, n, "%s %s %u %c %u %s %s%s",
		p.system == eDVBFrontendParametersSatellite::System_DVB_S2 ? "DVB-S2" : "DVB-S", modSat(p.modulation),
		p.frequency / 1000, (p.polarisation >= 0 && p.polarisation < 4) ? POL[p.polarisation] : '?', p.symbol_rate / 1000,
		fecSat(p.fec), poz, flux);
}

void textCablu(char *buf, size_t n, const eDVBFrontendParametersCable &p)
{
	static const char *const QAM[] = { "auto", "QAM16", "QAM32", "QAM64", "QAM128", "QAM256" };
	snprintf(buf, n, "DVB-C %u.%03u MHz %u %s", p.frequency / 1000, p.frequency % 1000,
		p.symbol_rate / 1000, (p.modulation >= 0 && p.modulation < 6) ? QAM[p.modulation] : "?");
}

void textTerestru(char *buf, size_t n, const eDVBFrontendParametersTerrestrial &p)
{
	static const char *const LATIME[] = { "8 MHz", "7 MHz", "6 MHz" };
	char latime[24];
	if (p.bandwidth >= 0 && p.bandwidth < 3)
		snprintf(latime, sizeof(latime), "%s", LATIME[p.bandwidth]);
	else
		snprintf(latime, sizeof(latime), "latime %d", p.bandwidth);
	snprintf(buf, n, "DVB-T %u.%03u MHz %s", p.frequency / 1000000, (p.frequency / 1000) % 1000, latime);
}

void acordareSat(Stare &s, int slot, const eDVBFrontendParametersSatellite &p, int reacordare)
{
	(void)slot;
	inceput(s, reacordare);
	textSat(s.parametri, sizeof(s.parametri), p);
}

void acordareCablu(Stare &s, int slot, const eDVBFrontendParametersCable &p, int reacordare)
{
	(void)slot;
	inceput(s, reacordare);
	textCablu(s.parametri, sizeof(s.parametri), p);
}

void acordareTerestru(Stare &s, int slot, const eDVBFrontendParametersTerrestrial &p, int reacordare)
{
	(void)slot;
	inceput(s, reacordare);
	textTerestru(s.parametri, sizeof(s.parametri), p);
}

/* ------------------------------------------------------------------ secventa LNB */

static void lnb(Stare &s, const char *text)
{
	/* comenzile repetate (DiSEqC cu repetari) se scriu o singura data */
	size_t l = strlen(s.lnb), t = strlen(text);
	if (l >= t && !strcmp(s.lnb + l - t, text) && (l == t || s.lnb[l - t - 1] == ' '))
		return;
	adauga(s.lnb, sizeof(s.lnb), text);
}

void tensiune(Stare &s, int v)
{
	static const char *const T[] = { "0V", "13V", "18V", "14V", "19V" };
	lnb(s, (v >= V_OFF && v <= V_18_5) ? T[v] : "V?");
}

void ton(Stare &s, int t)
{
	lnb(s, t ? "22k" : "fara22k");
}

void toneburst(Stare &s, int b)
{
	lnb(s, b ? "toneburstB" : "toneburstA");
}

void diseqc(Stare &s, const unsigned char *d, int len)
{
	char t[64];
	if (len >= 4 && d[0] == 0x70)
		snprintf(t, sizeof(t), "JESS UB%d", (d[1] >> 3) + 1);
	else if (len >= 3 && (d[0] & 0xFC) == 0xE0)
	{
		unsigned char adr = d[1], cmd = d[2];
		if (adr >= 0x30 && adr <= 0x32 && cmd >= 0x60 && cmd <= 0x6F)
			snprintf(t, sizeof(t), "motor");  /* amanuntele in hds-motor.log */
		else if (cmd == 0x38 && len >= 4)
			snprintf(t, sizeof(t), "DiSEqC1.0 port %d", ((d[3] >> 2) & 3) + 1);
		else if (cmd == 0x39 && len >= 4)
			snprintf(t, sizeof(t), "DiSEqC1.1 port %d", (d[3] & 0x0F) + 1);
		else if (cmd == 0x5A && len >= 4)
			snprintf(t, sizeof(t), "Unicable UB%d", ((d[3] >> 5) & 7) + 1);
		else if (cmd == 0x5B)
			snprintf(t, sizeof(t), "Unicable oprit");
		else if (cmd == 0x00)
			snprintf(t, sizeof(t), "DiSEqC reset");
		else if (cmd == 0x03)
			snprintf(t, sizeof(t), "DiSEqC pornit");
		else
		{
			int n = snprintf(t, sizeof(t), "DiSEqC");
			for (int i = 0; i < len && i < 6 && n > 0 && n < (int)sizeof(t) - 3; ++i)
				n += snprintf(t + n, sizeof(t) - n, " %02X", d[i]);
		}
	}
	else
		snprintf(t, sizeof(t), "DiSEqC? %d octeti", len);
	lnb(s, t);
}

/* ------------------------------------------------------------------ rezultatul */

static long durata(const Stare &s)
{
	return s.pornit_ms ? (long)(hdsjurnal::monotonMs() - s.pornit_ms) : -1;
}

void prins(Stare &s, int slot, int snr_db100)
{
	if (!s.pornit_ms)
		return;
	long ms = durata(s);
	s.pornit_ms = 0;
	s.prins_o_data = 1;
	unsigned long sarite = 0;
	if (s.reacordare && !s.frana_reacordare.lasa(sarite))
		return;
	char snr[32] = "";
	if (snr_db100 >= 0 && snr_db100 <= 6000)  /* 0..60 dB; altceva (unele drivere dau o valoare de umplutura) nescris */
		snprintf(snr, sizeof(snr), " snr %d.%02d dB", snr_db100 / 100, snr_db100 % 100);
	char sar[48] = "";
	if (sarite)
		snprintf(sar, sizeof(sar), " (%lu reacordari nescrise)", sarite);
	hdsjurnal::scrief(COMPONENTA, hdsjurnal::INFO, "acordare", "%c %s | lnb %s | semnal in %ld ms%s%s%s", litera(slot),
		s.parametri, s.lnb[0] ? s.lnb : "-", ms, snr, s.reacordare ? " dupa semnal pierdut" : "", sar);
}

/* nivelul semnalului in procente (FE_READ_SIGNAL_STRENGTH da 0..65535); gol cand nu se stie */
static void textNivel(char *buf, size_t n, int nivel)
{
	buf[0] = 0;
	if (nivel >= 0 && nivel <= 65535)
		snprintf(buf, n, " nivel %d%%", (nivel * 100 + 32767) / 65535);
}

void faraSemnal(Stare &s, int slot, int status, int nivel)
{
	if (!s.pornit_ms)
		return;
	long ms = durata(s);
	s.pornit_ms = 0;
	unsigned long sarite = 0;
	if (s.reacordare && !s.frana_reacordare.lasa(sarite))
		return;
	char st[96] = "";
	if (status >= 0)  /* FE_HAS_SIGNAL 0x01, CARRIER 0x02, VITERBI 0x04, SYNC 0x08, LOCK 0x10 */
		snprintf(st, sizeof(st), " stare semnal=%d purtatoare=%d viterbi=%d sincronizare=%d", !!(status & 1),
			!!(status & 2), !!(status & 4), !!(status & 8));
	char niv[24];
	textNivel(niv, sizeof(niv), nivel);
	char sar[48] = "";
	if (sarite)
		snprintf(sar, sizeof(sar), " (%lu reacordari nescrise)", sarite);
	hdsjurnal::scrief(COMPONENTA, hdsjurnal::AVERT, "acordare", "%c %s | lnb %s | fara semnal dupa %ld ms%s%s%s%s",
		litera(slot), s.parametri, s.lnb[0] ? s.lnb : "-", ms, st, niv, s.reacordare ? " dupa semnal pierdut" : "", sar);
}

void pierdut(Stare &s, int slot)
{
	if (!s.prins_o_data)
		return;
	s.prins_o_data = 0;
	unsigned long sarite = 0;
	if (!s.frana_pierdut.lasa(sarite))
		return;
	char sar[48] = "";
	if (sarite)
		snprintf(sar, sizeof(sar), " (%lu pierderi nescrise)", sarite);
	hdsjurnal::scrief(COMPONENTA, hdsjurnal::AVERT, "semnal", "%c semnal pierdut pe %s%s", litera(slot), s.parametri, sar);
}

void refuzat(Stare &s, int slot, const char *apel, int err)
{
	hdsjurnal::scrief(COMPONENTA, hdsjurnal::EROARE, "acordare", "%c %s refuzat de driver: %s (errno %d) | %s",
		litera(slot), apel, strerror(err), err, s.parametri);
}

void sistem(int slot, const char *spre, int err)
{
	if (err)
		hdsjurnal::scrief(COMPONENTA, hdsjurnal::EROARE, "sistem", "%c sistemul %s refuzat de driver: %s (errno %d)",
			litera(slot), spre, strerror(err), err);
	else
		hdsjurnal::scrief(COMPONENTA, hdsjurnal::INFO, "sistem", "%c trecut pe %s", litera(slot), spre);
}

void textParametri(char *buf, size_t n, iDVBFrontendParameters *p)
{
	int tip = -1;
	snprintf(buf, n, "?");
	if (!p || p->getSystem(tip))
		return;
	if (tip == iDVBFrontend::feSatellite)
	{
		eDVBFrontendParametersSatellite s;
		if (!p->getDVBS(s))
			textSat(buf, n, s);
	}
	else if (tip == iDVBFrontend::feCable)
	{
		eDVBFrontendParametersCable c;
		if (!p->getDVBC(c))
			textCablu(buf, n, c);
	}
	else if (tip == iDVBFrontend::feTerrestrial)
	{
		eDVBFrontendParametersTerrestrial t;
		if (!p->getDVBT(t))
			textTerestru(buf, n, t);
	}
}

}

namespace hdsjscan
{

static const char *const COMPONENTA = "scanare";

/* peste atat, o citire de semnal nu mai e neglijabila fata de citirea tabelelor: scanarea nu mai citeste semnalul */
static const long CITIRE_MAX_MS = 100;

Stare::Stare()
	: pornit_ms(0), tp_ms(0), servicii_inainte(0), fara_citiri(0)
{
	tp[0] = 0;
}

void pornita(Stare &s, size_t transpondere, int steaguri)
{
	s.pornit_ms = hdsjurnal::monotonMs();
	s.tp_ms = 0;
	s.fara_citiri = 0;
	hdsjurnal::scrief(COMPONENTA, hdsjurnal::INFO, "scanare", "pornita: %zu transpondere de cercetat, steaguri 0x%x",
		transpondere, steaguri);
}

void transponder(Stare &s, iDVBFrontendParameters *p, size_t servicii)
{
	if (!s.pornit_ms)
	{
		s.tp_ms = 0;  /* cautarea din fundal: nimic scris */
		return;
	}
	s.tp_ms = hdsjurnal::monotonMs();
	s.servicii_inainte = servicii;
	hdsjtuner::textParametri(s.tp, sizeof(s.tp), p);
}

bool citesteSemnal(const Stare &s)
{
	return s.tp_ms && !s.fara_citiri;
}

void prins(Stare &s, size_t servicii, int snr_db100, int nivel, long citire_ms)
{
	if (!s.tp_ms)
		return;
	char semnal[96] = "";
	if (citire_ms >= 0)
	{
		char snr[32] = "", niv[24];
		if (snr_db100 >= 0 && snr_db100 <= 6000)  /* 0..60 dB, ca la acordare */
			snprintf(snr, sizeof(snr), ", snr %d.%02d dB", snr_db100 / 100, snr_db100 % 100);
		hdsjtuner::textNivel(niv, sizeof(niv), nivel);
		snprintf(semnal, sizeof(semnal), "%s%s%s, citit in %ld ms", snr, niv[0] ? "," : "", niv, citire_ms);
		if (citire_ms > CITIRE_MAX_MS)
			s.fara_citiri = 1;
	}
	hdsjurnal::scrief(COMPONENTA, hdsjurnal::INFO, "transponder", "%s prins, tabele citite in %ld ms, %zu servicii noi%s",
		s.tp, (long)(hdsjurnal::monotonMs() - s.tp_ms), servicii >= s.servicii_inainte ? servicii - s.servicii_inainte : 0,
		semnal);
	s.tp_ms = 0;
}

void faraSemnal(Stare &s)
{
	if (!s.tp_ms)
		return;
	hdsjurnal::scrief(COMPONENTA, hdsjurnal::AVERT, "transponder", "%s fara semnal dupa %ld ms", s.tp,
		(long)(hdsjurnal::monotonMs() - s.tp_ms));
	s.tp_ms = 0;
}

void gata(Stare &s, size_t cercetate, size_t fara_semnal, size_t servicii)
{
	if (!s.pornit_ms)
		return;  /* cautarea din fundal de la fiecare zap (fara pornita): nimic scris */
	hdsjurnal::scrief(COMPONENTA, hdsjurnal::INFO, "scanare", "gata in %ld s: %zu transpondere prinse, %zu fara semnal, "
		"%zu servicii", (long)((hdsjurnal::monotonMs() - s.pornit_ms) / 1000), cercetate, fara_semnal, servicii);
	s.pornit_ms = 0;
}

}
