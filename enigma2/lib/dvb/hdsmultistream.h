/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsmultistream.h: multistream DVB-S2 (fluxul ales si secventa PLS) pentru tunerul de satelit. Numai functii pure,
 * fara enigma2, ca sa se probeze singure, pe PC.
 *
 * Valorile, la fel in structura eDVBFrontendParametersSatellite, in lamedb, in satellites.xml si in Python:
 *   is_id     0..255 = fluxul ales (Input Stream Identifier); -1 = fara filtru (orice alta valoare devine -1);
 *   pls_mode  0 Root, 1 Gold, 2 Combo (Combo se acordeaza ca Gold);
 *   pls_code  18 biti. Secventa implicita are trei scrieri: Gold 0, Root 1 si Root 0 (Root 0 nu e o radacina buna,
 *             dar o scriu listele care nu au PLS); toate inseamna „fara PLS".
 * Codul Gold n si radacina sunt doua scrieri ale aceleiasi secvente x din EN 302 307 (5.5.4): x(i+18) = x(i+7) xor
 * x(i), cu x(0) = 1 si x(1..17) = 0. Radacina lui n e registrul dupa n pasi, bitul k fiind x(n+k). Perioada e 2^18 - 1.
 *
 * Ce primeste driverul:
 *   - pana la DVB API 5.10 o singura proprietate, DTV_STREAM_ID = ISI | Gold << 8 | mod << 26. Modul trimis e mereu
 *     Gold (1): driverul tunerului u57 nu reinitializeaza secventa cand primeste Root cu ISI 0. Valorile 0 si
 *     0xFFFFFFFF inseamna „fara filtru si fara PLS", deci cu PLS si fara ISI se trimite ISI 0 (cu modul Gold pus,
 *     valoarea nu poate fi 0);
 *   - de la 5.11 PLS-ul are proprietatea lui (DTV_SCRAMBLING_SEQUENCE_INDEX, codul Gold), iar DTV_STREAM_ID e numai
 *     ISI-ul (sau NO_STREAM_ID_FILTER).
 * Pe un nucleu 5.10 proprietatea 70 nu exista si face sa cada tot apelul FE_SET_PROPERTY (acordul nu se mai face),
 * iar antetele din sysroot pot fi mai noi decat nucleul de pe receptor: forma se alege dupa versiunea citita din
 * frontend (DTV_API_VERSION), nu dupa antete.
 */

#ifndef __lib_dvb_hdsmultistream_h
#define __lib_dvb_hdsmultistream_h

#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

namespace hdsms
{
	enum
	{
		ISI_FARA_FILTRU = -1,
		MOD_ROOT = 0,
		MOD_GOLD = 1,
		MOD_COMBO = 2,
		PLS_MASCA = 0x3FFFF,
		PLS_PERIOADA = 262143,           /* 2^18 - 1 */
		API_PLS_SEPARAT = 0x050B,        /* 5.11: DTV_SCRAMBLING_SEQUENCE_INDEX exista */
		PROPRIETATE_PLS = 70,            /* DTV_SCRAMBLING_SEQUENCE_INDEX */
		T2MI_FARA_PLP = -1,
		T2MI_PID_IMPLICIT = 4096,
		CAP_MULTISTREAM = 0x4000000,     /* FE_CAN_MULTISTREAM din caps (FE_GET_INFO); in antete e membru de enum */
	};

	/* 0..255 raman, orice altceva (si 0xFFFFFFFF citit ca intreg) e „fara filtru" */
	inline int isiNormalizat(int is_id)
	{
		return (is_id >= 0 && is_id <= 255) ? is_id : ISI_FARA_FILTRU;
	}

	inline unsigned int pasRegistru(unsigned int s)
	{
		unsigned int nou = (s ^ (s >> 7)) & 1;
		return (s >> 1) | (nou << 17);
	}

	/* codul Gold -> radacina; -1 pentru un cod din afara perioadei */
	inline int radacinaDinGold(int gold)
	{
		if (gold < 0 || gold >= PLS_PERIOADA)
			return -1;
		unsigned int s = 1;
		for (int i = 0; i < gold; ++i)
			s = pasRegistru(s);
		return (int)s;
	}

	/* radacina -> codul Gold; -1 pentru 0 sau o valoare de peste 18 biti */
	inline int goldDinRadacina(int radacina)
	{
		if (radacina <= 0 || radacina > PLS_MASCA)
			return -1;
		unsigned int s = 1;
		for (int n = 0; n < PLS_PERIOADA; ++n)
		{
			if (s == (unsigned int)radacina)
				return n;
			s = pasRegistru(s);
		}
		return -1;
	}

	/* codul Gold al secventei ceruta: 0 pentru secventa implicita (si pentru Root 0), -1 pentru un cod care nu se poate
	   folosi (Root peste 18 biti, Gold peste perioada) */
	inline int codGold(int pls_mode, int pls_code)
	{
		if (pls_code < 0)
			return -1;
		if (pls_mode == MOD_ROOT)
		{
			if (pls_code == 0 || pls_code == 1)
				return 0;
			return goldDinRadacina(pls_code);
		}
		if (pls_mode == MOD_GOLD || pls_mode == MOD_COMBO)
			return pls_code < PLS_PERIOADA ? pls_code : -1;
		return -1;
	}

	/* secventa implicita, in oricare din scrierile ei */
	inline bool plsImplicit(int pls_mode, int pls_code)
	{
		return codGold(pls_mode, pls_code) == 0;
	}

	/* transponderul cere filtrul de flux sau o secventa PLS: numai atunci se trimite ceva driverului */
	inline bool cereFlux(int is_id, int pls_mode, int pls_code)
	{
		return isiNormalizat(is_id) != ISI_FARA_FILTRU || !plsImplicit(pls_mode, pls_code);
	}

	/* fluxul ca o pereche comparabila: (ISI sau -1, codul Gold sau -1 pentru un cod rau) */
	struct Cheie
	{
		int isi;
		int gold;
	};

	inline Cheie cheie(int is_id, int pls_mode, int pls_code)
	{
		Cheie c;
		c.isi = isiNormalizat(is_id);
		c.gold = codGold(pls_mode, pls_code);
		return c;
	}

	inline bool acelasiFlux(const Cheie &a, const Cheie &b)
	{
		return a.isi == b.isi && a.gold == b.gold;
	}

	/* codul Gold de trimis: un cod rau (Root peste 18 biti, Gold peste perioada) cade pe secventa implicita, ca ISI-ul
	   sa ajunga totusi la driver */
	inline int goldDeTrimis(int pls_mode, int pls_code)
	{
		int gold = codGold(pls_mode, pls_code);
		return gold < 0 ? 0 : gold;
	}

	/* DTV_STREAM_ID pentru API 5.10: ISI | Gold << 8 | 1 << 26 (modul Gold). Fara nimic de cerut: 0xFFFFFFFF, adica
	   fara filtru. */
	inline uint32_t streamIdImpachetat(int is_id, int pls_mode, int pls_code)
	{
		int gold = goldDeTrimis(pls_mode, pls_code);
		int isi = isiNormalizat(is_id);
		if (isi == ISI_FARA_FILTRU && gold == 0)
			return 0xFFFFFFFFU;
		if (isi == ISI_FARA_FILTRU)
			isi = 0;
		return (uint32_t)(isi & 0xFF) | ((uint32_t)(gold & PLS_MASCA) << 8) | ((uint32_t)MOD_GOLD << 26);
	}

	/* DTV_STREAM_ID pentru API 5.11 si mai nou: numai ISI-ul */
	inline uint32_t streamIdSeparat(int is_id)
	{
		int isi = isiNormalizat(is_id);
		return isi == ISI_FARA_FILTRU ? 0xFFFFFFFFU : (uint32_t)isi;
	}

	/* versiunea DVB API citita din frontend (major << 8 | minor); 0 = necitita, se ia forma veche */
	inline bool plsSeparat(int versiune_api)
	{
		return versiune_api >= API_PLS_SEPARAT;
	}

	/* Randul unui transponder de satelit din lamedb, fara „\ts " din fata:
	     /4/  frecventa:sr:pol:fec:pozitie:inversare:steaguri[:sistem:modulatie:rolloff:pilot[:is_id:pls_code:pls_mode
	          [:t2mi_plp_id:t2mi_pid]]]
	     /3/  la fel, fara steaguri.
	   Pozitia vestica e scrisa cu minus (-50 = 5,0 V), in structura 3550. Campurile T2-MI sunt numai date (lamedb,
	   afisare): driverul nu le foloseste, iar decapsularea T2-MI se face in Hds/DabT2. */
	struct LinieSatelit
	{
		int frequency, symbol_rate, polarisation, fec, orbital_position, inversion, flags;
		int system, modulation, rolloff, pilot;
		int is_id, pls_mode, pls_code, t2mi_plp_id, t2mi_pid;
	};

	inline void impliciteMultistream(LinieSatelit &l)
	{
		l.is_id = ISI_FARA_FILTRU;
		l.pls_mode = MOD_GOLD;
		l.pls_code = 0;
		l.t2mi_plp_id = T2MI_FARA_PLP;
		l.t2mi_pid = T2MI_PID_IMPLICIT;
	}

	/* intoarce cate valori s-au citit (cel putin 6 pentru un rand bun); ce lipseste ramane implicit. Sistemul:
	   0 DVB-S, 1 DVB-S2; modulatia 1 QPSK; rolloff 0 (0,35); pilot 2 (necunoscut). Un rand cu flux sau PLS si cu
	   sistemul DVB-S trece pe DVB-S2 (multistream exista numai in DVB-S2). */
	inline int citesteLinieSatelit(const char *text, int versiune, LinieSatelit &l)
	{
		l.frequency = l.symbol_rate = l.polarisation = l.fec = l.orbital_position = l.inversion = 0;
		l.flags = 0;
		l.system = 0;
		l.modulation = 1;
		l.rolloff = 0;
		l.pilot = 2;
		impliciteMultistream(l);
		int n;
		if (versiune == 3)
			n = sscanf(text, "%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d", &l.frequency, &l.symbol_rate,
				&l.polarisation, &l.fec, &l.orbital_position, &l.inversion, &l.system, &l.modulation, &l.rolloff,
				&l.pilot, &l.is_id, &l.pls_code, &l.pls_mode, &l.t2mi_plp_id, &l.t2mi_pid);
		else
			n = sscanf(text, "%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d", &l.frequency, &l.symbol_rate,
				&l.polarisation, &l.fec, &l.orbital_position, &l.inversion, &l.flags, &l.system, &l.modulation,
				&l.rolloff, &l.pilot, &l.is_id, &l.pls_code, &l.pls_mode, &l.t2mi_plp_id, &l.t2mi_pid);
		if (l.orbital_position < 0)
			l.orbital_position += 3600;
		l.is_id = isiNormalizat(l.is_id);
		l.pls_code &= PLS_MASCA;
		l.pls_mode &= 3;
		if (l.t2mi_plp_id < 0 || l.t2mi_plp_id > 255)
			l.t2mi_plp_id = T2MI_FARA_PLP;
		if (l.t2mi_pid <= 0 || l.t2mi_pid > 0x1FFE)
			l.t2mi_pid = T2MI_PID_IMPLICIT;
		if (l.system == 0 && cereFlux(l.is_id, l.pls_mode, l.pls_code))
			l.system = 1;
		return n;
	}

	/* randul /4/ (fara „\ts " si fara sfarsitul de rand); campurile DVB-S2 numai la DVB-S2, cele multistream numai
	   cand difera de implicit sau cand urmeaza T2-MI, T2-MI numai cand are PLP. -> lungimea scrisa (snprintf). */
	inline int scrieLinieSatelit(char *buf, size_t marime, const LinieSatelit &l)
	{
		int pozitie = l.orbital_position > 1800 ? l.orbital_position - 3600 : l.orbital_position;
		bool flux = cereFlux(l.is_id, l.pls_mode, l.pls_code);
		bool t2mi = l.t2mi_plp_id >= 0 && l.t2mi_plp_id <= 255;
		bool s2 = l.system == 1 || flux || t2mi;
		int n = snprintf(buf, marime, "%d:%d:%d:%d:%d:%d:%d", l.frequency, l.symbol_rate, l.polarisation, l.fec,
			pozitie, l.inversion, l.flags);
		if (!s2 || n < 0 || (size_t)n >= marime)
			return n;
		n += snprintf(buf + n, marime - n, ":%d:%d:%d:%d", 1, l.modulation, l.rolloff, l.pilot);
		if ((!flux && !t2mi) || (size_t)n >= marime)
			return n;
		n += snprintf(buf + n, marime - n, ":%d:%d:%d", isiNormalizat(l.is_id), l.pls_code & PLS_MASCA,
			l.pls_mode & 3);
		if (!t2mi || (size_t)n >= marime)
			return n;
		n += snprintf(buf + n, marime - n, ":%d:%d", l.t2mi_plp_id, l.t2mi_pid);
		return n;
	}
}

#endif
